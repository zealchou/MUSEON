"""
Token Self-Optimization Module

Observes routing patterns and suggests optimizations:
1. Observe: Analyze which tasks route to Haiku vs Sonnet
2. Suggest: Identify tasks that could be downgraded safely
3. Verify: Test downgrade quality (allow max 5-point drop)
4. Rollback: Automatically revert if quality drops too much
"""
import logging
from typing import Dict, Any, List, Optional
from statistics import mean

logger = logging.getLogger(__name__)


class TokenOptimizer:
    """Handles token usage optimization through routing analysis."""

    def __init__(self, quality_threshold: int = 5):
        """
        Initialize token optimizer.

        Args:
            quality_threshold: Maximum allowed quality drop (default 5 points)
        """
        self.quality_threshold = quality_threshold

    async def observe_patterns(self, routing_stats: Dict[str, Any]) -> Dict[str, Any]:
        """
        Observe routing patterns from historical data.

        Args:
            routing_stats: Dict containing routing statistics
                {
                    "haiku": {"count": N, "success_rate": X, "avg_quality": Y},
                    "sonnet": {...},
                    "tasks": [{"type": "...", "model": "...", "quality": N, "tokens": N}]
                }

        Returns:
            Dict with pattern analysis
        """
        logger.info("Observing routing patterns")

        patterns = {
            "haiku": routing_stats.get("haiku", {}),
            "sonnet": routing_stats.get("sonnet", {}),
            "task_types": {}
        }

        # Analyze by task type
        tasks = routing_stats.get("tasks", [])
        for task in tasks:
            task_type = task.get("type", "unknown")

            if task_type not in patterns["task_types"]:
                patterns["task_types"][task_type] = {
                    "haiku": [],
                    "sonnet": []
                }

            model = task.get("model", "unknown")
            if model in ["haiku", "sonnet"]:
                patterns["task_types"][task_type][model].append({
                    "quality": task.get("quality", 0),
                    "tokens": task.get("tokens", 0)
                })

        # Calculate averages per task type
        for task_type, models in patterns["task_types"].items():
            for model in ["haiku", "sonnet"]:
                if models[model]:
                    models[f"{model}_avg_quality"] = mean(
                        t["quality"] for t in models[model]
                    )
                    models[f"{model}_avg_tokens"] = mean(
                        t["tokens"] for t in models[model]
                    )
                    models[f"{model}_count"] = len(models[model])

        return patterns

    async def suggest_downgrade(self, routing_stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Suggest tasks that could be downgraded from Sonnet to Haiku.

        Criteria for downgrade suggestion:
        - Task is currently using Sonnet
        - Similar tasks on Haiku have comparable quality (within threshold)
        - Token savings are significant (>100 tokens)

        Args:
            routing_stats: Routing statistics

        Returns:
            List of downgrade suggestions
        """
        logger.info("Analyzing downgrade opportunities")

        suggestions = []
        tasks = routing_stats.get("tasks", [])

        # Group tasks by type
        task_groups = {}
        for task in tasks:
            task_type = task.get("type", "unknown")
            if task_type not in task_groups:
                task_groups[task_type] = {"haiku": [], "sonnet": []}

            model = task.get("model")
            if model in ["haiku", "sonnet"]:
                task_groups[task_type][model].append(task)

        # Analyze each task type
        for task_type, models in task_groups.items():
            haiku_tasks = models.get("haiku", [])
            sonnet_tasks = models.get("sonnet", [])

            # Skip if no comparison data
            if not haiku_tasks or not sonnet_tasks:
                continue

            # Calculate averages
            haiku_avg_quality = mean(t.get("quality", 0) for t in haiku_tasks)
            sonnet_avg_quality = mean(t.get("quality", 0) for t in sonnet_tasks)
            sonnet_avg_tokens = mean(t.get("tokens", 0) for t in sonnet_tasks)
            haiku_avg_tokens = mean(t.get("tokens", 0) for t in haiku_tasks)

            quality_diff = sonnet_avg_quality - haiku_avg_quality
            token_savings = sonnet_avg_tokens - haiku_avg_tokens

            # Check if downgrade is viable
            if quality_diff <= self.quality_threshold and token_savings > 100:
                suggestions.append({
                    "task_type": task_type,
                    "current_model": "sonnet",
                    "suggested_model": "haiku",
                    "quality_diff": quality_diff,
                    "tokens_saved": int(token_savings),
                    "confidence": "high" if quality_diff <= 2 else "medium",
                    "sonnet_count": len(sonnet_tasks)
                })

        logger.info(f"Found {len(suggestions)} downgrade opportunities")
        return suggestions

    async def verify_quality(
        self,
        task_type: str,
        original_quality: float,
        new_quality: float,
        threshold: Optional[int] = None
    ) -> bool:
        """
        Verify if quality after downgrade is acceptable.

        Args:
            task_type: Type of task
            original_quality: Original quality score
            new_quality: New quality score after downgrade
            threshold: Max allowed drop (uses instance threshold if not provided)

        Returns:
            True if quality is acceptable, False otherwise
        """
        if threshold is None:
            threshold = self.quality_threshold

        quality_drop = original_quality - new_quality

        acceptable = quality_drop <= threshold

        logger.info(
            f"Quality verification for {task_type}: "
            f"drop={quality_drop:.1f}, threshold={threshold}, "
            f"acceptable={acceptable}"
        )

        return acceptable

    async def calculate_potential_savings(
        self,
        suggestions: List[Dict[str, Any]],
        daily_task_frequency: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Calculate potential token savings from suggestions.

        Args:
            suggestions: List of downgrade suggestions
            daily_task_frequency: Optional dict of task type -> daily count

        Returns:
            Dict with savings estimates
        """
        if not daily_task_frequency:
            # Use suggestion counts as proxy
            daily_task_frequency = {
                s["task_type"]: s.get("sonnet_count", 1)
                for s in suggestions
            }

        total_daily_savings = 0
        breakdown = []

        for suggestion in suggestions:
            task_type = suggestion["task_type"]
            tokens_per_task = suggestion["tokens_saved"]
            daily_count = daily_task_frequency.get(task_type, 1)

            daily_savings = tokens_per_task * daily_count
            total_daily_savings += daily_savings

            breakdown.append({
                "task_type": task_type,
                "tokens_per_task": tokens_per_task,
                "daily_count": daily_count,
                "daily_savings": daily_savings
            })

        # Calculate costs (approximate Claude pricing)
        # Haiku: $0.25/$1.25 per MTok, Sonnet: $3/$15 per MTok
        # Average: Haiku ~$0.75/MTok, Sonnet ~$9/MTok
        # Savings rate: ~$8.25 per 1M tokens
        cost_savings_usd = (total_daily_savings / 1_000_000) * 8.25

        return {
            "total_daily_savings_tokens": total_daily_savings,
            "total_weekly_savings_tokens": total_daily_savings * 7,
            "total_monthly_savings_tokens": total_daily_savings * 30,
            "estimated_monthly_savings_usd": cost_savings_usd * 30,
            "breakdown": breakdown
        }

    async def apply_optimization(
        self,
        suggestion: Dict[str, Any],
        router_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply an optimization suggestion to router config.

        This would update the router rules to downgrade the specified task type.

        Args:
            suggestion: Downgrade suggestion
            router_config: Current router configuration

        Returns:
            Updated router config
        """
        task_type = suggestion["task_type"]
        new_model = suggestion["suggested_model"]

        logger.info(f"Applying optimization: {task_type} -> {new_model}")

        # Update router config (implementation depends on router structure)
        if "task_rules" not in router_config:
            router_config["task_rules"] = {}

        router_config["task_rules"][task_type] = {
            "model": new_model,
            "reason": "optimized_by_nightly_job",
            "original_model": suggestion["current_model"],
            "applied_at": __import__('datetime').datetime.now().isoformat()
        }

        return router_config

    async def rollback_optimization(
        self,
        task_type: str,
        router_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Rollback an optimization if quality dropped too much.

        Args:
            task_type: Task type to rollback
            router_config: Current router configuration

        Returns:
            Updated router config
        """
        logger.warning(f"Rolling back optimization for {task_type}")

        if "task_rules" in router_config and task_type in router_config["task_rules"]:
            rule = router_config["task_rules"][task_type]

            # Restore original model
            original_model = rule.get("original_model", "sonnet")
            router_config["task_rules"][task_type] = {
                "model": original_model,
                "reason": "rollback_quality_drop",
                "rolled_back_at": __import__('datetime').datetime.now().isoformat()
            }

        return router_config
