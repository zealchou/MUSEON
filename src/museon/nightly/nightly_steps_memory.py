"""NightlyStepsMemoryMixin — 記憶與結晶相關步驟.

包含的步驟：
- _step_asset_decay (Step 1)
- _step_archive_assets (Step 2)
- _step_memory_maintenance (Step 3)
- _step_wee_compress (Step 4)
- _step_wee_fuse (Step 5)
- _step_cross_crystallize (Step 5.5, DORMANT)
- _step_knowledge_lattice (Step 5.6)
- _step_lesson_distill (Step 5.6.5)
- _step_crystal_actuator (Step 5.7)
"""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

DAILY_DECAY_FACTOR = 0.993
ARCHIVE_THRESHOLD = 0.3
WEE_MIN_CRYSTALS_FOR_FUSE = 3
SKILL_FORGE_MIN_CLUSTER = 3
SKILL_FORGE_SIMILARITY_THRESHOLD = 0.5


class NightlyStepsMemoryMixin:
    """記憶維護與結晶相關的 Nightly 步驟."""

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
        from datetime import timezone as _timezone
        TZ_TAIPEI = _timezone(timedelta(hours=8))

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
        from datetime import timezone as _timezone
        TZ_TAIPEI = _timezone(timedelta(hours=8))

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
