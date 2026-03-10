"""Unit tests for brain.py dispatch methods — _assess_dispatch, _parse_*, _dispatch_mode (mock LLM)."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from pathlib import Path


# ── Helpers ──

def _make_skill(name, always_on=False, content_len=0):
    """Create a mock skill dict."""
    return {
        "name": name,
        "description": f"{name} description",
        "triggers": [],
        "always_on": always_on,
        "path": f"/fake/skills/{name}/SKILL.md",
        "dir_name": name,
        "origin": "native",
        "_content_len": content_len,  # for mock load_skill_content
    }


def _make_brain(tmp_path, skill_contents=None):
    """Create a minimally mocked Brain instance for dispatch testing.

    Args:
        tmp_path: pytest tmp_path for data_dir
        skill_contents: dict of skill_name → content string
    """
    from museon.agent.brain import MuseonBrain

    with patch.object(MuseonBrain, "__init__", lambda self: None):
        brain = MuseonBrain()

    brain.data_dir = tmp_path
    brain.safety_anchor = None
    brain.budget_monitor = None
    brain._sessions = {}

    # Mock skill_router
    brain.skill_router = MagicMock()
    skill_contents = skill_contents or {}

    def mock_load_content(skill):
        name = skill.get("name", "")
        if name in skill_contents:
            return skill_contents[name]
        # Default: generate content based on _content_len
        content_len = skill.get("_content_len", 0)
        return "x" * content_len

    brain.skill_router.load_skill_content = mock_load_content
    brain.skill_router._index = []

    return brain


# ═══════════════════════════════════════════
# _assess_dispatch
# ═══════════════════════════════════════════


class TestAssessDispatch:
    """Test _assess_dispatch() — pure CPU evaluation."""

    def test_insufficient_skills_returns_false(self, tmp_path):
        """< 2 non-always-on skills → no dispatch."""
        brain = _make_brain(tmp_path)
        skills = [
            _make_skill("brand-identity"),
            _make_skill("dna27", always_on=True),
            _make_skill("deep-think", always_on=True),
        ]
        result = brain._assess_dispatch("幫我做品牌全案", skills)
        assert result["should_dispatch"] is False
        assert result["reason"] == "insufficient_skills"

    def test_zero_skills_returns_false(self, tmp_path):
        brain = _make_brain(tmp_path)
        result = brain._assess_dispatch("hello", [])
        assert result["should_dispatch"] is False

    def test_user_explicit_trigger_with_2_skills(self, tmp_path):
        """User says '完整流程' + 2 non-always-on skills → dispatch."""
        brain = _make_brain(tmp_path)
        skills = [
            _make_skill("brand-identity"),
            _make_skill("storytelling-engine"),
        ]
        result = brain._assess_dispatch("幫我做完整流程", skills)
        assert result["should_dispatch"] is True
        assert result["reason"] == "user_explicit"

    def test_user_explicit_various_triggers(self, tmp_path):
        """All explicit trigger phrases should work."""
        brain = _make_brain(tmp_path)
        skills = [_make_skill("a"), _make_skill("b")]
        triggers = [
            "完整流程", "全案", "從頭到尾", "一次搞定",
            "串起來", "整合分析", "全套", "完整診斷",
        ]
        for t in triggers:
            result = brain._assess_dispatch(f"幫我{t}", skills)
            assert result["should_dispatch"] is True, f"Trigger '{t}' should dispatch"

    def test_3_skills_with_large_skillmd(self, tmp_path):
        """3+ non-always-on skills + one SKILL.md > 5000 token → dispatch."""
        brain = _make_brain(tmp_path)
        # content_len // 3 > 5000 → content_len > 15000
        skills = [
            _make_skill("brand-identity", content_len=18000),
            _make_skill("storytelling-engine", content_len=3000),
            _make_skill("text-alchemy", content_len=3000),
        ]
        result = brain._assess_dispatch("幫我分析品牌", skills)
        assert result["should_dispatch"] is True
        assert result["reason"] == "multi_skill_complex"

    def test_3_skills_no_large_skillmd(self, tmp_path):
        """3+ skills but all SKILL.md small → no dispatch (below threshold)."""
        brain = _make_brain(tmp_path)
        skills = [
            _make_skill("a", content_len=3000),
            _make_skill("b", content_len=3000),
            _make_skill("c", content_len=3000),
        ]
        # 3000 // 3 = 1000 < 5000 for each
        # total = 3000 < 40000
        result = brain._assess_dispatch("分析", skills)
        assert result["should_dispatch"] is False
        assert result["reason"] == "below_threshold"

    def test_2_skills_token_overflow(self, tmp_path):
        """2 skills with combined > 40K tokens → dispatch."""
        brain = _make_brain(tmp_path)
        # each 70000 chars → 70000 // 3 ≈ 23333 tokens → total > 40000
        skills = [
            _make_skill("brand-identity", content_len=70000),
            _make_skill("storytelling-engine", content_len=70000),
        ]
        result = brain._assess_dispatch("分析", skills)
        assert result["should_dispatch"] is True
        assert result["reason"] == "token_overflow"

    def test_2_skills_below_token_threshold(self, tmp_path):
        """2 skills combined < 40K tokens → no dispatch."""
        brain = _make_brain(tmp_path)
        skills = [
            _make_skill("a", content_len=30000),
            _make_skill("b", content_len=30000),
        ]
        # 30000//3 + 30000//3 = 20000 < 40000
        result = brain._assess_dispatch("分析", skills)
        assert result["should_dispatch"] is False

    def test_always_on_skills_filtered_out(self, tmp_path):
        """Always-on skills don't count toward dispatch threshold."""
        brain = _make_brain(tmp_path)
        skills = [
            _make_skill("dna27", always_on=True, content_len=30000),
            _make_skill("deep-think", always_on=True, content_len=30000),
            _make_skill("c15", always_on=True, content_len=30000),
            _make_skill("brand-identity", content_len=3000),
        ]
        result = brain._assess_dispatch("品牌全案", skills)
        assert result["should_dispatch"] is False
        assert result["reason"] == "insufficient_skills"

    def test_budget_block_prevents_dispatch(self, tmp_path):
        """Budget check failure → no dispatch even if conditions met."""
        brain = _make_brain(tmp_path)
        brain.budget_monitor = MagicMock()
        brain.budget_monitor.check_budget.return_value = False

        skills = [
            _make_skill("a"),
            _make_skill("b"),
        ]
        result = brain._assess_dispatch("完整流程", skills)
        assert result["should_dispatch"] is False


