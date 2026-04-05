"""NightlyPipeline — 18 步凌晨整合管線.

依據 NIGHTLY_SYSTEM_BDD_SPEC 實作。
每步獨立錯誤隔離（_safe_step），單步失敗不中斷整條管線。
支援 Federation 模式：full / origin / node。
零 LLM 依賴（Step 16 除外）。
"""

import json
import logging
import math
import os
import random
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from museon.core.event_bus import (
    DATA_DEAD_WRITE_DETECTED,
    DATA_HEALTH_CHECKED,
    DATA_STORAGE_WARNING,
    DATA_STORE_DEGRADED,
    EVOLUTION_VELOCITY_ALERT,
    KNOWLEDGE_GRAPH_UPDATED,
    NIGHTLY_COMPLETED,
    NIGHTLY_DAG_EXECUTED,
    NIGHTLY_HEALTH_GATE,
    NIGHTLY_STARTED,
)
from museon.nightly.nightly_steps_memory import NightlyStepsMemoryMixin
from museon.nightly.nightly_steps_morphenix import NightlyStepsMorphenixMixin
from museon.nightly.nightly_steps_skill import NightlyStepsSkillMixin
from museon.nightly.nightly_steps_identity import NightlyStepsIdentityMixin
from museon.nightly.nightly_steps_ecosystem import NightlyStepsEcosystemMixin
from museon.nightly.nightly_steps_maintenance import NightlyStepsMaintenanceMixin
from museon.nightly.nightly_steps_persona import NightlyStepsPersonaMixin

logger = logging.getLogger(__name__)


