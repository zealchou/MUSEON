"""Recommender 推薦引擎單元測試."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from museon.agent.recommender import (
    ACTION_WEIGHTS,
    NOVELTY_BONUS,
    RECENCY_HALF_LIFE_DAYS,
    Recommender,
)


@pytest.fixture
def workspace(tmp_path):
    """建立臨時工作空間."""
    (tmp_path / "data" / "_system" / "recommendations").mkdir(parents=True)
    return str(tmp_path)


@pytest.fixture
def mock_crystal_store():
    """模擬 CrystalStore."""
    store = MagicMock()
    store.load_crystals_raw.return_value = [
        {
            "cuid": "INS-001",
            "crystal_type": "Insight",
            "g1_summary": "系統架構的模組化設計原則",
            "g3_root_inquiry": "如何在複雜系統中保持模組獨立性",
            "tags": '["architecture", "modularity"]',
            "domain": "software_engineering",
            "ri_score": 0.85,
            "status": "active",
        },
        {
            "cuid": "PAT-002",
            "crystal_type": "Pattern",
            "g1_summary": "事件驅動架構的反模式",
            "g3_root_inquiry": "事件風暴導致的系統耦合",
            "tags": '["event-driven", "anti-pattern"]',
            "domain": "software_engineering",
            "ri_score": 0.72,
            "status": "active",
        },
        {
            "cuid": "LES-003",
            "crystal_type": "Lesson",
            "g1_summary": "投資組合的風險平衡策略",
            "g3_root_inquiry": "資產配置中的風險分散",
            "tags": '["investment", "risk"]',
            "domain": "finance",
            "ri_score": 0.60,
            "status": "active",
        },
        {
            "cuid": "ARC-004",
            "crystal_type": "Insight",
            "g1_summary": "已歸檔的過期洞見",
            "g3_root_inquiry": "",
            "tags": "[]",
            "domain": "",
            "ri_score": 0.01,
            "status": "archived",
        },
    ]
    store.load_links.return_value = [
        {"from_cuid": "INS-001", "to_cuid": "PAT-002", "link_type": "supports", "confidence": 0.9},
        {"from_cuid": "PAT-002", "to_cuid": "LES-003", "link_type": "relates", "confidence": 0.5},
    ]
    return store


@pytest.fixture
def recommender(workspace, mock_crystal_store):
    """建立 Recommender 實例."""
    return Recommender(
        workspace=workspace,
        event_bus=None,
        crystal_store=mock_crystal_store,
    )


@pytest.fixture
def recommender_no_store(workspace):
    """建立無 CrystalStore 的降級 Recommender."""
    return Recommender(workspace=workspace, crystal_store=None)


# ── 初始化測試 ──


class TestInit:
    def test_init_with_crystal_store(self, recommender, mock_crystal_store):
        """CrystalStore 注入後正常初始化."""
        assert recommender._crystal_store is mock_crystal_store
        assert recommender._interactions == []
        assert recommender._item_stats == {}

    def test_init_degraded_without_crystal_store(self, recommender_no_store):
        """無 CrystalStore 時降級運行（不拋異常）."""
        assert recommender_no_store._crystal_store is None

    def test_interactions_dir_created(self, workspace):
        """互動歷史目錄自動建立."""
        r = Recommender(workspace=workspace)
        assert r._interactions_dir.exists()

    def test_load_existing_interactions(self, workspace):
        """載入既有互動歷史."""
        interactions = [
            {"item_id": "X-001", "action": "view", "timestamp": "2026-03-20T10:00:00+08:00"},
        ]
        p = Path(workspace) / "data" / "_system" / "recommendations" / "interactions.json"
        p.write_text(json.dumps(interactions), encoding="utf-8")

        r = Recommender(workspace=workspace)
        assert len(r._interactions) == 1
        assert r._interactions[0]["item_id"] == "X-001"


# ── 內容過濾測試 ──


class TestContentFilter:
    def test_content_filter_from_crystals(self, recommender):
        """從 CrystalStore 的結晶做內容過濾."""
        context = {"keywords": ["architecture"]}
        candidates = recommender._content_filter(context)

        assert len(candidates) >= 1
        matched_ids = {c["item_id"] for c in candidates}
        assert "INS-001" in matched_ids  # g1_summary 含 architecture tag

    def test_content_filter_excludes_archived(self, recommender):
        """已歸檔結晶不在推薦結果中."""
        context = {"keywords": ["過期"]}
        candidates = recommender._content_filter(context)
        matched_ids = {c["item_id"] for c in candidates}
        assert "ARC-004" not in matched_ids

    def test_content_filter_no_context(self, recommender):
        """無上下文時回傳空列表."""
        candidates = recommender._content_filter({})
        assert candidates == []

    def test_content_filter_degraded_no_store(self, recommender_no_store):
        """無 CrystalStore 時回傳空列表（不拋異常）."""
        candidates = recommender_no_store._content_filter({"keywords": ["test"]})
        assert candidates == []

    def test_content_filter_uses_ri_score(self, recommender):
        """推薦結果的 score 使用結晶的 ri_score."""
        context = {"keywords": ["架構"]}
        candidates = recommender._content_filter(context)
        for c in candidates:
            if c["item_id"] == "INS-001":
                assert c["score"] == 0.85
                break

    def test_content_filter_matches_domain(self, recommender):
        """domain 欄位也被搜尋."""
        context = {"keywords": ["finance"]}
        candidates = recommender._content_filter(context)
        matched_ids = {c["item_id"] for c in candidates}
        assert "LES-003" in matched_ids


# ── 協同過濾測試 ──


class TestCollaborativeFilter:
    def test_collaborative_filter_from_links(self, recommender):
        """從 crystal links 做協同過濾."""
        # 先記錄互動讓 INS-001 成為高分項目
        recommender.record_interaction("INS-001", "bookmark")

        candidates = recommender._collaborative_filter({})

        # PAT-002 應該被推薦（因為 INS-001 → PAT-002 有 link）
        matched_ids = {c["item_id"] for c in candidates}
        assert "PAT-002" in matched_ids

    def test_collaborative_filter_no_interactions(self, recommender):
        """無互動歷史時回傳空列表."""
        candidates = recommender._collaborative_filter({})
        assert candidates == []

    def test_collaborative_filter_degraded_no_store(self, recommender_no_store):
        """無 CrystalStore 時回傳空列表."""
        candidates = recommender_no_store._collaborative_filter({})
        assert candidates == []


# ── 評分測試 ──


class TestScoring:
    def test_score_item_recency_decay(self, recommender):
        """近因性衰減計算正確."""
        item = {"item_id": "NEW-001", "title": "test", "score": 1.0}
        # 未見過的項目，近因性 = 1.0，新奇性 = 1.0
        score = recommender._score_item(item, {})
        assert score > 0  # 應有正分

    def test_score_novel_vs_seen(self, recommender):
        """未見過的項目分數高於見過的."""
        item_novel = {"item_id": "NOVEL", "title": "test", "score": 1.0}
        recommender.record_interaction("SEEN", "view")
        item_seen = {"item_id": "SEEN", "title": "test", "score": 1.0}

        score_novel = recommender._score_item(item_novel, {})
        score_seen = recommender._score_item(item_seen, {})
        assert score_novel > score_seen

    def test_compute_relevance_with_keywords(self, recommender):
        """關鍵字匹配計算相關性."""
        item = {"title": "Python architecture patterns", "tags": ["python", "design"]}
        context = {"keywords": ["python", "architecture"]}
        relevance = recommender._compute_relevance(item, context)
        assert relevance > 0.5  # 兩個關鍵字都匹配

    def test_compute_relevance_no_context(self, recommender):
        """無上下文時給中等分."""
        item = {"title": "test"}
        relevance = recommender._compute_relevance(item, {})
        assert relevance == 0.5


# ── 互動記錄測試 ──


class TestRecordInteraction:
    def test_record_interaction_persists(self, recommender):
        """互動記錄持久化."""
        recommender.record_interaction("INS-001", "click")
        assert len(recommender._interactions) == 1
        assert recommender._interactions[0]["action"] == "click"

        # 持久化檔案存在
        assert recommender._interactions_path.exists()
        saved = json.loads(recommender._interactions_path.read_text(encoding="utf-8"))
        assert len(saved) == 1

    def test_record_interaction_updates_stats(self, recommender):
        """互動記錄更新統計快取."""
        recommender.record_interaction("INS-001", "bookmark")
        stats = recommender._item_stats.get("INS-001")
        assert stats is not None
        assert stats["count"] == 1
        assert stats["total_score"] == ACTION_WEIGHTS["bookmark"]

    def test_record_interaction_with_rating(self, recommender):
        """顯式評分覆蓋預設權重."""
        recommender.record_interaction("INS-001", "rate", rating=0.9)
        stats = recommender._item_stats["INS-001"]
        assert stats["total_score"] == 0.9


# ── 偶然性注入測試 ──


class TestSerendipity:
    def test_serendipity_injection(self, recommender):
        """偶然性注入邏輯."""
        items = [
            {"item_id": "A", "score": 0.9, "reason": "test"},
            {"item_id": "B", "score": 0.8, "reason": "test"},
            {"item_id": "C", "score": 0.7, "reason": "test"},
        ]
        result = recommender._serendipity_injection(items, ratio=0.3)
        # 結果不少於原始項目
        assert len(result) >= len(items)

    def test_serendipity_empty_items(self, recommender):
        """空列表不拋異常."""
        result = recommender._serendipity_injection([], ratio=0.3)
        assert result == []

    def test_discover_random_items(self, recommender):
        """從 CrystalStore 隨機發現結晶."""
        items = recommender._discover_random_items(limit=2)
        assert len(items) <= 2
        for item in items:
            assert item["item_type"] == "crystal"
            assert item["score"] == NOVELTY_BONUS

    def test_discover_random_degraded(self, recommender_no_store):
        """無 CrystalStore 時回傳空列表."""
        items = recommender_no_store._discover_random_items(limit=2)
        assert items == []


# ── 整合測試 ──


class TestGetRecommendations:
    @pytest.mark.asyncio
    async def test_get_recommendations_basic(self, recommender):
        """完整推薦流程（async）."""
        result = await recommender.get_recommendations(
            user_context={"keywords": ["architecture"]},
            limit=5,
        )
        assert isinstance(result, list)
        # 應該有結果（因為 mock crystal_store 有 architecture 相關結晶）
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_get_recommendations_empty_context(self, recommender):
        """無上下文時仍可運行."""
        result = await recommender.get_recommendations(limit=5)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_recommendations_degraded(self, recommender_no_store):
        """降級模式下仍可運行（回傳空或少量結果）."""
        result = await recommender_no_store.get_recommendations(
            user_context={"keywords": ["test"]},
            limit=5,
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_recommendations_respects_limit(self, recommender):
        """結果數量不超過 limit."""
        result = await recommender.get_recommendations(
            user_context={"keywords": ["architecture", "event", "investment"]},
            limit=2,
        )
        assert len(result) <= 2
