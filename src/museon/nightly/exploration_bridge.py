"""ExplorationBridge — 探索→演化的路由橋樑.

訂閱 EXPLORATION_CRYSTALLIZED / EXPLORATION_INSIGHT 事件，
純 CPU 分析探索結果，分流到三個下游：
  1. SkillForgeScout — 如果探索發現了技能改善線索
  2. CuriosityRouter — 如果探索產生了新的好奇問題
  3. Morphenix Notes — 如果探索產出了演化建議

設計原則：
  - 純 CPU，零 LLM Token
  - 關鍵字匹配 + 規則路由
  - 寫入中間檔案供下游 cron 消費（鬆耦合）
"""

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.core.event_bus import (
    EXPLORATION_CRYSTALLIZED,
    EXPLORATION_INSIGHT,
    NIGHTLY_COMPLETED,
    PROACTIVE_MESSAGE,
    SCOUT_DRAFT_READY,
    SCOUT_GAP_DETECTED,
)

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 技能改善信號關鍵字
_SKILL_SIGNALS = [
    "最佳實踐", "best practice", "更好的方法", "改善", "優化",
    "框架", "framework", "方法論", "methodology", "pattern",
    "架構", "architecture", "設計模式", "design pattern",
    "升級", "upgrade", "進化", "evolve", "改進", "enhance",
]

# 演化建議信號關鍵字
_EVOLUTION_SIGNALS = [
    "應該", "建議", "可以改", "值得嘗試", "下一步",
    "缺少", "missing", "不足", "gap", "弱點",
    "新增", "add", "整合", "integrate", "引入", "introduce",
]

# 問句偵測模式
_QUESTION_PATTERN = re.compile(r"[？?]\s*$|^如何|^為什麼|^怎麼|^what |^how |^why ", re.I)


