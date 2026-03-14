"""Zotero Bridge — Zotero API 客戶端 + Qdrant 匯入.

透過 Zotero Web API 同步文獻，並將文獻向量化後匯入 Qdrant
的 "references" collection，實現語意搜尋。

設計原則：
- 所有外部 API 呼叫 try/except 包裹，失敗不影響系統運行
- 同步狀態持久化到 _system/zotero_sync.json
- 透過 EventBus 發布 ZOTERO_ITEM_IMPORTED 事件
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

ZOTERO_API_BASE = "https://api.zotero.org"
QDRANT_DEFAULT_URL = "http://localhost:6333"
QDRANT_COLLECTION = "references"
EMBEDDING_DIM = 1024  # Claude embedding dimension

# Zotero item types we care about
SUPPORTED_ITEM_TYPES = {
    "journalArticle", "book", "bookSection", "conferencePaper",
    "report", "thesis", "webpage", "preprint", "manuscript",
}


class ZoteroBridge:
    """Zotero API 客戶端 + Qdrant 文獻向量匯入."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        library_id: Optional[str] = None,
        library_type: str = "user",
        event_bus: Any = None,
        workspace: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.getenv("ZOTERO_API_KEY", "")
        self._library_id = library_id or os.getenv("ZOTERO_LIBRARY_ID", "")
        self._library_type = library_type
        self._base_url = f"{ZOTERO_API_BASE}/{library_type}s/{self._library_id}"
        self._event_bus = event_bus
        self._qdrant_url = os.getenv("QDRANT_URL", QDRANT_DEFAULT_URL)

        ws = workspace or os.getenv("MUSEON_WORKSPACE", str(Path.home() / "MUSEON"))
        self._workspace = Path(ws)
        self._sync_state_path = self._workspace / "_system" / "zotero_sync.json"
        self._sync_state_path.parent.mkdir(parents=True, exist_ok=True)

        self._sync_state = self._load_sync_state()

    # ── Sync State Persistence ──────────────────────────

    def _load_sync_state(self) -> Dict:
        """載入同步狀態."""
        if self._sync_state_path.exists():
            try:
                return json.loads(self._sync_state_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load zotero sync state: {e}")
        return {"last_version": 0, "item_count": 0, "last_sync": None}

    def _save_sync_state(self) -> None:
        """持久化同步狀態."""
        try:
            self._sync_state_path.write_text(
                json.dumps(self._sync_state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save zotero sync state: {e}")

    # ── Zotero API ──────────────────────────────────────

    async def sync_items(
        self, since_version: Optional[int] = None, limit: int = 50
    ) -> Dict:
        """GET /items — 取得新增/更新的 Zotero 項目.

        Args:
            since_version: 從此版本之後的變更。預設使用上次同步版本。
            limit: 每次最多取得幾筆。

        Returns:
            Dict with keys: items (list), version (int), count (int)
        """
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp not installed — cannot sync Zotero items")
            return {"items": [], "version": 0, "count": 0, "error": "aiohttp_missing"}

        version = since_version if since_version is not None else self._sync_state.get("last_version", 0)
        headers = {"Zotero-API-Key": self._api_key}
        params: Dict[str, Any] = {
            "format": "json",
            "limit": limit,
            "sort": "dateModified",
            "direction": "desc",
        }
        if version > 0:
            params["since"] = version

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url}/items",
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Zotero API error: HTTP {resp.status}")
                        return {"items": [], "version": version, "count": 0, "error": f"http_{resp.status}"}

                    items_raw = await resp.json()
                    new_version = int(resp.headers.get("Last-Modified-Version", version))
        except Exception as e:
            logger.error(f"Zotero sync failed: {e}")
            return {"items": [], "version": version, "count": 0, "error": str(e)}

        # 過濾支援的類型
        items = [
            item for item in items_raw
            if item.get("data", {}).get("itemType") in SUPPORTED_ITEM_TYPES
        ]

        # 更新同步狀態
        self._sync_state["last_version"] = new_version
        self._sync_state["item_count"] = self._sync_state.get("item_count", 0) + len(items)
        self._sync_state["last_sync"] = datetime.now(TZ8).isoformat()
        self._save_sync_state()

        logger.info(f"Zotero sync: {len(items)} items fetched (version {new_version})")
        return {"items": items, "version": new_version, "count": len(items)}

    # ── Qdrant Import ───────────────────────────────────

    async def import_to_qdrant(self, items: List[Dict]) -> Dict:
        """將 Zotero 項目轉換為向量並 upsert 到 Qdrant "references" collection.

        Args:
            items: Zotero API 回傳的項目列表

        Returns:
            Dict with keys: imported (int), skipped (int), errors (int)
        """
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp not installed — cannot import to Qdrant")
            return {"imported": 0, "skipped": 0, "errors": 1, "error": "aiohttp_missing"}

        imported = 0
        skipped = 0
        errors = 0

        try:
            async with aiohttp.ClientSession() as session:
                # 確保 collection 存在
                await self._ensure_qdrant_collection(session)

                for item in items:
                    try:
                        data = item.get("data", {})
                        point = self._item_to_qdrant_point(data)
                        if point is None:
                            skipped += 1
                            continue

                        payload = {"points": [point]}
                        async with session.put(
                            f"{self._qdrant_url}/collections/{QDRANT_COLLECTION}/points",
                            json=payload,
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as resp:
                            if resp.status in (200, 201):
                                imported += 1
                                self._publish_imported_event(data)
                            else:
                                errors += 1
                                logger.warning(f"Qdrant upsert failed for {data.get('key', '?')}: HTTP {resp.status}")
                    except Exception as e:
                        errors += 1
                        logger.warning(f"Qdrant upsert error: {e}")
        except Exception as e:
            logger.error(f"Qdrant session error: {e}")
            errors += 1

        logger.info(f"Qdrant import: {imported} imported, {skipped} skipped, {errors} errors")
        return {"imported": imported, "skipped": skipped, "errors": errors}

    async def _ensure_qdrant_collection(self, session: Any) -> None:
        """確保 Qdrant collection 存在，不存在則建立."""
        try:
            async with session.get(
                f"{self._qdrant_url}/collections/{QDRANT_COLLECTION}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return
        except Exception as e:
            logger.debug(f"[ZOTERO_BRIDGE] file stat failed (degraded): {e}")

        # 建立 collection
        try:
            create_payload = {
                "vectors": {"size": EMBEDDING_DIM, "distance": "Cosine"},
            }
            async with session.put(
                f"{self._qdrant_url}/collections/{QDRANT_COLLECTION}",
                json=create_payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 201):
                    logger.info(f"Created Qdrant collection: {QDRANT_COLLECTION}")
                else:
                    logger.warning(f"Failed to create Qdrant collection: HTTP {resp.status}")
        except Exception as e:
            logger.error(f"Qdrant collection creation failed: {e}")

    def _item_to_qdrant_point(self, data: Dict) -> Optional[Dict]:
        """將 Zotero 項目轉為 Qdrant point 格式."""
        title = data.get("title", "")
        abstract = data.get("abstractNote", "")
        if not title:
            return None

        # 生成確定性 ID（基於 Zotero key）
        zotero_key = data.get("key", "")
        point_id = int(hashlib.md5(zotero_key.encode()).hexdigest()[:8], 16)

        # 文本拼接用於 embedding（placeholder — 需接入真實 embedding API）
        text = f"{title}. {abstract}"
        vector = self._placeholder_embedding(text)

        payload = {
            "zotero_key": zotero_key,
            "title": title,
            "abstract": abstract[:500],
            "item_type": data.get("itemType", ""),
            "creators": [
                c.get("lastName", "") + ", " + c.get("firstName", "")
                for c in data.get("creators", [])[:5]
            ],
            "date": data.get("date", ""),
            "tags": [t.get("tag", "") for t in data.get("tags", [])],
            "url": data.get("url", ""),
            "doi": data.get("DOI", ""),
            "imported_at": datetime.now(TZ8).isoformat(),
        }

        return {"id": point_id, "vector": vector, "payload": payload}

    @staticmethod
    def _placeholder_embedding(text: str) -> List[float]:
        """Placeholder embedding — 用 hash 產生偽向量。正式環境應接 Claude embedding API."""
        import struct
        digest = hashlib.sha512(text.encode()).digest()
        # 從 SHA512 擴展到 EMBEDDING_DIM 維
        values: List[float] = []
        for i in range(EMBEDDING_DIM):
            byte_idx = i % len(digest)
            values.append((digest[byte_idx] - 128) / 128.0)
        # L2 normalize
        norm = sum(v * v for v in values) ** 0.5
        if norm > 0:
            values = [v / norm for v in values]
        return values

    # ── Qdrant Search ───────────────────────────────────

    async def search_references(self, query: str, limit: int = 10) -> List[Dict]:
        """搜尋 Qdrant 中的相似文獻.

        Args:
            query: 搜尋查詢文字
            limit: 最多回傳幾筆

        Returns:
            List of matching reference dicts with score
        """
        try:
            import aiohttp
        except ImportError:
            return []

        vector = self._placeholder_embedding(query)
        search_payload = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._qdrant_url}/collections/{QDRANT_COLLECTION}/points/search",
                    json=search_payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Qdrant search failed: HTTP {resp.status}")
                        return []
                    result = await resp.json()
                    hits = result.get("result", [])
                    return [
                        {**hit.get("payload", {}), "score": hit.get("score", 0.0)}
                        for hit in hits
                    ]
        except Exception as e:
            logger.error(f"Qdrant search error: {e}")
            return []

    # ── Status ──────────────────────────────────────────

    def get_sync_status(self) -> Dict:
        """回傳同步狀態摘要."""
        return {
            "last_version": self._sync_state.get("last_version", 0),
            "item_count": self._sync_state.get("item_count", 0),
            "last_sync": self._sync_state.get("last_sync"),
            "configured": bool(self._api_key and self._library_id),
        }

    # ── Event Publishing ────────────────────────────────

    def _publish_imported_event(self, data: Dict) -> None:
        """發布 ZOTERO_ITEM_IMPORTED 事件."""
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import ZOTERO_ITEM_IMPORTED
                self._event_bus.publish(ZOTERO_ITEM_IMPORTED, {
                    "key": data.get("key", ""),
                    "title": data.get("title", ""),
                    "item_type": data.get("itemType", ""),
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
        except Exception as e:
            logger.warning(f"Failed to publish ZOTERO_ITEM_IMPORTED: {e}")
