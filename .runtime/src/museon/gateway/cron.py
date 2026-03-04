"""Cron Engine - Unix-style job scheduling."""

import asyncio
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.job import Job


class CronEngine:
    """
    Cron engine for scheduling background tasks.

    Supports both cron expressions (for nightly jobs) and interval triggers
    (for heartbeat polling).
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
        **trigger_args: Any,
    ) -> str:
        """
        Add a scheduled job.

        Args:
            func: The function to execute
            trigger: 'cron' or 'interval'
            job_id: Unique identifier for the job
            **trigger_args: Arguments for the trigger (e.g., hour=2, minute=0)

        Returns:
            The job ID

        Examples:
            # Interval trigger (every 30 minutes)
            engine.add_job(heartbeat, trigger='interval', minutes=30, job_id='heartbeat')

            # Cron trigger (every day at 2am)
            engine.add_job(nightly_job, trigger='cron', hour=2, minute=0, job_id='nightly')
        """
        if trigger == "cron":
            trigger_obj = CronTrigger(**trigger_args)
        elif trigger == "interval":
            trigger_obj = IntervalTrigger(**trigger_args)
        else:
            raise ValueError(f"Unknown trigger type: {trigger}")

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
