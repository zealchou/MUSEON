"""Tests for heartbeat_focus.py — 自適應焦點.

依據 THREE_LAYER_PULSE BDD Spec §4 的 BDD scenarios 驗證。
"""

import json
import time

import pytest

from museon.pulse.heartbeat_focus import (
    FOCUS_HIGH_THRESHOLD,
    FOCUS_MEDIUM_THRESHOLD,
    FOCUS_WINDOW_HOURS,
    INTERACTION_EXPIRY_HOURS,
    MAX_INTERVAL_HOURS,
    MIN_INTERVAL_HOURS,
    HeartbeatFocus,
)


# ═══════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════


class TestConstants:
    """常數驗證."""

    def test_focus_high_threshold(self):
        assert FOCUS_HIGH_THRESHOLD == 10

    def test_focus_medium_threshold(self):
        assert FOCUS_MEDIUM_THRESHOLD == 3

    def test_focus_window_hours(self):
        assert FOCUS_WINDOW_HOURS == 6

    def test_min_interval(self):
        assert MIN_INTERVAL_HOURS == 1.5

    def test_max_interval(self):
        assert MAX_INTERVAL_HOURS == 6.0


# ═══════════════════════════════════════════
# Adaptive Interval Tests
# ═══════════════════════════════════════════


class TestAdaptiveInterval:
    """自適應間隔測試（BDD Spec §4.3）."""

    def test_high_activity(self):
        """BDD: 6 小時內 12 次互動 → 1.5."""
        hf = HeartbeatFocus()
        now = time.time()
        hf._interactions = [now - i * 60 for i in range(12)]
        assert hf.compute_adaptive_interval() == 1.5

    def test_medium_activity(self):
        """BDD: 6 小時內 6 次互動 → 介於 1.5 和 6.0."""
        hf = HeartbeatFocus()
        now = time.time()
        hf._interactions = [now - i * 600 for i in range(6)]
        interval = hf.compute_adaptive_interval()
        assert 1.5 < interval < 6.0

    def test_low_activity(self):
        """BDD: 6 小時內 1 次互動 → 6.0."""
        hf = HeartbeatFocus()
        now = time.time()
        hf._interactions = [now - 100]
        assert hf.compute_adaptive_interval() == 6.0

    def test_zero_interactions(self):
        """BDD: 零互動 → 6.0."""
        hf = HeartbeatFocus()
        assert hf.compute_adaptive_interval() == 6.0

    def test_exactly_high_threshold(self):
        """BDD: 恰好 10 次互動 → 1.5."""
        hf = HeartbeatFocus()
        now = time.time()
        hf._interactions = [now - i * 60 for i in range(10)]
        assert hf.compute_adaptive_interval() == 1.5

    def test_exactly_medium_threshold(self):
        """BDD: 恰好 3 次互動 → 6.0."""
        hf = HeartbeatFocus()
        now = time.time()
        hf._interactions = [now - i * 60 for i in range(3)]
        interval = hf.compute_adaptive_interval()
        assert interval == 6.0

    def test_linear_interpolation(self):
        """BDD: 線性插值正確."""
        hf = HeartbeatFocus()
        now = time.time()
        # 中間點：(3+10)/2 = 6.5，取 7 次
        hf._interactions = [now - i * 60 for i in range(7)]
        interval = hf.compute_adaptive_interval()
        # ratio = (7-3)/(10-3) ≈ 0.571
        # expected = 6.0 - 0.571 * 4.5 ≈ 3.43
        assert 3.0 < interval < 4.0

    def test_old_interactions_excluded(self):
        """BDD: 超過 6 小時的互動不計入."""
        hf = HeartbeatFocus()
        now = time.time()
        # 全部在 7 小時前
        hf._interactions = [now - 7 * 3600 - i * 60 for i in range(15)]
        assert hf.compute_adaptive_interval() == 6.0


