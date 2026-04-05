"""NightlyStepsIdentityMixin — 身份與探索相關步驟.

包含的步驟：
- _step_diary_generation (Step 10)
- _step_soul_identity_check (Step 10.6, DORMANT)
- _step_ring_review (Step 10.5, DORMANT)
- _step_dream_engine (Step 11, DORMANT)
- _step_heartbeat_focus (Step 12)
- _step_curiosity_scan (Step 13)
- _step_curiosity_research (Step 13.5)
- _step_outward_trigger_scan (Step 13.6)
- _step_outward_research (Step 13.7, DORMANT)
"""

import json
import logging
import collections
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))
DAILY_DECAY_FACTOR = 0.993


def _run_async_safe(coro, timeout: int = 120):
    """同步呼叫 async 協程的橋接函數."""
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


class NightlyStepsIdentityMixin:
    """身份、靈魂與探索相關的 Nightly 步驟."""

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
