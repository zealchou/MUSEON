"""Tests for heartbeat_engine.py — 單例心跳引擎.

依據 THREE_LAYER_PULSE BDD Spec §2 的 BDD scenarios 驗證。
"""

import json
import time

import pytest

from museon.pulse.heartbeat_engine import (
    TICK_INTERVAL,
    HeartbeatEngine,
    HeartbeatTask,
    _reset_heartbeat_engine,
    get_heartbeat_engine,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    """每個測試前重置 HeartbeatEngine 單例."""
    _reset_heartbeat_engine()
    yield
    _reset_heartbeat_engine()


# ═══════════════════════════════════════════
# Singleton Tests
# ═══════════════════════════════════════════


class TestSingleton:
    """單例模式測試."""

    def test_same_instance(self):
        """BDD: 多次呼叫 get_heartbeat_engine() 回傳同一個實例."""
        engine1 = get_heartbeat_engine()
        engine2 = get_heartbeat_engine()
        assert engine1 is engine2


# ═══════════════════════════════════════════
# Register / Unregister Tests
# ═══════════════════════════════════════════


class TestRegister:
    """註冊任務測試."""

    def test_register_task(self):
        """BDD: 註冊任務後存在於 _tasks."""
        engine = HeartbeatEngine()
        engine.register("test", lambda: None, interval_seconds=1800)
        assert "test" in engine._tasks
        assert engine._tasks["test"].interval_seconds == 1800

    def test_register_enabled_default(self):
        """BDD: 預設 enabled=True."""
        engine = HeartbeatEngine()
        engine.register("test", lambda: None, interval_seconds=10)
        assert engine._tasks["test"].enabled is True

    def test_register_disabled(self):
        """BDD: enabled=False."""
        engine = HeartbeatEngine()
        engine.register("test", lambda: None, interval_seconds=10, enabled=False)
        assert engine._tasks["test"].enabled is False

    def test_unregister(self):
        """BDD: 移除任務後不再存在."""
        engine = HeartbeatEngine()
        engine.register("a", lambda: None, interval_seconds=10)
        engine.unregister("a")
        assert "a" not in engine._tasks

    def test_unregister_nonexistent(self):
        """BDD: 移除不存在的任務不報錯."""
        engine = HeartbeatEngine()
        engine.unregister("nope")  # should not raise


# ═══════════════════════════════════════════
# Tick Tests
# ═══════════════════════════════════════════


class TestTick:
    """tick 觸發測試."""

    def test_tick_triggers_due_task(self):
        """BDD: tick 觸發到期任務."""
        engine = HeartbeatEngine()
        called = []
        engine.register("a", lambda: called.append(1), interval_seconds=10)
        # 設定 last_run 為 15 秒前
        engine._tasks["a"].last_run = time.time() - 15
        engine.tick()
        assert len(called) == 1
        assert engine._tasks["a"].run_count == 1

    def test_tick_no_trigger_not_due(self):
        """BDD: tick 不觸發未到期任務."""
        engine = HeartbeatEngine()
        called = []
        engine.register("b", lambda: called.append(1), interval_seconds=1800)
        engine._tasks["b"].last_run = time.time() - 5
        engine.tick()
        assert len(called) == 0

    def test_tick_updates_last_run(self):
        """BDD: tick 後 last_run 更新."""
        engine = HeartbeatEngine()
        engine.register("a", lambda: None, interval_seconds=10)
        engine._tasks["a"].last_run = time.time() - 15
        before = time.time()
        engine.tick()
        assert engine._tasks["a"].last_run >= before

    def test_task_error_isolated(self):
        """BDD: 任務錯誤不影響其他任務."""
        engine = HeartbeatEngine()
        results = []

        def bad_func():
            raise RuntimeError("boom")

        def good_func():
            results.append("ok")

        engine.register("bad", bad_func, interval_seconds=1)
        engine.register("good", good_func, interval_seconds=1)
        engine._tasks["bad"].last_run = 0
        engine._tasks["good"].last_run = 0

        engine.tick()

        assert engine._tasks["bad"].last_error == "boom"
        assert results == ["ok"]

    def test_disabled_task_not_triggered(self):
        """BDD: 停用任務不執行."""
        engine = HeartbeatEngine()
        called = []
        engine.register("a", lambda: called.append(1), interval_seconds=1, enabled=False)
        engine._tasks["a"].last_run = 0
        engine.tick()
        assert len(called) == 0

    def test_run_count_increments(self):
        """BDD: run_count 遞增."""
        engine = HeartbeatEngine()
        engine.register("a", lambda: None, interval_seconds=1)
        engine._tasks["a"].last_run = 0
        engine.tick()
        assert engine._tasks["a"].run_count == 1
        engine._tasks["a"].last_run = 0
        engine.tick()
        assert engine._tasks["a"].run_count == 2


# ═══════════════════════════════════════════
# Daemon Thread Tests
# ═══════════════════════════════════════════


class TestDaemonThread:
    """守護線程測試."""

    def test_daemon_thread(self):
        """BDD: start() 後 _thread.daemon == True."""
        engine = HeartbeatEngine()
        engine._tick_interval = 0.1
        engine.register("test", lambda: None, interval_seconds=3600)
        engine.start()
        try:
            assert engine._thread is not None
            assert engine._thread.daemon is True
            assert engine._running is True
        finally:
            engine.stop()
        assert engine._running is False

    def test_start_idempotent(self):
        """BDD: 多次 start() 不產生多個線程."""
        engine = HeartbeatEngine()
        engine._tick_interval = 0.1
        engine.start()
        thread1 = engine._thread
        engine.start()
        thread2 = engine._thread
        engine.stop()
        assert thread1 is thread2


# ═══════════════════════════════════════════
# Status Tests
# ═══════════════════════════════════════════


class TestStatus:
    """狀態報告測試."""

    def test_status_report(self):
        """BDD: status() 回傳正確格式."""
        engine = HeartbeatEngine()
        engine.register("a", lambda: None, interval_seconds=1800)
        engine._tasks["a"].run_count = 5
        engine._tasks["a"].last_run = 12345.0
        engine._tasks["a"].last_error = None

        status = engine.status()
        assert "a" in status
        assert status["a"]["run_count"] == 5
        assert status["a"]["last_run"] == 12345.0
        assert status["a"]["last_error"] is None
        assert status["a"]["enabled"] is True
        assert status["a"]["interval_seconds"] == 1800


# ═══════════════════════════════════════════
# Persistence Tests
# ═══════════════════════════════════════════


class TestPersistence:
    """持久化測試."""

    def test_save_and_restore(self, tmp_path):
        """BDD: 狀態持久化 + 重啟恢復."""
        path = str(tmp_path / "state" / "heartbeat_tasks.json")

        engine1 = HeartbeatEngine(state_path=path)
        engine1.register("a", lambda: None, interval_seconds=1800)
        engine1._tasks["a"].last_run = 12345.0
        engine1._tasks["a"].run_count = 10
        engine1._save_state()

        # 新實例載入
        engine2 = HeartbeatEngine(state_path=path)
        engine2.register("a", lambda: None, interval_seconds=1800)
        assert engine2._tasks["a"].last_run == 12345.0
        assert engine2._tasks["a"].run_count == 10

    def test_no_state_path_no_error(self):
        """BDD: 無 state_path 不報錯."""
        engine = HeartbeatEngine()
        engine.register("a", lambda: None, interval_seconds=10)
        engine._save_state()  # should not raise

    def test_restore_prevents_immediate_rerun(self, tmp_path):
        """BDD: 重啟後不立即重新執行剛執行過的任務."""
        path = str(tmp_path / "heartbeat_tasks.json")

        engine1 = HeartbeatEngine(state_path=path)
        engine1.register("a", lambda: None, interval_seconds=1800)
        engine1._tasks["a"].last_run = time.time()  # 剛執行過
        engine1._save_state()

        # 新實例
        engine2 = HeartbeatEngine(state_path=path)
        called = []
        engine2.register("a", lambda: called.append(1), interval_seconds=1800)
        engine2.tick()
        assert len(called) == 0  # 不應重新執行

    def test_state_file_format(self, tmp_path):
        """BDD: 狀態檔案 JSON 格式正確."""
        path = str(tmp_path / "heartbeat_tasks.json")

        engine = HeartbeatEngine(state_path=path)
        engine.register("a", lambda: None, interval_seconds=1800)
        engine._tasks["a"].last_run = 1000.0
        engine._tasks["a"].run_count = 3
        engine._save_state()

        with open(path, "r") as f:
            data = json.load(f)
        assert "a" in data
        assert data["a"]["last_run"] == 1000.0
        assert data["a"]["run_count"] == 3
