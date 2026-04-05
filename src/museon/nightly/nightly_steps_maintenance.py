"""NightlyStepsMaintenanceMixin — 系統維護步驟群 (Steps 20-32.5).

包含突觸衰減、肌肉萎縮、免疫清除、觸發評估、演化速度、週/月循環、
日誌輪替、WAL Checkpoint、資料看門狗、藍圖一致性、快取重建、結晶衰減、
荒謬雷達重算等系統健康維護步驟。
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from museon.core.event_bus import (
    DATA_DEAD_WRITE_DETECTED,
    DATA_HEALTH_CHECKED,
    DATA_STORAGE_WARNING,
    DATA_STORE_DEGRADED,
    EVOLUTION_VELOCITY_ALERT,
)

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


class NightlyStepsMaintenanceMixin:
    """系統維護步驟 Mixin (Steps 20-32.5)."""

    # ═══════════════════════════════════════════
    # Step 20: 突觸衰減
    # ═══════════════════════════════════════════

    def _step_synapse_decay(self) -> Dict:
        """Step 20: SkillSynapse 每日衰減 — 所有突觸權重 ×0.98."""
        try:
            from museon.evolution.skill_synapse import SynapseNetwork
            network = SynapseNetwork(data_dir=self._workspace)
        except Exception as e:
            return {"skipped": f"SynapseNetwork not available: {e}"}

        decayed_count = network.daily_decay()
        preloads = network.get_strongest_connections(limit=5)

        # 預載候選發布事件
        if preloads and self._event_bus:
            try:
                from museon.core.event_bus import SYNAPSE_PRELOAD
                self._event_bus.publish(SYNAPSE_PRELOAD, {
                    "strongest": preloads[:3],
                })
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {
            "decayed_synapses": decayed_count,
            "top_connections": preloads[:5],
        }

    # ═══════════════════════════════════════════
    # Step 21: 肌肉萎縮
    # ═══════════════════════════════════════════

    def _step_muscle_atrophy(self) -> Dict:
        """Step 21: ToolMuscle 每日萎縮 — 所有工具熟練度 ×0.99."""
        try:
            from museon.evolution.tool_muscle import ToolMuscleTracker
            tracker = ToolMuscleTracker(data_dir=self._workspace)
        except Exception as e:
            return {"skipped": f"ToolMuscleTracker not available: {e}"}

        atrophied_count = tracker.daily_atrophy()
        dormant = tracker.get_dormant_tools(days=30)

        # 休眠工具發布事件
        if dormant and self._event_bus:
            try:
                from museon.core.event_bus import TOOL_MUSCLE_DORMANT
                self._event_bus.publish(TOOL_MUSCLE_DORMANT, {
                    "dormant_tools": dormant[:10],
                    "count": len(dormant),
                })
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {
            "atrophied_tools": atrophied_count,
            "dormant_count": len(dormant),
            "dormant_tools": [d.get("tool_id", "") if isinstance(d, dict) else str(d) for d in dormant[:5]],
        }

    # ═══════════════════════════════════════════
    # Step 22: 弱免疫規則清除
    # ═══════════════════════════════════════════

    def _step_immune_prune(self) -> Dict:
        """Step 22: ImmuneMemory 弱規則清除 — confidence < 0.2 的移除."""
        try:
            from museon.governance.immune_memory import ImmuneMemoryBank
            bank = ImmuneMemoryBank(data_dir=self._workspace)
        except Exception as e:
            return {"skipped": f"ImmuneMemoryBank not available: {e}"}

        pruned = bank.prune_weak()
        stats = bank.get_stats()
        active = bank.get_active_defenses()

        # 學到新防禦時發布事件
        if active and self._event_bus:
            try:
                from museon.core.event_bus import IMMUNE_MEMORY_LEARNED
                self._event_bus.publish(IMMUNE_MEMORY_LEARNED, {
                    "active_defenses": len(active),
                    "avg_confidence": stats.get("avg_confidence", 0),
                })
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {
            "pruned_weak_rules": pruned,
            "total_memories": stats.get("total_memories", 0),
            "active_defenses": stats.get("active_defenses", 0),
            "avg_confidence": stats.get("avg_confidence", 0),
        }

    # ═══════════════════════════════════════════
    # Step 23: 13 觸發器綜合評估
    # ═══════════════════════════════════════════

    def _step_trigger_evaluation(self) -> Dict:
        """Step 23: TriggerEngine 綜合評估 — 13 觸發器掃描.

        收集各觸發因子，計算 trigger_score = Σ(weight × factor) × vitality。
        """
        try:
            from museon.evolution.trigger_weights import TriggerEngine, TriggerType
            engine = TriggerEngine(data_dir=self._workspace)
        except Exception as e:
            return {"skipped": f"TriggerEngine not available: {e}"}

        # 收集因子
        factors: Dict[str, float] = {}

        # 1. 統計累積 — WEE 執行次數
        wee_runs_dir = self._workspace / "_system" / "wee" / "sessions"
        if wee_runs_dir.exists():
            run_count = len(list(wee_runs_dir.glob("*.json")))
            factors[TriggerType.STAT_ACCUMULATION.value] = min(1.0, run_count / 50.0)

        # 2. 時間週期 — 夜間固定高
        factors[TriggerType.TIME_CYCLE.value] = 0.8

        # 4. 餘裕探索 — TokenBudget reserve 健康度
        try:
            from museon.pulse.token_budget import TokenBudgetManager
            budget = TokenBudgetManager(data_dir=self._workspace)
            if budget.can_afford_exploration():
                factors[TriggerType.SURPLUS_BASED.value] = 0.7
            vitality = budget.get_vitality_modifier()
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            vitality = 1.0

        # 13. 熵增警報 — 檢查系統目錄大小
        system_dir = self._workspace / "_system"
        if system_dir.exists():
            file_count = sum(1 for _ in system_dir.rglob("*") if _.is_file())
            factors[TriggerType.ENTROPY_ALARM.value] = min(1.0, file_count / 1000.0)

        # 執行評估
        result = engine.evaluate(factors=factors, vitality_modifier=vitality)

        # 觸發事件
        if result.should_evolve and self._event_bus:
            try:
                from museon.core.event_bus import TRIGGER_FIRED
                self._event_bus.publish(TRIGGER_FIRED, {
                    "total_score": result.total_score,
                    "fired_triggers": result.fired_triggers,
                    "vitality_modifier": result.vitality_modifier,
                })
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        # ── 修復→認知：將今日修復事件摘要寫入 EvalEngine 可讀的路徑 ──
        try:
            import json
            from datetime import date
            repair_log_path = self._workspace / "guardian" / "repair_log.jsonl"
            if repair_log_path.exists():
                today_str = date.today().isoformat()
                total_repairs = 0
                success_count = 0
                failed_count = 0
                details = []
                with open(repair_log_path, encoding="utf-8") as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if not _line:
                            continue
                        try:
                            _entry = json.loads(_line)
                        except json.JSONDecodeError:
                            continue
                        # 只統計今日事件（依 timestamp 欄位，格式 YYYY-MM-DD...）
                        _ts = _entry.get("timestamp", "") or _entry.get("date", "")
                        if not str(_ts).startswith(today_str):
                            continue
                        total_repairs += 1
                        _repair_id = _entry.get("repair_id", _entry.get("id", "unknown"))
                        _status = str(_entry.get("status", "")).upper()
                        if _status in ("OK", "SUCCESS", "DONE", "FIXED", "REPAIRED"):
                            success_count += 1
                            details.append(f"{_repair_id}: OK")
                        else:
                            failed_count += 1
                            details.append(f"{_repair_id}: FAILED")

                if total_repairs > 0:
                    _success_rate = round(success_count / total_repairs, 2)
                    _eval_dir = self._workspace / "eval"
                    _eval_dir.mkdir(parents=True, exist_ok=True)
                    _quality_path = _eval_dir / "repair_quality.json"
                    _payload = {
                        "date": today_str,
                        "total_repairs": total_repairs,
                        "success": success_count,
                        "failed": failed_count,
                        "success_rate": _success_rate,
                        "details": details,
                    }
                    with open(_quality_path, "w", encoding="utf-8") as _out:
                        json.dump(_payload, _out, ensure_ascii=False, indent=2)
                    logger.info(
                        f"[NIGHTLY] 修復品質摘要已寫入 eval/repair_quality.json — "
                        f"共 {total_repairs} 筆，成功率 {_success_rate:.0%}"
                    )
                else:
                    logger.debug("[NIGHTLY] 今日無修復事件，跳過 repair_quality 寫入")
        except Exception as _repair_exc:
            logger.warning(f"[NIGHTLY] 修復→認知弱通連線失敗（不影響主流程）：{_repair_exc}")

        return {
            "total_score": result.total_score,
            "vitality_modifier": result.vitality_modifier,
            "fired_triggers": result.fired_triggers,
            "should_evolve": result.should_evolve,
            "details": result.details,
        }

    # ═══════════════════════════════════════════
    # Evolution Architecture 新增步驟
    # ═══════════════════════════════════════════

    def _step_evolution_velocity(self) -> Dict:
        """Step 24: 演化速度計算.

        每日累計（週日正式計算完整快照），追蹤五項核心指標的趨勢。
        """
        try:
            from museon.evolution.evolution_velocity import get_evolution_velocity
            ev = get_evolution_velocity(self._workspace)
            snapshot = ev.calculate_weekly()
            dashboard = ev.get_dashboard()

            # 若偵測到高原期或退化，發布事件
            if snapshot.plateau_alert or snapshot.regression_alert:
                self._publish(EVOLUTION_VELOCITY_ALERT, {
                    "composite_velocity": dashboard.get("composite_velocity", 0),
                    "trend": dashboard.get("trend", "unknown"),
                    "plateau_alert": snapshot.plateau_alert,
                    "regression_alert": snapshot.regression_alert,
                })

            return {
                "composite_velocity": dashboard.get("composite_velocity", 0),
                "trend": dashboard.get("trend", "unknown"),
                "plateau_alert": snapshot.plateau_alert,
                "regression_alert": snapshot.regression_alert,
            }
        except Exception as e:
            return {"skipped": f"EvolutionVelocity not available: {e}"}

    def _step_periodic_cycle_check(self) -> Dict:
        """Step 25: 週/月循環觸發檢查.

        檢查今天是否為週日或月初，若是則自動執行對應的週/月循環。
        """
        now = datetime.now(TZ_TAIPEI)
        results: Dict[str, Any] = {"checked_at": now.isoformat()}

        try:
            from museon.nightly.periodic_cycles import WeeklyCycle, MonthlyCycle

            # 週日執行週循環
            if now.weekday() == 6:  # Sunday
                weekly = WeeklyCycle(
                    workspace=self._workspace,
                    event_bus=self._event_bus,
                )
                weekly_report = weekly.run()
                results["weekly_cycle"] = {
                    "executed": True,
                    "ok": weekly_report.get("summary", {}).get("ok", 0),
                    "error": weekly_report.get("summary", {}).get("error", 0),
                }
                logger.info(
                    f"[NIGHTLY] Weekly cycle executed: "
                    f"{results['weekly_cycle']}"
                )
            else:
                results["weekly_cycle"] = {"executed": False, "reason": f"weekday={now.weekday()}"}

            # 月初執行月循環
            if now.day == 1:
                monthly = MonthlyCycle(
                    workspace=self._workspace,
                    event_bus=self._event_bus,
                )
                monthly_report = monthly.run()
                results["monthly_cycle"] = {
                    "executed": True,
                    "ok": monthly_report.get("summary", {}).get("ok", 0),
                    "error": monthly_report.get("summary", {}).get("error", 0),
                }
                logger.info(
                    f"[NIGHTLY] Monthly cycle executed: "
                    f"{results['monthly_cycle']}"
                )
            else:
                results["monthly_cycle"] = {"executed": False, "reason": f"day={now.day}"}

        except Exception as e:
            results["error"] = f"PeriodicCycles not available: {e}"

        return results

    # v1.75: _step_session_cleanup (Step 26) 已刪除，由每小時 cron 涵蓋，Nightly 重複執行無附加價值

    # ═══════════════════════════════════════════
    # Step 27: JSONL 日誌輪替
    # ═══════════════════════════════════════════

    def _step_log_rotation(self) -> Dict:
        """Step 27: 輪替無日期的 JSONL 日誌 — 超過 5MB 自動歸檔."""
        import gzip
        import shutil

        SIZE_THRESHOLD = 5 * 1024 * 1024  # 5 MB
        MAX_ARCHIVE_DAYS = 30

        # 已知的無日期 JSONL 檔案（相對於 workspace）
        jsonl_paths = [
            "heartbeat.jsonl",
            "_system/footprints/actions.jsonl",
            "_system/footprints/decisions.jsonl",
            "_system/footprints/evolutions.jsonl",
            "intuition/signal_log.jsonl",
            "eval/q_scores.jsonl",
            "eval/satisfaction.jsonl",
        ]

        rotated = []
        cleaned = []
        today_str = datetime.now(TZ_TAIPEI).strftime("%Y%m%d")

        for rel_path in jsonl_paths:
            fp = self._workspace / rel_path
            if not fp.exists():
                continue

            try:
                size = fp.stat().st_size
                if size < SIZE_THRESHOLD:
                    continue

                # 歸檔：rename → .gz
                archive_name = f"{fp.stem}_{today_str}.jsonl.gz"
                archive_path = fp.parent / archive_name

                with open(fp, "rb") as f_in:
                    with gzip.open(archive_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # 清空原檔（保留檔案，避免其他進程 FileNotFoundError）
                with open(fp, "w") as f:
                    pass

                rotated.append(f"{rel_path} ({size // 1024}KB)")

            except Exception as e:
                logger.debug(f"[NIGHTLY] log rotation skip {rel_path}: {e}")

        # 清理超過 30 天的 .gz 歸檔
        cutoff = time.time() - MAX_ARCHIVE_DAYS * 86400
        for gz in self._workspace.rglob("*.jsonl.gz"):
            try:
                if gz.stat().st_mtime < cutoff:
                    gz.unlink()
                    cleaned.append(gz.name)
            except Exception:
                pass

        if rotated:
            logger.info(f"[NIGHTLY] log rotation: {rotated}")

        # ── 按日期命名的 JSONL 清理（cache_log_*, routing_log_* 等）──
        # 這些檔案每天自動產生，保留 30 天，超齡刪除
        dated_jsonl_dirs = [
            self._workspace / "_system" / "budget",   # cache_log_YYYY-MM-DD.jsonl
            self._workspace / "_system" / "pulse",     # routing_log_YYYY-MM-DD.jsonl
        ]
        dated_removed = 0
        for d in dated_jsonl_dirs:
            if not d.exists():
                continue
            for f in d.glob("*_20??-??-??.jsonl"):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
                        dated_removed += 1
                except Exception:
                    pass
        if dated_removed > 0:
            logger.info(f"[NIGHTLY] dated JSONL cleanup: removed {dated_removed}")

        return {
            "rotated": rotated,
            "archives_cleaned": len(cleaned),
            "dated_jsonl_removed": dated_removed,
        }

    def _step_wal_checkpoint(self) -> Dict:
        """Step 28: SQLite WAL Checkpoint — 壓縮所有 WAL 日誌.

        避免 WAL 檔案無限成長（group_context.db-wal 曾達 4MB）。
        對所有已知的 SQLite 資料庫執行 PRAGMA wal_checkpoint(TRUNCATE)。
        """
        import sqlite3

        DB_PATHS = [
            self._workspace / "pulse" / "pulse.db",
            self._workspace / "_system" / "group_context.db",
            self._workspace / "_system" / "wee" / "workflow_state.db",
            self._workspace / "registry" / "cli_user" / "registry.db",
        ]

        results = {}
        for db_path in DB_PATHS:
            name = db_path.stem
            if not db_path.exists():
                results[name] = "not_found"
                continue
            try:
                conn = sqlite3.connect(str(db_path), timeout=10)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.close()
                # 檢查 WAL 檔案大小
                wal_path = db_path.parent / f"{db_path.name}-wal"
                wal_size = wal_path.stat().st_size if wal_path.exists() else 0
                results[name] = f"ok (wal={wal_size}B)"
            except Exception as e:
                results[name] = f"error: {e}"
                logger.debug(f"[NIGHTLY] WAL checkpoint {name}: {e}")

        logger.info(f"[NIGHTLY] WAL checkpoint: {results}")
        return {"databases": results}

    def _auto_register_known_stores(self, bus) -> None:
        """自動發現並註冊已知的 DataContract Store 到 DataBus.

        Phase 3 設計了 DataContract 介面，PulseDB/GroupContextStore 皆有實作，
        但「註冊環節」未完成。此方法在 DataWatchdog 步驟中補完。
        """
        # PulseDB（singleton，不會重複建立）
        pulse_path = self._workspace / "pulse" / "pulse.db"
        if pulse_path.exists():
            try:
                from museon.pulse.pulse_db import get_pulse_db
                pulse_db = get_pulse_db(self._workspace)
                spec = pulse_db.store_spec() if hasattr(pulse_db, "store_spec") else None
                bus.register("pulse", pulse_db, spec)
            except Exception as e:
                logger.debug(f"[NIGHTLY] Auto-register pulse failed: {e}")

        # GroupContextStore
        gc_path = self._workspace / "_system" / "group_context.db"
        if gc_path.exists():
            try:
                from museon.governance.group_context import GroupContextStore
                gc_store = GroupContextStore(data_dir=self._workspace)
                spec = gc_store.store_spec() if hasattr(gc_store, "store_spec") else None
                bus.register("group_context", gc_store, spec)
            except Exception as e:
                logger.debug(f"[NIGHTLY] Auto-register group_context failed: {e}")

        # WorkflowEngine（工作流狀態 SQLite）
        wf_path = self._workspace / "_system" / "wee" / "workflow_state.db"
        if wf_path.exists():
            try:
                from museon.workflow.workflow_engine import WorkflowEngine
                wf_engine = WorkflowEngine(workspace=self._workspace)
                spec = wf_engine.store_spec() if hasattr(wf_engine, "store_spec") else None
                bus.register("workflow_state_db", wf_engine, spec)
                # 順便清理過期 executions（已歸檔工作流的 90 天以上紀錄）
                if hasattr(wf_engine, "cleanup_old_executions"):
                    cleanup_result = wf_engine.cleanup_old_executions(days=90)
                    if cleanup_result.get("deleted_executions", 0) > 0:
                        logger.info(f"[NIGHTLY] WorkflowEngine cleanup: {cleanup_result}")
            except Exception as e:
                logger.debug(f"[NIGHTLY] Auto-register workflow_state_db failed: {e}")

    def _step_data_watchdog(self) -> Dict:
        """Step 29: DataWatchdog — 資料層健康監控、空間預警、Dead Write 偵測.

        基於 Phase 3 DataContract + DataBus 架構：
        - 對所有已註冊 Store 執行 health_check
        - 檢查儲存空間閾值
        - 比對歷史快照偵測 Dead Write
        - 發布 EventBus 告警事件
        """
        from museon.core.data_bus import get_data_bus
        from museon.core.data_watchdog import DataWatchdog

        bus = get_data_bus()

        # 自動發現並註冊已知 Store（Phase 3 未完成的註冊環節）
        if not bus.list_stores():
            self._auto_register_known_stores(bus)
        if not bus.list_stores():
            logger.info("[NIGHTLY] DataWatchdog: 無可註冊的 Store，跳過")
            return {"status": "skipped", "reason": "no stores found"}

        watchdog = DataWatchdog(data_dir=self._workspace)
        report = watchdog.run_health_check(bus=bus)

        # 發布 EventBus 事件
        self._publish(DATA_HEALTH_CHECKED, {
            "status": report["status"],
            "store_count": len(report["stores"]),
            "alert_count": len(report["alerts"]),
            "total_bytes": report["storage"]["total_bytes"],
        })

        # 個別告警事件
        for alert in report.get("alerts", []):
            if alert["severity"] == "critical":
                self._publish(DATA_STORE_DEGRADED, alert)
            elif "空間" in alert.get("message", "") or "預警線" in alert.get("message", ""):
                self._publish(DATA_STORAGE_WARNING, alert)

        for suspect in report.get("dead_write_suspects", []):
            self._publish(DATA_DEAD_WRITE_DETECTED, suspect)

        logger.info(
            f"[NIGHTLY] DataWatchdog: {report['status']} | "
            f"stores={len(report['stores'])} | "
            f"alerts={len(report['alerts'])} | "
            f"dead_suspects={len(report['dead_write_suspects'])}"
        )

        return {
            "status": report["status"],
            "stores_checked": len(report["stores"]),
            "alerts": len(report["alerts"]),
            "dead_write_suspects": len(report["dead_write_suspects"]),
            "total_storage": report["storage"]["total_bytes"],
        }

    def _step_blueprint_consistency(self) -> Dict:
        """Step 30: 藍圖一致性驗證 — 確保工程藍圖與程式碼同步.

        檢查項：
        - 30.1 四張藍圖存在性（blast-radius / joint-map / system-topology / persistence-contract）
        - 30.2 藍圖新鮮度（docs/*.md vs src/ 最後修改時間差異）
        - 30.3 禁區模組路徑存在性（blast-radius 標為禁區的模組是否實際存在）
        """
        issues: List[str] = []
        docs_dir = self._source_root / "docs"

        # ── 30.1 藍圖存在性 ──
        blueprint_names = [
            "blast-radius.md",
            "joint-map.md",
            "system-topology.md",
            "persistence-contract.md",
        ]
        for name in blueprint_names:
            bp_path = docs_dir / name
            if not bp_path.exists():
                issues.append(f"藍圖缺失: {name}")
            elif bp_path.stat().st_size == 0:
                issues.append(f"藍圖為空: {name}")

        # ── 30.2 藍圖新鮮度 ──
        src_dir = self._source_root / "src" / "museon"
        if src_dir.exists() and docs_dir.exists():
            try:
                # 找 src/ 下最新修改的 .py
                latest_src_mtime = 0.0
                for py_file in src_dir.rglob("*.py"):
                    try:
                        mt = py_file.stat().st_mtime
                        if mt > latest_src_mtime:
                            latest_src_mtime = mt
                    except OSError:
                        pass

                # 找 docs/ 下最舊的藍圖
                oldest_doc_mtime = float("inf")
                for name in blueprint_names:
                    bp_path = docs_dir / name
                    if bp_path.exists():
                        try:
                            mt = bp_path.stat().st_mtime
                            if mt < oldest_doc_mtime:
                                oldest_doc_mtime = mt
                        except OSError:
                            pass

                # 如果程式碼比藍圖新超過 72 小時，警告
                if latest_src_mtime > 0 and oldest_doc_mtime < float("inf"):
                    drift_hours = (latest_src_mtime - oldest_doc_mtime) / 3600
                    if drift_hours > 72:
                        issues.append(
                            f"藍圖過期: src/ 比 docs/ 新 {drift_hours:.0f} 小時"
                        )
            except Exception as e:
                logger.debug(f"[NIGHTLY] Blueprint freshness check failed: {e}")

        # ── 30.3 禁區模組路徑存在性 ──
        try:
            from museon.core.blueprint_reader import BlastRadiusReader

            reader = BlastRadiusReader(docs_dir)
            for mod_path in reader.get_forbidden_modules():
                full_path = src_dir / mod_path
                if not full_path.exists():
                    issues.append(f"禁區模組不存在: {mod_path}")
        except Exception as e:
            logger.debug(f"[NIGHTLY] Blueprint forbidden check skipped: {e}")

        status = "ok" if not issues else "warning"
        logger.info(
            f"[NIGHTLY] BlueprintConsistency: {status} | "
            f"issues={len(issues)}"
        )
        if issues:
            for issue in issues:
                logger.warning(f"[NIGHTLY] BlueprintConsistency: {issue}")

        return {
            "status": status,
            "issues": issues,
            "blueprints_checked": len(blueprint_names),
        }

    def _step_context_cache_rebuild(self) -> Dict:
        """Step 31: v2 context_cache 重建 — 為 L1/L2 生成快取檔。

        重建 persona_digest.md / active_rules.json / user_summary.json / self_summary.json。
        """
        try:
            from museon.cache.context_cache_builder import build_all
            result = build_all()
            logger.info(f"[NIGHTLY] ContextCache rebuilt: {result}")
            return {"status": "ok", "result": result}
        except Exception as e:
            logger.warning(f"[NIGHTLY] ContextCache rebuild failed: {e}")
            return {"status": "error", "error": str(e)}

    def _step_crystal_decay(self) -> Dict:
        """Step 32: Crystal ri_score 每日衰減 — 每次 Nightly 衰減 0.5%，低於 0.1 歸檔。

        直接用 sqlite3 做 UPDATE，不做全量覆寫（效能考量）。
        """
        import sqlite3

        try:
            from museon.agent.crystal_store import CrystalStore

            store = CrystalStore(data_dir=str(self._workspace))
            db_path = store._db_path

            decayed = 0
            archived = 0
            total_active = 0

            conn = sqlite3.connect(str(db_path), timeout=10)
            conn.execute("PRAGMA busy_timeout=5000")
            try:
                # 取得所有活躍結晶的 cuid + ri_score
                rows = conn.execute(
                    "SELECT cuid, ri_score FROM crystals WHERE archived = 0"
                ).fetchall()
                total_active = len(rows)

                for cuid, ri_score in rows:
                    ri = float(ri_score) if ri_score is not None else 0.0
                    new_ri = ri * 0.995  # 每日衰減 0.5%

                    if new_ri < 0.1:
                        conn.execute(
                            "UPDATE crystals SET ri_score = ?, archived = 1, status = 'decayed'"
                            " WHERE cuid = ?",
                            (new_ri, cuid),
                        )
                        archived += 1
                    else:
                        conn.execute(
                            "UPDATE crystals SET ri_score = ? WHERE cuid = ?",
                            (new_ri, cuid),
                        )
                        decayed += 1

                conn.commit()
            finally:
                conn.close()

            logger.info(
                f"[NIGHTLY] CrystalDecay: total_active={total_active}, "
                f"decayed={decayed}, archived={archived}"
            )
            return {
                "status": "ok",
                "decayed": decayed,
                "archived": archived,
                "total_active": total_active,
            }
        except Exception as e:
            logger.warning(f"[NIGHTLY] CrystalDecay failed: {e}")
            return {"status": "error", "error": str(e)}

    def _step_absurdity_radar_recalc(self) -> Dict:
        """Step 32.5: 荒謬雷達每日重算.

        根據近 30 天的 Skill 使用頻率和結晶數量，重新校準雷達分數。
        漸進更新，不突變。
        """
        from museon.agent.absurdity_radar import (
            load_radar, save_radar, ABSURDITY_DIMENSIONS,
        )

        # 掃描所有使用者的 radar 檔案
        radar_dir = self._workspace / "_system" / "absurdity_radar"
        if not radar_dir.exists():
            return {"recalculated": 0}

        recalculated = 0
        for f in radar_dir.glob("*.json"):
            user_id = f.stem
            try:
                radar = load_radar(user_id, data_dir=str(self._workspace))

                # 衰減：所有維度緩慢向 0.5 回歸（防止永遠偏高）
                # 衰減幅度 = 0.02 × (當前值 - 0.5)
                for dim in ABSURDITY_DIMENSIONS:
                    current = radar.get(dim, 0.5)
                    radar[dim] = current - 0.02 * (current - 0.5)

                # 信心衰減：每天 -0.01（鼓勵持續互動）
                radar["confidence"] = max(0.0, radar.get("confidence", 0.0) - 0.01)

                save_radar(radar, user_id, data_dir=str(self._workspace))
                recalculated += 1
            except Exception as e:
                logger.warning(f"[NIGHTLY] Absurdity radar recalc failed for {user_id}: {e}")

        return {"recalculated": recalculated}
