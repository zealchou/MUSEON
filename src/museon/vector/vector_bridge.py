"""VectorBridge — 語義搜尋統一門面.

整合 Qdrant 向量資料庫 + Embedder 嵌入引擎，提供：
- 7 個 collection（memories, skills, dna27, crystals, workflows, documents, references）
- index / search / batch 操作
- 完整 graceful degradation（Qdrant 或 fastembed 不可用時靜默失敗）

設計原則：
- 所有操作 try/except 包裝，不拋異常（不影響主流程）
- Lazy init：首次呼叫才連 Qdrant + 載入模型
- is_available() 結果快取 60 秒
"""

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.vector.embedder import Embedder

logger = logging.getLogger(__name__)

# Qdrant 連線
QDRANT_URL = "http://127.0.0.1:6333"

# 7 個 Collection 定義
COLLECTIONS: Dict[str, Dict[str, Any]] = {
    "memories": {"desc": "六層記憶語義索引"},
    "skills": {"desc": "技能語義匹配"},
    "dna27": {"desc": "DNA27 反射弧語義"},
    "crystals": {"desc": "知識晶體語義"},
    "workflows": {"desc": "工作流語義"},
    "documents": {"desc": "結構化資料語義索引"},
    "references": {"desc": "Zotero 文獻語義索引"},
    "primals": {"desc": "八原語語義偵測"},
}

# documents collection 的 payload index 定義
DOCUMENTS_PAYLOAD_INDEXES: Dict[str, str] = {
    "doc_type": "keyword",      # ledger, meeting, event, contact
    "user_id": "keyword",       # 使用者 ID（multitenancy 分隔）
    "created_at": "integer",    # UNIX timestamp（範圍查詢）
    "tags": "keyword",          # 標籤（多值 keyword）
}

# 可用性快取時間（秒）
_AVAILABILITY_CACHE_TTL = 60


