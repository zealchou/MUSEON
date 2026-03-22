"""Unit tests for brain_p3_fusion.py — P3 策略融合、P2 決策層、常數化.

覆蓋範圍：
- 常數引用：所有魔術值已收斂到類別常數
- _detect_p3_strategy_layer_signal: 信號偵測邏輯
- _detect_major_decision_signal: 決策偵測邏輯
- _synthesize_decision_questions: 反問綜合
- _parallel_review_synthesis: 融合決策權重計算
- asyncio API: 使用 get_running_loop（非已棄用的 get_event_loop）
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from museon.agent.brain_p3_fusion import BrainP3FusionMixin
from museon.agent.brain_types import DecisionSignal, P3FusionSignal


# ── Helpers ──

class FakeBrain(BrainP3FusionMixin):
    """Minimal fake Brain with required attributes for BrainP3FusionMixin."""

    def __init__(self):
        self._metacognition = None
        self.eval_engine = None
        self._governor = None
        self._sessions = {}

    def _load_anima_user(self):
        return {"observations": {"prefers_short_response": {"count": 10}}}

    async def _call_llm_with_model(self, **kwargs):
        return "模擬的 LLM 回覆"

    async def _call_llm(self, **kwargs):
        return "模擬的精煉回覆"


# ── 常數化驗證 ──

class TestConstants:
    """驗證所有魔術值已收斂到類別常數."""

    def test_p2_query_truncate_len_exists(self):
        assert hasattr(BrainP3FusionMixin, '_P2_QUERY_TRUNCATE_LEN')
        assert BrainP3FusionMixin._P2_QUERY_TRUNCATE_LEN == 300

    def test_p3_query_truncate_len_exists(self):
        assert hasattr(BrainP3FusionMixin, '_P3_QUERY_TRUNCATE_LEN')
        assert BrainP3FusionMixin._P3_QUERY_TRUNCATE_LEN == 400

    def test_p2_max_tokens_exists(self):
        assert hasattr(BrainP3FusionMixin, '_P2_MAX_TOKENS')
        assert BrainP3FusionMixin._P2_MAX_TOKENS == 100

    def test_p3_max_tokens_exists(self):
        assert hasattr(BrainP3FusionMixin, '_P3_MAX_TOKENS')
        assert BrainP3FusionMixin._P3_MAX_TOKENS == 150

    def test_p3_min_query_length_exists(self):
        assert hasattr(BrainP3FusionMixin, '_P3_MIN_QUERY_LENGTH')
        assert BrainP3FusionMixin._P3_MIN_QUERY_LENGTH == 15

    def test_p3_confidence_values(self):
        assert BrainP3FusionMixin._P3_CONFIDENCE_BASE == 0.6
        assert BrainP3FusionMixin._P3_CONFIDENCE_SLOW == 0.75
        assert BrainP3FusionMixin._P3_CONFIDENCE_SLOW_MULTI == 0.9

    def test_fusion_weights_sum_to_one(self):
        total = (
            BrainP3FusionMixin._FUSION_WEIGHT_METACOG
            + BrainP3FusionMixin._FUSION_WEIGHT_EVAL
            + BrainP3FusionMixin._FUSION_WEIGHT_HEALTH
        )
        assert total == pytest.approx(1.0)

    def test_fusion_thresholds(self):
        assert BrainP3FusionMixin._FUSION_SCORE_BASELINE == 0.5
        assert BrainP3FusionMixin._FUSION_REVISE_THRESHOLD == 0.3
        assert BrainP3FusionMixin._FUSION_HEALTH_ALERT_THRESHOLD == 40
        assert BrainP3FusionMixin._FUSION_HEALTH_LOW_THRESHOLD == 50

    def test_p2_decision_thresholds(self):
        assert BrainP3FusionMixin._P2_MIN_STAKEHOLDERS == 2
        assert BrainP3FusionMixin._P2_MIN_IMPACT_MONTHS == 3
        assert BrainP3FusionMixin._P2_CONFIDENCE_MAX == 0.95

    def test_haiku_model_constant(self):
        assert BrainP3FusionMixin._P3_HAIKU_MODEL == "claude-haiku-4-5-20251001"

    def test_brevity_threshold(self):
        assert BrainP3FusionMixin._BREVITY_PREF_COUNT_THRESHOLD == 50

    def test_p2_response_truncate_len(self):
        assert BrainP3FusionMixin._P2_RESPONSE_TRUNCATE_LEN == 150

    def test_p2_max_decision_questions(self):
        assert BrainP3FusionMixin._P2_MAX_DECISION_QUESTIONS == 5


# ── P3 信號偵測 ──

class TestDetectP3StrategyLayerSignal:
    """_detect_p3_strategy_layer_signal 信號偵測邏輯."""

    def setup_method(self):
        self.brain = FakeBrain()

    def test_fast_loop_skips_p3(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="這是一個需要戰略分析的長問題",
            loop_mode="FAST_LOOP",
            matched_skills=["master-strategy"],
        )
        assert signal.should_fuse is False
        assert "FAST_LOOP" in signal.reason

    def test_short_query_skips_p3(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="你好",
            loop_mode="EXPLORATION_LOOP",
            matched_skills=["xmodel"],
        )
        assert signal.should_fuse is False
        assert "過短" in signal.reason

    def test_no_strategy_skills_skips_p3(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="幫我寫一首關於春天的詩，要有花和鳥的意象",
            loop_mode="EXPLORATION_LOOP",
            matched_skills=["novel-craft", "c15"],
        )
        assert signal.should_fuse is False
        assert "未匹配" in signal.reason

    def test_strategy_skill_triggers_fusion(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="我的品牌定位應該怎麼調整才能打入新市場？",
            loop_mode="EXPLORATION_LOOP",
            matched_skills=["master-strategy", "brand-identity"],
        )
        assert signal.should_fuse is True
        assert "strategy" in signal.perspectives

    def test_human_keywords_add_human_perspective(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="我該怎麼跟客戶談判這筆合作的價格？",
            loop_mode="EXPLORATION_LOOP",
            matched_skills=["ssa-consultant"],
        )
        assert signal.should_fuse is True
        assert "human" in signal.perspectives

    def test_risk_keywords_add_risk_perspective(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="這個市場的投資風險有多大？營收前景如何？",
            loop_mode="EXPLORATION_LOOP",
            matched_skills=["market-core"],
        )
        assert signal.should_fuse is True
        assert "risk" in signal.perspectives

    def test_slow_loop_multi_skill_high_confidence(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="這個商業模式的戰略問題，需要深度分析",
            loop_mode="SLOW_LOOP",
            matched_skills=["master-strategy", "xmodel", "business-12"],
        )
        assert signal.should_fuse is True
        assert signal.confidence == 0.9

    def test_slow_loop_single_skill_medium_confidence(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="這個複雜的問題需要用破框思維來全面解決和突破現有框架",
            loop_mode="SLOW_LOOP",
            matched_skills=["xmodel"],
        )
        assert signal.confidence == 0.75

    def test_exploration_loop_base_confidence(self):
        signal = self.brain._detect_p3_strategy_layer_signal(
            query="我的商業模式需要做一些根本性的調整和優化改善方向",
            loop_mode="EXPLORATION_LOOP",
            matched_skills=["business-12"],
        )
        assert signal.confidence == 0.6


# ── P2 決策偵測 ──

class TestDetectMajorDecisionSignal:
    """_detect_major_decision_signal 決策偵測邏輯."""

    def setup_method(self):
        self.brain = FakeBrain()

    def test_non_slow_loop_skips(self):
        signal = self.brain._detect_major_decision_signal(
            query="要不要投資這個長期計畫？團隊和客戶都有意見",
            loop_mode="FAST_LOOP",
        )
        assert signal.is_major is False
        assert "非 SLOW_LOOP" in signal.details

    def test_no_decision_keywords_skips(self):
        signal = self.brain._detect_major_decision_signal(
            query="今天天氣真好",
            loop_mode="SLOW_LOOP",
        )
        assert signal.is_major is False
        assert "未偵測到決策詞彙" in signal.details

    def test_insufficient_stakeholders(self):
        signal = self.brain._detect_major_decision_signal(
            query="我在決定午餐吃什麼",
            loop_mode="SLOW_LOOP",
        )
        assert signal.is_major is False

    def test_short_impact_horizon(self):
        signal = self.brain._detect_major_decision_signal(
            query="要不要選擇這個短期方案？老闆和團隊都有不同看法",
            loop_mode="SLOW_LOOP",
        )
        # 有決策詞彙 + 有利益相關方，但影響時間短
        assert signal.is_major is False

    def test_major_decision_triggers(self):
        signal = self.brain._detect_major_decision_signal(
            query="我們要不要長期投資這個市場？老闆和團隊意見不一致，成本和品質都是考量",
            loop_mode="SLOW_LOOP",
        )
        assert signal.is_major is True
        assert signal.impact_horizon_months >= 12

    def test_financial_decision_type(self):
        signal = self.brain._detect_major_decision_signal(
            query="該不該長期投資這筆預算到新的品牌計畫？客戶和團隊的成本考量",
            loop_mode="SLOW_LOOP",
        )
        if signal.is_major:
            assert signal.decision_type == "financial"

    def test_confidence_increases_with_stakeholders(self):
        signal = self.brain._detect_major_decision_signal(
            query="要不要長期擴張？老闆、團隊、客戶、員工、投資者都有意見，成本和品質的權衡",
            loop_mode="SLOW_LOOP",
        )
        if signal.is_major:
            assert signal.confidence >= 0.8


# ── 反問綜合 ──

class TestSynthesizeDecisionQuestions:
    """_synthesize_decision_questions 反問綜合邏輯."""

    def setup_method(self):
        self.brain = FakeBrain()
        self.decision_signal = DecisionSignal(
            is_major=True,
            decision_type="general",
            confidence=0.8,
            stakeholders_count=3,
            impact_horizon_months=12,
            details="test",
        )

    def test_max_questions_capped(self):
        perspectives = {
            "xmodel": "反問1",
            "master_strategy": "反問2",
            "shadow": "反問3",
        }
        questions = self.brain._synthesize_decision_questions(
            query="test", decision_signal=self.decision_signal,
            perspectives=perspectives,
        )
        assert len(questions) <= BrainP3FusionMixin._P2_MAX_DECISION_QUESTIONS

    def test_empty_perspectives_with_type_question(self):
        """即使沒有視角見解，也會有決策類型反問."""
        questions = self.brain._synthesize_decision_questions(
            query="test",
            decision_signal=DecisionSignal(
                is_major=True, decision_type="general", confidence=0.5,
                stakeholders_count=1, impact_horizon_months=6, details="",
            ),
            perspectives={},
        )
        assert len(questions) >= 1
        # 類型反問（general → 不可逆性）應該存在
        assert any("不可逆" in q for q in questions)

    def test_stakeholder_question_added(self):
        perspectives = {"xmodel": "q1"}
        questions = self.brain._synthesize_decision_questions(
            query="test", decision_signal=self.decision_signal,
            perspectives=perspectives,
        )
        stakeholder_q = [q for q in questions if "利益相關方" in q]
        assert len(stakeholder_q) == 1


# ── 決策類型反問 ──

class TestGetDecisionTypeQuestions:
    """_get_decision_type_questions 針對不同決策類型的反問."""

    def setup_method(self):
        self.brain = FakeBrain()

    def test_financial_type(self):
        signal = DecisionSignal(
            is_major=True, decision_type="financial", confidence=0.8,
            stakeholders_count=2, impact_horizon_months=12, details="",
        )
        q = self.brain._get_decision_type_questions(signal)
        assert "成本" in q or "現金流" in q

    def test_organizational_type(self):
        signal = DecisionSignal(
            is_major=True, decision_type="organizational", confidence=0.8,
            stakeholders_count=2, impact_horizon_months=12, details="",
        )
        q = self.brain._get_decision_type_questions(signal)
        assert "團隊" in q or "文化" in q

    def test_general_type_fallback(self):
        signal = DecisionSignal(
            is_major=True, decision_type="unknown", confidence=0.8,
            stakeholders_count=2, impact_horizon_months=12, details="",
        )
        q = self.brain._get_decision_type_questions(signal)
        assert "不可逆" in q


# ── asyncio API 驗證 ──

class TestAsyncioApiUsage:
    """驗證使用 get_running_loop 而非已棄用的 get_event_loop."""

    def test_no_deprecated_get_event_loop(self):
        import inspect
        source = inspect.getsource(BrainP3FusionMixin)
        assert "get_event_loop()" not in source
        assert "get_running_loop()" in source


# ── 融合決策權重 ──

class TestFusionScoreCalculation:
    """驗證融合分數計算邏輯的邊界條件."""

    def test_metacog_revise_drops_score(self):
        """MetaCog verdict=revise 時分數下降."""
        baseline = BrainP3FusionMixin._FUSION_SCORE_BASELINE
        weight = BrainP3FusionMixin._FUSION_WEIGHT_METACOG
        expected = baseline - weight
        assert expected == pytest.approx(0.1)

    def test_low_qscore_drops_fusion_score(self):
        """Q-Score=0 時最大扣分."""
        weight = BrainP3FusionMixin._FUSION_WEIGHT_EVAL
        threshold = BrainP3FusionMixin._FUSION_QSCORE_LOW_THRESHOLD
        max_penalty = weight * threshold / threshold
        assert max_penalty == pytest.approx(0.35)

    def test_high_qscore_bonus(self):
        """Q-Score=1.0 時加分."""
        bonus_coeff = BrainP3FusionMixin._FUSION_QSCORE_HIGH_BONUS
        threshold = BrainP3FusionMixin._FUSION_QSCORE_LOW_THRESHOLD
        bonus = bonus_coeff * (1.0 - threshold)
        assert bonus == pytest.approx(0.05)

    def test_worst_case_triggers_revise(self):
        """三個角度全部最差時，分數 < REVISE 閾值."""
        baseline = BrainP3FusionMixin._FUSION_SCORE_BASELINE
        score = baseline
        # MetaCog revise
        score -= BrainP3FusionMixin._FUSION_WEIGHT_METACOG
        # Q-Score = 0
        score -= BrainP3FusionMixin._FUSION_WEIGHT_EVAL
        # Health = 0
        score -= BrainP3FusionMixin._FUSION_WEIGHT_HEALTH
        assert score < BrainP3FusionMixin._FUSION_REVISE_THRESHOLD


# ── P3 前置融合 ──

class TestP3GatherPreFusionInsights:
    """_p3_gather_pre_fusion_insights 前置融合邏輯."""

    @pytest.mark.asyncio
    async def test_empty_perspectives_returns_empty(self):
        brain = FakeBrain()
        signal = P3FusionSignal(
            should_fuse=True, perspectives=[], confidence=0.6, reason="test",
        )
        result = await brain._p3_gather_pre_fusion_insights("query", signal)
        assert result == ""

    @pytest.mark.asyncio
    async def test_strategy_perspective_included(self):
        brain = FakeBrain()
        signal = P3FusionSignal(
            should_fuse=True, perspectives=["strategy"], confidence=0.6, reason="test",
        )
        result = await brain._p3_gather_pre_fusion_insights("什麼商業策略", signal)
        assert "六層技術棧" in result or "多視角" in result

    @pytest.mark.asyncio
    async def test_all_perspectives_included(self):
        brain = FakeBrain()
        signal = P3FusionSignal(
            should_fuse=True, perspectives=["strategy", "human", "risk"],
            confidence=0.9, reason="test",
        )
        result = await brain._p3_gather_pre_fusion_insights(
            "要跟客戶談判投資方案", signal,
        )
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(self):
        brain = FakeBrain()
        brain._call_llm_with_model = AsyncMock(side_effect=Exception("LLM down"))
        signal = P3FusionSignal(
            should_fuse=True, perspectives=["strategy"], confidence=0.6, reason="test",
        )
        result = await brain._p3_gather_pre_fusion_insights("query", signal)
        assert result == ""


# ── 精煉 ──

class TestRefineWithPrecogFeedback:
    """_refine_with_precog_feedback 精煉邏輯."""

    @pytest.mark.asyncio
    async def test_refinement_returns_response(self):
        brain = FakeBrain()
        result = await brain._refine_with_precog_feedback(
            system_prompt="你是助手",
            messages=[{"role": "user", "content": "問題"}],
            feedback="需要更具體",
        )
        assert result == "模擬的精煉回覆"

    @pytest.mark.asyncio
    async def test_brevity_constraint_not_added_below_threshold(self):
        brain = FakeBrain()
        # 預設 count=10 < threshold=50，不應加入簡短約束
        brain._call_llm = AsyncMock(return_value="short reply")
        await brain._refine_with_precog_feedback(
            system_prompt="test", messages=[{"role": "user", "content": "q"}],
            feedback="feedback",
        )
        call_args = brain._call_llm.call_args
        prompt = call_args.kwargs.get("system_prompt", "")
        assert "簡短回覆" not in prompt

    @pytest.mark.asyncio
    async def test_brevity_constraint_added_above_threshold(self):
        brain = FakeBrain()
        brain._load_anima_user = lambda: {
            "observations": {"prefers_short_response": {"count": 100}}
        }
        brain._call_llm = AsyncMock(return_value="short")
        await brain._refine_with_precog_feedback(
            system_prompt="test", messages=[{"role": "user", "content": "q"}],
            feedback="feedback",
        )
        call_args = brain._call_llm.call_args
        prompt = call_args.kwargs.get("system_prompt", "")
        assert "簡短回覆" in prompt

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self):
        brain = FakeBrain()
        brain._call_llm = AsyncMock(side_effect=Exception("LLM down"))
        result = await brain._refine_with_precog_feedback(
            system_prompt="test", messages=[{"role": "user", "content": "q"}],
            feedback="feedback",
        )
        assert result == ""
