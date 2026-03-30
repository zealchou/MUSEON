"""
compare_districts.py — DARWIN 多區比較工具

提供兩個公開 API：
  compare_districts(districts, strategy_config, ...)
      → 同一策略在多個區的完整模擬比較
  quick_scan(strategy_config, top_n, ...)
      → 快速掃描所有區，找出最適合策略的 Top N 區域（純能量向量匹配，不跑完整模擬）
"""

from __future__ import annotations

import logging
import math
from typing import Any

from museon.darwin.config import PRIMALS
from museon.darwin.run_simulation import prepare_simulation, run_real_data_simulation

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 內部工具
# ──────────────────────────────────────────────────────────────


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """計算兩個能量向量的餘弦相似度（-1 ~ 1）。"""
    keys = list(PRIMALS)
    a = [vec_a.get(k, 0.0) for k in keys]
    b = [vec_b.get(k, 0.0) for k in keys]

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


def _strategy_to_energy_dict(strategy_config: dict) -> dict[str, float]:
    """
    將 strategy_config 轉為方位能量 dict，用於匹配計算。
    主打方位設為 intensity 值，其他方位為 0。
    """
    intensity = float(strategy_config.get("intensity", 0.7))
    target_primals = strategy_config.get("target_primals", [])
    result = {p: 0.0 for p in PRIMALS}
    for primal in target_primals:
        if primal in result:
            result[primal] = intensity
    return result


def _weeks_to_threshold(
    snapshots: list,
    threshold: float,
) -> int | None:
    """
    找出模擬中第幾週 penetration_rate 首次達到 threshold。
    找不到則回傳 None。
    """
    for snap in snapshots:
        rate = snap.business_metrics.get("penetration_rate", 0.0)
        if rate >= threshold:
            return snap.week
    return None


def _weeks_to_chasm(snapshots: list) -> int | None:
    """
    鴻溝 = early majority 開始大量採用的節點。
    用 penetration_rate 達到 16%（innovator + early_adopter 飽和）作為替代指標。
    """
    return _weeks_to_threshold(snapshots, threshold=0.16)


def _generate_insights(district_results: dict[str, dict]) -> list[str]:
    """
    根據各區比較結果生成純文字洞察列表。
    district_results: {district_name: {...district result dict...}}
    """
    insights: list[str] = []

    if not district_results:
        return insights

    # 按 penetration_rate 排序
    sorted_districts = sorted(
        district_results.items(),
        key=lambda x: x[1].get("penetration_rate", 0.0),
        reverse=True,
    )

    best_name, best_data = sorted_districts[0]
    worst_name, worst_data = sorted_districts[-1]

    # 洞察 1：最佳 vs 最差
    if len(sorted_districts) >= 2:
        best_rate = best_data.get("penetration_rate", 0.0)
        worst_rate = worst_data.get("penetration_rate", 0.0)
        insights.append(
            f"{best_name} 採用率最高（{best_rate:.1%}），"
            f"{worst_name} 最低（{worst_rate:.1%}），"
            f"差距 {best_rate - worst_rate:.1%}。"
        )

    # 洞察 2：週數比較
    weeks_10pct_data = [
        (name, d.get("weeks_to_10pct"))
        for name, d in sorted_districts
        if d.get("weeks_to_10pct") is not None
    ]
    if len(weeks_10pct_data) >= 2:
        fastest_name, fastest_weeks = min(weeks_10pct_data, key=lambda x: x[1])
        slowest_name, slowest_weeks = max(weeks_10pct_data, key=lambda x: x[1])
        if fastest_name != slowest_name:
            insights.append(
                f"到達 10% 採用率：{fastest_name} 最快（第 {fastest_weeks} 週），"
                f"{slowest_name} 最慢（第 {slowest_weeks} 週）。"
            )
    elif weeks_10pct_data:
        name, weeks = weeks_10pct_data[0]
        insights.append(f"{name} 在第 {weeks} 週達到 10% 採用率。")
    else:
        # 所有區都沒有到達 10%
        insights.append("所有比較區域在 52 週內均未達到 10% 採用率，建議調整策略強度或目標客群。")

    # 洞察 3：跨越鴻溝
    chasm_data = [
        (name, d.get("weeks_to_chasm"))
        for name, d in sorted_districts
        if d.get("weeks_to_chasm") is not None
    ]
    chasm_none = [name for name, d in sorted_districts if d.get("weeks_to_chasm") is None]
    if chasm_data:
        chasm_best_name, chasm_best_weeks = min(chasm_data, key=lambda x: x[1])
        insights.append(f"{chasm_best_name} 在第 {chasm_best_weeks} 週跨越鴻溝（16% 採用率）。")
    if chasm_none:
        insights.append(f"{'、'.join(chasm_none)} 在模擬期內未跨越鴻溝。")

    # 洞察 4：TAM 大小與市場機會
    sorted_by_tam = sorted(district_results.items(), key=lambda x: x[1].get("tam", 0), reverse=True)
    if sorted_by_tam:
        biggest_name, biggest_data = sorted_by_tam[0]
        biggest_revenue = biggest_data.get("revenue_ntd", 0)
        insights.append(
            f"{biggest_name} TAM 最大（{biggest_data.get('tam', 0):,} 人），"
            f"若策略奏效預估營收 NT${biggest_revenue:,.0f}。"
        )

    return insights


