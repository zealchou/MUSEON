"""Tests for InteractionRequest/Response system (v10.0).

Tests:
- ChoiceOption / InteractionRequest / InteractionResponse data structures
- BrainResponse with interaction field
- InteractionQueue submit / resolve / wait / timeout / cleanup
"""

import asyncio
import pytest
from datetime import datetime

from museon.gateway.message import (
    BrainResponse,
    ChoiceOption,
    InteractionRequest,
    InteractionResponse,
)
from museon.gateway.interaction import InteractionQueue


# ══════════════════════════════════════════════════
# Data Structures
# ══════════════════════════════════════════════════


class TestChoiceOption:
    def test_defaults(self):
        opt = ChoiceOption(label="Option A")
        assert opt.label == "Option A"
        assert opt.value == "Option A"  # defaults to label
        assert opt.description == ""

    def test_explicit_value(self):
        opt = ChoiceOption(label="選項A", value="opt_a", description="第一個選項")
        assert opt.value == "opt_a"
        assert opt.description == "第一個選項"

    def test_to_dict(self):
        opt = ChoiceOption(label="Test", value="v", description="d")
        d = opt.to_dict()
        assert d == {"label": "Test", "value": "v", "description": "d"}


class TestInteractionRequest:
    def test_basic(self):
        req = InteractionRequest(
            question_id="q123",
            question="你想聚焦哪個方向？",
            options=[
                ChoiceOption(label="策略層面", value="strategy"),
                ChoiceOption(label="執行層面", value="execution"),
            ],
        )
        assert req.question_id == "q123"
        assert len(req.options) == 2
        assert req.multi_select is False
        assert req.allow_free_text is True
        assert req.timeout_seconds == 120

    def test_with_header_and_context(self):
        req = InteractionRequest(
            question_id="q456",
            question="這個問題有多種理解方式",
            options=[ChoiceOption(label="A"), ChoiceOption(label="B")],
            header="思維前置",
            context="query-clarity",
        )
        assert req.header == "思維前置"
        assert req.context == "query-clarity"

    def test_to_dict(self):
        req = InteractionRequest(
            question_id="q789",
            question="Test?",
            options=[ChoiceOption(label="X", value="x")],
            header="H",
            multi_select=True,
        )
        d = req.to_dict()
        assert d["question_id"] == "q789"
        assert d["multi_select"] is True
        assert len(d["options"]) == 1
        assert d["options"][0]["value"] == "x"


class TestInteractionResponse:
    def test_single_select(self):
        resp = InteractionResponse(
            question_id="q123",
            selected=["strategy"],
            responder_id="user_001",
            channel="telegram",
        )
        assert resp.get_choice_text() == "strategy"
        assert resp.timed_out is False

    def test_multi_select(self):
        resp = InteractionResponse(
            question_id="q123",
            selected=["A", "B", "C"],
        )
        assert resp.get_choice_text() == "A, B, C"

    def test_free_text(self):
        resp = InteractionResponse(
            question_id="q123",
            selected=[],
            free_text="我想要自定義方向",
        )
        assert resp.get_choice_text() == "我想要自定義方向"

    def test_timeout(self):
        resp = InteractionResponse(
            question_id="q123",
            timed_out=True,
        )
        assert resp.timed_out is True
        assert resp.get_choice_text() == "(未選擇)"

    def test_to_dict(self):
        resp = InteractionResponse(
            question_id="q1",
            selected=["v1"],
            channel="discord",
        )
        d = resp.to_dict()
        assert d["question_id"] == "q1"
        assert d["selected"] == ["v1"]
        assert d["channel"] == "discord"


class TestBrainResponseWithInteraction:
    def test_no_interaction(self):
        br = BrainResponse(text="Hello")
        assert br.has_interaction() is False
        assert br.interaction is None

    def test_with_interaction(self):
        req = InteractionRequest(
            question_id="q1",
            question="Pick one",
            options=[ChoiceOption(label="A"), ChoiceOption(label="B")],
        )
        br = BrainResponse(text="I need your input", interaction=req)
        assert br.has_interaction() is True
        assert br.interaction.question_id == "q1"

    def test_to_dict_with_interaction(self):
        req = InteractionRequest(
            question_id="q1",
            question="Pick one",
            options=[ChoiceOption(label="A")],
        )
        br = BrainResponse(text="text", interaction=req)
        d = br.to_dict()
        assert "interaction" in d
        assert d["interaction"]["question_id"] == "q1"

    def test_to_dict_without_interaction(self):
        br = BrainResponse(text="text")
        d = br.to_dict()
        assert "interaction" not in d


# ══════════════════════════════════════════════════
# InteractionQueue
# ══════════════════════════════════════════════════


