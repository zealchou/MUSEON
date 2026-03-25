"""PDR (Progressive Depth Response) Tuning Parameters.

可由 MuseQA 全自動調控的 PDR 管線參數。
每個參數有硬上下限、locked 標記、冷卻期。

持久化：data/_system/pdr_params.json
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 參數硬護欄定義：{param_name: (min_val, max_val, default)}
_PARAM_BOUNDS = {
    "phase0_enabled": (None, None, True),
    "phase0_max_tokens": (30, 150, 80),
    "phase2_trigger_loops": (None, None, ("EXPLORATION_LOOP", "SLOW_LOOP")),
    "phase2_confidence_threshold": (0.2, 0.95, 0.6),
    "phase2_advisor_count": (1, 4, 3),
    "phase2_upgrade_rate_limit": (3, 30, 10),
    "phase3_trigger_qscore": (0.3, 0.8, 0.5),
    "phase3_daily_budget": (1, 20, 5),
    "proactive_skill_expand": (None, None, True),
    "proactive_tool_invoke": (None, None, True),
    "proactive_workflow_trigger": (None, None, True),
    "proactive_forge_trigger": (None, None, True),
    "cost_multiplier": (0.5, 3.0, 1.0),
    "feature_flag": (None, None, False),
}

# MuseQA 單次調幅上限
_MAX_ADJUSTMENT_RATIO = 0.20  # +-20%

# 冷卻期（秒）
_COOLDOWN_SECONDS = 1800  # 30 分鐘


@dataclass
class PDRTuningParams:
    """PDR 可調參數."""

    # Phase 0
    phase0_enabled: bool = True
    phase0_max_tokens: int = 80

    # Phase 2
    phase2_trigger_loops: tuple = ("EXPLORATION_LOOP", "SLOW_LOOP")
    phase2_confidence_threshold: float = 0.6
    phase2_advisor_count: int = 3
    phase2_upgrade_rate_limit: int = 10  # per hour

    # Phase 3
    phase3_trigger_qscore: float = 0.5
    phase3_daily_budget: int = 5

    # Proactive
    proactive_skill_expand: bool = True
    proactive_tool_invoke: bool = True
    proactive_workflow_trigger: bool = True
    proactive_forge_trigger: bool = True

    # Global
    cost_multiplier: float = 1.0
    feature_flag: bool = False  # master switch

    # Internal tracking (not user-facing)
    _locked: Dict[str, bool] = field(default_factory=dict)
    _last_adjusted: Dict[str, float] = field(default_factory=dict)

    def is_locked(self, param: str) -> bool:
        """Check if a parameter is locked by the user."""
        return self._locked.get(param, False)

    def lock(self, param: str) -> None:
        """Lock a parameter (user override, MuseQA cannot change)."""
        self._locked[param] = True

    def unlock(self, param: str) -> None:
        """Unlock a parameter."""
        self._locked.pop(param, None)

    def can_adjust(self, param: str) -> bool:
        """Check if MuseQA can adjust this parameter now."""
        if self.is_locked(param):
            return False
        last = self._last_adjusted.get(param, 0)
        if time.time() - last < _COOLDOWN_SECONDS:
            return False
        return True

    def adjust(self, param: str, new_value: Any) -> bool:
        """Safely adjust a parameter within bounds.

        Returns True if adjustment was applied, False if rejected.
        """
        if not self.can_adjust(param):
            logger.info(f"[PDR] Adjustment rejected: {param} is locked or in cooldown")
            return False

        if param not in _PARAM_BOUNDS:
            logger.warning(f"[PDR] Unknown parameter: {param}")
            return False

        min_val, max_val, default = _PARAM_BOUNDS[param]
        old_value = getattr(self, param, default)

        # Bool parameters: no bounds check
        if isinstance(old_value, bool):
            setattr(self, param, bool(new_value))
            self._last_adjusted[param] = time.time()
            return True

        # Numeric: enforce bounds + max adjustment ratio
        if min_val is not None and new_value < min_val:
            new_value = min_val
        if max_val is not None and new_value > max_val:
            new_value = max_val

        # Max adjustment ratio check
        if old_value != 0:
            ratio = abs(new_value - old_value) / abs(old_value)
            if ratio > _MAX_ADJUSTMENT_RATIO:
                # Clamp to max ratio
                direction = 1 if new_value > old_value else -1
                new_value = old_value * (1 + direction * _MAX_ADJUSTMENT_RATIO)
                if min_val is not None:
                    new_value = max(new_value, min_val)
                if max_val is not None:
                    new_value = min(new_value, max_val)

        # Apply type-consistent value
        if isinstance(old_value, int):
            new_value = int(round(new_value))
        elif isinstance(old_value, float):
            new_value = round(float(new_value), 4)

        setattr(self, param, new_value)
        self._last_adjusted[param] = time.time()
        logger.info(f"[PDR] Adjusted {param}: {old_value} -> {new_value}")
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON persistence."""
        d = {}
        for k, v in asdict(self).items():
            if not k.startswith("_"):
                d[k] = v
        d["_locked"] = dict(self._locked)
        d["_last_adjusted"] = dict(self._last_adjusted)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDRTuningParams":
        """Deserialize from JSON."""
        locked = data.pop("_locked", {})
        last_adj = data.pop("_last_adjusted", {})
        # Filter only known fields
        known = {f.name for f in cls.__dataclass_fields__.values() if not f.name.startswith("_")}
        clean = {k: v for k, v in data.items() if k in known}
        params = cls(**clean)
        params._locked = locked
        params._last_adjusted = last_adj
        return params


