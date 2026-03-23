"""Soul Ring Vector Index 單元測試.

Project Epigenesis 迭代 3：Soul Ring → Qdrant 語義索引。
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from museon.agent.soul_ring import DiaryStore, SoulRing, GENESIS_HASH


@pytest.fixture
def tmp_data_dir():
    """建立臨時資料目錄."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_vector_bridge():
    """模擬 VectorBridge."""
    vb = MagicMock()
    vb.index.return_value = True
    vb.search.return_value = []
    return vb


@pytest.fixture
def store_with_vector(tmp_data_dir, mock_vector_bridge):
    """帶 VectorBridge 的 DiaryStore."""
    return DiaryStore(data_dir=tmp_data_dir, vector_bridge=mock_vector_bridge)


@pytest.fixture
def store_without_vector(tmp_data_dir):
    """不帶 VectorBridge 的 DiaryStore."""
    return DiaryStore(data_dir=tmp_data_dir)


def _make_ring(ring_type="cognitive_breakthrough", desc="test ring", ctx="test context") -> SoulRing:
    """建立測試用 SoulRing."""
    ring = SoulRing(
        type=ring_type,
        description=desc,
        context=ctx,
        impact="test impact",
        created_at=datetime.now().isoformat(),
        prev_hash=GENESIS_HASH,
    )
    ring.hash = ring.compute_hash(GENESIS_HASH)
    return ring


class TestSoulRingVectorIndex:
    """向量索引 hook 測試."""

    def test_append_triggers_index(self, store_with_vector, mock_vector_bridge):
        """追加年輪時觸發 Qdrant 索引."""
        ring = _make_ring()
        store_with_vector.append_soul_ring(ring)

        mock_vector_bridge.index.assert_called_once()
        call_args = mock_vector_bridge.index.call_args
        assert call_args[0][0] == "soul_rings"  # collection
        assert call_args[0][1] == ring.hash  # doc_id
        assert "test ring" in call_args[0][2]  # searchable text
        assert call_args[0][3]["type"] == "cognitive_breakthrough"

    def test_append_without_vector_bridge(self, store_without_vector):
        """沒有 VectorBridge 時不報錯."""
        ring = _make_ring()
        # 不應拋出任何異常
        store_without_vector.append_soul_ring(ring)
        # 驗證年輪仍然被寫入
        rings = store_without_vector.load_soul_rings(verify=False)
        assert len(rings) == 1

    def test_index_failure_doesnt_block_append(self, store_with_vector, mock_vector_bridge):
        """向量索引失敗不阻斷年輪寫入."""
        mock_vector_bridge.index.side_effect = RuntimeError("Qdrant down")
        ring = _make_ring()
        store_with_vector.append_soul_ring(ring)

        # 年輪仍然被寫入
        rings = store_with_vector.load_soul_rings(verify=False)
        assert len(rings) == 1

    def test_set_vector_bridge_post_init(self, store_without_vector, mock_vector_bridge):
        """後注入 VectorBridge."""
        store_without_vector.set_vector_bridge(mock_vector_bridge)
        ring = _make_ring()
        store_without_vector.append_soul_ring(ring)
        mock_vector_bridge.index.assert_called_once()


class TestSoulRingRecall:
    """語義搜索測試."""

    def test_recall_with_results(self, store_with_vector, mock_vector_bridge):
        """有搜索結果時返回匹配的年輪."""
        # 先寫入一條年輪
        ring = _make_ring(desc="投資決策的失敗教訓")
        store_with_vector.append_soul_ring(ring)

        # 模擬 Qdrant 搜索結果
        mock_hit = MagicMock()
        mock_hit.score = 0.85
        mock_hit.payload = {
            "ring_hash": ring.hash,
            "type": "cognitive_breakthrough",
        }
        mock_vector_bridge.search.return_value = [mock_hit]

        results = store_with_vector.recall_soul_rings("投資失敗")
        assert len(results) == 1
        assert results[0]["score"] == 0.85
        assert results[0]["ring"]["description"] == "投資決策的失敗教訓"

    def test_recall_filters_low_score(self, store_with_vector, mock_vector_bridge):
        """低分結果被過濾."""
        ring = _make_ring()
        store_with_vector.append_soul_ring(ring)

        mock_hit = MagicMock()
        mock_hit.score = 0.1  # 低於預設 min_score 0.3
        mock_hit.payload = {"ring_hash": ring.hash}
        mock_vector_bridge.search.return_value = [mock_hit]

        results = store_with_vector.recall_soul_rings("test")
        assert len(results) == 0

    def test_recall_without_vector_bridge(self, store_without_vector):
        """沒有 VectorBridge 時返回空."""
        results = store_without_vector.recall_soul_rings("test")
        assert results == []

    def test_recall_empty_results(self, store_with_vector, mock_vector_bridge):
        """Qdrant 無結果時返回空."""
        mock_vector_bridge.search.return_value = []
        results = store_with_vector.recall_soul_rings("nonexistent topic")
        assert results == []

    def test_recall_failure_returns_empty(self, store_with_vector, mock_vector_bridge):
        """搜索失敗時返回空（降級保護）."""
        mock_vector_bridge.search.side_effect = RuntimeError("Qdrant down")
        results = store_with_vector.recall_soul_rings("test")
        assert results == []


class TestSoulRingBackfill:
    """回填索引測試."""

    def test_backfill_basic(self, store_with_vector, mock_vector_bridge):
        """回填既有年輪到 Qdrant."""
        # 寫入 3 條年輪
        prev_hash = GENESIS_HASH
        for i in range(3):
            ring = SoulRing(
                type="cognitive_breakthrough",
                description=f"ring {i}",
                context="test",
                impact="test",
                created_at=datetime.now().isoformat(),
                prev_hash=prev_hash,
            )
            ring.hash = ring.compute_hash(prev_hash)
            store_with_vector.append_soul_ring(ring)
            prev_hash = ring.hash

        # 重置 mock 計數
        mock_vector_bridge.index.reset_mock()

        # 回填
        indexed = store_with_vector.backfill_vector_index()
        assert indexed == 3
        assert mock_vector_bridge.index.call_count == 3

    def test_backfill_without_vector_bridge(self, store_without_vector):
        """沒有 VectorBridge 時回填返回 0."""
        result = store_without_vector.backfill_vector_index()
        assert result == 0

    def test_backfill_empty_rings(self, store_with_vector):
        """無年輪時回填返回 0."""
        result = store_with_vector.backfill_vector_index()
        assert result == 0
