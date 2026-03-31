"""AwarenessSignal — MUSEON 統一覺察訊號格式.

所有覺察源（DendriticScorer、SkillHealthTracker、WEE、EvalEngine 等）
共用此格式，讓分診台能統一消費。

設計原則：
- 夠小才能到處生產，夠結構才能機器消費
- LLM 能讀 dict，code 能讀 dataclass
- actionability 是最關鍵的欄位——決定「覺察後該做什麼」
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


# ── 列舉型別 ──────────────────────────────────────────────────────────────────


class Severity(str, Enum):
    """訊號嚴重度，決定分診台的處理優先順序."""

    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SignalType(str, Enum):
    """訊號類型，描述覺察來自哪個維度."""

    QUALITY_DROP = "quality_drop"          # 輸出品質下降
    SKILL_DEGRADED = "skill_degraded"      # Skill 健康度退化
    HEALTH_ANOMALY = "health_anomaly"      # 系統健康異常
    SYSTEM_FAULT = "system_fault"          # 系統錯誤 / 例外
    LEARNING_GAP = "learning_gap"          # 學習空缺偵測
    BEHAVIOR_DRIFT = "behavior_drift"      # 行為偏移
    RESOURCE_STRESS = "resource_stress"    # 資源壓力


class Actionability(str, Enum):
    """覺察後的動作模式.

    AUTO  — 系統可以自動處理，不需要人介入
    PROMPT — 需要 LLM 判斷後決定如何處理
    HUMAN  — 必須推播給人類決策
    """

    AUTO = "AUTO"
    PROMPT = "PROMPT"
    HUMAN = "HUMAN"


# ── 主要 dataclass ─────────────────────────────────────────────────────────────


@dataclass
class AwarenessSignal:
    """MUSEON 統一覺察訊號.

    使用方式：
        sig = AwarenessSignal(
            source="skill_health_tracker",
            skill_name="darwin",
            severity=Severity.HIGH,
            signal_type=SignalType.SKILL_DEGRADED,
            title="darwin Skill 健康度低於門檻",
            actionability=Actionability.PROMPT,
            suggested_action="降低輸出複雜度，等候下次 Nightly 重評",
        )
        write_signal(workspace, sig)
    """

    # ── 身份 ──────────────────────────────────────────────────────────────────
    source: str
    """產生訊號的模組名稱，例如 'skill_health_tracker'"""

    title: str
    """人類可讀的訊號標題（一行）"""

    severity: Severity
    """嚴重度：INFO / LOW / MEDIUM / HIGH / CRITICAL"""

    signal_type: SignalType
    """訊號類型（覺察維度）"""

    actionability: Actionability
    """動作模式：AUTO / PROMPT / HUMAN"""

    # ── 自動填充欄位 ───────────────────────────────────────────────────────────
    signal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    """8 位十六進制唯一 ID"""

    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    """ISO 8601 建立時間（UTC）"""

    # ── 選填欄位 ───────────────────────────────────────────────────────────────
    skill_name: Optional[str] = None
    """關聯的 Skill 名稱（可為空）"""

    suggested_action: Optional[str] = None
    """建議的處理動作（自然語言描述）"""

    metric_name: Optional[str] = None
    """觸發訊號的指標名稱，例如 'health_score'"""

    metric_value: Optional[float] = None
    """目前指標值"""

    metric_baseline: Optional[float] = None
    """指標基準值（用於計算偏差）"""

    context: Dict[str, Any] = field(default_factory=dict)
    """額外上下文資訊（自由鍵值對）"""

    # ── 分診狀態 ───────────────────────────────────────────────────────────────
    status: str = "pending"
    """訊號狀態：pending / triaged / acted / dropped"""

    triage_action: Optional[str] = None
    """分診台決定的處理動作（完成分診後填入）"""

    # ── 序列化方法 ─────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """轉為 JSON 可序列化的 dict."""
        return {
            "signal_id": self.signal_id,
            "created_at": self.created_at,
            "source": self.source,
            "skill_name": self.skill_name,
            "severity": self.severity.value if isinstance(self.severity, Severity) else self.severity,
            "signal_type": self.signal_type.value if isinstance(self.signal_type, SignalType) else self.signal_type,
            "title": self.title,
            "actionability": self.actionability.value if isinstance(self.actionability, Actionability) else self.actionability,
            "suggested_action": self.suggested_action,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "metric_baseline": self.metric_baseline,
            "context": self.context,
            "status": self.status,
            "triage_action": self.triage_action,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AwarenessSignal":
        """從 dict 重建 AwarenessSignal（例如從 JSONL 讀取時）."""
        return cls(
            signal_id=data.get("signal_id", uuid.uuid4().hex[:8]),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            source=data["source"],
            skill_name=data.get("skill_name"),
            severity=Severity(data["severity"]),
            signal_type=SignalType(data["signal_type"]),
            title=data["title"],
            actionability=Actionability(data["actionability"]),
            suggested_action=data.get("suggested_action"),
            metric_name=data.get("metric_name"),
            metric_value=data.get("metric_value"),
            metric_baseline=data.get("metric_baseline"),
            context=data.get("context", {}),
            status=data.get("status", "pending"),
            triage_action=data.get("triage_action"),
        )

    def __str__(self) -> str:
        """對外安全的字串表示，不洩漏內部結構."""
        return (
            f"[{self.severity.value}] {self.title} "
            f"(id={self.signal_id}, source={self.source})"
        )
