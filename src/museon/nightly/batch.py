"""
Batch API Integration

Uses Claude Batch API for non-real-time nightly tasks:
- 50% cost savings
- 24-hour completion window
- Perfect for memory fusion, quality analysis, etc.

Batch API allows processing multiple requests together at half the cost.
"""
import logging
import asyncio
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class BatchStatus(str, Enum):
    """Batch processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchProcessor:
    """Handles Claude Batch API integration for nightly jobs."""

    def __init__(self, llm_client):
        """
        Initialize batch processor.

        Args:
            llm_client: LLM client with Batch API support
        """
        self.llm_client = llm_client
        self.batches = {}  # Track active batches

    async def create_batch(
        self,
        tasks: List[Dict[str, Any]],
        batch_name: Optional[str] = None
    ) -> str:
        """
        Create a batch job with multiple tasks.

        Args:
            tasks: List of task dicts, each containing:
                - type: Task type (e.g., "fusion", "analysis")
                - data: Task-specific data
            batch_name: Optional batch identifier

        Returns:
            Batch ID for tracking
        """
        batch_id = batch_name or f"batch_{uuid.uuid4().hex[:8]}"

        logger.info(f"Creating batch {batch_id} with {len(tasks)} tasks")

        # Convert tasks to batch requests
        batch_requests = self._prepare_batch_requests(tasks)

        # Store batch info
        self.batches[batch_id] = {
            "id": batch_id,
            "status": BatchStatus.PENDING,
            "tasks": tasks,
            "requests": batch_requests,
            "created_at": datetime.now().isoformat(),
            "total_tasks": len(tasks),
            "completed_tasks": 0,
            "results": []
        }

        # Submit batch to API (mock for now)
        try:
            # In real implementation, this would call:
            # response = await self.llm_client.batches.create(requests=batch_requests)
            # For now, simulate submission
            self.batches[batch_id]["status"] = BatchStatus.PROCESSING
            logger.info(f"Batch {batch_id} submitted successfully")

        except Exception as e:
            logger.error(f"Failed to create batch {batch_id}: {e}")
            self.batches[batch_id]["status"] = BatchStatus.FAILED
            self.batches[batch_id]["error"] = str(e)

        return batch_id

    async def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """
        Check status of a batch job.

        Args:
            batch_id: Batch ID to check

        Returns:
            Dict with batch status and progress
        """
        if batch_id not in self.batches:
            return {
                "status": "not_found",
                "error": f"Batch {batch_id} not found"
            }

        batch = self.batches[batch_id]

        # In real implementation, poll API for status
        # For now, return stored status
        return {
            "batch_id": batch_id,
            "status": batch["status"],
            "progress": (batch["completed_tasks"] / batch["total_tasks"]) * 100,
            "total_tasks": batch["total_tasks"],
            "completed_tasks": batch["completed_tasks"],
            "created_at": batch["created_at"],
            "results": batch.get("results", [])
        }

    async def wait_for_batch(
        self,
        batch_id: str,
        timeout_seconds: int = 86400  # 24 hours
    ) -> Dict[str, Any]:
        """
        Wait for batch to complete (with timeout).

        Args:
            batch_id: Batch ID to wait for
            timeout_seconds: Max wait time (default 24 hours)

        Returns:
            Final batch results
        """
        logger.info(f"Waiting for batch {batch_id} (timeout: {timeout_seconds}s)")

        start_time = datetime.now()
        poll_interval = 60  # Check every minute

        while True:
            status = await self.get_batch_status(batch_id)

            if status["status"] in [BatchStatus.COMPLETED, BatchStatus.FAILED, BatchStatus.CANCELLED]:
                return status

            # Check timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout_seconds:
                logger.error(f"Batch {batch_id} timed out after {elapsed}s")
                return {
                    "batch_id": batch_id,
                    "status": "timeout",
                    "error": f"Batch did not complete within {timeout_seconds}s"
                }

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    def calculate_batch_cost(self, standard_tokens: int) -> int:
        """
        Calculate batch API cost (50% of standard).

        Args:
            standard_tokens: Token count at standard pricing

        Returns:
            Batch API equivalent token cost
        """
        return standard_tokens // 2  # 50% savings

    async def process_fusion_batch(
        self,
        dates: List[str],
        memory_store
    ) -> Dict[str, Any]:
        """
        Process multiple memory fusion tasks as a batch.

        Args:
            dates: List of dates to process
            memory_store: Memory store instance

        Returns:
            Batch processing results
        """
        logger.info(f"Processing fusion batch for {len(dates)} dates")

        # Prepare fusion tasks
        tasks = []
        for date in dates:
            tasks.append({
                "type": "fusion",
                "data": {"date": date}
            })

        # Create batch
        batch_id = await self.create_batch(tasks, batch_name=f"fusion_{datetime.now().date()}")

        # Wait for completion (in background for real usage)
        # For testing, simulate immediate completion
        self.batches[batch_id]["status"] = BatchStatus.COMPLETED
        self.batches[batch_id]["completed_tasks"] = len(tasks)

        return await self.get_batch_status(batch_id)

    def _prepare_batch_requests(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert tasks to Batch API request format.

        Args:
            tasks: List of tasks

        Returns:
            List of batch API requests
        """
        requests = []

        for i, task in enumerate(tasks):
            task_type = task.get("type")
            task_data = task.get("data", {})

            # Create request based on task type
            if task_type == "fusion":
                request = {
                    "custom_id": f"task_{i}",
                    "params": {
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 1000,
                        "messages": [{
                            "role": "user",
                            "content": self._create_fusion_prompt(task_data)
                        }]
                    }
                }
                requests.append(request)

            elif task_type == "analysis":
                request = {
                    "custom_id": f"task_{i}",
                    "params": {
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": 500,
                        "messages": [{
                            "role": "user",
                            "content": task_data.get("prompt", "")
                        }]
                    }
                }
                requests.append(request)

        return requests

    def _create_fusion_prompt(self, task_data: Dict[str, Any]) -> str:
        """Create fusion prompt from task data."""
        date = task_data.get("date", "unknown")
        return f"Fuse memories for date: {date}"

    async def cancel_batch(self, batch_id: str) -> bool:
        """
        Cancel a pending or processing batch.

        Args:
            batch_id: Batch ID to cancel

        Returns:
            True if cancelled successfully
        """
        if batch_id not in self.batches:
            logger.error(f"Cannot cancel unknown batch {batch_id}")
            return False

        batch = self.batches[batch_id]

        if batch["status"] == BatchStatus.COMPLETED:
            logger.warning(f"Cannot cancel already completed batch {batch_id}")
            return False

        batch["status"] = BatchStatus.CANCELLED
        logger.info(f"Batch {batch_id} cancelled")
        return True

    async def get_all_batches(self) -> List[Dict[str, Any]]:
        """
        Get status of all batches.

        Returns:
            List of batch status dicts
        """
        return [
            {
                "id": batch_id,
                "status": batch["status"],
                "total_tasks": batch["total_tasks"],
                "completed_tasks": batch["completed_tasks"],
                "created_at": batch["created_at"]
            }
            for batch_id, batch in self.batches.items()
        ]

    def estimate_savings(
        self,
        standard_cost_tokens: int,
        tasks_per_day: int,
        days_per_month: int = 30
    ) -> Dict[str, Any]:
        """
        Estimate cost savings from using Batch API.

        Args:
            standard_cost_tokens: Standard API token cost per task
            tasks_per_day: Number of tasks per day
            days_per_month: Days to calculate for (default 30)

        Returns:
            Dict with savings estimates
        """
        # Batch API is 50% cheaper
        batch_cost_tokens = self.calculate_batch_cost(standard_cost_tokens)
        savings_per_task = standard_cost_tokens - batch_cost_tokens

        daily_savings = savings_per_task * tasks_per_day
        monthly_savings = daily_savings * days_per_month

        # Estimate USD cost (approximate Claude pricing)
        # Average: ~$0.50 per 1M input tokens for Haiku
        savings_usd = (monthly_savings / 1_000_000) * 0.50

        return {
            "standard_tokens_per_task": standard_cost_tokens,
            "batch_tokens_per_task": batch_cost_tokens,
            "savings_per_task": savings_per_task,
            "daily_token_savings": daily_savings,
            "monthly_token_savings": monthly_savings,
            "estimated_monthly_savings_usd": savings_usd,
            "savings_percentage": 50
        }