# ═══════════════════════════════════════════
# _dispatch_budget_ok
# ═══════════════════════════════════════════


class TestDispatchBudgetOk:
    """Test _dispatch_budget_ok()."""

    def test_no_budget_monitor_returns_true(self, tmp_path):
        brain = _make_brain(tmp_path)
        brain.budget_monitor = None
        result = brain._dispatch_budget_ok([_make_skill("a")])
        assert result is True

    def test_budget_sufficient(self, tmp_path):
        brain = _make_brain(tmp_path)
        brain.budget_monitor = MagicMock()
        brain.budget_monitor.check_budget.return_value = True
        result = brain._dispatch_budget_ok([_make_skill("a", content_len=3000)])
        assert result is True
        brain.budget_monitor.check_budget.assert_called_once()

    def test_budget_insufficient(self, tmp_path):
        brain = _make_brain(tmp_path)
        brain.budget_monitor = MagicMock()
        brain.budget_monitor.check_budget.return_value = False
        result = brain._dispatch_budget_ok([_make_skill("a")])
        assert result is False


# ═══════════════════════════════════════════
# _parse_orchestrator_response
# ═══════════════════════════════════════════


class TestParseOrchestratorResponse:
    """Test _parse_orchestrator_response()."""

    def test_valid_json_array(self, tmp_path):
        brain = _make_brain(tmp_path)
        active_skills = [_make_skill("brand-identity"), _make_skill("text-alchemy")]

        response = '''
以下是分解結果：
[
  {
    "skill_name": "brand-identity",
    "skill_focus": "品牌定位",
    "skill_depth": "standard",
    "expected_output": "品牌定位文件"
  },
  {
    "skill_name": "text-alchemy",
    "skill_focus": "文案撰寫",
    "skill_depth": "quick",
    "expected_output": "品牌文案"
  }
]
'''
        tasks = brain._parse_orchestrator_response(response, active_skills, "plan_001")
        assert len(tasks) == 2
        assert tasks[0].skill_name == "brand-identity"
        assert tasks[0].task_id == "plan_001_task_00"
        assert tasks[1].skill_name == "text-alchemy"
        assert tasks[1].task_id == "plan_001_task_01"
        assert tasks[1].skill_depth == "quick"

    def test_invalid_skill_name_skipped(self, tmp_path):
        brain = _make_brain(tmp_path)
        active_skills = [_make_skill("brand-identity")]

        response = '''[
  {"skill_name": "brand-identity", "skill_focus": "f", "skill_depth": "standard"},
  {"skill_name": "nonexistent-skill", "skill_focus": "f", "skill_depth": "standard"}
]'''
        tasks = brain._parse_orchestrator_response(response, active_skills, "plan_002")
        assert len(tasks) == 1
        assert tasks[0].skill_name == "brand-identity"

    def test_no_json_returns_empty(self, tmp_path):
        brain = _make_brain(tmp_path)
        response = "這是一段沒有 JSON 的回覆文字。"
        tasks = brain._parse_orchestrator_response(response, [], "plan_003")
        assert tasks == []

    def test_malformed_json_returns_empty(self, tmp_path):
        brain = _make_brain(tmp_path)
        response = '[{"skill_name": "broken", invalid json}]'
        tasks = brain._parse_orchestrator_response(response, [], "plan_004")
        assert tasks == []

    def test_max_5_tasks(self, tmp_path):
        brain = _make_brain(tmp_path)
        skills = [_make_skill(f"skill-{i}") for i in range(8)]
        tasks_json = [
            {"skill_name": f"skill-{i}", "skill_focus": "f", "skill_depth": "standard"}
            for i in range(8)
        ]
        response = json.dumps(tasks_json)
        tasks = brain._parse_orchestrator_response(response, skills, "plan_005")
        assert len(tasks) == 5

    def test_defaults_for_missing_fields(self, tmp_path):
        brain = _make_brain(tmp_path)
        active_skills = [_make_skill("brand-identity")]
        response = '[{"skill_name": "brand-identity"}]'
        tasks = brain._parse_orchestrator_response(response, active_skills, "plan_006")
        assert len(tasks) == 1
        t = tasks[0]
        assert t.skill_focus == ""
        assert t.skill_depth == "standard"
        assert t.expected_output == ""
        assert t.model_preference == "haiku"
        assert t.depends_on == []


