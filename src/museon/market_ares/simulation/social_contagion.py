"""力量二：社會傳導 — SIR 傳染病模型變體

狀態轉移：
  unaware → aware → considering → decided → loyal
                                          ↘ resistant
"""

from __future__ import annotations

from museon.market_ares.config import SOCIAL_CONTAGION_BASE_RATE
from museon.market_ares.storage.models import Archetype

# 狀態轉移的有序列表
_STATE_ORDER = ["unaware", "aware", "considering", "decided", "loyal"]
_POSITIVE_STATES = {"decided", "loyal"}
_TERMINAL_STATES = {"loyal", "resistant"}


def _get_wind_factor(archetype: Archetype) -> float:
    """風能量（溝通接受度）：影響從 aware→considering 的轉化

    風高=容易被說服，風低=溝通無效
    """
    wind_inner = getattr(archetype.current_inner, "風", 0.0)
    # 正規化到 0.3 ~ 1.5
    return 0.3 + (wind_inner + 4) / 8 * 1.2


def _get_mountain_defense(archetype: Archetype) -> float:
    """山能量（防衛係數）：山高=不容易被動搖

    但一旦轉化就很穩定（不容易 resistant→回到 unaware）
    """
    mountain_inner = getattr(archetype.current_inner, "山", 0.0)
    # 正規化到 0.0 ~ 0.5
    return max(0.0, (mountain_inner + 4) / 8 * 0.5)


def _get_lake_spread(archetype: Archetype) -> float:
    """澤能量（傳播力）：澤高=超級傳播者"""
    lake_inner = getattr(archetype.current_inner, "澤", 0.0)
    # 正規化到 0.5 ~ 2.0
    return 0.5 + (lake_inner + 4) / 8 * 1.5


def compute_social_pressure(
    archetype: Archetype,
    all_archetypes: list[Archetype],
    topology_weights: dict[int, dict[int, float]] | None = None,
) -> float:
    """計算某原型受到的社會傳導壓力

    Args:
        archetype: 目標原型
        all_archetypes: 所有原型
        topology_weights: 影響力拓樸矩陣 {from_id: {to_id: weight}}

    Returns:
        轉化壓力值（0-1），越高越可能往下一個狀態推進
    """
    if archetype.awareness_state in _TERMINAL_STATES:
        return 0.0

    # 計算已轉化鄰居的加權比例
    converted_pressure = 0.0
    total_weight = 0.0

    for other in all_archetypes:
        if other.id == archetype.id:
            continue

        # 影響力權重
        if topology_weights and archetype.id in topology_weights:
            w = topology_weights[archetype.id].get(other.id, 0.1)
        else:
            # 無拓樸資訊時，用權重（人口佔比）作為影響力
            w = other.weight

        # 已轉化的原型的傳播力
        if other.awareness_state in _POSITIVE_STATES:
            spread_power = _get_lake_spread(other)
            converted_pressure += w * spread_power

        total_weight += w

    if total_weight > 0:
        neighbors_ratio = converted_pressure / total_weight
    else:
        neighbors_ratio = 0.0

    # 基礎轉化率 × 從眾壓力 × 風能量 × (1 - 山防衛)
    wind = _get_wind_factor(archetype)
    defense = _get_mountain_defense(archetype)

    # 雷能量高的人自我驅動轉化（不需要從眾壓力）
    thunder_inner = getattr(archetype.current_inner, "雷", 0.0)
    self_drive = max(0, thunder_inner) * 0.02

    conversion_rate = (
        SOCIAL_CONTAGION_BASE_RATE
        + self_drive  # 自我驅動
        + neighbors_ratio * 0.15  # 從眾壓力
    ) * wind * (1 - defense * 0.3)

    return min(1.0, max(0.0, conversion_rate))


def advance_state(archetype: Archetype, pressure: float, resistance_threshold: float = 0.3) -> str:
    """根據累積壓力決定是否推進到下一個狀態

    累積曝光機制：每週的壓力會累積，不是獨立判斷。
    接觸越多次，轉化的機率越高。

    Args:
        archetype: 原型
        pressure: 本週社會壓力值
        resistance_threshold: 觸發抗拒的地能量閾值

    Returns:
        新的 awareness_state
    """
    current = archetype.awareness_state

    if current in _TERMINAL_STATES:
        return current

    # 累積壓力（每週衰減 10%，但持續接觸會疊加）
    archetype.accumulated_pressure = archetype.accumulated_pressure * 0.9 + pressure
    archetype.exposure_count += 1

    # 曝光加成：接觸越多次，閾值實際上越低
    exposure_bonus = min(0.15, archetype.exposure_count * 0.005)

    # 地能量極低的人更容易轉為 resistant（匱乏感導致排斥）
    earth_inner = getattr(archetype.current_inner, "地", 0.0)
    if earth_inner < -2.0 and current in ("aware", "considering"):
        if archetype.accumulated_pressure < 0.05:
            return "resistant"

    # 有效壓力 = 累積壓力 + 曝光加成
    effective_pressure = archetype.accumulated_pressure + exposure_bonus

    idx = _STATE_ORDER.index(current) if current in _STATE_ORDER else 0

    # 每往前一步需要的累積壓力越大
    thresholds = {
        "unaware": 0.03,
        "aware": 0.12,
        "considering": 0.25,
        "decided": 0.45,
    }

    threshold = thresholds.get(current, 0.5)

    if effective_pressure >= threshold and idx < len(_STATE_ORDER) - 1:
        return _STATE_ORDER[idx + 1]

    return current
