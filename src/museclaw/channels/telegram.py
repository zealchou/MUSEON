"""Telegram Channel Adapter using python-telegram-bot 20.x."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from museclaw.channels.base import ChannelAdapter, TrustLevel
from museclaw.gateway.message import InternalMessage

logger = logging.getLogger(__name__)


class TelegramAdapter(ChannelAdapter):
    """
    Telegram channel adapter using python-telegram-bot 20.x.

    Features:
    - Async polling for updates
    - Trusted user whitelist
    - Main session merging (all DMs go to one session)
    - Message queue for handling updates
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Telegram adapter.

        Args:
            config: Configuration dictionary containing:
                - bot_token: Telegram bot API token
                - trusted_user_ids: List of trusted user IDs (strings)
        """
        super().__init__(config)
        self.bot_token = config["bot_token"]
        self.trusted_user_ids = config.get("trusted_user_ids", [])

        self.application: Optional[Application] = None
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def start(self) -> None:
        """Start the Telegram bot and begin polling."""
        if self._running:
            return

        self.application = Application.builder().token(self.bot_token).build()

        # Register handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self.application.add_handler(CommandHandler("start", self._handle_start_command))

        # Start polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        self._running = True
        logger.info("TelegramAdapter started and polling for updates")

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if not self._running or not self.application:
            return

        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()

        self._running = False
        logger.info("TelegramAdapter stopped")

    async def _handle_message(self, update: Update, context: Any) -> None:
        """Handle incoming text message."""
        await self.message_queue.put(update)

    async def _handle_start_command(self, update: Update, context: Any) -> None:
        """Handle /start command."""
        await self.message_queue.put(update)

    async def receive(self) -> InternalMessage:
        """
        Receive a message from Telegram.

        Returns:
            InternalMessage: Unified message format

        Raises:
            ValueError: If update format is invalid
        """
        # For testing purposes, allow mock updates
        if hasattr(self, "_get_update"):
            update = self._get_update()
        else:
            # Wait for next update from queue
            update = await self.message_queue.get()

        if not update or not update.message:
            raise ValueError("Invalid Telegram update format")

        user_id = str(update.message.from_user.id)
        chat_id = update.message.chat.id
        content = update.message.text or ""
        timestamp = update.message.date

        # All DMs from owner/trusted users go to main session
        session_id = f"telegram_{chat_id}"

        trust_level = self.get_trust_level(user_id)

        return InternalMessage(
            source="telegram",
            session_id=session_id,
            user_id=user_id,
            content=content,
            timestamp=timestamp,
            trust_level=trust_level.value,
            metadata={
                "chat_id": chat_id,
                "message_id": update.message.message_id,
                "first_name": update.message.from_user.first_name,
                "username": update.message.from_user.username,
            },
        )

    async def send(self, message: InternalMessage) -> bool:
        """
        Send a message to Telegram.

        Args:
            message: InternalMessage to send

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            # For testing purposes, allow mock send
            if hasattr(self, "_send_telegram_message"):
                return self._send_telegram_message(message)

            if not self.application:
                logger.error("Telegram application not initialized")
                return False

            chat_id = message.metadata.get("chat_id")
            if not chat_id:
                logger.error("No chat_id in message metadata")
                return False

            await self.application.bot.send_message(chat_id=chat_id, text=message.content)
            return True

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def get_trust_level(self, user_id: str) -> TrustLevel:
        """
        Determine trust level for a Telegram user.

        Args:
            user_id: Telegram user ID

        Returns:
            TrustLevel: CORE if user is in trusted list, EXTERNAL otherwise
        """
        if user_id in self.trusted_user_ids:
            return TrustLevel.CORE
        return TrustLevel.EXTERNAL
