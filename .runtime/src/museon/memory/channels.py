"""Four-channel memory system for MUSEON.

Based on plan-v7.md Chapter 6:
- meta-thinking: "How I thought about this" → thought patterns and reasoning
- event: "What happened" → concrete events and facts
- outcome: "What was the result" → success/failure/metrics
- user-reaction: "How did user react" → user feedback and preferences

Each channel stores different aspects of the same interaction.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime


class MemoryChannel(ABC):
    """Base class for memory channels."""

    @abstractmethod
    def get_channel_name(self) -> str:
        """Return the name of this channel."""
        pass

    @abstractmethod
    def validate_entry(self, entry: Dict[str, Any]) -> bool:
        """Validate that an entry has the required structure for this channel."""
        pass

    def get_required_fields(self) -> list:
        """Return list of required fields for this channel."""
        return ["timestamp"]


class MetaThinkingChannel(MemoryChannel):
    """Meta-thinking channel: stores thought patterns and reasoning.

    This is the "wisdom" channel - how MUSEON thinks about problems.
    Gets naturally reinforced because it's used in every interaction.

    Security: ONLY accepts entries from TRUSTED sources (boss/MUSEON).
    """

    def get_channel_name(self) -> str:
        return "meta-thinking"

    def get_required_fields(self) -> list:
        return super().get_required_fields() + [
            "thought_pattern",
            "reasoning",
        ]

    def validate_entry(self, entry: Dict[str, Any]) -> bool:
        """Validate meta-thinking entry structure."""
        required = self.get_required_fields()

        # Check all required fields present
        for field in required:
            if field not in entry:
                return False

        # Optional but recommended fields
        if "outcome" in entry:
            if entry["outcome"] not in ["positive", "negative", "neutral"]:
                return False

        if "confidence" in entry:
            if not (0 <= entry["confidence"] <= 1.0):
                return False

        return True


class EventChannel(MemoryChannel):
    """Event channel: stores concrete events and facts.

    Records what actually happened - user actions, system events, etc.
    Events fade over time but patterns remain.

    Security: Accepts from any source, but marks trust level.
    """

    def get_channel_name(self) -> str:
        return "event"

    def get_required_fields(self) -> list:
        return super().get_required_fields() + [
            "event_type",
            "description",
        ]

    def validate_entry(self, entry: Dict[str, Any]) -> bool:
        """Validate event entry structure."""
        required = self.get_required_fields()

        for field in required:
            if field not in entry:
                return False

        # Event type should be from known categories
        valid_event_types = [
            "user_instruction",
            "task_completion",
            "skill_execution",
            "system_event",
            "external_trigger",
            "heartbeat_patrol",
            "nightly_job",
        ]

        if entry["event_type"] not in valid_event_types:
            # Allow unknown event types but they should be strings
            if not isinstance(entry["event_type"], str):
                return False

        return True


class OutcomeChannel(MemoryChannel):
    """Outcome channel: stores results and metrics.

    Records what happened after an action - success/failure, metrics.
    Used to validate meta-thinking predictions.

    Security: Accepts from VERIFIED and TRUSTED sources.
    """

    def get_channel_name(self) -> str:
        return "outcome"

    def get_required_fields(self) -> list:
        return super().get_required_fields() + [
            "task_id",
            "result",
        ]

    def validate_entry(self, entry: Dict[str, Any]) -> bool:
        """Validate outcome entry structure."""
        required = self.get_required_fields()

        for field in required:
            if field not in entry:
                return False

        # Result should be success/failure/partial
        if entry["result"] not in ["success", "failure", "partial", "unknown"]:
            return False

        # Metrics should be dict if present
        if "metrics" in entry:
            if not isinstance(entry["metrics"], dict):
                return False

            # Check metrics structure
            metrics = entry["metrics"]
            if "token_used" in metrics and not isinstance(metrics["token_used"], (int, float)):
                return False
            if "time_taken" in metrics and not isinstance(metrics["time_taken"], (int, float)):
                return False
            if "quality_score" in metrics and not (0 <= metrics["quality_score"] <= 10):
                return False

        return True


class UserReactionChannel(MemoryChannel):
    """User-reaction channel: stores user feedback and preferences.

    Records how the user reacted - likes/dislikes, explicit feedback.
    Stored separately to avoid being corrupted by low-quality users.

    Security: ONLY accepts from TRUSTED sources (actual user reactions).
    """

    def get_channel_name(self) -> str:
        return "user-reaction"

    def get_required_fields(self) -> list:
        return super().get_required_fields() + [
            "task_id",
            "reaction",
        ]

    def validate_entry(self, entry: Dict[str, Any]) -> bool:
        """Validate user-reaction entry structure."""
        required = self.get_required_fields()

        for field in required:
            if field not in entry:
                return False

        # Reaction should be positive/negative/neutral
        if entry["reaction"] not in ["positive", "negative", "neutral", "unknown"]:
            return False

        # Explicit rating should be 0-10 if present
        if "explicit_rating" in entry:
            if not isinstance(entry["explicit_rating"], (int, float)):
                return False
            if not (0 <= entry["explicit_rating"] <= 10):
                return False

        return True


class ChannelManager:
    """Manages all four memory channels.

    Provides unified interface for writing to multiple channels simultaneously.
    """

    def __init__(self):
        self.channels = {
            "meta-thinking": MetaThinkingChannel(),
            "event": EventChannel(),
            "outcome": OutcomeChannel(),
            "user-reaction": UserReactionChannel(),
        }

    def get_channel(self, channel_name: str) -> Optional[MemoryChannel]:
        """Get a specific channel by name."""
        return self.channels.get(channel_name)

    def validate_multi_channel_entry(
        self, entries: Dict[str, Dict[str, Any]]
    ) -> Dict[str, bool]:
        """Validate entries for multiple channels.

        Args:
            entries: Dict mapping channel names to entry dicts

        Returns:
            Dict mapping channel names to validation results
        """
        results = {}

        for channel_name, entry in entries.items():
            channel = self.get_channel(channel_name)
            if channel:
                results[channel_name] = channel.validate_entry(entry)
            else:
                results[channel_name] = False

        return results

    def get_all_channel_names(self) -> list:
        """Get names of all available channels."""
        return list(self.channels.keys())