# ──────────────────────────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────────────────────────


def compare_districts(
    districts: list[str],
    strategy_config: dict,
    raw_data_dir: str = "data/darwin/raw_data",
    places_cache: str | None = "data/darwin/raw_data/places_cache.json",
    weeks: int = 52,
) -> dict:
    """
    同一策略在多區的模擬比較。

    Args:
        districts:       要比較的區域列表，例如 ["臺北市信義區", "臺南市永康區"]
        strategy_config: 統一策略設定（含 name / target_primals / intensity / channels）
        raw_data_dir:    政府數據目錄
        places_cache:    Places API 快取路徑（None = 跳過）
        weeks:           模擬週數（預設 52）

    Returns:
        {
            "strategy": dict,
            "districts": {
                "臺北市信義區": {
                    "population": int,
                    "tam": int,
                    "energy": {"inner": dict, "outer": dict},
                    "coverage": dict,
                    "final_state": dict,
                    "penetration_rate": float,
                    "revenue_ntd": int,
                    "weeks_to_10pct": int | None,
                    "weeks_to_chasm": int | None,
                },
                ...
            },
            "ranking": list[str],       # 按 penetration_rate 降序
            "insights": list[str],      # 比較洞察（純文字）
        }
    """
    results: dict[str, dict] = {}

    for district in districts:
        logger.info(f"[compare_districts] 開始模擬：{district}")
        try:
            sim = run_real_data_simulation(
                district_name=district,
                strategy_config=strategy_config,
                raw_data_dir=raw_data_dir,
                places_cache=places_cache,
                weeks=weeks,
            )

            snapshots = sim.get("snapshots", [])

            # 最終 penetration_rate（decided + loyal）
            final_snap = snapshots[-1] if snapshots else None
            penetration_rate = 0.0
            revenue_ntd = 0
            if final_snap:
                penetration_rate = final_snap.business_metrics.get("penetration_rate", 0.0)
                revenue_ntd = final_snap.business_metrics.get("revenue_ntd", 0)

            weeks_to_10pct = _weeks_to_threshold(snapshots, threshold=0.10)
            weeks_to_chasm_val = _weeks_to_chasm(snapshots)

            results[district] = {
                "population": sim.get("population"),
                "tam": sim.get("tam", 0),
                "energy": sim.get("energy", {"inner": {}, "outer": {}}),
                "coverage": sim.get("coverage", {}),
                "final_state": sim.get("final_state", {}),
                "penetration_rate": round(penetration_rate, 4),
                "revenue_ntd": revenue_ntd,
                "weeks_to_10pct": weeks_to_10pct,
                "weeks_to_chasm": weeks_to_chasm_val,
            }
            logger.info(
                f"[compare_districts] {district} 完成 | "
                f"滲透率={penetration_rate:.2%} | 第{weeks_to_10pct}週達10%"
            )

        except Exception as e:
            logger.error(f"[compare_districts] {district} 模擬失敗：{e}")
            results[district] = {
                "population": None,
                "tam": 0,
                "energy": {"inner": {}, "outer": {}},
                "coverage": {},
                "final_state": {},
                "penetration_rate": 0.0,
                "revenue_ntd": 0,
                "weeks_to_10pct": None,
                "weeks_to_chasm": None,
                "error": str(e),
            }

    # 按 penetration_rate 降序排名
    ranking = sorted(
        results.keys(),
        key=lambda d: results[d].get("penetration_rate", 0.0),
        reverse=True,
    )

    insights = _generate_insights(results)

    return {
        "strategy": strategy_config,
        "districts": results,
        "ranking": ranking,
        "insights": insights,
    }


