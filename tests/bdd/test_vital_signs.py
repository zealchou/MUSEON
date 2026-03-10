"""BDD step definitions for Vital Signs Monitor."""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_bdd import given, scenarios, then, when, parsers

from museon.governance.vital_signs import (
    CheckStatus,
    VitalReport,
    VitalSignsMonitor,
)

# ── Link feature file ──
scenarios("../../features/vital_signs.feature")


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

@pytest.fixture
def test_data_dir(tmp_path):
    """Provide a temporary data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = data_dir / "_system" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def monitor(test_data_dir):
    """Create a VitalSignsMonitor with test data dir."""
    return VitalSignsMonitor(data_dir=test_data_dir)


# ═══════════════════════════════════════
# Shared State
# ═══════════════════════════════════════

class Context:
    """Test context for sharing state between steps."""
    def __init__(self):
        self.monitor = None
        self.report = None
        self.guidance = None

@pytest.fixture
def ctx():
    return Context()


# ═══════════════════════════════════════
# Background
# ═══════════════════════════════════════

@given("VitalSignsMonitor is initialized with test data directory")
def given_vsm_initialized(monitor, ctx):
    ctx.monitor = monitor


# ═══════════════════════════════════════
# Layer 1: Preflight
# ═══════════════════════════════════════

@given("no LLM adapter is registered")
def given_no_llm(ctx):
    ctx.monitor._llm_adapter = None


@given("a healthy LLM adapter is registered")
def given_healthy_llm(ctx):
    adapter = MagicMock()
    adapter.call = AsyncMock(
        return_value=MagicMock(
            text="OK", stop_reason="end_turn"
        )
    )
    ctx.monitor.register_llm_adapter(adapter)


@given("a failing LLM adapter is registered")
def given_failing_llm(ctx):
    adapter = MagicMock()
    adapter.call = AsyncMock(side_effect=RuntimeError("LLM connection failed"))
    ctx.monitor.register_llm_adapter(adapter)


@when("preflight runs")
def when_preflight_runs(ctx):
    ctx.report = asyncio.get_event_loop().run_until_complete(
        ctx.monitor.run_preflight()
    )


@then(parsers.parse('the "{check_name}" check should be "{expected_status}"'))
def then_check_status(ctx, check_name, expected_status):
    matching = [c for c in ctx.report.checks if c.name == check_name]
    assert len(matching) > 0, f"Check '{check_name}' not found in report"
    assert matching[0].status.value == expected_status


@then(parsers.parse('the overall report should not be "{status}"'))
def then_overall_not(ctx, status):
    assert ctx.report.overall.value != status


@then(parsers.parse('the "{check_name}" check should exist'))
def then_check_exists(ctx, check_name):
    matching = [c for c in ctx.report.checks if c.name == check_name]
    assert len(matching) > 0, f"Check '{check_name}' not found"


@then("the check result should have a message")
def then_check_has_message(ctx):
    for check in ctx.report.checks:
        assert check.message, f"Check '{check.name}' has no message"


# ═══════════════════════════════════════
# Layer 2: Pulse
# ═══════════════════════════════════════

@when("pulse runs")
def when_pulse_runs(ctx):
    ctx.report = asyncio.get_event_loop().run_until_complete(
        ctx.monitor.run_pulse()
    )


@then(parsers.parse("the pulse report should contain at least {n:d} checks"))
def then_pulse_min_checks(ctx, n):
    assert len(ctx.report.checks) >= n


@then(parsers.parse('the overall pulse report should not be "{status}"'))
def then_pulse_overall_not(ctx, status):
    assert ctx.report.overall.value != status


# ═══════════════════════════════════════
# Layer 3: Sentinel
# ═══════════════════════════════════════

@when(parsers.parse('offline is triggered with error "{error_msg}"'))
def when_offline_triggered(ctx, error_msg):
    with patch.object(ctx.monitor, "_push_alert", new_callable=AsyncMock):
        asyncio.get_event_loop().run_until_complete(
            ctx.monitor.on_offline_triggered(error_msg)
        )


@when(parsers.parse('offline is triggered with error "{error_msg}" within same minute'))
def when_offline_same_minute(ctx, error_msg):
    with patch.object(ctx.monitor, "_push_alert", new_callable=AsyncMock):
        asyncio.get_event_loop().run_until_complete(
            ctx.monitor.on_offline_triggered(error_msg)
        )


@then(parsers.parse("the sentinel count should be {n:d}"))
def then_sentinel_count(ctx, n):
    assert ctx.monitor._sentinel_count == n


@then(parsers.parse("consecutive LLM failures should be {n:d}"))
def then_consecutive_failures(ctx, n):
    assert ctx.monitor._consecutive_llm_failures == n


@given(parsers.parse("consecutive LLM failures is {n:d}"))
def given_consecutive_failures(ctx, n):
    ctx.monitor._consecutive_llm_failures = n


@when("LLM success is reported")
def when_llm_success(ctx):
    ctx.monitor.on_llm_success()


# ═══════════════════════════════════════
# Integration
# ═══════════════════════════════════════

@given("VitalSignsMonitor is started")
def given_vsm_started(ctx):
    ctx.monitor._running = True


@when("get_status is called")
def when_get_status(ctx):
    ctx.status = ctx.monitor.get_status()


@then(parsers.parse('the status should contain "{key}" as true'))
def then_status_key_true(ctx, key):
    assert ctx.status.get(key) is True


@then(parsers.parse('the status should contain "{key}"'))
def then_status_contains(ctx, key):
    assert key in ctx.status


@when(parsers.parse('diagnosing error "{error_msg}"'))
def when_diagnose(ctx, error_msg):
    ctx.guidance = ctx.monitor._diagnose_offline_cause(error_msg)


@then(parsers.parse('the guidance should mention "{keyword}"'))
def then_guidance_mentions(ctx, keyword):
    assert keyword in ctx.guidance
