"""Session Manager - Ensures serial processing per session."""

import asyncio
from typing import Dict, Optional


class SessionManager:
    """
    Manages session locks to ensure serial message processing.

    Each session can only process one message at a time. If a new message
    arrives while a session is processing, it must wait.
    """

    def __init__(self) -> None:
        self._locks: Dict[str, asyncio.Lock] = {}
        self._processing: Dict[str, bool] = {}

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
            async with asyncio.timeout(timeout) if timeout else asyncio.nullcontext():
                await self._locks[session_id].acquire()
                self._processing[session_id] = True
                return True
        except asyncio.TimeoutError:
            return False
