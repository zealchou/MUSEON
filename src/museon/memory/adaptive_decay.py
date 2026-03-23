"""AdaptiveDecay — ACT-R 啟發的統一衰減引擎.

Project Epigenesis 迭代 4：DNA 的「遺忘是功能，不是缺陷」。

設計原則（ACT-R Base-Level Activation）：
  B_i = ln(Σ t_j^{-d}) + β_i

  - t_j = 距離第 j 次存取的時間（天）
  - d = 衰減率（預設 0.5，人類認知實驗值）
  - β_i = 情感/重要性加成

存取越頻繁 → 越不容易遺忘
情感越強烈 → 越不容易遺忘
時間越久遠 → 越容易沉降（但不刪除）

此引擎不刪除任何記憶——只調整 activation_level。
高 activation 的記憶在回憶時更容易被找到。
低 activation 的記憶沉降，但永遠可被直接查詢。

消費者：nightly_pipeline.py 每日呼叫 sweep()
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# ACT-R 衰減率（d）：人類認知實驗標準值
DECAY_RATE: float = 0.5

# 情感加成映射：Soul Ring reinforcement_count → β 加成
REINFORCEMENT_BONUS = {
    0: 0.0,     # 無強化
    1: 0.3,     # 曾被強化 1 次
    2: 0.6,     # 曾被強化 2 次
    3: 1.0,     # 3+ 次強化（重要記憶）
}

# 年輪類型加成
RING_TYPE_BONUS = {
    "failure_lesson": 1.0,       # 失敗教訓最不應被遺忘
    "value_calibration": 0.8,    # 價值校準
    "cognitive_breakthrough": 0.5,  # 認知突破
    "service_milestone": 0.3,    # 服務里程碑
}

# entry_type 加成
ENTRY_TYPE_BONUS = {
    "event": 0.3,          # 即時事件
    "reflection": 0.5,     # 反思（更有價值）
    "daily_summary": 0.1,  # 每日摘要（常規）
}

# 最低 activation（不會衰減到零以下）
MIN_ACTIVATION: float = -5.0

# activation 閾值：低於此值視為「沉降」
DORMANT_THRESHOLD: float = -2.0


# ═══════════════════════════════════════════
# 資料結構
# ═══════════════════════════════════════════

@dataclass
class ActivationRecord:
    """單條記憶的活化度記錄."""
    memory_id: str            # 唯一 ID（hash / CUID / doc_id）
    memory_type: str          # "soul_ring" / "crystal" / "memory_item"
    created_at: str           # ISO8601 建立時間
    access_timestamps: List[str] = field(default_factory=list)  # 每次被存取的時間戳
    activation_level: float = 0.0  # 當前活化度
    emotional_bonus: float = 0.0   # 情感加成 β_i
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════
# 核心計算
# ═══════════════════════════════════════════

def compute_base_level_activation(
    access_days_ago: List[float],
    decay_rate: float = DECAY_RATE,
    emotional_bonus: float = 0.0,
) -> float:
    """計算 ACT-R Base-Level Activation.

    B_i = ln(Σ t_j^{-d}) + β_i

    Args:
        access_days_ago: 每次存取距今的天數列表（必須 > 0）
        decay_rate: 衰減率 d
        emotional_bonus: 情感加成 β_i

    Returns:
        activation 值（越高越容易被召回）
    """
    if not access_days_ago:
        return MIN_ACTIVATION + emotional_bonus

    # 過濾掉 <= 0 的值（當天存取視為 0.1 天）
    valid_times = [max(t, 0.1) for t in access_days_ago]

    summation = sum(t ** (-decay_rate) for t in valid_times)

    if summation <= 0:
        return MIN_ACTIVATION + emotional_bonus

    return math.log(summation) + emotional_bonus


def compute_emotional_bonus(
    ring_type: Optional[str] = None,
    entry_type: Optional[str] = None,
    reinforcement_count: int = 0,
) -> float:
    """計算情感/重要性加成 β_i.

    Args:
        ring_type: Soul Ring 類型
        entry_type: 條目類型
        reinforcement_count: 強化次數

    Returns:
        β_i 值
    """
    bonus = 0.0

    # 年輪類型加成
    if ring_type:
        bonus += RING_TYPE_BONUS.get(ring_type, 0.0)

    # entry_type 加成
    if entry_type:
        bonus += ENTRY_TYPE_BONUS.get(entry_type, 0.0)

    # 強化次數加成（上限 3）
    capped = min(reinforcement_count, 3)
    bonus += REINFORCEMENT_BONUS.get(capped, 1.0)

    return bonus


# ═══════════════════════════════════════════
# AdaptiveDecay Engine
# ═══════════════════════════════════════════

class AdaptiveDecay:
    """ACT-R 式統一衰減引擎.

    不刪除任何記憶，只調整 activation_level。
    由 nightly_pipeline 每日呼叫 sweep()。

    設計模式：
    - 無狀態計算引擎（不持有記憶資料）
    - 接收記憶列表 → 計算 activation → 回傳排序結果
    - 消費者決定如何使用 activation（篩選/排序/標記）
    """

    def __init__(self, decay_rate: float = DECAY_RATE) -> None:
        self._decay_rate = decay_rate

    def compute_activation(
        self,
        created_at: str,
        access_timestamps: Optional[List[str]] = None,
        ring_type: Optional[str] = None,
        entry_type: Optional[str] = None,
        reinforcement_count: int = 0,
        now: Optional[datetime] = None,
    ) -> float:
        """計算單條記憶的 activation level.

        Args:
            created_at: 記憶建立時間（ISO8601）
            access_timestamps: 存取時間戳列表（ISO8601）
            ring_type: Soul Ring 類型
            entry_type: 條目類型
            reinforcement_count: 強化次數
            now: 當前時間（預設 datetime.now()，方便測試注入）

        Returns:
            activation 值
        """
        now = now or datetime.now()

        # 計算每次存取距今的天數
        timestamps = list(access_timestamps or [])
        if created_at and created_at not in timestamps:
            timestamps.insert(0, created_at)  # 建立時間也算一次存取

        days_ago = []
        for ts in timestamps:
            try:
                dt = datetime.fromisoformat(ts)
                delta = (now - dt).total_seconds() / 86400.0  # 轉換為天
                days_ago.append(max(delta, 0.1))
            except (ValueError, TypeError):
                continue

        # 情感加成
        bonus = compute_emotional_bonus(
            ring_type=ring_type,
            entry_type=entry_type,
            reinforcement_count=reinforcement_count,
        )

        return compute_base_level_activation(
            days_ago,
            decay_rate=self._decay_rate,
            emotional_bonus=bonus,
        )

    def rank_by_activation(
        self,
        memories: List[Dict[str, Any]],
        now: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """根據 activation level 對記憶列表排序.

        Args:
            memories: 記憶列表，每筆需包含：
                - created_at: str
                - access_timestamps: Optional[List[str]]
                - type / ring_type: Optional[str]
                - entry_type: Optional[str]
                - reinforcement_count: Optional[int]
            now: 當前時間

        Returns:
            按 activation 降序排列的記憶列表，
            每筆新增 "_activation" 欄位
        """
        for mem in memories:
            activation = self.compute_activation(
                created_at=mem.get("created_at", ""),
                access_timestamps=mem.get("access_timestamps"),
                ring_type=mem.get("type") or mem.get("ring_type"),
                entry_type=mem.get("entry_type"),
                reinforcement_count=mem.get("reinforcement_count", 0),
                now=now,
            )
            mem["_activation"] = round(activation, 4)

        return sorted(memories, key=lambda m: m.get("_activation", MIN_ACTIVATION), reverse=True)

    def classify_dormancy(
        self,
        memories: List[Dict[str, Any]],
        dormant_threshold: float = DORMANT_THRESHOLD,
        now: Optional[datetime] = None,
    ) -> Tuple[List[Dict], List[Dict]]:
        """將記憶分為「活躍」和「沉降」兩組.

        Args:
            memories: 記憶列表
            dormant_threshold: 沉降閾值
            now: 當前時間

        Returns:
            (active_memories, dormant_memories)
        """
        ranked = self.rank_by_activation(memories, now=now)

        active = [m for m in ranked if m.get("_activation", 0) >= dormant_threshold]
        dormant = [m for m in ranked if m.get("_activation", 0) < dormant_threshold]

        logger.debug(
            f"AdaptiveDecay classify | "
            f"active={len(active)} | dormant={len(dormant)}"
        )
        return active, dormant
