"""P0 思考路徑可見化 — Brain 集成測試.

驗證思考路徑摘要在回覆中正確出現。
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from museon.agent.brain import MuseonBrain
from museon.agent.metacognition import MetaCognitionEngine


class TestBrainThinkingPathIntegration:
    """Brain 中思考路徑摘要的集成測試."""

    @pytest.fixture
    def temp_data_dir(self):
        """暫時資料目錄."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def brain(self, temp_data_dir):
        """初始化 Brain（最小依賴）."""
        return MuseonBrain(data_dir=temp_data_dir)

    def test_brain_initializes_with_metacognition(self, brain):
        """Brain 成功初始化 MetaCognitionEngine."""
        assert brain._metacognition is not None
        assert isinstance(brain._metacognition, MetaCognitionEngine)

    @pytest.mark.asyncio
    async def test_extract_thinking_summary_in_process_flow(self, brain, temp_data_dir):
        """
        完整流程：pre_review → extract_thinking_summary → 注入回覆.

        這是一個簡化的集成測試，模擬 Step 6.2 到最終回覆的流程。
        """
        # 模擬 pre_review 結果
        mock_pre_review = {
            "verdict": "pass",
            "feedback": "",
            "review_time_ms": 100.0,
        }

        # 呼叫 extract_thinking_summary
        summary = brain._metacognition.extract_thinking_summary(
            pre_review=mock_pre_review,
            user_query="如何提高團隊效率？",
        )

        # 驗證摘要被產生
        assert summary != ""
        assert "確認" in summary

        # 模擬最終回覆組裝（模擬 Step 7 邏輯）
        response_text = "建議建立日會制度，分享進度與阻礙。"
        if summary:
            final_response = f"【我的思考路徑】{summary}\n\n{response_text}"
        else:
            final_response = response_text

        # 驗證最終回覆包含思考摘要前置
        assert "【我的思考路徑】" in final_response
        assert summary in final_response
        assert response_text in final_response

    @pytest.mark.asyncio
    async def test_pre_review_revise_thinking_path(self, brain):
        """
        Verdict=revise 時的思考路徑摘要生成.

        驗證當 PreCognition 建議修改時，能正確提煉維度摘要。
        """
        mock_pre_review = {
            "verdict": "revise",
            "feedback": "回覆未充分考慮隱含假設：使用者可能沒有預算。",
            "review_time_ms": 110.0,
        }

        summary = brain._metacognition.extract_thinking_summary(
            pre_review=mock_pre_review,
            user_query="要不要購買新軟體？",
        )

        # 驗證摘要包含「假設」相關詞
        assert summary != ""
        assert "假設" in summary or "驗證" in summary

    def test_thinking_path_summary_format(self, brain):
        """
        驗證摘要格式符合要求（2-3 句，150 tokens 以內）.
        """
        pre_reviews = [
            {
                "verdict": "pass",
                "feedback": "",
                "review_time_ms": 100.0,
            },
            {
                "verdict": "revise",
                "feedback": "假設未驗證",
                "review_time_ms": 110.0,
            },
            {
                "verdict": "revise",
                "feedback": "視角不夠多元，影響分析不足",
                "review_time_ms": 120.0,
            },
        ]

        for pre_review in pre_reviews:
            summary = brain._metacognition.extract_thinking_summary(pre_review)

            # 驗證格式
            if summary:
                # 字數限制（粗估）
                assert len(summary) <= 200, f"摘要過長: {summary}"
                # 應該是中文
                assert any('\u4e00' <= c <= '\u9fff' for c in summary)
                # 應該以「我」開頭
                assert summary.startswith("我")

    def test_thinking_path_injection_into_response(self, brain):
        """
        驗證思考摘要注入回覆的格式.

        測試最終回覆的結構：【我的思考路徑】+ 摘要 + 原始回覆
        """
        mock_response = "這是原始回覆內容。"
        mock_summary = "我考慮了假設的合理性。"

        # 模擬 Step 7 的注入邏輯
        if mock_summary:
            final = f"【我的思考路徑】{mock_summary}\n\n{mock_response}"
        else:
            final = mock_response

        # 驗證結構
        assert final.startswith("【我的思考路徑】")
        assert mock_summary in final
        assert mock_response in final

    def test_no_thinking_path_when_skipped(self, brain):
        """
        Verdict=skipped 時，不注入思考摘要.
        """
        mock_pre_review = {
            "verdict": "skipped",
            "feedback": "",
            "review_time_ms": 0.0,
        }

        summary = brain._metacognition.extract_thinking_summary(mock_pre_review)
        assert summary == ""

        # 模擬回覆組裝
        mock_response = "原始回覆"
        if summary:
            final = f"【我的思考路徑】{summary}\n\n{mock_response}"
        else:
            final = mock_response

        # 驗證不包含思考摘要前置
        assert "【我的思考路徑】" not in final
        assert final == mock_response


class TestThinkingPathEdgeCases:
    """邊界情況測試."""

    @pytest.fixture
    def brain(self):
        """最小 Brain 實例."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield MuseonBrain(data_dir=tmpdir)

    def test_very_long_feedback_truncation(self, brain):
        """
        Feedback 非常長時，摘要仍在限制內.
        """
        long_feedback = (
            "這是一個非常長的反饋，" * 50 +
            "涉及假設、視角、影響、框架和真實需求。" * 30
        )
        pre_review = {
            "verdict": "revise",
            "feedback": long_feedback,
            "review_time_ms": 200.0,
        }

        summary = brain._metacognition.extract_thinking_summary(pre_review)

        # 即使 feedback 非常長，摘要也應該在限制內
        assert len(summary) <= 200

    def test_multiple_keywords_select_first_two(self, brain):
        """
        包含多個維度關鍵詞時，應選前 2 個.
        """
        pre_review = {
            "verdict": "revise",
            "feedback": (
                "影響分析不足，"
                "假設未驗證，"
                "視角單一，"
                "框架被困，"
                "真需偏差"
            ),
            "review_time_ms": 115.0,
        }

        summary = brain._metacognition.extract_thinking_summary(pre_review)

        # 驗證只包含前 2 個維度（「、」連接符）
        # 最多應該有 1 個「、」（表示 2 個維度）
        count_joints = summary.count("、")
        assert count_joints <= 1, f"包含超過 2 個維度: {summary}"

    def test_mixed_english_feedback(self, brain):
        """
        Feedback 包含英文關鍵詞時，摘要仍用中文.
        """
        pre_review = {
            "verdict": "revise",
            "feedback": "assumption validation missing, impact not considered",
            "review_time_ms": 105.0,
        }

        summary = brain._metacognition.extract_thinking_summary(pre_review)

        # 摘要應該是中文
        if summary:
            assert any('\u4e00' <= c <= '\u9fff' for c in summary)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
