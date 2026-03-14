"""Tests for VectorBridge — 語義搜尋統一門面.

測試 Embedder + VectorBridge 的 graceful degradation 行為。
大部分測試 mock 掉 Qdrant/fastembed（CI 環境無 Docker）。
"""

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from museon.vector.embedder import (
    DEFAULT_DIMENSION,
    DEFAULT_MODEL,
    Embedder,
)
from museon.vector.vector_bridge import (
    COLLECTIONS,
    QDRANT_URL,
    VectorBridge,
)


# ═══════════════════════════════════════════
# TestEmbedder
# ═══════════════════════════════════════════


class TestEmbedder:
    """Embedder 嵌入引擎測試."""

    def test_default_model(self):
        """預設模型名稱."""
        emb = Embedder()
        assert emb.model_name == DEFAULT_MODEL

    def test_default_dimension(self):
        """預設向量維度."""
        emb = Embedder()
        assert emb.dimension == DEFAULT_DIMENSION
        assert emb.dimension == 512

    def test_custom_model(self):
        """自訂模型."""
        emb = Embedder(model_name="test-model", dimension=768)
        assert emb.model_name == "test-model"
        assert emb.dimension == 768

    def test_embed_empty_list(self):
        """空 list 回傳空 list."""
        emb = Embedder()
        assert emb.embed([]) == []

    def test_embed_fastembed_not_installed(self):
        """fastembed 未安裝時 graceful degradation."""
        emb = Embedder()
        with patch.dict("sys.modules", {"fastembed": None}):
            emb._model = None
            emb._available = None
            result = emb.embed(["test"])
            assert result == []

    def test_embed_single_none_when_unavailable(self):
        """embed_single 不可用時回傳 None."""
        emb = Embedder()
        emb._available = False
        with patch.object(emb, "embed", return_value=[]):
            result = emb.embed_single("test")
            assert result is None

    def test_embed_single_returns_vector(self):
        """embed_single 正常回傳向量."""
        emb = Embedder()
        mock_vector = [0.1] * 512
        with patch.object(emb, "embed", return_value=[mock_vector]):
            result = emb.embed_single("test")
            assert result == mock_vector

    def test_is_available_caches_result(self):
        """is_available 結果快取."""
        emb = Embedder()
        emb._available = True
        assert emb.is_available() is True

    def test_is_available_false_when_no_fastembed(self):
        """fastembed 不可用."""
        emb = Embedder()
        emb._available = None
        with patch.object(emb, "_get_model", return_value=None):
            assert emb.is_available() is False
            # 結果已快取
            assert emb._available is False

    def test_embed_with_mock_model(self):
        """Mock model 回傳嵌入向量."""
        emb = Embedder()
        mock_model = MagicMock()

        # 模擬 fastembed 回傳（有 tolist() 方法的物件）
        class FakeArray:
            def __init__(self, data):
                self._data = data
            def tolist(self):
                return self._data

        mock_model.embed.return_value = [
            FakeArray([0.1, 0.2, 0.3]),
            FakeArray([0.4, 0.5, 0.6]),
        ]
        emb._model = mock_model
        emb._available = True

        result = emb.embed(["hello", "world"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    def test_embed_exception_graceful(self):
        """嵌入過程異常時 graceful degradation."""
        emb = Embedder()
        mock_model = MagicMock()
        mock_model.embed.side_effect = RuntimeError("GPU error")
        emb._model = mock_model
        emb._available = True

        result = emb.embed(["test"])
        assert result == []
        assert emb._available is False


# ═══════════════════════════════════════════
# TestVectorBridge — 基礎測試（無 Qdrant）
# ═══════════════════════════════════════════


class TestVectorBridge:
    """VectorBridge 基礎測試（Qdrant 不可用）."""

    def test_collections_count(self):
        """7 個 collection（含 references）."""
        assert len(COLLECTIONS) == 7
        expected = {"memories", "skills", "dna27", "crystals", "workflows", "documents", "references"}
        assert set(COLLECTIONS.keys()) == expected

    def test_qdrant_url(self):
        """Qdrant 預設 URL."""
        assert QDRANT_URL == "http://127.0.0.1:6333"

    def test_init(self, tmp_path):
        """初始化."""
        vb = VectorBridge(workspace=tmp_path)
        assert vb._workspace == tmp_path
        assert vb._client is None
        assert vb._embedder is None

    def test_is_available_false_no_qdrant(self, tmp_path):
        """Qdrant 不可用時 is_available=False."""
        vb = VectorBridge(workspace=tmp_path)
        with patch.object(vb, "_get_client", return_value=None):
            assert vb.is_available() is False

    def test_is_available_caches(self, tmp_path):
        """is_available 結果快取 60 秒."""
        vb = VectorBridge(workspace=tmp_path)
        vb._available = True
        import time as _time
        vb._available_checked_at = _time.time()
        assert vb.is_available() is True

    def test_search_unknown_collection(self, tmp_path):
        """搜尋不存在的 collection 回傳空 list."""
        vb = VectorBridge(workspace=tmp_path)
        result = vb.search("nonexistent", "query")
        assert result == []

    def test_index_unknown_collection(self, tmp_path):
        """索引到不存在的 collection 回傳 False."""
        vb = VectorBridge(workspace=tmp_path)
        result = vb.index("nonexistent", "id1", "text")
        assert result is False

    def test_index_batch_empty(self, tmp_path):
        """批次索引空 list."""
        vb = VectorBridge(workspace=tmp_path)
        result = vb.index_batch("memories", [])
        assert result == 0

    def test_search_returns_empty_when_unavailable(self, tmp_path):
        """Qdrant 不可用時搜尋回傳空 list."""
        vb = VectorBridge(workspace=tmp_path)
        with patch.object(vb, "_get_client", return_value=None):
            result = vb.search("memories", "test query")
            assert result == []

    def test_index_returns_false_when_unavailable(self, tmp_path):
        """Qdrant 不可用時索引回傳 False."""
        vb = VectorBridge(workspace=tmp_path)
        with patch.object(vb, "_get_embedder") as mock_emb:
            mock_emb.return_value.embed_single.return_value = [0.1] * 512
            with patch.object(vb, "_get_client", return_value=None):
                result = vb.index("memories", "id1", "test text")
                assert result is False


# ═══════════════════════════════════════════
# TestVectorBridgeWithMockQdrant
# ═══════════════════════════════════════════


class TestVectorBridgeWithMockQdrant:
    """VectorBridge 與 mock Qdrant 的整合測試."""

    def _make_bridge(self, tmp_path):
        """建立 VectorBridge with mock client + embedder."""
        vb = VectorBridge(workspace=tmp_path)

        # Mock embedder
        mock_embedder = MagicMock(spec=Embedder)
        mock_embedder.dimension = 512
        mock_embedder.is_available.return_value = True
        mock_embedder.embed_single.return_value = [0.1] * 512
        mock_embedder.embed.return_value = [[0.1] * 512, [0.2] * 512]
        vb._embedder = mock_embedder

        # Mock Qdrant client
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock()
        mock_client.get_collection.return_value = MagicMock()  # collection exists
        vb._client = mock_client

        # Mock qdrant_client.models（可能未安裝）
        self._mock_qdrant_models()

        return vb, mock_client, mock_embedder

    def _mock_qdrant_models(self):
        """Mock qdrant_client 模組（CI 環境可能未安裝）."""
        import sys

        if "qdrant_client" not in sys.modules:
            mock_qdrant = MagicMock()
            mock_qdrant.models.PointStruct = type("PointStruct", (), {
                "__init__": lambda self, **kwargs: self.__dict__.update(kwargs),
            })
            mock_qdrant.models.Distance = MagicMock()
            mock_qdrant.models.Distance.COSINE = "Cosine"
            mock_qdrant.models.VectorParams = MagicMock()
            sys.modules["qdrant_client"] = mock_qdrant
            sys.modules["qdrant_client.models"] = mock_qdrant.models

    def test_is_available_true(self, tmp_path):
        """Qdrant + Embedder 都可用."""
        vb, mock_client, _ = self._make_bridge(tmp_path)
        assert vb.is_available() is True

    def test_index_calls_upsert(self, tmp_path):
        """index 呼叫 Qdrant upsert."""
        vb, mock_client, _ = self._make_bridge(tmp_path)
        result = vb.index("memories", "mem-001", "test content")
        assert result is True
        mock_client.upsert.assert_called_once()

    def test_index_with_metadata(self, tmp_path):
        """index 帶 metadata."""
        vb, mock_client, _ = self._make_bridge(tmp_path)
        result = vb.index(
            "skills", "skill-1", "coding skill",
            metadata={"tags": ["python"], "level": 3},
        )
        assert result is True
        mock_client.upsert.assert_called_once()
        # 驗證 payload 含 metadata
        call_args = mock_client.upsert.call_args
        points = call_args.kwargs.get("points", call_args[1].get("points", []))
        payload = points[0].payload
        assert payload["doc_id"] == "skill-1"
        assert payload["tags"] == ["python"]

    def test_search_returns_results(self, tmp_path):
        """search 回傳結果."""
        vb, mock_client, _ = self._make_bridge(tmp_path)

        # Mock search result
        mock_hit = MagicMock()
        mock_hit.id = "point-1"
        mock_hit.score = 0.95
        mock_hit.payload = {
            "doc_id": "mem-001",
            "text": "test result",
            "layer": "L0_buffer",
        }

        # qdrant-client >=1.7 uses query_points; MagicMock always has
        # the attribute, so the code takes the query_points path.
        mock_response = MagicMock()
        mock_response.points = [mock_hit]
        mock_client.query_points.return_value = mock_response

        results = vb.search("memories", "test query", limit=5)
        assert len(results) == 1
        assert results[0]["id"] == "mem-001"
        assert results[0]["score"] == 0.95
        assert results[0]["text"] == "test result"
        assert results[0]["layer"] == "L0_buffer"

    def test_batch_index(self, tmp_path):
        """batch index 多筆."""
        vb, mock_client, mock_embedder = self._make_bridge(tmp_path)
        mock_embedder.embed.return_value = [[0.1] * 512, [0.2] * 512]

        items = [
            {"id": "mem-1", "text": "first memory"},
            {"id": "mem-2", "text": "second memory"},
        ]
        count = vb.index_batch("memories", items)
        assert count == 2
        mock_client.upsert.assert_called_once()

    def test_ensure_collections(self, tmp_path):
        """ensure_collections 建立缺少的 collection."""
        vb, mock_client, _ = self._make_bridge(tmp_path)

        # 模擬前 2 個存在，其餘不存在
        existing = {"memories", "skills"}
        def mock_get_collection(name):
            if name in existing:
                return MagicMock()
            raise Exception("not found")

        mock_client.get_collection.side_effect = mock_get_collection

        result = vb.ensure_collections()
        assert "memories" in result["existing"]
        assert "skills" in result["existing"]
        assert len(result["created"]) == len(COLLECTIONS) - len(existing)
        assert result["error"] is None

    def test_get_stats(self, tmp_path):
        """get_stats 回傳各 collection 統計."""
        vb, mock_client, _ = self._make_bridge(tmp_path)

        mock_info = MagicMock()
        mock_info.points_count = 42
        mock_info.status = "green"
        mock_client.get_collection.return_value = mock_info

        stats = vb.get_stats()
        assert len(stats) == len(COLLECTIONS)
        assert stats["memories"]["points"] == 42

    def test_delete_collection(self, tmp_path):
        """delete_collection 呼叫 Qdrant."""
        vb, mock_client, _ = self._make_bridge(tmp_path)
        result = vb.delete_collection("memories")
        assert result is True
        mock_client.delete_collection.assert_called_once_with(
            collection_name="memories"
        )

    def test_doc_id_to_point_id_deterministic(self, tmp_path):
        """同一 doc_id 產生同一 UUID."""
        vb = VectorBridge(workspace=tmp_path)
        id1 = vb._doc_id_to_point_id("test-doc")
        id2 = vb._doc_id_to_point_id("test-doc")
        assert id1 == id2
        # 是合法 UUID
        uuid.UUID(id1)

    def test_doc_id_to_point_id_different(self, tmp_path):
        """不同 doc_id 產生不同 UUID."""
        vb = VectorBridge(workspace=tmp_path)
        id1 = vb._doc_id_to_point_id("doc-a")
        id2 = vb._doc_id_to_point_id("doc-b")
        assert id1 != id2
