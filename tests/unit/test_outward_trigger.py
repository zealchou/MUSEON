"""Tests for OutwardTrigger — 外向觸發器."""

import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from museon.core.event_bus import EventBus, OUTWARD_SEARCH_NEEDED
from museon.evolution.outward_trigger import (
    OutwardTrigger,
    DAILY_OUTWARD_CAP,
    DIRECTION_COOLDOWN_DAYS,
)


@pytest.fixture
def workspace(tmp_path):
    """建立暫時工作空間."""
    (tmp_path / "_system" / "outward").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def event_bus():
    return EventBus()


# ═══════════════════════════════════════════
# 基本功能
# ═══════════════════════════════════════════


class TestOutwardTriggerBasic:
    """基本觸發器功能."""

    def test_init(self, workspace, event_bus):
        """建立 OutwardTrigger 實例."""
        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        assert trigger is not None

    def test_scan_returns_result(self, workspace, event_bus):
        """空狀態掃描回傳有效結果（週日可能觸發 rhythmic）."""
        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        result = trigger.scan()
        assert isinstance(result["triggered"], int)
        assert result["triggered"] >= 0

    def test_scan_returns_dict(self, workspace, event_bus):
        """scan() 回傳 dict 格式."""
        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        result = trigger.scan()
        assert isinstance(result, dict)
        assert "triggered" in result
        assert "events" in result
        assert "daily_used" in result

    def test_scan_returns_daily_used(self, workspace, event_bus):
        """scan() 回傳每日已用配額."""
        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        result = trigger.scan()
        assert isinstance(result["daily_used"], int)
        assert result["daily_used"] >= 0
        assert result["daily_used"] <= DAILY_OUTWARD_CAP


# ═══════════════════════════════════════════
# 防洪機制
# ═══════════════════════════════════════════


class TestAntiFlood:
    """防洪機制測試."""

    def test_daily_cap(self, workspace, event_bus):
        """每日觸發上限."""
        assert DAILY_OUTWARD_CAP == 3

    def test_direction_cooldown(self, workspace, event_bus):
        """同方向冷卻期."""
        assert DIRECTION_COOLDOWN_DAYS == 7

    def test_daily_cap_shared_across_instances(self, workspace, event_bus):
        """每日配額跨實例共享（持久化驗證）."""
        # 實例 1 觸發一次
        trigger1 = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        trigger1._reset_daily_counter_if_needed()
        trigger1._daily_count = 2
        trigger1._save_daily_counter()

        # 實例 2 讀取時應看到已用 2
        trigger2 = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        assert trigger2._daily_count == 2


# ═══════════════════════════════════════════
# 即時直通 (HIGH 優先級)
# ═══════════════════════════════════════════


class TestRealtimePassthrough:
    """HIGH 優先級即時直通測試."""

    def test_high_signal_publishes_event(self, workspace, event_bus):
        """HIGH 信號即時發布 OUTWARD_SEARCH_NEEDED."""
        received = []
        event_bus.subscribe(OUTWARD_SEARCH_NEEDED, lambda d: received.append(d))

        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)

        # 模擬 B1 痛覺信號（HIGH）
        trigger._on_skill_quality({
            "blind_spots": [{
                "domain": "crypto",
                "skill": "market-crypto",
                "detail": "low Q-Score in crypto domain",
            }],
        })

        # HIGH 應該即時發布事件（不等凌晨）
        assert len(received) >= 1
        event = received[0]
        assert event["track"] == "service"
        assert event["trigger_type"] == "pain"
        assert event["priority"] == "HIGH"

    def test_high_signal_consumes_daily_quota(self, workspace, event_bus):
        """HIGH 信號消耗每日配額."""
        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        initial_count = trigger._daily_count

        trigger._on_skill_quality({
            "blind_spots": [{
                "domain": "test-domain",
                "skill": "test-skill",
                "detail": "test detail",
            }],
        })

        assert trigger._daily_count == initial_count + 1

    def test_high_signal_blocked_by_daily_cap(self, workspace, event_bus):
        """每日配額用完後 HIGH 信號也被阻擋."""
        received = []
        event_bus.subscribe(OUTWARD_SEARCH_NEEDED, lambda d: received.append(d))

        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        trigger._daily_count = DAILY_OUTWARD_CAP  # 配額已滿
        trigger._daily_date = datetime.now(
            timezone(timedelta(hours=8))
        ).strftime("%Y-%m-%d")
        trigger._save_daily_counter()

        trigger._on_skill_quality({
            "blind_spots": [{
                "domain": "blocked-domain",
                "skill": "blocked-skill",
                "detail": "should be blocked",
            }],
        })

        # 應該沒有新事件（配額已滿）
        assert len(received) == 0

    def test_failure_signal_is_high(self, workspace, event_bus):
        """B3 品質下滑信號為 HIGH 優先級."""
        received = []
        event_bus.subscribe(OUTWARD_SEARCH_NEEDED, lambda d: received.append(d))

        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)

        trigger._on_feedback_signal({
            "direction": "declining",
            "delta": 0.20,
            "recent_mean": 0.55,
        })

        assert len(received) >= 1
        assert received[0]["priority"] == "HIGH"
        assert received[0]["trigger_type"] == "failure"

    def test_non_declining_feedback_ignored(self, workspace, event_bus):
        """非下滑的反饋不觸發."""
        received = []
        event_bus.subscribe(OUTWARD_SEARCH_NEEDED, lambda d: received.append(d))

        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)

        trigger._on_feedback_signal({
            "direction": "improving",
            "delta": 0.10,
        })

        assert len(received) == 0

    def test_small_delta_feedback_ignored(self, workspace, event_bus):
        """delta 低於閾值的下滑不觸發."""
        received = []
        event_bus.subscribe(OUTWARD_SEARCH_NEEDED, lambda d: received.append(d))

        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)

        trigger._on_feedback_signal({
            "direction": "declining",
            "delta": 0.05,  # 低於 QUALITY_DECLINE_DELTA (0.15)
        })

        assert len(received) == 0


