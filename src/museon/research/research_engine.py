"""ResearchEngine — 統一研究引擎.

為 SkillForgeScout、CuriosityRouter、ImmuneResearch 提供共享的
「上網研究學習」能力。複用 Explorer 的 SearXNG + Haiku 篩選管線。

五種研究情境：
  - context="skill"           → 技能改善最佳實踐搜尋
  - context="curiosity"        → 好奇心驅動知識研究
  - context="repair"           → 問題修復方案搜尋
  - context="outward_self"     → 外向自我進化（Track A）
  - context="outward_service"  → 外向服務進化（Track B）

成本控制：
  - 每次研究 ≤ $0.05（Haiku 篩選）
  - 深度分析另計 ≤ $0.10（Sonnet，僅高價值時）
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 模型配置（與 Explorer 一致）
FILTER_MODEL = "claude-haiku-4-5-20251001"

# 成本上限
MAX_COST_PER_RESEARCH = 0.05  # USD（不含深度分析）
MAX_ROUNDS_PER_RESEARCH = 3
DEDUP_TTL_SECONDS = 86400  # 24 小時去重 TTL


@dataclass
class SearchHit:
    """單筆搜尋結果."""

    title: str = ""
    content: str = ""
    url: str = ""
    relevance: float = 0.0


@dataclass
class ResearchResult:
    """研究結果."""

    query: str = ""
    context_type: str = ""  # "skill" | "curiosity" | "repair"
    hits: List[SearchHit] = field(default_factory=list)
    filtered_summary: str = ""
    is_valuable: bool = False
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    rounds_completed: int = 0
    status: str = "pending"  # "pending" | "done" | "failed" | "no_value"


# 情境專用篩選 prompt
_FILTER_PROMPTS = {
    "skill": """你是 MUSEON 技能改善研究助手。評估搜尋結果是否包含可用的最佳實踐。

搜尋主題：{query}

搜尋結果：
{hits}

請判斷：
1. 有沒有具體可借鏡的方法論或架構模式？
2. 有沒有已在實際系統中驗證過的做法？
3. 如果有價值，用 3-5 句話提煉核心做法。如果沒有，回覆「NO_VALUE」。""",

    "curiosity": """你是 MUSEON 的知識探索助手。評估搜尋結果的學習價值。

搜尋主題：{query}

搜尋結果：
{hits}

請判斷：
1. 這些結果中有沒有真正有價值的新知？
2. 如果有，用 3-5 句話提煉核心洞見。
3. 如果沒有，回覆「NO_VALUE」。""",

    "repair": """你是 MUSEON 的系統修復研究助手。評估搜尋結果是否包含可用的修復方案。

問題描述：{query}

搜尋結果：
{hits}

請判斷：
1. 有沒有針對類似問題的解決方案或 workaround？
2. 解決方案的可行性和風險如何？
3. 如果有價值，用 3-5 句話提煉修復方向。如果沒有，回覆「NO_VALUE」。""",

    "outward_self": """你是 MUSEON 的自我進化研究助手。評估搜尋結果是否包含可改善 AI Agent 架構或能力的前沿知識。

搜尋主題：{query}

搜尋結果：
{hits}

請判斷：
1. 有沒有前沿的 AI Agent 架構設計、prompt 技法或系統優化方法？
2. 這些做法是否已在實際系統中驗證過？
3. 如果有價值，用 3-5 句話提煉核心做法與適用條件。如果沒有，回覆「NO_VALUE」。""",

    "outward_service": """你是 MUSEON 的服務進化研究助手。評估搜尋結果是否包含可提升使用者服務品質的領域知識。

搜尋主題：{query}

搜尋結果：
{hits}

