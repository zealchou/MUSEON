"""Tests for task_scheduler.py — TaskScheduler cron 排程.

依據 THREE_LAYER_PULSE BDD Spec §9 的 BDD scenarios 驗證。
"""

import json
from datetime import datetime

import pytest

from museon.pulse.task_scheduler import ScheduledTask, TaskScheduler


# ═══════════════════════════════════════════
# Daily Schedule Tests
# ═══════════════════════════════════════════


class TestDailySchedule:
    """日排程測試（BDD Spec §9.2）."""

    def test_daily_trigger(self):
        """BDD: cron_hour=3 在 03:00 觸發."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register("nightly", lambda: executed.append(1), cron_hour=3)

        now = datetime(2026, 2, 27, 3, 0)
        result = scheduler.check_due(now)
        assert "nightly" in result
        assert len(executed) == 1

    def test_not_due_wrong_hour(self):
        """BDD: 非 cron_hour 不觸發."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register("nightly", lambda: executed.append(1), cron_hour=3)

        now = datetime(2026, 2, 27, 5, 0)
        result = scheduler.check_due(now)
        assert result == []
        assert len(executed) == 0

    def test_no_duplicate_daily(self):
        """BDD: 今日已執行不重複."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register("nightly", lambda: executed.append(1), cron_hour=3)

        now = datetime(2026, 2, 27, 3, 0)
        scheduler.check_due(now)
        assert len(executed) == 1

        # 同一天再檢查
        now2 = datetime(2026, 2, 27, 3, 5)
        scheduler.check_due(now2)
        assert len(executed) == 1  # 不重複

    def test_next_day_triggers(self):
        """BDD: 隔天再次觸發."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register("nightly", lambda: executed.append(1), cron_hour=3)

        day1 = datetime(2026, 2, 27, 3, 0)
        scheduler.check_due(day1)
        assert len(executed) == 1

        day2 = datetime(2026, 2, 28, 3, 0)
        scheduler.check_due(day2)
        assert len(executed) == 2

    def test_minute_check(self):
        """BDD: cron_minute 檢查."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register(
            "job", lambda: executed.append(1), cron_hour=3, cron_minute=30
        )

        # 03:15 — 未到
        early = datetime(2026, 2, 27, 3, 15)
        scheduler.check_due(early)
        assert len(executed) == 0

        # 03:30 — 到了
        on_time = datetime(2026, 2, 27, 3, 30)
        scheduler.check_due(on_time)
        assert len(executed) == 1


# ═══════════════════════════════════════════
# Weekly Schedule Tests
# ═══════════════════════════════════════════


class TestWeeklySchedule:
    """週排程測試."""

    def test_weekly_trigger_monday(self):
        """BDD: cron_day_of_week=0 (週一) 在週一觸發."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register(
            "weekly", lambda: executed.append(1),
            cron_hour=3, cron_day_of_week=0,
        )

        # 2026-03-02 is Monday
        monday = datetime(2026, 3, 2, 3, 0)
        assert monday.weekday() == 0
        scheduler.check_due(monday)
        assert len(executed) == 1

    def test_weekly_no_trigger_wrong_day(self):
        """BDD: 非指定週幾不觸發."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register(
            "weekly", lambda: executed.append(1),
            cron_hour=3, cron_day_of_week=0,  # Monday
        )

        # 2026-02-27 is Friday
        friday = datetime(2026, 2, 27, 3, 0)
        assert friday.weekday() == 4
        scheduler.check_due(friday)
        assert len(executed) == 0


# ═══════════════════════════════════════════
# Monthly Schedule Tests
# ═══════════════════════════════════════════


class TestMonthlySchedule:
    """月排程測試."""

    def test_monthly_trigger(self):
        """BDD: cron_day_of_month=1 在每月 1 號觸發."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register(
            "monthly", lambda: executed.append(1),
            cron_hour=3, cron_day_of_month=1,
        )

        first = datetime(2026, 3, 1, 3, 0)
        scheduler.check_due(first)
        assert len(executed) == 1

    def test_monthly_no_trigger_wrong_day(self):
        """BDD: 非 1 號不觸發."""
        scheduler = TaskScheduler()
        executed = []
        scheduler.register(
            "monthly", lambda: executed.append(1),
            cron_hour=3, cron_day_of_month=1,
        )

        other = datetime(2026, 3, 15, 3, 0)
        scheduler.check_due(other)
        assert len(executed) == 0


# ═══════════════════════════════════════════
# Error Handling Tests
# ═══════════════════════════════════════════


class TestErrorHandling:
    """錯誤處理測試."""

    def test_task_error_no_crash(self):
        """BDD: 任務錯誤不中斷排程器."""
        scheduler = TaskScheduler()
        results = []

        def bad(): raise RuntimeError("fail")
        def good(): results.append(1)

        scheduler.register("bad", bad, cron_hour=3)
        scheduler.register("good", good, cron_hour=3)

        now = datetime(2026, 2, 27, 3, 0)
        executed = scheduler.check_due(now)
        # good 應該被執行
        assert "good" in executed
        assert len(results) == 1

    def test_replace_same_name(self):
        """BDD: 同名任務覆寫."""
        scheduler = TaskScheduler()
        results = []
        scheduler.register("job", lambda: results.append("old"), cron_hour=3)
        scheduler.register("job", lambda: results.append("new"), cron_hour=3)

        now = datetime(2026, 2, 27, 3, 0)
        scheduler.check_due(now)
        assert results == ["new"]


# ═══════════════════════════════════════════
# Persistence Tests
# ═══════════════════════════════════════════


class TestPersistence:
    """狀態持久化測試."""

    def test_save_and_restore(self, tmp_path):
        """BDD: 狀態持久化 + 恢復."""
        path = str(tmp_path / "schedules.json")

        sched1 = TaskScheduler(state_path=path)
        sched1.register("nightly", lambda: None, cron_hour=3)
        sched1.check_due(datetime(2026, 2, 27, 3, 0))

        # 新實例載入
        sched2 = TaskScheduler(state_path=path)
        sched2.register("nightly", lambda: None, cron_hour=3)

        # 同天不重複
        executed = []
        sched2.register("nightly", lambda: executed.append(1), cron_hour=3)
        sched2.check_due(datetime(2026, 2, 27, 3, 5))
        assert len(executed) == 0

    def test_no_state_path(self):
        """BDD: 無 state_path 不報錯."""
        scheduler = TaskScheduler()
        scheduler.register("job", lambda: None, cron_hour=3)
        scheduler.check_due(datetime(2026, 2, 27, 3, 0))


# ═══════════════════════════════════════════
# Get Tasks Tests
# ═══════════════════════════════════════════


class TestGetTasks:
    """任務列表測試."""

    def test_get_tasks(self):
        """BDD: get_tasks 正確."""
        scheduler = TaskScheduler()
        scheduler.register("a", lambda: None, cron_hour=3, description="夜間任務")
        scheduler.register("b", lambda: None, cron_hour=8, cron_day_of_week=0)

        tasks = scheduler.get_tasks()
        assert len(tasks) == 2
        names = [t["name"] for t in tasks]
        assert "a" in names
        assert "b" in names
