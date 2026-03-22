"""Base Channel Adapter interface.

v10.0: Added present_choices() for cross-channel interactive choices.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
import logging
from typing import Any, Dict, TYPE_CHECKING

from museon.gateway.message import InternalMessage

if TYPE_CHECKING:
    from museon.gateway.interaction import InteractionQueue
    from museon.gateway.message import InteractionRequest

logger = logging.getLogger(__name__)


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

    # ── v10.0: 跨通道互動選項 ──

    async def present_choices(
        self,
        chat_id: str,
        request: "InteractionRequest",
        interaction_queue: "InteractionQueue",
    ) -> None:
        """呈現互動選項給使用者.

        子類覆寫此方法以使用平台原生 UI（InlineKeyboard、Button、Quick Reply）。
        使用者回應後，子類呼叫 interaction_queue.resolve() 觸發回應。

        預設實作：降級為純文字編號清單（fallback for all adapters）。

        Args:
            chat_id: 目標聊天室 ID
            request: InteractionRequest 物件
            interaction_queue: InteractionQueue 實例（用於 resolve 回調）
        """
        # 建構純文字版本
        header = f"【{request.header}】\n" if request.header else ""
        multi_hint = "（可多選）" if request.multi_select else ""
        text = f"{header}{request.question}{multi_hint}\n\n"

        for i, opt in enumerate(request.options, 1):
            text += f"  {i}. {opt.label}"
            if opt.description:
                text += f" — {opt.description}"
            text += "\n"

        if request.allow_free_text:
            text += "\n請回覆數字選擇，或直接輸入文字。"

        # 透過 send() 發送純文字
        try:
            msg = InternalMessage(
                source="system",
                session_id="interaction",
                user_id="system",
                content=text,
                timestamp=datetime.now(),
                trust_level="core",
                metadata={"chat_id": chat_id, "interaction_id": request.question_id},
            )
            await self.send(msg)
        except Exception as e:
            logger.error(f"ChannelAdapter.present_choices fallback failed: {e}")