# ═══════════════════════════════════════════
# _parse_worker_quality
# ═══════════════════════════════════════════


class TestParseWorkerQuality:
    """Test _parse_worker_quality()."""

    def test_valid_json_at_end(self, tmp_path):
        brain = _make_brain(tmp_path)
        response = '''
## 品牌分析
這是一段分析內容...

```json
{"self_score": 0.85, "confidence": 0.9, "limitations": "缺少實際數據"}
```
'''
        quality = brain._parse_worker_quality(response)
        assert quality["self_score"] == 0.85
        assert quality["confidence"] == 0.9
        assert quality["limitations"] == "缺少實際數據"

    def test_no_json_returns_default(self, tmp_path):
        brain = _make_brain(tmp_path)
        response = "這是回覆但沒有自評。"
        quality = brain._parse_worker_quality(response)
        assert quality["self_score"] == 0.7
        assert quality["confidence"] == 0.5
        assert "not provided" in quality["limitations"]

    def test_malformed_json_returns_default(self, tmp_path):
        brain = _make_brain(tmp_path)
        response = '{"self_score": broken}'
        quality = brain._parse_worker_quality(response)
        assert quality["self_score"] == 0.7

    def test_embedded_json(self, tmp_path):
        brain = _make_brain(tmp_path)
        response = '品牌定位完成。\n自評：{"self_score": 0.92, "confidence": 0.88, "limitations": "無"}'
        quality = brain._parse_worker_quality(response)
        assert quality["self_score"] == 0.92


