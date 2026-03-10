"""BDD step definitions for Session Resilience."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, scenarios, then, when

# ── Link feature file ──
scenarios("../../features/session_resilience.feature")


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

@pytest.fixture
def test_data_dir(tmp_path):
    """Provide a temporary data directory with session subdirectory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = data_dir / "_system" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def brain(test_data_dir):
    """Create a minimal MuseonBrain for testing session operations."""
    from museon.agent.brain import MuseonBrain
    b = MuseonBrain(data_dir=str(test_data_dir))
    return b


class Context:
    def __init__(self):
        self.brain = None
        self.messages = None
        self.response = None
        self.loaded_session = None

@pytest.fixture
def ctx():
    return Context()


# ═══════════════════════════════════════
# Background
# ═══════════════════════════════════════

@given("a MuseonBrain instance with test data directory")
def given_brain(brain, ctx):
    ctx.brain = brain


# ═══════════════════════════════════════
# Offline Flag
# ═══════════════════════════════════════

@when("the brain generates an offline response")
def when_offline_response(ctx):
    if ctx.messages is None:
        ctx.messages = [
            {"role": "user", "content": "Hello"},
        ]
    ctx.response = ctx.brain._offline_response(ctx.messages)


@then("the offline flag should be True")
def then_offline_flag_true(ctx):
    assert ctx.brain._offline_flag is True


# ═══════════════════════════════════════
# Offline Response Content
# ═══════════════════════════════════════

@given("messages contain a long assistant response and a short user message")
def given_mixed_messages(ctx):
    ctx.messages = [
        {"role": "assistant", "content": "台灣的 AI 產業正在快速發展" * 100},
        {"role": "user", "content": "你好嗎"},
    ]
    ctx._assistant_garbage = "台灣的 AI 產業正在快速發展"
    ctx._user_msg = "你好嗎"


@then("the response should contain the user message")
def then_response_has_user_msg(ctx):
    assert ctx._user_msg in ctx.response


@then("the response should not contain the assistant response content")
def then_response_no_assistant(ctx):
    assert ctx._assistant_garbage not in ctx.response


@given("messages contain a user message longer than 100 characters")
def given_long_user_msg(ctx):
    long_msg = "A" * 200
    ctx.messages = [{"role": "user", "content": long_msg}]


@then("the response user message excerpt should be at most 100 characters")
def then_excerpt_max_100(ctx):
    # The response format is: ...收到的訊息：「{user_msg[:100]}」
    # Extract content between 「 and 」
    start = ctx.response.index("「") + 1
    end = ctx.response.index("」")
    excerpt = ctx.response[start:end]
    assert len(excerpt) <= 100


# ═══════════════════════════════════════
# Session Loading & Sanitization
# ═══════════════════════════════════════

@given("a session file with repeated chaos patterns")
def given_polluted_session(ctx):
    chaos = "台灣的 AI 產業正在快速發展" * 200  # >5000 chars, repeated pattern
    data = [
        {"role": "user", "content": "正常問題"},
        {"role": "assistant", "content": "正常回覆"},
        {"role": "assistant", "content": chaos},
    ]
    session_dir = ctx.brain.data_dir / "_system" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "test_polluted.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    ctx._session_id = "test_polluted"


@when("the session is loaded from disk")
def when_load_session(ctx):
    ctx.loaded_session = ctx.brain._load_session_from_disk(ctx._session_id)


@then("the polluted messages should be filtered out")
def then_polluted_filtered(ctx):
    for msg in ctx.loaded_session:
        content = msg.get("content", "")
        assert len(content) <= 5000 or content.count(content[:50]) <= 3


@then("the clean messages should remain")
def then_clean_remain(ctx):
    contents = [m.get("content", "") for m in ctx.loaded_session]
    assert "正常問題" in contents or "正常回覆" in contents


@given("a session file with normal conversation")
def given_normal_session(ctx):
    data = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什麼我可以幫你的嗎？"},
    ]
    session_dir = ctx.brain.data_dir / "_system" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "test_normal.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    ctx._session_id = "test_normal"


@then("all messages should be preserved")
def then_all_preserved(ctx):
    assert len(ctx.loaded_session) == 2
    assert ctx.loaded_session[0]["content"] == "你好"


@given("an empty session file")
def given_empty_session(ctx):
    session_dir = ctx.brain.data_dir / "_system" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "test_empty.json").write_text("[]", encoding="utf-8")
    ctx._session_id = "test_empty"


@then("the result should be an empty list")
def then_empty_list(ctx):
    assert ctx.loaded_session == [] or ctx.loaded_session is None
