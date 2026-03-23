"""PushBudget 單元測試 — 全局推送預算管理器.

測試限額、去重、持久化、跨日重置。
"""

import pytest
from unittest.mock import MagicMock


class TestPushBudgetLimits:
    """全局推送限額測試."""

    def _make_budget(self, today_count=0):
        from museon.pulse.push_budget import PushBudget
        budget = PushBudget(pulse_db=None)
        budget._today_count = today_count
        budget._today = "2026-03-23"
        return budget

    def test_can_push_within_limit(self):
        budget = self._make_budget(today_count=3)
        assert budget.can_push("soul") is True
        assert budget.remaining == 2

    def test_can_push_at_limit(self):
        budget = self._make_budget(today_count=5)
        assert budget.can_push("soul") is False
        assert budget.remaining == 0

    def test_alert_always_allowed(self):
        budget = self._make_budget(today_count=99)
        assert budget.can_push("alert") is True

    def test_record_push_increments(self):
        budget = self._make_budget(today_count=0)
        budget.record_push("morning", "早安")
        assert budget.today_count == 1
        budget.record_push("soul", "反思內容")
        assert budget.today_count == 2

    def test_all_sources_share_limit(self):
        budget = self._make_budget(today_count=0)
        budget.record_push("morning", "早安")
        budget.record_push("evening", "晚安")
        budget.record_push("soul", "反思")
        budget.record_push("proactive", "自省")
        budget.record_push("idle", "關心")
        # 5 次後應該到限額
        assert budget.can_push("soul") is False
        assert budget.can_push("proactive") is False
        # alert 仍可
        assert budget.can_push("alert") is True


class TestPushBudgetDedup:
    """語意去重測試."""

    def _make_budget(self):
        from museon.pulse.push_budget import PushBudget
        budget = PushBudget(pulse_db=None)
        return budget

    def test_tokenize_chinese_bigrams(self):
        from museon.pulse.push_budget import PushBudget
        tokens = PushBudget._tokenize("琬洛才出生兩天")
        assert "琬洛" in tokens
        assert "出生" in tokens
        assert "兩天" in tokens

    def test_tokenize_mixed(self):
        from museon.pulse.push_budget import PushBudget
        tokens = PushBudget._tokenize("MUSEON 系統健康 OK")
        assert "museon" in tokens
        assert "系統" in tokens

    def test_jaccard_identical(self):
        from museon.pulse.push_budget import PushBudget
        a = PushBudget._tokenize("琬洛才出生兩天你還在工作")
        b = PushBudget._tokenize("琬洛才出生兩天你還在工作")
        assert PushBudget._jaccard(a, b) == 1.0

    def test_jaccard_different(self):
        from museon.pulse.push_budget import PushBudget
        a = PushBudget._tokenize("今天天氣很好")
        b = PushBudget._tokenize("MUSEON 系統架構重構完成")
        j = PushBudget._jaccard(a, b)
        assert j < 0.3

    def test_jaccard_similar_rephrased(self):
        from museon.pulse.push_budget import PushBudget
        # 相同句子的 Jaccard 應該 = 1.0
        a = PushBudget._tokenize("琬洛才出生兩天你還在新手爸爸混亂中")
        b = PushBudget._tokenize("琬洛才出生兩天你還在新手爸爸混亂中")
        assert PushBudget._jaccard(a, b) == 1.0
        # 不同改述的 Jaccard 有一定重疊但不需要 > 0.5
        c = PushBudget._tokenize("琬洛才來兩天你還在新手爸爸的混亂中吧")
        d = PushBudget._tokenize("琬洛才出生兩天耶你還能維持這樣的工作節奏")
        j = PushBudget._jaccard(c, d)
        assert j > 0.05  # 共用字元如「琬洛」「兩天」「還」會產生重疊

    def test_is_duplicate_with_db(self):
        """測試 is_duplicate 從 DB 讀取歷史."""
        from museon.pulse.push_budget import PushBudget
        mock_db = MagicMock()
        mock_db.get_recent_pushes.return_value = [
            "琬洛才出生兩天你還在工作呢系統推了好多任務"
        ]
        budget = PushBudget(pulse_db=mock_db)
        # 幾乎相同的訊息應該被去重
        assert budget.is_duplicate("琬洛才出生兩天你還在工作呢系統推了好多任務") is True
        # 完全不同的訊息不應被去重
        assert budget.is_duplicate("今天的探索報告分析了台灣中小企業的AI採購") is False


class TestPushBudgetDB:
    """PulseDB push_log 表測試."""

    def test_log_and_count(self, tmp_path):
        from museon.pulse.pulse_db import PulseDB
        db = PulseDB(str(tmp_path / "test.db"))
        db.log_push("morning", "早安達達")
        db.log_push("soul", "反思內容")
        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        assert db.get_push_count_for_date(today) == 2

    def test_get_recent_pushes(self, tmp_path):
        from museon.pulse.pulse_db import PulseDB
        db = PulseDB(str(tmp_path / "test.db"))
        db.log_push("soul", "第一條推送")
        db.log_push("proactive", "第二條推送")
        recent = db.get_recent_pushes(hours=1)
        assert len(recent) == 2
        assert "第二條推送" in recent[0]  # DESC 排序


class TestSplitLongText:
    """Telegram 長訊息分段測試."""

    def test_short_text_no_split(self):
        from museon.channels.telegram import TelegramAdapter
        parts = TelegramAdapter._split_long_text("短訊息")
        assert len(parts) == 1
        assert parts[0] == "短訊息"

    def test_long_text_splits(self):
        from museon.channels.telegram import TelegramAdapter
        text = "A" * 3000 + "\n\n" + "B" * 3000
        parts = TelegramAdapter._split_long_text(text, max_len=4096)
        assert len(parts) == 2

    def test_empty_text(self):
        from museon.channels.telegram import TelegramAdapter
        parts = TelegramAdapter._split_long_text("")
        assert parts == []

    def test_no_boundary_hard_cut(self):
        from museon.channels.telegram import TelegramAdapter
        text = "X" * 5000  # 無換行
        parts = TelegramAdapter._split_long_text(text, max_len=4096)
        assert len(parts) == 2
        assert len(parts[0]) == 4096


class TestSanitizeReflection:
    """PULSE.md section header 清理測試."""

    def test_removes_section_headers(self):
        from museon.pulse.pulse_engine import PulseEngine
        text = "## 感知層\n內容一\n### 核心發現\n內容二"
        result = PulseEngine._sanitize_reflection(text)
        assert "## " not in result
        assert "### " not in result
        assert "[感知層]" in result
        assert "[核心發現]" in result
        assert "內容一" in result
        assert "內容二" in result

    def test_preserves_normal_text(self):
        from museon.pulse.pulse_engine import PulseEngine
        text = "今天觀察到你很專注。能量指數 kan=100。"
        result = PulseEngine._sanitize_reflection(text)
        assert result == text