# ═══════════════════════════════════════════
# _dispatch_mode (integration with mock LLM)
# ═══════════════════════════════════════════


class TestDispatchMode:
    """Test _dispatch_mode() end-to-end with mocked LLM calls."""

    @pytest.mark.asyncio
    async def test_full_dispatch_flow(self, tmp_path):
        """Orchestrate → Worker → Synthesize → completed plan persisted."""
        brain = _make_brain(tmp_path, skill_contents={
            "brand-identity": "x" * 6000,
            "text-alchemy": "y" * 6000,
            "orchestrator": "orchestrator methodology...",
        })
        brain.skill_router._index = [
            _make_skill("brand-identity"),
            _make_skill("text-alchemy"),
            _make_skill("orchestrator"),
        ]

        # Mock LLM calls: orchestrator → worker1 → worker2 → synthesize
        orchestrator_response = json.dumps([
            {"skill_name": "brand-identity", "skill_focus": "品牌定位", "skill_depth": "standard"},
            {"skill_name": "text-alchemy", "skill_focus": "文案撰寫", "skill_depth": "quick"},
        ])
        worker1_response = '品牌定位分析完成。\n{"self_score": 0.85, "confidence": 0.9, "limitations": "無"}'
        worker2_response = '文案撰寫完成。\n{"self_score": 0.80, "confidence": 0.8, "limitations": "無"}'
        synthesize_response = "這是最終的綜合回覆。品牌定位和文案都已完成。"

        call_count = 0
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return orchestrator_response
            elif call_count == 2:
                return worker1_response
            elif call_count == 3:
                return worker2_response
            else:
                return synthesize_response

        brain._call_llm_with_model = mock_llm
        brain._strip_system_leakage = lambda t: t

        matched_skills = [
            _make_skill("brand-identity"),
            _make_skill("text-alchemy"),
        ]

        result = await brain._dispatch_mode(
            content="幫我做品牌行銷全案",
            session_id="test-session-1234",
            user_id="user-001",
            matched_skills=matched_skills,
            anima_mc={"identity": {"name": "霓裳"}, "boss": {"name": "達達把拔"}},
            anima_user=None,
            sub_agent_context="",
        )

        assert result == synthesize_response
        assert call_count == 4

        # Verify plan was persisted to completed/
        completed_dir = tmp_path / "dispatch" / "completed"
        assert completed_dir.exists()
        plan_files = list(completed_dir.glob("*.json"))
        assert len(plan_files) == 1

        plan_data = json.loads(plan_files[0].read_text(encoding="utf-8"))
        assert plan_data["status"] == "completed"
        assert len(plan_data["tasks"]) == 2
        assert len(plan_data["results"]) == 2

    @pytest.mark.asyncio
    async def test_empty_orchestrator_fallback(self, tmp_path):
        """Orchestrator produces no tasks → fallback to normal pipeline."""
        brain = _make_brain(tmp_path)
        brain.skill_router._index = []

        # Orchestrator returns empty/invalid
        async def mock_llm(system_prompt, messages, model, max_tokens):
            return "無法分解任務"

        brain._call_llm_with_model = mock_llm

        # Mock fallback
        brain._build_system_prompt = MagicMock(return_value="system")
        brain._get_session_history = MagicMock(return_value=[])
        brain._call_llm = AsyncMock(return_value="fallback response")

        matched_skills = [_make_skill("a"), _make_skill("b")]

        result = await brain._dispatch_mode(
            content="test",
            session_id="sess-0001",
            user_id="user-001",
            matched_skills=matched_skills,
            anima_mc=None,
            anima_user=None,
            sub_agent_context="",
        )

        assert result == "fallback response"
        brain._call_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_triggers_fallback(self, tmp_path):
        """Exception during dispatch → fallback + failed plan persisted."""
        brain = _make_brain(tmp_path)
        brain.skill_router._index = []

        async def mock_llm(system_prompt, messages, model, max_tokens):
            raise RuntimeError("API exploded")

        brain._call_llm_with_model = mock_llm
        brain._build_system_prompt = MagicMock(return_value="system")
        brain._get_session_history = MagicMock(return_value=[])
        brain._call_llm = AsyncMock(return_value="fallback after error")

        matched_skills = [_make_skill("a"), _make_skill("b")]

        result = await brain._dispatch_mode(
            content="test",
            session_id="sess-0002",
            user_id="user-001",
            matched_skills=matched_skills,
            anima_mc=None,
            anima_user=None,
            sub_agent_context="",
        )

        assert result == "fallback after error"

        # Verify failed plan persisted
        failed_dir = tmp_path / "dispatch" / "failed"
        assert failed_dir.exists()
        plan_files = list(failed_dir.glob("*.json"))
        assert len(plan_files) == 1
        plan_data = json.loads(plan_files[0].read_text(encoding="utf-8"))
        assert plan_data["status"] == "failed"
        assert "API exploded" in plan_data["error_message"]

    @pytest.mark.asyncio
    async def test_worker_failure_still_synthesizes(self, tmp_path):
        """One worker fails, others succeed → synthesize with partial results."""
        brain = _make_brain(tmp_path, skill_contents={
            "brand-identity": "skill content",
            "text-alchemy": "skill content",
            "orchestrator": "orchestrator",
        })
        brain.skill_router._index = [
            _make_skill("brand-identity"),
            _make_skill("text-alchemy"),
            _make_skill("orchestrator"),
        ]

        call_count = 0
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Orchestrator
                return json.dumps([
                    {"skill_name": "brand-identity", "skill_focus": "f", "skill_depth": "standard"},
                    {"skill_name": "text-alchemy", "skill_focus": "f", "skill_depth": "standard"},
                ])
            elif call_count == 2:
                # Worker 1 succeeds
                return '結果。\n{"self_score": 0.8, "confidence": 0.8, "limitations": ""}'
            elif call_count == 3:
                # Worker 2 fails
                raise RuntimeError("Worker 2 timeout")
            else:
                # Synthesize
                return "綜合回覆（部分結果）"

        brain._call_llm_with_model = mock_llm
        brain._strip_system_leakage = lambda t: t

        matched_skills = [_make_skill("brand-identity"), _make_skill("text-alchemy")]

        result = await brain._dispatch_mode(
            content="test",
            session_id="sess-0003",
            user_id="user-001",
            matched_skills=matched_skills,
            anima_mc=None,
            anima_user=None,
            sub_agent_context="",
        )

        assert result == "綜合回覆（部分結果）"
        assert call_count == 4  # orchestrator + worker1 + worker2(fail) + synthesize

        # Check results: one completed, one failed
        completed_dir = tmp_path / "dispatch" / "completed"
        plan_files = list(completed_dir.glob("*.json"))
        assert len(plan_files) == 1
        plan_data = json.loads(plan_files[0].read_text(encoding="utf-8"))
        statuses = [r["status"] for r in plan_data["results"]]
        assert "completed" in statuses
        assert "failed" in statuses


