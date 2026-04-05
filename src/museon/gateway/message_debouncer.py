"""Message Debouncer — 合併使用者連發的多則訊息.

使用者在短時間內連發多則文字或多個檔案時，
debouncer 會緩衝這些訊息，等待一段靜默期後合併成一則處理。

設計原則：
- 每個 chat_id 一個獨立的緩衝區
- 靜默期內收到新訊息 → 重設計時器
- 靜默期結束 → 合併所有緩衝訊息，呼叫 handler
- 第一則訊息立刻觸發 typing indicator（用戶不會覺得無反應）
"""

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)

# 預設靜默等待秒數
DEFAULT_QUIET_SECONDS = 4.0
# 最長等待時間（避免使用者一直打字導致永遠不觸發）
MAX_WAIT_SECONDS = 15.0


class MessageDebouncer:
    """Per-chat_id 訊息合併器."""

    def __init__(
        self,
        handler: Callable[[Any, Any], Coroutine],
        adapter: Any,
        quiet_seconds: float = DEFAULT_QUIET_SECONDS,
        max_wait_seconds: float = MAX_WAIT_SECONDS,
    ):
        """初始化 debouncer.

        Args:
            handler: 合併後呼叫的處理函數 (adapter, merged_message) -> None
            adapter: TelegramAdapter 實例
            quiet_seconds: 靜默等待秒數
            max_wait_seconds: 最長等待時間
        """
        self._handler = handler
        self._adapter = adapter
        self._quiet_seconds = quiet_seconds
        self._max_wait_seconds = max_wait_seconds

        # 緩衝區：chat_id → list of messages
        self._buffers: Dict[str, List[Any]] = {}
        # 計時器：chat_id → asyncio.Task
        self._timers: Dict[str, asyncio.Task] = {}
        # 第一則訊息到達時間：chat_id → timestamp
        self._first_arrival: Dict[str, float] = {}

    def _get_chat_key(self, message: Any) -> str:
        """從訊息中提取 chat_id 作為 buffer key."""
        chat_id = getattr(message, 'metadata', {}).get('chat_id')
        if chat_id:
            return str(chat_id)
        session_id = getattr(message, 'session_id', '')
        return session_id or 'unknown'

    async def add(self, message: Any) -> None:
        """收到新訊息，加入緩衝區.

        第一則訊息會立刻觸發 typing indicator。
        """
        key = self._get_chat_key(message)

        # 第一則：觸發 typing + 記錄到達時間
        if key not in self._buffers or not self._buffers[key]:
            self._buffers[key] = []
            self._first_arrival[key] = time.monotonic()
            chat_id = getattr(message, 'metadata', {}).get('chat_id')
            if chat_id:
                try:
                    await self._adapter.start_typing(chat_id)
                except Exception:
                    pass

        self._buffers[key].append(message)

        # 取消舊計時器
        if key in self._timers:
            self._timers[key].cancel()

        # 計算等待時間：取靜默期和最長等待的較小值
        elapsed = time.monotonic() - self._first_arrival.get(key, time.monotonic())
        remaining_max = max(0.5, self._max_wait_seconds - elapsed)
        wait = min(self._quiet_seconds, remaining_max)

        # 啟動新計時器
        self._timers[key] = asyncio.create_task(self._flush_after(key, wait))

    async def _flush_after(self, key: str, wait: float) -> None:
        """等待指定秒數後觸發 flush."""
        try:
            await asyncio.sleep(wait)
            await self._flush(key)
        except asyncio.CancelledError:
            pass

    async def _flush(self, key: str) -> None:
        """合併緩衝區中的訊息並呼叫 handler."""
        messages = self._buffers.pop(key, [])
        self._timers.pop(key, None)
        self._first_arrival.pop(key, None)

        if not messages:
            return

        if len(messages) == 1:
            # 只有一則，直接處理不需合併
            logger.debug(f"[Debounce] {key}: single message, dispatching directly")
            asyncio.create_task(self._handler(self._adapter, messages[0]))
            return

        # 多則訊息 → 合併
        merged = self._merge_messages(messages)
        logger.info(
            f"[Debounce] {key}: merged {len(messages)} messages into one "
            f"({len(merged.content)} chars)"
        )
        asyncio.create_task(self._handler(self._adapter, merged))

    def _merge_messages(self, messages: List[Any]) -> Any:
        """合併多則訊息為一則.

        策略：
        - 文字訊息：用換行合併
        - 保留第一則的 metadata（chat_id, session_id 等）
        - 附件路徑全部保留到 metadata
        """
        base = messages[0]
        texts = []
        image_paths = []
        attachment_ids = []

        for msg in messages:
            content = getattr(msg, 'content', '') or ''
            if content.strip():
                texts.append(content.strip())

            meta = getattr(msg, 'metadata', {}) or {}
            if meta.get('image_path'):
                image_paths.append(meta['image_path'])
            if meta.get('attachment_file_id'):
                attachment_ids.append(meta['attachment_file_id'])

        # 合併文字
        merged_content = '\n'.join(texts) if texts else base.content

        # 使用第一則的基礎屬性，更新內容
        base.content = merged_content

        # 更新 metadata 中的附件
        if not hasattr(base, 'metadata') or base.metadata is None:
            base.metadata = {}
        if image_paths:
            base.metadata['image_paths'] = image_paths
            if not base.metadata.get('image_path'):
                base.metadata['image_path'] = image_paths[0]
        if attachment_ids:
            base.metadata['attachment_file_ids'] = attachment_ids

        # 標記為合併訊息
        base.metadata['debounced'] = True
        base.metadata['debounced_count'] = len(messages)

        return base
