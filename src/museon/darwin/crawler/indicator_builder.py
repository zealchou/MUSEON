"""
indicator_builder.py — 整合三個數據來源，產出完整的 40 indicator dict

數據來源：
  1. 政府數據（data_loader.py）  → 8 個 indicator
  2. Places API（places_crawler.py）→ 7 個 indicator
  3. 衍生推導（本模組）           → 5 個 indicator
  其餘 20 個設為 None，energy_mapper 以權重歸零處理。

公開 API：
  build_district_indicators(raw_data_dir, places_cache_path)
      → dict[str, dict[str, float | None]]
  build_benchmarks(indicators)
      → dict[str, dict[str, float]]
  get_available_indicators()
      → list[str]
  get_coverage_report(indicators)
      → dict
"""

from __future__ import annotations

import statistics
from pathlib import Path

from museon.darwin.crawler.data_loader import (
    _load_population_density,
    load_government_data,
)
from museon.darwin.crawler.places_crawler import compute_places_indicators


# ──────────────────────────────────────────
# 常數：40 個 indicator 完整列表
# ──────────────────────────────────────────

ALL_INDICATORS: list[str] = [
    # 天 outer
    "startup_density",
    "outdoor_venue_density",
    "political_participation",
    # 天 inner
    "volunteer_org_density",
    "community_group_count",
    # 風 outer
    "sales_job_ratio",
    "partnership_ratio",
    "business_survival_rate",
    # 風 inner
    "marriage_rate",
    "mediation_success_rate",
    # 水 outer
    "household_size",
    "divorce_rate",
    "birth_rate",
    # 水 inner
    "care_facility_density",
    "longterm_care_density",
    # 山 outer
    "gym_density",
    "fine_dining_density",
    "religious_venue_density",
    # 山 inner
    "savings_rate",
    "insurance_penetration",
    # 地 outer
    "household_income",
    "home_ownership_rate",
    "franchise_density",
    # 地 inner
    "population_density",
    "passive_income_ratio",
    # 雷 outer
    "wellness_course_density",
    "art_event_count",
    "subculture_density",
    # 雷 inner
    "meditation_search_trend",
    "counseling_density",
    # 火 outer
    "exhibition_attendance",
    "training_enrollment",
    # 火 inner
    "subscription_usage",
    "research_firm_density",
    # 澤 outer
    "cafe_density",
    "mall_density",
    "creator_ratio",
    # 澤 inner
    "social_interaction_rate",
    "kol_density",
    "brand_store_density",
]

# 政府數據提供的 indicator（data_loader.py 產出的欄位名稱）
_GOV_INDICATORS: set[str] = {
    "population_density",
    "household_income",
    "birth_rate",
    "divorce_rate",
    "marriage_rate",
    "household_size",
    "home_ownership_rate",
    "passive_income_ratio",
}

# Places API 提供的 indicator（places_crawler.py 產出的欄位名稱）
_PLACES_INDICATORS: set[str] = {
    "cafe_density",
    "gym_density",
    "mall_density",
    "religious_venue_density",
    "fine_dining_density",
    "outdoor_venue_density",
    "brand_store_density",
}

# 衍生推導的 indicator
_DERIVED_INDICATORS: set[str] = {
    "savings_rate",
    "insurance_penetration",
    "counseling_density",
    "community_group_count",
    "franchise_density",
}

# 有真實或衍生數據的 indicator（供 get_available_indicators 使用）
_AVAILABLE_INDICATORS: list[str] = sorted(
    _GOV_INDICATORS | _PLACES_INDICATORS | _DERIVED_INDICATORS
)


# ──────────────────────────────────────────
# 正規化工具
# ──────────────────────────────────────────

def _normalize_site_id(name: str) -> str:
    """統一「台」→「臺」，去掉多餘空白。"""
    return name.replace("台", "臺").strip().replace(" ", "").replace("\u3000", "")


# ──────────────────────────────────────────
# 衍生指標推導
# ──────────────────────────────────────────