class VectorBridge:
    """語義搜尋統一門面.

    Usage:
        vb = VectorBridge(workspace=Path("data"))
        if vb.is_available():
            vb.index("memories", "mem-001", "今天學會了新技能")
            results = vb.search("memories", "學技能", limit=5)
    """

    def __init__(self, workspace: Path, event_bus=None):
        """初始化 VectorBridge.

        Args:
            workspace: 工作目錄（brain.data_dir）
            event_bus: EventBus 實例（可選）
        """
        self._workspace = Path(workspace)
        self._event_bus = event_bus
        self._embedder: Optional[Embedder] = None
        self._client = None  # lazy QdrantClient
        self._available: Optional[bool] = None
        self._available_checked_at: float = 0.0
        self._subscribe()

    def _subscribe(self) -> None:
        """訂閱 MEMORY_STORED 作為備援索引路徑."""
        if not self._event_bus:
            return
        try:
            from museon.core.event_bus import MEMORY_STORED
            self._event_bus.subscribe(MEMORY_STORED, self._on_memory_stored)
        except Exception as e:
            logger.debug(f"[VECTOR_BRIDGE] memory failed (degraded): {e}")

    def _on_memory_stored(self, data: Optional[Dict] = None) -> None:
        """MEMORY_STORED 備援索引：若主流程索引失敗，此路徑補索引."""
        if not data or not self.is_available():
            return
        try:
            memory_id = data.get("memory_id", "")
            if not memory_id:
                return
            # 檢查是否已索引（避免重複）
            results = self.search("memories", memory_id, limit=1)
            if results and any(r.get("id") == memory_id for r in results):
                return
            # 備援索引（content 不在事件中，跳過）
        except Exception as e:
            logger.debug(f"[VECTOR_BRIDGE] memory failed (degraded): {e}")

    # ═══════════════════════════════════════════
    # 可用性檢查
    # ═══════════════════════════════════════════

    def is_available(self) -> bool:
        """檢查 Qdrant + Embedder 是否都可用.

        結果快取 60 秒。
        """
        now = time.time()
        if (
            self._available is not None
            and now - self._available_checked_at < _AVAILABILITY_CACHE_TTL
        ):
            return self._available

        try:
            client = self._get_client()
            if client is None:
                self._available = False
                self._available_checked_at = now
                return False

            embedder = self._get_embedder()
            if not embedder.is_available():
                self._available = False
                self._available_checked_at = now
                return False

            # 嘗試 Qdrant 連線
            client.get_collections()
            self._available = True
            self._available_checked_at = now
            return True

        except Exception as e:
            logger.debug(f"VectorBridge not available: {e}")
            self._available = False
            self._available_checked_at = now
            return False

    # ═══════════════════════════════════════════
    # 索引操作
    # ═══════════════════════════════════════════

    def index(
        self,
        collection: str,
        doc_id: str,
        text: str,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """嵌入 + 存入 Qdrant.

        失敗靜默（不影響主流程）。

        Args:
            collection: collection 名稱（memories, skills, ...）
            doc_id: 文件唯一 ID
            text: 要嵌入的文本
            metadata: 額外 metadata（會存入 payload）

        Returns:
            True if indexed, False otherwise.
        """
        if collection not in COLLECTIONS:
            logger.warning(f"Unknown collection: {collection}")
            return False

        try:
            embedder = self._get_embedder()
            vector = embedder.embed_single(text)
            if vector is None:
                return False

            client = self._get_client()
            if client is None:
                return False

            from qdrant_client.models import PointStruct

            # 確保 collection 存在
            self._ensure_collection(collection, embedder.dimension)

            payload = {
                "doc_id": doc_id,
                "text": text[:500],  # 限制 payload 大小
            }
            if metadata:
                payload.update(metadata)

            # 用 doc_id 的 hash 作為 point ID
            point_id = self._doc_id_to_point_id(doc_id)

            client.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload,
                    ),
                ],
            )

            # 發布 MEMORY_VECTOR_INDEXED 事件
            if self._event_bus and collection == "memories":
                try:
                    from museon.core.event_bus import MEMORY_VECTOR_INDEXED
                    self._event_bus.publish(MEMORY_VECTOR_INDEXED, {
                        "doc_id": doc_id,
                        "collection": collection,
                    })
                except Exception as e:
                    logger.debug(f"[VECTOR_BRIDGE] vector failed (degraded): {e}")

            return True

        except Exception as e:
            logger.debug(f"VectorBridge index failed: {e}")
            return False

    def index_batch(
        self,
        collection: str,
        items: List[Dict],
    ) -> int:
        """批次索引.

        Args:
            items: [{"id": str, "text": str, "metadata": dict}, ...]

        Returns:
            成功索引的數量。
        """
        if not items or collection not in COLLECTIONS:
            return 0

        try:
            embedder = self._get_embedder()
            texts = [item.get("text", "") for item in items]
            vectors = embedder.embed(texts)

            if not vectors or len(vectors) != len(items):
                return 0

            client = self._get_client()
            if client is None:
                return 0

            from qdrant_client.models import PointStruct

            self._ensure_collection(collection, embedder.dimension)

            points = []
            for item, vector in zip(items, vectors):
                doc_id = item.get("id", str(uuid.uuid4()))
                payload = {
                    "doc_id": doc_id,
                    "text": item.get("text", "")[:500],
                }
                if item.get("metadata"):
                    payload.update(item["metadata"])

                points.append(
                    PointStruct(
                        id=self._doc_id_to_point_id(doc_id),
                        vector=vector,
                        payload=payload,
                    )
                )

            client.upsert(
                collection_name=collection,
                points=points,
            )

            return len(points)

        except Exception as e:
            logger.debug(f"VectorBridge batch index failed: {e}")
            return 0

    # ═══════════════════════════════════════════
    # 搜尋操作
    # ═══════════════════════════════════════════

    def search(
        self,
        collection: str,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.3,
    ) -> List[Dict]:
        """語義搜尋.

        Args:
            collection: collection 名稱
            query: 查詢文本
            limit: 回傳上限
            score_threshold: 最低相似度分數

        Returns:
            [{id, score, text, metadata}, ...] 按 score 降序。
            搜尋失敗回傳空 list。
        """
        if collection not in COLLECTIONS:
            return []

        try:
            embedder = self._get_embedder()
            query_vector = embedder.embed_single(query)
            if query_vector is None:
                return []

            client = self._get_client()
            if client is None:
                return []

            # 確保 collection 存在
            self._ensure_collection(collection, embedder.dimension)

            # qdrant-client ≥1.7 uses query_points; fallback to search for older
            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name=collection,
                    query=query_vector,
                    limit=limit,
                    score_threshold=score_threshold,
                    with_payload=True,
                )
                hits = response.points
            else:
                hits = client.search(
                    collection_name=collection,
                    query_vector=query_vector,
                    limit=limit,
                    score_threshold=score_threshold,
                )

            return [
                {
                    "id": hit.payload.get("doc_id", str(hit.id)),
                    "score": hit.score,
                    "text": hit.payload.get("text", ""),
                    **{
                        k: v
                        for k, v in hit.payload.items()
                        if k not in ("doc_id", "text")
                    },
                }
                for hit in hits
            ]

        except Exception as e:
            logger.debug(f"VectorBridge search failed: {e}")
            return []

    # ═══════════════════════════════════════════
    # 管理操作
    # ═══════════════════════════════════════════

    def ensure_collections(self) -> Dict:
        """確保 6 個 collection 都存在.

        Returns:
            {"created": [...], "existing": [...], "error": str|None}
        """
        result = {"created": [], "existing": [], "error": None}

        try:
            client = self._get_client()
            if client is None:
                result["error"] = "qdrant_unavailable"
                return result

            embedder = self._get_embedder()
            dim = embedder.dimension

            for name in COLLECTIONS:
                try:
                    client.get_collection(name)
                    result["existing"].append(name)
                except Exception:
                    self._create_collection(name, dim)
                    result["created"].append(name)

            # 確保既有 collection 的 indexing_threshold 為 1000
            self._ensure_optimizers(client, result["existing"])

            # documents collection 需要額外建立 payload indexes
            self._ensure_payload_indexes("documents")

        except Exception as e:
            result["error"] = str(e)

        return result

    def get_stats(self) -> Dict:
        """取得各 collection 的統計.

        Returns:
            {collection_name: {"points": int, "status": str}, ...}
        """
        stats = {}
        try:
            client = self._get_client()
            if client is None:
                return {
                    name: {"points": 0, "status": "unavailable"}
                    for name in COLLECTIONS
                }

            for name in COLLECTIONS:
                try:
                    info = client.get_collection(name)
                    stats[name] = {
                        "points": info.points_count,
                        "status": str(info.status),
                    }
                except Exception:
                    stats[name] = {"points": 0, "status": "not_found"}

        except Exception as e:
            logger.debug(f"VectorBridge stats failed: {e}")
            stats = {
                name: {"points": 0, "status": "error"}
                for name in COLLECTIONS
            }

        return stats

    def delete_collection(self, collection: str) -> bool:
        """刪除 collection.

        Args:
            collection: collection 名稱

        Returns:
            True if deleted.
        """
        try:
            client = self._get_client()
            if client is None:
                return False

            client.delete_collection(collection_name=collection)
            return True

        except Exception as e:
            logger.debug(f"VectorBridge delete failed: {e}")
            return False

    # ═══════════════════════════════════════════
    # 私有方法
    # ═══════════════════════════════════════════

    def _get_embedder(self) -> Embedder:
        """Lazy 取得 Embedder."""
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    def _get_client(self):
        """Lazy 取得 QdrantClient."""
        if self._client is not None:
            return self._client

        try:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url=QDRANT_URL, timeout=5)
            return self._client

        except ImportError:
            logger.info(
                "qdrant-client not installed — "
                "VectorBridge unavailable"
            )
            return None

        except Exception as e:
            logger.debug(f"QdrantClient init failed: {e}")
            return None

    def _ensure_collection(self, name: str, dimension: int) -> None:
        """確保 collection 存在（不存在則建立）."""
        try:
            client = self._get_client()
            if client is None:
                return

            client.get_collection(name)

        except Exception:
            # Collection 不存在，建立
            self._create_collection(name, dimension)

    def _create_collection(self, name: str, dimension: int) -> None:
        """建立 collection."""
        try:
            client = self._get_client()
            if client is None:
                return

            from qdrant_client.models import (
                Distance,
                OptimizersConfigDiff,
                VectorParams,
            )

            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=Distance.COSINE,
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=1000,
                ),
            )
            logger.info(f"Created Qdrant collection: {name} (dim={dimension})")

        except Exception as e:
            logger.warning(f"Failed to create collection {name}: {e}")

    def _ensure_optimizers(self, client, collection_names: List[str]) -> None:
        """確保既有 collection 的 indexing_threshold 足夠低以建立 HNSW 索引."""
        try:
            from qdrant_client.models import OptimizersConfigDiff

            for name in collection_names:
                try:
                    info = client.get_collection(name)
                    current = getattr(
                        info.config.optimizer_config, "indexing_threshold", None
                    )
                    if current is not None and current > 1000:
                        client.update_collection(
                            collection_name=name,
                            optimizers_config=OptimizersConfigDiff(
                                indexing_threshold=1000,
                            ),
                        )
                        logger.info(
                            f"Updated {name} indexing_threshold: "
                            f"{current} → 1000"
                        )
                except Exception as e:
                    logger.debug(f"Skip optimizer check for {name}: {e}")
        except ImportError:
            pass

    def _ensure_payload_indexes(self, collection: str) -> None:
        """確保 payload indexes 存在（目前用於 documents collection）.

        靜默失敗，不影響主流程。
        """
        if collection not in COLLECTIONS:
            return

        indexes = DOCUMENTS_PAYLOAD_INDEXES if collection == "documents" else {}
        if not indexes:
            return

        try:
            client = self._get_client()
            if client is None:
                return

            from qdrant_client.models import PayloadSchemaType

            type_map = {
                "keyword": PayloadSchemaType.KEYWORD,
                "integer": PayloadSchemaType.INTEGER,
                "float": PayloadSchemaType.FLOAT,
                "text": PayloadSchemaType.TEXT,
            }

            for field_name, field_type in indexes.items():
                try:
                    schema_type = type_map.get(field_type)
                    if schema_type is None:
                        continue
                    client.create_payload_index(
                        collection_name=collection,
                        field_name=field_name,
                        field_schema=schema_type,
                    )
                    logger.debug(
                        f"Created payload index: {collection}.{field_name} "
                        f"({field_type})"
                    )
                except Exception:
                    # Index 可能已存在，靜默略過
                    pass

        except Exception as e:
            logger.debug(f"Failed to ensure payload indexes: {e}")

    def search_documents(
        self,
        query: str,
        doc_type: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 10,
        score_threshold: float = 0.3,
    ) -> List[Dict]:
        """搜尋 documents collection（支援 payload filter）.

        Args:
            query: 查詢文本
            doc_type: 文件類型篩選（ledger, meeting, event, contact）
            user_id: 使用者 ID 篩選
            limit: 回傳上限
            score_threshold: 最低相似度分數

        Returns:
            搜尋結果列表
        """
        try:
            embedder = self._get_embedder()
            query_vector = embedder.embed_single(query)
            if query_vector is None:
                return []

            client = self._get_client()
            if client is None:
                return []

            self._ensure_collection("documents", embedder.dimension)

            # 建立 filter
            must_conditions = []
            if doc_type:
                from qdrant_client.models import FieldCondition, MatchValue
                must_conditions.append(
                    FieldCondition(
                        key="doc_type",
                        match=MatchValue(value=doc_type),
                    )
                )
            if user_id:
                from qdrant_client.models import FieldCondition, MatchValue
                must_conditions.append(
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    )
                )

            query_filter = None
            if must_conditions:
                from qdrant_client.models import Filter
                query_filter = Filter(must=must_conditions)

            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name="documents",
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=score_threshold,
                    with_payload=True,
                )
                hits = response.points
            else:
                hits = client.search(
                    collection_name="documents",
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=score_threshold,
                )

            return [
                {
                    "id": hit.payload.get("doc_id", str(hit.id)),
                    "score": hit.score,
                    "text": hit.payload.get("text", ""),
                    **{
                        k: v
                        for k, v in hit.payload.items()
                        if k not in ("doc_id", "text")
                    },
                }
                for hit in hits
            ]

        except Exception as e:
            logger.debug(f"VectorBridge search_documents failed: {e}")
            return []

    @staticmethod
    def _doc_id_to_point_id(doc_id: str) -> str:
        """將 doc_id 轉為 Qdrant 相容的 UUID point ID.

        Qdrant 支援 UUID 或 int 作為 point ID。
        使用 UUID5 從 doc_id 產生確定性 UUID（相同 doc_id → 相同 UUID）。
        """
        return str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))
