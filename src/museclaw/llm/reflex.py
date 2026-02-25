"""Reflex Engine - Template-based responses without LLM calls."""

import re
from typing import Dict, List, Optional, Tuple


class ReflexEngine:
    """
    Reflex engine for instant template-based responses.

    For common queries that don't need LLM processing, return pre-defined
    responses instantly. This saves tokens and reduces latency.
    """

    def __init__(self) -> None:
        """Initialize Reflex Engine with default templates."""
        self._templates: List[Tuple[re.Pattern, str]] = []

        # Add default templates
        self._add_default_templates()

    def _add_default_templates(self) -> None:
        """Add default reflex templates."""
        default_templates = [
            # Contact information
            (
                r"(?i)(what'?s? (your|the) (phone|number|contact))",
                "Please contact us at: [CONTACT_INFO_PLACEHOLDER]",
            ),
            # Operating hours
            (
                r"(?i)(what('?s| are) (your|the) (hours|opening|business hours))",
                "Our business hours are: [HOURS_PLACEHOLDER]",
            ),
            # Location/address
            (
                r"(?i)(where (are you|is (the )?(shop|store|office)))",
                "We're located at: [ADDRESS_PLACEHOLDER]",
            ),
            # Pricing (generic)
            (
                r"(?i)(how much|what('?s| is) (the )?(price|cost))",
                "Please check our price list: [PRICING_PLACEHOLDER]",
            ),
        ]

        for pattern, response in default_templates:
            self.add_template(pattern=pattern, response=response)

    def add_template(self, pattern: str, response: str) -> None:
        """
        Add a reflex template.

        Args:
            pattern: Regex pattern to match
            response: Response to return when matched
        """
        compiled_pattern = re.compile(pattern, re.IGNORECASE)
        self._templates.append((compiled_pattern, response))

    def match(self, message: str) -> Optional[str]:
        """
        Try to match message against templates.

        Args:
            message: User message

        Returns:
            Template response if matched, None otherwise
        """
        for pattern, response in self._templates:
            if pattern.search(message):
                return response

        return None

    def remove_template(self, pattern: str) -> bool:
        """
        Remove a template by pattern.

        Args:
            pattern: Pattern string to remove

        Returns:
            True if removed, False if not found
        """
        original_length = len(self._templates)
        self._templates = [
            (p, r) for p, r in self._templates if p.pattern != pattern
        ]
        return len(self._templates) < original_length

    def get_all_templates(self) -> List[Dict[str, str]]:
        """
        Get all templates.

        Returns:
            List of dicts with pattern and response
        """
        return [
            {"pattern": p.pattern, "response": r}
            for p, r in self._templates
        ]

    def clear_custom_templates(self) -> None:
        """Clear all custom templates (keep defaults)."""
        self._templates.clear()
        self._add_default_templates()
