"""IntentionRadar — 意圖雷達.

把 OutwardTrigger 的觸發信號轉化為「帶著問題的搜尋計畫」。
純 CPU 模板填充，不用 LLM。

雙軌模板：
  Track A（自我進化）：技術/架構導向查詢
  Track B（服務進化）：領域/實務導向查詢
"""

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══ 搜尋查詢模板 ═══

QUERY_TEMPLATES_SELF = {
    "plateau": [
        "{skill_name} breakthrough methodology AI agent",
        "{domain} cutting edge approach {year}",
    ],
    "architecture": [
        "{bottleneck_topic} SOTA solution {year}",
        "AI agent {bottleneck_topic} best architecture",
    ],
    "rhythmic": [
        "AI agent architecture trends {year} {month}",
        "prompt engineering latest techniques {year}",
    ],
}

QUERY_TEMPLATES_SERVICE = {
    "pain": [
        "{domain} best practices {year}",
        "{skill_name} advanced techniques",
    ],
    "curiosity": [
        "{new_topic} fundamentals practical guide {year}",
        "{new_topic} key frameworks and methodology",
    ],
    "failure": [
        "{declining_area} quality improvement strategies",
        "{declining_area} AI assistant common pitfalls",
    ],
}

MAX_QUERIES_PER_EVENT = 2  # 每個觸發事件最多生成 2 條查詢


class IntentionRadar:
    """意圖雷達 — 觸發信號 → 搜尋計畫."""

    def __init__(
        self,
        workspace: Path,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._workspace = workspace
        self._event_bus = event_bus
        self._subscribe()

    def _subscribe(self) -> None:
        """訂閱外向搜尋需求事件."""
        if not self._event_bus:
            return
        try:
            from museon.core.event_bus import OUTWARD_SEARCH_NEEDED
            self._event_bus.subscribe(
                OUTWARD_SEARCH_NEEDED, self._on_search_needed
            )
            logger.info("IntentionRadar subscribed to OUTWARD_SEARCH_NEEDED")
        except Exception as e:
            logger.debug(f"IntentionRadar subscription failed: {e}")

    def _on_search_needed(self, data: Optional[Dict] = None) -> None:
        """收到觸發事件時，追加到搜尋計畫佇列."""
        if not data:
            return
        queries = self.generate_queries(data)
        if queries:
            self._append_to_plan(queries)

    # ─── 核心：生成搜尋查詢 ───

    def generate_queries(self, event: Dict) -> List[Dict]:
        """將一個 OUTWARD_SEARCH_NEEDED 事件轉為搜尋查詢列表.

        Returns:
            [
                {
                    "query": str,
                    "track": "self"|"service",
                    "context_type": "outward_self"|"outward_service",
                    "trigger_type": str,
                    "related_skill": str,
                    "related_domain": str,
                    "priority": str,
                    "max_rounds": int,
                    "scheduled_at": str,
                }
            ]
        """
        track = event.get("track", "service")
        trigger_type = event.get("trigger_type", "")
        now = datetime.now(TZ8)

        # 選擇模板
        if track == "self":
            templates = QUERY_TEMPLATES_SELF.get(trigger_type, [])
            context_type = "outward_self"
        else:
            templates = QUERY_TEMPLATES_SERVICE.get(trigger_type, [])
            context_type = "outward_service"

        if not templates:
            logger.warning(
                f"IntentionRadar: no template for track={track}, "
                f"trigger_type={trigger_type}"
            )
            return []

        # 準備模板變數
        variables = self._extract_variables(event, now)

        # 填充模板
        queries = []
        for template in templates[:MAX_QUERIES_PER_EVENT]:
            try:
                query_text = template.format(**variables)
            except KeyError:
                query_text = template  # 缺少變數時直接用原模板

            # 去重檢查
            if self._is_duplicate_query(query_text):
                continue

            queries.append({
                "query": query_text,
                "track": track,
                "context_type": context_type,
                "trigger_type": trigger_type,
                "related_skill": event.get("related_skill", ""),
                "related_domain": event.get("related_domain", ""),
                "priority": event.get("priority", "NORMAL"),
                "max_rounds": 2,
                "scheduled_at": now.isoformat(),
                "search_intent": event.get("search_intent", ""),
            })

        return queries

    def _extract_variables(self, event: Dict, now: datetime) -> Dict[str, str]:
        """從事件中提取模板填充變數."""
        intent = event.get("search_intent", "")
        return {
            "skill_name": event.get("related_skill", "unknown"),
            "domain": event.get("related_domain", "unknown"),
            "year": str(now.year),
            "month": now.strftime("%B"),
            "bottleneck_topic": self._extract_topic_from_intent(intent),
            "new_topic": event.get("related_domain", "unknown"),
            "declining_area": event.get("related_domain", "unknown"),
        }

    def _extract_topic_from_intent(self, intent: str) -> str:
        """從搜尋意圖中提取主題關鍵字."""
        # 簡單提取引號中的內容
        if "'" in intent:
            parts = intent.split("'")
            if len(parts) >= 2:
                return parts[1][:50]
        return intent[:50] if intent else "unknown"

    # ─── 佇列管理 ───

    def _append_to_plan(self, queries: List[Dict]) -> None:
        """追加查詢到搜尋計畫."""
        plan_dir = self._workspace / "_system" / "outward"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_file = plan_dir / "search_plan.json"

        existing = []
        if plan_file.exists():
            try:
                with open(plan_file, "r", encoding="utf-8") as fh:
                    existing = json.load(fh)
            except Exception:
                existing = []

        existing.extend(queries)

        # 只保留最近 50 條
        existing = existing[-50:]

        try:
            with open(plan_file, "w", encoding="utf-8") as fh:
                json.dump(existing, fh, ensure_ascii=False, indent=2)
            logger.info(
                f"IntentionRadar: {len(queries)} queries appended to plan"
            )
        except Exception as e:
            logger.error(f"IntentionRadar: save plan failed: {e}")

    def load_pending_plan(self) -> List[Dict]:
        """載入待執行的搜尋計畫（供 Nightly Step 13.7 使用）."""
        plan_file = self._workspace / "_system" / "outward" / "search_plan.json"
        if not plan_file.exists():
            return []
        try:
            with open(plan_file, "r", encoding="utf-8") as fh:
                plan = json.load(fh)
            # 只回傳未執行的
            return [q for q in plan if not q.get("executed")]
        except Exception:
            return []

    def mark_executed(self, query: Dict) -> None:
        """標記查詢已執行."""
        query["executed"] = True
        query["executed_at"] = datetime.now(TZ8).isoformat()

    def save_plan(self, plan: List[Dict]) -> None:
        """儲存更新後的計畫."""
        plan_dir = self._workspace / "_system" / "outward"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_file = plan_dir / "search_plan.json"
        try:
            with open(plan_file, "w", encoding="utf-8") as fh:
                json.dump(plan, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"IntentionRadar: save plan failed: {e}")

    def _is_duplicate_query(self, query: str) -> bool:
        """檢查查詢是否與現有計畫重複."""
        plan = self.load_pending_plan()
        query_lower = query.lower().strip()
        for existing in plan:
            if existing.get("query", "").lower().strip() == query_lower:
                return True
        return False
