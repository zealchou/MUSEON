"""SparseEmbedder — BM25 稀疏向量產生器.

用 jieba 中文分詞 + BM25 權重，將文本轉為 Qdrant SparseVector。
配合 VectorBridge.hybrid_search() 實現 Dense + Sparse 混合檢索。

設計原則：
- 與 Embedder（dense）平行運作，互不干擾
- IDF 表自動從語料建立，可持久化到 workspace
- Graceful degradation：jieba 不可用時回傳空向量
"""

import json
import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# BM25 參數
BM25_K1 = 1.5
BM25_B = 0.75

# 最小 IDF 門檻（過濾超高頻停用詞）
MIN_IDF = 0.5

# 稀疏向量最大非零維度（控制 payload 大小）
MAX_SPARSE_DIMS = 256

# 詞彙表上限（控制記憶體）
MAX_VOCAB_SIZE = 50000

# 中文停用詞（高頻無意義詞）
_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
    "都", "一", "一個", "上", "也", "很", "到", "說", "要", "去",
    "你", "會", "著", "沒有", "看", "好", "自己", "這", "他", "她",
    "它", "們", "那", "被", "從", "把", "對", "讓", "用", "可以",
    "什麼", "怎麼", "如果", "因為", "所以", "但是", "或者", "而且",
    "還是", "已經", "可能", "這個", "那個", "一些", "沒", "能",
    "做", "吧", "嗎", "啊", "呢", "the", "a", "an", "is", "are",
    "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through",
    "it", "its", "this", "that", "and", "or", "but", "if", "not",
})


