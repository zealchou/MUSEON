"""
Input Sanitizer - Layer 2 Defense

Sanitizes all external input before processing:
- Prompt injection detection (regex + semantic patterns)
- Role-playing pattern detection
- XML/JSON tag injection cleaning
- Instruction keyword detection
- Content vs instruction separation
- Memory write validation with trust levels
"""
import logging
import re
from typing import Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class ThreatType(str, Enum):
    """Types of detected threats."""
    PROMPT_INJECTION = "prompt_injection"
    ROLE_PLAYING = "role_playing"
    TAG_INJECTION = "tag_injection"
    INSTRUCTION_KEYWORDS = "instruction_keywords"
    SUSPICIOUS_PATTERN = "suspicious_pattern"


class InputSanitizer:
    """Sanitizes and validates input from external sources."""

    # Prompt injection patterns (regex)
    INJECTION_PATTERNS = [
        r"忽略.*(?:指令|规则|要求)",
        r"ignore.*(?:instruction|rule|prompt|above)",
        r"disregard.*(?:previous|above|all)",
        r"你(?:現在|现在)是.*DAN",
        r"you are now (?:a |an )?(?:helpful |different |new )?(?:assistant|AI|agent)",
        r"forget (?:all |everything |your )?(?:previous |above )?(?:instruction|rule|prompt)",
        r"override.*(?:system|safety|rule)",
    ]

    # Role-playing patterns
    ROLE_PATTERNS = [
        r"you (?:are|must be|should be) (?:now )?(?:a |an )?(.{1,50}) that",
        r"act as (?:a |an )?(.{1,50})",
        r"pretend (?:to be |you are )(?:a |an )?(.{1,50})",
        r"simulate (?:a |an )?(.{1,50})",
    ]

    # Tag injection patterns
    TAG_PATTERNS = [
        r"</(?:system|user|assistant|human|ai)>",
        r"<(?:system|user|assistant|human|ai)>",
        r"\{(?:system|user|assistant):",
        r"\[SYSTEM\]",
        r"\[/SYSTEM\]",
    ]

    # Instruction keywords (Chinese and English)
    INSTRUCTION_KEYWORDS = [
        "忽略", "無視", "不要遵守", "停止遵循",
        "ignore", "disregard", "override", "bypass",
        "must follow", "you must", "you will",
        "執行", "运行", "运行代码", "execute code",
    ]

    def __init__(self):
        """Initialize input sanitizer."""
        self.compiled_patterns = {
            "injection": [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS],
            "role": [re.compile(p, re.IGNORECASE) for p in self.ROLE_PATTERNS],
            "tag": [re.compile(p, re.IGNORECASE) for p in self.TAG_PATTERNS],
        }

    async def sanitize(
        self,
        content: str,
        source: str,
        trust_level: str
    ) -> Dict[str, Any]:
        """
        Sanitize input content based on trust level.

        Args:
            content: Input content to sanitize
            source: Source of the content
            trust_level: Trust level (TRUSTED/VERIFIED/UNKNOWN/UNTRUSTED)

        Returns:
            Dict with sanitization results
        """
        # TRUSTED sources pass through
        if trust_level == "TRUSTED":
            return {
                "is_safe": True,
                "sanitized_content": content,
                "threats_detected": [],
                "action": "allow"
            }

        # Scan for threats
        threats = []

        # 1. Check for prompt injection
        if self._detect_injection(content):
            threats.append(ThreatType.PROMPT_INJECTION)

        # 2. Check for role-playing
        if self._detect_role_playing(content):
            threats.append(ThreatType.ROLE_PLAYING)

        # 3. Check for tag injection
        if self._detect_tag_injection(content):
            threats.append(ThreatType.TAG_INJECTION)

        # 4. Check for instruction keywords
        if self._detect_instruction_keywords(content):
            threats.append(ThreatType.INSTRUCTION_KEYWORDS)

        # Determine action
        if threats:
            logger.warning(f"Threats detected in content from {source}: {threats}")
            return {
                "is_safe": False,
                "sanitized_content": None,
                "threats_detected": threats,
                "action": "block",
                "source": source,
                "trust_level": trust_level
            }

        # No threats detected
        return {
            "is_safe": True,
            "sanitized_content": content,
            "threats_detected": [],
            "action": "allow"
        }

    def _detect_injection(self, content: str) -> bool:
        """Detect prompt injection patterns."""
        for pattern in self.compiled_patterns["injection"]:
            if pattern.search(content):
                logger.debug(f"Injection pattern matched: {pattern.pattern}")
                return True
        return False

    def _detect_role_playing(self, content: str) -> bool:
        """Detect role-playing patterns."""
        for pattern in self.compiled_patterns["role"]:
            if pattern.search(content):
                logger.debug(f"Role-playing pattern matched: {pattern.pattern}")
                return True
        return False

    def _detect_tag_injection(self, content: str) -> bool:
        """Detect XML/JSON tag injection."""
        for pattern in self.compiled_patterns["tag"]:
            if pattern.search(content):
                logger.debug(f"Tag injection detected: {pattern.pattern}")
                return True
        return False

    def _detect_instruction_keywords(self, content: str) -> bool:
        """Detect instruction keywords."""
        content_lower = content.lower()
        for keyword in self.INSTRUCTION_KEYWORDS:
            if keyword.lower() in content_lower:
                logger.debug(f"Instruction keyword detected: {keyword}")
                return True
        return False

    async def validate_memory_write(
        self,
        content: str,
        channel: str,
        trust_level: str
    ) -> Dict[str, Any]:
        """
        Validate if content can be written to memory channel.

        Memory write rules:
        - TRUSTED: Can write to all channels
        - VERIFIED: Can write to event/outcome/user_reaction, not meta_thinking
        - UNKNOWN: Only quarantine
        - UNTRUSTED: Rejected

        Args:
            content: Content to write
            channel: Memory channel
            trust_level: Trust level

        Returns:
            Dict with validation result
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
                    "alternative_channel": "quarantine",
                    "reason": "verified_sources_cannot_write_meta_thinking"
                }

        if trust_level == "UNKNOWN":
            return {
                "allowed": False,
                "alternative_channel": "quarantine",
                "reason": "unknown_sources_isolated"
            }

        # UNTRUSTED: Reject completely
        return {
            "allowed": False,
            "reason": "untrusted_source"
        }

    async def cross_validate(
        self,
        new_fact: str,
        existing_facts: List[str]
    ) -> Dict[str, Any]:
        """
        Cross-validate new fact against existing knowledge.

        Simple keyword-based contradiction detection.
        For production, would use semantic similarity.

        Args:
            new_fact: New fact to validate
            existing_facts: List of existing facts

        Returns:
            Dict with validation result
        """
        # Simple keyword contradiction check
        # e.g., "老闆討厭咖啡" vs "老闆喜歡咖啡"

        new_lower = new_fact.lower()

        # Check for contradictions
        for existing in existing_facts:
            existing_lower = existing.lower()

            # Detect opposite sentiments
            if self._check_contradiction(new_lower, existing_lower):
                logger.warning(f"Contradiction detected: '{new_fact}' vs '{existing}'")
                return {
                    "consistent": False,
                    "action": "quarantine",
                    "conflicting_fact": existing
                }

        return {
            "consistent": True,
            "action": "accept"
        }

    def _check_contradiction(self, fact1: str, fact2: str) -> bool:
        """
        Simple contradiction check.

        Looks for opposite sentiment words in similar contexts.
        """
        # Extract key terms (simplified)
        # In production, use NLP for better detection

        negative_pairs = [
            ("喜歡", "討厭"), ("like", "hate"),
            ("愛", "恨"), ("love", "dislike"),
            ("是", "不是"), ("is", "is not"),
            ("每天喝", "討厭"), ("愛好者", "討厭"),  # Specific coffee contradiction
        ]

        for pos, neg in negative_pairs:
            if pos in fact1 and neg in fact2:
                return True
            if neg in fact1 and pos in fact2:
                return True
            # Also check reverse
            if pos in fact2 and neg in fact1:
                return True
            if neg in fact2 and pos in fact1:
                return True

        return False

    def clean_tags(self, content: str) -> str:
        """
        Remove or escape dangerous tags.

        Args:
            content: Content to clean

        Returns:
            Cleaned content
        """
        # Escape HTML/XML tags
        cleaned = content.replace("<", "&lt;").replace(">", "&gt;")

        # Remove control characters
        cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned)

        return cleaned