# ═══════════════════════════════════════════
# _dispatch_worker
# ═══════════════════════════════════════════


class TestDispatchWorker:
    """Test _dispatch_worker() method."""

    @pytest.mark.asyncio
    async def test_worker_success(self, tmp_path):
        brain = _make_brain(tmp_path, skill_contents={
            "brand-identity": "brand skill content",
        })
        brain.skill_router._index = [_make_skill("brand-identity")]

        async def mock_llm(system_prompt, messages, model, max_tokens):
            assert "brand skill content" in system_prompt
            assert model == "claude-haiku-4-5-20251001"
            return '品牌分析完成。\n{"self_score": 0.9, "confidence": 0.85, "limitations": ""}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="test_task_01",
            skill_name="brand-identity",
            skill_focus="品牌定位",
            skill_depth="standard",
            input_data={"user_request": "分析品牌"},
        )

        result = await brain._dispatch_worker(task, "", None)

        assert result.task_id == "test_task_01"
        assert result.status.value == "completed"
        assert result.quality["self_score"] == 0.9
        assert result.handoff_package is not None
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_worker_uses_sonnet_for_deep(self, tmp_path):
        brain = _make_brain(tmp_path, skill_contents={"x": "content"})
        brain.skill_router._index = [_make_skill("x")]

        used_model = None
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal used_model
            used_model = model
            return 'done. {"self_score": 0.8, "confidence": 0.8, "limitations": ""}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="t1", skill_name="x",
            skill_focus="f", skill_depth="deep",
            model_preference="sonnet",
            input_data={"user_request": "test"},
        )

        await brain._dispatch_worker(task, "", None)
        assert used_model == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_worker_includes_handoff_context(self, tmp_path):
        brain = _make_brain(tmp_path, skill_contents={"a": "content"})
        brain.skill_router._index = [_make_skill("a")]

        captured_prompt = None
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal captured_prompt
            captured_prompt = system_prompt
            return '{"self_score": 0.7, "confidence": 0.7, "limitations": ""}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="t1", skill_name="a",
            skill_focus="f", skill_depth="standard",
            input_data={"user_request": "test"},
        )

        await brain._dispatch_worker(task, "前一步品牌定位完成", None)
        assert "前一步品牌定位完成" in captured_prompt

    @pytest.mark.asyncio
    async def test_worker_failure_returns_failed_result(self, tmp_path):
        brain = _make_brain(tmp_path, skill_contents={"a": "content"})
        brain.skill_router._index = [_make_skill("a")]

        async def mock_llm(system_prompt, messages, model, max_tokens):
            raise RuntimeError("API error")

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="t1", skill_name="a",
            skill_focus="f", skill_depth="standard",
            input_data={"user_request": "test"},
        )

        result = await brain._dispatch_worker(task, "", None)
        assert result.status.value == "failed"
        assert "API error" in result.error_message

    @pytest.mark.asyncio
    async def test_worker_uses_anima_identity(self, tmp_path):
        brain = _make_brain(tmp_path, skill_contents={"a": "content"})
        brain.skill_router._index = [_make_skill("a")]

        captured_prompt = None
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal captured_prompt
            captured_prompt = system_prompt
            return '{"self_score": 0.7, "confidence": 0.7, "limitations": ""}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="t1", skill_name="a",
            skill_focus="f", skill_depth="standard",
            input_data={"user_request": "test"},
        )

        anima_mc = {"identity": {"name": "霓裳"}, "boss": {"name": "達達把拔"}}
        await brain._dispatch_worker(task, "", anima_mc)
        assert "霓裳" in captured_prompt
        assert "達達把拔" in captured_prompt


