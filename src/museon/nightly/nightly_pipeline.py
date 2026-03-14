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
    EVOLUTION_VELOCITY_ALERT,
    KNOWLEDGE_GRAPH_UPDATED,
    NIGHTLY_COMPLETED,
    NIGHTLY_DAG_EXECUTED,
    NIGHTLY_HEALTH_GATE,
    NIGHTLY_STARTED,
)

logger = logging.getLogger(__name__)


def _run_async_safe(coro, timeout: int = 120):
    """統一的 sync-in-async 橋接.

    在 Gateway async context 中安全執行 async 函數。
    如果當前有 event loop 正在運行，使用 ThreadPoolExecutor 橋接。
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=timeout)
        else:
            return asyncio.run(coro)
    except RuntimeError:
        return asyncio.run(coro)


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
    "0", "0.1",  # Budget settlement + Footprint cleanup (最先執行)
    "1", "2", "3", "4", "5", "5.5", "5.6", "5.7", "5.8", "5.9", "5.9.5", "5.10",
    "6", "6.5", "7", "7.5", "8", "8.5", "9", "10", "10.5", "11", "12", "13", "13.5",
    "13.6", "13.7", "13.8",  # 外向型進化：觸發掃描 → 外向研究 → 消化生命週期
    "14", "15", "16", "17",
    "18",
    "20", "21", "22", "23",  # 新增：synapse_decay/muscle_atrophy/immune_prune/trigger_eval
    "24", "25",  # 新增：演化速度計算 / 週月循環觸發檢查
]
_ORIGIN_STEPS = ["5.8", "6", "7", "8", "16"]
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
    | 8.5  | DNA27 反射向量重索引          | 0     |
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
            "8.5": ("step_08_5_dna27_reindex", self._step_dna27_reindex),
            "9": ("step_09_graph_consolidation", self._step_graph_consolidation),
            "10": ("step_10_soul_nightly", self._step_soul_nightly),
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
                if score <= 40:
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

        return report

    # ═══════════════════════════════════════════
    # WP-03: 健康閘門步驟集
    # ═══════════════════════════════════════════

    def _get_degraded_steps(self) -> List[str]:
        """降級模式：跳過 Morphenix、Claude Skill Forge、外向搜尋等重型步驟."""
        skip = {"5.8", "5.9", "5.10", "13.5", "13.6", "13.7", "13.8", "16"}
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

    def _step_cross_crystallize(self) -> Dict:
        """Step 5.5: L2_ep 跨使用者聚類."""
        memory_dir = self._workspace / "_system" / "memory"
        if not memory_dir.exists():
            return {"skipped": "no memory directory"}

        # 聚合 shared / owner / cli_user 三個 scope 的 L2_ep
        l2_items = []
        seen_ids = set()
        for scope in ["shared", "owner", "cli_user"]:
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

        從五個系統信號源偵測問題，自動生成具體的 Morphenix 提案：
        1. Q-Score 連續低分 → 調整 prompt 策略
        2. Knowledge Lattice 降級結晶 → 修正相關 Skill
        3. MetaCognition 預判失準 → 調整預測參數
        4. Skill Router 命中率低 → 調整路由權重
        5. 迭代筆記累積 → 傳統筆記結晶提案

        這是從「被動記錄」跨越到「主動演化」的關鍵步驟。
        """
        proposals_dir = self._workspace / "_system" / "morphenix" / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        proposals_created = 0
        signals_scanned = 0
        diagnostics = []

        # ═══ 信號源 1: Q-Score 連續低分偵測 ═══
        try:
            qscore_file = self._workspace / "_system" / "eval" / "qscore_history.jsonl"
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
            lattice_dir = self._workspace / "lattice"
            crystals_file = lattice_dir / "crystals.json"
            if crystals_file.exists():
                signals_scanned += 1
                with open(crystals_file, "r", encoding="utf-8") as fh:
                    crystals_data = json.load(fh)

                # 統計被降級的結晶（有反證的 Insight）
                downgraded = [
                    c for c in crystals_data
                    if isinstance(c, dict)
                    and c.get("counter_evidence_count", 0) >= 2
                    and c.get("crystal_type") == "Insight"
                ]
                if downgraded:
                    domains = set(c.get("domain", "general") for c in downgraded)
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
                    proposal = {
                        "category": "L2",
                        "source": "iteration_notes",
                        "title": f"{len(notes)} 條迭代筆記待結晶",
                        "description": f"累積 {len(notes)} 條迭代觀察筆記，建議結晶為具體改進提案。",
                        "action": "crystallize_notes",
                        "source_notes": [f.name for f in notes_dir.glob("*.json") if f.is_file()][:20],
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
                        pulse_db.save_proposal(
                            proposal_id=pid,
                            level="L1",
                            title=proposal.get("title", "L1 Config 提案"),
                            description=proposal.get("description", proposal.get("summary", "")),
                            affected_files=proposal.get("affected_files", []) if isinstance(proposal.get("affected_files"), list) else [],
                            source_notes=proposal.get("source_notes", []) if isinstance(proposal.get("source_notes"), list) else [],
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
                        pulse_db.save_proposal(
                            proposal_id=pid,
                            level="L2",
                            title=proposal.get("title", "L2 Logic 提案"),
                            description=proposal.get("description", proposal.get("summary", "")),
                            affected_files=proposal.get("affected_files", []) if isinstance(proposal.get("affected_files"), list) else [],
                            source_notes=proposal.get("source_notes", []) if isinstance(proposal.get("source_notes"), list) else [],
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
                # 未分類，預設為 L1
                proposal["status"] = "approved"
                proposal["decided_by"] = "auto"
                proposal["decided_at"] = datetime.now(TZ_TAIPEI).isoformat()
                results["auto_approved"] += 1

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
    # Step 6: 技能鍛造
    # ═══════════════════════════════════════════

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
    # Step 8.5: DNA27 反射模式向量重索引
    # ═══════════════════════════════════════════

    def _step_dna27_reindex(self) -> Dict:
        """Step 8.5: 重新索引 DNA27 反射模式到 Qdrant（零 LLM）."""
        try:
            from museon.agent.reflex_router import index_reflex_patterns_to_qdrant
            indexed = index_reflex_patterns_to_qdrant(str(self._workspace))
            return {"indexed_count": indexed}
        except Exception as e:
            return {"skipped": f"DNA27 reindex failed: {e}"}

    # ═══════════════════════════════════════════
    # Step 9: 知識圖譜睡眠整合
    # ═══════════════════════════════════════════

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
    # Step 10: 靈魂層夜間整合
    # ═══════════════════════════════════════════

    def _step_soul_nightly(self) -> Dict:
        """Step 10: 靈魂整合（情緒衰減、自我認知更新）."""
        soul_dir = self._workspace / "_system" / "soul"
        if not soul_dir.exists():
            return {"skipped": "no soul directory"}

        state_file = soul_dir / "soul_state.json"
        if not state_file.exists():
            return {"skipped": "no soul state"}

        try:
            with open(state_file, "r", encoding="utf-8") as fh:
                state = json.load(fh)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return {"skipped": "soul state unreadable"}

        # 情緒衰減
        emotions = state.get("emotions", {})
        for key in emotions:
            if isinstance(emotions[key], (int, float)):
                emotions[key] = round(emotions[key] * DAILY_DECAY_FACTOR, 4)

        state["last_nightly"] = datetime.now(TZ_TAIPEI).isoformat()

        with open(state_file, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2)

        return {"emotions_decayed": len(emotions)}

    # ═══════════════════════════════════════════
    # Step 10.6: SOUL.md 身份驗證
    # ═══════════════════════════════════════════

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

    def _step_curiosity_scan(self) -> Dict:
        """Step 13: 提取未解答的好奇問題."""
        curiosity_dir = self._workspace / "_system" / "curiosity"
        curiosity_dir.mkdir(parents=True, exist_ok=True)

        queue_file = curiosity_dir / "question_queue.json"
        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                queue = json.load(fh)
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
                            if q_text[:100] not in existing_qs:
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
                            if q_text[:100] not in existing_qs:
                                queue.append({
                                    "question": q_text,
                                    "source_date": yesterday,
                                    "status": "pending",
                                })
                                existing_qs.add(q_text[:100])
                                new_questions += 1
                except Exception as e:
                    logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

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

            results = _run_async_safe(router.process_queue(max_items=2))

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
                            resp = asyncio.get_event_loop().run_until_complete(
                                adapter.call(
                                    system_prompt="你是技能精煉專家。",
                                    messages=[{"role": "user", "content": prompt}],
                                    model="sonnet",
                                    max_tokens=200,
                                )
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

    # ═══════════════════════════════════════════
    # Federation Upload（Node 專屬）
    # ═══════════════════════════════════════════

    def _step_federation_upload(self) -> Dict:
        """Federation 同步（v3 Git 模式）.

        - origin 模式：收集所有子體經驗
        - node 模式：推送匿名化經驗到 GitHub
        """
        try:
            from museon.federation.sync import FederationSync
        except ImportError as e:
            return {"skipped": f"FederationSync not available: {e}"}

        fed_mode = os.environ.get("MUSEON_FEDERATION_MODE", "")
        if not fed_mode:
            return {"skipped": "MUSEON_FEDERATION_MODE not set"}

        try:
            sync = FederationSync(data_dir=str(self._workspace))
        except Exception as e:
            return {"error": f"FederationSync init failed: {e}"}

        if fed_mode == "origin":
            # 母體：收集子體經驗
            result = sync.collect_children()
        else:
            # 子體：推送同步包 + 拉取母體更新
            push_result = sync.push_sync_package()
            pull_result = sync.pull_evolution()
            result = {"push": push_result, "pull": pull_result}

        return result

    def _step_federation_upload_legacy(self) -> Dict:
        """[Legacy] Node 上繳知識到 Origin（HTTP 模式，已棄用）."""
        node_id = os.environ.get("MUSEON_NODE_ID")
        if not node_id:
            return {"skipped": "not a federation node (no MUSEON_NODE_ID)"}

        origin_url = os.environ.get("MUSEON_ORIGIN_URL", "http://127.0.0.1:9200")

        upload_items = []
        for level in ["L2_sem", "L3_procedural"]:
            level_dir = self._workspace / "_system" / "memory" / "shared" / level
            if not level_dir.exists():
                continue
            for f in level_dir.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        item = json.load(fh)
                    if not item.get("uploaded"):
                        upload_items.append((f, item))
                except Exception as e:
                    logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        if not upload_items:
            return {"skipped": "nothing to upload"}

        uploaded = 0
        for f, item in upload_items:
            try:
                item["uploaded"] = True
                item["uploaded_at"] = datetime.now(TZ_TAIPEI).isoformat()
                item["uploaded_to"] = origin_url
                with open(f, "w", encoding="utf-8") as fh:
                    json.dump(item, fh, ensure_ascii=False, indent=2)
                uploaded += 1
            except Exception as e:
                logger.debug(f"[NIGHTLY] operation failed (degraded): {e}")

        return {"uploaded": uploaded, "node_id": node_id, "origin_url": origin_url}

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
        for step_name, step_data in steps.items():
            result_str = step_data.get("result", "")
            if "escalated" in result_str.lower() or "l3" in result_str.lower():
                decisions.append({
                    "type": "morphenix_l3_review",
                    "step": step_name,
                    "description": f"有 Morphenix L3 提案需要你審查",
                })

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

        # 降級：讀取原始 nightly report
        report_path = state_dir / "nightly_report.json"
        if not report_path.exists():
            return None
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"[NIGHTLY] degraded: {e}")
            return None

    scheduler.register(
        name="nightly_morning_report",
        func=_morning_report,
        cron_hour=MORNING_REPORT_HOUR,
        cron_minute=MORNING_REPORT_MINUTE,
        description="Morning report: read nightly results for push",
    )
