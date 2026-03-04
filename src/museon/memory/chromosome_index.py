"""ChromosomeIndex — TF-IDF + jieba 語義搜尋引擎.

依據 SIX_LAYER_MEMORY BDD Spec §5 實作：
  - 零外部 API：純 Python TF-IDF + jieba 分詞
  - 零 Token 消耗：不呼叫任何 LLM
  - 稀疏向量：Dict[str, float]（非 dense embedding）
  - 執行緒安全：RLock
  - Tag Boosting：每個 tag 重複 3 次
  - IDF 公式：log(N / df) + 1.0（smoothed）
"""

import json
import logging
import threading
from collections import Counter
from math import log, sqrt
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Tag boosting: 每個 tag 重複次數
_TAG_BOOST = 3

# Token 最小長度
_MIN_TOKEN_LEN = 2

# 聚類預設閾值
_DEFAULT_CLUSTER_THRESHOLD = 0.5


# ═══════════════════════════════════════════
# Tokenizer (jieba lazy load)
# ═══════════════════════════════════════════

_jieba = None
_jieba_lock = threading.Lock()


def _get_jieba():
    """懶載入 jieba."""
    global _jieba
    if _jieba is None:
        with _jieba_lock:
            if _jieba is None:
                import jieba as _jb
                _jb.setLogLevel(logging.WARNING)
                _jieba = _jb
    return _jieba


def _tokenize(text: str) -> List[str]:
    """jieba 中文分詞 + 英文 token 化.

    - 過濾 < 2 字元的 token
    - 全部轉小寫
    """
    if not text:
        return []

    jb = _get_jieba()
    tokens = []
    for word in jb.cut(text):
        word = word.strip().lower()
        if len(word) >= _MIN_TOKEN_LEN:
            tokens.append(word)
    return tokens


# ═══════════════════════════════════════════
# Cosine Similarity
# ═══════════════════════════════════════════


def cosine_similarity(
    vec_a: Dict[str, float], vec_b: Dict[str, float],
) -> float:
    """計算兩個稀疏向量的餘弦相似度."""
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0

    dot = sum(vec_a[k] * vec_b[k] for k in common)
    norm_a = sqrt(sum(v * v for v in vec_a.values()))
    norm_b = sqrt(sum(v * v for v in vec_b.values()))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


# ═══════════════════════════════════════════
# ChromosomeIndex
# ═══════════════════════════════════════════


