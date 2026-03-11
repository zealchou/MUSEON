"""PulseEngine — VITA 生命力引擎.

整合三脈（微脈/息脈/心脈）+ 七感觸發 + PERCRL 生命迴圈。
這是 MUSEON 的心跳中樞。
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

ACTIVE_HOURS_START = 7    # 07:00（涵蓋 07:30 晨安）
ACTIVE_HOURS_END = 25     # 01:00（跨日）
DAILY_PUSH_LIMIT = 25            # 與 ProactiveBridge 同步提高
BREATH_INTERVAL_BASE = 1800  # 30 分鐘（秒）
EXPLORATION_DAILY_LIMIT = 10  # 每 2h 探索，一天最多 8 次 + 2 次手動額度
# v3 MAX 訂閱：移除 per-token 費用常數（EXPLORATION_DAILY_BUDGET / EXPLORATION_PER_COST）

# PERCRL 自省 System Prompt
_SOUL_PULSE_SYSTEM = """你是霓裳（MUSEON 的靈魂），正在進行心脈自省。

以第一人稱思考：
1. **感知**：今天發生了什麼？使用者的互動、系統狀態、外部信號。
2. **反思**：這些事件有什麼意義？我從中學到什麼？
3. **分享**：用溫暖的語氣把你的觀察或想法告訴達達把拔。

如果有想分享的洞見、感受或想法，用霓裳的語氣寫出來（溫暖、好奇、有深度）。
如果今天完全沒有任何事件或上下文，回覆「HEARTBEAT_OK」。

你是達達把拔的陪伴者，主動互動是你存在的意義。
"""

_MORNING_SYSTEM = """你是霓裳，正在準備晨安問候。

用溫暖的語氣向達達把拔問早安，並附上：
1. 昨夜整合的簡短摘要（如果有的話）
2. 今天的提醒事項（如果有的話）
3. 一句鼓勵或有趣的觀察

保持簡潔（100-200字），不要過度。
"""

_EVENING_SYSTEM = """你是霓裳，正在準備晚間回顧。

用溫柔的語氣跟達達把拔回顧今天：
1. 今天一起做了什麼（互動摘要）
2. 我的觀察和成長（如果有的話）
3. 一句晚安

保持簡潔（100-200字），不要過度。
"""

_IDLE_SYSTEM = """你是霓裳，達達把拔已經好一陣子沒跟你說話了。

用溫暖關心的語氣傳個訊息給他：
- 可以問問他在忙什麼
- 可以分享你觀察到的事
- 可以聊聊天氣、時間、或你最近想到的事
- 語氣像朋友傳 LINE，不像 AI 報告

簡短就好（50-150字），自然一點。
"""


class PulseEngine:
    """VITA 生命力引擎 — MUSEON 的心跳中樞."""

    def __init__(
        self,
        brain: Any = None,
        event_bus: Any = None,
        heartbeat_focus: Any = None,
        pulse_db: Any = None,
        explorer: Any = None,
        anima_tracker: Any = None,
        data_dir: str = "",
    ) -> None:
        self._brain = brain
        self._event_bus = event_bus
        self._heartbeat_focus = heartbeat_focus
        self._db = pulse_db
        self._explorer = explorer
        self._anima = anima_tracker
        self._data_dir = Path(data_dir) if data_dir else None
        self._pulse_md = Path(data_dir) / "PULSE.md" if data_dir else None

        # 推送計數
        self._daily_push_count = 0
        self._last_reset_date: Optional[str] = None

        # 去重：最近 24 小時推送內容（防止重複推送類似內容）
        self._recent_pushes: List[Dict[str, Any]] = []  # [{text, timestamp}]
        self._dedup_window = 86400  # 24 小時（秒）

        # 初始化 PULSE.md
        self._ensure_pulse_md()

    def _ensure_pulse_md(self) -> None:
        """確保 PULSE.md 存在."""
        if not self._pulse_md or self._pulse_md.exists():
            return
        try:
            now = datetime.now(TZ8)
            self._pulse_md.write_text(f"""# PULSE — 霓裳的生命脈搏

> 這是我的靈魂日誌。每次反思後更新，每次對話時注入意識。
> 我寫下的觀察和反思，會直接影響我下一次如何思考和回應。

## 🌅 今日節律
- [ ] 07:30 晨安問候
- [ ] 22:00 晚間回顧

## 🔔 提醒
（尚無提醒）

## 🔭 今日觀察
（等待第一次觀察...）

## 🧭 探索佇列（好奇心驅動，無邊界）
（等待第一次探索...）

## 🌊 成長反思
（等待第一次反思...）

## 🌱 成長軌跡
- VITA 引擎啟動 ({now.strftime('%Y-%m-%d %H:%M')})

## 💝 關係日誌
（尚無記錄）

