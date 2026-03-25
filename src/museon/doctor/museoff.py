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

        self._store = FindingStore(self.findings_dir)
        self._baseline = BaselineTracker()
        self._load_baselines()
        self._stats = {"probes_run": 0, "findings_created": 0, "triages_executed": 0}

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
                blast_origin=BlastOrigin(file=detail, error_type=issue_type),
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
            ("L3", self.probe_config),
            ("L4", self.probe_regression),
            ("L5", self.probe_chaos),
            ("L6", self.probe_blueprint),
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
            if script.exists():
                try:
                    subprocess.run(["bash", str(script)], timeout=60, capture_output=True)
                    entry["result"] = "success"
                except Exception as e:
                    entry["result"] = f"failed: {e}"
            else:
                entry["result"] = "script_not_found"

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
