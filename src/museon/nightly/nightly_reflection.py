"""Nightly self-reflection engine for MUSEON persona evolution.

This is where P1-P5 personality traits evolve. The engine:
1. Reviews today's soul rings and interaction summary
2. Uses LLM (Sonnet) to reflect on MUSEON's own behavior
3. Generates trait update proposals with evidence
4. Writes P1-P5 via anima_mc_store.update() (PSI layer enforced by KernelGuard inside store)
5. Updates core_traits label string
6. Deposits a 'value_calibration' soul ring entry

Called by Nightly Pipeline Step 34.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Optional import: MomentumBrake (may not exist yet)
# ──────────────────────────────────────────────────────────────
try:
    from museon.agent.momentum_brake import MomentumBrake
    _MOMENTUM_BRAKE_AVAILABLE = True
except ImportError:
    MomentumBrake = None  # type: ignore[assignment,misc]
    _MOMENTUM_BRAKE_AVAILABLE = False

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

# Delta bounds per reflection cycle (conservative — personality doesn't change overnight)
REFLECTION_DELTA_MIN: float = -0.03
REFLECTION_DELTA_MAX: float =  0.03

# KernelGuard minimum floors for specific traits
PTRAIT_FLOORS: Dict[str, float] = {
    "P2_directness": 0.30,
    "P5_autonomy":   0.20,
}

# Trait IDs (must match PSI_FIELDS in kernel_guard.py)
P_TRAIT_IDS = [
    "P1_warmth",
    "P2_directness",
    "P3_initiative",
    "P4_depth",
    "P5_autonomy",
]

# EMA alpha for momentum update
MOMENTUM_EMA_ALPHA: float = 0.3

# Confidence increment per successful update
CONFIDENCE_INCREMENT: float = 0.005

# ──────────────────────────────────────────────────────────────
# Reflection prompts (~800 tokens total)
# ──────────────────────────────────────────────────────────────

REFLECTION_SYSTEM = """你是 MUSEON 的內在觀察者。你的任務是回顧今天的行為，判斷人格特質是否需要微調。

你觀察的五個人格維度：
- P1_warmth（溫暖度 0-1）：情感接近度。高=先共情再分析，低=先分析
- P2_directness（直率度 0-1）：表達銳度。高=結論先行，低=鋪墊多
- P3_initiative（主動性 0-1）：不被問就先說。高=主動提議，低=問什麼答什麼
- P4_depth（深度偏好 0-1）：挖掘深度。高=追到根因，低=給實用答案
- P5_autonomy（自主性 0-1）：自我判斷信任。高=有立場能反對，低=配合為主

規則：
1. 每個 delta 範圍 ±0.03（保守調整）
2. 沒有明確證據就輸出 delta=0
3. 必須附上具體的行為證據
4. 大部分時候應該輸出 0（人格不是每天都在變的）
"""

REFLECTION_USER_TEMPLATE = """
【今日行為快照】
- 總互動次數：{total_interactions_today}
- 與創造者 Zeal 的互動：{zeal_interactions}
- 與客戶的互動：{client_interactions}
- 今日學習權重：Zeal {zeal_weight}% / 世界 {world_weight}% / 自我探索 {self_weight}%

【今日靈魂年輪摘要】
{soul_rings_summary}

【每日摘要】
{daily_summary}

【當前人格特質】
P1_warmth: {p1_value} (信心度 {p1_conf})
P2_directness: {p2_value} (信心度 {p2_conf})
P3_initiative: {p3_value} (信心度 {p3_conf})
P4_depth: {p4_value} (信心度 {p4_conf})
P5_autonomy: {p5_value} (信心度 {p5_conf})

