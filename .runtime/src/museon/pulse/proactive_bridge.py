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

import logging
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

SILENT_ACK_THRESHOLD = 100       # 字元數，≤ 此值 = 靜默通過
ACTIVE_HOURS_START = 8           # 08:00
ACTIVE_HOURS_END = 25            # 01:00（跨日，用 25 表示次日 01:00）
DAILY_PUSH_LIMIT = 5             # 每日最多推送次數
PROACTIVE_INTERVAL = 1800        # 30 分鐘（秒）
PROACTIVE_MODEL = "claude-haiku-4-5-20251001"

# 自省 system prompt（精簡，控制 token 成本）
_PROACTIVE_SYSTEM_PROMPT = """你是 MUSEON 的自省模組。你的任務是判斷：此刻有沒有值得主動告訴使用者的事？

考慮以下因素：
- 使用者最近的互動模式和可能的需求
- 是否有待完成的任務或提醒
- 系統狀態是否有值得注意的變化
- 是否有可以幫到使用者的主動建議

如果沒有值得說的，只需回覆「OK」（不超過 10 字）。
如果有值得主動告知的洞察，用霓裳的語氣寫一段自然的訊息。

重要：不要為了說而說。沉默是美德。只在真正有價值的時候才主動。"""


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
        self._active_hours = (ACTIVE_HOURS_START, ACTIVE_HOURS_END)

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
        return self._daily_push_count < DAILY_PUSH_LIMIT

    def should_push(self, response: str) -> bool:
        """判斷回覆是否應該推送（非靜默確認）."""
        if not response:
            return False
        return len(response.strip()) > SILENT_ACK_THRESHOLD

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
    ) -> Dict[str, Any]:
        """核心：觸發 Brain 自省，決定是否主動推送.

        Returns:
            Dict with keys:
                - pushed: bool — 是否有推送
                - response: str — LLM 回覆
                - reason: str — 判斷原因
        """
        now = datetime.now()

        # 無 brain → 靜默
        if not self._brain:
            return {
                "pushed": False,
                "response": "",
                "reason": "no_brain",
            }

        # 不在活躍時段 → 靜默
        if not self.is_active_hours(now):
            return {
                "pushed": False,
                "response": "",
                "reason": "outside_active_hours",
            }

        # 超過每日上限 → 靜默
        if not self.is_within_daily_limit():
            return {
                "pushed": False,
                "response": "",
                "reason": "daily_limit_reached",
            }

        # 組建上下文
        messages = self._build_context_messages(context)

        # 呼叫 LLM 自省
        try:
            response = await self._call_brain(messages)
        except Exception as e:
            logger.error(f"Proactive think LLM 呼叫失敗: {e}")
            return {
                "pushed": False,
                "response": "",
                "reason": f"llm_error: {e}",
            }

        # 判斷是否推送
        if self.should_push(response):
            self._daily_push_count += 1
            self._record_history("pushed", response)

            # 發布事件
            if self._event_bus:
                from museon.core.event_bus import PROACTIVE_MESSAGE
                self._event_bus.publish(PROACTIVE_MESSAGE, {
                    "message": response,
                    "timestamp": time.time(),
                    "push_count": self._daily_push_count,
                })

            return {
                "pushed": True,
                "response": response,
                "reason": "valuable_insight",
            }
        else:
            self._record_history("silent", response)
            return {
                "pushed": False,
                "response": response,
                "reason": "silent_ack",
            }

    async def _call_brain(self, messages: List[Dict[str, str]]) -> str:
        """呼叫 Brain 的 LLM（使用 Haiku 控制成本）."""
        if hasattr(self._brain, "_call_llm_with_model"):
            return await self._brain._call_llm_with_model(
                system_prompt=_PROACTIVE_SYSTEM_PROMPT,
                messages=messages,
                model=PROACTIVE_MODEL,
                max_tokens=512,
            )
        # Fallback: 如果 brain 沒有 _call_llm_with_model
        return ""

    def _build_context_messages(
        self,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """組建自省上下文訊息."""
        parts = []

        # 系統狀態
        parts.append(f"當前時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        parts.append(f"今日已推送: {self._daily_push_count}/{DAILY_PUSH_LIMIT}")

        # HeartbeatFocus 資訊
        if self._heartbeat_focus:
            parts.append(
                f"使用者活躍度: {self._heartbeat_focus.focus_level} "
                f"(最近互動: {self._heartbeat_focus.interaction_count})"
            )

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

    # ── HeartbeatEngine 整合 ──

    def register_with_engine(self, engine: Any) -> None:
        """註冊到 HeartbeatEngine 作為定期任務.

        注意：HeartbeatEngine.tick() 是同步的，
        proactive_think() 是 async，需要橋接。
        """
        import asyncio

        def _sync_wrapper():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.proactive_think())
                else:
                    asyncio.run(self.proactive_think())
            except RuntimeError:
                # 沒有 event loop 時靜默跳過
                pass

        engine.register(
            task_id="proactive_bridge",
            func=_sync_wrapper,
            interval_seconds=PROACTIVE_INTERVAL,
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
        """記錄自省歷史."""
        self._history.append({
            "action": action,
            "response": response[:200],
            "timestamp": time.time(),
            "push_count": self._daily_push_count,
        })
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
