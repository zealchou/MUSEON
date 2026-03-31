"""Momentum Brake — prevents runaway personality trait evolution.

Two safety mechanisms:
1. Single-step cap: No single update can change a trait by more than ±DELTA_CAP
2. Momentum cap: 7-day cumulative change cannot exceed ±MOMENTUM_CAP

On trigger: clips the delta to the cap (does NOT reject the write).
This is different from KernelGuard which can DENY writes.

Also provides directional drift detection: if a trait has been moving
in the same direction for too long, it flags a warning.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DELTA_CAP = 0.05          # Max change per single update
MOMENTUM_CAP = 0.20       # Max 7-day cumulative change per trait
WINDOW_DAYS = 7           # Lookback window for momentum
DIRECTION_ALERT_DAYS = 5  # Consecutive same-direction days → warning


class MomentumBrake:
    """Stateless brake that clips trait deltas to prevent runaway evolution.

    No internal state — all computation reads from trait_history passed
    as parameters. Safe for concurrent use across Nightly and TraitEngine.
    """

    def check_and_clip(
        self,
        trait_id: str,
        proposed_delta: float,
        trait_history: list,
    ) -> Tuple[float, dict]:
        """Clip a proposed trait delta using single-step and momentum caps.

        Args:
            trait_id: The trait being updated (e.g. "P1_warmth").
            proposed_delta: The raw delta before braking.
            trait_history: anima_mc["evolution"]["trait_history"] entries.

        Returns:
            clipped_delta: The delta after applying caps.
            audit_info: {
                "original": float,
                "clipped": float,
                "reason": str | None,
                "momentum_7d": float,
                "direction_alert": bool,
            }
        """
        original = proposed_delta
        reason = None

        # ------------------------------------------------------------------
        # 1. Single-step cap
        # ------------------------------------------------------------------
        if abs(proposed_delta) > DELTA_CAP:
            sign = 1.0 if proposed_delta > 0 else -1.0
            proposed_delta = sign * DELTA_CAP
            reason = f"single_step_cap: {original:.4f} → {proposed_delta:.4f}"
            logger.debug("[MomentumBrake] %s %s", trait_id, reason)

        # ------------------------------------------------------------------
        # 2. Momentum check (7-day cumulative)
        # ------------------------------------------------------------------
        momentum_7d = self._compute_momentum(trait_id, trait_history, WINDOW_DAYS)

        combined = abs(momentum_7d + proposed_delta)
        if combined > MOMENTUM_CAP:
            available_room = MOMENTUM_CAP - abs(momentum_7d)
            if available_room <= 0:
                pre_clip = proposed_delta
                proposed_delta = 0.0
                _r = f"momentum_cap_exhausted: room=0, clipped {pre_clip:.4f} → 0"
                reason = reason + " | " + _r if reason else _r
                logger.debug("[MomentumBrake] %s %s", trait_id, _r)
            else:
                sign = 1.0 if proposed_delta > 0 else (-1.0 if proposed_delta < 0 else 0.0)
                pre_clip = proposed_delta
                proposed_delta = sign * available_room
                _r = (
                    f"momentum_cap: 7d={momentum_7d:.4f}, room={available_room:.4f}, "
                    f"clipped {pre_clip:.4f} → {proposed_delta:.4f}"
                )
                reason = reason + " | " + _r if reason else _r
                logger.debug("[MomentumBrake] %s %s", trait_id, _r)

        # ------------------------------------------------------------------
        # 3. Direction alert
        # ------------------------------------------------------------------
        direction_alert = self._check_direction_alert(trait_id, trait_history, DIRECTION_ALERT_DAYS)
        if direction_alert:
            logger.warning(
                "[MomentumBrake] %s has moved in same direction for %d+ days",
                trait_id,
                DIRECTION_ALERT_DAYS,
            )

        audit_info: dict = {
            "original": original,
            "clipped": proposed_delta,
            "reason": reason,
            "momentum_7d": momentum_7d,
            "direction_alert": direction_alert,
        }
        return proposed_delta, audit_info

    # ------------------------------------------------------------------
    # Capture risk
    # ------------------------------------------------------------------

    def check_capture_risk(
        self,
        trait_deltas: dict,
        user_primals: dict,
    ) -> Tuple[float, str]:
        """Detect if MUSEON is being captured by a user's personality.

        Args:
            trait_deltas: {trait_id: delta} — pending changes.
            user_primals: User's eight primal scores (0-1 floats).

        Returns:
            capture_risk: 0-1 (cosine similarity magnitude).
            direction: "toward_user" | "away_from_user" | "neutral".
        """
        # Map user primals to trait dimensions
        primal_to_trait = {
            "curiosity": "P4_depth",
            "emotion_pattern": "P1_warmth",
            "action_power": "P3_initiative",
            "boundary": "P2_directness",  # inverse
        }

        # Build aligned vectors
        delta_vec: List[float] = []
        user_vec: List[float] = []

        for primal_key, trait_id in primal_to_trait.items():
            user_score = float(user_primals.get(primal_key, 0.0))
            delta_val = float(trait_deltas.get(trait_id, 0.0))

            # boundary is inverse: high boundary → low directness tendency
            if primal_key == "boundary":
                user_score = 1.0 - user_score

            # User vector: deviation from midpoint (0.5)
            user_vec.append(user_score - 0.5)
            delta_vec.append(delta_val)

        similarity = self._cosine_similarity(delta_vec, user_vec)

        if similarity > 0.6:
            direction = "toward_user"
        elif similarity < -0.3:
            direction = "away_from_user"
        else:
            direction = "neutral"

        return abs(similarity), direction

    # ------------------------------------------------------------------
    # Directional drift analysis
    # ------------------------------------------------------------------

    def compute_directional_drift(
        self,
        trait_history: list,
        days: int = 7,
    ) -> dict:
        """Analyse all traits' directional drift over a time window.

        Args:
            trait_history: anima_mc["evolution"]["trait_history"].
            days: Lookback window in days.

        Returns:
            {
                trait_id: {
                    "total_drift": float,
                    "direction": "positive" | "negative" | "stable",
                    "consecutive_same_direction": int,
                    "alert": bool,
                }
            }
        """
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - days * 86400

        # Group entries by trait_id within window
        grouped: Dict[str, List[float]] = {}
        for entry in trait_history:
            ts = self._parse_timestamp(entry.get("timestamp", ""))
            if ts is None or ts < cutoff:
                continue
            tid = entry.get("trait_id", "")
            if not tid:
                continue
            grouped.setdefault(tid, []).append(float(entry.get("delta", 0.0)))

        result: dict = {}
        for tid, deltas in grouped.items():
            total_drift = sum(deltas)

            if abs(total_drift) < 1e-6:
                direction = "stable"
            elif total_drift > 0:
                direction = "positive"
            else:
                direction = "negative"

            consecutive = self._consecutive_same_direction(deltas)
            alert = consecutive >= DIRECTION_ALERT_DAYS

            result[tid] = {
                "total_drift": round(total_drift, 6),
                "direction": direction,
                "consecutive_same_direction": consecutive,
                "alert": alert,
            }

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_momentum(
        self,
        trait_id: str,
        trait_history: list,
        window_days: int,
    ) -> float:
        """Sum deltas for trait_id within the last window_days."""
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - window_days * 86400
        total = 0.0
        for entry in trait_history:
            if entry.get("trait_id") != trait_id:
                continue
            ts = self._parse_timestamp(entry.get("timestamp", ""))
            if ts is None or ts < cutoff:
                continue
            total += float(entry.get("delta", 0.0))
        return total

    def _check_direction_alert(
        self,
        trait_id: str,
        trait_history: list,
        alert_days: int,
    ) -> bool:
        """Return True if the last alert_days entries for trait_id share a sign."""
        entries = [
            e for e in trait_history if e.get("trait_id") == trait_id
        ]
        # Sort by timestamp descending, take most recent alert_days
        entries.sort(key=lambda e: self._parse_timestamp(e.get("timestamp", "")) or 0, reverse=True)
        recent = entries[:alert_days]
        if len(recent) < alert_days:
            return False
        signs = [math.copysign(1, float(e.get("delta", 0.0))) for e in recent if e.get("delta", 0.0) != 0]
        if len(signs) < alert_days:
            return False
        return len(set(signs)) == 1

    @staticmethod
    def _parse_timestamp(ts_str: str) -> Optional[float]:
        """Parse an ISO-8601 timestamp string to a UTC epoch float."""
        if not ts_str:
            return None
        try:
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Cosine similarity between two vectors; returns 0 if either is zero."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(y * y for y in b))
        if mag_a < 1e-9 or mag_b < 1e-9:
            return 0.0
        return dot / (mag_a * mag_b)

    @staticmethod
    def _consecutive_same_direction(deltas: List[float]) -> int:
        """Count the longest tail of same-sign deltas from the end of the list."""
        if not deltas:
            return 0
        count = 1
        ref_sign = math.copysign(1, deltas[-1]) if deltas[-1] != 0 else 0
        for d in reversed(deltas[:-1]):
            s = math.copysign(1, d) if d != 0 else 0
            if s == ref_sign:
                count += 1
            else:
                break
        return count
