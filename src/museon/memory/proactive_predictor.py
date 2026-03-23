"""ProactivePredictor — 需求預判引擎.

Project Epigenesis 迭代 7：從「預判使用者反應」升級為「預判使用者下一步需要什麼」。

Proactive AI 核心：不是等使用者問，而是預見使用者需要什麼。

預判維度：
  1. Skill 序列模式：上次用了 A → 70% 接著用 B
  2. 時間模式：週一早上通常問 X
  3. 情緒軌跡：連續低能量 → 可能需要 Resonance
  4. 決策循環：問了問題 → 做了決定 → 可能需要執行計畫

消費者：brain.py（透過 EpigeneticRouter.proactive_hint）
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# 最低預測信心度（低於此值不主動推薦）
MIN_PREDICTION_CONFIDENCE: float = 0.5

# Skill 序列模式：記錄最近 N 次的 Skill 使用序列
SEQUENCE_WINDOW: int = 20

# 常見的 Skill 接續模式（手工知識 + 統計學習）
SKILL_TRANSITION_PRIORS: Dict[str, List[Tuple[str, float]]] = {
    # 用了投資分析 → 可能需要風險矩陣
    "market-core": [("risk-matrix", 0.6), ("investment-masters", 0.5)],
    "market-equity": [("risk-matrix", 0.5), ("sentiment-radar", 0.4)],
    # 用了商業診斷 → 可能需要破框或品牌
    "business-12": [("xmodel", 0.5), ("brand-identity", 0.4)],
    # 用了 SSA 銷售 → 可能需要品牌或故事
    "ssa-consultant": [("brand-identity", 0.4), ("storytelling-engine", 0.4)],
    # 用了 Resonance → 可能需要 DHARMA
    "resonance": [("dharma", 0.5)],
    # 用了 DSE 技術研究 → 可能需要鍛造
    "dse": [("acsf", 0.5), ("plan-engine", 0.4)],
    # 用了 xmodel → 可能需要 PDEIF
    "xmodel": [("pdeif", 0.5), ("master-strategy", 0.4)],
}

# 決策循環階段
DECISION_CYCLE = {
    "exploring": "analysis",     # 探索 → 分析
    "analysis": "decision",      # 分析 → 決定
    "decision": "execution",     # 決定 → 執行
    "execution": "review",       # 執行 → 回顧
}


@dataclass
class ProactiveHint:
    """預判式建議."""
    suggested_skill: str          # 建議的 Skill
    confidence: float             # 信心度（0.0~1.0）
    reason: str                   # 預判理由
    source: str = "sequence"      # 預判來源（sequence/time/emotion/decision）


# ═══════════════════════════════════════════
# ProactivePredictor
# ═══════════════════════════════════════════

class ProactivePredictor:
    """需求預判引擎.

    基於四維分析預測使用者下一步可能需要什麼。
    純 CPU 計算，不呼叫 LLM。
    """

    def __init__(self) -> None:
        # 學習到的 Skill 轉移矩陣（運行時累積）
        self._learned_transitions: Dict[str, Counter] = {}
        # 最近的 Skill 使用序列
        self._recent_skills: List[str] = []

    def predict(
        self,
        current_skills: Optional[List[str]] = None,
        anima_user: Optional[Dict] = None,
        session_history: Optional[List[Dict]] = None,
    ) -> Optional[ProactiveHint]:
        """預測使用者下一步需求.

        Args:
            current_skills: 本輪使用的 Skill 名稱列表
            anima_user: ANIMA_USER dict
            session_history: 本 session 的歷史（含 skills_used）

        Returns:
            ProactiveHint 或 None（信心度不足時不推薦）
        """
        hints: List[ProactiveHint] = []

        # 維度 1: Skill 序列模式
        if current_skills:
            hint = self._predict_from_sequence(current_skills)
            if hint:
                hints.append(hint)

        # 維度 2: 情緒軌跡
        if anima_user:
            hint = self._predict_from_emotion(anima_user)
            if hint:
                hints.append(hint)

        # 維度 3: 決策循環
        if session_history:
            hint = self._predict_from_decision_cycle(session_history)
            if hint:
                hints.append(hint)

        if not hints:
            return None

        # 選信心度最高的
        best = max(hints, key=lambda h: h.confidence)
        if best.confidence < MIN_PREDICTION_CONFIDENCE:
            return None

        logger.debug(
            f"ProactivePredictor | skill={best.suggested_skill} | "
            f"confidence={best.confidence:.2f} | source={best.source}"
        )
        return best

    def record_skill_usage(self, skills: List[str]) -> None:
        """記錄 Skill 使用（供序列學習）.

        Args:
            skills: 本輪使用的 Skill 列表
        """
        for skill in skills:
            self._recent_skills.append(skill)

        # 保持窗口大小
        if len(self._recent_skills) > SEQUENCE_WINDOW:
            self._recent_skills = self._recent_skills[-SEQUENCE_WINDOW:]

        # 學習轉移：前一個 Skill → 當前 Skill
        if len(self._recent_skills) >= 2:
            prev = self._recent_skills[-2]
            curr = self._recent_skills[-1]
            self._learned_transitions.setdefault(prev, Counter())[curr] += 1

    # ── 預測維度 ──────────────────────────────

    def _predict_from_sequence(
        self, current_skills: List[str]
    ) -> Optional[ProactiveHint]:
        """從 Skill 序列模式預測.

        先查學習到的轉移矩陣，再查先驗知識。
        """
        if not current_skills:
            return None

        last_skill = current_skills[-1]

        # 先查學習到的轉移
        if last_skill in self._learned_transitions:
            counter = self._learned_transitions[last_skill]
            total = sum(counter.values())
            if total >= 2:  # 至少觀察到 2 次才有信心
                most_common_skill, count = counter.most_common(1)[0]
                confidence = min(count / total, 0.9)  # 上限 0.9
                if confidence >= MIN_PREDICTION_CONFIDENCE:
                    return ProactiveHint(
                        suggested_skill=most_common_skill,
                        confidence=confidence,
                        reason=f"過去 {total} 次用 {last_skill} 後，{count} 次接著用 {most_common_skill}",
                        source="sequence_learned",
                    )

        # 再查先驗知識
        if last_skill in SKILL_TRANSITION_PRIORS:
            transitions = SKILL_TRANSITION_PRIORS[last_skill]
            best_skill, best_conf = transitions[0]
            return ProactiveHint(
                suggested_skill=best_skill,
                confidence=best_conf,
                reason=f"根據常見模式，{last_skill} 之後通常需要 {best_skill}",
                source="sequence_prior",
            )

        return None

    def _predict_from_emotion(
        self, anima_user: Dict
    ) -> Optional[ProactiveHint]:
        """從情緒軌跡預測.

        如果使用者的情緒相關原語持續偏高，可能需要 Resonance。
        """
        primals = anima_user.get("eight_primals", {})

        emotion = primals.get("emotion_pattern", 0)
        if isinstance(emotion, dict):
            emotion = emotion.get("level", 0)

        boundary = primals.get("boundary", 0)
        if isinstance(boundary, dict):
            boundary = boundary.get("level", 0)

        # 高情緒 + 低邊界 → 可能需要情緒支持
        if isinstance(emotion, (int, float)) and isinstance(boundary, (int, float)):
            if emotion > 70 and boundary < 30:
                return ProactiveHint(
                    suggested_skill="resonance",
                    confidence=0.6,
                    reason="情緒原語偏高、邊界原語偏低，可能需要情緒承接",
                    source="emotion",
                )

        return None

    def _predict_from_decision_cycle(
        self, session_history: List[Dict]
    ) -> Optional[ProactiveHint]:
        """從決策循環階段預測.

        如果 session 中出現了「分析」→「決定」的模式，
        下一步可能需要「執行計畫」。
        """
        if len(session_history) < 2:
            return None

        # 從最近的 session 歷史中偵測決策關鍵詞
        recent_text = " ".join(
            h.get("content", "")[:100] for h in session_history[-3:]
        )

        decision_indicators = ["我決定", "就這樣做", "確定", "拍板", "就這麼辦"]
        if any(kw in recent_text for kw in decision_indicators):
            return ProactiveHint(
                suggested_skill="plan-engine",
                confidence=0.55,
                reason="偵測到決策信號，可能需要將決定轉化為執行計畫",
                source="decision",
            )

        return None
