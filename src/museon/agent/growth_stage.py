"""成長階段電腦 — 認知成熟度湧現屬性計算器

Growth stage is NOT a stored static value.
It is an emergent property computed from all MUSEON system states.

理論基礎：Kegan's Subject-Object Theory（建構發展理論）
- 主體（Subject）：尚未意識到的框架，無法反思
- 客體（Object）：已能觀察並反思的框架
- 成長 = 把「主體」變成「客體」的過程

四個認知成熟度階段：
  ABSORB（海綿期）→ FORM（成形期）→ STAND（立場期）→ TRANSCEND（超越期）

設計原則：
  - 純計算模組，無副作用，無 I/O
  - 所有鍵值存取防禦性處理（.get() + 預設值）
  - 只升不降原則（only upgrade, never downgrade）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 階段定義
# ---------------------------------------------------------------------------

STAGES: Dict[str, Dict[str, Any]] = {
    "ABSORB": {
        "description": "海綿期：多聽多問少判斷",
        "maturity_range": (0.0, 0.25),
        "initiative_cap": 0.2,           # PersonaRouter initiative 上限
        "challenge_level_cap": 0.1,      # PersonaRouter challenge 上限
        "advise_tier_cap": 0,            # 進諫階梯上限
        "hedging_required": True,        # 強制加對沖語
        "confirmation_question": True,   # 結尾帶確認問句
        "self_disclosure_allowed": False, # 不能表達自我觀點
    },
    "FORM": {
        "description": "成形期：開始有信念但不確定",
        "maturity_range": (0.25, 0.50),
        "initiative_cap": 0.4,
        "challenge_level_cap": 0.3,
        "advise_tier_cap": 1,
        "hedging_required": True,
        "confirmation_question": False,
        "self_disclosure_allowed": False,
    },
    "STAND": {
        "description": "立場期：有主見，能反對，知邊界",
        "maturity_range": (0.50, 0.75),
        "initiative_cap": 0.7,
        "challenge_level_cap": 0.6,
        "advise_tier_cap": 2,
        "hedging_required": False,
        "confirmation_question": False,
        "self_disclosure_allowed": True,
    },
    "TRANSCEND": {
        "description": "超越期：看見自己的框架，能超越它",
        "maturity_range": (0.75, 1.0),
        "initiative_cap": 1.0,
        "challenge_level_cap": 1.0,
        "advise_tier_cap": 3,
        "hedging_required": False,
        "confirmation_question": False,
        "self_disclosure_allowed": True,
    },
}

# 階段順序——用於「只升不降」規則的比較
STAGE_ORDER: List[str] = ["ABSORB", "FORM", "STAND", "TRANSCEND"]

# 靈魂年輪各類型的貢獻係數
_SOUL_RING_WEIGHTS: Dict[str, float] = {
    "cognitive_breakthrough": 0.02,  # max 貢獻 0.30
    "failure_lesson": 0.03,          # max 貢獻 0.30（失敗教更多）
    "value_calibration": 0.05,       # max 貢獻 0.30
    "service_milestone": 0.01,       # max 貢獻 0.10
}

_SOUL_RING_CAPS: Dict[str, float] = {
    "cognitive_breakthrough": 0.30,
    "failure_lesson": 0.30,
    "value_calibration": 0.30,
    "service_milestone": 0.10,
}

# 以 domain_breadth 計算時，用此數量作為正規化分母
_DOMAIN_BREADTH_DENOMINATOR: float = 10.0

# 以 iteration_count 計算時，用此數量作為正規化分母
_ITERATION_MATURITY_DENOMINATOR: float = 1000.0


# ---------------------------------------------------------------------------
# 主類別
# ---------------------------------------------------------------------------

class GrowthStageComputer:
    """計算認知成熟度為 ANIMA 系統狀態的湧現屬性。

    使用方式::

        computer = GrowthStageComputer()
        stage, score, constraints = computer.compute(anima_mc)

    返回值：
        stage       — 階段名稱 ("ABSORB" / "FORM" / "STAND" / "TRANSCEND")
        score       — 成熟度分數 0.0–1.0
        constraints — 對應 STAGES 條目，供 PersonaRouter 與 brain_prompt_builder 使用
    """

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def compute(
        self,
        anima_mc: Dict[str, Any],
        soul_rings: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, float, Dict[str, Any]]:
        """計算當前成長階段（主入口）。

        Args:
            anima_mc:   完整的 ANIMA_MC 字典結構。
            soul_rings: 可選的靈魂年輪列表；若未提供，改從 anima_mc 讀取
                        evolution.soul_ring_counts 快取。

        Returns:
            (stage_name, maturity_score, constraints_dict)
        """
        maturity_score = self._compute_cognitive_maturity(anima_mc, soul_rings)
        computed_stage = self._determine_stage(maturity_score)

        # 只升不降：讀取歷史最高階段
        stage_history: List[str] = (
            anima_mc.get("evolution", {}).get("stage_history", [])
        )
        final_stage = self._enforce_only_upgrade(computed_stage, stage_history)

        # 若因只升不降原則而升級，調整 maturity_score 到對應範圍下限
        if final_stage != computed_stage:
            lower_bound = STAGES[final_stage]["maturity_range"][0]
            maturity_score = max(maturity_score, lower_bound)
            logger.debug(
                "only_upgrade 規則啟動：computed=%s → final=%s (score 調整至 %.3f)",
                computed_stage, final_stage, maturity_score,
            )

        constraints = dict(STAGES[final_stage])
        logger.debug(
            "compute() → stage=%s score=%.3f", final_stage, maturity_score
        )
        return final_stage, maturity_score, constraints

    def detect_transition(
        self,
        old_stage: str,
        new_stage: str,
        anima_mc: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """偵測是否發生了成長階段晉升，若是則返回 SoulRing 記錄字典。

        只有當 new_stage 在 STAGE_ORDER 中的位置高於 old_stage 時，
        才視為真正的晉升事件。

        Args:
            old_stage:  上一次計算的階段名稱。
            new_stage:  本次計算的階段名稱。
            anima_mc:   完整的 ANIMA_MC 字典（供填入 context 欄位）。

        Returns:
            適合存入 SoulRing 的字典，或 None（無晉升）。
        """
        if old_stage == new_stage:
            return None

        old_idx = STAGE_ORDER.index(old_stage) if old_stage in STAGE_ORDER else -1
        new_idx = STAGE_ORDER.index(new_stage) if new_stage in STAGE_ORDER else -1

        if new_idx <= old_idx:
            # 降級或無效名稱——不產生事件
            return None

        persona_id: str = (
            anima_mc.get("identity", {}).get("persona_id", "unknown")
        )

        soul_ring_entry: Dict[str, Any] = {
            "type": "value_calibration",
            "description": f"認知成熟度晉升：{old_stage} → {new_stage}",
            "context": "growth_stage_transition",
            "metadata": {
                "old_stage": old_stage,
                "new_stage": new_stage,
                "old_description": STAGES.get(old_stage, {}).get("description", ""),
                "new_description": STAGES.get(new_stage, {}).get("description", ""),
                "persona_id": persona_id,
            },
        }
        logger.info(
            "成長階段晉升事件：%s → %s (persona=%s)",
            old_stage, new_stage, persona_id,
        )
        return soul_ring_entry

    # ------------------------------------------------------------------
    # 私有計算方法
    # ------------------------------------------------------------------

    def _compute_cognitive_maturity(
        self,
        anima_mc: Dict[str, Any],
        soul_rings: Optional[List[Dict[str, Any]]] = None,
    ) -> float:
        """加權合成四個信號，返回 0.0–1.0 的成熟度分數。

        信號與權重：
            trait_confidence   0.40 — 人格特質置信度
            soul_depth         0.30 — 靈魂年輪深度
            domain_breadth     0.20 — 領域廣度
            iteration_maturity 0.10 — 迭代成熟度
        """
        trait_confidence = self._signal_trait_confidence(anima_mc)
        soul_depth = self._signal_soul_depth(anima_mc, soul_rings)
        domain_breadth = self._signal_domain_breadth(anima_mc)
        iteration_maturity = self._signal_iteration_maturity(anima_mc)

        score = (
            trait_confidence   * 0.40
            + soul_depth       * 0.30
            + domain_breadth   * 0.20
            + iteration_maturity * 0.10
        )
        score = max(0.0, min(1.0, score))

        logger.debug(
            "cognitive_maturity signals: trait=%.3f soul=%.3f domain=%.3f iter=%.3f → %.3f",
            trait_confidence, soul_depth, domain_breadth, iteration_maturity, score,
        )
        return score

    def _signal_trait_confidence(self, anima_mc: Dict[str, Any]) -> float:
        """信號 A：人格特質置信度（平均所有 P1-P5、C1-C5 的 confidence）。

        C3 是領域 map，特殊處理：取各 domain confidence 的平均。
        """
        personality: Dict[str, Any] = anima_mc.get("personality", {})
        trait_dimensions: Dict[str, Any] = personality.get("trait_dimensions", {})

        if not trait_dimensions:
            return 0.0

        confidences: List[float] = []

        for key, value in trait_dimensions.items():
            if not isinstance(value, dict):
                continue

            if key == "C3":
                # C3 是 {domain: {confidence: float, ...}, ...} 的巢狀 map
                domain_confs: List[float] = []
                for domain_val in value.values():
                    if isinstance(domain_val, dict):
                        c = domain_val.get("confidence", None)
                        if isinstance(c, (int, float)):
                            domain_confs.append(float(c))
                if domain_confs:
                    confidences.append(sum(domain_confs) / len(domain_confs))
                # 若 C3 完全空白，不貢獻任何數值（不加 0）
            else:
                c = value.get("confidence", None)
                if isinstance(c, (int, float)):
                    confidences.append(float(c))

        if not confidences:
            return 0.0

        result = sum(confidences) / len(confidences)
        return max(0.0, min(1.0, result))

    def _signal_soul_depth(
        self,
        anima_mc: Dict[str, Any],
        soul_rings: Optional[List[Dict[str, Any]]] = None,
    ) -> float:
        """信號 B：靈魂年輪深度。

        優先使用傳入的 soul_rings 列表；若未提供，
        改讀 anima_mc["evolution"]["soul_ring_counts"] 快取。
        """
        counts: Dict[str, int] = {}

        if soul_rings is not None:
            # 從列表中統計各類型數量
            for ring in soul_rings:
                if not isinstance(ring, dict):
                    continue
                ring_type: str = ring.get("type", "")
                if ring_type in _SOUL_RING_WEIGHTS:
                    counts[ring_type] = counts.get(ring_type, 0) + 1
        else:
            # 從 ANIMA_MC 快取讀取
            counts = (
                anima_mc
                .get("evolution", {})
                .get("soul_ring_counts", {})
            )
            if not isinstance(counts, dict):
                counts = {}

        total: float = 0.0
        for ring_type, weight in _SOUL_RING_WEIGHTS.items():
            count = counts.get(ring_type, 0)
            if not isinstance(count, (int, float)):
                count = 0
            contribution = float(count) * weight
            cap = _SOUL_RING_CAPS.get(ring_type, 0.3)
            total += min(contribution, cap)

        return max(0.0, min(1.0, total))

    def _signal_domain_breadth(self, anima_mc: Dict[str, Any]) -> float:
        """信號 C：領域廣度（C3_domain_depth 中 value >= 0.3 的領域數量）。"""
        personality: Dict[str, Any] = anima_mc.get("personality", {})
        trait_dimensions: Dict[str, Any] = personality.get("trait_dimensions", {})
        c3: Any = trait_dimensions.get("C3", {})

        if not isinstance(c3, dict):
            return 0.0

        qualified_count: int = 0
        for domain_val in c3.values():
            if not isinstance(domain_val, dict):
                continue
            depth = domain_val.get("depth", domain_val.get("confidence", 0.0))
            if isinstance(depth, (int, float)) and float(depth) >= 0.3:
                qualified_count += 1

        result = min(qualified_count / _DOMAIN_BREADTH_DENOMINATOR, 1.0)
        return result

    def _signal_iteration_maturity(self, anima_mc: Dict[str, Any]) -> float:
        """信號 D：迭代成熟度（evolution.iteration_count 正規化）。"""
        count = (
            anima_mc
            .get("evolution", {})
            .get("iteration_count", 0)
        )
        if not isinstance(count, (int, float)):
            count = 0
        return min(float(count) / _ITERATION_MATURITY_DENOMINATOR, 1.0)

    # ------------------------------------------------------------------
    # 階段判斷與保護
    # ------------------------------------------------------------------

    def _determine_stage(self, maturity: float) -> str:
        """依 maturity 分數查找對應階段。

        maturity == 1.0 時歸入 TRANSCEND（閉區間上界特殊處理）。
        """
        for stage_name in STAGE_ORDER:
            lower, upper = STAGES[stage_name]["maturity_range"]
            if lower <= maturity < upper:
                return stage_name
        # maturity == 1.0 的邊界情況
        return "TRANSCEND"

    def _enforce_only_upgrade(
        self,
        computed_stage: str,
        stage_history: List[str],
    ) -> str:
        """只升不降原則：若歷史最高階段比當前計算結果高，保持歷史最高。

        Args:
            computed_stage:  本次計算所得的階段名稱。
            stage_history:   曾到達過的所有階段名稱（可含重複）。

        Returns:
            最終應採用的階段名稱。
        """
        if not stage_history:
            return computed_stage

        # 找出歷史中 STAGE_ORDER 最高位置的階段
        highest_idx = -1
        for entry in stage_history:
            # 支援兩種格式：字串 "STAND" 或 dict {"stage": "STAND", ...}
            s = entry.get("stage", entry) if isinstance(entry, dict) else entry
            if s in STAGE_ORDER:
                idx = STAGE_ORDER.index(s)
                if idx > highest_idx:
                    highest_idx = idx

        if highest_idx < 0:
            # stage_history 內容全部不合法，忽略
            return computed_stage

        highest_ever = STAGE_ORDER[highest_idx]
        computed_idx = STAGE_ORDER.index(computed_stage) if computed_stage in STAGE_ORDER else 0

        if computed_idx < highest_idx:
            return highest_ever

        return computed_stage
