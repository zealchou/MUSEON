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
from museon.vector.sparse_embedder import SparseEmbedder
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
        """9 個 collection（含 references + primals + soul_rings）."""
        assert len(COLLECTIONS) == 9
        expected = {"memories", "skills", "dna27", "crystals", "workflows", "documents", "references", "primals", "soul_rings"}
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


# ═══════════════════════════════════════════
# TestSparseEmbedder
# ═══════════════════════════════════════════


class TestSparseEmbedder:
    """SparseEmbedder BM25 稀疏向量測試."""

    def test_is_available(self):
        """jieba 可用."""
        se = SparseEmbedder()
        assert se.is_available() is True

    def test_tokenize_chinese(self):
        """中文分詞 + 停用詞過濾."""
        se = SparseEmbedder()
        tokens = se.tokenize("MUSEON 知識晶格系統")
        assert "museon" in tokens
        assert "知識" in tokens
        assert "晶格" in tokens
        # 停用詞應被過濾
        assert "的" not in tokens
        assert "是" not in tokens

    def test_tokenize_empty(self):
        """空文本回傳空 list."""
        se = SparseEmbedder()
        assert se.tokenize("") == []

    def test_tokenize_stopwords_only(self):
        """純停用詞回傳空 list."""
        se = SparseEmbedder()
        result = se.tokenize("的 了 在 是")
        assert result == []

    def test_build_idf(self):
        """IDF 建立."""
        se = SparseEmbedder()
        corpus = [
            "知識結晶化是一個過程",
            "語義搜尋使用向量",
            "混合檢索結合兩種方法",
        ]
        vocab_size = se.build_idf(corpus)
        assert vocab_size > 0
        assert se.has_idf()
        assert se._doc_count == 3
        assert se._avg_dl > 0

    def test_encode_without_idf(self):
        """未建 IDF 時回傳空."""
        se = SparseEmbedder()
        indices, values = se.encode("test query")
        assert indices == []
        assert values == []

    def test_encode_with_idf(self):
        """建 IDF 後可正常編碼."""
        se = SparseEmbedder()
        corpus = [
            "知識結晶化是一個過程",
            "語義搜尋使用向量資料庫",
            "混合檢索結合語義和關鍵字",
            "稀疏向量使用 BM25 權重",
        ]
        se.build_idf(corpus)
        indices, values = se.encode("語義搜尋")
        assert len(indices) > 0
        assert len(indices) == len(values)
        assert all(v > 0 for v in values)

    def test_encode_empty_text(self):
        """空文本編碼回傳空."""
        se = SparseEmbedder()
        se.build_idf(["一些語料"])
        indices, values = se.encode("")
        assert indices == []
        assert values == []

    def test_idf_persistence(self, tmp_path):
        """IDF 表可持久化和載入."""
        # 建立並儲存
        se1 = SparseEmbedder(workspace=tmp_path)
        corpus = ["語義搜尋", "知識結晶", "混合檢索"]
        se1.build_idf(corpus)
        vocab1 = len(se1._idf)

        # 重新載入
        se2 = SparseEmbedder(workspace=tmp_path)
        assert se2.has_idf()
        assert len(se2._idf) == vocab1

    def test_encode_batch(self):
        """批次編碼."""
        se = SparseEmbedder()
        se.build_idf(["語義搜尋", "知識結晶", "混合檢索"])
        results = se.encode_batch(["語義", "知識"])
        assert len(results) == 2
        for indices, values in results:
            assert isinstance(indices, list)
            assert isinstance(values, list)


# ═══════════════════════════════════════════
# TestRRFMerge
# ═══════════════════════════════════════════


