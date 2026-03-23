"""Budget Monitor - Track and enforce token usage limits with disk persistence."""

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, date

logger = logging.getLogger(__name__)


class BudgetMonitor:
    """
    Monitor token usage and enforce daily budget limits.

    Features:
    - Track input and output tokens separately
    - Per-model usage tracking (Sonnet / Haiku)
    - Per-model cost estimation with accurate pricing
    - Daily budget enforcement
    - Warning thresholds
    - Usage statistics
    - **Disk persistence**: survives Gateway restarts
    - **Monthly cumulative**: track spending across the month
    """

    # Model pricing (USD per 1M tokens) — 2026-03 Claude 4 系列
    MODEL_PRICING = {
        "claude-opus-4-6": {"input": 15.0, "output": 75.0, "label": "Opus"},
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0, "label": "Sonnet"},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0, "label": "Haiku"},
        # 舊版 fallback
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0, "label": "Sonnet"},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25, "label": "Haiku"},
    }

    def __init__(
        self,
        daily_limit: int = 0,
        warning_threshold: float = 0.8,
        data_dir: Optional[str] = None,
    ) -> None:
        """
        Initialize Budget Monitor.

        Args:
            daily_limit: Daily token limit (0 = read from env MUSEON_DAILY_TOKEN_LIMIT, default 200000)
            warning_threshold: Percentage (0-1) at which to warn
            data_dir: Path to data directory for persistence (e.g., ~/MUSEON 正式版/MUSEON/data)
        """
        if daily_limit <= 0:
            env_limit = os.environ.get("MUSEON_DAILY_TOKEN_LIMIT", "200000")
            try:
                daily_limit = int(env_limit)
            except (ValueError, TypeError):
                daily_limit = 200000
        self._daily_limit = daily_limit
        self._warning_threshold = warning_threshold

        # Persistence directory
        self._budget_dir: Optional[Path] = None
        if data_dir:
            self._budget_dir = Path(data_dir) / "_system" / "budget"
            try:
                self._budget_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(f"Cannot create budget dir: {e}")
                self._budget_dir = None

        # Thread safety (P2: brain asyncio + nightly thread 並發保護)
        self._lock = threading.Lock()

        # Track usage by day
        self._today = datetime.now().date()
        self._daily_usage = 0
        self._input_tokens = 0
        self._output_tokens = 0

        # Per-model tracking: { "opus": {...}, "sonnet": {...}, "haiku": {...} }
        self._model_usage: Dict[str, Dict[str, int]] = {
            "opus": {"input": 0, "output": 0, "calls": 0},
            "sonnet": {"input": 0, "output": 0, "calls": 0},
            "haiku": {"input": 0, "output": 0, "calls": 0},
        }

        # Load persisted data for today
        self._load_today()

    # ── Persistence ──────────────────────────────────────

    def _month_file(self, d: Optional[date] = None) -> Optional[Path]:
        """Get the monthly usage file path: usage_YYYY-MM.json."""
        if not self._budget_dir:
            return None
        d = d or self._today
        return self._budget_dir / f"usage_{d.strftime('%Y-%m')}.json"

    def _load_month_data(self, d: Optional[date] = None) -> Dict[str, Any]:
        """Load a month's usage data from disk."""
        fp = self._month_file(d)
        if not fp or not fp.exists():
            return {"days": {}, "monthly_totals": self._empty_totals()}
        try:
            raw = fp.read_text(encoding="utf-8")
            data = json.loads(raw)
            # Ensure structure
            if "days" not in data:
                data["days"] = {}
            if "monthly_totals" not in data:
                data["monthly_totals"] = self._empty_totals()
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load budget data from {fp}: {e}")
            return {"days": {}, "monthly_totals": self._empty_totals()}

    def _save_month_data(self, data: Dict[str, Any], d: Optional[date] = None) -> None:
        """Save a month's usage data to disk (P2: atomic write via tmp→rename)."""
        fp = self._month_file(d)
        if not fp:
            return
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2)
            # 原子寫入：tmp 檔案 → rename（同目錄內 rename 是原子操作）
            fd, tmp_path = tempfile.mkstemp(
                dir=str(fp.parent), suffix=".tmp", prefix=".budget_"
            )
            fd_closed = False
            try:
                os.write(fd, content.encode("utf-8"))
                os.fsync(fd)
                os.close(fd)
                fd_closed = True
                os.replace(tmp_path, str(fp))
            except Exception:
                if not fd_closed:
                    os.close(fd)
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except OSError as e:
            logger.warning(f"Failed to save budget data to {fp}: {e}")

    def _empty_totals(self) -> Dict[str, Any]:
        """Empty totals structure."""
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "models": {
                "opus": {"input": 0, "output": 0, "calls": 0},
                "sonnet": {"input": 0, "output": 0, "calls": 0},
                "haiku": {"input": 0, "output": 0, "calls": 0},
            },
        }

    def _empty_day_entry(self) -> Dict[str, Any]:
        """Empty day entry structure."""
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "models": {
                "opus": {"input": 0, "output": 0, "calls": 0},
                "sonnet": {"input": 0, "output": 0, "calls": 0},
                "haiku": {"input": 0, "output": 0, "calls": 0},
            },
        }

    def _load_today(self) -> None:
        """Load today's usage from disk (called on init and day change)."""
        data = self._load_month_data()
        today_key = self._today.isoformat()
        day_data = data.get("days", {}).get(today_key, None)
        if day_data:
            self._input_tokens = day_data.get("input_tokens", 0)
            self._output_tokens = day_data.get("output_tokens", 0)
            self._daily_usage = day_data.get("total_tokens", 0)
            models = day_data.get("models", {})
            for cat in ("opus", "sonnet", "haiku"):
                m = models.get(cat, {})
                self._model_usage[cat] = {
                    "input": m.get("input", 0),
                    "output": m.get("output", 0),
                    "calls": m.get("calls", 0),
                }
        else:
            # No data for today yet — start fresh
            self._daily_usage = 0
            self._input_tokens = 0
            self._output_tokens = 0
            self._model_usage = {
                "opus": {"input": 0, "output": 0, "calls": 0},
                "sonnet": {"input": 0, "output": 0, "calls": 0},
                "haiku": {"input": 0, "output": 0, "calls": 0},
            }

    def _persist_today(self) -> None:
        """Persist today's usage to disk and update monthly totals."""
        data = self._load_month_data()
        today_key = self._today.isoformat()

        # Save today's entry (P0 fix: 加入 opus — v4 三層路由)
        data["days"][today_key] = {
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "total_tokens": self._daily_usage,
            "models": {
                cat: dict(self._model_usage[cat]) for cat in ("opus", "sonnet", "haiku")
            },
        }

        # Recalculate monthly totals from all days
        totals = self._empty_totals()
        for _day_key, day_data in data["days"].items():
            totals["input_tokens"] += day_data.get("input_tokens", 0)
            totals["output_tokens"] += day_data.get("output_tokens", 0)
            totals["total_tokens"] += day_data.get("total_tokens", 0)
            for cat in ("opus", "sonnet", "haiku"):
                m = day_data.get("models", {}).get(cat, {})
                totals["models"][cat]["input"] += m.get("input", 0)
                totals["models"][cat]["output"] += m.get("output", 0)
                totals["models"][cat]["calls"] += m.get("calls", 0)

        # Calculate monthly cost
        totals["estimated_cost_usd"] = round(
            self._calc_cost_from_usage(totals["models"]), 4
        )

        data["monthly_totals"] = totals
        self._save_month_data(data)

    # ── Day change ───────────────────────────────────────

    def _reset_if_new_day(self) -> None:
        """Reset counters if day has changed, loading persisted data for new day."""
        today = datetime.now().date()
        if today != self._today:
            self._today = today
            self._load_today()

    # ── Model classification & pricing ───────────────────

    def _classify_model(self, model: Optional[str]) -> str:
        """Classify a model ID into 'opus', 'sonnet', or 'haiku'."""
        if not model:
            return "opus"  # 預設
        m = model.lower()
        if "haiku" in m:
            return "haiku"
        if "opus" in m:
            return "opus"
        return "sonnet"

    def _get_pricing(self, model: Optional[str]) -> Dict[str, float]:
        """Get pricing for a model."""
        if model and model in self.MODEL_PRICING:
            return self.MODEL_PRICING[model]
        # Fallback — Sonnet 級定價
        return {"input": 3.0, "output": 15.0, "label": "Sonnet"}

    def _calc_model_cost(self, category: str) -> float:
        """Calculate cost for a model category (today only)."""
        usage = self._model_usage.get(category, {"input": 0, "output": 0})
        pricing = {
            "opus": (15.0, 75.0),
            "sonnet": (3.0, 15.0),
            "haiku": (0.80, 4.0),
        }
        inp_rate, out_rate = pricing.get(category, (3.0, 15.0))
        return (
            (usage["input"] / 1_000_000) * inp_rate
            + (usage["output"] / 1_000_000) * out_rate
        )

    def _calc_cost_from_usage(self, models: Dict[str, Dict[str, int]]) -> float:
        """Calculate cost from a models dict (for monthly totals)."""
        pricing = {
            "opus": (15.0, 75.0),
            "sonnet": (3.0, 15.0),
            "haiku": (0.80, 4.0),
        }
        cost = 0.0
        for cat in ("opus", "sonnet", "haiku"):
            m = models.get(cat, {"input": 0, "output": 0})
            inp_rate, out_rate = pricing.get(cat, (3.0, 15.0))
            cost += (m.get("input", 0) / 1_000_000) * inp_rate
            cost += (m.get("output", 0) / 1_000_000) * out_rate
        return cost

    # ── Usage tracking ───────────────────────────────────

    def track_usage(
        self, input_tokens: int, output_tokens: int, model: Optional[str] = None
    ) -> None:
        """
        Track token usage and persist to disk (P2: thread-safe).

        Args:
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens used
            model: Model ID (e.g., "claude-sonnet-4-20250514")
        """
        with self._lock:
            self._reset_if_new_day()

            total_tokens = input_tokens + output_tokens
            self._daily_usage += total_tokens
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens

            # Per-model tracking
            category = self._classify_model(model)
            self._model_usage[category]["input"] += input_tokens
            self._model_usage[category]["output"] += output_tokens
            self._model_usage[category]["calls"] += 1

            # Persist to disk
            self._persist_today()

    # ── Query methods ────────────────────────────────────

    def get_total_usage(self) -> int:
        """Get total tokens used today."""
        return self._daily_usage

    def get_usage_percentage(self) -> float:
        """Get usage as percentage of daily limit."""
        if self._daily_limit <= 0:
            return 0.0
        return (self._daily_usage / self._daily_limit) * 100

    def check_budget(self, required_tokens: int = 0) -> bool:
        """Check if we're within budget."""
        projected_usage = self._daily_usage + required_tokens
        return projected_usage <= self._daily_limit

    def should_warn(self) -> bool:
        """Check if we should warn about approaching budget limit."""
        if self._daily_limit <= 0:
            return False
        usage_percentage = self._daily_usage / self._daily_limit
        return usage_percentage >= self._warning_threshold

    def get_remaining_budget(self) -> int:
        """Get remaining tokens in budget."""
        return max(0, self._daily_limit - self._daily_usage)

    def set_daily_limit(self, new_limit: int) -> None:
        """Set new daily token limit.

        Also persists to MUSEON_DAILY_TOKEN_LIMIT env var.

        Args:
            new_limit: New daily token limit (must be > 0)
        """
        if new_limit <= 0:
            raise ValueError("Daily limit must be > 0")
        self._daily_limit = new_limit
        os.environ["MUSEON_DAILY_TOKEN_LIMIT"] = str(new_limit)

    # ── Statistics ───────────────────────────────────────

    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get detailed usage statistics with per-model breakdown + monthly cumulative.

        Returns:
            Dict with daily usage, monthly totals, and model-level detail
        """
        self._reset_if_new_day()

        opus_cost = self._calc_model_cost("opus")
        sonnet_cost = self._calc_model_cost("sonnet")
        haiku_cost = self._calc_model_cost("haiku")
        total_cost = opus_cost + sonnet_cost + haiku_cost

        # Load monthly cumulative
        month_data = self._load_month_data()
        monthly = month_data.get("monthly_totals", self._empty_totals())

        def _model_stats(cat: str, cost: float) -> Dict[str, Any]:
            u = self._model_usage.get(cat, {"input": 0, "output": 0, "calls": 0})
            return {
                "input_tokens": u["input"],
                "output_tokens": u["output"],
                "total_tokens": u["input"] + u["output"],
                "calls": u["calls"],
                "cost_usd": round(cost, 4),
            }

        return {
            "daily_limit": self._daily_limit,
            "used": self._daily_usage,
            "remaining": self.get_remaining_budget(),
            "percentage": self.get_usage_percentage(),
            "should_warn": self.should_warn(),
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "estimated_cost_usd": round(total_cost, 4),
            # Per-model breakdown (today)
            "models": {
                "opus": _model_stats("opus", opus_cost),
                "sonnet": _model_stats("sonnet", sonnet_cost),
                "haiku": _model_stats("haiku", haiku_cost),
            },
            # Monthly cumulative
            "monthly": {
                "month": self._today.strftime("%Y-%m"),
                "total_tokens": monthly.get("total_tokens", 0),
                "input_tokens": monthly.get("input_tokens", 0),
                "output_tokens": monthly.get("output_tokens", 0),
                "estimated_cost_usd": monthly.get("estimated_cost_usd", 0.0),
                "days_tracked": len(month_data.get("days", {})),
                "models": monthly.get("models", self._empty_totals()["models"]),
            },
        }

    def get_monthly_history(self, months: int = 3) -> List[Dict[str, Any]]:
        """Get monthly usage history for the last N months.

        Args:
            months: Number of months to look back (default 3)

        Returns:
            List of monthly summaries, most recent first
        """
        history = []
        today = self._today
        for i in range(months):
            # Calculate the month
            year = today.year
            month = today.month - i
            while month <= 0:
                month += 12
                year -= 1
            d = date(year, month, 1)
            data = self._load_month_data(d)
            totals = data.get("monthly_totals", self._empty_totals())
            history.append({
                "month": d.strftime("%Y-%m"),
                "total_tokens": totals.get("total_tokens", 0),
                "estimated_cost_usd": totals.get("estimated_cost_usd", 0.0),
                "days_tracked": len(data.get("days", {})),
            })
        return history
