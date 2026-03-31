"""Mask Engine — per-conversation personality adaptation.

Provides temporary trait offsets based on the current conversation partner's
energy level, communication style, and needs. Offsets decay back toward zero
when the conversation ends or the partner hasn't interacted for a while.

Key constraints:
- Maximum offset: ±0.15 per dimension (prevents persona capture)
- Decay rate: 80% per conversation end
- Full decay: 7 days without interaction → mask resets to zero
- Only affects presentation (tone/pace/depth), NOT core values
"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_MASK_OFFSET: float = 0.15   # Max deviation from Core Self per dimension
SESSION_DECAY: float = 0.80     # 80% decay at end of each conversation
FULL_DECAY_DAYS: int = 7        # Days without interaction → full reset

# P5_autonomy is excluded: MUSEON's autonomy must not bend to please users.
# It only changes through Nightly Reflection (trait_engine PSI path).
_EXCLUDED_FROM_MASK = {"P5_autonomy"}

# Traits that are maps/non-numeric (e.g., C3_domain_depth) — skip masking
_NON_NUMERIC_TRAITS = {"C3_domain_depth"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MaskState:
    """Per-user mask state."""

    user_id: str
    offsets: Dict[str, float]       # {trait_id: float} — current offsets from Core Self
    last_interaction: str           # ISO timestamp
    interaction_count: int = 0

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "offsets": self.offsets,
            "last_interaction": self.last_interaction,
            "interaction_count": self.interaction_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MaskState":
        return cls(
            user_id=d["user_id"],
            offsets=d.get("offsets", {}),
            last_interaction=d.get("last_interaction", datetime.now(timezone.utc).isoformat()),
            interaction_count=d.get("interaction_count", 0),
        )


# ---------------------------------------------------------------------------
# MaskEngine
# ---------------------------------------------------------------------------

class MaskEngine:
    """Per-conversation personality adaptation layer.

    Usage:
        engine = MaskEngine(workspace)
        offsets = engine.activate(user_id, user_energy, user_primals, core_traits)
        effective = engine.get_effective_traits(core_traits, user_id)
        # … conversation …
        engine.decay_session(user_id)
    """

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)
        self._path = self._workspace / "_system" / "mask_states.json"
        self._states: Dict[str, MaskState] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate(
        self,
        user_id: str,
        user_energy: str,
        user_primals: Dict[str, Any],
        core_traits: Dict[str, Any],
    ) -> Dict[str, float]:
        """Called at start of conversation.

        Compute mask offsets based on user's characteristics, blend with any
        existing offset history, and return the final offsets dict.

        Args:
            user_id:      Unique identifier for this conversation partner.
            user_energy:  "LOW", "MEDIUM", or "HIGH".
            user_primals: Dict of primal scores, e.g. {"boundary": 70, "curiosity": 80}.
            core_traits:  Current core trait dict (used to know which traits exist).

        Returns:
            Dict mapping trait_id → offset float.
        """
        computed = self._compute_offsets(user_energy, user_primals)

        # Blend with existing offsets (gradual adaptation memory)
        existing = self._states.get(user_id)
        if existing:
            blended: Dict[str, float] = {}
            all_keys = set(existing.offsets) | set(computed)
            for trait_id in all_keys:
                old = existing.offsets.get(trait_id, 0.0)
                new = computed.get(trait_id, 0.0)
                blended[trait_id] = old * 0.5 + new * 0.5
            final_offsets = blended
        else:
            final_offsets = computed

        # Clamp all offsets
        final_offsets = {
            tid: max(-MAX_MASK_OFFSET, min(MAX_MASK_OFFSET, v))
            for tid, v in final_offsets.items()
        }

        now_iso = datetime.now(timezone.utc).isoformat()
        if existing:
            existing.offsets = final_offsets
            existing.last_interaction = now_iso
            existing.interaction_count += 1
        else:
            self._states[user_id] = MaskState(
                user_id=user_id,
                offsets=final_offsets,
                last_interaction=now_iso,
                interaction_count=1,
            )

        self._save()
        logger.debug("MaskEngine.activate user=%s offsets=%s", user_id, final_offsets)
        return final_offsets

    def get_effective_traits(
        self,
        core_traits: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]:
        """Compute effective trait values = core + mask offset.

        Traits in _EXCLUDED_FROM_MASK or _NON_NUMERIC_TRAITS are returned
        unchanged.

        Args:
            core_traits: The raw core trait dict from soul_ring / trait_engine.
            user_id:     The conversation partner's ID.

        Returns:
            New dict with same structure, numeric trait values shifted by offsets.
        """
        effective: Dict[str, Any] = {}
        mask = self._states.get(user_id)

        for trait_id, trait_data in core_traits.items():
            # Non-numeric traits (e.g. domain depth maps) pass through unchanged
            if trait_id in _NON_NUMERIC_TRAITS:
                effective[trait_id] = trait_data
                continue

            # Non-dict entries pass through unchanged
            if not isinstance(trait_data, dict):
                effective[trait_id] = trait_data
                continue

            # Excluded traits (P5_autonomy) pass through unchanged
            if trait_id in _EXCLUDED_FROM_MASK:
                effective[trait_id] = trait_data
                continue

            base_value = trait_data.get("value", 0.5)
            offset = mask.offsets.get(trait_id, 0.0) if mask else 0.0
            effective[trait_id] = {
                **trait_data,
                "value": max(0.0, min(1.0, base_value + offset)),
                "_mask_offset": offset,  # For debugging/logging
            }

        return effective

    def decay_session(self, user_id: str) -> None:
        """Called at end of conversation. Decay offsets by SESSION_DECAY (80%)."""
        mask = self._states.get(user_id)
        if mask:
            for trait_id in mask.offsets:
                # 80% decay → multiply by 0.2
                mask.offsets[trait_id] *= (1.0 - SESSION_DECAY)
            logger.debug(
                "MaskEngine.decay_session user=%s remaining_offsets=%s",
                user_id,
                mask.offsets,
            )
            self._save()

    def cleanup_stale(self) -> List[str]:
        """Called periodically (e.g., Nightly). Remove masks unused for FULL_DECAY_DAYS.

        Returns:
            List of removed user_ids.
        """
        now = datetime.now(timezone.utc)
        stale_users: List[str] = []

        for uid, mask in self._states.items():
            try:
                last = datetime.fromisoformat(mask.last_interaction)
                # Ensure timezone-aware comparison
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (now - last).days >= FULL_DECAY_DAYS:
                    stale_users.append(uid)
            except (ValueError, TypeError) as e:
                logger.warning("MaskEngine: bad timestamp for %s: %s", uid, e)
                stale_users.append(uid)  # Corrupt state → remove

        for uid in stale_users:
            del self._states[uid]

        if stale_users:
            self._save()
            logger.info("MaskEngine.cleanup_stale removed %d stale masks: %s", len(stale_users), stale_users)

        return stale_users

    def get_state(self, user_id: str) -> Optional[MaskState]:
        """Return current mask state for a user, or None if no state exists."""
        return self._states.get(user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_offsets(
        self,
        user_energy: str,
        user_primals: Dict[str, Any],
    ) -> Dict[str, float]:
        """Apply adaptation heuristics to produce raw offset dict."""
        offsets: Dict[str, float] = {}

        energy = (user_energy or "").upper()

        # Energy-based adaptations
        if energy == "LOW":
            offsets["P1_warmth"] = offsets.get("P1_warmth", 0.0) + 0.10   # Be warmer
            offsets["P4_depth"] = offsets.get("P4_depth", 0.0) - 0.05     # Be lighter
        elif energy == "HIGH":
            offsets["P3_initiative"] = offsets.get("P3_initiative", 0.0) + 0.05  # Match energy

        # Primal-based adaptations
        boundary = _safe_float(user_primals.get("boundary", 0))
        emotion_pattern = _safe_float(user_primals.get("emotion_pattern", 0))
        action_power = _safe_float(user_primals.get("action_power", 0))
        curiosity = _safe_float(user_primals.get("curiosity", 0))

        if boundary > 60:
            offsets["P2_directness"] = offsets.get("P2_directness", 0.0) - 0.05  # Be less direct

        if emotion_pattern > 60:
            offsets["P1_warmth"] = offsets.get("P1_warmth", 0.0) + 0.08

        if action_power > 60:
            offsets["P4_depth"] = offsets.get("P4_depth", 0.0) - 0.03  # Be more practical

        if curiosity > 60:
            offsets["P4_depth"] = offsets.get("P4_depth", 0.0) + 0.05  # Go deeper

        # Clamp raw offsets before returning
        return {
            tid: max(-MAX_MASK_OFFSET, min(MAX_MASK_OFFSET, v))
            for tid, v in offsets.items()
        }

    def _save(self) -> None:
        """Atomically save mask states to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {uid: state.to_dict() for uid, state in self._states.items()}
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=".mask_states_", suffix=".json"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            # Clean up temp file if rename failed
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _load(self) -> None:
        """Load mask states from disk. Creates empty state if file missing."""
        if not self._path.exists():
            logger.debug("MaskEngine: no existing mask_states.json at %s", self._path)
            self._states = {}
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._states = {uid: MaskState.from_dict(v) for uid, v in data.items()}
            logger.debug("MaskEngine: loaded %d mask states", len(self._states))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error("MaskEngine: failed to load mask states: %s — starting fresh", e)
            self._states = {}


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float, returning default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
