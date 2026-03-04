"""TaskScheduler — cron 風格排程器.

依據 THREE_LAYER_PULSE BDD Spec §9 實作。
Facade on CronEngine，提供更高階的 cron 排程抽象。
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# ScheduledTask
# ═══════════════════════════════════════════


@dataclass
class ScheduledTask:
    """排程任務."""

    name: str
    func: Callable
    interval: int = 86400  # 預設每日
    cron_hour: Optional[int] = None
    cron_minute: int = 0
    cron_day_of_week: Optional[int] = None  # 0=Monday
    cron_day_of_month: Optional[int] = None
    last_run: Optional[str] = None  # ISO format date string
    description: str = ""


# ═══════════════════════════════════════════
# TaskScheduler
# ═══════════════════════════════════════════


class TaskScheduler:
    """cron 風格排程器.

    支援：
    - 日排程（cron_hour + cron_minute）
    - 週排程（cron_day_of_week）
    - 月排程（cron_day_of_month）
    - 每日只執行一次保護
    - 狀態持久化
    """

    def __init__(self, state_path: Optional[str] = None) -> None:
        self._tasks: List[ScheduledTask] = []
        self._state_path = Path(state_path) if state_path else None
        self._saved_state: Dict[str, str] = {}
        self._running = False
        self._load_state()

    def register(
        self,
        name: str,
        func: Callable,
        cron_hour: Optional[int] = None,
        cron_minute: int = 0,
        cron_day_of_week: Optional[int] = None,
        cron_day_of_month: Optional[int] = None,
        description: str = "",
    ) -> None:
        """註冊排程任務."""
        last_run = self._saved_state.get(name)
        task = ScheduledTask(
            name=name,
            func=func,
            cron_hour=cron_hour,
            cron_minute=cron_minute,
            cron_day_of_week=cron_day_of_week,
            cron_day_of_month=cron_day_of_month,
            last_run=last_run,
            description=description,
        )
        # 替換同名任務
        self._tasks = [t for t in self._tasks if t.name != name]
        self._tasks.append(task)

    def check_due(self, now: Optional[datetime] = None) -> List[str]:
        """檢查並執行到期的任務.

        Returns:
            已執行的任務名稱列表
        """
        if now is None:
            now = datetime.now()

        executed = []
        for task in self._tasks:
            if self._is_due(task, now):
                try:
                    task.func()
                    task.last_run = now.date().isoformat()
                    executed.append(task.name)
                    logger.info(f"TaskScheduler executed: {task.name}")
                except Exception as e:
                    logger.error(
                        f"TaskScheduler task '{task.name}' failed: {e}"
                    )

        if executed:
            self._save_state()

        return executed

    def _is_due(self, task: ScheduledTask, now: datetime) -> bool:
        """判斷任務是否到期."""
        # 今日已執行？
        today = now.date().isoformat()
        if task.last_run == today:
            return False

        # 時間匹配？
        if task.cron_hour is not None:
            if now.hour != task.cron_hour:
                return False
            if now.minute < task.cron_minute:
                return False

        # 週幾匹配？
        if task.cron_day_of_week is not None:
            if now.weekday() != task.cron_day_of_week:
                return False

        # 日期匹配？
        if task.cron_day_of_month is not None:
            if now.day != task.cron_day_of_month:
                return False

        return True

    def get_tasks(self) -> List[Dict]:
        """回傳所有任務資訊."""
        return [
            {
                "name": t.name,
                "cron_hour": t.cron_hour,
                "cron_minute": t.cron_minute,
                "cron_day_of_week": t.cron_day_of_week,
                "last_run": t.last_run,
                "description": t.description,
            }
            for t in self._tasks
        ]

    # ── 持久化 ──

    def _save_state(self) -> None:
        """儲存排程狀態."""
        if not self._state_path:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {t.name: t.last_run for t in self._tasks if t.last_run}
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.rename(self._state_path)
        except Exception as e:
            logger.error(f"TaskScheduler save state failed: {e}")

    def _load_state(self) -> None:
        """載入排程狀態."""
        if not self._state_path or not self._state_path.exists():
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                self._saved_state = json.load(f)
        except Exception as e:
            logger.error(f"TaskScheduler load state failed: {e}")
