"""RSS Aggregator — FreshRSS API 客戶端.

透過 FreshRSS Google Reader API 整合 RSS 資訊流：
- 輪詢未讀條目
- 利用 Haiku 過濾相關內容（如有 brain）
- 標記已讀
- 透過 EventBus 發布 RSS_NEW_ITEMS 事件

設計原則：
- 所有外部 API 呼叫以 try/except 包裹
- 使用 aiohttp 非同步 HTTP
- 所有 event_bus 操作以 try/except 保護
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 輪詢間隔（秒）
POLL_INTERVAL = 3600

# FreshRSS Google Reader API endpoints
_STREAM_CONTENTS = "/api/greader.php/reader/api/0/stream/contents/reading-list"
_EDIT_TAG = "/api/greader.php/reader/api/0/edit-tag"


class RSSAggregator:
    """FreshRSS RSS 聚合器.

    透過 FreshRSS 的 Google Reader 相容 API 輪詢新文章，
    可選用 Haiku 過濾相關內容，並透過 EventBus 通知下游。
    """

    def __init__(
        self,
        freshrss_url: str = "http://127.0.0.1:8080",
        api_key: Optional[str] = None,
        event_bus: Any = None,
        brain: Any = None,
    ) -> None:
        """
        Args:
            freshrss_url: FreshRSS 實例 URL
            api_key: FreshRSS API Key（Google Reader 認證）
            event_bus: EventBus 實例（可選）
            brain: Brain 實例，用於 Haiku 過濾（可選）
        """
        self._base_url = freshrss_url.rstrip("/")
        self._api_key = api_key or ""
        self._event_bus = event_bus
        self._brain = brain
        self._last_poll: Optional[datetime] = None
        self._poll_count: int = 0

    # ── Public API ──

    async def poll_new_items(self, max_items: int = 20) -> List[Dict]:
        """輪詢 FreshRSS 取得未讀條目.

        Args:
            max_items: 最大取回條目數

        Returns:
            過濾後的新條目列表
        """
        raw_items = await self._fetch_unread(max_items)
        if not raw_items:
            logger.debug("RSS poll: no new items")
            return []

        # 如有 brain，透過 Haiku 過濾
        relevant = await self._filter_relevant(raw_items)

        self._last_poll = datetime.now(TZ8)
        self._poll_count += 1

        # 發布事件
        if relevant:
            try:
                if self._event_bus is not None:
                    from museon.core.event_bus import RSS_NEW_ITEMS
                    self._event_bus.publish(RSS_NEW_ITEMS, {
                        "items": relevant,
                        "count": len(relevant),
                        "timestamp": self._last_poll.isoformat(),
                    })
            except Exception as e:
                logger.error(f"EventBus publish RSS_NEW_ITEMS failed: {e}")

            # 標記已讀
            item_ids = [item.get("id", "") for item in relevant if item.get("id")]
            if item_ids:
                self._mark_read(item_ids)

        logger.info(
            f"RSS poll #{self._poll_count}: {len(raw_items)} fetched, "
            f"{len(relevant)} relevant"
        )
        return relevant

    async def _filter_relevant(self, items: List[Dict]) -> List[Dict]:
        """利用 Haiku 過濾相關條目.

        如 brain 不可用，直接回傳所有條目。

        Args:
            items: 原始 RSS 條目

        Returns:
            過濾後的相關條目
        """
        if self._brain is None:
            return items

        relevant: List[Dict] = []
        for item in items:
            title = item.get("title", "")
            summary = item.get("summary", "")[:500]
            try:
                prompt = (
                    f"判斷這篇文章是否與 AI、軟體開發、創業、生產力工具相關。\n"
                    f"標題：{title}\n摘要：{summary}\n"
                    f"回答 YES 或 NO，不要解釋。"
                )
                # 使用 brain 的 lightweight 路徑（Haiku）
                if hasattr(self._brain, "quick_judge"):
                    result = await self._brain.quick_judge(prompt)
                else:
                    result = "YES"  # fallback: 沒有 quick_judge 就全部通過

                if "YES" in str(result).upper():
                    relevant.append(item)
            except Exception as e:
                logger.warning(f"Haiku filter error for '{title}': {e}")
                relevant.append(item)  # 過濾失敗時保留

        return relevant

    def _mark_read(self, item_ids: List[str]) -> None:
        """標記條目為已讀（同步，背景執行）.

        Args:
            item_ids: FreshRSS 條目 ID 列表
        """
        import asyncio

        async def _do_mark():
            try:
                import aiohttp
                url = f"{self._base_url}{_EDIT_TAG}"
                headers = self._build_headers()
                for item_id in item_ids:
                    payload = {
                        "i": item_id,
                        "a": "user/-/state/com.google/read",
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            url, data=payload, headers=headers,
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as resp:
                            if resp.status != 200:
                                logger.warning(
                                    f"Mark read failed for {item_id}: "
                                    f"HTTP {resp.status}"
                                )
            except Exception as e:
                logger.error(f"Mark read error: {e}")

        try:
            # 合約 3：用 get_running_loop() 取代 deprecated get_event_loop()
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_do_mark())
            except RuntimeError:
                # 不在 async context 中 → 建立獨立 loop
                asyncio.run(_do_mark())
        except Exception as e:
            logger.error(f"Mark read scheduling error: {e}")

    # ── Internal Helpers ──

    def _build_headers(self) -> Dict[str, str]:
        """建構 API 請求標頭."""
        headers: Dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if self._api_key:
            headers["Authorization"] = f"GoogleLogin auth={self._api_key}"
        return headers

    async def _fetch_unread(self, max_items: int) -> List[Dict]:
        """呼叫 FreshRSS API 取得未讀條目.

        Args:
            max_items: 最大取回數量

        Returns:
            解析後的條目列表
        """
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp is required for RSS aggregator")
            return []

        url = f"{self._base_url}{_STREAM_CONTENTS}"
        params = {
            "n": str(max_items),
            "xt": "user/-/state/com.google/read",  # 排除已讀
        }
        headers = self._build_headers()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"FreshRSS API error: HTTP {resp.status}")
                        return []

                    data = await resp.json(content_type=None)
                    raw_items = data.get("items", [])

                    return [self._parse_item(item) for item in raw_items]

        except Exception as e:
            logger.error(f"FreshRSS fetch error: {e}")
            return []

    @staticmethod
    def _parse_item(raw: Dict) -> Dict:
        """解析 Google Reader API 條目格式.

        Args:
            raw: 原始 API 回應條目

        Returns:
            標準化的條目字典
        """
        summary_obj = raw.get("summary", {})
        summary_content = (
            summary_obj.get("content", "") if isinstance(summary_obj, dict)
            else str(summary_obj)
        )

        canonical = raw.get("canonical", [{}])
        link = canonical[0].get("href", "") if canonical else ""
        if not link:
            alternate = raw.get("alternate", [{}])
            link = alternate[0].get("href", "") if alternate else ""

        published = raw.get("published", 0)
        try:
            pub_dt = datetime.fromtimestamp(published, tz=TZ8)
        except (OSError, ValueError):
            pub_dt = datetime.now(TZ8)

        return {
            "id": raw.get("id", ""),
            "title": raw.get("title", ""),
            "summary": summary_content[:1000],
            "link": link,
            "published": pub_dt.isoformat(),
            "origin": raw.get("origin", {}).get("title", ""),
            "categories": [
                c.get("label", "") for c in raw.get("categories", [])
                if isinstance(c, dict)
            ],
        }

    # ── Status ──

    def get_status(self) -> Dict[str, Any]:
        """取得聚合器狀態."""
        return {
            "base_url": self._base_url,
            "configured": bool(self._api_key),
            "last_poll": self._last_poll.isoformat() if self._last_poll else None,
            "poll_count": self._poll_count,
            "has_brain": self._brain is not None,
            "has_event_bus": self._event_bus is not None,
        }