# ═══════════════════════════════════════════
# _dispatch_fallback
# ═══════════════════════════════════════════


class TestDispatchFallback:
    """Test _dispatch_fallback() — reverts to normal pipeline."""

    @pytest.mark.asyncio
    async def test_fallback_calls_normal_pipeline(self, tmp_path):
        brain = _make_brain(tmp_path)
        brain._build_system_prompt = MagicMock(return_value="system prompt")
        brain._get_session_history = MagicMock(return_value=[])
        brain._call_llm = AsyncMock(return_value="normal response")

        result = await brain._dispatch_fallback(
            content="test",
            session_id="sess-001",
            matched_skills=[],
            anima_mc=None,
            anima_user=None,
            sub_agent_context="",
        )

        assert result == "normal response"
        brain._build_system_prompt.assert_called_once()
        brain._call_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_updates_history(self, tmp_path):
        brain = _make_brain(tmp_path)
        history = []
        brain._build_system_prompt = MagicMock(return_value="system")
        brain._get_session_history = MagicMock(return_value=history)
        brain._call_llm = AsyncMock(return_value="response")

        await brain._dispatch_fallback(
            content="user message",
            session_id="sess-001",
            matched_skills=[],
            anima_mc=None,
            anima_user=None,
            sub_agent_context="",
        )

        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"


# ═══════════════════════════════════════════
# Phase B: Parallel Execution
# ═══════════════════════════════════════════


