"""Session Manager - Ensures serial processing per session."""

import asyncio
import contextlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manages session locks to ensure serial message processing.

    Each session can only process one message at a time. If a new message
    arrives while a session is processing, it must wait.

    Also tracks session activity for automatic cleanup of stale sessions.
    """

    def __init__(self, metadata_dir: Optional[Path] = None) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._processing: Dict[str, bool] = {}
        self._metadata_dir = metadata_dir or Path.home() / ".museon" / "session_metadata"
        self._metadata_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_file = self._metadata_dir / "session_metadata.json"
        self._metadata: Dict[str, Dict] = self._load_metadata()

    def _load_metadata(self) -> Dict[str, Dict]:
        """Load session metadata from disk."""
        if self._metadata_file.exists():
            try:
                with open(self._metadata_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load session metadata: {e}")
        return {}

    def _save_metadata(self) -> None:
        """Persist session metadata to disk."""
        try:
            with open(self._metadata_file, "w") as f:
                json.dump(self._metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save session metadata: {e}")

    def _update_last_activity(self, session_id: str) -> None:
        """Update the last activity timestamp for a session."""
        now = datetime.now(timezone.utc).isoformat()
        if session_id not in self._metadata:
            self._metadata[session_id] = {"created_at": now, "last_activity": now}
        else:
            self._metadata[session_id]["last_activity"] = now
        self._save_metadata()

    async def acquire(self, session_id: str) -> bool:
        """
        Attempt to acquire processing lock for a session.

        Args:
            session_id: The session identifier

        Returns:
            True if lock acquired, False if session is already processing
        """
        # Create lock if it doesn't exist
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()

        # Try to acquire lock (non-blocking check)
        lock = self._locks[session_id]

        if lock.locked():
            return False

        await lock.acquire()
        self._processing[session_id] = True
        self._update_last_activity(session_id)
        return True

    async def release(self, session_id: str) -> None:
        """
        Release processing lock for a session.

        Args:
            session_id: The session identifier
        """
        if session_id in self._locks:
            self._processing[session_id] = False
            self._locks[session_id].release()
            self._update_last_activity(session_id)

    def is_processing(self, session_id: str) -> bool:
        """
        Check if a session is currently processing.

        Args:
            session_id: The session identifier

        Returns:
            True if session is processing, False otherwise
        """
        return self._processing.get(session_id, False)

    async def wait_and_acquire(self, session_id: str, timeout: Optional[float] = None) -> bool:
        """
        Wait for lock to become available and acquire it.

        Args:
            session_id: The session identifier
            timeout: Maximum time to wait in seconds

        Returns:
            True if lock acquired, False if timeout
        """
        # Create lock if it doesn't exist
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()

        try:
            async with asyncio.timeout(timeout) if timeout else contextlib.nullcontext():
                await self._locks[session_id].acquire()
                self._processing[session_id] = True
                self._update_last_activity(session_id)
                return True
        except asyncio.TimeoutError:
            return False

    def get_stale_sessions(self, days: int = 3) -> List[str]:
        """
        Get list of session IDs that haven't been active for more than N days.

        Args:
            days: Number of days of inactivity threshold (default: 3)

        Returns:
            List of stale session IDs
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)
        stale_sessions = []

        for session_id, metadata in self._metadata.items():
            last_activity_str = metadata.get("last_activity")
            if not last_activity_str:
                continue

            try:
                last_activity = datetime.fromisoformat(last_activity_str)
                if last_activity < cutoff_time:
                    stale_sessions.append(session_id)
            except (ValueError, TypeError):
                logger.warning(f"Invalid timestamp for session {session_id}: {last_activity_str}")

        return stale_sessions

    async def cleanup_stale_sessions(self, days: int = 3) -> Dict[str, any]:
        """
        Clean up stale sessions (no activity for N days).

        Removes:
        - Session lock from memory
        - Session from processing dict
        - Session metadata from disk

        Args:
            days: Number of days of inactivity threshold (default: 3)

        Returns:
            Cleanup report dict with counts
        """
        stale = self.get_stale_sessions(days)

        removed_count = 0
        for session_id in stale:
            try:
                # Remove lock from memory
                if session_id in self._locks:
                    del self._locks[session_id]
                # Remove processing flag
                if session_id in self._processing:
                    del self._processing[session_id]
                # Remove metadata
                if session_id in self._metadata:
                    del self._metadata[session_id]

                logger.info(f"Released stale session: {session_id}")
                removed_count += 1
            except Exception as e:
                logger.error(f"Failed to cleanup session {session_id}: {e}")

        # Persist metadata changes
        self._save_metadata()

        return {
            "cleaned_at": datetime.now(timezone.utc).isoformat(),
            "threshold_days": days,
            "total_sessions": len(self._metadata),
            "removed_count": removed_count,
            "stale_sessions": stale,
        }
