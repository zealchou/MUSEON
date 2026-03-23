"""MemoryReflector — Hindsight 式反思引擎.

Project Epigenesis 迭代 5：在 Recall 和 Response 之間加入 Reflect。

Hindsight 三階段管線：
  Retain（保留）→ Recall（回憶）→ Reflect（反思）

Reflect 做什麼：
  1. 交叉比對：召回的記憶之間是否矛盾？
  2. 模式發現：跨時間的重複模式 → 標記為值得注意
  3. 時間軸整理：將零散的召回按時序重組為脈絡
  4. 信念強化/削弱：reinforcement_count 高的記憶 → 強調；低的 → 降權
  5. 產出反思摘要：供 brain.py 注入 context

此引擎是純 CPU 計算（不呼叫 LLM），保持低延遲。

消費者：brain.py _build_memory_inject() 中的表觀遺傳路由後
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from museon.memory.adaptive_decay import AdaptiveDecay

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# 矛盾偵測：兩條記憶的 type 組合被視為潛在矛盾
CONTRADICTION_PAIRS = {
    ("cognitive_breakthrough", "failure_lesson"),  # 突破 vs 失敗
}

# 模式偵測：相同 type 的記憶超過此數量 → 標記為重複模式
PATTERN_THRESHOLD: int = 2

# 反思摘要的最大字數
MAX_REFLECTION_CHARS: int = 500

# 時間軸排序的日期格式
DATE_FORMAT: str = "%Y-%m-%d"


# ═══════════════════════════════════════════
# 資料結構
# ═══════════════════════════════════════════

@dataclass
class ReflectionResult:
    """反思引擎的輸出."""
    # 按 activation 排序後的記憶（已加入 _activation 欄位）
    ranked_memories: List[Dict[str, Any]] = field(default_factory=list)

    # 偵測到的矛盾
    contradictions: List[Dict[str, Any]] = field(default_factory=list)

    # 偵測到的重複模式
    patterns: List[Dict[str, Any]] = field(default_factory=list)

    # 時間軸脈絡（按時序排列的摘要）
    timeline: List[Dict[str, Any]] = field(default_factory=list)

    # 反思摘要文字（供注入 context）
    summary: str = ""

    # 反思元資料
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════
# MemoryReflector
# ═══════════════════════════════════════════

class MemoryReflector:
    """Hindsight 式反思引擎.

    純 CPU 計算，不呼叫 LLM，保持低延遲。
    在 Recall 結果進來後：
    1. 用 AdaptiveDecay 計算 activation 並排序
    2. 偵測矛盾
    3. 偵測重複模式
    4. 整理時間軸
    5. 產出反思摘要
    """

    def __init__(self, decay_engine: Optional[AdaptiveDecay] = None) -> None:
        """初始化反思引擎.

        Args:
            decay_engine: AdaptiveDecay 實例（None 時自動建立）
        """
        self._decay = decay_engine or AdaptiveDecay()

    def reflect(
        self,
        recalled_memories: Optional[List[Dict]] = None,
        recalled_crystals: Optional[List[Dict]] = None,
        recalled_soul_rings: Optional[List[Dict]] = None,
        current_query: str = "",
    ) -> ReflectionResult:
        """執行反思.

        Args:
            recalled_memories: recall() 返回的記憶項目
            recalled_crystals: recall_tiered() 返回的結晶
            recalled_soul_rings: recall_soul_rings() 返回的年輪
            current_query: 使用者當前問題

        Returns:
            ReflectionResult 包含排序、矛盾、模式、時間軸、摘要
        """
        result = ReflectionResult()
        all_items: List[Dict] = []

        # 合併所有來源
        for mem in (recalled_memories or []):
            item = dict(mem)
            item.setdefault("_source", "memory")
            all_items.append(item)

        for crystal in (recalled_crystals or []):
            item = dict(crystal)
            item.setdefault("_source", "crystal")
            all_items.append(item)

        for sr in (recalled_soul_rings or []):
            item = dict(sr.get("ring", sr))
            item["_score"] = sr.get("score", 0.0)
            item.setdefault("_source", "soul_ring")
            all_items.append(item)

        if not all_items:
            result.metadata = {"total_items": 0, "query": current_query[:50]}
            return result

        # Step 1: Activation 排序
        result.ranked_memories = self._decay.rank_by_activation(all_items)

        # Step 2: 矛盾偵測
        result.contradictions = self._detect_contradictions(all_items)

        # Step 3: 模式偵測
        result.patterns = self._detect_patterns(all_items)

        # Step 4: 時間軸整理
        result.timeline = self._build_timeline(all_items)

        # Step 5: 反思摘要
        result.summary = self._build_summary(result, current_query)

        result.metadata = {
            "total_items": len(all_items),
            "active_count": len([
                m for m in result.ranked_memories
                if m.get("_activation", 0) >= -2.0
            ]),
            "contradiction_count": len(result.contradictions),
            "pattern_count": len(result.patterns),
            "query": current_query[:50],
        }

        logger.debug(
            f"MemoryReflector | items={len(all_items)} | "
            f"contradictions={len(result.contradictions)} | "
            f"patterns={len(result.patterns)}"
        )
        return result

    # ── 內部方法 ──────────────────────────────

    def _detect_contradictions(
        self, items: List[Dict]
    ) -> List[Dict[str, Any]]:
        """偵測召回記憶之間的潛在矛盾.

        策略：比對 Soul Ring 的 type 組合。
        例如：同一主題下既有 cognitive_breakthrough 又有 failure_lesson。
        """
        contradictions = []

        # 按 context 的前 50 字分組（粗略主題分組）
        topic_groups: Dict[str, List[Dict]] = {}
        for item in items:
            topic_key = item.get("context", "")[:50].strip()
            if topic_key:
                topic_groups.setdefault(topic_key, []).append(item)

        for topic, group in topic_groups.items():
            types = set(item.get("type", "") for item in group)
            for pair in CONTRADICTION_PAIRS:
                if pair[0] in types and pair[1] in types:
                    contradictions.append({
                        "topic": topic,
                        "types": list(pair),
                        "items_count": len(group),
                    })

        return contradictions

    def _detect_patterns(
        self, items: List[Dict]
    ) -> List[Dict[str, Any]]:
        """偵測重複出現的模式.

        策略：相同 type 的記憶超過閾值 → 標記為模式。
        """
        type_counts: Dict[str, int] = {}
        type_examples: Dict[str, List[str]] = {}

        for item in items:
            t = item.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
            desc = item.get("description", "")[:80]
            type_examples.setdefault(t, []).append(desc)

        patterns = []
        for t, count in type_counts.items():
            if count >= PATTERN_THRESHOLD:
                patterns.append({
                    "type": t,
                    "count": count,
                    "examples": type_examples.get(t, [])[:3],
                })

        return patterns

    def _build_timeline(
        self, items: List[Dict]
    ) -> List[Dict[str, Any]]:
        """將零散的召回按時序重組.

        Returns:
            [{"date": "2026-03-20", "items": [...], "summary": "..."}]
        """
        # 按日期分組
        date_groups: Dict[str, List[Dict]] = {}
        for item in items:
            created = item.get("created_at", "")
            day = created[:10] if len(created) >= 10 else "unknown"
            date_groups.setdefault(day, []).append(item)

        timeline = []
        for day in sorted(date_groups.keys()):
            group = date_groups[day]
            descriptions = [
                item.get("description", "")[:60]
                for item in group
            ]
            timeline.append({
                "date": day,
                "count": len(group),
                "items": descriptions,
            })

        return timeline

    def _build_summary(
        self, result: ReflectionResult, query: str
    ) -> str:
        """產出反思摘要文字.

        格式：適合注入 system prompt 的簡短文字。
        """
        parts = []

        # 模式提醒
        if result.patterns:
            for p in result.patterns[:2]:
                parts.append(
                    f"⚠️ 重複模式：{p['type']} 出現 {p['count']} 次"
                )

        # 矛盾提醒
        if result.contradictions:
            for c in result.contradictions[:1]:
                parts.append(
                    f"💡 注意：同一主題有 {' 和 '.join(c['types'])} 的記錄"
                )

        # 時間跨度
        if result.timeline and len(result.timeline) >= 2:
            first_date = result.timeline[0]["date"]
            last_date = result.timeline[-1]["date"]
            if first_date != last_date:
                parts.append(
                    f"📅 記憶跨度：{first_date} ~ {last_date}"
                )

        # 活躍記憶數
        active_count = result.metadata.get("active_count", 0)
        total = result.metadata.get("total_items", 0)
        if total > 0:
            parts.append(f"🧠 {active_count}/{total} 條記憶活躍")

        summary = " | ".join(parts)
        return summary[:MAX_REFLECTION_CHARS] if summary else ""
