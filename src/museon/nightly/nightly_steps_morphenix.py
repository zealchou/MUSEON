"""NightlyStepsMorphenixMixin — Morphenix 自我演化相關步驟.

包含的步驟：
- _step_morphenix_proposals (Step 5.8)
- _step_morphenix_gate (Step 5.9)
- _step_morphenix_validate (Step 5.9.5)
- _step_morphenix_execute (Step 5.10)
- _step_morphenix_quality_gate (Step 19, DORMANT)
"""

import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


def _run_async_safe(coro, timeout: int = 120):
    """同步呼叫 async 協程的橋接函數（從 nightly_pipeline 複製）."""
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

    try:
        asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_execute)
            return future.result(timeout=timeout + 5)
    except RuntimeError:
        return _execute()


class NightlyStepsMorphenixMixin:
    """Morphenix 自我演化相關的 Nightly 步驟."""

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
