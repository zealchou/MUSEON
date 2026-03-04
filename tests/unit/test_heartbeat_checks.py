"""Tests for heartbeat_checks.py — Evolution Heartbeat RED/YELLOW/GREEN.

依據 THREE_LAYER_PULSE BDD Spec §7 的 BDD scenarios 驗證。
"""

import os

import pytest

from museon.core.event_bus import EVOLUTION_HEARTBEAT, EventBus
from museon.pulse.heartbeat_checks import (
    EVOLUTION_HB_INTERVAL,
    MIN_MEMORY_LAYERS,
    MIN_SCHEDULED_JOBS,
    _check_green,
    _check_red,
    _check_yellow,
    evolution_heartbeat_check,
    get_beat_counter,
    reset_beat_counter,
)


@pytest.fixture(autouse=True)
def reset_counter():
    """每個測試前重置 beat counter."""
    reset_beat_counter()
    yield
    reset_beat_counter()


@pytest.fixture
def workspace(tmp_path):
    return tmp_path / "workspace"


# ═══════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════


class TestConstants:
    """常數驗證."""

    def test_interval(self):
        assert EVOLUTION_HB_INTERVAL == 1800

    def test_min_jobs(self):
        assert MIN_SCHEDULED_JOBS == 5

    def test_min_layers(self):
        assert MIN_MEMORY_LAYERS == 2


# ═══════════════════════════════════════════
# Tri-Color Rotation Tests
# ═══════════════════════════════════════════


class TestTriColorRotation:
    """三色輪轉測試（BDD Spec §7.3）."""

    def test_red_every_beat(self, workspace):
        """BDD: RED 每次執行."""
        results = evolution_heartbeat_check(workspace, job_count=5)
        assert "red" in results
        assert "yellow" not in results
        assert "green" not in results
        assert get_beat_counter() == 1

    def test_yellow_even_beats(self, workspace):
        """BDD: YELLOW 偶數次."""
        evolution_heartbeat_check(workspace, job_count=5)
        results = evolution_heartbeat_check(workspace, job_count=5)
        assert "red" in results
        assert "yellow" in results
        assert "green" not in results
        assert get_beat_counter() == 2

    def test_green_every_4(self, workspace):
        """BDD: GREEN 每 4 次."""
        for _ in range(3):
            evolution_heartbeat_check(workspace, job_count=5)
        results = evolution_heartbeat_check(workspace, job_count=5)
        assert "red" in results
        assert "yellow" in results
        assert "green" in results
        assert get_beat_counter() == 4

    def test_beat_5_no_green(self, workspace):
        """BDD: 第 5 次 → RED only."""
        for _ in range(4):
            evolution_heartbeat_check(workspace, job_count=5)
        results = evolution_heartbeat_check(workspace, job_count=5)
        assert "red" in results
        assert "yellow" not in results
        assert "green" not in results

    def test_beat_8_all_colors(self, workspace):
        """BDD: 第 8 次 → 全三色."""
        for _ in range(7):
            evolution_heartbeat_check(workspace, job_count=5)
        results = evolution_heartbeat_check(workspace, job_count=5)
        assert "red" in results
        assert "yellow" in results
        assert "green" in results


# ═══════════════════════════════════════════
# RED Check Tests
# ═══════════════════════════════════════════


class TestRedCheck:
    """RED 檢查測試."""

    def test_jobs_below_threshold(self, workspace):
        """BDD: 排程 job 不足 → warning."""
        result = _check_red(workspace, job_count=2)
        assert result["status"] == "warning"
        assert any("below threshold" in w for w in result["warnings"])

    def test_jobs_at_threshold(self, workspace):
        """BDD: 排程 job 恰好 5 → ok."""
        result = _check_red(workspace, job_count=5)
        assert result["scheduled_jobs"] == 5
        # memory layers might be 0, so could still be warning
        # just check jobs warning is absent
        job_warnings = [w for w in result["warnings"] if "scheduled jobs" in w]
        assert len(job_warnings) == 0

    def test_memory_layers_counted(self, workspace):
        """BDD: 記憶層正確計算."""
        workspace.mkdir(parents=True)
        # 建立 2 個記憶層
        memory = workspace / "memory" / "user1"
        (memory / "L0_buffer").mkdir(parents=True)
        (memory / "L0_buffer" / "test.json").write_text("{}")
        (memory / "L1_short").mkdir(parents=True)
        (memory / "L1_short" / "test.json").write_text("{}")

        result = _check_red(workspace, job_count=5)
        assert result["memory_layers"] >= 2


# ═══════════════════════════════════════════
# YELLOW Check Tests
# ═══════════════════════════════════════════


class TestYellowCheck:
    """YELLOW 檢查測試."""

    def test_no_evolution_state(self, workspace):
        """BDD: 進化狀態檔案不存在 → warning."""
        workspace.mkdir(parents=True, exist_ok=True)
        result = _check_yellow(workspace)
        assert not result["evolution_state_exists"]
        assert result["status"] == "warning"

    def test_evolution_state_exists(self, workspace):
        """BDD: 進化狀態檔案存在 → ok."""
        state_dir = workspace / "_system" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "evolution_state.json").write_text("{}")
        result = _check_yellow(workspace)
        assert result["evolution_state_exists"]
        assert result["status"] == "ok"


# ═══════════════════════════════════════════
# GREEN Check Tests
# ═══════════════════════════════════════════


class TestGreenCheck:
    """GREEN 檢查測試."""

    def test_no_forge_dir(self, workspace):
        """BDD: 無 forge 目錄."""
        workspace.mkdir(parents=True, exist_ok=True)
        result = _check_green(workspace)
        assert result["skill_forge_scan"] is False

    def test_forge_with_pending(self, workspace):
        """BDD: 有待處理課程和突變."""
        forge_dir = workspace / "_system" / "state" / "forge"
        forge_dir.mkdir(parents=True)
        (forge_dir / "curriculum_001.json").write_text("{}")
        (forge_dir / "curriculum_002.json").write_text("{}")
        (forge_dir / "mutation_001.json").write_text("{}")

        result = _check_green(workspace)
        assert result["skill_forge_scan"] is True
        assert result["pending_curriculum"] == 2
        assert result["pending_mutations"] == 1


# ═══════════════════════════════════════════
# EventBus Integration Tests
# ═══════════════════════════════════════════


class TestEventBusIntegration:
    """EventBus 整合測試."""

    def test_publishes_event(self, workspace):
        """BDD: 發布 EVOLUTION_HEARTBEAT 事件."""
        bus = EventBus()
        received = []
        bus.subscribe(EVOLUTION_HEARTBEAT, lambda d: received.append(d))

        evolution_heartbeat_check(workspace, event_bus=bus, job_count=5)
        assert len(received) == 1
        assert "red" in received[0]

    def test_no_event_bus_ok(self, workspace):
        """BDD: 無 event_bus 不報錯."""
        result = evolution_heartbeat_check(workspace, job_count=5)
        assert "red" in result
