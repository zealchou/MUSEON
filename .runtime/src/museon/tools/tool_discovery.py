"""Tool Discovery — 每日凌晨自動發現新工具.

每天 5am 使用 SearXNG 搜尋最新免費自建 AI 工具，
DSE 風格分析後決定是否推薦安裝。

依賴：SearXNG（Layer 1 搜尋能力）已安裝且啟用。
"""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# 搜尋關鍵字模板
SEARCH_QUERIES = [
    "self-hosted AI tools 2026 open source",
    "free alternative to paid AI API self-host",
    "open source LLM tools docker self-hosted",
    "AI agent tools self-hosted free 2026",
    "open source vector database embedding",
    "self-hosted speech recognition OCR free",
]

# 已知工具（不重複推薦）
KNOWN_TOOLS = {
    "searxng", "ollama", "qdrant", "whisper", "whisper.cpp",
    "paddleocr", "kokoro", "firecrawl", "n8n", "dify",
    "chromadb", "supabase", "vllm", "piper",
}

# 安全黑名單
BLACKLISTED_TOOLS = {
    "openclaw",  # 824+ 惡意 skills
}

# 最低推薦門檻
MIN_GITHUB_STARS = 1000
MIN_SCORE = 6  # /10


class ToolDiscovery:
    """工具自動發現引擎.

    流程：
    1. SearXNG 搜尋新工具
    2. 過濾已知 / 黑名單
    3. DSE 風格評分
    4. 高分推薦，記錄到 discoveries.json
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)
        self._dir = self._workspace / "_system" / "tools"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._discoveries_path = self._dir / "discoveries.json"

    def discover(self, searxng_url: str = "http://127.0.0.1:8888") -> Dict:
        """執行一次發現掃描.

        Args:
            searxng_url: SearXNG 實例 URL

        Returns:
            {"searched": int, "found": int, "recommended": [...]}
        """
        all_results = []
        searched = 0

        for query in SEARCH_QUERIES:
            try:
                results = self._search(searxng_url, query)
                all_results.extend(results)
                searched += 1
            except Exception as e:
                logger.warning(f"Search failed for '{query}': {e}")

        # 去重 + 過濾
        candidates = self._filter_results(all_results)

        # 評分
        scored = []
        for c in candidates:
            score = self._score_candidate(c)
            if score >= MIN_SCORE:
                c["score"] = score
                scored.append(c)

        # 排序
        scored.sort(key=lambda x: x["score"], reverse=True)
        recommended = scored[:5]

        # 持久化
        discovery_record = {
            "timestamp": datetime.now(TZ_TAIPEI).isoformat(),
            "searched": searched,
            "found": len(candidates),
            "recommended": recommended,
        }
        self._save_discovery(discovery_record)

        return discovery_record

    def get_latest_discoveries(self) -> Dict:
        """取得最近一次發現結果."""
        if not self._discoveries_path.exists():
            return {
                "timestamp": "",
                "searched": 0,
                "found": 0,
                "recommended": [],
            }

        try:
            data = json.loads(
                self._discoveries_path.read_text(encoding="utf-8")
            )
            # 回傳最後一筆
            if isinstance(data, list) and data:
                return data[-1]
            return data
        except Exception:
            return {"timestamp": "", "searched": 0, "found": 0, "recommended": []}

    def get_all_discoveries(self) -> List[Dict]:
        """取得所有發現紀錄."""
        if not self._discoveries_path.exists():
            return []

        try:
            data = json.loads(
                self._discoveries_path.read_text(encoding="utf-8")
            )
            if isinstance(data, list):
                return data
            return [data]
        except Exception:
            return []

    # ── Internal ──

    def _search(self, searxng_url: str, query: str) -> List[Dict]:
        """透過 SearXNG 搜尋."""
        import urllib.request
        import urllib.parse

        params = urllib.parse.urlencode({
            "q": query,
            "format": "json",
            "engines": "duckduckgo,bing",
            "language": "en",
        })
        url = f"{searxng_url}/search?{params}"

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("results", [])[:10]
        except Exception as e:
            logger.warning(f"SearXNG search error: {e}")
            return []

    def _filter_results(self, results: List[Dict]) -> List[Dict]:
        """過濾搜尋結果."""
        seen_urls = set()
        candidates = []

        for r in results:
            url = r.get("url", "")
            title = r.get("title", "").lower()

            # 去重
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # 過濾已知工具
            skip = False
            for known in KNOWN_TOOLS:
                if known in title:
                    skip = True
                    break
            if skip:
                continue

            # 過濾黑名單
            for black in BLACKLISTED_TOOLS:
                if black in title:
                    skip = True
                    break
            if skip:
                continue

            # 只保留 GitHub 或技術相關
            if any(
                d in url for d in [
                    "github.com", "gitlab.com", "huggingface.co",
                    "producthunt.com", "alternativeto.net",
                ]
            ):
                candidates.append({
                    "title": r.get("title", ""),
                    "url": url,
                    "content": r.get("content", "")[:200],
                })

        return candidates[:20]

    def _score_candidate(self, candidate: Dict) -> int:
        """DSE 風格評分（0-10）.

        評分維度：
        1. GitHub 存在 (+2)
        2. 標題含 "self-hosted" / "open source" (+1)
        3. 標題含 "AI" / "LLM" / "agent" (+1)
        4. 標題含 "docker" (+1)
        5. 描述含 "free" / "no cost" (+1)
        6. 非付費平台 (+1)
        7. 2026 年內容 (+1)
        8. 有 ARM / Apple Silicon 支援提及 (+1)
        9. 無安全問題提及 (+1)
        """
        score = 0
        title = candidate.get("title", "").lower()
        url = candidate.get("url", "").lower()
        content = candidate.get("content", "").lower()
        combined = f"{title} {content}"

        # GitHub 存在
        if "github.com" in url:
            score += 2

        # 關鍵字
        if any(kw in combined for kw in ["self-hosted", "self-host", "open source"]):
            score += 1
        if any(kw in combined for kw in ["ai", "llm", "agent", "machine learning"]):
            score += 1
        if "docker" in combined:
            score += 1
        if any(kw in combined for kw in ["free", "no cost", "$0"]):
            score += 1

        # 非付費
        if not any(kw in combined for kw in ["pricing", "$", "subscribe", "paid"]):
            score += 1

        # 新鮮度
        if "2026" in combined:
            score += 1

        # ARM / Apple Silicon
        if any(kw in combined for kw in ["arm", "apple silicon", "m1", "m2", "m3", "m4"]):
            score += 1

        # 無安全問題
        if not any(kw in combined for kw in ["vulnerability", "cve", "exploit", "malicious"]):
            score += 1

        return min(score, 10)

    def _save_discovery(self, record: Dict) -> None:
        """持久化發現紀錄."""
        discoveries = self.get_all_discoveries()
        discoveries.append(record)
        # 最多保留 30 天
        if len(discoveries) > 30:
            discoveries = discoveries[-30:]

        self._discoveries_path.write_text(
            json.dumps(discoveries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
