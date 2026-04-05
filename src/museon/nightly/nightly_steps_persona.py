"""NightlyStepsPersonaMixin — 人格演化與報告步驟群 (Steps 32.6-34.9 + 報告).

包含多星座衰減、結晶升級、人格反思、特質代謝、漂移方向檢查、
呼吸分析、願景迴圈，以及報告持久化和三層晨報生成。
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

REPORT_TRUNCATE_CHARS = 200


class NightlyStepsPersonaMixin:
    """人格演化與報告步驟 Mixin (Steps 32.6-34.9 + 報告持久化)."""

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
