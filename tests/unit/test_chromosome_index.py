"""Tests for chromosome_index.py — TF-IDF + jieba 語義搜尋引擎.

依據 SIX_LAYER_MEMORY BDD Spec §5 的 BDD scenarios 驗證。
"""

import json
import os
import pytest
import threading

from museon.memory.chromosome_index import (
    ChromosomeIndex,
    _TAG_BOOST,
    _tokenize,
    cosine_similarity,
)


# ═══════════════════════════════════════════
# Tokenizer Tests
# ═══════════════════════════════════════════


class TestTokenize:
    """jieba 分詞測試."""

    def test_chinese_text(self):
        """BDD: 中文文本分詞."""
        tokens = _tokenize("機器學習模型訓練")
        assert len(tokens) > 0
        assert all(len(t) >= 2 for t in tokens)

    def test_english_text(self):
        """BDD: 英文文本分詞."""
        tokens = _tokenize("machine learning model")
        assert len(tokens) > 0

    def test_mixed_text(self):
        """BDD: 中英混合分詞."""
        tokens = _tokenize("AI 機器學習 model")
        assert len(tokens) > 0

    def test_empty_text(self):
        """BDD: 空文本 → 空列表."""
        assert _tokenize("") == []

    def test_short_tokens_filtered(self):
        """BDD: < 2 字元的 token 被過濾."""
        tokens = _tokenize("I am a b c 的 了")
        assert all(len(t) >= 2 for t in tokens)

    def test_lowercase(self):
        """BDD: 全部轉小寫."""
        tokens = _tokenize("Machine Learning AI")
        assert all(t == t.lower() for t in tokens)


# ═══════════════════════════════════════════
# Cosine Similarity Tests
# ═══════════════════════════════════════════


class TestCosineSimilarity:
    """餘弦相似度測試."""

    def test_identical_vectors(self):
        """BDD: 相同向量 → 1.0."""
        vec = {"a": 1.0, "b": 2.0}
        assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=0.01)

    def test_orthogonal_vectors(self):
        """BDD: 正交向量 → 0.0."""
        vec_a = {"a": 1.0}
        vec_b = {"b": 1.0}
        assert cosine_similarity(vec_a, vec_b) == 0.0

    def test_empty_vectors(self):
        """BDD: 空向量 → 0.0."""
        assert cosine_similarity({}, {}) == 0.0
        assert cosine_similarity({"a": 1.0}, {}) == 0.0

    def test_partial_overlap(self):
        """BDD: 部分重疊 → 0 < sim < 1."""
        vec_a = {"a": 1.0, "b": 1.0}
        vec_b = {"b": 1.0, "c": 1.0}
        sim = cosine_similarity(vec_a, vec_b)
        assert 0.0 < sim < 1.0

    def test_zero_norm_vector(self):
        """BDD: 零向量 → 0.0."""
        assert cosine_similarity({"a": 0.0}, {"a": 1.0}) == 0.0


# ═══════════════════════════════════════════
# ChromosomeIndex Tests
# ═══════════════════════════════════════════


