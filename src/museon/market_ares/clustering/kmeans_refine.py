"""Market Ares — K-Means 收斂

Step 4: 以階層式聚類建議的群數，用 K-Means 重新跑，得到穩定分群
"""

from __future__ import annotations

import logging

import numpy as np
from scipy.cluster.vq import kmeans2, whiten

from museon.market_ares.config import PRIMALS
from museon.market_ares.storage.models import Archetype, EnergyVector

logger = logging.getLogger(__name__)


def refine_with_kmeans(
    matrix: np.ndarray,
    k: int,
    n_init: int = 10,
    max_iter: int = 100,
) -> tuple[np.ndarray, np.ndarray]:
    """用 K-Means 對階層式聚類結果做精煉

    Args:
        matrix: (N, 16) 能量矩陣
        k: 目標群數
        n_init: 跑幾次取最佳
        max_iter: 每次最大迭代數

    Returns:
        (centers, labels): centers=(k, 16), labels=(N,)
    """
    logger.info(f"K-Means 精煉：k={k}, n_init={n_init}")

    # 白化（正規化方差），讓各維度權重相等
    whitened = whiten(matrix)

    best_centers = None
    best_labels = None
    best_distortion = float("inf")

    for i in range(n_init):
        try:
            centers, labels = kmeans2(whitened, k, iter=max_iter, minit="points")
            # 計算總畸變
            distortion = sum(
                np.linalg.norm(whitened[j] - centers[labels[j]]) ** 2
                for j in range(len(labels))
            )
            if distortion < best_distortion:
                best_distortion = distortion
                best_centers = centers
                best_labels = labels
        except Exception as e:
            logger.warning(f"K-Means 第 {i+1} 次跑失敗：{e}")
            continue

    if best_centers is None:
        raise RuntimeError("K-Means 所有嘗試均失敗")

    # 將白化後的中心反轉回原始尺度
    std = matrix.std(axis=0)
    std[std == 0] = 1.0
    original_centers = best_centers * std

    logger.info(f"K-Means 完成：畸變={best_distortion:.2f}")
    return original_centers, best_labels


def centers_to_archetypes(
    centers: np.ndarray,
    labels: np.ndarray,
    total_population: int = 1,
) -> list[Archetype]:
    """將聚類中心轉換為 Archetype 物件

    Args:
        centers: (k, 16) 聚類中心
        labels: (N,) 每筆數據的群組標籤
        total_population: 總數據點數（用於計算權重）

    Returns:
        list[Archetype]
    """
    k = centers.shape[0]
    primals = list(PRIMALS)
    archetypes = []

    for i in range(k):
        inner_dict = {primals[j]: round(float(centers[i, j]), 2) for j in range(8)}
        outer_dict = {primals[j]: round(float(centers[i, j + 8]), 2) for j in range(8)}

        count = (labels == i).sum()
        weight = count / len(labels) if len(labels) > 0 else 1.0 / k

        # 根據能量特徵判斷 adoption stage
        sky = inner_dict.get("天", 0)
        thunder = inner_dict.get("雷", 0)
        earth = inner_dict.get("地", 0)
        mountain = inner_dict.get("山", 0)

        if sky > 2.0 and thunder > 2.0:
            stage = "innovator"
        elif sky > 1.0 or thunder > 1.0:
            stage = "early_adopter"
        elif earth > 2.0 and mountain > 2.0:
            stage = "laggard"
        elif earth > 1.0 or mountain > 1.0:
            stage = "late_majority"
        else:
            stage = "early_majority"

        archetype = Archetype(
            id=i,
            name=f"原型_{i:03d}",  # 暫時命名，後續由 LLM 重新命名
            description="",
            weight=round(weight, 4),
            inner_energy=EnergyVector.from_dict(inner_dict),
            outer_energy=EnergyVector.from_dict(outer_dict),
            adoption_stage=stage,
        )
        archetypes.append(archetype)

    return archetypes
