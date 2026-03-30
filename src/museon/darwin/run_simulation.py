"""
run_simulation.py — DARWIN 端到端模擬入口（One Muse 八方位 64 原型版）

流程：選區 → 真實政府數據 → 能量向量 → 64 原型生成 → 52 週模擬 → 結果輸出

64 原型 = 8 內在主導 × 8 外在主導（One Muse 八方位笛卡兒積）

公開 API：
  prepare_simulation(district_name, ...)
      → dict（含 energy、coverage、tam、archetypes，可直接餵給 SimulationEngine）
  run_real_data_simulation(district_name, strategy_config, ...)
      → dict（含 52 週模擬快照與最終狀態）
"""

from __future__ import annotations

import copy
import logging
import math
import random
from pathlib import Path
from typing import Any

from museon.darwin.config import ENERGY_MAX, ENERGY_MIN, PRIMALS
from museon.darwin.crawler.data_loader import _load_population_density
from museon.darwin.crawler.indicator_builder import (
    build_benchmarks,
    build_district_indicators,
    get_coverage_report,
)
from museon.darwin.mapping.energy_mapper import compute_region_energy
from museon.darwin.storage.models import (
    Archetype,
    EnergyVector,
    StrategyVector,
    WeeklySnapshot,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# One Muse 對軸定義
# ──────────────────────────────────────────────────────────────

OPPOSITE_AXIS: dict[str, str] = {
    "天": "地", "地": "天",
    "風": "雷", "雷": "風",
    "火": "水", "水": "火",
    "山": "澤", "澤": "山",
}

# ──────────────────────────────────────────────────────────────
# 購買動機 & 抗拒因子（從方位推導，不寫死在個別原型）
# ──────────────────────────────────────────────────────────────

PRIMAL_PURCHASE_TRIGGERS: dict[str, list[str]] = {
    "天": ["vision", "mission", "leadership", "purpose"],
    "風": ["recommendation", "partnership", "negotiation", "peer_advice"],
    "水": ["relationship", "trust", "family_approval", "care"],
    "山": ["evidence", "reviews", "certification", "long_term_value"],
    "地": ["roi", "stability", "value_for_money", "asset_building"],
    "雷": ["insight", "personal_growth", "awareness", "breakthrough"],
    "火": ["novelty", "trend", "experience", "excitement"],
    "澤": ["brand", "community", "social_proof", "identity"],
}

PRIMAL_RESISTANCE_TRIGGERS: dict[str, list[str]] = {
    "天": ["lack_of_vision", "no_clear_direction"],
    "風": ["poor_communication", "no_referral"],
    "水": ["no_trust", "isolation"],
    "山": ["no_evidence", "unproven"],
    "地": ["too_expensive", "financial_risk"],
    "雷": ["too_conventional", "boring"],
    "火": ["nothing_new", "stale"],
    "澤": ["no_community", "no_brand"],
}

# ──────────────────────────────────────────────────────────────
# 內部工具
# ──────────────────────────────────────────────────────────────

def _normalize_district_name(name: str) -> str:
    """統一「台」→「臺」，去掉多餘空白。"""
    return name.replace("台", "臺").strip().replace(" ", "").replace("\u3000", "")


def _clamp(lo: float, hi: float, v: float) -> float:
    """裁剪到 [lo, hi] 範圍。"""
    return max(lo, min(hi, v))


# ──────────────────────────────────────────────────────────────
# 64 原型生成核心邏輯
# ──────────────────────────────────────────────────────────────

def _create_archetype_energy(
    inner_dominant: str,
    outer_dominant: str,
    region_inner: EnergyVector,
    region_outer: EnergyVector,
    rng: random.Random,
) -> tuple[EnergyVector, EnergyVector]:
    """
    以區域能量為基底，生成特定內在+外在主導方位的能量向量。

    規則：
    1. 以區域能量為基底
    2. 內在主導方位 +2.0（這個人的內在驅力）
    3. 外在主導方位 +2.0（這個人的行為表現）
    4. 對軸方位 -1.0（能量守恆：某方位高，對面就低）
    5. 加少量隨機擾動 ±0.3（個體差異）
    6. clamp 到 [-4, +4]
    """
    inner_base = region_inner.to_dict()
    outer_base = region_outer.to_dict()

    inner_d: dict[str, float] = {}
    outer_d: dict[str, float] = {}

    for primal in PRIMALS:
        # 隨機擾動 ±0.3
        jitter_i = rng.gauss(0, 0.3)
        jitter_o = rng.gauss(0, 0.3)
        inner_d[primal] = inner_base.get(primal, 0.0) + jitter_i
        outer_d[primal] = outer_base.get(primal, 0.0) + jitter_o

    # 內在主導：+2.0，對軸：-1.0
    inner_d[inner_dominant] = inner_d.get(inner_dominant, 0.0) + 2.0
    inner_opposite = OPPOSITE_AXIS[inner_dominant]
    inner_d[inner_opposite] = inner_d.get(inner_opposite, 0.0) - 1.0

    # 外在主導：+2.0，對軸：-1.0
    outer_d[outer_dominant] = outer_d.get(outer_dominant, 0.0) + 2.0
    outer_opposite = OPPOSITE_AXIS[outer_dominant]
    outer_d[outer_opposite] = outer_d.get(outer_opposite, 0.0) - 1.0

    # clamp 到 [-4, +4]
    inner_clamped = {p: _clamp(ENERGY_MIN, ENERGY_MAX, v) for p, v in inner_d.items()}
    outer_clamped = {p: _clamp(ENERGY_MIN, ENERGY_MAX, v) for p, v in outer_d.items()}

    return EnergyVector.from_dict(inner_clamped), EnergyVector.from_dict(outer_clamped)


def _compute_archetype_weight(
    inner_dominant: str,
    outer_dominant: str,
    region_inner: EnergyVector,
    region_outer: EnergyVector,
    all_weights: list[float],
    temperature: float = 2.0,
) -> float:
    """
    以 softmax 計算原型在此區域的人口分布 weight。

    原理：區域澤能量高 → 澤主導的原型在這個區的人更多
    similarity = region_inner[inner_dominant] + region_outer[outer_dominant]
    weight = exp(similarity / temperature) / sum(all exp)
    """
    inner_dict = region_inner.to_dict()
    outer_dict = region_outer.to_dict()
    similarity = inner_dict.get(inner_dominant, 0.0) + outer_dict.get(outer_dominant, 0.0)
    return math.exp(similarity / temperature)


def infer_adoption_stage(inner_dominant: str, outer_dominant: str) -> str:
    """從主導方位推導 Rogers 分類（用於顯示，不影響計算）"""
    if inner_dominant in ("火", "澤") and outer_dominant in ("火", "澤"):
        return "innovator"  # 純先鋒：火+澤雙主導
    elif inner_dominant in ("火", "澤") or outer_dominant in ("火", "澤"):
        return "early_adopter"  # 有先鋒特質
    elif inner_dominant in ("天", "風") or outer_dominant in ("天", "風"):
        return "early_adopter"  # 目標+溝通導向
    elif inner_dominant in ("地", "山") and outer_dominant not in ("水", "雷"):
        return "early_majority"  # 穩健型
    elif inner_dominant in ("水", "雷") or outer_dominant in ("水", "雷"):
        return "late_majority"  # 關係+覺察導向
    else:
        return "early_majority"


def _compute_influence_network(archetypes: list[Archetype]) -> None:
    """
    基於能量相似度建立影響網絡。

    規則：
    1. 只有能量距離 < INFLUENCE_THRESHOLD 的原型能互相影響（有界信任）
    2. 澤外在主導的原型有更大的影響範圍（社群力）
    3. influence_targets 用 id 列表儲存
    """
    INFLUENCE_THRESHOLD = 4.0

    # 建立 id → archetype 映射
    id_to_arch = {a.id: a for a in archetypes}

    # 預先計算各原型的主導方位資訊（從 name 解析，格式：inner_outer）
    # name 格式：{inner}_{outer}（來自 _build_archetypes）
    outer_dominant_map: dict[int, str] = {}
    for a in archetypes:
        parts = a.name.split("_")
        if len(parts) == 2:
            outer_dominant_map[a.id] = parts[1]

    for a in archetypes:
        a.influence_targets = []
        a.influenced_by = []

    for i, arch_a in enumerate(archetypes):
        a_inner = arch_a.inner_energy.to_dict()
        for j, arch_b in enumerate(archetypes):
            if i == j:
                continue
            b_inner = arch_b.inner_energy.to_dict()
            # 計算能量距離（L2）
            distance = math.sqrt(sum(
                (a_inner.get(p, 0.0) - b_inner.get(p, 0.0)) ** 2
                for p in PRIMALS
            ))
            if distance < INFLUENCE_THRESHOLD:
                arch_a.influence_targets.append(arch_b.id)
                arch_b.influenced_by.append(arch_a.id)


def _build_archetypes(
    inner_vector: EnergyVector,
    outer_vector: EnergyVector,
    tam: int,
    district_name: str = "",
) -> list[Archetype]:
    """
    根據區域基準能量向量生成 64 個 Archetype（8×8 笛卡兒積）。

    每個原型 = 一種「內在主導 + 外在主導」的能量組合。
    weight 由 softmax(region_similarity) 決定，反映此區人口的真實分布。

    seed 以 district_name 的 hash 固定，確保結果可重現。
    """
    # 以地區名稱固定 seed，確保可重現
    seed = hash(district_name) % (2 ** 32)
    rng = random.Random(seed)

    # ── Phase 1：計算所有 64 組合的 raw softmax scores ──
    raw_scores: list[tuple[str, str, float]] = []
    for inner_dom in PRIMALS:
        for outer_dom in PRIMALS:
            inner_dict = inner_vector.to_dict()
            outer_dict = outer_vector.to_dict()
            similarity = inner_dict.get(inner_dom, 0.0) + outer_dict.get(outer_dom, 0.0)
            raw_scores.append((inner_dom, outer_dom, math.exp(similarity / 2.0)))

    total_score = sum(s for _, _, s in raw_scores)

    # ── Phase 2：生成 64 個原型 ──
    archetypes: list[Archetype] = []
    archetype_id = 0

    for idx, (inner_dom, outer_dom, raw_score) in enumerate(raw_scores):
        archetype_id += 1
        weight = raw_score / total_score  # 正規化後的 weight

        # 生成能量向量
        ind_inner, ind_outer = _create_archetype_energy(
            inner_dominant=inner_dom,
            outer_dominant=outer_dom,
            region_inner=inner_vector,
            region_outer=outer_vector,
            rng=rng,
        )

        # 推導 adoption_stage
        adoption_stage = infer_adoption_stage(inner_dom, outer_dom)

        # 購買動機 = 主導方位的 triggers
        purchase_triggers = list(PRIMAL_PURCHASE_TRIGGERS[inner_dom])
        # 補充外在主導的 triggers（去重，最多取 2 個）
        for t in PRIMAL_PURCHASE_TRIGGERS[outer_dom]:
            if t not in purchase_triggers:
                purchase_triggers.append(t)
                if len(purchase_triggers) >= 6:
                    break

        # 抗拒因子 = 對軸方位的 triggers（弱點）
        inner_weak = OPPOSITE_AXIS[inner_dom]
        outer_weak = OPPOSITE_AXIS[outer_dom]
        resistance_triggers = list(PRIMAL_RESISTANCE_TRIGGERS[inner_weak])
        for t in PRIMAL_RESISTANCE_TRIGGERS[outer_weak]:
            if t not in resistance_triggers:
                resistance_triggers.append(t)

        # 人口數（依 weight 比例分配）
        population = max(0, round(tam * weight))

        a = Archetype(
            id=archetype_id,
            name=f"{inner_dom}_{outer_dom}",
            description=f"內在{inner_dom}外在{outer_dom}",
            weight=round(weight, 6),
            inner_energy=ind_inner,
            outer_energy=ind_outer,
            adoption_stage=adoption_stage,
            purchase_triggers=purchase_triggers,
            resistance_triggers=resistance_triggers,
            influence_targets=[],  # 稍後由 _compute_influence_network 填入
            influenced_by=[],
        )
        a.population = population  # type: ignore[attr-defined]
        archetypes.append(a)

    # ── Phase 3：建立影響網絡 ──
    _compute_influence_network(archetypes)

    return archetypes


def _build_strategy_vector(strategy_config: dict) -> StrategyVector:
    """
    將 strategy_config dict 轉換為 StrategyVector。

    strategy_config 格式：
      {
        "name": str,
        "target_primals": list[str],   # 主打方位，e.g. ["澤", "風"]
        "intensity": float,            # 0-1，策略強度
        "channels": list[str],         # 渠道標籤（目前存入 specific）
      }
    """
    intensity = float(strategy_config.get("intensity", 0.7))
    target_primals = strategy_config.get("target_primals", [])
    channels = strategy_config.get("channels", [])
    name = strategy_config.get("name", "自訂策略")

    impact_dict = {p: 0.0 for p in PRIMALS}
    for primal in target_primals:
        if primal in impact_dict:
            impact_dict[primal] = round(intensity * ENERGY_MAX, 2)

    return StrategyVector(
        impact=EnergyVector.from_dict(impact_dict),
        specific=f"{name} | 渠道：{', '.join(channels)}",
        measurable="採用率",
        achievable=f"強度 {intensity:.0%}",
        relevant="One Muse 八方位策略",
        time_bound="52 週",
    )


def _get_population(raw_data_dir: str, district_name: str) -> int | None:
    """從 population_density 檔案取得該區實際人口數。"""
    base = Path(raw_data_dir)
    try:
        pop_data = _load_population_density(base)
        normalized_name = _normalize_district_name(district_name)
        # 先精確匹配
        if normalized_name in pop_data:
            return int(pop_data[normalized_name].get("people_total", 0))
        # 台/臺 都試
        alt_name = district_name.replace("臺", "台")
        if alt_name in pop_data:
            return int(pop_data[alt_name].get("people_total", 0))
        # 模糊匹配（包含關係）
        for sid, info in pop_data.items():
            if normalized_name in sid or sid in normalized_name:
                return int(info.get("people_total", 0))
    except Exception as e:
        logger.warning(f"無法取得 {district_name} 人口數：{e}")
    return None


def _compute_tam(population: int | None, tam_override: int | None) -> int:
    """
    TAM 計算：
    - 若 tam_override 有值 → 直接用
    - 否則：人口 × 2.5%（創業家比例）× 13.5%（先鋒比例）= 首批可能買家
    """
    if tam_override is not None:
        return tam_override
    if population is not None and population > 0:
        tam = int(population * 0.025 * 0.135)
        return max(tam, 10)  # 至少 10 人，避免太小
    # 無人口數時用預設值
    logger.warning("無法取得人口數，使用預設 TAM=500")
    return 500


# ──────────────────────────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────────────────────────

def prepare_simulation(
    district_name: str,
    raw_data_dir: str = "data/darwin/raw_data",
    places_cache: str | None = "data/darwin/raw_data/places_cache.json",
    tam: int | None = None,
) -> dict:
    """
    準備模擬所需的所有元素（不跑模擬引擎）。

    Args:
        district_name: 選區名稱，例如 "臺北市信義區"
        raw_data_dir:  原始政府數據目錄
        places_cache:  Places API 快取路徑（None = 跳過）
        tam:           手動指定 TAM（None = 自動計算）

    Returns:
        {
            "district": str,
            "inner_vector": EnergyVector,
            "outer_vector": EnergyVector,
            "coverage": dict,
            "tam": int,
            "population": int | None,
            "archetypes": list[Archetype],   # 64 個（8×8）
            "indicators": dict,   # 該區的 40 個 indicator 值
            "benchmarks": dict,   # 全國基準
        }
    """
    normalized_name = _normalize_district_name(district_name)
    logger.info(f"[prepare_simulation] 開始處理：{normalized_name}")

    # 1. 建立所有區的 indicator dict（含 None 填充）
    places_cache_resolved: str | None = places_cache
    if places_cache is not None:
        p = Path(places_cache)
        if not p.exists():
            logger.warning(f"places_cache 不存在：{places_cache}，跳過 Places 數據")
            places_cache_resolved = None

    all_indicators = build_district_indicators(
        raw_data_dir=raw_data_dir,
        places_cache_path=places_cache_resolved,
    )

    if not all_indicators:
        raise ValueError(f"無法載入任何 indicator 數據（raw_data_dir={raw_data_dir}）")

    # 2. 定位目標選區（台/臺 模糊比對）
    district_indicators: dict[str, float | None] | None = None
    matched_sid = normalized_name
    for sid in all_indicators:
        norm_sid = _normalize_district_name(sid)
        if norm_sid == normalized_name:
            district_indicators = all_indicators[sid]
            matched_sid = sid
            break

    if district_indicators is None:
        # 嘗試部分匹配
        for sid in all_indicators:
            norm_sid = _normalize_district_name(sid)
            if normalized_name in norm_sid or norm_sid in normalized_name:
                district_indicators = all_indicators[sid]
                matched_sid = sid
                logger.info(f"模糊匹配：{district_name} → {sid}")
                break

    if district_indicators is None:
        available = sorted(all_indicators.keys())[:10]
        raise ValueError(
            f"找不到選區 '{district_name}'（正規化後：'{normalized_name}'）。\n"
            f"可用範例：{available}"
        )

    # 3. 計算全國基準 + 該區能量向量
    benchmarks = build_benchmarks(all_indicators)

    # energy_mapper 要求 indicators 為 {str: float}（過濾 None）
    clean_indicators: dict[str, float] = {
        k: v for k, v in district_indicators.items() if v is not None
    }

    inner_vector, outer_vector = compute_region_energy(clean_indicators, benchmarks)

    # 4. 覆蓋率報告（用單一區的 indicators dict 格式）
    coverage = get_coverage_report({matched_sid: district_indicators})

    # 5. TAM 計算
    population = _get_population(raw_data_dir, district_name)
    tam_value = _compute_tam(population, tam)

    # 6. 生成 64 個原型（8×8 One Muse 八方位笛卡兒積）
    archetypes = _build_archetypes(inner_vector, outer_vector, tam_value, district_name=normalized_name)

    logger.info(
        f"[prepare_simulation] 完成 | "
        f"覆蓋率={coverage['available']}/{coverage['total_indicators']} | "
        f"TAM={tam_value} | "
        f"原型數={len(archetypes)} | "
        f"Inner={inner_vector} | Outer={outer_vector}"
    )

    return {
        "district": normalized_name,
        "inner_vector": inner_vector,
        "outer_vector": outer_vector,
        "coverage": coverage,
        "tam": tam_value,
        "population": population,
        "archetypes": archetypes,
        "indicators": district_indicators,
        "benchmarks": benchmarks,
    }


def run_real_data_simulation(
    district_name: str,
    strategy_config: dict,
    raw_data_dir: str = "data/darwin/raw_data",
    places_cache: str | None = "data/darwin/raw_data/places_cache.json",
    tam: int | None = None,
    product_type: str = "b2b_saas",
    weeks: int = 52,
) -> dict:
    """
    端到端模擬：選區 → 真實數據 → 能量 → 52 週模擬 → 結果

    Args:
        district_name:   選區，例如 "臺北市信義區"
        strategy_config: 策略設定 dict（見 _build_strategy_vector）
        raw_data_dir:    政府數據目錄
        places_cache:    Places 快取路徑（None = 跳過）
        tam:             手動指定 TAM（None = 自動計算）
        product_type:    產品類型（傳給模擬引擎）
        weeks:           模擬週數（預設 52）

    Returns:
        {
            "district": str,
            "energy": {"inner": dict, "outer": dict},
            "coverage": dict,
            "tam": int,
            "snapshots": list[WeeklySnapshot],
            "final_state": dict,   # 最終各狀態人數比例
        }
    """
    # -- 延遲匯入避免循環依賴 --
    from museon.darwin.simulation.engine import SimulationEngine

    # 1. 準備基礎元素
    prep = prepare_simulation(
        district_name=district_name,
        raw_data_dir=raw_data_dir,
        places_cache=places_cache,
        tam=tam,
    )

    # 2. 建立 StrategyVector
    strategy = _build_strategy_vector(strategy_config)

    # 3. 初始化引擎
    engine = SimulationEngine(
        archetypes=prep["archetypes"],
        strategy=strategy,
        baseline_inner=prep["inner_vector"],
        baseline_outer=prep["outer_vector"],
        tam=prep["tam"],
        product_type=product_type,
    )

    # 4. 執行模擬
    logger.info(f"[run_real_data_simulation] 開始 {weeks} 週模擬 | {prep['district']}")
    snapshots = engine.run(weeks=weeks)
    logger.info(f"[run_real_data_simulation] 模擬完成，共 {len(snapshots)} 週快照")

    # 5. 彙整最終狀態
    final_snapshot = snapshots[-1] if snapshots else None
    final_state: dict = {}
    if final_snapshot:
        state_dist = final_snapshot.business_metrics.get("state_distribution", {})
        tam_value = prep["tam"]
        for state, ratio in state_dist.items():
            final_state[state] = {
                "ratio": round(ratio, 4),
                "count": int(ratio * tam_value),
            }

    return {
        "district": prep["district"],
        "energy": {
            "inner": prep["inner_vector"].to_dict(),
            "outer": prep["outer_vector"].to_dict(),
        },
        "coverage": prep["coverage"],
        "tam": prep["tam"],
        "population": prep["population"],
        "archetypes": prep["archetypes"],
        "snapshots": snapshots,
        "final_state": final_state,
    }
