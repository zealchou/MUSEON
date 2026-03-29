"""Market Ares — 數據→能量映射引擎

五層原始數據 → 八方位 × 內在/外在 = 16 維能量向量
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from museon.market_ares.config import ENERGY_MAX, ENERGY_MIN, PRIMALS
from museon.market_ares.storage.models import EnergyVector

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "mapping_config.yaml"


def load_mapping_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _normalize(value: float, min_val: float, max_val: float) -> float:
    """將原始數據正規化到 0-1 區間"""
    if max_val == min_val:
        return 0.5
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def _scale_to_energy(normalized: float, direction: str = "positive") -> float:
    """將 0-1 正規化值轉換為 -4 ~ +4 的能量值

    positive: 0→-4, 0.5→0, 1→+4
    negative: 0→+4, 0.5→0, 1→-4
    """
    if direction == "negative":
        normalized = 1.0 - normalized
    return ENERGY_MIN + normalized * (ENERGY_MAX - ENERGY_MIN)


def compute_primal_energy(
    primal: str,
    indicators: dict[str, float],
    benchmarks: dict[str, dict[str, float]],
    config: dict | None = None,
) -> tuple[float, float]:
    """計算單一方位的內在與外在能量值

    Args:
        primal: 方位名稱（天/風/水/山/地/雷/火/澤）
        indicators: 該地區的原始指標數據 {indicator_name: value}
        benchmarks: 全國基準數據 {indicator_name: {min, max, mean}}
        config: 映射設定（可選，預設讀取 yaml）

    Returns:
        (inner_energy, outer_energy) 各為 -4 ~ +4
    """
    if config is None:
        config = load_mapping_config()

    primal_config = config.get(primal)
    if not primal_config:
        logger.warning(f"未找到方位 {primal} 的映射設定")
        return 0.0, 0.0

    outer_score = 0.0
    outer_weight_sum = 0.0
    inner_score = 0.0
    inner_weight_sum = 0.0

    # 外在指標
    for ind in primal_config.get("outer_indicators", []):
        name = ind["name"]
        weight = abs(ind["weight"])
        direction = ind.get("direction", "positive")

        if name not in indicators:
            continue

        bench = benchmarks.get(name, {})
        min_val = bench.get("min", 0)
        max_val = bench.get("max", 1)

        normalized = _normalize(indicators[name], min_val, max_val)
        energy = _scale_to_energy(normalized, direction)

        outer_score += energy * weight
        outer_weight_sum += weight

    # 內在指標
    for ind in primal_config.get("inner_indicators", []):
        name = ind["name"]
        weight = abs(ind["weight"])
        direction = ind.get("direction", "positive")

        if name not in indicators:
            continue

        # contextual 方向需要特殊處理
        if direction == "contextual":
            # 例：人口密度+低收入=地能量低
            # 簡化處理：目前當作 negative
            direction = "negative"

        bench = benchmarks.get(name, {})
        min_val = bench.get("min", 0)
        max_val = bench.get("max", 1)

        normalized = _normalize(indicators[name], min_val, max_val)
        energy = _scale_to_energy(normalized, direction)

        inner_score += energy * weight
        inner_weight_sum += weight

    # 加權平均
    outer = (outer_score / outer_weight_sum) if outer_weight_sum > 0 else 0.0
    inner = (inner_score / inner_weight_sum) if inner_weight_sum > 0 else 0.0

    # 裁剪到有效範圍
    outer = max(ENERGY_MIN, min(ENERGY_MAX, outer))
    inner = max(ENERGY_MIN, min(ENERGY_MAX, inner))

    return inner, outer


def compute_region_energy(
    indicators: dict[str, float],
    benchmarks: dict[str, dict[str, float]],
) -> tuple[EnergyVector, EnergyVector]:
    """計算地區的完整 16 維能量向量

    Args:
        indicators: 該地區的所有原始指標數據
        benchmarks: 全國基準數據

    Returns:
        (inner_vector, outer_vector)
    """
    config = load_mapping_config()
    inner_dict = {}
    outer_dict = {}

    for primal in PRIMALS:
        inner, outer = compute_primal_energy(primal, indicators, benchmarks, config)
        inner_dict[primal] = round(inner, 2)
        outer_dict[primal] = round(outer, 2)

    return EnergyVector.from_dict(inner_dict), EnergyVector.from_dict(outer_dict)
