"""AlgedonicAlert 單元測試.

測試三個核心行為：
1. 收到 ALGEDONIC_SIGNAL → 產出 PROACTIVE_MESSAGE 事件
2. 防洪機制：30 秒內同類型的第二次警報被擋下
3. 不同類型的警報各自獨立冷卻
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List
from unittest.mock import patch

import pytest

from museon.governance.algedonic_alert import AlgedonicAlert


# ─── 測試用 Fake EventBus ───


class FakeEventBus:
    """最小化假事件匯流排，記錄 subscribe 和 publish 呼叫."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable]] = {}
        self.published: List[Dict[str, Any]] = []

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    def publish(self, event_type: str, data: Any = None) -> None:
        self.published.append({"event_type": event_type, "data": data})

    def fire(self, event_type: str, data: Any = None) -> None:
        """觸發事件，呼叫所有已訂閱的 handler."""
        for handler in self._subscribers.get(event_type, []):
            handler(data)


# ─── 測試案例 ───


class TestAlgedonicAlertBasic:
    """TC-01: 收到 ALGEDONIC_SIGNAL → 產出 PROACTIVE_MESSAGE."""

    def test_publishes_proactive_message_on_signal(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        # 觸發 GOVERNANCE_ALGEDONIC_SIGNAL
        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {
                "source": "system_audit",
                "overall": "critical",
                "summary": "Test critical situation",
            },
        )

        # 應該發布了 PROACTIVE_MESSAGE
        proactive_events = [
            e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"
        ]
        assert len(proactive_events) == 1, (
            f"期望 1 個 PROACTIVE_MESSAGE，實際 {len(proactive_events)} 個"
        )

    def test_proactive_message_contains_alert_content(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {
                "source": "soul_identity_check",
                "overall": "critical",
                "summary": {"event": "SOUL_IDENTITY_TAMPERED"},
            },
        )

        proactive_events = [
            e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"
        ]
        assert len(proactive_events) == 1
        msg = proactive_events[0]["data"]["message"]

        assert "🚨" in msg, "訊息應包含警報 emoji"
        assert "soul_identity_check" in msg, "訊息應包含警報來源"
        assert "建議動作" in msg, "訊息應包含建議動作"

    def test_message_source_field_is_alert(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {"source": "gateway", "health_tier": "critical"},
        )

        proactive_events = [
            e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"
        ]
        assert proactive_events[0]["data"]["source"] == "alert"


class TestAlgedonicAlertCooldown:
    """TC-02: 防洪機制——30 秒內同類型的第二次警報被擋下."""

    def test_second_alert_same_type_within_cooldown_is_blocked(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        signal_data = {"source": "system_audit", "overall": "critical"}

        # 第一次：應該通過
        bus.fire("GOVERNANCE_ALGEDONIC_SIGNAL", signal_data)
        first_count = len([e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"])
        assert first_count == 1, "第一次警報應該推播"

        # 第二次（立即，冷卻未過）：應該被擋下
        bus.fire("GOVERNANCE_ALGEDONIC_SIGNAL", signal_data)
        second_count = len([e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"])
        assert second_count == 1, f"冷卻期內第二次警報不應推播，但 count={second_count}"

    def test_alert_passes_after_cooldown_expires(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        signal_data = {"source": "system_audit", "overall": "critical"}

        # 第一次
        bus.fire("GOVERNANCE_ALGEDONIC_SIGNAL", signal_data)

        # 模擬冷卻時間已過（直接操縱 _recent_alerts 時間戳）
        alert._recent_alerts["system_audit"] = time.time() - (AlgedonicAlert.COOLDOWN + 1)

        # 第二次（冷卻已過）：應該通過
        bus.fire("GOVERNANCE_ALGEDONIC_SIGNAL", signal_data)
        count = len([e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"])
        assert count == 2, f"冷卻後應允許再次推播，但 count={count}"


class TestAlgedonicAlertIndependentCooldown:
    """TC-03: 不同類型的警報各自獨立冷卻."""

    def test_different_sources_have_independent_cooldowns(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        # 第一個類型
        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {"source": "system_audit", "overall": "critical"},
        )

        # 第二個類型（不同來源）
        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {"source": "soul_identity_check", "overall": "critical"},
        )

        # 兩者都應該推播
        count = len([e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"])
        assert count == 2, (
            f"不同類型的警報應各自獨立，期望 2 個 PROACTIVE_MESSAGE，實際 {count} 個"
        )

    def test_same_source_blocked_different_source_passes(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        # 第一次 system_audit
        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {"source": "system_audit", "overall": "critical"},
        )
        # 第二次 system_audit（冷卻中，應被擋）
        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {"source": "system_audit", "overall": "critical"},
        )
        # gateway（不同來源，應通過）
        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {"source": "gateway", "health_tier": "critical"},
        )

        count = len([e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"])
        assert count == 2, (
            f"system_audit 第二次應被擋，gateway 應通過，期望 2 個，實際 {count} 個"
        )

    def test_health_tier_and_source_are_separate_keys(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        # 僅帶 health_tier（沒有 source）
        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {"health_tier": "CRITICAL", "symptom_count": 3},
        )
        # 帶 source
        bus.fire(
            "GOVERNANCE_ALGEDONIC_SIGNAL",
            {"source": "system_audit", "overall": "critical"},
        )

        count = len([e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"])
        assert count == 2, (
            f"health_tier 和 source 應使用不同 key，期望 2 個，實際 {count} 個"
        )


class TestAlgedonicAlertEdgeCases:
    """邊界條件測試."""

    def test_empty_data_does_not_crash(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        # 空資料不應 crash
        bus.fire("GOVERNANCE_ALGEDONIC_SIGNAL", {})
        bus.fire("GOVERNANCE_ALGEDONIC_SIGNAL", None)

        # 至少第一個應該推播
        count = len([e for e in bus.published if e["event_type"] == "PROACTIVE_MESSAGE"])
        assert count >= 1, "空資料應仍能推播"

    def test_no_event_bus_does_not_crash(self) -> None:
        # event_bus 為 None 時不應 crash
        alert = AlgedonicAlert(None)
        alert._on_algedonic({"source": "test"})  # 不應 raise

    def test_subscribes_on_init(self) -> None:
        bus = FakeEventBus()
        alert = AlgedonicAlert(bus)

        # 應該訂閱了 GOVERNANCE_ALGEDONIC_SIGNAL
        assert "GOVERNANCE_ALGEDONIC_SIGNAL" in bus._subscribers
        assert len(bus._subscribers["GOVERNANCE_ALGEDONIC_SIGNAL"]) >= 1