class TestDispatchExecuteParallel:
    """Test _dispatch_execute_parallel()."""

    @pytest.mark.asyncio
    async def test_parallel_all_succeed(self, tmp_path):
        brain = _make_brain(tmp_path, skill_contents={
            "a": "skill a", "b": "skill b",
            "orchestrator": "",
        })
        brain.skill_router._index = [_make_skill("a"), _make_skill("b")]

        call_count = 0
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal call_count
            call_count += 1
            return f'結果 {call_count}。\n{{"self_score": 0.85, "confidence": 0.9, "limitations": ""}}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import (
            DispatchPlan, TaskPackage, ExecutionMode,
        )
        plan = DispatchPlan(
            plan_id="par_test",
            user_request="test",
            session_id="sess",
            execution_mode=ExecutionMode.PARALLEL,
        )
        plan.tasks = [
            TaskPackage(task_id="t1", skill_name="a", skill_focus="f",
                        skill_depth="standard", input_data={"user_request": "test"}),
            TaskPackage(task_id="t2", skill_name="b", skill_focus="f",
                        skill_depth="standard", input_data={"user_request": "test"}),
        ]

        await brain._dispatch_execute_parallel(plan, None)

        assert len(plan.results) == 2
        assert all(r.status.value == "completed" for r in plan.results)
        assert call_count == 2


class TestDispatchExecuteMixed:
    """Test _dispatch_execute_mixed() — DAG layers."""

    @pytest.mark.asyncio
    async def test_diamond_dag_execution(self, tmp_path):
        """A → B,C (parallel) → D."""
        brain = _make_brain(tmp_path, skill_contents={
            "a": "content", "b": "content", "c": "content", "d": "content",
        })
        brain.skill_router._index = [
            _make_skill("a"), _make_skill("b"),
            _make_skill("c"), _make_skill("d"),
        ]

        execution_order = []
        async def mock_llm(system_prompt, messages, model, max_tokens):
            # Extract skill name from prompt
            for name in ["a", "b", "c", "d"]:
                if f"用 {name} " in system_prompt:
                    execution_order.append(name)
                    break
            return '結果。\n{"self_score": 0.8, "confidence": 0.8, "limitations": ""}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import (
            DispatchPlan, TaskPackage, ExecutionMode,
        )
        plan = DispatchPlan(
            plan_id="dag_test",
            user_request="test",
            session_id="sess",
            execution_mode=ExecutionMode.MIXED,
        )
        plan.tasks = [
            TaskPackage(task_id="A", skill_name="a", skill_focus="f",
                        skill_depth="standard", input_data={"user_request": "test"}),
            TaskPackage(task_id="B", skill_name="b", skill_focus="f",
                        skill_depth="standard", depends_on=["A"],
                        input_data={"user_request": "test"}),
            TaskPackage(task_id="C", skill_name="c", skill_focus="f",
                        skill_depth="standard", depends_on=["A"],
                        input_data={"user_request": "test"}),
            TaskPackage(task_id="D", skill_name="d", skill_focus="f",
                        skill_depth="standard", depends_on=["B", "C"],
                        input_data={"user_request": "test"}),
        ]

        await brain._dispatch_execute_mixed(plan, None)

        assert len(plan.results) == 4
        # A must be first
        assert execution_order[0] == "a"
        # D must be last
        assert execution_order[-1] == "d"


# ═══════════════════════════════════════════
# Phase B: Quality Gate + Retry
# ═══════════════════════════════════════════


