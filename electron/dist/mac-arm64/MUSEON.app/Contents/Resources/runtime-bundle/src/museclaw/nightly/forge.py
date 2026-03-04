"""
Self-Forging Engine - Trigger Detection

Three types of triggers:
1. Quality-driven: Q-Score < 70 for 5 consecutive times
2. Usage-driven: Repeated task (10+ times) without dedicated skill
3. Time-driven: Nightly scan for outdated skills (>30 days unused)

All triggers go through safety guardrails before actual forging.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from statistics import mean

logger = logging.getLogger(__name__)


class ForgeEngine:
    """Handles self-forging trigger detection."""

    def __init__(
        self,
        quality_threshold: int = 70,
        quality_consecutive: int = 5,
        usage_threshold: int = 10,
        outdated_days: int = 30
    ):
        """
        Initialize forge engine.

        Args:
            quality_threshold: Q-Score threshold for quality triggers (default 70)
            quality_consecutive: Number of consecutive low scores needed (default 5)
            usage_threshold: Number of repeated uses to trigger (default 10)
            outdated_days: Days since last use to mark as outdated (default 30)
        """
        self.quality_threshold = quality_threshold
        self.quality_consecutive = quality_consecutive
        self.usage_threshold = usage_threshold
        self.outdated_days = outdated_days

    async def check_quality_triggers(
        self,
        quality_history: Dict[str, List[int]]
    ) -> List[Dict[str, Any]]:
        """
        Check for quality-driven forge triggers.

        Triggers when:
        - Q-Score < threshold for consecutive_count times
        - Boss modification rate > 60% for 7 days
        - Boss says "不是這個意思" > 3 times/day

        Args:
            quality_history: Dict of skill_name -> list of recent Q-scores

        Returns:
            List of quality trigger events
        """
        logger.info("Checking quality-driven forge triggers")

        triggers = []

        for skill_name, scores in quality_history.items():
            if not scores or len(scores) < self.quality_consecutive:
                continue

            # Check last N scores
            recent_scores = scores[-self.quality_consecutive:]

            # All below threshold?
            if all(score < self.quality_threshold for score in recent_scores):
                avg_score = mean(recent_scores)
                triggers.append({
                    "skill": skill_name,
                    "trigger_type": "quality_decline",
                    "recent_scores": recent_scores,
                    "avg_score": avg_score,
                    "threshold": self.quality_threshold,
                    "severity": self._calculate_severity(avg_score),
                    "action": self._suggest_action(avg_score)
                })

        logger.info(f"Found {len(triggers)} quality-driven triggers")
        return triggers

    async def check_usage_triggers(
        self,
        usage_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Check for usage-driven forge triggers.

        Triggers when:
        - Same task type repeated 10+ times without dedicated skill
        - Workflow requires 3+ manual steps repeatedly
        - Boss's questions outside skill coverage for 5+ days

        Args:
            usage_data: Dict with task usage patterns
                {
                    "tasks": [
                        {"type": "...", "has_skill": bool, "count": N},
                        ...
                    ]
                }

        Returns:
            List of usage trigger events
        """
        logger.info("Checking usage-driven forge triggers")

        triggers = []
        tasks = usage_data.get("tasks", [])

        for task in tasks:
            task_type = task.get("type")
            has_skill = task.get("has_skill", False)
            count = task.get("count", 0)

            # Trigger if repeated many times without skill
            if not has_skill and count >= self.usage_threshold:
                triggers.append({
                    "task_type": task_type,
                    "trigger_type": "repeated_manual",
                    "occurrence_count": count,
                    "has_dedicated_skill": has_skill,
                    "threshold": self.usage_threshold,
                    "action": "forge_new_skill",
                    "priority": "high" if count > 20 else "medium"
                })

        logger.info(f"Found {len(triggers)} usage-driven triggers")
        return triggers

    async def time_driven_scan(
        self,
        skill_health: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Time-driven nightly scan for skill health.

        Scans for:
        - Outdated skills (>30 days unused)
        - Skills with outdated knowledge
        - Skill efficiency degradation

        Args:
            skill_health: Dict with skill health metrics
                {
                    "skills": [
                        {"name": "...", "last_used": "...", "days_since": N},
                        ...
                    ]
                }

        Returns:
            Dict with scan results
        """
        logger.info("Running time-driven nightly scan")

        skills = skill_health.get("skills", [])

        outdated_skills = []
        update_candidates = []

        for skill in skills:
            skill_name = skill.get("name")
            days_since = skill.get("days_since", 0)

            # Mark as outdated if not used for long time
            if days_since > self.outdated_days:
                outdated_skills.append({
                    "name": skill_name,
                    "days_since_use": days_since,
                    "last_used": skill.get("last_used"),
                    "action": "archive_or_update",
                    "urgency": "high" if days_since > 60 else "low"
                })

            # Check if needs knowledge update (heuristic: 14-30 days)
            elif 14 <= days_since <= 30:
                update_candidates.append({
                    "name": skill_name,
                    "days_since_use": days_since,
                    "action": "consider_update"
                })

        return {
            "scan_date": datetime.now().date().isoformat(),
            "total_skills_scanned": len(skills),
            "outdated_skills": outdated_skills,
            "update_candidates": update_candidates,
            "needs_attention": len(outdated_skills) + len(update_candidates)
        }

    async def check_all_triggers(
        self,
        quality_history: Dict[str, List[int]],
        usage_data: Dict[str, Any],
        skill_health: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Check all three types of triggers at once.

        Args:
            quality_history: Quality score history
            usage_data: Usage pattern data
            skill_health: Skill health metrics

        Returns:
            Combined trigger report
        """
        logger.info("Checking all forge triggers")

        quality_triggers = await self.check_quality_triggers(quality_history)
        usage_triggers = await self.check_usage_triggers(usage_data)
        time_scan = await self.time_driven_scan(skill_health)

        total_triggers = (
            len(quality_triggers) +
            len(usage_triggers) +
            time_scan.get("needs_attention", 0)
        )

        return {
            "check_date": datetime.now().isoformat(),
            "quality_triggers": quality_triggers,
            "usage_triggers": usage_triggers,
            "time_scan": time_scan,
            "total_triggers": total_triggers,
            "priority_actions": self._prioritize_actions(
                quality_triggers,
                usage_triggers,
                time_scan
            )
        }

    def _calculate_severity(self, avg_score: float) -> str:
        """Calculate severity level based on average score."""
        if avg_score < 50:
            return "critical"
        elif avg_score < 60:
            return "high"
        elif avg_score < 70:
            return "medium"
        else:
            return "low"

    def _suggest_action(self, avg_score: float) -> str:
        """Suggest action based on score."""
        if avg_score < 50:
            return "L3_rebuild"  # Complete rebuild needed
        elif avg_score < 60:
            return "L2_refactor"  # Logic modification needed
        else:
            return "L1_tune"  # Parameter tuning sufficient

    def _prioritize_actions(
        self,
        quality_triggers: List[Dict[str, Any]],
        usage_triggers: List[Dict[str, Any]],
        time_scan: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Prioritize all triggers by urgency and impact.

        Returns:
            Sorted list of actions to take
        """
        actions = []

        # Quality triggers (high priority if critical)
        for trigger in quality_triggers:
            priority = 1 if trigger["severity"] == "critical" else 2
            actions.append({
                "type": "quality_improvement",
                "target": trigger["skill"],
                "action": trigger["action"],
                "priority": priority,
                "details": trigger
            })

        # Usage triggers (medium-high priority)
        for trigger in usage_triggers:
            priority = 2 if trigger.get("priority") == "high" else 3
            actions.append({
                "type": "new_skill",
                "target": trigger["task_type"],
                "action": trigger["action"],
                "priority": priority,
                "details": trigger
            })

        # Time scan (low-medium priority)
        for skill in time_scan.get("outdated_skills", []):
            priority = 3 if skill.get("urgency") == "high" else 4
            actions.append({
                "type": "maintenance",
                "target": skill["name"],
                "action": skill["action"],
                "priority": priority,
                "details": skill
            })

        # Sort by priority
        actions.sort(key=lambda x: x["priority"])

        return actions

    async def validate_forge_safety(
        self,
        trigger: Dict[str, Any],
        sandbox_available: bool = True
    ) -> Dict[str, Any]:
        """
        Validate if forge trigger passes safety guardrails.

        Safety rules:
        - New skills must be tested in sandbox-lab (10+ simulations)
        - L1 tuning: Auto-approve
        - L2 refactor: Auto-approve if sandbox passes
        - L3 rebuild: Requires MUSEON (Zeal) approval

        Args:
            trigger: Forge trigger to validate
            sandbox_available: Whether sandbox testing is available

        Returns:
            Validation result with approval status
        """
        action = trigger.get("action", "")

        # L1 tuning: Always auto-approved
        if action == "L1_tune":
            return {
                "approved": True,
                "auto_execute": True,
                "reason": "L1_parameter_tuning",
                "requires_sandbox": False,
                "requires_human_approval": False
            }

        # L2 refactor: Auto-approved if sandbox available
        elif action == "L2_refactor":
            return {
                "approved": sandbox_available,
                "auto_execute": sandbox_available,
                "reason": "L2_logic_modification",
                "requires_sandbox": True,
                "requires_human_approval": False
            }

        # L3 rebuild: Requires human approval
        elif action == "L3_rebuild" or action == "forge_new_skill":
            return {
                "approved": False,
                "auto_execute": False,
                "reason": "L3_requires_human_approval",
                "requires_sandbox": True,
                "requires_human_approval": True,
                "notify_museon": True
            }

        # Unknown action: Reject
        else:
            return {
                "approved": False,
                "auto_execute": False,
                "reason": "unknown_action_type",
                "requires_sandbox": True,
                "requires_human_approval": True
            }
