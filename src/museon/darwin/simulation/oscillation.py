"""力量三：能量擺盪與反轉 — 阻尼振盪模型

核心法則：能量越偏離基底，反轉壓力越大。
±4 極值時反轉壓力最強。
反轉週期：2 週 ~ 3 個月。
"""

from __future__ import annotations

from museon.darwin.config import (
    ENERGY_MAX,
    ENERGY_MIN,
    OSCILLATION_DAMPING,
    OSCILLATION_K,
    PRIMALS,
    REVERSAL_THRESHOLD,
)
from museon.darwin.storage.models import EnergyVector


def compute_oscillation_delta(
    current: float,
    baseline: float,
    k: float = OSCILLATION_K,
    damping: float = OSCILLATION_DAMPING,
) -> float:
    """計算單一方位的擺盪反轉力

    Args:
        current: 當前能量值
        baseline: 基底能量值（地區平均）
        k: 彈性係數
        damping: 阻尼係數

    Returns:
        能量變化量（負值=往回拉）
    """
    displacement = current - baseline

    # 非線性回復力：越極端，反轉越強
    # F = -k * x * |x|（二次方回復力）
    restoring = -k * displacement * abs(displacement)

    # 額外的極值懲罰：接近 ±4 時急劇增大
    if abs(current) > REVERSAL_THRESHOLD:
        overshoot = abs(current) - REVERSAL_THRESHOLD
        penalty = -0.2 * overshoot * (1 if current > 0 else -1)
        restoring += penalty

    # 阻尼衰減（模擬摩擦力，讓震盪最終收斂）
    restoring *= (1 - damping)

    return round(restoring, 4)


def apply_oscillation(
    current_energy: EnergyVector,
    baseline_energy: EnergyVector,
) -> dict[str, float]:
    """計算整個能量向量的擺盪反轉

    Args:
        current_energy: 當前能量向量
        baseline_energy: 基底能量向量

    Returns:
        各方位的能量變化量
    """
    delta = {}
    current_dict = current_energy.to_dict()
    baseline_dict = baseline_energy.to_dict()

    for primal in PRIMALS:
        cur = current_dict.get(primal, 0.0)
        base = baseline_dict.get(primal, 0.0)
        delta[primal] = compute_oscillation_delta(cur, base)

    return delta


def clamp_energy(value: float) -> float:
    """將能量值裁剪到有效範圍"""
    return max(ENERGY_MIN, min(ENERGY_MAX, value))
