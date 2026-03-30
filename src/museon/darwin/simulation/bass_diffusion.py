"""DARWIN — Bass 擴散模型

Frank Bass (1969) 新產品擴散模型，替換 SIR 傳染病模型。

核心公式：
  f(t) = [p + q × F(t)] × [1 - F(t)]

  p = 創新係數（被策略/廣告直接觸及，個人不受口碑影響的採用率）
  q = 模仿係數（被口碑/社會影響帶動的採用率）
  F(t) = 累積採用比例（0~1）
  1-F(t) = 剩餘潛在市場

特性：
  - S 曲線自然湧現
  - 天花板 = TAM（永遠不會超過 100%）
  - p 決定起步速度，q 決定加速斜率
  - 峰值時間 = -ln(p/q) / (p+q)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from museon.darwin.storage.models import Archetype


# 避免循環匯入：用 TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from museon.darwin.simulation.product_profile import ProductProfile


@dataclass
class BassParameters:
    """每個原型的個性化 Bass 參數"""
    p: float = 0.01   # 創新係數（基礎）
    q: float = 0.20   # 模仿係數（基礎）
    chasm_resistance: float = 0.0  # 鴻溝阻力（0~1）


def compute_bass_params(
    archetype: Archetype,
    profile: "ProductProfile | None" = None,
) -> BassParameters:
    """根據 One Muse 八方位能量計算個性化的 Bass p/q 參數

    p（創新係數）= f(火能量, 天能量, 雷能量)
      - 火高 → p 高（被新奇事物吸引，主動嘗試）
      - 天高 → p 略高（目標明確，主動行動）
      - 雷高 → p 略高（洞察力強，願意破框）

    q（模仿係數）= f(澤能量, 水能量, 風能量)
      - 澤高 → q 高（願意社交傳播，也容易被社群影響）
      - 水高 → q 略高（重視關係，聽朋友推薦）
      - 風高 → q 略高（善於溝通協商，易受人脈影響）

    chasm_resistance = f(山能量, 地能量)
      - 山高 → 要看數據證據才行動，鴻溝寬
      - 地高 → 保守穩定，不輕易改變，鴻溝寬
      - 雷低 → 不願破框，鴻溝更寬

    profile（可選）= 品類修正因子，套用在能量計算結果上
    """
    inner = archetype.inner_energy.to_dict()

    # p（創新係數）：0.005 ~ 0.06
    fire = inner.get("火", 0)
    sky = inner.get("天", 0)
    thunder = inner.get("雷", 0)
    p_base = 0.01
    p = p_base + max(0, fire) * 0.006 + max(0, sky) * 0.003 + max(0, thunder) * 0.003
    p = max(0.005, min(0.06, p))

    # q（模仿係數）：0.03 ~ 0.45
    lake = inner.get("澤", 0)
    water = inner.get("水", 0)
    wind = inner.get("風", 0)
    q_base = 0.08
    q = q_base + max(0, lake) * 0.04 + max(0, water) * 0.02 + max(0, wind) * 0.02
    q = max(0.03, min(0.45, q))

    # chasm_resistance：0 ~ 0.7（保守程度）
    mountain = inner.get("山", 0)
    earth = inner.get("地", 0)
    chasm = 0.0
    if mountain > 1.5:
        chasm += 0.25  # 山高 → 要充分證據才跨越
    if earth > 1.5:
        chasm += 0.15  # 地高 → 保守穩定，不輕易改變
    if thunder < -1.0:
        chasm += 0.15  # 雷低 → 不願破框
    chasm = min(0.7, chasm)

    # ── 品類修正（ProductProfile）──
    if profile is not None:
        # 基礎倍率
        p *= profile.p_multiplier
        q *= profile.q_multiplier

        # 關鍵方位共振加成：該方位能量高 → p/q 額外加成
        for primal in profile.critical_primals:
            val = inner.get(primal, 0)
            if val > 1.0:
                p *= 1.0 + val * 0.05
                q *= 1.0 + val * 0.03

        # 輔助方位小加成
        for primal in profile.boost_primals:
            val = inner.get(primal, 0)
            if val > 1.0:
                p *= 1.0 + val * 0.02
                q *= 1.0 + val * 0.015

        # 鴻溝寬度修正
        chasm *= profile.chasm_width

        # 重新 clamp
        p = max(0.002, min(0.15, p))
        q = max(0.01, min(0.60, q))
        chasm = min(0.85, chasm)

    return BassParameters(p=round(p, 4), q=round(q, 4), chasm_resistance=round(chasm, 2))


def bass_adoption_probability(
    params: BassParameters,
    cumulative_adoption_ratio: float,
    is_past_chasm: bool = False,
) -> float:
    """計算本週的採用機率

    Args:
        params: 個性化 Bass 參數
        cumulative_adoption_ratio: 目前的累積採用比例（0~1）
        is_past_chasm: 市場是否已跨越鴻溝

    Returns:
        本週的採用機率（0~1）
    """
    remaining = 1.0 - cumulative_adoption_ratio

    if remaining <= 0.001:
        return 0.0

    # Bass 核心公式
    hazard_rate = params.p + params.q * cumulative_adoption_ratio

    # 鴻溝效應：在 15-20% 採用率時，如果還沒跨越鴻溝，阻力最大
    if not is_past_chasm and 0.10 < cumulative_adoption_ratio < 0.35:
        chasm_drag = params.chasm_resistance * (1.0 - abs(cumulative_adoption_ratio - 0.20) / 0.15)
        hazard_rate *= (1.0 - chasm_drag)

    adoption_prob = hazard_rate * remaining

    # 週度轉換
    # Bass 原始參數是年度尺度，我們的模擬是 52 週（1 年）
    # 為了讓 S 曲線在 52 週內完整展開，直接用 hazard_rate 作為週度機率
    # hazard_rate 本身就是 0~0.5 的合理範圍
    weekly_prob = adoption_prob  # 不除，直接用

    return max(0.0, min(0.35, weekly_prob))


def is_chasm_crossed(
    archetypes: list[Archetype],
    adoption_ratio: float,
) -> bool:
    """判斷市場是否已跨越鴻溝（One Muse 64 原型版）

    跨越條件：
    1. 採用率 > 12%
    2. 已有「山高或地高」的保守型原型也開始採用
       （山能量 > 1.5 或 地能量 > 1.5 = 保守型）
    3. 有可引用的成功案例（用 decided+loyal 的數量代理）
    """
    if adoption_ratio < 0.12:
        return False

    # 在 64 原型中，保守型 = 山能量高或地能量高的原型
    conservative_adopted = sum(
        a.weight for a in archetypes
        if (
            a.inner_energy.to_dict().get("山", 0) > 1.5
            or a.inner_energy.to_dict().get("地", 0) > 1.5
        )
        and a.awareness_state in ("decided", "loyal")
    )

    return conservative_adopted > 0.02  # 有 2% 以上的保守者也買了
