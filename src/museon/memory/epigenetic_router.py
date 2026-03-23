"""EpigeneticRouter — 表觀遺傳路由器（MAGMA 式多圖遍歷）.

Project Epigenesis 迭代 6：情境驅動的記憶啟動。

DNA 隱喻：不改變記憶本身，改變的是「什麼記憶在什麼時候被表達」。
像 DNA 的甲基化開關——同一段基因在不同環境下被不同地表達。

MAGMA 四張正交圖：
  1. semantic：語義相關 → Qdrant 向量搜索
  2. temporal：時間相關 → Changelog + PulseDB + date_range
  3. causal：因果相關 → Soul Ring 因果鏈
  4. entity：實體相關 → 使用者/外部 Anima 交叉

路由決策：分析 query 的意圖，決定走哪張圖（可多張並行）。

消費者：brain.py _build_memory_inject()
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from museon.memory.memory_reflector import MemoryReflector, ReflectionResult

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 意圖分類
# ═══════════════════════════════════════════

# 時間意圖關鍵詞
TEMPORAL_KEYWORDS = [
    "上次", "最近", "之前", "以前", "過去", "歷史", "一個月前",
    "三個月前", "去年", "曾經", "那時候", "當時", "以來",
    "什麼時候", "幾天前", "多久", "趨勢", "變化",
    "last time", "recently", "before", "history", "trend",
]

# 因果意圖關鍵詞
CAUSAL_KEYWORDS = [
    "為什麼", "原因", "因為", "所以", "導致", "根因",
    "教訓", "失敗", "學到", "結果", "影響", "後果",
    "怎麼會", "怎麼回事", "發生了什麼",
    "why", "because", "lesson", "cause", "result",
]

# 實體意圖關鍵詞
ENTITY_KEYWORDS = [
    "跟", "和", "與", "客戶", "朋友", "老闆",
    "他", "她", "他們", "誰", "那個人",
    "A客戶", "B客戶",
]

# 經驗回顧意圖關鍵詞
EXPERIENCE_KEYWORDS = [
    "經驗", "做過", "處理過", "遇過", "試過",
    "成功", "失敗", "突破", "里程碑", "成長",
    "日記", "年輪", "記錄", "回顧", "反思",
]


@dataclass
class QueryIntent:
    """查詢意圖分類結果."""
    needs_semantic: bool = True    # 永遠啟用（baseline）
    needs_temporal: bool = False   # 需要時間維度
    needs_causal: bool = False     # 需要因果維度
    needs_entity: bool = False     # 需要實體維度
    needs_experience: bool = False  # 需要經驗回顧
    confidence: float = 0.5        # 分類信心度
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class MemoryActivation:
    """表觀遺傳路由的輸出."""
    # 啟動的記憶（已排序 + 反思）
    memories: List[Dict[str, Any]] = field(default_factory=list)

    # 反思結果
    reflection: Optional[ReflectionResult] = None

    # 啟動理由
    rationale: str = ""

    # 使用了哪些圖
    graphs_used: List[str] = field(default_factory=list)

    # 預判式建議（Proactive Hint）
    proactive_hint: Optional[str] = None

    # 元資料
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════
# EpigeneticRouter
# ═══════════════════════════════════════════

class EpigeneticRouter:
    """表觀遺傳路由器 — 情境驅動的記憶啟動.

    不是「搜索最相似的記憶」，
    而是「判斷此刻需要什麼類型的記憶」。
    """

    def __init__(
        self,
        reflector: Optional[MemoryReflector] = None,
        # 下游服務（由 brain.py 注入）
        memory_manager=None,      # MemoryManager（六層記憶）
        diary_store=None,         # DiaryStore（Soul Ring）
        knowledge_lattice=None,   # KnowledgeLattice（結晶）
        anima_changelog=None,     # AnimaChangelog（使用者變化歷史）
        pulse_db=None,            # PulseDB（八元素歷史）
    ) -> None:
        self._reflector = reflector or MemoryReflector()
        self._memory_manager = memory_manager
        self._diary_store = diary_store
        self._knowledge_lattice = knowledge_lattice
        self._anima_changelog = anima_changelog
        self._pulse_db = pulse_db

    def activate(
        self,
        query: str,
        anima_user: Optional[Dict] = None,
        session_context: Optional[Dict] = None,
    ) -> MemoryActivation:
        """情境感知的記憶啟動.

        Args:
            query: 使用者問題
            anima_user: 使用者 ANIMA（可選，用於實體圖）
            session_context: 工作階段上下文（可選）

        Returns:
            MemoryActivation 包含啟動的記憶 + 反思 + 理由
        """
        result = MemoryActivation()

        # Step 1: 意圖分類
        intent = self.classify_intent(query)

        # Step 2: 多圖遍歷
        all_memories = []
        all_crystals = []
        all_soul_rings = []
        graphs_used = ["semantic"]  # semantic 永遠啟用

        # 2a: Semantic（語義圖 — baseline）
        semantic_hits = self._traverse_semantic(query)
        all_memories.extend(semantic_hits)

        # 2b: Temporal（時間圖）
        if intent.needs_temporal:
            graphs_used.append("temporal")
            temporal_hits = self._traverse_temporal(query)
            all_soul_rings.extend(temporal_hits)

        # 2c: Causal（因果圖）
        if intent.needs_causal or intent.needs_experience:
            graphs_used.append("causal")
            causal_hits = self._traverse_causal(query)
            all_soul_rings.extend(causal_hits)

        # 2d: Entity（實體圖）
        if intent.needs_entity:
            graphs_used.append("entity")
            # 實體圖預留——需要 ExternalAnimaManager 接入

        # 2e: Crystal recall（如果有 lattice）
        crystal_hits = self._traverse_crystals(query)
        all_crystals.extend(crystal_hits)

        # Step 3: Reflect（反思）
        reflection = self._reflector.reflect(
            recalled_memories=all_memories,
            recalled_crystals=all_crystals,
            recalled_soul_rings=all_soul_rings,
            current_query=query,
        )

        # Step 4: 組裝結果
        result.memories = reflection.ranked_memories
        result.reflection = reflection
        result.graphs_used = graphs_used
        result.rationale = self._build_rationale(intent, graphs_used)
        result.metadata = {
            "intent": {
                "semantic": intent.needs_semantic,
                "temporal": intent.needs_temporal,
                "causal": intent.needs_causal,
                "entity": intent.needs_entity,
                "experience": intent.needs_experience,
            },
            "matched_keywords": intent.matched_keywords,
            "total_memories": len(all_memories),
            "total_crystals": len(all_crystals),
            "total_soul_rings": len(all_soul_rings),
        }

        logger.debug(
            f"EpigeneticRouter | graphs={graphs_used} | "
            f"memories={len(all_memories)} | crystals={len(all_crystals)} | "
            f"soul_rings={len(all_soul_rings)}"
        )
        return result

    # ── 意圖分類 ──────────────────────────────

    def classify_intent(self, query: str) -> QueryIntent:
        """分析查詢意圖，決定走哪些圖.

        純關鍵詞匹配（不呼叫 LLM），保持低延遲。
        """
        intent = QueryIntent()
        matched = []

        for kw in TEMPORAL_KEYWORDS:
            if kw in query:
                intent.needs_temporal = True
                matched.append(kw)

        for kw in CAUSAL_KEYWORDS:
            if kw in query:
                intent.needs_causal = True
                matched.append(kw)

        for kw in ENTITY_KEYWORDS:
            if kw in query:
                intent.needs_entity = True
                matched.append(kw)

        for kw in EXPERIENCE_KEYWORDS:
            if kw in query:
                intent.needs_experience = True
                matched.append(kw)

        intent.matched_keywords = list(set(matched))

        # 信心度：匹配越多關鍵詞越高
        total_matches = len(intent.matched_keywords)
        if total_matches >= 3:
            intent.confidence = 0.9
        elif total_matches >= 1:
            intent.confidence = 0.7
        else:
            intent.confidence = 0.5  # 只走 semantic baseline

        return intent

    # ── 圖遍歷 ──────────────────────────────────

    def _traverse_semantic(self, query: str) -> List[Dict]:
        """語義圖遍歷 — Qdrant 向量搜索."""
        if not self._memory_manager:
            return []
        try:
            return self._memory_manager.recall(query, limit=10)
        except Exception as e:
            logger.debug(f"Semantic traverse failed: {e}")
            return []

    def _traverse_temporal(self, query: str) -> List[Dict]:
        """時間圖遍歷 — Soul Ring 日期檢索 + Changelog."""
        results = []

        # Soul Ring 語義搜索（帶時間語境）
        if self._diary_store:
            try:
                hits = self._diary_store.recall_soul_rings(query, limit=5)
                results.extend(hits)
            except Exception as e:
                logger.debug(f"Temporal soul_ring recall failed: {e}")

        # Changelog 變化歷史（如果問到趨勢/變化）
        if self._anima_changelog:
            try:
                trend_keywords = ["趨勢", "變化", "成長", "演化", "trend"]
                if any(kw in query for kw in trend_keywords):
                    summary = self._anima_changelog.get_evolution_summary(months=3)
                    if summary.get("total_changes", 0) > 0:
                        results.append({
                            "_source": "changelog",
                            "type": "evolution_summary",
                            "description": f"使用者演化摘要：{summary.get('period', '')}",
                            "context": str(summary.get("primals_trend", {}))[:200],
                            "impact": f"共 {summary['total_changes']} 次變化",
                            "created_at": "",
                        })
            except Exception as e:
                logger.debug(f"Temporal changelog failed: {e}")

        return results

    def _traverse_causal(self, query: str) -> List[Dict]:
        """因果圖遍歷 — Soul Ring 搜索（偏重 failure_lesson + value_calibration）."""
        if not self._diary_store:
            return []
        try:
            # 因果查詢偏重教訓和校準
            hits = self._diary_store.recall_soul_rings(query, limit=5)
            # 加權：failure_lesson 和 value_calibration 排前面
            causal_types = {"failure_lesson", "value_calibration"}
            causal = [h for h in hits if h.get("ring", {}).get("type") in causal_types]
            others = [h for h in hits if h.get("ring", {}).get("type") not in causal_types]
            return causal + others
        except Exception as e:
            logger.debug(f"Causal traverse failed: {e}")
            return []

    def _traverse_crystals(self, query: str) -> List[Dict]:
        """結晶圖遍歷."""
        if not self._knowledge_lattice:
            return []
        try:
            crystals = self._knowledge_lattice.recall_tiered(
                context=query, max_push=5
            )
            if isinstance(crystals, str):
                # recall_tiered 可能返回格式化字串
                return []
            return crystals if isinstance(crystals, list) else []
        except Exception as e:
            logger.debug(f"Crystal traverse failed: {e}")
            return []

    # ── 輔助方法 ──────────────────────────────

    def _build_rationale(
        self, intent: QueryIntent, graphs_used: List[str]
    ) -> str:
        """建構啟動理由."""
        parts = []
        if intent.needs_temporal:
            parts.append("時間維度（因問題涉及過去/趨勢）")
        if intent.needs_causal:
            parts.append("因果維度（因問題涉及原因/教訓）")
        if intent.needs_entity:
            parts.append("實體維度（因問題涉及特定人物）")
        if intent.needs_experience:
            parts.append("經驗維度（因問題涉及過往經歷）")

        if parts:
            return f"記憶啟動：{' + '.join(parts)}"
        return "記憶啟動：語義搜索（baseline）"
