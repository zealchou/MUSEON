"""Email Channel Adapter — IMAP + SMTP 整合.

透過 IMAP 收取未讀郵件、SMTP 發送郵件：
- 非同步輪詢 IMAP UNSEEN 郵件
- 解析 multipart 郵件內容
- SMTP 發送純文字 / HTML 郵件
- 透過 EventBus 發布 CHANNEL_MESSAGE_RECEIVED / CHANNEL_MESSAGE_SENT

設計原則：
- IMAP / SMTP 操作使用 asyncio.to_thread 包裹（imaplib / smtplib 為同步）
- 所有外部操作以 try/except 保護
- 郵件解析容錯（壞編碼、缺欄位等）

標準庫依賴：imaplib, smtplib, email
"""

from __future__ import annotations

import asyncio
import email
import email.header
import email.utils
import imaplib
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from museon.channels.base import ChannelAdapter, TrustLevel
from museon.gateway.message import InternalMessage

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))


class EmailAdapter(ChannelAdapter):
    """Email 通道適配器 — IMAP 收信 + SMTP 發信.

    Features:
    - IMAP UNSEEN 輪詢（支援 SSL）
    - SMTP 發信（支援 STARTTLS / SSL）
    - multipart 郵件解析（text/plain 優先）
    - 信任層級由設定中的 trusted_senders 決定
    - 內部佇列 + EventBus 事件發布
    """

    def __init__(self, config: Dict[str, Any], event_bus: Any = None) -> None:
        """
        Args:
            config: 設定字典，含:
                - imap_host: IMAP 伺服器位址
                - imap_port: IMAP 埠號（預設 993）
                - smtp_host: SMTP 伺服器位址
                - smtp_port: SMTP 埠號（預設 587）
                - username: 郵件帳號
                - password: 郵件密碼（或 app-specific password）
                - use_ssl: IMAP 是否使用 SSL（預設 True）
                - smtp_ssl: SMTP 是否使用 SSL（預設 False, 使用 STARTTLS）
                - trusted_senders: 受信任寄件者 email 列表
                - from_name: 發件人顯示名稱
            event_bus: EventBus 實例（可選）
        """
        super().__init__(config)
        self._imap_host: str = config.get("imap_host", "")
        self._imap_port: int = config.get("imap_port", 993)
        self._smtp_host: str = config.get("smtp_host", "")
        self._smtp_port: int = config.get("smtp_port", 587)
        self._username: str = config.get("username", "")
        self._password: str = config.get("password", "")
        self._use_ssl: bool = config.get("use_ssl", True)
        self._smtp_ssl: bool = config.get("smtp_ssl", False)
        self._trusted_senders: List[str] = config.get("trusted_senders", [])
        self._from_name: str = config.get("from_name", "MUSEON")
        self._event_bus = event_bus

        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running: bool = False
        self._poll_task: Optional[asyncio.Task] = None
        self._poll_interval: int = config.get("poll_interval", 300)  # 5 分鐘

    async def start(self) -> None:
        """啟動郵件輪詢背景任務."""
        if self._running:
            return

        if not self._imap_host or not self._username:
            logger.error("Email imap_host and username are required")
            return

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"EmailAdapter started (IMAP: {self._imap_host}:{self._imap_port}, "
            f"poll interval: {self._poll_interval}s)"
        )

    async def stop(self) -> None:
        """停止郵件輪詢."""
        if not self._running:
            return

        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError as e:
                logger.debug(f"[EMAIL] operation failed (degraded): {e}")
            self._poll_task = None

        logger.info("EmailAdapter stopped")

    async def receive(self) -> InternalMessage:
        """從內部佇列取出已轉換的郵件訊息.

        Returns:
            InternalMessage: 統一訊息格式
        """
        msg = await self._message_queue.get()
        return msg

    async def send(self, message: InternalMessage) -> bool:
        """透過 SMTP 發送郵件.

        Args:
            message: 要發送的 InternalMessage，metadata 需含:
                - to: 收件人 email
                - subject: 郵件主旨
                - html: 可選 HTML 內容（否則用 content 純文字）

        Returns:
            bool: 發送是否成功
        """
        to_addr = message.metadata.get("to", "")
        subject = message.metadata.get("subject", "MUSEON Notification")
        html_body = message.metadata.get("html")

        if not to_addr:
            logger.error("No recipient address in email message metadata")
            return False

        if not self._smtp_host or not self._username:
            logger.error("SMTP not configured")
            return False

        try:
            success = await asyncio.to_thread(
                self._send_smtp, to_addr, subject, message.content, html_body
            )

            if success:
                # 發布送出事件
                try:
                    if self._event_bus is not None:
                        from museon.core.event_bus import CHANNEL_MESSAGE_SENT
                        self._event_bus.publish(CHANNEL_MESSAGE_SENT, {
                            "channel": "email",
                            "to": to_addr,
                            "subject": subject,
                            "content_length": len(message.content),
                            "timestamp": datetime.now(TZ8).isoformat(),
                        })
                except Exception as e:
                    logger.error(f"EventBus publish CHANNEL_MESSAGE_SENT failed: {e}")

            return success

        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False

    def get_trust_level(self, user_id: str) -> TrustLevel:
        """根據寄件者 email 判斷信任層級.

        Args:
            user_id: 寄件者 email

        Returns:
            TrustLevel: 信任等級
        """
        sender_lower = user_id.lower()
        for trusted in self._trusted_senders:
            if sender_lower == trusted.lower():
                return TrustLevel.CORE
        return TrustLevel.EXTERNAL

    # ── IMAP Polling ──

    async def _poll_loop(self) -> None:
        """背景輪詢迴圈."""
        while self._running:
            try:
                messages = await self.poll_inbox()
                for msg in messages:
                    await self._message_queue.put(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Email poll error: {e}")

            try:
                await asyncio.sleep(self._poll_interval)
            except asyncio.CancelledError:
                break

    async def poll_inbox(self, max_messages: int = 10) -> List[InternalMessage]:
        """輪詢 IMAP 收件箱取得未讀郵件.

        Args:
            max_messages: 最大取回郵件數

        Returns:
            InternalMessage 列表
        """
        try:
            results = await asyncio.to_thread(
                self._fetch_unseen_imap, max_messages
            )
            messages: List[InternalMessage] = []
            for raw_msg in results:
                parsed = self._parse_email(raw_msg)
                if parsed:
                    messages.append(parsed)

                    # 發布接收事件
                    try:
                        if self._event_bus is not None:
                            from museon.core.event_bus import CHANNEL_MESSAGE_RECEIVED
                            self._event_bus.publish(CHANNEL_MESSAGE_RECEIVED, {
                                "channel": "email",
                                "user_id": parsed.user_id,
                                "content_length": len(parsed.content),
                                "trust_level": parsed.trust_level,
                                "timestamp": parsed.timestamp.isoformat(),
                            })
                    except Exception as e:
                        logger.error(
                            f"EventBus publish CHANNEL_MESSAGE_RECEIVED failed: {e}"
                        )

            return messages

        except Exception as e:
            logger.error(f"IMAP poll error: {e}")
            return []

    def _fetch_unseen_imap(self, max_messages: int) -> List[email.message.Message]:
        """同步 IMAP 操作 — 取得 UNSEEN 郵件.

        Args:
            max_messages: 最大取回數

        Returns:
            email.message.Message 列表
        """
        messages: List[email.message.Message] = []

        try:
            if self._use_ssl:
                conn = imaplib.IMAP4_SSL(self._imap_host, self._imap_port)
            else:
                conn = imaplib.IMAP4(self._imap_host, self._imap_port)

            conn.login(self._username, self._password)
            conn.select("INBOX")

            status, data = conn.search(None, "UNSEEN")
            if status != "OK" or not data[0]:
                conn.logout()
                return []

            msg_ids = data[0].split()
            # 只取最新的 max_messages 封
            msg_ids = msg_ids[-max_messages:]

            for msg_id in msg_ids:
                try:
                    status, msg_data = conn.fetch(msg_id, "(RFC822)")
                    if status == "OK" and msg_data[0]:
                        raw_bytes = msg_data[0][1]
                        if isinstance(raw_bytes, bytes):
                            parsed = email.message_from_bytes(raw_bytes)
                            messages.append(parsed)
                except Exception as e:
                    logger.warning(f"Failed to fetch email {msg_id}: {e}")

            conn.logout()

        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP error: {e}")
        except Exception as e:
            logger.error(f"IMAP connection error: {e}")

        return messages

    def _parse_email(self, raw: email.message.Message) -> Optional[InternalMessage]:
        """解析原始郵件為 InternalMessage.

        Args:
            raw: email.message.Message 物件

        Returns:
            InternalMessage 或 None（解析失敗時）
        """
        try:
            # 解析寄件者
            from_header = raw.get("From", "")
            from_name, from_addr = email.utils.parseaddr(from_header)
            if not from_addr:
                from_addr = from_header

            # 解析主旨
            subject_raw = raw.get("Subject", "")
            subject = self._decode_header(subject_raw)

            # 解析時間
            date_str = raw.get("Date", "")
            try:
                msg_time = email.utils.parsedate_to_datetime(date_str)
                if msg_time.tzinfo is None:
                    msg_time = msg_time.replace(tzinfo=TZ8)
            except Exception:
                msg_time = datetime.now(TZ8)

            # 解析內文（優先 text/plain）
            body = self._extract_body(raw)
            if not body.strip():
                body = f"[Empty email with subject: {subject}]"

            # 組合 content
            content = f"[Email] {subject}\n\n{body}"

            trust_level = self.get_trust_level(from_addr)

            message_id = raw.get("Message-ID", "")
            session_id = f"email_{from_addr}"

            return InternalMessage(
                source="email",
                session_id=session_id,
                user_id=from_addr,
                content=content,
                timestamp=msg_time,
                trust_level=trust_level.value,
                metadata={
                    "from_name": from_name,
                    "from_addr": from_addr,
                    "subject": subject,
                    "message_id": message_id,
                    "to": raw.get("To", ""),
                    "cc": raw.get("Cc", ""),
                },
            )

        except Exception as e:
            logger.error(f"Email parse error: {e}")
            return None

    @staticmethod
    def _extract_body(msg: email.message.Message) -> str:
        """從 multipart 郵件中提取文字內容.

        優先 text/plain，其次 text/html（去 tag）。

        Args:
            msg: email.message.Message

        Returns:
            提取的文字內容
        """
        if not msg.is_multipart():
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace")
                except Exception:
                    return payload.decode("utf-8", errors="replace")
            return ""

        text_parts: List[str] = []
        html_parts: List[str] = []

        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        text_parts.append(payload.decode(charset, errors="replace"))
                    except Exception:
                        text_parts.append(payload.decode("utf-8", errors="replace"))
            elif content_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html_parts.append(payload.decode(charset, errors="replace"))
                    except Exception:
                        html_parts.append(payload.decode("utf-8", errors="replace"))

        if text_parts:
            return "\n".join(text_parts)

        # Fallback: 簡易去 HTML tag
        if html_parts:
            import re
            html = "\n".join(html_parts)
            clean = re.sub(r"<[^>]+>", "", html)
            clean = re.sub(r"\s+", " ", clean).strip()
            return clean

        return ""

    @staticmethod
    def _decode_header(raw: str) -> str:
        """解碼 MIME 編碼的郵件標頭.

        Args:
            raw: 原始標頭字串

        Returns:
            解碼後的字串
        """
        try:
            parts = email.header.decode_header(raw)
            decoded = []
            for part, charset in parts:
                if isinstance(part, bytes):
                    decoded.append(part.decode(charset or "utf-8", errors="replace"))
                else:
                    decoded.append(str(part))
            return " ".join(decoded)
        except Exception:
            return str(raw)

    # ── SMTP Sending ──

    def _send_smtp(
        self,
        to_addr: str,
        subject: str,
        text_body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """同步 SMTP 發送操作.

        Args:
            to_addr: 收件人 email
            subject: 郵件主旨
            text_body: 純文字內容
            html_body: HTML 內容（可選）

        Returns:
            bool: 是否成功
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{self._from_name} <{self._username}>"
            msg["To"] = to_addr
            msg["Subject"] = subject

            msg.attach(MIMEText(text_body, "plain", "utf-8"))
            if html_body:
                msg.attach(MIMEText(html_body, "html", "utf-8"))

            if self._smtp_ssl:
                server = smtplib.SMTP_SSL(self._smtp_host, self._smtp_port)
            else:
                server = smtplib.SMTP(self._smtp_host, self._smtp_port)
                server.starttls()

            server.login(self._username, self._password)
            server.send_message(msg)
            server.quit()

            logger.info(f"Email sent to {to_addr}: {subject}")
            return True

        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False

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
            "imap_configured": bool(self._imap_host and self._username),
            "smtp_configured": bool(self._smtp_host and self._username),
            "poll_interval": self._poll_interval,
            "imap_host": self._imap_host,
            "smtp_host": self._smtp_host,
        }
