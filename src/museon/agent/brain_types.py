"""Brain 共享型別定義 — L3-A2 Mixin 拆分用.

從 brain.py 提取的 dataclass，供 brain.py 各 Mixin 共用，
避免循環 import。
"""

from dataclasses import dataclass


# ═══════════════════════════════════════════════════════════════════
# 決策信號偵測（P2 重大決策先問後答）
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DecisionSignal:
    """重大決策信號 — 決策層路由用."""
    is_major: bool
    decision_type: str  # e.g., "cost-vs-quality", "speed-vs-perfection", "business-investment"
    confidence: float  # 0.0-1.0
    stakeholders_count: int  # 涉及的利益相關方數量
    impact_horizon_months: int  # 影響時間範圍（月）
    details: str  # 簡短說明

