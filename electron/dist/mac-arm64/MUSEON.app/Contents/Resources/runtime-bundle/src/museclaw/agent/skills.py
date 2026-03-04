"""Skill loader - loads skills from SKILL.md or BRIEF.md files.

Supports two skill definition formats:
- SKILL.md: MUSEON/DNA27 skills with YAML frontmatter (name, description, etc.)
- BRIEF.md: Legacy format with H2-section structure (Purpose, When to Use, etc.)

Skills are organized by category in data/skills/<skill-name>/.
- Core skills (Zeal-written) have CORE trust level
- Self-forged skills (ACSF) have VERIFIED trust level

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

    # Recognized skill definition filenames (priority order)
    SKILL_FILES = ["SKILL.md", "BRIEF.md"]

    def _find_skill_file(self, skill_dir: Path) -> Optional[Path]:
        """Find the skill definition file in a directory.

        Args:
            skill_dir: Skill directory to search

        Returns:
            Path to SKILL.md or BRIEF.md, or None
        """
        for filename in self.SKILL_FILES:
            path = skill_dir / filename
            if path.exists():
                return path
        return None

    def list_skills(self) -> List[str]:
        """List all available skills.

        Returns:
            List of skill names (directory names)
        """
        if not self.skills_dir.exists():
            return []

        skills = []
        for item in self.skills_dir.iterdir():
            if item.is_dir() and self._find_skill_file(item):
                skills.append(item.name)

        return sorted(skills)

    def load_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Load a skill by name.

        Args:
            skill_name: Name of the skill (directory name)

        Returns:
            Skill dict with parsed content, or None if not found/invalid
        """
        # Check cache first
        if skill_name in self._skills_cache:
            return self._skills_cache[skill_name]

        skill_dir = self.skills_dir / skill_name
        skill_file = self._find_skill_file(skill_dir)

        if not skill_file:
            return None

        # Parse based on format
        if skill_file.name == "SKILL.md":
            skill = self._parse_skill_md(skill_file)
        else:
            skill = self._parse_brief(skill_file)

        if skill is None:
            return None

        # Add metadata
        skill["name"] = skill_name
        skill["directory"] = str(skill_dir)
        skill["format"] = skill_file.name

        # For SKILL.md format, default trust_level to CORE if not set
        if "trust_level" not in skill:
            skill["trust_level"] = "CORE"

        # Validate skill
        if not self.validate_skill(skill):
            return None

        # Cache and return
        self._skills_cache[skill_name] = skill
        return skill

    def _parse_skill_md(self, skill_path: Path) -> Optional[Dict[str, Any]]:
        """Parse SKILL.md file with YAML frontmatter.

        SKILL.md format:
        ---
        name: skill-name
        description: What this skill does and when to trigger
        ---
        (markdown body with full skill instructions)

        Args:
            skill_path: Path to SKILL.md

        Returns:
            Parsed skill dict, or None if parsing fails
        """
        try:
            content = skill_path.read_text(encoding="utf-8")
        except Exception:
            return None

        skill: Dict[str, Any] = {}

        # Parse YAML frontmatter (between --- delimiters)
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1].strip()
                body = parts[2].strip()

                # Simple YAML parsing (key: value per line)
                for line in frontmatter.split("\n"):
                    line = line.strip()
                    if ":" in line and not line.startswith("#"):
                        key, _, value = line.partition(":")
                        key = key.strip()
                        value = value.strip()
                        if key and value:
                            skill[key] = value

                skill["body"] = body
                skill["purpose"] = skill.get("description", "")
        else:
            # No frontmatter — treat entire file as body
            skill["body"] = content
            # Try to extract purpose from first non-empty line
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    skill["purpose"] = line[:200]
                    break

        # Extract title from H1 if present
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if h1_match:
            skill["title"] = h1_match.group(1).strip()

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
        - Has a name
        - Has purpose or description or body
        - Trust level is valid (defaults to CORE for owner-provided skills)

        Args:
            skill: Skill dict

        Returns:
            True if valid
        """
        # Must have a name
        if "name" not in skill:
            return False

        # Must have some content (purpose, description, or body)
        has_content = any(
            skill.get(field)
            for field in ["purpose", "description", "body"]
        )
        if not has_content:
            return False

        # Valid trust levels
        # FORGED = 由 MuseClaw 自主搜尋外部 Skill 後經 DSE+ACSF 二次鍛造
        valid_trust_levels = ["CORE", "VERIFIED", "FORGED", "EXTERNAL", "UNTRUSTED"]
        trust_level = skill.get("trust_level", "CORE")

        if trust_level not in valid_trust_levels:
            return False

        # v2: CORE, VERIFIED, and FORGED (EXTERNAL/UNTRUSTED still blocked)
        if trust_level not in ["CORE", "VERIFIED", "FORGED"]:
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