class ExplorationBridge:
    """探索→演化的橋梁 — 純 CPU 路由."""

    def __init__(
        self,
        event_bus: Any,
        workspace: Path,
    ) -> None:
        self._event_bus = event_bus
        self._workspace = workspace
        self._pending_routes: List[Dict] = []
        self._subscribe()

    def _subscribe(self) -> None:
        """訂閱探索事件."""
        if self._event_bus:
            self._event_bus.subscribe(EXPLORATION_CRYSTALLIZED, self._on_exploration)
            self._event_bus.subscribe(EXPLORATION_INSIGHT, self._on_exploration)
            self._event_bus.subscribe(NIGHTLY_COMPLETED, self._on_nightly_complete)
            self._event_bus.subscribe(SCOUT_DRAFT_READY, self._on_scout_draft)

    def _on_exploration(self, data: Optional[Dict] = None) -> None:
        """處理探索完成事件 — 純 CPU 分析並分流."""
        if not data:
            return

        findings = data.get("findings", "")
        topic = data.get("topic", "")
        crystallized = data.get("crystallized", False)

        if not findings or len(findings) < 20:
            return

        routes = []

        # 1. 檢查技能改善線索
        if self._has_signal(findings, _SKILL_SIGNALS):
            routes.append("skill")
            self._route_to_scout(topic, findings)

        # 2. 檢查新問題
        new_questions = self._extract_questions(findings)
        if new_questions:
            routes.append("curiosity")
            self._route_to_curiosity(new_questions)

        # 3. 檢查演化建議
        if self._has_signal(findings, _EVOLUTION_SIGNALS):
            routes.append("evolution")
            self._route_to_morphenix_notes(topic, findings)

        if routes:
            logger.info(
                f"ExplorationBridge: topic='{topic[:30]}' "
                f"routed to {routes}"
            )

        # 探索有洞見 → 主動推送給使用者（透過 PROACTIVE_MESSAGE 事件）
        if findings and len(findings) > 50 and self._event_bus:
            crystal_tag = "💎 " if crystallized else ""
            # 三句摘要格式：發現了什麼 + 為什麼重要 + 下一步
            sentences = [s.strip() for s in re.split(r"[。！？\n]", findings) if s.strip()]
            what = sentences[0][:120] if sentences else findings[:120]
            why = sentences[1][:120] if len(sentences) > 1 else "此發現與 MUSEON 的核心使命相關"
            next_step = sentences[2][:120] if len(sentences) > 2 else "已加入知識庫供後續深化"
            msg = (
                f"🔭 {crystal_tag}探索「{topic[:30]}」\n\n"
                f"📌 發現：{what}\n"
                f"💡 意義：{why}\n"
                f"⏭ 後續：{next_step}"
            )
            self._event_bus.publish(PROACTIVE_MESSAGE, {
                "message": msg,
                "timestamp": datetime.now(TZ8).timestamp(),
                "source": "exploration_bridge",
            })

        # 結晶完成後的行動路由
        if crystallized and findings:
            self._route_crystal(topic, findings)

        # 記錄待批次處理
        self._pending_routes.append({
            "topic": topic,
            "routes": routes,
            "timestamp": datetime.now(TZ8).isoformat(),
            "crystallized": crystallized,
        })

    def _on_nightly_complete(self, data: Optional[Dict] = None) -> None:
        """凌晨整合完成後，產出路由摘要."""
        if not self._pending_routes:
            return

        summary_dir = self._workspace / "_system" / "bridge"
        summary_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        summary_file = summary_dir / f"routes_{today}.json"

        try:
            with open(summary_file, "w", encoding="utf-8") as fh:
                json.dump(self._pending_routes, fh, ensure_ascii=False, indent=2)
            logger.info(
                f"ExplorationBridge: {len(self._pending_routes)} routes "
                f"saved to {summary_file.name}"
            )
        except Exception as e:
            logger.error(f"ExplorationBridge summary write failed: {e}")

        self._pending_routes.clear()

    # ── 路由目標 ──

    def _route_to_scout(self, topic: str, findings: str) -> None:
        """將技能改善線索寫入 Scout 待研究佇列."""
        scout_dir = self._workspace / "_system" / "bridge" / "scout_queue"
        scout_dir.mkdir(parents=True, exist_ok=True)

        queue_file = scout_dir / "pending.json"
        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                queue = json.load(fh)
        except Exception:
            queue = []

        queue.append({
            "topic": topic,
            "findings_snippet": findings[:1200],
            "source": "exploration_bridge",
            "created_at": datetime.now(TZ8).isoformat(),
            "status": "pending",
        })

        # 保留最近 20 個
        queue = queue[-20:]

        with open(queue_file, "w", encoding="utf-8") as fh:
            json.dump(queue, fh, ensure_ascii=False, indent=2)

        if self._event_bus:
            self._event_bus.publish(SCOUT_GAP_DETECTED, {"topic": topic})

    def _route_to_curiosity(self, questions: List[str]) -> None:
        """將新問題追加到好奇心佇列."""
        curiosity_dir = self._workspace / "_system" / "curiosity"
        curiosity_dir.mkdir(parents=True, exist_ok=True)

        queue_file = curiosity_dir / "question_queue.json"
        try:
            with open(queue_file, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
                # 相容兩種格式：{"questions": [...]} 或 [...]
                queue = raw.get("questions", []) if isinstance(raw, dict) else raw
        except Exception:
            queue = []

        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        for q in questions:
            queue.append({
                "question": q[:200],
                "source_date": today,
                "status": "pending",
                "source": "exploration_bridge",
            })

        queue = queue[-50:]

        with open(queue_file, "w", encoding="utf-8") as fh:
            json.dump(queue, fh, ensure_ascii=False, indent=2)

    def _route_to_morphenix_notes(self, topic: str, findings: str) -> None:
        """將演化建議寫入 Morphenix 迭代筆記."""
        notes_dir = self._workspace / "_system" / "morphenix" / "notes"
        notes_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(TZ8)
        note_id = now.strftime("%Y%m%d_%H%M%S")
        note_file = notes_dir / f"exploration_{note_id}.json"

        note = {
            "type": "exploration_insight",
            "topic": topic,
            "observation": findings[:5000],
            "source": "exploration_bridge",
            "created_at": now.isoformat(),
        }

        with open(note_file, "w", encoding="utf-8") as fh:
            json.dump(note, fh, ensure_ascii=False, indent=2)

    def _on_scout_draft(self, data: Optional[Dict] = None) -> None:
        """接收 Scout 草稿完成事件 → 路由到 Morphenix notes."""
        if not data:
            return
        topic = data.get("topic", "")
        draft = data.get("draft_path", "")
        if topic:
            self._route_to_morphenix_notes(
                topic=f"[Scout] {topic}",
                findings=data.get("summary", f"Scout 草稿已完成：{draft}"),
            )
            logger.info(f"ExplorationBridge: Scout draft routed to morphenix: {topic[:40]}")

    # ── 純 CPU 分析工具 ──

    def _has_signal(self, text: str, keywords: List[str]) -> bool:
        """檢查文本是否包含任何信號關鍵字."""
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)

    def _extract_questions(self, text: str) -> List[str]:
        """從文本中提取問句."""
        questions = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if _QUESTION_PATTERN.search(line):
                # 清理 markdown 格式
                clean = re.sub(r"^[-*>\d.]+\s*", "", line).strip()
                if 5 < len(clean) < 200:
                    questions.append(clean)
        return questions[:5]  # 最多 5 個

    def _route_crystal(self, crystal_topic: str, crystal_findings: str) -> None:
        """結晶完成後的行動路由 — 觸發後續行動而非只存文章."""
        findings_lower = crystal_findings.lower()
        now = datetime.now(TZ8)
        ts = now.strftime("%Y%m%d_%H%M%S")

        # 技術洞見 → 檢查是否有 Skill 需要改進（寫入 scout_queue）
        if any(kw in findings_lower for kw in ["skill", "工具", "方法", "框架", "最佳實踐"]):
            try:
                scout_dir = self._workspace / "_system" / "bridge" / "scout_queue"
                scout_dir.mkdir(parents=True, exist_ok=True)
                note_file = scout_dir / f"scout_crystal_insight_{ts}.json"
                note_file.write_text(
                    json.dumps({
                        "type": "scout_crystal_insight",
                        "topic": crystal_topic,
                        "gap_identified": crystal_findings[:200],
                        "source": "exploration_crystal",
                        "created_at": now.isoformat(),
                        "auto_propose": True,
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(f"ExplorationBridge: crystal insight routed to scout_queue: {crystal_topic[:40]}")
            except Exception as e:
                logger.debug(f"ExplorationBridge: scout routing failed (degraded): {e}")

        # 自我認知更新 → 寫入觀察日誌
        if any(kw in findings_lower for kw in ["認知", "盲點", "偏見", "學到", "發現"]):
            try:
                obs_path = self._workspace / "_system" / "footprints" / "crystal_observations.jsonl"
                obs_path.parent.mkdir(parents=True, exist_ok=True)
                with obs_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({
                        "topic": crystal_topic,
                        "observation": crystal_findings[:500],
                        "timestamp": now.isoformat(),
                    }, ensure_ascii=False) + "\n")
                logger.info(f"ExplorationBridge: crystal observation logged: {crystal_topic[:40]}")
            except Exception as e:
                logger.debug(f"ExplorationBridge: observation logging failed (degraded): {e}")
