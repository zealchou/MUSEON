"""
Nightly Job - Main Workflow

Runs at 3AM daily:
1. Memory fusion across four channels
2. Token optimization analysis
3. Self-forging trigger checks
4. Security health report generation
"""
import asyncio
import logging
from datetime import datetime, time
from typing import Dict, Any, List
from pathlib import Path

from .fusion import MemoryFusion
from .optimize import TokenOptimizer
from .forge import ForgeEngine
from .batch import BatchProcessor

logger = logging.getLogger(__name__)


def get_schedule_time() -> time:
    """Get the scheduled time for nightly job (3:00 AM)."""
    return time(hour=3, minute=0)


class NightlyJob:
    """Main nightly job orchestrator."""

    def __init__(
        self,
        memory_store,
        llm_client,
        data_dir: Path = None
    ):
        """
        Initialize nightly job.

        Args:
            memory_store: Memory store instance
            llm_client: LLM client for processing
            data_dir: Data directory for logs and reports
        """
        self.memory_store = memory_store
        self.llm_client = llm_client
        self.data_dir = data_dir or Path.home() / ".museclaw" / "data"

        # Initialize components
        self.fusion = MemoryFusion(memory_store, llm_client)
        self.optimizer = TokenOptimizer()
        self.forge_engine = ForgeEngine()
        self.batch_processor = BatchProcessor(llm_client)

    async def run(self) -> Dict[str, Any]:
        """
        Execute complete nightly job workflow.

        Returns:
            Dict with status and results of all tasks
        """
        logger.info("Starting nightly job")
        start_time = datetime.now()

        results = {
            "status": "completed",
            "start_time": start_time.isoformat(),
            "tasks": {},
            "errors": []
        }

        # Task 1: Memory Fusion
        try:
            logger.info("Running memory fusion")
            fusion_result = await self._run_memory_fusion()
            results["tasks"]["fusion"] = fusion_result
        except Exception as e:
            logger.error(f"Memory fusion failed: {e}")
            results["errors"].append({"task": "fusion", "error": str(e)})
            results["tasks"]["fusion"] = {"status": "failed", "error": str(e)}

        # Task 2: Token Optimization
        try:
            logger.info("Running token optimization")
            optimization_result = await self._run_token_optimization()
            results["tasks"]["optimization"] = optimization_result
        except Exception as e:
            logger.error(f"Token optimization failed: {e}")
            results["errors"].append({"task": "optimization", "error": str(e)})
            results["tasks"]["optimization"] = {"status": "failed", "error": str(e)}

        # Task 3: Self-Forging Checks
        try:
            logger.info("Running self-forging checks")
            forge_result = await self._run_forge_checks()
            results["tasks"]["forge_check"] = forge_result
        except Exception as e:
            logger.error(f"Forge check failed: {e}")
            results["errors"].append({"task": "forge_check", "error": str(e)})
            results["tasks"]["forge_check"] = {"status": "failed", "error": str(e)}

        # Task 4: Health Report
        try:
            logger.info("Generating health report")
            health_report = await self._generate_health_report(results)
            results["health_report"] = health_report
        except Exception as e:
            logger.error(f"Health report generation failed: {e}")
            results["errors"].append({"task": "health_report", "error": str(e)})

        # Determine final status
        if results["errors"]:
            results["status"] = "partial_success" if any(
                task.get("status") == "completed"
                for task in results["tasks"].values()
            ) else "failed"

        end_time = datetime.now()
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()

        logger.info(f"Nightly job completed: {results['status']}")
        return results

    async def _run_memory_fusion(self) -> Dict[str, Any]:
        """Run memory fusion for yesterday's data."""
        from datetime import timedelta
        yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
        result = await self.fusion.fuse_daily_memories(date=yesterday)
        return result

    async def _run_token_optimization(self) -> Dict[str, Any]:
        """Run token optimization analysis."""
        # Load past 7 days routing stats
        routing_stats = await self._load_routing_stats(days=7)

        # Observe patterns
        patterns = await self.optimizer.observe_patterns(routing_stats)

        # Suggest downgrades
        suggestions = await self.optimizer.suggest_downgrade(routing_stats)

        return {
            "status": "completed",
            "patterns": patterns,
            "suggestions": suggestions,
            "potential_savings": sum(s.get("tokens_saved", 0) for s in suggestions)
        }

    async def _run_forge_checks(self) -> Dict[str, Any]:
        """Run all three types of self-forging checks."""
        # Load necessary data
        quality_history = await self._load_quality_history()
        usage_data = await self._load_usage_data()
        skill_health = await self._load_skill_health()

        # Check all trigger types
        quality_triggers = await self.forge_engine.check_quality_triggers(quality_history)
        usage_triggers = await self.forge_engine.check_usage_triggers(usage_data)
        time_scan = await self.forge_engine.time_driven_scan(skill_health)

        return {
            "status": "completed",
            "quality_triggers": quality_triggers,
            "usage_triggers": usage_triggers,
            "time_scan": time_scan,
            "total_triggers": len(quality_triggers) + len(usage_triggers)
        }

    async def _generate_health_report(self, nightly_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate daily security and health report.

        Args:
            nightly_results: Results from all nightly tasks

        Returns:
            Health report dict
        """
        # Load token usage stats
        token_stats = await self._load_token_stats()

        # Load memory status
        memory_status = await self._get_memory_status()

        # Load security summary (from audit logs)
        security_summary = await self._get_security_summary()

        return {
            "date": datetime.now().date().isoformat(),
            "token_usage": token_stats,
            "memory_status": memory_status,
            "security_summary": security_summary,
            "nightly_tasks": {
                task: result.get("status")
                for task, result in nightly_results.get("tasks", {}).items()
            },
            "recommendations": self._generate_recommendations(nightly_results)
        }

    async def _load_routing_stats(self, days: int = 7) -> Dict[str, Any]:
        """Load routing statistics from past N days."""
        # Implementation would load from actual stats files
        # For now, return mock structure
        return {
            "haiku": {"count": 0, "success_rate": 0.0, "avg_quality": 0},
            "sonnet": {"count": 0, "success_rate": 0.0, "avg_quality": 0},
            "tasks": []
        }

    async def _load_quality_history(self) -> Dict[str, List[int]]:
        """Load quality score history for skills."""
        # Implementation would load from actual quality tracking
        return {}

    async def _load_usage_data(self) -> Dict[str, Any]:
        """Load usage patterns data."""
        # Implementation would load from actual usage logs
        return {"tasks": []}

    async def _load_skill_health(self) -> Dict[str, Any]:
        """Load skill health metrics."""
        # Implementation would load from actual skill tracking
        return {"skills": []}

    async def _load_token_stats(self) -> Dict[str, Any]:
        """Load token usage statistics."""
        return {
            "daily_usage": 0,
            "weekly_usage": 0,
            "budget_remaining": 0,
            "cost_usd": 0.0
        }

    async def _get_memory_status(self) -> Dict[str, Any]:
        """Get current memory system status."""
        return {
            "total_memories": 0,
            "channels": {
                "meta_thinking": 0,
                "event": 0,
                "outcome": 0,
                "user_reaction": 0
            },
            "last_fusion": None
        }

    async def _get_security_summary(self) -> Dict[str, Any]:
        """Get security audit summary."""
        return {
            "suspicious_inputs": 0,
            "blocked_commands": 0,
            "trust_violations": 0,
            "incidents": []
        }

    def _generate_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on nightly results."""
        recommendations = []

        # Check for forge triggers
        forge_check = results.get("tasks", {}).get("forge_check", {})
        if forge_check.get("total_triggers", 0) > 0:
            recommendations.append(
                f"自鍛造觸發: {forge_check['total_triggers']} 個改良機會待處理"
            )

        # Check for token optimization
        optimization = results.get("tasks", {}).get("optimization", {})
        if optimization.get("potential_savings", 0) > 0:
            recommendations.append(
                f"Token 優化: 可節省 {optimization['potential_savings']} tokens/day"
            )

        # Check for errors
        if results.get("errors"):
            recommendations.append(
                f"錯誤偵測: {len(results['errors'])} 個任務需要檢查"
            )

        return recommendations
