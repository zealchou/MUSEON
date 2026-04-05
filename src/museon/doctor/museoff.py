"""
MuseOff — 巡邏糾察隊

24/7 背景巡邏，7 層探測（L0-L6），找到問題立即止損並留下診斷卡。
全部零 Token（純 CPU），效能上限 30%。

設計參考：
- K8s Liveness/Readiness/Startup Probes（探針分離）
- Datadog Watchdog（baseline 異常偵測）
- PagerDuty AIOps（事件去重）
- Netflix Chaos Monkey（故障注入）
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from museon.doctor.finding import (
    BaselineTracker,
    BlastOrigin,
    BlastTarget,
    Finding,
    FindingStore,
    Prescription,
    TriageAction,
)
from museon.doctor.shared_board import read_shared_board, update_shared_board

logger = logging.getLogger(__name__)


class MuseOff:
    """巡邏糾察隊——7 層探測 + 應急止損"""

    VERSION = "1.0.0"
    CPU_CEILING = 0.30
    MAX_PROBE_DURATION = 60
    PROBE_COOLDOWN = 30

    def __init__(self, museon_home: Path | str | None = None):
        self.home = Path(museon_home or "/Users/ZEALCHOU/MUSEON")
        self.src_dir = self.home / "src" / "museon"
        self.findings_dir = self.home / "data" / "_system" / "museoff" / "findings"
        self.triage_log = self.home / "data" / "_system" / "museoff" / "triage_log.jsonl"
        self.baselines_path = self.home / "data" / "_system" / "museoff" / "baselines.json"
        self.stats_path = self.home / "data" / "_system" / "museoff" / "probe_stats.json"

        self.findings_dir.mkdir(parents=True, exist_ok=True)

        self._data_dir = self.home / "data"
        self._store = FindingStore(self.findings_dir)
        self._baseline = BaselineTracker()
        self._load_baselines()
        self._stats = {"probes_run": 0, "findings_created": 0, "triages_executed": 0}

        # 啟動時讀取共享看板，了解其他虎將狀態
        self._recent_board = read_shared_board(self._data_dir)

    # -------------------------------------------------------------------
    # L0: Liveness Probe（每 60 秒）
    # -------------------------------------------------------------------

    async def probe_liveness(self) -> None:
        """L0: Gateway 活著嗎？死了就重啟。"""
        if not self._should_probe():
            return
        from museon.doctor.probes.liveness import LivenessProbe
        result = await LivenessProbe().check()
        self._stats["probes_run"] += 1

        if not result["alive"]:
            logger.warning("[MuseOff L0] Liveness FAILED: %s", result["detail"])
            self._create_finding(
                probe_layer="L0",
                severity="CRITICAL",
                title=f"Gateway liveness 失敗: {result['detail']}",
                blast_origin=BlastOrigin(file="gateway/server.py", error_type="LivenessFailure"),
                blast_radius=[
                    BlastTarget(module="所有通道", impact="使用者無法收到回覆", fan_in="N/A"),
                ],
                prescription=Prescription(
                    diagnosis=result["detail"],
                    root_cause="Gateway 進程死亡或 HTTP 無回應",
                    suggested_fix="重啟 Gateway",
                    runbook_id="RB-restart-gateway",
                    fix_complexity="GREEN",
                ),
            )
            self._triage("restart_gateway")

    # -------------------------------------------------------------------
    # L1: Readiness Probe（每 5 分鐘）
    # -------------------------------------------------------------------

    async def probe_readiness(self) -> None:
        """L1: Brain 就緒嗎？沒 ready 就降級，不重啟。"""
        if not self._should_probe():
            return
        from museon.doctor.probes.readiness import ReadinessProbe
        result = await ReadinessProbe().check()
        self._stats["probes_run"] += 1

        if not result["ready"]:
            logger.warning("[MuseOff L1] Readiness FAILED: %s", result["detail"])
            self._create_finding(
                probe_layer="L1",
                severity="HIGH",
                title=f"系統就緒檢查失敗: {result['detail']}",
                blast_origin=BlastOrigin(
                    file="gateway/server.py",
                    error_type="ReadinessFailure",
                ),
                blast_radius=[
                    BlastTarget(module=f, impact="服務降級", fan_in="N/A")
                    for f in result["failed"]
                ],
                prescription=Prescription(
                    diagnosis=result["detail"],
                    root_cause=f"以下服務未就緒: {', '.join(result['failed'])}",
                    suggested_fix="檢查相關服務狀態",
                ),
            )

    # -------------------------------------------------------------------
    # L2: Import Guard（每 30 分鐘）
    # -------------------------------------------------------------------

    async def probe_import(self) -> None:
        """L2: 所有核心模組能正常 import 嗎？"""
        if not self._should_probe():
            return

        core_modules = [
            "museon.agent.brain",
            "museon.gateway.server",
            "museon.gateway.message",
            "museon.core.event_bus",
            "museon.core.data_bus",
            "museon.pulse.pulse_db",
            "museon.pulse.pulse_engine",
            "museon.memory.memory_manager",
            "museon.agent.skill_router",
            "museon.governance.governor",
            "museon.agent.knowledge_lattice",
            "museon.agent.metacognition",
        ]

        failed = []
        for mod_name in core_modules:
            t0 = time.monotonic()
            try:
                if mod_name in sys.modules:
                    importlib.reload(sys.modules[mod_name])
                else:
                    importlib.import_module(mod_name)
                elapsed = time.monotonic() - t0
                self._baseline.record(f"import_{mod_name}", elapsed)

                if self._baseline.is_anomaly(f"import_{mod_name}", elapsed):
                    logger.info("[MuseOff L2] Slow import: %s (%.2fs)", mod_name, elapsed)
            except Exception as e:
                failed.append((mod_name, str(e)))

        self._stats["probes_run"] += 1

        for mod_name, error in failed:
            rel = mod_name.replace("museon.", "").replace(".", "/") + ".py"
            logger.error("[MuseOff L2] Import FAILED: %s — %s", mod_name, error)
            self._create_finding(
                probe_layer="L2",
                severity="CRITICAL",
                title=f"{rel} import 失敗",
                blast_origin=BlastOrigin(file=rel, error_type="ImportError", traceback=error),
                blast_radius=[
                    BlastTarget(module="brain.py", impact="Brain 可能無法初始化", fan_in=1),
                ],
                prescription=Prescription(
                    diagnosis=f"ImportError: {error}",
                    root_cause="模組語法錯誤或依賴缺失",
                    suggested_fix="檢查最近的 git diff",
                    post_check=f"python -c 'import {mod_name}'",
                ),
            )

    # -------------------------------------------------------------------
    # L2b: ANIMA 身份完整性探針（每 1 小時）
    # -------------------------------------------------------------------

    async def probe_anima_integrity(self) -> None:
        """L2b: ANIMA_MC.json 身份核心是否完整？損壞/清空立即告警。"""
        if not self._should_probe():
            return

        anima_path = self.home / "data" / "ANIMA_MC.json"
        self._stats["probes_run"] += 1

        # 檔案不存在
        if not anima_path.exists():
            self._create_finding(
                probe_layer="L2",
                severity="CRITICAL",
                title="ANIMA_MC.json 不存在——系統身份核心遺失",
                blast_origin=BlastOrigin(
                    file="data/ANIMA_MC.json",
                    error_type="MissingFile",
                ),
                prescription=Prescription(
                    diagnosis="data/ANIMA_MC.json 不存在",
                    root_cause="檔案遺失（可能被誤刪或從未建立）",
                    suggested_fix="從備份或 MUSEON_archive 恢復 ANIMA_MC.json",
                    runbook_id="RB-anima-restore",
                ),
            )
            return

        # 檔案大小 < 100 bytes（可能被清空）
        file_size = anima_path.stat().st_size
        if file_size < 100:
            self._create_finding(
                probe_layer="L2",
                severity="HIGH",
                title=f"ANIMA_MC.json 異常小（{file_size} bytes）——可能被清空",
                blast_origin=BlastOrigin(
                    file="data/ANIMA_MC.json",
                    error_type="SuspiciouslySmallFile",
                ),
                prescription=Prescription(
                    diagnosis=f"檔案大小僅 {file_size} bytes，低於正常門檻 100 bytes",
                    root_cause="檔案可能在寫入中途被截斷或被清空",
                    suggested_fix="從備份或 MUSEON_archive 恢復 ANIMA_MC.json",
                ),
            )
            return

        # JSON 解析
        try:
            anima_data = json.loads(anima_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            self._create_finding(
                probe_layer="L2",
                severity="CRITICAL",
                title=f"ANIMA_MC.json 解析失敗——身份資料損壞",
                blast_origin=BlastOrigin(
                    file="data/ANIMA_MC.json",
                    error_type="JSONDecodeError",
                    traceback=str(e),
                ),
                prescription=Prescription(
                    diagnosis=f"JSON 解析錯誤: {e}",
                    root_cause="檔案損壞（可能是寫入中途斷電或不合法 JSON）",
                    suggested_fix="從備份或 MUSEON_archive 恢復 ANIMA_MC.json",
                ),
            )
            return

        # 必要欄位檢查
        missing_fields = []
        identity = anima_data.get("identity", {})
        if not identity.get("name"):
            missing_fields.append("identity.name")
        if not identity.get("birth_date"):
            missing_fields.append("identity.birth_date")
        if "ceremony" not in anima_data:
            missing_fields.append("ceremony")
        personality = anima_data.get("personality", {})
        trait_dims = personality.get("trait_dimensions", {})
        if not isinstance(trait_dims, dict) or len(trait_dims) < 5:
            missing_fields.append(
                f"personality.trait_dimensions（需 ≥5 維，實際 {len(trait_dims) if isinstance(trait_dims, dict) else 0}）"
            )

        if missing_fields:
            self._create_finding(
                probe_layer="L2",
                severity="HIGH",
                title=f"ANIMA_MC.json 必要欄位缺失: {', '.join(missing_fields)}",
                blast_origin=BlastOrigin(
                    file="data/ANIMA_MC.json",
                    error_type="MissingFields",
                ),
                context={"missing_fields": missing_fields},
                prescription=Prescription(
                    diagnosis=f"缺失欄位: {missing_fields}",
                    root_cause="ANIMA_MC.json 未完整建立，或欄位被意外刪除",
                    suggested_fix="補全缺失欄位，或從備份恢復",
                ),
            )
        # 全部通過 → 靜默返回

    # -------------------------------------------------------------------
    # L3: Config Validator（每 1 小時）
    # -------------------------------------------------------------------

    async def probe_config(self) -> None:
        """L3: 配置和路徑都正確嗎？"""
        if not self._should_probe():
            return

        issues = []

        # 檢查必要檔案
        required_files = [
            ("data/pulse/pulse.db", "PulseDB"),
            ("data/lattice/crystal.db", "CrystalDB"),
            ("data/ANIMA_MC.json", "ANIMA_MC"),
            ("data/_system/museon-persona.md", "Persona"),
            (".env", ".env config"),
        ]
        for rel, name in required_files:
            path = self.home / rel
            if not path.exists():
                issues.append(("missing_file", name, rel))
            elif path.stat().st_size == 0:
                issues.append(("empty_file", name, rel))

        # 檢查 .env 權限
        env_path = self.home / ".env"
        if env_path.exists():
            mode = oct(env_path.stat().st_mode)[-3:]
            if mode != "600":
                issues.append(("bad_permissions", ".env", f"mode={mode}, should be 600"))

        # 檢查 DB schema（WAL 模式）— 用 PRAGMA 查實際模式，不靠 .db-wal 檔案存在判斷
        import sqlite3 as _sqlite3
        for db_rel in [
            "data/pulse/pulse.db",
            "data/lattice/crystal.db",
            "data/_system/group_context.db",
            "data/_system/wee/workflow_state.db",
            "data/_system/message_queue.db",
        ]:
            db_path = self.home / db_rel
            if db_path.exists():
                try:
                    _conn = _sqlite3.connect(str(db_path))
                    _mode = _conn.execute("PRAGMA journal_mode").fetchone()[0]
                    _conn.close()
                    if _mode != "wal":
                        issues.append(("no_wal", db_rel, f"journal_mode={_mode}, should be wal"))
                except Exception as _db_err:
                    issues.append(("db_error", db_rel, str(_db_err)))

        self._stats["probes_run"] += 1

        for issue_type, name, detail in issues:
            self._create_finding(
                probe_layer="L3",
                severity="HIGH" if issue_type in ("missing_file", "empty_file") else "MEDIUM",
                title=f"配置問題: {name} — {issue_type}",
                blast_origin=BlastOrigin(file=name, error_type=issue_type, traceback=detail),
                prescription=Prescription(
                    diagnosis=f"{issue_type}: {detail}",
                    runbook_id="RB-003" if issue_type == "missing_file" else "",
                ),
            )

    # -------------------------------------------------------------------
    # L4: Regression Probe（每 2 小時）
    # -------------------------------------------------------------------

    async def probe_regression(self) -> None:
        """L4: pytest-testmon 只跑受影響測試"""
        if not self._should_probe():
            return

        try:
            result = subprocess.run(
                [str(self.home / ".venv" / "bin" / "python"), "-m", "pytest",
                 "--testmon", "-x", "-q", "--timeout=120", "--no-header"],
                capture_output=True, text=True, timeout=180,
                cwd=str(self.home),
            )
            self._stats["probes_run"] += 1

            if result.returncode != 0:
                # 解析失敗的測試
                output = result.stdout + result.stderr
                logger.warning("[MuseOff L4] Regression tests FAILED:\n%s", output[:500])
                self._create_finding(
                    probe_layer="L4",
                    severity="HIGH",
                    title="回歸測試失敗",
                    blast_origin=BlastOrigin(file="tests/", error_type="TestFailure", traceback=output[:1000]),
                    prescription=Prescription(
                        diagnosis="pytest-testmon 偵測到受影響測試失敗",
                        post_check="pytest --testmon -x",
                    ),
                )
        except subprocess.TimeoutExpired:
            logger.warning("[MuseOff L4] Regression tests timed out")
        except FileNotFoundError:
            logger.info("[MuseOff L4] pytest-testmon not installed, skipping")

    # -------------------------------------------------------------------
    # L5: Chaos Probe（每 6 小時）
    # -------------------------------------------------------------------

    async def probe_chaos(self) -> None:
        """L5: 故障注入——測試系統韌性"""
        if not self._should_probe():
            return

        self._stats["probes_run"] += 1

        # Chaos 1: 讀取空/損壞的 JSON
        test_files = [
            self.home / "data" / "ANIMA_MC.json",
            self.home / "data" / "_system" / "baihe_cache.json",
        ]
        for f in test_files:
            if f.exists():
                try:
                    json.loads(f.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    self._create_finding(
                        probe_layer="L5",
                        severity="HIGH",
                        title=f"JSON 損壞: {f.name}",
                        blast_origin=BlastOrigin(
                            file=str(f.relative_to(self.home)),
                            error_type="JSONDecodeError",
                            traceback=str(e),
                        ),
                        prescription=Prescription(
                            diagnosis=f"JSON 解析失敗: {e}",
                            root_cause="檔案損壞（可能是寫入中途斷電）",
                            suggested_fix="從 backup 恢復",
                        ),
                    )

        # Chaos 2: 檢查 Qdrant 連線韌性
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://127.0.0.1:6333/collections",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        collections = [c["name"] for c in data.get("result", {}).get("collections", [])]
                        expected = ["memories", "skills", "crystals", "dna27"]
                        missing = [c for c in expected if c not in collections]
                        if missing:
                            self._create_finding(
                                probe_layer="L5",
                                severity="HIGH",
                                title=f"Qdrant collections 缺失: {missing}",
                                blast_origin=BlastOrigin(file="qdrant:6333", error_type="MissingCollection"),
                                prescription=Prescription(
                                    diagnosis=f"Expected collections {expected}, missing: {missing}",
                                    suggested_fix="重建 Qdrant collections（Nightly Step 8.6）",
                                ),
                            )
        except Exception:
            pass  # Qdrant 離線已在 L1 檢查過

    # -------------------------------------------------------------------
    # L6: Blueprint Drift（每 12 小時）
    # -------------------------------------------------------------------

    async def probe_blueprint(self) -> None:
        """L6: 藍圖 vs 實際程式碼有沒有漂移？"""
        if not self._should_probe():
            return

        self._stats["probes_run"] += 1

        # 呼叫 validate_connections
        try:
            result = subprocess.run(
                [str(self.home / ".venv" / "bin" / "python"),
                 str(self.home / "scripts" / "validate_connections.py")],
                capture_output=True, text=True, timeout=60,
                cwd=str(self.home),
            )
            if "錯誤" in result.stdout and "0 錯誤" not in result.stdout:
                self._create_finding(
                    probe_layer="L6",
                    severity="MEDIUM",
                    title="Skill 連線驗證發現錯誤",
                    blast_origin=BlastOrigin(file="scripts/validate_connections.py", error_type="ConnectionError"),
                    context={"output": result.stdout[:500]},
                    prescription=Prescription(
                        diagnosis="validate_connections 報告連線錯誤",
                        post_check="python scripts/validate_connections.py",
                    ),
                )
        except (subprocess.TimeoutExpired, OSError):
            pass

        # 用 MuseWorker 快照比對扇入
        snapshot_path = self.home / "data" / "_system" / "museworker" / "snapshot.json"
        if snapshot_path.exists():
            try:
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                path_health = snapshot.get("path_health", {})
                zombies = path_health.get("zombie_files", [])
                if zombies:
                    self._create_finding(
                        probe_layer="L6",
                        severity="LOW",
                        title=f"發現 {len(zombies)} 個殭屍檔案",
                        blast_origin=BlastOrigin(file="data/", error_type="ZombieFile"),
                        context={"zombies": zombies},
                        prescription=Prescription(
                            diagnosis=f"0 bytes 的檔案: {zombies}",
                            suggested_fix="刪除或重建",
                        ),
                    )
            except (json.JSONDecodeError, OSError):
                pass

    # -------------------------------------------------------------------
    # L6b: Crystal Pattern 回饋探針（每 12 小時）
    # -------------------------------------------------------------------

    async def probe_crystal_patterns(self) -> None:
        """L6b: 學習→察覺連線——KnowledgeLattice 中已知失敗模式是否反覆出現？

        從 crystal.db 讀取 failure/error/fix 類型結晶，提取關鍵字，
        比對最近 24h 的 findings，找出「系統已學過但仍在犯的問題」。
        """
        if not self._should_probe():
            return

        self._stats["probes_run"] += 1

        crystal_db = self.home / "data" / "lattice" / "crystal.db"
        if not crystal_db.exists():
            return  # 靜默返回

        # 讀取最近 24h 的 findings 文字（用於關鍵字比對）
        recent_finding_texts: list[dict] = []
        try:
            cutoff = time.time() - 86400  # 24 小時前
            for fpath in sorted(self.findings_dir.glob("*.json")):
                if fpath.stat().st_mtime >= cutoff:
                    try:
                        fd = json.loads(fpath.read_text(encoding="utf-8"))
                        recent_finding_texts.append({
                            "id": fd.get("finding_id", fpath.stem),
                            "text": (fd.get("title", "") + " " + fd.get("prescription", {}).get("diagnosis", "")).lower(),
                        })
                    except (json.JSONDecodeError, OSError):
                        pass
        except OSError:
            pass

        if not recent_finding_texts:
            return  # 最近沒有 finding，不需比對

        # 查詢 crystal.db 中 failure/error/fix 相關結晶
        import sqlite3 as _sqlite3
        crystals: list[dict] = []
        try:
            conn = _sqlite3.connect(str(crystal_db), timeout=5)
            # 嘗試查詢——欄位名稱根據實際 schema，容錯處理
            try:
                rows = conn.execute(
                    """
                    SELECT id, title, content, tags, crystal_type
                    FROM crystals
                    WHERE (crystal_type = 'pattern' OR crystal_type = 'lesson')
                      AND (tags LIKE '%failure%'
                           OR tags LIKE '%error%'
                           OR tags LIKE '%fix%')
                    LIMIT 200
                    """
                ).fetchall()
                for row in rows:
                    crystals.append({
                        "id": row[0],
                        "title": row[1] or "",
                        "content": row[2] or "",
                        "tags": row[3] or "",
                        "type": row[4] or "",
                    })
            except _sqlite3.OperationalError:
                # schema 不同，嘗試不帶 type/tags 過濾
                try:
                    rows = conn.execute(
                        "SELECT id, title, content FROM crystals LIMIT 200"
                    ).fetchall()
                    for row in rows:
                        crystals.append({"id": row[0], "title": row[1] or "", "content": row[2] or ""})
                except _sqlite3.OperationalError:
                    pass
            conn.close()
        except (_sqlite3.DatabaseError, OSError):
            return  # 靜默返回

        if not crystals:
            return

        # 從結晶 content 提取關鍵字（取較具體的技術詞彙）
        _STOPWORDS = {"the", "a", "an", "is", "in", "on", "at", "to", "of", "and", "or", "for",
                      "with", "it", "this", "that", "was", "are", "be", "by", "from", "as", "有",
                      "的", "了", "在", "是", "和", "不", "也", "會", "可", "以", "但", "到"}
        import re as _re

        def _extract_keywords(text: str) -> list[str]:
            # 保留英數詞（≥4 字元）及中文技術詞（≥2 字）
            tokens = _re.findall(r'[a-zA-Z0-9_\-]{4,}|[\u4e00-\u9fff]{2,}', text)
            return [t.lower() for t in tokens if t.lower() not in _STOPWORDS][:30]

        # 比對 findings
        matches: list[dict] = []
        for crystal in crystals:
            combined_text = crystal.get("title", "") + " " + crystal.get("content", "")
            keywords = _extract_keywords(combined_text)
            if not keywords:
                continue
            for finding in recent_finding_texts:
                finding_text = finding["text"]
                matched_kw = next((kw for kw in keywords if kw in finding_text), None)
                if matched_kw:
                    crystal_id = str(crystal.get("id", ""))
                    finding_id = finding["id"]
                    # 避免重複記錄同一組合
                    if not any(
                        m["crystal_id"] == crystal_id and m["finding_id"] == finding_id
                        for m in matches
                    ):
                        matches.append({
                            "crystal_id": crystal_id,
                            "finding_id": finding_id,
                            "keyword": matched_kw,
                        })
                        pattern_title = crystal.get("title") or f"crystal#{crystal_id}"
                        logger.info(
                            "[MuseOff L6] Crystal-informed: 已知模式 '%s' 再次出現（關鍵字: %s）",
                            pattern_title,
                            matched_kw,
                        )

        # 寫入 crystal_informed.json
        output_dir = self.home / "data" / "_system" / "museoff"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "crystal_informed.json"
        try:
            output_path.write_text(
                json.dumps(
                    {"updated_at": _now_iso(), "matches": matches},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("[MuseOff L6] 寫入 crystal_informed.json 失敗: %s", e)

    # -------------------------------------------------------------------
    # L6c: 意識→察覺連線 — pulse_alerts 消費端
    # -------------------------------------------------------------------

    async def probe_pulse_alerts(self) -> None:
        """L6c: 意識→察覺連線——讀取 pulse_engine 寫入的 pulse_alerts.jsonl，
        對反覆出現的 keyword 或 CRITICAL severity 建立 finding。
        """
        if not self._should_probe():
            return

        self._stats["probes_run"] += 1

        alerts_path = self.home / "data" / "_system" / "pulse_alerts.jsonl"
        if not alerts_path.exists():
            return  # 靜默返回

        cutoff = time.time() - 86400  # 最近 24h
        keyword_counts: dict[str, int] = {}
        critical_alerts: list[str] = []

        try:
            with alerts_path.open("r", encoding="utf-8") as f:
                for raw_line in f:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        entry = json.loads(raw_line)
                        # 時間過濾：用 timestamp 欄位（ISO8601）
                        ts_str = entry.get("timestamp", "")
                        if ts_str:
                            try:
                                from datetime import datetime, timezone
                                ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                ts_epoch = ts_dt.timestamp()
                                if ts_epoch < cutoff:
                                    continue
                            except (ValueError, OSError):
                                pass  # 無法解析時間 → 不過濾

                        keyword = entry.get("keyword", entry.get("type", "unknown"))
                        severity = entry.get("severity", "").upper()

                        if keyword:
                            keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1

                        if severity == "CRITICAL":
                            msg = entry.get("message", entry.get("detail", keyword))
                            critical_alerts.append(str(msg))

                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError:
            return  # 靜默返回

        # 反覆問題（同一 keyword 出現 3+ 次）→ MEDIUM finding
        for keyword, count in keyword_counts.items():
            if count >= 3:
                self._create_finding(
                    probe_layer="L6c",
                    severity="MEDIUM",
                    title=f"意識層偵測到反覆問題：{keyword}，出現 {count} 次",
                    blast_origin=BlastOrigin(
                        file="data/_system/pulse_alerts.jsonl",
                        error_type="RepeatedAlert",
                    ),
                    context={"keyword": keyword, "count": count},
                    prescription=Prescription(
                        diagnosis=f"pulse_alerts.jsonl 中關鍵字 '{keyword}' 在最近 24h 出現 {count} 次",
                        root_cause="可能是系統持續性問題導致 pulse_engine 循環觸發",
                        suggested_fix=f"調查 pulse_engine 寫入的 '{keyword}' 告警來源",
                    ),
                )

        # CRITICAL severity alert → HIGH finding
        for msg in critical_alerts:
            self._create_finding(
                probe_layer="L6c",
                severity="HIGH",
                title=f"意識層 CRITICAL 告警：{msg[:80]}",
                blast_origin=BlastOrigin(
                    file="data/_system/pulse_alerts.jsonl",
                    error_type="CriticalAlert",
                ),
                context={"alert_message": msg},
                prescription=Prescription(
                    diagnosis=f"pulse_engine 寫入了 CRITICAL 級別的告警：{msg}",
                    root_cause="系統觸發了嚴重等級的 pulse 告警",
                    suggested_fix="立即調查 pulse_alerts.jsonl 中的 CRITICAL 條目，確認系統狀態",
                ),
            )

    # -------------------------------------------------------------------
    # L7: 管線完整性探針 — 消費端→寫入端反向追蹤
    # -------------------------------------------------------------------

    async def probe_pipeline_integrity(self) -> None:
        """L7: 管線完整性 — 從消費端倒追寫入端，驗證關鍵管線是否接通。

        方法論來源：2026-03-25 session 教訓——
        「寫入成功≠系統能用」「追完整條消費鏈」「測試通過≠系統會執行」
        """
        if not self._should_probe():
            return

        self._stats["probes_run"] += 1
        broken_pipelines = []

        # --- 檢查 1: Nightly _FULL_STEPS 與 self._steps 一致性 ---
        try:
            nightly_path = self.home / "src" / "museon" / "nightly" / "nightly_pipeline.py"
            if nightly_path.exists():
                content = nightly_path.read_text(encoding="utf-8")
                # 提取 _FULL_STEPS 列表
                import re
                full_match = re.search(r'_FULL_STEPS\s*=\s*\[(.*?)\]', content, re.DOTALL)
                steps_match = re.findall(r'"([\d.]+)":\s*\(', content)
                if full_match and steps_match:
                    full_steps = set(re.findall(r'"([\d.]+)"', full_match.group(1)))
                    registered_steps = set(steps_match)
                    missing = registered_steps - full_steps
                    if missing:
                        broken_pipelines.append(f"_FULL_STEPS 漏列: {missing}")
        except Exception:
            pass

        # --- 檢查 2: Crystal Actuator 規則品質 ---
        try:
            rules_path = self.home / "data" / "_system" / "crystal_rules.json"
            if rules_path.exists():
                rules_data = json.loads(rules_path.read_text(encoding="utf-8"))
                rules = rules_data.get("rules", [])
                # 檢查是否有保護規則存在
                boss_rules = [r for r in rules if "boss_directive" in r.get("crystal_origin", "")]
                if len(boss_rules) == 0:
                    broken_pipelines.append("Crystal Actuator 無 boss_directive 規則——教訓蒸餾管線可能斷裂")
                # 檢查是否有垃圾規則（summary 太長或包含程式碼）
                garbage = [r for r in rules if len(r.get("summary", "")) > 200 or "```" in r.get("summary", "")]
                if len(garbage) > 5:
                    broken_pipelines.append(f"Crystal Actuator 可能有 {len(garbage)} 條垃圾規則")
        except Exception:
            pass

        # --- 檢查 3: memories Qdrant collection 是否有資料 ---
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(host="localhost", port=6333, timeout=5)
            info = client.get_collection("memories")
            if info.points_count == 0:
                broken_pipelines.append("Qdrant memories collection 是空的——語義搜索完全失效")
            # 檢查維度是否匹配 embedder
            if info.config.params.vectors.size != 512:
                broken_pipelines.append(
                    f"memories 維度={info.config.params.vectors.size}，embedder 產出 512——維度不匹配"
                )
        except Exception:
            pass

        # --- 檢查 4: heuristics.json 是否存在且有效 ---
        try:
            heur_path = self.home / "data" / "intuition" / "heuristics.json"
            if not heur_path.exists():
                broken_pipelines.append("heuristics.json 不存在——Intuition 注入是空殼")
            else:
                heur_data = json.loads(heur_path.read_text(encoding="utf-8"))
                if len(heur_data.get("rules", [])) == 0:
                    broken_pipelines.append("heuristics.json 規則為空——Intuition 注入無效")
        except Exception:
            pass

        # --- 檢查 5: GroupContextStore 有 DM + bot_reply 記錄 ---
        try:
            import sqlite3
            db_path = self.home / "data" / "_system" / "group_context.db"
            if db_path.exists():
                conn = sqlite3.connect(str(db_path), timeout=5)
                dm_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE msg_type='dm'"
                ).fetchone()[0]
                bot_count = conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE msg_type='bot_reply'"
                ).fetchone()[0]
                conn.close()
                if dm_count == 0 and bot_count == 0:
                    broken_pipelines.append("GroupContextStore 無 DM/bot_reply 記錄——對話持久化管線可能斷裂")
        except Exception:
            pass

        # --- 檢查 6: Cron Job 健康度 ---
        try:
            from museon.gateway.cron import CronEngine as _CronEngine
            import sys as _sys
            # 取得已在 server 模組中初始化的全域 cron_engine（避免重複建立實例）
            _server_mod = _sys.modules.get("museon.gateway.server")
            _cron = getattr(_server_mod, "cron_engine", None)
            if _cron and hasattr(_cron, "status"):
                _cron_stats = _cron.status()
                _unhealthy = []
                for _jid, _s in _cron_stats.items():
                    if _s.get("consecutive_failures", 0) >= 3:
                        _unhealthy.append(
                            f"{_jid}: {_s['consecutive_failures']} consecutive failures, "
                            f"last_error={_s.get('last_error', '?')}"
                        )
                if _unhealthy:
                    broken_pipelines.append(f"Cron jobs unhealthy: {'; '.join(_unhealthy[:5])}")
        except Exception:
            pass

        if broken_pipelines:
            self._create_finding(
                probe_layer="L7",
                severity="HIGH",
                title=f"管線完整性問題: {len(broken_pipelines)} 條斷裂",
                blast_origin=BlastOrigin(file="system-wide", error_type="PipelineIntegrity"),
                context={"broken_pipelines": broken_pipelines},
                prescription=Prescription(
                    diagnosis="\n".join(broken_pipelines),
                    suggested_fix="執行 /fv audit 進行三維 Fix-Verify 驗證",
                ),
            )

    # -------------------------------------------------------------------
    # 一次全跑（CLI 用）
    # -------------------------------------------------------------------

    async def run_all_once(self) -> dict:
        """跑一輪全部探測（CLI --once 用）"""
        results = {}
        probes = [
            ("L0", self.probe_liveness),
            ("L1", self.probe_readiness),
            ("L2", self.probe_import),
            ("L2b", self.probe_anima_integrity),
            ("L3", self.probe_config),
            ("L4", self.probe_regression),
            ("L5", self.probe_chaos),
            ("L6", self.probe_blueprint),
            ("L6b", self.probe_crystal_patterns),
            ("L6c", self.probe_pulse_alerts),
            ("L7", self.probe_pipeline_integrity),
        ]
        for name, func in probes:
            t0 = time.monotonic()
            try:
                await asyncio.wait_for(func(), timeout=self.MAX_PROBE_DURATION)
                results[name] = {"status": "ok", "duration_ms": int((time.monotonic() - t0) * 1000)}
            except asyncio.TimeoutError:
                results[name] = {"status": "timeout", "duration_ms": self.MAX_PROBE_DURATION * 1000}
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}

        self._save_baselines()
        self._save_stats()

        # 寫入共享看板
        findings_count = self._stats["findings_created"]
        status = "critical" if findings_count > 5 else "warning" if findings_count > 0 else "ok"
        update_shared_board(
            self._data_dir,
            source="museoff",
            summary=f"巡邏完成: {self._stats['probes_run']} 探針, {findings_count} 發現, {self._stats['triages_executed']} 應急",
            findings_count=findings_count,
            actions=[f"triage:{self._stats['triages_executed']}"],
            status=status,
        )

        return results

    # -------------------------------------------------------------------
    # 應急處理
    # -------------------------------------------------------------------

    def _triage(self, action: str) -> None:
        """執行應急動作"""
        logger.info("[MuseOff] Triage: %s", action)
        self._stats["triages_executed"] += 1

        entry = {"timestamp": _now_iso(), "action": action, "result": "unknown"}

        if action == "restart_gateway":
            script = self.home / "scripts" / "workflows" / "restart-gateway.sh"
            try:
                result = subprocess.run(
                    ["bash", str(script)],
                    timeout=120, capture_output=True
                )
                entry["result"] = "success" if result.returncode == 0 else f"rc={result.returncode}"
            except Exception as e:
                entry["result"] = f"failed: {e}"

        elif action == "kill_zombie_bun":
            try:
                subprocess.run(
                    ["pkill", "-f", "bun.*server.ts.*orphan"],
                    timeout=5, capture_output=True,
                )
                entry["result"] = "attempted"
            except Exception:
                entry["result"] = "failed"

        # 記錄 triage log
        with open(self.triage_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -------------------------------------------------------------------
    # Finding 建立（含去重）
    # -------------------------------------------------------------------

    def _create_finding(
        self,
        probe_layer: str,
        severity: str,
        title: str,
        blast_origin: BlastOrigin,
        blast_radius: list[BlastTarget] | None = None,
        context: dict | None = None,
        prescription: Prescription | None = None,
    ) -> Finding | None:
        finding = Finding(
            probe_layer=probe_layer,
            severity=severity,
            title=title,
            source="museoff",
            blast_origin=blast_origin,
            blast_radius=blast_radius or [],
            context=context or {},
            prescription=prescription,
        )

        if self._store.is_duplicate(finding):
            logger.debug("[MuseOff] Duplicate finding suppressed: %s", title)
            return None

        self._store.save(finding)
        self._stats["findings_created"] += 1
        logger.info("[MuseOff] Finding created: %s [%s] %s", finding.finding_id, severity, title)

        # 反覆出現的問題 → 升級給 Morphenix
        origin_key = self._store._origin_key(finding)
        occurrence_count = self._store.record_occurrence(origin_key)
        if occurrence_count >= 3:
            try:
                from museon.nightly.triage_step import write_signal
                from museon.core.awareness import (
                    AwarenessSignal,
                    Severity as AwSeverity,
                    SignalType,
                    Actionability,
                )
                write_signal(self.home, AwarenessSignal(
                    source="museoff",
                    severity=AwSeverity.HIGH,
                    signal_type=SignalType.SYSTEM_FAULT,
                    title=f"反覆失敗({occurrence_count}次): {title[:50]}",
                    actionability=Actionability.AUTO,
                    suggested_action="escalate_to_morphenix",
                    context={"finding_key": origin_key, "count": occurrence_count},
                ))
                logger.warning(
                    "[MuseOff] Finding '%s' occurred %d times, escalated to Morphenix",
                    origin_key,
                    occurrence_count,
                )
            except Exception:
                pass  # 升級失敗不阻擋主流程

        # 即時 DM 通知老闆（所有 severity 都通知）
        try:
            from museon.doctor.notify import notify_owner
            notify_owner(severity, title, finding.finding_id, source="museoff", home=self.home)
        except Exception:
            pass  # 通知失敗不阻擋主流程

        return finding

    # -------------------------------------------------------------------
    # 效能控制
    # -------------------------------------------------------------------

    def _should_probe(self) -> bool:
        """系統負載過高時暫停巡邏"""
        try:
            load = os.getloadavg()[0] / os.cpu_count()
            return load < 0.7
        except (OSError, AttributeError):
            return True

    # -------------------------------------------------------------------
    # 持久化
    # -------------------------------------------------------------------

    def _load_baselines(self) -> None:
        if self.baselines_path.exists():
            try:
                data = json.loads(self.baselines_path.read_text(encoding="utf-8"))
                self._baseline.load_from_dict(data)
            except (json.JSONDecodeError, OSError):
                pass

    def _save_baselines(self) -> None:
        self.baselines_path.parent.mkdir(parents=True, exist_ok=True)
        self.baselines_path.write_text(
            json.dumps(self._baseline.to_dict(), ensure_ascii=False),
            encoding="utf-8",
        )

    def _save_stats(self) -> None:
        self.stats_path.write_text(
            json.dumps(self._stats, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    async def main():
        off = MuseOff()
        if "--once" in sys.argv:
            results = await off.run_all_once()
            print(f"\n{'='*50}")
            print("MuseOff 巡邏報告")
            print(f"{'='*50}")
            for layer, r in results.items():
                status = r["status"]
                icon = "✅" if status == "ok" else "❌" if status == "error" else "⏱"
                duration = r.get("duration_ms", "?")
                print(f"  {icon} {layer}: {status} ({duration}ms)")
            print(f"\nFindings: {off._stats['findings_created']}")
            print(f"Triages: {off._stats['triages_executed']}")
        else:
            print("Usage: python -m museon.doctor.museoff --once")

    asyncio.run(main())
