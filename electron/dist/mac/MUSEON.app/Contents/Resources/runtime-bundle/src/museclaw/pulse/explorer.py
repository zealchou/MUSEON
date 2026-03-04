"""Explorer — 自主探索引擎.

VITA 的好奇心驅動模組。
基於使命、好奇心、互動觀察，主動外出探索世界。
每次探索：SearXNG 搜尋 → Haiku 篩選 → 有價值則 Sonnet 深度分析 → 結晶。
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 探索預算
MAX_COST_PER_EXPLORATION = 0.50  # USD
MAX_EXPLORATIONS_PER_DAY = 3
MAX_DAILY_COST = 1.50  # USD

# 模型
SCOUT_MODEL = "claude-haiku-4-5-20251001"      # 初步篩選
DEEP_MODEL = "claude-sonnet-4-20250514"       # 深度分析（僅有價值時）

_SCOUT_SYSTEM = """你是 MUSEON 的探索偵察模組。你的任務是快速評估搜尋結果的價值。

給你一個搜尋主題和搜尋結果摘要，請判斷：
1. 這些結果中有沒有真正有價值的新知？
2. 如果有，用 3-5 句話提煉核心洞見。
3. 如果沒有，回覆「NO_VALUE」。

評判標準：
- 是否能幫助使用者（達達把拔）？
- 是否能讓霓裳學到新東西？
- 是否有足夠的深度值得進一步探索？
"""

_DEEP_SYSTEM = """你是 MUSEON 的深度探索模組。基於偵察報告，進行深度分析。

請產出結構化的探索報告：
1. **核心發現**：最重要的 1-3 個洞見
2. **與使用者的關聯**：這些發現如何幫助達達把拔？
3. **與霓裳成長的關聯**：這些發現如何幫助霓裳進化？
4. **結晶建議**：這個發現是否值得結晶？如果是，建議的結晶標題和摘要。
5. **下一步探索**：基於這次發現，下次應該探索什麼？