# ═══════════════════════════════════════════
# Record Interaction Tests
# ═══════════════════════════════════════════


class TestRecordInteraction:
    """互動記錄測試."""

    def test_record_adds_timestamp(self):
        """BDD: record_interaction() 增加當前時間戳."""
        hf = HeartbeatFocus()
        hf.record_interaction()
        assert len(hf._interactions) == 1
        assert abs(hf._interactions[0] - time.time()) < 1.0

    def test_record_updates_focus_level(self):
        """BDD: 記錄互動後重新計算 _focus_level."""
        hf = HeartbeatFocus()
        for _ in range(12):
            hf.record_interaction()
        assert hf.focus_level == "high"

    def test_expired_interactions_cleaned(self):
        """BDD: 舊於 24 小時的紀錄被清除."""
        hf = HeartbeatFocus()
        old_time = time.time() - 25 * 3600  # 25 小時前
        hf._interactions = [old_time]
        hf.record_interaction()
        # old_time 應被清除
        assert all(t > time.time() - 24 * 3600 for t in hf._interactions)

    def test_record_beat(self):
        """BDD: record_beat() 遞增 beat_count."""
        hf = HeartbeatFocus()
        hf.record_beat()
        assert hf.beat_count == 1
        hf.record_beat()
        assert hf.beat_count == 2
        assert hf._last_beat is not None


# ═══════════════════════════════════════════
# Focus Level Tests
# ═══════════════════════════════════════════


class TestFocusLevel:
    """焦點等級測試."""

    def test_default_low(self):
        """BDD: 預設 low."""
        hf = HeartbeatFocus()
        assert hf.focus_level == "low"

    def test_high_focus(self):
        """BDD: ≥10 互動 → high."""
        hf = HeartbeatFocus()
        now = time.time()
        hf._interactions = [now - i * 60 for i in range(12)]
        hf._update_focus_level()
        assert hf.focus_level == "high"

    def test_medium_focus(self):
        """BDD: 3-9 互動 → medium."""
        hf = HeartbeatFocus()
        now = time.time()
        hf._interactions = [now - i * 60 for i in range(5)]
        hf._update_focus_level()
        assert hf.focus_level == "medium"

    def test_interaction_count(self):
        """BDD: interaction_count 正確."""
        hf = HeartbeatFocus()
        now = time.time()
        hf._interactions = [now - i * 60 for i in range(5)]
        assert hf.interaction_count == 5


# ═══════════════════════════════════════════
# Persistence Tests
# ═══════════════════════════════════════════


class TestPersistence:
    """持久化測試."""

    def test_save_and_load(self, tmp_path):
        """BDD: save + load 往返正確."""
        path = str(tmp_path / "heartbeat_focus.json")

        hf1 = HeartbeatFocus(state_path=path)
        for _ in range(5):
            hf1.record_interaction()
        hf1.record_beat()

        hf2 = HeartbeatFocus(state_path=path)
        assert hf2.beat_count == 1
        assert len(hf2._interactions) == 5
        assert hf2._last_beat is not None

    def test_load_nonexistent(self, tmp_path):
        """BDD: 不存在的檔案不報錯."""
        path = str(tmp_path / "missing" / "focus.json")
        hf = HeartbeatFocus(state_path=path)
        assert hf.beat_count == 0

    def test_no_state_path(self):
        """BDD: 無 state_path 不報錯."""
        hf = HeartbeatFocus()
        hf.record_interaction()  # should not raise

    def test_state_json_schema(self, tmp_path):
        """BDD: JSON schema 正確."""
        path = str(tmp_path / "focus.json")
        hf = HeartbeatFocus(state_path=path)
        hf.record_interaction()
        hf.record_beat()

        with open(path, "r") as f:
            data = json.load(f)
        assert "beat_count" in data
        assert "last_beat" in data
        assert "interaction_count" in data
        assert "focus_level" in data
        assert "interactions" in data
