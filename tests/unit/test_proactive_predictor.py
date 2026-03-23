"""ProactivePredictor 單元測試.

Project Epigenesis 迭代 7：需求預判引擎。
"""

import pytest

from museon.memory.proactive_predictor import (
    ProactivePredictor,
    ProactiveHint,
    MIN_PREDICTION_CONFIDENCE,
)


@pytest.fixture
def predictor():
    return ProactivePredictor()


class TestPredictFromSequence:
    """Skill 序列模式預測."""

    def test_prior_knowledge(self, predictor):
        """先驗知識：market-core → risk-matrix."""
        hint = predictor.predict(current_skills=["market-core"])
        assert hint is not None
        assert hint.suggested_skill == "risk-matrix"
        assert hint.source == "sequence_prior"

    def test_learned_pattern(self, predictor):
        """學習到的模式優先於先驗."""
        # 模擬學習：market-core 後面 3 次都接 sentiment-radar
        for _ in range(3):
            predictor.record_skill_usage(["market-core"])
            predictor.record_skill_usage(["sentiment-radar"])

        hint = predictor.predict(current_skills=["market-core"])
        assert hint is not None
        assert hint.suggested_skill == "sentiment-radar"
        assert "learned" in hint.source

    def test_no_prediction_unknown_skill(self, predictor):
        """未知 Skill 無先驗 → 可能返回 None."""
        hint = predictor.predict(current_skills=["unknown-skill-xyz"])
        assert hint is None

    def test_resonance_to_dharma(self, predictor):
        """resonance → dharma（先驗知識）."""
        hint = predictor.predict(current_skills=["resonance"])
        assert hint is not None
        assert hint.suggested_skill == "dharma"


class TestPredictFromEmotion:
    """情緒軌跡預測."""

    def test_high_emotion_low_boundary(self, predictor):
        """高情緒 + 低邊界 → resonance."""
        anima = {
            "eight_primals": {
                "emotion_pattern": 80,
                "boundary": 20,
            }
        }
        hint = predictor.predict(anima_user=anima)
        assert hint is not None
        assert hint.suggested_skill == "resonance"
        assert hint.source == "emotion"

    def test_balanced_emotions_no_hint(self, predictor):
        """均衡情緒 → 不推薦."""
        anima = {
            "eight_primals": {
                "emotion_pattern": 50,
                "boundary": 50,
            }
        }
        hint = predictor.predict(anima_user=anima)
        # 只從情緒維度來看，應該沒有推薦
        assert hint is None or hint.source != "emotion"


class TestPredictFromDecisionCycle:
    """決策循環預測."""

    def test_decision_signal(self, predictor):
        """偵測到決策信號 → plan-engine."""
        history = [
            {"content": "幫我分析一下這個方案"},
            {"content": "好，我決定用方案 A"},
        ]
        hint = predictor.predict(session_history=history)
        assert hint is not None
        assert hint.suggested_skill == "plan-engine"
        assert hint.source == "decision"

    def test_no_decision_signal(self, predictor):
        """無決策信號 → 不推薦."""
        history = [
            {"content": "你好"},
            {"content": "今天天氣如何"},
        ]
        hint = predictor.predict(session_history=history)
        assert hint is None


class TestRecordSkillUsage:
    """Skill 使用記錄."""

    def test_record_builds_sequence(self, predictor):
        """記錄累積序列."""
        predictor.record_skill_usage(["market-core"])
        predictor.record_skill_usage(["risk-matrix"])
        assert len(predictor._recent_skills) == 2

    def test_window_limit(self, predictor):
        """窗口大小限制."""
        for i in range(30):
            predictor.record_skill_usage([f"skill-{i}"])
        assert len(predictor._recent_skills) <= 20

    def test_transition_learning(self, predictor):
        """轉移學習."""
        predictor.record_skill_usage(["a"])
        predictor.record_skill_usage(["b"])
        assert "b" in predictor._learned_transitions.get("a", {})


class TestMultiDimensionPrediction:
    """多維度綜合預測."""

    def test_highest_confidence_wins(self, predictor):
        """最高信心度的預測勝出."""
        # 同時有序列先驗（0.6）和情緒（0.6）
        anima = {"eight_primals": {"emotion_pattern": 80, "boundary": 20}}
        hint = predictor.predict(
            current_skills=["market-core"],
            anima_user=anima,
        )
        assert hint is not None
        assert hint.confidence >= MIN_PREDICTION_CONFIDENCE