class TestInteractionQueue:
    def test_submit(self):
        q = InteractionQueue()
        req = InteractionRequest(
            question_id="q1",
            question="Test?",
            options=[ChoiceOption(label="A")],
        )
        qid = q.submit(req)
        assert qid == "q1"
        assert q.is_pending("q1") is True
        assert q.pending_count == 1

    def test_resolve(self):
        q = InteractionQueue()
        req = InteractionRequest(
            question_id="q1",
            question="Test?",
            options=[ChoiceOption(label="A")],
        )
        q.submit(req)

        resp = InteractionResponse(
            question_id="q1",
            selected=["A"],
            channel="telegram",
        )
        result = q.resolve("q1", resp)
        assert result is True
        assert q.is_pending("q1") is False

    def test_resolve_unknown(self):
        q = InteractionQueue()
        resp = InteractionResponse(question_id="unknown", selected=["x"])
        result = q.resolve("unknown", resp)
        assert result is False

    def test_resolve_duplicate(self):
        q = InteractionQueue()
        req = InteractionRequest(
            question_id="q1",
            question="Test?",
            options=[ChoiceOption(label="A")],
        )
        q.submit(req)

        resp = InteractionResponse(question_id="q1", selected=["A"])
        q.resolve("q1", resp)
        # Second resolve should fail
        result = q.resolve("q1", resp)
        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_response(self):
        q = InteractionQueue()
        req = InteractionRequest(
            question_id="q1",
            question="Test?",
            options=[ChoiceOption(label="A")],
            timeout_seconds=5,
        )
        q.submit(req)

        # Resolve in background after short delay
        async def resolve_later():
            await asyncio.sleep(0.1)
            resp = InteractionResponse(question_id="q1", selected=["A"])
            q.resolve("q1", resp)

        asyncio.create_task(resolve_later())

        response = await q.wait_for_response("q1", timeout=3)
        assert response.selected == ["A"]
        assert response.timed_out is False

    @pytest.mark.asyncio
    async def test_wait_timeout(self):
        q = InteractionQueue()
        req = InteractionRequest(
            question_id="q1",
            question="Test?",
            options=[ChoiceOption(label="A")],
            timeout_seconds=1,
        )
        q.submit(req)

        # Don't resolve — should timeout
        response = await q.wait_for_response("q1", timeout=0.2)
        assert response.timed_out is True

    @pytest.mark.asyncio
    async def test_wait_unknown_qid(self):
        q = InteractionQueue()
        response = await q.wait_for_response("nonexistent")
        assert response.timed_out is True

    def test_get_request(self):
        q = InteractionQueue()
        req = InteractionRequest(
            question_id="q1",
            question="Test?",
            options=[ChoiceOption(label="A")],
            context="deep-think",
        )
        q.submit(req)
        retrieved = q.get_request("q1")
        assert retrieved is not None
        assert retrieved.context == "deep-think"

    def test_get_request_unknown(self):
        q = InteractionQueue()
        assert q.get_request("unknown") is None

    def test_cleanup_expired(self):
        q = InteractionQueue()
        req = InteractionRequest(
            question_id="q1",
            question="Test?",
            options=[ChoiceOption(label="A")],
        )
        q.submit(req)

        # Manually age the entry
        q._pending["q1"]["created_at"] = datetime(2020, 1, 1)

        cleaned = q.cleanup_expired(max_age_hours=1)
        assert cleaned == 1
        assert q.pending_count == 0

    def test_stats(self):
        q = InteractionQueue()
        req1 = InteractionRequest(question_id="q1", question="T?", options=[ChoiceOption(label="A")])
        req2 = InteractionRequest(question_id="q2", question="T?", options=[ChoiceOption(label="B")])
        q.submit(req1)
        q.submit(req2)
        q.resolve("q1", InteractionResponse(question_id="q1", selected=["A"]))

        stats = q.stats()
        assert stats["total"] == 2
        assert stats["pending"] == 1
        assert stats["resolved"] == 1


# ══════════════════════════════════════════════════
# Telegram Callback Data Size
# ══════════════════════════════════════════════════


class TestTelegramCallbackSize:
    """驗證 callback_data 符合 Telegram 64 bytes 限制."""

    def test_short_callback_data(self):
        qid = "abc123"
        value = "opt_a"
        cb_data = f"choice:{qid}:{value}"
        assert len(cb_data.encode("utf-8")) <= 64

    def test_uuid_callback_data(self):
        """12 char hex question_id + short value should fit."""
        qid = "a1b2c3d4e5f6"  # 12 chars
        value = "strategy"
        cb_data = f"choice:{qid}:{value}"
        assert len(cb_data.encode("utf-8")) <= 64

    def test_freetext_callback_data(self):
        qid = "a1b2c3d4e5f6"
        cb_data = f"choice:{qid}:__freetext__"
        assert len(cb_data.encode("utf-8")) <= 64

    def test_chinese_value_may_exceed(self):
        """Chinese characters take 3 bytes each in UTF-8."""
        qid = "a1b2c3d4e5f6"
        value = "策略層面分析報告"  # 8 chars * 3 bytes = 24 bytes
        cb_data = f"choice:{qid}:{value}"
        # Should be: 7 + 12 + 1 + 24 = 44 bytes — fits
        assert len(cb_data.encode("utf-8")) <= 64