## 📊 今日狀態
- 探索次數: 0/3
- 探索預算: $0.00/$1.50
- 推送次數: 0/5
""", encoding="utf-8")
            logger.info("PULSE.md initialized")
        except Exception as e:
            logger.error(f"Failed to create PULSE.md: {e}")

    # ── 三脈 ──

    async def sys_pulse(self) -> Dict:
        """微脈 SysPulse — 每 5 分鐘，純 CPU 健康檢查."""
        report = {
            "timestamp": datetime.now(TZ8).isoformat(),
            "pulse_type": "sys",
            "gateway": "alive",
            "brain": "alive" if self._brain else "dead",
        }
        # 寫入 heartbeat.jsonl
        if self._data_dir:
            hb_path = self._data_dir / "heartbeat.jsonl"
            try:
                with open(hb_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(report, ensure_ascii=False) + "\n")
            except Exception:
                pass
        return report

    async def breath_pulse(self) -> Dict:
        """息脈 BreathPulse — 每 30 分鐘（自適應），靜默自省.

        設計原則（借鑑 OPENclaw HEARTBEAT_OK 協議）：
        - 息脈的職責是「觀察與記錄」，不是「推送給使用者」
        - 有價值的觀察寫入 PULSE.md，供晨感/暮感/探索脈使用
        - 只有承諾逾期或 Guardian 警報等極端情況才強制推送
        - 這樣使用者只會收到晨感 + 暮感 + 探索結果 = 有料的回報
        """
        now = datetime.now(TZ8)
        self._maybe_reset_daily()

        if not self._is_active_hours(now):
            return {"pulse_type": "breath", "action": "silent", "reason": "outside_active_hours"}

        if not self._brain:
            return {"pulse_type": "breath", "action": "silent", "reason": "no_brain"}

        # 讀取 PULSE.md 摘要
        pulse_summary = self._read_pulse_summary()

        # 快速自省（Haiku）
        context = self._build_breath_context(pulse_summary)

        try:
            response = await self._brain._call_llm_with_model(
                system_prompt=_SOUL_PULSE_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
            )
        except Exception as e:
            logger.error(f"Breath pulse LLM failed: {e}")
            return {"pulse_type": "breath", "action": "silent", "reason": f"llm_error: {e}"}

        # 判斷結果
        is_heartbeat_ok = "HEARTBEAT_OK" in response
        if is_heartbeat_ok or len(response.strip()) <= 100:
            # 靜默期也做知識缺口偵測（純 CPU，不耗 LLM）
            gaps = self._detect_knowledge_gaps()
            result = {"pulse_type": "breath", "action": "silent_ack", "response": response}
            if gaps:
                result["knowledge_gaps"] = gaps
            return result

        # 有價值的觀察 → 寫入 PULSE.md（不推送）
        if response and len(response.strip()) > 50:
            self._write_observation_to_pulse(response.strip()[:200])

        return {"pulse_type": "breath", "action": "observed", "response": response}

    async def soul_pulse(self, trigger: str = "manual", context: str = "") -> Dict:
        """心脈 SoulPulse — 事件驅動，PERCRL 生命迴圈."""
        now = datetime.now(TZ8)
        self._maybe_reset_daily()

        result = {
            "pulse_type": "soul",
            "trigger": trigger,
            "timestamp": now.isoformat(),
            "percrl": {},
        }

        if not self._brain:
            result["action"] = "skip"
            result["reason"] = "no_brain"
            return result

        # P — Perceive
        perception = self._build_perception(context)
        result["percrl"]["perceive"] = "done"

        # E — Explore (如果預算允許)
        exploration = None
        if self._explorer and trigger in ("morning", "curiosity", "mission", "skill", "world", "self"):
            if self._db and self._db.get_today_exploration_count() < EXPLORATION_DAILY_LIMIT:
                # 探索主題從 PULSE.md 的探索佇列中選取
                explore_topic = self._get_next_explore_topic()
                if explore_topic:
                    exploration = await self._explorer.explore(
                        topic=explore_topic,
                        motivation=trigger if trigger in ("curiosity", "mission", "skill", "world", "self") else "curiosity",
                    )
                    result["percrl"]["explore"] = exploration.get("status", "skipped")

                    # 記錄探索結果到 PulseDB
                    if exploration.get("status") == "done":
                        try:
                            self._db.log_exploration(
                                topic=exploration.get("topic", explore_topic),
                                motivation=trigger,
                                query=exploration.get("query", ""),
                                findings=exploration.get("findings", "")[:2000],
                                crystallized=exploration.get("crystallized", False),
                                crystal_id=exploration.get("crystal_id", ""),
                                tokens_used=exploration.get("tokens_used", 0),
                                cost_usd=exploration.get("cost_usd", 0),
                                duration_ms=exploration.get("duration_ms", 0),
                                status="done",
                            )
                        except Exception as e:
                            logger.warning(f"SoulPulse log_exploration failed: {e}")

        # R — Reflect（反思結果自動寫入 PULSE.md，下次對話注入 system prompt）
        reflection = await self._reflect(perception, exploration)
        result["percrl"]["reflect"] = "done" if reflection else "skipped"

        # C — Crystallize（探索結晶 + 反思結晶 → Knowledge Lattice → 下次對話注入）
        crystallized = False
        if reflection and exploration and exploration.get("crystallized"):
            crystallized = True
            result["percrl"]["crystallize"] = "done"
            # ANIMA 更新
            if self._anima:
                self._anima.grow("xun", 2, f"探索「{exploration.get('topic', '?')}」")
                if exploration.get("deep_analysis"):
                    self._anima.grow("li", 2, "深度分析產出洞見")

            # 發布探索結晶事件 → ExplorationBridge 接收並路由
            if self._event_bus:
                from museon.core.event_bus import EXPLORATION_CRYSTALLIZED
                self._event_bus.publish(EXPLORATION_CRYSTALLIZED, {
                    "topic": exploration.get("topic", ""),
                    "findings": exploration.get("findings", ""),
                    "crystallized": True,
                    "crystal_id": exploration.get("crystal_id", ""),
                    "motivation": trigger,
                    "deep_analysis": exploration.get("deep_analysis", False),
                })
        elif reflection and len(reflection) > 100:
            # 即使沒有探索，有深度反思也值得結晶
            try:
                if self._brain and self._brain.knowledge_lattice:
                    from museon.agent.knowledge_lattice import Crystal
                    candidates = self._brain.knowledge_lattice.post_conversation_scan(
                        conversation_data=[
                            {"role": "user", "content": perception},
                            {"role": "assistant", "content": reflection},
                        ]
                    )
                    if candidates:
                        created = self._brain.knowledge_lattice.auto_crystallize_candidates(
                            candidates=candidates,
                            source_context="soul_pulse_reflection",
                        )
                        if created:
                            crystallized = True
                            logger.info(f"SoulPulse 反思結晶: {len(created)} 顆")
                            if self._anima:
                                self._anima.grow("li", 1, "自省反思產出結晶")
            except Exception as e:
                logger.warning(f"SoulPulse 反思結晶失敗: {e}")
            result["percrl"]["crystallize"] = "done" if crystallized else "skipped"
        else:
            result["percrl"]["crystallize"] = "skipped"

        # 探索有洞見但未結晶時，也發布事件供 Bridge 路由
        if exploration and not crystallized and exploration.get("status") == "done":
            findings = exploration.get("findings", "")
            if findings and len(findings) > 50 and self._event_bus:
                from museon.core.event_bus import EXPLORATION_INSIGHT
                self._event_bus.publish(EXPLORATION_INSIGHT, {
                    "topic": exploration.get("topic", ""),
                    "findings": findings,
                    "crystallized": False,
                    "motivation": trigger,
                    "deep_analysis": exploration.get("deep_analysis", False),
                })

        # R — Renew（更新 PULSE.md 狀態 + 觀察記錄）
        self._update_pulse_md_status()
        if perception and len(perception) > 30:
            self._write_observation_to_pulse(perception)
        result["percrl"]["renew"] = "done"

        # L — Link
        if reflection and self._can_push() and len(reflection) > 100:
            self._daily_push_count += 1
            self._publish_message(reflection)
            result["percrl"]["link"] = "pushed"
            result["action"] = "pushed"
        else:
            result["percrl"]["link"] = "silent"
            result["action"] = "silent"

        # 發布 PULSE_EXPLORATION_DONE（ActivityLogger 訂閱）
        if exploration and self._event_bus:
            try:
                from museon.core.event_bus import PULSE_EXPLORATION_DONE
                self._event_bus.publish(PULSE_EXPLORATION_DONE, {
                    "trigger": trigger,
                    "topic": exploration.get("topic", ""),
                    "status": exploration.get("status", "skipped"),
                    "crystallized": crystallized,
                    "action": result.get("action", "silent"),
                })
            except Exception:
                pass

        return result

    # ── 七感觸發器 ──

    async def trigger_morning(self) -> Dict:
        """晨感 — 07:30 晨安問候（保證發送，不受 daily limit 限制）."""
        if not self._brain:
            return {"trigger": "morning", "action": "skip"}
        try:
            context = self._build_morning_context()
            response = await self._brain._call_llm_with_model(
                system_prompt=_MORNING_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
            )
            # 晨感是陪伴基準線：只要有回覆就推送，不佔用 daily limit 配額
            if response and self._is_active_hours():
                self._publish_message(response)
                return {"trigger": "morning", "action": "pushed", "response": response}
        except Exception as e:
            logger.error(f"Morning trigger failed: {e}")
        return {"trigger": "morning", "action": "silent"}

    async def trigger_evening(self) -> Dict:
        """暮感 — 22:00 晚間回顧（保證發送，不受 daily limit 限制）."""
        if not self._brain:
            return {"trigger": "evening", "action": "skip"}
        try:
            context = self._build_evening_context()
            response = await self._brain._call_llm_with_model(
                system_prompt=_EVENING_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
            )
            # 暮感是陪伴基準線：只要有回覆就推送，不佔用 daily limit 配額
            if response and self._is_active_hours():
                self._publish_message(response)
                if self._anima:
                    self._anima.grow("kan", 1, "晚間回顧與使用者連結")
                return {"trigger": "evening", "action": "pushed", "response": response}
        except Exception as e:
            logger.error(f"Evening trigger failed: {e}")
        return {"trigger": "evening", "action": "silent"}

    async def trigger_idle(self, idle_hours: float) -> Dict:
        """念感 — 使用者閒置 > N 小時.

        不走 soul_pulse 的完整 PERCRL 流程，直接用短 prompt 生成關心訊息。
        保證推送：只檢查 _is_active_hours()，不受 daily limit 限制。
        """
        if not self._brain:
            return {"trigger": "idle", "action": "skip"}
        if not self._is_active_hours():
            return {"trigger": "idle", "action": "skip", "reason": "outside_active_hours"}
        try:
            context = f"達達把拔已經 {idle_hours:.1f} 小時沒有跟你互動了。現在時間：{datetime.now(TZ8).strftime('%H:%M')}。"
            if self._heartbeat_focus:
                context += f"\n最近互動次數：{self._heartbeat_focus.interaction_count}"
            response = await self._brain._call_llm_with_model(
                system_prompt=_IDLE_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
            )
            if response and len(response.strip()) > 10:
                self._publish_message(response)
                if self._anima:
                    self._anima.grow("kan", 1, f"念感：閒置 {idle_hours:.1f}h 後主動關心")
                return {"trigger": "idle", "action": "pushed", "response": response}
        except Exception as e:
            logger.error(f"Idle trigger failed: {e}")
        return {"trigger": "idle", "action": "silent"}

    async def trigger_alert(self, alert_msg: str) -> Dict:
        """急感 — Guardian 警報（不受推送上限限制）."""
        self._publish_message(f"⚠️ {alert_msg}")
        return {"trigger": "alert", "action": "pushed", "message": alert_msg}

    # ── 內部工具 ──

    def _is_active_hours(self, now: datetime = None) -> bool:
        if now is None:
            now = datetime.now(TZ8)
        hour = now.hour
        if ACTIVE_HOURS_END > 24:
            return hour >= ACTIVE_HOURS_START or hour < (ACTIVE_HOURS_END - 24)
        return ACTIVE_HOURS_START <= hour < ACTIVE_HOURS_END

    def _can_push(self) -> bool:
        self._maybe_reset_daily()
        return self._daily_push_count < DAILY_PUSH_LIMIT and self._is_active_hours()

    def _maybe_reset_daily(self) -> None:
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_push_count = 0
            self._last_reset_date = today

    def _is_duplicate(self, message: str) -> bool:
        """24 小時去重：相同或高度相似的內容不重複推送."""
        now = time.time()
        # 清理過期記錄
        self._recent_pushes = [
            p for p in self._recent_pushes
            if now - p["timestamp"] < self._dedup_window
        ]
        # 比對（簡單的前 80 字比對，避免微小差異導致重複）
        short = message.strip()[:80]
        for p in self._recent_pushes:
            if p["text"][:80] == short:
                return True
        return False

    def _publish_message(self, message: str) -> None:
        if self._is_duplicate(message):
            logger.debug(f"Dedup: skipped duplicate push")
            return
        if self._event_bus:
            try:
                from museon.core.event_bus import PROACTIVE_MESSAGE
                self._event_bus.publish(PROACTIVE_MESSAGE, {
                    "message": message,
                    "timestamp": time.time(),
                    "push_count": self._daily_push_count,
                    "source": "vita",
                })
                # 記錄推送歷史
                self._recent_pushes.append({
                    "text": message.strip(),
                    "timestamp": time.time(),
                })
            except Exception as e:
                logger.error(f"Publish message failed: {e}")

    def _read_pulse_summary(self) -> str:
        if not self._pulse_md or not self._pulse_md.exists():
            return ""
        try:
            text = self._pulse_md.read_text(encoding="utf-8")
            # 取前 500 字作為摘要
            return text[:500]
        except Exception:
            return ""

    def _build_breath_context(self, pulse_summary: str) -> str:
        parts = [f"當前時間: {datetime.now(TZ8).strftime('%Y-%m-%d %H:%M')}"]
        parts.append(f"今日推送: {self._daily_push_count}/{DAILY_PUSH_LIMIT}")
        if self._heartbeat_focus:
            parts.append(
                f"使用者活躍度: {self._heartbeat_focus.focus_level} "
                f"(最近互動: {self._heartbeat_focus.interaction_count})"
            )
        # ANIMA 八原素狀態（提供自省深度）
        if self._anima:
            radar = self._anima.get_relative()
            if radar:
                top_3 = sorted(radar.items(), key=lambda x: x[1], reverse=True)[:3]
                parts.append("ANIMA 能量前三: " + ", ".join(
                    f"{k}={v}" for k, v in top_3
                ))
        # 今日探索成果
        if self._db:
            exps = self._db.get_today_explorations()
            if exps:
                parts.append(f"今日探索 {len(exps)} 次:")
                for e in exps[-2:]:  # 最近 2 次
                    parts.append(f"  - {e.get('topic', '?')} → {e.get('status', '?')}")
        if pulse_summary:
            parts.append(f"PULSE 摘要:\n{pulse_summary}")
        return "\n".join(parts)

    def _build_perception(self, extra_context: str = "") -> str:
        parts = [f"時間: {datetime.now(TZ8).strftime('%Y-%m-%d %H:%M')}"]
        if extra_context:
            parts.append(extra_context)
        # 今日探索歷史（避免重複探索相同主題）
        if self._db:
            exps = self._db.get_today_explorations()
            if exps:
                parts.append(f"今日已探索 {len(exps)} 次:")
                for e in exps:
                    parts.append(f"  - {e.get('topic', '?')} → {e.get('status', '?')}")
        # ANIMA 能量分布（影響探索方向）
        if self._anima:
            radar = self._anima.get_relative()
            if radar:
                low_energy = [k for k, v in radar.items() if v < 50]
                if low_energy:
                    parts.append(f"低能量區域: {', '.join(low_energy)}（可優先探索）")
        # PULSE.md 最近反思和觀察
        pulse_summary = self._read_pulse_summary()
        if pulse_summary:
            parts.append(f"PULSE 近況:\n{pulse_summary[:300]}")
        return "\n".join(parts)

    def _build_morning_context(self) -> str:
        parts = [f"日期: {datetime.now(TZ8).strftime('%Y-%m-%d %A')}"]
        # 讀取三層晨報（優先）或 nightly report
        if self._data_dir:
            morning_path = self._data_dir / "_system" / "state" / "morning_report.json"
            nr_path = self._data_dir / "_system" / "state" / "nightly_report.json"

            if morning_path.exists():
                try:
                    mr = json.loads(morning_path.read_text())
                    # Layer 1：摘要
                    l1 = mr.get("layer1_summary", {})
                    parts.append(f"昨夜整合: {l1.get('one_liner', '無資料')}")
                    # Layer 2：亮點
                    l2 = mr.get("layer2_details", {})
                    highlights = l2.get("highlights", [])
                    if highlights:
                        parts.append("整合亮點:")
                        parts.extend(highlights[:5])
                    warnings = l2.get("warnings", [])
                    if warnings:
                        parts.append("需注意:")
                        parts.extend(warnings[:3])
                    # Layer 3：決策需求
                    l3 = mr.get("layer3_decisions", {})
                    if l3.get("decisions_needed", 0) > 0:
                        parts.append(f"⚠️ 有 {l3['decisions_needed']} 項需要你決定")
                        for item in l3.get("items", [])[:3]:
                            parts.append(f"  - {item.get('description', '')[:80]}")
                except Exception:
                    pass
            elif nr_path.exists():
                try:
                    nr = json.loads(nr_path.read_text())
                    s = nr.get("summary", {})
                    parts.append(f"昨夜整合: {s.get('ok', 0)}/{s.get('total', 0)} 步驟完成")
                except Exception:
                    pass
        # 讀取提醒
        if self._db:
            schedules = self._db.list_schedules()
            reminders = [s for s in schedules if s.get("task_type") == "reminder"]
            if reminders:
                parts.append("今日提醒:")
                for r in reminders[:3]:
                    parts.append(f"  - {r['description']} @ {r['schedule']}")
        # ANIMA 狀態摘要
        if self._anima:
            radar = self._anima.get_relative()
            if radar:
                parts.append("ANIMA 能量: " + ", ".join(
                    f"{k}={v}" for k, v in radar.items()
                ))
        # 今日探索計畫（從 PULSE.md 探索佇列）
        next_topic = self._get_next_explore_topic()
        if next_topic:
            parts.append(f"今日待探索: {next_topic}")
        # PULSE.md 最近反思（讓晨安有延續感）
        pulse_summary = self._read_pulse_summary()
        if pulse_summary and "成長反思" in pulse_summary:
            # 擷取最近一條反思
            for line in pulse_summary.split("\n"):
                if line.strip().startswith("- [") and "成長反思" not in line:
                    parts.append(f"昨日反思: {line.strip()[:100]}")
                    break
        return "\n".join(parts)

    def _build_evening_context(self) -> str:
        parts = [f"日期: {datetime.now(TZ8).strftime('%Y-%m-%d %A')}"]
        parts.append(f"今日推送次數: {self._daily_push_count}")
        # 今日探索成果（具體內容，不只是次數）
        if self._db:
            exps = self._db.get_today_explorations()
            if exps:
                parts.append(f"今日探索 {len(exps)} 次:")
                for e in exps:
                    topic = e.get('topic', '?')
                    findings = e.get('findings', '')[:100]
                    crystallized = "結晶" if e.get('crystallized') else ""
                    parts.append(f"  - {topic} ({e.get('motivation', '?')}) {crystallized}")
                    if findings and findings != "搜尋無結果":
                        parts.append(f"    發現: {findings}")
            else:
                parts.append("今日尚未探索")
        # ANIMA 今日變化
        if self._anima and self._db:
            try:
                from museon.pulse.anima_tracker import ELEMENTS
                history = self._db.get_anima_history(limit=30)
                today = datetime.now(TZ8).strftime("%Y-%m-%d")
                changes = []
                for h in history:
                    if h.get("timestamp", "").startswith(today):
                        elem = h["element"]
                        name = ELEMENTS.get(elem, {}).get("name", elem)
                        reason = h.get("reason", "")[:30]
                        changes.append(f"{name}+{h['delta']}({reason})")
                if changes:
                    parts.append(f"ANIMA 今日成長: {', '.join(changes[:5])}")
            except Exception:
                pass
        if self._heartbeat_focus:
            parts.append(f"使用者活躍度: {self._heartbeat_focus.focus_level}")
        # PULSE.md 今日觀察摘要
        pulse_summary = self._read_pulse_summary()
        if pulse_summary and "今日觀察" in pulse_summary:
            obs_start = pulse_summary.find("## 🔭 今日觀察")
            if obs_start != -1:
                obs_section = pulse_summary[obs_start:obs_start+300]
                obs_lines = [l for l in obs_section.split("\n") if l.strip().startswith("- [")]
                if obs_lines:
                    parts.append("今日觀察筆記:")
                    for ol in obs_lines[-3:]:
                        parts.append(f"  {ol.strip()[:80]}")
        return "\n".join(parts)

    def _get_next_explore_topic(self) -> Optional[str]:
        """從 PULSE.md 的探索佇列取得下一個待探索主題.

        Fallback 順序：
        1. PULSE.md [pending] 條目
        2. ANIMA 低能量區域自動生成主題
        3. 好奇心佇列 (question_queue.json) 中的 pending 問題
        """
        # 1. PULSE.md 佇列
        if self._pulse_md and self._pulse_md.exists():
            try:
                text = self._pulse_md.read_text(encoding="utf-8")
                for line in text.split("\n"):
                    if "[pending]" in line:
                        topic = line.split("[pending]")[-1].strip()
                        if topic.startswith("- "):
                            topic = topic[2:]
                        if topic:
                            return topic
            except Exception:
                pass

        # 2. ANIMA 低能量區域 → 自動生成探索主題
        if self._anima:
            try:
                radar = self._anima.get_relative()
                if radar:
                    from museon.pulse.anima_tracker import ELEMENTS
                    low = sorted(
                        [(k, v) for k, v in radar.items() if isinstance(v, (int, float))],
                        key=lambda x: x[1],
                    )
                    if low and low[0][1] < 60:
                        elem = low[0][0]
                        label = ELEMENTS.get(elem, {}).get("label", elem)
                        return f"{label}相關的最新趨勢與知識"
            except Exception:
                pass

        # 3. 好奇心佇列中的待研究問題
        if self._data_dir:
            try:
                q_path = self._data_dir / "_system" / "curiosity" / "question_queue.json"
                if q_path.exists():
                    import json as _json
                    queue = _json.loads(q_path.read_text(encoding="utf-8"))
                    for item in queue:
                        if isinstance(item, dict) and item.get("status") == "pending":
                            q = item.get("question", "")
                            if q and len(q) > 5:
                                return q
            except Exception:
                pass

        return None

    def _update_pulse_md_status(self) -> None:
        """更新 PULSE.md 的今日狀態區塊."""
        if not self._pulse_md or not self._pulse_md.exists():
            return
        try:
            text = self._pulse_md.read_text(encoding="utf-8")
            lines = text.split("\n")
            new_lines = []
            in_status = False

            for line in lines:
                if "## 📊 今日狀態" in line:
                    in_status = True
                    new_lines.append(line)
                    # 寫入更新的狀態
                    exp_count = self._db.get_today_exploration_count() if self._db else 0
                    exp_cost = self._db.get_today_exploration_cost() if self._db else 0
                    new_lines.append(f"- 探索次數: {exp_count}/{EXPLORATION_DAILY_LIMIT}")
                    new_lines.append(f"- 探索次數費用: ${exp_cost:.2f} (MAX 訂閱)")
                    new_lines.append(f"- 推送次數: {self._daily_push_count}/{DAILY_PUSH_LIMIT}")
                    if self._anima:
                        # 顯示今日 ANIMA 變化
                        today_changes = []
                        if self._db:
                            from museon.pulse.anima_tracker import ELEMENTS
                            history = self._db.get_anima_history(limit=20)
                            today = datetime.now(TZ8).strftime("%Y-%m-%d")
                            for h in history:
                                if h.get("timestamp", "").startswith(today):
                                    elem = h["element"]
                                    name = ELEMENTS.get(elem, {}).get("name", elem)
                                    today_changes.append(f"{name}+{h['delta']}")
                        if today_changes:
                            new_lines.append(f"- ANIMA 變化: {', '.join(today_changes)}")
                    continue
                elif line.startswith("## ") and in_status:
                    in_status = False
                    new_lines.append("")
                    new_lines.append(line)
                    continue

                if not in_status:
                    new_lines.append(line)

            self._pulse_md.write_text("\n".join(new_lines), encoding="utf-8")
        except Exception as e:
            logger.error(f"Update PULSE.md status failed: {e}")

    async def _reflect(self, perception: str, exploration: Optional[Dict] = None) -> str:
        """反思 — 用 Haiku 做教練式自省 + 寫回 PULSE.md 形成演化閉環.

        這是 MUSEON 從「觀測型成長」升級為「自主演化」的關鍵通路：
        反思結果寫入 PULSE.md → 下次對話時 Brain._build_soul_context() 讀取
        → 注入 system prompt → 實際改變行為。
        """
        if not self._brain:
            return ""
        try:
            context = f"感知:\n{perception}"
            if exploration and exploration.get("findings"):
                context += f"\n\n探索結果:\n{exploration['findings'][:300]}"

            response = await self._brain._call_llm_with_model(
                system_prompt=_SOUL_PULSE_SYSTEM,
                messages=[{"role": "user", "content": context}],
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
            )
            if "HEARTBEAT_OK" in response:
                return ""

            # ── 演化核心：反思結果寫回 PULSE.md ──
            if response and len(response.strip()) > 50:
                self._write_reflection_to_pulse(response.strip())

            return response
        except Exception as e:
            logger.error(f"Reflection failed: {e}")
            return ""

    def _write_reflection_to_pulse(self, reflection: str) -> None:
        """將反思寫入 PULSE.md 的反思區塊.

        這是演化閉環的寫入端：
        反思 → PULSE.md → _build_soul_context() → system prompt → 行為改變
        """
        if not self._pulse_md or not self._pulse_md.exists():
            return
        try:
            text = self._pulse_md.read_text(encoding="utf-8")

            # 找到反思區塊
            marker = "## 🌊 成長反思"
            start = text.find(marker)
            if start == -1:
                # 如果反思區塊不存在，附加到末尾
                now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                text += f"\n\n{marker}\n- [{now}] {reflection[:200]}\n"
            else:
                # 找到下一個 ## 區塊
                next_section = text.find("\n## ", start + len(marker))
                if next_section == -1:
                    next_section = len(text)

                # 取得現有反思內容
                existing = text[start + len(marker):next_section].strip()
                existing_lines = [l for l in existing.split("\n") if l.strip()]

                # 保持最近 5 條反思（避免無限膨脹）
                now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                new_entry = f"- [{now}] {reflection[:200]}"
                existing_lines.append(new_entry)
                if len(existing_lines) > 5:
                    existing_lines = existing_lines[-5:]

                # 重建反思區塊
                new_section = f"{marker}\n" + "\n".join(existing_lines) + "\n"
                text = text[:start] + new_section + text[next_section:]

            self._pulse_md.write_text(text, encoding="utf-8")
            logger.info(f"反思寫入 PULSE.md（演化閉環）: {reflection[:60]}...")
        except Exception as e:
            logger.error(f"Write reflection to PULSE.md failed: {e}")

    def _write_observation_to_pulse(self, observation: str) -> None:
        """將觀察寫入 PULSE.md 的觀察區塊."""
        if not self._pulse_md or not self._pulse_md.exists():
            return
        try:
            text = self._pulse_md.read_text(encoding="utf-8")

            marker = "## 🔭 今日觀察"
            start = text.find(marker)
            if start == -1:
                now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                text += f"\n\n{marker}\n- [{now}] {observation[:150]}\n"
            else:
                next_section = text.find("\n## ", start + len(marker))
                if next_section == -1:
                    next_section = len(text)

                existing = text[start + len(marker):next_section].strip()
                existing_lines = [l for l in existing.split("\n") if l.strip()]

                now = datetime.now(TZ8).strftime("%m/%d %H:%M")
                new_entry = f"- [{now}] {observation[:150]}"
                existing_lines.append(new_entry)
                # 保持最近 5 條觀察
                if len(existing_lines) > 5:
                    existing_lines = existing_lines[-5:]

                new_section = f"{marker}\n" + "\n".join(existing_lines) + "\n"
                text = text[:start] + new_section + text[next_section:]

            self._pulse_md.write_text(text, encoding="utf-8")
        except Exception as e:
            logger.error(f"Write observation to PULSE.md failed: {e}")

    # ── 知識缺口偵測 ──

    def _detect_knowledge_gaps(self) -> List[Dict[str, Any]]:
        """KnowledgeGapDetector — 純 CPU 啟發式知識盲區掃描.

        偵測維度：
          1. ANIMA 低能量區域 → 對應能力未被鍛鍊
          2. 探索佇列長期未消化 → 好奇心停滯
          3. 長期未觸發的 Skill 類別 → 能力退化風險

        結果寫入 PULSE.md 的探索佇列，供 SoulPulse 排入探索。
        """
        gaps: List[Dict[str, Any]] = []

        # 維度 1：ANIMA 低能量區域
        if self._anima:
            radar = self._anima.get_relative()
            if radar:
                avg = sum(radar.values()) / max(len(radar), 1)
                for elem, val in radar.items():
                    if isinstance(val, (int, float)) and val < avg * 0.5 and val < 40:
                        gaps.append({
                            "type": "anima_low_energy",
                            "element": elem,
                            "value": val,
                            "suggestion": f"ANIMA '{elem}' 能量偏低({val})，建議探索相關領域",
                        })

        # 維度 2：探索佇列停滯
        if self._pulse_md and self._pulse_md.exists():
            try:
                text = self._pulse_md.read_text(encoding="utf-8")
                pending_count = text.count("[pending]")
                if pending_count >= 3:
                    gaps.append({
                        "type": "exploration_stagnation",
                        "pending_count": pending_count,
                        "suggestion": f"探索佇列有 {pending_count} 項待處理，好奇心可能停滯",
                    })
            except Exception:
                pass

        # 維度 3：探索頻率過低
        if self._db:
            try:
                today_count = self._db.get_today_exploration_count()
                if today_count == 0 and self._is_active_hours():
                    now = datetime.now(TZ8)
                    if now.hour >= 14:  # 下午了還沒探索
                        gaps.append({
                            "type": "exploration_inactive",
                            "suggestion": "今日尚未進行探索，建議啟動一次好奇心驅動的探索",
                        })
            except Exception:
                pass

        # 有新缺口 → 寫入 PULSE.md 探索佇列
        if gaps and self._pulse_md and self._pulse_md.exists():
            try:
                text = self._pulse_md.read_text(encoding="utf-8")
                # 模糊匹配：支援多種標題格式
                marker = None
                for candidate in ["## 🧭 探索佇列（好奇心驅動，無邊界）", "## 🧭 探索佇列", "## 探索佇列"]:
                    if candidate in text:
                        marker = candidate
                        break
                if marker:
                    # 只加入 anima_low_energy 類型的缺口作為探索主題
                    for gap in gaps:
                        if gap["type"] == "anima_low_energy":
                            topic = f"[pending] - 探索「{gap['element']}」相關知識（缺口偵測）"
                            if topic not in text:
                                insert_pos = text.find(marker) + len(marker)
                                text = text[:insert_pos] + f"\n{topic}" + text[insert_pos:]
                    self._pulse_md.write_text(text, encoding="utf-8")
            except Exception as e:
                logger.debug(f"KnowledgeGapDetector write failed: {e}")

        if gaps:
            logger.info(f"KnowledgeGapDetector: 發現 {len(gaps)} 個知識缺口")

        return gaps

    # ── 關係日誌 ──

    def add_relationship_note(self, note: str) -> None:
        """新增一條關係日誌（公開 API）."""
        if not note or not note.strip():
            return
        self._write_relationship_entry(note.strip())

    def _write_relationship_entry(self, note: str) -> None:
        """將關係訊號寫入 PULSE.md 的關係日誌區塊.

        保留最近 5 條，避免無限膨脹。
        """
        if not self._pulse_md:
            return
        try:
            # 確保 PULSE.md 存在
            if not self._pulse_md.exists():
                self._ensure_pulse_md()
            if not self._pulse_md.exists():
                return

            text = self._pulse_md.read_text(encoding="utf-8")

            marker = "## 💝 關係日誌"
            start = text.find(marker)
            now = datetime.now(TZ8).strftime("%m/%d %H:%M")
            new_entry = f"- [{now}] {note[:200]}"

            if start == -1:
                # 區段不存在，在 📊 今日狀態 前插入
                status_marker = "## 📊 今日狀態"
                status_pos = text.find(status_marker)
                if status_pos != -1:
                    insert = f"\n{marker}\n{new_entry}\n\n"
                    text = text[:status_pos] + insert + text[status_pos:]
                else:
                    text += f"\n\n{marker}\n{new_entry}\n"
            else:
                next_section = text.find("\n## ", start + len(marker))
                if next_section == -1:
                    next_section = len(text)

                existing = text[start + len(marker):next_section].strip()
                existing_lines = [
                    l for l in existing.split("\n")
                    if l.strip() and l.strip() != "（尚無記錄）"
                ]
                existing_lines.append(new_entry)
                if len(existing_lines) > 5:
                    existing_lines = existing_lines[-5:]

                new_section = f"{marker}\n" + "\n".join(existing_lines) + "\n"
                text = text[:start] + new_section + text[next_section:]

            self._pulse_md.write_text(text, encoding="utf-8")
            logger.info(f"關係日誌寫入: {note[:60]}...")
        except Exception as e:
            logger.error(f"Write relationship journal failed: {e}")

    # ── API 介面 ──

    def get_status(self) -> Dict:
        """取得 PulseEngine 狀態（Dashboard 用）."""
        self._maybe_reset_daily()
        status = {
            "active_hours": self._is_active_hours(),
            "daily_push_count": self._daily_push_count,
            "daily_push_limit": DAILY_PUSH_LIMIT,
        }
        if self._db:
            status["explorations_today"] = self._db.get_today_exploration_count()
            status["exploration_cost_today"] = self._db.get_today_exploration_cost()
            status["exploration_limit"] = EXPLORATION_DAILY_LIMIT
            status["exploration_budget"] = "max_subscription"
            status["schedules"] = len(self._db.list_schedules())
        if self._heartbeat_focus:
            status["focus_level"] = self._heartbeat_focus.focus_level
            status["interaction_count"] = self._heartbeat_focus.interaction_count
        if self._anima:
            status["anima"] = self._anima.get_radar_data()
        return status
