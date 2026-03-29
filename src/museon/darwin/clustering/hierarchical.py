"""Market Ares — 階層式聚類

Step 1: 對 16 維能量向量跑階層式聚類
Step 2: 產出樹狀圖，找自然斷點
Step 3: 輸出建議的群數（64-512 之間）
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

from museon.darwin.config import ARCHETYPE_MAX, ARCHETYPE_MIN

logger = logging.getLogger(__name__)


def build_energy_matrix(
    inner_vectors: list[dict[str, float]],
    outer_vectors: list[dict[str, float]],
) -> np.ndarray:
    """將內外在能量向量合併為 16 維矩陣

    Args:
        inner_vectors: 每筆數據的內在八方位 [{天: x, 風: y, ...}, ...]
        outer_vectors: 每筆數據的外在八方位

    Returns:
        (N, 16) 的 numpy 矩陣
    """
    primals = ("天", "風", "水", "山", "地", "雷", "火", "澤")
    rows = []
    for inner, outer in zip(inner_vectors, outer_vectors):
        row = [inner.get(p, 0.0) for p in primals] + [outer.get(p, 0.0) for p in primals]
        rows.append(row)
    return np.array(rows, dtype=np.float64)


def run_hierarchical(
    matrix: np.ndarray,
    method: str = "ward",
) -> np.ndarray:
    """執行階層式聚類

    Args:
        matrix: (N, 16) 能量矩陣
        method: 聚類方法（ward / complete / average）

    Returns:
        linkage matrix（scipy 格式）
    """
    if matrix.shape[0] < 2:
        raise ValueError(f"至少需要 2 筆數據，收到 {matrix.shape[0]}")

    logger.info(f"開始階層式聚類：{matrix.shape[0]} 筆 × {matrix.shape[1]} 維，方法={method}")
    Z = linkage(matrix, method=method, metric="euclidean")
    logger.info("階層式聚類完成")
    return Z


def find_natural_cutoff(
    Z: np.ndarray,
    min_k: int = ARCHETYPE_MIN,
    max_k: int = ARCHETYPE_MAX,
) -> int:
    """找自然斷點：合併損失曲線的最大跳躍

    掃描 min_k 到 max_k 之間的群數，找到 merge distance 跳躍最大的位置。

    Args:
        Z: linkage matrix
        min_k: 最小群數
        max_k: 最大群數

    Returns:
        建議的群數
    """
    n = Z.shape[0] + 1  # 原始數據點數量
    max_k = min(max_k, n)
    min_k = min(min_k, n)

    if min_k >= max_k:
        return min_k

    # Z 的第三欄是 merge distance，倒序排列可得到不同 k 的 distance
    distances = Z[:, 2]

    # 從 n 群到 1 群的 merge distance
    # k=n → distance[0], k=n-1 → distance[1], ...
    # k 群時的 merge distance = distances[n-k]

    best_k = min_k
    max_jump = 0.0

    for k in range(min_k, max_k):
        idx = n - k - 1
        if idx < 0 or idx >= len(distances) - 1:
            continue
        jump = distances[idx + 1] - distances[idx]
        if jump > max_jump:
            max_jump = jump
            best_k = k

    logger.info(f"自然斷點：k={best_k}（最大跳躍={max_jump:.4f}）")
    return best_k


def cut_tree(Z: np.ndarray, k: int) -> np.ndarray:
    """在指定群數切割樹狀圖

    Args:
        Z: linkage matrix
        k: 目標群數

    Returns:
        (N,) 陣列，每筆數據的群組標籤（0-indexed）
    """
    labels = fcluster(Z, t=k, criterion="maxclust")
    # fcluster 是 1-indexed，轉 0-indexed
    return labels - 1


def compute_cluster_centers(
    matrix: np.ndarray,
    labels: np.ndarray,
    k: int,
) -> tuple[np.ndarray, np.ndarray]:
    """計算每個群的中心向量和權重

    Args:
        matrix: (N, 16) 能量矩陣
        labels: (N,) 群組標籤
        k: 群數

    Returns:
        (centers, weights): centers=(k, 16), weights=(k,) 各群佔比
    """
    centers = np.zeros((k, matrix.shape[1]))
    weights = np.zeros(k)

    for i in range(k):
        mask = labels == i
        count = mask.sum()
        if count > 0:
            centers[i] = matrix[mask].mean(axis=0)
            weights[i] = count / len(labels)

    return centers, weights
