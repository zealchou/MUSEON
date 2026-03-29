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


@dataclass
class BassParameters:
    """每個原型的個性化 Bass 參數"""
    p: float = 0.01   # 創新係數（基礎）
    q: float = 0.20   # 模仿係數（基礎）
    chasm_resistance: float = 0.0  # 鴻溝阻力（0~1）


def compute_bass_params(archetype: Archetype) -> BassParameters:
    """根據能量特徵計算個性化的 Bass p/q 參數

    p（創新係數）：
      - 火高 → p 高（被新奇事物吸引，主動嘗試）
      - 天高 → p 略高（目標明確，主動行動）
      - 地低 → p 略高（沒有包袱，敢試）

    q（模仿係數）：
      - 澤高 → q 高（願意社交傳播，也容易被社群影響）
      - 水高 → q 略高（重視關係，聽朋友推薦）
      - 山高 → q 低（保守、要看數據證據）

    鴻溝阻力：
      - 山高 + 地高 → 鴻溝寬（需要充分證據才跨越）
      - 雷低 → 鴻溝寬（不願改變認知框架）
    """
    inner = archetype.inner_energy.to_dict()
    fire = inner.get("火", 0)
    lake = inner.get("澤", 0)
    sky = inner.get("天", 0)
    thunder = inner.get("雷", 0)
    earth = inner.get("地", 0)
    mountain = inner.get("山", 0)
    water = inner.get("水", 0)
    wind = inner.get("風", 0)

    # p（創新係數）：0.005 ~ 0.08
    p_base = 0.015
    p_fire = max(0, fire) * 0.008     # 火高 → 主動嘗試
    p_sky = max(0, sky) * 0.003       # 天高 → 主動行動
    p_earth_penalty = max(0, -earth) * 0.002  # 地低 → 沒包袱（反而是正面）
    p = max(0.005, min(0.08, p_base + p_fire + p_sky + p_earth_penalty))

    # q（模仿係數）：0.05 ~ 0.50
    q_base = 0.12
    q_lake = max(0, lake) * 0.04      # 澤高 → 社交傳播
    q_water = max(0, water) * 0.02    # 水高 → 聽朋友推薦
    q_wind = max(0, wind) * 0.015     # 風高 → 溝通適應
    q_mountain_drag = max(0, mountain) * 0.03  # 山高 → 保守不輕信
    q = max(0.05, min(0.50, q_base + q_lake + q_water + q_wind - q_mountain_drag))

    # 鴻溝阻力：0 ~ 0.8
    chasm = 0.0
    if mountain > 1.5 and earth > 1.0:
        chasm += 0.3  # 保守穩定型 → 大鴻溝
    if thunder < -1.0:
        chasm += 0.2  # 不願破框 → 鴻溝更寬
    if fire < -0.5:
        chasm += 0.15  # 不追新 → 鴻溝寬
    chasm = min(0.8, chasm)

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
    """判斷市場是否已跨越鴻溝

    跨越條件：
    1. 採用率 > 15%
    2. 已有「山高」的保守型原型也開始採用
    3. 有可引用的成功案例（用 decided+loyal 的數量代理）
    """
    if adoption_ratio < 0.12:
        return False

    # 檢查是否有保守型也採用了
    conservative_adopted = sum(
        a.weight for a in archetypes
        if a.adoption_stage in ("late_majority", "laggard")
        and a.awareness_state in ("decided", "loyal")
    )

    return conservative_adopted > 0.02  # 有 2% 以上的保守者也買了
