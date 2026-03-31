"""Cron Engine - Unix-style job scheduling."""

import asyncio
import functools
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.job import Job

logger = logging.getLogger(__name__)

# 預設超時秒數（依觸發類型）
_DEFAULT_TIMEOUT_CRON = 600     # cron 排程：10 分鐘
_DEFAULT_TIMEOUT_INTERVAL = 120  # interval 排程：2 分鐘


def _wrap_with_timeout(
    func: Callable, timeout: float, job_id: str, job_stats: dict
) -> Callable:
    """包裝 async 函式加入超時保護與執行統計."""
    if not asyncio.iscoroutinefunction(func):
        return func  # 同步函式不包裝

    @functools.wraps(func)
    async def _wrapper():
        _stat = job_stats.setdefault(job_id, {
            "run_count": 0, "fail_count": 0,
            "consecutive_failures": 0,
            "last_success": None, "last_error": None,
        })
        try:
            await asyncio.wait_for(func(), timeout=timeout)
            _stat["run_count"] += 1
            _stat["consecutive_failures"] = 0
            _stat["last_success"] = datetime.now().isoformat()
        except asyncio.TimeoutError:
            _stat["fail_count"] += 1
            _stat["consecutive_failures"] += 1
            _stat["last_error"] = f"timeout after {timeout}s"
            logger.warning(f"Cron job '{job_id}' timed out after {timeout}s, killed")
        except Exception as e:
            _stat["fail_count"] += 1
            _stat["consecutive_failures"] += 1
            _stat["last_error"] = str(e)[:200]
            logger.warning(f"Cron job '{job_id}' failed: {e}")

    return _wrapper


class CronEngine:
    """
    Cron engine for scheduling background tasks.

    Supports both cron expressions (for nightly jobs) and interval triggers
    (for heartbeat polling). All async jobs are wrapped with timeout protection.
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._job_stats: dict[str, dict] = {}

    def start(self) -> None:
        """Start the scheduler."""
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)

    def add_job(
        self,
        func: Callable,
        trigger: str,
        job_id: str,
        timeout: Optional[float] = None,
        **trigger_args: Any,
    ) -> str:
        """
        Add a scheduled job with automatic timeout protection.

        Args:
            func: The function to execute
            trigger: 'cron' or 'interval'
            job_id: Unique identifier for the job
            timeout: Timeout in seconds. Defaults to 600s for cron, 120s for interval.
                     Set to 0 to disable timeout.
            **trigger_args: Arguments for the trigger (e.g., hour=2, minute=0)

        Returns:
            The job ID
        """
        if trigger == "cron":
            trigger_obj = CronTrigger(**trigger_args)
            default_timeout = _DEFAULT_TIMEOUT_CRON
        elif trigger == "interval":
            trigger_obj = IntervalTrigger(**trigger_args)
            default_timeout = _DEFAULT_TIMEOUT_INTERVAL
        else:
            raise ValueError(f"Unknown trigger type: {trigger}")

        # 超時保護：包裝 async 函式
        effective_timeout = timeout if timeout is not None else default_timeout
        if effective_timeout > 0:
            func = _wrap_with_timeout(func, effective_timeout, job_id, self._job_stats)

        self._scheduler.add_job(func, trigger_obj, id=job_id, replace_existing=True)
        return job_id

    def remove_job(self, job_id: str) -> None:
        """
        Remove a scheduled job.

        Args:
            job_id: The job identifier
        """
        self._scheduler.remove_job(job_id)

    def get_job(self, job_id: str) -> Optional[Job]:
        """
        Get a scheduled job.

        Args:
            job_id: The job identifier

        Returns:
            The Job object or None if not found
        """
        return self._scheduler.get_job(job_id)

    def get_all_jobs(self) -> list:
        """
        Get all scheduled jobs.

        Returns:
            List of Job objects
        """
        return self._scheduler.get_jobs()

    def status(self) -> dict:
        """Return execution stats for all registered jobs."""
        return dict(self._job_stats)