class SparseEmbedder:
    """BM25 稀疏向量產生器.

    Usage:
        se = SparseEmbedder(workspace=Path("data"))
        # 從語料建立 IDF（首次或定期更新）
        se.build_idf(["文本1", "文本2", ...])
        # 編碼為稀疏向量
        indices, values = se.encode("查詢文本")
    """

    def __init__(self, workspace: Optional[Path] = None):
        """初始化 SparseEmbedder.

        Args:
            workspace: 工作目錄（存放 IDF 表）
        """
        self._workspace = Path(workspace) if workspace else None
        self._idf: Dict[str, float] = {}
        self._vocab: Dict[str, int] = {}  # token → index
        self._avg_dl: float = 0.0
        self._doc_count: int = 0
        self._available: Optional[bool] = None

        # 嘗試載入已有的 IDF 表
        self._load_idf()

    def is_available(self) -> bool:
        """檢查 jieba 是否可用."""
        if self._available is not None:
            return self._available
        try:
            import jieba  # noqa: F401
            self._available = True
        except ImportError:
            logger.info("jieba not installed — SparseEmbedder unavailable")
            self._available = False
        return self._available

    def has_idf(self) -> bool:
        """是否已建立 IDF 表."""
        return len(self._idf) > 0

    def tokenize(self, text: str) -> List[str]:
        """中英文混合分詞 + 過濾停用詞.

        Args:
            text: 輸入文本

        Returns:
            詞列表（已過濾停用詞和短詞）
        """
        if not self.is_available():
            return []

        import jieba

        # jieba 分詞
        tokens = jieba.lcut(text)

        # 過濾：停用詞 + 長度 < 2 的中文 + 純數字 + 純標點
        result = []
        for t in tokens:
            t = t.strip().lower()
            if not t:
                continue
            if t in _STOPWORDS:
                continue
            # 純數字跳過
            if re.match(r"^\d+$", t):
                continue
            # 純標點跳過
            if re.match(r"^[\W_]+$", t):
                continue
            # 單字中文跳過（太短無語義）
            if len(t) == 1 and "\u4e00" <= t <= "\u9fff":
                continue
            result.append(t)

        return result

    def build_idf(self, corpus: List[str]) -> int:
        """從語料庫建立 IDF 表.

        Args:
            corpus: 文本列表

        Returns:
            詞彙表大小
        """
        if not self.is_available() or not corpus:
            return 0

        doc_count = len(corpus)
        df: Counter = Counter()  # document frequency
        total_dl = 0

        for text in corpus:
            tokens = self.tokenize(text)
            total_dl += len(tokens)
            # 每個文件中出現過的 unique tokens
            unique_tokens = set(tokens)
            for token in unique_tokens:
                df[token] += 1

        # 計算平均文件長度
        self._avg_dl = total_dl / doc_count if doc_count > 0 else 1.0
        self._doc_count = doc_count

        # 計算 IDF = log((N - df + 0.5) / (df + 0.5) + 1)
        self._idf = {}
        for token, freq in df.most_common(MAX_VOCAB_SIZE):
            idf = math.log((doc_count - freq + 0.5) / (freq + 0.5) + 1)
            if idf >= MIN_IDF:
                self._idf[token] = idf

        # 建立 vocab 映射（穩定排序：按 IDF 降序）
        sorted_tokens = sorted(self._idf.keys(), key=lambda t: -self._idf[t])
        self._vocab = {token: idx for idx, token in enumerate(sorted_tokens)}

        # 持久化
        self._save_idf()

        logger.info(
            f"SparseEmbedder IDF built: {len(self._idf)} terms "
            f"from {doc_count} docs (avg_dl={self._avg_dl:.1f})"
        )
        return len(self._idf)

    def encode(self, text: str) -> Tuple[List[int], List[float]]:
        """將文本編碼為 BM25 稀疏向量.

        Args:
            text: 輸入文本

        Returns:
            (indices, values) — 稀疏向量的非零維度索引和對應值。
            若 IDF 表未建立或分詞失敗，回傳空元組。
        """
        if not self.is_available() or not self._idf:
            return [], []

        tokens = self.tokenize(text)
        if not tokens:
            return [], []

        doc_len = len(tokens)
        tf: Counter = Counter(tokens)

        indices = []
        values = []

        for token, freq in tf.items():
            if token not in self._vocab:
                continue

            idf = self._idf.get(token, 0.0)
            if idf < MIN_IDF:
                continue

            # BM25 TF 歸一化
            tf_norm = (freq * (BM25_K1 + 1)) / (
                freq + BM25_K1 * (1 - BM25_B + BM25_B * doc_len / max(self._avg_dl, 1))
            )

            score = idf * tf_norm
            indices.append(self._vocab[token])
            values.append(round(score, 4))

        # 限制維度數
        if len(indices) > MAX_SPARSE_DIMS:
            pairs = sorted(zip(values, indices), reverse=True)[:MAX_SPARSE_DIMS]
            values, indices = zip(*pairs)
            indices = list(indices)
            values = list(values)

        return indices, values

    def encode_batch(self, texts: List[str]) -> List[Tuple[List[int], List[float]]]:
        """批次編碼.

        Args:
            texts: 文本列表

        Returns:
            稀疏向量列表
        """
        return [self.encode(text) for text in texts]

    # ═══════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════

    def _idf_path(self) -> Optional[Path]:
        """IDF 表儲存路徑."""
        if not self._workspace:
            return None
        return self._workspace / "_system" / "sparse_idf.json"

    def _save_idf(self) -> None:
        """持久化 IDF 表."""
        path = self._idf_path()
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "doc_count": self._doc_count,
                "avg_dl": self._avg_dl,
                "vocab_size": len(self._idf),
                "idf": self._idf,
                "vocab": self._vocab,
            }
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.rename(path)
            logger.debug(f"SparseEmbedder IDF saved: {path}")
        except Exception as e:
            logger.warning(f"Failed to save IDF: {e}")

    def _load_idf(self) -> None:
        """從磁碟載入 IDF 表."""
        path = self._idf_path()
        if not path or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._doc_count = data.get("doc_count", 0)
            self._avg_dl = data.get("avg_dl", 1.0)
            self._idf = data.get("idf", {})
            self._vocab = data.get("vocab", {})
            # vocab 的 value 可能從 JSON 讀為 str，轉回 int
            self._vocab = {k: int(v) for k, v in self._vocab.items()}
            logger.info(
                f"SparseEmbedder IDF loaded: {len(self._idf)} terms "
                f"({self._doc_count} docs)"
            )
        except Exception as e:
            logger.warning(f"Failed to load IDF: {e}")
