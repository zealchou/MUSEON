"""QualityGate — gold/silver/bronze 三級品質閘門.

依據 SIX_LAYER_MEMORY BDD Spec §4 實作：
  - gold (1.5×):   高價值洞察 → recall 加權 150%
  - silver (1.0×):  正常使用者訊息 → 基準
  - bronze (0.5×):  系統自動生成 → recall 降權 50%

評估規則（優先順序）：
  1. failure_distill → silver（特例，非 bronze）
  2. 系統來源 → bronze
  3. 晉升/取代/對話來源 → gold
  4. 含信號關鍵字 → gold
  5. < 20 字元 → bronze
  6. 預設 → silver
"""

from typing import Dict

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

QUALITY_WEIGHTS: Dict[str, float] = {
    "gold": 1.5,
    "silver": 1.0,
    "bronze": 0.5,
}

VALID_TIERS = frozenset(QUALITY_WEIGHTS.keys())

MIN_CONTENT_LENGTH = 20

# 22 個信號關鍵字 — 內容含這些詞 → gold
_SIGNAL_KEYWORDS = frozenset({
    "學到", "原來", "發現", "決定", "完成", "失敗", "做完", "教訓",
    "下次", "改進", "規劃", "目標", "策略", "解決", "結晶", "覆盤",
    "反思", "問題", "嘗試", "成功", "關鍵", "重要",
})

# 9 個系統來源 → bronze
_SYSTEM_SOURCES = frozenset({
    "system", "wee_auto", "nightly", "heartbeat",
    "auto_morphenix", "curriculum_diagnosis", "skill_forge",
    "consolidation", "auto_session",
})

# 晉升/取代/對話來源 → gold
_GOLD_SOURCES = frozenset({
    "promoted", "supersede", "chat_session",
})


# ═══════════════════════════════════════════
# Quality Assessment
# ═══════════════════════════════════════════


def assess_quality(content: str, source: str = "") -> str:
    """評估記憶品質等級.

    Args:
        content: 記憶內容
        source: 記憶來源標記

    Returns:
        "gold" | "silver" | "bronze"
    """
    # 1. failure_distill 特例 → silver（非 bronze）
    if source == "failure_distill":
        return "silver"

    # 2. 系統來源 → bronze
    if source in _SYSTEM_SOURCES:
        return "bronze"

    # 3. 晉升/取代/對話來源 → gold
    if source in _GOLD_SOURCES:
        return "gold"

    # 4. 含信號關鍵字 → gold
    if any(kw in content for kw in _SIGNAL_KEYWORDS):
        return "gold"

    # 5. 太短 → bronze
    if len(content.strip()) < MIN_CONTENT_LENGTH:
        return "bronze"

    # 6. 預設 → silver
    return "silver"


def apply_weight(similarity: float, quality_tier: str) -> float:
    """品質加權：similarity × quality_weight.

    Args:
        similarity: TF-IDF 相似度分數
        quality_tier: "gold" | "silver" | "bronze"

    Returns:
        加權後的分數
    """
    weight = QUALITY_WEIGHTS.get(quality_tier, 1.0)
    return similarity * weight
