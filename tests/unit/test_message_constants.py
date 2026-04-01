"""測試 message_constants 統一常數源的正確性和一致性。"""
import pytest


class TestMessageConstants:
    """常數值正確性。"""

    def test_import_all_constants(self):
        from museon.core.message_constants import (
            SIMPLE_MESSAGE_LENGTH, SIGNAL_LENGTH_SHORT, SIGNAL_LENGTH_LONG,
            SIMPLE_EXCLUDE_KEYWORDS, SIMPLE_GREETINGS,
            LOOP_FAST, LOOP_SLOW, LOOP_EXPLORATION,
        )
        assert SIMPLE_MESSAGE_LENGTH == 15
        assert SIGNAL_LENGTH_SHORT == 30
        assert SIGNAL_LENGTH_LONG == 300

    def test_length_threshold_ordering(self):
        from museon.core.message_constants import (
            SIMPLE_MESSAGE_LENGTH, SIGNAL_LENGTH_SHORT, SIGNAL_LENGTH_LONG,
        )
        assert SIMPLE_MESSAGE_LENGTH <= SIGNAL_LENGTH_SHORT < SIGNAL_LENGTH_LONG

    def test_exclude_keywords_contains_slash(self):
        from museon.core.message_constants import SIMPLE_EXCLUDE_KEYWORDS
        assert "/" in SIMPLE_EXCLUDE_KEYWORDS

    def test_greetings_are_frozenset(self):
        from museon.core.message_constants import SIMPLE_GREETINGS
        assert isinstance(SIMPLE_GREETINGS, frozenset)
        assert "你好" in SIMPLE_GREETINGS
        assert "OK" in SIMPLE_GREETINGS

    def test_loop_constants_are_strings(self):
        from museon.core.message_constants import LOOP_FAST, LOOP_SLOW, LOOP_EXPLORATION
        assert LOOP_FAST == "FAST_LOOP"
        assert LOOP_SLOW == "SLOW_LOOP"
        assert LOOP_EXPLORATION == "EXPLORATION_LOOP"

    def test_greetings_and_keywords_no_overlap(self):
        from museon.core.message_constants import SIMPLE_EXCLUDE_KEYWORDS, SIMPLE_GREETINGS
        overlap = SIMPLE_EXCLUDE_KEYWORDS & SIMPLE_GREETINGS
        assert len(overlap) == 0, f"Unexpected overlap: {overlap}"


class TestBrainIsSimpleConsistency:
    """驗證 brain._is_simple 邏輯的邊界行為。"""

    def _is_simple(self, content: str) -> bool:
        from museon.core.message_constants import SIMPLE_MESSAGE_LENGTH, SIMPLE_EXCLUDE_KEYWORDS
        return (
            len(content.strip()) < SIMPLE_MESSAGE_LENGTH
            and not any(kw in content for kw in SIMPLE_EXCLUDE_KEYWORDS)
        )

    def test_short_greeting_is_simple(self):
        assert self._is_simple("你好") is True

    def test_14_chars_is_simple(self):
        assert self._is_simple("一二三四五六七八九十一二三四") is True  # 14 chars

    def test_15_chars_not_simple(self):
        assert self._is_simple("一二三四五六七八九十一二三四五") is False  # 15 chars

    def test_short_with_keyword_not_simple(self):
        assert self._is_simple("分析") is False

    def test_slash_command_not_simple(self):
        assert self._is_simple("/help") is False

    def test_empty_is_simple(self):
        assert self._is_simple("") is True
