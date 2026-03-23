"""AnimaChangelog — ANIMA_USER 差分版本追蹤.

Project Epigenesis 迭代 1：讓 ANIMA_USER 的每次變化可追溯。
「什麼時候開始偏好簡潔風格」「信任等級何時升級」「八原語長期趨勢」

設計原則：
- Append-only JSONL（與 Soul Ring 的安全哲學一致）
- 純 hook 式接入——不改 ANIMA_USER 本身的讀寫邏輯
- 寫入失敗不阻斷主流程（降級保護）
- 支援三種查詢：按欄位、按時間、演化摘要

儲存路徑：data/anima/anima_user_changelog.jsonl
格式：{"ts": ISO8601, "diffs": [...], "trigger": "observe_user"}

影響範圍：docs/blast-radius.md 純新增模組（扇入 1: brain.py）
共享狀態：docs/joint-map.md #3 ANIMA_USER.json 新增一個讀取者
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# Changelog 檔案名
CHANGELOG_FILENAME = "anima_user_changelog.jsonl"

# 單次 diff 的最大欄位數（防止首次寫入產生巨大 diff）
MAX_DIFFS_PER_RECORD = 50

# 壓縮閾值：超過此天數的 diff 合併為月摘要
COMPRESSION_THRESHOLD_DAYS = 90

# 查詢時預設回看天數
DEFAULT_LOOKBACK_DAYS = 30

# 忽略的欄位路徑（高頻低價值變化，不記入 changelog）
IGNORED_PATHS = frozenset({
    "relationship.last_interaction",      # 每次都變
    "_pref_buffer",                       # 內部暫存
    "_tone_history",                      # 內部暫存
    "_rc_calibration",                    # 內部校準
    "L8_context_behavior_notes",          # 高頻低價值
})


# ═══════════════════════════════════════════
# Diff 計算
# ═══════════════════════════════════════════

def compute_diff(
    old: Optional[Dict[str, Any]],
    new: Dict[str, Any],
    prefix: str = "",
) -> List[Dict[str, Any]]:
    """遞迴計算兩個 dict 之間的差異.

    只記錄葉節點的變化（不展開 list 內部元素）。

    Args:
        old: 舊版本（None 時視為空 dict）
        new: 新版本
        prefix: 路徑前綴（遞迴用）

    Returns:
        [{"path": "relationship.trust_level", "old": "building", "new": "growing"}, ...]
    """
    if old is None:
        old = {}

    diffs: List[Dict[str, Any]] = []

    all_keys = set(old.keys()) | set(new.keys())

    for key in sorted(all_keys):
        path = f"{prefix}.{key}" if prefix else key

        # 跳過忽略的路徑
        if path in IGNORED_PATHS:
            continue

        old_val = old.get(key)
        new_val = new.get(key)

        if old_val == new_val:
            continue

        # 兩邊都是 dict → 遞迴比較
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            diffs.extend(compute_diff(old_val, new_val, prefix=path))
        else:
            # 葉節點變化（含 list、scalar、None）
            diffs.append({
                "path": path,
                "old": _safe_serialize(old_val),
                "new": _safe_serialize(new_val),
            })

        # 防止首次寫入產生巨量 diff
        if len(diffs) >= MAX_DIFFS_PER_RECORD:
            diffs.append({"path": "_truncated", "old": None, "new": f">{MAX_DIFFS_PER_RECORD} diffs"})
            break

    return diffs


def _safe_serialize(val: Any) -> Any:
    """將值安全序列化為 JSON 可存儲格式.

    大型 list/dict 只記摘要（長度+類型），不記完整內容。
    """
    if val is None:
        return None
    if isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, list):
        if len(val) > 5:
            return f"[list:{len(val)} items]"
        return val
    if isinstance(val, dict):
        if len(val) > 10:
            return f"{{dict:{len(val)} keys}}"
        return val
    return str(val)


# ═══════════════════════════════════════════
# AnimaChangelog
# ═══════════════════════════════════════════

class AnimaChangelog:
    """ANIMA_USER 差分日誌 — append-only JSONL.

    每次 brain._save_anima_user() 時被 hook 調用，
    計算 old vs new 的 diff 並追加一筆記錄。

    設計模式與 DiaryStore（Soul Ring）一致：
    - Append-only（不修改、不刪除）
    - 寫入失敗不阻斷主流程
    - 執行緒安全（threading.Lock）
    """

    def __init__(self, data_dir: str = "data") -> None:
        """初始化 Changelog.

        Args:
            data_dir: 資料根目錄
        """
        self._data_dir = Path(data_dir)
        self._anima_dir = self._data_dir / "anima"
        self._anima_dir.mkdir(parents=True, exist_ok=True)

        self._changelog_path = self._anima_dir / CHANGELOG_FILENAME
        self._lock = threading.Lock()

        logger.info(f"AnimaChangelog initialized | path={self._changelog_path}")

    # ── 寫入（Hook 入口）──────────────────────

    def record(
        self,
        old_data: Optional[Dict[str, Any]],
        new_data: Dict[str, Any],
        trigger: str = "observe_user",
    ) -> int:
        """記錄一筆差分.

        在 brain._save_anima_user() 寫入前被調用。
        計算 diff → 追加到 JSONL。

        Args:
            old_data: 寫入前的 ANIMA_USER（None = 首次）
            new_data: 即將寫入的 ANIMA_USER
            trigger: 觸發來源（observe_user / rename / ceremony）

        Returns:
            記錄的 diff 數量（0 = 無變化，不寫入）
        """
        try:
            diffs = compute_diff(old_data, new_data)

            if not diffs:
                return 0

            record = {
                "ts": datetime.now().isoformat(),
                "trigger": trigger,
                "diff_count": len(diffs),
                "diffs": diffs,
            }

            with self._lock:
                with open(self._changelog_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())

            logger.debug(
                f"AnimaChangelog recorded | trigger={trigger} | "
                f"diffs={len(diffs)}"
            )
            return len(diffs)

        except Exception as e:
            # 降級保護：changelog 失敗不阻斷 ANIMA_USER 寫入
            logger.debug(f"AnimaChangelog record failed (degraded): {e}")
            return 0

    # ── 查詢 API ──────────────────────────────

    def get_changes(
        self,
        field_path: str,
        days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> List[Dict[str, Any]]:
        """查詢特定欄位的變化歷史.

        Args:
            field_path: 欄位路徑（如 "relationship.trust_level"）
            days: 回看天數

        Returns:
            [{"ts": "...", "old": ..., "new": ...}, ...]
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        results = []

        for record in self._read_records():
            if record.get("ts", "") < cutoff:
                continue
            for diff in record.get("diffs", []):
                if diff.get("path") == field_path:
                    results.append({
                        "ts": record["ts"],
                        "trigger": record.get("trigger", "unknown"),
                        "old": diff.get("old"),
                        "new": diff.get("new"),
                    })

        return results

    def get_changes_by_prefix(
        self,
        path_prefix: str,
        days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> List[Dict[str, Any]]:
        """查詢特定路徑前綴下所有欄位的變化.

        Args:
            path_prefix: 路徑前綴（如 "eight_primals"、"seven_layers"）
            days: 回看天數

        Returns:
            [{"ts": "...", "path": "...", "old": ..., "new": ...}, ...]
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        results = []

        for record in self._read_records():
            if record.get("ts", "") < cutoff:
                continue
            for diff in record.get("diffs", []):
                if diff.get("path", "").startswith(path_prefix):
                    results.append({
                        "ts": record["ts"],
                        "trigger": record.get("trigger", "unknown"),
                        "path": diff["path"],
                        "old": diff.get("old"),
                        "new": diff.get("new"),
                    })

        return results

    def get_evolution_summary(self, months: int = 3) -> Dict[str, Any]:
        """從 changelog 萃取使用者的演化摘要.

        Args:
            months: 回看月數

        Returns:
            {
                "period": "2026-01-01 ~ 2026-03-23",
                "total_changes": 142,
                "trust_evolution": [...],
                "primals_trend": {"curiosity": +12, ...},
                "preference_shifts": [...],
                "notable_transitions": [...],
            }
        """
        days = months * 30
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        total_changes = 0
        trust_changes: List[Dict] = []
        primal_changes: Dict[str, List[Tuple[str, Any, Any]]] = {}
        preference_shifts: List[Dict] = []
        notable: List[Dict] = []

        for record in self._read_records():
            if record.get("ts", "") < cutoff:
                continue

            total_changes += record.get("diff_count", 0)

            for diff in record.get("diffs", []):
                path = diff.get("path", "")
                ts = record["ts"]

                # 信任等級變化
                if path == "relationship.trust_level":
                    trust_changes.append({
                        "ts": ts,
                        "from": diff.get("old"),
                        "to": diff.get("new"),
                    })

                # 八原語變化
                elif path.startswith("eight_primals."):
                    primal_name = path.split(".")[-1]
                    primal_changes.setdefault(primal_name, []).append(
                        (ts, diff.get("old"), diff.get("new"))
                    )

                # 偏好變化
                elif path.startswith("preferences."):
                    preference_shifts.append({
                        "ts": ts,
                        "field": path,
                        "from": diff.get("old"),
                        "to": diff.get("new"),
                    })

                # 互動次數里程碑
                elif path == "relationship.total_interactions":
                    old_val = diff.get("old", 0)
                    new_val = diff.get("new", 0)
                    if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                        if int(new_val) % 50 == 0:
                            notable.append({
                                "ts": ts,
                                "type": "milestone",
                                "description": f"累積 {int(new_val)} 次互動",
                            })

        # 計算八原語趨勢（最早值 vs 最新值）
        primals_trend = {}
        for name, changes in primal_changes.items():
            if len(changes) >= 2:
                first_val = changes[0][1]  # old of first change
                last_val = changes[-1][2]  # new of last change
                if isinstance(first_val, (int, float)) and isinstance(last_val, (int, float)):
                    primals_trend[name] = round(last_val - first_val, 1)

        return {
            "period": f"{start_date} ~ {end_date}",
            "total_changes": total_changes,
            "trust_evolution": trust_changes,
            "primals_trend": primals_trend,
            "preference_shifts": preference_shifts[:10],  # 最近 10 筆
            "notable_transitions": notable + trust_changes,
        }

    def get_record_count(self) -> int:
        """取得 changelog 的總記錄數."""
        count = 0
        for _ in self._read_records():
            count += 1
        return count

    # ── 內部方法 ──────────────────────────────

    def _read_records(self) -> List[Dict[str, Any]]:
        """讀取所有 changelog 記錄.

        Returns:
            記錄列表（按時間順序）
        """
        if not self._changelog_path.exists():
            return []

        records = []
        try:
            with open(self._changelog_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.debug(f"AnimaChangelog read failed: {e}")

        return records

    def compress_old_records(self, threshold_days: int = COMPRESSION_THRESHOLD_DAYS) -> int:
        """壓縮超過閾值天數的舊記錄.

        將每天的多筆 diff 合併為單一日摘要。
        由 nightly_pipeline 呼叫。

        Args:
            threshold_days: 壓縮閾值（天）

        Returns:
            壓縮掉的記錄數
        """
        cutoff = (datetime.now() - timedelta(days=threshold_days)).isoformat()

        records = self._read_records()
        if not records:
            return 0

        old_records = [r for r in records if r.get("ts", "") < cutoff]
        recent_records = [r for r in records if r.get("ts", "") >= cutoff]

        if len(old_records) <= 1:
            return 0

        # 按天分組
        daily_groups: Dict[str, List[Dict]] = {}
        for r in old_records:
            day = r.get("ts", "")[:10]  # YYYY-MM-DD
            daily_groups.setdefault(day, []).append(r)

        # 每天合併為一筆摘要
        compressed = []
        for day, group in sorted(daily_groups.items()):
            all_diffs = []
            for r in group:
                all_diffs.extend(r.get("diffs", []))

            # 去重：同一 path 只保留最早的 old 和最新的 new
            path_summary: Dict[str, Dict] = {}
            for d in all_diffs:
                p = d.get("path", "")
                if p not in path_summary:
                    path_summary[p] = {"path": p, "old": d.get("old"), "new": d.get("new")}
                else:
                    path_summary[p]["new"] = d.get("new")

            compressed.append({
                "ts": f"{day}T23:59:59",
                "trigger": "daily_compressed",
                "diff_count": len(path_summary),
                "diffs": list(path_summary.values()),
            })

        # 重寫檔案
        all_new = compressed + recent_records
        removed_count = len(old_records) - len(compressed)

        with self._lock:
            tmp_path = self._changelog_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                for r in all_new:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self._changelog_path)

        logger.info(
            f"AnimaChangelog compressed | removed={removed_count} | "
            f"remaining={len(all_new)}"
        )
        return removed_count
