"""Trait metabolism engine for MUSEON's 10-dimension personality system.

P1-P5 (Personality): Only Zeal DM + self-exploration can influence.
C1-C5 (Capability): All interactions contribute.

Write paths:
  P1-P5: via kernel_guard.evolution_write() (PSI layer) — only in Nightly
  C1-C5: via anima_mc_store.update() (FREE layer) — real-time ok
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Learning weight decay schedule: list of (days_threshold, weight_dict)
# First entry where days_alive <= threshold wins.
WEIGHT_SCHEDULE = [
    (30,     {"zeal": 0.70, "world": 0.10, "self": 0.20}),
    (90,     {"zeal": 0.50, "world": 0.20, "self": 0.30}),
    (180,    {"zeal": 0.30, "world": 0.30, "self": 0.40}),
    (999999, {"zeal": 0.20, "world": 0.30, "self": 0.50}),
]

# P-trait IDs (personality, PSI-protected — only Zeal DM or self-exploration)
P_TRAITS = [
    "P1_warmth",
    "P2_directness",
    "P3_initiative",
    "P4_depth",
    "P5_autonomy",
]

# C-trait IDs (capability, FREE layer — real-time updates ok)
C_TRAITS = [
    "C1_empathy_breadth",
    "C2_pattern_recognition",
    "C3_domain_depth",
    "C4_conflict_navigation",
    "C5_metacognition",
]

# Per-interaction delta cap — no single observation moves a trait more than this
DELTA_CAP: float = 0.02

# Human-readable label thresholds for P-traits
# Format: list of (min_value, label); first matching entry (value >= min_value) wins
TRAIT_LABELS: Dict[str, List[tuple]] = {
    "P1_warmth":    [(0.7, "溫暖"),    (0.4, "平衡"),    (0.0, "理性")],
    "P2_directness": [(0.7, "直率"),   (0.4, "適度"),    (0.0, "婉轉")],
    "P3_initiative": [(0.7, "主動"),   (0.4, "回應式"),  (0.0, "被動")],
    "P4_depth":      [(0.7, "深度偏好"), (0.4, "平衡"),  (0.0, "實用偏好")],
    "P5_autonomy":   [(0.7, "獨立判斷"), (0.4, "協作"),  (0.0, "服從")],
}

# Emotional keywords used for C1 empathy signal detection
_EMOTIONAL_KEYWORDS = [
    "感覺", "情緒", "難過", "開心", "焦慮", "害怕", "生氣", "擔心",
    "feel", "emotion", "sad", "happy", "anxious", "scared", "angry", "worried",
    "hurt", "lonely", "excited", "grief", "love", "heartbreak",
]

# Analytical skill name fragments for C2 pattern recognition
_ANALYTICAL_SKILL_FRAGMENTS = [
    "analysis", "analyze", "pattern", "insight", "audit", "diagnose",
    "evaluate", "assess", "report", "map", "chart", "dse", "review",
    "scan", "detect", "metric", "monitor",
]

# Proactive suggestion markers for P3 initiative detection
_PROACTIVE_MARKERS = [
    "建議", "可以考慮", "不妨", "試試", "下一步", "主動",
    "suggest", "recommend", "consider", "proactive", "next step", "initiative",
    "you could", "you might", "let's", "shall we",
]

# Disagreement markers for P5 autonomy detection
_DISAGREEMENT_MARKERS = [
    "不同意", "但是", "然而", "我認為", "我覺得不", "我持不同意見",
    "disagree", "however", "but actually", "i think differently",
    "not sure about", "i'd push back", "actually,", "in contrast",
]

# Emotional validation patterns for P1 warmth detection
_VALIDATION_PATTERNS = [
    "理解你", "聽到你", "感受到", "完全理解", "這很正常", "你的感受",
    "i understand", "i hear you", "that makes sense", "your feelings",
    "it's okay", "valid", "completely normal", "i see",
]

# Direct / assertive response markers for P2 directness detection
_DIRECTNESS_MARKERS = [
    "直接說", "簡單來說", "就是", "確實", "清楚", "結論是",
    "simply put", "in short", "directly:", "the answer is", "clearly",
    "bottom line", "to be direct",
]


# ---------------------------------------------------------------------------
# TraitEngine
# ---------------------------------------------------------------------------

class TraitEngine:
    """Handles trait metabolism: computes deltas from interactions and applies them."""

    # ------------------------------------------------------------------
    # 1. Weight profile
    # ------------------------------------------------------------------

    def compute_weight_profile(self, days_alive: int) -> Dict[str, float]:
        """Return source weight profile based on ANIMA's age in days.

        Args:
            days_alive: Number of days since ANIMA was initialised.

        Returns:
            Dict with keys 'zeal', 'world', 'self' summing to 1.0.
        """
        for threshold, weights in WEIGHT_SCHEDULE:
            if days_alive <= threshold:
                return dict(weights)
        # Fallback — should never reach here given 999999 sentinel
        return dict(WEIGHT_SCHEDULE[-1][1])

    # ------------------------------------------------------------------
    # 2. Observe interaction → raw deltas
    # ------------------------------------------------------------------

    def observe_interaction(
        self,
        interaction_data: Dict[str, Any],
        anima_mc: Dict[str, Any],
        anima_user: Dict[str, Any],
    ) -> Dict[str, float]:
        """Compute trait deltas from a single interaction.

        Args:
            interaction_data: Keys expected:
                - content (str): Incoming message text.
                - source (str): 'zeal' | 'world' | 'self'.
                - response_content (str): ANIMA's reply text.
                - skill_names (list[str]): Skills invoked during this interaction.
                - quality_score (float 0-1): Self-assessed response quality.
            anima_mc: Full ANIMA-MC document.
            anima_user: ANIMA-User document (unused in Phase 2, reserved for Phase 6+).

        Returns:
            Dict mapping trait_id → delta float (already weighted and clamped).
        """
        content: str = interaction_data.get("content", "")
        source: str = interaction_data.get("source", "world")
        response: str = interaction_data.get("response_content", "")
        skill_names: List[str] = interaction_data.get("skill_names", [])
        quality_score: float = float(interaction_data.get("quality_score", 0.0))

        # Determine ANIMA's age for weight profile
        days_alive = self._compute_days_alive(anima_mc)
        weight_profile = self.compute_weight_profile(days_alive)
        source_weight: float = weight_profile.get(source, weight_profile["world"])

        deltas: Dict[str, float] = {}

        # ---- C-trait signals (all sources contribute) ----
        c_deltas = self._compute_c_deltas(
            content, source, response, skill_names, quality_score
        )
        for trait_id, raw_delta in c_deltas.items():
            if trait_id == "C3_domain_depth":
                # raw_delta is a dict {domain: float}; weight each domain independently
                if isinstance(raw_delta, dict) and raw_delta:
                    deltas["C3_domain_depth"] = {
                        domain: self._clamp(d * source_weight)
                        for domain, d in raw_delta.items()
                    }
            else:
                weighted = self._clamp(float(raw_delta) * source_weight)
                if weighted != 0.0:
                    deltas[trait_id] = weighted

        # ---- P-trait signals (only zeal or self can influence) ----
        if source in ("zeal", "self"):
            p_deltas = self._compute_p_deltas(response)
            for trait_id, raw_delta in p_deltas.items():
                weighted = self._clamp(raw_delta * source_weight)
                if weighted != 0.0:
                    deltas[trait_id] = weighted

        logger.debug(
            "observe_interaction source=%s days_alive=%d deltas=%s",
            source, days_alive, deltas,
        )
        return deltas

    # ------------------------------------------------------------------
    # 3. Apply C-trait deltas (real-time, FREE layer)
    # ------------------------------------------------------------------

    def apply_c_deltas(
        self,
        c_deltas: Dict[str, Any],
        anima_mc: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply C-trait deltas directly to anima_mc trait_dimensions.

        Modifies and returns the trait_dimensions sub-dict.
        C3_domain_depth is a nested dict: {domain: {value, confidence, last_updated}}.

        Args:
            c_deltas: Mapping of trait_id → delta (float), except C3_domain_depth
                      which maps to {domain_name: delta}.
            anima_mc: Full ANIMA-MC document (modified in-place).

        Returns:
            The updated trait_dimensions section.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        trait_dims: Dict[str, Any] = (
            anima_mc
            .setdefault("personality", {})
            .setdefault("trait_dimensions", {})
        )

        for trait_id, delta in c_deltas.items():
            if trait_id not in C_TRAITS:
                continue

            if trait_id == "C3_domain_depth":
                # delta is expected to be a dict: {domain: float_delta}
                if not isinstance(delta, dict):
                    logger.warning("C3_domain_depth delta should be dict, got %s", type(delta))
                    continue
                domain_store: Dict[str, Any] = trait_dims.setdefault("C3_domain_depth", {})
                for domain, d in delta.items():
                    entry = domain_store.setdefault(domain, {
                        "value": 0.0,
                        "confidence": 0.0,
                        "last_updated": now_iso,
                    })
                    old_val: float = float(entry.get("value", 0.0))
                    new_val = max(0.0, min(1.0, old_val + d))
                    entry["value"] = new_val
                    entry["confidence"] = min(1.0, float(entry.get("confidence", 0.0)) + 0.001)
                    entry["last_updated"] = now_iso
            else:
                entry = trait_dims.setdefault(trait_id, {
                    "value": 0.5,
                    "confidence": 0.0,
                    "momentum": 0.0,
                    "source_mix": {"zeal": 0, "world": 0, "self": 0},
                    "last_updated": now_iso,
                })
                old_val = float(entry.get("value", 0.5))
                new_val = max(0.0, min(1.0, old_val + delta))
                entry["value"] = new_val

                # Confidence grows slowly
                entry["confidence"] = min(
                    1.0, float(entry.get("confidence", 0.0)) + 0.001
                )

                # Momentum: EMA with alpha=0.3
                old_momentum: float = float(entry.get("momentum", 0.0))
                entry["momentum"] = round(0.3 * delta + 0.7 * old_momentum, 6)

                # Source mix count (best-effort; source not carried here — increment 'world')
                entry.setdefault("source_mix", {"zeal": 0, "world": 0, "self": 0})
                entry["source_mix"]["world"] = entry["source_mix"].get("world", 0) + 1

                entry["last_updated"] = now_iso

        return trait_dims

    # ------------------------------------------------------------------
    # 4. Apply P-trait deltas (Nightly only, PSI layer)
    # ------------------------------------------------------------------

    def apply_p_deltas(
        self,
        p_deltas: Dict[str, float],
        anima_mc: Dict[str, Any],
        kernel_guard: Any,
        anima_mc_store: Any,
    ) -> List[str]:
        """Apply P-trait deltas via kernel_guard.evolution_write().

        MUST be called only from Nightly (Phase 5). Never call real-time.

        Args:
            p_deltas: Mapping of P-trait ID → weighted delta.
            anima_mc: Full ANIMA-MC document.
            kernel_guard: KernelGuard instance exposing evolution_write().
            anima_mc_store: Store exposing update() (used by kernel_guard internally).

        Returns:
            List of trait IDs that were successfully queued for evolution.
        """
        applied: List[str] = []
        trait_dims: Dict[str, Any] = (
            anima_mc
            .get("personality", {})
            .get("trait_dimensions", {})
        )

        for trait_id, delta in p_deltas.items():
            if trait_id not in P_TRAITS or delta == 0.0:
                continue

            field_path = f"personality.trait_dimensions.{trait_id}.value"
            old_entry = trait_dims.get(trait_id, {})
            old_value: float = float(old_entry.get("value", 0.5))
            new_value = max(0.0, min(1.0, old_value + delta))

            evidence = {
                "trigger": "nightly_reflection",
                "context": "trait delta from reflection",
                "delta": delta,
                "source": "nightly",
            }

            try:
                kernel_guard.evolution_write(
                    "ANIMA_MC",
                    field_path,
                    old_entry,
                    new_value,
                    evidence,
                )
                applied.append(trait_id)
                logger.info(
                    "P-trait evolution queued: %s  %.4f → %.4f",
                    trait_id, old_value, new_value,
                )
            except Exception as exc:
                logger.error(
                    "kernel_guard.evolution_write failed for %s: %s",
                    trait_id, exc,
                )

        return applied

    # ------------------------------------------------------------------
    # 5. Compute core traits label
    # ------------------------------------------------------------------

    def compute_core_traits_label(
        self,
        trait_dimensions: Dict[str, Any],
    ) -> List[str]:
        """Derive 3-5 human-readable trait labels from P1-P5 values.

        Only includes traits with confidence > 0.2.

        Args:
            trait_dimensions: The trait_dimensions sub-dict from anima_mc.

        Returns:
            List of label strings, e.g. ["溫暖", "直率", "深度偏好"].
        """
        labels: List[str] = []

        for trait_id in P_TRAITS:
            entry = trait_dimensions.get(trait_id)
            if not entry:
                continue
            confidence: float = float(entry.get("confidence", 0.0))
            if confidence <= 0.2:
                continue
            value: float = float(entry.get("value", 0.5))
            thresholds = TRAIT_LABELS.get(trait_id, [])
            for min_val, label in thresholds:
                if value >= min_val:
                    labels.append(label)
                    break

        logger.debug("compute_core_traits_label → %s", labels)
        return labels

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_days_alive(self, anima_mc: Dict[str, Any]) -> int:
        """Compute how many days ANIMA has been alive from anima_mc metadata."""
        try:
            created_at_str: str = (
                anima_mc.get("meta", {}).get("created_at", "")
                or anima_mc.get("created_at", "")
            )
            if not created_at_str:
                return 0
            created_at = datetime.fromisoformat(created_at_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - created_at
            return max(0, delta.days)
        except Exception:
            logger.debug("Could not parse created_at from anima_mc, defaulting days_alive=0")
            return 0

    def _compute_c_deltas(
        self,
        content: str,
        source: str,
        response: str,
        skill_names: List[str],
        quality_score: float,
    ) -> Dict[str, Any]:
        """Compute raw (unweighted) C-trait deltas from interaction signals."""
        deltas: Dict[str, Any] = {}

        # C1 — empathy breadth: emotional content from world
        if source == "world":
            content_lower = content.lower()
            if any(kw in content_lower for kw in _EMOTIONAL_KEYWORDS):
                deltas["C1_empathy_breadth"] = 0.005

        # C2 — pattern recognition: analytical skills used
        analytical_count = sum(
            1 for sk in skill_names
            if any(frag in sk.lower() for frag in _ANALYTICAL_SKILL_FRAGMENTS)
        )
        if analytical_count > 0:
            deltas["C2_pattern_recognition"] = 0.003 * analytical_count

        # C3 — domain depth: each skill used bumps its domain
        if skill_names:
            domain_deltas: Dict[str, float] = {sk: 0.005 for sk in skill_names}
            deltas["C3_domain_depth"] = domain_deltas

        # C4 — conflict navigation: placeholder (populated by DissentEngine in Phase 6)
        deltas["C4_conflict_navigation"] = 0.0

        # C5 — metacognition: self-aware of good performance
        if quality_score > 0.8:
            deltas["C5_metacognition"] = 0.002

        return deltas

    def _compute_p_deltas(self, response: str) -> Dict[str, float]:
        """Compute raw (unweighted) P-trait deltas from response content."""
        deltas: Dict[str, float] = {}
        response_lower = response.lower()

        # P1 — warmth: emotional validation patterns
        if any(p in response_lower for p in _VALIDATION_PATTERNS):
            deltas["P1_warmth"] = 0.005

        # P2 — directness: short + assertive response
        is_short = len(response.strip()) < 200
        has_direct_marker = any(m in response_lower for m in _DIRECTNESS_MARKERS)
        if is_short or has_direct_marker:
            deltas["P2_directness"] = 0.003

        # P3 — initiative: proactive suggestions present
        if any(m in response_lower for m in _PROACTIVE_MARKERS):
            deltas["P3_initiative"] = 0.004

        # P4 — depth: long, substantive response
        if len(response) > 500:
            deltas["P4_depth"] = 0.003

        # P5 — autonomy: disagreement markers
        if any(m in response_lower for m in _DISAGREEMENT_MARKERS):
            deltas["P5_autonomy"] = 0.005

        return deltas

    @staticmethod
    def _clamp(value: float) -> float:
        """Clamp a delta to [-DELTA_CAP, +DELTA_CAP]."""
        return max(-DELTA_CAP, min(DELTA_CAP, value))
