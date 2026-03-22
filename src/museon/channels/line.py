"""LINE Channel Adapter — line-bot-sdk v3 整合.

v10.0: 新增 LINE 通道適配器，支援：
- 訊息接收（Webhook）與發送（Push/Reply）
- Quick Reply + Flex Message 互動選項
- Postback 回調處理
- 信任層級管理

依賴：
- line-bot-sdk v3 (pip install line-bot-sdk)

環境變數：
- LINE_CHANNEL_ACCESS_TOKEN: LINE Bot Channel Access Token
- LINE_CHANNEL_SECRET: LINE Bot Channel Secret

Webhook：
- 需在 server.py 新增 /webhook/line 端點
- LINE Developers Console 設定 Webhook URL
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import base64
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from museon.channels.base import ChannelAdapter, TrustLevel
from museon.gateway.message import InternalMessage

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))


class LINEAdapter(ChannelAdapter):
    """LINE 通道適配器 — 使用 line-bot-sdk v3.

    Features:
    - Webhook 訊息接收
    - Push Message 發送（主動推送）
    - Quick Reply（≤ 13 選項）+ Flex Message（> 13 或富文本）互動選項
    - Postback 回調處理（InteractionRequest）
    - 信任層級管理
    """

    def __init__(self, config: Dict[str, Any], event_bus: Any = None) -> None:
        """
        Args:
            config: 設定字典，含:
                - channel_access_token: LINE Channel Access Token
                - channel_secret: LINE Channel Secret
                - trusted_user_ids: 受信任使用者 ID 列表
            event_bus: EventBus 實例（可選）
        """
        super().__init__(config)
        self._access_token: str = config.get("channel_access_token", "")
        self._channel_secret: str = config.get("channel_secret", "")
        self._trusted_user_ids: List[str] = config.get("trusted_user_ids", [])
        self._event_bus = event_bus

        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running: bool = False

        # v10.0: InteractionRequest
        self._interaction_queue = None
        self._api = None  # MessagingApi instance

    async def start(self) -> None:
        """初始化 LINE SDK.

        注意：LINE 使用 Webhook 模式，不需要 polling。
        實際的 HTTP 端點由 server.py 管理。
        """
        if self._running:
            return

        if not self._access_token:
            logger.error("LINE channel_access_token is required")
            return

        try:
            from linebot.v3.messaging import MessagingApi, Configuration, ApiClient
            config = Configuration(access_token=self._access_token)
            self._api_client = ApiClient(config)
            self._api = MessagingApi(self._api_client)
            self._running = True
            logger.info("LINEAdapter initialized (webhook mode)")
        except ImportError:
            logger.error(
                "line-bot-sdk v3 is required: pip install line-bot-sdk"
            )
        except Exception as e:
            logger.error(f"LINEAdapter start failed: {e}")

    async def stop(self) -> None:
        """停止 LINE adapter."""
        self._running = False
        self._api = None
        logger.info("LINEAdapter stopped")

    async def receive(self) -> InternalMessage:
        """從內部佇列取出已轉換的訊息."""
        return await self._message_queue.get()

    async def send(self, message: InternalMessage) -> bool:
        """發送訊息到 LINE 使用者.

        使用 Push Message API（需要 user_id 在 metadata.chat_id 中）。
        """
        if not self._api:
            logger.error("LINE API not initialized")
            return False

        user_id = message.metadata.get("chat_id", "")
        if not user_id:
            logger.error("No target user_id for LINE message")
            return False

        try:
            from linebot.v3.messaging import TextMessage, PushMessageRequest

            # LINE 單則訊息上限 5000 字元
            content = message.content
            if len(content) > 5000:
                content = content[:4990] + "\n..."

            req = PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=content)],
            )
            self._api.push_message(req)
            logger.debug(f"LINE message sent to {user_id[:8]}...")
            return True

        except Exception as e:
            logger.error(f"LINE send failed: {e}")
            return False

    def get_trust_level(self, user_id: str) -> TrustLevel:
        """根據設定判斷信任層級."""
        if user_id in self._trusted_user_ids:
            return TrustLevel.CORE
        return TrustLevel.EXTERNAL

    # ── Webhook 事件處理 ──

    def verify_signature(self, body: str, signature: str) -> bool:
        """驗證 LINE Webhook 簽名.

        Args:
            body: Request body (raw string)
            signature: X-Line-Signature header value

        Returns:
            True if signature is valid
        """
        if not self._channel_secret:
            logger.warning("LINE channel_secret not set, skipping signature verification")
            return True

        gen_signature = hmac.new(
            self._channel_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(gen_signature).decode("utf-8")
        return hmac.compare_digest(signature, expected)

    async def handle_webhook_events(self, events: List[Dict[str, Any]]) -> None:
        """處理 LINE Webhook 事件列表.

        由 server.py 的 /webhook/line 端點呼叫。

        Args:
            events: LINE webhook events list
        """
        for event in events:
            event_type = event.get("type", "")

            if event_type == "message":
                await self._handle_message_event(event)
            elif event_type == "postback":
                await self._handle_postback_event(event)
            elif event_type == "follow":
                logger.info(f"LINE follow event: {event.get('source', {}).get('userId', '')}")
            elif event_type == "unfollow":
                logger.info(f"LINE unfollow event")
            else:
                logger.debug(f"LINE unhandled event type: {event_type}")

    async def _handle_message_event(self, event: Dict[str, Any]) -> None:
        """處理 LINE 訊息事件."""
        source = event.get("source", {})
        user_id = source.get("userId", "")
        message = event.get("message", {})
        msg_type = message.get("type", "")

        if msg_type != "text":
            logger.debug(f"LINE non-text message type: {msg_type}")
            return

        text = message.get("text", "")
        if not text.strip():
            return

        try:
            ts = int(event.get("timestamp", 0)) / 1000
            msg_time = datetime.fromtimestamp(ts, tz=TZ8)
        except Exception:
            msg_time = datetime.now(TZ8)

        trust_level = self.get_trust_level(user_id)

        # 判斷聊天類型
        source_type = source.get("type", "user")  # user / group / room
        if source_type == "group":
            group_id = source.get("groupId", "")
            session_id = f"line_group_{group_id}"
        elif source_type == "room":
            room_id = source.get("roomId", "")
            session_id = f"line_room_{room_id}"
        else:
            session_id = f"line_{user_id}"

        internal_msg = InternalMessage(
            source="line",
            session_id=session_id,
            user_id=user_id,
            content=text,
            timestamp=msg_time,
            trust_level=trust_level.value,
            metadata={
                "chat_id": user_id,
                "reply_token": event.get("replyToken", ""),
                "source_type": source_type,
                "message_id": message.get("id", ""),
            },
        )

        await self._message_queue.put(internal_msg)

    async def _handle_postback_event(self, event: Dict[str, Any]) -> None:
        """處理 LINE Postback 事件（InteractionRequest callback）.

        postback.data 格式: choice:{question_id}:{value}
        """
        source = event.get("source", {})
        user_id = source.get("userId", "")
        postback = event.get("postback", {})
        data = postback.get("data", "")

        if not data:
            return

        # 解析 choice callback
        parts = data.split(":", 2)
        if len(parts) == 3 and parts[0] == "choice":
            _, question_id, selected_value = parts

            from museon.gateway.message import InteractionResponse
            response = InteractionResponse(
                question_id=question_id,
                selected=[selected_value],
                responder_id=user_id,
                channel="line",
            )

            if self._interaction_queue:
                self._interaction_queue.resolve(question_id, response)
                logger.debug(
                    f"LINE postback resolved: qid={question_id}, value={selected_value}"
                )
            else:
                logger.warning(
                    f"No interaction_queue for LINE postback: qid={question_id}"
                )
        else:
            logger.debug(f"LINE unhandled postback data: {data}")

    # ══════════════════════════════════════════════════
    # v10.0: InteractionRequest — 跨通道互動選項
    # ══════════════════════════════════════════════════

    def set_interaction_queue(self, queue) -> None:
        """設定 InteractionQueue 實例."""
        self._interaction_queue = queue

    async def present_choices(
        self,
        chat_id: str,
        request,
        interaction_queue,
    ) -> None:
        """呈現互動選項為 LINE Quick Reply 或 Flex Message.

        - ≤ 13 選項 且非多選 → Quick Reply（底部快速回覆按鈕）
        - > 13 選項 或多選 → Flex Message（卡片式按鈕）

        Args:
            chat_id: LINE user ID
            request: InteractionRequest 物件
            interaction_queue: InteractionQueue 實例
        """
        self._interaction_queue = interaction_queue

        if not self._api:
            logger.error("LINE API not initialized for present_choices")
            return

        if len(request.options) <= 13 and not request.multi_select:
            await self._present_quick_reply(chat_id, request)
        else:
            await self._present_flex_message(chat_id, request)

    async def _present_quick_reply(self, chat_id: str, request) -> None:
        """用 Quick Reply 呈現選項（≤ 13 個）."""
        try:
            from linebot.v3.messaging import (
                TextMessage, PushMessageRequest,
                QuickReply, QuickReplyItem,
                PostbackAction,
            )

            items = []
            for opt in request.options:
                cb_value = opt.value or opt.label
                pb_data = f"choice:{request.question_id}:{cb_value}"

                # LINE postback data 限 300 chars
                if len(pb_data) > 300:
                    pb_data = pb_data[:300]

                items.append(
                    QuickReplyItem(
                        action=PostbackAction(
                            label=opt.label[:20],  # LINE Quick Reply label 限 20 字
                            data=pb_data,
                            display_text=opt.label,
                        )
                    )
                )

            header = f"【{request.header}】\n" if request.header else ""
            text = f"{header}{request.question}"

            msg = TextMessage(
                text=text,
                quick_reply=QuickReply(items=items),
            )

            req = PushMessageRequest(to=chat_id, messages=[msg])
            self._api.push_message(req)

            logger.debug(
                f"LINE Quick Reply presented: qid={request.question_id}, "
                f"options={len(items)}"
            )

        except ImportError:
            logger.error("line-bot-sdk v3 required for Quick Reply")
        except Exception as e:
            logger.error(f"LINE Quick Reply present failed: {e}")

    async def _present_flex_message(self, chat_id: str, request) -> None:
        """用 Flex Message 呈現選項（> 13 個或多選）."""
        try:
            from linebot.v3.messaging import (
                FlexMessage, FlexContainer, PushMessageRequest,
            )

            # 建構 Flex Message 的按鈕
            button_contents = []
            for opt in request.options:
                cb_value = opt.value or opt.label
                pb_data = f"choice:{request.question_id}:{cb_value}"
                if len(pb_data) > 300:
                    pb_data = pb_data[:300]

                button_contents.append({
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "margin": "sm",
                    "action": {
                        "type": "postback",
                        "label": opt.label[:20],
                        "data": pb_data,
                        "displayText": opt.label,
                    },
                })

                # 有描述時加一行說明文字
                if opt.description:
                    button_contents.append({
                        "type": "text",
                        "text": opt.description,
                        "size": "xs",
                        "color": "#888888",
                        "margin": "none",
                        "wrap": True,
                    })

            flex_content = {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": request.header or "MUSEON",
                            "weight": "bold",
                            "size": "lg",
                            "color": "#C4502A",
                        },
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": request.question,
                            "wrap": True,
                            "size": "md",
                        },
                        {"type": "separator", "margin": "md"},
                        *button_contents,
                    ],
                },
            }

            flex_msg = FlexMessage(
                alt_text=request.question[:400],
                contents=FlexContainer.from_dict(flex_content),
            )

            req = PushMessageRequest(to=chat_id, messages=[flex_msg])
            self._api.push_message(req)

            logger.debug(
                f"LINE Flex Message presented: qid={request.question_id}, "
                f"options={len(request.options)}"
            )

        except ImportError:
            logger.error("line-bot-sdk v3 required for Flex Message")
        except Exception as e:
            logger.error(f"LINE Flex Message present failed: {e}")

    # ── Status ──

    @property
    def is_running(self) -> bool:
        """適配器是否正在運行."""
        return self._running

    def get_status(self) -> Dict[str, Any]:
        """取得適配器狀態."""
        return {
            "running": self._running,
            "api_initialized": self._api is not None,
            "queue_size": self._message_queue.qsize(),
            "configured": bool(self._access_token),
        }
