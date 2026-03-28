"""MuseDoctor — 持續巡邏員（第六虎將）

職責：每次 tick 推進一個節點，執行 CPU-only 健康掃描。
      CPU 掃描發現異常後，記入 llm_queue 等待 LLM 深挖。
      零 Token 常態巡邏，只在發現異常時才升級到 LLM。

觸發條件：
  - 定時：每 8 分鐘推進一個節點（cron_registry 排程）
  - 熱插隊：trigger_hot(module_ids) — 被改的模組立即插隊
  - 狀態查詢：get_status() — 給 Telegram /patrol 指令

狀態儲存：data/_system/doctor/patrol_state.json（單一寫入者）
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 常數
# ──────────────────────────────────────────────────────────────────────────────
_PATROL_CYCLE_RESET_HOURS = 24   # 超過 N 小時未推進則重置游標
_LOG_SCAN_LINES = 2000           # 每次掃 log 的行數上限
_LOG_ERROR_WINDOW_HOURS = 6      # 只看最近 N 小時的 log
_MAX_LLM_QUEUE = 20              # llm_queue 上限（防膨脹）
_MAX_ANOMALIES_TODAY = 50        # 今日異常記錄上限
_NIGHTLY_PIPELINE_PATH = "src/museon/nightly/nightly_pipeline.py"


class MuseDoctor:
    """持續巡邏員 — CPU-only 健康掃描，每次 tick 一個節點"""

    VERSION = "1.0.0"

    def __init__(self, museon_home: Path | str | None = None):
        self.home = Path(museon_home or "/Users/ZEALCHOU/MUSEON")
        self.src_dir = self.home / "src" / "museon"
        self.logs_dir = self.home / "logs"
        self.doctor_dir = self.home / "data" / "_system" / "doctor"
        self.state_path = self.doctor_dir / "patrol_state.json"
        self.topology_path = self.home / "scripts" / "topology_report.json"

        self.doctor_dir.mkdir(parents=True, exist_ok=True)

        self._state: dict[str, Any] = self._load_state()
        self._node_list: list[str] = []  # lazy build

    # ─────────────────────────── 主入口 ──────────────────────────────────────

    def patrol_tick(self) -> None:
        """主入口 — cron 每 8 分鐘呼叫一次，推進一個節點"""
        try:
            nodes = self._get_node_list()
            if not nodes:
                logger.warning("[MuseDoctor] 節點列表為空，跳過")
                return

            cursor = self._state.get("cursor", 0) % len(nodes)
            module_path = nodes[cursor]

            anomalies = self._cpu_check_node(module_path)

            # 推進游標
            new_cursor = (cursor + 1) % len(nodes)
            cycle_count = self._state.get("cycle_count", 0)
            if new_cursor == 0:
                cycle_count += 1
                logger.info(
                    "[MuseDoctor] 完成第 %d 輪巡邏，共 %d 個節點",
                    cycle_count,
                    len(nodes),
                )

            # 更新狀態
            self._state["cursor"] = new_cursor
            self._state["cycle_count"] = cycle_count
            self._state["last_tick"] = datetime.now(timezone.utc).isoformat()
            self._state["total_nodes"] = len(nodes)

            if anomalies:
                self._record_anomaly(module_path, anomalies)
                logger.info(
                    "[MuseDoctor] %s → 異常 %d 項：%s",
                    module_path,
                    len(anomalies),
                    "; ".join(anomalies[:2]),
                )
            else:
                logger.debug("[MuseDoctor] %s → OK", module_path)

            self._save_state()

        except Exception as e:
            logger.error("[MuseDoctor] patrol_tick error: %s", e, exc_info=True)

    def trigger_hot(self, module_paths: list[str]) -> None:
        """熱插隊 — 將指定模組加到 llm_queue 前端（由外部觸發）"""
        queue: list[str] = self._state.setdefault("llm_queue", [])
        inserted = 0
        for mp in reversed(module_paths):
            if mp not in queue:
                queue.insert(0, mp)
                inserted += 1
        # 截斷上限
        self._state["llm_queue"] = queue[:_MAX_LLM_QUEUE]
        if inserted:
            self._save_state()
            logger.info("[MuseDoctor] 熱插隊 %d 個模組", inserted)

    def get_status(self) -> dict[str, Any]:
        """給 /patrol 指令或 shared_board 讀取的狀態摘要"""
        nodes = self._get_node_list()
        cursor = self._state.get("cursor", 0)
        current = nodes[cursor % len(nodes)] if nodes else "—"
        anomalies_today = self._state.get("anomalies_today", {})
        llm_queue = self._state.get("llm_queue", [])

        return {
            "version": self.VERSION,
            "cursor": cursor,
            "total_nodes": len(nodes),
            "progress_pct": round(cursor / len(nodes) * 100, 1) if nodes else 0,
            "cycle_count": self._state.get("cycle_count", 0),
            "last_tick": self._state.get("last_tick", "—"),
            "current_node": current,
            "anomalies_today_count": len(anomalies_today),
            "llm_queue_count": len(llm_queue),
            "anomalies_today": anomalies_today,
            "llm_queue": llm_queue[:5],  # 只回傳前 5 個
        }

    # ─────────────────────── CPU 健康檢查 ────────────────────────────────────

    def _cpu_check_node(self, module_path: str) -> list[str]:
        """
        CPU-only 健康檢查，返回異常列表（空 = 健康）。

        檢查項目：
        1. 對應的 .py 檔案是否存在
        2. 是否在 broken_imports 清單中
        3. 最近 N 小時的 log 是否有包含此模組名稱的 ERROR
        4. （nightly 模組）是否在 _FULL_STEPS 清單中
        """
        anomalies: list[str] = []

        # 1. 檔案存在？
        file_path = self._module_to_path(module_path)
        if file_path and not file_path.exists():
            anomalies.append(f"檔案不存在: {file_path.relative_to(self.home)}")

        # 2. broken_imports 清單
        broken = self._get_broken_imports()
        for b in broken:
            if b.get("in_module") == module_path:
                anomalies.append(
                    f"broken import: {b['missing_import']}.{b['symbol']}"
                )

        # 3. log ERROR 掃描
        log_errors = self._scan_logs_for_module(module_path)
        if log_errors:
            anomalies.append(f"近期 log ERROR x{log_errors}")

        # 4. nightly 模組：確認在 _FULL_STEPS
        if "nightly" in module_path and module_path not in (
            "museon.nightly.nightly_pipeline",
            "museon.nightly.__init__",
        ):
            step_id = self._infer_nightly_step_id(module_path)
            if step_id and not self._is_in_full_steps(step_id):
                anomalies.append(f"未在 _FULL_STEPS: {step_id}")

        return anomalies

    # ─────────────────────── 內部工具 ────────────────────────────────────────

    def _get_node_list(self) -> list[str]:
        """回傳節點列表（按 fan_in 降序，高風險優先巡邏）"""
        if self._node_list:
            return self._node_list

        # 先取 fan_in_table 的高 fan_in 節點
        high_fi: list[str] = []
        low_fi: list[str] = []

        try:
            if self.topology_path.exists():
                report = json.loads(self.topology_path.read_text())
                fi_table = report.get("fan_in_table", [])
                high_fi = [e["module"] for e in fi_table if e.get("fan_in", 0) >= 2]
        except Exception as e:
            logger.warning("[MuseDoctor] 無法讀 topology_report: %s", e)

        # 再掃 src/ 補上其他模組
        high_fi_set = set(high_fi)
        for py_file in sorted(self.src_dir.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            module = self._path_to_module(py_file)
            if module and module not in high_fi_set:
                low_fi.append(module)

        self._node_list = high_fi + low_fi
        return self._node_list

    def _module_to_path(self, module: str) -> Path | None:
        """將 'museon.doctor.museworker' 轉換為實際 Path"""
        try:
            relative = module.replace("museon.", "", 1).replace(".", "/")
            return self.src_dir / (relative + ".py")
        except Exception:
            return None

    def _path_to_module(self, path: Path) -> str | None:
        """將 Path 轉換為 module 字串"""
        try:
            rel = path.relative_to(self.src_dir)
            parts = list(rel.parts)
            if parts[-1].endswith(".py"):
                parts[-1] = parts[-1][:-3]
            return "museon." + ".".join(parts)
        except Exception:
            return None

    def _get_broken_imports(self) -> list[dict]:
        """從 topology_report 取 broken_imports（帶快取）"""
        cache_attr = "_broken_imports_cache"
        if not hasattr(self, cache_attr):
            try:
                if self.topology_path.exists():
                    report = json.loads(self.topology_path.read_text())
                    setattr(self, cache_attr, report.get("broken_imports", []))
                else:
                    setattr(self, cache_attr, [])
            except Exception:
                setattr(self, cache_attr, [])
        return getattr(self, cache_attr, [])

    def _scan_logs_for_module(self, module: str) -> int:
        """掃描 logs/ 中最近 N 小時是否有包含此模組名稱的 ERROR，返回次數"""
        if not self.logs_dir.exists():
            return 0

        # 模組名稱的最後一段（e.g., 'museworker' from 'museon.doctor.museworker'）
        short_name = module.split(".")[-1]
        cutoff = time.time() - _LOG_ERROR_WINDOW_HOURS * 3600
        error_count = 0

        try:
            for log_file in self.logs_dir.glob("*.log"):
                if log_file.stat().st_mtime < cutoff:
                    continue
                try:
                    lines = log_file.read_text(errors="replace").splitlines()
                    for line in lines[-_LOG_SCAN_LINES:]:
                        if "ERROR" in line and short_name in line:
                            error_count += 1
                except OSError:
                    continue
        except Exception as e:
            logger.debug("[MuseDoctor] log scan error: %s", e)

        return error_count

    def _infer_nightly_step_id(self, module: str) -> str | None:
        """
        從模組名稱推斷 nightly step ID。
        e.g., 'museon.nightly.curiosity_router' → 'curiosity_router'
        """
        return module.split(".")[-1]

    def _is_in_full_steps(self, step_id: str) -> bool:
        """檢查 step_id 是否在 nightly_pipeline._FULL_STEPS 中"""
        try:
            pipeline_path = self.home / _NIGHTLY_PIPELINE_PATH
            if not pipeline_path.exists():
                return True  # 找不到就假設 OK，不誤報
            content = pipeline_path.read_text(errors="replace")
            # 找 _FULL_STEPS = [ ... ] 區塊
            match = re.search(r"_FULL_STEPS\s*=\s*\[([^\]]+)\]", content, re.DOTALL)
            if not match:
                return True
            steps_block = match.group(1)
            return step_id in steps_block
        except Exception:
            return True

    # ─────────────────────── 異常記錄 ────────────────────────────────────────

    def _record_anomaly(self, module: str, anomalies: list[str]) -> None:
        """記錄異常到 state，並加入 llm_queue"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 今日異常清單
        anomalies_today: dict = self._state.setdefault("anomalies_today", {})
        if len(anomalies_today) < _MAX_ANOMALIES_TODAY:
            anomalies_today[module] = {
                "date": today,
                "anomalies": anomalies,
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }

        # llm_queue（不重複加入）
        queue: list[str] = self._state.setdefault("llm_queue", [])
        if module not in queue and len(queue) < _MAX_LLM_QUEUE:
            queue.append(module)

        # 每日重置 anomalies_today
        last_reset = self._state.get("last_anomaly_reset", "")
        if not last_reset.startswith(today):
            self._state["anomalies_today"] = {module: anomalies_today.get(module, {})}
            self._state["last_anomaly_reset"] = today

    # ─────────────────────── 狀態持久化 ──────────────────────────────────────

    def _load_state(self) -> dict[str, Any]:
        try:
            if self.state_path.exists():
                return json.loads(self.state_path.read_text())
        except Exception as e:
            logger.warning("[MuseDoctor] 無法載入狀態: %s", e)
        return {
            "cursor": 0,
            "cycle_count": 0,
            "last_tick": None,
            "llm_queue": [],
            "anomalies_today": {},
            "last_anomaly_reset": "",
            "total_nodes": 0,
        }

    def _save_state(self) -> None:
        try:
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))
            tmp.replace(self.state_path)
        except Exception as e:
            logger.error("[MuseDoctor] 無法儲存狀態: %s", e)
