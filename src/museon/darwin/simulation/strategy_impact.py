"""力量一：策略衝擊 — 策略向量 × 原型敏感度"""

from __future__ import annotations

from museon.darwin.config import PRIMALS, STRATEGY_SENSITIVITY_BASE
from museon.darwin.storage.models import Archetype, EnergyVector, StrategyVector


def compute_sensitivity(archetype: Archetype, primal: str) -> float:
    """原型對特定方位的敏感度

    能量越極端（正或負），對該方位的刺激反應越強烈。
    但方向不同：正能量的人是被「共鳴」放大，負能量的人是被「觸痛」放大。
    """
    inner_val = getattr(archetype.current_inner, primal, 0.0)
    outer_val = getattr(archetype.current_outer, primal, 0.0)

    # 敏感度 = 基礎值 × (1 + |能量值|的平均)
    avg_magnitude = (abs(inner_val) + abs(outer_val)) / 2
    return STRATEGY_SENSITIVITY_BASE * (1 + avg_magnitude / 4)


def apply_strategy_impact(
    archetype: Archetype,
    strategy: StrategyVector,
) -> tuple[dict[str, float], dict[str, float]]:
    """計算策略對單個原型的能量衝擊

    Returns:
        (inner_delta, outer_delta): 每個方位的能量變化量
    """
    inner_delta = {}
    outer_delta = {}

    strategy_dict = strategy.impact.to_dict()

    for primal in PRIMALS:
        stim = strategy_dict.get(primal, 0.0)
        if abs(stim) < 0.01:
            inner_delta[primal] = 0.0
            outer_delta[primal] = 0.0
            continue

        sens = compute_sensitivity(archetype, primal)
        inner_val = getattr(archetype.current_inner, primal, 0.0)

        # 正能量的人遇到正刺激 → 共鳴放大
        # 負能量的人遇到負刺激 → 恐懼加深
        # 正能量的人遇到負刺激 → 部分抵抗
        # 負能量的人遇到正刺激 → 可能被點燃或排斥
        if inner_val * stim > 0:
            # 同方向：放大
            multiplier = 1.2
        elif inner_val * stim < 0:
            # 反方向：抵抗（但不完全抵消）
            multiplier = 0.5
        else:
            multiplier = 1.0

        delta = stim * sens * multiplier

        # 內在變化較慢（權重 0.4），外在變化較快（權重 0.6）
        inner_delta[primal] = round(delta * 0.4, 4)
        outer_delta[primal] = round(delta * 0.6, 4)

    return inner_delta, outer_delta