def _run_async_safe(coro, timeout: int = 120):
    """統一的 sync-in-async 橋接（合約 3 修復）.

    NightlyPipeline 運行在獨立背景線程，需要呼叫 async 函數。
    始終建立獨立 event loop，避免與 Gateway 主 loop 衝突。

    修復前問題：
    - asyncio.get_event_loop() 在 Python 3.10+ deprecated
    - 若線程看到 Gateway 主 loop → run_until_complete() 拋 RuntimeError
    - Python 3.10+ 的 events._get_running_loop() 是 thread-local，
      若當前線程有 running loop，new_event_loop 也無法 run_until_complete

    修復策略：偵測當前線程是否有 running loop，若有則在獨立線程執行。
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _execute():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            loop.close()

    # 偵測當前線程是否有 running loop
    try:
        asyncio.get_running_loop()
        # 有 running loop → 在獨立線程執行，避免 RuntimeError
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_execute)
            return future.result(timeout=timeout + 5)
    except RuntimeError:
        # 沒有 running loop → 直接執行
        return _execute()


# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

NIGHTLY_CRON_HOUR = 3
NIGHTLY_CRON_MINUTE = 0
MORNING_REPORT_HOUR = 7
MORNING_REPORT_MINUTE = 30

DAILY_DECAY_FACTOR = 0.993
ARCHIVE_THRESHOLD = 0.3
REPORT_TRUNCATE_CHARS = 200

# WEE constants
WEE_MIN_CRYSTALS_FOR_FUSE = 3

# Skill Forge constants
SKILL_FORGE_MIN_CLUSTER = 3
SKILL_FORGE_SIMILARITY_THRESHOLD = 0.5

# Knowledge Graph constants
GRAPH_REPLAY_BOOST = 0.20
GRAPH_DECAY_FACTOR = 0.993
GRAPH_WEAK_EDGE_THRESHOLD = 0.1

# Workflow Mutation constants
PLATEAU_MIN_RUNS = 5
PLATEAU_MAX_VARIANCE = 0.5
PLATEAU_MAX_AVG = 7.0
MUTATION_STRATEGIES = ["reorder", "simplify", "amplify", "parallel"]

# Skill Lifecycle constants
SKILL_PROMOTE_MIN_SUCCESS = 3
SKILL_DEPRECATE_FAIL_RATE = 0.5
SKILL_ARCHIVE_INACTIVE_DAYS = 30

# Federation step sets
_FULL_STEPS = [
    # Phase 0: Nightly減法手術 v1 (2026-04-06)
    # 移除12個 ghost steps（三份報告全部 always-skipped，資料來源不存在）：
    # 5.5(no memory dir), 6(no L2_ep dir), 8(no workflows dir), 9(no graph dir),
    # 10.5(no soul_rings.json), 10.6(SOUL.md not found), 11(no memory for dreaming),
    # 13.7(no pending outward queries), 14(no skills dir), 15(no departments dir),
    # 16(no L3_procedural), 19(no effect_tracker.json)
    # re-enable these steps by adding back to this list when data source exists.
    "0", "0.1",  # Budget settlement + Footprint cleanup (最先執行)
    "1", "2", "3", "4", "5", "5.6", "5.6.5", "5.7", "5.8", "5.9", "5.9.5", "5.10",
    # "5.5" GHOST: step_05_5_cross_crystallize — skipped: no memory directory
    "6.5", "7", "7.5", "8.6", "8.7", "10", "12", "13", "13.5",
    # "6"   GHOST: step_06_skill_forge — skipped: no L2_ep directory
    # "8"   GHOST: step_08_workflow_mutation — skipped: no workflows directory
    # "9"   GHOST: step_09_graph_consolidation — skipped: no graph directory
    # "10.5" GHOST: step_10_5_ring_review — skipped: no soul_rings.json
    # "10.6" GHOST: step_10_6_soul_identity_check — skipped: SOUL.md not found
    # "11"  GHOST: step_11_dream_engine — skipped: no memory for dreaming
    "13.6", "13.8",  # 外向型進化：觸發掃描 → 消化生命週期
    # "13.7" GHOST: step_13_7_outward_research — skipped: no pending outward queries
    "17", "17.5",  # 17.5: 生態系雷達（週一限定）— 搜尋外部工具/Skill 趨勢
    # "14"  GHOST: step_14_skill_lifecycle — skipped: no skills directory
    # "15"  GHOST: step_15_dept_health — skipped: no departments directory
    # "16"  GHOST: step_16_claude_skill_forge — skipped: no L3_procedural skills to refine
    "18", "18.5", "18.6", "18.7",  # 18.5: 客戶互動萃取 → 18.6: Ares 橋接 → 18.7: 六層健康檢查
    # "19"  GHOST: step_19_morphenix_quality_gate — skipped: no effect_tracker.json
    "19.5", "19.6", "19.7",  # Skill 自動演化：健康追蹤 → 鍛造/優化 → QA 品質閘門
    "20", "21", "22", "23",  # 新增：synapse_decay/muscle_atrophy/immune_prune/trigger_eval
    "24", "25",  # 新增：演化速度計算 / 週月循環觸發檢查
    "27", "28", "29",  # 持久層衛生：JSONL 輪替 / WAL checkpoint / DataWatchdog  # v1.75: "26" session_cleanup 已刪除，由每小時 cron 涵蓋
    "30",  # 藍圖一致性驗證
    "31",  # v2 context_cache 重建
    "32", "32.5", "32.6", "33",  # Crystal ri_score 衰減 / 荒謬雷達重算 / 多星座衰減 / Crystal→Heuristic 升級
    "34", "34.5", "34.7", "34.8", "34.9",  # Phase 5/8: 人格自省 → Trait 代謝 → 方向性漂移檢查 → 呼吸分析 → 願景迴圈
]
_ORIGIN_STEPS = ["5.8", "7"]  # 5.8: Morphenix proposals, 7: curriculum
_NODE_STEPS = [
    "1", "2", "3", "4", "5", "5.5",
    "9", "10", "11", "12", "13", "13.5", "14", "15",
]

TZ_TAIPEI = timezone(timedelta(hours=8))


class NightlyPipeline(
    NightlyStepsMemoryMixin,
    NightlyStepsMorphenixMixin,
    NightlyStepsSkillMixin,
    NightlyStepsIdentityMixin,
    NightlyStepsEcosystemMixin,
    NightlyStepsMaintenanceMixin,
    NightlyStepsPersonaMixin,
):
    """18 步凌晨整合管線.

    | Step | 功能                        | Token |
    |------|-----------------------------|-------|
    | 1    | 資產衰減 × 0.993             | 0     |
    | 2    | 品質 < 0.3 → 歸檔            | 0     |
    | 3    | 品質閘門重掃（預留）           | 0     |
    | 4    | WEE 壓縮                    | 0     |
    | 5    | WEE 融合                    | 0     |
    | 5.5  | 跨用戶知識融合               | 0     |
    | 5.8  | Morphenix 提案              | 0     |
    | 5.10 | Morphenix 執行              | 0     |
    | 6    | Skill Forge                 | 0     |
    | 7    | 課程處方                     | 0     |
    | 8    | 工作流突變                   | 0     |
    | 9    | 圖譜整合                     | 0     |
    | 10   | 靈魂夜間                     | 0     |
    | 11   | 夢境引擎                     | 0     |
    | 12   | 焦點重算                     | 0     |
    | 13   | 好奇掃描                     | 0     |
    | 14   | Skill 生命週期               | 0     |
    | 15   | 部門健康                     | 0     |
    | 16   | Claude Skill 鍛造            | ~500  |
    """

    def __init__(
        self,
        workspace: Path,
        memory_manager: Optional[Any] = None,
        heartbeat_focus: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        brain: Optional[Any] = None,
        dendritic_scorer: Optional[Any] = None,
    ) -> None:
        self._workspace = workspace
        self._source_root = workspace.parent if workspace else Path.cwd()
        self._memory_manager = memory_manager
        self._heartbeat_focus = heartbeat_focus
        self._event_bus = event_bus
        self._brain = brain
        self._dendritic_scorer = dendritic_scorer

        # Step map: step_id → (name, method)
        self._step_map: Dict[str, tuple] = {
            "1": ("step_01_asset_decay", self._step_asset_decay),
            "2": ("step_02_archive_assets", self._step_archive_assets),
            "3": ("step_03_memory_maintenance", self._step_memory_maintenance),
            "4": ("step_04_wee_compress", self._step_wee_compress),
            "5": ("step_05_wee_fuse", self._step_wee_fuse),
            "5.5": ("step_05_5_cross_crystallize", self._step_cross_crystallize),
            "5.6": ("step_05_6_knowledge_lattice", self._step_knowledge_lattice),
            "5.6.5": ("step_05_6_5_lesson_distill", self._step_lesson_distill),
            "5.7": ("step_05_7_crystal_actuator", self._step_crystal_actuator),
            "5.8": ("step_05_8_morphenix_proposals", self._step_morphenix_proposals),
            "5.9": ("step_05_9_morphenix_gate", self._step_morphenix_gate),
            "5.9.5": ("step_05_9_5_morphenix_validate", self._step_morphenix_validate),
            "5.10": ("step_05_10_morphenix_execute", self._step_morphenix_execute),
            "6": ("step_06_skill_forge", self._step_skill_forge),
            "6.5": ("step_06_5_skill_scout", self._step_skill_scout),
            "7": ("step_07_curriculum", self._step_curriculum),
            "7.5": ("step_07_5_auto_course", self._step_auto_course),
            "8": ("step_08_workflow_mutation", self._step_workflow_mutation),
            "8.6": ("step_08_6_skill_vector_reindex", self._step_skill_vector_reindex),
            "8.7": ("step_08_7_sparse_idf_rebuild", self._step_sparse_idf_rebuild),
            "9": ("step_09_graph_consolidation", self._step_graph_consolidation),
            "10": ("step_10_diary_generation", self._step_diary_generation),
            "10.5": ("step_10_5_ring_review", self._step_ring_review),
            "11": ("step_11_dream_engine", self._step_dream_engine),
            "12": ("step_12_heartbeat_focus", self._step_heartbeat_focus),
            "13": ("step_13_curiosity_scan", self._step_curiosity_scan),
            "13.5": ("step_13_5_curiosity_research", self._step_curiosity_research),
            "13.6": ("step_13_6_outward_trigger_scan", self._step_outward_trigger_scan),
            "13.7": ("step_13_7_outward_research", self._step_outward_research),
            "13.8": ("step_13_8_digest_lifecycle", self._step_digest_lifecycle),
            "14": ("step_14_skill_lifecycle", self._step_skill_lifecycle),
            "15": ("step_15_dept_health", self._step_dept_health),
            "16": ("step_16_claude_skill_forge", self._step_claude_skill_forge),
            "17": ("step_17_tool_discovery", self._step_tool_discovery),
            "17.5": ("step_17_5_ecosystem_radar", self._step_ecosystem_radar),
            "18": ("step_18_daily_summary", self._step_daily_summary),
            "18.5": ("step_18_5_client_profile_update", self._step_client_profile_update),
            "18.6": ("step_18_6_ares_bridge_sync", self._step_ares_bridge_sync),
            "18.7": ("step_18_7_system_health_audit", self._step_system_health_audit),
            "19": ("step_19_morphenix_quality_gate", self._step_morphenix_quality_gate),
            # ── Skill 自動演化管線（Organ Growth Pipeline）──
            "19.5": ("step_19_5_skill_health_scan", self._step_skill_health_scan),
            "19.6": ("step_19_6_skill_draft_forge", self._step_skill_draft_forge),
            "19.7": ("step_19_7_skill_qa_gate", self._step_skill_qa_gate),
            # ── Autonomy Architecture 新增步驟 ──
            "0": ("step_00_budget_settlement", self._step_budget_settlement),
            "0.1": ("step_00_1_footprint_cleanup", self._step_footprint_cleanup),
            "20": ("step_20_synapse_decay", self._step_synapse_decay),
            "21": ("step_21_muscle_atrophy", self._step_muscle_atrophy),
            "22": ("step_22_immune_prune", self._step_immune_prune),
            "23": ("step_23_trigger_evaluation", self._step_trigger_evaluation),
            "10.6": ("step_10_6_soul_identity_check", self._step_soul_identity_check),
            # ── Evolution Architecture 新增步驟 ──
            "24": ("step_24_evolution_velocity", self._step_evolution_velocity),
            "25": ("step_25_periodic_cycle_check", self._step_periodic_cycle_check),
            # ── 持久層衛生 ──  # v1.75: "26" session_cleanup 已刪除，由每小時 cron 涵蓋
            "27": ("step_27_log_rotation", self._step_log_rotation),
            "28": ("step_28_wal_checkpoint", self._step_wal_checkpoint),
            "29": ("step_29_data_watchdog", self._step_data_watchdog),
            # ── 藍圖驗證 ──
            "30": ("step_30_blueprint_consistency", self._step_blueprint_consistency),
            # ── v2 context_cache 重建 ──
            "31": ("step_31_context_cache_rebuild", self._step_context_cache_rebuild),
            # ── Crystal 生命週期管理 ──
            "32": ("step_32_crystal_decay", self._step_crystal_decay),
            "32.5": ("step_32.5_absurdity_radar", self._step_absurdity_radar_recalc),
            "32.6": ("step_32.6_constellation_decay", self._step_constellation_decay),
            "33": ("step_33_crystal_promotion", self._step_crystal_promotion),
            # ── Phase 5/8: Persona Evolution ──
            "34": ("persona_reflection", self._step_persona_reflection),
            "34.5": ("trait_metabolize", self._step_trait_metabolize),
            "34.7": ("drift_direction_check", self._step_drift_direction_check),
            "34.8": ("breath_analysis", self._step_breath_analysis),
            "34.9": ("vision_loop", self._step_vision_loop),
        }

    def run(self, mode: str = "full") -> Dict:
        """執行凌晨整合管線.

        Args:
            mode: "full" | "origin" | "node"

        Returns:
            管線執行報告（steps 為 dict 格式）
        """
        started_at = datetime.now(TZ_TAIPEI)

        # 發布 NIGHTLY_STARTED
        self._publish(NIGHTLY_STARTED, {
            "mode": mode,
            "started_at": started_at.isoformat(),
        })

        start = time.time()

        if mode == "origin":
            step_ids = _ORIGIN_STEPS
        elif mode == "node":
            step_ids = list(_NODE_STEPS)
        else:
            step_ids = _FULL_STEPS

        # WP-03: 健康閘門 — 根據 Health Score 決定執行範圍
        gate_mode = "full"
        if self._dendritic_scorer and mode == "full":
            try:
                score = self._dendritic_scorer.calculate_score()
                if score == 0.0:
                    # Health Gate fallback：DendriticScorer 返回 0.0 時使用備用計分
                    # 檢查上次 Nightly 成功完成時間，24h 內 → full mode (score=80)，否則 degraded
                    fallback_score = 55.0  # 預設 degraded
                    try:
                        _last_ok = self._workspace / "_system" / "nightly_last_ok.txt"
                        if _last_ok.exists():
                            _last_ts = float(_last_ok.read_text(encoding="utf-8").strip())
                            import time as _time
                            if (_time.time() - _last_ts) < 86400:  # 24 小時內
                                fallback_score = 80.0
                    except Exception:
                        pass

                    if fallback_score >= 71:
                        # 24h 內成功完成 → full mode
                        gate_mode = "full"
                        logger.info(
                            "[NIGHTLY] Health gate: score=0.0 but last Nightly <24h ago, "
                            "fallback_score=%.1f → full mode", fallback_score
                        )
                    else:
                        step_ids = self._get_degraded_steps()
                        gate_mode = "degraded"
                        logger.warning(
                            "[NIGHTLY] Health gate: score=0.0 "
                            "(cold start or insufficient data), "
                            "fallback_score=%.1f → degraded mode", fallback_score
                        )
                elif score <= 40:
                    # 危險：僅執行最小集合
                    step_ids = self._get_minimal_steps()
                    gate_mode = "minimal"
                elif score <= 70:
                    # 降級：跳過重型步驟
                    step_ids = self._get_degraded_steps()
                    gate_mode = "degraded"
                self._publish(NIGHTLY_HEALTH_GATE, {
                    "health_score": round(score, 1),
                    "gate_mode": gate_mode,
                    "step_count": len(step_ids),
                })
                if gate_mode != "full":
                    logger.info(
                        f"[NIGHTLY] Health gate: score={score:.1f} → "
                        f"mode={gate_mode} ({len(step_ids)} steps)"
                    )
            except Exception as e:
                logger.debug(f"[NIGHTLY] Health gate check failed: {e}")

        # ── DAG 模式（full 模式使用 DAG 排程，其他模式保持線性）──
        use_dag = mode == "full"
        steps_dict: Dict[str, Dict] = {}

        if use_dag:
            try:
                from museon.nightly.pipeline_dag import build_museon_dag
                dag = build_museon_dag(self._step_map, step_ids=step_ids)
                dag_report = dag.execute()
                # 轉換 DAGExecutionReport → steps_dict 格式
                for step_id, step_result in dag_report.steps.items():
                    steps_dict[step_result.name] = step_result.to_dict()
                self._publish(NIGHTLY_DAG_EXECUTED, {
                    "execution_order": dag_report.execution_order,
                    "skipped_due_to_dependency": dag_report.skipped_due_to_dependency,
                })
                logger.info(
                    f"[NIGHTLY] DAG execution: "
                    f"{dag_report.ok_count} ok, {dag_report.error_count} error, "
                    f"{dag_report.skipped_count} skipped"
                )
            except Exception as e:
                logger.warning(f"[NIGHTLY] DAG execution failed, fallback to linear: {e}")
                use_dag = False

        if not use_dag:
            # 線性執行（origin / node / DAG 回退）
            for step_id in step_ids:
                if step_id not in self._step_map:
                    continue
                name, func = self._step_map[step_id]
                result = self._safe_step(name, func)
                steps_dict[name] = result

        # Node 模式額外執行 federation upload
        if mode == "node":
            fed_result = self._safe_step(
                "step_federation_upload", self._step_federation_upload
            )
            steps_dict["step_federation_upload"] = fed_result

        elapsed = round(time.time() - start, 2)
        completed_at = datetime.now(TZ_TAIPEI)

        ok_count = sum(1 for s in steps_dict.values() if s["status"] == "ok")
        error_count = sum(1 for s in steps_dict.values() if s["status"] == "error")
        skipped_count = sum(
            1 for s in steps_dict.values()
            if s["status"] in ("skipped", "skipped_dependency_failed")
        )

        errors = [
            {"step": k, "error": v.get("error", "")}
            for k, v in steps_dict.items()
            if v["status"] == "error"
        ]

        report = {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "elapsed_seconds": elapsed,
            "mode": mode,
            "steps": steps_dict,
            "summary": {
                "total": len(steps_dict),
                "ok": ok_count,
                "error": error_count,
                "skipped": skipped_count,
            },
            "errors": errors,
        }

        # 持久化報告
        self._persist_report(report)

        # 發布 NIGHTLY_COMPLETED
        self._publish(NIGHTLY_COMPLETED, {
            "mode": mode,
            "elapsed_seconds": elapsed,
            "summary": report["summary"],
            "errors": errors,
        })

        # 記錄成功完成時間（供 Health Gate fallback 使用）
        if not errors:
            try:
                import time as _time
                _last_ok = self._workspace / "_system" / "nightly_last_ok.txt"
                _last_ok.parent.mkdir(parents=True, exist_ok=True)
                _last_ok.write_text(str(_time.time()), encoding="utf-8")
            except Exception:
                pass

        # 寫入五虎將共享看板
        try:
            from museon.doctor.shared_board import update_shared_board
            ok_count = report["summary"].get("ok", 0)
            total_count = report["summary"].get("total", 0)
            err_count = len(errors)
            _status = "critical" if err_count > 3 else "warning" if err_count > 0 else "ok"
            update_shared_board(
                self._workspace,
                source="nightly",
                summary=f"Nightly {mode}: {ok_count}/{total_count} ok, {err_count} errors, {elapsed:.0f}s",
                findings_count=err_count,
                actions=[f"mode:{mode}", f"gate:{gate_mode}"],
                status=_status,
            )
        except Exception:
            pass

        return report

    # ═══════════════════════════════════════════
    # WP-03: 健康閘門步驟集
    # ═══════════════════════════════════════════

    def _get_degraded_steps(self) -> List[str]:
        """降級模式：跳過 Morphenix、Claude Skill Forge、外向搜尋等重型步驟."""
        skip = {"5.8", "5.9", "5.10", "13.5", "13.6", "13.7", "13.8", "16", "17"}
        return [s for s in _FULL_STEPS if s not in skip]

    def _get_minimal_steps(self) -> List[str]:
        """最小模式：僅執行必要的維護步驟."""
        keep = {"0", "0.1", "1", "2", "3", "15", "18"}
        return [s for s in _FULL_STEPS if s in keep]

    # ═══════════════════════════════════════════
    # EventBus 發布
    # ═══════════════════════════════════════════

    def _publish(self, event_type: str, data: Dict) -> None:
        """發布事件到 EventBus."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception as e:
                logger.warning(f"EventBus publish {event_type} failed: {e}")

    # ═══════════════════════════════════════════
    # Safe Step 錯誤隔離
    # ═══════════════════════════════════════════

    def _safe_step(self, name: str, func: Callable) -> Dict:
        """單步執行 + 錯誤隔離."""
        try:
            result = func()
            # 截斷結果字串
            result_str = str(result)
            if len(result_str) > REPORT_TRUNCATE_CHARS:
                result_str = result_str[:REPORT_TRUNCATE_CHARS] + "..."
            return {"status": "ok", "result": result_str}
        except NotImplementedError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"status": "skipped", "result": "subsystem not available"}
        except Exception as e:
            logger.error(f"[NIGHTLY] Step {name} failed: {e}")
            return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════
