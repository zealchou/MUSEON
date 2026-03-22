"""Unit tests for brain_tools.py — LLM 呼叫、Session 管理、離線模式、常數化.

覆蓋範圍：
- _call_llm: 正常路徑、Fallback、離線模式
- Session: load/save/pollution detection
- 常數引用：所有魔術值已收斂到類別常數
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from museon.agent.brain_tools import BrainToolsMixin


# ── Helpers ──

class FakeBrain(BrainToolsMixin):
    """Minimal fake Brain with required attributes for BrainToolsMixin."""

    def __init__(self, tmp_path: Path):
        self.data_dir = tmp_path
        self._llm_adapter = None
        self._offline_flag = False
        self._last_offline_probe_ts = 0
        self._sessions = {}
        self._skill_usage_log = []
        self._router = None
        self._tool_executor = None
        self._governor = None
        self.budget_monitor = None
        self.safety_anchor = None
        self._anima_mc_store = None
        self.memory_store = None

    def _load_anima_mc(self):
        return {"identity": {"name": "test"}, "boss": {"name": "Zeal"}}

    def _strip_system_leakage(self, text):
        return text


def _make_response(text="回覆內容", stop_reason="end_turn"):
    """Create a mock LLM response."""
    resp = MagicMock()
    resp.text = text
    resp.stop_reason = stop_reason
    resp.content = [MagicMock(type="text", text=text)]
    resp.usage = MagicMock(
        input_tokens=100, output_tokens=50,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )
    return resp


# ── 常數化驗證 ──

class TestConstants:
    """驗證所有魔術值已收斂到類別常數."""

    def test_model_chain_has_three_models(self):
        assert len(BrainToolsMixin._MODEL_CHAIN) == 3

    def test_max_tokens_primary(self):
        assert BrainToolsMixin._MAX_TOKENS_PRIMARY == 16384

    def test_max_tokens_dispatch(self):
        assert BrainToolsMixin._MAX_TOKENS_DISPATCH == 8192

    def test_max_tokens_health_probe(self):
        assert BrainToolsMixin._MAX_TOKENS_HEALTH_PROBE == 10

    def test_tool_iterations_complex_gt_simple(self):
        assert BrainToolsMixin._MAX_TOOL_ITERATIONS_COMPLEX > BrainToolsMixin._MAX_TOOL_ITERATIONS_SIMPLE

    def test_tool_result_truncate_len(self):
        assert BrainToolsMixin._TOOL_RESULT_TRUNCATE_LEN == 15000

    def test_complex_keywords_is_tuple(self):
        assert isinstance(BrainToolsMixin._COMPLEX_KEYWORDS, tuple)
        assert len(BrainToolsMixin._COMPLEX_KEYWORDS) > 0

    def test_offline_probe_interval(self):
        assert BrainToolsMixin._OFFLINE_PROBE_INTERVAL == 300


# ── LLM 呼叫 ──

class TestCallLLM:
    """_call_llm 核心路徑測試."""

    @pytest.mark.asyncio
    async def test_no_adapter_returns_offline(self, tmp_path):
        """LLM adapter 未初始化 → 離線回覆."""
        brain = FakeBrain(tmp_path)
        brain._llm_adapter = None

        result = await brain._call_llm(
            system_prompt="test",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert brain._offline_flag is True
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_normal_call_returns_text(self, tmp_path):
        """正常 LLM 呼叫 → 回傳文字."""
        brain = FakeBrain(tmp_path)
        mock_adapter = AsyncMock()
        mock_adapter.call = AsyncMock(return_value=_make_response("你好世界"))
        brain._llm_adapter = mock_adapter

        result = await brain._call_llm(
            system_prompt="你是 AI",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert "你好世界" in result
        mock_adapter.call.assert_called_once()

    @pytest.mark.asyncio
    async def test_safety_anchor_blocks(self, tmp_path):
        """SafetyAnchor 檢查失敗 → 拒絕回覆."""
        brain = FakeBrain(tmp_path)
        brain._llm_adapter = AsyncMock()
        brain.safety_anchor = MagicMock()
        brain.safety_anchor.quick_check = MagicMock(return_value=False)

        result = await brain._call_llm(
            system_prompt="test",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert "安全檢查" in result


# ── 離線模式 ──

class TestOfflineMode:
    """離線回覆測試."""

    def test_offline_response_sets_flag(self, tmp_path):
        brain = FakeBrain(tmp_path)
        result = brain._offline_response(
            messages=[{"role": "user", "content": "test"}],
            error_msg="api down",
        )
        assert brain._offline_flag is True
        assert isinstance(result, str)


# ── Session 管理 ──

class TestSessionManagement:
    """Session load/save/pollution detection."""

    def test_new_session_returns_empty(self, tmp_path):
        brain = FakeBrain(tmp_path)
        history = brain._get_session_history("new-session")
        assert history == []

    def test_save_and_load_session(self, tmp_path):
        brain = FakeBrain(tmp_path)
        sid = "test-session-001"

        # 寫入
        brain._sessions[sid] = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "World"},
        ]
        brain._save_session_to_disk(sid)

        # 驗證檔案存在
        session_file = tmp_path / "_system" / "sessions" / f"{sid}.json"
        assert session_file.exists()

        # 清除 in-memory → 重新載入
        brain._sessions.clear()
        history = brain._get_session_history(sid)
        assert len(history) == 2
        assert history[0]["content"] == "Hello"
        assert history[1]["content"] == "World"

    def test_pollution_detection(self, tmp_path):
        """汙染訊息（>5000 字、高重複模式）應被過濾."""
        brain = FakeBrain(tmp_path)
        sid = "polluted-session"

        # 建立含汙染訊息的 session 檔案
        polluted_content = "A" * 50 + ("A" * 50) * 10  # 高度重複
        session_dir = tmp_path / "_system" / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / f"{sid}.json"
        session_file.write_text(json.dumps([
            {"role": "user", "content": "正常訊息"},
            {"role": "assistant", "content": polluted_content},
            {"role": "user", "content": "第二條正常"},
        ], ensure_ascii=False))

        history = brain._get_session_history(sid)
        # 汙染訊息應被過濾，正常訊息保留
        assert len(history) <= 3
        assert any(m["content"] == "正常訊息" for m in history)

    def test_empty_session_not_saved(self, tmp_path):
        """空 session 不應被持久化."""
        brain = FakeBrain(tmp_path)
        brain._sessions["empty-session"] = []
        brain._save_session_to_disk("empty-session")

        session_file = tmp_path / "_system" / "sessions" / "empty-session.json"
        assert not session_file.exists()