class ChromosomeIndex:
    """TF-IDF 語義搜尋索引.

    每筆文件以稀疏 TF-IDF 向量表示，搜尋時計算餘弦相似度。
    """

    def __init__(self, persist_path: Optional[str] = None):
        self._lock = threading.RLock()
        self._docs: Dict[str, Dict] = {}  # {memory_id: {tf, tags, token_count}}
        self._idf_cache: Dict[str, float] = {}
        self._idf_dirty: bool = True
        self._persist_path: Optional[Path] = (
            Path(persist_path) if persist_path else None
        )

        # 初始化時嘗試載入
        if self._persist_path:
            self._load()

    # ─── Index ───

    def index(
        self,
        memory_id: str,
        text: str,
        tags: Optional[List[str]] = None,
    ) -> None:
        """索引一筆記憶.

        Args:
            memory_id: 記憶 UUID
            text: 記憶內容文本
            tags: 可搜尋標籤（Tag Boosting ×3）
        """
        with self._lock:
            tokens = _tokenize(text)

            # Tag Boosting
            if tags:
                for tag in tags:
                    tag_lower = tag.lower().strip()
                    if len(tag_lower) >= _MIN_TOKEN_LEN:
                        tokens.extend([tag_lower] * _TAG_BOOST)

            if not tokens:
                return

            tf = Counter(tokens)
            self._docs[memory_id] = {
                "tf": tf,
                "tags": set(tags or []),
                "token_count": len(tokens),
            }
            self._idf_dirty = True

    def remove(self, memory_id: str) -> None:
        """從索引中移除一筆記憶."""
        with self._lock:
            if memory_id in self._docs:
                del self._docs[memory_id]
                self._idf_dirty = True

    # ─── IDF ───

    def _ensure_idf(self) -> None:
        """懶重算 IDF cache（需在 lock 內呼叫）."""
        if not self._idf_dirty:
            return

        n = len(self._docs)
        if n == 0:
            self._idf_cache = {}
            self._idf_dirty = False
            return

        # 計算 document frequency
        df: Dict[str, int] = {}
        for doc in self._docs.values():
            for token in doc["tf"]:
                df[token] = df.get(token, 0) + 1

        # IDF = log(N / df) + 1.0（smoothed）
        self._idf_cache = {
            token: log(n / freq) + 1.0
            for token, freq in df.items()
        }
        self._idf_dirty = False

    def _tf_idf_vector(
        self, tf: Counter, token_count: int,
    ) -> Dict[str, float]:
        """計算 TF-IDF 稀疏向量（需在 lock 內 + IDF 已更新）."""
        vec: Dict[str, float] = {}
        for token, count in tf.items():
            idf = self._idf_cache.get(token, 1.0)
            tf_norm = count / token_count if token_count > 0 else 0
            vec[token] = tf_norm * idf
        return vec

    # ─── Search ───

    def search(
        self, query: str, top_k: int = 10,
    ) -> List[Tuple[str, float]]:
        """TF-IDF 語義搜尋.

        Args:
            query: 查詢文本
            top_k: 回傳前 K 筆

        Returns:
            [(memory_id, similarity_score), ...] 降序排列
        """
        with self._lock:
            if not self._docs:
                return []

            self._ensure_idf()

            # Query → TF-IDF vector
            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            query_tf = Counter(query_tokens)
            query_vec = self._tf_idf_vector(query_tf, len(query_tokens))

            # 計算相似度
            results: List[Tuple[str, float]] = []
            for memory_id, doc in self._docs.items():
                doc_vec = self._tf_idf_vector(doc["tf"], doc["token_count"])
                sim = cosine_similarity(query_vec, doc_vec)
                if sim > 0.0:
                    results.append((memory_id, sim))

            # 降序排列
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:top_k]

    # ─── Cluster ───

    def cluster(
        self,
        memory_ids: Optional[List[str]] = None,
        threshold: float = _DEFAULT_CLUSTER_THRESHOLD,
    ) -> List[List[str]]:
        """貪心層級聚類.

        Args:
            memory_ids: 要聚類的記憶 ID（None = 全部）
            threshold: 相似度閾值

        Returns:
            [[memory_id, ...], ...] 群組列表
        """
        with self._lock:
            self._ensure_idf()

            target_ids = memory_ids or list(self._docs.keys())
            if not target_ids:
                return []

            # 預算所有向量
            vectors: Dict[str, Dict[str, float]] = {}
            for mid in target_ids:
                doc = self._docs.get(mid)
                if doc:
                    vectors[mid] = self._tf_idf_vector(
                        doc["tf"], doc["token_count"],
                    )

            groups: List[List[str]] = []
            centroids: List[Dict[str, float]] = []

            for mid, vec in vectors.items():
                placed = False
                for i, centroid in enumerate(centroids):
                    if cosine_similarity(vec, centroid) >= threshold:
                        groups[i].append(mid)
                        # 更新質心：元素平均
                        centroids[i] = self._avg_vectors(
                            [vectors[m] for m in groups[i]],
                        )
                        placed = True
                        break

                if not placed:
                    groups.append([mid])
                    centroids.append(vec)

            return groups

    @staticmethod
    def _avg_vectors(
        vecs: List[Dict[str, float]],
    ) -> Dict[str, float]:
        """計算向量的元素平均."""
        if not vecs:
            return {}
        all_keys: Set[str] = set()
        for v in vecs:
            all_keys.update(v.keys())
        n = len(vecs)
        return {
            k: sum(v.get(k, 0.0) for v in vecs) / n
            for k in all_keys
        }

    # ─── Stats ───

    def doc_count(self) -> int:
        """索引中的文件數."""
        with self._lock:
            return len(self._docs)

    def contains(self, memory_id: str) -> bool:
        """檢查記憶是否在索引中."""
        with self._lock:
            return memory_id in self._docs

    # ─── Persistence ───

    def save(self) -> None:
        """持久化索引到 JSON 檔案."""
        if not self._persist_path:
            return

        with self._lock:
            data = {
                "docs": {
                    mid: {
                        "tf": dict(doc["tf"]),
                        "tags": list(doc["tags"]),
                        "token_count": doc["token_count"],
                    }
                    for mid, doc in self._docs.items()
                },
            }

        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except OSError as e:
            logger.error(f"ChromosomeIndex save error: {e}")

    def _load(self) -> None:
        """從 JSON 檔案載入索引."""
        if not self._persist_path or not self._persist_path.exists():
            return

        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            with self._lock:
                for mid, doc_data in data.get("docs", {}).items():
                    self._docs[mid] = {
                        "tf": Counter(doc_data.get("tf", {})),
                        "tags": set(doc_data.get("tags", [])),
                        "token_count": doc_data.get("token_count", 0),
                    }
                self._idf_dirty = True

            logger.debug(
                f"ChromosomeIndex loaded {len(self._docs)} docs "
                f"from {self._persist_path}"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"ChromosomeIndex load error: {e}")