def quick_scan(
    strategy_config: dict,
    top_n: int = 10,
    raw_data_dir: str = "data/darwin/raw_data",
    places_cache: str | None = "data/darwin/raw_data/places_cache.json",
) -> list[dict]:
    """
    快速掃描所有區，找出最適合該策略的 Top N 區域。

    不跑完整模擬，只用能量向量距離做初步排序：
    - 策略主打方位與區域能量的餘弦相似度
    - 人口 / TAM 大小（加分）
    - 數據覆蓋率

    Args:
        strategy_config: 策略設定
        top_n:           回傳前 N 名
        raw_data_dir:    政府數據目錄
        places_cache:    Places API 快取路徑（None = 跳過）

    Returns:
        [
            {
                "district": str,
                "match_score": float,  # 0-1
                "tam": int,
                "reason": str,
            },
            ...
        ]
    """
    from museon.darwin.crawler.indicator_builder import build_district_indicators
    from museon.darwin.mapping.energy_mapper import compute_region_energy
    from museon.darwin.crawler.indicator_builder import build_benchmarks
    from museon.darwin.run_simulation import _normalize_district_name, _get_population, _compute_tam
    from pathlib import Path

    # 1. 載入所有區 indicators
    places_cache_resolved: str | None = places_cache
    if places_cache is not None:
        p = Path(places_cache)
        if not p.exists():
            logger.warning(f"places_cache 不存在：{places_cache}，跳過 Places 數據")
            places_cache_resolved = None

    logger.info("[quick_scan] 載入所有區 indicator 數據...")
    all_indicators = build_district_indicators(
        raw_data_dir=raw_data_dir,
        places_cache_path=places_cache_resolved,
    )

    if not all_indicators:
        logger.error("[quick_scan] 無法載入任何 indicator 數據")
        return []

    benchmarks = build_benchmarks(all_indicators)
    strategy_energy = _strategy_to_energy_dict(strategy_config)
    target_primals = strategy_config.get("target_primals", [])

    # 2. 針對每個區計算匹配分數
    candidates: list[dict] = []

    for district_id, indicators in all_indicators.items():
        try:
            clean_indicators: dict[str, float] = {
                k: v for k, v in indicators.items() if v is not None
            }
            inner_vec, outer_vec = compute_region_energy(clean_indicators, benchmarks)

            inner_dict = inner_vec.to_dict()
            outer_dict = outer_vec.to_dict()

            # 能量匹配：取內在向量（購買動機）和外在向量（社會行為）的平均相似度
            sim_inner = _cosine_similarity(strategy_energy, inner_dict)
            sim_outer = _cosine_similarity(strategy_energy, outer_dict)
            energy_score = (sim_inner + sim_outer) / 2.0

            # 正規化到 0-1（餘弦值域 -1~1 → 0~1）
            energy_score_normalized = (energy_score + 1.0) / 2.0

            # TAM 加分（人口越多分數加成越高，log 避免極端值）
            population = _get_population(raw_data_dir, district_id)
            tam = _compute_tam(population, None)
            # TAM 加分：相對於台灣平均 TAM（約 500）做 log 正規化
            if tam > 0:
                tam_bonus = min(0.15, math.log(tam / 100 + 1) * 0.05)
            else:
                tam_bonus = 0.0

            # 覆蓋率加分
            coverage_count = sum(1 for v in indicators.values() if v is not None)
            total_indicators = len(indicators) if indicators else 1
            coverage_ratio = coverage_count / total_indicators
            coverage_bonus = coverage_ratio * 0.05

            match_score = min(1.0, energy_score_normalized + tam_bonus + coverage_bonus)

            # 生成原因說明（列出主打方位的具體能量值）
            reason_parts = []
            for primal in target_primals:
                inner_val = inner_dict.get(primal, 0.0)
                outer_val = outer_dict.get(primal, 0.0)
                reason_parts.append(f"{primal}能量 內{inner_val:+.1f}/外{outer_val:+.1f}")
            reason = "、".join(reason_parts) if reason_parts else "無主打方位"

            normalized_name = _normalize_district_name(district_id)
            candidates.append(
                {
                    "district": normalized_name,
                    "match_score": round(match_score, 4),
                    "tam": tam,
                    "reason": reason,
                }
            )

        except Exception as e:
            logger.debug(f"[quick_scan] 跳過 {district_id}：{e}")
            continue

    # 3. 排序取 Top N
    candidates.sort(key=lambda x: x["match_score"], reverse=True)
    top_results = candidates[:top_n]

    logger.info(f"[quick_scan] 掃描完成，共 {len(candidates)} 區，回傳 Top {top_n}")
    return top_results
