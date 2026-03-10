"""CourseGenerator — 從知識圖譜自動生成學習課程.

分析知識圖譜的覆蓋率與缺口，自動建構結構化課程：
Module → Lesson → Resource。

設計原則：
- 知識缺口診斷驅動（先找不足，再補強）
- 課程結構化為 JSON，持久化到 _system/courses/
- 外部資源搜尋可接 SearXNG（如可用）
- 零 LLM 依賴（純邏輯建構，LLM 可選性增強）
- 用於 NightlyPipeline Step 7.5
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

DIFFICULTY_LEVELS = ("beginner", "intermediate", "advanced", "expert")
MAX_MODULES_PER_COURSE = 10
MAX_LESSONS_PER_MODULE = 8
MAX_RESOURCES_PER_LESSON = 5
SEARXNG_DEFAULT_URL = "http://localhost:8888"

# 知識強度閾值
STRONG_KNOWLEDGE_THRESHOLD = 0.7
WEAK_KNOWLEDGE_THRESHOLD = 0.3
GAP_THRESHOLD = 0.1


class CourseGenerator:
    """從知識圖譜自動生成結構化學習課程."""

    def __init__(
        self,
        workspace: Optional[str] = None,
        event_bus: Any = None,
        brain: Any = None,
    ) -> None:
        ws = workspace or os.getenv("MUSEON_WORKSPACE", str(Path.home() / "MUSEON"))
        self._workspace = Path(ws)
        self._event_bus = event_bus
        self._brain = brain
        self._searxng_url = os.getenv("SEARXNG_URL", SEARXNG_DEFAULT_URL)

        # 課程儲存目錄
        self._courses_dir = self._workspace / "_system" / "courses"
        self._courses_dir.mkdir(parents=True, exist_ok=True)

        # 知識圖譜路徑
        self._kg_path = self._workspace / "_system" / "knowledge_graph.json"

    # ── Public API ──────────────────────────────────────

    async def generate_course(
        self, topic: str, difficulty: str = "intermediate"
    ) -> Dict:
        """分析知識圖譜，為指定主題生成結構化課程.

        Args:
            topic: 課程主題
            difficulty: 難度等級 (beginner/intermediate/advanced/expert)

        Returns:
            Dict: 完整課程結構
        """
        if difficulty not in DIFFICULTY_LEVELS:
            difficulty = "intermediate"

        logger.info(f"Generating course: topic='{topic}', difficulty='{difficulty}'")

        # 1. 載入知識圖譜
        kg = self._load_knowledge_graph()

        # 2. 診斷知識缺口
        gaps = self._diagnose_gaps(topic, kg)

        # 3. 找出已有知識
        existing = self._find_existing_knowledge(topic, kg)

        # 4. 建構課程結構
        curriculum = self._build_curriculum(topic, gaps, existing, difficulty)

        # 5. 搜尋外部資源（非同步）
        try:
            for module in curriculum.get("modules", []):
                for lesson in module.get("lessons", []):
                    resources = await self._find_external_resources(
                        f"{topic} {lesson.get('title', '')}"
                    )
                    lesson["external_resources"] = resources[:MAX_RESOURCES_PER_LESSON]
        except Exception as e:
            logger.warning(f"External resource search failed: {e}")

        # 6. 生成課程 ID 與 metadata
        course_id = self._generate_course_id(topic)
        course = {
            "id": course_id,
            "topic": topic,
            "difficulty": difficulty,
            "created_at": datetime.now(TZ8).isoformat(),
            "gap_count": len(gaps),
            "existing_knowledge_count": len(existing),
            "status": "generated",
            **curriculum,
        }

        # 7. 持久化
        self._save_course(course)

        # 8. 發布事件
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import KNOWLEDGE_GRAPH_UPDATED
                self._event_bus.publish(KNOWLEDGE_GRAPH_UPDATED, {
                    "action": "course_generated",
                    "course_id": course_id,
                    "topic": topic,
                    "timestamp": datetime.now(TZ8).isoformat(),
                })
        except Exception as e:
            logger.warning(f"Failed to publish course event: {e}")

        logger.info(f"Course generated: {course_id} with {len(curriculum.get('modules', []))} modules")
        return course

    def list_courses(self) -> List[Dict]:
        """列出所有已生成的課程.

        Returns:
            List of course summary dicts
        """
        courses: List[Dict] = []
        try:
            for fp in sorted(self._courses_dir.glob("*.json")):
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    courses.append({
                        "id": data.get("id", fp.stem),
                        "topic": data.get("topic", ""),
                        "difficulty": data.get("difficulty", ""),
                        "created_at": data.get("created_at", ""),
                        "module_count": len(data.get("modules", [])),
                        "status": data.get("status", "unknown"),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Failed to list courses: {e}")
        return courses

    def get_course(self, course_id: str) -> Optional[Dict]:
        """取得特定課程的完整內容.

        Args:
            course_id: 課程 ID

        Returns:
            課程 Dict 或 None
        """
        fp = self._courses_dir / f"{course_id}.json"
        if not fp.exists():
            return None
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to read course {course_id}: {e}")
            return None

    # ── Knowledge Graph Analysis ────────────────────────

    def _load_knowledge_graph(self) -> Dict:
        """載入知識圖譜."""
        if not self._kg_path.exists():
            logger.info("Knowledge graph not found, using empty graph")
            return {"nodes": [], "edges": []}
        try:
            return json.loads(self._kg_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to load knowledge graph: {e}")
            return {"nodes": [], "edges": []}

    def _diagnose_gaps(self, topic: str, kg: Optional[Dict] = None) -> List[Dict]:
        """識別知識缺口.

        分析知識圖譜中與主題相關的節點，找出強度低於閾值的區域。

        Args:
            topic: 主題
            kg: 知識圖譜（可選，預設載入）

        Returns:
            知識缺口列表 [{concept, current_strength, gap_type}]
        """
        if kg is None:
            kg = self._load_knowledge_graph()

        nodes = kg.get("nodes", [])
        edges = kg.get("edges", [])
        topic_lower = topic.lower()
        gaps: List[Dict] = []

        # 找到與主題相關的節點
        related_nodes: List[Dict] = []
        for node in nodes:
            node_text = (
                node.get("label", "") + " " +
                node.get("content", "") + " " +
                " ".join(node.get("tags", []))
            ).lower()
            if topic_lower in node_text:
                related_nodes.append(node)

        if not related_nodes:
            # 無相關知識 = 全是缺口
            gaps.append({
                "concept": topic,
                "current_strength": 0.0,
                "gap_type": "no_coverage",
                "description": f"No existing knowledge found for '{topic}'",
            })
            return gaps

        # 分析每個相關節點的強度
        for node in related_nodes:
            strength = node.get("strength", node.get("weight", 0.5))
            node_id = node.get("id", node.get("label", ""))
            if strength < WEAK_KNOWLEDGE_THRESHOLD:
                gaps.append({
                    "concept": node.get("label", node_id),
                    "current_strength": strength,
                    "gap_type": "weak_knowledge",
                    "description": f"Weak understanding of '{node.get('label', node_id)}'",
                })
            elif strength < STRONG_KNOWLEDGE_THRESHOLD:
                gaps.append({
                    "concept": node.get("label", node_id),
                    "current_strength": strength,
                    "gap_type": "needs_reinforcement",
                    "description": f"Moderate knowledge, needs reinforcement",
                })

        # 檢查連結缺口（有知識但缺少連結）
        node_ids = {n.get("id", n.get("label", "")) for n in related_nodes}
        connected: Set[str] = set()
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if src in node_ids:
                connected.add(tgt)
            if tgt in node_ids:
                connected.add(src)

        isolated = node_ids - connected
        for nid in isolated:
            node_data = next((n for n in related_nodes if n.get("id") == nid), None)
            if node_data:
                gaps.append({
                    "concept": node_data.get("label", nid),
                    "current_strength": node_data.get("strength", 0.5),
                    "gap_type": "isolated_knowledge",
                    "description": "Knowledge exists but lacks connections",
                })

        return gaps

    def _find_existing_knowledge(self, topic: str, kg: Dict) -> List[Dict]:
        """找出已有的強項知識."""
        nodes = kg.get("nodes", [])
        topic_lower = topic.lower()
        existing: List[Dict] = []
        for node in nodes:
            node_text = (
                node.get("label", "") + " " +
                node.get("content", "") + " " +
                " ".join(node.get("tags", []))
            ).lower()
            strength = node.get("strength", node.get("weight", 0.5))
            if topic_lower in node_text and strength >= STRONG_KNOWLEDGE_THRESHOLD:
                existing.append({
                    "concept": node.get("label", ""),
                    "strength": strength,
                    "type": node.get("type", "unknown"),
                })
        return existing

    # ── Curriculum Building ─────────────────────────────

    def _build_curriculum(
        self,
        topic: str,
        gaps: List[Dict],
        existing_knowledge: List[Dict],
        difficulty: str = "intermediate",
    ) -> Dict:
        """建構學習路徑：Module → Lesson → Resource.

        Args:
            topic: 主題
            gaps: 知識缺口列表
            existing_knowledge: 已有知識列表
            difficulty: 難度

        Returns:
            Dict with modules array
        """
        modules: List[Dict] = []
        difficulty_idx = DIFFICULTY_LEVELS.index(difficulty) if difficulty in DIFFICULTY_LEVELS else 1

        # Module 0: 基礎回顧（如果有已有知識）
        if existing_knowledge and difficulty_idx <= 1:
            review_lessons = []
            for ek in existing_knowledge[:MAX_LESSONS_PER_MODULE]:
                review_lessons.append({
                    "title": f"Review: {ek['concept']}",
                    "objective": f"Refresh understanding of {ek['concept']}",
                    "estimated_minutes": 10,
                    "lesson_type": "review",
                    "external_resources": [],
                })
            if review_lessons:
                modules.append({
                    "module_id": f"M0-review",
                    "title": f"Foundations Review: {topic}",
                    "description": "Review existing knowledge before diving deeper",
                    "order": 0,
                    "lessons": review_lessons,
                })

        # 根據缺口類型分組
        no_coverage = [g for g in gaps if g["gap_type"] == "no_coverage"]
        weak = [g for g in gaps if g["gap_type"] == "weak_knowledge"]
        reinforce = [g for g in gaps if g["gap_type"] == "needs_reinforcement"]
        isolated = [g for g in gaps if g["gap_type"] == "isolated_knowledge"]

        module_order = len(modules)

        # Module: 核心概念（全新覆蓋）
        if no_coverage:
            lessons = []
            for gap in no_coverage:
                lessons.append({
                    "title": f"Introduction to {gap['concept']}",
                    "objective": f"Build foundational understanding of {gap['concept']}",
                    "estimated_minutes": 30 + difficulty_idx * 10,
                    "lesson_type": "new_concept",
                    "external_resources": [],
                })
            modules.append({
                "module_id": f"M{module_order}-core",
                "title": f"Core Concepts: {topic}",
                "description": "Build foundational knowledge from scratch",
                "order": module_order,
                "lessons": lessons[:MAX_LESSONS_PER_MODULE],
            })
            module_order += 1

        # Module: 弱項強化
        if weak:
            lessons = []
            for gap in weak:
                lessons.append({
                    "title": f"Strengthen: {gap['concept']}",
                    "objective": f"Deepen understanding from {gap['current_strength']:.0%} to solid level",
                    "estimated_minutes": 20 + difficulty_idx * 5,
                    "lesson_type": "strengthening",
                    "external_resources": [],
                })
            modules.append({
                "module_id": f"M{module_order}-strengthen",
                "title": f"Deepening: {topic}",
                "description": "Strengthen weak areas of understanding",
                "order": module_order,
                "lessons": lessons[:MAX_LESSONS_PER_MODULE],
            })
            module_order += 1

        # Module: 知識連結（孤立知識）
        if isolated:
            lessons = []
            for gap in isolated:
                lessons.append({
                    "title": f"Connect: {gap['concept']}",
                    "objective": "Build connections between isolated knowledge nodes",
                    "estimated_minutes": 15 + difficulty_idx * 5,
                    "lesson_type": "connecting",
                    "external_resources": [],
                })
            modules.append({
                "module_id": f"M{module_order}-connect",
                "title": f"Knowledge Integration: {topic}",
                "description": "Connect isolated knowledge nodes into a cohesive understanding",
                "order": module_order,
                "lessons": lessons[:MAX_LESSONS_PER_MODULE],
            })
            module_order += 1

        # Module: 鞏固強化（有一定基礎但需鞏固）
        if reinforce:
            lessons = []
            for gap in reinforce:
                lessons.append({
                    "title": f"Reinforce: {gap['concept']}",
                    "objective": f"Solidify understanding through practice",
                    "estimated_minutes": 15 + difficulty_idx * 5,
                    "lesson_type": "reinforcement",
                    "external_resources": [],
                })
            modules.append({
                "module_id": f"M{module_order}-reinforce",
                "title": f"Reinforcement: {topic}",
                "description": "Consolidate knowledge through practice and application",
                "order": module_order,
                "lessons": lessons[:MAX_LESSONS_PER_MODULE],
            })
            module_order += 1

        # Module: 進階應用（進階以上難度）
        if difficulty_idx >= 2:
            modules.append({
                "module_id": f"M{module_order}-advanced",
                "title": f"Advanced Applications: {topic}",
                "description": "Apply knowledge to complex real-world scenarios",
                "order": module_order,
                "lessons": [
                    {
                        "title": f"Case Study: {topic} in Practice",
                        "objective": "Analyze real-world application scenarios",
                        "estimated_minutes": 45,
                        "lesson_type": "case_study",
                        "external_resources": [],
                    },
                    {
                        "title": f"Project: Build with {topic}",
                        "objective": "Hands-on project applying all learned concepts",
                        "estimated_minutes": 60,
                        "lesson_type": "project",
                        "external_resources": [],
                    },
                ],
            })
            module_order += 1

        # 計算總學習時間
        total_minutes = sum(
            sum(l.get("estimated_minutes", 0) for l in m.get("lessons", []))
            for m in modules
        )

        return {
            "modules": modules[:MAX_MODULES_PER_COURSE],
            "total_estimated_minutes": total_minutes,
            "total_modules": len(modules[:MAX_MODULES_PER_COURSE]),
            "total_lessons": sum(len(m.get("lessons", [])) for m in modules[:MAX_MODULES_PER_COURSE]),
        }

    # ── External Resources ──────────────────────────────

    async def _find_external_resources(self, topic: str) -> List[Dict]:
        """搜尋外部學習資源（透過 SearXNG 如果可用）.

        Args:
            topic: 搜尋主題

        Returns:
            List of resource dicts [{title, url, source}]
        """
        try:
            import aiohttp
        except ImportError:
            logger.debug("aiohttp not installed — skipping external resource search")
            return []

        resources: List[Dict] = []
        query = f"{topic} tutorial learn"

        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "q": query,
                    "format": "json",
                    "categories": "general",
                    "language": "en",
                    "pageno": 1,
                }
                async with session.get(
                    f"{self._searxng_url}/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        logger.debug(f"SearXNG search returned HTTP {resp.status}")
                        return []
                    data = await resp.json()
                    results = data.get("results", [])
                    for r in results[:MAX_RESOURCES_PER_LESSON]:
                        resources.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "source": r.get("engine", "searxng"),
                            "snippet": r.get("content", "")[:200],
                        })
        except Exception as e:
            logger.debug(f"External resource search failed: {e}")

        return resources

    # ── Helpers ──────────────────────────────────────────

    @staticmethod
    def _generate_course_id(topic: str) -> str:
        """生成課程 ID."""
        slug = topic.lower().replace(" ", "-")[:30]
        ts = datetime.now(TZ8).strftime("%Y%m%d%H%M")
        short_hash = hashlib.md5(f"{topic}{ts}".encode()).hexdigest()[:6]
        return f"course-{slug}-{short_hash}"

    def _save_course(self, course: Dict) -> None:
        """持久化課程到 _system/courses/."""
        try:
            fp = self._courses_dir / f"{course['id']}.json"
            fp.write_text(
                json.dumps(course, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"Course saved: {fp}")
        except Exception as e:
            logger.error(f"Failed to save course: {e}")
