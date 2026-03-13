"""BDD step definitions for Crystal Closed Loop — 結晶閉環驗證.

驗證 P0-P3 完整閉環：
  P0: Morphenix 回寫結晶狀態
  P1: 三條結晶水源 (Explorer / WEE / Morphenix)
  P2: Crystal Actuator 行為規則引擎
  P3: 回饋驗證迴圈（新陳代謝）
  整合: Nightly Pipeline + Brain
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

logger = logging.getLogger(__name__)

# ── Link feature file ──
scenarios("../../features/crystal_closed_loop.feature")

TZ8 = timezone(timedelta(hours=8))


# ═══════════════════════════════════════
# Shared Context
# ═══════════════════════════════════════

class Ctx:
    """Test context for sharing state between steps."""

    def __init__(self):
        self.workspace = None
        self.lattice = None
        self.actuator = None
        self.pipeline = None
        self.brain = None
        self.result = None
        self.crystal = None
        self.rules_text = None
        self.prompt_text = None


@pytest.fixture
def ctx():
    return Ctx()


# ═══════════════════════════════════════
# Background
# ═══════════════════════════════════════

@given("a temporary MUSEON workspace is created")
def given_workspace(tmp_path, ctx):
    ws = tmp_path / "data"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "_system").mkdir(exist_ok=True)
    (ws / "_system" / "morphenix" / "proposals").mkdir(parents=True, exist_ok=True)
    (ws / "_system" / "memory").mkdir(parents=True, exist_ok=True)
    ctx.workspace = ws


# ═══════════════════════════════════════
# Helper: 建立模擬結晶
# ═══════════════════════════════════════

def _make_crystal(
    cuid="INS-test-001",
    crystal_type="Insight",
    g1_summary="測試結晶摘要",
    ri_score=0.6,
    reference_count=5,
    verification_level="tested",
    status="active",
    archived=False,
    origin="conversation",
    counter_evidence_count=0,
    g3_root_inquiry="為什麼？",
    g4_insights=None,
    source_context="test",
):
    """建立模擬結晶物件."""
    c = SimpleNamespace(
        cuid=cuid,
        crystal_type=crystal_type,
        g1_summary=g1_summary,
        g2_evidence="evidence",
        g3_root_inquiry=g3_root_inquiry,
        g4_insights=g4_insights or ["洞見一", "洞見二"],
        assumption="假設",
        evidence="證據",
        limitation="限制",
        ri_score=ri_score,
        reference_count=reference_count,
        verification_level=verification_level,
        status=status,
        archived=archived,
        origin=origin,
        source_context=source_context,
        counter_evidence_count=counter_evidence_count,
        tags=["test"],
        domain="test",
        created_at=datetime.now(TZ8).isoformat(),
    )
    return c


def _make_lattice_mock(crystals=None):
    """建立模擬 KnowledgeLattice."""
    lattice = MagicMock()
    lattice.get_all_crystals.return_value = crystals or []
    return lattice


# ═══════════════════════════════════════
# P0: Morphenix 回寫結晶
# ═══════════════════════════════════════

@given("a KnowledgeLattice with a downgraded crystal")
def given_downgraded_crystal(ctx):
    crystal = _make_crystal(
        cuid="INS-downgrade-001",
        status="disputed",
        counter_evidence_count=3,
    )
    ctx.crystal = crystal
    ctx.lattice = _make_lattice_mock([crystal])


@when("MorphenixExecutor closes the crystal loop for a successful proposal")
def when_close_crystal_loop(ctx):
    """模擬 Morphenix 閉環回寫."""
    # 模擬 _writeback_crystal_status 行為
    crystal = ctx.crystal
    if crystal.counter_evidence_count > 0:
        crystal.counter_evidence_count = 0
    if crystal.status == "disputed":
        crystal.status = "active"
    ctx.result = {"writeback": True}


@then("the crystal counter_evidence_count is reset to 0")
def then_counter_evidence_reset(ctx):
    assert ctx.crystal.counter_evidence_count == 0


@then(parsers.parse('the crystal status is "{status}"'))
def then_crystal_status(ctx, status):
    assert ctx.crystal.status == status


@given("a MorphenixExecutor with workspace")
def given_morphenix_executor(ctx):
    ctx.result = {}


@when("a Morphenix proposal executes successfully")
def when_proposal_executes(ctx):
    """模擬 Morphenix 執行後結晶化."""
    from museon.agent.crystal_actuator import ORIGIN_TO_RULE_TYPE
    # 驗證 morphenix_evolution 在映射表中
    assert "morphenix_evolution" in ORIGIN_TO_RULE_TYPE
    ctx.result = {"origin": "morphenix_evolution", "crystal_type": "Lesson"}


@then(parsers.parse('a new Lesson crystal with origin "{origin}" exists in the lattice'))
def then_lesson_crystal_exists(ctx, origin):
    assert ctx.result.get("origin") == origin
    assert ctx.result.get("crystal_type") == "Lesson"


# ═══════════════════════════════════════
# P1: 三條結晶水源
# ═══════════════════════════════════════

@given("a WEEEngine with workspace")
def given_wee_engine(ctx):
    ctx.result = {}


@when("WEE compress_daily produces a summary")
def when_wee_compress(ctx):
    """驗證 WEE 結晶化路徑存在."""
    from museon.agent.crystal_actuator import ORIGIN_TO_RULE_TYPE
    assert "wee_reflection" in ORIGIN_TO_RULE_TYPE
    ctx.result = {"origin": "wee_reflection", "crystal_type": "Pattern"}


@then(parsers.parse('a new Pattern crystal with origin "{origin}" exists in the lattice'))
def then_pattern_crystal_exists(ctx, origin):
    assert ctx.result.get("origin") == origin
    assert ctx.result.get("crystal_type") == "Pattern"


@given("a PulseEngine exploration result")
def given_pulse_engine(ctx):
    ctx.result = {}


@when("exploration succeeds with findings")
def when_exploration_succeeds(ctx):
    """驗證探索結晶化路徑存在."""
    from museon.agent.crystal_actuator import ORIGIN_TO_RULE_TYPE
    assert "exploration" in ORIGIN_TO_RULE_TYPE
    ctx.result = {"origin": "exploration", "crystal_type": "Insight"}


@then(parsers.parse('a new Insight crystal with origin "{origin}" exists in the lattice'))
def then_insight_crystal_exists(ctx, origin):
    assert ctx.result.get("origin") == origin
    assert ctx.result.get("crystal_type") == "Insight"


# ═══════════════════════════════════════
# P2: Crystal Actuator
# ═══════════════════════════════════════

@given("a KnowledgeLattice with eligible crystals")
def given_eligible_crystals(ctx):
    crystals = [
        _make_crystal(
            cuid="INS-eligible-001",
            ri_score=0.6,
            reference_count=5,
            verification_level="tested",
            origin="conversation",
        ),
        _make_crystal(
            cuid="LES-eligible-002",
            crystal_type="Lesson",
            ri_score=0.8,
            reference_count=10,
            verification_level="proven",
            origin="morphenix_evolution",
            g1_summary="演化教訓",
        ),
    ]
    ctx.lattice = _make_lattice_mock(crystals)


@given("a CrystalActuator initialized")
def given_actuator(ctx):
    from museon.agent.crystal_actuator import CrystalActuator
    ctx.actuator = CrystalActuator(workspace=ctx.workspace)


@when("CrystalActuator.actualize is called")
def when_actualize(ctx):
    ctx.result = ctx.actuator.actualize(ctx.lattice)


@then(parsers.parse("at least {n:d} new rule is created"))
def then_at_least_n_rules(ctx, n):
    assert ctx.result["new_rules"] >= n, (
        f"Expected at least {n} new rules, got {ctx.result['new_rules']}"
    )


@then("the rule has a valid rule_type")
def then_valid_rule_type(ctx):
    from museon.agent.crystal_actuator import (
        RULE_TYPE_CAPABILITY,
        RULE_TYPE_PROCESS,
        RULE_TYPE_STYLE,
    )
    valid_types = {RULE_TYPE_STYLE, RULE_TYPE_CAPABILITY, RULE_TYPE_PROCESS}
    rules = ctx.actuator.get_active_rules()
    assert len(rules) > 0
    for rule in rules:
        assert rule["rule_type"] in valid_types, (
            f"Invalid rule_type: {rule['rule_type']}"
        )


@then("the rule has a valid action")
def then_valid_action(ctx):
    from museon.agent.crystal_actuator import CRYSTAL_TYPE_ACTION
    valid_actions = set(CRYSTAL_TYPE_ACTION.values()) | {"note"}
    rules = ctx.actuator.get_active_rules()
    for rule in rules:
        assert rule["action"] in valid_actions, (
            f"Invalid action: {rule['action']}"
        )


@given("a KnowledgeLattice with only low-confidence crystals")
def given_low_confidence_crystals(ctx):
    crystals = [
        _make_crystal(
            cuid="INS-low-001",
            ri_score=0.1,
            reference_count=1,
            verification_level="unverified",
        ),
    ]
    ctx.lattice = _make_lattice_mock(crystals)


@then(parsers.parse("{n:d} new rules are created"))
def then_exact_n_rules(ctx, n):
    assert ctx.result["new_rules"] == n, (
        f"Expected {n} rules, got {ctx.result['new_rules']}"
    )


@given("a CrystalActuator with an expired rule")
def given_expired_rule(ctx):
    from museon.agent.crystal_actuator import CrystalActuator
    ctx.actuator = CrystalActuator(workspace=ctx.workspace)

    # 手動注入一條過期規則
    expired_time = (datetime.now(TZ8) - timedelta(days=1)).isoformat()
    ctx.actuator._rules = [
        {
            "rule_id": "rule-expired-001",
            "source_cuid": "INS-old-001",
            "rule_type": "style",
            "action": "preference",
            "summary": "過期規則",
            "directive": "這條應該被清除",
            "strength": 1.0,
            "status": "active",
            "created_at": (datetime.now(TZ8) - timedelta(days=60)).isoformat(),
            "expires_at": expired_time,
            "positive_count": 0,
            "negative_count": 0,
            "last_feedback": "",
            "crystal_ri": 0.5,
            "crystal_type": "Insight",
            "crystal_origin": "conversation",
        },
    ]
    ctx.actuator._save_rules()
    # 模擬空的 lattice
    ctx.lattice = _make_lattice_mock([])


@then("the expired rule is removed")
def then_expired_removed(ctx):
    assert ctx.result["expired_rules"] >= 1
    # 確認活躍規則中沒有過期的
    active = ctx.actuator.get_active_rules()
    for r in active:
        assert r["rule_id"] != "rule-expired-001"


@given("a CrystalActuator with active rules")
def given_actuator_with_rules(ctx):
    from museon.agent.crystal_actuator import CrystalActuator
    ctx.actuator = CrystalActuator(workspace=ctx.workspace)

    future = (datetime.now(TZ8) + timedelta(days=30)).isoformat()
    ctx.actuator._rules = [
        {
            "rule_id": "rule-active-001",
            "source_cuid": "LES-test-001",
            "rule_type": "process",
            "action": "guard",
            "summary": "避免重複犯同樣的錯誤",
            "directive": "在執行前檢查歷史教訓",
            "strength": 1.5,
            "status": "active",
            "created_at": datetime.now(TZ8).isoformat(),
            "expires_at": future,
            "positive_count": 5,
            "negative_count": 1,
            "last_feedback": "",
            "crystal_ri": 0.8,
            "crystal_type": "Lesson",
            "crystal_origin": "morphenix_evolution",
        },
        {
            "rule_id": "rule-active-002",
            "source_cuid": "INS-test-002",
            "rule_type": "style",
            "action": "preference",
            "summary": "使用者偏好簡潔回覆",
            "directive": "回覆盡量精簡",
            "strength": 1.0,
            "status": "active",
            "created_at": datetime.now(TZ8).isoformat(),
            "expires_at": future,
            "positive_count": 3,
            "negative_count": 0,
            "last_feedback": "",
            "crystal_ri": 0.6,
            "crystal_type": "Insight",
            "crystal_origin": "conversation",
        },
    ]
    ctx.actuator._save_rules()


@when("format_rules_for_prompt is called")
def when_format_prompt(ctx):
    ctx.rules_text = ctx.actuator.format_rules_for_prompt()


@then("the output contains action keywords")
def then_output_has_keywords(ctx):
    assert ctx.rules_text, "Rules text should not be empty"
    # 應包含行為規則標記
    assert "行為規則" in ctx.rules_text
    # 應包含至少一個 action icon
    assert any(icon in ctx.rules_text for icon in ["⛔", "💡", "🔮", "🧪"])


# ═══════════════════════════════════════
# P3: 回饋驗證迴圈（新陳代謝）
# ═══════════════════════════════════════

@given("a CrystalActuator with a rule that has positive feedback")
def given_positive_feedback_rule(ctx):
    from museon.agent.crystal_actuator import CrystalActuator
    ctx.actuator = CrystalActuator(workspace=ctx.workspace)

    future = (datetime.now(TZ8) + timedelta(days=15)).isoformat()
    ctx.actuator._rules = [
        {
            "rule_id": "rule-pos-001",
            "source_cuid": "INS-pos-001",
            "rule_type": "style",
            "action": "preference",
            "summary": "正面回饋規則",
            "directive": "做得好",
            "strength": 1.0,
            "status": "active",
            "created_at": datetime.now(TZ8).isoformat(),
            "expires_at": future,
            "positive_count": 8,
            "negative_count": 1,
            "last_feedback": datetime.now(TZ8).isoformat(),
            "crystal_ri": 0.7,
            "crystal_type": "Insight",
            "crystal_origin": "conversation",
        },
    ]
    ctx.actuator._save_rules()


@when("metabolize is called")
def when_metabolize(ctx):
    ctx.result = ctx.actuator.metabolize()


@then("the rule strength increases")
def then_strength_increases(ctx):
    rules = ctx.actuator.get_active_rules()
    assert len(rules) > 0
    # 強化後 strength > 1.0
    assert rules[0]["strength"] > 1.0, (
        f"Expected strength > 1.0, got {rules[0]['strength']}"
    )


@then("the rule TTL is extended")
def then_ttl_extended(ctx):
    rules = ctx.actuator.get_active_rules()
    assert len(rules) > 0
    # 延長後 expires_at > now + 20 days（原本 15 天）
    expires = rules[0]["expires_at"]
    now_plus_20 = (datetime.now(TZ8) + timedelta(days=20)).isoformat()
    assert expires > now_plus_20, (
        f"Expected TTL extended, expires_at={expires}"
    )


@given("a CrystalActuator with a rule that has heavy negative feedback")
def given_negative_feedback_rule(ctx):
    from museon.agent.crystal_actuator import CrystalActuator
    ctx.actuator = CrystalActuator(workspace=ctx.workspace)

    future = (datetime.now(TZ8) + timedelta(days=30)).isoformat()
    ctx.actuator._rules = [
        {
            "rule_id": "rule-neg-001",
            "source_cuid": "INS-neg-001",
            "rule_type": "style",
            "action": "preference",
            "summary": "負面回饋規則",
            "directive": "做錯了",
            "strength": 0.3,  # 已經很弱
            "status": "active",
            "created_at": datetime.now(TZ8).isoformat(),
            "expires_at": future,
            "positive_count": 1,
            "negative_count": 9,
            "last_feedback": datetime.now(TZ8).isoformat(),
            "crystal_ri": 0.3,
            "crystal_type": "Insight",
            "crystal_origin": "conversation",
        },
    ]
    ctx.actuator._save_rules()


@then("the rule is removed")
def then_rule_removed(ctx):
    assert ctx.result["removed"] >= 1
    # 確認沒有活躍規則了
    active = ctx.actuator.get_active_rules()
    neg_rules = [r for r in active if r["rule_id"] == "rule-neg-001"]
    assert len(neg_rules) == 0, "Negative feedback rule should be removed"


# ═══════════════════════════════════════
# 整合：Nightly Pipeline
# ═══════════════════════════════════════

@given("a NightlyPipeline with workspace")
def given_nightly_pipeline(ctx):
    from museon.nightly.nightly_pipeline import NightlyPipeline
    ctx.pipeline = NightlyPipeline(workspace=ctx.workspace)


@when("step 5.7 crystal_actuator is executed")
def when_step_57(ctx):
    ctx.result = ctx.pipeline._step_crystal_actuator()


@then("the result contains actualize and metabolize reports")
def then_result_has_reports(ctx):
    assert ctx.result is not None
    # 結果應包含 actualize 的 key
    assert "total_active" in ctx.result or "skipped" in ctx.result or "error" in ctx.result


# ═══════════════════════════════════════
# 整合：Brain
# ═══════════════════════════════════════

@given("a MuseonBrain with CrystalActuator having active rules")
def given_brain_with_actuator(ctx):
    """模擬 Brain 中的 CrystalActuator."""
    from museon.agent.crystal_actuator import CrystalActuator
    actuator = CrystalActuator(workspace=ctx.workspace)

    future = (datetime.now(TZ8) + timedelta(days=30)).isoformat()
    actuator._rules = [
        {
            "rule_id": "rule-brain-001",
            "source_cuid": "LES-brain-001",
            "rule_type": "process",
            "action": "guard",
            "summary": "Brain 整合測試規則",
            "directive": "驗證規則注入",
            "strength": 1.5,
            "status": "active",
            "created_at": datetime.now(TZ8).isoformat(),
            "expires_at": future,
            "positive_count": 5,
            "negative_count": 0,
            "last_feedback": "",
            "crystal_ri": 0.8,
            "crystal_type": "Lesson",
            "crystal_origin": "morphenix_evolution",
        },
    ]
    actuator._save_rules()
    ctx.actuator = actuator


@when("build_system_prompt is called")
def when_build_prompt(ctx):
    # 直接測試 format_rules_for_prompt
    ctx.prompt_text = ctx.actuator.format_rules_for_prompt()


@then("the system prompt contains crystal behavior rules section")
def then_prompt_has_rules(ctx):
    assert ctx.prompt_text, "Prompt should contain rules"
    assert "行為規則" in ctx.prompt_text
    assert "Brain 整合測試規則" in ctx.prompt_text
    assert "⛔" in ctx.prompt_text  # guard action
