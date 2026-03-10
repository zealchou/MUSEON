"""ImmuneResearch — 免疫系統研究引擎.

偵測到問題後，在嘗試修復之前，先上網研究類似問題的解法。
與 SkillForgeScout 共享 ResearchEngine（統一研究引擎），
context_type="repair"。

設計原則：
  - 只在 Tier 2 問題觸發（Health Score ≤ 70）
  - 研究結果只提供參考，不自動 apply
  - 每次研究 ≤ $0.05（Haiku 篩選）
  - 研究結果標記信心度
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))


@dataclass
class RepairReference:
    """修復參考 — 研究結果的結構化輸出."""

    incident_id: str
    module: str
    pattern: str
    research_query: str
    summary: str            # 研究摘要
    confidence: float       # 信心度 0-1
    source_urls: List[str]  # 參考來源
    status: str = "pending"  # "pending"|"done"|"no_value"|"failed"


class ImmuneResearch:
    """免疫系統研究引擎.

    偵測到 Tier 2 問題時，先上網研究再嘗試修復。
    """

    def __init__(
        self,
        brain: Any = None,
        event_bus: Any = None,
        workspace: Optional[Path] = None,
        searxng_url: str = "http://127.0.0.1:8888",
    ) -> None:
        self._brain = brain
        self._event_bus = event_bus
        self._workspace = workspace
        self._searxng_url = searxng_url
        self._research_history: List[RepairReference] = []
        self._subscribe()

    def _subscribe(self) -> None:
        """訂閱 Incident 事件."""
        if not self._event_bus:
            return
        try:
            from museon.core.event_bus import INCIDENT_DETECTED
            self._event_bus.subscribe(INCIDENT_DETECTED, self._on_incident)
        except Exception as e:
            logger.debug(f"ImmuneResearch subscription failed: {e}")

    def _on_incident(self, data: Optional[Dict] = None) -> None:
        """Incident 事件回調 — 只對 Tier 2 觸發研究."""
        if not data:
            return

        tier = data.get("suggested_tier", 1)
        if tier < 2:
            return  # Tier 1 不需要研究

        module = data.get("module", "unknown")
        pattern = data.get("pattern", "unknown")
        incident_id = data.get("incident_id", "")

        logger.info(
            f"ImmuneResearch: Tier 2 incident detected — "
            f"module={module}, pattern={pattern}"
        )

        # 排隊研究（由 cron 或手動觸發實際執行）
        self._queue_research(incident_id, module, pattern)

    def _queue_research(
        self, incident_id: str, module: str, pattern: str,
    ) -> None:
        """將研究任務加入佇列."""
        if not self._workspace:
            return

        queue_dir = self._workspace / "_system" / "bridge" / "immune_queue"
        queue_dir.mkdir(parents=True, exist_ok=True)

        queue_file = queue_dir / "pending.json"
        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                queue = json.load(fh)
        except Exception:
            queue = []

        # 避免重複
        existing_patterns = {q.get("pattern") for q in queue}
        if pattern in existing_patterns:
            return

        queue.append({
            "incident_id": incident_id,
            "module": module,
            "pattern": pattern,
            "query": f"{module} {pattern} fix solution python",
            "created_at": datetime.now(TZ8).isoformat(),
            "status": "pending",
        })

        # 保留最近 10 個
        queue = queue[-10:]

        with open(queue_file, "w", encoding="utf-8") as fh:
            json.dump(queue, fh, ensure_ascii=False, indent=2)

    async def research_incident(
        self,
        incident_id: str,
        module: str,
        pattern: str,
        query: Optional[str] = None,
    ) -> RepairReference:
        """對一個 Incident 執行研究.

        Args:
            incident_id: 事件 ID
            module: 問題模組
            pattern: 問題模式
            query: 自定搜尋查詢（預設自動生成）

        Returns:
            RepairReference 修復參考
        """
        search_query = query or f"{module} {pattern} fix solution"

        ref = RepairReference(
            incident_id=incident_id,
            module=module,
            pattern=pattern,
            research_query=search_query,
            summary="",
            confidence=0.0,
            source_urls=[],
        )

        try:
            from museon.research.research_engine import ResearchEngine

            engine = ResearchEngine(
                brain=self._brain,
                searxng_url=self._searxng_url,
            )
            result = await engine.research(
                query=search_query,
                context_type="repair",
                max_rounds=2,
                language="en",
            )

            if result.is_valuable and result.filtered_summary:
                ref.summary = result.filtered_summary
                ref.confidence = 0.7  # Haiku 篩選後的基礎信心度
                ref.source_urls = [h.url for h in result.hits[:5] if h.url]
                ref.status = "done"
            else:
                ref.status = "no_value"

        except Exception as e:
            logger.error(f"ImmuneResearch failed for {incident_id}: {e}")
            ref.status = "failed"

        self._research_history.append(ref)
        # 保留最近 20 筆
        if len(self._research_history) > 20:
            self._research_history = self._research_history[-20:]

        # 寫入結果檔案
        self._save_result(ref)

        # 發布事件
        if ref.status == "done" and self._event_bus:
            from museon.core.event_bus import (
                REPAIR_RESEARCH_READY, IMMUNE_KNOWLEDGE_GAINED,
            )
            self._event_bus.publish(REPAIR_RESEARCH_READY, {
                "incident_id": incident_id,
                "module": module,
                "pattern": pattern,
                "summary": ref.summary[:300],
                "confidence": ref.confidence,
            })
            # WP-04: 研究完成 → 發布知識學習事件
            self._event_bus.publish(IMMUNE_KNOWLEDGE_GAINED, {
                "incident_id": incident_id,
                "module": module,
                "pattern": pattern,
                "defense_summary": ref.summary[:200],
                "confidence": ref.confidence,
            })

        return ref

    async def process_queue(self, max_items: int = 2) -> List[RepairReference]:
        """處理待研究佇列.

        Args:
            max_items: 最多處理幾筆

        Returns:
            研究結果列表
        """
        if not self._workspace:
            return []

        queue_file = self._workspace / "_system" / "bridge" / "immune_queue" / "pending.json"
        if not queue_file.exists():
            return []

        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                queue = json.load(fh)
        except Exception:
            return []

        pending = [q for q in queue if q.get("status") == "pending"]
        if not pending:
            return []

        results = []
        for item in pending[:max_items]:
            ref = await self.research_incident(
                incident_id=item.get("incident_id", ""),
                module=item.get("module", "unknown"),
                pattern=item.get("pattern", "unknown"),
                query=item.get("query"),
            )
            results.append(ref)
            # 標記為已處理
            item["status"] = ref.status

        # 寫回更新後的佇列
        try:
            with open(queue_file, "w", encoding="utf-8") as fh:
                json.dump(queue, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"ImmuneResearch queue save failed: {e}")

        return results

    def _save_result(self, ref: RepairReference) -> None:
        """儲存研究結果到檔案."""
        if not self._workspace:
            return

        results_dir = self._workspace / "_system" / "bridge" / "immune_results"
        results_dir.mkdir(parents=True, exist_ok=True)

        result_file = results_dir / f"{ref.incident_id}.json"
        try:
            data = {
                "incident_id": ref.incident_id,
                "module": ref.module,
                "pattern": ref.pattern,
                "query": ref.research_query,
                "summary": ref.summary,
                "confidence": ref.confidence,
                "source_urls": ref.source_urls,
                "status": ref.status,
                "created_at": datetime.now(TZ8).isoformat(),
            }
            with open(result_file, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"ImmuneResearch save failed: {e}")

    def get_status(self) -> Dict:
        """取得狀態."""
        return {
            "total_researched": len(self._research_history),
            "done": sum(1 for r in self._research_history if r.status == "done"),
            "no_value": sum(1 for r in self._research_history if r.status == "no_value"),
            "failed": sum(1 for r in self._research_history if r.status == "failed"),
        }
