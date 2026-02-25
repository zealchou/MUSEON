"""Budget Monitor - Track and enforce token usage limits."""

import time
from typing import Dict, List
from datetime import datetime, timedelta


class BudgetMonitor:
    """
    Monitor token usage and enforce daily budget limits.

    Features:
    - Track input and output tokens separately
    - Daily budget enforcement
    - Warning thresholds
    - Usage statistics
    """

    def __init__(
        self,
        daily_limit: int = 200000,
        warning_threshold: float = 0.8,
    ) -> None:
        """
        Initialize Budget Monitor.

        Args:
            daily_limit: Daily token limit
            warning_threshold: Percentage (0-1) at which to warn
        """
        self._daily_limit = daily_limit
        self._warning_threshold = warning_threshold

        # Track usage by day
        self._usage_log: List[Dict[str, any]] = []
        self._today = datetime.now().date()
        self._daily_usage = 0

    def track_usage(self, input_tokens: int, output_tokens: int) -> None:
        """
        Track token usage.

        Args:
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
        """
        # Check if we've rolled over to a new day
        today = datetime.now().date()
        if today != self._today:
            self._today = today
            self._daily_usage = 0

        total_tokens = input_tokens + output_tokens
        self._daily_usage += total_tokens

        # Log the usage
        self._usage_log.append(
            {
                "timestamp": datetime.now(),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }
        )

    def get_total_usage(self) -> int:
        """
        Get total tokens used today.

        Returns:
            Total token count
        """
        return self._daily_usage

    def get_usage_percentage(self) -> float:
        """
        Get usage as percentage of daily limit.

        Returns:
            Percentage (0-100)
        """
        return (self._daily_usage / self._daily_limit) * 100

    def check_budget(self, required_tokens: int = 0) -> bool:
        """
        Check if we're within budget.

        Args:
            required_tokens: Tokens needed for next request

        Returns:
            True if within budget, False if exceeded
        """
        projected_usage = self._daily_usage + required_tokens
        return projected_usage <= self._daily_limit

    def should_warn(self) -> bool:
        """
        Check if we should warn about approaching budget limit.

        Returns:
            True if usage exceeds warning threshold
        """
        usage_percentage = self._daily_usage / self._daily_limit
        return usage_percentage >= self._warning_threshold

    def get_remaining_budget(self) -> int:
        """
        Get remaining tokens in budget.

        Returns:
            Number of tokens remaining
        """
        return max(0, self._daily_limit - self._daily_usage)

    def get_usage_stats(self) -> Dict[str, any]:
        """
        Get detailed usage statistics.

        Returns:
            Dict with usage statistics
        """
        return {
            "daily_limit": self._daily_limit,
            "used": self._daily_usage,
            "remaining": self.get_remaining_budget(),
            "percentage": self.get_usage_percentage(),
            "should_warn": self.should_warn(),
        }
