"""Cron Engine - Unix-style job scheduling."""

import asyncio
import functools
import logging
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.job import Job

logger = logging.getLogger(__name__)

# 預設超時秒數（依觸發類型）
_DEFAULT_TIMEOUT_CRON = 600     # cron 排程：10 分鐘
_DEFAULT_TIMEOUT_INTERVAL = 120  # interval 排程：2 分鐘


def _wrap_with_timeout(func: Callable, timeout: float, job_id: str) -> Callable:
    """包裝 async 函式加入超時保護."""
    if not asyncio.iscoroutinefunction(func):
        return func  # 同步函式不包裝

    @functools.wraps(func)
    async def _wrapper():
        try:
            await asyncio.wait_for(func(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(
                f"Cron job '{job_id}' timed out after {timeout}s, killed"
            )
        except Exception as e:
            logger.debug(f"Cron job '{job_id}' failed: {e}")

    return _wrapper


class CronEngine:
    """
    Cron engine for scheduling background tasks.

    Supports both cron expressions (for nightly jobs) and interval triggers
    (for heartbeat polling). All async jobs are wrapped with timeout protection.
    """

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

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
            func = _wrap_with_timeout(func, effective_timeout, job_id)

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
