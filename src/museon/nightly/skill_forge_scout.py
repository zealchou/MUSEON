"""SkillForgeScout — 技能鍛造偵察引擎.

三模式偵察：
  Mode A (Gap Detection) — 偵測能力缺口，搜尋最佳實踐
  Mode B (Upgrade Scan)  — 掃描現有 Skill 的升級機會（Phase 2 預留）
  Mode C (Blank Filling) — 從探索結晶中提煉技能改善線索

核心約束：
  - 只產草稿，絕不直接修改 SKILL.md
  - 草稿提交到 Morphenix 流程（notes → proposal → gate → execute）
  - 每次研究 ≤ $0.05（Haiku 篩選）

資料流：
  ExplorationBridge → scout_queue/pending.json → SkillForgeScout
  → ResearchEngine(context="skill") → 草稿 → morphenix/notes/
  → publish SCOUT_DRAFT_READY → Morphenix pipeline 消費
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 每次最多處理幾個 scout queue 項目
MAX_QUEUE_ITEMS_PER_RUN = 3


class SkillForgeScout:
    """技能鍛造偵察引擎 — 研究後產草稿，交 Morphenix 審核.

    使用 ResearchEngine 進行上網研究（SearXNG + Haiku 篩選），
    將研究結果轉化為 Morphenix 可消費的 iteration note。
    """

    def __init__(
        self,
        brain: Any = None,
        event_bus: Any = None,
        workspace: Optional[Path] = None,
        pulse_db: Any = None,
        searxng_url: str = "http://127.0.0.1:8888",
    ) -> None:
        self._brain = brain
        self._event_bus = event_bus
        self._workspace = workspace
        self._pulse_db = pulse_db
        self._searxng_url = searxng_url
        self._subscribe()

    def _subscribe(self) -> None:
        """訂閱 scout gap 事件 — 自動觸發研究."""
        if not self._event_bus:
            return
        try:
            from museon.core.event_bus import SCOUT_GAP_DETECTED
            self._event_bus.subscribe(SCOUT_GAP_DETECTED, self._on_gap_detected)
        except Exception as e:
            logger.debug(f"SkillForgeScout subscription failed: {e}")

    def _on_gap_detected(self, data: Optional[Dict] = None) -> None:
        """ExplorationBridge 偵測到技能改善信號時的回調.

        記錄到日誌，實際研究由 process_queue 或 cron 觸發。
        """
        if not data:
            return
        topic = data.get("topic", "")
        logger.info(f"SkillForgeScout: gap detected — '{topic[:50]}'")

    async def process_queue(self, max_items: int = MAX_QUEUE_ITEMS_PER_RUN) -> List[Dict]:
        """處理 scout_queue/pending.json 中的待研究項目.

        流程：
        1. 讀取 pending.json
        2. 對每個 pending 項目執行 ResearchEngine 研究
        3. 將研究結果轉化為草稿
        4. 草稿寫入 morphenix/notes/ 供 Nightly 消費
        5. 發布 SCOUT_DRAFT_READY 事件

        Returns:
            處理結果列表
        """
        if not self._workspace:
            return []

        queue_file = self._workspace / "_system" / "bridge" / "scout_queue" / "pending.json"
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
            topic = item.get("topic", "")
            findings_snippet = item.get("findings_snippet", "")

            result = await self._research_and_draft(topic, findings_snippet)
            results.append(result)

            # 更新佇列狀態
            item["status"] = result.get("status", "done")

        # 寫回更新的佇列
        try:
            with open(queue_file, "w", encoding="utf-8") as fh:
                json.dump(queue, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"SkillForgeScout queue save failed: {e}")

        return results

    async def _research_and_draft(self, topic: str, findings_snippet: str) -> Dict:
        """對一個主題執行研究並產出草稿.

        Args:
            topic: 技能改善主題
            findings_snippet: 探索發現片段（提供上下文）

        Returns:
            {status, topic, summary, draft_id}
        """
        result = {"topic": topic, "status": "failed", "summary": "", "draft_id": ""}

        # 建構搜尋查詢
        query = self._build_skill_query(topic, findings_snippet)

        try:
            from museon.research.research_engine import ResearchEngine

            engine = ResearchEngine(
                brain=self._brain,
                searxng_url=self._searxng_url,
            )
            research_result = await engine.research(
                query=query,
                context_type="skill",
                max_rounds=3,
                language="zh-TW",
            )

            if not research_result.is_valuable or not research_result.filtered_summary:
                result["status"] = "no_value"
                return result

            # 產出草稿
            draft = self._generate_draft(
                topic=topic,
                research_summary=research_result.filtered_summary,
                source_urls=[h.url for h in research_result.hits[:5] if h.url],
            )

            # 寫入 morphenix/notes/
            draft_id = self._write_to_morphenix_notes(topic, draft)
            result["draft_id"] = draft_id
            result["summary"] = research_result.filtered_summary[:200]
            result["status"] = "done"

            # 儲存到 PulseDB
            if self._pulse_db:
                try:
                    self._pulse_db.save_scout_draft(
                        draft_id=draft_id,
                        topic=topic,
                        mode="gap",
                        draft_content=draft,
                        research_summary=research_result.filtered_summary,
                    )
                except Exception as e:
                    logger.debug(f"Scout draft DB save failed: {e}")

            # 發布事件
            if self._event_bus:
                from museon.core.event_bus import SCOUT_DRAFT_READY
                self._event_bus.publish(SCOUT_DRAFT_READY, {
                    "draft_id": draft_id,
                    "topic": topic,
                    "summary": result["summary"],
                })

            logger.info(f"SkillForgeScout: draft ready — '{topic[:40]}' → {draft_id}")

        except Exception as e:
            logger.error(f"SkillForgeScout research failed for '{topic}': {e}")

        return result

    def _build_skill_query(self, topic: str, findings_snippet: str) -> str:
        """根據主題和探索片段建構搜尋查詢."""
        # 從 findings 中提取關鍵詞
        keywords = []
        if findings_snippet:
            # 取前 100 字的核心內容
            snippet = findings_snippet[:100].replace("\n", " ")
            keywords.append(snippet)

        # 組合查詢
        base = f"{topic} best practices"
        if keywords:
            return f"{base} {keywords[0]}"
        return base

    def _generate_draft(
        self, topic: str, research_summary: str, source_urls: List[str],
    ) -> str:
        """將研究結果轉化為 Morphenix 可消費的草稿格式."""
        now = datetime.now(TZ8)
        urls_text = "\n".join(f"  - {url}" for url in source_urls[:3]) if source_urls else "  - (無外部來源)"

        draft = f"""## Scout 技能改善草稿

