"""Orchestrator-Worker subagent pattern.

Based on plan-v7.md:
- Orchestrator: Routes complex tasks to specialized workers
- Worker: Executes specific skill with focused context
- Allows parallel execution of independent subtasks
- Aggregates results back to main agent

This pattern enables:
- Better token efficiency (workers have minimal context)
- Parallel execution of independent tasks
- Skill specialization
- Clean separation of concerns
"""

from typing import Dict, Any, List, Optional
import asyncio


class Orchestrator:
    """Orchestrates complex tasks by delegating to workers."""

    def __init__(self):
        """Initialize orchestrator."""
        self.active_workers = {}

    def route_to_skill(self, task: Dict[str, Any]) -> Optional[str]:
        """Route task to appropriate skill.

        Args:
            task: Task dict with type and parameters

        Returns:
            Skill name to use, or None if no match
        """
        task_type = task.get("type", "")

        # Simple routing rules (in production, this would be more sophisticated)
        routing_map = {
            "instagram_post": "instagram-content-creator",
            "blog_post": "blog-writer",
            "research": "web-researcher",
            "email": "email-composer",
            "analysis": "data-analyzer",
        }

        return routing_map.get(task_type)

    def create_worker(
        self,
        task: Dict[str, Any],
        skill_name: Optional[str] = None,
    ) -> "Worker":
        """Create a worker for a task.

        Args:
            task: Task to execute
            skill_name: Optional skill to use (auto-route if not provided)

        Returns:
            Worker instance
        """
        if skill_name is None:
            skill_name = self.route_to_skill(task)

        if skill_name is None:
            skill_name = "general-purpose"

        worker_id = f"worker_{len(self.active_workers)}"

        worker = Worker(
            worker_id=worker_id,
            skill_name=skill_name,
            context={
                "task": task,
                "orchestrator_id": id(self),
            },
        )

        self.active_workers[worker_id] = worker
        return worker

    async def execute_parallel(
        self, tasks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute multiple tasks in parallel.

        Args:
            tasks: List of tasks to execute

        Returns:
            List of results (in same order as tasks)
        """
        # Create workers for each task
        workers = [self.create_worker(task) for task in tasks]

        # Execute all workers in parallel
        results = await asyncio.gather(
            *[worker.execute(task) for worker, task in zip(workers, tasks)],
            return_exceptions=True,
        )

        # Clean up workers
        for worker in workers:
            if worker.worker_id in self.active_workers:
                del self.active_workers[worker.worker_id]

        return results

    def aggregate_results(
        self, results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Aggregate results from multiple workers.

        Args:
            results: List of worker results

        Returns:
            Aggregated result
        """
        # Simple aggregation - combine all results
        aggregated = {
            "success": all(r.get("success", False) for r in results if isinstance(r, dict)),
            "results": results,
            "count": len(results),
            "summary": self._create_summary(results),
        }

        return aggregated

    def _create_summary(self, results: List[Dict[str, Any]]) -> str:
        """Create summary of results.

        Args:
            results: List of results

        Returns:
            Summary string
        """
        successful = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        total = len(results)

        return f"Completed {successful}/{total} tasks successfully"


class Worker:
    """Worker that executes a specific skill."""

    def __init__(
        self,
        worker_id: str,
        skill_name: str,
        context: Dict[str, Any],
    ):
        """Initialize worker.

        Args:
            worker_id: Unique worker identifier
            skill_name: Name of skill to execute
            context: Execution context (minimal, focused)
        """
        self.worker_id = worker_id
        self.skill_name = skill_name
        self.context = context

        # Load skill
        from museon.agent.skills import SkillLoader

        self.skill_loader = SkillLoader()
        self.skill = None

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the task using loaded skill.

        Args:
            task: Task parameters

        Returns:
            Execution result
        """
        # Load skill if not already loaded
        if self.skill is None:
            self.skill = self.load_skill(self.skill_name)

            if self.skill is None:
                return {
                    "success": False,
                    "error": f"Skill '{self.skill_name}' not found",
                    "worker_id": self.worker_id,
                }

        # Execute skill
        try:
            result = await self.execute_skill(task)
            return {
                "success": True,
                "result": result,
                "worker_id": self.worker_id,
                "skill_used": self.skill_name,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "worker_id": self.worker_id,
            }

    def load_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Load skill definition.

        Args:
            skill_name: Name of skill

        Returns:
            Skill dict or None
        """
        return self.skill_loader.load_skill(skill_name)

    async def execute_skill(self, task: Dict[str, Any]) -> Any:
        """Execute skill with task parameters.

        This is a simplified version. In production:
        - Load skill's specific prompt
        - Create minimal context (token efficient)
        - Execute with skill's required tools
        - Return structured result

        Args:
            task: Task parameters

        Returns:
            Skill execution result
        """
        # Placeholder implementation
        # Real implementation would:
        # 1. Load skill's BRIEF.md for prompt
        # 2. Create focused system prompt
        # 3. Execute with LLM
        # 4. Return result

        return {
            "task_type": task.get("type"),
            "skill": self.skill_name,
            "result": "Executed successfully",
        }


class SubagentPool:
    """Pool of subagents for reuse."""

    def __init__(self, max_workers: int = 5):
        """Initialize subagent pool.

        Args:
            max_workers: Maximum concurrent workers
        """
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)

    async def execute_with_limit(
        self, worker: Worker, task: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute worker with concurrency limit.

        Args:
            worker: Worker instance
            task: Task to execute

        Returns:
            Execution result
        """
        async with self.semaphore:
            return await worker.execute(task)
