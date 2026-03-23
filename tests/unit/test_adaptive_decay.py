"""AdaptiveDecay 單元測試.

Project Epigenesis 迭代 4：ACT-R 式統一衰減引擎。
"""

import math
from datetime import datetime, timedelta

import pytest

from museon.memory.adaptive_decay import (
    AdaptiveDecay,
    compute_base_level_activation,
    compute_emotional_bonus,
    DECAY_RATE,
    DORMANT_THRESHOLD,
    MIN_ACTIVATION,
)


class TestComputeBaseLevel:
    """compute_base_level_activation() 測試."""

    def test_recent_access_high_activation(self):
        """最近存取 → 高 activation."""
        result = compute_base_level_activation([0.1])  # 今天
        assert result > 0

    def test_old_access_low_activation(self):
        """久遠存取 → 低 activation."""
        result = compute_base_level_activation([365.0])  # 一年前
        recent = compute_base_level_activation([1.0])    # 昨天
        assert result < recent

    def test_multiple_access_boosts(self):
        """多次存取 → 更高 activation（頻繁使用不容易遺忘）."""
        single = compute_base_level_activation([1.0])
        multiple = compute_base_level_activation([1.0, 2.0, 3.0])
        assert multiple > single

    def test_empty_access_returns_minimum(self):
        """無存取記錄 → 最低 activation."""
        result = compute_base_level_activation([])
        assert result == MIN_ACTIVATION

    def test_emotional_bonus_adds(self):
        """情感加成提升 activation."""
        without = compute_base_level_activation([1.0], emotional_bonus=0.0)
        with_bonus = compute_base_level_activation([1.0], emotional_bonus=1.0)
        assert with_bonus - without == pytest.approx(1.0)


class TestComputeEmotionalBonus:
    """compute_emotional_bonus() 測試."""

    def test_failure_lesson_highest(self):
        """failure_lesson 加成最高."""
        failure = compute_emotional_bonus(ring_type="failure_lesson")
        milestone = compute_emotional_bonus(ring_type="service_milestone")
        assert failure > milestone

    def test_reinforcement_count_caps_at_3(self):
        """強化次數上限 3."""
        bonus_3 = compute_emotional_bonus(reinforcement_count=3)
        bonus_10 = compute_emotional_bonus(reinforcement_count=10)
        assert bonus_3 == bonus_10

    def test_combined_bonus(self):
        """組合加成."""
        bonus = compute_emotional_bonus(
            ring_type="failure_lesson",
            entry_type="reflection",
            reinforcement_count=2,
        )
        # failure_lesson(1.0) + reflection(0.5) + reinf_2(0.6) = 2.1
        assert bonus == pytest.approx(2.1)

    def test_no_bonus(self):
        """無任何加成."""
        bonus = compute_emotional_bonus()
        assert bonus == 0.0


class TestAdaptiveDecayEngine:
    """AdaptiveDecay 引擎測試."""

    def setup_method(self):
        self.engine = AdaptiveDecay()
        self.now = datetime(2026, 3, 23, 12, 0, 0)

    def test_compute_activation_recent(self):
        """最近建立的記憶有較高 activation."""
        yesterday = (self.now - timedelta(days=1)).isoformat()
        last_month = (self.now - timedelta(days=30)).isoformat()

        act_recent = self.engine.compute_activation(
            created_at=yesterday, now=self.now,
        )
        act_old = self.engine.compute_activation(
            created_at=last_month, now=self.now,
        )
        assert act_recent > act_old

    def test_compute_activation_with_accesses(self):
        """有多次存取的記憶比只有建立時間的更高."""
        created = (self.now - timedelta(days=30)).isoformat()
        accesses = [
            (self.now - timedelta(days=5)).isoformat(),
            (self.now - timedelta(days=2)).isoformat(),
        ]

        with_access = self.engine.compute_activation(
            created_at=created, access_timestamps=accesses, now=self.now,
        )
        without_access = self.engine.compute_activation(
            created_at=created, now=self.now,
        )
        assert with_access > without_access

    def test_failure_lesson_resists_decay(self):
        """failure_lesson 因情感加成而抵抗衰減."""
        old_date = (self.now - timedelta(days=90)).isoformat()

        failure = self.engine.compute_activation(
            created_at=old_date,
            ring_type="failure_lesson",
            reinforcement_count=2,
            now=self.now,
        )
        milestone = self.engine.compute_activation(
            created_at=old_date,
            ring_type="service_milestone",
            now=self.now,
        )
        assert failure > milestone

    def test_rank_by_activation(self):
        """排序正確（最近 + 高情感 → 排前面）."""
        memories = [
            {
                "id": "old_boring",
                "created_at": (self.now - timedelta(days=60)).isoformat(),
                "type": "service_milestone",
            },
            {
                "id": "recent",
                "created_at": (self.now - timedelta(days=1)).isoformat(),
                "type": "cognitive_breakthrough",
            },
            {
                "id": "old_important",
                "created_at": (self.now - timedelta(days=60)).isoformat(),
                "type": "failure_lesson",
                "reinforcement_count": 3,
            },
        ]

        ranked = self.engine.rank_by_activation(memories, now=self.now)
        assert ranked[0]["id"] == "recent"  # 最近的排第一
        assert ranked[1]["id"] == "old_important"  # 雖然舊但重要
        assert ranked[2]["id"] == "old_boring"  # 舊且不重要

    def test_classify_dormancy(self):
        """沉降分類."""
        memories = [
            {
                "id": "active",
                "created_at": (self.now - timedelta(days=1)).isoformat(),
            },
            {
                "id": "dormant",
                "created_at": (self.now - timedelta(days=365)).isoformat(),
            },
        ]

        active, dormant = self.engine.classify_dormancy(
            memories, now=self.now
        )
        # 昨天的應該是 active
        active_ids = [m["id"] for m in active]
        dormant_ids = [m["id"] for m in dormant]
        assert "active" in active_ids
        assert "dormant" in dormant_ids

    def test_classify_empty_list(self):
        """空列表不報錯."""
        active, dormant = self.engine.classify_dormancy([])
        assert active == []
        assert dormant == []

    def test_activation_added_to_dict(self):
        """rank_by_activation 在 dict 中新增 _activation 欄位."""
        memories = [{"created_at": self.now.isoformat()}]
        ranked = self.engine.rank_by_activation(memories, now=self.now)
        assert "_activation" in ranked[0]
        assert isinstance(ranked[0]["_activation"], float)