請判斷：
1. 有沒有該領域的最佳實踐、新框架或專家級方法論？
2. 這些知識對服務使用者有多大幫助？
3. 如果有價值，用 3-5 句話提煉核心知識與應用場景。如果沒有，回覆「NO_VALUE」。""",
}


class ResearchEngine:
    """統一研究引擎 — Scout、好奇心、免疫系統共用.

    複用 Explorer 的 SearXNG 搜尋管線，但加入情境感知的篩選。
    """

    def __init__(
        self,
        brain: Any = None,
        searxng_url: str = "http://127.0.0.1:8888",
        event_bus: Any = None,
    ) -> None:
        self._brain = brain
        self._searxng_url = searxng_url
        self._event_bus = event_bus
        # 去重表：{query_hash: timestamp}，TTL 24h
        self._dedup: Dict[str, float] = {}

    @staticmethod
    def _normalize_query(query: str) -> str:
        """正規化查詢字串（去空白、小寫、排序詞彙）."""
        words = sorted(query.lower().strip().split())
        return " ".join(words)

    def _query_hash(self, query: str, context_type: str) -> str:
        """產生查詢的唯一 hash."""
        normalized = self._normalize_query(query)
        key = f"{context_type}:{normalized}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def _is_duplicate(self, query: str, context_type: str) -> bool:
        """檢查查詢是否在 24h 內已研究過."""
        now = time.time()
        # 清理過期項
        self._dedup = {
            k: v for k, v in self._dedup.items()
            if now - v < DEDUP_TTL_SECONDS
        }
        qhash = self._query_hash(query, context_type)
        return qhash in self._dedup

    def _mark_researched(self, query: str, context_type: str) -> None:
        """標記查詢已研究."""
        qhash = self._query_hash(query, context_type)
        self._dedup[qhash] = time.time()

    async def research(
        self,
        query: str,
        context_type: str = "curiosity",
        max_rounds: int = MAX_ROUNDS_PER_RESEARCH,
        language: str = "zh-TW",
    ) -> ResearchResult:
        """執行一次研究.

        Args:
            query: 搜尋查詢
            context_type: 情境類型 ("skill" | "curiosity" | "repair")
            max_rounds: 最多搜尋輪數
            language: 搜尋語言

        Returns:
            ResearchResult 結構化研究結果
        """
        # 去重檢查：24h 內相同查詢不重複研究
        if self._is_duplicate(query, context_type):
            logger.debug(f"Research dedup hit: '{query}' ({context_type})")
            return ResearchResult(
                query=query,
                context_type=context_type,
                status="dedup",
            )

        start = time.monotonic()
        result = ResearchResult(query=query, context_type=context_type)

        try:
            all_hits: List[SearchHit] = []

            for round_idx in range(max_rounds):
                # 成本檢查
                if result.cost_usd >= MAX_COST_PER_RESEARCH:
                    break

                # 搜尋
                round_query = self._build_round_query(query, context_type, round_idx)
                round_lang = self._round_language(round_idx, language)
                hits = await self._search_round(round_query, round_lang)
                all_hits.extend(hits)
                result.rounds_completed = round_idx + 1

                if not hits:
                    continue

            if not all_hits:
                result.status = "no_value"
                result.duration_ms = int((time.monotonic() - start) * 1000)
                return result

            result.hits = all_hits

            # Haiku 篩選
            filter_result = await self._filter_hits(all_hits, query, context_type)
            result.tokens_used += filter_result.get("tokens", 0)
            result.cost_usd += filter_result.get("cost", 0)

            if filter_result.get("verdict") == "NO_VALUE":
                result.status = "no_value"
            else:
                result.filtered_summary = filter_result.get("summary", "")
                result.is_valuable = True
                result.status = "done"

        except Exception as e:
            logger.error(f"Research failed for '{query}': {e}")
            result.status = "failed"

        result.duration_ms = int((time.monotonic() - start) * 1000)

        # 標記已研究（成功或無價值都標記，避免重複嘗試）
        if result.status in ("done", "no_value"):
            self._mark_researched(query, context_type)

        # 發布 RESEARCH_COMPLETED 事件
        if self._event_bus and result.status != "dedup":
            try:
                from museon.core.event_bus import RESEARCH_COMPLETED
                self._event_bus.publish(RESEARCH_COMPLETED, {
                    "query": query,
                    "context_type": context_type,
                    "status": result.status,
                    "is_valuable": result.is_valuable,
                    "cost_usd": result.cost_usd,
                    "duration_ms": result.duration_ms,
                })
            except Exception:
                pass

        return result

    def _build_round_query(self, base_query: str, context_type: str, round_idx: int) -> str:
        """根據輪次和情境建構搜尋查詢."""
        if round_idx == 0:
            return base_query

        suffixes = {
            "skill": [
                "",
                "best practices implementation",
                "real world case study",
            ],
            "curiosity": [
                "",
                "research findings 2025 2026",
                "practical applications",
            ],
            "repair": [
                "",
                "solution fix workaround",
                "root cause analysis",
            ],
            "outward_self": [
                "",
                "SOTA architecture 2025 2026",
                "open source implementation benchmark",
            ],
            "outward_service": [
                "",
                "expert methodology framework 2026",
                "practical guide best practices",
            ],
        }
        suffix_list = suffixes.get(context_type, ["", "", ""])
        suffix = suffix_list[min(round_idx, len(suffix_list) - 1)]
        return f"{base_query} {suffix}".strip()

    def _round_language(self, round_idx: int, default_lang: str) -> str:
        """第一輪用預設語言，後續輪次用英文擴大搜尋範圍."""
        if round_idx == 0:
            return default_lang
        return "en"

    async def _search_round(self, query: str, language: str = "zh-TW") -> List[SearchHit]:
        """透過 SearXNG 執行一輪搜尋."""
        try:
            import aiohttp

            params = {
                "q": query,
                "format": "json",
                "language": language,
                "categories": "general",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._searxng_url}/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    results = data.get("results", [])[:5]
                    return [
                        SearchHit(
                            title=r.get("title", ""),
                            content=r.get("content", "")[:300],
                            url=r.get("url", ""),
                        )
                        for r in results
                    ]
        except Exception as e:
            logger.warning(f"SearXNG search failed for '{query}': {e}")
            return []

    async def _filter_hits(
        self, hits: List[SearchHit], query: str, context_type: str,
    ) -> Dict:
        """Haiku 篩選搜尋結果."""
        if not self._brain or not hasattr(self._brain, "_call_llm_with_model"):
            return {"verdict": "NO_VALUE", "tokens": 0, "cost": 0}

        hits_text = "\n".join(
            f"- {h.title}: {h.content} ({h.url})" for h in hits[:10]
        )

        template = _FILTER_PROMPTS.get(context_type, _FILTER_PROMPTS["curiosity"])
        prompt = template.format(query=query, hits=hits_text)

        try:
            response = await self._brain._call_llm_with_model(
                system_prompt="你是 MUSEON 的研究助手。請簡潔評估搜尋結果。",
                messages=[{"role": "user", "content": prompt}],
                model=FILTER_MODEL,
                max_tokens=400,
            )
            is_no_value = "NO_VALUE" in response
            tokens = 900
            cost = tokens * 0.25 / 1_000_000
            return {
                "verdict": "NO_VALUE" if is_no_value else "VALUABLE",
                "summary": response if not is_no_value else "",
                "tokens": tokens,
                "cost": cost,
            }
        except Exception as e:
            logger.error(f"Filter failed: {e}")
            return {"verdict": "NO_VALUE", "tokens": 0, "cost": 0}
