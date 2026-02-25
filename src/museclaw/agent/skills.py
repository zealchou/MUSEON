"""Skill loader - loads skills from BRIEF.md files.

Based on plan-v7.md:
- Each skill has a directory with BRIEF.md
- BRIEF.md contains: Purpose, When to Use, Tools Required, Trust Level
- Skills are organized by category
- Self-forged skills (ACSF) have VERIFIED trust level
- Core skills (Zeal-written) have CORE trust level

Security: Only CORE and VERIFIED skills loaded in v1 (no EXTERNAL/UNTRUSTED).
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import re


class SkillLoader:
    """Loads and manages skills."""

    def __init__(self, skills_dir: str = "data/skills"):
        """Initialize skill loader.

        Args:
            skills_dir: Directory containing skill subdirectories
        """
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        # Loaded skills cache
        self._skills_cache = {}

    def list_skills(self) -> List[str]:
        """List all available skills.

        Returns:
            List of skill names (directory names)
        """
        if not self.skills_dir.exists():
            return []

        skills = []
        for item in self.skills_dir.iterdir():
            if item.is_dir() and (item / "BRIEF.md").exists():
                skills.append(item.name)

        return skills

    def load_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Load a skill by name.

        Args:
            skill_name: Name of the skill (directory name)

        Returns:
            Skill dict with parsed BRIEF.md, or None if not found/invalid
        """
        # Check cache first
        if skill_name in self._skills_cache:
            return self._skills_cache[skill_name]

        skill_dir = self.skills_dir / skill_name
        brief_path = skill_dir / "BRIEF.md"

        if not brief_path.exists():
            return None

        # Parse BRIEF.md
        skill = self._parse_brief(brief_path)
        if skill is None:
            return None

        # Add metadata
        skill["name"] = skill_name
        skill["directory"] = str(skill_dir)

        # Validate skill
        if not self.validate_skill(skill):
            return None

        # Cache and return
        self._skills_cache[skill_name] = skill
        return skill

    def _parse_brief(self, brief_path: Path) -> Optional[Dict[str, Any]]:
        """Parse BRIEF.md file.

        Expected format:
        # Skill Name

        ## Purpose
        Description of what this skill does

        ## When to Use
        - Situation 1
        - Situation 2

        ## Tools Required
        - tool_name_1
        - tool_name_2

        ## Trust Level
        CORE|VERIFIED|EXTERNAL|UNTRUSTED

        Args:
            brief_path: Path to BRIEF.md

        Returns:
            Parsed skill dict, or None if parsing fails
        """
        try:
            content = brief_path.read_text(encoding="utf-8")
        except Exception:
            return None

        skill = {}

        # Parse sections using markdown headers
        sections = self._split_into_sections(content)

        # Extract skill name from H1
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if h1_match:
            skill["title"] = h1_match.group(1).strip()

        # Extract Purpose
        if "purpose" in sections:
            skill["purpose"] = sections["purpose"].strip()

        # Extract When to Use
        if "when to use" in sections:
            when_to_use = []
            for line in sections["when to use"].split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    when_to_use.append(line[1:].strip())
            skill["when_to_use"] = when_to_use

        # Extract Tools Required
        if "tools required" in sections:
            tools = []
            for line in sections["tools required"].split("\n"):
                line = line.strip()
                if line.startswith("-") or line.startswith("*"):
                    tool_name = line[1:].strip()
                    # Remove backticks if present
                    tool_name = tool_name.replace("`", "")
                    tools.append(tool_name)
            skill["tools_required"] = tools

        # Extract Trust Level
        if "trust level" in sections:
            trust_level = sections["trust level"].strip().upper()
            skill["trust_level"] = trust_level

        return skill

    def _split_into_sections(self, content: str) -> Dict[str, str]:
        """Split markdown content into sections by H2 headers.

        Args:
            content: Markdown content

        Returns:
            Dict mapping section names (lowercased) to content
        """
        sections = {}
        current_section = None
        current_content = []

        for line in content.split("\n"):
            # Check for H2 header
            h2_match = re.match(r"^##\s+(.+)$", line)
            if h2_match:
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content)

                # Start new section
                current_section = h2_match.group(1).strip().lower()
                current_content = []
            else:
                # Add to current section
                if current_section:
                    current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content)

        return sections

    def validate_skill(self, skill: Dict[str, Any]) -> bool:
        """Validate a loaded skill.

        Checks:
        - Has required fields
        - Trust level is valid
        - Trust level is CORE or VERIFIED (v1 restriction)

        Args:
            skill: Skill dict

        Returns:
            True if valid
        """
        # Required fields
        required_fields = ["name", "purpose", "trust_level"]
        for field in required_fields:
            if field not in skill:
                return False

        # Valid trust levels
        valid_trust_levels = ["CORE", "VERIFIED", "EXTERNAL", "UNTRUSTED"]
        trust_level = skill.get("trust_level", "")

        if trust_level not in valid_trust_levels:
            return False

        # v1 restriction: Only CORE and VERIFIED
        if trust_level not in ["CORE", "VERIFIED"]:
            return False

        return True

    def get_skills_by_trust_level(
        self, trust_level: str
    ) -> List[Dict[str, Any]]:
        """Get all skills with a specific trust level.

        Args:
            trust_level: Trust level to filter by

        Returns:
            List of skills
        """
        skills = []

        for skill_name in self.list_skills():
            skill = self.load_skill(skill_name)
            if skill and skill.get("trust_level") == trust_level:
                skills.append(skill)

        return skills

    def search_skills(self, query: str) -> List[Dict[str, Any]]:
        """Search skills by query string.

        Searches in: purpose, when_to_use, skill name

        Args:
            query: Search query

        Returns:
            List of matching skills
        """
        query_lower = query.lower()
        matches = []

        for skill_name in self.list_skills():
            skill = self.load_skill(skill_name)
            if not skill:
                continue

            # Search in name
            if query_lower in skill.get("name", "").lower():
                matches.append(skill)
                continue

            # Search in purpose
            if query_lower in skill.get("purpose", "").lower():
                matches.append(skill)
                continue

            # Search in when_to_use
            when_to_use = skill.get("when_to_use", [])
            for item in when_to_use:
                if query_lower in item.lower():
                    matches.append(skill)
                    break

        return matches

    def reload_skills(self):
        """Reload all skills from disk (clear cache)."""
        self._skills_cache = {}
