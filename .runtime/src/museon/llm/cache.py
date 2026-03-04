"""Prompt Caching configuration for Claude API."""

from typing import Dict, Any, Literal


class PromptCacheConfig:
    """
    Configuration helpers for Claude Prompt Caching.

    Claude supports up to 4 cache breakpoints with different TTLs:
    - 5 minutes: 1.25x write cost, 0.1x read cost
    - 1 hour: 2x write cost, 0.1x read cost (not used in current implementation)

    Prompt Caching is GA (General Availability) - no beta flag needed.
    """

    @staticmethod
    def create_system_cache(content: str, ttl: int = 300) -> Dict[str, Any]:
        """
        Create a cacheable system prompt block.

        Args:
            content: The system prompt content
            ttl: Time to live in seconds (300 = 5 min, 3600 = 1 hour)

        Returns:
            Dict formatted for Claude API with cache_control
        """
        return {
            "type": "text",
            "text": content,
            "cache_control": {"type": "ephemeral"},
        }

    @staticmethod
    def create_tool_cache(tools: list) -> list:
        """
        Create cacheable tool definitions.

        The last tool in the list gets a cache breakpoint.

        Args:
            tools: List of tool definitions

        Returns:
            Tools list with cache_control on the last tool
        """
        if not tools:
            return []

        # Add cache control to the last tool
        cacheable_tools = tools.copy()
        if len(cacheable_tools) > 0:
            cacheable_tools[-1]["cache_control"] = {"type": "ephemeral"}

        return cacheable_tools

    @staticmethod
    def create_conversation_cache(messages: list) -> list:
        """
        Create cacheable conversation history.

        The last user message gets a cache breakpoint to cache conversation context.

        Args:
            messages: List of message dicts

        Returns:
            Messages list with cache_control on the last message
        """
        if not messages:
            return []

        cacheable_messages = messages.copy()

        # Find the last message and add cache control
        if len(cacheable_messages) > 0:
            last_msg = cacheable_messages[-1]

            # Add cache_control to content if it's a dict
            if isinstance(last_msg.get("content"), str):
                cacheable_messages[-1] = {
                    "role": last_msg["role"],
                    "content": [
                        {
                            "type": "text",
                            "text": last_msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }

        return cacheable_messages


class CacheStrategy:
    """
    Strategies for where to place cache breakpoints.

    Max 4 breakpoints, prioritize by update frequency:
    1. DNA27 core system prompt (rarely changes) - 1 hour cache
    2. Active skills (changes per task) - 5 min cache
    3. Conversation history (changes per turn) - 5 min cache
    4. Tools (rarely changes) - 5 min cache
    """

    @staticmethod
    def get_optimal_breakpoints(
        has_system: bool = False,
        has_skills: bool = False,
        has_history: bool = False,
        has_tools: bool = False,
    ) -> Dict[str, bool]:
        """
        Determine optimal cache breakpoints based on what's present.

        Args:
            has_system: Whether system prompt is present
            has_skills: Whether skills are active
            has_history: Whether conversation history is present
            has_tools: Whether tools are present

        Returns:
            Dict indicating which components should be cached
        """
        breakpoints: Dict[str, bool] = {
            "system": False,
            "skills": False,
            "history": False,
            "tools": False,
        }

        # Priority order (up to 4 breakpoints)
        available = 4

        if has_system and available > 0:
            breakpoints["system"] = True
            available -= 1

        if has_skills and available > 0:
            breakpoints["skills"] = True
            available -= 1

        if has_history and available > 0:
            breakpoints["history"] = True
            available -= 1

        if has_tools and available > 0:
            breakpoints["tools"] = True
            available -= 1

        return breakpoints
