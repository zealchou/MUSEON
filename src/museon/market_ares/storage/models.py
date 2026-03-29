"""Market Ares — 資料模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EnergyVector:
    """八方位能量向量（內在或外在）"""

    天: float = 0.0
    風: float = 0.0
    水: float = 0.0
    山: float = 0.0
    地: float = 0.0
    雷: float = 0.0
    火: float = 0.0
    澤: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "天": self.天, "風": self.風, "水": self.水, "山": self.山,
            "地": self.地, "雷": self.雷, "火": self.火, "澤": self.澤,
        }

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> EnergyVector:
        return cls(**{k: d.get(k, 0.0) for k in ("天", "風", "水", "山", "地", "雷", "火", "澤")})

    def __str__(self) -> str:
        parts = [f"{k}:{v:+.1f}" for k, v in self.to_dict().items()]
        return f"Energy({', '.join(parts)})"


@dataclass
class Archetype:
    """一個人群原型"""

    id: int
    name: str
    description: str
    weight: float  # 在地區人口中的佔比（0-1）

    inner_energy: EnergyVector = field(default_factory=EnergyVector)
    outer_energy: EnergyVector = field(default_factory=EnergyVector)

    adoption_stage: str = "early_majority"
    # innovator / early_adopter / early_majority / late_majority / laggard

    purchase_triggers: list[str] = field(default_factory=list)
    resistance_triggers: list[str] = field(default_factory=list)
    influence_targets: list[int] = field(default_factory=list)
    influenced_by: list[int] = field(default_factory=list)

    # 模擬中動態變化的狀態
    awareness_state: str = "unaware"
    current_inner: Optional[EnergyVector] = None
    current_outer: Optional[EnergyVector] = None

    def __post_init__(self):
        if self.current_inner is None:
            self.current_inner = EnergyVector(**self.inner_energy.to_dict())
        if self.current_outer is None:
            self.current_outer = EnergyVector(**self.outer_energy.to_dict())


@dataclass
class CompetitorAgent:
    """競爭者 Agent"""

    id: str
    name: str
    market_share: float
    energy_profile: EnergyVector = field(default_factory=EnergyVector)

    reaction_style: str = "analytical"  # aggressive / analytical / defensive
    reaction_threshold: float = 0.05  # 市佔率下降超過此比例觸發反應

    last_action: Optional[str] = None
    last_action_week: int = -1


@dataclass
class PartnerAgent:
    """生態夥伴 Agent"""

    id: str
    name: str
    role: str  # supplier / distributor / platform
    cooperation_score: float = 0.7  # 配合度（0-1）

    energy_profile: EnergyVector = field(default_factory=EnergyVector)
    interest_alignment: float = 0.5  # 利益一致性（0-1）


@dataclass
class StrategyVector:
    """策略向量：每個方位的刺激強度"""

    impact: EnergyVector = field(default_factory=EnergyVector)

    # SMART 屬性
    specific: str = ""
    measurable: str = ""
    achievable: str = ""
    relevant: str = ""
    time_bound: str = ""

    city: str = ""
    country: str = "台灣"


@dataclass
class WeeklySnapshot:
    """每週快照"""

    week: int
    archetype_states: dict  # {archetype_id: {awareness_state, current_inner, current_outer}}
    business_metrics: dict  # {revenue, market_share, fans, reputation_score, ...}
    competitor_actions: list[dict]
    partner_attitudes: list[dict]
    events: list[dict]
    insight: str = ""  # LLM 生成的洞察
    is_turning_point: bool = False


@dataclass
class SimulationResult:
    """完整模擬結果"""

    simulation_id: str
    region_id: str
    strategy: StrategyVector
    mode: str  # self_drive / chauffeur
    round_number: int
    snapshots: list[WeeklySnapshot] = field(default_factory=list)
    status: str = "pending"  # pending / running / completed / aborted