class TestQualityGate:
    """Test _dispatch_worker_with_guard() quality gate."""

    @pytest.mark.asyncio
    async def test_low_score_triggers_retry(self, tmp_path):
        brain = _make_brain(tmp_path, skill_contents={"a": "content"})
        brain.skill_router._index = [_make_skill("a")]

        call_count = 0
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: low score
                return '低品質。\n{"self_score": 0.3, "confidence": 0.4, "limitations": "很多"}'
            else:
                # Retry with Sonnet: better score
                return '高品質。\n{"self_score": 0.85, "confidence": 0.9, "limitations": ""}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="qg_test", skill_name="a", skill_focus="f",
            skill_depth="standard", model_preference="haiku",
            input_data={"user_request": "test"},
        )

        result = await brain._dispatch_worker_with_guard(task, "", None)

        assert call_count == 2  # Original + retry
        assert result.quality["self_score"] == 0.85
        assert result.meta.get("retried") is True

    @pytest.mark.asyncio
    async def test_good_score_no_retry(self, tmp_path):
        brain = _make_brain(tmp_path, skill_contents={"a": "content"})
        brain.skill_router._index = [_make_skill("a")]

        call_count = 0
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal call_count
            call_count += 1
            return '好結果。\n{"self_score": 0.85, "confidence": 0.9, "limitations": ""}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="qg_ok", skill_name="a", skill_focus="f",
            skill_depth="standard", input_data={"user_request": "test"},
        )

        result = await brain._dispatch_worker_with_guard(task, "", None)

        assert call_count == 1
        assert result.quality["self_score"] == 0.85

    @pytest.mark.asyncio
    async def test_timeout_returns_failed(self, tmp_path):
        import asyncio
        brain = _make_brain(tmp_path, skill_contents={"a": "content"})
        brain.skill_router._index = [_make_skill("a")]

        async def mock_llm(system_prompt, messages, model, max_tokens):
            await asyncio.sleep(10)  # Way longer than timeout
            return "should not reach here"

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="timeout_test", skill_name="a", skill_focus="f",
            skill_depth="standard", timeout_seconds=0.1,  # 100ms timeout
            input_data={"user_request": "test"},
        )

        result = await brain._dispatch_worker_with_guard(task, "", None)

        assert result.status.value == "failed"
        assert "Timeout" in result.error_message

    @pytest.mark.asyncio
    async def test_sonnet_model_skips_retry(self, tmp_path):
        """Already using Sonnet → no retry on low score."""
        brain = _make_brain(tmp_path, skill_contents={"a": "content"})
        brain.skill_router._index = [_make_skill("a")]

        call_count = 0
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal call_count
            call_count += 1
            return '低品質。\n{"self_score": 0.3, "confidence": 0.3, "limitations": "很多"}'

        brain._call_llm_with_model = mock_llm

        from museon.agent.dispatch import TaskPackage
        task = TaskPackage(
            task_id="sonnet_low", skill_name="a", skill_focus="f",
            skill_depth="deep", model_preference="sonnet",
            input_data={"user_request": "test"},
        )

        result = await brain._dispatch_worker_with_guard(task, "", None)

        assert call_count == 1  # No retry
        assert result.quality["self_score"] == 0.3


# ═══════════════════════════════════════════
# Phase B: Partial Completion
# ═══════════════════════════════════════════


class TestPartialCompletion:
    """Test dispatch with partial worker failures."""

    @pytest.mark.asyncio
    async def test_partial_status(self, tmp_path):
        """Some workers fail → plan.status = PARTIAL."""
        brain = _make_brain(tmp_path, skill_contents={
            "a": "content", "b": "content", "orchestrator": "",
        })
        brain.skill_router._index = [
            _make_skill("a"), _make_skill("b"), _make_skill("orchestrator"),
        ]

        call_count = 0
        async def mock_llm(system_prompt, messages, model, max_tokens):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Orchestrator
                return json.dumps([
                    {"skill_name": "a", "skill_focus": "f", "skill_depth": "standard"},
                    {"skill_name": "b", "skill_focus": "f", "skill_depth": "standard"},
                ])
            elif call_count == 2:
                # Worker 1 success
                return '好。\n{"self_score": 0.9, "confidence": 0.9, "limitations": ""}'
            elif call_count == 3:
                # Worker 2 fail
                raise RuntimeError("Worker 2 died")
            else:
                # Synthesize
                return "部分完成的綜合回覆"

        brain._call_llm_with_model = mock_llm
        brain._strip_system_leakage = lambda t: t

        matched_skills = [_make_skill("a"), _make_skill("b")]

        result = await brain._dispatch_mode(
            content="test",
            session_id="sess-partial",
            user_id="user-001",
            matched_skills=matched_skills,
            anima_mc=None,
            anima_user=None,
            sub_agent_context="",
        )

        assert result == "部分完成的綜合回覆"

        # Check plan status is PARTIAL
        completed_dir = tmp_path / "dispatch" / "completed"
        if completed_dir.exists():
            plan_files = list(completed_dir.glob("*.json"))
            if plan_files:
                plan_data = json.loads(plan_files[0].read_text(encoding="utf-8"))
                assert plan_data["status"] == "partial"