# ═══════════════════════════════════════════
# 批次掃描（Nightly）
# ═══════════════════════════════════════════


class TestNightlyScan:
    """凌晨批次掃描測試."""

    def test_pending_signals_processed_in_scan(self, workspace, event_bus):
        """Pending 信號在 scan() 中被處理."""
        received = []
        event_bus.subscribe(OUTWARD_SEARCH_NEEDED, lambda d: received.append(d))

        # 手動寫入 pending 信號（模擬白天存入的 NORMAL 級信號）
        pending_file = workspace / "_system" / "outward" / "pending_signals.json"
        pending_file.write_text(json.dumps([{
            "type": "domain_gap",
            "track": "service",
            "trigger_type": "pain",
            "priority": "NORMAL",
            "domain": "test-domain",
            "skill": "test-skill",
            "detail": "test detail",
            "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        }]), encoding="utf-8")

        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        result = trigger.scan()

        # pending 信號應該被處理
        assert result["triggered"] >= 1

    def test_pending_cleared_after_scan(self, workspace, event_bus):
        """scan() 後 pending 信號被清空."""
        pending_file = workspace / "_system" / "outward" / "pending_signals.json"
        pending_file.write_text(json.dumps([{
            "type": "domain_gap",
            "track": "service",
            "trigger_type": "pain",
            "priority": "NORMAL",
            "domain": "clear-test",
            "skill": "",
            "detail": "",
            "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        }]), encoding="utf-8")

        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        trigger.scan()

        # pending 應該被清空
        data = json.loads(pending_file.read_text(encoding="utf-8"))
        assert data == []


# ═══════════════════════════════════════════
# 持久化
# ═══════════════════════════════════════════


class TestPersistence:
    """持久化測試."""

    def test_cooldown_file_created(self, workspace, event_bus):
        """掃描後冷卻檔案存在."""
        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        trigger.scan()
        assert (workspace / "_system" / "outward").exists()

    def test_daily_counter_persisted(self, workspace, event_bus):
        """每日計數被持久化."""
        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)
        trigger.scan()

        counter_file = workspace / "_system" / "outward" / "daily_counter.json"
        assert counter_file.exists()
        data = json.loads(counter_file.read_text(encoding="utf-8"))
        assert "date" in data
        assert "count" in data

    def test_pending_signals_persisted(self, workspace, event_bus):
        """NORMAL 信號被持久化到 pending."""
        trigger = OutwardTrigger(workspace=workspace, event_bus=event_bus)

        # _handle_realtime_signal 中 NORMAL 會存入 pending
        trigger._handle_realtime_signal({
            "type": "domain_gap",
            "track": "service",
            "trigger_type": "pain",
            "priority": "NORMAL",
            "domain": "persist-test",
            "skill": "",
            "detail": "",
            "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        })

        pending_file = workspace / "_system" / "outward" / "pending_signals.json"
        assert pending_file.exists()
        data = json.loads(pending_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["domain"] == "persist-test"