@dataclass
class PDRAdjustment:
    """A single parameter adjustment record (for audit log)."""

    param: str
    old_value: Any
    new_value: Any
    reason: str
    source: str = "museqa"  # "museqa" | "user" | "nightly"
    timestamp: float = 0.0
    before_avg_qscore: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProactiveAction:
    """An action triggered by the nine advisors council."""

    type: str  # "skill_invoke" | "tool_use" | "workflow" | "agent_dispatch" | "forge"
    target: str  # skill name / tool name / agent registry ID
    reason: str
    priority: int = 1  # 0=immediate, 1=background, 2=suggest to user
    input_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PDRVerdict:
    """Result of the nine advisors council review."""

    KEEP = "KEEP"
    EDIT = "EDIT"
    APPEND = "APPEND"
    REPLACE = "REPLACE"
    ACTION = "ACTION"

    def __init__(
        self,
        verdict: str,
        supplement: str = "",
        actions: Optional[list] = None,
        advisor_scores: Optional[Dict[str, float]] = None,
        reasoning: str = "",
    ):
        self.verdict = verdict
        self.supplement = supplement  # text to append/edit
        self.actions = actions or []  # List[ProactiveAction]
        self.advisor_scores = advisor_scores or {}
        self.reasoning = reasoning

    @property
    def should_deepen(self) -> bool:
        """Whether Phase 3 deep thinking should be triggered."""
        avg = sum(self.advisor_scores.values()) / max(len(self.advisor_scores), 1)
        return avg < 5.0  # average quality score below 5/10

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict,
            "supplement": self.supplement,
            "actions": [a.to_dict() for a in self.actions],
            "advisor_scores": self.advisor_scores,
            "reasoning": self.reasoning,
            "should_deepen": self.should_deepen,
        }


# ═══════════════════════════════════════
# Singleton + Persistence
# ═══════════════════════════════════════

_instance: Optional[PDRTuningParams] = None
_persist_path: Optional[Path] = None


def init_pdr_params(data_dir: str) -> PDRTuningParams:
    """Initialize PDR params from persistent storage."""
    global _instance, _persist_path
    _persist_path = Path(data_dir) / "_system" / "pdr_params.json"
    if _persist_path.exists():
        try:
            with open(_persist_path) as f:
                _instance = PDRTuningParams.from_dict(json.load(f))
            logger.info(f"[PDR] Params loaded: feature_flag={_instance.feature_flag}")
        except Exception as e:
            logger.warning(f"[PDR] Failed to load params, using defaults: {e}")
            _instance = PDRTuningParams()
    else:
        _instance = PDRTuningParams()
        save_pdr_params()
    return _instance


def get_pdr_params() -> PDRTuningParams:
    """Get current PDR params (lazy init with defaults if not initialized)."""
    global _instance
    if _instance is None:
        _instance = PDRTuningParams()
    return _instance


def save_pdr_params() -> None:
    """Persist current params to disk."""
    if _instance and _persist_path:
        try:
            _persist_path.parent.mkdir(parents=True, exist_ok=True)
            with open(_persist_path, "w") as f:
                json.dump(_instance.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"[PDR] Failed to save params: {e}")
