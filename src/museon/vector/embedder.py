"""Embedder — 可插拔的嵌入向量產生器.

預設引擎：fastembed（Qdrant 團隊出品，輕量 ONNX Runtime）。
支援中文 bge 系列模型，不依賴 Ollama。

Graceful degradation：fastembed 不可用時回傳空 list，
由 VectorBridge 層降級到 TF-IDF。
"""

import logging
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)

# 預設模型：bge-small-zh-v1.5（512 維，~100MB，中英文雙語）
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_DIMENSION = 512

_GLOBAL_EMBEDDER = None
_EMBEDDER_LOCK = threading.Lock()


def get_global_embedder():
    """全域 Embedder Singleton — 整個 MUSEON 只載入一次模型."""
    global _GLOBAL_EMBEDDER
    if _GLOBAL_EMBEDDER is None:
        with _EMBEDDER_LOCK:
            if _GLOBAL_EMBEDDER is None:
                _GLOBAL_EMBEDDER = Embedder()
    return _GLOBAL_EMBEDDER


class Embedder:
    """可插拔的嵌入向量產生器.

    使用 fastembed 做本地 embedding，支援中英文。
    Lazy init：首次 embed() 才載入模型。

    Usage:
        embedder = Embedder()
        vectors = embedder.embed(["你好世界", "Hello World"])
        # vectors: [[0.1, 0.2, ...], [0.3, 0.4, ...]]  # 512-dim each
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
    ):
        """初始化 Embedder.

        Args:
            model_name: fastembed 模型名稱
            dimension: 向量維度（需與模型匹配）
        """
        self._model_name = model_name
        self._dimension = dimension
        self._model = None  # lazy init
        self._available: Optional[bool] = None

    def embed(self, texts: List[str]) -> List[List[float]]:
        """批次嵌入文本為向量.

        Args:
            texts: 要嵌入的文本列表

        Returns:
            向量列表。若 fastembed 不可用，回傳空 list。
        """
        if not texts:
            return []

        try:
            model = self._get_model()
            if model is None:
                return []

            # fastembed 的 embed() 回傳 generator
            embeddings = list(model.embed(texts))
            # 轉為 Python list（fastembed 回傳 numpy array）
            return [emb.tolist() for emb in embeddings]

        except Exception as e:
            logger.warning(f"Embedding failed: {e}")
            self._available = False
            return []

    def embed_single(self, text: str) -> Optional[List[float]]:
        """嵌入單一文本.

        Args:
            text: 要嵌入的文本

        Returns:
            向量（list of float），或 None。
        """
        results = self.embed([text])
        return results[0] if results else None

    @property
    def dimension(self) -> int:
        """向量維度."""
        return self._dimension

    @property
    def model_name(self) -> str:
        """模型名稱."""
        return self._model_name

    def is_available(self) -> bool:
        """檢查 fastembed 是否可用.

        首次呼叫會嘗試 import + 載入模型。
        結果會快取。
        """
        if self._available is not None:
            return self._available

        try:
            model = self._get_model()
            self._available = model is not None
        except Exception:
            self._available = False

        return self._available

    def _get_model(self):
        """Lazy 初始化 fastembed TextEmbedding 模型."""
        if self._model is not None:
            return self._model

        try:
            from fastembed import TextEmbedding  # noqa: F811

            self._model = TextEmbedding(
                model_name=self._model_name,
            )
            self._available = True
            logger.info(
                f"Embedder loaded: {self._model_name} "
                f"(dim={self._dimension})"
            )
            return self._model

        except ImportError:
            logger.info(
                "fastembed not installed — "
                "VectorBridge will degrade to TF-IDF"
            )
            self._available = False
            return None

        except Exception as e:
            logger.warning(f"Failed to load embedder: {e}")
            self._available = False
            return None
