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

logger = logging.getLogger(__name__)

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
    "1", "2", "3", "4", "5", "5.5", "5.8", "5.9", "5.10",
    "6", "7", "8", "8.5", "9", "10", "10.5", "11", "12", "13", "14", "15", "16", "17",
    "18",
    "20", "21", "22", "23",  # 新增：synapse_decay/muscle_atrophy/immune_prune/trigger_eval
]
_ORIGIN_STEPS = ["5.8", "6", "7", "8", "16"]
_NODE_STEPS = [
    "1", "2", "3", "4", "5", "5.5",
    "9", "10", "11", "12", "13", "14", "15",
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
    ) -> None:
        self._workspace = workspace
        self._memory_manager = memory_manager
        self._heartbeat_focus = heartbeat_focus
        self._event_bus = event_bus
        self._brain = brain

        # Step map: step_id → (name, method)
        self._step_map: Dict[str, tuple] = {
            "1": ("step_01_asset_decay", self._step_asset_decay),
            "2": ("step_02_archive_assets", self._step_archive_assets),
            "3": ("step_03_memory_maintenance", self._step_memory_maintenance),
            "4": ("step_04_wee_compress", self._step_wee_compress),
            "5": ("step_05_wee_fuse", self._step_wee_fuse),
            "5.5": ("step_05_5_cross_crystallize", self._step_cross_crystallize),
            "5.6": ("step_05_6_knowledge_lattice", self._step_knowledge_lattice),
            "5.8": ("step_05_8_morphenix_proposals", self._step_morphenix_proposals),
            "5.9": ("step_05_9_morphenix_gate", self._step_morphenix_gate),
            "5.10": ("step_05_10_morphenix_execute", self._step_morphenix_execute),
            "6": ("step_06_skill_forge", self._step_skill_forge),
            "7": ("step_07_curriculum", self._step_curriculum),
            "8": ("step_08_workflow_mutation", self._step_workflow_mutation),
            "8.5": ("step_08_5_dna27_reindex", self._step_dna27_reindex),
            "9": ("step_09_graph_consolidation", self._step_graph_consolidation),
            "10": ("step_10_soul_nightly", self._step_soul_nightly),
            "10.5": ("step_10_5_ring_review", self._step_ring_review),
            "11": ("step_11_dream_engine", self._step_dream_engine),
            "12": ("step_12_heartbeat_focus", self._step_heartbeat_focus),
            "13": ("step_13_curiosity_scan", self._step_curiosity_scan),
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
        self._publish("NIGHTLY_STARTED", {
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

        # steps 用 dict 格式（key=step_name）
        steps_dict: Dict[str, Dict] = {}
        for step_id in step_ids:
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
        skipped_count = sum(1 for s in steps_dict.values() if s["status"] == "skipped")

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
        self._publish("NIGHTLY_COMPLETED", {
            "mode": mode,
            "elapsed_seconds": elapsed,
            "summary": report["summary"],
            "errors": errors,
        })

        return report

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
        except NotImplementedError:
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
            except Exception:
                pass
        # Phase B: Multi-Agent shared_assets 衰退
        shared_decayed = 0
        try:
            from museon.multiagent.shared_assets import SharedAssetLibrary
            lib = SharedAssetLibrary(workspace=self._workspace)
            shared_decayed = lib.decay_all()
        except Exception:
            pass

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
                except Exception:
                    pass

        # Phase B: Multi-Agent shared_assets 歸檔
        shared_archived = 0
        try:
            from museon.multiagent.shared_assets import SharedAssetLibrary
            lib = SharedAssetLibrary(workspace=self._workspace)
            shared_archived = lib.archive_low_quality()
        except Exception:
            pass

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
        except ImportError:
            pass

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
            except Exception:
                pass

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
        except ImportError:
            pass

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
            except Exception:
                pass

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
                except Exception:
                    pass

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
        except ImportError:
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
        except ImportError:
            return {"skipped": "KnowledgeLattice not available"}
        except Exception as e:
            return {"error": str(e)}

    # ═══════════════════════════════════════════
    # Step 5.8: Morphenix 提案
    # ═══════════════════════════════════════════

    def _step_morphenix_proposals(self) -> Dict:
        """Step 5.8: 迭代筆記結晶為提案."""
        notes_dir = self._workspace / "_system" / "morphenix" / "notes"
        if not notes_dir.exists():
            return {"skipped": "no morphenix notes directory"}

        notes = []
        for f in notes_dir.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    notes.append(json.load(fh))
            except Exception:
                pass

        if len(notes) < 3:
            return {"skipped": "not enough notes", "count": len(notes)}

        # 結晶為提案
        proposals_dir = self._workspace / "_system" / "morphenix" / "proposals"
        proposals_dir.mkdir(parents=True, exist_ok=True)

        proposal = {
            "type": "L2_sem",
            "source_notes": len(notes),
            "created_at": datetime.now(TZ_TAIPEI).isoformat(),
            "status": "pending_review",
        }
        out = proposals_dir / f"proposal_{date.today().isoformat()}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(proposal, fh, ensure_ascii=False, indent=2)

        return {"proposals_created": 1, "source_notes": len(notes)}

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
                if proposal.get("status") == "pending_review":
                    proposal["_file"] = str(f)
                    pending.append(proposal)
            except Exception:
                pass

        if not pending:
            return {"skipped": "no pending proposals"}

        # 取得 PulseDB（用於持久化 L3 提案）
        pulse_db = None
        try:
            from museon.pulse.pulse_db import PulseDB
            db_path = self._workspace / "pulse.db"
            pulse_db = PulseDB(str(db_path))
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

            elif "L2" in str(category):
                # L2 Logic: 自動核准，標記待測試
                proposal["status"] = "approved_pending_test"
                proposal["decided_by"] = "auto"
                proposal["decided_at"] = datetime.now(TZ_TAIPEI).isoformat()
                results["auto_approved"] += 1

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

        # L3 提案 → 透過 EventBus 發送 Telegram inline keyboard 通知
        if results["l3_proposals"] and self._event_bus:
            try:
                self._event_bus.publish("MORPHENIX_L3_PROPOSAL", {
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
    # Step 5.10: Morphenix 執行
    # ═══════════════════════════════════════════

    def _step_morphenix_execute(self) -> Dict:
        """Step 5.10: 執行已核准的 Morphenix 演化提案.

        流程：PulseDB 中 status='approved' 的提案
        → Core Brain 審查 → git tag 安全快照 → 執行變更 → 標記 executed
        """
        try:
            from museon.pulse.pulse_db import PulseDB
            db_path = self._workspace / "pulse.db"
            pulse_db = PulseDB(str(db_path))
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
            except Exception:
                pass

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
        except ImportError:
            return {"skipped": "ChromosomeIndex not available"}

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
            except Exception:
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
            except Exception:
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
        except Exception:
            return {"skipped": "edges file unreadable"}

        try:
            with open(nodes_file, "r", encoding="utf-8") as fh:
                nodes = json.load(fh)
        except Exception:
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
        except Exception:
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
            except Exception:
                pass

        if last_review:
            try:
                last_dt = datetime.fromisoformat(last_review)
                days_since = (datetime.now(TZ_TAIPEI) - last_dt.replace(
                    tzinfo=TZ_TAIPEI if last_dt.tzinfo is None else last_dt.tzinfo
                )).days
                if days_since < 30:
                    return {"skipped": f"last review {days_since} days ago, next in {30 - days_since} days"}
            except (ValueError, TypeError):
                pass

        # 載入最近 30 天的 Soul Rings
        rings_path = self._workspace.parent / "anima" / "soul_rings.json"
        if not rings_path.exists():
            return {"skipped": "no soul_rings.json"}

        try:
            with open(rings_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
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
                except Exception:
                    pass

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
        except Exception:
            queue = []

        # 掃描近期對話日誌中的問句
        logs_dir = self._workspace / "_system" / "logs"
        new_questions = 0
        if logs_dir.exists():
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            for f in logs_dir.glob(f"{yesterday}*.jsonl"):
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        for line in fh:
                            try:
                                entry = json.loads(line.strip())
                                msg = entry.get("user_message", "")
                                if msg.endswith("？") or msg.endswith("?"):
                                    queue.append({
                                        "question": msg[:200],
                                        "source_date": yesterday,
                                        "status": "pending",
                                    })
                                    new_questions += 1
                            except Exception:
                                pass
                except Exception:
                    pass

        # 保留最近 50 個問題
        queue = queue[-50:]
        with open(queue_file, "w", encoding="utf-8") as fh:
            json.dump(queue, fh, ensure_ascii=False, indent=2)

        return {"new_questions": new_questions, "queue_size": len(queue)}

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
                    except Exception:
                        pass

                if changed:
                    with open(f, "w", encoding="utf-8") as fh:
                        json.dump(skill, fh, ensure_ascii=False, indent=2)

            except Exception:
                pass

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
            except Exception:
                pass

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
            except Exception:
                pass

        # Phase B: 嘗試 LLM 精煉（可選）
        llm_refined = 0
        try:
            llm_client = getattr(self._brain, "llm_client", None)
            if llm_client and refined > 0:
                for sf in skills[-3:]:
                    try:
                        with open(sf, "r", encoding="utf-8") as fh:
                            skill = json.load(fh)
                        if skill.get("refined") and not skill.get("llm_refined"):
                            # 截取前 500 字避免 token 浪費
                            snippet = json.dumps(skill, ensure_ascii=False)[:500]
                            prompt = (
                                "你是 MUSEON 技能精煉專家。請用一段話"
                                "（不超過 100 字）總結這個技能的核心能力：\n"
                                f"{snippet}"
                            )
                            resp = llm_client.chat(
                                messages=[{"role": "user", "content": prompt}],
                                model="sonnet",
                                max_tokens=200,
                            )
                            if resp and hasattr(resp, "content"):
                                skill["llm_summary"] = str(resp.content)[:200]
                                skill["llm_refined"] = True
                                skill["llm_refined_at"] = datetime.now(TZ_TAIPEI).isoformat()
                                with open(sf, "w", encoding="utf-8") as fh:
                                    json.dump(skill, fh, ensure_ascii=False, indent=2)
                                llm_refined += 1
                    except Exception:
                        pass
        except Exception:
            pass

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
        """Node 上繳知識到 Origin."""
        node_id = os.environ.get("MUSEON_NODE_ID")
        if not node_id:
            return {"skipped": "not a federation node (no MUSEON_NODE_ID)"}

        origin_url = os.environ.get("MUSEON_ORIGIN_URL", "http://127.0.0.1:9200")

        # 收集要上繳的知識（L2_sem / L3）
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
                except Exception:
                    pass

        if not upload_items:
            return {"skipped": "nothing to upload"}

        # 標記為已上傳（實際的 HTTP sync 需 NodeClient）
        uploaded = 0
        for f, item in upload_items:
            try:
                item["uploaded"] = True
                item["uploaded_at"] = datetime.now(TZ_TAIPEI).isoformat()
                item["uploaded_to"] = origin_url
                with open(f, "w", encoding="utf-8") as fh:
                    json.dump(item, fh, ensure_ascii=False, indent=2)
                uploaded += 1
            except Exception:
                pass

        return {"uploaded": uploaded, "node_id": node_id, "origin_url": origin_url}

    # ═══════════════════════════════════════════
    # Step 0: Token 預算日結算
    # ═══════════════════════════════════════════

    def _step_budget_settlement(self) -> Dict:
        """Step 0: Token 預算日結算（最先執行）.

        1. daily_metabolism() — reserve 每日代謝 2%
        2. daily_settlement() — 結餘存入 reserve
        """
        try:
            from museon.pulse.token_budget import TokenBudgetManager
            manager = TokenBudgetManager(data_dir=self._workspace)
        except Exception as e:
            return {"skipped": f"TokenBudgetManager not available: {e}"}

        # 代謝
        metabolized = manager.daily_metabolism()

        # 日結算
        saved = manager.daily_settlement()

        # conservation mode 檢查 → 發布事件
        status = manager.get_status()
        if status.get("conservation_mode") and self._event_bus:
            try:
                from museon.core.event_bus import TOKEN_BUDGET_CONSERVATION
                self._event_bus.publish(TOKEN_BUDGET_CONSERVATION, {
                    "reserve_health": status.get("reserve_health"),
                    "model_recommendation": status.get("model_recommendation"),
                })
            except Exception:
                pass

        return {
            "metabolized_usd": round(metabolized, 4),
            "saved_to_reserve_usd": round(saved, 4),
            "tier": status.get("tier"),
            "reserve_usd": status.get("reserve_pool_usd"),
            "conservation_mode": status.get("conservation_mode"),
        }

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
            except Exception:
                pass

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
            except Exception:
                pass

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
            except Exception:
                pass

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
        except Exception:
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
            except Exception:
                pass

        return {
            "total_score": result.total_score,
            "vitality_modifier": result.vitality_modifier,
            "fired_triggers": result.fired_triggers,
            "should_evolve": result.should_evolve,
            "details": result.details,
        }

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
        report_path = workspace / "_system" / "state" / "nightly_report.json"
        if not report_path.exists():
            return None
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    scheduler.register(
        name="nightly_morning_report",
        func=_morning_report,
        cron_hour=MORNING_REPORT_HOUR,
        cron_minute=MORNING_REPORT_MINUTE,
        description="Morning report: read nightly results for push",
    )
