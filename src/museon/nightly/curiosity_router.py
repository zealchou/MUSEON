"""CuriosityRouter — 好奇心路由器.

從 question_queue.json 選取最值得研究的問題，
透過 ResearchEngine 進行實際研究，結果結晶到 Knowledge Lattice。

讓好奇掃描（Nightly Step 13）收集的問題不再只是「存著」，
而是真正被研究、被學習、被結晶。
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.core.event_bus import CURIOSITY_RESEARCHED

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 每次最多研究幾個問題（控制成本）
MAX_QUESTIONS_PER_RUN = 2


class CuriosityRouter:
    """好奇心路由器 — 把問題變成探索行動."""

    def __init__(
        self,
        workspace: Path,
        research_engine: Any = None,
        event_bus: Any = None,
        pulse_db: Any = None,
    ) -> None:
        self._workspace = workspace
        self._research = research_engine
        self._event_bus = event_bus
        self._db = pulse_db

    async def process_queue(self, max_items: int = MAX_QUESTIONS_PER_RUN) -> List[Dict]:
        """處理好奇心佇列中的 pending 問題.

        Returns:
            研究結果列表
        """
        queue = self._load_queue()
        pending = [q for q in queue if q.get("status") == "pending"]

        if not pending:
            logger.info("CuriosityRouter: no pending questions")
            return []

        # 優先排序（純 CPU）
        prioritized = self._prioritize(pending)
        to_research = prioritized[:max_items]
        results = []

        for question_entry in to_research:
            question = question_entry.get("question", "")
            if not question:
                continue

            logger.info(f"CuriosityRouter: researching '{question[:50]}'")

            try:
                research_result = await self._do_research(question)

                # 更新佇列狀態
                question_entry["status"] = "researched"
                question_entry["researched_at"] = datetime.now(TZ8).isoformat()

                result_dict = {
                    "question": question,
                    "is_valuable": research_result.is_valuable if research_result else False,
                    "summary": research_result.filtered_summary if research_result else "",
                    "cost_usd": research_result.cost_usd if research_result else 0,
                    "status": "researched",
                }
                results.append(result_dict)

                # 發布事件
                if self._event_bus and research_result and research_result.is_valuable:
                    self._event_bus.publish(CURIOSITY_RESEARCHED, {
                        "question": question,
                        "summary": research_result.filtered_summary,
                        "is_valuable": True,
                    })

                # 記錄到 PulseDB
                if self._db and research_result:
                    try:
                        self._db.log_exploration(
                            topic=question,
                            motivation="curiosity_router",
                            query=question,
                            findings=research_result.filtered_summary or "無價值發現",
                            crystallized=research_result.is_valuable,
                            crystal_id="",
                            tokens_used=research_result.tokens_used,
                            cost_usd=research_result.cost_usd,
                        )
                    except Exception as e:
                        logger.warning(f"CuriosityRouter: PulseDB log failed: {e}")

            except Exception as e:
                logger.error(f"CuriosityRouter: research failed for '{question[:50]}': {e}")
                question_entry["status"] = "failed"
                results.append({
                    "question": question,
                    "is_valuable": False,
                    "status": "failed",
                    "error": str(e),
                })

        # 儲存更新後的佇列
        self._save_queue(queue)

        valuable_count = sum(1 for r in results if r.get("is_valuable"))
        logger.info(
            f"CuriosityRouter: {len(results)} researched, "
            f"{valuable_count} valuable"
        )

        return results

    async def _do_research(self, question: str) -> Optional[Any]:
        """透過 ResearchEngine 研究一個問題."""
        if not self._research:
            logger.warning("CuriosityRouter: no research_engine available")
            return None

        return await self._research.research(
            query=question,
            context_type="curiosity",
            max_rounds=2,  # 好奇心研究只做 2 輪（節省成本）
        )

    def _prioritize(self, questions: List[Dict]) -> List[Dict]:
        """純 CPU 優先排序.

        排序因素：
        1. source_date 越新越優先
        2. question 長度適中（太短太長都降級）
        3. 來自 exploration_bridge 的優先（有上下文）
        """
        def score(q: Dict) -> float:
            s = 0.0
            # 新鮮度
            try:
                source_date = q.get("source_date", "2020-01-01")
                days_old = (datetime.now(TZ8).date() - datetime.fromisoformat(source_date).date()).days
                s += max(0, 10 - days_old)
            except Exception as e:
                logger.debug(f"[CURIOSITY_ROUTER] operation failed (degraded): {e}")
            # 長度適中
            qlen = len(q.get("question", ""))
            if 10 < qlen < 100:
                s += 3
            elif qlen >= 100:
                s += 1
            # 來源加分
            if q.get("source") == "exploration_bridge":
                s += 5
            return s

        return sorted(questions, key=score, reverse=True)

    def _load_queue(self) -> List[Dict]:
        """讀取 question_queue.json."""
        queue_file = self._workspace / "_system" / "curiosity" / "question_queue.json"
        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
                # 相容兩種格式：{"questions": [...]} 或 [...]
                return raw.get("questions", []) if isinstance(raw, dict) else raw
        except Exception:
            return []

    def _save_queue(self, queue: List[Dict]) -> None:
        """儲存 question_queue.json."""
        curiosity_dir = self._workspace / "_system" / "curiosity"
        curiosity_dir.mkdir(parents=True, exist_ok=True)
        queue_file = curiosity_dir / "question_queue.json"
        try:
            with open(queue_file, "w", encoding="utf-8") as fh:
                json.dump(queue, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"CuriosityRouter: save queue failed: {e}")
