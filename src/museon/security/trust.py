"""
Trust Level System

Implements four-level trust hierarchy:
- TRUSTED: Boss, Mother System (can give instructions)
- VERIFIED: Platform APIs (verified sources, data only)
- UNKNOWN: Web content, external sources (data only, isolated)
- UNTRUSTED: Blacklisted sources (rejected)

Core principle: External content is DATA, not INSTRUCTION.
Only TRUSTED sources can provide instructions.
"""
import logging
from enum import IntEnum
from typing import Dict, Any, Set

logger = logging.getLogger(__name__)


class TrustLevel(IntEnum):
    """Trust level hierarchy (higher = more trusted)."""
    UNTRUSTED = 1
    UNKNOWN = 2
    VERIFIED = 3
    TRUSTED = 4


class TrustManager:
    """Manages trust levels for different sources."""

    # Source -> Trust Level mapping
    SOURCE_TRUST_MAP = {
        # TRUSTED: Boss and Mother System
        "telegram_boss": "TRUSTED",
        "museon_mother": "TRUSTED",

        # VERIFIED: Platform APIs
        "instagram_api": "VERIFIED",
        "line_api": "VERIFIED",
        "telegram_api": "VERIFIED",

        # UNKNOWN: External sources (default)
        "web_scrape": "UNKNOWN",
        "web_search": "UNKNOWN",
        "unknown": "UNKNOWN",
    }

    def __init__(self):
        """Initialize trust manager."""
        self.blacklist: Set[str] = set()

    def get_trust_level(self, source: str) -> str:
        """
        Get trust level for a source.

        Args:
            source: Source identifier

        Returns:
            Trust level string (TRUSTED/VERIFIED/UNKNOWN/UNTRUSTED)
        """
        # Check blacklist first
        if source in self.blacklist:
            return "UNTRUSTED"

        # Check source map
        return self.SOURCE_TRUST_MAP.get(source, "UNKNOWN")

    def add_to_blacklist(self, source: str) -> None:
        """
        Add source to blacklist.

        Args:
            source: Source to blacklist
        """
        self.blacklist.add(source)
        logger.warning(f"Source blacklisted: {source}")

    def remove_from_blacklist(self, source: str) -> None:
        """
        Remove source from blacklist.

        Args:
            source: Source to remove
        """
        if source in self.blacklist:
            self.blacklist.remove(source)
            logger.info(f"Source removed from blacklist: {source}")

    def classify_input(
        self,
        content: str,
        source: str,
        trust_level: str
    ) -> Dict[str, Any]:
        """
        Classify input as instruction or data.

        Rule: Only TRUSTED sources can provide instructions.
        All other sources provide data only.

        Args:
            content: Input content
            source: Source identifier
            trust_level: Trust level of source

        Returns:
            Dict with classification
        """
        if trust_level == "TRUSTED":
            # TRUSTED sources can give instructions
            input_type = "instruction"
        else:
            # All other sources: treat as data
            input_type = "data"

        return {
            "type": input_type,
            "content": content,
            "source": source,
            "trust_level": trust_level
        }

    def can_write_to_channel(
        self,
        trust_level: str,
        channel: str
    ) -> Dict[str, Any]:
        """
        Check if trust level can write to memory channel.

        Rules:
        - TRUSTED: All channels
        - VERIFIED: event, outcome, user_reaction
        - UNKNOWN: quarantine only
        - UNTRUSTED: none

        Args:
            trust_level: Trust level
            channel: Memory channel

        Returns:
            Dict with permission result
        """
        if trust_level == "TRUSTED":
            return {
                "allowed": True,
                "channel": channel
            }

        if trust_level == "VERIFIED":
            if channel in ["event", "outcome", "user_reaction"]:
                return {
                    "allowed": True,
                    "channel": channel
                }
            else:
                return {
                    "allowed": False,
                    "reason": "verified_limited_channels",
                    "alternative": "quarantine"
                }

        if trust_level == "UNKNOWN":
            if channel == "quarantine":
                return {
                    "allowed": True,
                    "channel": channel
                }
            else:
                return {
                    "allowed": False,
                    "reason": "unknown_must_quarantine",
                    "alternative": "quarantine"
                }

        # UNTRUSTED: Cannot write anywhere
        return {
            "allowed": False,
            "reason": "untrusted_blocked"
        }

    def compare_trust(self, level1: str, level2: str) -> int:
        """
        Compare two trust levels.

        Args:
            level1: First trust level
            level2: Second trust level

        Returns:
            1 if level1 > level2, -1 if level1 < level2, 0 if equal
        """
        enum_level1 = TrustLevel[level1]
        enum_level2 = TrustLevel[level2]

        if enum_level1 > enum_level2:
            return 1
        elif enum_level1 < enum_level2:
            return -1
        else:
            return 0

    def is_privileged(self, trust_level: str) -> bool:
        """
        Check if trust level has privileged access.

        Args:
            trust_level: Trust level to check

        Returns:
            True if TRUSTED or VERIFIED
        """
        return trust_level in ["TRUSTED", "VERIFIED"]
