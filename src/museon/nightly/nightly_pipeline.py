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
    "17",
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


class NightlyPipeline:
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
    # Step 1-2: 共享資產
    # ═══════════════════════════════════════════

    def _step_asset_decay(self) -> Dict:
        """Step 1: 所有共享資產 × 0.993."""
        asset_dir = self._workspace / "_system" / "assets"
        if not asset_dir.exists():
            return {"decayed": 0}

        decayed = 0
        for f in asset_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if "quality" in data:
                    data["quality"] = round(
                        data["quality"] * DAILY_DECAY_FACTOR, 4
                    )
                    decayed += 1
                    with open(f, "w", encoding="utf-8") as fh:
                        json.dump(data, fh, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.debug(f"[NIGHTLY] JSON parse failed (degraded): {e}")
        # Phase B: Multi-Agent shared_assets 衰退
        shared_decayed = 0
        try:
            from museon.multiagent.shared_assets import SharedAssetLibrary
            lib = SharedAssetLibrary(workspace=self._workspace)
            shared_decayed = lib.decay_all()
        except Exception as e:
            logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {"decayed": decayed, "shared_decayed": shared_decayed}

    def _step_archive_assets(self) -> Dict:
        """Step 2: 品質 < 0.3 → 歸檔."""
        asset_dir = self._workspace / "_system" / "assets"
        archive_dir = self._workspace / "_system" / "assets_archive"
        if not asset_dir.exists():
            archived = 0
        else:
            archived = 0
            for f in asset_dir.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    if data.get("quality", 1.0) < ARCHIVE_THRESHOLD:
                        archive_dir.mkdir(parents=True, exist_ok=True)
                        f.rename(archive_dir / f.name)
                        archived += 1
                except Exception as e:
                    logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        # Phase B: Multi-Agent shared_assets 歸檔
        shared_archived = 0
        try:
            from museon.multiagent.shared_assets import SharedAssetLibrary
            lib = SharedAssetLibrary(workspace=self._workspace)
            shared_archived = lib.archive_low_quality()
        except Exception as e:
            logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {"archived": archived, "shared_archived": shared_archived}

    # ═══════════════════════════════════════════
    # Step 3: 記憶維護
    # ═══════════════════════════════════════════

    def _step_memory_maintenance(self) -> Dict:
        """Step 3: 品質閘門重掃."""
        if self._memory_manager and hasattr(self._memory_manager, "maintenance"):
            result = self._memory_manager.maintenance()
            return {"maintained": True, "result": str(result)}
        return {"status": "pass"}

    # ═══════════════════════════════════════════
    # Step 4-5: WEE 壓縮 / 融合
    # ═══════════════════════════════════════════

    def _step_wee_compress(self) -> Dict:
        """Step 4: WEE 壓縮 — 昨日 session → L2_ep crystal.

        委派到 WEEEngine.compress_daily()。
        ImportError → 保留原始 filesystem fallback。
        """
        try:
            from museon.evolution.wee_engine import get_wee_engine
            from museon.core.event_bus import get_event_bus

            event_bus = get_event_bus()
            memory_manager = getattr(self, "_memory_manager", None)
            wee = get_wee_engine(
                user_id="boss",
                workspace=self._workspace,
                event_bus=event_bus,
                memory_manager=memory_manager,
            )
            return wee.compress_daily()
        except ImportError as e:
            logger.debug(f"[NIGHTLY] WEE engine failed (degraded): {e}")

        # ── Filesystem fallback（原始邏輯）──
        wee_dir = self._workspace / "_system" / "wee" / "sessions"
        if not wee_dir.exists():
            return {"skipped": "no wee sessions directory"}

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        session_files = list(wee_dir.glob(f"{yesterday}*.json"))

        if not session_files:
            return {"skipped": "no sessions"}

        compressed = 0
        crystal_dir = self._workspace / "_system" / "wee" / "crystals" / "daily"
        crystal_dir.mkdir(parents=True, exist_ok=True)

        for sf in session_files:
            try:
                with open(sf, "r", encoding="utf-8") as fh:
                    session = json.load(fh)
                crystal = {
                    "type": "L2_ep",
                    "source_date": yesterday,
                    "source_file": sf.name,
                    "summary": str(session)[:500],
                    "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                }
                out = crystal_dir / f"crystal_{yesterday}_{compressed}.json"
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(crystal, fh, ensure_ascii=False, indent=2)
                compressed += 1
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {"compressed": compressed, "source_date": yesterday}

    def _step_wee_fuse(self) -> Dict:
        """Step 5: WEE 融合 — 同週 3+ daily crystal → weekly crystal.

        委派到 WEEEngine.fuse_weekly()。
        ImportError → 保留原始 filesystem fallback。
        """
        try:
            from museon.evolution.wee_engine import get_wee_engine
            from museon.core.event_bus import get_event_bus

            event_bus = get_event_bus()
            memory_manager = getattr(self, "_memory_manager", None)
            wee = get_wee_engine(
                user_id="boss",
                workspace=self._workspace,
                event_bus=event_bus,
                memory_manager=memory_manager,
            )
            return wee.fuse_weekly()
        except ImportError as e:
            logger.debug(f"[NIGHTLY] WEE engine failed (degraded): {e}")

        # ── Filesystem fallback（原始邏輯）──
        crystal_dir = self._workspace / "_system" / "wee" / "crystals" / "daily"
        if not crystal_dir.exists():
            return {"skipped": "no daily crystals directory"}

        iso_cal = date.today().isocalendar()
        iso_week = f"{iso_cal[0]}-W{iso_cal[1]:02d}"

        week_crystals = []
        for f in crystal_dir.glob("crystal_*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                src_date = data.get("source_date", "")
                if src_date:
                    d = date.fromisoformat(src_date)
                    d_cal = d.isocalendar()
                    d_week = f"{d_cal[0]}-W{d_cal[1]:02d}"
                    if d_week == iso_week:
                        week_crystals.append(data)
            except Exception as e:
                logger.debug(f"[NIGHTLY] WEE engine failed (degraded): {e}")

        if len(week_crystals) < WEE_MIN_CRYSTALS_FOR_FUSE:
            return {"skipped": "not enough crystals", "count": len(week_crystals)}

        weekly_dir = self._workspace / "_system" / "wee" / "crystals" / "weekly"
        weekly_dir.mkdir(parents=True, exist_ok=True)

        fused = {
            "type": "L2_sem",
            "iso_week": iso_week,
            "source_count": len(week_crystals),
            "created_at": datetime.now(TZ_TAIPEI).isoformat(),
        }
        out = weekly_dir / f"weekly_{iso_week}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(fused, fh, ensure_ascii=False, indent=2)

        return {"fused": 1, "iso_week": iso_week, "source_count": len(week_crystals)}

    # ═══════════════════════════════════════════
    # Step 5.5: 交叉層結晶
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/memory/ directory with L2_ep items)
    def _step_cross_crystallize(self) -> Dict:
        """Step 5.5: L2_ep 跨使用者聚類."""
        memory_dir = self._workspace / "_system" / "memory"
        if not memory_dir.exists():
            return {"skipped": "no memory directory"}

        # 聚合 shared / owner / cli_user / boss 四個 scope 的 L2_ep
        l2_items = []
        seen_ids = set()
        for scope in ["shared", "owner", "cli_user", "boss"]:
            scope_dir = memory_dir / scope / "L2_ep"
            if not scope_dir.exists():
                continue
            for f in scope_dir.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        item = json.load(fh)
                    item_id = item.get("id", f.stem)
                    if item_id not in seen_ids:
                        seen_ids.add(item_id)
                        l2_items.append(item)
                except Exception as e:
                    logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        if len(l2_items) < 3:
            return {"skipped": "not enough L2_ep items", "count": len(l2_items)}

        # 嘗試用 ChromosomeIndex 做聚類
        try:
            from museon.memory.chromosome_index import ChromosomeIndex
            ci = ChromosomeIndex()
            for item in l2_items:
                text = item.get("content", item.get("summary", ""))
                tags = item.get("tags", [])
                ci.add(item.get("id", ""), text, tags=tags)
            clusters = ci.cluster(
                threshold=SKILL_FORGE_SIMILARITY_THRESHOLD,
                min_size=SKILL_FORGE_MIN_CLUSTER,
            )
            return {"clusters": len(clusters), "total_items": len(l2_items)}
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "ChromosomeIndex not available"}

    # ═══════════════════════════════════════════
    # Step 5.6: 知識晶格 — 夜間維護 + 再結晶
    # ═══════════════════════════════════════════

    def _step_knowledge_lattice(self) -> Dict:
        """Step 5.6: Knowledge Lattice 夜間維護.

        1. 更新所有結晶的共振指數
        2. 歸檔過期結晶
        3. 執行再結晶掃描（合併相似結晶）
        """
        try:
            from museon.agent.knowledge_lattice import KnowledgeLattice
            lattice = KnowledgeLattice(data_dir=str(self._workspace))
            report = lattice.nightly_maintenance()
            total_crystals = report.get("total_crystals", 0)
            return {
                "total_crystals": total_crystals,
                "archived": report.get("archived", 0),
                "recrystallized": report.get("recrystallized", 0),
                "ri_updated": report.get("ri_updated", 0),
            }
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "KnowledgeLattice not available"}
        except Exception as e:
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 5.6.5: 教訓蒸餾 — metacog + failure → Crystal Actuator guard 規則
    # ═══════════════════════════════════════════

    def _step_lesson_distill(self) -> Dict:
        """Step 5.6.5: 從 metacognition 洞察和失敗記憶萃取行為規則.

        管線 A: morphenix/notes/mc_*_metacog_insight.json 中 REVISE 標記 → guard 規則
        管線 B: memory_v3/*/L1_short/ 中 outcome=failed → guard 規則
        規則寫入 crystal_rules.json 供 Crystal Actuator 注入每次對話 prompt。
        """
        import json
        import glob
        from datetime import datetime, timedelta

        rules_file = self._workspace / "_system" / "crystal_rules.json"
        stats = {"metacog_scanned": 0, "failure_scanned": 0, "new_rules": 0, "skipped_dup": 0}

        # Load existing rules
        try:
            with open(rules_file, "r", encoding="utf-8") as f:
                rules_data = json.load(f)
        except Exception:
            rules_data = {"version": "2.0", "updated_at": "", "rules": []}

        existing_sources = {r.get("source_cuid", "") for r in rules_data.get("rules", [])}
        max_rules = 30  # 總規則上限

        # ── 管線 A: MetaCognition insights → guard rules ──
        notes_dir = self._workspace / "_system" / "morphenix" / "notes"
        cutoff = datetime.now() - timedelta(days=7)  # 只掃最近 7 天

        for mc_file in sorted(notes_dir.glob("mc_*_metacog_insight.json")):
            stats["metacog_scanned"] += 1
            try:
                with open(mc_file, "r", encoding="utf-8") as f:
                    note = json.load(f)

                content = note.get("content", "")
                # 只萃取 REVISE 標記的洞察
                if "REVISE" not in content and "revise" not in content.lower():
                    continue

                source_id = note.get("id", mc_file.stem)
                if source_id in existing_sources:
                    stats["skipped_dup"] += 1
                    continue

                # 檢查時間
                created = note.get("created_at", "")
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace("+08:00", "+08:00"))
                        if dt.replace(tzinfo=None) < cutoff:
                            continue
                    except Exception:
                        pass

                # 萃取規則：取 REVISE 後面的修改建議作為 directive
                directive = content
                if "REVISE" in content:
                    parts = content.split("REVISE", 1)
                    directive = parts[1].strip().lstrip(":").lstrip("\n").strip() if len(parts) > 1 else content
                directive = directive[:500]  # 截斷

                if len(rules_data["rules"]) >= max_rules:
                    break

                rules_data["rules"].append({
                    "rule_id": f"rule-MC-{source_id[-8:]}",
                    "source_cuid": source_id,
                    "rule_type": "methodology",
                    "action": "guard",
                    "summary": directive[:100],
                    "directive": directive,
                    "strength": 1.2,
                    "status": "active",
                    "created_at": created or datetime.now().isoformat(),
                    "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
                    "positive_count": 0,
                    "negative_count": 0,
                    "last_feedback": "",
                    "crystal_ri": 0.8,
                    "crystal_type": "Insight",
                    "crystal_origin": f"metacog_distill:{mc_file.name}",
                })
                existing_sources.add(source_id)
                stats["new_rules"] += 1

            except Exception as e:
                logger.debug(f"[NIGHTLY] metacog parse error {mc_file.name}: {e}")

        # ── 管線 B: Failure memories → guard rules ──
        memory_root = self._workspace / "memory_v3"
        for user_dir in memory_root.iterdir():
            if not user_dir.is_dir():
                continue
            l1_dir = user_dir / "L1_short"
            if not l1_dir.exists():
                continue

            for mem_file in l1_dir.glob("*.json"):
                stats["failure_scanned"] += 1
                try:
                    with open(mem_file, "r", encoding="utf-8") as f:
                        mem = json.load(f)

                    if mem.get("outcome") != "failed":
                        continue
                    if mem.get("source") != "failure_distill":
                        continue

                    source_id = mem.get("id", mem_file.stem)
                    if source_id in existing_sources:
                        stats["skipped_dup"] += 1
                        continue

                    # 檢查時間
                    created = mem.get("created_at", "")
                    if created:
                        try:
                            dt = datetime.fromisoformat(created.replace("+08:00", "+08:00"))
                            if dt.replace(tzinfo=None) < cutoff:
                                continue
                        except Exception:
                            pass

                    content = mem.get("content", "")
                    # 從失敗經驗萃取教訓摘要
                    summary = content[:200]

                    if len(rules_data["rules"]) >= max_rules:
                        break

                    rules_data["rules"].append({
                        "rule_id": f"rule-FAIL-{source_id[:8]}",
                        "source_cuid": source_id,
                        "rule_type": "anti_pattern",
                        "action": "guard",
                        "summary": summary[:100],
                        "directive": f"過去失敗經驗：{summary}",
                        "strength": 1.0,
                        "status": "active",
                        "created_at": created or datetime.now().isoformat(),
                        "expires_at": (datetime.now() + timedelta(days=14)).isoformat(),
                        "positive_count": 0,
                        "negative_count": 0,
                        "last_feedback": "",
                        "crystal_ri": 0.7,
                        "crystal_type": "Lesson",
                        "crystal_origin": f"failure_distill:{mem_file.name}",
                    })
                    existing_sources.add(source_id)
                    stats["new_rules"] += 1

                except Exception as e:
                    logger.debug(f"[NIGHTLY] failure mem parse error {mem_file.name}: {e}")

        # Save updated rules
        if stats["new_rules"] > 0:
            rules_data["updated_at"] = datetime.now().isoformat()
            with open(rules_file, "w", encoding="utf-8") as f:
                json.dump(rules_data, f, ensure_ascii=False, indent=2)
            logger.info(
                f"[NIGHTLY] Lesson distill: +{stats['new_rules']} rules "
                f"(metacog={stats['metacog_scanned']}, failures={stats['failure_scanned']})"
            )

        return stats

    # Step 5.7: Crystal Actuator — 結晶行為規則引擎
    # ═══════════════════════════════════════════

    def _step_crystal_actuator(self) -> Dict:
        """Step 5.7: 結晶 → 行為規則轉化 + 新陳代謝.

        1. actualize: 掃描高置信結晶 → 轉化為行為規則
        2. metabolize: 根據回饋強化/淘汰規則（P3 核心）
        """
        try:
            from museon.agent.crystal_actuator import CrystalActuator
            from museon.agent.knowledge_lattice import KnowledgeLattice

            lattice = KnowledgeLattice(data_dir=str(self._workspace))
            actuator = CrystalActuator(
                workspace=self._workspace, event_bus=self._event_bus,
            )

            # Phase 1: 轉化高置信結晶為行為規則
            actualize_report = actuator.actualize(lattice)

            # Phase 2: 新陳代謝（P3 回饋驅動的強化/淘汰）
            metabolize_report = actuator.metabolize()

            return {
                "new_rules": actualize_report.get("new_rules", 0),
                "expired_rules": actualize_report.get("expired_rules", 0),
                "total_active": actualize_report.get("total_active", 0),
                "strengthened": metabolize_report.get("strengthened", 0),
                "weakened": metabolize_report.get("weakened", 0),
                "removed": metabolize_report.get("removed", 0),
            }
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "CrystalActuator not available"}
        except Exception as e:
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 5.8: Morphenix 提案
    # ═══════════════════════════════════════════

    def _step_morphenix_proposals(self) -> Dict:
        """Step 5.8: ★ 信號驅動的自動演化提案生成.

        從七個系統信號源偵測問題，自動生成具體的 Morphenix 提案：
        0. Triage HIGH 訊號 → 先轉為迭代筆記（drain_priority_queue_to_notes）
        1. Q-Score 連續低分 → 調整 prompt 策略
        2. Knowledge Lattice 降級結晶 → 修正相關 Skill
        3. MetaCognition 預判失準 → 調整預測參數
        4. Skill Router 命中率低 → 調整路由權重
        5. 迭代筆記累積（含 triage 轉入）→ 傳統筆記結晶提案
        6. Nightly Report 錯誤步驟 → 管線修復提案

        這是從「被動記錄」跨越到「主動演化」的關鍵步驟。
        """
        # ── 前置步驟：將 triage HIGH 訊號轉為迭代筆記 ──
        # 必須在信號源 5 掃描 notes 之前執行，這樣 HIGH 訊號才會被信號源 5 直接消費。
        try:
            from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes
            _triage_result = drain_priority_queue_to_notes(self._workspace)
            if _triage_result["notes_created"] > 0:
                logger.info(
                    "[MORPHENIX 5.8] Triage 前置：%d 條 HIGH 訊號 → %d 條迭代筆記",
                    _triage_result["processed"],
                    _triage_result["notes_created"],
                )
        except Exception as e:
            logger.warning("[MORPHENIX 5.8] Triage 前置失敗（降級繼續）: %s", e)

        proposals_dir = self._workspace / "_system" / "morphenix" / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        proposals_created = 0
        signals_scanned = 0
        diagnostics = []

        # ═══ 信號源 1: Q-Score 連續低分偵測 ═══
        try:
            qscore_file = self._workspace / "eval" / "q_scores.jsonl"
            if qscore_file.exists():
                signals_scanned += 1
                recent_scores = []
                with open(qscore_file, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            recent_scores.append(entry)
                        except Exception as e:
                            logger.debug(f"[NIGHTLY] scoring failed (degraded): {e}")

                # 取最近 7 天
                week_ago = (datetime.now(TZ_TAIPEI) - timedelta(days=7)).isoformat()
                recent = [s for s in recent_scores if s.get("timestamp", "") >= week_ago]

                if len(recent) >= 5:
                    # 找出持續最低的維度
                    dims = ["understanding", "depth", "clarity", "actionability"]
                    dim_avgs = {}
                    for dim in dims:
                        vals = [s.get(dim, 0.5) for s in recent]
                        dim_avgs[dim] = sum(vals) / len(vals)

                    weakest_dim = min(dim_avgs, key=dim_avgs.get)
                    weakest_avg = dim_avgs[weakest_dim]

                    # 連續低分閾值：平均 < 0.5
                    if weakest_avg < 0.5:
                        # 計算新權重：基於差距比例提升（最多 +50%）
                        boost = min(1.5, 1.0 + (0.5 - weakest_avg))
                        proposal = {
                            "category": "L1",
                            "source": "qscore_signal",
                            "title": f"Q-Score 弱項修復: {weakest_dim} 維度平均僅 {weakest_avg:.2f}",
                            "description": (
                                f"過去 7 天 {len(recent)} 次互動中，"
                                f"{weakest_dim} 維度平均分數 {weakest_avg:.2f}（低於 0.5 閾值）。"
                                f"建議在系統提示詞中強化該維度的指引。"
                            ),
                            "action": f"increase_prompt_weight_{weakest_dim}",
                            "metric": {"dimension": weakest_dim, "current_avg": round(weakest_avg, 3)},
                            "metadata": {
                                "config_changes": [
                                    {
                                        "file": "_system/context_cache/active_rules.json",
                                        "key": f"{weakest_dim}_weight",
                                        "value": round(boost, 2),
                                        "old_value": 1.0,
                                    }
                                ]
                            },
                            "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                            "status": "pending_review",
                        }
                        out = proposals_dir / f"proposal_qscore_{date.today().isoformat()}.json"
                        with open(out, "w", encoding="utf-8") as fh:
                            json.dump(proposal, fh, ensure_ascii=False, indent=2)
                        proposals_created += 1
                        diagnostics.append(f"Q-Score: {weakest_dim} 偏弱 ({weakest_avg:.2f})")

                    # 整體品質下降偵測
                    overall_avg = sum(dim_avgs.values()) / len(dim_avgs)
                    consecutive_low = sum(
                        1 for s in recent[-5:]
                        if s.get("tier", "") == "low"
                    )
                    if consecutive_low >= 3:
                        # 找出最弱維度，產生可執行的 config_changes
                        _weakest = min(dim_avgs, key=dim_avgs.get) if dim_avgs else "depth"
                        _boost = round(min(1.5, 1.0 + (0.5 - overall_avg)), 2)
                        proposal = {
                            "category": "L2",
                            "source": "qscore_consecutive_low",
                            "title": f"連續 {consecutive_low} 次低分警報",
                            "description": (
                                f"最近 5 次互動中有 {consecutive_low} 次品質為 low。"
                                f"整體平均 {overall_avg:.2f}。需要深度檢視回應策略。"
                            ),
                            "action": "review_response_strategy",
                            "metric": {"consecutive_low": consecutive_low, "overall_avg": round(overall_avg, 3)},
                            "metadata": {
                                "config_changes": [
                                    {
                                        "file": "_system/context_cache/active_rules.json",
                                        "key": f"{_weakest}_weight",
                                        "value": _boost,
                                        "old_value": 1.0,
                                    }
                                ]
                            },
                            "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                            "status": "pending_review",
                        }
                        out = proposals_dir / f"proposal_consecutive_low_{date.today().isoformat()}.json"
                        with open(out, "w", encoding="utf-8") as fh:
                            json.dump(proposal, fh, ensure_ascii=False, indent=2)
                        proposals_created += 1
                        diagnostics.append(f"連續低分: {consecutive_low}/5")
        except Exception as e:
            logger.debug(f"Morphenix Q-Score signal scan failed: {e}")

        # ═══ 信號源 2: Knowledge Lattice 降級/矛盾偵測 ═══
        try:
            from museon.agent.crystal_store import CrystalStore
            _cs = CrystalStore(data_dir=str(self._workspace))
            if _cs.is_healthy():
                signals_scanned += 1
                crystals_data = _cs.load_crystals_raw()

                # 統計被降級的結晶（有反證的 Insight）
                downgraded = [
                    c for c in crystals_data
                    if isinstance(c, dict)
                    and c.get("counter_evidence_count", 0) >= 2
                    and c.get("crystal_type") == "Insight"
                ]
                if downgraded:
                    domains = set(c.get("domain", "general") for c in downgraded)
                    # 為每個被反證的領域產生降權 config_change
                    _lattice_changes = [
                        {
                            "file": "_system/context_cache/active_rules.json",
                            "key": f"domain_{d}_confidence",
                            "value": 0.7,
                            "old_value": 1.0,
                        }
                        for d in list(domains)[:3]
                    ]
                    proposal = {
                        "category": "L2",
                        "source": "knowledge_lattice_downgrade",
                        "title": f"{len(downgraded)} 顆 Insight 被反證，涉及領域: {', '.join(domains)}",
                        "description": (
                            f"知識晶格中有 {len(downgraded)} 顆 Insight 被反證 2+ 次，"
                            f"表示相關 Skill 的邏輯可能需要修正。"
                            f"涉及領域: {', '.join(domains)}"
                        ),
                        "action": "review_skill_logic",
                        "metric": {"downgraded_count": len(downgraded), "domains": list(domains)},
                        "metadata": {
                            "config_changes": _lattice_changes,
                        },
                        "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                        "status": "pending_review",
                    }
                    out = proposals_dir / f"proposal_lattice_{date.today().isoformat()}.json"
                    with open(out, "w", encoding="utf-8") as fh:
                        json.dump(proposal, fh, ensure_ascii=False, indent=2)
                    proposals_created += 1
                    diagnostics.append(f"Knowledge Lattice: {len(downgraded)} 降級")
        except Exception as e:
            logger.debug(f"Morphenix Lattice signal scan failed: {e}")

        # ═══ 信號源 3: MetaCognition 預判準確率 ═══
        try:
            meta_file = self._workspace / "_system" / "metacognition" / "accuracy_stats.json"
            if meta_file.exists():
                signals_scanned += 1
                with open(meta_file, "r", encoding="utf-8") as fh:
                    meta_stats = json.load(fh)

                accuracy = meta_stats.get("overall_accuracy", 0.5)
                total_predictions = meta_stats.get("total_predictions", 0)

                if total_predictions >= 10 and accuracy < 0.5:
                    proposal = {
                        "category": "L1",
                        "source": "metacognition_accuracy",
                        "title": f"元認知預判準確率偏低: {accuracy:.1%}",
                        "description": (
                            f"過去 {total_predictions} 次預判中，"
                            f"準確率僅 {accuracy:.1%}（目標 > 50%）。"
                            f"建議調整 _SIMILAR_TYPES 映射或預測啟發式參數。"
                        ),
                        "action": "tune_metacognition_params",
                        "metric": {"accuracy": round(accuracy, 3), "total_predictions": total_predictions},
                        "metadata": {
                            "config_changes": [
                                {
                                    "file": "_system/metacognition/accuracy_stats.json",
                                    "key": "prediction_confidence_threshold",
                                    "value": round(max(0.3, accuracy - 0.1), 2),
                                    "old_value": 0.5,
                                }
                            ]
                        },
                        "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                        "status": "pending_review",
                    }
                    out = proposals_dir / f"proposal_metacog_{date.today().isoformat()}.json"
                    with open(out, "w", encoding="utf-8") as fh:
                        json.dump(proposal, fh, ensure_ascii=False, indent=2)
                    proposals_created += 1
                    diagnostics.append(f"MetaCognition: 準確率 {accuracy:.1%}")
        except Exception as e:
            logger.debug(f"Morphenix MetaCognition signal scan failed: {e}")

        # ═══ 信號源 4: Skill Router 命中率 ═══
        try:
            usage_file = self._workspace / "skill_usage_log.jsonl"
            if usage_file.exists():
                signals_scanned += 1
                week_ago = (datetime.now(TZ_TAIPEI) - timedelta(days=7)).isoformat()
                total_routes = 0
                hits = 0

                with open(usage_file, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if entry.get("timestamp", "") >= week_ago:
                                total_routes += 1
                                if entry.get("user_accepted", True):
                                    hits += 1
                        except Exception as e:
                            logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

                if total_routes >= 10:
                    hit_rate = hits / total_routes
                    if hit_rate < 0.6:
                        # 提升 RC 倍率以增加路由命中率
                        new_rc = round(min(2.0, 1.0 + (0.6 - hit_rate)), 2)
                        proposal = {
                            "category": "L1",
                            "source": "skill_router_hit_rate",
                            "title": f"Skill Router 命中率偏低: {hit_rate:.1%}",
                            "description": (
                                f"過去 7 天 {total_routes} 次技能路由中，"
                                f"命中率僅 {hit_rate:.1%}（目標 > 60%）。"
                                f"建議調整 RC 倍率或觸發詞匹配策略。"
                            ),
                            "action": "tune_skill_router",
                            "metric": {"hit_rate": round(hit_rate, 3), "total_routes": total_routes},
                            "metadata": {
                                "config_changes": [
                                    {
                                        "file": "_system/context_cache/active_rules.json",
                                        "key": "skill_router_rc_multiplier",
                                        "value": new_rc,
                                        "old_value": 1.0,
                                    }
                                ]
                            },
                            "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                            "status": "pending_review",
                        }
                        out = proposals_dir / f"proposal_router_{date.today().isoformat()}.json"
                        with open(out, "w", encoding="utf-8") as fh:
                            json.dump(proposal, fh, ensure_ascii=False, indent=2)
                        proposals_created += 1
                        diagnostics.append(f"Skill Router: 命中率 {hit_rate:.1%}")
        except Exception as e:
            logger.debug(f"Morphenix Skill Router signal scan failed: {e}")

        # ═══ 信號源 5: 傳統迭代筆記（保留原邏輯）═══
        try:
            notes_dir = self._workspace / "_system" / "morphenix" / "notes"
            if notes_dir.exists():
                signals_scanned += 1
                notes = []
                for f in notes_dir.glob("*.json"):
                    try:
                        with open(f, "r", encoding="utf-8") as fh:
                            notes.append(json.load(fh))
                    except Exception as e:
                        logger.debug(f"[NIGHTLY] JSON parse failed (degraded): {e}")

                if len(notes) >= 3:
                    # 迭代筆記是觀察型提案，標記為 type=observation
                    # Executor 看到 observation 會記錄但不做 config 變更
                    proposal = {
                        "category": "L2",
                        "source": "iteration_notes",
                        "title": f"{len(notes)} 條迭代筆記待結晶",
                        "description": f"累積 {len(notes)} 條迭代觀察筆記，建議結晶為具體改進提案。",
                        "action": "crystallize_notes",
                        "source_notes": [f.name for f in notes_dir.glob("*.json") if f.is_file()][:20],
                        "metadata": {
                            "type": "observation",
                            "config_changes": [],
                        },
                        "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                        "status": "pending_review",
                    }
                    out = proposals_dir / f"proposal_notes_{date.today().isoformat()}.json"
                    with open(out, "w", encoding="utf-8") as fh:
                        json.dump(proposal, fh, ensure_ascii=False, indent=2)
                    proposals_created += 1
                    diagnostics.append(f"迭代筆記: {len(notes)} 條")
        except Exception as e:
            logger.debug(f"Morphenix notes signal scan failed: {e}")

        # ═══ 信號源 6: Nightly Report 錯誤步驟 → 修復提案 ═══
        try:
            report_file = self._workspace / "_system" / "state" / "nightly_report.json"
            if report_file.exists():
                signals_scanned += 1
                with open(report_file, "r", encoding="utf-8") as fh:
                    report_data = json.load(fh)

                error_steps = []
                for step_name, step_info in report_data.get("steps", {}).items():
                    if isinstance(step_info, dict) and step_info.get("status") == "error":
                        error_steps.append({
                            "step": step_name,
                            "result": str(step_info.get("result", ""))[:200],
                        })

                if error_steps:
                    # Nightly 錯誤步驟 → 標記需修復的步驟清單
                    config_changes = []
                    for es in error_steps[:5]:
                        config_changes.append({
                            "file": "_system/state/nightly_report.json",
                            "key": f"steps.{es['step']}.needs_repair",
                            "value": True,
                            "old_value": None,
                        })
                    proposal = {
                        "category": "L1",
                        "source": "nightly_report_errors",
                        "title": f"Nightly 管線 {len(error_steps)} 個步驟失敗需修復",
                        "description": (
                            f"上次 Nightly 執行中有 {len(error_steps)} 個步驟報錯: "
                            f"{', '.join(s['step'] for s in error_steps[:5])}。"
                            f"需要檢查並修復以恢復管線完整性。"
                        ),
                        "action": "fix_nightly_errors",
                        "metric": {
                            "error_count": len(error_steps),
                            "error_steps": error_steps[:10],
                        },
                        "metadata": {
                            "config_changes": config_changes,
                        },
                        "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                        "status": "pending_review",
                    }
                    out = proposals_dir / f"proposal_nightly_errors_{date.today().isoformat()}.json"
                    with open(out, "w", encoding="utf-8") as fh:
                        json.dump(proposal, fh, ensure_ascii=False, indent=2)
                    proposals_created += 1
                    diagnostics.append(f"Nightly Report: {len(error_steps)} 步驟失敗")
        except Exception as e:
            logger.debug(f"Morphenix Nightly Report signal scan failed: {e}")

        # ═══ 信號源 7: FeedbackLoop 隱性品質趨勢 ═══
        try:
            fl_file = self._workspace / "_system" / "feedback_loop" / "daily_summary.json"
            if fl_file.exists():
                signals_scanned += 1
                with open(fl_file, "r", encoding="utf-8") as fh:
                    fl_data = json.load(fh)

                avg_quality = fl_data.get("avg_quality", 0.5)
                interaction_count = fl_data.get("interaction_count", 0)
                trend = fl_data.get("trend_direction", "stable")

                if interaction_count >= 10 and avg_quality < 0.45:
                    proposal = {
                        "category": "L1",
                        "source": "feedback_loop_quality",
                        "title": f"使用者互動品質偏低: {avg_quality:.2f}",
                        "description": (
                            f"FeedbackLoop 偵測到近期 {interaction_count} 次互動的"
                            f"平均品質分 {avg_quality:.2f}（閾值 0.45），趨勢: {trend}。"
                            f"建議提升回應深度與個人化程度。"
                        ),
                        "action": "boost_response_quality",
                        "metric": {
                            "avg_quality": round(avg_quality, 3),
                            "interaction_count": interaction_count,
                            "trend": trend,
                        },
                        "metadata": {
                            "config_changes": [
                                {
                                    "file": "_system/context_cache/active_rules.json",
                                    "key": "response_depth_boost",
                                    "value": round(min(1.5, 1.0 + (0.45 - avg_quality)), 2),
                                    "old_value": 1.0,
                                }
                            ]
                        },
                        "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                        "status": "pending_review",
                    }
                    out = proposals_dir / f"proposal_feedback_{date.today().isoformat()}.json"
                    with open(out, "w", encoding="utf-8") as fh:
                        json.dump(proposal, fh, ensure_ascii=False, indent=2)
                    proposals_created += 1
                    diagnostics.append(f"FeedbackLoop: 品質 {avg_quality:.2f}, 趨勢 {trend}")
        except Exception as e:
            logger.debug(f"Morphenix FeedbackLoop signal scan failed: {e}")

        # ═══ 信號源 8: WEE 熟練度退化 → Skill 強化方向 ═══
        try:
            curricula_dir = self._workspace / "_system" / "curricula"
            if curricula_dir.exists():
                signals_scanned += 1
                # 讀取最近一份診斷
                diag_files = sorted(curricula_dir.glob("diagnosis_*.json"), reverse=True)
                if diag_files:
                    with open(diag_files[0], "r", encoding="utf-8") as fh:
                        diag = json.load(fh)

                    scores = diag.get("scores", {})
                    weak_dims = {k: v for k, v in scores.items() if isinstance(v, (int, float)) and v < 4.0}

                    if weak_dims:
                        weakest = min(weak_dims, key=weak_dims.get)
                        weakest_score = weak_dims[weakest]
                        proposal = {
                            "category": "L2",
                            "source": "wee_proficiency_gap",
                            "title": f"WEE 偵測到 {len(weak_dims)} 個弱項維度，最弱: {weakest} ({weakest_score:.1f})",
                            "description": (
                                f"工作流熟練度診斷顯示 {len(weak_dims)} 個維度低於 4.0: "
                                f"{', '.join(f'{k}={v:.1f}' for k, v in weak_dims.items())}。"
                                f"建議研究或強化相關 Skill 的處理能力。"
                            ),
                            "action": "skill_gap_research",
                            "metric": {"weak_dims": {k: round(v, 2) for k, v in weak_dims.items()}},
                            "metadata": {
                                "type": "skill_research_request",
                                "config_changes": [],
                                "scout_topics": [f"{dim} 能力強化" for dim in list(weak_dims.keys())[:3]],
                            },
                            "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                            "status": "pending_review",
                        }
                        out = proposals_dir / f"proposal_wee_gap_{date.today().isoformat()}.json"
                        with open(out, "w", encoding="utf-8") as fh:
                            json.dump(proposal, fh, ensure_ascii=False, indent=2)
                        proposals_created += 1
                        diagnostics.append(f"WEE: {len(weak_dims)} 弱項, 最弱 {weakest}={weakest_score:.1f}")
        except Exception as e:
            logger.debug(f"Morphenix WEE signal scan failed: {e}")

        result = {
            "signals_scanned": signals_scanned,
            "proposals_created": proposals_created,
            "diagnostics": diagnostics,
        }

        if proposals_created > 0:
            logger.info(
                f"[MORPHENIX] 信號驅動提案: 掃描 {signals_scanned} 個信號源, "
                f"生成 {proposals_created} 個提案 | {'; '.join(diagnostics)}"
            )
        else:
            logger.info(
                f"[MORPHENIX] 信號掃描完成: {signals_scanned} 個信號源, 系統健康無需提案"
            )

        return result

    # ═══════════════════════════════════════════
    # Step 5.9: Morphenix 演化門控
    # ═══════════════════════════════════════════

    def _step_morphenix_gate(self) -> Dict:
        """Step 5.9: 處理 pending proposals → 分級門控 → 執行/排隊.

        L1: 自動核准 + 立即執行
        L2: 自動核准，標記待測試
        L3: 寫入 PulseDB + Telegram inline keyboard 通知 → 72hr 未處理自動批准
        """
        proposals_dir = self._workspace / "_system" / "morphenix" / "proposals"
        if not proposals_dir.exists():
            return {"skipped": "no proposals directory"}

        pending = []
        for f in proposals_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    proposal = json.load(fh)
                _st = proposal.get("status", "")
                if _st in ("pending_review", "approved_pending_test", "pending"):
                    proposal["_file"] = str(f)
                    pending.append(proposal)
                    logger.info(
                        f"[MORPHENIX 5.9] Found proposal: {f.name}, "
                        f"status={_st}, category={proposal.get('category', '?')}"
                    )
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        if not pending:
            return {"skipped": "no pending proposals"}

        # 取得 PulseDB（用於持久化 L3 提案）
        pulse_db = None
        try:
            from museon.pulse.pulse_db import get_pulse_db
            pulse_db = get_pulse_db(self._workspace)
        except Exception as e:
            logger.warning(f"Morphenix gate: PulseDB init failed: {e}")

        results = {"auto_approved": 0, "needs_human": 0, "executed": 0, "l3_proposals": []}

        for proposal in pending:
            category = proposal.get("category", proposal.get("type", "L1"))

            # 分級門控
            if "L1" in str(category):
                # L1 Config: 自動核准 + 立即執行
                proposal["status"] = "approved"
                proposal["decided_by"] = "auto"
                proposal["decided_at"] = datetime.now(TZ_TAIPEI).isoformat()
                results["auto_approved"] += 1
                results["executed"] += 1

                # L1 持久化到 PulseDB（讓 Executor 能看到）
                if pulse_db:
                    try:
                        pid = f"morphenix_{date.today().isoformat()}_L1_{results['auto_approved']:03d}"
                        # 傳遞 metadata（含 config_changes）讓 Executor 能實際執行
                        _meta = proposal.get("metadata", {})
                        if not _meta and proposal.get("action"):
                            # fallback: 把 action/metric 打包進 metadata
                            _meta = {
                                "action": proposal.get("action", ""),
                                "metric": proposal.get("metric", {}),
                            }
                        pulse_db.save_proposal(
                            proposal_id=pid,
                            level="L1",
                            title=proposal.get("title", "L1 Config 提案"),
                            description=proposal.get("description", proposal.get("summary", "")),
                            affected_files=proposal.get("affected_files", []) if isinstance(proposal.get("affected_files"), list) else [],
                            source_notes=proposal.get("source_notes", []) if isinstance(proposal.get("source_notes"), list) else [],
                            metadata=_meta,
                        )
                        pulse_db.approve_proposal(pid, decided_by="auto")
                        logger.info(f"Morphenix L1 proposal saved+approved in DB: {pid}")
                    except Exception as e:
                        logger.error(f"Morphenix L1 DB persist FAILED: {e}", exc_info=True)

            elif "L2" in str(category):
                # L2 Logic: 自動核准（直接 approved，因無測試設施）
                proposal["status"] = "approved"
                proposal["decided_by"] = "auto"
                proposal["decided_at"] = datetime.now(TZ_TAIPEI).isoformat()
                results["auto_approved"] += 1

                # L2 持久化到 PulseDB（讓 Executor 能看到）
                if pulse_db:
                    try:
                        pid = f"morphenix_{date.today().isoformat()}_L2_{results['auto_approved']:03d}"
                        _meta = proposal.get("metadata", {})
                        if not _meta and proposal.get("action"):
                            _meta = {
                                "action": proposal.get("action", ""),
                                "metric": proposal.get("metric", {}),
                            }
                        pulse_db.save_proposal(
                            proposal_id=pid,
                            level="L2",
                            title=proposal.get("title", "L2 Logic 提案"),
                            description=proposal.get("description", proposal.get("summary", "")),
                            affected_files=proposal.get("affected_files", []) if isinstance(proposal.get("affected_files"), list) else [],
                            source_notes=proposal.get("source_notes", []) if isinstance(proposal.get("source_notes"), list) else [],
                            metadata=_meta,
                        )
                        pulse_db.approve_proposal(pid, decided_by="auto")
                        logger.info(f"Morphenix L2 proposal saved+approved in DB: {pid}")
                    except Exception as e:
                        logger.error(f"Morphenix L2 DB persist FAILED: {e}", exc_info=True)

            elif "L3" in str(category):
                # L3 Architecture: 寫入 DB + Telegram 通知
                proposal["status"] = "awaiting_human_approval"
                proposal["decided_by"] = "pending"
                results["needs_human"] += 1

                # 持久化到 PulseDB
                if pulse_db:
                    try:
                        proposal_id = f"morphenix_{date.today().isoformat()}_{results['needs_human']:03d}"
                        title = proposal.get("title", proposal.get("type", "L3 提案"))
                        description = proposal.get("description", proposal.get("summary", "系統架構級演化提案"))
                        affected = proposal.get("affected_files", [])
                        notes = proposal.get("source_notes", [])

                        pulse_db.save_proposal(
                            proposal_id=proposal_id,
                            level="L3",
                            title=title,
                            description=description,
                            affected_files=affected if isinstance(affected, list) else [],
                            source_notes=[str(n) for n in (notes if isinstance(notes, list) else [])],
                            metadata=proposal.get("metadata", {}),
                        )
                        results["l3_proposals"].append({
                            "id": proposal_id,
                            "title": title,
                            "description": description,
                            "affected_files": affected if isinstance(affected, list) else [],
                        })
                        logger.info(f"Morphenix L3 proposal saved to DB: {proposal_id}")
                    except Exception as e:
                        logger.error(f"Morphenix L3 DB save failed: {e}")

            else:
                # 未分類，預設為 L1（Contract 4: 同時寫入 PulseDB）
                proposal["status"] = "approved"
                proposal["decided_by"] = "auto"
                proposal["decided_at"] = datetime.now(TZ_TAIPEI).isoformat()
                results["auto_approved"] += 1

                # 持久化到 PulseDB（確保 Executor 能讀到）
                if pulse_db:
                    try:
                        pid = f"morphenix_{date.today().isoformat()}_auto_{results['auto_approved']:03d}"
                        _meta = proposal.get("metadata", {})
                        if not _meta and proposal.get("action"):
                            _meta = {
                                "action": proposal.get("action", ""),
                                "metric": proposal.get("metric", {}),
                            }
                        pulse_db.save_proposal(
                            proposal_id=pid,
                            level="L1",
                            title=proposal.get("title", "未分類提案"),
                            description=proposal.get("description", proposal.get("summary", "")),
                            affected_files=proposal.get("affected_files", []) if isinstance(proposal.get("affected_files"), list) else [],
                            source_notes=proposal.get("source_notes", []) if isinstance(proposal.get("source_notes"), list) else [],
                            metadata=_meta,
                        )
                        pulse_db.approve_proposal(pid, decided_by="auto")
                        logger.info(f"Morphenix uncategorized proposal saved+approved in DB: {pid}")
                    except Exception as e:
                        logger.error(f"Morphenix uncategorized DB persist FAILED: {e}")

            # 寫回 JSON 檔
            try:
                filepath = proposal.pop("_file", None)
                if filepath:
                    with open(filepath, "w", encoding="utf-8") as fh:
                        json.dump(proposal, fh, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"Morphenix gate write-back failed: {e}")

        # 發布 MORPHENIX_PROPOSAL_CREATED（ActivityLogger 訂閱）
        total_proposals = results["auto_approved"] + results["needs_human"]
        if total_proposals > 0 and self._event_bus:
            try:
                from museon.core.event_bus import MORPHENIX_PROPOSAL_CREATED
                self._event_bus.publish(MORPHENIX_PROPOSAL_CREATED, {
                    "auto_approved": results["auto_approved"],
                    "needs_human": results["needs_human"],
                    "l3_count": len(results.get("l3_proposals", [])),
                    "total": total_proposals,
                })
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        # L3 提案 → 透過 EventBus 發送 Telegram inline keyboard 通知
        if results["l3_proposals"] and self._event_bus:
            try:
                from museon.core.event_bus import MORPHENIX_L3_PROPOSAL
                self._event_bus.publish(MORPHENIX_L3_PROPOSAL, {
                    "proposals": results["l3_proposals"],
                })
                logger.info(
                    f"Morphenix: published {len(results['l3_proposals'])} L3 proposals to EventBus"
                )
            except Exception as e:
                logger.warning(f"Morphenix EventBus publish failed: {e}")

        if results["needs_human"] > 0:
            logger.info(
                f"Morphenix: {results['needs_human']} proposals need human approval (72h auto-approve)"
            )

        return results

    # ═══════════════════════════════════════════
    # Step 5.9.5: Morphenix Docker 驗證
    # ═══════════════════════════════════════════

    def _step_morphenix_validate(self) -> Dict:
        """Step 5.9.5: 在 Docker 隔離環境中驗證 L2+ 提案.

        L1 跳過 Docker（只改 JSON，風險低）。
        L2+ 強制 Docker pytest 驗證，失敗則 reject。
        """
        try:
            from museon.pulse.pulse_db import get_pulse_db
            pulse_db = get_pulse_db(self._workspace)
        except Exception as e:
            return {"skipped": f"PulseDB init failed: {e}"}

        approved = [
            p for p in pulse_db.get_all_proposals(100)
            if p.get("status") == "approved"
        ]
        l2_plus = [p for p in approved if p.get("level") in ("L2", "L3")]

        if not l2_plus:
            return {"skipped": "no L2+ proposals to validate", "total_approved": len(approved)}

        try:
            from museon.nightly.morphenix_validator import MorphenixValidator
            validator = MorphenixValidator(source_root=self._source_root)
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "MorphenixValidator not available"}

        results = {"validated": 0, "passed": 0, "failed": 0, "details": []}

        for proposal in l2_plus:
            pid = proposal.get("id", "?")
            try:
                vresult = _run_async_safe(validator.validate_proposal(proposal))
                results["validated"] += 1

                if vresult.passed:
                    results["passed"] += 1
                    logger.info(
                        f"[MORPHENIX 5.9.5] {pid} Docker validation PASSED "
                        f"({vresult.reason}, {vresult.duration_ms}ms)"
                    )
                else:
                    results["failed"] += 1
                    # reject 提案
                    pulse_db.reject_proposal(pid, decided_by="docker_validator")
                    logger.warning(
                        f"[MORPHENIX 5.9.5] {pid} Docker validation FAILED: "
                        f"{vresult.reason} — REJECTED"
                    )

                results["details"].append({
                    "id": pid,
                    "passed": vresult.passed,
                    "reason": vresult.reason,
                    "duration_ms": vresult.duration_ms,
                })

            except Exception as e:
                logger.error(f"[MORPHENIX 5.9.5] {pid} validation error: {e}")
                results["details"].append({
                    "id": pid,
                    "passed": False,
                    "reason": f"error: {str(e)[:100]}",
                })

        return results

    # ═══════════════════════════════════════════
    # Step 5.10: Morphenix 執行
    # ═══════════════════════════════════════════

    def _step_morphenix_execute(self) -> Dict:
        """Step 5.10: 執行已核准的 Morphenix 演化提案.

        流程：PulseDB 中 status='approved' 的提案
        → Core Brain 審查 → git tag 安全快照 → 執行變更 → 標記 executed
        """
        try:
            from museon.pulse.pulse_db import get_pulse_db
            pulse_db = get_pulse_db(self._workspace)
        except Exception as e:
            return {"skipped": f"PulseDB init failed: {e}"}

        # 先執行 72 小時自動批准
        try:
            auto_approved = pulse_db.auto_approve_stale_proposals(hours=72)
            if auto_approved:
                logger.info(
                    f"Morphenix: auto-approved {len(auto_approved)} stale proposals"
                )
        except Exception as e:
            logger.warning(f"Morphenix auto-approve failed: {e}")

        try:
            from museon.nightly.morphenix_executor import MorphenixExecutor

            source_root = Path(os.environ.get(
                "MUSEON_SOURCE_ROOT",
                str(self._workspace.parent.parent / "museon"),
            ))

            executor = MorphenixExecutor(
                workspace=self._workspace,
                source_root=source_root,
                pulse_db=pulse_db,
                event_bus=self._event_bus,
            )
            result = executor.execute_approved()
            return result

        except Exception as e:
            logger.error(f"Morphenix Executor step failed: {e}")
            return {"error": str(e), "executed": 0}

    # ═══════════════════════════════════════════
    # Step 19: Morphenix 演化品質驗證
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/morphenix/logs/effect_tracker.json)
    def _step_morphenix_quality_gate(self) -> Dict:
        """Step 19: Morphenix 執行後品質驗證.

        讀取演化執行前的品質基線，與最近 10 筆互動比較。
        品質下降 > 10% → 自動生成回滾提案。
        """
        try:
            from museon.pulse.pulse_db import get_pulse_db
            pulse_db = get_pulse_db(self._workspace)
        except Exception as e:
            return {"skipped": f"PulseDB init failed: {e}"}

        # 讀取 effect_tracker 中最近執行的提案
        log_dir = self._workspace / "_system" / "morphenix" / "logs"
        tracker_file = log_dir / "effect_tracker.json"
        if not tracker_file.exists():
            return {"skipped": "no effect_tracker.json"}

        try:
            with open(tracker_file, "r", encoding="utf-8") as fh:
                tracker = json.load(fh)
        except Exception as e:
            return {"skipped": f"effect_tracker read failed: {e}"}

        # 找出過去 24 小時內執行的提案
        now = datetime.now(TZ_TAIPEI)
        recent_executions = []
        for pid, entry in tracker.items():
            if entry.get("evaluated"):
                continue
            try:
                exec_at = datetime.fromisoformat(entry["executed_at"])
                if (now - exec_at).total_seconds() < 86400:
                    recent_executions.append((pid, entry))
            except (KeyError, ValueError):
                continue

        if not recent_executions:
            return {"skipped": "no recent executions to verify", "tracker_size": len(tracker)}

        # 讀取品質基線：最近 10 筆 Q-Score
        qscore_file = self._workspace / "eval" / "q_scores.jsonl"
        if not qscore_file.exists():
            return {
                "skipped": "no q_scores.jsonl for comparison",
                "recent_executions": len(recent_executions),
            }

        recent_scores = []
        try:
            with open(qscore_file, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        recent_scores.append(json.loads(line))
                    except Exception:
                        pass
        except Exception as e:
            return {"skipped": f"q_scores read failed: {e}"}

        if len(recent_scores) < 5:
            return {"skipped": "insufficient q_scores data", "count": len(recent_scores)}

        # 取最近 10 筆和之前 10 筆比較
        latest_10 = recent_scores[-10:]
        baseline_10 = recent_scores[-20:-10] if len(recent_scores) >= 20 else recent_scores[:-10]

        if not baseline_10:
            return {"skipped": "insufficient baseline data"}

        dims = ["understanding", "depth", "clarity", "actionability"]
        regression_detected = False
        regressions = []

        for dim in dims:
            latest_avg = sum(s.get(dim, 0.5) for s in latest_10) / len(latest_10)
            baseline_avg = sum(s.get(dim, 0.5) for s in baseline_10) / len(baseline_10)

            if baseline_avg > 0 and (baseline_avg - latest_avg) / baseline_avg > 0.1:
                regression_detected = True
                regressions.append({
                    "dimension": dim,
                    "baseline_avg": round(baseline_avg, 3),
                    "latest_avg": round(latest_avg, 3),
                    "drop_pct": round((baseline_avg - latest_avg) / baseline_avg * 100, 1),
                })

        rollback_proposals = 0

        if regression_detected:
            # 品質下降 > 10% → 為最近執行的提案生成回滾提案
            proposals_dir = self._workspace / "_system" / "morphenix" / "proposals"
            proposals_dir.mkdir(parents=True, exist_ok=True)

            for pid, entry in recent_executions:
                rollback_proposal = {
                    "category": "L1",
                    "source": "quality_gate_rollback",
                    "title": f"品質回滾: {entry.get('title', pid)}",
                    "description": (
                        f"提案 {pid} 執行後品質下降超過 10%。"
                        f"下降維度: {', '.join(r['dimension'] + '(-' + str(r['drop_pct']) + '%)' for r in regressions)}。"
                        f"建議回滾。"
                    ),
                    "action": "rollback_proposal",
                    "metric": {
                        "original_proposal": pid,
                        "regressions": regressions,
                        "safety_tag": entry.get("safety_tag", ""),
                    },
                    "metadata": {
                        "rollback_target": pid,
                        "safety_tag": entry.get("safety_tag", ""),
                        "config_changes": entry.get("exec_result", {}).get("applied", []),
                    },
                    "created_at": now.isoformat(),
                    "status": "pending_review",
                }
                out = proposals_dir / f"proposal_rollback_{pid}_{date.today().isoformat()}.json"
                try:
                    with open(out, "w", encoding="utf-8") as fh:
                        json.dump(rollback_proposal, fh, ensure_ascii=False, indent=2)
                    rollback_proposals += 1
                    logger.warning(
                        f"[MORPHENIX QG] Quality regression detected after {pid}: "
                        f"{regressions} — rollback proposal created"
                    )
                except Exception as e:
                    logger.error(f"[MORPHENIX QG] Failed to write rollback proposal: {e}")

            # 透過 EventBus 警告
            if self._event_bus and rollback_proposals > 0:
                try:
                    self._event_bus.publish("PROACTIVE_MESSAGE", {
                        "message": (
                            f"Morphenix 品質警報\n\n"
                            f"最近執行的 {len(recent_executions)} 個演化提案導致品質下降：\n"
                            + "\n".join(
                                f"  - {r['dimension']}: {r['baseline_avg']:.2f} -> {r['latest_avg']:.2f} (-{r['drop_pct']}%)"
                                for r in regressions
                            )
                            + f"\n\n已生成 {rollback_proposals} 個回滾提案。"
                        ),
                        "source": "alert",
                        "timestamp": time.time(),
                    })
                except Exception as e:
                    logger.debug(f"[MORPHENIX QG] EventBus publish failed: {e}")

        return {
            "recent_executions": len(recent_executions),
            "regression_detected": regression_detected,
            "regressions": regressions,
            "rollback_proposals_created": rollback_proposals,
        }

    # ═══════════════════════════════════════════
    # Step 6: 技能鍛造
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/memory/shared/L2_ep/ directory with items)
    def _step_skill_forge(self) -> Dict:
        """Step 6: L2_ep 聚類 → L3_procedural 技能."""
        memory_dir = self._workspace / "_system" / "memory" / "shared" / "L2_ep"
        if not memory_dir.exists():
            return {"skipped": "no L2_ep directory"}

        items = []
        for f in memory_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    items.append(json.load(fh))
            except Exception as e:
                logger.debug(f"[NIGHTLY] JSON parse failed (degraded): {e}")

        if len(items) < SKILL_FORGE_MIN_CLUSTER:
            return {"skipped": "not enough L2_ep items", "count": len(items)}

        try:
            from museon.memory.chromosome_index import ChromosomeIndex
            ci = ChromosomeIndex()
            for item in items:
                text = item.get("content", item.get("summary", ""))
                tags = item.get("tags", [])
                ci.add(item.get("id", ""), text, tags=tags)

            clusters = ci.cluster(
                threshold=SKILL_FORGE_SIMILARITY_THRESHOLD,
                min_size=SKILL_FORGE_MIN_CLUSTER,
            )

            # 每個聚類鍛造為 L3_procedural
            forged = 0
            l3_dir = self._workspace / "_system" / "memory" / "shared" / "L3_procedural"
            l3_dir.mkdir(parents=True, exist_ok=True)
            for i, cluster in enumerate(clusters):
                skill = {
                    "type": "L3_procedural",
                    "cluster_id": i,
                    "source_count": len(cluster) if isinstance(cluster, list) else 1,
                    "forged_at": datetime.now(TZ_TAIPEI).isoformat(),
                }
                out = l3_dir / f"skill_{date.today().isoformat()}_{i}.json"
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(skill, fh, ensure_ascii=False, indent=2)
                forged += 1

            return {"forged": forged, "clusters": len(clusters)}
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "ChromosomeIndex not available"}

    # ═══════════════════════════════════════════
    # Step 6.5: SkillForge Scout（探索發現 → 技能改善研究）
    # ═══════════════════════════════════════════

    def _step_skill_scout(self) -> Dict:
        """Step 6.5: 消費 scout_queue 中的待研究項目，產出技能改善草稿."""
        queue_file = self._workspace / "_system" / "bridge" / "scout_queue" / "pending.json"
        if not queue_file.exists():
            return {"skipped": "no scout_queue"}

        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                queue = json.load(fh)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "scout_queue read error"}

        pending = [q for q in queue if q.get("status") == "pending"]
        if not pending:
            return {"skipped": "no pending scout items"}

        # 去重：相同 topic 只保留第一個
        seen_topics: set = set()
        deduped: list = []
        for item in pending:
            topic = item.get("topic", "").strip()
            if topic and topic not in seen_topics:
                seen_topics.add(topic)
                deduped.append(item)
        removed_dupes = len(pending) - len(deduped)

        if not deduped:
            return {"skipped": "all scout items were duplicates", "removed": removed_dupes}

        # 嘗試呼叫 SkillForgeScout
        processed = 0
        errors = []
        try:
            from museon.nightly.skill_forge_scout import SkillForgeScout
            scout = SkillForgeScout(
                brain=self._brain,
                event_bus=self._event_bus,
                workspace=self._workspace,
            )
            # 每次最多處理 3 個（控制 Token 成本）
            results = _run_async_safe(scout.process_queue(max_items=3))
            processed = len(results) if results else 0
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            errors.append("SkillForgeScout not available")
        except Exception as e:
            errors.append(str(e))
            logger.warning(f"SkillForgeScout process_queue failed: {e}")

        # 更新 queue：標記已處理的 + 去重後的
        updated_queue = []
        for item in queue:
            topic = item.get("topic", "").strip()
            if topic in seen_topics:
                if topic not in {d.get("topic", "").strip() for d in updated_queue if d.get("status") == "pending"}:
                    updated_queue.append(item)
            else:
                updated_queue.append(item)

        try:
            with open(queue_file, "w", encoding="utf-8") as fh:
                json.dump(updated_queue, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"scout_queue write-back failed: {e}")

        return {
            "processed": processed,
            "deduped": len(deduped),
            "removed_duplicates": removed_dupes,
            "errors": errors if errors else None,
        }

    # ═══════════════════════════════════════════
    # Step 7: 課程診斷
    # ═══════════════════════════════════════════

    def _step_curriculum(self) -> Dict:
        """Step 7: WEE 熟練度診斷."""
        scores_file = self._workspace / "_system" / "wee" / "proficiency.json"
        if not scores_file.exists():
            # 使用預設分數
            scores = {"speed": 5.0, "quality": 5.0, "alignment": 5.0, "leverage": 5.0}
        else:
            try:
                with open(scores_file, "r", encoding="utf-8") as fh:
                    scores = json.load(fh)
            except Exception as e:
                logger.debug(f"[NIGHTLY] degraded: {e}")
                scores = {"speed": 5.0, "quality": 5.0, "alignment": 5.0, "leverage": 5.0}

        avg = sum(scores.values()) / max(len(scores), 1)
        if avg >= 8.0:
            level = "advanced"
        elif avg >= 5.0:
            level = "intermediate"
        else:
            level = "beginner"

        # 寫入課程處方
        curricula_dir = self._workspace / "_system" / "curricula"
        curricula_dir.mkdir(parents=True, exist_ok=True)
        prescription = {
            "level": level,
            "scores": scores,
            "avg": round(avg, 2),
            "diagnosed_at": datetime.now(TZ_TAIPEI).isoformat(),
        }
        out = curricula_dir / f"diagnosis_{date.today().isoformat()}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(prescription, fh, ensure_ascii=False, indent=2)

        return {"level": level, "avg_score": round(avg, 2)}

    # ═══════════════════════════════════════════
    # Step 7.5: 自動課程生成 (EXT-10)
    # ═══════════════════════════════════════════

    def _step_auto_course(self) -> Dict:
        """Step 7.5: 根據知識圖譜自動生成/更新課程."""
        try:
            from museon.nightly.course_generator import CourseGenerator

            generator = CourseGenerator(
                workspace=self._workspace,
                event_bus=self._event_bus,
                brain=self._brain,
            )

            # 從最近的課程診斷取得 topic
            curricula_dir = self._workspace / "_system" / "curricula"
            topics = []
            if curricula_dir.exists():
                for f in sorted(curricula_dir.glob("diagnosis_*.json"), reverse=True)[:1]:
                    try:
                        with open(f, "r", encoding="utf-8") as fh:
                            diag = json.load(fh)
                        level = diag.get("level", "intermediate")
                        # 取得低分項目作為課程主題
                        scores = diag.get("scores", {})
                        weak = [k for k, v in scores.items() if v < 5.0]
                        topics.extend(weak[:2])
                    except Exception as e:
                        logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

            if not topics:
                return {"skipped": "no weak topics identified"}

            # 同步呼叫（CourseGenerator.generate_course 是 async，這裡包裝）
            results = []
            for topic in topics:
                try:
                    course = _run_async_safe(generator.generate_course(topic))
                    results.append({"topic": topic, "course_id": course.get("course_id")})
                except Exception as e:
                    results.append({"topic": topic, "error": str(e)})

            return {"courses_generated": len(results), "results": results}
        except ImportError as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "course_generator not available"}

    # ═══════════════════════════════════════════
    # Step 8: 工作流突變
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/wee/workflows/ directory)
    def _step_workflow_mutation(self) -> Dict:
        """Step 8: 高原偵測 + 自動突變."""
        wee_dir = self._workspace / "_system" / "wee" / "workflows"
        if not wee_dir.exists():
            return {"skipped": "no workflows directory"}

        scanned = 0
        plateaus = 0
        mutations = 0

        for wf_dir in wee_dir.iterdir():
            if not wf_dir.is_dir():
                continue

            # 讀取執行記錄
            runs_file = wf_dir / "runs.json"
            if not runs_file.exists():
                scanned += 1
                continue

            try:
                with open(runs_file, "r", encoding="utf-8") as fh:
                    runs = json.load(fh)
            except Exception as e:
                logger.debug(f"[NIGHTLY] degraded: {e}")
                scanned += 1
                continue

            scanned += 1
            scores = [r.get("score", 0) for r in runs if "score" in r]

            if len(scores) < PLATEAU_MIN_RUNS:
                continue

            avg = sum(scores) / len(scores)
            variance = sum((s - avg) ** 2 for s in scores) / len(scores)

            if variance < PLATEAU_MAX_VARIANCE and avg < PLATEAU_MAX_AVG:
                plateaus += 1
                # 自動生成突變方案
                strategy = random.choice(MUTATION_STRATEGIES)
                mutation = {
                    "workflow": wf_dir.name,
                    "strategy": strategy,
                    "avg_score": round(avg, 2),
                    "variance": round(variance, 3),
                    "created_at": datetime.now(TZ_TAIPEI).isoformat(),
                }
                mutation_file = wf_dir / f"mutation_{date.today().isoformat()}.json"
                with open(mutation_file, "w", encoding="utf-8") as fh:
                    json.dump(mutation, fh, ensure_ascii=False, indent=2)
                mutations += 1

        return {
            "workflows_scanned": scanned,
            "plateaus_found": plateaus,
            "mutations_applied": mutations,
        }

    # ═══════════════════════════════════════════
    # Step 8.6: Skill 向量重索引
    # ═══════════════════════════════════════════

    def _step_skill_vector_reindex(self) -> Dict:
        """Step 8.6: Skill 向量重索引——全量重建 skills collection（零 LLM）."""
        try:
            from museon.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=self._workspace, event_bus=self._event_bus)
            result = vb.index_all_skills()
            return {"skill_reindex": result}
        except Exception as e:
            logger.warning(f"Nightly skill reindex failed: {e}")
            return {"skill_reindex": {"error": str(e)}}

    # ═══════════════════════════════════════════
    # Step 8.7: Sparse IDF 重建 + 回填
    # ═══════════════════════════════════════════

    def _step_sparse_idf_rebuild(self) -> Dict:
        """Step 8.7: 重建 BM25 IDF 表 + 回填 sparse collections（零 LLM）.

        從 memories dense collection 建立 IDF → 回填所有 sparse collections。
        """
        try:
            from museon.vector.vector_bridge import VectorBridge
            vb = VectorBridge(workspace=self._workspace, event_bus=self._event_bus)

            # Phase 1: 從 memories 語料建立 IDF
            vocab_size = vb.build_sparse_idf("memories")
            if vocab_size == 0:
                return {"sparse_idf": "skipped — no corpus or jieba unavailable"}

            # Phase 2: 回填各 collection 的 sparse 版本
            backfill_results = {}
            for collection in ("memories", "skills", "crystals"):
                try:
                    count = vb.backfill_sparse(collection, batch_size=50)
                    backfill_results[collection] = count
                except Exception as e:
                    backfill_results[collection] = f"error: {e}"

            return {
                "sparse_idf": {
                    "vocab_size": vocab_size,
                    "backfill": backfill_results,
                }
            }
        except Exception as e:
            logger.warning(f"Nightly sparse IDF rebuild failed: {e}")
            return {"sparse_idf": {"error": str(e)}}

    # ═══════════════════════════════════════════
    # Step 9: 知識圖譜睡眠整合
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/graph/edges.json and nodes.json)
    def _step_graph_consolidation(self) -> Dict:
        """Step 9: 7 層遺忘機制."""
        graph_dir = self._workspace / "_system" / "graph"
        if not graph_dir.exists():
            return {"skipped": "no graph directory"}

        edges_file = graph_dir / "edges.json"
        nodes_file = graph_dir / "nodes.json"
        if not edges_file.exists():
            return {"skipped": "no graph edges"}

        try:
            with open(edges_file, "r", encoding="utf-8") as fh:
                edges = json.load(fh)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "edges file unreadable"}

        try:
            with open(nodes_file, "r", encoding="utf-8") as fh:
                nodes = json.load(fh)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            nodes = {}

        stats = {
            "replay_boosted": 0,
            "decayed": 0,
            "pruned": 0,
            "archived_nodes": 0,
            "merged_nodes": 0,
        }

        # 1. 重播強化（高頻存取邊 +20%）
        for eid, edge in edges.items():
            access_count = edge.get("access_count", 0)
            if access_count >= 3:  # 高頻閾值
                edge["weight"] = min(1.0, edge.get("weight", 0.5) * (1 + GRAPH_REPLAY_BOOST))
                stats["replay_boosted"] += 1

        # 2. 自然衰減
        for eid, edge in edges.items():
            edge["weight"] = round(edge.get("weight", 0.5) * GRAPH_DECAY_FACTOR, 4)
            stats["decayed"] += 1

        # 3. 修剪弱邊（< 0.1）
        to_prune = [eid for eid, e in edges.items() if e.get("weight", 0) < GRAPH_WEAK_EDGE_THRESHOLD]
        for eid in to_prune:
            del edges[eid]
            stats["pruned"] += 1

        # 4. 垃圾回收（孤立節點歸檔）
        connected_nodes = set()
        for edge in edges.values():
            connected_nodes.add(edge.get("source", ""))
            connected_nodes.add(edge.get("target", ""))

        archive_dir = graph_dir / "archived"
        archive_dir.mkdir(parents=True, exist_ok=True)
        orphans = [nid for nid in nodes if nid not in connected_nodes]
        for nid in orphans:
            archived = nodes.pop(nid)
            archived["archived_at"] = datetime.now(TZ_TAIPEI).isoformat()
            arch_file = archive_dir / f"{nid}.json"
            with open(arch_file, "w", encoding="utf-8") as fh:
                json.dump(archived, fh, ensure_ascii=False, indent=2)
            stats["archived_nodes"] += 1

        # 5. 合併弱節點（簡化：同名節點合併）
        # 完整版需語意相似度，此處用 placeholder
        stats["merged_nodes"] = 0

        # 回寫
        with open(edges_file, "w", encoding="utf-8") as fh:
            json.dump(edges, fh, ensure_ascii=False, indent=2)
        with open(nodes_file, "w", encoding="utf-8") as fh:
            json.dump(nodes, fh, ensure_ascii=False, indent=2)

        # WP-06: 發布 KNOWLEDGE_GRAPH_UPDATED（含高品質節點供 SharedAssets 自動發布）
        high_quality_nodes = []
        for nid, node in nodes.items():
            q = node.get("quality", node.get("weight", 0.5))
            if q > 0.6:
                high_quality_nodes.append({
                    "title": node.get("label", node.get("title", nid)),
                    "content": node.get("content", node.get("description", "")),
                    "quality": q,
                    "tags": node.get("tags", []),
                })
        self._publish(KNOWLEDGE_GRAPH_UPDATED, {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "high_quality_nodes": high_quality_nodes[:10],
            **stats,
        })

        return stats

    # ═══════════════════════════════════════════
    # Step 10: 靈魂日記生成 + 情緒衰減（v2.0）
    # ═══════════════════════════════════════════

    def _step_diary_generation(self) -> Dict:
        """Step 10: 靈魂日記生成 + 情緒衰減（v2.0 重構版）.

        合併原 _step_soul_nightly 的情緒衰減功能，
        並整合 DiaryStore.generate_daily_summary() 生成每日日記條目。
        """
        result: Dict[str, Any] = {}

        # Part A: 情緒衰減（保留原邏輯）
        soul_dir = self._workspace / "_system" / "soul"
        if soul_dir.exists():
            state_file = soul_dir / "soul_state.json"
            if state_file.exists():
                try:
                    with open(state_file, "r", encoding="utf-8") as fh:
                        state = json.load(fh)
                    emotions = state.get("emotions", {})
                    for key in emotions:
                        if isinstance(emotions[key], (int, float)):
                            emotions[key] = round(
                                emotions[key] * DAILY_DECAY_FACTOR, 4
                            )
                    state["last_nightly"] = datetime.now(TZ_TAIPEI).isoformat()
                    with open(state_file, "w", encoding="utf-8") as fh:
                        json.dump(state, fh, ensure_ascii=False, indent=2)
                    result["emotions_decayed"] = len(emotions)
                except Exception as e:
                    logger.debug(f"[NIGHTLY] emotion decay degraded: {e}")
                    result["emotion_decay_error"] = str(e)

        # Part B: 每日日記生成（v2.0 新增）
        try:
            from museon.agent.soul_ring import DiaryStore
            from museon.core.activity_logger import ActivityLogger
            from datetime import date as _date

            diary_store = DiaryStore(data_dir=str(self._workspace))
            today = _date.today()

            # 收集當日互動統計
            al = ActivityLogger(data_dir=str(self._workspace))
            today_events = al.today_events()
            interaction_count = len(today_events)

            # 收集 Q-Score（從持久化檔案）
            q_path = self._workspace / "_system" / "q_score_history.json"
            q_scores = None
            if q_path.exists():
                try:
                    q_scores = json.loads(q_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # 收集八原語（從 ANIMA_USER）
            primals = None
            anima_path = self._workspace / "anima" / "anima_user.json"
            if anima_path.exists():
                try:
                    anima_data = json.loads(
                        anima_path.read_text(encoding="utf-8")
                    )
                    primals = anima_data.get("eight_primal_energies")
                except Exception:
                    pass

            # 生成亮點（從事件類型統計）
            highlights = []
            if today_events:
                event_types: Dict[str, int] = {}
                for evt in today_events:
                    etype = evt.get("event", "unknown")
                    event_types[etype] = event_types.get(etype, 0) + 1
                top_events = sorted(
                    event_types.items(), key=lambda x: -x[1]
                )[:3]
                highlights = [
                    f"{etype}: {count} 次" for etype, count in top_events
                ]

            # 生成日記條目
            ring = diary_store.generate_daily_summary(
                target_date=today,
                interaction_count=interaction_count,
                q_scores=q_scores,
                primals=primals,
                highlights=highlights,
            )

            result["diary_generated"] = ring is not None
            result["interaction_count"] = interaction_count

        except Exception as e:
            logger.debug(f"[NIGHTLY] diary generation degraded: {e}")
            result["diary_error"] = str(e)

        return result

    # ═══════════════════════════════════════════
    # Step 10.6: SOUL.md 身份驗證
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires SOUL.md with SHA-256 hash at workspace.parent/SOUL.md)
    def _step_soul_identity_check(self) -> Dict:
        """Step 10.6: 驗證 SOUL.md 核心身份 hash 未被篡改."""
        import hashlib
        soul_file = self._workspace.parent / "SOUL.md"
        if not soul_file.exists():
            return {"skipped": "SOUL.md not found"}

        try:
            content = soul_file.read_text(encoding="utf-8")
        except Exception as e:
            return {"error": f"Cannot read SOUL.md: {e}"}

        # 提取嵌入的 hash
        import re as _re
        hash_match = _re.search(r"SHA-256:\s*([a-f0-9]{64})", content)
        if not hash_match:
            return {"warning": "No SHA-256 hash found in SOUL.md"}
        embedded_hash = hash_match.group(1)

        # 提取 CORE_IDENTITY 內容
        core_match = _re.search(
            r"<!-- BEGIN_CORE_IDENTITY -->\s*\n.*?SHA-256:.*?\n(.*?)<!-- END_CORE_IDENTITY -->",
            content, _re.DOTALL,
        )
        if not core_match:
            return {"warning": "Cannot find CORE_IDENTITY block in SOUL.md"}

        core_text = core_match.group(1).strip()
        computed_hash = hashlib.sha256(core_text.encode("utf-8")).hexdigest()

        if computed_hash == embedded_hash:
            return {"status": "verified", "hash": computed_hash[:16] + "..."}

        # CRITICAL: Hash 不符！
        logger.critical(
            f"SOUL.md CORE_IDENTITY hash mismatch! "
            f"embedded={embedded_hash[:16]}... computed={computed_hash[:16]}..."
        )
        if self._event_bus:
            try:
                from museon.core.event_bus import SOUL_IDENTITY_TAMPERED
                self._event_bus.publish(SOUL_IDENTITY_TAMPERED, {
                    "embedded_hash": embedded_hash,
                    "computed_hash": computed_hash,
                    "severity": "CRITICAL",
                })
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {
            "status": "TAMPERED",
            "severity": "CRITICAL",
            "embedded_hash": embedded_hash,
            "computed_hash": computed_hash,
        }

    # ═══════════════════════════════════════════
    # Step 10.5: 30 天年輪回顧
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires workspace.parent/anima/soul_rings.json)
    def _step_ring_review(self) -> Dict:
        """Step 10.5: 每 30 天回顧 Soul Rings，分析模式."""
        review_dir = self._workspace.parent / "anima" / "ring_reviews"
        review_dir.mkdir(parents=True, exist_ok=True)

        # 檢查是否需要回顧（每 30 天一次）
        state_file = review_dir / "_review_state.json"
        last_review = None
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as fh:
                    state = json.load(fh)
                last_review = state.get("last_review")
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        if last_review:
            try:
                last_dt = datetime.fromisoformat(last_review)
                days_since = (datetime.now(TZ_TAIPEI) - last_dt.replace(
                    tzinfo=TZ_TAIPEI if last_dt.tzinfo is None else last_dt.tzinfo
                )).days
                if days_since < 30:
                    return {"skipped": f"last review {days_since} days ago, next in {30 - days_since} days"}
            except (ValueError, TypeError) as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        # 載入最近 30 天的 Soul Rings
        rings_path = self._workspace.parent / "anima" / "soul_rings.json"
        if not rings_path.exists():
            return {"skipped": "no soul_rings.json"}

        try:
            with open(rings_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "soul_rings.json unreadable"}

        rings = data.get("soul_rings", [])
        if not rings:
            return {"skipped": "no rings to review"}

        # 過濾最近 30 天
        cutoff = (datetime.now(TZ_TAIPEI) - timedelta(days=30)).isoformat()
        recent = [r for r in rings if r.get("created_at", "") >= cutoff]

        if not recent:
            return {"skipped": "no recent rings in last 30 days"}

        # 分析模式
        type_counts: Dict[str, int] = {}
        for r in recent:
            rtype = r.get("type", "unknown")
            type_counts[rtype] = type_counts.get(rtype, 0) + 1

        # 生成回顧報告
        review = {
            "review_date": datetime.now(TZ_TAIPEI).isoformat(),
            "period": "30_days",
            "total_rings": len(recent),
            "type_distribution": type_counts,
            "patterns": [],
        }

        # 模式偵測
        if type_counts.get("failure_lesson", 0) >= 3:
            review["patterns"].append({
                "type": "failure_pattern",
                "description": f"重複失敗 {type_counts['failure_lesson']} 次，需關注根因",
                "severity": "high",
            })

        if type_counts.get("cognitive_breakthrough", 0) >= 3:
            review["patterns"].append({
                "type": "growth_trajectory",
                "description": f"連續突破 {type_counts['cognitive_breakthrough']} 次，成長良好",
                "severity": "positive",
            })

        if type_counts.get("value_calibration", 0) >= 2:
            review["patterns"].append({
                "type": "value_shift",
                "description": f"價值校準 {type_counts['value_calibration']} 次，可能需要 L5 偏好更新",
                "severity": "medium",
            })

        # 寫入回顧報告
        out = review_dir / f"{date.today().isoformat()}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(review, fh, ensure_ascii=False, indent=2)

        # 更新回顧狀態
        with open(state_file, "w", encoding="utf-8") as fh:
            json.dump({"last_review": datetime.now(TZ_TAIPEI).isoformat()},
                       fh, ensure_ascii=False, indent=2)

        return {
            "total_rings_reviewed": len(recent),
            "patterns_found": len(review["patterns"]),
            "type_distribution": type_counts,
        }

    # ═══════════════════════════════════════════
    # Step 11: 夢境引擎
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/memory/ directory with L2_ep items)
    def _step_dream_engine(self) -> Dict:
        """Step 11: 離線夢境處理（記憶重組）."""
        dream_dir = self._workspace / "_system" / "dreams"
        dream_dir.mkdir(parents=True, exist_ok=True)

        # 從今日記憶中提取素材
        memory_dir = self._workspace / "_system" / "memory"
        if not memory_dir.exists():
            return {"skipped": "no memory for dreaming"}

        # 收集近期記憶片段
        fragments = []
        for scope in ["shared", "owner"]:
            ep_dir = memory_dir / scope / "L2_ep"
            if not ep_dir.exists():
                continue
            for f in sorted(ep_dir.glob("*.json"))[-10:]:
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    fragments.append(data.get("content", data.get("summary", "")))
                except Exception as e:
                    logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        if not fragments:
            return {"skipped": "no memory fragments"}

        # 夢境 = 記憶片段的隨機重組聯想
        dream = {
            "date": date.today().isoformat(),
            "fragments_used": len(fragments),
            "created_at": datetime.now(TZ_TAIPEI).isoformat(),
        }
        out = dream_dir / f"dream_{date.today().isoformat()}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(dream, fh, ensure_ascii=False, indent=2)

        return {"dream_generated": True, "fragments_used": len(fragments)}

    # ═══════════════════════════════════════════
    # Step 12: 脈搏焦點調整
    # ═══════════════════════════════════════════

    def _step_heartbeat_focus(self) -> Dict:
        """Step 12: 夜間焦點重校."""
        if self._heartbeat_focus:
            if hasattr(self._heartbeat_focus, "nightly_adjust"):
                result = self._heartbeat_focus.nightly_adjust()
                return result if isinstance(result, dict) else {"adjusted": True}
            interval = self._heartbeat_focus.compute_adaptive_interval()
            level = self._heartbeat_focus.focus_level
            return {
                "interval_hours": interval,
                "focus_level": level,
                "beat_count": self._heartbeat_focus.beat_count,
            }
        return {"recalculated": False, "reason": "heartbeat_focus not available"}

    # ═══════════════════════════════════════════
    # Step 13: 好奇心掃描
    # ═══════════════════════════════════════════

    @staticmethod
    def _should_enqueue_question(question: str) -> bool:
        """品質過濾：排除閒聊、指令、過短問題."""
        if len(question.strip()) < 15:
            return False
        low_value = [
            "叫什麼", "是誰", "在嗎", "你好", "早安", "晚安", "謝謝",
            "收到", "了解", "@", "http://", "https://",
        ]
        q_lower = question.lower()
        if any(w in q_lower for w in low_value):
            return False
        return True

    def _step_curiosity_scan(self) -> Dict:
        """Step 13: 提取未解答的好奇問題."""
        import collections
        curiosity_dir = self._workspace / "_system" / "curiosity"
        curiosity_dir.mkdir(parents=True, exist_ok=True)

        queue_file = curiosity_dir / "question_queue.json"
        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
                # 相容兩種格式：{"questions": [...]} 或 [...]
                queue = raw.get("questions", []) if isinstance(raw, dict) else raw
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            queue = []

        # 掃描近期對話中的問句（從 session 檔案 + 每日記憶）
        sessions_dir = self._workspace / "_system" / "sessions"
        memory_dir = self._workspace / "memory"
        new_questions = 0
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        # 已存在問題的去重集合
        existing_qs = {q.get("question", "")[:100] for q in queue}

        # 來源 1: session JSON 檔案（包含完整對話歷史）
        if sessions_dir.exists():
            for f in sessions_dir.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        messages = json.load(fh)
                    if not isinstance(messages, list):
                        continue
                    for msg in messages:
                        if msg.get("role") != "user":
                            continue
                        content = msg.get("content", "")
                        if not isinstance(content, str):
                            continue
                        content = content.strip()
                        if (content.endswith("？") or content.endswith("?")) and len(content) > 5:
                            q_text = content[:200]
                            if q_text[:100] not in existing_qs and self._should_enqueue_question(q_text):
                                queue.append({
                                    "question": q_text,
                                    "source_date": yesterday,
                                    "status": "pending",
                                })
                                existing_qs.add(q_text[:100])
                                new_questions += 1
                except Exception as e:
                    logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        # 來源 2: 每日記憶 markdown（備援）
        if memory_dir.exists():
            yesterday_md = memory_dir / f"{yesterday}.md"
            if yesterday_md.exists():
                try:
                    text = yesterday_md.read_text(encoding="utf-8")
                    for line in text.split("\n"):
                        line = line.strip().lstrip("- ").strip()
                        if (line.endswith("？") or line.endswith("?")) and len(line) > 5:
                            q_text = line[:200]
                            if q_text[:100] not in existing_qs and self._should_enqueue_question(q_text):
                                queue.append({
                                    "question": q_text,
                                    "source_date": yesterday,
                                    "status": "pending",
                                })
                                existing_qs.add(q_text[:100])
                                new_questions += 1
                except Exception as e:
                    logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        # ── 四個新方向注入來源 ──────────────────────────────────

        # 來源 A: 原語輪替（每週一個八原語維度）
        try:
            primals = ["感知", "直覺", "意志", "情感", "理性", "創造", "連結", "超越"]
            week_num = date.today().isocalendar()[1]
            primal = primals[week_num % 8]
            primal_q = (
                f"關於「{primal}」這個能量維度，最新的心理學或認知科學研究有什麼新發現？"
                f"如何應用到 AI Agent 的人格設計？"
            )
            if primal_q[:100] not in existing_qs:
                queue.append({
                    "question": primal_q,
                    "source_date": yesterday,
                    "status": "pending",
                    "source": "primal_rotation",
                    "priority": 2,
                })
                existing_qs.add(primal_q[:100])
                new_questions += 1
        except Exception as e:
            logger.debug(f"[NIGHTLY] primal_rotation failed (degraded): {e}")

        # 來源 B: 使用者互動模式（最近 7 天高頻主題）
        try:
            activity_log = self._workspace / "activity_log.jsonl"
            if activity_log.exists():
                topic_counter: collections.Counter = collections.Counter()
                cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                for line in activity_log.read_text(encoding="utf-8").splitlines()[-500:]:
                    try:
                        entry = json.loads(line)
                        if entry.get("timestamp", "") >= cutoff:
                            content = entry.get("user_content", entry.get("content", ""))
                            if content and len(content) > 20:
                                topic_counter[content[:30]] += 1
                    except (json.JSONDecodeError, KeyError):
                        continue
                for topic, count in topic_counter.most_common(3):
                    if count >= 2:
                        user_q = (
                            f"使用者最近反覆討論「{topic}」相關議題，"
                            f"有什麼最新的專業知識或最佳實踐可以幫助他們？"
                        )
                        if user_q[:100] not in existing_qs:
                            queue.append({
                                "question": user_q,
                                "source_date": yesterday,
                                "status": "pending",
                                "source": "user_interaction_pattern",
                                "priority": 1,
                            })
                            existing_qs.add(user_q[:100])
                            new_questions += 1
        except Exception as e:
            logger.debug(f"[NIGHTLY] user_interaction_pattern failed (degraded): {e}")

        # 來源 C: Skill 使用熱力圖（最常用 Skill 找最佳實踐）
        try:
            usage_path = self._workspace / "_system" / "skill_usage_stats.json"
            if usage_path.exists():
                usage = json.loads(usage_path.read_text(encoding="utf-8"))
                if isinstance(usage, dict):
                    sorted_skills = sorted(usage.items(), key=lambda x: x[1], reverse=True)
                    if sorted_skills:
                        top_skill = sorted_skills[0][0]
                        skill_q = (
                            f"「{top_skill}」是目前最常被使用的 Skill，"
                            f"這個領域有什麼最新的方法論或工具可以讓它更強？"
                        )
                        if skill_q[:100] not in existing_qs:
                            queue.append({
                                "question": skill_q,
                                "source_date": yesterday,
                                "status": "pending",
                                "source": "skill_heatmap",
                                "priority": 2,
                            })
                            existing_qs.add(skill_q[:100])
                            new_questions += 1
        except Exception as e:
            logger.debug(f"[NIGHTLY] skill_heatmap failed (degraded): {e}")

        # 來源 D: 外部生態掃描（每週一次，週一執行）
        try:
            if date.today().weekday() == 0:  # Monday
                eco_q = (
                    "2026 年最新的 AI Agent 工具和 Skill 生態系有什麼重要更新？"
                    "MCP、Agent Skills、A2A 協議有什麼新發展？"
                )
                if eco_q[:100] not in existing_qs:
                    queue.append({
                        "question": eco_q,
                        "source_date": yesterday,
                        "status": "pending",
                        "source": "ecosystem_scan",
                        "priority": 3,
                    })
                    existing_qs.add(eco_q[:100])
                    new_questions += 1
        except Exception as e:
            logger.debug(f"[NIGHTLY] ecosystem_scan failed (degraded): {e}")

        # 保留最近 50 個問題
        queue = queue[-50:]
        with open(queue_file, "w", encoding="utf-8") as fh:
            json.dump(queue, fh, ensure_ascii=False, indent=2)

        return {"new_questions": new_questions, "queue_size": len(queue)}

    # ═══════════════════════════════════════════
    # Step 13.5: 好奇問題研究路由
    # ═══════════════════════════════════════════

    def _step_curiosity_research(self) -> Dict:
        """Step 13.5: 將 pending 好奇問題送入 ResearchEngine 研究."""
        try:
            from museon.nightly.curiosity_router import CuriosityRouter
            from museon.research.research_engine import ResearchEngine

            research_engine = ResearchEngine(brain=self._brain)
            # 取得 PulseDB（用於記錄探索結果）
            _pulse_db = None
            try:
                from museon.pulse.pulse_db import get_pulse_db
                _pulse_db = get_pulse_db(self._workspace)
            except Exception as e:
                logger.debug(f"[NIGHTLY] pulse failed (degraded): {e}")
            router = CuriosityRouter(
                workspace=self._workspace,
                research_engine=research_engine,
                event_bus=self._event_bus,
                pulse_db=_pulse_db,
            )

            results = _run_async_safe(router.process_queue(max_items=None))

            valuable = sum(1 for r in results if r.get("is_valuable"))
            return {
                "researched": len(results),
                "valuable": valuable,
            }
        except Exception as e:
            logger.warning(f"Step 13.5 curiosity research failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 13.6: 外向觸發掃描
    # ═══════════════════════════════════════════

    def _step_outward_trigger_scan(self) -> Dict:
        """Step 13.6: 掃描外向搜尋觸發信號（純 CPU, 0 token）."""
        try:
            from museon.evolution.outward_trigger import OutwardTrigger

            trigger = OutwardTrigger(
                workspace=self._workspace,
                event_bus=self._event_bus,
            )
            result = trigger.scan()
            return {
                "triggered": result.get("triggered", 0),
                "events": result.get("events", []),
            }
        except Exception as e:
            logger.warning(f"Step 13.6 outward trigger scan failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 13.7: 外向研究
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires IntentionRadar to produce pending outward queries)
    def _step_outward_research(self) -> Dict:
        """Step 13.7: 執行外向搜尋計畫（ResearchEngine, ≤$0.15）."""
        try:
            import asyncio
            from museon.evolution.intention_radar import IntentionRadar
            from museon.evolution.digest_engine import DigestEngine
            from museon.research.research_engine import ResearchEngine

            radar = IntentionRadar(
                workspace=self._workspace,
                event_bus=self._event_bus,
            )
            digest = DigestEngine(
                workspace=self._workspace,
                event_bus=self._event_bus,
            )
            research_engine = ResearchEngine(
                brain=self._brain,
                event_bus=self._event_bus,
            )

            plan = radar.load_pending_plan()
            if not plan:
                return {"skipped": "no pending outward queries"}

            researched = 0
            ingested = 0

            for query_item in plan[:3]:  # 每次最多執行 3 條
                if query_item.get("executed"):
                    continue

                query = query_item.get("query", "")
                context_type = query_item.get("context_type", "outward_service")
                max_rounds = query_item.get("max_rounds", 2)

                # 執行研究
                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(
                        research_engine.research(
                            query=query,
                            context_type=context_type,
                            max_rounds=max_rounds,
                        )
                    )
                finally:
                    loop.close()

                radar.mark_executed(query_item)
                researched += 1

                # 有價值的結果送入消化引擎
                if result.is_valuable and result.filtered_summary:
                    qid = digest.ingest(
                        research_result={
                            "filtered_summary": result.filtered_summary,
                            "source_urls": [h.url for h in result.hits if h.url],
                        },
                        search_context={
                            "query": query,
                            "track": query_item.get("track", "service"),
                            "trigger_type": query_item.get("trigger_type", ""),
                        },
                    )
                    if qid:
                        ingested += 1

            radar.save_plan(plan)

            return {
                "researched": researched,
                "ingested": ingested,
                "pending_remaining": len([q for q in plan if not q.get("executed")]),
            }
        except Exception as e:
            logger.warning(f"Step 13.7 outward research failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 13.8: 消化生命週期
    # ═══════════════════════════════════════════

    def _step_digest_lifecycle(self) -> Dict:
        """Step 13.8: 隔離區生命週期掃描 — 晉升/淘汰/TTL（純 CPU, 0 token）."""
        try:
            from museon.evolution.digest_engine import DigestEngine

            digest = DigestEngine(
                workspace=self._workspace,
                event_bus=self._event_bus,
            )
            result = digest.lifecycle_scan()
            return result
        except Exception as e:
            logger.warning(f"Step 13.8 digest lifecycle failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 14: 技能生命週期
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/memory/shared/L3_procedural/ with .json skill files)
    def _step_skill_lifecycle(self) -> Dict:
        """Step 14: 自動升降級."""
        skills_dir = self._workspace / "_system" / "skills"
        if not skills_dir.exists():
            return {"skipped": "no skills directory"}

        promoted = 0
        deprecated = 0
        archived = 0
        today = date.today()

        for f in skills_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    skill = json.load(fh)

                status = skill.get("status", "experimental")
                success_count = skill.get("success_count", 0)
                fail_count = skill.get("fail_count", 0)
                total_uses = success_count + fail_count
                last_used = skill.get("last_used")

                changed = False

                # experimental → stable: 3+ 次成功
                if status == "experimental" and success_count >= SKILL_PROMOTE_MIN_SUCCESS:
                    skill["status"] = "stable"
                    promoted += 1
                    changed = True

                # stable → deprecated: > 50% 失敗
                elif status == "stable" and total_uses > 0:
                    if fail_count / total_uses > SKILL_DEPRECATE_FAIL_RATE:
                        skill["status"] = "deprecated"
                        deprecated += 1
                        changed = True

                # deprecated → archived: 30 天無使用
                elif status == "deprecated" and last_used:
                    try:
                        last = date.fromisoformat(last_used[:10])
                        if (today - last).days >= SKILL_ARCHIVE_INACTIVE_DAYS:
                            skill["status"] = "archived"
                            archived += 1
                            changed = True
                    except Exception as e:
                        logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

                if changed:
                    with open(f, "w", encoding="utf-8") as fh:
                        json.dump(skill, fh, ensure_ascii=False, indent=2)

            except Exception as e:
                logger.debug(f"[NIGHTLY] JSON parse failed (degraded): {e}")

        # Phase B: per-skill _meta.json（SkillManager 整合）
        phase_b = {"promoted": 0, "deprecated": 0, "archived": 0}
        try:
            from museon.core.skill_manager import SkillManager
            manager = SkillManager(workspace=self._workspace)
            phase_b = manager.nightly_maintenance()
        except Exception as e:
            phase_b["error"] = str(e)

        return {
            "promoted": promoted + phase_b.get("promoted", 0),
            "deprecated": deprecated + phase_b.get("deprecated", 0),
            "archived": archived + phase_b.get("archived", 0),
        }

    # ═══════════════════════════════════════════
    # Step 15: 部門健康掃描
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/departments/ directory with dept .json files)
    def _step_dept_health(self) -> Dict:
        """Step 15: 掃描部門健康度."""
        dept_dir = self._workspace / "_system" / "departments"
        if not dept_dir.exists():
            return {"skipped": "no departments directory"}

        departments = []
        for f in dept_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    dept = json.load(fh)
                dept["_file"] = f.name
                departments.append(dept)
            except Exception as e:
                logger.debug(f"[NIGHTLY] department failed (degraded): {e}")

        if not departments:
            return {"skipped": "no departments found"}

        # 計算每個部門健康分數
        results = []
        for dept in departments:
            score = dept.get("health_score", 0.5)
            weaknesses = dept.get("weaknesses", [])
            results.append({
                "dept": dept.get("name", dept["_file"]),
                "score": score,
                "weaknesses": weaknesses,
            })

        # 保存快照
        snapshot_dir = self._workspace / "_system" / "health_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "date": date.today().isoformat(),
            "departments": results,
        }
        out = snapshot_dir / f"health_{date.today().isoformat()}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, ensure_ascii=False, indent=2)

        # 找出最弱的 2 個部門
        results.sort(key=lambda x: x["score"])
        weakest = results[:2]

        return {"departments_scanned": len(results), "weakest": weakest}

    # ═══════════════════════════════════════════
    # Step 16: Claude 精煉鍛造
    # ═══════════════════════════════════════════

    # DORMANT: removed from _FULL_STEPS, re-enable when data source exists
    # (requires data/_system/memory/shared/L3_procedural/ with .json skill files)
    def _step_claude_skill_forge(self) -> Dict:
        """Step 16: AI 輔助技能精煉（唯一 LLM 步驟）."""
        if not self._brain:
            return {"skipped": "brain not available"}

        l3_dir = self._workspace / "_system" / "memory" / "shared" / "L3_procedural"
        if not l3_dir.exists():
            return {"skipped": "no L3_procedural skills to refine"}

        skills = list(l3_dir.glob("*.json"))
        if not skills:
            return {"skipped": "no skills to refine"}

        # 只精煉最新的（控制 Token 成本）
        refined = 0
        for sf in skills[-3:]:  # 最多精煉 3 個
            try:
                with open(sf, "r", encoding="utf-8") as fh:
                    skill = json.load(fh)
                if not skill.get("refined"):
                    skill["refined"] = True
                    skill["refined_at"] = datetime.now(TZ_TAIPEI).isoformat()
                    with open(sf, "w", encoding="utf-8") as fh:
                        json.dump(skill, fh, ensure_ascii=False, indent=2)
                    refined += 1
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        # Phase B: 嘗試 LLM 精煉（透過 LLMAdapter，MAX 訂閱方案）
        llm_refined = 0
        try:
            import asyncio
            adapter = getattr(self._brain, "_llm_adapter", None)
            if adapter and refined > 0:
                for sf in skills[-3:]:
                    try:
                        with open(sf, "r", encoding="utf-8") as fh:
                            skill = json.load(fh)
                        if skill.get("refined") and not skill.get("llm_refined"):
                            snippet = json.dumps(skill, ensure_ascii=False)[:500]
                            prompt = (
                                "你是 MUSEON 技能精煉專家。請用一段話"
                                "（不超過 100 字）總結這個技能的核心能力：\n"
                                f"{snippet}"
                            )
                            resp = _run_async_safe(
                                adapter.call(
                                    system_prompt="你是技能精煉專家。",
                                    messages=[{"role": "user", "content": prompt}],
                                    model="sonnet",
                                    max_tokens=200,
                                ),
                                timeout=30,
                            )
                            if resp and resp.text:
                                skill["llm_summary"] = resp.text[:200]
                                skill["llm_refined"] = True
                                skill["llm_refined_at"] = datetime.now(TZ_TAIPEI).isoformat()
                                with open(sf, "w", encoding="utf-8") as fh:
                                    json.dump(skill, fh, ensure_ascii=False, indent=2)
                                llm_refined += 1
                    except Exception as e:
                        logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")
        except Exception as e:
            logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {
            "refined": refined,
            "llm_refined": llm_refined,
            "total_l3_skills": len(skills),
        }

    # ═══════════════════════════════════════════
    # Step 17: Tool Discovery（每日 5am 由 cron 獨立觸發，
    #          此步驟在凌晨整合管線中做工具健康檢查）
    # ═══════════════════════════════════════════

    def _step_tool_discovery(self) -> Dict:
        """Step 17: 工具兵器庫健康檢查 + 自動偵測.

        真正的工具發現（SearXNG 搜尋）由 cron 5am 獨立觸發。
        此步驟只做：
        1. 自動偵測已安裝工具
        2. 健康檢查所有已啟用工具
        3. 讀取最近發現結果
        """
        try:
            from museon.tools.tool_registry import ToolRegistry
            from museon.tools.tool_discovery import ToolDiscovery

            registry = ToolRegistry(workspace=self._workspace)
            discovery = ToolDiscovery(workspace=self._workspace)

            # Phase A: 自動偵測
            detected = registry.auto_detect()

            # Phase B: 健康檢查
            health = registry.check_all_health()
            healthy_count = sum(
                1 for r in health.values() if r.get("healthy")
            )

            # Phase C: 最近發現
            latest = discovery.get_latest_discoveries()

            return {
                "detected": len(detected),
                "healthy": healthy_count,
                "total_tools": len(health),
                "last_discovery": latest.get("timestamp", ""),
                "recommended": len(latest.get("recommended", [])),
            }
        except Exception as e:
            return {"error": str(e)}

    def _step_daily_summary(self) -> Dict:
        """Step 18: 每日摘要生成 — 從 activity log + memory 頻道產生一則快照.

        產出儲存到 data/daily_summaries/YYYY-MM-DD.json
        """
        try:
            from datetime import date as _date
            from museon.core.activity_logger import ActivityLogger

            today = _date.today().isoformat()
            summary_dir = self._workspace / "daily_summaries"
            summary_dir.mkdir(parents=True, exist_ok=True)
            summary_path = summary_dir / f"{today}.json"

            # 如果今天已經有摘要就跳過
            if summary_path.exists():
                return {"skipped": True, "date": today, "reason": "already_exists"}

            # 收集活動日誌
            al = ActivityLogger(data_dir=str(self._workspace))
            today_events = al.today_events()

            # 收集記憶頻道內容
            memory_dir = self._workspace / "memory"
            now = _date.today()
            date_path = memory_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
            channels = {}
            if date_path.exists():
                for md_file in date_path.glob("*.md"):
                    channel = md_file.stem
                    content = md_file.read_text(encoding="utf-8").strip()
                    if content:
                        channels[channel] = content[:2000]  # 截取前 2000 字

            # 組裝摘要
            event_summary = []
            for evt in today_events[:50]:
                event_summary.append({
                    "ts": evt.get("ts", ""),
                    "event": evt.get("event", ""),
                    "source": evt.get("source", ""),
                })

            summary = {
                "date": today,
                "generated_at": datetime.now().isoformat(),
                "event_count": len(today_events),
                "events_digest": event_summary,
                "memory_channels": list(channels.keys()),
                "memory_excerpts": channels,
                "narrative": self._generate_narrative(today_events, channels),
            }

            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {"date": today, "event_count": len(today_events), "channels": len(channels)}

        except Exception as e:
            return {"error": str(e)}

    def _generate_narrative(self, events: list, channels: dict) -> str:
        """Generate a brief narrative summary from events + memory channels.

        For now uses a simple template. Can be upgraded to LLM later.
        """
        lines = []
        if events:
            event_types = {}
            for evt in events:
                etype = evt.get("event", "unknown")
                event_types[etype] = event_types.get(etype, 0) + 1
            top = sorted(event_types.items(), key=lambda x: -x[1])[:5]
            lines.append(f"今日共 {len(events)} 個活動事件。")
            for etype, count in top:
                lines.append(f"  - {etype}: {count} 次")

        if channels:
            lines.append(f"記錄了 {len(channels)} 個記憶頻道。")
            for ch in channels:
                excerpt = channels[ch][:80].replace("\n", " ")
                lines.append(f"  - {ch}: {excerpt}...")

        if not lines:
            lines.append("今日尚無顯著活動。")

        return "\n".join(lines)

    def _step_federation_upload(self) -> Dict:
        """Federation 未實作，保留 node 模式進入點供未來擴充."""
        return {"skipped": "federation not implemented"}

    # ═══════════════════════════════════════════
    # Step 0: Token 預算日結算
    # ═══════════════════════════════════════════

    def _step_budget_settlement(self) -> Dict:
        """Step 0: 每日呼叫統計摘要（MAX 訂閱方案 — 無 per-token 計費）.

        v3: 改為記錄每日呼叫次數、模型分布，不再做 token 預算結算。
        """
        # 嘗試從 BudgetMonitor 取得統計（僅記錄用途）
        try:
            if hasattr(self, '_brain') and self._brain and hasattr(self._brain, 'budget_monitor'):
                bm = self._brain.budget_monitor
                if bm:
                    stats = bm.get_usage_stats()
                    return {
                        "mode": "max_subscription",
                        "daily_calls": sum(
                            stats.get("models", {}).get(m, {}).get("calls", 0)
                            for m in ("sonnet", "haiku")
                        ),
                        "model_distribution": {
                            m: stats.get("models", {}).get(m, {}).get("calls", 0)
                            for m in ("sonnet", "haiku")
                        },
                        "daily_tokens": stats.get("used", 0),
                    }
        except Exception as e:
            logger.warning(f"Budget stats read failed: {e}")

        return {"mode": "max_subscription", "skipped": "no_budget_monitor"}

    # ═══════════════════════════════════════════
    # Step 18.5: 客戶互動萃取 — dispatch/completed → external_users + clients
    # ═══════════════════════════════════════════

    def _step_client_profile_update(self) -> Dict:
        """Step 18.5: 從 dispatch/completed 萃取客戶互動摘要.

        管線接通：
        - dispatch/completed/*.json（最完整的對話紀錄）→ 讀取
        - external_users/{user_id}.json → 更新 context_summary
        - group_context.db clients 表 → 更新 personality_notes
        """
        import json
        import glob
        from datetime import datetime, timedelta

        stats = {"dispatches_scanned": 0, "profiles_updated": 0, "clients_updated": 0}

        dispatch_dir = self._workspace / "dispatch" / "completed"
        if not dispatch_dir.exists():
            return {"skipped": "no dispatch/completed directory"}

        # 只掃最近 3 天
        cutoff = datetime.now() - timedelta(days=3)

        # 收集每個 session 的互動摘要
        session_interactions: dict = {}  # session_id → [user_request snippets]

        for dfile in sorted(dispatch_dir.glob("*.json")):
            stats["dispatches_scanned"] += 1
            try:
                data = json.loads(dfile.read_text(encoding="utf-8"))
                created = data.get("created_at", "")
                if created:
                    try:
                        dt = datetime.fromisoformat(created)
                        if dt < cutoff:
                            continue
                    except Exception:
                        pass

                session_id = data.get("session_id", "")
                user_req = data.get("user_request", "")[:500]
                if session_id and user_req:
                    session_interactions.setdefault(session_id, []).append(user_req)

            except Exception:
                continue

        # 從 group_context.db 的 clients 表讀取現有用戶
        # 用 dispatch 中的 session_id 反查 group_id → 找到互動的用戶
        try:
            from museon.governance.group_context import get_group_context_store
            gc_store = get_group_context_store()
            conn = gc_store._get_conn()

            # 取最近 3 天活躍的 clients
            active_clients = conn.execute("""
                SELECT DISTINCT c.user_id, c.display_name, c.personality_notes
                FROM clients c
                JOIN messages m ON c.user_id = m.user_id
                WHERE m.created_at > datetime('now', '-3 days')
                  AND c.user_id != 'bot'
                ORDER BY c.last_seen DESC
                LIMIT 20
            """).fetchall()

            for client in active_clients:
                user_id = client[0]
                display_name = client[1] or ""
                existing_notes = client[2] or ""

                # 取此用戶最近的訊息做互動摘要
                recent_msgs = conn.execute("""
                    SELECT text FROM messages
                    WHERE user_id = ? AND created_at > datetime('now', '-7 days')
                    ORDER BY created_at DESC LIMIT 20
                """, (user_id,)).fetchall()

                if not recent_msgs:
                    continue

                # 簡單摘要：取最近訊息的關鍵詞
                msg_texts = [m[0] for m in recent_msgs if m[0]]
                topics = set()
                for t in msg_texts[:10]:
                    # 取每則訊息的前 30 字作為話題
                    snippet = t[:30].strip()
                    if snippet and len(snippet) > 3:
                        topics.add(snippet)

                if topics:
                    topic_summary = "、".join(list(topics)[:5])
                    new_notes = f"[{datetime.now().strftime('%m/%d')}] 近期話題：{topic_summary}"

                    # 追加而非覆蓋（保留歷史，最多 500 字）
                    if existing_notes:
                        combined = f"{new_notes}\n{existing_notes}"[:500]
                    else:
                        combined = new_notes[:500]

                    conn.execute(
                        "UPDATE clients SET personality_notes = ? WHERE user_id = ?",
                        (combined, user_id),
                    )
                    stats["clients_updated"] += 1

            conn.commit()
        except Exception as e:
            logger.warning(f"[NIGHTLY] Client profile update failed: {e}")

        # 更新 external_users 的 context_summary（如果是空的）
        try:
            from museon.governance.multi_tenant import ExternalAnimaManager
            ext_mgr = ExternalAnimaManager(self._workspace)
            for p in ext_mgr.users_dir.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if data.get("context_summary"):
                        continue  # 已有摘要，跳過
                    user_id = data.get("user_id", p.stem)
                    display_name = data.get("display_name", "")
                    if not display_name:
                        continue

                    # 從 group_context.db 取此用戶的訊息
                    recent = gc_store._get_conn().execute("""
                        SELECT text FROM messages
                        WHERE user_id = ? ORDER BY created_at DESC LIMIT 10
                    """, (user_id,)).fetchall()

                    if recent:
                        snippets = [r[0][:50] for r in recent if r[0]][:5]
                        if snippets:
                            data["context_summary"] = f"{display_name} 的近期話題：{'；'.join(snippets)}"
                            ext_mgr.save(user_id, data)
                            stats["profiles_updated"] += 1
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"[NIGHTLY] External user update failed: {e}")

        if stats["clients_updated"] > 0 or stats["profiles_updated"] > 0:
            logger.info(
                f"[NIGHTLY] Client profile update: clients={stats['clients_updated']}, "
                f"external_users={stats['profiles_updated']}"
            )

        return stats

    # ═══════════════════════════════════════════
    # Step 18.7: 六層系統健康檢查
    # ═══════════════════════════════════════════

    def _step_system_health_audit(self) -> Dict:
        """Step 18.7: 全系統六層健康檢查.

        先嘗試讀取快取（< 2 小時內的 shared_board.json），避免重複 subprocess。
        快取不新鮮或不存在時，fallback 重跑 full_system_audit。
        如果有 CRITICAL/HIGH 問題，記錄到 shared_board 供 MuseDoctor 巡邏時處理。
        """
        import time

        # ── 嘗試讀取快取 ──
        cache_dir = self._workspace / "_system" / "doctor"
        shared_board_path = cache_dir / "shared_board.json"
        _CACHE_TTL = 2 * 3600  # 2 小時

        if shared_board_path.exists():
            try:
                cache_mtime = shared_board_path.stat().st_mtime
                if (time.time() - cache_mtime) < _CACHE_TTL:
                    with open(shared_board_path, encoding="utf-8") as f:
                        board = json.load(f)
                    nightly_entry = board.get("nightly") or {}
                    summary = nightly_entry.get("summary", "")
                    # 快取有效：直接返回摘要，跳過重跑
                    logger.info(f"[NIGHTLY 18.7] Using cached audit (age < 2h): {summary}")
                    return {"cached": True, "summary": summary}
            except Exception as cache_err:
                logger.debug(f"[NIGHTLY 18.7] Cache read failed, will re-run audit: {cache_err}")

        # ── Fallback：重跑 full_system_audit ──
        try:
            import subprocess
            import sys
            script = self._workspace.parent / "scripts" / "full_system_audit.py"
            if not script.exists():
                # 嘗試相對路徑
                script = Path(__file__).resolve().parent.parent.parent.parent / "scripts" / "full_system_audit.py"
            if not script.exists():
                return {"skipped": "full_system_audit.py not found"}

            r = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, timeout=60,
                cwd=str(script.parent.parent),
            )
            output = r.stdout

            # 解析結果
            import re
            health_match = re.search(r"系統狀態:\s*\x1b\[\d+m(\w+)", output)
            health = health_match.group(1) if health_match else "UNKNOWN"

            pass_match = re.search(r"通過:\s*\x1b\[\d+m(\d+)", output)
            fail_match = re.search(r"失敗:\s*\x1b\[\d+m(\d+)", output)
            warn_match = re.search(r"警告:\s*\x1b\[\d+m(\d+)", output)

            stats = {
                "health": health,
                "pass": int(pass_match.group(1)) if pass_match else 0,
                "fail": int(fail_match.group(1)) if fail_match else 0,
                "warn": int(warn_match.group(1)) if warn_match else 0,
            }

            if health not in ("HEALTHY",):
                logger.warning(f"[NIGHTLY] System health: {health} (fail={stats['fail']}, warn={stats['warn']})")

            return stats
        except Exception as e:
            logger.warning(f"[NIGHTLY] System health audit failed: {e}")
            return {"skipped": str(e)}

    # ═══════════════════════════════════════════
    # Step 18.6: Ares 橋接同步
    # ═══════════════════════════════════════════

    def _step_ares_bridge_sync(self) -> Dict:
        """Step 18.6: 將 external_users 同步到 Ares ProfileStore.

        接在 Step 18.5 之後——18.5 更新 external_users，18.6 橋接到 Ares。
        """
        try:
            from museon.athena.profile_store import ProfileStore
            from museon.athena.external_bridge import ExternalBridge

            store = ProfileStore(self._workspace)
            ext_dir = self._workspace / "_system" / "external_users"
            if not ext_dir.exists():
                ext_dir = self._workspace / "data" / "_system" / "external_users"
            if not ext_dir.exists():
                return {"skipped": "external_users directory not found"}

            bridge = ExternalBridge(store, ext_dir)
            stats = bridge.sync_all()
            if stats["created"] > 0 or stats["updated"] > 0:
                logger.info(
                    f"[NIGHTLY] Ares bridge sync: created={stats['created']}, "
                    f"updated={stats['updated']}, errors={stats['errors']}"
                )

            # ── 溫度自動衰減 ──
            try:
                _ps = ProfileStore(self._workspace)
                _index = _ps.list_all()
                _decay_count = 0
                _now = datetime.now()
                for _pid, _entry in _index.items():
                    _profile = _ps.load(_pid)
                    if not _profile:
                        continue
                    _temp = _profile.get("temperature", {})
                    _current = _temp.get("level", "new")
                    # 只衰減 hot 和 warm，cold 和 new 不動
                    if _current not in ("hot", "warm"):
                        continue
                    _last = _profile.get("L4_interactions", {}).get("last_interaction")
                    if not _last:
                        continue
                    try:
                        _days = (_now - datetime.fromisoformat(_last)).days
                    except Exception:
                        continue
                    # 衰減規則：hot → warm (14天), warm → cold (30天)
                    _new_level = _current
                    if _current == "hot" and _days > 14:
                        _new_level = "warm"
                    elif _current == "warm" and _days > 30:
                        _new_level = "cold"
                    if _new_level != _current:
                        _profile["temperature"] = {
                            "level": _new_level,
                            "trend": "falling",
                            "last_updated": _now.isoformat(),
                        }
                        _ps._save_profile(_profile)
                        _ps._update_index_entry(_profile)
                        _decay_count += 1
                        logger.info(
                            f"[NIGHTLY] Temperature decay: {_entry.get('name', _pid)} "
                            f"{_current} → {_new_level}"
                        )
                if _decay_count > 0:
                    logger.info(f"[NIGHTLY] Temperature decay: {_decay_count} profiles updated")
                stats["temperature_decay"] = _decay_count
            except Exception as e:
                logger.warning(f"[NIGHTLY] Temperature decay failed: {e}")

            # ── 自動建立 alias（從 ExternalAnima display_name）──
            try:
                from museon.governance.group_context import GroupContextStore
                _gcs = GroupContextStore(self.data_dir)
                _ext_map = bridge._load_map()  # {telegram_uid: ares_profile_id}
                _alias_count = 0
                for _tg_uid, _ares_pid in _ext_map.items():
                    # 讀 ExternalAnima 取 display_name
                    _ext_path = bridge.ext_dir / f"{_tg_uid}.json"
                    if not _ext_path.exists():
                        continue
                    try:
                        _ext_data = json.loads(_ext_path.read_text(encoding="utf-8"))
                        _display_name = _ext_data.get("display_name", "")
                        if not _display_name or _display_name.startswith("User_"):
                            continue
                        # 建 display_name → ares_profile alias
                        _gcs.add_alias(_display_name, _ares_pid, "ares_profile", "nightly_auto")
                        # 建 display_name → telegram_uid alias
                        _gcs.add_alias(_display_name, _tg_uid, "telegram_uid", "nightly_auto")
                        _alias_count += 1
                    except Exception:
                        continue
                if _alias_count > 0:
                    logger.info(f"[NIGHTLY] Auto-alias: {_alias_count} names synced")
                stats["auto_aliases"] = _alias_count
            except Exception as e:
                logger.warning(f"[NIGHTLY] Auto-alias failed: {e}")

            # ── 從群組名稱建立 alias ──
            try:
                _group_alias_count = 0
                _owner_ids = {"6969045906", "boss", "bot"}  # Owner + Bot 的 UID
                conn = _gcs._get_conn()
                groups = conn.execute("SELECT group_id, title FROM groups").fetchall()
                for _grp in groups:
                    _title = _grp[1] or ""
                    # 解析 "Museon x 客戶名" 或 "MUSEON 測試 x 客戶名" pattern
                    import re as _re
                    _match = _re.search(r'museon\s*(?:測試\s*)?x\s+(.+)', _title, _re.IGNORECASE)
                    if not _match:
                        continue
                    _client_name = _match.group(1).strip()
                    if not _client_name:
                        continue
                    # 找該群組的非 Owner 成員
                    _members = conn.execute(
                        "SELECT user_id FROM group_members WHERE group_id = ?",
                        (_grp[0],),
                    ).fetchall()
                    for _mem in _members:
                        _uid = str(_mem[0])
                        if _uid in _owner_ids:
                            continue
                        # 建 alias: 群組名中的客戶名 → 該成員
                        _gcs.add_alias(_client_name, _uid, "telegram_uid", "nightly_group_name")
                        # 如果有 ares profile 映射，也建
                        _ares_pid = _ext_map.get(_uid)
                        if _ares_pid:
                            _gcs.add_alias(_client_name, _ares_pid, "ares_profile", "nightly_group_name")
                        _group_alias_count += 1
                if _group_alias_count > 0:
                    logger.info(f"[NIGHTLY] Group-name alias: {_group_alias_count} names synced")
                stats["group_name_aliases"] = _group_alias_count
            except Exception as e:
                logger.warning(f"[NIGHTLY] Group-name alias failed: {e}")

            # ── 重複 profile 偵測 ──
            try:
                _index = _ps.list_all() if '_ps' in dir() else ProfileStore(self._workspace).list_all()
                _name_groups: dict[str, list[str]] = {}
                for _pid, _entry in _index.items():
                    _name = (_entry.get("name") or "").strip()
                    if _name:
                        _name_groups.setdefault(_name, []).append(_pid)
                _duplicates = {n: pids for n, pids in _name_groups.items() if len(pids) > 1}
                if _duplicates:
                    _dup_summary = "; ".join(f"{n}({len(pids)})" for n, pids in _duplicates.items())
                    logger.warning(f"[NIGHTLY] Duplicate profiles detected: {_dup_summary}")
                    # 寫入 pending_signals 供推播
                    try:
                        _signals_path = self.data_dir / "_system" / "ares" / "pending_signals.json"
                        _signals = json.loads(_signals_path.read_text(encoding="utf-8")) if _signals_path.exists() else {"alerts": []}
                        if isinstance(_signals, list):
                            _signals = {"alerts": []}  # 舊格式相容：捨棄 list 重建 dict
                        # 避免重複 alert（每天只發一次）
                        _today = datetime.now().strftime("%Y-%m-%d")
                        _existing_dup_alerts = [a for a in _signals.get("alerts", []) if a.get("type") == "duplicate_profiles" and a.get("date") == _today]
                        if not _existing_dup_alerts:
                            _signals.setdefault("alerts", []).append({
                                "type": "duplicate_profiles",
                                "date": _today,
                                "summary": f"偵測到重複人物檔案：{_dup_summary}",
                                "details": {n: pids for n, pids in _duplicates.items()},
                                "action": "建議使用者確認是否為同一人並合併",
                            })
                            _signals_path.parent.mkdir(parents=True, exist_ok=True)
                            _tmp = _signals_path.with_suffix(".tmp")
                            _tmp.write_text(json.dumps(_signals, ensure_ascii=False, indent=2), encoding="utf-8")
                            _tmp.rename(_signals_path)
                    except Exception as _se:
                        logger.debug(f"[NIGHTLY] Duplicate alert write failed: {_se}")
                stats["duplicate_profiles"] = len(_duplicates) if '_duplicates' in dir() else 0
            except Exception as e:
                logger.warning(f"[NIGHTLY] Duplicate detection failed: {e}")

            return stats
        except Exception as e:
            logger.warning(f"[NIGHTLY] Ares bridge sync failed: {e}")
            return {"skipped": str(e)}

    # ═══════════════════════════════════════════
    # Step 0.1: 足跡清理
    # ═══════════════════════════════════════════

    def _step_footprint_cleanup(self) -> Dict:
        """Step 0.1: 足跡清理 — L1 30天 / L2 90天."""
        try:
            from museon.governance.footprint import FootprintStore
            store = FootprintStore(data_dir=self._workspace)
        except Exception as e:
            return {"skipped": f"FootprintStore not available: {e}"}

        result = store.cleanup()
        stats = store.get_stats()

        return {
            "l1_removed": result.get("l1_removed", 0),
            "l2_removed": result.get("l2_removed", 0),
            "remaining": stats,
        }

    # ═══════════════════════════════════════════
    # Step 19.5: Skill 健康度掃描
    # ═══════════════════════════════════════════

    def _step_skill_health_scan(self) -> Dict:
        """Step 19.5: 掃描所有 Skill 的健康度，偵測退化信號."""
        try:
            from museon.nightly.skill_health_tracker import SkillHealthTracker
            tracker = SkillHealthTracker(workspace=self._workspace)
            health_map = tracker.scan_all_skills()
            degradation = tracker.detect_degradation()
            tracker.persist()
            return {
                "skills_scanned": len(health_map),
                "degradation_signals": len(degradation),
                "degraded_skills": [d.skill_name for d in degradation],
            }
        except Exception as e:
            logger.debug(f"Step 19.5 skill_health_scan failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 19.6: Skill 草稿鍛造/優化
    # ═══════════════════════════════════════════

    def _step_skill_draft_forge(self) -> Dict:
        """Step 19.6: 從 Scout 筆記或退化信號自動鍛造/優化 Skill 草稿."""
        try:
            from museon.nightly.skill_draft_forger import SkillDraftForger
            forger = SkillDraftForger(workspace=self._workspace)
            result = forger.run()
            return result
        except Exception as e:
            logger.debug(f"Step 19.6 skill_draft_forge failed: {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 19.7: Skill QA 品質閘門
    # ═══════════════════════════════════════════

    def _step_skill_qa_gate(self) -> Dict:
        """Step 19.7: 對 pending_qa 狀態的草稿跑三維品質驗證."""
        try:
            from museon.nightly.skill_qa_gate import SkillQAGate
            from pathlib import Path
            gate = SkillQAGate(
                workspace=self._workspace,
                skills_dir=Path.home() / ".claude" / "skills",
            )
            drafts_dir = self._workspace / "_system" / "skills_draft"
            if not drafts_dir.exists():
                return {"drafts_evaluated": 0}

            results = []
            for draft_file in drafts_dir.glob("draft_*.json"):
                try:
                    import json
                    draft = json.loads(draft_file.read_text(encoding="utf-8"))
                    if draft.get("status") != "pending_qa":
                        continue
                    qa_result = gate.evaluate(draft_file)
                    # 更新草稿狀態
                    draft["status"] = "approved" if qa_result.passed else "quarantine"
                    draft["qa_score"] = qa_result.overall_score
                    draft["qa_result"] = {
                        "d1": {"passed": qa_result.d1.passed, "score": qa_result.d1.score},
                        "d2": {"passed": qa_result.d2.passed, "score": qa_result.d2.score},
                        "d3": {"passed": qa_result.d3.passed, "score": qa_result.d3.score},
                    }
                    tmp = draft_file.with_suffix(".tmp")
                    tmp.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
                    tmp.rename(draft_file)
                    results.append({
                        "id": draft.get("id", ""),
                        "passed": qa_result.passed,
                        "score": qa_result.overall_score,
                    })
                except Exception as e:
                    logger.debug(f"QA Gate eval failed for {draft_file.name}: {e}")

            # ── 晨間報告推播 ──
            report = {
                "drafts_evaluated": len(results),
                "passed": sum(1 for r in results if r["passed"]),
                "quarantined": sum(1 for r in results if not r["passed"]),
                "details": results,
            }

            # 讀取 19.5 的健康掃描結果（從 nightly report 回讀）
            health_info = ""
            try:
                report_file = self._workspace / "_system" / "state" / "nightly_report.json"
                if report_file.exists():
                    nr = json.load(open(report_file, "r", encoding="utf-8"))
                    h = nr.get("steps", {}).get("step_19_5_skill_health_scan", {}).get("result", {})
                    if h.get("degradation_signals", 0) > 0:
                        health_info = f"⚠️ {h['degradation_signals']} 個 Skill 退化中: {', '.join(h.get('degraded_skills', []))}\n"
            except Exception:
                pass

            # 有內容才推播
            if results or health_info:
                lines = ["🧬 Skill 演化晨報\n"]
                if health_info:
                    lines.append(health_info)
                passed = report["passed"]
                quarantined = report["quarantined"]
                if passed > 0:
                    names = [r["id"] for r in results if r["passed"]]
                    lines.append(f"✅ {passed} 個草稿通過 QA，等待你核准: {', '.join(names)}")
                if quarantined > 0:
                    lines.append(f"🔒 {quarantined} 個草稿品質不足，已隔離")
                if not results and health_info:
                    lines.append("今夜無新草稿產出。")

                if self._event_bus:
                    try:
                        self._event_bus.publish("PROACTIVE_MESSAGE", {
                            "message": "\n".join(lines),
                            "source": "alert",
                            "timestamp": datetime.now(TZ_TAIPEI).timestamp(),
                        })
                    except Exception:
                        pass

                    # 為每個通過 QA 的草稿發送帶 Inline Keyboard 的核准請求
                    for r in results:
                        if r["passed"]:
                            try:
                                draft_file = drafts_dir / f"{r['id']}.json"
                                if draft_file.exists():
                                    d = json.loads(draft_file.read_text(encoding="utf-8"))
                                    self._event_bus.publish("SKILL_APPROVAL_REQUEST", {
                                        "draft_id": r["id"],
                                        "skill_name": d.get("skill_name", r["id"]),
                                        "qa_score": r.get("score", 0),
                                        "summary": d.get("skill_md_content", "")[:200],
                                    })
                            except Exception:
                                pass

            return report
        except Exception as e:
            logger.debug(f"Step 19.7 skill_qa_gate failed: {e}")
            return {"error": str(e)}

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

    def _step_constellation_decay(self) -> Dict:
        """Step 32.6: 多星座每日衰減.

        遍歷所有已註冊的 active 星座（跳過 absurdity，已由 Step 32.5 處理），
        對每個星座的所有使用者雷達執行每日衰減：
        - 各維度向 0.5 回歸（衰減幅度由星座定義的 decay_rate 決定）
        - 信心值每天遞減（confidence_decay），下限為定義的 min_confidence（預設 0.0）
        """
        import json
        from museon.agent import constellation_radar

        data_dir = str(self._workspace)
        registry_path = self._workspace / "_system" / "constellations" / "registry.json"

        # 讀取 registry，取得所有已註冊星座
        if not registry_path.exists():
            logger.info("[NIGHTLY] 32.6: constellations/registry.json 不存在，跳過")
            return {"constellations_processed": 0, "users_decayed": 0, "details": {}}

        try:
            registry_data = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[NIGHTLY] 32.6: 讀取 registry.json 失敗: {e}")
            return {"constellations_processed": 0, "users_decayed": 0, "details": {}}

        # 取得 active 星座名稱列表（支援 list of dicts 或 list of strings 兩種格式）
        raw_constellations = registry_data.get("constellations", [])
        if isinstance(raw_constellations, list):
            active_names = []
            for item in raw_constellations:
                if isinstance(item, dict):
                    # list of dicts 格式：{"name": "...", "status": "active", ...}
                    name = item.get("name", "")
                    status = item.get("status", "active")
                    if name and status == "active":
                        active_names.append(name)
                elif isinstance(item, str):
                    # list of strings 格式：直接取名稱
                    active_names.append(item)
        elif isinstance(raw_constellations, dict):
            # dict 格式：{name: meta, ...}
            active_names = [
                name for name, meta in raw_constellations.items()
                if isinstance(meta, dict) and meta.get("active", True)
            ]
        else:
            active_names = []

        constellations_processed = 0
        total_users_decayed = 0
        details: dict = {}

        for name in active_names:
            # 跳過 absurdity：已由 Step 32.5 專責處理
            if name == "absurdity":
                continue

            # 載入星座定義
            defn = constellation_radar.load_definition(name, data_dir)
            if defn is None:
                logger.warning(f"[NIGHTLY] 32.6: 星座 {name} 定義不存在，跳過")
                continue

            dimensions = tuple(defn.get("dimensions", []))
            if not dimensions:
                logger.warning(f"[NIGHTLY] 32.6: 星座 {name} 無 dimensions，跳過")
                continue

            decay_rate: float = defn.get("decay_rate", 0.02)
            confidence_decay: float = defn.get("confidence_decay", 0.01)
            min_confidence: float = defn.get("min_confidence", 0.0)

            # 掃描此星座的所有使用者 radar 檔案
            radars_dir = self._workspace / "_system" / "constellations" / name / "radars"
            if not radars_dir.exists():
                # 星座目錄存在但尚無任何 radar 資料，正常情況，不報 warning
                continue

            users_decayed_this_constellation = 0
            for radar_file in radars_dir.glob("*.json"):
                user_id = radar_file.stem
                try:
                    radar = constellation_radar.load_radar(name, user_id, data_dir)

                    # 維度衰減：向 0.5 回歸
                    radar = constellation_radar.decay_radar(radar, dimensions, decay_rate)

                    # 信心衰減：覆寫 decay_radar 固定的 -0.01，改用星座自訂 confidence_decay
                    # decay_radar() 已把 confidence 減了 0.01，加回 0.01 再減 confidence_decay
                    # 等效於只減 confidence_decay（尊重星座自訂衰減率）
                    radar["confidence"] = round(
                        max(min_confidence, radar.get("confidence", 0.0) - confidence_decay + 0.01),
                        4,
                    )

                    constellation_radar.save_radar(name, radar, user_id, data_dir)
                    users_decayed_this_constellation += 1
                except Exception as e:
                    logger.warning(
                        f"[NIGHTLY] 32.6: 星座 {name} 使用者 {user_id} 衰減失敗: {e}"
                    )

            if users_decayed_this_constellation > 0:
                constellations_processed += 1
                total_users_decayed += users_decayed_this_constellation
                details[name] = users_decayed_this_constellation

        logger.info(
            f"[NIGHTLY] 32.6: 多星座衰減完成 — "
            f"{constellations_processed} 星座 × {total_users_decayed} 使用者"
        )
        return {
            "constellations_processed": constellations_processed,
            "users_decayed": total_users_decayed,
            "details": details,
        }

    def _step_crystal_promotion(self) -> Dict:
        """Step 33: 自動升級 Heuristic — 高頻結晶提升為啟發式規則。

        條件：reinforcement_count >= 3 AND crystal_type in (Lesson, Procedure, Pattern)
        上限：每次最多升級 3 條，heuristics 總條目上限 50。
        """
        try:
            from museon.agent.crystal_store import CrystalStore
            from museon.agent.intuition import IntuitionEngine, HeuristicRule

            # 載入活躍結晶
            store = CrystalStore(data_dir=str(self._workspace))
            crystals = store.load_crystals_raw()

            # 篩選符合條件的候選結晶
            ELIGIBLE_TYPES = {"Lesson", "Procedure", "Pattern"}
            candidates = [
                c for c in crystals
                if isinstance(c, dict)
                and c.get("reinforcement_count", 0) >= 3
                and c.get("crystal_type", "") in ELIGIBLE_TYPES
                and not c.get("archived", False)
            ]

            # 載入現有啟發式規則
            engine = IntuitionEngine(data_dir=str(self._workspace))
            existing = engine.store.load_heuristics()

            # 檢查哪些結晶已被升級過（rule_id 以 h-auto- 開頭並包含 cuid）
            already_promoted_cuids = {
                r.rule_id.replace("h-auto-", "")
                for r in existing
                if r.rule_id.startswith("h-auto-")
            }

            # 過濾掉已升級的
            new_candidates = [
                c for c in candidates
                if c.get("cuid", "") not in already_promoted_cuids
            ]

            # 排序：ri_score 高優先
            new_candidates.sort(key=lambda c: c.get("ri_score", 0.0), reverse=True)

            # 上限檢查
            MAX_HEURISTICS = 50
            MAX_PROMOTE_PER_RUN = 3
            available_slots = MAX_HEURISTICS - len(existing)
            to_promote = new_candidates[: min(MAX_PROMOTE_PER_RUN, available_slots)]

            # 建立新規則
            new_rules = []
            for crystal in to_promote:
                cuid = crystal.get("cuid", "")
                summary = (
                    crystal.get("g1_summary", "")
                    or crystal.get("title", "")
                    or cuid
                )
                new_rule = HeuristicRule(
                    rule_id=f"h-auto-{cuid}",
                    condition=summary,
                    prediction=summary,
                    confidence=0.8,
                    ri_score=float(crystal.get("ri_score", 0.0)),
                    source_crystals=[cuid],
                    last_updated=datetime.now().isoformat(),
                )
                new_rules.append(new_rule)

            # 寫入（追加到現有列表）
            if new_rules:
                updated = existing + new_rules
                engine.store.save_heuristics(updated)

            promoted = len(new_rules)
            total_heuristics = len(existing) + promoted
            logger.info(
                f"[NIGHTLY] CrystalPromotion: candidates={len(new_candidates)}, "
                f"promoted={promoted}, total_heuristics={total_heuristics}"
            )

            # ── Crystal Rules 硬上限：最多保留 50 條活躍規則 ──
            try:
                rules_path = self._workspace / "_system" / "crystal_rules.json"
                if rules_path.exists():
                    data = json.loads(rules_path.read_text(encoding="utf-8"))
                    rules = data.get("rules", [])
                    active = [r for r in rules if r.get("status") == "active"]
                    if len(active) > 50:
                        # 按 strength 排序，保留 top 50
                        active.sort(key=lambda r: r.get("strength", 0), reverse=True)
                        keep_ids = {r.get("rule_id") for r in active[:50]}
                        pruned = 0
                        for r in rules:
                            if r.get("status") == "active" and r.get("rule_id") not in keep_ids:
                                r["status"] = "expired"
                                pruned += 1
                        if pruned > 0:
                            data["rules"] = [r for r in rules if r.get("status") == "active"]
                            rules_path.write_text(
                                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                            )
                            logger.info(f"[NIGHTLY] Crystal rules pruned: {pruned} expired, {len(data['rules'])} remaining")
            except Exception as e:
                logger.warning(f"[NIGHTLY] Crystal rules pruning failed: {e}")

            return {
                "status": "ok",
                "promoted": promoted,
                "total_heuristics": total_heuristics,
            }
        except Exception as e:
            logger.warning(f"[NIGHTLY] CrystalPromotion failed: {e}")
            return {"status": "error", "error": str(e)}

    # ═══════════════════════════════════════════
    # Phase 5 + Phase 8: Persona Evolution Steps
    # ═══════════════════════════════════════════

    def _step_persona_reflection(self) -> dict:
        """Step 34: Nightly persona self-reflection (P1-P5 evolution)."""
        try:
            from museon.nightly.nightly_reflection import NightlyReflectionEngine
            from museon.pulse.anima_mc_store import get_anima_mc_store

            engine = NightlyReflectionEngine()
            _anima_mc_path = self._workspace / "ANIMA_MC.json"
            anima_mc_store = get_anima_mc_store(path=_anima_mc_path)
            anima_mc = anima_mc_store.load()
            if not anima_mc:
                return {"skipped": "no ANIMA_MC"}

            # Get today's soul rings
            recent_rings = []
            try:
                rings_path = self._workspace / "anima" / "soul_rings.json"
                if rings_path.exists():
                    import json
                    with open(rings_path) as f:
                        all_rings = json.load(f)
                    # Filter to today
                    from datetime import datetime, timezone
                    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    recent_rings = [r for r in all_rings if r.get("created_at", "").startswith(today)]
            except Exception:
                pass

            # Get daily summary from Step 10's output
            daily_summary = ""
            try:
                summary_path = self._workspace / "_system" / "state" / "nightly_report.json"
                if summary_path.exists():
                    import json
                    with open(summary_path) as f:
                        report = json.load(f)
                    daily_summary = report.get("daily_summary", "")
            except Exception:
                pass

            # LLM caller — 使用 ClaudeCLIAdapter（claude -p，MAX OAuth）
            def llm_caller(system_prompt: str, user_prompt: str) -> str:
                import asyncio
                from museon.llm.adapters import ClaudeCLIAdapter
                adapter = ClaudeCLIAdapter()
                resp = asyncio.run(adapter.call(
                    system_prompt=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    model="haiku",
                    max_tokens=1000,
                ))
                return resp.text

            # Soul ring depositor
            def soul_ring_depositor(**kwargs):
                try:
                    from museon.agent.soul_ring import RingDepositor, SoulRingStore
                    store = SoulRingStore(str(self._workspace / "anima"))
                    depositor = RingDepositor(store=store, data_dir=str(self._workspace))
                    depositor.deposit_soul_ring(**kwargs)
                except Exception as e:
                    logger.warning(f"Soul ring deposit failed: {e}")

            # KernelGuard
            kernel_guard = None
            try:
                from museon.agent.kernel_guard import KernelGuard
                kernel_guard = KernelGuard(data_dir=self._workspace)
            except Exception:
                pass

            # ── 學習→意識：將 KnowledgeLattice Top-RI 結晶注入反思上下文 ──
            try:
                import sqlite3
                _crystal_db = self._workspace / "lattice" / "crystal.db"
                if _crystal_db.exists():
                    _conn = sqlite3.connect(str(_crystal_db))
                    try:
                        _cursor = _conn.execute(
                            "SELECT cuid, crystal_type, g1_summary, ri_score "
                            "FROM crystals WHERE status='active' "
                            "ORDER BY ri_score DESC LIMIT 5"
                        )
                        _rows = _cursor.fetchall()
                    finally:
                        _conn.close()
                    if _rows:
                        _crystal_lines = ["\n\n【重要知識結晶（Top RI）】"]
                        for _row in _rows:
                            _cid, _ctype, _summary, _ri = _row
                            _ri_val = float(_ri) if _ri is not None else 0.0
                            _title = (_summary or "").strip()[:60]
                            _crystal_lines.append(f"- [{_ctype}] {_title} (RI: {_ri_val:.2f})")
                        daily_summary += "\n".join(_crystal_lines)
                        logger.info(
                            f"[NIGHTLY] 已將 {len(_rows)} 條高 RI 結晶注入 NightlyReflection 上下文"
                        )
                    else:
                        logger.debug("[NIGHTLY] crystal.db 無 active 結晶，跳過注入")
            except Exception as _crystal_exc:
                logger.warning(f"[NIGHTLY] 學習→意識弱通連線失敗（不影響主流程）：{_crystal_exc}")

            result = engine.run(
                anima_mc=anima_mc,
                recent_soul_rings=recent_rings,
                daily_summary=daily_summary,
                llm_caller=llm_caller,
                kernel_guard=kernel_guard,
                anima_mc_store=anima_mc_store,
                soul_ring_depositor=soul_ring_depositor,
            )
            return {"reflections": result.get("updates_applied", 0), "summary": result.get("reflection_summary", "")}
        except Exception as e:
            logger.warning(f"Step 34 persona_reflection failed: {e}")
            return {"error": str(e)}

    def _step_trait_metabolize(self) -> dict:
        """Step 34.5: Update weight_profile + recompute core_traits + growth stage."""
        try:
            from museon.agent.trait_engine import TraitEngine
            from museon.agent.growth_stage import GrowthStageComputer
            from museon.pulse.anima_mc_store import get_anima_mc_store

            te = TraitEngine()
            gsc = GrowthStageComputer()
            _anima_mc_path = self._workspace / "ANIMA_MC.json"
            store = get_anima_mc_store(path=_anima_mc_path)

            def updater(anima_mc):
                days = anima_mc.get("identity", {}).get("days_alive", 0)
                personality = anima_mc.setdefault("personality", {})

                # Update weight profile
                personality["weight_profile"] = te.compute_weight_profile(days)
                personality["weight_profile"]["computed_at_day"] = days

                # Recompute human-readable core_traits
                td = personality.get("trait_dimensions", {})
                personality["core_traits"] = te.compute_core_traits_label(td)

                # Recompute growth stage
                stage, maturity, constraints = gsc.compute(anima_mc)
                identity = anima_mc.setdefault("identity", {})
                old_stage = identity.get("growth_stage", "ABSORB")
                identity["growth_stage"] = stage
                identity["cognitive_maturity"] = round(maturity, 3)
                identity["stage_constraints"] = constraints
                personality["growth_stage_computed"] = stage
                personality["cognitive_maturity"] = round(maturity, 3)

                return anima_mc

            store.update(updater)
            return {"ok": True}
        except Exception as e:
            logger.warning(f"Step 34.5 trait_metabolize failed: {e}")
            return {"error": str(e)}

    def _step_drift_direction_check(self) -> dict:
        """Step 34.7: Check directional drift and personality capture risk."""
        try:
            from museon.agent.momentum_brake import MomentumBrake
            from museon.pulse.anima_mc_store import get_anima_mc_store
            import json

            mb = MomentumBrake()
            _anima_mc_path = self._workspace / "ANIMA_MC.json"
            store = get_anima_mc_store(path=_anima_mc_path)
            anima_mc = store.load()
            if not anima_mc:
                return {"skipped": "no ANIMA_MC"}

            trait_history = anima_mc.get("evolution", {}).get("trait_history", [])
            drift_report = mb.compute_directional_drift(trait_history, days=7)

            # Check for alerts
            alerts = {tid: info for tid, info in drift_report.items() if info.get("alert")}

            if alerts:
                logger.info(f"[DRIFT DIRECTION] Alerts: {list(alerts.keys())}")
                # Deposit warning soul ring
                try:
                    from museon.agent.soul_ring import DiaryStore
                    ds = DiaryStore(self._workspace / "anima")
                    alert_summary = ", ".join(f"{tid}: {info['direction']} ({info['consecutive_same_direction']}天)" for tid, info in alerts.items())
                    ds.deposit_soul_ring(
                        ring_type="value_calibration",
                        description=f"方向性漂移警告：{alert_summary}",
                        context="drift_direction_alert",
                        impact="啟動慣性煞車觀察",
                        entry_type="reflection",
                        force=True,
                    )
                except Exception as e:
                    logger.debug(f"Drift alert soul ring failed: {e}")

            return {"drift_report": {k: v.get("direction", "stable") for k, v in drift_report.items()}, "alerts": list(alerts.keys())}
        except Exception as e:
            logger.warning(f"Step 34.7 drift_direction_check failed: {e}")
            return {"error": str(e)}

    def _step_breath_analysis(self) -> Dict:
        """Step 34.8: 呼吸系統 Day 3-4 自動分析."""
        try:
            from museon.nightly.breath_analyzer import run_breath_analysis
            result = run_breath_analysis(self.data_dir)
            status = result.get("status", "unknown")
            if status == "skipped":
                return {"breath": "skipped (not Wed/Thu)"}
            if status == "no_observations":
                return {"breath": "no observations this week"}
            if status == "already_analyzed":
                return {"breath": "already done this week"}
            scope = result.get("layers", {}).get("L4_coupling", {}).get("affected_scope", "?")
            return {"breath": f"analyzed, scope={scope}"}
        except Exception as e:
            logger.warning(f"[BREATH] Step 34.8 failed: {e}")
            return {"breath_error": str(e)}

    def _step_vision_loop(self) -> Dict:
        """Step 34.9: 願景迴圈 — MUSEON 自主方向探索."""
        try:
            from museon.nightly.vision_loop import generate_vision_proposals
            result = generate_vision_proposals(self.data_dir)
            status = result.get("status", "unknown")
            if status == "skipped":
                return {"vision": "skipped (not Sunday)"}
            count = len(result.get("proposals", []))
            return {"vision": f"{status}, {count} proposals"}
        except Exception as e:
            logger.warning(f"[VISION] Step 34.9 failed: {e}")
            return {"vision_error": str(e)}

    # ═══════════════════════════════════════════
    # 報告持久化
    # ═══════════════════════════════════════════

    def _persist_report(self, report: Dict) -> None:
        """儲存管線報告（原子寫入）."""
        state_dir = self._workspace / "_system" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        path = state_dir / "nightly_report.json"

        # 截斷 result 為最多 200 字元（避免超大檔案）
        persist_report = {
            "completed_at": report.get("completed_at", ""),
            "elapsed_seconds": report.get("elapsed_seconds", 0),
            "mode": report.get("mode", "full"),
            "steps": {},
            "summary": report.get("summary", {}),
            "errors": report.get("errors", []),
        }
        for step_name, step_data in report.get("steps", {}).items():
            entry = {"status": step_data.get("status", "unknown")}
            if "result" in step_data:
                r = str(step_data["result"])
                entry["result"] = r[:REPORT_TRUNCATE_CHARS] if len(r) > REPORT_TRUNCATE_CHARS else r
            if "error" in step_data:
                entry["error"] = step_data["error"]
            persist_report["steps"][step_name] = entry

        try:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(persist_report, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.rename(path)

            # 歷史保留：按日期存一份副本（不覆蓋）
            history_dir = state_dir / "nightly_history"
            history_dir.mkdir(parents=True, exist_ok=True)
            completed = persist_report.get("completed_at", "")[:10]  # YYYY-MM-DD
            if completed:
                history_path = history_dir / f"nightly_report_{completed}.json"
                if not history_path.exists():
                    import shutil
                    shutil.copy2(path, history_path)
                    # 保留最近 30 份，清理更早的
                    history_files = sorted(history_dir.glob("nightly_report_*.json"))
                    if len(history_files) > 30:
                        for old in history_files[:-30]:
                            old.unlink()

        except Exception as e:
            logger.error(f"NightlyPipeline report persist failed: {e}")

        # 同時生成三層晨報結構
        self._generate_morning_layers(persist_report, state_dir)

    def _generate_morning_layers(self, report: Dict, state_dir: Path) -> None:
        """生成三層晨報結構.

        Layer 1 (摘要層): 2-3 句話，30 秒讀完
        Layer 2 (詳情層): 關鍵步驟列表 + 警告/錯誤
        Layer 3 (決策需求層): 需要人類決定的事項
        """
        summary = report.get("summary", {})
        steps = report.get("steps", {})
        errors = report.get("errors", [])

        ok = summary.get("ok", 0)
        total = summary.get("total", 0)
        error_count = summary.get("error", 0)
        elapsed = report.get("elapsed_seconds", 0)

        # ── Layer 1：摘要 ──
        if error_count == 0:
            verdict = f"昨夜整合全部完成 ({ok}/{total} 步驟通過)"
        else:
            verdict = f"昨夜整合有 {error_count} 步異常 ({ok}/{total} 通過)"

        layer1 = {
            "verdict": verdict,
            "elapsed_seconds": elapsed,
            "one_liner": f"{verdict}，耗時 {elapsed:.0f} 秒。" + (
                "" if error_count == 0 else " 請查看 Layer 3 的決策需求。"
            ),
        }

        # ── Layer 2：詳情 ──
        highlights = []
        warnings = []
        for step_name, step_data in steps.items():
            status = step_data.get("status", "unknown")
            result_str = step_data.get("result", "")

            if status == "ok" and "skipped" not in result_str.lower():
                # 挑出有實質結果的步驟
                if any(kw in result_str for kw in [
                    "decayed", "archived", "executed", "forged",
                    "pruned", "explored", "crystal",
                ]):
                    highlights.append(f"  ✅ {step_name}: {result_str[:80]}")
            elif status == "error":
                warnings.append(f"  ❌ {step_name}: {step_data.get('error', '?')[:80]}")
            elif status == "skipped":
                pass  # 跳過的步驟不列出

        layer2 = {
            "highlights": highlights[:10],
            "warnings": warnings,
            "step_count": {"ok": ok, "error": error_count, "total": total},
        }

        # ── Layer 3：決策需求 ──
        decisions = []
        for err in errors:
            step_name = err.get("step", "?")
            error_msg = err.get("error", "")[:120]
            decisions.append({
                "type": "error_needs_attention",
                "step": step_name,
                "description": f"{step_name} 執行失敗: {error_msg}",
            })

        # 檢查 Morphenix L3 提案（需人類審查）
        # 只看 l3_proposals 非空（"escalated" 字串太寬泛，MuseOff finding 也會命中）
        for step_name, step_data in steps.items():
            result_str = step_data.get("result", "")
            if "l3_proposals" in result_str:
                import json as _json
                try:
                    _res = _json.loads(result_str) if isinstance(result_str, str) else result_str
                    _l3 = _res.get("l3_proposals", []) if isinstance(_res, dict) else []
                    if _l3:  # 只有實際有 L3 提案才報
                        decisions.append({
                            "type": "morphenix_l3_review",
                            "step": step_name,
                            "description": f"有 {len(_l3)} 個 Morphenix L3 提案需要你審查",
                        })
                except (ValueError, AttributeError):
                    pass

        layer3 = {
            "decisions_needed": len(decisions),
            "items": decisions,
        }

        morning_report = {
            "generated_at": datetime.now(TZ_TAIPEI).isoformat(),
            "layer1_summary": layer1,
            "layer2_details": layer2,
            "layer3_decisions": layer3,
        }

        try:
            morning_path = state_dir / "morning_report.json"
            morning_path.write_text(
                json.dumps(morning_report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Morning report generation failed: {e}")


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
