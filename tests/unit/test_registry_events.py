"""Unit tests for Registry Manager — Events & Reminders (Phase 4)."""

from datetime import datetime, timedelta

import pytest

from museon.registry.registry_manager import RegistryManager


@pytest.fixture
def data_dir(tmp_path):
    return str(tmp_path / "data")


@pytest.fixture
def m(data_dir):
    return RegistryManager(data_dir=data_dir, user_id="test_user")


# ═══════════════════════════════════════
# Events CRUD
# ═══════════════════════════════════════

class TestEvents:

    def test_add_event(self, m):
        eid = m.add_event(
            title="跟王總開會",
            datetime_start="2026-03-12T06:00:00",
            datetime_end="2026-03-12T07:00:00",
            timezone="Asia/Taipei",
            location="台北辦公室",
        )
        assert eid is not None
        assert eid.startswith("evt_")

    def test_get_event(self, m):
        eid = m.add_event(
            title="團隊站會",
            datetime_start="2026-03-10T01:00:00",
            timezone="Asia/Taipei",
            reminder_minutes=15,
        )
        event = m.get_event(eid)
        assert event is not None
        assert event["title"] == "團隊站會"
        assert event["timezone"] == "Asia/Taipei"
        assert event["status"] == "upcoming"
        assert event["reminder_minutes"] == 15
        assert event["reminder_sent"] == 0

    def test_add_event_with_recurrence(self, m):
        eid = m.add_event(
            title="每週一站會",
            datetime_start="2026-03-09T01:00:00",
            recurrence="RRULE:FREQ=WEEKLY;BYDAY=MO",
        )
        event = m.get_event(eid)
        assert event["recurrence"] == "RRULE:FREQ=WEEKLY;BYDAY=MO"

    def test_add_event_with_tokyo_timezone(self, m):
        eid = m.add_event(
            title="日本客戶視訊",
            datetime_start="2026-03-10T06:00:00",
            timezone="Asia/Tokyo",
        )
        event = m.get_event(eid)
        assert event["timezone"] == "Asia/Tokyo"

    def test_update_event_status_cancelled(self, m):
        eid = m.add_event(
            title="要取消的會議",
            datetime_start="2026-03-15T06:00:00",
        )
        result = m.update_event_status(eid, "cancelled")
        assert result is True

        event = m.get_event(eid)
        assert event["status"] == "cancelled"

    def test_query_events_by_status(self, m):
        eid1 = m.add_event(
            title="進行中", datetime_start="2026-03-10T06:00:00"
        )
        eid2 = m.add_event(
            title="已取消", datetime_start="2026-03-11T06:00:00"
        )
        m.update_event_status(eid2, "cancelled")

        upcoming = m.query_events(status="upcoming")
        assert len(upcoming) == 1
        assert upcoming[0]["title"] == "進行中"

    def test_query_events_by_date(self, m):
        m.add_event(
            title="三月事件",
            datetime_start="2026-03-15T06:00:00",
        )
        m.add_event(
            title="四月事件",
            datetime_start="2026-04-15T06:00:00",
        )

        march = m.query_events(
            date_from="2026-03-01T00:00:00",
            date_to="2026-03-31T23:59:59",
        )
        assert len(march) == 1
        assert march[0]["title"] == "三月事件"

    def test_event_pending_index(self, m):
        m.add_event(title="索引事件", datetime_start="2026-03-10T06:00:00")
        pending = m.get_pending_indexes()
        event_indexes = [p for p in pending if p["doc_type"] == "event"]
        assert len(event_indexes) == 1


# ═══════════════════════════════════════
# Reminder System
# ═══════════════════════════════════════

class TestReminders:

    def test_mark_reminder_sent(self, m):
        eid = m.add_event(
            title="要提醒的",
            datetime_start="2026-03-10T06:00:00",
        )
        m.mark_reminder_sent(eid)
        event = m.get_event(eid)
        assert event["reminder_sent"] == 1

    def test_get_upcoming_reminders(self, m):
        # 建立一個 30 分鐘後的事件
        future = (datetime.utcnow() + timedelta(minutes=20)).isoformat()
        past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        far = (datetime.utcnow() + timedelta(hours=3)).isoformat()

        m.add_event(title="即將到來", datetime_start=future)
        m.add_event(title="已過去", datetime_start=past)
        m.add_event(title="太遠了", datetime_start=far)

        reminders = m.get_upcoming_reminders(within_minutes=60)
        assert len(reminders) == 1
        assert reminders[0]["title"] == "即將到來"

    def test_no_duplicate_reminder(self, m):
        future = (datetime.utcnow() + timedelta(minutes=20)).isoformat()
        eid = m.add_event(title="只提醒一次", datetime_start=future)
        m.mark_reminder_sent(eid)

        reminders = m.get_upcoming_reminders(within_minutes=60)
        assert len(reminders) == 0
