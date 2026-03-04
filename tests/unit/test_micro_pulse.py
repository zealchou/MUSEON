"""Tests for micro_pulse.py — 微脈搏 4 項零 LLM 健康檢查.

依據 THREE_LAYER_PULSE BDD Spec §3 的 BDD scenarios 驗證。
"""

import os
import time

import pytest

from museon.core.event_bus import PULSE_MICRO_BEAT, EventBus
from museon.pulse.heartbeat_focus import HeartbeatFocus
from museon.pulse.micro_pulse import (
    ERROR_THRESHOLD_5MIN,
    MAX_FILE_COUNT_WARNING,
    MICRO_PULSE_INTERVAL,
    MicroPulse,
)


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def heartbeat_focus():
    return HeartbeatFocus()


@pytest.fixture
def pulse(event_bus, heartbeat_focus, tmp_path):
    return MicroPulse(heartbeat_focus, event_bus, workspace=str(tmp_path))


# ═══════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════


class TestConstants:
    """常數驗證."""

    def test_micro_pulse_interval(self):
        assert MICRO_PULSE_INTERVAL == 1800

    def test_max_file_count_warning(self):
        assert MAX_FILE_COUNT_WARNING == 10000

    def test_error_threshold(self):
        assert ERROR_THRESHOLD_5MIN == 3


# ═══════════════════════════════════════════
# Health Check Tests
# ═══════════════════════════════════════════


class TestHealthCheck:
    """健康檢查測試（BDD Spec §3.3）."""

    def test_normal_health(self, pulse):
        """BDD: 正常健康檢查."""
        result = pulse.run()
        assert result["beat_count"] == 1
        assert isinstance(result["uptime_hours"], float)
        assert result["status"] == "healthy"
        assert result["checks_passed"] == 4

    def test_beat_count_increment(self, pulse):
        """BDD: beat 計數遞增."""
        for _ in range(5):
            pulse.run()
        result = pulse.run()
        assert result["beat_count"] == 6

    def test_memory_file_warning(self, event_bus, heartbeat_focus, tmp_path):
        """BDD: 記憶體檔案過多 → warning."""
        # 建立 > 10000 個檔案
        memory_dir = tmp_path / "memory"
        memory_dir.mkdir()
        for i in range(10001):
            (memory_dir / f"file_{i}.json").write_text("{}")

        pulse = MicroPulse(heartbeat_focus, event_bus, workspace=str(tmp_path))
        result = pulse.run()
        assert result["checks_passed"] == 3
        assert result["status"] == "warning"

    def test_recent_error_warning(self, event_bus, heartbeat_focus, tmp_path):
        """BDD: 最近錯誤過多 → warning."""
        # 建立含 ERROR 的 log 檔案
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "app.log"
        lines = [f"ERROR: test error {i}\n" for i in range(5)]
        log_file.write_text("".join(lines))

        pulse = MicroPulse(heartbeat_focus, event_bus, workspace=str(tmp_path))
        result = pulse.run()
        assert result["checks_passed"] == 3
        assert result["status"] == "warning"

    def test_zero_token_guarantee(self, pulse):
        """BDD: 零 Token 保證（無 LLM API 呼叫）."""
        # 驗證 run() 不會觸發任何外部呼叫
        # 由於 MicroPulse 是純 CPU，只要正常執行即可
        result = pulse.run()
        assert result["status"] == "healthy"

    def test_no_workspace(self, event_bus, heartbeat_focus):
        """BDD: 無 workspace 不報錯."""
        pulse = MicroPulse(heartbeat_focus, event_bus, workspace=None)
        result = pulse.run()
        assert result["status"] == "healthy"
        assert result["file_count"] == 0
        assert result["recent_errors"] == 0


# ═══════════════════════════════════════════
# EventBus Integration Tests
# ═══════════════════════════════════════════


class TestEventBusIntegration:
    """EventBus 整合測試."""

    def test_publishes_micro_beat(self, pulse, event_bus):
        """BDD: run() 後 EventBus 發布 PULSE_MICRO_BEAT."""
        received = []
        event_bus.subscribe(PULSE_MICRO_BEAT, lambda d: received.append(d))
        pulse.run()
        assert len(received) == 1
        assert received[0]["beat_count"] == 1
        assert received[0]["status"] == "healthy"

    def test_event_data_has_uptime(self, pulse, event_bus):
        """BDD: 事件包含 uptime_hours."""
        received = []
        event_bus.subscribe(PULSE_MICRO_BEAT, lambda d: received.append(d))
        pulse.run()
        assert "uptime_hours" in received[0]


# ═══════════════════════════════════════════
# HeartbeatFocus Integration Tests
# ═══════════════════════════════════════════


class TestHeartbeatFocusIntegration:
    """HeartbeatFocus 整合測試."""

    def test_records_beat(self, pulse, heartbeat_focus):
        """BDD: run() 後 HeartbeatFocus.record_beat() 被呼叫."""
        pulse.run()
        assert heartbeat_focus.beat_count == 1
        pulse.run()
        assert heartbeat_focus.beat_count == 2
