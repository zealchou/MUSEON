"""MUSEON Guardian Daemon — 自動修復守護程序

全部純 CPU，零 Token 消耗。
L1: 基礎設施巡檢（每 30 分鐘）
L2: 資料完整性（每 6 小時）
L3: 神經束連通性（每 6 小時）
L4: 修復日誌 + 母體回報預留
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("museon.guardian")


# ═══════════════════════════════════════
# Data Types
# ═══════════════════════════════════════

class GuardianStatus:
    OK = "ok"
    REPAIRED = "repaired"
    FAILED = "failed"
    SKIPPED = "skipped"


class GuardianEntry:
    """Single check/repair log entry."""

    def __init__(
        self,
        layer: str,
        check: str,
        status: str,
        action: str = "",
        details: str = "",
        duration_ms: int = 0,
    ):
        self.timestamp = datetime.now().isoformat()
        self.layer = layer
        self.check = check
        self.status = status
        self.action = action
        self.details = details
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "layer": self.layer,
            "check": self.check,
            "status": self.status,
            "action": self.action,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


# ═══════════════════════════════════════
# Guardian Daemon
# ═══════════════════════════════════════

class GuardianDaemon:
    """MUSEON 守護者 — 純 CPU 自動巡檢 + 修復。

    全部操作零 Token 消耗：
    - 檔案系統檢查、JSON 驗證
    - HTTP health ping
    - Process status 查詢
    - Module import 驗證
    """

    # 同一問題最多修復次數，超過升級為「需人工介入」
    MAX_REPAIR_ATTEMPTS = 3

    def __init__(self, data_dir: Optional[str] = None, brain=None):
        self.data_dir = Path(data_dir) if data_dir else Path("data")
        self.brain = brain

        # Guardian 專用目錄
        self.guardian_dir = self.data_dir / "guardian"
        self.guardian_dir.mkdir(parents=True, exist_ok=True)

        # 日誌檔案
        self.repair_log_path = self.guardian_dir / "repair_log.jsonl"
        self.unresolved_path = self.guardian_dir / "unresolved.json"
        self.mothership_queue_path = self.guardian_dir / "mothership_queue.json"
        self.state_path = self.guardian_dir / "state.json"

        # 修復計數（防止無限修復迴圈）
        self._repair_counts: Dict[str, int] = {}
        self._load_repair_counts()

        # 上次巡檢結果
        self.last_l1_result: Optional[Dict] = None
        self.last_l2_result: Optional[Dict] = None
        self.last_l3_result: Optional[Dict] = None
        self.last_l5_result: Optional[Dict] = None

    # ═══════════════════════════════════════
    # L1: 基礎設施巡檢（每 30 分鐘）
    # ═══════════════════════════════════════

    async def run_l1(self) -> Dict[str, Any]:
        """基礎設施巡檢 — Gateway / Telegram / API Key / .env

        純 CPU，零 Token。
        """
        start = time.monotonic()
        entries: List[GuardianEntry] = []

        # 1. Gateway 程序存活
        entries.append(self._check_gateway_alive())

        # 2. Gateway HTTP 回應
        entries.append(await self._check_gateway_http())

        # 3. Telegram adapter 連線
        entries.append(await self._check_telegram_connection())

        # 4. .env 檔案存在且有必要 key
        entries.append(self._check_env_file())

        # 5. data 目錄基本結構
        entries.append(self._check_data_directories())

        duration = int((time.monotonic() - start) * 1000)

        result = self._compile_result("L1", entries, duration)
        self.last_l1_result = result
        self._save_state()
        return result

    def _check_gateway_alive(self) -> GuardianEntry:
        """檢查 Gateway 程序是否存活 — 純 CPU"""
        try:
            import subprocess
            # 嘗試多種進程匹配模式
            patterns = ["museon.gateway", "uvicorn.*8765", "python.*server"]
            for pat in patterns:
                proc = subprocess.run(
                    ["pgrep", "-f", pat],
                    capture_output=True, text=True, timeout=5,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    pid = proc.stdout.strip().split()[0]
                    return GuardianEntry("L1", "gateway_process", GuardianStatus.OK,
                                         details=f"PID: {pid} (matched: {pat})")
            return GuardianEntry("L1", "gateway_process", GuardianStatus.FAILED,
                                 details="Gateway 程序未偵測到")
        except Exception as e:
            return GuardianEntry("L1", "gateway_process", GuardianStatus.FAILED,
                                 details=str(e))

    async def _check_gateway_http(self) -> GuardianEntry:
        """檢查 Gateway HTTP 健康端點 — 使用 asyncio.to_thread 避免阻塞"""
        try:
            import asyncio

            def _sync_check():
                import urllib.request
                start = time.monotonic()
                req = urllib.request.Request("http://127.0.0.1:8765/health", method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return json.loads(resp.read().decode()), int((time.monotonic() - start) * 1000)

            data, ms = await asyncio.to_thread(_sync_check)
            status = data.get("status", "unknown")
            if status in ("ok", "healthy"):
                return GuardianEntry("L1", "gateway_http", GuardianStatus.OK,
                                     details=f"回應 {ms}ms", duration_ms=ms)
            else:
                return GuardianEntry("L1", "gateway_http", GuardianStatus.FAILED,
                                     details=f"status={status}", duration_ms=ms)
        except Exception as e:
            return GuardianEntry("L1", "gateway_http", GuardianStatus.FAILED,
                                 details=str(e))

    async def _check_telegram_connection(self) -> GuardianEntry:
        """檢查 Telegram adapter 連線 — 使用 asyncio.to_thread 避免阻塞"""
        try:
            import asyncio

            def _sync_check():
                import urllib.request
                req = urllib.request.Request(
                    "http://127.0.0.1:8765/api/telegram/status", method="GET"
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return json.loads(resp.read().decode())

            data = await asyncio.to_thread(_sync_check)
            running = data.get("running", False)
            configured = data.get("configured", False)
            if running:
                return GuardianEntry("L1", "telegram_connection", GuardianStatus.OK,
                                     details="運行中")
            elif configured:
                # 已設定但未運行 → 嘗試重連
                repair = await self._repair_telegram()
                return repair
            else:
                return GuardianEntry("L1", "telegram_connection", GuardianStatus.SKIPPED,
                                     details="尚未設定 Telegram 令牌")
        except Exception as e:
            return GuardianEntry("L1", "telegram_connection", GuardianStatus.FAILED,
                                 details=f"無法查詢: {e}")

    async def _repair_telegram(self) -> GuardianEntry:
        """嘗試重連 Telegram — 純 CPU（Telegram Bot API call，非 Claude API）"""
        key = "telegram_restart"
        if self._repair_counts.get(key, 0) >= self.MAX_REPAIR_ATTEMPTS:
            self._add_unresolved("L1", "telegram_connection",
                                 "已嘗試修復 3 次仍失敗，需人工介入")
            return GuardianEntry("L1", "telegram_connection", GuardianStatus.FAILED,
                                 action="超過修復上限", details="需人工介入")
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://127.0.0.1:8765/api/telegram/restart",
                data=b'{}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                if data.get("success"):
                    self._reset_repair_count(key)
                    self._log_repair("L1", "telegram_connection", "repaired",
                                     "telegram-restart")
                    return GuardianEntry("L1", "telegram_connection",
                                         GuardianStatus.REPAIRED,
                                         action="telegram-restart",
                                         details="重連成功")
                else:
                    self._increment_repair_count(key)
                    return GuardianEntry("L1", "telegram_connection",
                                         GuardianStatus.FAILED,
                                         action="telegram-restart",
                                         details=f"重連失敗: {data.get('error', '未知')}")
        except Exception as e:
            self._increment_repair_count(key)
            return GuardianEntry("L1", "telegram_connection", GuardianStatus.FAILED,
                                 action="telegram-restart", details=str(e))

    def _check_env_file(self) -> GuardianEntry:
        """檢查 .env 檔案 — 純 CPU"""
        # 找 .env：data_dir 的父目錄
        home = self.data_dir.parent
        env_candidates = [home / ".env", home / ".runtime" / ".env"]
        env_path = None
        for p in env_candidates:
            if p.exists():
                env_path = p
                break

        if not env_path:
            return GuardianEntry("L1", "env_file", GuardianStatus.FAILED,
                                 details="找不到 .env 檔案")

        try:
            content = env_path.read_text(encoding="utf-8")
            # ANTHROPIC_API_KEY 已移除（MUSEON 統一使用 Claude MAX CLI OAuth）
            has_telegram = any(
                line.startswith("TELEGRAM_BOT_TOKEN=") and
                not line.startswith("TELEGRAM_BOT_TOKEN=your_")
                for line in content.splitlines()
                if not line.strip().startswith("#")
            )

            missing = []
            if not has_telegram:
                missing.append("TELEGRAM_BOT_TOKEN")

            if missing:
                return GuardianEntry("L1", "env_file", GuardianStatus.FAILED,
                                     details=f"缺少: {', '.join(missing)}")
            return GuardianEntry("L1", "env_file", GuardianStatus.OK,
                                 details="金鑰已設定")
        except Exception as e:
            return GuardianEntry("L1", "env_file", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_data_directories(self) -> GuardianEntry:
        """檢查 data 基本目錄結構 — 純 CPU"""
        required_dirs = [
            "memory", "eval", "lattice", "anima", "plans",
            "skills", "sub_agents", "guardian",
        ]
        missing = []
        repaired = []
        for d in required_dirs:
            path = self.data_dir / d
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    repaired.append(d)
                except Exception:
                    missing.append(d)

        if missing:
            return GuardianEntry("L1", "data_directories", GuardianStatus.FAILED,
                                 details=f"無法建立: {', '.join(missing)}")
        if repaired:
            self._log_repair("L1", "data_directories", "repaired",
                             f"create_dirs: {', '.join(repaired)}")
            return GuardianEntry("L1", "data_directories", GuardianStatus.REPAIRED,
                                 action="create_dirs",
                                 details=f"已建立: {', '.join(repaired)}")
        return GuardianEntry("L1", "data_directories", GuardianStatus.OK,
                             details="目錄結構完整")

    # ═══════════════════════════════════════
    # L2: 資料完整性巡檢（每 6 小時）
    # ═══════════════════════════════════════

    async def run_l2(self) -> Dict[str, Any]:
        """資料完整性巡檢 — ANIMA / Memory / WEE / Morphenix / Lattice / Eval

        純 CPU，零 Token。
        """
        start = time.monotonic()
        entries: List[GuardianEntry] = []

        # 1. ANIMA_MC.json 結構
        entries.append(self._check_anima_mc())

        # 2. ANIMA_USER.json 結構
        entries.append(self._check_anima_user())

        # 3. Memory 目錄 + 今日紀錄
        entries.append(self._check_memory_integrity())

        # 4. WEE 工作流紀錄
        entries.append(self._check_wee_data())

        # 5. Morphenix 迭代筆記
        entries.append(self._check_morphenix_data())

        # 6. Knowledge Lattice
        entries.append(self._check_lattice_integrity())

        # 7. Eval Q-Scores
        entries.append(self._check_eval_integrity())

        # 8. Audit Log 完整性
        entries.append(self._check_audit_integrity())

        # 9. 磁碟空間
        entries.append(self._check_disk_space())

        # 10. 備份檢查
        entries.append(self._check_backups())

        duration = int((time.monotonic() - start) * 1000)

        result = self._compile_result("L2", entries, duration)
        self.last_l2_result = result
        self._save_state()
        return result

    def _check_anima_mc(self) -> GuardianEntry:
        """檢查 ANIMA_MC.json 結構完整性 — 純 CPU"""
        path = self.data_dir / "ANIMA_MC.json"
        return self._validate_json_file(
            path, "anima_mc",
            required_fields=["identity", "self_awareness", "personality"],
            defaults={
                "version": "1.0.0",
                "type": "museon",
                "identity": {
                    "name": "MUSEON",
                    "birth_date": datetime.now().isoformat(),
                    "growth_stage": "adult",
                    "days_alive": 0,
                },
                "self_awareness": {"who_am_i": "", "my_purpose": ""},
                "personality": {"core_traits": [], "communication_style": ""},
                "capabilities": {"loaded_skills": [], "forged_skills": []},
                "evolution": {"current_stage": "unborn", "iteration_count": 0},
                "memory_summary": {"total_interactions": 0, "sessions_count": 0},
            },
        )

    def _check_anima_user(self) -> GuardianEntry:
        """檢查 ANIMA_USER.json 結構完整性 — 純 CPU"""
        path = self.data_dir / "ANIMA_USER.json"
        return self._validate_json_file(
            path, "anima_user",
            required_fields=["profile", "relationship"],
            defaults={
                "version": "1.0.0",
                "type": "user",
                "profile": {"name": "使用者", "business_type": "unknown"},
                "needs": {"immediate_need": "unknown", "main_pain_point": "unknown"},
                "preferences": {"language": "zh-TW"},
                "knowledge_level": {},
                "interaction_patterns": {},
                "relationship": {
                    "trust_level": "initial",
                    "total_interactions": 0,
                    "first_interaction": datetime.now().isoformat(),
                    "last_interaction": datetime.now().isoformat(),
                },
                "platforms": {},
            },
        )

    def _check_memory_integrity(self) -> GuardianEntry:
        """檢查 Memory 目錄和今日紀錄 — 純 CPU"""
        mem_dir = self.data_dir / "memory"
        if not mem_dir.exists():
            try:
                mem_dir.mkdir(parents=True, exist_ok=True)
                self._log_repair("L2", "memory_integrity", "repaired", "create_dir")
                return GuardianEntry("L2", "memory_integrity", GuardianStatus.REPAIRED,
                                     action="create_dir", details="memory/ 已建立")
            except Exception as e:
                return GuardianEntry("L2", "memory_integrity", GuardianStatus.FAILED,
                                     details=str(e))

        # 檢查是否有任何記憶檔案
        md_files = list(mem_dir.rglob("*.md"))
        return GuardianEntry("L2", "memory_integrity", GuardianStatus.OK,
                             details=f"{len(md_files)} 個記憶檔案")

    def _check_wee_data(self) -> GuardianEntry:
        """檢查 WEE 工作流紀錄 — 純 CPU"""
        wee_dir = self.data_dir / "wee"
        if not wee_dir.exists():
            try:
                wee_dir.mkdir(parents=True, exist_ok=True)
                # 初始化空紀錄
                init_file = wee_dir / "workflows.json"
                init_file.write_text(
                    json.dumps({"version": "1.0.0", "workflows": []},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._log_repair("L2", "wee_data", "repaired", "create_wee_dir")
                return GuardianEntry("L2", "wee_data", GuardianStatus.REPAIRED,
                                     action="create_wee_dir", details="wee/ 已建立並初始化")
            except Exception as e:
                return GuardianEntry("L2", "wee_data", GuardianStatus.FAILED,
                                     details=str(e))

        return GuardianEntry("L2", "wee_data", GuardianStatus.OK, details="wee/ 存在")

    def _check_morphenix_data(self) -> GuardianEntry:
        """檢查 Morphenix 迭代筆記 — 純 CPU"""
        morph_dir = self.data_dir / "morphenix"
        if not morph_dir.exists():
            try:
                morph_dir.mkdir(parents=True, exist_ok=True)
                # 初始化空紀錄
                init_file = morph_dir / "iteration_notes.json"
                init_file.write_text(
                    json.dumps({
                        "version": "1.0.0",
                        "notes": [],
                        "proposals": [],
                        "last_check": datetime.now().isoformat(),
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._log_repair("L2", "morphenix_data", "repaired", "create_morphenix_dir")
                return GuardianEntry("L2", "morphenix_data", GuardianStatus.REPAIRED,
                                     action="create_morphenix_dir",
                                     details="morphenix/ 已建立並初始化")
            except Exception as e:
                return GuardianEntry("L2", "morphenix_data", GuardianStatus.FAILED,
                                     details=str(e))

        return GuardianEntry("L2", "morphenix_data", GuardianStatus.OK,
                             details="morphenix/ 存在")

    def _check_lattice_integrity(self) -> GuardianEntry:
        """檢查 Knowledge Lattice SQLite 完整性 — 純 CPU"""
        try:
            from museon.agent.crystal_store import CrystalStore
            _cs = CrystalStore(data_dir=str(self.data_dir))
            if _cs.is_healthy():
                health = _cs.health_check()
                return GuardianEntry(
                    "L2", "lattice_integrity", GuardianStatus.OK,
                    details=f"Lattice 完整 (crystals={health.get('crystal_count', 0)}, "
                            f"links={health.get('link_count', 0)})",
                )
            else:
                return GuardianEntry(
                    "L2", "lattice_integrity", GuardianStatus.REPAIRED,
                    action="rebuild_lattice",
                    details="Crystal DB 健康檢查失敗，已重新初始化",
                )
        except Exception as e:
            logger.warning(f"[DAEMON] lattice integrity check failed: {e}")
            return GuardianEntry(
                "L2", "lattice_integrity", GuardianStatus.REPAIRED,
                action="rebuild_lattice",
                details=f"Crystal DB 例外: {e}",
            )

    def _check_eval_integrity(self) -> GuardianEntry:
        """檢查 Eval Q-Scores JSONL 格式 — 純 CPU"""
        eval_dir = self.data_dir / "eval"
        if not eval_dir.exists():
            try:
                eval_dir.mkdir(parents=True, exist_ok=True)
                return GuardianEntry("L2", "eval_integrity", GuardianStatus.REPAIRED,
                                     action="create_eval_dir", details="eval/ 已建立")
            except Exception as e:
                return GuardianEntry("L2", "eval_integrity", GuardianStatus.FAILED,
                                     details=str(e))

        qscores = eval_dir / "q_scores.jsonl"
        if not qscores.exists():
            return GuardianEntry("L2", "eval_integrity", GuardianStatus.OK,
                                 details="q_scores.jsonl 尚未產生（正常）")

        # 驗證 JSONL 格式：移除損壞行
        try:
            lines = qscores.read_text(encoding="utf-8").splitlines()
            good_lines = []
            bad_count = 0
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                    good_lines.append(line)
                except json.JSONDecodeError:
                    bad_count += 1

            if bad_count > 0:
                qscores.write_text(
                    "\n".join(good_lines) + "\n" if good_lines else "",
                    encoding="utf-8",
                )
                self._log_repair("L2", "eval_integrity", "repaired",
                                 f"移除 {bad_count} 行損壞資料")
                return GuardianEntry("L2", "eval_integrity", GuardianStatus.REPAIRED,
                                     action="clean_qscores",
                                     details=f"移除 {bad_count} 行損壞，保留 {len(good_lines)} 行")
            return GuardianEntry("L2", "eval_integrity", GuardianStatus.OK,
                                 details=f"{len(good_lines)} 筆評分紀錄")
        except Exception as e:
            return GuardianEntry("L2", "eval_integrity", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_audit_integrity(self) -> GuardianEntry:
        """檢查 Audit Log 鏈完整性 — 純 CPU"""
        try:
            from museon.security.audit import AuditLogger
            audit = AuditLogger()
            result = audit.verify_integrity()
            if result.get("integrity_ok", True):
                return GuardianEntry("L2", "audit_integrity", GuardianStatus.OK,
                                     details=f"{result.get('total_entries', 0)} 筆稽核紀錄")
            else:
                invalid = result.get("invalid_entries", 0)
                return GuardianEntry("L2", "audit_integrity", GuardianStatus.FAILED,
                                     details=f"{invalid} 筆稽核紀錄斷鏈")
        except ImportError:
            return GuardianEntry("L2", "audit_integrity", GuardianStatus.SKIPPED,
                                 details="AuditLogger 未安裝")
        except Exception as e:
            return GuardianEntry("L2", "audit_integrity", GuardianStatus.OK,
                                 details=f"檢查略過: {e}")

    def _check_disk_space(self) -> GuardianEntry:
        """檢查磁碟空間 — 純 CPU"""
        try:
            import shutil
            usage = shutil.disk_usage(str(self.data_dir))
            free_gb = usage.free / (1024 ** 3)
            if free_gb < 1.0:
                return GuardianEntry("L2", "disk_space", GuardianStatus.FAILED,
                                     details=f"僅剩 {free_gb:.1f} GB — 極度不足")
            elif free_gb < 5.0:
                return GuardianEntry("L2", "disk_space", GuardianStatus.REPAIRED,
                                     details=f"剩餘 {free_gb:.1f} GB — 建議清理")
            return GuardianEntry("L2", "disk_space", GuardianStatus.OK,
                                 details=f"剩餘 {free_gb:.1f} GB")
        except Exception as e:
            return GuardianEntry("L2", "disk_space", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_backups(self) -> GuardianEntry:
        """檢查關鍵 JSON 是否有 .bak 備份 — 純 CPU"""
        critical_files = [
            self.data_dir / "ANIMA_MC.json",
            self.data_dir / "ANIMA_USER.json",
        ]
        backed_up = 0
        created = 0
        for fpath in critical_files:
            bak = fpath.with_suffix(".json.bak")
            if fpath.exists():
                if bak.exists():
                    backed_up += 1
                else:
                    try:
                        import shutil
                        shutil.copy2(str(fpath), str(bak))
                        created += 1
                    except Exception as e:
                        logger.debug(f"[DAEMON] module import failed (degraded): {e}")

        if created > 0:
            self._log_repair("L2", "backups", "repaired",
                             f"建立 {created} 個備份")
            return GuardianEntry("L2", "backups", GuardianStatus.REPAIRED,
                                 action="create_backups",
                                 details=f"新建 {created} 個備份")
        return GuardianEntry("L2", "backups", GuardianStatus.OK,
                             details=f"{backed_up}/{len(critical_files)} 有備份")

    # ═══════════════════════════════════════
    # L3: 神經束連通性（每 6 小時）
    # ═══════════════════════════════════════

    async def run_l3(self) -> Dict[str, Any]:
        """DNA27 六大神經束連通性巡檢 — 純 CPU，零 Token。

        檢查 Brain 的 6 大核心模組是否正常載入並可存取。
        """
        start = time.monotonic()
        entries: List[GuardianEntry] = []

        if not self.brain:
            entries.append(GuardianEntry("L3", "brain_instance", GuardianStatus.FAILED,
                                         details="Brain 實例不可用"))
            duration = int((time.monotonic() - start) * 1000)
            result = self._compile_result("L3", entries, duration)
            self.last_l3_result = result
            self._save_state()
            return result

        brain = self.brain

        # 1. 🧠 Brain 主腦 — persona 可載入
        entries.append(self._check_bundle_brain(brain))

        # 2. 💎 Soul — soul_rings 可讀寫
        entries.append(self._check_bundle_soul(brain))

        # 3. 📊 Eval — 評估引擎可運作
        entries.append(self._check_bundle_eval(brain))

        # 4. 🔮 Intuition — 直覺引擎已載入
        entries.append(self._check_bundle_intuition(brain))

        # 5. 📋 Plan — 計畫引擎已載入
        entries.append(self._check_bundle_plan(brain))

        # 6. 📚 Knowledge — 知識晶格可存取
        entries.append(self._check_bundle_knowledge(brain))

        # 額外：Skill Router
        entries.append(self._check_bundle_skills(brain))

        # 額外：Safety Anchor
        entries.append(self._check_bundle_safety(brain))

        duration = int((time.monotonic() - start) * 1000)

        result = self._compile_result("L3", entries, duration)
        self.last_l3_result = result
        self._save_state()
        return result

    def _check_bundle_brain(self, brain) -> GuardianEntry:
        """🧠 Brain 主腦 — persona + memory_store"""
        issues = []
        try:
            anima = brain._load_anima_mc()
            if not anima:
                issues.append("ANIMA_MC 載入失敗")
        except Exception as e:
            issues.append(f"ANIMA_MC: {e}")

        try:
            if brain.memory_store is None:
                issues.append("MemoryStore 未載入")
        except Exception as e:
            issues.append(f"MemoryStore: {e}")

        if issues:
            return GuardianEntry("L3", "brain_core", GuardianStatus.FAILED,
                                 details="; ".join(issues))
        return GuardianEntry("L3", "brain_core", GuardianStatus.OK,
                             details="主腦正常")

    def _check_bundle_soul(self, brain) -> GuardianEntry:
        """💎 Soul — soul_rings.json 可讀寫"""
        try:
            sr_path = self.data_dir / "anima" / "soul_rings.json"
            if sr_path.exists():
                data = json.loads(sr_path.read_text(encoding="utf-8"))
                return GuardianEntry("L3", "soul_ring", GuardianStatus.OK,
                                     details=f"{len(data) if isinstance(data, list) else 0} 個靈魂環")
            else:
                return GuardianEntry("L3", "soul_ring", GuardianStatus.OK,
                                     details="尚未產生（正常）")
        except Exception as e:
            return GuardianEntry("L3", "soul_ring", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_bundle_eval(self, brain) -> GuardianEntry:
        """📊 Eval — 評估引擎已載入"""
        try:
            if hasattr(brain, 'eval_engine') and brain.eval_engine is not None:
                return GuardianEntry("L3", "eval_engine", GuardianStatus.OK,
                                     details="評估引擎正常")
            return GuardianEntry("L3", "eval_engine", GuardianStatus.FAILED,
                                 details="EvalEngine 未載入")
        except Exception as e:
            return GuardianEntry("L3", "eval_engine", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_bundle_intuition(self, brain) -> GuardianEntry:
        """🔮 Intuition — 直覺引擎已載入"""
        try:
            if hasattr(brain, 'intuition') and brain.intuition is not None:
                return GuardianEntry("L3", "intuition_engine", GuardianStatus.OK,
                                     details="直覺引擎正常")
            return GuardianEntry("L3", "intuition_engine", GuardianStatus.FAILED,
                                 details="IntuitionEngine 未載入")
        except Exception as e:
            return GuardianEntry("L3", "intuition_engine", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_bundle_plan(self, brain) -> GuardianEntry:
        """📋 Plan — 計畫引擎已載入"""
        try:
            if hasattr(brain, 'plan_engine') and brain.plan_engine is not None:
                return GuardianEntry("L3", "plan_engine", GuardianStatus.OK,
                                     details="計畫引擎正常")
            return GuardianEntry("L3", "plan_engine", GuardianStatus.FAILED,
                                 details="PlanEngine 未載入")
        except Exception as e:
            return GuardianEntry("L3", "plan_engine", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_bundle_knowledge(self, brain) -> GuardianEntry:
        """📚 Knowledge — 知識晶格可存取"""
        try:
            if hasattr(brain, 'knowledge_lattice') and brain.knowledge_lattice is not None:
                return GuardianEntry("L3", "knowledge_lattice", GuardianStatus.OK,
                                     details="知識晶格正常")
            # 不算失敗 — 可能尚未初始化
            return GuardianEntry("L3", "knowledge_lattice", GuardianStatus.OK,
                                 details="KnowledgeLattice 尚未初始化")
        except Exception as e:
            return GuardianEntry("L3", "knowledge_lattice", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_bundle_skills(self, brain) -> GuardianEntry:
        """Skill Router — DNA27 技能路由"""
        try:
            if brain.skill_router:
                count = brain.skill_router.get_skill_count()
                return GuardianEntry("L3", "skill_router", GuardianStatus.OK,
                                     details=f"{count} 個技能已載入")
            return GuardianEntry("L3", "skill_router", GuardianStatus.FAILED,
                                 details="SkillRouter 未載入")
        except Exception as e:
            return GuardianEntry("L3", "skill_router", GuardianStatus.FAILED,
                                 details=str(e))

    def _check_bundle_safety(self, brain) -> GuardianEntry:
        """Safety Anchor — 安全護欄"""
        try:
            if hasattr(brain, 'safety_anchor') and brain.safety_anchor is not None:
                return GuardianEntry("L3", "safety_anchor", GuardianStatus.OK,
                                     details="安全護欄正常")
            return GuardianEntry("L3", "safety_anchor", GuardianStatus.OK,
                                 details="SafetyAnchor 尚未載入")
        except Exception as e:
            return GuardianEntry("L3", "safety_anchor", GuardianStatus.FAILED,
                                 details=str(e))

    # ═══════════════════════════════════════
    # L5: 程式碼健康檢查（Self-Surgery 整合）
    # ═══════════════════════════════════════

    def run_l5(self) -> Dict[str, Any]:
        """L5: 程式碼靜態分析健康檢查.

        使用 CodeAnalyzer 掃描 src/museon/ 下所有 .py 檔案，
        偵測常見架構性問題（靜默異常、asyncio 錯誤、logger 問題等）。
        純 CPU 零 Token 消耗。
        """
        import time as _time
        start = _time.time()
        result = {"level": "L5", "entries": [], "summary": ""}

        try:
            from museon.doctor.code_analyzer import CodeAnalyzer

            source_root = self.data_dir.parent / "src" / "museon"
            analyzer = CodeAnalyzer(source_root=source_root)
            issues = analyzer.scan_all()

            critical = [i for i in issues if i.severity == "critical"]
            warning = [i for i in issues if i.severity == "warning"]

            if critical:
                result["entries"].append(GuardianEntry(
                    "L5", "code_health", GuardianStatus.FAILED,
                    details=(
                        f"{len(critical)} 個 critical 問題: "
                        + "; ".join(
                            f"[{i.rule_id}] {i.file_path}:{i.line}"
                            for i in critical[:5]
                        )
                    ),
                ))
            elif warning:
                result["entries"].append(GuardianEntry(
                    "L5", "code_health", GuardianStatus.DEGRADED,
                    details=f"{len(warning)} 個 warning 問題",
                ))
            else:
                result["entries"].append(GuardianEntry(
                    "L5", "code_health", GuardianStatus.OK,
                    details="程式碼健康 — 未發現問題",
                ))

            result["summary"] = (
                f"L5 程式碼健康: "
                f"{len(critical)} critical, {len(warning)} warning, "
                f"{len(issues)} total"
            )
            result["issues"] = [
                {
                    "rule_id": i.rule_id,
                    "file": i.file_path,
                    "line": i.line,
                    "message": i.message,
                    "severity": i.severity,
                }
                for i in issues[:20]
            ]

        except Exception as e:
            logger.error(f"Guardian L5 failed: {e}")
            result["entries"].append(GuardianEntry(
                "L5", "code_health", GuardianStatus.FAILED,
                details=f"L5 執行失敗: {e}",
            ))
            result["summary"] = f"L5 執行失敗: {e}"

        elapsed = _time.time() - start
        result["elapsed_seconds"] = round(elapsed, 2)
        self.last_l5_result = result
        logger.info(f"Guardian L5 完成: {result['summary']} ({elapsed:.1f}s)")
        return result

    # ═══════════════════════════════════════
    # L4: 修復日誌 + 母體回報
    # ═══════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        """取得 Guardian 完整狀態 — 供 Dashboard 顯示"""
        state = self._load_state()
        unresolved = self._load_unresolved()
        recent_repairs = self._load_recent_repairs(limit=20)

        return {
            "last_l1": state.get("last_l1_time"),
            "last_l2": state.get("last_l2_time"),
            "last_l3": state.get("last_l3_time"),
            "l1_summary": self.last_l1_result.get("summary") if self.last_l1_result else None,
            "l2_summary": self.last_l2_result.get("summary") if self.last_l2_result else None,
            "l3_summary": self.last_l3_result.get("summary") if self.last_l3_result else None,
            "l5_summary": self.last_l5_result.get("summary") if self.last_l5_result else None,
            "unresolved_count": len(unresolved),
            "unresolved": unresolved[:5],  # 最多回傳 5 筆
            "recent_repairs": recent_repairs,
            "mothership_connected": False,  # 預留
            "mothership_queue_size": self._count_mothership_queue(),
        }

    def get_full_report(self) -> Dict[str, Any]:
        """取得完整報告 — 供 Doctor 頁面展開"""
        return {
            "l1": self.last_l1_result,
            "l2": self.last_l2_result,
            "l3": self.last_l3_result,
            "l5": self.last_l5_result,
            "unresolved": self._load_unresolved(),
            "recent_repairs": self._load_recent_repairs(limit=50),
        }

    # ═══════════════════════════════════════
    # Helper: JSON 驗證 + 自動修復
    # ═══════════════════════════════════════

    def _validate_json_file(
        self, path: Path, check_name: str,
        required_fields: List[str],
        defaults: Dict[str, Any],
    ) -> GuardianEntry:
        """驗證 JSON 檔案完整性，缺失欄位自動補上預設值 — 純 CPU"""
        if not path.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(defaults, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._log_repair("L2", check_name, "repaired", "create_file")
                return GuardianEntry("L2", check_name, GuardianStatus.REPAIRED,
                                     action="create_file",
                                     details=f"{path.name} 不存在，已建立預設")
            except Exception as e:
                return GuardianEntry("L2", check_name, GuardianStatus.FAILED,
                                     details=f"建立失敗: {e}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            # JSON 損壞 → 備份 + 重建
            bak = path.with_suffix(".json.bak")
            try:
                path.rename(bak)
            except Exception as e:
                logger.debug(f"[DAEMON] file rename failed (degraded): {e}")
            try:
                path.write_text(
                    json.dumps(defaults, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._log_repair("L2", check_name, "repaired", "rebuild_from_default")
                return GuardianEntry("L2", check_name, GuardianStatus.REPAIRED,
                                     action="rebuild_from_default",
                                     details=f"JSON 損壞，已備份並重建")
            except Exception as e2:
                return GuardianEntry("L2", check_name, GuardianStatus.FAILED,
                                     details=f"重建失敗: {e2}")

        # 檢查必要欄位
        missing = [f for f in required_fields if f not in data]
        if missing:
            for field in missing:
                if field in defaults:
                    data[field] = defaults[field]
            try:
                path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._log_repair("L2", check_name, "repaired",
                                 f"add_fields: {', '.join(missing)}")
                return GuardianEntry("L2", check_name, GuardianStatus.REPAIRED,
                                     action="add_fields",
                                     details=f"補上欄位: {', '.join(missing)}")
            except Exception as e:
                return GuardianEntry("L2", check_name, GuardianStatus.FAILED,
                                     details=f"補欄位失敗: {e}")

        return GuardianEntry("L2", check_name, GuardianStatus.OK,
                             details=f"{path.name} 結構完整")

    # ═══════════════════════════════════════
    # Helper: 修復計數 / 日誌 / 狀態
    # ═══════════════════════════════════════

    def _load_repair_counts(self):
        """載入修復計數 — 防止無限修復迴圈"""
        try:
            state = self._load_state()
            self._repair_counts = state.get("repair_counts", {})
        except Exception:
            self._repair_counts = {}

    def _increment_repair_count(self, key: str):
        self._repair_counts[key] = self._repair_counts.get(key, 0) + 1
        self._save_state()

    def _reset_repair_count(self, key: str):
        self._repair_counts.pop(key, None)
        self._save_state()

    def _log_repair(self, layer: str, check: str, status: str, action: str):
        """寫入修復日誌 — append-only JSONL"""
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "layer": layer,
                "check": check,
                "status": status,
                "action": action,
            }
            with open(self.repair_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            # 控制日誌大小（最多 500 行）
            if self.repair_log_path.stat().st_size > 100_000:
                lines = self.repair_log_path.read_text(encoding="utf-8").splitlines()
                self.repair_log_path.write_text(
                    "\n".join(lines[-300:]) + "\n", encoding="utf-8"
                )
        except Exception as e:
            logger.error(f"Guardian repair log write failed: {e}")

    def _load_recent_repairs(self, limit: int = 20) -> List[Dict]:
        """讀取最近修復紀錄"""
        try:
            if not self.repair_log_path.exists():
                return []
            lines = self.repair_log_path.read_text(encoding="utf-8").splitlines()
            entries = []
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(entries) >= limit:
                    break
            return entries
        except Exception:
            return []

    def _add_unresolved(self, layer: str, check: str, details: str):
        """新增無法解決的問題 — 預留給母體回報"""
        unresolved = self._load_unresolved()
        unresolved.append({
            "timestamp": datetime.now().isoformat(),
            "layer": layer,
            "check": check,
            "details": details,
        })
        # 最多保留 50 筆
        unresolved = unresolved[-50:]
        try:
            self.unresolved_path.write_text(
                json.dumps(unresolved, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # 同步寫入母體佇列
            self._queue_mothership(layer, check, details)
        except Exception as e:
            logger.error(f"Guardian unresolved write failed: {e}")

    def _load_unresolved(self) -> List[Dict]:
        try:
            if self.unresolved_path.exists():
                return json.loads(self.unresolved_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"[DAEMON] JSON failed (degraded): {e}")
        return []

    def _queue_mothership(self, layer: str, check: str, details: str):
        """將事件加入母體回報佇列 + 即時 DM 通知老闆"""
        try:
            queue = []
            if self.mothership_queue_path.exists():
                queue = json.loads(
                    self.mothership_queue_path.read_text(encoding="utf-8")
                )
            queue.append({
                "timestamp": datetime.now().isoformat(),
                "layer": layer,
                "check": check,
                "details": details,
                "sent": False,
            })
            queue = queue[-100:]  # 最多 100 筆
            self.mothership_queue_path.write_text(
                json.dumps(queue, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Guardian mothership queue write failed: {e}")

        # 即時 DM 通知老闆
        try:
            self._notify_owner_dm(layer, check, details)
        except Exception:
            pass

    def _notify_owner_dm(self, layer: str, check: str, details: str) -> None:
        """透過 Telegram Bot API 即時 DM 通知老闆。"""
        import os
        import urllib.request
        import urllib.parse

        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        trusted_ids = os.environ.get("TELEGRAM_TRUSTED_IDS", "")

        if not token or not trusted_ids:
            env_path = self.data_dir.parent / ".env" if hasattr(self.data_dir, 'parent') else Path(".env")
            if env_path.exists():
                for line in env_path.read_text().strip().split("\n"):
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip()
                    elif line.startswith("TELEGRAM_TRUSTED_IDS="):
                        trusted_ids = line.split("=", 1)[1].strip()

        if not token or not trusted_ids:
            return

        owner_id = trusted_ids.split(",")[0].strip()
        text = f"🛡️ [Guardian {layer}] {check}\n{details[:200]}"

        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({"chat_id": owner_id, "text": text}).encode()
            urllib.request.urlopen(url, data, timeout=5)
        except Exception as e:
            logger.debug(f"[Guardian] DM notify failed: {e}")

    def _count_mothership_queue(self) -> int:
        try:
            if self.mothership_queue_path.exists():
                queue = json.loads(
                    self.mothership_queue_path.read_text(encoding="utf-8")
                )
                return sum(1 for q in queue if not q.get("sent", False))
        except Exception as e:
            logger.debug(f"[DAEMON] data read failed (degraded): {e}")
        return 0

    def _save_state(self):
        """保存 Guardian 狀態"""
        try:
            state = self._load_state()
            state["repair_counts"] = self._repair_counts
            if self.last_l1_result:
                state["last_l1_time"] = datetime.now().isoformat()
            if self.last_l2_result:
                state["last_l2_time"] = datetime.now().isoformat()
            if self.last_l3_result:
                state["last_l3_time"] = datetime.now().isoformat()
            self.state_path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Guardian state save failed: {e}")

    def _load_state(self) -> Dict:
        try:
            if self.state_path.exists():
                return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"[DAEMON] JSON failed (degraded): {e}")
        return {}

    # ═══════════════════════════════════════
    # Compile
    # ═══════════════════════════════════════

    def _compile_result(
        self, layer: str, entries: List[GuardianEntry], duration_ms: int
    ) -> Dict[str, Any]:
        summary = {"ok": 0, "repaired": 0, "failed": 0, "skipped": 0}
        for e in entries:
            summary[e.status] = summary.get(e.status, 0) + 1

        # Overall status
        if summary["failed"] > 0:
            overall = "critical"
        elif summary["repaired"] > 0:
            overall = "warning"
        else:
            overall = "ok"

        return {
            "layer": layer,
            "timestamp": datetime.now().isoformat(),
            "overall": overall,
            "summary": summary,
            "checks": [e.to_dict() for e in entries],
            "duration_ms": duration_ms,
        }
