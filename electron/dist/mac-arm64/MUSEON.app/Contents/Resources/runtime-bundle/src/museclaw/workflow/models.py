"""Workflow 共用資料模型.

FourDScore, WorkflowRecord, ExecutionRecord 以及生命週期常數。
被 WorkflowEngine 和 WEEEngine 共用。
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════
# 生命週期常數
# ═══════════════════════════════════════════

LIFECYCLE_STAGES = (
    "birth",
    "growth",
    "maturity",
    "plateau",
    "evolution",
    "archived",
)

LIFECYCLE_TO_LAYER = {
    "birth": "L0_buffer",
    "growth": "L2_ep",
    "maturity": "L2_sem",
    "plateau": "L2_sem",
    "evolution": "L5_scratch",
    "archived": "L3_procedural",
}

# 自動遷轉閾值
BIRTH_TO_GROWTH_SUCCESS = 3
GROWTH_TO_MATURITY_SUCCESS = 8
GROWTH_TO_MATURITY_AVG = 7.0

# 高原偵測
PLATEAU_MIN_RUNS = 5
PLATEAU_MAX_VARIANCE = 0.5
PLATEAU_MAX_AVG = 7.0

# 滾動平均
ROLLING_WINDOW = 5


# ═══════════════════════════════════════════
# FourDScore — 四維分數
# ═══════════════════════════════════════════


@dataclass
class FourDScore:
    """4D 分數（speed, quality, alignment, leverage）.

    每個維度 0-10 分，composite 為四維幾何平均。
    """

    speed: float = 5.0
    quality: float = 5.0
    alignment: float = 5.0
    leverage: float = 4.0

    @property
    def composite(self) -> float:
        """幾何平均: (S × Q × A × L) ^ 0.25."""
        product = self.speed * self.quality * self.alignment * self.leverage
        if product <= 0:
            return 0.0
        return product ** 0.25

    def clamp(self) -> "FourDScore":
        """將所有分數限制在 [0, 10] 範圍."""
        self.speed = max(0.0, min(10.0, self.speed))
        self.quality = max(0.0, min(10.0, self.quality))
        self.alignment = max(0.0, min(10.0, self.alignment))
        self.leverage = max(0.0, min(10.0, self.leverage))
        return self

    def to_dict(self) -> Dict[str, float]:
        """轉換為 dict."""
        return {
            "speed": self.speed,
            "quality": self.quality,
            "alignment": self.alignment,
            "leverage": self.leverage,
            "composite": self.composite,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FourDScore":
        """從 dict 建構."""
        return cls(
            speed=float(d.get("speed", 5.0)),
            quality=float(d.get("quality", 5.0)),
            alignment=float(d.get("alignment", 5.0)),
            leverage=float(d.get("leverage", 4.0)),
        )


# ═══════════════════════════════════════════
# WorkflowRecord — 工作流狀態記錄
# ═══════════════════════════════════════════


@dataclass
class WorkflowRecord:
    """工作流狀態記錄（對應 SQLite workflows 表）."""

    workflow_id: str = ""
    user_id: str = ""
    name: str = ""
    lifecycle: str = "birth"
    success_count: int = 0
    total_runs: int = 0
    avg_composite: float = 0.0
    variance: float = 0.0
    baseline_composite: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    @property
    def memory_layer(self) -> str:
        """對應記憶層."""
        return LIFECYCLE_TO_LAYER.get(self.lifecycle, "L0_buffer")

    def to_dict(self) -> Dict[str, Any]:
        """轉換為 dict."""
        return {
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "name": self.name,
            "lifecycle": self.lifecycle,
            "success_count": self.success_count,
            "total_runs": self.total_runs,
            "avg_composite": round(self.avg_composite, 4),
            "variance": round(self.variance, 4),
            "baseline_composite": self.baseline_composite,
            "tags": self.tags,
            "memory_layer": self.memory_layer,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ═══════════════════════════════════════════
# ExecutionRecord — 單次執行記錄
# ═══════════════════════════════════════════


@dataclass
class ExecutionRecord:
    """單次執行記錄（對應 SQLite executions 表）."""

    execution_id: str = ""
    workflow_id: str = ""
    user_id: str = ""
    speed: float = 5.0
    quality: float = 5.0
    alignment: float = 5.0
    leverage: float = 4.0
    composite: float = 0.0
    outcome: str = "success"
    context: str = ""
    created_at: str = ""

    @property
    def score(self) -> FourDScore:
        """取得 FourDScore."""
        return FourDScore(
            speed=self.speed,
            quality=self.quality,
            alignment=self.alignment,
            leverage=self.leverage,
        )

    def to_dict(self) -> Dict[str, Any]:
        """轉換為 dict."""
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "user_id": self.user_id,
            "speed": self.speed,
            "quality": self.quality,
            "alignment": self.alignment,
            "leverage": self.leverage,
            "composite": round(self.composite, 4),
            "outcome": self.outcome,
            "context": self.context,
            "created_at": self.created_at,
        }
