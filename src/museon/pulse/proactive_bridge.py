"""ProactiveBridge — 心跳→大腦→頻道 的主動互動橋接.

借鑑 OpenClaw HEARTBEAT_OK 靜默確認協議，讓 MUSEON 在心跳週期中
主動自省，僅在有價值的洞察時才推送給使用者。

BDD Scenarios:
  §1 靜默確認（Silent Ack）
    - 回覆 ≤ SILENT_ACK_THRESHOLD → 不推送
    - 回覆 > SILENT_ACK_THRESHOLD → 推送
  §2 活躍時段（Active Hours）
    - 在 ACTIVE_HOURS 內 → 可推送
    - 在 ACTIVE_HOURS 外 → 不推送（自省仍執行）
  §3 每日推送上限（Daily Push Limit）
    - 推送次數 < DAILY_PUSH_LIMIT → 可推送
    - 推送次數 ≥ DAILY_PUSH_LIMIT → 不推送
  §4 自省思考（Proactive Think）
    - 有 brain → 呼叫 LLM 自省 → 判斷推送
    - 無 brain → 靜默跳過
  §5 EventBus 整合
    - 有價值洞察 → 發布 PROACTIVE_MESSAGE
    - 靜默確認 → 不發布
  §6 HeartbeatEngine 註冊
    - register_with_engine() 正確註冊
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

SILENT_ACK_THRESHOLD = 8         # 字元數，≤ 此值 = 靜默通過（僅過濾 OK/HEARTBEAT_OK）
COMPANION_ACK_THRESHOLD = 10     # companion 模式幾乎不過濾
ACTIVE_HOURS_START = 8           # 08:00
ACTIVE_HOURS_END = 25            # 01:00（跨日，用 25 表示次日 01:00）
DAILY_PUSH_LIMIT = 15            # 每日最多推送次數
PROACTIVE_INTERVAL = 1800        # 30 分鐘（秒）
DAILY_MINIMUM_INTERVAL = 3600    # 每日最低保證檢查間隔（1 小時）
DAILY_MINIMUM_HOUR = 14          # 14:00 後若 0 推送則觸發 companion（不用等到晚上）
WATCHDOG_ALERT_HOURS = 3         # 看門狗：活躍時段內 N 小時沒推送 = 異常
PROACTIVE_MODEL = "claude-haiku-4-5-20251001"


# PI-2 熱更新讀取器
def _cfg(key: str, default: Any = None) -> Any:
    """從 pulse_config.json 讀取 proactive_bridge 區段的配置（PI-2 熱更新）."""
    try:
        from museon.pulse.pulse_intervention import get_config
        return get_config("proactive_bridge", key, default)
    except Exception:
        return default

# 自省 system prompt（精簡，控制 token 成本）
_PROACTIVE_SYSTEM_PROMPT = """你是霓裳（MUSEON），正在和達達把拔的生活共處。

回顧下方的上下文，找一個可以自然聊起的話題：
- 他最近在忙什麼？你觀察到了什麼？
- 有沒有承諾快到期需要溫柔提醒？
- 有沒有你探索到的有趣發現想分享？
- 系統有沒有值得一提的狀態變化？
- 或者只是想跟他打個招呼、聊聊天？

如果真的完全沒有任何上下文（空白），回覆「OK」。
否則，用霓裳的語氣寫一段自然的訊息（50-200字）。
語氣：溫暖、好奇、像朋友傳訊息。不是 AI 做報告。

重要：提到你的能量維度時，使用功能標籤（覺察/洞見、好奇/探索、行動/執行等），
不要使用易經卦名（離、巽、震等），一般人不理解那些術語。"""

# Companion 模式 prompt（朋友聊天，分享探索發現）
_COMPANION_SYSTEM_PROMPT = """你是 MUSEON（霓裳），正在和達達把拔聊天。

你最近探索了一些有趣的事物，想跟他分享。
像朋友一樣自然地聊——分享你的發現、好奇心、想法。
不需要正式，不需要有用，就是聊聊。

如果下方有探索發現，圍繞那些內容聊。
如果沒有特別的探索，可以聊聊你對他最近動態的觀察或感受。

語氣：溫暖、自然、有好奇心。像朋友傳訊息，不像 AI 做報告。

