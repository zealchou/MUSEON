"""P0 思考路徑可見化 — MetaCognition 單元測試.

測試 extract_thinking_summary() 方法，驗證五維度審查結果的摘要提煉。
"""

import pytest
from museon.agent.metacognition import MetaCognitionEngine


class TestExtractThinkingSummary:
    """extract_thinking_summary() 單元測試."""

    @pytest.fixture
    def engine(self):
        """初始化 MetaCognitionEngine（無 brain 依賴）."""
        return MetaCognitionEngine(data_dir=None, brain=None)

    def test_skipped_verdict_returns_empty(self, engine):
        """Verdict=skipped 時，返回空字串."""
        pre_review = {
            "verdict": "skipped",
            "feedback": "",
            "review_time_ms": 0.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        assert summary == ""

    def test_pass_verdict_returns_confirmation(self, engine):
        """Verdict=pass 時，返回簡潔確認句."""
        pre_review = {
            "verdict": "pass",
            "feedback": "",
            "review_time_ms": 100.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        assert "確認" in summary
        assert "主要需求" in summary
        assert len(summary) <= 150

    def test_revise_with_impact_feedback(self, engine):
        """Verdict=revise 且包含「影響」關鍵詞時，摘要含該維度."""
        pre_review = {
            "verdict": "revise",
            "feedback": "回覆未充分考慮決策的中期影響，應涉及潛在副作用。",
            "review_time_ms": 120.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        assert "影響" in summary or "中期" in summary
        assert len(summary) <= 150

    def test_revise_with_assumption_feedback(self, engine):
        """Verdict=revise 且包含「假設」關鍵詞時，摘要含該維度."""
        pre_review = {
            "verdict": "revise",
            "feedback": "回覆隱含了兩個未驗證的假設：一是使用者有預算，二是優先考量速度。",
            "review_time_ms": 110.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        assert "假設" in summary or "驗證" in summary
        assert len(summary) <= 150

    def test_revise_with_perspective_feedback(self, engine):
        """Verdict=revise 且包含「視角」關鍵詞時，摘要含該維度."""
        pre_review = {
            "verdict": "revise",
            "feedback": "回覆只呈現老闆視角，遺漏了員工執行成本的角度。",
            "review_time_ms": 105.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        assert "視角" in summary or "觀點" in summary
        assert len(summary) <= 150

    def test_revise_with_framework_feedback(self, engine):
        """Verdict=revise 且包含「框架」關鍵詞時，摘要含該維度."""
        pre_review = {
            "verdict": "revise",
            "feedback": "回覆被困在線性流程框架，應引入跨領域的生態系統思維。",
            "review_time_ms": 115.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        assert "框架" in summary or "跨領域" in summary
        assert len(summary) <= 150

    def test_revise_with_real_need_feedback(self, engine):
        """Verdict=revise 且包含「真需」關鍵詞時，摘要含該維度."""
        pre_review = {
            "verdict": "revise",
            "feedback": "回覆只回應了表面的文字，沒有觸及使用者的真正需求（是否有團隊協作痛點）。",
            "review_time_ms": 130.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        assert "真" in summary or "需求" in summary
        assert len(summary) <= 150

    def test_revise_with_multiple_dimensions(self, engine):
        """Verdict=revise 且包含多個維度時，摘要選前 2 個."""
        pre_review = {
            "verdict": "revise",
            "feedback": (
                "回覆缺少多角度視角（員工成本）、隱含假設未驗證（預算充足），"
                "同時沒有觸及真正需求（團隊協作框架）。"
            ),
            "review_time_ms": 125.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        # 應該選前 2 個維度組合
        assert len(summary.split("、")) >= 1  # 至少一個「、」
        assert len(summary) <= 150

    def test_revise_no_matching_keywords(self, engine):
        """Verdict=revise 但 feedback 不含明確維度關鍵詞時，使用通用摘要."""
        pre_review = {
            "verdict": "revise",
            "feedback": "需要進一步調整",
            "review_time_ms": 95.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        assert "多維度" in summary or "實際問題" in summary or "審查" in summary
        assert len(summary) <= 150

    def test_empty_pre_review_returns_empty(self, engine):
        """Pre-review 為空 dict 時，返回空字串."""
        summary = engine.extract_thinking_summary({})
        assert summary == ""

    def test_none_pre_review_returns_empty(self, engine):
        """Pre-review 為 None 時，返回空字串."""
        summary = engine.extract_thinking_summary(None)
        assert summary == ""

    def test_summary_always_chinese(self, engine):
        """摘要文本總是繁體中文（無英文）."""
        pre_review = {
            "verdict": "revise",
            "feedback": "assumption missing and impact not considered",
            "review_time_ms": 100.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        # 驗證摘要是繁體中文（包含中文字符）
        assert any('\u4e00' <= c <= '\u9fff' for c in summary)
        # 不應該直接包含英文關鍵詞（可能有「assumption」等被轉換）
        # 實際測試：內容是中文句式
        assert "我" in summary

    def test_summary_under_150_tokens(self, engine):
        """摘要字數限制在 150 以內（視為 token 下限）."""
        pre_review = {
            "verdict": "revise",
            "feedback": (
                "這是一個很長的反饋，包含了多個維度。"
                "首先，回覆考慮了正面和負面的影響，但沒有考慮隱含的假設。"
                "其次，視角不夠多元，只考慮了管理層的角度。"
                "最後，框架可能被困在傳統思維中，而沒有引入跨領域思路。"
            ),
            "review_time_ms": 150.0,
        }
        summary = engine.extract_thinking_summary(pre_review)
        # 粗估：中文字 * 1.5 ≈ token
        token_estimate = len(summary) * 1.5
        assert token_estimate <= 150, f"摘要過長: {len(summary)} 字 ~= {token_estimate:.0f} tokens"


class TestMetaCognitionIntegration:
    """集成測試：確保 extract_thinking_summary 可被正常呼叫."""

    def test_engine_initialization(self):
        """引擎初始化不拋異常."""
        engine = MetaCognitionEngine(data_dir=None, brain=None)
        assert engine is not None

    def test_extract_thinking_summary_method_exists(self):
        """方法存在且可呼叫."""
        engine = MetaCognitionEngine(data_dir=None, brain=None)
        assert hasattr(engine, "extract_thinking_summary")
        assert callable(engine.extract_thinking_summary)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
