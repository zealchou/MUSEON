"""Telegram Channel Adapter using python-telegram-bot 20.x."""

import asyncio
import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from museon.channels.base import ChannelAdapter, TrustLevel
from museon.core.event_bus import (
    MORPHENIX_EXECUTION_COMPLETED,
    MORPHENIX_L3_PROPOSAL,
    MORPHENIX_ROLLBACK,
    PROACTIVE_MESSAGE,
    PULSE_MICRO_BEAT,
    PULSE_NIGHTLY_DONE,
    PULSE_RHYTHM_CHECK,
    EventBus,
)
from museon.gateway.message import InternalMessage

logger = logging.getLogger(__name__)


class TelegramAdapter(ChannelAdapter):
    """
    Telegram channel adapter using python-telegram-bot 20.x.

    Features:
    - Async polling for updates
    - Trusted user whitelist
    - Main session merging (all DMs go to one session)
    - Message queue for handling updates
    - Processing status messages (show progress, auto-delete on completion)
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
        self._last_message_time: Optional[datetime] = None
        self._typing_tasks: Dict[int, asyncio.Task] = {}  # chat_id -> typing task

        # Pulse EventBus integration
        self._event_bus: Optional[EventBus] = None
        self._heartbeat_focus = None  # HeartbeatFocus instance
        self._notified_users: set = set()  # 閒置推播已通知用戶

        # Proactive reply threading: 追蹤主動推送的 message_id
        self._proactive_message_ids: Dict[int, str] = {}  # {msg_id: push_context}
        self._max_proactive_ids = 50

        # Deduplication: 追蹤已處理的 update_id，防止重複訊息
        self._seen_update_ids: set = set()
        self._max_seen_update_ids = 1000  # 避免無限成長

    async def start(self) -> None:
        """Start the Telegram bot and begin polling."""
        if self._running:
            return

        self.application = Application.builder().token(self.bot_token).build()

        # Register handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self._handle_file_upload))
        self.application.add_handler(MessageHandler(filters.PHOTO, self._handle_file_upload))
        self.application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self._handle_file_upload))
        self.application.add_handler(MessageHandler(filters.VIDEO, self._handle_file_upload))
        self.application.add_handler(CommandHandler("start", self._handle_start_command))

        # Multi-Agent 部門指令（/dept, /flywheel, /thunder~earth）
        self.application.add_handler(CommandHandler("dept", self._handle_dept_command))
        self.application.add_handler(CommandHandler("flywheel", self._handle_flywheel_command))
        for _cmd in ("thunder", "fire", "lake", "heaven", "wind", "water", "mountain", "earth", "core", "okr"):
            self.application.add_handler(CommandHandler(_cmd, self._handle_switch_dept_command))

        # Morphenix L3 inline keyboard callback
        self.application.add_handler(
            CallbackQueryHandler(self._handle_morphenix_callback, pattern=r"^morphenix:")
        )

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
        if update.update_id in self._seen_update_ids:
            logger.debug("Duplicate update_id %s, skipping", update.update_id)
            return
        self._seen_update_ids.add(update.update_id)
        if len(self._seen_update_ids) > self._max_seen_update_ids:
            self._seen_update_ids = set(list(self._seen_update_ids)[-500:])

        # ── Group chat: read all, reply only when @mentioned ──
        if update.message and update.message.chat.type in ("group", "supergroup"):
            from_user = update.message.from_user
            user_id_str = str(from_user.id) if from_user else ""
            is_owner = user_id_str in self.trusted_user_ids

            # Check if bot is @mentioned (must be THIS bot, not any @user)
            text = update.message.text or ""
            is_mentioned = False
            bot_username = context.bot.username.lower() if context.bot and context.bot.username else ""
            bot_id = context.bot.id if context.bot else None
            if update.message.entities and bot_username:
                for ent in update.message.entities:
                    if ent.type == "mention":
                        # @username mention — extract and compare
                        mentioned = text[ent.offset:ent.offset + ent.length].lower()
                        if mentioned == f"@{bot_username}":
                            is_mentioned = True
                            break
                    elif ent.type == "text_mention" and ent.user:
                        # Inline mention with user object — compare bot ID
                        if bot_id and ent.user.id == bot_id:
                            is_mentioned = True
                            break
            # Fallback: direct text check for bot username
            if not is_mentioned and bot_username:
                is_mentioned = f"@{bot_username}" in text.lower()

            # Always log group messages for context building
            sender_name = from_user.first_name or "" if from_user else ""
            username = from_user.username or "" if from_user else ""
            chat_id = update.message.chat.id
            group_title = update.message.chat.title or ""
            chat_type = update.message.chat.type or "supergroup"
            self._log_group_message(
                group_id=chat_id,
                user_id=user_id_str,
                display_name=sender_name,
                text=(text or "")[:500],
                bot_replied=False,
            )
            # Structured DB recording
            try:
                from museon.governance.group_context import get_group_context_store
                store = get_group_context_store()
                store.upsert_group(chat_id, group_title, chat_type)
                store.record_message(
                    group_id=chat_id,
                    user_id=user_id_str,
                    text=(text or "")[:2000],
                    message_id=update.message.message_id,
                    display_name=sender_name,
                    username=username,
                )
            except Exception as _db_err:
                logger.debug(f"Group context DB write error: {_db_err}")

            if not is_mentioned:
                # Silent record — don't push to message_queue, just log
                logger.debug(
                    "Group message recorded (silent) from %s in %s",
                    user_id_str, chat_id,
                )
                return

        # 記錄互動（HeartbeatFocus + 清除閒置推播狀態）
        if update.message and update.message.from_user:
            self.record_user_interaction(str(update.message.from_user.id))
        await self.message_queue.put(update)

    async def _handle_file_upload(self, update: Update, context: Any) -> None:
        """Handle incoming file uploads (document, photo, voice, audio, video)."""
        if update.update_id in self._seen_update_ids:
            logger.debug("Duplicate update_id %s, skipping", update.update_id)
            return
        self._seen_update_ids.add(update.update_id)
        if len(self._seen_update_ids) > self._max_seen_update_ids:
            self._seen_update_ids = set(list(self._seen_update_ids)[-500:])

        # Group file uploads: always log, only process if @mentioned
        if update.message and update.message.chat.type in ("group", "supergroup"):
            from_user = update.message.from_user
            user_id_str = str(from_user.id) if from_user else ""
            sender_name = from_user.first_name or "" if from_user else ""
            chat_id = update.message.chat.id
            caption = update.message.caption or ""
            fname = ""
            if update.message.document:
                fname = update.message.document.file_name or "file"
            elif update.message.photo:
                fname = "photo"
            elif update.message.voice:
                fname = "voice"
            self._log_group_message(
                group_id=chat_id,
                user_id=user_id_str,
                display_name=sender_name,
                text=f"[檔案: {fname}] {caption}"[:500],
                bot_replied=False,
            )
            # Structured DB recording for file uploads
            try:
                from museon.governance.group_context import get_group_context_store
                store = get_group_context_store()
                store.upsert_group(chat_id, update.message.chat.title or "", update.message.chat.type or "supergroup")
                store.record_message(
                    group_id=chat_id,
                    user_id=user_id_str,
                    text=f"[檔案: {fname}] {caption}"[:2000],
                    message_id=update.message.message_id,
                    msg_type="file",
                    display_name=sender_name,
                    username=from_user.username or "" if from_user else "",
                )
            except Exception as _db_err:
                logger.debug(f"Group context DB write error (file): {_db_err}")

            # Check @mention in caption (must be THIS bot, not any @user)
            is_mentioned = False
            _bot_username = context.bot.username.lower() if context.bot and context.bot.username else ""
            _bot_id = context.bot.id if context.bot else None
            if update.message.caption_entities and _bot_username:
                for ent in update.message.caption_entities:
                    if ent.type == "mention":
                        mentioned = caption[ent.offset:ent.offset + ent.length].lower()
                        if mentioned == f"@{_bot_username}":
                            is_mentioned = True
                            break
                    elif ent.type == "text_mention" and ent.user:
                        if _bot_id and ent.user.id == _bot_id:
                            is_mentioned = True
                            break
            if not is_mentioned and _bot_username:
                is_mentioned = f"@{_bot_username}" in caption.lower()
            if not is_mentioned:
                logger.debug("Group file upload recorded (silent) from %s", user_id_str)
                return

        if update.message and update.message.from_user:
            self.record_user_interaction(str(update.message.from_user.id))
        await self.message_queue.put(update)

    async def _download_telegram_file(self, file_obj) -> Optional[Dict[str, Any]]:
        """Download a Telegram file to local uploads directory.

        Args:
            file_obj: Telegram file object (Document, PhotoSize, Voice, Audio, Video)

        Returns:
            Dict with file info or None on failure
        """
        try:
            if not self.application:
                return None

            # Get file from Telegram servers
            tg_file = await self.application.bot.get_file(file_obj.file_id)

            # Determine filename
            file_name = getattr(file_obj, 'file_name', None)
            if not file_name:
                ext = ''
                mime = getattr(file_obj, 'mime_type', '')
                if mime:
                    ext_map = {
                        'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif',
                        'image/webp': '.webp', 'audio/ogg': '.ogg', 'audio/mpeg': '.mp3',
                        'video/mp4': '.mp4', 'application/pdf': '.pdf',
                        'text/plain': '.txt', 'application/json': '.json',
                    }
                    ext = ext_map.get(mime, '')
                if not ext and tg_file.file_path:
                    ext = Path(tg_file.file_path).suffix
                file_name = f"{file_obj.file_unique_id}{ext}"

            # Save to uploads directory
            uploads_dir = Path(
                os.environ.get("MUSEON_HOME", "/tmp")
            ) / "data" / "uploads" / "telegram"
            uploads_dir.mkdir(parents=True, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            local_path = uploads_dir / f"{ts}_{file_name}"

            await tg_file.download_to_drive(str(local_path))

            logger.info(f"Telegram file downloaded: {file_name} -> {local_path}")

            return {
                "local_path": str(local_path),
                "file_name": file_name,
                "file_size": getattr(file_obj, 'file_size', None),
                "mime_type": getattr(file_obj, 'mime_type', None),
                "file_id": file_obj.file_id,
            }

        except Exception as e:
            logger.error(f"Failed to download Telegram file: {e}")
            return None

    async def _handle_start_command(self, update: Update, context: Any) -> None:
        """Handle /start command — 歡迎訊息 + 權限聲明."""
        # 先發送權限聲明
        if update.message:
            permission_notice = (
                "⚠️ 權限聲明\n\n"
                "MUSEON 擁有與啟動者相同的系統權限，"
                "可執行 shell 指令、讀寫檔案、存取網路服務。\n\n"
                "僅攔截不可逆的毀滅性操作（格式化硬碟、刪除根目錄等 7 類指令）。\n\n"
                "如需調整權限設定，請至 MUSEON Dashboard 管理。"
            )
            await update.message.reply_text(permission_notice)
        # 再讓 Brain 處理正常的 /start 歡迎流程
        await self.message_queue.put(update)

    async def _handle_dept_command(self, update: Update, context: Any) -> None:
        """Handle /dept — 顯示當前部門."""
        try:
            from museon.multiagent.department_config import get_department
            brain = self._get_brain()
            if brain and brain._context_switcher:
                dept_id = brain._context_switcher.current_dept
                dept = get_department(dept_id)
                if dept:
                    await update.message.reply_text(
                        f"{dept.emoji} {dept.name}\n{dept.role}"
                    )
                    return
            await update.message.reply_text("Multi-Agent 未啟用")
        except Exception as e:
            logger.error(f"dept command error: {e}")

    async def _handle_flywheel_command(self, update: Update, context: Any) -> None:
        """Handle /flywheel — 顯示飛輪八卦狀態."""
        try:
            from museon.multiagent.department_config import get_flywheel_departments
            depts = get_flywheel_departments()
            lines = []
            brain = self._get_brain()
            current = ""
            if brain and brain._context_switcher:
                current = brain._context_switcher.current_dept
            for d in depts:
                marker = " ◀" if d.dept_id == current else ""
                lines.append(f"{d.emoji} {d.name}{marker}")
            await update.message.reply_text("\n".join(lines))
        except Exception as e:
            logger.error(f"flywheel command error: {e}")

    async def _handle_switch_dept_command(self, update: Update, context: Any) -> None:
        """Handle /thunder ~/earth — 切換至指定部門."""
        try:
            from museon.multiagent.department_config import get_department
            dept_id = update.message.text.strip("/").split()[0].lower()
            dept = get_department(dept_id)
            if not dept:
                await update.message.reply_text(f"未知部門：{dept_id}")
                return
            brain = self._get_brain()
            if brain and brain._context_switcher:
                brain._context_switcher.switch_to(dept_id)
                await update.message.reply_text(
                    f"已切換到 {dept.emoji} {dept.name} 部門\n{dept.role}"
                )
            else:
                await update.message.reply_text("Multi-Agent 未啟用")
        except Exception as e:
            logger.error(f"switch dept command error: {e}")

    def _get_brain(self):
        """取得 brain 實例（from gateway）."""
        try:
            from museon.gateway.server import _get_brain
            return _get_brain()
        except Exception:
            return None

    # ─── Morphenix L3 Approval via Inline Keyboard ───

    async def push_proposal_notification(
        self, proposal_id: str, title: str, description: str,
        level: str = "L3", affected_files: list = None,
    ) -> Optional[int]:
        """推送 Morphenix 提案到 Telegram，附帶 inline 批准/拒絕按鈕.

        Returns:
            sent message_id (for tracking), or None on failure.
        """
        if not self.application or not self._running:
            return None

        text = (
            f"🔄 【Morphenix {level} 提案】\n\n"
            f"📋 {title}\n"
            f"{description}\n"
        )
        if affected_files:
            text += "\n影響檔案:\n"
            for f in affected_files[:5]:
                text += f"  · {f}\n"
        text += (
            f"\n提案 ID: {proposal_id}\n"
            f"⏰ 72 小時未處理將自動批准"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ 批准", callback_data=f"morphenix:approve:{proposal_id}"
                ),
                InlineKeyboardButton(
                    "❌ 拒絕", callback_data=f"morphenix:reject:{proposal_id}"
                ),
            ]
        ])

        targets = [int(uid) for uid in self.trusted_user_ids if uid]
        msg_id = None
        for cid in targets:
            try:
                msg = await self.application.bot.send_message(
                    chat_id=cid, text=text, reply_markup=keyboard,
                )
                msg_id = msg.message_id
            except Exception as e:
                logger.error(f"Morphenix push failed for chat_id={cid}: {e}")

        return msg_id

    async def _handle_morphenix_callback(
        self, update: Update, context: Any,
    ) -> None:
        """處理 Morphenix inline keyboard 的 approve/reject 回調."""
        query = update.callback_query
        if not query or not query.data:
            return

        # 驗證使用者身份
        user_id = str(query.from_user.id)
        if user_id not in self.trusted_user_ids:
            await query.answer("⛔ 無權限操作", show_alert=True)
            return

        parts = query.data.split(":")
        if len(parts) != 3:
            await query.answer("格式錯誤")
            return

        _, action, proposal_id = parts

        # 取得 PulseDB
        try:
            brain = self._get_brain()
            if not brain:
                await query.answer("系統未就緒", show_alert=True)
                return

            db_path = brain.data_dir / "pulse.db"
            from museon.pulse.pulse_db import PulseDB
            db = PulseDB(str(db_path))

            if action == "approve":
                success = db.approve_proposal(proposal_id, decided_by="human")
                if success:
                    await query.answer("✅ 已批准！霓裳將執行演化")
                    await query.edit_message_text(
                        f"✅ 提案 {proposal_id} 已批准\n"
                        f"批准者: {query.from_user.first_name}\n"
                        f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                    logger.info(f"Morphenix proposal {proposal_id} approved by {user_id}")
                else:
                    await query.answer("提案不存在或已處理", show_alert=True)

            elif action == "reject":
                success = db.reject_proposal(proposal_id, decided_by="human")
                if success:
                    await query.answer("❌ 已拒絕")
                    await query.edit_message_text(
                        f"❌ 提案 {proposal_id} 已拒絕\n"
                        f"拒絕者: {query.from_user.first_name}\n"
                        f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                    logger.info(f"Morphenix proposal {proposal_id} rejected by {user_id}")
                else:
                    await query.answer("提案不存在或已處理", show_alert=True)

        except Exception as e:
            logger.error(f"Morphenix callback error: {e}")
            await query.answer(f"處理失敗: {e}", show_alert=True)

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
        self._last_message_time = datetime.now()

        # ── 回覆上下文：提取被回覆的訊息內容 ──
        msg = update.message
        reply_context = ""
        is_proactive_reply = False
        if msg.reply_to_message:
            replied = msg.reply_to_message
            replied_text = replied.text or replied.caption or ""

            # 偵測是否回覆主動推送訊息
            replied_msg_id = replied.message_id
            if replied_msg_id in self._proactive_message_ids:
                is_proactive_reply = True
                push_ctx = self._proactive_message_ids[replied_msg_id]
                reply_context = f"[回覆霓裳的主動訊息：{push_ctx}]\n\n"
            elif replied_text:
                # 截斷過長的回覆上下文（避免 token 浪費）
                if len(replied_text) > 500:
                    replied_text = replied_text[:500] + "..."
                if replied.from_user and replied.from_user.is_bot:
                    replied_from = "霓裳"
                elif replied.from_user:
                    # Use actual display name; mark owner if in trusted list
                    _replied_uid = str(replied.from_user.id)
                    _replied_name = replied.from_user.first_name or replied.from_user.username or "某人"
                    if _replied_uid in self.trusted_user_ids:
                        replied_from = f"{_replied_name}（老闆）"
                    else:
                        replied_from = _replied_name
                else:
                    replied_from = "某人"
                reply_context = f"[回覆 {replied_from} 的訊息：{replied_text}]\n\n"

        if reply_context and content:
            content = reply_context + content

        # Handle file uploads: download file + build descriptive content
        file_info = None

        if msg.document:
            file_info = await self._download_telegram_file(msg.document)
            caption = msg.caption or ""
            fname = msg.document.file_name or "file"
            content = f"[📎 檔案上傳: {fname}]"
            if caption:
                content += f"\n{caption}"
            if file_info:
                content += f"\n檔案已儲存至: {file_info['local_path']}"

        elif msg.photo:
            # Photo comes as list of sizes, pick the largest
            photo = msg.photo[-1]
            file_info = await self._download_telegram_file(photo)
            caption = msg.caption or ""
            content = "[🖼️ 圖片上傳]"
            if caption:
                content += f"\n{caption}"
            if file_info:
                content += f"\n圖片已儲存至: {file_info['local_path']}"

        elif msg.voice:
            file_info = await self._download_telegram_file(msg.voice)
            content = "[🎤 語音訊息]"
            if file_info:
                content += f"\n語音已儲存至: {file_info['local_path']}"

        elif msg.audio:
            file_info = await self._download_telegram_file(msg.audio)
            aname = getattr(msg.audio, 'file_name', 'audio')
            content = f"[🎵 音訊: {aname}]"
            if file_info:
                content += f"\n音訊已儲存至: {file_info['local_path']}"

        elif msg.video:
            file_info = await self._download_telegram_file(msg.video)
            vname = getattr(msg.video, 'file_name', 'video')
            caption = msg.caption or ""
            content = f"[🎬 影片: {vname}]"
            if caption:
                content += f"\n{caption}"
            if file_info:
                content += f"\n影片已儲存至: {file_info['local_path']}"

        # Group-aware session and metadata
        is_group = update.message.chat.type in ("group", "supergroup")
        is_owner = user_id in self.trusted_user_ids
        sender_name = msg.from_user.first_name or ""

        if is_group:
            session_id = f"telegram_group_{abs(chat_id)}"
            self._log_group_message(
                group_id=chat_id,
                user_id=user_id,
                display_name=sender_name,
                text=(update.message.text or "")[:500],
            )
        else:
            session_id = f"telegram_{chat_id}"

        trust_level = self.get_trust_level(user_id)

        metadata = {
            "chat_id": chat_id,
            "message_id": msg.message_id,
            "first_name": msg.from_user.first_name,
            "username": msg.from_user.username,
            "is_group": is_group,
            "is_owner": is_owner,
            "sender_name": sender_name,
        }
        if is_group:
            metadata["group_id"] = chat_id
        if file_info:
            metadata["file"] = file_info
        if msg.reply_to_message:
            metadata["reply_to_message_id"] = msg.reply_to_message.message_id
        if is_proactive_reply:
            metadata["is_proactive_reply"] = True

        return InternalMessage(
            source="telegram",
            session_id=session_id,
            user_id=user_id,
            content=content,
            timestamp=timestamp,
            trust_level=trust_level.value,
            metadata=metadata,
        )

    def _log_group_message(
        self,
        group_id: int,
        user_id: str,
        display_name: str,
        text: str,
        bot_replied: bool = False,
    ) -> None:
        """Append group message to jsonl log file."""
        try:
            log_dir = (
                Path(os.environ.get("MUSEON_HOME", "/tmp"))
                / "data" / "logs" / "groups" / str(abs(group_id))
            )
            log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_file = log_dir / f"{date_str}.jsonl"
            entry = {
                "ts": datetime.now().isoformat(),
                "group_id": group_id,
                "user_id": user_id,
                "name": display_name,
                "text": text[:500],
                "bot_replied": bot_replied,
            }
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Group log write failed: {e}")

    async def send_dm_to_owner(self, text: str) -> bool:
        """Send a DM directly to the owner (first trusted_user_id)."""
        if not self.application or not self.trusted_user_ids:
            return False
        try:
            owner_id = int(self.trusted_user_ids[0])
            await self.application.bot.send_message(chat_id=owner_id, text=text)
            return True
        except Exception as e:
            logger.error(f"send_dm_to_owner failed: {e}")
            return False

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

            # 去除 Markdown 語法，使用自然語言格式
            clean_text = self._strip_markdown(message.content)

            # Telegram 單則訊息上限 4096 字元，超長自動分段
            MAX_TG_LEN = 4096
            if len(clean_text) <= MAX_TG_LEN:
                await self.application.bot.send_message(chat_id=chat_id, text=clean_text)
            else:
                # 優先在段落邊界（\n\n）切，其次在換行（\n）切
                remaining = clean_text
                while remaining:
                    if len(remaining) <= MAX_TG_LEN:
                        await self.application.bot.send_message(chat_id=chat_id, text=remaining)
                        break
                    # 在 MAX_TG_LEN 範圍內找最後的段落邊界
                    cut = remaining[:MAX_TG_LEN].rfind("\n\n")
                    if cut < 500:  # 太靠前，改找換行
                        cut = remaining[:MAX_TG_LEN].rfind("\n")
                    if cut < 500:  # 還是太靠前，硬切
                        cut = MAX_TG_LEN
                    chunk = remaining[:cut].rstrip()
                    remaining = remaining[cut:].lstrip()
                    if chunk:
                        await self.application.bot.send_message(chat_id=chat_id, text=chunk)
                        if remaining:
                            await asyncio.sleep(0.15)  # 避免 Telegram rate limit
            return True

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_document(self, chat_id: int, file_path: str, caption: str = "") -> bool:
        """透過 Telegram Bot API 傳送檔案（v9.0）."""
        try:
            if not self.application:
                logger.error("Telegram application not initialized")
                return False
            from pathlib import Path
            fp = Path(file_path)
            if not fp.exists():
                logger.error(f"File not found: {file_path}")
                return False
            with open(file_path, "rb") as f:
                await self.application.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    caption=caption[:1024] if caption else None,
                )
            logger.info(f"Document sent: {fp.name} -> {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Telegram send_document failed: {e}")
            return False

    async def send_response(self, message, brain_response) -> bool:
        """傳送 BrainResponse（文字 + 附件）（v9.0）.

        Args:
            message: InternalMessage with response text
            brain_response: BrainResponse object (or str for backward compat)
        """
        from museon.gateway.message import BrainResponse

        # 1. Send text reply
        success = await self.send(message)

        # 2. Send artifacts if any
        if isinstance(brain_response, BrainResponse) and brain_response.has_artifacts():
            chat_id = message.metadata.get("chat_id")
            if chat_id:
                from pathlib import Path
                for artifact in brain_response.artifacts:
                    if artifact.type == "link":
                        continue  # Links are in the text response
                    file_path = artifact.content
                    if file_path and Path(file_path).exists():
                        await self.send_document(
                            chat_id=int(chat_id),
                            file_path=file_path,
                            caption=f"📎 {artifact.description}",
                        )
                    else:
                        logger.warning(f"Artifact file not found: {file_path}")
        return success

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """去除 Markdown 語法，轉為自然語言格式。Telegram 應用人類自然語言溝通。

        v10.5: 程式碼區塊保留內容（舊版會完全刪除導致回覆被吃掉）。
        """
        # 移除標題語法 (##, ###, ####)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # 移除粗體/斜體 (**text**, __text__, *text*, _text_)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)', r'\1', text)
        # 移除行內代碼 `code` → 保留內容
        text = re.sub(r'`([^`]+)`', r'\1', text)
        # 程式碼區塊 ```...``` → 保留內容，只移除圍欄標記
        text = re.sub(r'```\w*\n?', '', text)
        # 移除無序列表符號 (- item, * item) 改為自然段落
        text = re.sub(r'^\s*[-*]\s+', '· ', text, flags=re.MULTILINE)
        # 移除有序列表格式 (1. item) 保留數字
        text = re.sub(r'^(\s*\d+)\.\s+', r'\1. ', text, flags=re.MULTILINE)
        # 移除連結語法 [text](url) → text (url)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
        # 移除水平線 ---
        text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
        # 清理多餘空行（超過兩個連續空行 → 兩個）
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

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

    # ─── Processing Status Messages ───

    async def send_processing_status(self, chat_id: int, text: str = "⏳ 收到，正在思考...") -> Optional[int]:
        """
        Send a temporary processing status message.

        Returns the message_id so it can be updated or deleted later.
        """
        try:
            if not self.application:
                return None
            msg = await self.application.bot.send_message(chat_id=chat_id, text=text)
            return msg.message_id
        except Exception as e:
            logger.error(f"Failed to send processing status: {e}")
            return None

    async def update_processing_status(self, chat_id: int, message_id: int, text: str) -> bool:
        """
        Edit an existing processing status message.
        """
        try:
            if not self.application:
                return False
            await self.application.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update processing status: {e}")
            return False

    async def delete_processing_status(self, chat_id: int, message_id: int) -> bool:
        """
        Delete a processing status message (after response is sent).
        """
        try:
            if not self.application:
                return False
            await self.application.bot.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except Exception as e:
            logger.error(f"Failed to delete processing status: {e}")
            return False

    async def start_typing(self, chat_id: int) -> None:
        """
        Start continuous typing indicator for a chat.
        Sends 'typing' action every 4 seconds until stop_typing is called.
        """
        async def _typing_loop():
            try:
                while True:
                    if not self.application:
                        break
                    await self.application.bot.send_chat_action(
                        chat_id=chat_id, action=ChatAction.TYPING
                    )
                    await asyncio.sleep(4)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug(f"Typing indicator stopped: {e}")

        # Cancel existing typing task if any
        if chat_id in self._typing_tasks:
            self._typing_tasks[chat_id].cancel()

        if self.application:
            self._typing_tasks[chat_id] = asyncio.create_task(_typing_loop())

    async def stop_typing(self, chat_id: int) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @property
    def is_running(self) -> bool:
        """Whether the adapter is currently running."""
        return self._running

    @property
    def last_message_time(self) -> Optional[datetime]:
        """Timestamp of the last received message."""
        return self._last_message_time

    def get_status(self) -> Dict[str, Any]:
        """Get adapter status for Dashboard display."""
        return {
            "running": self._running,
            "last_message_time": self._last_message_time.isoformat() if self._last_message_time else None,
            "queue_size": self.message_queue.qsize(),
        }

    # ─── Push Notifications（純 CPU 模板 → Telegram）───

    async def push_notification(
        self, text: str, chat_ids: Optional[list] = None
    ) -> int:
        """推播通知到指定或所有受信任使用者 — 零 Token.

        Args:
            text: 推播訊息（純文字或 Telegram Markdown）
            chat_ids: 指定推播的 chat_id 列表，None = 所有 trusted users

        Returns:
            成功送出的訊息數量
        """
        if not self.application or not self._running:
            logger.warning("Telegram adapter not running, cannot push notification")
            return 0

        targets = chat_ids or [int(uid) for uid in self.trusted_user_ids if uid]
        if not targets:
            logger.warning("No push targets (trusted_user_ids empty)")
            return 0

        sent = 0
        for cid in targets:
            try:
                msg = await self.application.bot.send_message(
                    chat_id=cid, text=text
                )
                sent += 1
                # 追蹤主動推送 message_id（用於回覆串接）
                if msg and msg.message_id:
                    self._proactive_message_ids[msg.message_id] = text[:200]
                    # 維持上限
                    if len(self._proactive_message_ids) > self._max_proactive_ids:
                        oldest = next(iter(self._proactive_message_ids))
                        del self._proactive_message_ids[oldest]
            except Exception as e:
                logger.error(f"Push notification failed for chat_id={cid}: {e}")

        logger.info(f"📢 Push notification sent to {sent}/{len(targets)} users")
        return sent

    # ─── Pulse EventBus Integration ───

    def connect_pulse(
        self,
        event_bus: "EventBus",
        heartbeat_focus=None,
    ) -> None:
        """連接脈搏系統 EventBus.

        Args:
            event_bus: EventBus 實例
            heartbeat_focus: HeartbeatFocus 實例（記錄互動用）
        """
        self._event_bus = event_bus
        self._heartbeat_focus = heartbeat_focus

        # 保存主事件迴圈引用（Telegram bot 運行的迴圈）
        # 用於跨線程安全推送：EventBus callback 可能從 HeartbeatEngine daemon thread 呼叫
        import asyncio
        try:
            self._main_async_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_async_loop = asyncio.get_event_loop()

        # 訂閱脈搏事件
        event_bus.subscribe(PULSE_RHYTHM_CHECK, self._on_rhythm_check)
        event_bus.subscribe(PULSE_NIGHTLY_DONE, self._on_nightly_done)
        event_bus.subscribe(PROACTIVE_MESSAGE, self._on_proactive_message)
        event_bus.subscribe(MORPHENIX_L3_PROPOSAL, self._on_morphenix_l3)
        event_bus.subscribe(MORPHENIX_EXECUTION_COMPLETED, self._on_morphenix_executed)
        event_bus.subscribe(MORPHENIX_ROLLBACK, self._on_morphenix_rollback)
        logger.info("TelegramAdapter connected to pulse EventBus")

    def _on_rhythm_check(self, data: Optional[Dict] = None) -> None:
        """處理 Rhythm-Pulse 推播事件.

        EventBus 是同步的，callback 可能從 HeartbeatEngine daemon thread 呼叫，
        因此用 run_coroutine_threadsafe 排入 Telegram 主事件迴圈。
        """
        if not data or not self._running:
            return
        message = data.get("message", "")
        if not message:
            return
        try:
            main_loop = getattr(self, "_main_async_loop", None)
            if main_loop and not main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(self.push_notification(message), main_loop)
            else:
                logger.warning("Rhythm check: 主事件迴圈不可用，跳過推送")
        except Exception as e:
            logger.error(f"Rhythm check push failed: {e}")

    def _on_nightly_done(self, data: Optional[Dict] = None) -> None:
        """處理凌晨管線完成事件 → 晨間廣播."""
        if not data or not self._running:
            return
        summary = data.get("summary", "")
        if not summary:
            return
        try:
            main_loop = getattr(self, "_main_async_loop", None)
            if main_loop and not main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(self.push_notification(summary), main_loop)
            else:
                logger.warning("Nightly done: 主事件迴圈不可用，跳過推送")
        except Exception as e:
            logger.error(f"Nightly done push failed: {e}")

    def _on_proactive_message(self, data: Optional[Dict] = None) -> None:
        """處理主動互動推播事件.

        ProactiveBridge 發布 PROACTIVE_MESSAGE 事件時觸發。
        callback 可能從 HeartbeatEngine daemon thread 呼叫，
        因此用 run_coroutine_threadsafe 排入 Telegram 主事件迴圈。
        """
        if not data or not self._running:
            return
        message = data.get("message", "")
        if not message:
            return
        try:
            async def _push_and_report():
                sent = await self.push_notification(message)
                if sent > 0 and self._event_bus:
                    from museon.core.event_bus import PULSE_PROACTIVE_SENT
                    self._event_bus.publish(PULSE_PROACTIVE_SENT, {
                        "message": message[:200],
                        "sent_count": sent,
                        "push_count": data.get("push_count", 0),
                    })

            main_loop = getattr(self, "_main_async_loop", None)
            if main_loop and not main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(_push_and_report(), main_loop)
            else:
                logger.warning("Proactive message: 主事件迴圈不可用，跳過推送")
        except Exception as e:
            logger.error(f"Proactive message push failed: {e}")

    def _on_morphenix_l3(self, data: Optional[Dict] = None) -> None:
        """處理 Morphenix L3 提案事件 → Telegram inline keyboard 通知."""
        if not data or not self._running:
            return
        proposals = data.get("proposals", [])
        if not proposals:
            return
        try:
            main_loop = getattr(self, "_main_async_loop", None)
            if not main_loop or main_loop.is_closed():
                logger.warning("Morphenix L3: 主事件迴圈不可用，跳過推送")
                return
            for p in proposals:
                asyncio.run_coroutine_threadsafe(
                    self.push_proposal_notification(
                        proposal_id=p["id"],
                        title=p.get("title", "L3 提案"),
                        description=p.get("description", ""),
                        level="L3",
                        affected_files=p.get("affected_files", []),
                    ),
                    main_loop,
                )
        except Exception as e:
            logger.error(f"Morphenix L3 push failed: {e}")

    def _on_morphenix_executed(self, data: Optional[Dict] = None) -> None:
        """處理 Morphenix 執行完成事件 → Telegram 通知."""
        if not data or not self._running:
            return
        executed = data.get("executed", 0)
        failed = data.get("failed", 0)
        details = data.get("details", [])
        if executed == 0 and failed == 0:
            return

        # 組裝通知訊息
        lines = ["🔥 *Morphenix Executor 報告*\n"]
        if executed > 0:
            lines.append(f"✅ 成功執行：{executed} 個提案")
        if failed > 0:
            lines.append(f"❌ 執行失敗：{failed} 個提案")

        for d in details[:5]:
            pid = d.get("proposal_id", "?")
            outcome = d.get("outcome", "?")
            title = d.get("title", "")
            level = d.get("level", "")
            safety_tag = d.get("safety_tag", "")
            icon = {"executed": "✅", "failed": "❌", "escalated": "⬆️"}.get(outcome, "❓")
            line = f"  {icon} `{pid}`"
            if level:
                line += f" [{level}]"
            if title:
                line += f" — {title}"
            lines.append(line)
            if safety_tag and outcome == "executed":
                lines.append(f"    🛡️ 安全快照：`{safety_tag}`")

        text = "\n".join(lines)

        if not self.application:
            logger.warning("Telegram adapter not initialized, skipping Morphenix notification")
            return

        try:
            owner_id = int(os.environ.get("TELEGRAM_OWNER_ID", "6969045906"))
            async def _safe_send():
                try:
                    await self.application.bot.send_message(
                        chat_id=owner_id,
                        text=text,
                        parse_mode="Markdown",
                    )
                except Exception as send_err:
                    logger.warning(f"Morphenix execution push send failed: {send_err}")

            main_loop = getattr(self, "_main_async_loop", None)
            if main_loop and not main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(_safe_send(), main_loop)
            else:
                logger.warning("Morphenix execution: 主事件迴圈不可用，跳過推送")
        except Exception as e:
            logger.error(f"Morphenix execution push failed: {e}")

    def _on_morphenix_rollback(self, data: Optional[Dict] = None) -> None:
        """處理 Morphenix 回滾事件 → Telegram 緊急通知."""
        if not data or not self._running:
            return

        rollback_type = data.get("type", "")

        if rollback_type == "daily_limit_reached":
            text = (
                "🚨 *Morphenix 緊急通知*\n\n"
                f"⛔ 每日回滾上限已達 ({data.get('rollback_count', '?')}"
                f"/{data.get('max_allowed', '?')})\n"
                "🔒 Morphenix 執行已自動暫停\n"
                "👤 需要人類介入檢查"
            )
        else:
            pid = data.get("proposal_id", "?")
            reason = data.get("reason", "unknown")
            tag = data.get("tag_name", "?")
            text = (
                "⚠️ *Morphenix 回滾通知*\n\n"
                f"📋 提案：`{pid}`\n"
                f"📌 原因：{reason}\n"
                f"🔄 回滾至：`{tag}`\n"
                f"🕐 時間：{data.get('timestamp', '?')}"
            )

        if not self.application:
            logger.warning("Telegram adapter not initialized, skipping rollback notification")
            return

        try:
            owner_id = int(os.environ.get("TELEGRAM_OWNER_ID", "6969045906"))
            async def _safe_send():
                try:
                    await self.application.bot.send_message(
                        chat_id=owner_id,
                        text=text,
                        parse_mode="Markdown",
                    )
                except Exception as send_err:
                    logger.warning(f"Morphenix rollback push send failed: {send_err}")

            main_loop = getattr(self, "_main_async_loop", None)
            if main_loop and not main_loop.is_closed():
                asyncio.run_coroutine_threadsafe(_safe_send(), main_loop)
            else:
                logger.warning("Morphenix rollback: 主事件迴圈不可用，跳過推送")
        except Exception as e:
            logger.error(f"Morphenix rollback push failed: {e}")

    def record_user_interaction(self, user_id: str) -> None:
        """記錄用戶互動 → 更新 HeartbeatFocus + 清除閒置推播狀態.

        應在每次收到用戶訊息時呼叫。
        """
        # 清除閒置推播狀態
        self._notified_users.discard(user_id)

        # 記錄到 HeartbeatFocus
        if self._heartbeat_focus:
            self._heartbeat_focus.record_interaction()

    def is_user_notified(self, user_id: str) -> bool:
        """用戶是否已被閒置推播通知過."""
        return user_id in self._notified_users

    def mark_user_notified(self, user_id: str) -> None:
        """標記用戶已被閒置推播通知."""
        self._notified_users.add(user_id)
