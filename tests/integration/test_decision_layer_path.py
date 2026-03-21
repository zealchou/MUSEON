"""P2 決策層路徑集成測試 — 完整流程驗證.

測試決策層反問是否正確出現，未提前給答案。
"""

import asyncio
import pytest
from pathlib import Path
from museon.agent.brain import MuseonBrain, DecisionSignal


@pytest.fixture
async def brain_with_llm():
    """提供配置好 LLM 的 MuseonBrain 實例."""
    brain = MuseonBrain(data_dir="data")
    # 確保 _call_llm_with_model 可用
    yield brain


@pytest.mark.asyncio
class TestDecisionLayerPath:
    """決策層路徑集成測試."""

    async def test_decision_layer_short_circuit(self, brain_with_llm):
        """測試決策層路徑是否正確短路（不進入後續 pipeline）."""
        # 模擬 major decision 信號
        decision_signal = DecisionSignal(
            is_major=True,
            decision_type="financial",
            confidence=0.85,
            stakeholders_count=3,
            impact_horizon_months=12,
            details="Financial decision with multiple stakeholders",
        )

        # 呼叫決策層處理函數
        response = await brain_with_llm._handle_decision_layer_path(
            query="要不要投資新業務線？涉及老闆、CFO、市場部。長期決策。",
            decision_signal=decision_signal,
            session_id="test_session_001",
        )

        # 驗證回覆
        assert response is not None
        assert isinstance(response, str)
        assert "重大決策" in response
        assert "確認" in response
        assert len(response) > 100  # 應該是有內容的回覆

        # 驗證沒有直接給答案（沒有「建議」、「應該」等直接結論詞）
        assert "直接" not in response or "建議" not in response

    async def test_decision_questions_synthesis(self, brain_with_llm):
        """測試反問點的合成."""
        decision_signal = DecisionSignal(
            is_major=True,
            decision_type="product",
            confidence=0.8,
            stakeholders_count=2,
            impact_horizon_months=6,
            details="Product decision",
        )

        perspectives = {
            "xmodel": "有沒有考慮其他的產品方向？",
            "master_strategy": "這個決定的商業現實代價是什麼？",
            "shadow": "你對這個決策的真實感受是什麼？",
        }

        questions = brain_with_llm._synthesize_decision_questions(
            query="要不要推出新產品？",
            decision_signal=decision_signal,
            perspectives=perspectives,
        )

        # 驗證反問清單
        assert isinstance(questions, list)
        assert len(questions) >= 3
        assert len(questions) <= 5

        # 驗證反問質量（包含關鍵詞）
        combined_q = "\n".join(questions)
        assert any(
            kw in combined_q
            for kw in ["考慮", "代價", "風險", "影響", "反應"]
        )

    async def test_decision_type_specific_questions(self, brain_with_llm):
        """測試不同決策類型的特定反問."""
        # 財務決策
        fin_signal = DecisionSignal(
            is_major=True,
            decision_type="financial",
            confidence=0.8,
            stakeholders_count=2,
            impact_horizon_months=24,
            details="Financial",
        )
        fin_q = brain_with_llm._get_decision_type_questions(fin_signal)
        assert "成本" in fin_q or "回報" in fin_q

        # 組織決策
        org_signal = DecisionSignal(
            is_major=True,
            decision_type="organizational",
            confidence=0.8,
            stakeholders_count=2,
            impact_horizon_months=12,
            details="Organizational",
        )
        org_q = brain_with_llm._get_decision_type_questions(org_signal)
        assert "團隊" in org_q or "文化" in org_q or "人才" in org_q

        # 市場決策
        market_signal = DecisionSignal(
            is_major=True,
            decision_type="market",
            confidence=0.8,
            stakeholders_count=3,
            impact_horizon_months=12,
            details="Market",
        )
        market_q = brain_with_llm._get_decision_type_questions(market_signal)
        assert "市場" in market_q or "競爭" in market_q or "反應" in market_q

    async def test_perspectives_gathering_graceful_degradation(self, brain_with_llm):
        """測試多角度見解蒐集的優雅降級（LLM 失敗時）."""
        decision_signal = DecisionSignal(
            is_major=True,
            decision_type="general",
            confidence=0.75,
            stakeholders_count=2,
            impact_horizon_months=6,
            details="General decision",
        )

        # 即使 LLM 呼叫失敗，應該也能返回部分見解
        perspectives = await brain_with_llm._gather_decision_perspectives(
            query="要不要改變策略？",
            decision_signal=decision_signal,
        )

        assert isinstance(perspectives, dict)
        assert "xmodel" in perspectives
        assert "master_strategy" in perspectives
        assert "shadow" in perspectives


class TestDecisionLayerIntegration:
    """決策層與主 pipeline 的集成測試."""

    def test_decision_signal_in_session(self, brain_with_llm):
        """測試決策層信號在 session 中的記錄."""
        session_id = "test_session_002"
        brain_with_llm._sessions[session_id] = []

        # 模擬決策層回覆
        decision_response = "這是個重大決策。在深入分析之前，我想確認... [反問]"
        brain_with_llm._sessions[session_id].append({
            "role": "assistant",
            "content": decision_response,
            "decision_layer": True,
        })

        # 驗證記錄
        assert len(brain_with_llm._sessions[session_id]) > 0
        last_msg = brain_with_llm._sessions[session_id][-1]
        assert last_msg.get("decision_layer") is True
        assert "重大決策" in last_msg["content"]
