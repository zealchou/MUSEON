"""Router - Smart model selection between Haiku and Sonnet."""

import re
from typing import Dict, Any, Literal


class Router:
    """
    Router classifies incoming messages and decides whether to use Haiku or Sonnet.

    Default: Sonnet (smarter, more capable)
    Downgrade to Haiku only when ALL of these conditions are met:
    - Message is short (< 50 words)
    - No active skills in session context
    - Matches one of the Haiku-eligible patterns
    """

    # Patterns that can be handled by Haiku
    HAIKU_PATTERNS = [
        (r"^(hello|hi|hey|good morning|good afternoon|good evening)(!|\s|$)", "simple greeting"),
        (r"(what('?s| is) (the )?(time|weather|date|temperature))", "simple query"),
        (r"(what time is it|what'?s the time)", "simple query"),
        (r"^(yes|no|ok|okay|sure|thanks|thank you)(!|\.|\s|$)", "simple acknowledgment"),
    ]

    # Keywords that require Sonnet
    SONNET_KEYWORDS = [
        # Content creation
        "write", "create", "generate", "compose", "draft",
        # Business/consulting
        "business", "revenue", "marketing", "strategy", "profit", "customer",
        # Brand/creative
        "brand", "story", "campaign", "post", "content",
        # Analysis/complex
        "analyze", "evaluate", "review", "assess", "diagnose",
        # Skill invocation indicators
        "help me", "need advice", "what should i",
    ]

    def classify(
        self, message: str, session_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Classify message and decide which model to use.

        Args:
            message: The user message
            session_context: Context about the current session

        Returns:
            Dict with keys: model ("haiku" | "sonnet"), reason (str)
        """
        message_lower = message.lower()

        # Rule 1: If active skills in session, maintain Sonnet
        if session_context.get("active_skills"):
            return {
                "model": "sonnet",
                "reason": "active skills in session",
            }

        # Rule 2: Check message length first
        word_count = len(message.split())
        if word_count > 50:
            return {
                "model": "sonnet",
                "reason": "message too long for Haiku",
            }

        # Rule 3: Check Haiku-eligible patterns (before keywords)
        for pattern, reason in self.HAIKU_PATTERNS:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return {
                    "model": "haiku",
                    "reason": reason,
                }

        # Rule 4: Check for Sonnet keywords
        for keyword in self.SONNET_KEYWORDS:
            if keyword in message_lower:
                return {
                    "model": "sonnet",
                    "reason": f"keyword detected: {keyword}",
                }

        # Default: Sonnet (safer choice)
        return {
            "model": "sonnet",
            "reason": "default for complex/ambiguous tasks",
        }