class TestRRFMerge:
    """Reciprocal Rank Fusion 測試."""

    def test_rrf_merge_basic(self):
        """基本 RRF 合併."""
        dense = [
            {"id": "doc-a", "score": 0.9, "text": "A"},
            {"id": "doc-b", "score": 0.8, "text": "B"},
            {"id": "doc-c", "score": 0.7, "text": "C"},
        ]
        sparse = [
            {"id": "doc-b", "score": 5.0, "text": "B"},
            {"id": "doc-d", "score": 4.0, "text": "D"},
            {"id": "doc-a", "score": 3.0, "text": "A"},
        ]
        merged = VectorBridge._rrf_merge(dense, sparse, k=60)

        # doc-a 和 doc-b 出現在兩組，應排前面
        ids = [r["id"] for r in merged]
        assert "doc-a" in ids
        assert "doc-b" in ids
        assert "doc-d" in ids

        # 每個結果都有 rrf_score
        for r in merged:
            assert "rrf_score" in r
            assert r["rrf_score"] > 0

    def test_rrf_merge_single_source(self):
        """只有一組結果時等同原排名."""
        dense = [
            {"id": "doc-a", "score": 0.9, "text": "A"},
            {"id": "doc-b", "score": 0.8, "text": "B"},
        ]
        merged = VectorBridge._rrf_merge(dense, [], k=60)
        assert len(merged) == 2
        assert merged[0]["id"] == "doc-a"

    def test_rrf_merge_both_empty(self):
        """兩組都空."""
        merged = VectorBridge._rrf_merge([], [], k=60)
        assert merged == []

    def test_rrf_merge_overlap_boosted(self):
        """重疊文件應得更高分."""
        dense = [
            {"id": "overlap", "score": 0.9, "text": "X"},
            {"id": "dense-only", "score": 0.8, "text": "Y"},
        ]
        sparse = [
            {"id": "overlap", "score": 5.0, "text": "X"},
            {"id": "sparse-only", "score": 4.0, "text": "Z"},
        ]
        merged = VectorBridge._rrf_merge(dense, sparse, k=60)

        # overlap 應排第一（因為兩組都有）
        assert merged[0]["id"] == "overlap"
        # overlap 的 RRF score 應大於單一來源的
        overlap_score = merged[0]["rrf_score"]
        other_scores = [r["rrf_score"] for r in merged if r["id"] != "overlap"]
        assert all(overlap_score > s for s in other_scores)


# ═══════════════════════════════════════════
# TestHybridSearch
# ═══════════════════════════════════════════


class TestHybridSearch:
    """hybrid_search 混合檢索測試."""

    def test_hybrid_fallback_to_dense(self, tmp_path):
        """sparse 不可用時降級為純 dense."""
        vb = VectorBridge(workspace=tmp_path)
        mock_dense = [
            {"id": "doc-1", "score": 0.9, "text": "result"},
        ]
        with patch.object(vb, "search", return_value=mock_dense):
            with patch.object(vb, "_sparse_search", return_value=[]):
                results = vb.hybrid_search("crystals", "test", limit=5)
                assert len(results) == 1
                assert results[0]["id"] == "doc-1"

    def test_hybrid_with_both_sources(self, tmp_path):
        """dense + sparse 都有結果時 RRF 融合."""
        vb = VectorBridge(workspace=tmp_path)
        mock_dense = [
            {"id": "doc-a", "score": 0.9, "text": "A"},
            {"id": "doc-b", "score": 0.8, "text": "B"},
        ]
        mock_sparse = [
            {"id": "doc-b", "score": 5.0, "text": "B"},
            {"id": "doc-c", "score": 4.0, "text": "C"},
        ]
        with patch.object(vb, "search", return_value=mock_dense):
            with patch.object(vb, "_sparse_search", return_value=mock_sparse):
                results = vb.hybrid_search("crystals", "test", limit=3)
                assert len(results) == 3
                # doc-b 出現在兩組，應排更前
                ids = [r["id"] for r in results]
                assert "doc-b" in ids
                # 每個結果有 rrf_score
                for r in results:
                    assert "rrf_score" in r