def _compute_derived_indicators(
    gov: dict[str, float],
    national_income_median: float,
    hh_raw: dict,
) -> dict[str, float | None]:
    """
    從政府數據推導 5 個衍生指標。

    Parameters
    ----------
    gov : dict[str, float]
        單一區的政府 indicator dict。
    national_income_median : float
        全國戶均所得中位數（千元），用於 savings_rate 正規化。
    hh_raw : dict
        該區的原始戶口數據（含 joint_households / solo_households）。

    Returns
    -------
    dict[str, float | None]
        5 個衍生 indicator 的值。
    """
    derived: dict[str, float | None] = {}

    # 1. savings_rate：所得相對全國中位數的比值，收入高 → 儲蓄傾向高
    income = gov.get("household_income", 0.0)
    if income > 0 and national_income_median > 0:
        # 比值（0~無上限），再做 min-cap 避免極端值
        derived["savings_rate"] = min(income / national_income_median, 3.0)
    else:
        derived["savings_rate"] = None

    # 2. insurance_penetration：用 home_ownership_rate 近似（有房=有保險傾向）
    home_rate = gov.get("home_ownership_rate")
    if home_rate is not None and home_rate > 0:
        derived["insurance_penetration"] = float(home_rate)
    else:
        derived["insurance_penetration"] = None

    # 3. counseling_density：獨居比例高 → 心理諮商需求高
    #    solo_ratio = 單獨生活戶 / (共同生活戶 + 單獨生活戶)
    joint = hh_raw.get("joint_households", 0)
    solo = hh_raw.get("solo_households", 0)
    total_hh = joint + solo
    if total_hh > 0:
        derived["counseling_density"] = solo / total_hh
    else:
        derived["counseling_density"] = None

    # 4. community_group_count：用 marriage_rate 近似（結婚率高=社區凝聚力高）
    marriage = gov.get("marriage_rate")
    if marriage is not None and marriage > 0:
        derived["community_group_count"] = float(marriage)
    else:
        derived["community_group_count"] = None

    # 5. franchise_density：用 population_density × household_income 乘積近似
    pop_density = gov.get("population_density", 0.0)
    if pop_density > 0 and income > 0:
        # 乘積可能很大，做 log-scaling 壓縮
        import math
        derived["franchise_density"] = math.log1p(pop_density * income / 1000)
    else:
        derived["franchise_density"] = None

    return derived


# ──────────────────────────────────────────
# 主要公開函數
# ──────────────────────────────────────────

def build_district_indicators(
    raw_data_dir: str = "data/darwin/raw_data",
    places_cache_path: str | None = None,
) -> dict[str, dict[str, float | None]]:
    """
    整合所有來源，回傳每個區的完整 40 indicator dict。
    缺失的 indicator 值為 None。

    Parameters
    ----------
    raw_data_dir : str
        raw_data 目錄路徑（相對或絕對）。
    places_cache_path : str | None
        places_cache.json 路徑。None = 跳過 Places 數據。

    Returns
    -------
    dict[str, dict[str, float | None]]
        {site_id: {indicator_name: value_or_None, ...}, ...}
        每個 site_id 的 dict 恰好包含全部 40 個 indicator key。
    """
    base = Path(raw_data_dir)

    # ── 1. 政府數據 ─────────────────────────────────
    gov_data = load_government_data(str(base))

    # 計算全國所得中位數（用於 savings_rate 推導）
    incomes = [v["household_income"] for v in gov_data.values() if v.get("household_income", 0) > 0]
    national_income_median = statistics.median(incomes) if incomes else 0.0

    # 載入原始戶口數據（供 counseling_density 推導）
    from museon.darwin.crawler.data_loader import _load_households
    hh_raw_data = _load_households(base)

    # ── 2. Places 數據 ───────────────────────────────
    places_data: dict[str, dict[str, float]] = {}
    if places_cache_path is not None:
        # compute_places_indicators 需要 {site_id: {people_total: float}}
        pop_raw = _load_population_density(base)
        # 正規化 site_id（Places 快取可能用「台」）
        pop_for_places = {
            _normalize_site_id(sid): info
            for sid, info in pop_raw.items()
        }
        raw_places = compute_places_indicators(places_cache_path, pop_for_places)
        # 正規化 Places 結果的 site_id
        places_data = {
            _normalize_site_id(sid): indicators
            for sid, indicators in raw_places.items()
        }

    # ── 3. 合併 + 衍生推導 ──────────────────────────
    result: dict[str, dict[str, float | None]] = {}

    for site_id, gov in gov_data.items():
        # 起始：全部 40 個 indicator 設為 None
        indicators: dict[str, float | None] = {k: None for k in ALL_INDICATORS}

        # 填入政府數據（8 個）
        for key in _GOV_INDICATORS:
            val = gov.get(key)
            if val is not None and val != 0.0:
                indicators[key] = val
            elif val == 0.0:
                # 0 值保留（部分 indicator 0 是有意義的值）
                indicators[key] = val

        # 填入 Places 數據（最多 7 個，若有快取）
        normalized_sid = _normalize_site_id(site_id)
        if normalized_sid in places_data:
            for key in _PLACES_INDICATORS:
                val = places_data[normalized_sid].get(key)
                if val is not None:
                    indicators[key] = val

        # 填入衍生推導（5 個）
        hh_raw = hh_raw_data.get(site_id, {})
        derived = _compute_derived_indicators(gov, national_income_median, hh_raw)
        for key, val in derived.items():
            indicators[key] = val

        result[site_id] = indicators

    return result