class TestChromosomeIndex:
    """ChromosomeIndex 核心功能測試."""

    def test_index_and_search(self):
        """BDD: 索引記憶並搜尋."""
        idx = ChromosomeIndex()
        idx.index("A", "機器學習模型訓練", tags=["AI", "ML"])
        idx.index("B", "深度學習神經網路", tags=["AI", "DL"])
        idx.index("C", "今天做了紅燒肉", tags=["料理"])

        results = idx.search("機器學習")
        assert len(results) > 0
        # A 應排第一（直接匹配）
        assert results[0][0] == "A"
        # C（料理）應不在結果中或相似度極低
        c_scores = [s for mid, s in results if mid == "C"]
        if c_scores:
            assert c_scores[0] < 0.1

    def test_tag_boosting(self):
        """BDD: Tag Boosting 效果."""
        idx = ChromosomeIndex()
        idx.index("D", "這是一段普通文字普通文字", tags=["重要"])
        results = idx.search("重要")
        assert len(results) > 0
        assert results[0][0] == "D"
        assert results[0][1] > 0

    def test_doc_count(self):
        """BDD: 文件計數正確."""
        idx = ChromosomeIndex()
        assert idx.doc_count() == 0
        idx.index("A", "文件一")
        idx.index("B", "文件二")
        assert idx.doc_count() == 2

    def test_remove(self):
        """BDD: 移除文件後搜尋不到."""
        idx = ChromosomeIndex()
        idx.index("A", "機器學習訓練")
        idx.remove("A")
        results = idx.search("機器學習")
        assert not any(mid == "A" for mid, _ in results)
        assert idx.doc_count() == 0

    def test_contains(self):
        """BDD: contains 正確."""
        idx = ChromosomeIndex()
        idx.index("A", "文件內容")
        assert idx.contains("A")
        assert not idx.contains("B")

    def test_empty_search(self):
        """BDD: 空索引搜尋 → 空列表."""
        idx = ChromosomeIndex()
        assert idx.search("任何查詢") == []

    def test_empty_query(self):
        """BDD: 空查詢 → 空列表."""
        idx = ChromosomeIndex()
        idx.index("A", "一些內容")
        assert idx.search("") == []

    def test_top_k_limit(self):
        """BDD: top_k 限制回傳數量."""
        idx = ChromosomeIndex()
        for i in range(20):
            idx.index(f"doc_{i}", f"機器學習模型 {i}")
        results = idx.search("機器學習", top_k=5)
        assert len(results) <= 5

    def test_idf_lazy_recalc(self):
        """BDD: IDF 懶重算."""
        idx = ChromosomeIndex()
        idx.index("A", "機器學習")
        idx.index("B", "深度學習")
        assert idx._idf_dirty is True
        # search 觸發 IDF 重算
        idx.search("學習")
        assert idx._idf_dirty is False
        # 再 index 後 dirty 重設
        idx.index("C", "強化學習")
        assert idx._idf_dirty is True


# ═══════════════════════════════════════════
# Cluster Tests
# ═══════════════════════════════════════════


class TestCluster:
    """聚類測試."""

    def test_similar_documents_cluster(self):
        """BDD: 相似文件被聚在一起."""
        idx = ChromosomeIndex()
        idx.index("A1", "機器學習模型訓練深度")
        idx.index("A2", "機器學習模型深度學習")
        idx.index("B1", "今天做了一道紅燒肉")

        groups = idx.cluster(threshold=0.3)
        assert len(groups) >= 2

    def test_empty_cluster(self):
        """BDD: 空索引聚類 → 空列表."""
        idx = ChromosomeIndex()
        assert idx.cluster() == []


# ═══════════════════════════════════════════
# Persistence Tests
# ═══════════════════════════════════════════


class TestPersistence:
    """持久化測試."""

    def test_save_and_load(self, tmp_path):
        """BDD: save + load 往返正確."""
        path = str(tmp_path / "index" / "chromosome.json")

        idx1 = ChromosomeIndex(persist_path=path)
        idx1.index("A", "機器學習", tags=["AI"])
        idx1.index("B", "深度學習", tags=["DL"])
        idx1.save()

        # 新實例載入
        idx2 = ChromosomeIndex(persist_path=path)
        assert idx2.doc_count() == 2
        assert idx2.contains("A")
        assert idx2.contains("B")

    def test_load_nonexistent(self, tmp_path):
        """BDD: 不存在的檔案不報錯."""
        path = str(tmp_path / "missing" / "chromosome.json")
        idx = ChromosomeIndex(persist_path=path)
        assert idx.doc_count() == 0

    def test_no_persist_path(self):
        """BDD: 無 persist_path 不報錯."""
        idx = ChromosomeIndex()
        idx.index("A", "內容")
        idx.save()  # should not raise


# ═══════════════════════════════════════════
# Thread Safety Tests
# ═══════════════════════════════════════════


class TestThreadSafety:
    """執行緒安全測試."""

    def test_concurrent_index_and_search(self):
        """BDD: 並行 index + search 無 race condition."""
        idx = ChromosomeIndex()
        errors = []

        def index_worker(start):
            try:
                for i in range(10):
                    idx.index(f"doc_{start}_{i}", f"內容 {start} {i}")
            except Exception as e:
                errors.append(e)

        def search_worker():
            try:
                for _ in range(10):
                    idx.search("內容")
            except Exception as e:
                errors.append(e)

        threads = []
        for t in range(5):
            threads.append(threading.Thread(target=index_worker, args=(t,)))
            threads.append(threading.Thread(target=search_worker))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert idx.doc_count() == 50  # 5 threads × 10 docs