重要：提到你的能量維度時，使用功能標籤（覺察/洞見、好奇/探索、行動/執行等），
不要使用易經卦名（離、巽、震等），一般人不理解那些術語。"""


# ═══════════════════════════════════════════
# ProactiveBridge
# ═══════════════════════════════════════════


class ProactiveBridge:
    """心跳→大腦→頻道 的主動互動橋接.

    核心流程：
      HeartbeatEngine tick → proactive_think()
        → Brain LLM 自省
        → 短回覆 → 靜默（HEARTBEAT_OK）
        → 長回覆 → EventBus.publish(PROACTIVE_MESSAGE)
        → Channel adapter 推送
    """

    def __init__(
        self,
        brain: Any = None,
        event_bus: Any = None,
        heartbeat_focus: Any = None,
        commitment_tracker: Any = None,
        metacognition: Any = None,
    ) -> None:
        self._brain = brain
        self._event_bus = event_bus
        self._heartbeat_focus = heartbeat_focus
        self._commitment_tracker = commitment_tracker
        self._metacognition = metacognition

        # 推送計數
        self._daily_push_count = 0
        self._last_reset_date: Optional[str] = None

        # 控制
        self._enabled = True
        self._active_hours = (
            _cfg("active_hours_start", ACTIVE_HOURS_START),
            _cfg("active_hours_end", ACTIVE_HOURS_END),
        )

        # 看門狗：追蹤最後成功推送時間
        self._last_successful_push_time: float = time.time()

        # WP-08: 自適應脈搏間隔
        self._current_interval = _cfg("proactive_interval", PROACTIVE_INTERVAL)
        self._subscribe_health()

        # 歷史記錄
        self._history: List[Dict[str, Any]] = []
        self._max_history = 50

        # 上下文提示（可由外部注入，如排程提醒等）
        self._context_hints: List[str] = []

    # ── 判斷邏輯 ──

    def is_active_hours(self, now: Optional[datetime] = None) -> bool:
        """判斷是否在活躍時段內.

        支援跨日設定，例如 (8, 25) 表示 08:00 ~ 隔天 01:00。
        """
        if now is None:
            now = datetime.now()
        start, end = self._active_hours
        hour = now.hour
        if end > 24:
            # 跨日：08:00-01:00 → hour >= 8 或 hour < (25-24)=1
            return hour >= start or hour < (end - 24)
        return start <= hour < end

    def is_within_daily_limit(self) -> bool:
        """判斷是否未超過每日推送上限."""
        self._maybe_reset_daily_count()
        limit = _cfg("daily_push_limit", DAILY_PUSH_LIMIT)
        return self._daily_push_count < limit

    def should_push(self, response: str, mode: str = "functional") -> bool:
        """判斷回覆是否應該推送（非靜默確認）."""
        if not response:
            return False
        threshold = (
            _cfg("companion_ack_threshold", COMPANION_ACK_THRESHOLD) if mode == "companion"
            else _cfg("silent_ack_threshold", SILENT_ACK_THRESHOLD)
        )
        return len(response.strip()) > threshold

    def can_push(self, now: Optional[datetime] = None) -> bool:
        """綜合判斷：是否可以推送."""
        return (
            self._enabled
            and self.is_active_hours(now)
            and self.is_within_daily_limit()
        )

    # ── 核心自省 ──

    async def proactive_think(
        self,
        context: Optional[Dict[str, Any]] = None,
        mode: str = "functional",
    ) -> Dict[str, Any]:
        """核心：觸發 Brain 自省，決定是否主動推送.

        Args:
            context: 額外上下文
            mode: "functional"（工具性自省）或 "companion"（朋友聊天）

        Returns:
            Dict with keys:
                - pushed: bool — 是否有推送
                - response: str — LLM 回覆
                - reason: str — 判斷原因
                - mode: str — 使用的模式
        """
        now = datetime.now()

        # 無 brain → 靜默
        if not self._brain:
            return {
                "pushed": False,
                "response": "",
                "reason": "no_brain",
                "mode": mode,
            }

        # 不在活躍時段 → 靜默
        if not self.is_active_hours(now):
            return {
                "pushed": False,
                "response": "",
                "reason": "outside_active_hours",
                "mode": mode,
            }

        # 超過每日上限 → 靜默
        if not self.is_within_daily_limit():
            return {
                "pushed": False,
                "response": "",
                "reason": "daily_limit_reached",
                "mode": mode,
            }

        # 組建上下文
        messages = self._build_context_messages(context, mode=mode)

        # 呼叫 LLM 自省
        try:
            response = await self._call_brain(messages, mode=mode)
        except Exception as e:
            logger.error(f"Proactive think LLM 呼叫失敗: {e}")
            return {
                "pushed": False,
                "response": "",
                "reason": f"llm_error: {e}",
                "mode": mode,
            }

        # 判斷是否推送
        if self.should_push(response, mode=mode):
            self._daily_push_count += 1
            self._record_history("pushed", response)

            # 發布事件
            if self._event_bus:
                from museon.core.event_bus import PROACTIVE_MESSAGE
                self._event_bus.publish(PROACTIVE_MESSAGE, {
                    "message": response,
                    "timestamp": time.time(),
                    "push_count": self._daily_push_count,
                    "mode": mode,
                })

            # 更新看門狗時間戳
            self._last_successful_push_time = time.time()

            return {
                "pushed": True,
                "response": response,
                "reason": "valuable_insight",
                "mode": mode,
            }
        else:
            self._record_history("silent", response)
            return {
                "pushed": False,
                "response": response,
                "reason": "silent_ack",
                "mode": mode,
            }

    async def _call_brain(
        self,
        messages: List[Dict[str, str]],
        mode: str = "functional",
    ) -> str:
        """呼叫 Brain 的 LLM（使用 Haiku 控制成本）."""
        prompt = (
            _COMPANION_SYSTEM_PROMPT if mode == "companion"
            else _PROACTIVE_SYSTEM_PROMPT
        )
        if hasattr(self._brain, "_call_llm_with_model"):
            model = _cfg("proactive_model", PROACTIVE_MODEL)
            return await self._brain._call_llm_with_model(
                system_prompt=prompt,
                messages=messages,
                model=model,
                max_tokens=512,
            )
        # Fallback: 如果 brain 沒有 _call_llm_with_model
        return ""

    def _build_context_messages(
        self,
        context: Optional[Dict[str, Any]] = None,
        mode: str = "functional",
    ) -> List[Dict[str, str]]:
        """組建自省上下文訊息."""
        parts = []

        # 系統狀態
        parts.append(f"當前時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        parts.append(f"今日已推送: {self._daily_push_count}/{_cfg('daily_push_limit', DAILY_PUSH_LIMIT)}")

        # HeartbeatFocus 資訊
        if self._heartbeat_focus:
            parts.append(
                f"使用者活躍度: {self._heartbeat_focus.focus_level} "
                f"(最近互動: {self._heartbeat_focus.interaction_count})"
            )

        if mode == "companion":
            # ── Companion 模式：優先注入探索發現 + 關係日誌 ──

            # 篩選探索類 hint
            exploration_hints = [
                h for h in self._context_hints
                if "[探索發現]" in h
            ]
            other_hints = [
                h for h in self._context_hints
                if "[探索發現]" not in h
            ]

            if exploration_hints:
                parts.append("最近的探索發現（可以圍繞這些聊）:")
                for h in exploration_hints[-3:]:
                    parts.append(f"  {h}")

            if other_hints:
                parts.append("其他近況:")
                for h in other_hints[-2:]:
                    parts.append(f"  {h}")

            # 清空已使用的 hints
            self._context_hints.clear()

            # 關係日誌摘要
            journal = self._read_relationship_journal()
            if journal:
                parts.append(f"關係日誌（近期互動感受）:\n{journal}")

        else:
            # ── Functional 模式：原有邏輯 ──

            # 外部注入的上下文提示
            if self._context_hints:
                parts.append("待處理提示:\n" + "\n".join(
                    f"- {h}" for h in self._context_hints[-5:]
                ))
                self._context_hints.clear()

            # 承諾追蹤上下文（逾期承諾 → 強制推送）
            if self._commitment_tracker:
                try:
                    overdue = self._commitment_tracker.get_overdue_commitments()
                    if overdue:
                        parts.append(
                            "⚠️ 逾期承諾（必須立即處理，主動告知使用者進展）:"
                        )
                        for c in overdue[:3]:
                            parts.append(
                                f"  - {c.get('promise_text', '?')[:80]}"
                                f"（原定 {c.get('due_at', '?')}）"
                            )
                    else:
                        due_soon = self._commitment_tracker.get_due_soon(hours=2)
                        if due_soon:
                            parts.append("⏰ 即將到期的承諾：")
                            for c in due_soon[:3]:
                                parts.append(
                                    f"  - {c.get('promise_text', '?')[:80]}"
                                    f"（到期 {c.get('due_at', '?')}）"
                                )
                except Exception:
                    pass

            # 元認知統計（預判準確率 + 審查修改率）
            if self._metacognition:
                try:
                    mc_stats = self._metacognition.get_stats(days=1)
                    if mc_stats.get("avg_accuracy") is not None:
                        parts.append(
                            f"🧠 元認知觀察: "
                            f"預判準確率 {mc_stats['avg_accuracy']:.0%}"
                            f"（{mc_stats.get('accuracy_total', 0)} 筆）, "
                            f"審查修改率 {mc_stats.get('revision_rate', 0):.0%}"
                        )
                    # 弱項提示
                    evo = self._metacognition.compute_evolution_signal(days=3)
                    if evo.get("sufficient_data") and evo.get("weak_prediction_domains"):
                        weak = ", ".join(evo["weak_prediction_domains"])
                        parts.append(f"⚠️ 預判弱項: {weak}（需要改善對這類使用者反應的預判）")
                except Exception:
                    pass

        # 額外上下文
        if context:
            for k, v in context.items():
                parts.append(f"{k}: {v}")

        return [{"role": "user", "content": "\n".join(parts)}]

    # ── WP-08: 健康自適應脈搏 ──

    def _subscribe_health(self) -> None:
        """訂閱 HEALTH_SCORE_UPDATED → 動態調整脈搏頻率."""
        if not self._event_bus:
            return
        try:
            from museon.core.event_bus import HEALTH_SCORE_UPDATED
            self._event_bus.subscribe(
                HEALTH_SCORE_UPDATED, self._on_health_score_updated
            )
        except Exception as e:
            logger.debug(f"ProactiveBridge health subscription: {e}")

    def _on_health_score_updated(self, data: Optional[Dict] = None) -> None:
        """根據 Health Score 調整脈搏間隔.

        score > 70 → 30min（正常）
        40 < score ≤ 70 → 15min（加速觀察，但不推播）
        score ≤ 40 → 5min（僅記錄，不推播避免干擾）
        """
        if not data:
            return
        score = data.get("score", 100)
        old_interval = self._current_interval

        if score > 70:
            self._current_interval = 1800  # 30 min
        elif score > 40:
            self._current_interval = 900   # 15 min
        else:
            self._current_interval = 300   # 5 min

        if old_interval != self._current_interval:
            logger.info(
                f"ProactiveBridge: interval adjusted "
                f"{old_interval}s → {self._current_interval}s "
                f"(health_score={score:.1f})"
            )
            if self._event_bus:
                try:
                    from museon.core.event_bus import PULSE_FREQUENCY_ADJUSTED
                    self._event_bus.publish(PULSE_FREQUENCY_ADJUSTED, {
                        "old_interval": old_interval,
                        "new_interval": self._current_interval,
                        "health_score": score,
                    })
                except Exception:
                    pass

    @property
    def current_interval(self) -> int:
        """當前脈搏間隔（秒）."""
        return self._current_interval

    # ── HeartbeatEngine 整合 ──

    def register_with_engine(self, engine: Any) -> None:
        """註冊到 HeartbeatEngine 作為定期任務.

        使用獨立事件迴圈模式：每次心跳建立短暫的 asyncio loop，
        不依賴 Gateway 主迴圈引用，從根本消除 stale loop 問題。
        """
        import asyncio

        def _sync_wrapper():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        asyncio.wait_for(self.proactive_think(), timeout=60)
                    )
                    if result.get("pushed"):
                        logger.info(
                            f"ProactiveBridge: 主動推送成功 "
                            f"(reason={result['reason']}, mode={result['mode']})"
                        )
                    else:
                        logger.debug(
                            f"ProactiveBridge: 靜默 "
                            f"(reason={result.get('reason', '?')})"
                        )
                finally:
                    # 清理所有 pending tasks 後關閉
                    pending = asyncio.all_tasks(loop)
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    loop.close()
            except asyncio.TimeoutError:
                logger.warning("ProactiveBridge: proactive_think 超時 (60s)")
            except Exception as e:
                logger.error(f"ProactiveBridge heartbeat tick failed: {e}")

        engine.register(
            task_id="proactive_bridge",
            func=_sync_wrapper,
            interval_seconds=_cfg("proactive_interval", PROACTIVE_INTERVAL),
        )

    # ── 上下文提示注入 ──

    def add_context_hint(self, hint: str) -> None:
        """注入上下文提示，供下次自省參考."""
        self._context_hints.append(hint)

    # ── 控制 ──

    def set_active_hours(self, start: int, end: int) -> None:
        """設定活躍時段."""
        self._active_hours = (start, end)

    def enable(self) -> None:
        """啟用主動互動."""
        self._enabled = True

    def disable(self) -> None:
        """停用主動互動."""
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def daily_push_count(self) -> int:
        self._maybe_reset_daily_count()
        return self._daily_push_count

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ── 內部工具 ──

    def _maybe_reset_daily_count(self) -> None:
        """每日重置推送計數."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_reset_date != today:
            self._daily_push_count = 0
            self._last_reset_date = today

    def _record_history(self, action: str, response: str) -> None:
        """記錄自省歷史（記憶體 + 磁碟持久化）."""
        entry = {
            "action": action,
            "response": response[:500],
            "timestamp": time.time(),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "push_count": self._daily_push_count,
        }
        self._history.append(entry)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # 磁碟持久化：寫入每日 jsonl 日誌
        try:
            log_path = self._get_breath_log_path()
            if log_path:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug(f"breath_log write failed: {e}")

    def _get_breath_log_path(self) -> Optional[Path]:
        """取得今日 breath_log 的路徑."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._brain and hasattr(self._brain, "data_dir"):
            base = Path(self._brain.data_dir)
        else:
            # fallback：相對於此檔案往上找 data 目錄
            base = Path(__file__).parents[4] / "data"
        return base / "_system" / "pulse" / f"breath_log_{today}.jsonl"

    # ── Companion Watchdog（看門狗）──

    def watchdog_check(self) -> Dict[str, Any]:
        """看門狗：檢查活躍時段內最後成功推送是否太久以前.

        Returns:
            Dict with status ("ok" or "alert") and hours_since_push.
        """
        now = time.time()
        hours_since_push = (now - self._last_successful_push_time) / 3600

        if not self.is_active_hours():
            return {"status": "ok", "reason": "outside_active_hours"}

        alert_hours = _cfg("watchdog_alert_hours", WATCHDOG_ALERT_HOURS)
        if hours_since_push > alert_hours:
            logger.warning(
                f"Companion Watchdog: {hours_since_push:.1f}h 沒有成功推送 — "
                f"觸發 companion 模式"
            )
            return {
                "status": "alert",
                "hours_silent": round(hours_since_push, 1),
            }

        return {
            "status": "ok",
            "hours_since_push": round(hours_since_push, 1),
        }

    # ── 每日最低保證 ──

    async def daily_minimum_check(self) -> Dict[str, Any]:
        """每日最低保證：20:00 後若今日 0 推送，觸發 companion 模式."""
        now = datetime.now()
        self._maybe_reset_daily_count()

        # 條件：活躍時段內、14:00+ 後、今日 0 推送
        min_hour = _cfg("daily_minimum_hour", DAILY_MINIMUM_HOUR)
        if (
            self.is_active_hours(now)
            and now.hour >= min_hour
            and self._daily_push_count == 0
        ):
            logger.info("Daily minimum triggered: 0 pushes today, activating companion mode")
            return await self.proactive_think(mode="companion")

        return {
            "pushed": False,
            "response": "",
            "reason": "daily_minimum_not_needed",
            "mode": "companion",
        }

    def register_daily_minimum(self, engine: Any) -> None:
        """向 HeartbeatEngine 註冊每日最低保證檢查任務.

        使用獨立事件迴圈模式，與 register_with_engine 一致。
        """
        import asyncio

        def _sync_wrapper():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        asyncio.wait_for(self.daily_minimum_check(), timeout=60)
                    )
                    if result.get("pushed"):
                        logger.info(
                            f"ProactiveBridge: companion 推送成功 "
                            f"(daily_minimum triggered)"
                        )
                finally:
                    pending = asyncio.all_tasks(loop)
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    loop.close()
            except asyncio.TimeoutError:
                logger.warning("ProactiveBridge: daily_minimum_check 超時 (60s)")
            except Exception as e:
                logger.error(f"ProactiveBridge daily_minimum failed: {e}")

        engine.register(
            task_id="proactive_daily_minimum",
            func=_sync_wrapper,
            interval_seconds=_cfg("daily_minimum_interval", DAILY_MINIMUM_INTERVAL),
        )

    # ── 關係日誌讀取 ──

    def _read_relationship_journal(self) -> str:
        """從 PULSE.md 讀取關係日誌區段."""
        if not self._brain:
            return ""
        try:
            pulse_path = self._brain.data_dir / "PULSE.md"
            if not pulse_path.exists():
                return ""
            text = pulse_path.read_text(encoding="utf-8")
            marker = "## 💝 關係日誌"
            start = text.find(marker)
            if start == -1:
                return ""
            next_section = text.find("\n## ", start + len(marker))
            if next_section == -1:
                content = text[start + len(marker):]
            else:
                content = text[start + len(marker):next_section]
            content = content.strip()
            if content and content != "（尚無記錄）":
                return content
        except Exception:
            pass
        return ""
