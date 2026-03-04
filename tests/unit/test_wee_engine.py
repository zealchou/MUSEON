"""Tests for WEEEngine — WEE 自動循環引擎.

依據 SELF_ITERATION BDD Spec 驗證：
- 信噪過濾（20 關鍵字 + 長度門檻）
- 啟發式 4D 評分（各項加減分 + clamp）
- Session 管理
- auto_cycle 完整流程
- Per-user 實例快取
- Nightly 壓縮 / 融合
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from museon.core.event_bus import EventBus
from museon.workflow.models import FourDScore
from museon.evolution.wee_engine import (
    WEEEngine,
    _SIGNAL_KEYWORDS_ZH,
    _MIN_CONTENT_LENGTH,
    _FAILURE_KEYWORDS,
    _PROCEDURAL_KW,
    _ANALYTICAL_KW,
    _DECISIONAL_KW,
    _PLATEAU_CHECK_INTERVAL,
    get_wee_engine,
    _reset_wee_instances,
)


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_instances():
    """每個測試前重置 per-user 實例快取."""
    _reset_wee_instances()
    yield
    _reset_wee_instances()


@pytest.fixture
def tmp_workspace(tmp_path):
    """提供暫時 workspace 目錄."""
    return tmp_path


@pytest.fixture
def event_bus():
    """提供乾淨的 EventBus 實例."""
    return EventBus()


@pytest.fixture
def mock_memory():
    """提供 mock MemoryManager."""
    mm = MagicMock()
    mm.store.return_value = str(uuid.uuid4())
    mm.recall.return_value = []
    return mm


@pytest.fixture
def wee(tmp_workspace, event_bus, mock_memory):
    """提供 WEEEngine 實例."""
    return WEEEngine(
        user_id="user-1",
        workspace=tmp_workspace,
        event_bus=event_bus,
        memory_manager=mock_memory,
    )


@pytest.fixture
def wee_no_memory(tmp_workspace, event_bus):
    """提供無 MemoryManager 的 WEEEngine 實例."""
    return WEEEngine(
        user_id="user-1",
        workspace=tmp_workspace,
        event_bus=event_bus,
        memory_manager=None,
    )


# ═══════════════════════════════════════════
# TestSignalNoiseFilter — 信噪過濾
# ═══════════════════════════════════════════


class TestSignalNoiseFilter:
    """信噪過濾測試."""

    def test_signal_keywords_count(self):
        """信號關鍵字共 20 個."""
        assert len(_SIGNAL_KEYWORDS_ZH) == 20

    def test_keyword_triggers_signal(self, wee):
        """含信號關鍵字 → True."""
        for kw in list(_SIGNAL_KEYWORDS_ZH)[:5]:
            assert wee.is_signal(f"我{kw}了這件事") is True

    def test_all_keywords_recognized(self, wee):
        """所有 20 個關鍵字都能被識別."""
        for kw in _SIGNAL_KEYWORDS_ZH:
            assert wee.is_signal(kw) is True, f"keyword '{kw}' not recognized"

    def test_long_content_is_signal(self, wee):
        """長度 >= 15 字元 → True."""
        content = "a" * _MIN_CONTENT_LENGTH
        assert wee.is_signal(content) is True

    def test_short_content_no_keyword_is_noise(self, wee):
        """短且無關鍵字 → False."""
        assert wee.is_signal("hi") is False
        assert wee.is_signal("ok") is False

    def test_empty_is_noise(self, wee):
        """空字串 → False."""
        assert wee.is_signal("") is False
        assert wee.is_signal("   ") is False

    def test_none_is_noise(self, wee):
        """None → False."""
        assert wee.is_signal(None) is False

    def test_just_below_length_threshold(self, wee):
        """剛好低於長度門檻 → False（無關鍵字時）."""
        content = "a" * (_MIN_CONTENT_LENGTH - 1)
        assert wee.is_signal(content) is False

    def test_keyword_in_short_content(self, wee):
        """短內容但含關鍵字 → True."""
        assert wee.is_signal("學到") is True
        assert wee.is_signal("成功") is True


# ═══════════════════════════════════════════
# TestHeuristicScoring — 啟發式評分
# ═══════════════════════════════════════════


class TestHeuristicScoring:
    """啟發式 4D 評分測試."""

    def test_base_score(self, wee):
        """基礎分：S=5, Q=5-0.5(short resp), A=5, L=4."""
        data = {"user_content": "", "response_content": ""}
        score = wee.heuristic_score(data)
        assert score.speed == 5.0
        # 空回應觸發 short response penalty (-0.5)
        assert score.quality == 4.5
        assert score.alignment == 5.0
        assert score.leverage == 4.0

    def test_high_q_score_boost(self, wee):
        """Q-Score high → quality +1.0 -0.5(short resp) = 5.5."""
        data = {
            "user_content": "",
            "response_content": "",
            "q_score_tier": "high",
        }
        score = wee.heuristic_score(data)
        assert score.quality == 5.5  # 5.0 + 1.0 - 0.5(short)

    def test_low_q_score_penalty(self, wee):
        """Q-Score low → quality -1.5 -0.5(short resp) = 3.0."""
        data = {
            "user_content": "",
            "response_content": "",
            "q_score_tier": "low",
        }
        score = wee.heuristic_score(data)
        assert score.quality == 3.0  # 5.0 - 1.5 - 0.5(short)

    def test_long_response_boost(self, wee):
        """回應 > 500 字元 → quality +0.5."""
        data = {
            "user_content": "",
            "response_content": "x" * 501,
        }
        score = wee.heuristic_score(data)
        assert score.quality == 5.5

    def test_short_response_penalty(self, wee):
        """回應 < 50 字元 → quality -0.5."""
        data = {
            "user_content": "",
            "response_content": "short",
        }
        score = wee.heuristic_score(data)
        assert score.quality == 4.5

    def test_failure_detection_penalty(self, wee):
        """偵測到失敗 → quality -2.0, alignment -1.0."""
        data = {
            "user_content": "這次失敗了",
            "response_content": "",
        }
        score = wee.heuristic_score(data)
        # quality: 5 - 2.0 - 0.5 (short response) + 0.5 (signal keyword) = 3.0
        # alignment: 5 - 1.0 = 4.0
        assert score.quality < 5.0
        assert score.alignment < 5.0

    def test_long_user_input_boost(self, wee):
        """使用者輸入 > 100 字元 → alignment +0.5."""
        data = {
            "user_content": "x" * 101,
            "response_content": "",
        }
        score = wee.heuristic_score(data)
        assert score.alignment == 5.5

    def test_leverage_short_in_long_out(self, wee):
        """短輸入 + 長輸出 → leverage +1.0."""
        data = {
            "user_content": "hi",
            "response_content": "x" * 301,
        }
        score = wee.heuristic_score(data)
        assert score.leverage == 5.0  # 4.0 + 1.0

    def test_procedural_keyword_boost(self, wee):
        """程序性關鍵字 → quality +0.5."""
        data = {
            "user_content": "步驟一：先準備材料",
            "response_content": "",
        }
        score = wee.heuristic_score(data)
        # quality: 5 + 0.5(procedural) - 0.5(short response) + 0.5(signal) = 5.5
        # (contains 嘗試 is not in procedural, but 步驟 is)
        assert score.quality >= 5.0

    def test_analytical_keyword_boost(self, wee):
        """分析性關鍵字 → alignment +0.5."""
        data = {
            "user_content": "分析這個情況",
            "response_content": "",
        }
        score = wee.heuristic_score(data)
        assert score.alignment >= 5.5

    def test_decisional_keyword_boost(self, wee):
        """決策性關鍵字 → leverage +0.5."""
        data = {
            "user_content": "最後決定用方案 A",
            "response_content": "",
        }
        score = wee.heuristic_score(data)
        # leverage: 4 + 0.5(decisional)
        assert score.leverage >= 4.5

    def test_matched_skills_boost(self, wee):
        """有 matched_skills → leverage +0.5."""
        data = {
            "user_content": "",
            "response_content": "",
            "matched_skills": ["skill-a"],
        }
        score = wee.heuristic_score(data)
        assert score.leverage == 4.5  # 4.0 + 0.5

    def test_signal_keyword_quality_boost(self, wee):
        """信號關鍵字 → quality +0.5."""
        data = {
            "user_content": "我學到了很多東西，真的很值得",
            "response_content": "",
        }
        score = wee.heuristic_score(data)
        # quality: 5 + 0.5(signal) - 0.5(short response) = 5.0
        assert score.quality >= 5.0

    def test_clamp_prevents_overflow(self, wee):
        """所有分數 clamp [0, 10]."""
        data = {
            "user_content": "",
            "response_content": "",
            "q_score_tier": "low",
        }
        score = wee.heuristic_score(data)
        assert score.speed >= 0 and score.speed <= 10
        assert score.quality >= 0 and score.quality <= 10
        assert score.alignment >= 0 and score.alignment <= 10
        assert score.leverage >= 0 and score.leverage <= 10

    def test_multiple_boosts_stack(self, wee):
        """多重加分可疊加."""
        data = {
            "user_content": "我決定用分析的方法步驟來完成這個規劃任務" + "x" * 60,
            "response_content": "x" * 600,
            "q_score_tier": "high",
            "matched_skills": ["skill-a", "skill-b"],
        }
        score = wee.heuristic_score(data)
        # Multiple boosts should stack
        assert score.quality > 5.0
        assert score.leverage > 4.0


# ═══════════════════════════════════════════
# TestFailureDetection — 失敗偵測
# ═══════════════════════════════════════════


class TestFailureDetection:
    """失敗偵測測試."""

    def test_all_failure_keywords(self, wee):
        """所有失敗關鍵字都能偵測."""
        for kw in _FAILURE_KEYWORDS:
            assert wee._detect_failure(f"something {kw} happened") is True

    def test_no_failure_normal(self, wee):
        """正常內容無失敗."""
        assert wee._detect_failure("一切順利完成") is False

    def test_empty_no_failure(self, wee):
        """空內容無失敗."""
        assert wee._detect_failure("") is False

    def test_failure_keyword_count(self):
        """失敗關鍵字共 7 個."""
        assert len(_FAILURE_KEYWORDS) == 7


# ═══════════════════════════════════════════
# TestSessionManagement — Session 管理
# ═══════════════════════════════════════════


class TestSessionManagement:
    """Session 管理測試."""

    def test_auto_session_format(self, wee):
        """自動 session ID 格式: session_YYYY-MM-DD_xxxxxxxx."""
        session = wee._ensure_session()
        assert session.startswith("session_")
        parts = session.split("_")
        assert len(parts) == 3
        # 日期部分
        date_part = parts[1]
        assert len(date_part) == 10  # YYYY-MM-DD

    def test_same_day_same_session(self, wee):
        """同一天多次呼叫回傳同一 session."""
        s1 = wee._ensure_session()
        s2 = wee._ensure_session()
        assert s1 == s2

    def test_date_change_new_session(self, wee):
        """日期切換 → 新 session."""
        s1 = wee._ensure_session()
        # 模擬日期切換
        wee._session_date = "2025-01-01"
        s2 = wee._ensure_session()
        assert s1 != s2

    def test_interaction_count_reset_on_new_session(self, wee):
        """新 session 重置互動計數."""
        wee._ensure_session()
        wee._interaction_count = 10
        # 模擬日期切換
        wee._session_date = "2025-01-01"
        wee._ensure_session()
        assert wee._interaction_count == 0


# ═══════════════════════════════════════════
# TestAutoCycle — 自動循環
# ═══════════════════════════════════════════


class TestAutoCycle:
    """auto_cycle 完整流程測試."""

    def test_signal_recorded(self, wee):
        """信號內容被記錄."""
        data = {
            "user_content": "我今天學到了一個重要的教訓，很有啟發",
            "response_content": "這是一個很好的學習經驗，值得記錄下來",
            "source": "chat",
        }
        result = wee.auto_cycle(data)
        assert result is not None
        assert "workflow_id" in result
        assert "score" in result
        assert result["outcome"] == "success"

    def test_noise_skipped(self, wee):
        """噪音被跳過 → None."""
        data = {
            "user_content": "ok",
            "response_content": "ok",
        }
        result = wee.auto_cycle(data)
        assert result is None

    def test_noise_counter_incremented(self, wee):
        """噪音計數器遞增."""
        data = {"user_content": "hi", "response_content": "hi"}
        wee.auto_cycle(data)
        assert wee._total_noise == 1

    def test_signal_counter_incremented(self, wee):
        """信號計數器遞增."""
        data = {
            "user_content": "我發現了一個問題需要解決",
            "response_content": "好的讓我們來看看",
        }
        wee.auto_cycle(data)
        assert wee._total_signals == 1

    def test_failure_outcome(self, wee):
        """偵測到失敗 → outcome = 'failed'."""
        data = {
            "user_content": "這次操作失敗了",
            "response_content": "讓我們找出失敗的原因",
        }
        result = wee.auto_cycle(data)
        assert result is not None
        assert result["outcome"] == "failed"

    def test_interaction_count_increments(self, wee):
        """互動計數遞增."""
        for i in range(3):
            data = {
                "user_content": f"問題第 {i} 個，我想要學到更多知識",
                "response_content": "回覆",
            }
            wee.auto_cycle(data)
        assert wee._interaction_count == 3

    def test_plateau_check_at_interval(self, wee):
        """每 N 輪觸發高原檢查."""
        for i in range(_PLATEAU_CHECK_INTERVAL):
            data = {
                "user_content": f"測試互動 {i} — 我學到了一些東西",
                "response_content": "回覆內容",
            }
            result = wee.auto_cycle(data)

        # 第 5 輪應有 plateau_check 結果
        assert result is not None
        assert result["plateau_check"] is not None

    def test_no_plateau_check_before_interval(self, wee):
        """N 輪之前不觸發高原檢查."""
        for i in range(_PLATEAU_CHECK_INTERVAL - 1):
            data = {
                "user_content": f"測試互動 {i} — 我決定要改進",
                "response_content": "好的",
            }
            result = wee.auto_cycle(data)

        # 第 4 輪不應有 plateau_check
        assert result is not None
        assert result["plateau_check"] is None

    def test_empty_data_returns_none(self, wee):
        """空 data → None."""
        assert wee.auto_cycle({}) is None
        assert wee.auto_cycle(None) is None

    def test_session_id_in_result(self, wee):
        """結果包含 session_id."""
        data = {
            "user_content": "我完成了一個重要的目標",
            "response_content": "恭喜完成目標",
        }
        result = wee.auto_cycle(data)
        assert result is not None
        assert "session_id" in result
        assert result["session_id"].startswith("session_")

    def test_source_becomes_workflow_name(self, wee):
        """data['source'] 成為 workflow name."""
        data = {
            "user_content": "我學到了新技巧",
            "response_content": "很好",
            "source": "my_skill",
        }
        result = wee.auto_cycle(data)
        assert result is not None
        # 驗證 workflow 已建立
        workflows = wee._wf_engine.list_workflows("user-1")
        names = [w.name for w in workflows]
        assert "my_skill" in names


# ═══════════════════════════════════════════
# TestPerUserInstances — Per-user 實例快取
# ═══════════════════════════════════════════


class TestPerUserInstances:
    """Per-user 實例快取測試."""

    def test_same_user_same_instance(self, tmp_workspace, event_bus):
        """同一 user → 同一實例."""
        e1 = get_wee_engine("user-1", tmp_workspace, event_bus)
        e2 = get_wee_engine("user-1", tmp_workspace, event_bus)
        assert e1 is e2

    def test_different_user_different_instance(self, tmp_workspace, event_bus):
        """不同 user → 不同實例."""
        e1 = get_wee_engine("user-1", tmp_workspace, event_bus)
        e2 = get_wee_engine("user-2", tmp_workspace, event_bus)
        assert e1 is not e2

    def test_reset_clears_cache(self, tmp_workspace, event_bus):
        """reset 清除快取."""
        e1 = get_wee_engine("user-1", tmp_workspace, event_bus)
        _reset_wee_instances()
        e2 = get_wee_engine("user-1", tmp_workspace, event_bus)
        assert e1 is not e2


# ═══════════════════════════════════════════
# TestCompressDaily — 壓縮
# ═══════════════════════════════════════════


class TestCompressDaily:
    """compress_daily Nightly 壓縮測試."""

    def test_compress_with_records(self, wee, mock_memory):
        """有記錄的壓縮 → compressed = True."""
        # 先記錄一些互動
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        for i in range(3):
            data = {
                "user_content": f"學到了重要的第 {i} 課",
                "response_content": "很好的學習經驗",
            }
            wee.auto_cycle(data)

        # 壓縮今天的記錄
        result = wee.compress_daily(target_date=today)
        assert result["compressed"] is True
        assert result["interactions"] == 3
        assert mock_memory.store.called

    def test_compress_no_workflows(self, wee_no_memory, tmp_workspace):
        """無工作流 → compressed = False."""
        engine = WEEEngine(
            user_id="user-new",
            workspace=tmp_workspace,
            event_bus=None,
            memory_manager=None,
        )
        result = engine.compress_daily()
        assert result["compressed"] is False
        assert result["reason"] == "no_workflows"

    def test_compress_no_records_for_date(self, wee):
        """指定日期無記錄 → compressed = False."""
        # 先記錄以建立工作流
        data = {
            "user_content": "我發現了一些問題",
            "response_content": "回覆",
        }
        wee.auto_cycle(data)

        result = wee.compress_daily(target_date="2020-01-01")
        assert result["compressed"] is False
        assert result["reason"] == "no_records_for_date"

    def test_compress_without_memory_manager(self, wee_no_memory):
        """無 MemoryManager → crystal 仍可壓縮但 ID 為空."""
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        data = {
            "user_content": "我學到了很多東西",
            "response_content": "很好的學習",
        }
        wee_no_memory.auto_cycle(data)

        result = wee_no_memory.compress_daily(target_date=today)
        if result["compressed"]:
            assert result["crystal_id"] == ""

    def test_compress_crystal_content_format(self, wee, mock_memory):
        """crystal 內容格式正確."""
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        data = {
            "user_content": "我完成了一個重要的目標",
            "response_content": "恭喜",
        }
        wee.auto_cycle(data)

        result = wee.compress_daily(target_date=today)
        if result["compressed"]:
            assert "[Daily Crystal" in result["summary"]
            assert "interactions=" in result["summary"]
            assert "avg_composite=" in result["summary"]


# ═══════════════════════════════════════════
# TestFuseWeekly — 融合
# ═══════════════════════════════════════════


class TestFuseWeekly:
    """fuse_weekly Nightly 融合測試."""

    def test_fuse_insufficient_crystals(self, wee, mock_memory):
        """不足 3 筆 daily crystal → fused = False."""
        mock_memory.recall.return_value = [
            {"tags": ["wee_daily_crystal"], "content": "crystal 1"},
        ]
        result = wee.fuse_weekly()
        assert result["fused"] is False
        assert result["reason"] == "insufficient_crystals"

    def test_fuse_with_enough_crystals(self, wee, mock_memory):
        """3+ daily crystals → fused = True."""
        mock_memory.recall.return_value = [
            {"tags": ["wee_daily_crystal"], "content": "crystal 1"},
            {"tags": ["wee_daily_crystal"], "content": "crystal 2"},
            {"tags": ["wee_daily_crystal"], "content": "crystal 3"},
        ]
        result = wee.fuse_weekly()
        assert result["fused"] is True
        assert result["daily_crystals"] == 3
        assert mock_memory.store.called

    def test_fuse_without_memory_manager(self, wee_no_memory):
        """無 MemoryManager → fused = False."""
        result = wee_no_memory.fuse_weekly()
        assert result["fused"] is False
        assert result["reason"] == "no_memory_manager"

    def test_fuse_crystal_stored_in_l2_sem(self, wee, mock_memory):
        """weekly crystal 存入 L2_sem."""
        mock_memory.recall.return_value = [
            {"tags": ["wee_daily_crystal"], "content": "c1"},
            {"tags": ["wee_daily_crystal"], "content": "c2"},
            {"tags": ["wee_daily_crystal"], "content": "c3"},
            {"tags": ["wee_daily_crystal"], "content": "c4"},
        ]
        wee.fuse_weekly()
        # 確認 store 被呼叫
        if mock_memory.store.called:
            call_kwargs = mock_memory.store.call_args
            # 檢查 layer 參數
            assert call_kwargs[1]["layer"] == "L2_sem" or (
                len(call_kwargs[0]) > 2 and call_kwargs[0][2] == "L2_sem"
            )

    def test_fuse_filters_non_crystal_results(self, wee, mock_memory):
        """過濾非 wee_daily_crystal 的結果."""
        mock_memory.recall.return_value = [
            {"tags": ["wee_daily_crystal"], "content": "c1"},
            {"tags": ["other_tag"], "content": "not a crystal"},
            {"tags": ["wee_daily_crystal"], "content": "c2"},
            {"tags": [], "content": "no tags"},
        ]
        result = wee.fuse_weekly()
        # 只有 2 筆 crystal → 不足 3 → not fused
        assert result["fused"] is False
        assert result["crystal_count"] == 2


# ═══════════════════════════════════════════
# TestGetStatus — 狀態摘要
# ═══════════════════════════════════════════


class TestGetStatus:
    """get_status 狀態摘要測試."""

    def test_required_fields(self, wee):
        """狀態包含所有必要欄位."""
        status = wee.get_status()
        required = [
            "user_id",
            "current_session",
            "interaction_count",
            "total_signals",
            "total_noise",
            "signal_ratio",
            "proficiency",
            "active_workflows",
        ]
        for field in required:
            assert field in status, f"missing field: {field}"

    def test_initial_status(self, wee):
        """初始狀態值."""
        status = wee.get_status()
        assert status["user_id"] == "user-1"
        assert status["interaction_count"] == 0
        assert status["total_signals"] == 0
        assert status["total_noise"] == 0
        assert status["signal_ratio"] == 0.0
        assert status["active_workflows"] == 0

    def test_status_after_interactions(self, wee):
        """互動後狀態更新."""
        # 3 signal + 2 noise
        for i in range(3):
            wee.auto_cycle({
                "user_content": f"我學到了第 {i} 個重要的教訓",
                "response_content": "很好的觀察",
            })
        for _ in range(2):
            wee.auto_cycle({
                "user_content": "hi",
                "response_content": "hi",
            })

        status = wee.get_status()
        assert status["total_signals"] == 3
        assert status["total_noise"] == 2
        assert abs(status["signal_ratio"] - 0.6) < 0.01
        assert status["active_workflows"] >= 1


# ═══════════════════════════════════════════
# TestKeywordSets — 關鍵字集合驗證
# ═══════════════════════════════════════════


class TestKeywordSets:
    """關鍵字集合常數驗證."""

    def test_procedural_keywords(self):
        """程序性關鍵字集合非空."""
        assert len(_PROCEDURAL_KW) >= 5

    def test_analytical_keywords(self):
        """分析性關鍵字集合非空."""
        assert len(_ANALYTICAL_KW) >= 3

    def test_decisional_keywords(self):
        """決策性關鍵字集合非空."""
        assert len(_DECISIONAL_KW) >= 5

    def test_failure_keywords(self):
        """失敗關鍵字集合非空."""
        assert len(_FAILURE_KEYWORDS) >= 5

    def test_plateau_check_interval(self):
        """高原檢查間隔 = 5."""
        assert _PLATEAU_CHECK_INTERVAL == 5
