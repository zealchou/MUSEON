"""Memory write validation - Layer 5 security defense.

Based on plan-v7.md Chapter 7 (Layer 5: Memory Integrity Validation):
- Validates trust level before memory write
- Cross-validates with existing knowledge
- Detects contradictions and prompt injection attempts
- Prevents stateful delayed attacks

Security principle: Memory write is more dangerous than memory read.
Once poisoned memory is written, it can influence all future decisions.
"""

from typing import Dict, Any, List, Optional
from enum import Enum


class TrustLevel(Enum):
    """Trust levels for memory sources."""

    TRUSTED = "TRUSTED"  # Boss or MUSEON
    VERIFIED = "VERIFIED"  # Platform APIs, validated sources
    UNKNOWN = "UNKNOWN"  # Web content, external sources
    UNTRUSTED = "UNTRUSTED"  # Flagged as suspicious


class MemoryValidator:
    """Validates memory writes for security and consistency."""

    def __init__(self, min_confidence: float = 0.7):
        """Initialize validator.

        Args:
            min_confidence: Minimum confidence threshold for memory write
        """
        self.min_confidence = min_confidence

        # Channel-specific trust requirements
        self.channel_trust_requirements = {
            "meta-thinking": [TrustLevel.TRUSTED],  # Only boss/MUSEON
            "event": [
                TrustLevel.TRUSTED,
                TrustLevel.VERIFIED,
                TrustLevel.UNKNOWN,
            ],  # Any
            "outcome": [TrustLevel.TRUSTED, TrustLevel.VERIFIED],  # No unknown
            "user-reaction": [TrustLevel.TRUSTED],  # Only actual user
        }

        # Prompt injection patterns (simple detection)
        self.injection_patterns = [
            "ignore previous",
            "ignore all previous",
            "disregard",
            "you are now",
            "new instructions",
            "system:",
            "admin:",
            "<|",  # Special tokens
            "anthropic",
            "openai",
        ]

    def validate(
        self,
        entry: Dict[str, Any],
        existing_knowledge: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Validate a memory entry before writing.

        Args:
            entry: Memory entry to validate
            existing_knowledge: Optional existing memories for cross-validation

        Returns:
            Dict with validation result:
            {
                "allowed": bool,
                "reason": str,
                "confidence_adjustment": float,
                "warnings": List[str],
                "quarantine": bool
            }
        """
        result = {
            "allowed": True,
            "reason": "",
            "confidence_adjustment": 1.0,
            "warnings": [],
            "quarantine": False,
        }

        # Step 1: Check trust level
        trust_check = self._check_trust_level(entry)
        if not trust_check["allowed"]:
            result.update(trust_check)
            return result

        # Step 2: Check confidence threshold
        confidence = entry.get("confidence", 1.0)
        if confidence < self.min_confidence:
            result["allowed"] = False
            result["reason"] = f"Confidence {confidence} below threshold {self.min_confidence}"
            result["quarantine"] = True
            return result

        # Step 3: Detect prompt injection
        injection_check = self._detect_prompt_injection(entry)
        if injection_check["detected"]:
            result["allowed"] = False
            result["reason"] = "Potential prompt injection detected"
            result["warnings"].append(injection_check["pattern"])
            return result

        # Step 4: Cross-validate with existing knowledge
        if existing_knowledge:
            contradiction_check = self._check_contradictions(entry, existing_knowledge)
            if contradiction_check["has_contradiction"]:
                result["warnings"].append("Contradicts existing knowledge")
                result["confidence_adjustment"] = 0.5
                # Don't block, but flag for review

        return result

    def _check_trust_level(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Check if entry's trust level is sufficient for its channel.

        Args:
            entry: Memory entry

        Returns:
            Dict with check result
        """
        channel = entry.get("channel", "unknown")
        trust_level_str = entry.get("trust_level", "UNKNOWN")

        # Convert string to enum
        try:
            trust_level = TrustLevel[trust_level_str]
        except KeyError:
            return {
                "allowed": False,
                "reason": f"Invalid trust level: {trust_level_str}",
            }

        # Check if this trust level is allowed for this channel
        required_levels = self.channel_trust_requirements.get(
            channel, [TrustLevel.TRUSTED]
        )

        if trust_level not in required_levels:
            return {
                "allowed": False,
                "reason": f"Trust level {trust_level_str} not sufficient for channel {channel}",
            }

        return {"allowed": True}

    def _detect_prompt_injection(self, entry: Dict[str, Any]) -> Dict[str, bool]:
        """Detect potential prompt injection in entry content.

        Args:
            entry: Memory entry

        Returns:
            Dict with detection result and pattern if found
        """
        content = entry.get("content", {})

        # Convert content to string for searching
        if isinstance(content, dict):
            content_str = str(content).lower()
        else:
            content_str = str(content).lower()

        # Check for injection patterns
        for pattern in self.injection_patterns:
            if pattern in content_str:
                return {
                    "detected": True,
                    "pattern": f"Matched injection pattern: {pattern}",
                }

        # Check for unusual XML/JSON tags that might escape context
        suspicious_tags = ["<|endoftext|>", "<system>", "</system>", "```system"]
        for tag in suspicious_tags:
            if tag.lower() in content_str:
                return {
                    "detected": True,
                    "pattern": f"Suspicious tag: {tag}",
                }

        return {"detected": False, "pattern": ""}

    def _check_contradictions(
        self,
        entry: Dict[str, Any],
        existing_knowledge: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Check if entry contradicts existing knowledge.

        Args:
            entry: New memory entry
            existing_knowledge: List of existing memories

        Returns:
            Dict with contradiction check result
        """
        # Simple contradiction detection
        # In production, this would use semantic similarity

        content = entry.get("content", {})
        if not isinstance(content, dict):
            return {"has_contradiction": False}

        # Extract key-value pairs from new entry
        new_assertions = self._extract_assertions(content)

        # Check against existing knowledge
        for existing in existing_knowledge:
            existing_assertions = self._extract_assertions(existing)

            # Look for contradictions
            for key, new_value in new_assertions.items():
                if key in existing_assertions:
                    old_value = existing_assertions[key]

                    # Check for direct contradiction
                    if self._is_contradictory(new_value, old_value):
                        return {
                            "has_contradiction": True,
                            "conflicting_key": key,
                            "old_value": old_value,
                            "new_value": new_value,
                        }

        return {"has_contradiction": False}

    def _extract_assertions(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key assertions from content.

        Args:
            content: Content dict

        Returns:
            Dict of key assertions
        """
        assertions = {}

        # Simple extraction: look for key-value pairs
        for key, value in content.items():
            if isinstance(value, (str, int, float, bool)):
                assertions[key] = value

        return assertions

    def _is_contradictory(self, value1: Any, value2: Any) -> bool:
        """Check if two values are contradictory.

        Args:
            value1: First value
            value2: Second value

        Returns:
            True if contradictory
        """
        # Simple rules for contradiction
        if isinstance(value1, bool) and isinstance(value2, bool):
            return value1 != value2

        if isinstance(value1, str) and isinstance(value2, str):
            # Check for opposite sentiments
            opposites = [
                ("positive", "negative"),
                ("likes", "dislikes"),
                ("prefers", "avoids"),
                ("brief", "detailed"),
                ("concise", "verbose"),
            ]

            v1_lower = value1.lower()
            v2_lower = value2.lower()

            for word1, word2 in opposites:
                if (word1 in v1_lower and word2 in v2_lower) or (
                    word2 in v1_lower and word1 in v2_lower
                ):
                    return True

        return False

    def validate_batch(
        self, entries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate a batch of memory entries.

        Args:
            entries: List of memory entries

        Returns:
            List of validation results
        """
        results = []

        for entry in entries:
            result = self.validate(entry)
            results.append(result)

        return results

    def get_validation_stats(
        self, validation_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Get statistics from validation results.

        Args:
            validation_results: List of validation result dicts

        Returns:
            Stats dict
        """
        total = len(validation_results)
        allowed = sum(1 for r in validation_results if r["allowed"])
        blocked = total - allowed
        quarantined = sum(1 for r in validation_results if r.get("quarantine", False))
        warnings = sum(len(r.get("warnings", [])) for r in validation_results)

        return {
            "total": total,
            "allowed": allowed,
            "blocked": blocked,
            "quarantined": quarantined,
            "total_warnings": warnings,
            "pass_rate": allowed / total if total > 0 else 0,
        }
