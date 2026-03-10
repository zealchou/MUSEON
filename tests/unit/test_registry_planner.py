"""Unit tests for EventPlanner & timezone utilities (Phase 4)."""

from datetime import datetime, timedelta

import pytest

from museon.registry.planner import EventPlanner, infer_timezone
from museon.registry.registry_manager import RegistryManager


@pytest.fixture
def data_dir(tmp_path):
    return str(tmp_path / "data")


@pytest.fixture
def rm(data_dir):
    return RegistryManager(data_dir=data_dir, user_id="test_user")


# ═══════════════════════════════════════
# EventPlanner
# ═══════════════════════════════════════

class TestEventPlanner:

    def test_format_reminder_message(self, rm):
        planner = EventPlanner(registry_manager=rm)
        event = {
            "title": "跟王總開會",
            "datetime_start": "2026-03-12T06:00:00",
            "location": "台北辦公室",
            "timezone": "Asia/Taipei",
        }
        msg = planner.format_reminder_message(event)
        assert "跟王總開會" in msg
        assert "台北辦公室" in msg
        assert "Asia/Taipei" in msg

    def test_format_reminder_no_location(self, rm):
        planner = EventPlanner(registry_manager=rm)
        event = {"title": "電話會議", "datetime_start": "2026-03-12T06:00:00"}
        msg = planner.format_reminder_message(event)
        assert "電話會議" in msg
        assert "📍" not in msg

    @pytest.mark.asyncio
    async def test_scan_and_remind_triggers(self, rm):
        # 建立一個即將到來的事件
        future = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        rm.add_event(
            title="測試提醒",
            datetime_start=future,
            reminder_minutes=30,
        )

        notified = []
        planner = EventPlanner(
            registry_manager=rm,
            notify_callback=lambda e: notified.append(e),
        )

        reminded = await planner.scan_and_remind()
        assert len(reminded) == 1
        assert reminded[0]["title"] == "測試提醒"
        assert len(notified) == 1

    @pytest.mark.asyncio
    async def test_scan_no_reminder_for_past(self, rm):
        past = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        rm.add_event(title="已過的事件", datetime_start=past)

        planner = EventPlanner(registry_manager=rm)
        reminded = await planner.scan_and_remind()
        assert len(reminded) == 0

    @pytest.mark.asyncio
    async def test_scan_no_double_remind(self, rm):
        future = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        eid = rm.add_event(
            title="只提醒一次",
            datetime_start=future,
            reminder_minutes=30,
        )

        planner = EventPlanner(registry_manager=rm)
        await planner.scan_and_remind()
        reminded2 = await planner.scan_and_remind()
        assert len(reminded2) == 0


# ═══════════════════════════════════════
# Timezone Utilities
# ═══════════════════════════════════════

class TestTimezone:

    def test_infer_tokyo(self):
        assert infer_timezone("東京") == "Asia/Tokyo"

    def test_infer_new_york(self):
        assert infer_timezone("紐約") == "America/New_York"

    def test_infer_taipei(self):
        assert infer_timezone("台北") == "Asia/Taipei"

    def test_infer_case_insensitive(self):
        assert infer_timezone("Tokyo") == "Asia/Tokyo"
        assert infer_timezone("LONDON") == "Europe/London"

    def test_infer_unknown_returns_none(self):
        assert infer_timezone("火星") is None
        assert infer_timezone("") is None

    def test_infer_partial_match(self):
        assert infer_timezone("東京時間下午三點") == "Asia/Tokyo"
        assert infer_timezone("在新加坡開會") == "Asia/Singapore"
