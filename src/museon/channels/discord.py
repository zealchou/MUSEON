"""Discord Channel Adapter — discord.py 整合.

透過 discord.py 庫接收和發送 Discord 訊息：
- Bot 帳號連線 Gateway WebSocket
- 訊息轉為 InternalMessage 統一格式
- 支援指定 Guild / Channel 限制
- 透過 EventBus 發布 CHANNEL_MESSAGE_RECEIVED / CHANNEL_MESSAGE_SENT

依賴：
- discord.py (pip install discord.py)

環境變數：
- DISCORD_BOT_TOKEN: Discord Bot Token
- DISCORD_GUILD_ID: 限定的 Guild ID（可選）
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


class DiscordAdapter(ChannelAdapter):
    """Discord 通道適配器 — 使用 discord.py.

    Features:
    - Gateway WebSocket 連線
    - 訊息佇列 + InternalMessage 轉換
    - Guild 限定（避免被拉進不明伺服器後回應）
    - 信任層級由設定中的 trusted_user_ids 決定
    - EventBus 事件發布
    """

    def __init__(self, config: Dict[str, Any], event_bus: Any = None) -> None:
        """
        Args:
            config: 設定字典，含:
                - bot_token: Discord Bot Token
                - guild_id: 限定 Guild ID（可選）
                - trusted_user_ids: 受信任使用者 ID 列表
                - default_channel_id: 預設發送頻道 ID
            event_bus: EventBus 實例（可選）
        """
        super().__init__(config)
        self._token: str = config.get("bot_token", "")
        self._guild_id: Optional[str] = config.get("guild_id")
        self._trusted_user_ids: List[str] = config.get("trusted_user_ids", [])
        self._default_channel_id: Optional[str] = config.get("default_channel_id")
        self._event_bus = event_bus

        self._client: Any = None  # discord.Client
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running: bool = False
        self._bot_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """啟動 Discord Bot 並連線 Gateway."""
        if self._running:
            return

        if not self._token:
            logger.error("Discord bot_token is required")
            return

        try:
            import discord
        except ImportError:
            logger.error("discord.py is required: pip install discord.py")
            return

        try:
            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True

            self._client = discord.Client(intents=intents)

            @self._client.event
            async def on_ready():
                logger.info(
                    f"DiscordAdapter connected as {self._client.user} "
                    f"(guilds: {len(self._client.guilds)})"
                )

            @self._client.event
            async def on_message(message):
                await self._on_message(message)

            # 以背景任務啟動 bot（非阻塞）
            self._bot_task = asyncio.create_task(
                self._client.start(self._token)
            )
            self._running = True
            logger.info("DiscordAdapter starting...")

        except Exception as e:
            logger.error(f"DiscordAdapter start failed: {e}")
            self._running = False

    async def stop(self) -> None:
        """停止 Discord Bot."""
        if not self._running:
            return

        try:
            if self._client and not self._client.is_closed():
                await self._client.close()
        except Exception as e:
            logger.error(f"DiscordAdapter stop error: {e}")

        if self._bot_task:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except (asyncio.CancelledError, Exception) as e:
                logger.debug(f"[DISCORD] operation failed (degraded): {e}")
            self._bot_task = None

        self._running = False
        self._client = None
        logger.info("DiscordAdapter stopped")

    async def receive(self) -> InternalMessage:
        """從內部佇列取出已轉換的訊息.

        Returns:
            InternalMessage: 統一訊息格式
        """
        msg = await self._message_queue.get()
        return msg

    async def send(self, message: InternalMessage) -> bool:
        """發送訊息到 Discord 頻道.

        Args:
            message: 要發送的 InternalMessage

        Returns:
            bool: 發送是否成功
        """
        if not self._client or self._client.is_closed():
            logger.error("Discord client not connected")
            return False

        channel_id = message.metadata.get(
            "channel_id", self._default_channel_id
        )
        if not channel_id:
            logger.error("No target channel for Discord message")
            return False

        try:
            channel = self._client.get_channel(int(channel_id))
            if channel is None:
                channel = await self._client.fetch_channel(int(channel_id))

            if channel is None:
                logger.error(f"Discord channel not found: {channel_id}")
                return False

            # Discord 單則訊息上限 2000 字元
            content = message.content
            if len(content) > 2000:
                # 分段發送
                chunks = self._split_message(content, 2000)
                for chunk in chunks:
                    await channel.send(chunk)
            else:
                await channel.send(content)

            # 發布送出事件
            try:
                if self._event_bus is not None:
                    from museon.core.event_bus import CHANNEL_MESSAGE_SENT
                    self._event_bus.publish(CHANNEL_MESSAGE_SENT, {
                        "channel": "discord",
                        "channel_id": str(channel_id),
                        "content_length": len(content),
                        "timestamp": datetime.now(TZ8).isoformat(),
                    })
            except Exception as e:
                logger.error(f"EventBus publish CHANNEL_MESSAGE_SENT failed: {e}")

            return True

        except Exception as e:
            logger.error(f"Discord send failed: {e}")
            return False

    def get_trust_level(self, user_id: str) -> TrustLevel:
        """根據設定判斷信任層級.

        Args:
            user_id: Discord 使用者 ID

        Returns:
            TrustLevel: 信任等級
        """
        if user_id in self._trusted_user_ids:
            return TrustLevel.CORE
        return TrustLevel.EXTERNAL

    async def _on_message(self, message: Any) -> None:
        """Discord 訊息事件回呼.

        Args:
            message: discord.Message 物件
        """
        # 忽略 bot 自己的訊息
        if message.author == self._client.user:
            return
        if message.author.bot:
            return

        # Guild 限定
        if self._guild_id and message.guild:
            if str(message.guild.id) != str(self._guild_id):
                return

        user_id = str(message.author.id)
        text = message.content or ""

        if not text.strip():
            return

        # 處理附件描述
        attachments_desc = ""
        if message.attachments:
            att_names = [att.filename for att in message.attachments]
            attachments_desc = f"\n[附件: {', '.join(att_names)}]"

        full_content = text + attachments_desc

        try:
            msg_time = message.created_at.astimezone(TZ8)
        except Exception:
            msg_time = datetime.now(TZ8)

        trust_level = self.get_trust_level(user_id)

        channel_id = str(message.channel.id)
        guild_id = str(message.guild.id) if message.guild else "dm"
        session_id = f"discord_{guild_id}_{channel_id}_{user_id}"

        internal_msg = InternalMessage(
            source="discord",
            session_id=session_id,
            user_id=user_id,
            content=full_content,
            timestamp=msg_time,
            trust_level=trust_level.value,
            metadata={
                "channel_id": channel_id,
                "guild_id": guild_id,
                "message_id": str(message.id),
                "username": str(message.author),
                "display_name": message.author.display_name,
            },
        )

        await self._message_queue.put(internal_msg)

        # 發布接收事件
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import CHANNEL_MESSAGE_RECEIVED
                self._event_bus.publish(CHANNEL_MESSAGE_RECEIVED, {
                    "channel": "discord",
                    "user_id": user_id,
                    "content_length": len(full_content),
                    "trust_level": trust_level.value,
                    "timestamp": msg_time.isoformat(),
                })
        except Exception as e:
            logger.error(f"EventBus publish CHANNEL_MESSAGE_RECEIVED failed: {e}")

    @staticmethod
    def _split_message(text: str, max_length: int) -> List[str]:
        """將長訊息分段.

        Args:
            text: 原始訊息
            max_length: 每段最大長度

        Returns:
            分段後的訊息列表
        """
        chunks: List[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break
            # 優先在換行處切分
            cut = remaining[:max_length].rfind("\n")
            if cut < max_length // 4:
                cut = max_length
            chunk = remaining[:cut].rstrip()
            remaining = remaining[cut:].lstrip()
            if chunk:
                chunks.append(chunk)
        return chunks

    # ══════════════════════════════════════════════════
    # v10.0: InteractionRequest — 跨通道互動選項
    # ══════════════════════════════════════════════════

    async def present_choices(
        self,
        chat_id: str,
        request,
        interaction_queue,
    ) -> None:
        """呈現互動選項為 Discord Button 或 Select Menu.

        - ≤ 5 個選項 且非多選 → Button 一行排列
        - > 5 個選項 或多選 → Select Menu

        Args:
            chat_id: Discord channel ID
            request: InteractionRequest 物件
            interaction_queue: InteractionQueue 實例
        """
        if not self._client or self._client.is_closed():
            logger.error("Discord client not connected for present_choices")
            return

        try:
            import discord
            from discord.ui import View, Button, Select
        except ImportError:
            logger.error("discord.py is required for present_choices")
            return

        try:
            channel = self._client.get_channel(int(chat_id))
            if channel is None:
                channel = await self._client.fetch_channel(int(chat_id))
            if channel is None:
                logger.error(f"Discord channel not found: {chat_id}")
                return
        except Exception as e:
            logger.error(f"Discord fetch channel failed: {e}")
            return

        use_select = request.multi_select or len(request.options) > 5

        if use_select:
            view = self._build_select_view(request, interaction_queue)
        else:
            view = self._build_button_view(request, interaction_queue)

        header = f"**{request.header}**\n" if request.header else ""
        multi_hint = "\n（可多選）" if request.multi_select else ""
        text = f"{header}{request.question}{multi_hint}"

        try:
            await channel.send(text, view=view)
            logger.debug(
                f"InteractionRequest presented on Discord: qid={request.question_id}, "
                f"options={len(request.options)}, channel={chat_id}"
            )
        except Exception as e:
            logger.error(f"Discord present_choices send failed: {e}")

    def _build_button_view(self, request, interaction_queue):
        """建構 Discord Button View（≤5 選項）."""
        import discord
        from discord.ui import View, Button

        view = View(timeout=request.timeout_seconds)
        queue_ref = interaction_queue

        for opt in request.options:
            opt_value = opt.value or opt.label
            button = Button(
                label=opt.label[:80],
                style=discord.ButtonStyle.secondary,
                custom_id=f"choice:{request.question_id}:{opt_value}"[:100],
            )

            async def button_callback(
                interaction: discord.Interaction,
                qid=request.question_id,
                val=opt_value,
                q=queue_ref,
            ):
                from museon.gateway.message import InteractionResponse
                resp = InteractionResponse(
                    question_id=qid,
                    selected=[val],
                    responder_id=str(interaction.user.id),
                    channel="discord",
                )
                try:
                    await interaction.response.edit_message(
                        content=f"✅ 已選擇：{val}", view=None
                    )
                except Exception as e:
                    logger.debug(f"Discord edit_message failed: {e}")
                if q:
                    q.resolve(qid, resp)

            button.callback = button_callback
            view.add_item(button)

        return view

    def _build_select_view(self, request, interaction_queue):
        """建構 Discord Select Menu View（>5 選項或多選）."""
        import discord
        from discord.ui import View, Select

        view = View(timeout=request.timeout_seconds)
        queue_ref = interaction_queue

        options = []
        for opt in request.options:
            options.append(
                discord.SelectOption(
                    label=opt.label[:100],
                    description=opt.description[:100] if opt.description else None,
                    value=(opt.value or opt.label)[:100],
                )
            )

        max_vals = len(options) if request.multi_select else 1
        select = Select(
            placeholder="請選擇..." if not request.multi_select else "請選擇（可多選）...",
            options=options,
            min_values=1,
            max_values=max_vals,
            custom_id=f"choice:{request.question_id}"[:100],
        )

        async def select_callback(
            interaction: discord.Interaction,
            qid=request.question_id,
            q=queue_ref,
            sel=select,
        ):
            from museon.gateway.message import InteractionResponse
            resp = InteractionResponse(
                question_id=qid,
                selected=list(sel.values),
                responder_id=str(interaction.user.id),
                channel="discord",
            )
            selected_text = ", ".join(sel.values)
            try:
                await interaction.response.edit_message(
                    content=f"✅ 已選擇：{selected_text}", view=None
                )
            except Exception as e:
                logger.debug(f"Discord edit_message failed: {e}")
            if q:
                q.resolve(qid, resp)

        select.callback = select_callback
        view.add_item(select)

        return view

    # ── Status ──

    @property
    def is_running(self) -> bool:
        """適配器是否正在運行."""
        return self._running

    def get_status(self) -> Dict[str, Any]:
        """取得適配器狀態."""
        connected = False
        guild_count = 0
        if self._client and not self._client.is_closed():
            connected = True
            guild_count = len(self._client.guilds)

        return {
            "running": self._running,
            "connected": connected,
            "guild_count": guild_count,
            "queue_size": self._message_queue.qsize(),
            "configured": bool(self._token),
            "guild_id": self._guild_id,
        }