def build_benchmarks(
    indicators: dict[str, dict[str, float | None]],
) -> dict[str, dict[str, float]]:
    """
    從所有區的數據算出每個 indicator 的 min/max/mean/median/std。
    只計算非 None 且非 0 的值。

    Parameters
    ----------
    indicators : dict[str, dict[str, float | None]]
        build_district_indicators() 的輸出。

    Returns
    -------
    dict[str, dict[str, float]]
        {indicator_name: {min, max, mean, median, std}, ...}
    """
    benchmarks: dict[str, dict[str, float]] = {}

    for ind_name in ALL_INDICATORS:
        values = [
            v[ind_name]
            for v in indicators.values()
            if v.get(ind_name) is not None and v[ind_name] != 0.0
        ]
        if not values:
            benchmarks[ind_name] = {
                "min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0
            }
            continue

        benchmarks[ind_name] = {
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        }

    return benchmarks


def get_available_indicators() -> list[str]:
    """
    回傳目前有真實數據（政府 + Places + 衍生）的 indicator 名稱列表。
    不包含純 None 的 indicator。
    """
    return list(_AVAILABLE_INDICATORS)


def get_coverage_report(indicators: dict) -> dict:
    """
    回傳覆蓋率報告。

    Parameters
    ----------
    indicators : dict
        build_district_indicators() 的輸出。

    Returns
    -------
    dict
        {
          "total_districts": int,
          "total_indicators": int,
          "available": int,       # 有真實數據的 indicator 數
          "coverage_pct": float,
          "available_names": list[str],
          "missing_names": list[str],
        }
    """
    if not indicators:
        return {
            "total_districts": 0,
            "total_indicators": len(ALL_INDICATORS),
            "available": 0,
            "coverage_pct": 0.0,
            "available_names": [],
            "missing_names": list(ALL_INDICATORS),
        }

    # 取一個區的 dict 來判斷哪些 indicator 有非 None 值（跨所有區）
    all_with_data: set[str] = set()
    for dist_ind in indicators.values():
        for k, v in dist_ind.items():
            if v is not None:
                all_with_data.add(k)

    available_names = sorted(all_with_data)
    missing_names = sorted(set(ALL_INDICATORS) - all_with_data)

    return {
        "total_districts": len(indicators),
        "total_indicators": len(ALL_INDICATORS),
        "available": len(available_names),
        "coverage_pct": len(available_names) / len(ALL_INDICATORS) * 100,
        "available_names": available_names,
        "missing_names": missing_names,
    }
