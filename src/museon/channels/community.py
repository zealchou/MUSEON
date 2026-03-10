"""Community Adapter — 社群平台互動（Reddit / HackerNews / Medium）.

掃描多個公開社群平台，尋找與 MUSEON 相關的討論與提及，
並透過 EventBus 發布 CHANNEL_MESSAGE_RECEIVED 事件。

設計原則：
- 僅使用公開 API（Reddit JSON、HN Algolia、Medium RSS），不需認證
- 關鍵字相關性過濾，減少噪音
- 所有外部呼叫 try/except 包裹，單平台失敗不影響其他
- 掃描歷史持久化到 _system/community_scans.json
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

REDDIT_JSON_BASE = "https://www.reddit.com"
HN_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"
MEDIUM_RSS_BASE = "https://medium.com/feed/tag"

MAX_SCAN_HISTORY = 100
DEFAULT_USER_AGENT = "MUSEON-CommunityScanner/1.0"
REQUEST_TIMEOUT = 15


class CommunityAdapter:
    """社群平台互動 adapter — 掃描 Reddit / HackerNews / Medium."""

    def __init__(
        self,
        config: Optional[Dict] = None,
        event_bus: Any = None,
    ) -> None:
        config = config or {}
        self._event_bus = event_bus
        self._platforms: List[str] = config.get("platforms", ["reddit", "hackernews", "medium"])

        ws = config.get("workspace") or os.getenv("MUSEON_WORKSPACE", str(Path.home() / "MUSEON"))
        self._workspace = Path(ws)
        self._history_path = self._workspace / "_system" / "community_scans.json"
        self._history_path.parent.mkdir(parents=True, exist_ok=True)

        # Reddit 設定
        self._reddit_subreddits: List[str] = config.get("reddit_subreddits", [
            "artificial", "MachineLearning", "LocalLLaMA", "selfhosted",
        ])

        # 掃描歷史
        self._scan_history: List[Dict] = self._load_scan_history()

    # ── Persistence ─────────────────────────────────────

    def _load_scan_history(self) -> List[Dict]:
        """載入掃描歷史."""
        if self._history_path.exists():
            try:
                data = json.loads(self._history_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data[-MAX_SCAN_HISTORY:]
            except Exception as e:
                logger.warning(f"Failed to load scan history: {e}")
        return []

    def _save_scan_history(self) -> None:
        """持久化掃描歷史."""
        try:
            self._history_path.write_text(
                json.dumps(self._scan_history[-MAX_SCAN_HISTORY:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save scan history: {e}")

    # ── Public API ──────────────────────────────────────

    async def scan_mentions(
        self, keywords: List[str], limit: int = 20
    ) -> List[Dict]:
        """掃描所有啟用平台，尋找相關提及.

        Args:
            keywords: 關鍵字列表
            limit: 每個平台的最大結果數

        Returns:
            List of mention dicts: {platform, title, url, score, timestamp, ...}
        """
        all_items: List[Dict] = []

        platform_scanners = {
            "reddit": self._scan_reddit,
            "hackernews": self._scan_hackernews,
            "medium": self._scan_medium,
        }

        for platform in self._platforms:
            scanner = platform_scanners.get(platform)
            if scanner is None:
                logger.warning(f"Unknown platform: {platform}")
                continue
            try:
                items = await scanner(keywords, limit)
                all_items.extend(items)
            except Exception as e:
                logger.warning(f"Platform {platform} scan failed: {e}")

        # 過濾相關性
        filtered = self._filter_relevant(all_items, min_score=0.3)

        # 按分數排序
        filtered.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        result = filtered[:limit]

        # 記錄掃描歷史
        scan_record = {
            "timestamp": datetime.now(TZ8).isoformat(),
            "keywords": keywords,
            "platforms": self._platforms,
            "total_found": len(all_items),
            "relevant_count": len(result),
        }
        self._scan_history.append(scan_record)
        self._save_scan_history()

        # 發布事件（每個相關提及）
        for item in result:
            self._publish_mention_event(item)

        logger.info(f"Community scan: {len(result)} relevant items from {len(all_items)} total")
        return result

    def get_scan_history(self) -> List[Dict]:
        """回傳最近的掃描紀錄."""
        return list(self._scan_history)

    # ── Reddit Scanner ──────────────────────────────────

    async def _scan_reddit(self, keywords: List[str], limit: int) -> List[Dict]:
        """掃描 Reddit — 使用公開 JSON API（不需認證）.

        Args:
            keywords: 搜尋關鍵字
            limit: 最大結果數

        Returns:
            List of Reddit post dicts
        """
        try:
            import aiohttp
        except ImportError:
            logger.debug("aiohttp not installed — skipping Reddit scan")
            return []

        items: List[Dict] = []
        query = " ".join(keywords)
        headers = {"User-Agent": DEFAULT_USER_AGENT}

        for subreddit in self._reddit_subreddits:
            try:
                url = f"{REDDIT_JSON_BASE}/r/{subreddit}/search.json"
                params = {
                    "q": query,
                    "sort": "new",
                    "limit": min(limit, 25),
                    "restrict_sr": "on",
                    "t": "week",
                }
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    ) as resp:
                        if resp.status != 200:
                            logger.debug(f"Reddit r/{subreddit} returned HTTP {resp.status}")
                            continue
                        data = await resp.json()
                        posts = data.get("data", {}).get("children", [])
                        for post in posts:
                            pd = post.get("data", {})
                            items.append({
                                "platform": "reddit",
                                "subreddit": subreddit,
                                "title": pd.get("title", ""),
                                "url": f"https://reddit.com{pd.get('permalink', '')}",
                                "author": pd.get("author", ""),
                                "score": pd.get("score", 0),
                                "num_comments": pd.get("num_comments", 0),
                                "selftext": (pd.get("selftext", "") or "")[:300],
                                "created_utc": pd.get("created_utc", 0),
                                "timestamp": datetime.fromtimestamp(
                                    pd.get("created_utc", 0), tz=TZ8
                                ).isoformat() if pd.get("created_utc") else "",
                            })
            except Exception as e:
                logger.debug(f"Reddit r/{subreddit} scan error: {e}")

        return items[:limit]

    # ── HackerNews Scanner ──────────────────────────────

    async def _scan_hackernews(self, keywords: List[str], limit: int) -> List[Dict]:
        """掃描 HackerNews — 使用 Algolia Search API.

        Args:
            keywords: 搜尋關鍵字
            limit: 最大結果數

        Returns:
            List of HN story dicts
        """
        try:
            import aiohttp
        except ImportError:
            logger.debug("aiohttp not installed — skipping HackerNews scan")
            return []

        items: List[Dict] = []
        query = " ".join(keywords)

        try:
            url = f"{HN_ALGOLIA_BASE}/search_by_date"
            params = {
                "query": query,
                "tags": "story",
                "hitsPerPage": min(limit, 50),
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status != 200:
                        logger.debug(f"HN Algolia returned HTTP {resp.status}")
                        return []
                    data = await resp.json()
                    hits = data.get("hits", [])
                    for hit in hits:
                        items.append({
                            "platform": "hackernews",
                            "title": hit.get("title", ""),
                            "url": hit.get("url", "") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                            "hn_url": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                            "author": hit.get("author", ""),
                            "score": hit.get("points", 0) or 0,
                            "num_comments": hit.get("num_comments", 0) or 0,
                            "created_at": hit.get("created_at", ""),
                            "timestamp": hit.get("created_at", ""),
                        })
        except Exception as e:
            logger.debug(f"HackerNews scan error: {e}")

        return items[:limit]

    # ── Medium Scanner ──────────────────────────────────

    async def _scan_medium(self, keywords: List[str], limit: int) -> List[Dict]:
        """掃描 Medium — 使用 RSS Feed（Tag-based）.

        Args:
            keywords: 作為 tag 掃描的關鍵字
            limit: 最大結果數

        Returns:
            List of Medium article dicts
        """
        try:
            import aiohttp
        except ImportError:
            logger.debug("aiohttp not installed — skipping Medium scan")
            return []

        items: List[Dict] = []
        headers = {"User-Agent": DEFAULT_USER_AGENT}

        for keyword in keywords[:3]:  # 最多搜尋 3 個 tag
            tag = keyword.lower().replace(" ", "-")
            try:
                url = f"{MEDIUM_RSS_BASE}/{tag}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    ) as resp:
                        if resp.status != 200:
                            logger.debug(f"Medium tag '{tag}' returned HTTP {resp.status}")
                            continue
                        text = await resp.text()
                        # 簡易 RSS XML 解析（避免依賴 feedparser）
                        parsed = self._parse_rss_simple(text, tag)
                        items.extend(parsed)
            except Exception as e:
                logger.debug(f"Medium tag '{tag}' scan error: {e}")

        return items[:limit]

    @staticmethod
    def _parse_rss_simple(xml_text: str, tag: str) -> List[Dict]:
        """簡易 RSS XML 解析（不依賴 feedparser）."""
        items: List[Dict] = []
        # 簡易 regex 抽取 <item>...</item>
        item_blocks = re.findall(r"<item>(.*?)</item>", xml_text, re.DOTALL)
        for block in item_blocks[:10]:
            title = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", block)
            if not title:
                title = re.search(r"<title>(.*?)</title>", block)
            link = re.search(r"<link>(.*?)</link>", block)
            pub_date = re.search(r"<pubDate>(.*?)</pubDate>", block)
            creator = re.search(r"<dc:creator><!\[CDATA\[(.*?)\]\]></dc:creator>", block)

            items.append({
                "platform": "medium",
                "title": title.group(1) if title else "",
                "url": link.group(1) if link else "",
                "author": creator.group(1) if creator else "",
                "score": 0,
                "num_comments": 0,
                "tag": tag,
                "timestamp": pub_date.group(1) if pub_date else "",
            })
        return items

    # ── Relevance Filtering ─────────────────────────────

    def _filter_relevant(
        self, items: List[Dict], min_score: float = 0.5
    ) -> List[Dict]:
        """關鍵字相關性過濾.

        Args:
            items: 原始項目列表
            min_score: 最低相關性分數 (0.0~1.0)

        Returns:
            過濾後的項目列表（附 relevance_score）
        """
        filtered: List[Dict] = []
        for item in items:
            score = self._compute_relevance(item)
            if score >= min_score:
                item["relevance_score"] = round(score, 3)
                filtered.append(item)
        return filtered

    @staticmethod
    def _compute_relevance(item: Dict) -> float:
        """計算單一項目的相關性分數."""
        score = 0.3  # 基本分（既然搜尋到了就有一定相關性）

        # 標題長度（過短通常是垃圾）
        title = item.get("title", "")
        if len(title) < 10:
            score -= 0.2
        elif len(title) > 20:
            score += 0.1

        # 平台互動分數
        platform_score = item.get("score", 0)
        if platform_score > 100:
            score += 0.3
        elif platform_score > 10:
            score += 0.2
        elif platform_score > 0:
            score += 0.1

        # 評論數
        num_comments = item.get("num_comments", 0)
        if num_comments > 50:
            score += 0.2
        elif num_comments > 10:
            score += 0.1

        return min(1.0, max(0.0, score))

    # ── Event Publishing ────────────────────────────────

    def _publish_mention_event(self, item: Dict) -> None:
        """發布 CHANNEL_MESSAGE_RECEIVED 事件."""
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import CHANNEL_MESSAGE_RECEIVED
                self._event_bus.publish(CHANNEL_MESSAGE_RECEIVED, {
                    "channel": f"community:{item.get('platform', 'unknown')}",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "relevance_score": item.get("relevance_score", 0),
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
        except Exception as e:
            logger.warning(f"Failed to publish community mention event: {e}")
