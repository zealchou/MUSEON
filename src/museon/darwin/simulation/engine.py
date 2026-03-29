"""DARWIN — 模擬引擎 v2（Bass 擴散模型）

架構：Bass 擴散 × One Muse 能量 × 有界信任 × 鴻溝建模

每週更新：
1. 策略衝擊 → 能量向量變化
2. Bass 擴散 → 狀態轉移（含鴻溝、有界信任）
3. 能量擺盪 → 極值反轉
4. 環境事件 → 外部干擾
5. 競爭者/夥伴 → 生態回饋
"""

from __future__ import annotations

import logging
import random
import uuid
from copy import deepcopy

from museon.darwin.config import (
    EVENT_THRESHOLD_ENERGY_DELTA,
    EVENT_THRESHOLD_STATE_CHANGE_PCT,
    PRIMALS,
    SIMULATION_WEEKS,
)
from museon.darwin.simulation.bass_diffusion import (
    bass_adoption_probability,
    compute_bass_params,
    is_chasm_crossed,
)
from museon.darwin.simulation.oscillation import apply_oscillation, clamp_energy
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

# 狀態轉移順序
_STATE_ORDER = ["unaware", "aware", "considering", "decided", "loyal"]


class SimulationEngine:
    """52 週模擬引擎（Bass 擴散 v2）"""

    def __init__(
        self,
        archetypes: list[Archetype],
        strategy: StrategyVector,
        baseline_inner: EnergyVector,
        baseline_outer: EnergyVector,
        tam: int = 1000,
        competitors: list[CompetitorAgent] | None = None,
        partners: list[PartnerAgent] | None = None,
        events: list[dict] | None = None,
        product_type: str = "b2b_saas",
    ):
        self.simulation_id = str(uuid.uuid4())[:12]
        self.archetypes = deepcopy(archetypes)
        self.strategy = strategy
        self.baseline_inner = baseline_inner
        self.baseline_outer = baseline_outer
        self.tam = tam
        self.competitors = competitors or []
        self.partners = partners or []
        self.events = events or []
        self.product_type = product_type
        self.snapshots: list[WeeklySnapshot] = []

        # 預計算每個原型的 Bass 參數
        self._bass_params = {a.id: compute_bass_params(a) for a in self.archetypes}

        # 標記可觸及性
        for a in self.archetypes:
            if not hasattr(a, '_addressable'):
                a._addressable = True
                a._addressable_weight = 1.0

    def run(self, weeks: int = SIMULATION_WEEKS) -> list[WeeklySnapshot]:
        logger.info(f"DARWIN 模擬 {self.simulation_id} | TAM={self.tam} | {weeks} 週")
        for week in range(1, weeks + 1):
            snapshot = self._simulate_week(week)
            self.snapshots.append(snapshot)
        logger.info(f"模擬完成 {self.simulation_id}")
        return self.snapshots

    def _simulate_week(self, week: int) -> WeeklySnapshot:
        prev_states = {a.id: a.awareness_state for a in self.archetypes}

        # ── 1. 策略衝擊（能量向量變化）──
        for a in self.archetypes:
            inner_d, outer_d = apply_strategy_impact(a, self.strategy)
            self._apply_delta(a, inner_d, outer_d)

        # ── 2. Bass 擴散（狀態轉移）──
        adoption_ratio = self._get_adoption_ratio()
        chasm_crossed = is_chasm_crossed(self.archetypes, adoption_ratio)

        for a in self.archetypes:
            if not getattr(a, '_addressable', True):
                continue  # 不可觸及的原型跳過

            if a.awareness_state in ("loyal", "resistant"):
                continue  # 終態不變

            params = self._bass_params[a.id]
            prob = bass_adoption_probability(params, adoption_ratio, chasm_crossed)

            # 能量距離調整（有界信任）：策略能量跟原型能量差太遠 → 降低機率
            energy_distance = self._compute_energy_distance(a)
            if energy_distance > 3.0:
                prob *= 0.3  # 太遠，幾乎不影響
            elif energy_distance > 2.0:
                prob *= 0.6

            # 地能量低的人有機率 → resistant（$12,000 匱乏抗拒）
            earth = getattr(a.current_inner, "地", 0.0)
            if earth < -1.5 and a.awareness_state in ("aware", "considering"):
                if random.random() < abs(earth) * 0.015:
                    a.awareness_state = "resistant"
                    continue

            # 可觸及權重調整
            prob *= getattr(a, '_addressable_weight', 1.0)

            # 狀態推進（每週最多前進一步）
            if random.random() < prob:
                idx = _STATE_ORDER.index(a.awareness_state) if a.awareness_state in _STATE_ORDER else 0
                if idx < len(_STATE_ORDER) - 1:
                    a.awareness_state = _STATE_ORDER[idx + 1]

        # ── 3. 能量擺盪 ──
        for a in self.archetypes:
            inner_osc = apply_oscillation(a.current_inner, self.baseline_inner)
            outer_osc = apply_oscillation(a.current_outer, self.baseline_outer)
            self._apply_delta(a, inner_osc, outer_osc)

        # ── 4. 環境事件 ──
        week_events = [e for e in self.events if e.get("week") == week]
        for event in week_events:
            self._apply_event(event)

        # ── 5. 競爭者 + 夥伴 ──
        comp_actions = self._simulate_competitors(week)
        partner_att = self._update_partners(week)

        # ── 6. 商業指標 ──
        metrics = self._compute_business_metrics()
        is_tp = self._is_turning_point(prev_states, metrics)

        return WeeklySnapshot(
            week=week,
            archetype_states=self._snapshot_states(),
            business_metrics=metrics,
            competitor_actions=comp_actions,
            partner_attitudes=partner_att,
            events=[{"name": e.get("name", ""), "week": week} for e in week_events],
            is_turning_point=is_tp,
        )

    def _get_adoption_ratio(self) -> float:
        """累積採用比例（decided + loyal 佔可觸及原型的比例）"""
        addressable_weight = sum(
            a.weight for a in self.archetypes if getattr(a, '_addressable', True)
        )
        adopted_weight = sum(
            a.weight for a in self.archetypes
            if a.awareness_state in ("decided", "loyal") and getattr(a, '_addressable', True)
        )
        return adopted_weight / max(addressable_weight, 0.001)

    def _compute_energy_distance(self, archetype: Archetype) -> float:
        """計算原型能量跟策略能量的距離（有界信任）"""
        strategy_dict = self.strategy.impact.to_dict()
        inner_dict = archetype.current_inner.to_dict()

        total = 0.0
        count = 0
        for p in PRIMALS:
            s = strategy_dict.get(p, 0)
            if abs(s) < 0.1:
                continue  # 策略不刺激的方位不算
            i = inner_dict.get(p, 0)
            # 策略正刺激 vs 原型負能量 → 距離大
            if s > 0 and i < 0:
                total += abs(s - i)
            elif s < 0 and i > 0:
                total += abs(s - i)
            count += 1

        return total / max(count, 1)

    def _apply_delta(self, archetype, inner_delta, outer_delta):
        for p in PRIMALS:
            ci = getattr(archetype.current_inner, p, 0.0)
            co = getattr(archetype.current_outer, p, 0.0)
            setattr(archetype.current_inner, p, round(clamp_energy(ci + inner_delta.get(p, 0.0)), 3))
            setattr(archetype.current_outer, p, round(clamp_energy(co + outer_delta.get(p, 0.0)), 3))

    def _apply_event(self, event):
        impact = event.get("impact", {})
        if not impact:
            return
        for a in self.archetypes:
            self._apply_delta(a,
                {p: impact.get(p, 0.0) * 0.3 for p in PRIMALS},
                {p: impact.get(p, 0.0) * 0.7 for p in PRIMALS})

    def _simulate_competitors(self, week):
        actions = []
        adoption = self._get_adoption_ratio()
        for comp in self.competitors:
            if adoption > comp.reaction_threshold and (week - comp.last_action_week) >= 6:
                sky = getattr(comp.energy_profile, "天", 0.0)
                mountain = getattr(comp.energy_profile, "山", 0.0)
                if comp.reaction_style == "aggressive" or sky > 2.0:
                    action = {"type": "price_cut", "intensity": min(0.3, adoption * 0.5)}
                elif comp.reaction_style == "analytical" or mountain > 2.0:
                    action = {"type": "feature_match", "intensity": min(0.2, adoption * 0.3)}
                else:
                    action = {"type": "loyalty_program", "intensity": min(0.15, adoption * 0.2)}
                comp.last_action = action["type"]
                comp.last_action_week = week
                actions.append({"competitor": comp.name, **action, "week": week})
                # 競爭者行動讓部分 considering 的人流失
                for a in self.archetypes:
                    if a.awareness_state == "considering" and random.random() < action["intensity"] * 0.3:
                        a.awareness_state = "aware"  # 退回觀望
        return actions

    def _update_partners(self, week):
        attitudes = []
        adoption = self._get_adoption_ratio()
        for p in self.partners:
            delta = (adoption - 0.05) * p.interest_alignment * 0.05
            p.cooperation_score = max(0.0, min(1.0, p.cooperation_score + delta))
            attitudes.append({"partner": p.name, "cooperation_score": round(p.cooperation_score, 2), "role": p.role})
        return attitudes

    def _compute_business_metrics(self) -> dict:
        states = {}
        for s in ("unaware", "aware", "considering", "decided", "loyal", "resistant"):
            states[s] = sum(a.weight for a in self.archetypes if a.awareness_state == s)

        penetration = states["decided"] + states["loyal"]
        nps = (states["loyal"] - states["resistant"]) * 100

        reputation = sum(
            getattr(a.current_outer, "澤", 0.0) * a.weight
            for a in self.archetypes if a.awareness_state in ("decided", "loyal")
        )

        # 營收 = 採用者人數 × 客單價（用 TAM 換算）
        adopted_count = int(penetration * self.tam)
        revenue = adopted_count * 12000  # NT$12,000

        return {
            "penetration_rate": round(penetration, 4),
            "fan_ratio": round(states["loyal"], 4),
            "nps": round(nps, 1),
            "reputation_score": round(reputation, 2),
            "adopted_count": adopted_count,
            "revenue_ntd": revenue,
            "revenue_index": round(penetration * 100, 1),
            "state_distribution": {k: round(v, 4) for k, v in states.items()},
        }

    def _is_turning_point(self, prev_states, metrics) -> bool:
        changes = sum(1 for a in self.archetypes if prev_states.get(a.id) != a.awareness_state)
        pct = changes / max(len(self.archetypes), 1)
        return pct >= EVENT_THRESHOLD_STATE_CHANGE_PCT

    def _snapshot_states(self) -> dict:
        return {
            a.id: {
                "name": a.name, "state": a.awareness_state, "weight": a.weight,
                "role": a.adoption_stage,
                "inner": a.current_inner.to_dict(), "outer": a.current_outer.to_dict(),
            }
            for a in self.archetypes
        }
