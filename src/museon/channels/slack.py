"""Slack Channel Adapter — Bolt SDK Socket Mode 整合.

透過 Slack Bolt SDK 的 Socket Mode 接收訊息：
- WebSocket 連線（無需公網 URL）
- 訊息轉為 InternalMessage 統一格式
- 支援 Channel / DM 雙向通訊
- 透過 EventBus 發布 CHANNEL_MESSAGE_RECEIVED / CHANNEL_MESSAGE_SENT

依賴：
- slack_bolt (pip install slack-bolt)
- slack_sdk (由 slack_bolt 附帶)

環境變數：
- SLACK_BOT_TOKEN: Slack Bot User OAuth Token (xoxb-...)
- SLACK_APP_TOKEN: Slack App-Level Token (xapp-...) for Socket Mode
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from museon.channels.base import ChannelAdapter, TrustLevel
from museon.gateway.message import InternalMessage

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))


class SlackAdapter(ChannelAdapter):
    """Slack 通道適配器 — 使用 Bolt SDK Socket Mode.

    Features:
    - Socket Mode WebSocket（不需公開 URL）
    - 訊息佇列 + InternalMessage 轉換
    - 信任層級由設定中的 trusted_user_ids 決定
    - EventBus 事件發布
    """

    def __init__(self, config: Dict[str, Any], event_bus: Any = None) -> None:
        """
        Args:
            config: 設定字典，含:
                - bot_token: Slack Bot OAuth Token (xoxb-...)
                - app_token: Slack App-Level Token (xapp-...)
                - trusted_user_ids: 受信任使用者 ID 列表
                - default_channel: 預設發送頻道 ID
            event_bus: EventBus 實例（可選）
        """
        super().__init__(config)
        self._bot_token: str = config.get("bot_token", "")
        self._app_token: str = config.get("app_token", "")
        self._trusted_user_ids: List[str] = config.get("trusted_user_ids", [])
        self._default_channel: str = config.get("default_channel", "")
        self._event_bus = event_bus

        self._app: Any = None  # slack_bolt.async_app.AsyncApp
        self._handler: Any = None  # slack_bolt.adapter.socket_mode.async_handler
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running: bool = False
        self._web_client: Any = None  # slack_sdk.web.async_client.AsyncWebClient

    async def start(self) -> None:
        """啟動 Socket Mode WebSocket 監聽."""
        if self._running:
            return

        if not self._bot_token or not self._app_token:
            logger.error("Slack bot_token and app_token are required")
            return

        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import (
                AsyncSocketModeHandler,
            )
        except ImportError:
            logger.error(
                "slack-bolt is required: pip install slack-bolt"
            )
            return

        try:
            self._app = AsyncApp(token=self._bot_token)
            self._web_client = self._app.client

            # 註冊訊息事件處理器
            @self._app.event("message")
            async def _handle_message_event(event, say):
                await self._on_message(event)

            # 註冊 app_mention 事件（@bot）
            @self._app.event("app_mention")
            async def _handle_mention_event(event, say):
                await self._on_message(event)

            # 啟動 Socket Mode
            self._handler = AsyncSocketModeHandler(
                self._app, self._app_token
            )
            await self._handler.start_async()

            self._running = True
            logger.info("SlackAdapter started (Socket Mode)")

        except Exception as e:
            logger.error(f"SlackAdapter start failed: {e}")
            self._running = False

    async def stop(self) -> None:
        """停止 Socket Mode 監聽."""
        if not self._running:
            return

        try:
            if self._handler:
                await self._handler.close_async()
        except Exception as e:
            logger.error(f"SlackAdapter stop error: {e}")
        finally:
            self._running = False
            self._app = None
            self._handler = None
            logger.info("SlackAdapter stopped")

    async def receive(self) -> InternalMessage:
        """從內部佇列取出已轉換的訊息.

        Returns:
            InternalMessage: 統一訊息格式

        Raises:
            asyncio.CancelledError: 佇列等待被取消
        """
        msg = await self._message_queue.get()
        return msg

    async def send(self, message: InternalMessage) -> bool:
        """發送訊息到 Slack 頻道或 DM.

        Args:
            message: 要發送的 InternalMessage

        Returns:
            bool: 發送是否成功
        """
        if not self._web_client:
            logger.error("Slack web client not initialized")
            return False

        channel = message.metadata.get("channel_id", self._default_channel)
        if not channel:
            logger.error("No target channel for Slack message")
            return False

        try:
            # thread_ts 用於回覆特定執行緒
            thread_ts = message.metadata.get("thread_ts")
            kwargs: Dict[str, Any] = {
                "channel": channel,
                "text": message.content,
            }
            if thread_ts:
                kwargs["thread_ts"] = thread_ts

            await self._web_client.chat_postMessage(**kwargs)

            # 發布送出事件
            try:
                if self._event_bus is not None:
                    from museon.core.event_bus import CHANNEL_MESSAGE_SENT
                    self._event_bus.publish(CHANNEL_MESSAGE_SENT, {
                        "channel": "slack",
                        "channel_id": channel,
                        "content_length": len(message.content),
                        "timestamp": datetime.now(TZ8).isoformat(),
                    })
            except Exception as e:
                logger.error(f"EventBus publish CHANNEL_MESSAGE_SENT failed: {e}")

            return True

        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False

    def get_trust_level(self, user_id: str) -> TrustLevel:
        """根據設定判斷信任層級.

        Args:
            user_id: Slack 使用者 ID

        Returns:
            TrustLevel: 信任等級
        """
        return self.determine_trust_level(user_id)

    def determine_trust_level(self, source: str) -> TrustLevel:
        """根據使用者 ID 和設定判斷信任層級.

        Args:
            source: Slack 使用者 ID

        Returns:
            TrustLevel: CORE / VERIFIED / EXTERNAL
        """
        if source in self._trusted_user_ids:
            return TrustLevel.CORE
        # Slack workspace 內的使用者至少是 VERIFIED
        return TrustLevel.VERIFIED

    async def _on_message(self, event: Dict[str, Any]) -> None:
        """Slack 訊息事件回呼 — 轉為 InternalMessage 並入佇列.

        Args:
            event: Slack 事件字典
        """
        # 忽略 bot 自己的訊息
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        user_id = event.get("user", "unknown")
        text = event.get("text", "")
        channel_id = event.get("channel", "")
        thread_ts = event.get("thread_ts", event.get("ts", ""))
        ts = event.get("ts", "")

        if not text.strip():
            return

        # 時間戳轉換（Slack ts 是 Unix 浮點字串）
        try:
            msg_time = datetime.fromtimestamp(float(ts), tz=TZ8)
        except (ValueError, OSError):
            msg_time = datetime.now(TZ8)

        trust_level = self.determine_trust_level(user_id)

        session_id = f"slack_{channel_id}_{user_id}"

        internal_msg = InternalMessage(
            source="slack",
            session_id=session_id,
            user_id=user_id,
            content=text,
            timestamp=msg_time,
            trust_level=trust_level.value,
            metadata={
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "ts": ts,
                "channel_type": event.get("channel_type", ""),
            },
        )

        await self._message_queue.put(internal_msg)

        # 發布接收事件
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import CHANNEL_MESSAGE_RECEIVED
                self._event_bus.publish(CHANNEL_MESSAGE_RECEIVED, {
                    "channel": "slack",
                    "user_id": user_id,
                    "content_length": len(text),
                    "trust_level": trust_level.value,
                    "timestamp": msg_time.isoformat(),
                })
        except Exception as e:
            logger.error(f"EventBus publish CHANNEL_MESSAGE_RECEIVED failed: {e}")

    # ── Status ──

    @property
    def is_running(self) -> bool:
        """適配器是否正在運行."""
        return self._running

    def get_status(self) -> Dict[str, Any]:
        """取得適配器狀態."""
        return {
            "running": self._running,
            "queue_size": self._message_queue.qsize(),
            "configured": bool(self._bot_token and self._app_token),
            "default_channel": self._default_channel,
        }
