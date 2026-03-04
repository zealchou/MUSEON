"""Context Switcher BDD 測試.

依據 MULTI_AGENT_BDD_SPEC §4 驗證。
"""

import pytest

from museon.multiagent.context_switch import (
    COMPRESS_MAX_TOTAL,
    COMPRESS_MSG_COUNT,
    COMPRESS_MSG_MAX_CHARS,
    ContextSwitcher,
)


@pytest.fixture
def switcher():
    return ContextSwitcher()


class TestBasicSwitch:
    """Scenario: 基本切換."""

    def test_initial_dept_is_core(self, switcher):
        assert switcher.current_dept == "core"

    def test_switch_to_thunder(self, switcher):
        result = switcher.switch_to("thunder")
        assert result["switched"] is True
        assert result["from"] == "core"
        assert result["to"] == "thunder"
        assert switcher.current_dept == "thunder"

    def test_switch_count_increments(self, switcher):
        assert switcher.switch_count == 0
        switcher.switch_to("thunder")
        assert switcher.switch_count == 1
        switcher.switch_to("fire")
        assert switcher.switch_count == 2

    def test_invalid_dept(self, switcher):
        result = switcher.switch_to("nonexistent")
        assert result["switched"] is False
        assert result["reason"] == "department_not_found"

    def test_same_dept(self, switcher):
        result = switcher.switch_to("core")
        assert result["switched"] is False
        assert result["reason"] == "already_in_department"


class TestHistoryPreservation:
    """Scenario: 切換部門保留對話."""

    def test_history_preserved(self, switcher):
        switcher.add_message("user", "你好")
        switcher.add_message("assistant", "Hi!")
        switcher.switch_to("thunder")
        # core 歷史仍在
        history = switcher.get_history("core")
        assert len(history) == 2
        assert history[0]["content"] == "你好"

    def test_compressed_summary_injected(self, switcher):
        switcher.add_message("user", "分析一下市場狀況")
        switcher.switch_to("thunder")
        # thunder 收到壓縮摘要
        history = switcher.get_history("thunder")
        assert len(history) == 1
        assert history[0]["role"] == "system"
        assert "core→thunder" in history[0]["content"]

    def test_back_and_forth(self, switcher):
        """來回切換保留歷史."""
        # core: 2 條
        switcher.add_message("user", "msg1")
        switcher.add_message("assistant", "reply1")

        # switch to thunder: 3 條
        switcher.switch_to("thunder")
        switcher.add_message("user", "thunder msg")
        switcher.add_message("assistant", "thunder reply")

        # switch to fire
        switcher.switch_to("fire")

        # switch back to thunder
        switcher.switch_to("thunder")
        history = switcher.get_history("thunder")
        # thunder 應有：1(摘要) + 2(對話) + 1(fire摘要)
        assert len(history) >= 3


class TestCompression:
    """Scenario: 壓縮摘要."""

    def test_compress_truncates(self, switcher):
        # 加入超長訊息
        for i in range(10):
            switcher.add_message("user", f"Long message {i}: " + "x" * 100)
        result = switcher.switch_to("thunder")
        # 壓縮長度 ≤ 300
        assert result["compressed_len"] <= COMPRESS_MAX_TOTAL

    def test_empty_history_no_compression(self, switcher):
        result = switcher.switch_to("thunder")
        assert result["compressed_len"] == 0


class TestSwitchLog:
    """Scenario: 切換紀錄."""

    def test_log_records(self, switcher):
        switcher.switch_to("thunder")
        switcher.switch_to("fire")
        log = switcher.get_switch_log()
        assert len(log) == 2
        assert log[0]["from"] == "core"
        assert log[0]["to"] == "thunder"
        assert log[1]["from"] == "thunder"
        assert log[1]["to"] == "fire"


class TestStats:
    """Scenario: 統計資訊（Dashboard 用）."""

    def test_stats_structure(self, switcher):
        switcher.add_message("user", "hi")
        switcher.switch_to("thunder")
        stats = switcher.get_stats()
        assert stats["current_dept"] == "thunder"
        assert stats["switch_count"] == 1
        assert "core" in stats["dept_message_counts"]
        assert len(stats["recent_switches"]) == 1
