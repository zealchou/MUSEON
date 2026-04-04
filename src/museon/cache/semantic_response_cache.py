"""Semantic Response Cache — 零 LLM 語意快取層.

用本地 embedding（fastembed）+ Qdrant 實現語意查詢匹配，
命中時直接返回快取的回覆，省掉完整的 L2 LLM 呼叫。

設計原則：
  - 零 LLM token 消耗（embedding 在 CPU 本地計算）
  - 按 chat_id 嚴格隔離（群組 A 的快取查不到群組 B）
  - 不快取情緒型/時間敏感型回覆
  - TTL 依訊號類型動態調整

v12 Token 優化第三刀的核心組件。
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Cache TTL by signal type (seconds)
_TTL_CONFIG = {
    "default": 6 * 3600,          # 6 hours
    "market_business": 1800,       # 30 min (market data changes fast)
    "planning_mode": 3600,         # 1 hour
    "growth_seeking": 12 * 3600,   # 12 hours (knowledge is stable)
    "time_sensitive": 1800,        # 30 min
}

# Signals that should NOT be cached
_NO_CACHE_SIGNALS = frozenset([
    "emotional_intensity",
    "relationship_dynamic",
])

# Minimum query length to cache (too short = too ambiguous)
# 中文每字 ≈ 1 token，8 字已足夠辨識意圖（如「幫我分析品牌定位」）
_MIN_QUERY_LENGTH = 8

# Similarity threshold for cache hit
_SIMILARITY_THRESHOLD = 0.92


class SemanticResponseCache:
    """Qdrant-backed semantic response cache with per-chat isolation.

    Usage:
        cache = SemanticResponseCache(qdrant_url="localhost", qdrant_port=6333)

        # Query (before LLM call)
        hit = cache.query(chat_id="group_123", query="今天有什麼行程？")
        if hit:
            return hit  # Skip LLM entirely

        # Write (after LLM reply, from L4 CPU Observer)
        cache.write(
            chat_id="group_123",
            query="今天有什麼行程？",
            response="根據你的日曆...",
            signals={"planning_mode": 0.6},
        )
    """

    COLLECTION_NAME = "semantic_response_cache"
    VECTOR_DIM = 512  # BAAI/bge-small-zh-v1.5

    def __init__(
        self,
        qdrant_url: str = "localhost",
        qdrant_port: int = 6333,
    ):
        self._qdrant_url = qdrant_url
        self._qdrant_port = qdrant_port
        self._encoder = None
        self._client = None
        self._initialized = False

    def _ensure_initialized(self) -> bool:
        """Lazy init: only connect when first needed."""
        if self._initialized:
            return True
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import (
                Distance, VectorParams, PayloadSchemaType,
            )
            self._client = QdrantClient(
                url=self._qdrant_url,
                port=self._qdrant_port,
                timeout=5,
            )
            # Ensure collection exists
            collections = [c.name for c in self._client.get_collections().collections]
            if self.COLLECTION_NAME not in collections:
                self._client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_DIM,
                        distance=Distance.COSINE,
                    ),
                )
                # Create payload index for chat_id filtering
                self._client.create_payload_index(
                    collection_name=self.COLLECTION_NAME,
                    field_name="chat_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                )
                logger.info(f"[SemanticCache] Created collection: {self.COLLECTION_NAME}")

            # Init local embedder (use MUSEON global singleton)
            from museon.vector.embedder import get_global_embedder
            self._encoder = get_global_embedder()
            self._initialized = True
            return True
        except Exception as e:
            logger.warning(f"[SemanticCache] Init failed (degraded, no cache): {e}")
            return False

    def _encode(self, text: str) -> Optional[list]:
        """Encode text to vector using local fastembed."""
        if not self._encoder:
            return None
        try:
            vectors = self._encoder.embed([text])
            if vectors and len(vectors) > 0:
                v = vectors[0]
                return v.tolist() if hasattr(v, 'tolist') else list(v)
        except Exception as e:
            logger.debug(f"[SemanticCache] Encode error: {e}")
        return None

    def should_cache(self, query: str, signals: Dict[str, float]) -> bool:
        """Determine if this query/response should be cached."""
        if len(query.strip()) < _MIN_QUERY_LENGTH:
            return False
        # Don't cache emotional or relationship queries
        for sig in _NO_CACHE_SIGNALS:
            if signals.get(sig, 0) > 0.5:
                return False
        # Don't cache commands
        if query.strip().startswith("/"):
            return False
        return True

    def _get_ttl(self, signals: Dict[str, float]) -> int:
        """Determine TTL based on signal type."""
        # Find the strongest signal
        if not signals:
            return _TTL_CONFIG["default"]
        strongest = max(signals.items(), key=lambda x: x[1])
        return _TTL_CONFIG.get(strongest[0], _TTL_CONFIG["default"])

    def query(
        self,
        chat_id: str,
        query: str,
        threshold: float = _SIMILARITY_THRESHOLD,
    ) -> Optional[str]:
        """Query cache for a similar response. Returns cached response or None.

        Zero LLM tokens consumed. ~60ms latency (embedding + Qdrant search).
        """
        if not self._ensure_initialized():
            return None
        if len(query.strip()) < _MIN_QUERY_LENGTH:
            return None

        vector = self._encode(query)
        if not vector:
            return None

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            results = self._client.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=vector,
                query_filter=Filter(must=[
                    FieldCondition(
                        key="chat_id",
                        match=MatchValue(value=str(chat_id)),
                    ),
                ]),
                limit=1,
                score_threshold=threshold,
            )

            if not results:
                return None

            hit = results[0]
            payload = hit.payload or {}

            # Check TTL
            created_at = payload.get("created_at", 0)
            ttl = payload.get("ttl", _TTL_CONFIG["default"])
            if time.time() - created_at > ttl:
                # Expired — delete and return None
                try:
                    self._client.delete(
                        collection_name=self.COLLECTION_NAME,
                        points_selector=[hit.id],
                    )
                except Exception:
                    pass
                return None

            logger.info(
                f"[SemanticCache] HIT (score={hit.score:.3f}) "
                f"chat={chat_id} query='{query[:30]}...'"
            )
            return payload.get("response")

        except Exception as e:
            logger.debug(f"[SemanticCache] Query error: {e}")
            return None

    def write(
        self,
        chat_id: str,
        query: str,
        response: str,
        signals: Optional[Dict[str, float]] = None,
    ) -> bool:
        """Write a query-response pair to cache.

        Called by L4 CPU Observer after each reply.
        """
        signals = signals or {}
        if not self.should_cache(query, signals):
            return False
        if not self._ensure_initialized():
            return False

        vector = self._encode(query)
        if not vector:
            return False

        ttl = self._get_ttl(signals)
        point_id = str(uuid.uuid4())

        try:
            from qdrant_client.models import PointStruct

            self._client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "chat_id": str(chat_id),
                        "query": query[:500],
                        "response": response[:3000],
                        "signals": signals,
                        "ttl": ttl,
                        "created_at": time.time(),
                        "created_at_iso": datetime.now(timezone.utc).isoformat(),
                    },
                )],
            )
            logger.debug(
                f"[SemanticCache] WRITE chat={chat_id} "
                f"query='{query[:30]}...' ttl={ttl}s"
            )
            return True
        except Exception as e:
            logger.debug(f"[SemanticCache] Write error: {e}")
            return False

    def clear_chat(self, chat_id: str) -> int:
        """Clear all cached responses for a specific chat. Returns count deleted."""
        if not self._ensure_initialized():
            return 0
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            result = self._client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=Filter(must=[
                    FieldCondition(
                        key="chat_id",
                        match=MatchValue(value=str(chat_id)),
                    ),
                ]),
            )
            return getattr(result, 'deleted_count', 0)
        except Exception as e:
            logger.debug(f"[SemanticCache] Clear error: {e}")
            return 0

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self._ensure_initialized():
            return {"status": "not_initialized"}
        try:
            info = self._client.get_collection(self.COLLECTION_NAME)
            return {
                "status": "ok",
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
