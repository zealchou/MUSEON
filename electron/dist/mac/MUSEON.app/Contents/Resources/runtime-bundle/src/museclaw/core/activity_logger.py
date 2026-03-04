"""
Activity Logger — Append-only JSONL event log for MUSEON Dashboard.

Subscribes to EventBus events and persists them to activity_log.jsonl.
Provides tail-read for the Evolution tab's "Activity Log" section.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ActivityLogger:
    """Append-only JSONL logger for EventBus events."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.log_path = self.data_dir / "activity_log.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        event_type: str,
        data: Any = None,
        source: str = "system",
    ) -> None:
        """Append one event to the activity log.

        Args:
            event_type: EventBus event name (e.g. BRAIN_RESPONSE_COMPLETE)
            data: Arbitrary payload (must be JSON-serialisable)
            source: Origin identifier (e.g. 'brain', 'nightly', 'pulse')
        """
        entry = {
            "ts": datetime.now().isoformat(),
            "event": event_type,
            "source": source,
            "data": _safe_serialise(data),
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("Activity log write failed: %s", exc)

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Read the last *limit* entries (tail-read).

        Returns:
            List of event dicts, newest first.
        """
        if not self.log_path.exists():
            return []
        try:
            lines = self.log_path.read_text(encoding="utf-8").strip().split("\n")
            lines = [ln for ln in lines if ln.strip()]
            tail = lines[-limit:] if len(lines) > limit else lines
            events = []
            for ln in reversed(tail):  # newest first
                try:
                    events.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
            return events
        except Exception as exc:
            logger.warning("Activity log read failed: %s", exc)
            return []

    def today_events(self) -> List[Dict[str, Any]]:
        """Read all events from today (for daily summary generation)."""
        today_prefix = datetime.now().date().isoformat()
        if not self.log_path.exists():
            return []
        try:
            events = []
            for ln in self.log_path.read_text(encoding="utf-8").strip().split("\n"):
                if not ln.strip():
                    continue
                try:
                    entry = json.loads(ln)
                    if entry.get("ts", "").startswith(today_prefix):
                        events.append(entry)
                except json.JSONDecodeError:
                    pass
            return events
        except Exception as exc:
            logger.warning("Activity log today read failed: %s", exc)
            return []


def _safe_serialise(obj: Any) -> Any:
    """Ensure *obj* is JSON-serialisable; fall back to str()."""
    if obj is None:
        return None
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except (TypeError, ValueError):
        return str(obj)
