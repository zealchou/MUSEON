"""P2 決策層信號偵測測試 — detect_major_decision_signal() 核心邏輯.

5 個測試案例：
1. 決策 + 多利益相關方 + 長期 + SLOW_LOOP → is_major=True
2. 決策但 FAST_LOOP → is_major=False
3. 非決策問題 → is_major=False
4. 決策但單一領域/無衝突 → is_major=False
5. 決策但影響短期（≤3個月） → is_major=False
"""

import pytest
from museon.agent.brain import MuseonBrain, DecisionSignal


@pytest.fixture
def brain():
    """提供 MuseonBrain 實例."""
    return MuseonBrain(data_dir="data")


class TestDecisionSignalDetection:
    """決策信號偵測測試."""

    def test_case_1_major_decision_slow_loop(self, brain):
        """案例 1：決策 + 多利益相關方 + 長期 + SLOW_LOOP → is_major=True."""
        query = (
            "我在考慮要不要把公司的服務自動化。涉及老闆、團隊、客戶三方。"
            "這個決定會影響接下來 3 年的方向。"
            "成本高但能提升品質，快速但可能遺漏細節。"
        )

        signal = brain._detect_major_decision_signal(
            query=query,
            loop_mode="SLOW_LOOP",
        )

        assert signal.is_major is True
        assert signal.confidence > 0.7
        assert signal.stakeholders_count >= 2
        assert signal.impact_horizon_months >= 3
        assert signal.decision_type in ["product", "general", "financial"]

    def test_case_2_decision_fast_loop(self, brain):
        """案例 2：決策但 FAST_LOOP → is_major=False."""
        query = (
            "要不要參加明天的會議？涉及我和老闆。"
            "短期決定，影響不大。"
        )

        signal = brain._detect_major_decision_signal(
            query=query,
            loop_mode="FAST_LOOP",
        )

        assert signal.is_major is False
        assert signal.confidence == 0.0
        assert "跳過決策層偵測" in signal.details

    def test_case_3_non_decision_question(self, brain):
        """案例 3：非決策問題 → is_major=False."""
        query = (
            "怎樣才能改進銷售流程？"
            "有什麼最佳實踐？"
        )

        signal = brain._detect_major_decision_signal(
            query=query,
            loop_mode="SLOW_LOOP",
        )

        assert signal.is_major is False
        assert signal.confidence == 0.0
        assert "決策詞彙" in signal.details

    def test_case_4_decision_single_domain(self, brain):
        """案例 4：決策但單一領域/無衝突 → is_major=False."""
        query = (
            "要不要買這個工具？"
            "我個人使用，沒有涉及其他人。"
            "沒有什麼權衡，就是能用或不能用。"
        )

        signal = brain._detect_major_decision_signal(
            query=query,
            loop_mode="SLOW_LOOP",
        )

        assert signal.is_major is False
        assert signal.stakeholders_count < 2
        assert "利益相關方不足" in signal.details

    def test_case_5_decision_short_term(self, brain):
        """案例 5：決策但影響短期（≤3個月） → is_major=False."""
        query = (
            "我決定要不要用 Python 還是 JavaScript 做這個小專案？"
            "涉及我和實習生。"
            "就這一個月的工作，之後就結束了。"
            "有快速和完美的權衡。"
        )

        signal = brain._detect_major_decision_signal(
            query=query,
            loop_mode="SLOW_LOOP",
        )

        assert signal.is_major is False
        assert signal.confidence < 0.5
        assert signal.impact_horizon_months <= 3
        assert "影響時間短" in signal.details

    def test_decision_type_classification(self, brain):
        """測試決策類型分類."""
        financial_query = (
            "要不要投資 100 萬成立新部門？"
            "涉及老闆、CFO、市場。"
            "長期決策，5 年回報。"
            "成本高但收益大。"
        )
        signal_fin = brain._detect_major_decision_signal(
            query=financial_query,
            loop_mode="SLOW_LOOP",
        )
        assert signal_fin.is_major is True
        assert signal_fin.decision_type == "financial"

        org_query = (
            "該不該重新組織團隊結構？"
            "涉及老闆、部門主管、員工。"
            "長期決策，影響公司文化。"
            "人員配置 vs 效率的權衡。"
        )
        signal_org = brain._detect_major_decision_signal(
            query=org_query,
            loop_mode="SLOW_LOOP",
        )
        assert signal_org.is_major is True
        assert signal_org.decision_type == "organizational"

    def test_stakeholder_counting(self, brain):
        """測試利益相關方計數."""
        query = (
            "要不要把內部流程外包？"
            "涉及老闆、團隊、客戶、合作夥伴。"
            "長期決策，成本 vs 品質的權衡。"
        )

        signal = brain._detect_major_decision_signal(
            query=query,
            loop_mode="SLOW_LOOP",
        )

        assert signal.is_major is True
        assert signal.stakeholders_count >= 4

    def test_confidence_scaling(self, brain):
        """測試信心分數隨利益相關方數量的增加."""
        low_stakeholder_query = (
            "我要不要改變工作流程？"
            "就我一個人受影響。"
            "長期改善。"
            "快速 vs 完美的權衡。"
        )
        signal_low = brain._detect_major_decision_signal(
            query=low_stakeholder_query,
            loop_mode="SLOW_LOOP",
        )

        high_stakeholder_query = (
            "要不要改變公司工作流程？"
            "涉及老闆、全體團隊、客戶、投資者。"
            "長期改善，5 年規劃。"
            "成本高 vs 效率提升的權衡。"
        )
        signal_high = brain._detect_major_decision_signal(
            query=high_stakeholder_query,
            loop_mode="SLOW_LOOP",
        )

        if signal_high.is_major and signal_low.stakeholders_count < 2:
            assert signal_high.confidence >= signal_low.confidence
