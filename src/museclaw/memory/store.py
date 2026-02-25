"""Markdown-based memory storage for MuseClaw.

Stores memories in human-readable Markdown format organized by date and channel.
This allows the boss to read MuseClaw's memories directly.

Directory structure:
    memory/
      2026/
        02/
          25/
            meta-thinking.md
            event.md
            outcome.md
            user-reaction.md
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import json


class MemoryStore:
    """Markdown-based memory storage system."""

    def __init__(self, base_path: str = "data/memory"):
        """Initialize memory store.

        Args:
            base_path: Base directory for storing memories
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def get_memory_path(self, channel: str, timestamp: datetime) -> Path:
        """Get the file path for a memory entry.

        Organizes by year/month/day/channel.md

        Args:
            channel: Channel name (meta-thinking, event, outcome, user-reaction)
            timestamp: Timestamp of the entry

        Returns:
            Path object for the memory file
        """
        year = timestamp.strftime("%Y")
        month = timestamp.strftime("%m")
        day = timestamp.strftime("%d")

        # Create directory structure: memory/2026/02/25/
        day_dir = self.base_path / year / month / day
        day_dir.mkdir(parents=True, exist_ok=True)

        # File name: meta-thinking.md
        filename = f"{channel}.md"
        return day_dir / filename

    def write(self, entry: Dict[str, Any]) -> bool:
        """Write a memory entry to Markdown file.

        Args:
            entry: Memory entry with channel, content, timestamp

        Returns:
            True if write succeeded
        """
        channel = entry.get("channel")
        timestamp_str = entry.get("timestamp")
        content = entry.get("content", {})

        if not channel or not timestamp_str:
            return False

        # Parse timestamp
        try:
            if isinstance(timestamp_str, str):
                timestamp = datetime.fromisoformat(timestamp_str)
            else:
                timestamp = timestamp_str
        except (ValueError, AttributeError):
            timestamp = datetime.now()

        # Get file path
        file_path = self.get_memory_path(channel, timestamp)

        # Format as Markdown
        markdown_entry = self._format_as_markdown(entry, timestamp)

        # Append to file (or create if doesn't exist)
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                if file_path.stat().st_size == 0:
                    # New file, add header
                    header = f"# {channel.replace('-', ' ').title()}\n\n"
                    f.write(header)

                f.write(markdown_entry)
                f.write("\n\n---\n\n")

            return True

        except Exception as e:
            print(f"Error writing memory: {e}")
            return False

    def _format_as_markdown(self, entry: Dict[str, Any], timestamp: datetime) -> str:
        """Format memory entry as Markdown.

        Args:
            entry: Memory entry dict
            timestamp: Entry timestamp

        Returns:
            Markdown-formatted string
        """
        content = entry.get("content", {})
        trust_level = entry.get("trust_level", "UNKNOWN")

        # Time header
        time_str = timestamp.strftime("%H:%M:%S")
        md = f"## {time_str}\n\n"

        # Trust level badge
        md += f"**Trust Level:** {trust_level}\n\n"

        # Content (format varies by channel)
        if isinstance(content, dict):
            for key, value in content.items():
                # Format key nicely
                formatted_key = key.replace("_", " ").title()
                md += f"**{formatted_key}:** {value}\n\n"
        else:
            md += f"{content}\n\n"

        # Metadata
        if "confidence" in entry:
            md += f"**Confidence:** {entry['confidence']:.2f}\n\n"

        if "task_id" in entry:
            md += f"**Task ID:** {entry['task_id']}\n\n"

        return md

    def read(self, channel: str, date: str) -> List[Dict[str, Any]]:
        """Read memories from a specific channel and date.

        Args:
            channel: Channel name
            date: Date string in format YYYY-MM-DD

        Returns:
            List of memory entries
        """
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return []

        file_path = self.get_memory_path(channel, date_obj)

        if not file_path.exists():
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Parse markdown into entries
            entries = self._parse_markdown(content)
            return entries

        except Exception as e:
            print(f"Error reading memory: {e}")
            return []

    def _parse_markdown(self, markdown: str) -> List[Dict[str, Any]]:
        """Parse Markdown content into memory entries.

        Args:
            markdown: Markdown content

        Returns:
            List of parsed entries
        """
        # Split by horizontal rule
        sections = markdown.split("---")

        entries = []
        for section in sections:
            section = section.strip()
            if not section or section.startswith("#"):
                continue

            # Extract data from markdown
            entry = {}

            # Simple parsing - look for patterns like "**Key:** value"
            lines = section.split("\n")
            for line in lines:
                if "**" in line and ":**" in line:
                    # Extract key-value
                    start = line.find("**") + 2
                    end = line.find(":**")
                    if start > 1 and end > start:
                        key = line[start:end].lower().replace(" ", "_")
                        value = line[end + 3:].strip()
                        entry[key] = value

            if entry:
                entries.append(entry)

        return entries

    def read_recent(
        self, channel: str, days: int = 7
    ) -> List[Dict[str, Any]]:
        """Read recent memories from a channel.

        Args:
            channel: Channel name
            days: Number of days to look back

        Returns:
            List of recent memory entries
        """
        entries = []
        now = datetime.now()

        for i in range(days):
            date = now - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            day_entries = self.read(channel, date_str)
            entries.extend(day_entries)

        return entries

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get statistics about memory storage.

        Returns:
            Dict with stats: total files, total size, entries per channel
        """
        stats = {
            "total_files": 0,
            "total_size_bytes": 0,
            "channels": {},
        }

        # Walk through all memory files
        for file_path in self.base_path.rglob("*.md"):
            stats["total_files"] += 1
            stats["total_size_bytes"] += file_path.stat().st_size

            # Count per channel
            channel = file_path.stem
            if channel not in stats["channels"]:
                stats["channels"][channel] = {"files": 0, "size_bytes": 0}

            stats["channels"][channel]["files"] += 1
            stats["channels"][channel]["size_bytes"] += file_path.stat().st_size

        return stats


# Import timedelta for read_recent
from datetime import timedelta