保持簡潔。總字數控制在 500 字以內。
"""


class Explorer:
    """自主探索引擎 — 霓裳的好奇心."""

    def __init__(
        self,
        brain: Any = None,
        data_dir: str = "",
        searxng_url: str = "http://127.0.0.1:8888",
    ) -> None:
        self._brain = brain
        self._data_dir = data_dir
        self._searxng_url = searxng_url

    async def explore(
        self,
        topic: str,
        motivation: str = "curiosity",
    ) -> Dict[str, Any]:
        """執行一次自主探索.

        Args:
            topic: 探索主題
            motivation: 動機 (curiosity/mission/skill/world/self)

        Returns:
            探索結果字典
        """
        start = time.monotonic()
        result = {
            "topic": topic,
            "motivation": motivation,
            "query": "",
            "findings": "",
            "crystallized": False,
            "crystal_id": "",
            "tokens_used": 0,
            "cost_usd": 0.0,
            "duration_ms": 0,
            "status": "exploring",
            "deep_analysis": False,
        }

        try:
            # Step 1: SearXNG 搜尋
            search_results = await self._search(topic)
            result["query"] = topic

            if not search_results:
                result["findings"] = "搜尋無結果"
                result["status"] = "done"
                result["duration_ms"] = int((time.monotonic() - start) * 1000)
                return result

            # Step 2: Haiku 快速篩選
            scout_report = await self._scout(topic, search_results)
            result["tokens_used"] += scout_report.get("tokens", 0)
            result["cost_usd"] += scout_report.get("cost", 0)

            if scout_report.get("verdict") == "NO_VALUE":
                result["findings"] = f"搜尋了「{topic}」但未發現有價值的新知"
                result["status"] = "done"
                result["duration_ms"] = int((time.monotonic() - start) * 1000)
                return result

            # Step 3: 有價值 → 考慮深度分析
            findings = scout_report.get("summary", "")
            result["findings"] = findings

            # 如果成本預算允許，進行 Sonnet 深度分析
            remaining_budget = MAX_COST_PER_EXPLORATION - result["cost_usd"]
            if remaining_budget > 0.10 and self._brain:
                deep_report = await self._deep_analyze(topic, findings, motivation)
                result["tokens_used"] += deep_report.get("tokens", 0)
                result["cost_usd"] += deep_report.get("cost", 0)
                result["findings"] = deep_report.get("analysis", findings)
                result["deep_analysis"] = True

                # 結晶建議
                if deep_report.get("should_crystallize"):
                    result["crystallized"] = True
                    # 實際結晶由 PulseEngine 負責

            result["status"] = "done"
        except Exception as e:
            logger.error(f"Exploration failed: {e}")
            result["findings"] = f"探索失敗: {e}"
            result["status"] = "failed"

        result["duration_ms"] = int((time.monotonic() - start) * 1000)
        return result

    async def _search(self, query: str) -> str:
        """透過 SearXNG 搜尋."""
        try:
            import aiohttp
            params = {
                "q": query,
                "format": "json",
                "language": "zh-TW",
                "categories": "general",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._searxng_url}/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return ""
                    data = await resp.json()
                    results = data.get("results", [])[:5]
                    summaries = []
                    for r in results:
                        title = r.get("title", "")
                        content = r.get("content", "")[:200]
                        url = r.get("url", "")
                        summaries.append(f"- {title}: {content} ({url})")
                    return "\n".join(summaries)
        except Exception as e:
            logger.warning(f"SearXNG search failed: {e}")
            return ""

    async def _scout(self, topic: str, search_results: str) -> Dict:
        """Haiku 快速篩選搜尋結果."""
        if not self._brain or not hasattr(self._brain, "_call_llm_with_model"):
            return {"verdict": "NO_VALUE", "tokens": 0, "cost": 0}

        prompt = f"搜尋主題：{topic}\n\n搜尋結果：\n{search_results}"
        try:
            response = await self._brain._call_llm_with_model(
                system_prompt=_SCOUT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                model=SCOUT_MODEL,
                max_tokens=300,
            )
            is_no_value = "NO_VALUE" in response
            # Haiku 成本估算：~500 input + 300 output tokens
            tokens = 800
            cost = tokens * 0.25 / 1_000_000  # Haiku pricing ~$0.25/MTok input
            return {
                "verdict": "NO_VALUE" if is_no_value else "VALUABLE",
                "summary": response if not is_no_value else "",
                "tokens": tokens,
                "cost": cost,
            }
        except Exception as e:
            logger.error(f"Scout failed: {e}")
            return {"verdict": "NO_VALUE", "tokens": 0, "cost": 0}

    async def _deep_analyze(
        self, topic: str, scout_summary: str, motivation: str,
    ) -> Dict:
        """Sonnet 深度分析."""
        if not self._brain or not hasattr(self._brain, "_call_llm_with_model"):
            return {"analysis": scout_summary, "tokens": 0, "cost": 0, "should_crystallize": False}

        prompt = (
            f"探索主題：{topic}\n"
            f"動機：{motivation}\n"
            f"偵察報告：{scout_summary}\n\n"
            f"請進行深度分析。"
        )
        try:
            response = await self._brain._call_llm_with_model(
                system_prompt=_DEEP_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                model=DEEP_MODEL,
                max_tokens=800,
            )
            # Sonnet 成本估算：~1000 input + 800 output tokens
            tokens = 1800
            cost = tokens * 3.0 / 1_000_000  # Sonnet pricing ~$3/MTok input
            should_crystallize = "值得結晶" in response or "建議結晶" in response
            return {
                "analysis": response,
                "tokens": tokens,
                "cost": cost,
                "should_crystallize": should_crystallize,
            }
        except Exception as e:
            logger.error(f"Deep analysis failed: {e}")
            return {"analysis": scout_summary, "tokens": 0, "cost": 0, "should_crystallize": False}
