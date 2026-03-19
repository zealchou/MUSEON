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

from museon.core.data_bus import DataContract, StoreSpec, StoreEngine, TTLTier

logger = logging.getLogger(__name__)


class ActivityLogger(DataContract):
    """Append-only JSONL logger for EventBus events."""

    @classmethod
    def store_spec(cls) -> StoreSpec:
        return StoreSpec(
            name="activity_logger",
            engine=StoreEngine.JSONL,
            ttl=TTLTier.SHORT,
            write_mode="append_only",
            description="EventBus 事件 JSONL 日誌",
            tables=["activity_log.jsonl"],
        )

    def health_check(self) -> Dict[str, Any]:
        try:
            size = self.log_path.stat().st_size if self.log_path.exists() else 0
            return {"status": "ok", "size_bytes": size}
        except Exception as e:
            return {"status": "error", "error": str(e)}

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
                except json.JSONDecodeError as e:
                    logger.debug(f"[ACTIVITY_LOGGER] JSON failed (degraded): {e}")
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
                except json.JSONDecodeError as e:
                    logger.debug(f"[ACTIVITY_LOGGER] JSON failed (degraded): {e}")
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
