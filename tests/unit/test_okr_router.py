"""OKR Router BDD 測試.

依據 MULTI_AGENT_BDD_SPEC §3 驗證。
"""

import pytest

from museon.multiagent.okr_router import (
    CONFIDENCE_COMMAND,
    CONFIDENCE_DEFAULT,
    CONFIDENCE_FOLLOWUP,
    route,
    soft_route,
)


class TestCommandRouting:
    """Scenario: 指令直接路由."""

    def test_slash_thunder(self):
        dept, conf = route("/thunder 開始執行任務")
        assert dept == "thunder"
        assert conf == CONFIDENCE_COMMAND

    def test_slash_fire(self):
        dept, conf = route("/fire")
        assert dept == "fire"
        assert conf == CONFIDENCE_COMMAND

    def test_chinese_command_lei(self):
        dept, conf = route("/雷 快速推進")
        assert dept == "thunder"
        assert conf == CONFIDENCE_COMMAND

    def test_chinese_command_huo(self):
        dept, conf = route("/火")
        assert dept == "fire"
        assert conf == CONFIDENCE_COMMAND

    def test_all_flywheel_commands(self):
        commands = {
            "/thunder": "thunder", "/fire": "fire",
            "/lake": "lake", "/heaven": "heaven",
            "/wind": "wind", "/water": "water",
            "/mountain": "mountain", "/earth": "earth",
        }
        for cmd, expected in commands.items():
            dept, conf = route(cmd)
            assert dept == expected
            assert conf == CONFIDENCE_COMMAND


class TestKeywordRouting:
    """Scenario: 關鍵字路由."""

    def test_fire_keywords(self):
        dept, conf = route("幫我做品牌推廣計畫")
        assert dept == "fire"
        assert 0.4 <= conf <= 0.9

    def test_water_keywords(self):
        dept, conf = route("本月財務預算分析")
        assert dept == "water"
        assert 0.4 <= conf <= 0.9

    def test_thunder_keywords(self):
        dept, conf = route("啟動執行推進計畫")
        assert dept == "thunder"
        assert conf >= 0.6  # 至少 2 hits

    def test_multi_hit_high_confidence(self):
        dept, conf = route("行銷品牌推廣宣傳曝光社群")
        assert dept == "fire"
        assert conf == 0.9  # 多命中


class TestFollowupDetection:
    """Scenario: 後續對話留在當前部門."""

    def test_short_followup(self):
        dept, conf = route("好的，繼續", current_dept="thunder")
        assert dept == "thunder"
        assert conf == CONFIDENCE_FOLLOWUP

    def test_affirmation(self):
        dept, conf = route("嗯", current_dept="fire")
        assert dept == "fire"
        assert conf == CONFIDENCE_FOLLOWUP

    def test_long_message_not_followup(self):
        """長訊息不算後續對話."""
        dept, conf = route("好的，繼續，但是我想問一下關於品牌的事情", current_dept="thunder")
        # 超過 15 字元，不走 followup 路徑
        assert conf != CONFIDENCE_FOLLOWUP

    def test_core_no_followup(self):
        """在 core 時不觸發 followup."""
        dept, conf = route("好的", current_dept="core")
        assert conf != CONFIDENCE_FOLLOWUP


class TestDefaultRouting:
    """Scenario: 無匹配預設 core."""

    def test_hello(self):
        dept, conf = route("你好")
        assert dept == "core"
        assert conf == CONFIDENCE_DEFAULT

    def test_empty(self):
        dept, conf = route("")
        assert dept == "core"
        assert conf == CONFIDENCE_DEFAULT

    def test_random_text(self):
        dept, conf = route("晚安，睡覺了")
        assert dept == "core"
        assert conf == CONFIDENCE_DEFAULT


class TestSoftRoute:
    """Scenario: soft_route 飛輪分數."""

    def test_returns_8_departments(self):
        scores = soft_route("品牌行銷推廣")
        assert len(scores) == 8

    def test_fire_scores_highest(self):
        scores = soft_route("品牌行銷推廣")
        assert scores["fire"] > 0
        assert scores["fire"] >= scores["thunder"]

    def test_no_keywords_all_zero(self):
        scores = soft_route("你好")
        assert all(v == 0.0 for v in scores.values())

    def test_score_capped_at_1(self):
        scores = soft_route("行銷 品牌 推廣 宣傳 社群 曝光 火")
        assert scores["fire"] == 1.0
