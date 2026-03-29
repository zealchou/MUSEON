"""DARWIN — 市場規模計算（TAM/SAM/SOM）

根據產品類型、城市人口、目標角色，計算三層市場天花板。
先鋒買家 = Rogers 13.5% 早期採用者 = One Muse 火高+澤高的人群。
"""

from __future__ import annotations

from museon.darwin.storage.models import Archetype


# Rogers 擴散比例
ROGERS_INNOVATORS = 0.025       # 2.5% 發明家
ROGERS_EARLY_ADOPTERS = 0.135   # 13.5% 先鋒（早期採用者）
ROGERS_EARLY_MAJORITY = 0.34   # 34% 早期多數
ROGERS_LATE_MAJORITY = 0.34    # 34% 晚期多數
ROGERS_LAGGARDS = 0.16         # 16% 落後者


def classify_archetype_role(archetype: Archetype) -> str:
    """根據能量特徵判定原型在 Rogers 擴散中的角色

    先鋒（13.5%）= 火高（被新奇事物吸引）+ 澤高（願意主動拉攏人）
    """
    inner = archetype.inner_energy.to_dict()
    fire = inner.get("火", 0)
    lake = inner.get("澤", 0)
    sky = inner.get("天", 0)
    thunder = inner.get("雷", 0)
    earth = inner.get("地", 0)
    mountain = inner.get("山", 0)

    # 先鋒分數：火+澤為主（被新奇吸引 + 主動拉攏人）
    pioneer_score = fire * 0.4 + lake * 0.4 + sky * 0.1 + thunder * 0.1

    # 保守分數：地+山為主（重穩定 + 重累積）
    conservative_score = earth * 0.3 + mountain * 0.3 - thunder * 0.2 - fire * 0.2

    # 使用相對排序而非絕對閾值（避免基底偏移導致分類失效）
    # 先鋒 = 前 13.5%，保守 = 後 16%
    # 這裡先用分數，外部 filter_addressable_archetypes 會根據比例重新分配
    if pioneer_score > 0.8:
        return "pioneer"
    elif pioneer_score > 0.0:
        return "early_majority"
    elif conservative_score > 1.5:
        return "laggard"
    elif conservative_score > 0.5:
        return "late_majority"
    else:
        return "early_majority"


def compute_tam(
    city_population: int,
    product_type: str = "b2b_saas",
    price_ntd: float = 12000,
) -> dict:
    """計算 TAM / SAM / SOM

    Args:
        city_population: 城市總人口
        product_type: 產品類型（b2b_saas / b2c_service / b2c_product）
        price_ntd: 產品定價（台幣）

    Returns:
        {"tam": int, "sam": int, "som": int, "rationale": str}
    """
    if product_type == "b2b_saas":
        # B2B SaaS（如 DARWIN）
        # TAM = 所有企業主/創業家（人口的 ~2.5%，Rogers 創新者比例）
        # SAM = 企業主中的先鋒（13.5%，火高+澤高）= TAM × 13.5%
        # SOM = 先鋒中有預算且有需求的
        entrepreneur_ratio = ROGERS_INNOVATORS  # 2.5% 是創業家
        pioneer_of_entrepreneurs = ROGERS_EARLY_ADOPTERS  # 其中 13.5% 是先鋒
        budget_fit = max(0.10, 1.0 - price_ntd / 80000)
        need_fit = 0.40  # 有策略優化需求的

        tam = int(city_population * entrepreneur_ratio)
        sam = int(tam * pioneer_of_entrepreneurs * need_fit)
        som = int(sam * budget_fit)

        rationale = (
            f"TAM={tam:,}（{city_population:,}×創業家{entrepreneur_ratio:.1%}）"
            f"→ SAM={sam:,}（先鋒{pioneer_of_entrepreneurs:.1%}×有需求{need_fit:.0%}）"
            f"→ SOM={som:,}（預算適配{budget_fit:.0%}）"
        )

    elif product_type == "b2c_service":
        # B2C 服務（如餐廳、美業）
        pioneer_ratio = ROGERS_EARLY_ADOPTERS + ROGERS_EARLY_MAJORITY  # 前 47.5% 都可能嘗試
        price_sensitivity = max(0.1, 1.0 - price_ntd / 5000)  # B2C 價格敏感度高

        tam = city_population
        sam = int(tam * pioneer_ratio)
        som = int(sam * price_sensitivity * 0.1)  # 第一年能觸及的

        rationale = (
            f"TAM={tam:,}（全人口）"
            f"→ SAM={sam:,}（前{pioneer_ratio:.1%}願意嘗試）"
            f"→ SOM={som:,}（價格×首年觸及）"
        )

    else:  # b2c_product
        tam = city_population
        sam = int(tam * 0.3)
        som = int(sam * 0.05)
        rationale = f"TAM={tam:,} → SAM={sam:,} → SOM={som:,}"

    return {
        "tam": tam,
        "sam": sam,
        "som": som,
        "rationale": rationale,
    }


def filter_addressable_archetypes(
    archetypes: list[Archetype],
    product_type: str = "b2b_saas",
) -> list[Archetype]:
    """用排序比例分配 Rogers 角色，而非絕對閾值

    先鋒 = 火+澤最高的前 13.5%
    早期多數 = 接下來的 34%
    晚期多數 = 再接下來的 34%
    落後者 = 最後的 16%
    """
    # 計算每個原型的先鋒分數
    scores = []
    for a in archetypes:
        inner = a.inner_energy.to_dict()
        score = inner.get("火", 0) * 0.4 + inner.get("澤", 0) * 0.4 + inner.get("天", 0) * 0.1 + inner.get("雷", 0) * 0.1
        scores.append((a, score))

    # 按分數排序（高→低）
    scores.sort(key=lambda x: -x[1])

    # 按 Rogers 比例分配角色
    cumulative = 0.0
    for a, score in scores:
        cumulative += a.weight
        if cumulative <= ROGERS_EARLY_ADOPTERS:  # 前 13.5%
            a.adoption_stage = "pioneer"
        elif cumulative <= ROGERS_EARLY_ADOPTERS + ROGERS_EARLY_MAJORITY:  # 13.5-47.5%
            a.adoption_stage = "early_majority"
        elif cumulative <= ROGERS_EARLY_ADOPTERS + ROGERS_EARLY_MAJORITY + ROGERS_LATE_MAJORITY:  # 47.5-81.5%
            a.adoption_stage = "late_majority"
        else:
            a.adoption_stage = "laggard"

    # 設定可觸及性
    for a in archetypes:
        if product_type == "b2b_saas":
            if a.adoption_stage == "pioneer":
                a._addressable = True
                a._addressable_weight = 1.0
            elif a.adoption_stage == "early_majority":
                a._addressable = True
                a._addressable_weight = 0.3  # 需跨鴻溝
            else:
                a._addressable = False
                a._addressable_weight = 0.0
        else:
            a._addressable = True
            a._addressable_weight = 0.8 if a.adoption_stage != "laggard" else 0.2

    return archetypes
