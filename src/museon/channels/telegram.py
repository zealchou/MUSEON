"""Telegram Channel Adapter using python-telegram-bot 20.x."""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
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
    GROUP_SESSION_END,
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

        # ProactiveDispatcher（Phase 1：推播大總管，由 server.py 注入）
        self._proactive_dispatcher = None
        self._current_push_source: str = "unknown"

        # Deduplication: 追蹤已處理的 update_id，防止重複訊息
        self._seen_update_ids: set = set()
        self._max_seen_update_ids = 1000  # 避免無限成長

        # Content-hash deduplication: 防止相同內容在短時間內重複送達
        # {content_hash: last_seen_timestamp}
        self._content_dedup: Dict[str, float] = {}
        self._content_dedup_window = 30.0  # 30 秒內相同內容只處理一次

        # Bot identity cache (set after application.start())
        self._bot_username: str = ""
        self._bot_id: Optional[int] = None

        # Pending group file uploads: {chat_id: [(update, timestamp), ...]}
        # Files uploaded without @mention are held here for 10 minutes
        self._pending_group_files: Dict[int, list] = {}
        self._pending_file_ttl = 600  # seconds

        # Group session idle tracking: {group_id: last_activity_timestamp}
        self._group_last_activity: Dict[int, float] = {}
        self._group_session_idle_seconds = 30 * 60  # 30 分鐘無訊息 → 視為會話結束
        self._group_msg_counts: Dict[int, int] = {}  # 本次會話訊息數

        # v10.0: InteractionRequest 互動佇列
        self._interaction_queue = None  # InteractionQueue instance (set externally)
        self._pending_freetext: Dict[str, str] = {}  # {question_id: chat_id} 等待自由文字輸入

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

        # 授權系統 handlers: /pair, /auth + inline keyboard callbacks
        self.application.add_handler(CommandHandler("pair", self._handle_pair_command))
        self.application.add_handler(CommandHandler("auth", self._handle_auth_command))
        self.application.add_handler(
            CallbackQueryHandler(self._handle_pairing_callback, pattern=r"^pair:")
        )
        self.application.add_handler(
            CallbackQueryHandler(self._handle_auth_callback, pattern=r"^auth:")
        )

        # v10.0: InteractionRequest choice callback
        self.application.add_handler(
            CallbackQueryHandler(self._handle_choice_callback, pattern=r"^choice:")
        )

        # Start polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        # Cache bot identity so group mention checks don't rely on context.bot
        try:
            bot_info = await self.application.bot.get_me()
            self._bot_username = (bot_info.username or "").lower()
            self._bot_id = bot_info.id
            logger.info("Bot identity cached: @%s (id=%s)", self._bot_username, self._bot_id)
        except Exception as _e:
            logger.warning("Failed to cache bot identity: %s", _e)

        # ── 統一發送出口攔截（Safe Send Wrapper）──
        # 所有 bot.send_message 呼叫都經過此 wrapper，
        # 確保群組訊息 100% 過 sanitize，消滅多路徑繞過問題。
        self._install_safe_send_wrapper()

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

    def _install_safe_send_wrapper(self) -> None:
        """安裝統一發送出口 — 所有發送都過 sanitize.

        策略：不 monkey-patch ExtBot（PTB frozen 屬性不允許），
        改為提供 self._safe_send() 方法，並在所有發送路徑前統一呼叫。
        """
        if getattr(self, '_safe_send_installed', False):
            return
        self._safe_send_installed = True
        logger.info("[SafeSend] Unified send wrapper installed — _safe_send() ready")

    async def _safe_send(self, chat_id: int, text: str, **kwargs) -> Any:
        """統一發送出口 — 所有訊息發送前過 sanitize + 空訊息攔截.

        取代直接呼叫 self.application.bot.send_message()，
        確保群組訊息 100% 過 ResponseGuard sanitize。
        """
        if not text or not text.strip():
            logger.warning(f"[SafeSend] blocked empty message to chat_id={chat_id}")
            return None

        try:
            from museon.governance.response_guard import ResponseGuard
            is_group = int(chat_id) < 0
            cleaned = ResponseGuard.sanitize_for_group(text, is_group=is_group)
            if cleaned != text:
                logger.info(
                    f"[SafeSend] sanitized for chat_id={chat_id} "
                    f"(removed {len(text) - len(cleaned)} chars)"
                )
            text = cleaned
            if not text or not text.strip():
                logger.warning(f"[SafeSend] blocked empty-after-sanitize to chat_id={chat_id}")
                return None
        except Exception as e:
            logger.debug(f"[SafeSend] sanitize skipped: {e}")

        return await self.application.bot.send_message(chat_id=chat_id, text=text, **kwargs)

    async def _handle_message(self, update: Update, context: Any) -> None:
        """Handle incoming text message."""
        if update.update_id in self._seen_update_ids:
            logger.debug("Duplicate update_id %s, skipping", update.update_id)
            return
        self._seen_update_ids.add(update.update_id)
        if len(self._seen_update_ids) > self._max_seen_update_ids:
            self._seen_update_ids = set(list(self._seen_update_ids)[-500:])

        # Content-hash deduplication: 相同 chat+user+內容 在 30 秒內只處理一次
        if update.message:
            _msg = update.message
            _raw = f"{_msg.chat_id}:{getattr(_msg.from_user, 'id', '')}:{_msg.text or ''}"
            _chash = hashlib.md5(_raw.encode()).hexdigest()
            _now = time.time()
            if _chash in self._content_dedup and _now - self._content_dedup[_chash] < self._content_dedup_window:
                logger.warning(
                    "Content-dedup: skipping repeated message (hash=%s, update_id=%s, delta=%.1fs)",
                    _chash[:8], update.update_id, _now - self._content_dedup[_chash]
                )
                return
            self._content_dedup[_chash] = _now
            # 清理過期記錄
            if len(self._content_dedup) > 200:
                cutoff = _now - self._content_dedup_window
                self._content_dedup = {k: v for k, v in self._content_dedup.items() if v > cutoff}

        # ── v10.0: InteractionRequest freetext 攔截 ──
        # 使用者選了「自己說明」後，下一則文字訊息作為自由輸入回應
        if update.message and self._pending_freetext:
            chat_id_str = str(update.message.chat_id)
            for qid, pending_chat_id in list(self._pending_freetext.items()):
                if chat_id_str == pending_chat_id:
                    from museon.gateway.message import InteractionResponse
                    response = InteractionResponse(
                        question_id=qid,
                        selected=[],
                        free_text=update.message.text or "",
                        responder_id=str(update.message.from_user.id) if update.message.from_user else "",
                        channel="telegram",
                    )
                    if self._interaction_queue:
                        self._interaction_queue.resolve(qid, response)
                    del self._pending_freetext[qid]
                    logger.debug(f"InteractionRequest freetext resolved: qid={qid}")
                    return  # 不進入正常訊息處理流程

        # ── Group chat: read all, reply only when @mentioned ──
        if update.message and update.message.chat.type in ("group", "supergroup"):
            from_user = update.message.from_user
            user_id_str = str(from_user.id) if from_user else ""
            is_owner = user_id_str in self.trusted_user_ids

            # Check if bot is @mentioned (must be THIS bot, not any @user)
            text = update.message.text or ""
            is_mentioned = False
            bot_username = self._bot_username
            bot_id = self._bot_id
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
            # 追蹤群組活動（閒置偵測用）
            self._track_group_activity(chat_id)
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
                    text=(text or "")[:8000],
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

        # Inject any pending group file uploads before this @mention message
        if update.message and update.message.chat.type in ("group", "supergroup"):
            chat_id = update.message.chat.id
            if chat_id in self._pending_group_files and self._pending_group_files[chat_id]:
                import time as _time
                cutoff = _time.time() - self._pending_file_ttl
                valid_files = [(u, t) for u, t in self._pending_group_files[chat_id] if t > cutoff]
                for file_update, _ts in valid_files:
                    logger.info("Injecting pending file upload into queue for chat %s", chat_id)
                    if file_update.message and file_update.message.from_user:
                        self.record_user_interaction(str(file_update.message.from_user.id))
                    await self.message_queue.put(file_update)
                self._pending_group_files[chat_id] = []

        # 記錄互動（HeartbeatFocus + 清除閒置推播狀態）
        if update.message and update.message.from_user:
            self.record_user_interaction(str(update.message.from_user.id))

        # DM 訊息落地到 GroupContextStore（chat_id 為正數，區分群組的負數 ID）
        if update.message and update.message.chat.type == "private":
            try:
                from museon.governance.group_context import get_group_context_store
                _dm_store = get_group_context_store()
                _dm_user = update.message.from_user
                _dm_store.record_message(
                    group_id=update.message.chat_id,
                    user_id=str(_dm_user.id) if _dm_user else "unknown",
                    text=(update.message.text or "")[:8000],
                    message_id=update.message.message_id,
                    msg_type="dm",
                    display_name=_dm_user.first_name or "" if _dm_user else "",
                    username=_dm_user.username or "" if _dm_user else "",
                )
            except Exception as _dm_err:
                logger.debug(f"DM context DB write error: {_dm_err}")

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
                    text=f"[檔案: {fname}] {caption}"[:8000],
                    message_id=update.message.message_id,
                    msg_type="file",
                    display_name=sender_name,
                    username=from_user.username or "" if from_user else "",
                )
            except Exception as _db_err:
                logger.debug(f"Group context DB write error (file): {_db_err}")

            # Check @mention in caption (must be THIS bot, not any @user)
            is_mentioned = False
            _bot_username = self._bot_username
            _bot_id = self._bot_id
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
                # Stash the update so a subsequent @mention can retrieve it
                import time as _time
                if chat_id not in self._pending_group_files:
                    self._pending_group_files[chat_id] = []
                self._pending_group_files[chat_id].append((update, _time.time()))
                # Prune expired entries
                cutoff = _time.time() - self._pending_file_ttl
                self._pending_group_files[chat_id] = [
                    (u, t) for u, t in self._pending_group_files[chat_id] if t > cutoff
                ]
                logger.info("Group file upload stashed from %s in chat %s (pending @mention)", user_id_str, chat_id)
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
                msg = await self._safe_send(
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

            from museon.pulse.pulse_db import get_pulse_db
            db = get_pulse_db(brain.data_dir)

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

    def _track_group_activity(self, group_id: int) -> None:
        """追蹤群組訊息活動，用於閒置偵測."""
        import time as _time
        now = _time.time()
        prev = self._group_last_activity.get(group_id)
        # 如果距上次訊息已超過閒置閾值，視為新會話
        if prev and (now - prev) > self._group_session_idle_seconds:
            self._group_msg_counts[group_id] = 0
        self._group_last_activity[group_id] = now
        self._group_msg_counts[group_id] = self._group_msg_counts.get(group_id, 0) + 1

    def check_group_session_idle(self) -> None:
        """檢查所有群組的閒置狀態，發布 GROUP_SESSION_END 事件.

        由 HeartbeatEngine tick 定期呼叫。
        """
        import time as _time
        now = _time.time()
        ended_groups = []
        for group_id, last_ts in list(self._group_last_activity.items()):
            elapsed = now - last_ts
            if elapsed >= self._group_session_idle_seconds:
                msg_count = self._group_msg_counts.get(group_id, 0)
                if msg_count > 0 and self._event_bus:
                    self._event_bus.publish(GROUP_SESSION_END, {
                        "group_id": group_id,
                        "session_duration_seconds": int(elapsed),
                        "message_count": msg_count,
                    })
                    logger.info(
                        f"GROUP_SESSION_END published | group={group_id} "
                        f"msgs={msg_count} idle={int(elapsed)}s"
                    )
                ended_groups.append(group_id)
        # 清理已結束的會話
        for gid in ended_groups:
            self._group_msg_counts[gid] = 0

    async def send_dm_to_owner(self, text: str) -> bool:
        """Send a DM directly to the owner (first trusted_user_id)."""
        if not self.application or not self.trusted_user_ids:
            return False
        try:
            owner_id = int(self.trusted_user_ids[0])
            await self._safe_send(chat_id=owner_id, text=text)
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

            # Telegram 單則訊息上限 4096 字元，超長自動分段（P0-3：統一用 _split_long_text）
            parts = self._split_long_text(clean_text)
            for i, part in enumerate(parts):
                # Telegram Flood Control（429）防禦：RetryAfter 自動重試
                for _retry in range(3):
                    try:
                        await self._safe_send(chat_id=chat_id, text=part)
                        break
                    except Exception as _send_err:
                        _err_str = str(_send_err)
                        if "Flood control" in _err_str or "429" in _err_str or "retry_after" in _err_str.lower():
                            # 從錯誤訊息提取 retry_after 秒數
                            import re
                            _retry_match = re.search(r'retry.after[=: ]*(\d+)', _err_str, re.IGNORECASE)
                            _wait = int(_retry_match.group(1)) if _retry_match else 5
                            logger.warning(f"Telegram Flood Control: waiting {_wait}s (retry {_retry+1}/3)")
                            await asyncio.sleep(_wait + 1)
                        else:
                            raise  # 非 Flood Control 錯誤，不重試
                if i < len(parts) - 1:
                    await asyncio.sleep(0.3)  # 間隔從 0.15s 提高到 0.3s

            # Bot 回覆落地到 GroupContextStore
            try:
                from museon.governance.group_context import get_group_context_store
                _reply_store = get_group_context_store()
                _reply_store.record_message(
                    group_id=int(chat_id),
                    user_id="bot",
                    text=clean_text[:8000],
                    msg_type="bot_reply",
                    display_name="MUSEON",
                )
            except Exception as _reply_err:
                logger.debug(f"Bot reply DB write error: {_reply_err}")

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

        Hierarchy:
        1. Static trusted list (.env) → CORE
        2. Dynamic pairing (PairingManager) → VERIFIED
        3. Otherwise → EXTERNAL
        """
        if user_id in self.trusted_user_ids:
            return TrustLevel.CORE
        # 動態配對授權
        try:
            from museon.gateway.authorization import get_pairing_manager
            pm = get_pairing_manager()
            dynamic_trust = pm.get_dynamic_trust(user_id)
            if dynamic_trust == "TRUSTED":
                return TrustLevel.CORE
            if dynamic_trust == "VERIFIED":
                return TrustLevel.VERIFIED
        except Exception:
            pass
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
            msg = await self._safe_send(chat_id=chat_id, text=text)
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
            except asyncio.CancelledError as e:
                logger.debug(f"[TELEGRAM] async op failed (degraded): {e}")
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
            except asyncio.CancelledError as e:
                logger.debug(f"[TELEGRAM] operation failed (degraded): {e}")

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

    @staticmethod
    def _split_long_text(text: str, max_len: int = 4096) -> list:
        """將超長文字按段落邊界切分（P0-3：統一分段邏輯）."""
        if not text or len(text) <= max_len:
            return [text] if text else []
        chunks = []
        remaining = text
        while remaining:
            if len(remaining) <= max_len:
                chunks.append(remaining)
                break
            # 優先在段落邊界（\n\n）切，其次在換行（\n）切
            cut = remaining[:max_len].rfind("\n\n")
            if cut < 500:
                cut = remaining[:max_len].rfind("\n")
            if cut < 500:
                cut = max_len
            chunk = remaining[:cut].rstrip()
            remaining = remaining[cut:].lstrip()
            if chunk:
                chunks.append(chunk)
        return chunks

    async def push_notification(
        self, text: str, chat_ids: Optional[list] = None
    ) -> int:
        """推播通知到指定或所有受信任使用者 — 零 Token.

        P0-3 修復：超長訊息自動分段（之前直接送出會被 Telegram 截斷）。

        Args:
            text: 推播訊息（純文字或 Telegram Markdown）
            chat_ids: 指定推播的 chat_id 列表，None = 所有 trusted users

        Returns:
            成功送出的訊息數量
        """
        if not self.application or not self._running:
            logger.warning("Telegram adapter not running, cannot push notification")
            return 0

        # ProactiveDispatcher 攔截（Phase 1）
        try:
            if self._proactive_dispatcher:
                allowed, reason = await self._proactive_dispatcher.should_allow(
                    text, source=self._current_push_source
                )
                if not allowed:
                    logger.info(f"[Dispatcher] Push blocked: {reason}")
                    return 0
        except Exception as e:
            logger.debug(f"[Dispatcher] check skipped: {e}")

        targets = chat_ids or [int(uid) for uid in self.trusted_user_ids if uid]
        if not targets:
            logger.warning("No push targets (trusted_user_ids empty)")
            return 0

        # P0-3：超長文字分段
        parts = self._split_long_text(text)
        if not parts:
            return 0

        sent = 0
        for cid in targets:
            try:
                last_msg = None
                for i, part in enumerate(parts):
                    last_msg = await self._safe_send(
                        chat_id=cid, text=part
                    )
                    if i < len(parts) - 1:
                        await asyncio.sleep(0.15)
                sent += 1
                # 追蹤主動推送 message_id（用於回覆串接）
                if last_msg and last_msg.message_id:
                    self._proactive_message_ids[last_msg.message_id] = text[:200]
                    # 維持上限
                    if len(self._proactive_message_ids) > self._max_proactive_ids:
                        oldest = next(iter(self._proactive_message_ids))
                        del self._proactive_message_ids[oldest]
            except Exception as e:
                logger.error(f"Push notification failed for chat_id={cid}: {e}")

        logger.info(f"📢 Push notification sent to {sent}/{len(targets)} users ({len(parts)} parts)")

        # 記錄到 24hr 日誌（ProactiveDispatcher Phase 1）
        if sent > 0:
            try:
                if self._proactive_dispatcher:
                    self._proactive_dispatcher.record_push(
                        text, source=self._current_push_source
                    )
            except Exception:
                pass

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
        event_bus.subscribe(PROACTIVE_MESSAGE, self._on_proactive_message)
        event_bus.subscribe(MORPHENIX_L3_PROPOSAL, self._on_morphenix_l3)
        event_bus.subscribe(MORPHENIX_EXECUTION_COMPLETED, self._on_morphenix_executed)
        event_bus.subscribe(MORPHENIX_ROLLBACK, self._on_morphenix_rollback)
        logger.info("TelegramAdapter connected to pulse EventBus")

    def _on_proactive_message(self, data: Optional[Dict] = None) -> None:
        """處理主動互動推播事件.

        ProactiveBridge 發布 PROACTIVE_MESSAGE 事件時觸發。
        callback 可能從 HeartbeatEngine daemon thread 呼叫，
        因此用 run_coroutine_threadsafe 排入 Telegram 主事件迴圈。

        P1 修復：推送成功後寫入 Brain session history，
        避免使用者回覆推送時 Brain 沒有前文。
        """
        if not data or not self._running:
            return
        message = data.get("message", "")
        if not message:
            return
        # 提取推播來源供 Dispatcher 使用
        self._current_push_source = data.get("source", "proactive")
        try:
            async def _push_and_report():
                sent = await self.push_notification(message)
                if sent > 0:
                    # P1: 推送內容寫入 Brain session history
                    self._write_push_to_session(message)

                    if self._event_bus:
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

    def _write_push_to_session(self, message: str) -> None:
        """將推送內容寫入 owner 的 Brain session history.

        讓 Brain 在使用者回覆時能看到推送前文，
        避免上下文斷裂。
        """
        try:
            brain = self._get_brain()
            if not brain:
                return

            # 取得 owner session_id
            if not self.trusted_user_ids:
                return
            owner_chat_id = self.trusted_user_ids[0]
            session_id = f"telegram_{owner_chat_id}"

            # 寫入 session history（assistant role，帶推送標記前綴）
            from datetime import datetime
            push_prefix = f"[主動推送 {datetime.now().strftime('%H:%M')}]"
            push_content = f"{push_prefix} {message[:500]}"

            history = brain._get_session_history(session_id)
            history.append({
                "role": "assistant",
                "content": push_content,
            })
            brain._save_session_to_disk(session_id)

            logger.debug(
                f"推送已寫入 session {session_id}: {push_content[:80]}..."
            )
        except Exception as e:
            logger.debug(f"推送寫入 session 失敗（降級運行）: {e}")

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
                    await self._safe_send(
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
                    await self._safe_send(
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

    # ══════════════════════════════════════════════════
    # 授權系統 Handlers
    # ══════════════════════════════════════════════════

    async def _handle_pair_command(
        self, update: Update, context: Any,
    ) -> None:
        """處理 /pair 指令 — 非信任使用者請求配對."""
        if not update.message:
            return
        user_id = str(update.effective_user.id)
        display_name = update.effective_user.first_name or "Unknown"

        # 已信任使用者不需配對
        if user_id in self.trusted_user_ids:
            await update.message.reply_text("你已經是信任使用者，不需要配對。")
            return

        # 已配對？
        try:
            from museon.gateway.authorization import get_pairing_manager
            pm = get_pairing_manager()
            if pm.is_paired(user_id):
                await update.message.reply_text("你已完成配對，可以直接使用。")
                return
        except Exception as e:
            logger.error(f"Pair command error: {e}")
            await update.message.reply_text("授權系統暫時不可用，請稍後再試。")
            return

        # 生成配對碼
        code = pm.generate_code(user_id, display_name)
        await update.message.reply_text(
            f"你的配對碼：{code}\n"
            f"有效期 5 分鐘，已通知管理員。\n"
            f"等待管理員批准後即可使用。"
        )

        # 推到老闆 DM（inline keyboard）
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ 批准", callback_data=f"pair:approve:{code}"),
                InlineKeyboardButton("❌ 拒絕", callback_data=f"pair:deny:{code}"),
            ],
            [
                InlineKeyboardButton("⏰ 臨時 24h", callback_data=f"pair:temp:{code}"),
            ],
        ])
        await self.send_dm_to_owner(
            f"🔑 配對請求\n\n"
            f"使用者：{display_name} (ID: {user_id})\n"
            f"配對碼：{code}\n"
            f"時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        # 發 inline keyboard 給老闆
        if self.application and self.trusted_user_ids:
            try:
                owner_id = int(self.trusted_user_ids[0])
                await self._safe_send(
                    chat_id=owner_id,
                    text="選擇操作：",
                    reply_markup=keyboard,
                )
            except Exception as e:
                logger.error(f"Send pairing keyboard failed: {e}")

    async def _handle_pairing_callback(
        self, update: Update, context: Any,
    ) -> None:
        """處理配對 inline keyboard 回調（pair:approve/deny/temp:CODE）."""
        query = update.callback_query
        if not query or not query.data:
            return

        # 只有老闆可以批准
        user_id = str(query.from_user.id)
        if user_id not in self.trusted_user_ids:
            await query.answer("⛔ 無權限操作", show_alert=True)
            return

        parts = query.data.split(":")
        if len(parts) != 3:
            await query.answer("格式錯誤")
            return

        _, action, code = parts

        try:
            from museon.gateway.authorization import get_pairing_manager
            pm = get_pairing_manager()
            result = pm.verify_code(code)

            if not result:
                await query.answer("配對碼無效或已過期", show_alert=True)
                await query.edit_message_text(f"❌ 配對碼 {code} 已失效")
                return

            paired_uid = result["user_id"]
            paired_name = result["display_name"]

            if action == "approve":
                pm.add_user(paired_uid, paired_name, trust_level="VERIFIED")
                await query.answer("✅ 已批准配對")
                await query.edit_message_text(
                    f"✅ 使用者 {paired_name} 已配對\n"
                    f"信任等級：VERIFIED（永久）"
                )
                # 通知被配對的使用者
                try:
                    await self._safe_send(
                        chat_id=int(paired_uid),
                        text="✅ 配對成功！你現在可以使用 MUSEON。",
                    )
                except Exception:
                    pass

            elif action == "temp":
                ttl = 86400  # 24 hours
                pm.add_user(paired_uid, paired_name, trust_level="VERIFIED", ttl=ttl)
                await query.answer("⏰ 已授予 24h 臨時權限")
                await query.edit_message_text(
                    f"⏰ 使用者 {paired_name} 已臨時配對\n"
                    f"信任等級：VERIFIED（24 小時）"
                )
                try:
                    await self._safe_send(
                        chat_id=int(paired_uid),
                        text="✅ 臨時配對成功！你有 24 小時的使用權限。",
                    )
                except Exception:
                    pass

            elif action == "deny":
                await query.answer("❌ 已拒絕")
                await query.edit_message_text(
                    f"❌ 使用者 {paired_name} 的配對已被拒絕"
                )
                try:
                    await self._safe_send(
                        chat_id=int(paired_uid),
                        text="❌ 配對被拒絕。",
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Pairing callback error: {e}")
            await query.answer(f"處理失敗: {e}", show_alert=True)

    async def _handle_auth_callback(
        self, update: Update, context: Any,
    ) -> None:
        """處理工具授權 inline keyboard 回調（auth:approve/deny/grant:ENTRY_ID）."""
        query = update.callback_query
        if not query or not query.data:
            return

        user_id = str(query.from_user.id)
        if user_id not in self.trusted_user_ids:
            await query.answer("⛔ 無權限操作", show_alert=True)
            return

        parts = query.data.split(":")
        if len(parts) != 3:
            await query.answer("格式錯誤")
            return

        _, action, entry_id = parts

        try:
            from museon.gateway.authorization import get_tool_auth_queue
            taq = get_tool_auth_queue()
            entry = taq.get(entry_id)
            if not entry:
                await query.answer("授權請求不存在或已處理", show_alert=True)
                return

            tool_name = entry.get("tool_name", "unknown")
            user_name = entry.get("user_name", "unknown")

            if action == "approve":
                taq.resolve(entry_id, approved=True)
                await query.answer("✅ 已允許")
                await query.edit_message_text(
                    f"✅ 工具 {tool_name} 已允許\n"
                    f"使用者：{user_name}"
                )

            elif action == "deny":
                taq.resolve(entry_id, approved=False)
                await query.answer("❌ 已拒絕")
                await query.edit_message_text(
                    f"❌ 工具 {tool_name} 已拒絕\n"
                    f"使用者：{user_name}"
                )

            elif action == "grant":
                # session-level grant
                session_id = entry.get("session_id", "")
                taq.resolve(entry_id, approved=True)
                taq.grant_session(session_id, tool_name)
                await query.answer("✅ 本工具全允許")
                await query.edit_message_text(
                    f"✅ 工具 {tool_name} — 本會話全允許\n"
                    f"使用者：{user_name}"
                )

        except Exception as e:
            logger.error(f"Auth callback error: {e}")
            await query.answer(f"處理失敗: {e}", show_alert=True)

    async def _handle_auth_command(
        self, update: Update, context: Any,
    ) -> None:
        """處理 /auth 指令 — 授權管理（僅限老闆）.

        /auth list — 列出當前策略
        /auth move <tool> <tier> — 移動工具到指定級別
        /auth users — 列出配對使用者
        /auth revoke <user_id> — 撤銷使用者
        """
        if not update.message:
            return
        user_id = str(update.effective_user.id)
        if user_id not in self.trusted_user_ids:
            await update.message.reply_text("⛔ 此指令僅限管理員使用。")
            return

        args = (update.message.text or "").split()
        sub_cmd = args[1] if len(args) > 1 else "list"

        try:
            from museon.gateway.authorization import (
                get_authorization_policy,
                get_pairing_manager,
            )

            if sub_cmd == "list":
                policy = get_authorization_policy()
                p = policy.list_policy()
                lines = ["📋 授權策略\n"]
                for tier_name, tools in p.items():
                    emoji = {"auto": "🟢", "ask": "🟡", "block": "🔴"}.get(tier_name, "⚪")
                    lines.append(f"{emoji} {tier_name}: {', '.join(tools) if tools else '(空)'}")
                await update.message.reply_text("\n".join(lines))

            elif sub_cmd == "move" and len(args) >= 4:
                tool_name = args[2]
                target_tier = args[3]
                policy = get_authorization_policy()
                if policy.move_tool(tool_name, target_tier):
                    await update.message.reply_text(
                        f"✅ 工具 {tool_name} 已移至 {target_tier} 級別"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ 無效的級別：{target_tier}（可用：auto / ask / block）"
                    )

            elif sub_cmd == "users":
                pm = get_pairing_manager()
                users = pm.list_users()
                if not users:
                    await update.message.reply_text("目前無動態配對使用者。")
                    return
                lines = ["👥 動態配對使用者\n"]
                for uid, info in users.items():
                    name = info.get("display_name", "?")
                    trust = info.get("trust_level", "?")
                    ttl = info.get("ttl")
                    ttl_str = f"（{ttl // 3600}h）" if ttl else "（永久）"
                    lines.append(f"  {name} [{uid}] — {trust}{ttl_str}")
                await update.message.reply_text("\n".join(lines))

            elif sub_cmd == "revoke" and len(args) >= 3:
                target_uid = args[2]
                pm = get_pairing_manager()
                if pm.remove_user(target_uid):
                    await update.message.reply_text(f"✅ 使用者 {target_uid} 已撤銷")
                else:
                    await update.message.reply_text(f"❌ 使用者 {target_uid} 不在配對清單中")

            else:
                await update.message.reply_text(
                    "用法：\n"
                    "/auth list — 列出策略\n"
                    "/auth move <tool> <tier> — 移動工具\n"
                    "/auth users — 列出配對使用者\n"
                    "/auth revoke <user_id> — 撤銷使用者"
                )

        except Exception as e:
            logger.error(f"Auth command error: {e}")
            await update.message.reply_text(f"處理失敗：{e}")

    async def push_tool_auth_request(
        self,
        entry_id: str,
        tool_name: str,
        args_summary: str,
        user_name: str,
    ) -> None:
        """推送工具授權請求到老闆 DM（inline keyboard）."""
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ 允許", callback_data=f"auth:approve:{entry_id}"),
                InlineKeyboardButton("❌ 拒絕", callback_data=f"auth:deny:{entry_id}"),
            ],
            [
                InlineKeyboardButton("✅ 本工具全允許", callback_data=f"auth:grant:{entry_id}"),
            ],
        ])

        text = (
            f"🔧 工具授權請求\n\n"
            f"使用者：{user_name}\n"
            f"工具：{tool_name}\n"
            f"參數：{args_summary[:200]}\n"
            f"時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        if self.application and self.trusted_user_ids:
            try:
                owner_id = int(self.trusted_user_ids[0])
                await self._safe_send(
                    chat_id=owner_id,
                    text=text,
                    reply_markup=keyboard,
                )
            except Exception as e:
                logger.error(f"Push tool auth request failed: {e}")

    # ══════════════════════════════════════════════════
    # v10.0: InteractionRequest — 跨通道互動選項
    # ══════════════════════════════════════════════════

    def set_interaction_queue(self, queue) -> None:
        """設定 InteractionQueue 實例（由 server.py 在啟動時呼叫）."""
        self._interaction_queue = queue

    async def present_choices(
        self,
        chat_id: str,
        request,
        interaction_queue,
    ) -> None:
        """呈現互動選項為 Telegram InlineKeyboardMarkup.

        Args:
            chat_id: Telegram chat ID
            request: InteractionRequest 物件
            interaction_queue: InteractionQueue 實例
        """
        self._interaction_queue = interaction_queue

        keyboard = []
        for opt in request.options:
            # callback_data 格式: choice:{question_id}:{value}
            cb_value = opt.value or opt.label
            cb_data = f"choice:{request.question_id}:{cb_value}"

            # Telegram callback_data 限制 64 bytes
            if len(cb_data.encode("utf-8")) > 64:
                # 截斷 value 以符合限制
                max_val_len = 64 - len(f"choice:{request.question_id}:".encode("utf-8"))
                cb_value_truncated = cb_value.encode("utf-8")[:max_val_len].decode("utf-8", errors="ignore")
                cb_data = f"choice:{request.question_id}:{cb_value_truncated}"

            # 按鈕顯示文字
            btn_text = opt.label
            if opt.description:
                btn_text += f" — {opt.description}"

            keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

        # 「其他」自由輸入選項
        if request.allow_free_text:
            ft_data = f"choice:{request.question_id}:__freetext__"
            keyboard.append([InlineKeyboardButton("✏️ 自己說明", callback_data=ft_data)])

        # 組裝訊息文字
        header = f"【{request.header}】\n" if request.header else ""
        multi_hint = "\n（可多選，選完按確認）" if request.multi_select else ""
        text = f"{header}{request.question}{multi_hint}"

        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await self._safe_send(
                chat_id=int(chat_id),
                text=text,
                reply_markup=reply_markup,
            )
            logger.debug(
                f"InteractionRequest presented: qid={request.question_id}, "
                f"options={len(request.options)}, chat={chat_id}"
            )
        except Exception as e:
            logger.error(f"present_choices failed: {e}")

    async def _handle_choice_callback(self, update: Update, context: Any) -> None:
        """處理 InteractionRequest 的 InlineKeyboard callback.

        callback_data 格式: choice:{question_id}:{selected_value}
        """
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()

        parts = query.data.split(":", 2)
        if len(parts) != 3:
            logger.warning(f"Invalid choice callback data: {query.data}")
            return

        _, question_id, selected_value = parts

        # 自由文字模式：標記等待，下一則文字訊息會被攔截
        if selected_value == "__freetext__":
            self._pending_freetext[question_id] = str(query.message.chat_id)
            try:
                await query.edit_message_text(
                    text="✏️ 請直接輸入您的回答："
                )
            except Exception as e:
                logger.debug(f"edit_message_text for freetext failed: {e}")
            return

        # 正常選擇
        from museon.gateway.message import InteractionResponse
        response = InteractionResponse(
            question_id=question_id,
            selected=[selected_value],
            responder_id=str(query.from_user.id) if query.from_user else "",
            channel="telegram",
        )

        # 更新原訊息顯示已選結果
        try:
            await query.edit_message_text(
                text=f"✅ 已選擇：{selected_value}"
            )
        except Exception as e:
            logger.debug(f"edit_message_text for choice result failed: {e}")

        # 解決互動請求
        if self._interaction_queue:
            self._interaction_queue.resolve(question_id, response)
        else:
            logger.warning(
                f"No interaction_queue set for choice callback: qid={question_id}"
            )
