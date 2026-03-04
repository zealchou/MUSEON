"""Base Channel Adapter interface."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict

from museon.gateway.message import InternalMessage


class TrustLevel(str, Enum):
    """Trust levels for different channels and users."""

    CORE = "core"  # Owner/trusted users via Telegram/Electron
    VERIFIED = "verified"  # Verified webhook sources
    EXTERNAL = "external"  # Public users (LINE Bot, etc.)
    UNTRUSTED = "untrusted"  # Unknown/suspicious sources


class ChannelAdapter(ABC):
    """
    Abstract base class for all channel adapters.

    Each channel adapter is responsible for:
    1. Receiving messages from external platforms
    2. Converting to InternalMessage format
    3. Sending messages back to the platform
    4. Determining trust level for the source
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the channel adapter.

        Args:
            config: Channel-specific configuration dictionary
        """
        self.config = config

    @abstractmethod
    async def receive(self) -> InternalMessage:
        """
        Receive a message from the external platform.

        This method should:
        1. Poll/wait for incoming message from the platform
        2. Convert platform-specific format to InternalMessage
        3. Determine appropriate trust_level
        4. Return the unified InternalMessage

        Returns:
            InternalMessage: Unified message format

        Raises:
            ValueError: If message format is invalid
            ConnectionError: If connection to platform fails
        """
        pass

    @abstractmethod
    async def send(self, message: InternalMessage) -> bool:
        """
        Send a message to the external platform.

        This method should:
        1. Convert InternalMessage to platform-specific format
        2. Send via platform API/protocol
        3. Handle platform-specific errors

        Args:
            message: InternalMessage to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_trust_level(self, user_id: str) -> TrustLevel:
        """
        Determine trust level for a given user_id.

        Args:
            user_id: User identifier from the platform

        Returns:
            TrustLevel: Trust level for this user
        """
        pass
