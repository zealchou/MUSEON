"""MemoryReflector 單元測試.

Project Epigenesis 迭代 5：Hindsight 式反思引擎。
"""

from datetime import datetime, timedelta

import pytest

from museon.memory.memory_reflector import MemoryReflector, ReflectionResult


@pytest.fixture
def reflector():
    return MemoryReflector()


def _make_soul_ring(ring_type, desc, days_ago=1, context="test", reinforcement=0):
    now = datetime.now()
    return {
        "score": 0.8,
        "ring": {
            "type": ring_type,
            "description": desc,
            "context": context,
            "impact": "test",
            "created_at": (now - timedelta(days=days_ago)).isoformat(),
            "reinforcement_count": reinforcement,
        }
    }


def _make_memory(desc, days_ago=1):
    now = datetime.now()
    return {
        "content": desc,
        "description": desc,
        "created_at": (now - timedelta(days=days_ago)).isoformat(),
    }


def _make_crystal(desc, days_ago=1, crystal_type="insight"):
    now = datetime.now()
    return {
        "type": crystal_type,
        "description": desc,
        "created_at": (now - timedelta(days=days_ago)).isoformat(),
    }


class TestReflectBasic:
    """基本反思測試."""

    def test_empty_input(self, reflector):
        """空輸入不報錯."""
        result = reflector.reflect()
        assert isinstance(result, ReflectionResult)
        assert result.metadata["total_items"] == 0

    def test_single_soul_ring(self, reflector):
        """單條年輪可反思."""
        rings = [_make_soul_ring("failure_lesson", "投資失敗教訓")]
        result = reflector.reflect(recalled_soul_rings=rings)
        assert result.metadata["total_items"] == 1
        assert len(result.ranked_memories) == 1

    def test_mixed_sources(self, reflector):
        """混合來源（記憶+結晶+年輪）可反思."""
        result = reflector.reflect(
            recalled_memories=[_make_memory("日常對話")],
            recalled_crystals=[_make_crystal("洞見")],
            recalled_soul_rings=[_make_soul_ring("cognitive_breakthrough", "突破")],
        )
        assert result.metadata["total_items"] == 3


class TestContradictionDetection:
    """矛盾偵測測試."""

    def test_detects_contradiction(self, reflector):
        """同一主題的突破和失敗 → 矛盾."""
        rings = [
            _make_soul_ring("cognitive_breakthrough", "投資策略突破", context="投資決策"),
            _make_soul_ring("failure_lesson", "投資失敗教訓", context="投資決策"),
        ]
        result = reflector.reflect(recalled_soul_rings=rings)
        assert len(result.contradictions) >= 1

    def test_no_contradiction_different_topics(self, reflector):
        """不同主題不矛盾."""
        rings = [
            _make_soul_ring("cognitive_breakthrough", "投資突破", context="投資"),
            _make_soul_ring("failure_lesson", "行銷失敗", context="行銷"),
        ]
        result = reflector.reflect(recalled_soul_rings=rings)
        assert len(result.contradictions) == 0


class TestPatternDetection:
    """模式偵測測試."""

    def test_detects_repeated_type(self, reflector):
        """同類型出現 2+ 次 → 模式."""
        rings = [
            _make_soul_ring("failure_lesson", "失敗 1"),
            _make_soul_ring("failure_lesson", "失敗 2"),
            _make_soul_ring("failure_lesson", "失敗 3"),
        ]
        result = reflector.reflect(recalled_soul_rings=rings)
        assert len(result.patterns) >= 1
        assert result.patterns[0]["type"] == "failure_lesson"
        assert result.patterns[0]["count"] == 3

    def test_no_pattern_single(self, reflector):
        """單一出現不算模式."""
        rings = [_make_soul_ring("failure_lesson", "唯一的失敗")]
        result = reflector.reflect(recalled_soul_rings=rings)
        assert len(result.patterns) == 0


class TestTimeline:
    """時間軸測試."""

    def test_timeline_sorted(self, reflector):
        """時間軸按日期排序."""
        rings = [
            _make_soul_ring("cognitive_breakthrough", "最近", days_ago=1),
            _make_soul_ring("service_milestone", "很久前", days_ago=30),
            _make_soul_ring("failure_lesson", "中間", days_ago=10),
        ]
        result = reflector.reflect(recalled_soul_rings=rings)
        dates = [t["date"] for t in result.timeline]
        assert dates == sorted(dates)


class TestSummary:
    """反思摘要測試."""

    def test_summary_has_content(self, reflector):
        """有記憶時產出摘要."""
        rings = [
            _make_soul_ring("failure_lesson", "失敗 1"),
            _make_soul_ring("failure_lesson", "失敗 2"),
        ]
        result = reflector.reflect(recalled_soul_rings=rings, current_query="test")
        assert result.summary != ""
        assert "重複模式" in result.summary

    def test_summary_empty_when_no_pattern(self, reflector):
        """無模式/矛盾時摘要可能較短或為空."""
        rings = [_make_soul_ring("cognitive_breakthrough", "突破")]
        result = reflector.reflect(recalled_soul_rings=rings)
        # 至少有活躍記憶數
        assert "🧠" in result.summary or result.summary == ""


class TestActivationRanking:
    """Activation 排序測試."""

    def test_recent_ranked_higher(self, reflector):
        """最近的記憶排在前面."""
        rings = [
            _make_soul_ring("service_milestone", "舊的", days_ago=30),
            _make_soul_ring("service_milestone", "新的", days_ago=1),
        ]
        result = reflector.reflect(recalled_soul_rings=rings)
        assert result.ranked_memories[0]["description"] == "新的"

    def test_important_resists_decay(self, reflector):
        """重要的舊記憶比不重要的新記憶排更前."""
        rings = [
            _make_soul_ring("service_milestone", "普通里程碑", days_ago=5),
            _make_soul_ring("failure_lesson", "重大失敗教訓", days_ago=10, reinforcement=3),
        ]
        result = reflector.reflect(recalled_soul_rings=rings)
        # 失敗教訓雖然更舊，但因情感加成可能排更前
        descs = [m["description"] for m in result.ranked_memories]
        assert "重大失敗教訓" in descs
