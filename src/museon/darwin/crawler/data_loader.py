"""
data_loader.py — 載入政府原始數據，產出以「區」為單位的 indicator dict

數據來源：
  - population_density_113.json  → population_density
  - dynamics_11312.json          → birth_rate, divorce_rate, marriage_rate
  - households_113.json          → home_ownership_rate
  - household_structure_113.json → household_size
  - income_111.csv               → household_income, passive_income_ratio

公開 API：
  load_government_data(raw_data_dir)      → dict[site_id, dict[indicator, float]]
  load_national_benchmarks(raw_data_dir)  → dict[indicator, dict[min/max/mean, float]]
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path


# ──────────────────────────────────────────
# 內部工具
# ──────────────────────────────────────────

def _normalize_site_id(raw: str) -> str:
    """去掉多餘空白，統一全形半形不做轉換（保留原始臺/台字）。"""
    return raw.strip().replace(" ", "").replace("\u3000", "")


def _safe_float(value: str | None, default: float = 0.0) -> float:
    """安全轉換字串到 float，失敗回傳 default。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: str | None, default: int = 0) -> int:
    """安全轉換字串到 int，失敗回傳 default。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────
# 各數據源載入函數
# ──────────────────────────────────────────

def _load_population_density(raw_data_dir: Path) -> dict[str, dict]:
    """
    population_density_113.json
    回傳 {site_id: {population_density, people_total}}
    """
    path = raw_data_dir / "population_density_113.json"
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    result: dict[str, dict] = {}
    for rec in records:
        site_id = _normalize_site_id(rec.get("site_id", ""))
        if not site_id:
            continue
        result[site_id] = {
            "population_density": _safe_float(rec.get("population_density")),
            "people_total": _safe_float(rec.get("people_total")),
        }
    return result


def _load_dynamics(raw_data_dir: Path) -> dict[str, dict]:
    """
    dynamics_11312.json（村里級，113年12月單月）
    聚合到區級：{site_id: {birth_total, death_total, marry_pair, divorce_pair}}

    注意：dynamics 是單月數據（11312 = 113年12月）。
    若要計算年率，需乘以 12。此函數僅做加總聚合，比率計算在上層進行。
    """
    path = raw_data_dir / "dynamics_11312.json"
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    aggregated: dict[str, dict] = {}
    for rec in records:
        site_id = _normalize_site_id(rec.get("site_id", ""))
        if not site_id:
            continue
        if site_id not in aggregated:
            aggregated[site_id] = {
                "birth_total": 0,
                "death_total": 0,
                "marry_pair": 0,
                "divorce_pair": 0,
            }
        agg = aggregated[site_id]
        agg["birth_total"] += _safe_int(rec.get("birth_total"))
        agg["death_total"] += _safe_int(rec.get("death_total"))
        agg["marry_pair"] += _safe_int(rec.get("marry_pair"))
        agg["divorce_pair"] += _safe_int(rec.get("divorce_pair"))

    return aggregated


def _load_households(raw_data_dir: Path) -> dict[str, dict]:
    """
    households_113.json（村里級）
    聚合到區級：{site_id: {joint_households, solo_households}}
    home_ownership_rate ≈ 共同生活戶 / (共同生活戶 + 單獨生活戶)
    """
    path = raw_data_dir / "households_113.json"
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    aggregated: dict[str, dict] = {}
    for rec in records:
        site_id = _normalize_site_id(rec.get("區域別", ""))
        if not site_id:
            continue
        if site_id not in aggregated:
            aggregated[site_id] = {"joint_households": 0, "solo_households": 0}
        agg = aggregated[site_id]
        agg["joint_households"] += _safe_int(rec.get("共同生活戶_戶數"))
        agg["solo_households"] += _safe_int(rec.get("單獨生活戶_戶數"))

    return aggregated


def _load_household_structure(raw_data_dir: Path) -> dict[str, dict]:
    """
    household_structure_113.json（村里級）
    聚合到區級，計算加權平均戶均人口：
      household_size = Σ(n_人家戶 × n) / 總戶數
    10人以上家戶以 10 人計算。
    """
    path = raw_data_dir / "household_structure_113.json"
    with open(path, encoding="utf-8") as f:
        records = json.load(f)

    # 各人數對應欄位名稱
    SIZE_FIELDS = [
        ("1人家戶", 1),
        ("2人家戶", 2),
        ("3人家戶", 3),
        ("4人家戶", 4),
        ("5人家戶", 5),
        ("6人家戶", 6),
        ("7人家戶", 7),
        ("8人家戶", 8),
        ("9人家戶", 9),
        ("10人以上家戶", 10),
    ]

    aggregated: dict[str, dict] = {}
    for rec in records:
        site_id = _normalize_site_id(rec.get("區域別", ""))
        if not site_id:
            continue
        if site_id not in aggregated:
            aggregated[site_id] = {"weighted_sum": 0.0, "total_households": 0}
        agg = aggregated[site_id]
        for field, person_count in SIZE_FIELDS:
            count = _safe_int(rec.get(field))
            agg["weighted_sum"] += count * person_count
            agg["total_households"] += count

    return aggregated


def _load_income(raw_data_dir: Path) -> dict[str, dict]:
    """
    income_111.csv（村里級，BOM 編碼）
    欄位：縣市別（實為區域別）、村里、納稅單位(戶)、中位數、第三分位數
    聚合到區級（以納稅單位加權）：
      household_income   = Σ(中位數 × 納稅單位) / Σ(納稅單位)
      passive_income_ratio = Σ((第三分位數/中位數) × 納稅單位) / Σ(納稅單位)
    """
    path = raw_data_dir / "income_111.csv"
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        records = list(reader)

    # 找縣市別欄位（可能含 BOM）
    if records:
        first_keys = list(records[0].keys())
        city_field = next(
            (k for k in first_keys if "縣市別" in k),
            first_keys[0]
        )
    else:
        return {}

    aggregated: dict[str, dict] = {}
    for rec in records:
        # 縣市別欄位的值就是「臺北市松山區」這樣的區域別
        site_id = _normalize_site_id(rec.get(city_field, ""))
        if not site_id:
            continue
        # 過濾掉「其他」類別
        if "其他" in site_id:
            continue

        units = _safe_float(rec.get("納稅單位(戶)"))
        if units <= 0:
            continue

        median = _safe_float(rec.get("中位數"))
        q3 = _safe_float(rec.get("第三分位數"))

        if site_id not in aggregated:
            aggregated[site_id] = {
                "weighted_median_sum": 0.0,
                "weighted_ratio_sum": 0.0,
                "total_units": 0.0,
            }
        agg = aggregated[site_id]
        agg["weighted_median_sum"] += median * units
        # 避免除以零：若中位數為 0，比值設為 0
        ratio = (q3 / median) if median > 0 else 0.0
        agg["weighted_ratio_sum"] += ratio * units
        agg["total_units"] += units

    return aggregated


# ──────────────────────────────────────────
# 主要公開函數
# ──────────────────────────────────────────

def load_government_data(raw_data_dir: str) -> dict[str, dict[str, float]]:
    """
    載入所有政府數據，回傳以「區」為單位的 indicator dict。

    Parameters
    ----------
    raw_data_dir : str
        raw_data 目錄路徑（可為相對或絕對路徑）。

    Returns
    -------
    dict[str, dict[str, float]]
        {site_id: {indicator_name: value, ...}, ...}

    Indicators
    ----------
    population_density    人/km²
    household_income      千元（加權中位數）
    birth_rate            ‰（年化）
    divorce_rate          ‰（年化）
    marriage_rate         ‰（年化）
    household_size        人/戶（加權平均）
    home_ownership_rate   0~1（共同生活戶比率）
    passive_income_ratio  Q3/中位數（財富集中度近似）
    """
    base = Path(raw_data_dir)

    # 載入各數據源
    pop_data = _load_population_density(base)
    dyn_data = _load_dynamics(base)
    hh_data = _load_households(base)
    hhs_data = _load_household_structure(base)
    inc_data = _load_income(base)

    # 以 population_density 的 site_id 為主鍵（最完整的區級清單）
    all_site_ids = set(pop_data.keys())

    result: dict[str, dict[str, float]] = {}

    for site_id in all_site_ids:
        indicators: dict[str, float] = {}

        # ── population_density ──────────────────────────
        pop = pop_data.get(site_id, {})
        indicators["population_density"] = pop.get("population_density", 0.0)
        people_total = pop.get("people_total", 0.0)

        # ── birth_rate / divorce_rate / marriage_rate ───
        # dynamics 是單月（12月）數據，年化 × 12，再除以人口基數 × 1000 得‰
        dyn = dyn_data.get(site_id, {})
        if people_total > 0:
            indicators["birth_rate"] = (
                dyn.get("birth_total", 0) * 12 / people_total * 1000
            )
            indicators["divorce_rate"] = (
                dyn.get("divorce_pair", 0) * 12 / people_total * 1000
            )
            indicators["marriage_rate"] = (
                dyn.get("marry_pair", 0) * 12 / people_total * 1000
            )
        else:
            indicators["birth_rate"] = 0.0
            indicators["divorce_rate"] = 0.0
            indicators["marriage_rate"] = 0.0

        # ── home_ownership_rate ─────────────────────────
        hh = hh_data.get(site_id, {})
        joint = hh.get("joint_households", 0)
        solo = hh.get("solo_households", 0)
        total_hh = joint + solo
        indicators["home_ownership_rate"] = (
            joint / total_hh if total_hh > 0 else 0.0
        )

        # ── household_size ──────────────────────────────
        hhs = hhs_data.get(site_id, {})
        total_households = hhs.get("total_households", 0)
        weighted_sum = hhs.get("weighted_sum", 0.0)
        indicators["household_size"] = (
            weighted_sum / total_households if total_households > 0 else 0.0
        )

        # ── household_income / passive_income_ratio ─────
        inc = inc_data.get(site_id, {})
        total_units = inc.get("total_units", 0.0)
        if total_units > 0:
            indicators["household_income"] = (
                inc.get("weighted_median_sum", 0.0) / total_units
            )
            indicators["passive_income_ratio"] = (
                inc.get("weighted_ratio_sum", 0.0) / total_units
            )
        else:
            indicators["household_income"] = 0.0
            indicators["passive_income_ratio"] = 0.0

        result[site_id] = indicators

    return result


def load_national_benchmarks(
    raw_data_dir: str,
) -> dict[str, dict[str, float]]:
    """
    從全部區的數據計算每個 indicator 的統計基準值。

    Parameters
    ----------
    raw_data_dir : str
        raw_data 目錄路徑。

    Returns
    -------
    dict[str, dict[str, float]]
        {indicator_name: {min, max, mean, median, std}, ...}
    """
    data = load_government_data(raw_data_dir)
    if not data:
        return {}

    # 收集各 indicator 的全國數值列表（排除 0，避免缺值污染統計）
    indicator_names = [
        "population_density",
        "household_income",
        "birth_rate",
        "divorce_rate",
        "marriage_rate",
        "household_size",
        "home_ownership_rate",
        "passive_income_ratio",
    ]

    benchmarks: dict[str, dict[str, float]] = {}

    for indicator in indicator_names:
        values = [
            v[indicator]
            for v in data.values()
            if indicator in v and v[indicator] > 0
        ]
        if not values:
            benchmarks[indicator] = {"min": 0.0, "max": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0}
            continue

        benchmarks[indicator] = {
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        }

    return benchmarks
