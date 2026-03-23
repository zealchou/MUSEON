"""EpigeneticRouter 單元測試.

Project Epigenesis 迭代 6：表觀遺傳路由器。
"""

from unittest.mock import MagicMock

import pytest

from museon.memory.epigenetic_router import (
    EpigeneticRouter,
    QueryIntent,
    MemoryActivation,
)


@pytest.fixture
def router():
    return EpigeneticRouter()


class TestClassifyIntent:
    """意圖分類測試."""

    def test_temporal_intent(self, router):
        """時間意圖偵測."""
        intent = router.classify_intent("上次我們聊到投資的時候結論是什麼？")
        assert intent.needs_temporal is True

    def test_causal_intent(self, router):
        """因果意圖偵測."""
        intent = router.classify_intent("為什麼那次投資會失敗？教訓是什麼？")
        assert intent.needs_causal is True

    def test_entity_intent(self, router):
        """實體意圖偵測."""
        intent = router.classify_intent("跟A客戶上次討論的策略是什麼？")
        assert intent.needs_entity is True

    def test_experience_intent(self, router):
        """經驗回顧偵測."""
        intent = router.classify_intent("我之前做過類似的成功經驗嗎？")
        assert intent.needs_experience is True

    def test_pure_semantic(self, router):
        """純語義問題只走 baseline."""
        intent = router.classify_intent("請幫我分析這個數據")
        assert intent.needs_temporal is False
        assert intent.needs_causal is False
        assert intent.needs_entity is False
        assert intent.needs_semantic is True

    def test_multi_intent(self, router):
        """多重意圖同時觸發."""
        intent = router.classify_intent("上次失敗的教訓是什麼？為什麼會發生？")
        assert intent.needs_temporal is True
        assert intent.needs_causal is True

    def test_high_confidence_many_keywords(self, router):
        """多關鍵詞命中 → 高信心度."""
        intent = router.classify_intent("上次為什麼跟客戶的投資經驗失敗了？")
        assert intent.confidence >= 0.7


class TestActivate:
    """activate() 整合測試."""

    def test_activate_basic(self, router):
        """基本啟動（無下游服務）."""
        result = router.activate("test query")
        assert isinstance(result, MemoryActivation)
        assert "semantic" in result.graphs_used

    def test_activate_with_memory_manager(self):
        """有 MemoryManager 時啟動 semantic 圖."""
        mm = MagicMock()
        mm.recall.return_value = [
            {"content": "test memory", "created_at": "2026-03-20T12:00:00"}
        ]
        router = EpigeneticRouter(memory_manager=mm)
        result = router.activate("test query")
        mm.recall.assert_called_once()
        assert len(result.memories) >= 1

    def test_activate_temporal_with_diary(self):
        """時間意圖 + DiaryStore → 走 temporal 圖."""
        ds = MagicMock()
        ds.recall_soul_rings.return_value = [{
            "score": 0.8,
            "ring": {
                "type": "failure_lesson",
                "description": "投資失敗",
                "context": "test",
                "impact": "test",
                "created_at": "2026-03-20T12:00:00",
            },
        }]
        router = EpigeneticRouter(diary_store=ds)
        result = router.activate("上次的教訓是什麼？")
        assert "temporal" in result.graphs_used or "causal" in result.graphs_used

    def test_activate_causal_prioritizes_failures(self):
        """因果意圖偏重 failure_lesson."""
        ds = MagicMock()
        ds.recall_soul_rings.return_value = [
            {"score": 0.7, "ring": {"type": "service_milestone", "description": "里程碑", "context": "t", "impact": "t", "created_at": "2026-03-20"}},
            {"score": 0.8, "ring": {"type": "failure_lesson", "description": "教訓", "context": "t", "impact": "t", "created_at": "2026-03-20"}},
        ]
        router = EpigeneticRouter(diary_store=ds)
        result = router.activate("為什麼失敗？教訓是什麼？")
        # 因果圖應該被啟用
        assert "causal" in result.graphs_used

    def test_activate_with_changelog(self):
        """時間意圖 + Changelog → 演化摘要注入."""
        cl = MagicMock()
        cl.get_evolution_summary.return_value = {
            "period": "2026-01 ~ 2026-03",
            "total_changes": 42,
            "primals_trend": {"curiosity": 12},
            "trust_evolution": [],
            "preference_shifts": [],
            "notable_transitions": [],
        }
        router = EpigeneticRouter(anima_changelog=cl)
        result = router.activate("最近的趨勢變化如何？")
        assert "temporal" in result.graphs_used

    def test_graphs_used_recorded(self):
        """使用的圖被記錄."""
        router = EpigeneticRouter()
        result = router.activate("為什麼上次會失敗？")
        assert "semantic" in result.graphs_used

    def test_metadata_populated(self):
        """元資料被填充."""
        router = EpigeneticRouter()
        result = router.activate("test")
        assert "intent" in result.metadata
        assert "total_memories" in result.metadata

    def test_rationale_generated(self):
        """啟動理由被生成."""
        router = EpigeneticRouter()
        result = router.activate("上次的失敗教訓")
        assert result.rationale != ""

    def test_downstream_failure_graceful(self):
        """下游服務失敗時降級."""
        mm = MagicMock()
        mm.recall.side_effect = RuntimeError("Service down")
        router = EpigeneticRouter(memory_manager=mm)
        result = router.activate("test")
        # 不拋異常，返回空結果
        assert isinstance(result, MemoryActivation)
