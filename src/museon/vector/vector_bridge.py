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
from museon.vector.sparse_embedder import SparseEmbedder

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
        self._sparse_embedder: Optional[SparseEmbedder] = None
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
        filter_deprecated: bool = True,
    ) -> List[Dict]:
        """語義搜尋.

        Args:
            collection: collection 名稱
            query: 查詢文本
            limit: 回傳上限
            score_threshold: 最低相似度分數
            filter_deprecated: 是否過濾已廢棄的向量（預設 True）

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

            # 構建 Qdrant Filter（過濾 deprecated 向量）
            query_filter = None
            if filter_deprecated:
                try:
                    from qdrant_client.models import Filter, FieldCondition, MatchValue
                    query_filter = Filter(
                        must_not=[
                            FieldCondition(
                                key="status",
                                match=MatchValue(value="deprecated"),
                            )
                        ]
                    )
                except ImportError:
                    pass  # 舊版 qdrant-client，降級為不過濾

            # qdrant-client ≥1.7 uses query_points; fallback to search for older
            if hasattr(client, "query_points"):
                kwargs = {
                    "collection_name": collection,
                    "query": query_vector,
                    "limit": limit,
                    "score_threshold": score_threshold,
                    "with_payload": True,
                }
                if query_filter is not None:
                    kwargs["query_filter"] = query_filter
                response = client.query_points(**kwargs)
                hits = response.points
            else:
                kwargs = {
                    "collection_name": collection,
                    "query_vector": query_vector,
                    "limit": limit,
                    "score_threshold": score_threshold,
                }
                if query_filter is not None:
                    kwargs["query_filter"] = query_filter
                hits = client.search(**kwargs)

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
    # 記憶廢棄標記（P0 事實覆寫）
    # ═══════════════════════════════════════════

    def mark_deprecated(
        self,
        collection: str,
        doc_id: str,
    ) -> bool:
        """將指定向量標記為 deprecated（軟刪除）.

        被標記的向量在 search() 中會被自動過濾。

        Args:
            collection: collection 名稱
            doc_id: 文件唯一 ID

        Returns:
            True if marked, False otherwise.
        """
        if collection not in COLLECTIONS:
            return False

        try:
            client = self._get_client()
            if client is None:
                return False

            from qdrant_client.models import SetPayloadOperation, PointIdsList

            point_id = self._doc_id_to_point_id(doc_id)

            client.set_payload(
                collection_name=collection,
                payload={"status": "deprecated"},
                points=[point_id],
            )

            logger.info(
                f"VectorBridge mark_deprecated: {collection}/{doc_id}"
            )
            return True

        except Exception as e:
            logger.debug(f"VectorBridge mark_deprecated failed: {e}")
            return False

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
    # 全量索引操作
    # ═══════════════════════════════════════════

    def index_all_skills(self, skills_dir: str | Path | None = None) -> dict:
        """全量索引所有 Skill 到 Qdrant skills collection.

        讀取 data/skills/native/ 下所有 SKILL.md，
        組合 name + description + triggers 為可搜尋文本。

        Args:
            skills_dir: Skill 目錄路徑（預設自動偵測）

        Returns:
            {"indexed": int, "errors": list[str]}
        """
        import re

        result = {"indexed": 0, "errors": []}

        if not self.is_available():
            result["errors"].append("vector_bridge_unavailable")
            return result

        # 自動偵測 skills_dir
        if skills_dir is None:
            candidate = self._workspace / "skills" / "native"
            if not candidate.exists():
                # 嘗試上一級 data/skills/native/
                candidate = self._workspace.parent / "data" / "skills" / "native"
            if not candidate.exists():
                candidate = self._workspace / "skills" / "native"
            skills_dir = Path(candidate)
        else:
            skills_dir = Path(skills_dir)

        if not skills_dir.exists():
            result["errors"].append(f"skills_dir_not_found: {skills_dir}")
            return result

        # 掃描所有子目錄的 SKILL.md
        skill_dirs = sorted(
            d for d in skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        )

        for skill_path in skill_dirs:
            skill_name = skill_path.name
            skill_file = skill_path / "SKILL.md"

            try:
                raw = skill_file.read_text(encoding="utf-8")

                # 解析 YAML frontmatter
                name = skill_name
                layer = ""
                skill_type = ""
                description_text = ""
                triggers = ""

                # 嘗試解析 YAML frontmatter（--- ... ---）
                fm_match = re.match(
                    r"^---\s*\n(.*?)\n---\s*\n(.*)",
                    raw,
                    re.DOTALL,
                )
                if fm_match:
                    fm_block = fm_match.group(1)
                    body = fm_match.group(2)

                    # 簡易 YAML 解析（避免引入 pyyaml 依賴）
                    for line in fm_block.splitlines():
                        line_stripped = line.strip()
                        if line_stripped.startswith("name:"):
                            name = line_stripped.split(":", 1)[1].strip()
                        elif line_stripped.startswith("layer:"):
                            layer = line_stripped.split(":", 1)[1].strip()
                        elif line_stripped.startswith("type:"):
                            skill_type = line_stripped.split(":", 1)[1].strip()

                    # 從 description 欄位提取（多行 YAML）
                    desc_match = re.search(
                        r"description:\s*>?\s*\n((?:\s{2,}.*\n)*)",
                        fm_block,
                    )
                    if desc_match:
                        description_text = desc_match.group(1).strip()

                    # 如果 frontmatter description 不夠，用 body 前 500 字補充
                    if len(description_text) < 50:
                        description_text = body[:500]
                else:
                    # 沒有 frontmatter，使用整個文件前 500 字
                    body = raw
                    description_text = raw[:500]

                # 從正文提取觸發詞段落
                trigger_match = re.search(
                    r"觸發[詞時條件][:：]\s*(.+?)(?:\n\n|\n#|\Z)",
                    raw,
                    re.DOTALL,
                )
                if trigger_match:
                    triggers = trigger_match.group(1).strip()[:200]

                # 組合可搜尋文本
                searchable_text = (
                    f"{name} {layer} {skill_type} "
                    f"{triggers} {description_text[:500]}"
                ).strip()

                metadata = {
                    "name": name,
                    "layer": layer,
                    "type": skill_type,
                    "triggers": triggers[:200],
                    "source": "skills/native",
                }

                # 索引到 dense collection
                indexed = self.index(
                    "skills", skill_name, searchable_text, metadata=metadata
                )

                # 嘗試索引到 sparse collection
                try:
                    self.index_sparse(
                        "skills", skill_name, searchable_text, metadata=metadata
                    )
                except Exception:
                    pass  # sparse 不可用時靜默

                if indexed:
                    result["indexed"] += 1
                else:
                    result["errors"].append(f"index_failed: {skill_name}")

            except Exception as e:
                result["errors"].append(f"{skill_name}: {e}")

        logger.info(
            f"[VECTOR_BRIDGE] Skills indexed: {result['indexed']}/{len(skill_dirs)}"
            + (f", errors: {len(result['errors'])}" if result["errors"] else "")
        )

        return result

    def reindex_all(self, workspace: str | Path | None = None) -> dict:
        """全量重索引所有 collection（用於 Qdrant 重建後恢復）.

        Args:
            workspace: 工作目錄（可選，預設使用 self._workspace）

        Returns:
            {"skills": {...}, ...}
        """
        results = {}

        # Skills 全量重索引
        try:
            results["skills"] = self.index_all_skills()
        except Exception as e:
            logger.warning(f"[VECTOR_BRIDGE] Skills reindex failed: {e}")
            results["skills"] = {"indexed": 0, "errors": [str(e)]}

        # crystals 和 memories 的重索引留給各自的模組
        # （knowledge_lattice.py 管 crystals、memory_manager.py 管 memories）

        return results

    # ═══════════════════════════════════════════
    # 私有方法
    # ═══════════════════════════════════════════

    def _get_embedder(self) -> Embedder:
        """Lazy 取得 Embedder."""
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    def _get_sparse_embedder(self) -> SparseEmbedder:
        """Lazy 取得 SparseEmbedder."""
        if self._sparse_embedder is None:
            self._sparse_embedder = SparseEmbedder(workspace=self._workspace)
        return self._sparse_embedder

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

    # ═══════════════════════════════════════════
    # 混合檢索（Dense + Sparse → RRF 融合）
    # ═══════════════════════════════════════════

    def hybrid_search(
        self,
        collection: str,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.3,
        rrf_k: int = 60,
    ) -> List[Dict]:
        """混合檢索：Dense（語義）+ Sparse（BM25）→ RRF 融合.

        同時查詢 dense collection 和對應的 sparse collection，
        用 Reciprocal Rank Fusion 合併排名。

        若 sparse collection 不存在或 IDF 未建立，降級為純 dense 搜尋。

        Args:
            collection: collection 名稱（memories, crystals, ...）
            query: 查詢文本
            limit: 回傳上限
            score_threshold: dense search 的最低相似度分數
            rrf_k: RRF 參數（預設 60）

        Returns:
            [{id, score, text, metadata}, ...] 按 RRF score 降序。
        """
        # Phase 1: Dense search（一定執行）
        dense_results = self.search(
            collection=collection,
            query=query,
            limit=limit * 2,  # 多取一些供融合
            score_threshold=score_threshold,
        )

        # Phase 2: Sparse search（可選）
        sparse_results = self._sparse_search(
            collection=collection,
            query=query,
            limit=limit * 2,
        )

        # Phase 3: 如果沒有 sparse 結果，直接回 dense
        if not sparse_results:
            return dense_results[:limit]

        # Phase 4: RRF 融合
        merged = self._rrf_merge(
            dense_results=dense_results,
            sparse_results=sparse_results,
            k=rrf_k,
        )

        return merged[:limit]

    def _sparse_search(
        self,
        collection: str,
        query: str,
        limit: int = 20,
    ) -> List[Dict]:
        """稀疏向量搜尋（BM25）.

        使用 {collection}_sparse collection。

        Args:
            collection: 原始 collection 名稱
            query: 查詢文本
            limit: 回傳上限

        Returns:
            [{id, score, text}, ...] 按 score 降序。
            若 sparse collection 不存在或 IDF 未建立，回傳空 list。
        """
        sparse_collection = f"{collection}_sparse"
        sparse_embedder = self._get_sparse_embedder()

        if not sparse_embedder.is_available() or not sparse_embedder.has_idf():
            return []

        try:
            client = self._get_client()
            if client is None:
                return []

            # 檢查 sparse collection 是否存在
            try:
                client.get_collection(sparse_collection)
            except Exception:
                return []  # collection 不存在，靜默降級

            # 編碼 query 為稀疏向量
            indices, values = sparse_embedder.encode(query)
            if not indices:
                return []

            from qdrant_client.models import SparseVector, NamedSparseVector

            # Qdrant sparse vector search
            if hasattr(client, "query_points"):
                response = client.query_points(
                    collection_name=sparse_collection,
                    query=SparseVector(indices=indices, values=values),
                    using="bm25",
                    limit=limit,
                    with_payload=True,
                )
                hits = response.points
            else:
                # 舊版 API fallback
                return []

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
            logger.debug(f"VectorBridge sparse search failed: {e}")
            return []

    @staticmethod
    def _rrf_merge(
        dense_results: List[Dict],
        sparse_results: List[Dict],
        k: int = 60,
    ) -> List[Dict]:
        """Reciprocal Rank Fusion 合併兩組排名結果.

        RRF_score(d) = Σ 1/(k + rank_i(d))

        Args:
            dense_results: Dense 搜尋結果
            sparse_results: Sparse 搜尋結果
            k: RRF 常數（預設 60）

        Returns:
            合併後的結果，按 RRF score 降序。
        """
        scores: Dict[str, float] = {}
        items: Dict[str, Dict] = {}

        # Dense 排名分數
        for rank, item in enumerate(dense_results):
            doc_id = item.get("id", "")
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            if doc_id not in items:
                items[doc_id] = item

        # Sparse 排名分數
        for rank, item in enumerate(sparse_results):
            doc_id = item.get("id", "")
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
            if doc_id not in items:
                items[doc_id] = item

        # 按 RRF score 排序
        sorted_ids = sorted(scores.keys(), key=lambda d: -scores[d])

        result = []
        for doc_id in sorted_ids:
            item = items[doc_id].copy()
            item["rrf_score"] = round(scores[doc_id], 6)
            result.append(item)

        return result

    def index_sparse(
        self,
        collection: str,
        doc_id: str,
        text: str,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """將文本索引到 sparse collection.

        Args:
            collection: 原始 collection 名稱
            doc_id: 文件唯一 ID
            text: 要索引的文本
            metadata: 額外 metadata

        Returns:
            True if indexed, False otherwise.
        """
        sparse_collection = f"{collection}_sparse"
        sparse_embedder = self._get_sparse_embedder()

        if not sparse_embedder.is_available() or not sparse_embedder.has_idf():
            return False

        try:
            client = self._get_client()
            if client is None:
                return False

            indices, values = sparse_embedder.encode(text)
            if not indices:
                return False

            from qdrant_client.models import PointStruct, SparseVector

            # 確保 sparse collection 存在
            self._ensure_sparse_collection(sparse_collection)

            payload = {
                "doc_id": doc_id,
                "text": text[:500],
            }
            if metadata:
                payload.update(metadata)

            point_id = self._doc_id_to_point_id(doc_id)

            client.upsert(
                collection_name=sparse_collection,
                points=[
                    PointStruct(
                        id=point_id,
                        vector={
                            "bm25": SparseVector(
                                indices=indices,
                                values=values,
                            ),
                        },
                        payload=payload,
                    ),
                ],
            )

            return True

        except Exception as e:
            logger.debug(f"VectorBridge sparse index failed: {e}")
            return False

    def build_sparse_idf(self, collection: str) -> int:
        """從既有 dense collection 的 payload 建立 IDF 表.

        掃描 dense collection 中所有文件的 text 欄位，
        用來建立 BM25 的 IDF 統計。

        Args:
            collection: collection 名稱

        Returns:
            詞彙表大小。
        """
        try:
            client = self._get_client()
            if client is None:
                return 0

            # 用 scroll 取出所有 payload.text
            corpus = []
            offset = None
            while True:
                result = client.scroll(
                    collection_name=collection,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = result
                for point in points:
                    text = point.payload.get("text", "")
                    if text:
                        corpus.append(text)
                if next_offset is None:
                    break
                offset = next_offset

            if not corpus:
                logger.info(f"No documents in {collection} for IDF building")
                return 0

            sparse_embedder = self._get_sparse_embedder()
            return sparse_embedder.build_idf(corpus)

        except Exception as e:
            logger.debug(f"VectorBridge build_sparse_idf failed: {e}")
            return 0

    def backfill_sparse(self, collection: str, batch_size: int = 50) -> int:
        """將既有 dense collection 的文件回填到 sparse collection.

        Args:
            collection: collection 名稱
            batch_size: 每批處理數量

        Returns:
            成功索引的數量。
        """
        sparse_embedder = self._get_sparse_embedder()
        if not sparse_embedder.is_available() or not sparse_embedder.has_idf():
            return 0

        try:
            client = self._get_client()
            if client is None:
                return 0

            sparse_collection = f"{collection}_sparse"
            self._ensure_sparse_collection(sparse_collection)

            from qdrant_client.models import PointStruct, SparseVector

            indexed = 0
            offset = None

            while True:
                result = client.scroll(
                    collection_name=collection,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, next_offset = result

                if not points:
                    break

                batch_points = []
                for point in points:
                    text = point.payload.get("text", "")
                    if not text:
                        continue

                    indices, values = sparse_embedder.encode(text)
                    if not indices:
                        continue

                    batch_points.append(
                        PointStruct(
                            id=point.id,
                            vector={
                                "bm25": SparseVector(
                                    indices=indices,
                                    values=values,
                                ),
                            },
                            payload=point.payload,
                        )
                    )

                if batch_points:
                    client.upsert(
                        collection_name=sparse_collection,
                        points=batch_points,
                    )
                    indexed += len(batch_points)

                if next_offset is None:
                    break
                offset = next_offset

            logger.info(
                f"Backfilled {indexed} points to {sparse_collection}"
            )
            return indexed

        except Exception as e:
            logger.debug(f"VectorBridge backfill_sparse failed: {e}")
            return 0

    def _ensure_sparse_collection(self, name: str) -> None:
        """確保 sparse collection 存在（使用 SparseVectorParams）."""
        try:
            client = self._get_client()
            if client is None:
                return

            client.get_collection(name)

        except Exception:
            # Collection 不存在，建立 sparse-only collection
            self._create_sparse_collection(name)

    def _create_sparse_collection(self, name: str) -> None:
        """建立 sparse-only collection."""
        try:
            client = self._get_client()
            if client is None:
                return

            from qdrant_client.models import SparseVectorParams

            client.create_collection(
                collection_name=name,
                vectors_config={},
                sparse_vectors_config={
                    "bm25": SparseVectorParams(),
                },
            )
            logger.info(f"Created sparse collection: {name}")

        except Exception as e:
            logger.warning(f"Failed to create sparse collection {name}: {e}")

    @staticmethod
    def _doc_id_to_point_id(doc_id: str) -> str:
        """將 doc_id 轉為 Qdrant 相容的 UUID point ID.

        Qdrant 支援 UUID 或 int 作為 point ID。
        使用 UUID5 從 doc_id 產生確定性 UUID（相同 doc_id → 相同 UUID）。
        """
        return str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))
