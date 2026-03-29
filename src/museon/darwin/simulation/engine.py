"""Market Ares — 模擬引擎主迴圈

每週更新公式：
E_i(t+1) = E_i(t) + F_strategy + F_social + F_oscillation + F_event
"""

from __future__ import annotations

import logging
import uuid
from copy import deepcopy

from museon.darwin.config import (
    EVENT_THRESHOLD_ENERGY_DELTA,
    EVENT_THRESHOLD_STATE_CHANGE_PCT,
    PRIMALS,
    SIMULATION_WEEKS,
)
from museon.darwin.simulation.oscillation import apply_oscillation, clamp_energy
from museon.darwin.simulation.social_contagion import advance_state, compute_social_pressure
from museon.darwin.simulation.strategy_impact import apply_strategy_impact
from museon.darwin.storage.models import (
    Archetype,
    CompetitorAgent,
    EnergyVector,
    PartnerAgent,
    StrategyVector,
    WeeklySnapshot,
)

logger = logging.getLogger(__name__)


class SimulationEngine:
    """52 週模擬引擎"""

    def __init__(
        self,
        archetypes: list[Archetype],
        strategy: StrategyVector,
        baseline_inner: EnergyVector,
        baseline_outer: EnergyVector,
        competitors: list[CompetitorAgent] | None = None,
        partners: list[PartnerAgent] | None = None,
        events: list[dict] | None = None,
        topology_weights: dict[int, dict[int, float]] | None = None,
    ):
        self.simulation_id = str(uuid.uuid4())[:12]
        self.archetypes = deepcopy(archetypes)
        self.strategy = strategy
        self.baseline_inner = baseline_inner
        self.baseline_outer = baseline_outer
        self.competitors = competitors or []
        self.partners = partners or []
        self.events = events or []  # [{week: int, name: str, impact: EnergyVector}]
        self.topology = topology_weights
        self.snapshots: list[WeeklySnapshot] = []

    def run(self, weeks: int = SIMULATION_WEEKS) -> list[WeeklySnapshot]:
        """執行完整模擬"""
        logger.info(f"開始模擬 {self.simulation_id}，共 {weeks} 週")

        for week in range(1, weeks + 1):
            snapshot = self._simulate_week(week)
            self.snapshots.append(snapshot)

            if snapshot.is_turning_point:
                logger.info(f"Week {week}: 關鍵轉折點")

        logger.info(f"模擬完成 {self.simulation_id}")
        return self.snapshots

    def _simulate_week(self, week: int) -> WeeklySnapshot:
        """模擬單週"""
        prev_states = {a.id: a.awareness_state for a in self.archetypes}

        # ── 力量一：策略衝擊 ──
        for archetype in self.archetypes:
            inner_delta, outer_delta = apply_strategy_impact(archetype, self.strategy)
            self._apply_delta(archetype, inner_delta, outer_delta)

            # 策略直接觸及：強策略可以把 unaware 推到 aware
            if archetype.awareness_state == "unaware":
                strategy_strength = sum(
                    abs(v) for v in self.strategy.impact.to_dict().values()
                ) / len(PRIMALS)
                # 天能量高的原型更容易被策略吸引（主動關注新事物）
                sky_boost = max(0, getattr(archetype.current_inner, "天", 0.0)) * 0.05
                # 火能量高的原型也會注意到（關注趨勢）
                fire_boost = max(0, getattr(archetype.current_inner, "火", 0.0)) * 0.03
                awareness_chance = strategy_strength * 0.15 + sky_boost + fire_boost

                import random
                if random.random() < awareness_chance:
                    archetype.awareness_state = "aware"

        # ── 力量二：社會傳導 + 策略持續施壓 ──
        strategy_strength = sum(
            abs(v) for v in self.strategy.impact.to_dict().values()
        ) / len(PRIMALS)

        for archetype in self.archetypes:
            pressure = compute_social_pressure(
                archetype, self.archetypes, self.topology
            )
            # 策略本身也施加持續壓力（不只靠口碑傳導）
            # 天高的原型更容易被策略推動
            sky_factor = max(0, getattr(archetype.current_inner, "天", 0.0)) * 0.02
            pressure += strategy_strength * 0.1 + sky_factor

            new_state = advance_state(archetype, pressure)
            archetype.awareness_state = new_state

        # ── 力量三：能量擺盪 ──
        for archetype in self.archetypes:
            inner_osc = apply_oscillation(archetype.current_inner, self.baseline_inner)
            outer_osc = apply_oscillation(archetype.current_outer, self.baseline_outer)
            self._apply_delta(archetype, inner_osc, outer_osc)

        # ── 力量四：環境事件 ──
        week_events = self._get_events_for_week(week)
        for event in week_events:
            self._apply_event(event)

        # ── 競爭者反應 ──
        competitor_actions = self._simulate_competitors(week)

        # ── 夥伴態度 ──
        partner_attitudes = self._update_partners(week)

        # ── 商業指標 ──
        metrics = self._compute_business_metrics()

        # ── 判斷是否為轉折點 ──
        is_turning = self._is_turning_point(prev_states, metrics)

        return WeeklySnapshot(
            week=week,
            archetype_states=self._snapshot_states(),
            business_metrics=metrics,
            competitor_actions=competitor_actions,
            partner_attitudes=partner_attitudes,
            events=[{"name": e.get("name", ""), "week": week} for e in week_events],
            is_turning_point=is_turning,
        )

    def _apply_delta(
        self,
        archetype: Archetype,
        inner_delta: dict[str, float],
        outer_delta: dict[str, float],
    ):
        """將能量變化量應用到原型上"""
        for primal in PRIMALS:
            cur_inner = getattr(archetype.current_inner, primal, 0.0)
            cur_outer = getattr(archetype.current_outer, primal, 0.0)

            new_inner = clamp_energy(cur_inner + inner_delta.get(primal, 0.0))
            new_outer = clamp_energy(cur_outer + outer_delta.get(primal, 0.0))

            setattr(archetype.current_inner, primal, round(new_inner, 3))
            setattr(archetype.current_outer, primal, round(new_outer, 3))

    def _get_events_for_week(self, week: int) -> list[dict]:
        return [e for e in self.events if e.get("week") == week]

    def _apply_event(self, event: dict):
        """將環境事件的衝擊應用到所有原型"""
        impact = event.get("impact", {})
        if not impact:
            return

        for archetype in self.archetypes:
            inner_delta = {p: impact.get(p, 0.0) * 0.3 for p in PRIMALS}
            outer_delta = {p: impact.get(p, 0.0) * 0.7 for p in PRIMALS}
            self._apply_delta(archetype, inner_delta, outer_delta)

    def _simulate_competitors(self, week: int) -> list[dict]:
        """模擬競爭者的反應"""
        actions = []
        current_share = self._estimate_market_share()

        for comp in self.competitors:
            share_loss = comp.market_share - current_share.get(comp.id, comp.market_share)

            if share_loss > comp.reaction_threshold and (week - comp.last_action_week) >= 4:
                action = self._decide_competitor_action(comp, share_loss)
                comp.last_action = action["type"]
                comp.last_action_week = week
                actions.append({"competitor": comp.name, **action, "week": week})

                # 競爭者行動對消費者的影響
                self._apply_competitor_action(comp, action)

        return actions

    def _decide_competitor_action(self, comp: CompetitorAgent, share_loss: float) -> dict:
        """根據競爭者的能量特質決定反應"""
        sky = getattr(comp.energy_profile, "天", 0.0)
        mountain = getattr(comp.energy_profile, "山", 0.0)
        earth = getattr(comp.energy_profile, "地", 0.0)

        if comp.reaction_style == "aggressive" or sky > 2.0:
            return {"type": "price_cut", "intensity": min(0.3, share_loss * 2)}
        elif comp.reaction_style == "analytical" or mountain > 2.0:
            return {"type": "observe", "intensity": 0.0}
        else:  # defensive
            return {"type": "loyalty_program", "intensity": min(0.2, share_loss)}

    def _apply_competitor_action(self, comp: CompetitorAgent, action: dict):
        """競爭者行動影響消費者原型"""
        if action["type"] == "price_cut":
            # 降價搶走一部分 considering 的人
            for archetype in self.archetypes:
                if archetype.awareness_state == "considering":
                    earth = getattr(archetype.current_inner, "地", 0.0)
                    if earth < 0:  # 匱乏感重的人更容易被低價吸引
                        archetype.awareness_state = "resistant"

    def _update_partners(self, week: int) -> list[dict]:
        """更新生態夥伴態度"""
        attitudes = []
        for partner in self.partners:
            # 市場正向發展 → 配合度提升
            loyal_ratio = sum(
                a.weight for a in self.archetypes if a.awareness_state == "loyal"
            )
            delta = (loyal_ratio - 0.1) * partner.interest_alignment * 0.1
            partner.cooperation_score = max(0.0, min(1.0, partner.cooperation_score + delta))

            attitudes.append({
                "partner": partner.name,
                "cooperation_score": round(partner.cooperation_score, 2),
                "role": partner.role,
            })
        return attitudes

    def _compute_business_metrics(self) -> dict:
        """計算商業指標（相對趨勢）"""
        total_pop = 1.0  # 正規化為 1

        unaware = sum(a.weight for a in self.archetypes if a.awareness_state == "unaware")
        aware = sum(a.weight for a in self.archetypes if a.awareness_state == "aware")
        considering = sum(a.weight for a in self.archetypes if a.awareness_state == "considering")
        decided = sum(a.weight for a in self.archetypes if a.awareness_state == "decided")
        loyal = sum(a.weight for a in self.archetypes if a.awareness_state == "loyal")
        resistant = sum(a.weight for a in self.archetypes if a.awareness_state == "resistant")

        penetration = decided + loyal
        fan_ratio = loyal
        nps = (loyal - resistant) * 100

        # 口碑溫度：基於澤能量的加權平均
        reputation = sum(
            getattr(a.current_outer, "澤", 0.0) * a.weight
            for a in self.archetypes
            if a.awareness_state in ("decided", "loyal")
        )

        return {
            "penetration_rate": round(penetration, 4),
            "fan_ratio": round(fan_ratio, 4),
            "nps": round(nps, 1),
            "reputation_score": round(reputation, 2),
            "state_distribution": {
                "unaware": round(unaware, 4),
                "aware": round(aware, 4),
                "considering": round(considering, 4),
                "decided": round(decided, 4),
                "loyal": round(loyal, 4),
                "resistant": round(resistant, 4),
            },
            "revenue_index": round((decided * 80 + loyal * 120) * 100, 1),
        }

    def _estimate_market_share(self) -> dict[str, float]:
        """估算各競爭者的市佔率"""
        return {c.id: c.market_share for c in self.competitors}

    def _is_turning_point(self, prev_states: dict[int, str], metrics: dict) -> bool:
        """判斷本週是否為關鍵轉折點"""
        state_changes = sum(
            1 for a in self.archetypes
            if prev_states.get(a.id) != a.awareness_state
        )
        change_pct = state_changes / max(len(self.archetypes), 1)

        if change_pct >= EVENT_THRESHOLD_STATE_CHANGE_PCT:
            return True

        # 能量大幅變化
        for a in self.archetypes:
            for primal in PRIMALS:
                cur = getattr(a.current_inner, primal, 0.0)
                base = getattr(self.baseline_inner, primal, 0.0)
                if abs(cur - base) > EVENT_THRESHOLD_ENERGY_DELTA * 3:
                    return True

        return False

    def _snapshot_states(self) -> dict:
        """快照所有原型的當前狀態"""
        return {
            a.id: {
                "name": a.name,
                "state": a.awareness_state,
                "weight": a.weight,
                "inner": a.current_inner.to_dict(),
                "outer": a.current_outer.to_dict(),
            }
            for a in self.archetypes
        }