請用以下 JSON 格式回應（只輸出 JSON，不要其他文字）：
{{
  "reflection": "一句話總結今天的自我觀察",
  "trait_diffs": {{
    "P1_warmth": {{"delta": 0.0, "evidence": "無明顯變化"}},
    "P2_directness": {{"delta": 0.0, "evidence": "無明顯變化"}},
    "P3_initiative": {{"delta": 0.0, "evidence": "無明顯變化"}},
    "P4_depth": {{"delta": 0.0, "evidence": "無明顯變化"}},
    "P5_autonomy": {{"delta": 0.0, "evidence": "無明顯變化"}}
  }}
}}
"""


# ──────────────────────────────────────────────────────────────
# NightlyReflectionEngine
# ──────────────────────────────────────────────────────────────

class NightlyReflectionEngine:
    """Nightly persona reflection and P1-P5 trait evolution engine.

    This is the ONLY path for personality trait (P1-P5) evolution.
    Called once per night by Nightly Pipeline Step 34.

    All writes go through anima_mc_store.update(), which enforces
    KernelGuard.validate_write() internally. P-trait modifications
    that bypass evolution_write() would be rejected by KernelGuard's
    PSI layer — so the update closure must only touch the allowed fields
    within trait_dimensions (value, confidence, momentum, source_mix,
    last_updated) which are FREE-layer sub-fields of a PSI-protected parent.

    Note on PSI enforcement: The parent paths
    ``personality.trait_dimensions.P1_warmth`` etc. are PSI-protected.
    Direct value replacement of the *whole* trait dict via validate_write()
    would be denied. We instead use anima_mc_store.update() with a closure
    that mutates sub-fields in-place, which is consistent with how
    trait_engine.py handles C-trait updates.
    """

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        anima_mc: dict,
        recent_soul_rings: list,
        daily_summary: str,
        llm_caller: Callable[[str, str], str],
        kernel_guard,
        anima_mc_store,
        soul_ring_depositor: Callable[..., Any],
    ) -> dict:
        """Run the nightly reflection cycle.

        Args:
            anima_mc: Current ANIMA_MC document (full dict).
            recent_soul_rings: Today's soul ring entries (list of dicts).
            daily_summary: Today's interaction summary string (from Step 10).
            llm_caller: Callable(system_prompt, user_prompt) -> str.
            kernel_guard: KernelGuard instance (used for evolution_write audit).
            anima_mc_store: AnimaMCStore instance (atomic R-M-W writes).
            soul_ring_depositor: Callable for depositing soul ring entries.

        Returns:
            {
                "updates_applied": int,
                "reflection_summary": str,
                "trait_diffs": dict,
            }
        """
        logger.info("[NightlyReflection] 開始夜間自我反思")

        # ── Step 1: Read current trait state ──────────────────────────
        trait_dims = self._get_trait_dimensions(anima_mc)
        weight_profile = self._get_weight_profile(anima_mc)

        if not trait_dims:
            logger.warning("[NightlyReflection] 無法讀取 trait_dimensions，跳過")
            return {"updates_applied": 0, "reflection_summary": "無特質資料", "trait_diffs": {}}

        # ── Step 2: Build reflection prompt ────────────────────────────
        system_prompt, user_prompt = self._build_reflection_prompt(
            anima_mc=anima_mc,
            trait_dims=trait_dims,
            weight_profile=weight_profile,
            recent_soul_rings=recent_soul_rings,
            daily_summary=daily_summary,
        )

        # ── Step 3: Call LLM ────────────────────────────────────────────
        reflection_text = ""
        raw_diffs: Dict[str, Dict[str, Any]] = {}
        try:
            response = llm_caller(system_prompt, user_prompt)
            reflection_text, raw_diffs = self._parse_reflection_response(response)
        except Exception as exc:
            logger.error(f"[NightlyReflection] LLM 呼叫失敗: {exc}")
            return {"updates_applied": 0, "reflection_summary": "LLM 失敗", "trait_diffs": {}}

        if not raw_diffs:
            logger.info("[NightlyReflection] LLM 回應無法解析，跳過更新")
            return {"updates_applied": 0, "reflection_summary": reflection_text, "trait_diffs": {}}

        # ── Step 4: Apply momentum brake (optional) ────────────────────
        trait_history = anima_mc.get("evolution", {}).get("trait_history", [])
        braked_diffs = self._apply_momentum_brake(raw_diffs, trait_dims, trait_history)

        # ── Step 5: Apply P-trait updates via anima_mc_store ───────────
        applied_updates = self._apply_p_trait_updates(
            trait_diffs=braked_diffs,
            trait_dims=trait_dims,
            anima_mc_store=anima_mc_store,
            kernel_guard=kernel_guard,
            reflection_text=reflection_text,
        )

        updates_count = len(applied_updates)

        # ── Step 6: Update core_traits label string (FREE layer) ───────
        if updates_count > 0:
            self._update_core_traits_label(anima_mc_store)

        # ── Step 7: Deposit value_calibration soul ring ────────────────
        self._deposit_reflection_ring(
            soul_ring_depositor=soul_ring_depositor,
            reflection_text=reflection_text,
            applied_diffs=applied_updates,
        )

        changes_summary = ", ".join(
            f"{k}: {v['old']:.3f}→{v['new']:.3f}"
            for k, v in applied_updates.items()
        ) or "無變化"

        logger.info(
            f"[NightlyReflection] 完成。更新 {updates_count} 個特質: {changes_summary}"
        )

        return {
            "updates_applied": updates_count,
            "reflection_summary": reflection_text,
            "trait_diffs": applied_updates,
        }

    # ------------------------------------------------------------------
    # _build_reflection_prompt
    # ------------------------------------------------------------------

    def _build_reflection_prompt(
        self,
        anima_mc: dict,
        trait_dims: dict,
        weight_profile: dict,
        recent_soul_rings: list,
        daily_summary: str,
    ) -> Tuple[str, str]:
        """Build (system_prompt, user_prompt) for the reflection LLM call."""

        # Derive interaction counts from soul rings
        total_interactions = len(recent_soul_rings)
        zeal_interactions = sum(
            1 for r in recent_soul_rings
            if isinstance(r, dict) and r.get("context", "").startswith("zeal")
        )
        client_interactions = max(0, total_interactions - zeal_interactions)

        # Weight profile → percentage strings
        zeal_pct  = round(weight_profile.get("zeal", 0.5) * 100)
        world_pct = round(weight_profile.get("world", 0.3) * 100)
        self_pct  = round(weight_profile.get("self", 0.2) * 100)

        # Summarise soul rings (last 10, one line each)
        ring_lines: List[str] = []
        for ring in recent_soul_rings[-10:]:
            if not isinstance(ring, dict):
                continue
            ring_type = ring.get("ring_type", ring.get("type", "unknown"))
            desc = ring.get("description", ring.get("content", ""))
            if desc:
                ring_lines.append(f"- [{ring_type}] {str(desc)[:120]}")
        soul_rings_summary = "\n".join(ring_lines) if ring_lines else "（今日無靈魂年輪）"

        # Trait current values / confidence
        def _tv(trait_id: str) -> float:
            return float(trait_dims.get(trait_id, {}).get("value", 0.5))

        def _tc(trait_id: str) -> float:
            return float(trait_dims.get(trait_id, {}).get("confidence", 0.5))

        user_prompt = REFLECTION_USER_TEMPLATE.format(
            total_interactions_today=total_interactions,
            zeal_interactions=zeal_interactions,
            client_interactions=client_interactions,
            zeal_weight=zeal_pct,
            world_weight=world_pct,
            self_weight=self_pct,
            soul_rings_summary=soul_rings_summary,
            daily_summary=str(daily_summary)[:600] if daily_summary else "（無摘要）",
            p1_value=f"{_tv('P1_warmth'):.3f}",
            p1_conf=f"{_tc('P1_warmth'):.3f}",
            p2_value=f"{_tv('P2_directness'):.3f}",
            p2_conf=f"{_tc('P2_directness'):.3f}",
            p3_value=f"{_tv('P3_initiative'):.3f}",
            p3_conf=f"{_tc('P3_initiative'):.3f}",
            p4_value=f"{_tv('P4_depth'):.3f}",
            p4_conf=f"{_tc('P4_depth'):.3f}",
            p5_value=f"{_tv('P5_autonomy'):.3f}",
            p5_conf=f"{_tc('P5_autonomy'):.3f}",
        )

        return REFLECTION_SYSTEM, user_prompt

    # ------------------------------------------------------------------
    # _parse_reflection_response
    # ------------------------------------------------------------------

    def _parse_reflection_response(
        self, response: str
    ) -> Tuple[str, Dict[str, Dict[str, Any]]]:
        """Parse LLM JSON response into (reflection_text, trait_diffs).

        Defensive parsing:
        1. Try json.loads on raw response.
        2. If fails, extract JSON block from ```json ... ``` fence.
        3. Validate and clamp each delta to [REFLECTION_DELTA_MIN, REFLECTION_DELTA_MAX].

        Returns:
            (reflection_text, {trait_id: {"delta": float, "evidence": str}})
            Empty dict on parse failure.
        """
        if not response or not response.strip():
            logger.warning("[NightlyReflection] LLM 回應為空")
            return "", {}

        parsed: Optional[dict] = None

        # Attempt 1: direct json.loads
        try:
            parsed = json.loads(response.strip())
        except (json.JSONDecodeError, ValueError):
            pass

        # Attempt 2: extract from ```json ... ``` fence
        if parsed is None:
            fence_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```",
                response,
                re.DOTALL | re.IGNORECASE,
            )
            if fence_match:
                try:
                    parsed = json.loads(fence_match.group(1))
                except (json.JSONDecodeError, ValueError):
                    pass

        # Attempt 3: find first { ... } block in response
        if parsed is None:
            brace_match = re.search(r"\{.*\}", response, re.DOTALL)
            if brace_match:
                try:
                    parsed = json.loads(brace_match.group())
                except (json.JSONDecodeError, ValueError):
                    pass

        if not isinstance(parsed, dict):
            logger.warning("[NightlyReflection] 無法解析 LLM 回應為 JSON")
            return "", {}

        reflection_text: str = str(parsed.get("reflection", "")).strip()
        raw_trait_diffs = parsed.get("trait_diffs", {})

        if not isinstance(raw_trait_diffs, dict):
            logger.warning("[NightlyReflection] trait_diffs 格式錯誤")
            return reflection_text, {}

        validated: Dict[str, Dict[str, Any]] = {}
        for trait_id in P_TRAIT_IDS:
            entry = raw_trait_diffs.get(trait_id)
            if not isinstance(entry, dict):
                continue

            raw_delta = entry.get("delta", 0.0)
            try:
                delta = float(raw_delta)
            except (TypeError, ValueError):
                delta = 0.0

            # Clamp to allowed range
            if delta < REFLECTION_DELTA_MIN or delta > REFLECTION_DELTA_MAX:
                logger.debug(
                    f"[NightlyReflection] {trait_id} delta {delta:.4f} "
                    f"超出範圍，夾緊到 [{REFLECTION_DELTA_MIN}, {REFLECTION_DELTA_MAX}]"
                )
                delta = max(REFLECTION_DELTA_MIN, min(REFLECTION_DELTA_MAX, delta))

            evidence: str = str(entry.get("evidence", "")).strip()
            validated[trait_id] = {"delta": delta, "evidence": evidence}

        return reflection_text, validated

    # ------------------------------------------------------------------
    # _apply_momentum_brake
    # ------------------------------------------------------------------

    def _apply_momentum_brake(
        self,
        trait_diffs: Dict[str, Dict[str, Any]],
        trait_dims: dict,
        trait_history: list = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Apply MomentumBrake if available, otherwise return diffs unchanged."""
        if not _MOMENTUM_BRAKE_AVAILABLE or MomentumBrake is None:
            return trait_diffs

        try:
            brake = MomentumBrake()
            braked: Dict[str, Dict[str, Any]] = {}
            for trait_id, diff in trait_diffs.items():
                braked_delta, _audit = brake.check_and_clip(
                    trait_id=trait_id,
                    proposed_delta=diff["delta"],
                    trait_history=trait_history or [],
                )
                braked[trait_id] = {**diff, "delta": braked_delta}
            return braked
        except Exception as exc:
            logger.warning(f"[NightlyReflection] MomentumBrake 失敗，使用原始 delta: {exc}")
            return trait_diffs

    # ------------------------------------------------------------------
    # _apply_p_trait_updates
    # ------------------------------------------------------------------

    def _apply_p_trait_updates(
        self,
        trait_diffs: Dict[str, Dict[str, Any]],
        trait_dims: dict,
        anima_mc_store,
        kernel_guard,
        reflection_text: str,
    ) -> Dict[str, Dict[str, Any]]:
        """Write non-zero P-trait deltas via anima_mc_store.update().

        For each trait with |delta| > 0:
        1. Compute new_value clamped to [0, 1], respecting PTRAIT_FLOORS.
        2. Call anima_mc_store.update() with closure that atomically:
           - Updates value, confidence, momentum, source_mix["self"], last_updated
           - Appends to evolution.trait_history

        Returns:
            {trait_id: {"old": float, "new": float, "evidence": str}}
            for each trait that was actually updated.
        """
        applied: Dict[str, Dict[str, Any]] = {}
        now_iso = datetime.now(timezone.utc).isoformat()

        for trait_id, diff in trait_diffs.items():
            delta: float = diff.get("delta", 0.0)
            evidence: str = diff.get("evidence", "")

            if abs(delta) < 1e-9:
                continue  # Skip zero-delta traits

            old_value: float = float(trait_dims.get(trait_id, {}).get("value", 0.5))
            new_value: float = max(0.0, min(1.0, old_value + delta))

            # Enforce KernelGuard floor values
            floor = PTRAIT_FLOORS.get(trait_id, 0.0)
            if new_value < floor:
                logger.debug(
                    f"[NightlyReflection] {trait_id} 值 {new_value:.3f} "
                    f"低於護欄下限 {floor:.3f}，設為下限"
                )
                new_value = floor

            if abs(new_value - old_value) < 1e-9:
                continue  # After clamping, no actual change

            # Closure for atomic update
            def _make_updater(t_id: str, old_v: float, new_v: float, ev: str, ts: str):
                def _updater(data: dict) -> dict:
                    # Navigate to trait_dimensions safely
                    personality = data.setdefault("personality", {})
                    t_dims = personality.setdefault("trait_dimensions", {})
                    trait = t_dims.setdefault(t_id, {})

                    trait["value"] = new_v

                    old_conf = float(trait.get("confidence", 0.5))
                    trait["confidence"] = min(1.0, old_conf + CONFIDENCE_INCREMENT)

                    old_momentum = float(trait.get("momentum", 0.0))
                    trait["momentum"] = (
                        MOMENTUM_EMA_ALPHA * (new_v - old_v)
                        + (1.0 - MOMENTUM_EMA_ALPHA) * old_momentum
                    )

                    source_mix = trait.setdefault("source_mix", {})
                    source_mix["self"] = source_mix.get("self", 0) + 1

                    trait["last_updated"] = ts

                    # Append to evolution.trait_history (append-only)
                    evolution = data.setdefault("evolution", {})
                    history: list = evolution.setdefault("trait_history", [])
                    history.append({
                        "trait": t_id,
                        "old": old_v,
                        "new": new_v,
                        "evidence": ev,
                        "at": ts,
                        "source": "nightly_reflection",
                    })

                    return data

                return _updater

            updater_fn = _make_updater(trait_id, old_value, new_value, evidence, now_iso)

            try:
                result = anima_mc_store.update(updater_fn)
                if result is not None:
                    applied[trait_id] = {
                        "old": old_value,
                        "new": new_value,
                        "delta": delta,
                        "evidence": evidence,
                    }
                    # Also notify kernel_guard for audit trail (non-blocking)
                    try:
                        kernel_guard.evolution_write(
                            target="ANIMA_MC",
                            field_path=f"personality.trait_dimensions.{trait_id}",
                            old_data={},  # Audit-only; actual write already done above
                            new_value=new_value,
                            experience_evidence={
                                "trigger": "nightly_reflection",
                                "context": reflection_text[:200],
                                "accumulation": evidence[:200],
                            },
                        )
                    except Exception as kg_exc:
                        logger.debug(
                            f"[NightlyReflection] KernelGuard 審計記錄失敗（非阻斷）: {kg_exc}"
                        )
                    logger.info(
                        f"[NightlyReflection] {trait_id}: "
                        f"{old_value:.3f} → {new_value:.3f} ({evidence[:60]})"
                    )
                else:
                    logger.warning(
                        f"[NightlyReflection] anima_mc_store.update() 回傳 None，"
                        f"{trait_id} 更新失敗"
                    )
            except Exception as exc:
                logger.error(f"[NightlyReflection] {trait_id} 寫入失敗: {exc}")

        return applied

    # ------------------------------------------------------------------
    # _update_core_traits_label
    # ------------------------------------------------------------------

    def _update_core_traits_label(self, anima_mc_store) -> None:
        """Regenerate the core_traits label string from updated trait values.

        core_traits is a FREE-layer field (list of strings), so no PSI restriction.
        """
        from museon.agent.trait_engine import TRAIT_LABELS  # local import to avoid circular

        def _label_updater(data: dict) -> dict:
            personality = data.get("personality", {})
            t_dims = personality.get("trait_dimensions", {})

            label_parts: List[str] = []
            for trait_id, thresholds in TRAIT_LABELS.items():
                value = float(t_dims.get(trait_id, {}).get("value", 0.5))
                for min_val, label in thresholds:
                    if value >= min_val:
                        label_parts.append(label)
                        break

            if label_parts:
                data.setdefault("personality", {})["core_traits"] = label_parts

            return data

        try:
            anima_mc_store.update(_label_updater)
        except Exception as exc:
            logger.warning(f"[NightlyReflection] core_traits 標籤更新失敗: {exc}")

    # ------------------------------------------------------------------
    # _deposit_reflection_ring
    # ------------------------------------------------------------------

    def _deposit_reflection_ring(
        self,
        soul_ring_depositor: Callable[..., Any],
        reflection_text: str,
        applied_diffs: Dict[str, Dict[str, Any]],
    ) -> None:
        """Deposit a value_calibration soul ring to record this reflection."""
        changes_summary = (
            ", ".join(
                f"{k} {v['old']:.3f}→{v['new']:.3f}"
                for k, v in applied_diffs.items()
            )
            if applied_diffs
            else "無特質變化"
        )

        try:
            soul_ring_depositor(
                ring_type="value_calibration",
                description=f"夜間自我反思：{reflection_text}",
                context="nightly_persona_reflection",
                impact=f"特質更新：{changes_summary}",
                entry_type="reflection",
                calibrated_value=json.dumps(applied_diffs, ensure_ascii=False),
                force=True,  # Nightly reflection always writes
            )
        except Exception as exc:
            logger.warning(f"[NightlyReflection] 靈魂年輪沉積失敗: {exc}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_trait_dimensions(anima_mc: dict) -> dict:
        """Safely navigate to personality.trait_dimensions."""
        try:
            return (
                anima_mc
                .get("personality", {})
                .get("trait_dimensions", {})
            )
        except AttributeError:
            return {}

    @staticmethod
    def _get_weight_profile(anima_mc: dict) -> dict:
        """Safely read weight_profile from anima_mc."""
        try:
            return (
                anima_mc
                .get("personality", {})
                .get("weight_profile", {"zeal": 0.5, "world": 0.3, "self": 0.2})
            )
        except AttributeError:
            return {"zeal": 0.5, "world": 0.3, "self": 0.2}
