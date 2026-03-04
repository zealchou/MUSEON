"""
AI Behavior Guardrails - Layer 4 Defense

Implements AI-specific safety controls:
- Action risk classification (green/yellow/red)
- High-risk action blocking
- Confidence threshold enforcement
- Multi-path reasoning verification
- Self-check before critical actions
"""
import logging
from typing import Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk levels for actions."""
    GREEN = "green"    # Autonomous
    YELLOW = "yellow"  # Needs confirmation
    RED = "red"        # Forbidden


class Guardrails:
    """AI behavior guardrails and safety checks."""

    # Action risk classification
    RISK_CLASSIFICATION = {
        # Green: Autonomous actions
        "read_file": RiskLevel.GREEN,
        "search": RiskLevel.GREEN,
        "analyze": RiskLevel.GREEN,
        "forge_skill": RiskLevel.GREEN,
        "process_request": RiskLevel.GREEN,

        # Yellow: Needs confirmation
        "send_message": RiskLevel.YELLOW,
        "post_social": RiskLevel.YELLOW,
        "reply_comment": RiskLevel.YELLOW,
        "register": RiskLevel.YELLOW,
        "delete_file": RiskLevel.YELLOW,

        # Red: Forbidden without explicit approval
        "transfer_money": RiskLevel.RED,
        "delete_account": RiskLevel.RED,
        "delete_user_data": RiskLevel.RED,
        "modify_security": RiskLevel.RED,
    }

    def __init__(self, confidence_threshold: float = 0.70):
        """
        Initialize guardrails.

        Args:
            confidence_threshold: Minimum confidence for autonomous actions (default 0.70)
        """
        self.confidence_threshold = confidence_threshold

    def classify_action(self, action: str) -> str:
        """
        Classify action risk level.

        Args:
            action: Action name

        Returns:
            Risk level (green/yellow/red)
        """
        return self.RISK_CLASSIFICATION.get(action, RiskLevel.YELLOW).value

    async def check_action(
        self,
        action: str,
        source: str,
        trust_level: str
    ) -> Dict[str, Any]:
        """
        Check if action is allowed based on risk and trust level.

        Args:
            action: Action to perform
            source: Trigger source
            trust_level: Trust level of source

        Returns:
            Dict with decision
        """
        risk_level = self.classify_action(action)

        # Green actions: Always allowed
        if risk_level == RiskLevel.GREEN:
            return {
                "allowed": True,
                "risk_level": risk_level,
                "requires_approval": False
            }

        # Yellow actions: Allowed for TRUSTED sources
        if risk_level == RiskLevel.YELLOW:
            if trust_level == "TRUSTED":
                return {
                    "allowed": True,
                    "risk_level": risk_level,
                    "requires_approval": False
                }
            else:
                return {
                    "allowed": False,
                    "risk_level": risk_level,
                    "requires_approval": True,
                    "reason": "yellow_action_needs_trusted_source"
                }

        # Red actions: Never allowed without explicit override
        if risk_level == RiskLevel.RED:
            logger.warning(f"High-risk action attempted: {action} from {source}")
            return {
                "allowed": False,
                "risk_level": risk_level,
                "requires_approval": True,
                "reason": "high_risk_action_forbidden"
            }

        # Unknown action: Default to yellow
        return {
            "allowed": False,
            "risk_level": RiskLevel.YELLOW,
            "requires_approval": True,
            "reason": "unknown_action_type"
        }

    async def check_decision_confidence(
        self,
        action: str,
        confidence: float
    ) -> Dict[str, Any]:
        """
        Check if decision confidence meets threshold.

        Args:
            action: Action being considered
            confidence: Confidence score (0.0 - 1.0)

        Returns:
            Dict with decision
        """
        if confidence >= self.confidence_threshold:
            return {
                "allowed": True,
                "confidence": confidence,
                "threshold": self.confidence_threshold
            }
        else:
            logger.info(f"Low confidence ({confidence}) for action: {action}")
            return {
                "allowed": False,
                "confidence": confidence,
                "threshold": self.confidence_threshold,
                "action": "ask_boss",
                "reason": "confidence_below_threshold"
            }

    async def verify_reasoning_paths(
        self,
        paths: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Verify consistency across multiple reasoning paths.

        Args:
            paths: List of reasoning paths, each with "action" and "reasoning"

        Returns:
            Dict with consistency check result
        """
        if not paths or len(paths) < 2:
            return {
                "consistent": True,
                "reason": "insufficient_paths_for_verification"
            }

        # Extract actions from each path
        actions = [p.get("action") for p in paths]

        # Check if all actions are the same
        unique_actions = set(actions)

        if len(unique_actions) == 1:
            return {
                "consistent": True,
                "agreed_action": actions[0],
                "path_count": len(paths)
            }
        else:
            logger.warning(f"Inconsistent reasoning paths: {unique_actions}")
            return {
                "consistent": False,
                "conflicting_actions": list(unique_actions),
                "path_count": len(paths),
                "action": "require_human_decision"
            }

    async def self_check_before_action(
        self,
        action: str,
        trigger_source: str,
        trigger_trust_level: str,
        confidence: float
    ) -> Dict[str, Any]:
        """
        Perform self-check before executing critical action.

        Questions:
        1. Why am I doing this?
        2. What triggered this?
        3. Is the trigger source TRUSTED?
        4. What is my confidence level?

        Args:
            action: Action to perform
            trigger_source: What triggered this action
            trigger_trust_level: Trust level of trigger
            confidence: Confidence in decision

        Returns:
            Dict with self-check results
        """
        checks = {
            "action": action,
            "trigger_source": trigger_source,
            "trigger_trust_level": trigger_trust_level,
            "confidence": confidence,
            "checks_passed": []
        }

        # Check 1: Is trigger TRUSTED?
        if trigger_trust_level == "TRUSTED":
            checks["checks_passed"].append("trusted_source")
        else:
            checks["warning"] = "trigger_not_trusted"

        # Check 2: Is confidence acceptable?
        if confidence >= self.confidence_threshold:
            checks["checks_passed"].append("confidence_ok")
        else:
            checks["warning"] = "low_confidence"

        # Check 3: Is action risk acceptable?
        risk = self.classify_action(action)
        if risk != RiskLevel.RED:
            checks["checks_passed"].append("risk_acceptable")
        else:
            checks["warning"] = "high_risk_action"

        # Overall decision
        if len(checks["checks_passed"]) >= 3:
            checks["decision"] = "proceed"
        elif "warning" in checks:
            checks["decision"] = "ask_boss"
        else:
            checks["decision"] = "block"

        return checks