# HTML 報告生成
# ═══════════════════════════════════════════


def build_nightly_html(report: Dict) -> str:
    """將管線報告轉為 Telegram 可讀的 HTML 摘要."""
    summary = report.get("summary", {})
    ok = summary.get("ok", 0)
    total = summary.get("total", 0)
    error = summary.get("error", 0)
    skipped = summary.get("skipped", 0)
    elapsed = report.get("elapsed_seconds", 0)
    mode = report.get("mode", "full")

    status_emoji = "✅" if error == 0 else "⚠️"

    lines = [
        f"{status_emoji} <b>凌晨整合報告</b>",
        f"模式: {mode} | 耗時: {elapsed}s",
        f"✅ {ok} | ❌ {error} | ⊘ {skipped} / {total}",
        "",
    ]

    # 列出失敗步驟
    errors = report.get("errors", [])
    if errors:
        lines.append("<b>失敗步驟:</b>")
        for e in errors[:5]:
            step = e.get("step", "?")
            err = e.get("error", "unknown")[:80]
            lines.append(f"  ❌ {step}: {err}")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# 排程註冊
# ═══════════════════════════════════════════


def register_nightly_tasks(scheduler, workspace: Path, **kwargs) -> None:
    """註冊凌晨整合 + 早報推播到 TaskScheduler.

    Args:
        scheduler: TaskScheduler 實例
        workspace: 工作區路徑
        **kwargs: 傳給 NightlyPipeline 的額外參數
    """
    def _run_nightly():
        pipeline = NightlyPipeline(workspace=workspace, **kwargs)
        return pipeline.run()

    scheduler.register(
        name="nightly_consolidation",
        func=_run_nightly,
        cron_hour=NIGHTLY_CRON_HOUR,
        cron_minute=NIGHTLY_CRON_MINUTE,
        description="18-step nightly consolidation pipeline",
    )

    def _morning_report():
        state_dir = workspace / "_system" / "state"

        # 優先讀取三層晨報
        morning_path = state_dir / "morning_report.json"
        if morning_path.exists():
            try:
                with open(morning_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.debug(f"[NIGHTLY] JSON parse failed (degraded): {e}")

        # 降級：讀取原始 nightly report（可能被 MuseDoc git stash 污染）
        report_path = state_dir / "nightly_report.json"
        if report_path.exists():
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.debug(f"[NIGHTLY] degraded: {e}")

        # 最終降級：從 nightly_history 讀最新的報告（不受 git stash 影響）
        history_dir = state_dir / "nightly_history"
        if history_dir.exists():
            history_files = sorted(history_dir.glob("nightly_report_*.json"))
            if history_files:
                latest = history_files[-1]
                try:
                    with open(latest, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    logger.info(f"[NIGHTLY] morning_report: using history fallback {latest.name}")
                    return data
                except Exception as e:
                    logger.debug(f"[NIGHTLY] history fallback failed: {e}")

        return None

    scheduler.register(
        name="nightly_morning_report",
        func=_morning_report,
        cron_hour=MORNING_REPORT_HOUR,
        cron_minute=MORNING_REPORT_MINUTE,
        description="Morning report: read nightly results for push",
    )