**主題**: {topic}
**偵察模式**: Gap Detection (Mode A)
**產出時間**: {now.strftime('%Y-%m-%d %H:%M')}

### 研究摘要
{research_summary}

### 改善建議
基於上述研究，建議檢視以下方向是否可整合到現有 Skill 中：
1. 從研究中提煉的核心做法
2. 與現有系統的適配度評估
3. 具體的改善步驟（需人類確認）

### 參考來源
{urls_text}

### 安全聲明
- 此草稿由 SkillForgeScout 自動產出
- 需經 Morphenix L2 提案流程審核後方可執行
- 絕不直接修改 SKILL.md 或任何受保護檔案
"""
        return draft

    def _write_to_morphenix_notes(self, topic: str, draft: str) -> str:
        """將草稿寫入 morphenix/notes/ 目錄."""
        if not self._workspace:
            return ""

        notes_dir = self._workspace / "_system" / "morphenix" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(TZ8)
        draft_id = f"scout_{now.strftime('%Y%m%d_%H%M%S')}"
        note_file = notes_dir / f"{draft_id}.json"

        note = {
            "type": "scout_skill_draft",
            "topic": topic,
            "draft": draft,
            "source": "skill_forge_scout",
            "created_at": now.isoformat(),
            "auto_propose": True,  # 讓 Morphenix 自動提案
        }

        try:
            with open(note_file, "w", encoding="utf-8") as fh:
                json.dump(note, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Scout note write failed: {e}")
            return ""

        return draft_id

    async def forge_from_exploration(
        self, topic: str, findings: str,
    ) -> Optional[Dict]:
        """直接從探索結果觸發鍛造（不經佇列）.

        供探索完成後即時調用。

        Args:
            topic: 探索主題
            findings: 探索發現

        Returns:
            鍛造結果 or None
        """
        from museon.nightly.exploration_bridge import _SKILL_SIGNALS

        # 檢查是否包含技能改善信號
        text_lower = findings.lower()
        has_skill_signal = any(kw.lower() in text_lower for kw in _SKILL_SIGNALS)

        if not has_skill_signal:
            return None

        result = await self._research_and_draft(topic, findings[:1200])
        return result if result.get("status") == "done" else None
