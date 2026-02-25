"""Electron Channel Adapter using IPC (Unix socket)."""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from museclaw.channels.base import ChannelAdapter, TrustLevel
from museclaw.gateway.message import InternalMessage

logger = logging.getLogger(__name__)


class ElectronAdapter(ChannelAdapter):
    """
    Electron channel adapter using Unix domain socket IPC.

    Features:
    - Unix socket for low-latency IPC
    - Always CORE trust level (local owner)
    - Single main session (electron_main)
    - Bidirectional communication for Dashboard

    Use cases:
    - Token Dashboard queries
    - Health monitoring
    - Real-time statistics
    - System commands
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Electron adapter.

        Args:
            config: Configuration dictionary containing:
                - ipc_socket_path: Path to Unix socket (e.g., /tmp/museclaw.sock)
                - owner_user_id: Owner's user ID
        """
        super().__init__(config)
        self.ipc_socket_path = config["ipc_socket_path"]
        self.owner_user_id = config.get("owner_user_id", "owner")

        self.server: Optional[asyncio.Server] = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._running = False

    async def start_server(self) -> None:
        """Start IPC server listening on Unix socket."""
        if self._running:
            return

        # Remove existing socket if it exists
        socket_path = Path(self.ipc_socket_path)
        if socket_path.exists():
            socket_path.unlink()

        # Create parent directory if needed
        socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Start Unix socket server
        self.server = await asyncio.start_unix_server(self._handle_client, path=self.ipc_socket_path)

        self._running = True
        logger.info(f"ElectronAdapter IPC server started on {self.ipc_socket_path}")

    async def stop_server(self) -> None:
        """Stop IPC server."""
        if not self._running or not self.server:
            return

        self.server.close()
        await self.server.wait_closed()

        # Clean up socket file
        socket_path = Path(self.ipc_socket_path)
        if socket_path.exists():
            socket_path.unlink()

        self._running = False
        logger.info("ElectronAdapter IPC server stopped")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Handle incoming client connection."""
        self.reader = reader
        self.writer = writer
        logger.info("Electron client connected")

    async def receive(self) -> InternalMessage:
        """
        Receive a message from Electron via IPC.

        Returns:
            InternalMessage: Unified message format

        Raises:
            ConnectionError: If IPC connection is not established
            ValueError: If message format is invalid
        """
        # For testing purposes, allow mock IPC read
        if hasattr(self, "_read_from_ipc"):
            ipc_data = self._read_from_ipc()
        else:
            if not self.reader:
                raise ConnectionError("IPC connection not established")

            # Read length-prefixed message
            try:
                length_bytes = await self.reader.readexactly(4)
                message_length = int.from_bytes(length_bytes, byteorder="big")

                message_bytes = await self.reader.readexactly(message_length)
                ipc_data = json.loads(message_bytes.decode("utf-8"))
            except Exception as e:
                raise ValueError(f"Invalid IPC message format: {e}")

        # Parse IPC message
        user_id = ipc_data.get("user_id", self.owner_user_id)
        content = ipc_data.get("content", "")
        timestamp_str = ipc_data.get("timestamp")

        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = datetime.now()

        # Electron always uses main session
        session_id = "electron_main"

        return InternalMessage(
            source="electron",
            session_id=session_id,
            user_id=user_id,
            content=content,
            timestamp=timestamp,
            trust_level=TrustLevel.CORE.value,
            metadata={
                "ipc_socket": self.ipc_socket_path,
                "raw_data": ipc_data,
            },
        )

    async def send(self, message: InternalMessage) -> bool:
        """
        Send a message to Electron via IPC.

        Args:
            message: InternalMessage to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # For testing purposes, allow mock IPC write
            if hasattr(self, "_write_to_ipc"):
                return self._write_to_ipc(message)

            if not self.writer:
                logger.error("IPC writer not available")
                return False

            # Prepare response data
            response_data = {
                "content": message.content,
                "timestamp": message.timestamp.isoformat(),
                "metadata": message.metadata,
            }

            # Send length-prefixed message
            response_bytes = json.dumps(response_data).encode("utf-8")
            length_bytes = len(response_bytes).to_bytes(4, byteorder="big")

            self.writer.write(length_bytes + response_bytes)
            await self.writer.drain()

            return True

        except Exception as e:
            logger.error(f"Failed to send IPC message: {e}")
            return False

    def get_trust_level(self, user_id: str) -> TrustLevel:
        """
        Electron is always CORE trust level (local owner).

        Args:
            user_id: User identifier (ignored)

        Returns:
            TrustLevel: Always CORE
        """
        return TrustLevel.CORE

    async def send_json(self, data: Dict[str, Any]) -> bool:
        """
        Send raw JSON data to Electron.

        Convenience method for Dashboard queries.

        Args:
            data: JSON-serializable dictionary

        Returns:
            bool: True if sent successfully
        """
        try:
            if not self.writer:
                return False

            response_bytes = json.dumps(data).encode("utf-8")
            length_bytes = len(response_bytes).to_bytes(4, byteorder="big")

            self.writer.write(length_bytes + response_bytes)
            await self.writer.drain()

            return True

        except Exception as e:
            logger.error(f"Failed to send JSON via IPC: {e}")
            return False
