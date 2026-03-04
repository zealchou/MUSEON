"""Tests for proactive_bridge.py — 主動互動橋接.

依據 Proactive Interaction BDD Spec 驗證。
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from museon.core.event_bus import PROACTIVE_MESSAGE, EventBus
from museon.pulse.proactive_bridge import (
    ACTIVE_HOURS_END,
    ACTIVE_HOURS_START,
    DAILY_PUSH_LIMIT,
    PROACTIVE_INTERVAL,
    SILENT_ACK_THRESHOLD,
    ProactiveBridge,
)


# ═══════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════


class TestConstants:
    """常數驗證."""

    def test_silent_ack_threshold(self):
        assert SILENT_ACK_THRESHOLD == 100

    def test_active_hours_start(self):
        assert ACTIVE_HOURS_START == 8

    def test_active_hours_end(self):
        assert ACTIVE_HOURS_END == 25  # 跨日 01:00

    def test_daily_push_limit(self):
        assert DAILY_PUSH_LIMIT == 5

    def test_proactive_interval(self):
        assert PROACTIVE_INTERVAL == 1800


# ═══════════════════════════════════════════
# Silent Ack Tests (§1)
# ═══════════════════════════════════════════


class TestSilentAck:
    """靜默確認測試."""

    def test_short_response_not_pushed(self):
        """BDD: 短回覆 ≤ 100 字元 → 不推送."""
        bridge = ProactiveBridge()
        assert not bridge.should_push("OK")
        assert not bridge.should_push("一切正常")
        assert not bridge.should_push("x" * 100)

    def test_long_response_pushed(self):
        """BDD: 長回覆 > 100 字元 → 推送."""
        bridge = ProactiveBridge()
        assert bridge.should_push("x" * 101)

    def test_empty_response_not_pushed(self):
        """BDD: 空回覆 → 不推送."""
        bridge = ProactiveBridge()
        assert not bridge.should_push("")
        assert not bridge.should_push(None)

    def test_whitespace_only_not_pushed(self):
        """BDD: 純空白 → 不推送."""
        bridge = ProactiveBridge()
        assert not bridge.should_push("   ")
        assert not bridge.should_push("\n\n\n")

    def test_exactly_threshold_not_pushed(self):
        """BDD: 恰好 100 字元 → 不推送."""
        bridge = ProactiveBridge()
        assert not bridge.should_push("x" * 100)

    def test_threshold_plus_one_pushed(self):
        """BDD: 101 字元 → 推送."""
        bridge = ProactiveBridge()
        assert bridge.should_push("x" * 101)


# ═══════════════════════════════════════════
# Active Hours Tests (§2)
# ═══════════════════════════════════════════


class TestActiveHours:
    """活躍時段測試（預設 08:00 ~ 01:00 跨日）."""

    def test_within_active_hours(self):
        """BDD: 08:00-00:59 → 活躍."""
        bridge = ProactiveBridge()
        assert bridge.is_active_hours(datetime(2026, 2, 27, 8, 0))
        assert bridge.is_active_hours(datetime(2026, 2, 27, 12, 0))
        assert bridge.is_active_hours(datetime(2026, 2, 27, 23, 59))
        assert bridge.is_active_hours(datetime(2026, 2, 27, 0, 30))

    def test_outside_active_hours(self):
        """BDD: 01:00-07:59 → 非活躍."""
        bridge = ProactiveBridge()
        assert not bridge.is_active_hours(datetime(2026, 2, 27, 1, 0))
        assert not bridge.is_active_hours(datetime(2026, 2, 27, 3, 0))
        assert not bridge.is_active_hours(datetime(2026, 2, 27, 7, 59))

    def test_custom_active_hours(self):
        """BDD: 自訂活躍時段（不跨日）."""
        bridge = ProactiveBridge()
        bridge.set_active_hours(10, 20)
        assert not bridge.is_active_hours(datetime(2026, 2, 27, 9, 0))
        assert bridge.is_active_hours(datetime(2026, 2, 27, 10, 0))
        assert bridge.is_active_hours(datetime(2026, 2, 27, 19, 59))
        assert not bridge.is_active_hours(datetime(2026, 2, 27, 20, 0))

    def test_boundary_start(self):
        """BDD: 08:00 → 活躍."""
        bridge = ProactiveBridge()
        assert bridge.is_active_hours(datetime(2026, 2, 27, 8, 0))

    def test_boundary_end_cross_midnight(self):
        """BDD: 01:00 → 非活躍（跨日邊界）."""
        bridge = ProactiveBridge()
        assert not bridge.is_active_hours(datetime(2026, 2, 27, 1, 0))

    def test_midnight_active(self):
        """BDD: 00:00 → 活躍（在跨日範圍內）."""
        bridge = ProactiveBridge()
        assert bridge.is_active_hours(datetime(2026, 2, 27, 0, 0))


# ═══════════════════════════════════════════
# Daily Push Limit Tests (§3)
# ═══════════════════════════════════════════


class TestDailyPushLimit:
    """每日推送上限測試."""

    def test_within_limit(self):
        """BDD: 未到上限 → 可推送."""
        bridge = ProactiveBridge()
        assert bridge.is_within_daily_limit()

    def test_at_limit(self):
        """BDD: 到達上限 → 不可推送."""
        bridge = ProactiveBridge()
        bridge._daily_push_count = 5
        bridge._last_reset_date = datetime.now().strftime("%Y-%m-%d")
        assert not bridge.is_within_daily_limit()

    def test_over_limit(self):
        """BDD: 超過上限 → 不可推送."""
        bridge = ProactiveBridge()
        bridge._daily_push_count = 10
        bridge._last_reset_date = datetime.now().strftime("%Y-%m-%d")
        assert not bridge.is_within_daily_limit()

    def test_daily_reset(self):
        """BDD: 隔天自動重置."""
        bridge = ProactiveBridge()
        bridge._daily_push_count = 5
        bridge._last_reset_date = "2026-01-01"  # 過去日期
        assert bridge.is_within_daily_limit()
        assert bridge._daily_push_count == 0

    def test_push_count_property(self):
        """BDD: daily_push_count 正確."""
        bridge = ProactiveBridge()
        bridge._daily_push_count = 3
        bridge._last_reset_date = datetime.now().strftime("%Y-%m-%d")
        assert bridge.daily_push_count == 3


# ═══════════════════════════════════════════
# Can Push Tests (綜合判斷)
# ═══════════════════════════════════════════


class TestCanPush:
    """綜合推送判斷測試."""

    def test_all_conditions_met(self):
        """BDD: 啟用 + 活躍時段 + 未到上限 → 可推送."""
        bridge = ProactiveBridge()
        assert bridge.can_push(datetime(2026, 2, 27, 12, 0))

    def test_disabled(self):
        """BDD: 停用 → 不可推送."""
        bridge = ProactiveBridge()
        bridge.disable()
        assert not bridge.can_push(datetime(2026, 2, 27, 12, 0))

    def test_outside_hours(self):
        """BDD: 非活躍時段 → 不可推送."""
        bridge = ProactiveBridge()
        assert not bridge.can_push(datetime(2026, 2, 27, 3, 0))

    def test_limit_reached(self):
        """BDD: 到達上限 → 不可推送."""
        bridge = ProactiveBridge()
        bridge._daily_push_count = DAILY_PUSH_LIMIT
        bridge._last_reset_date = datetime.now().strftime("%Y-%m-%d")
        assert not bridge.can_push(datetime(2026, 2, 27, 12, 0))


# ═══════════════════════════════════════════
# Proactive Think Tests (§4)
# ═══════════════════════════════════════════


class TestProactiveThink:
    """自省思考測試."""

    @pytest.mark.asyncio
    async def test_no_brain_silent(self):
        """BDD: 無 brain → 靜默."""
        bridge = ProactiveBridge(brain=None)
        result = await bridge.proactive_think()
        assert not result["pushed"]
        assert result["reason"] == "no_brain"

    @pytest.mark.asyncio
    async def test_outside_hours_silent(self):
        """BDD: 非活躍時段 → 靜默."""
        brain = MagicMock()
        bridge = ProactiveBridge(brain=brain)
        with patch("museon.pulse.proactive_bridge.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 27, 3, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = await bridge.proactive_think()
        assert not result["pushed"]
        assert result["reason"] == "outside_active_hours"

    @pytest.mark.asyncio
    async def test_limit_reached_silent(self):
        """BDD: 到達上限 → 靜默."""
        brain = MagicMock()
        bridge = ProactiveBridge(brain=brain)
        bridge._daily_push_count = DAILY_PUSH_LIMIT
        bridge._last_reset_date = datetime.now().strftime("%Y-%m-%d")
        # 確保在活躍時段
        bridge.set_active_hours(0, 24)
        result = await bridge.proactive_think()
        assert not result["pushed"]
        assert result["reason"] == "daily_limit_reached"

    @pytest.mark.asyncio
    async def test_short_response_silent_ack(self):
        """BDD: 短回覆 → 靜默確認."""
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(return_value="OK")
        bridge = ProactiveBridge(brain=brain)
        bridge.set_active_hours(0, 24)
        result = await bridge.proactive_think()
        assert not result["pushed"]
        assert result["reason"] == "silent_ack"
        assert result["response"] == "OK"

    @pytest.mark.asyncio
    async def test_long_response_pushed(self):
        """BDD: 長回覆 → 推送."""
        long_msg = "達達把拔，我注意到你最近的工作模式有些變化，" * 5
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(return_value=long_msg)
        bus = EventBus()
        bridge = ProactiveBridge(brain=brain, event_bus=bus)
        bridge.set_active_hours(0, 24)
        result = await bridge.proactive_think()
        assert result["pushed"]
        assert result["reason"] == "valuable_insight"
        assert bridge.daily_push_count == 1

    @pytest.mark.asyncio
    async def test_llm_error_silent(self):
        """BDD: LLM 呼叫失敗 → 靜默."""
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(side_effect=Exception("API down"))
        bridge = ProactiveBridge(brain=brain)
        bridge.set_active_hours(0, 24)
        result = await bridge.proactive_think()
        assert not result["pushed"]
        assert "llm_error" in result["reason"]


# ═══════════════════════════════════════════
# EventBus Integration Tests (§5)
# ═══════════════════════════════════════════


class TestEventBusIntegration:
    """EventBus 整合測試."""

    @pytest.mark.asyncio
    async def test_publishes_proactive_message(self):
        """BDD: 有價值洞察 → 發布 PROACTIVE_MESSAGE."""
        long_msg = "達達把拔，我注意到你最近的工作模式有些重大的變化，想跟你分享我的觀察和一些建議。" * 3
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(return_value=long_msg)
        bus = EventBus()
        received = []
        bus.subscribe(PROACTIVE_MESSAGE, lambda d: received.append(d))

        bridge = ProactiveBridge(brain=brain, event_bus=bus)
        bridge.set_active_hours(0, 24)
        await bridge.proactive_think()

        assert len(received) == 1
        assert received[0]["message"] == long_msg
        assert "timestamp" in received[0]
        assert received[0]["push_count"] == 1

    @pytest.mark.asyncio
    async def test_no_event_on_silent_ack(self):
        """BDD: 靜默確認 → 不發布事件."""
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(return_value="OK")
        bus = EventBus()
        received = []
        bus.subscribe(PROACTIVE_MESSAGE, lambda d: received.append(d))

        bridge = ProactiveBridge(brain=brain, event_bus=bus)
        bridge.set_active_hours(0, 24)
        await bridge.proactive_think()

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_no_event_bus_ok(self):
        """BDD: 無 event_bus → 不報錯."""
        long_msg = "這是一段有價值的洞察。" * 10
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(return_value=long_msg)
        bridge = ProactiveBridge(brain=brain, event_bus=None)
        bridge.set_active_hours(0, 24)
        result = await bridge.proactive_think()
        assert result["pushed"]


# ═══════════════════════════════════════════
# HeartbeatEngine Registration Tests (§6)
# ═══════════════════════════════════════════


class TestHeartbeatEngineRegistration:
    """HeartbeatEngine 註冊測試."""

    def test_register_with_engine(self):
        """BDD: register_with_engine() 正確註冊."""
        engine = MagicMock()
        bridge = ProactiveBridge()
        bridge.register_with_engine(engine)
        engine.register.assert_called_once()
        call_kwargs = engine.register.call_args
        assert call_kwargs[1]["task_id"] == "proactive_bridge"
        assert call_kwargs[1]["interval_seconds"] == PROACTIVE_INTERVAL


# ═══════════════════════════════════════════
# Context Hints Tests
# ═══════════════════════════════════════════


class TestContextHints:
    """上下文提示測試."""

    def test_add_context_hint(self):
        """BDD: 注入上下文提示."""
        bridge = ProactiveBridge()
        bridge.add_context_hint("待辦事項: 完成報告")
        assert len(bridge._context_hints) == 1

    @pytest.mark.asyncio
    async def test_context_hints_consumed(self):
        """BDD: 自省後清除上下文提示."""
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(return_value="OK")
        bridge = ProactiveBridge(brain=brain)
        bridge.set_active_hours(0, 24)
        bridge.add_context_hint("提示 1")
        bridge.add_context_hint("提示 2")
        await bridge.proactive_think()
        assert len(bridge._context_hints) == 0


# ═══════════════════════════════════════════
# History Tests
# ═══════════════════════════════════════════


class TestHistory:
    """歷史記錄測試."""

    @pytest.mark.asyncio
    async def test_history_recorded(self):
        """BDD: 自省結果記錄到歷史."""
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(return_value="OK")
        bridge = ProactiveBridge(brain=brain)
        bridge.set_active_hours(0, 24)
        await bridge.proactive_think()
        assert len(bridge.history) == 1
        assert bridge.history[0]["action"] == "silent"

    @pytest.mark.asyncio
    async def test_push_history(self):
        """BDD: 推送記錄到歷史."""
        long_msg = "有價值的洞察" * 20
        brain = MagicMock()
        brain._call_llm_with_model = AsyncMock(return_value=long_msg)
        bridge = ProactiveBridge(brain=brain)
        bridge.set_active_hours(0, 24)
        await bridge.proactive_think()
        assert len(bridge.history) == 1
        assert bridge.history[0]["action"] == "pushed"


# ═══════════════════════════════════════════
# Enable/Disable Tests
# ═══════════════════════════════════════════


class TestEnableDisable:
    """啟用/停用測試."""

    def test_default_enabled(self):
        """BDD: 預設啟用."""
        bridge = ProactiveBridge()
        assert bridge.enabled

    def test_disable(self):
        """BDD: 停用後不可推送."""
        bridge = ProactiveBridge()
        bridge.disable()
        assert not bridge.enabled
        assert not bridge.can_push(datetime(2026, 2, 27, 12, 0))

    def test_re_enable(self):
        """BDD: 重新啟用."""
        bridge = ProactiveBridge()
        bridge.disable()
        bridge.enable()
        assert bridge.enabled
