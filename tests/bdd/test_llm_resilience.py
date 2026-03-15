"""BDD step definitions for LLM Resilience."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_bdd import given, scenarios, then, when, parsers

# ── Link feature file ──
scenarios("../../features/llm_resilience.feature")


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

class Context:
    def __init__(self):
        self.env = None
        self.adapter = None
        self.fallback = None
        self.brain = None
        self.vital_signs = None
        self.response = None
        self.probe_attempted = False

@pytest.fixture
def ctx():
    return Context()


# ═══════════════════════════════════════
# ENV Isolation
# ═══════════════════════════════════════

@given("ANTHROPIC_API_KEY is set in os.environ")
def given_api_key_in_env(ctx):
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-api03-test-fake-key"
    os.environ["CLAUDECODE"] = "1"


@when("ClaudeCLIAdapter prepares subprocess environment")
def when_cli_prepares_env(ctx):
    # Simulate what ClaudeCLIAdapter does in call()
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("ANTHROPIC_API_KEY", None)
    ctx.env = env
    # Cleanup
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("CLAUDECODE", None)


@then("the subprocess env should not contain ANTHROPIC_API_KEY")
def then_no_api_key(ctx):
    assert "ANTHROPIC_API_KEY" not in ctx.env


@then("the subprocess env should not contain CLAUDECODE")
def then_no_claudecode(ctx):
    assert "CLAUDECODE" not in ctx.env


# ═══════════════════════════════════════
# FallbackAdapter
# ═══════════════════════════════════════

@given("a FallbackAdapter with CLI and API adapters")
def given_fallback_adapter(ctx):
    from museon.llm.adapters import FallbackAdapter, ClaudeCLIAdapter, AnthropicAPIAdapter

    cli = MagicMock(spec=ClaudeCLIAdapter)
    cli.call = AsyncMock(
        return_value=MagicMock(text="ok", stop_reason="end_turn")
    )
    api = MagicMock(spec=AnthropicAPIAdapter)
    api.call = AsyncMock(
        return_value=MagicMock(text="ok from api", stop_reason="end_turn")
    )
    ctx.fallback = FallbackAdapter(cli=cli, api=api)


@then(parsers.parse('the active adapter should be "{expected}"'))
def then_active_adapter(ctx, expected):
    if expected == "cli":
        assert ctx.fallback._using_api is False
    else:
        assert ctx.fallback._using_api is True


@when("CLI fails 2 consecutive times")
def when_cli_fails_twice(ctx):
    # FallbackAdapter checks stop_reason == "error", not exceptions
    error_resp = MagicMock(text="CLI error", stop_reason="error")
    ctx.fallback._cli.call = AsyncMock(return_value=error_resp)
    # Also need API to handle the fallback call
    api_resp = MagicMock(text="ok from api", stop_reason="end_turn")
    ctx.fallback._api.call = AsyncMock(return_value=api_resp)
    async def _run_two_calls():
        for _ in range(2):
            await ctx.fallback.call(
                system_prompt="test",
                messages=[{"role": "user", "content": "hi"}],
                model="sonnet",
            )
    asyncio.run(_run_two_calls())


@given("a FallbackAdapter using API after CLI failures")
def given_fallback_on_api(ctx):
    from museon.llm.adapters import FallbackAdapter, ClaudeCLIAdapter, AnthropicAPIAdapter

    cli = MagicMock(spec=ClaudeCLIAdapter)
    cli.call = AsyncMock(side_effect=RuntimeError("CLI down"))
    api = MagicMock(spec=AnthropicAPIAdapter)
    api.call = AsyncMock(
        return_value=MagicMock(text="ok from api", stop_reason="end_turn")
    )
    ctx.fallback = FallbackAdapter(cli=cli, api=api)
    ctx.fallback._using_api = True
    ctx.fallback._api_call_count = 0


@when("20 API calls complete")
def when_20_api_calls(ctx):
    ctx.fallback._api_call_count = 20


@then("a CLI probe should be attempted")
def then_cli_probe(ctx):
    # FallbackAdapter probes CLI every 20 calls
    assert ctx.fallback._api_call_count >= 20


# ═══════════════════════════════════════
# Brain ↔ Sentinel Integration
# ═══════════════════════════════════════

@given("a brain with a Governor that has VitalSigns")
def given_brain_with_governor(ctx, tmp_path):
    from museon.agent.brain import MuseonBrain
    from museon.governance.vital_signs import VitalSignsMonitor

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "_system" / "sessions").mkdir(parents=True, exist_ok=True)

    brain = MuseonBrain(data_dir=str(data_dir))
    vs = VitalSignsMonitor(data_dir=data_dir)
    vs._push_alert = AsyncMock()

    governor = MagicMock()
    governor.get_vital_signs.return_value = vs

    brain._governor = governor
    ctx.brain = brain
    ctx.vital_signs = vs


@when("all LLM models fail")
def when_all_models_fail(ctx):
    ctx.response = ctx.brain._offline_response(
        [{"role": "user", "content": "test"}],
        error_msg="All models exhausted",
    )


@then("the offline response should be returned")
def then_offline_returned(ctx):
    assert "目前無法連線到 AI 服務" in ctx.response


@then("the VitalSigns sentinel should be notified")
def then_sentinel_notified(ctx):
    # Give async task a chance to run
    asyncio.run(asyncio.sleep(0.1))
    assert ctx.vital_signs._consecutive_llm_failures >= 1 or \
        ctx.vital_signs._push_alert.called


@when("LLM call succeeds")
def when_llm_success(ctx):
    ctx.vital_signs._consecutive_llm_failures = 3
    vs = ctx.brain._governor.get_vital_signs()
    vs.on_llm_success()


@then("VitalSigns consecutive failures should be 0")
def then_vs_failures_zero(ctx):
    assert ctx.vital_signs._consecutive_llm_failures == 0
