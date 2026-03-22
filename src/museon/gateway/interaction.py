"""InteractionQueue — 跨通道互動佇列.

v10.0: 基於 ApprovalQueue (authorization.py) 的 asyncio.Event 模式，
提供通用的「問使用者選擇 → 等待回應」非阻塞機制。

Architecture:
    1. Brain/Skill 產出 InteractionRequest
    2. Message pump 呼叫 adapter.present_choices() 呈現 UI
    3. submit(request) → 建立 pending + asyncio.Event
    4. 使用者在平台上點選 → adapter callback 呼叫 resolve()
    5. resolve() → event.set() 喚醒 wait_for_response()
    6. 回傳 InteractionResponse 給 message pump

Thread safety:
    所有方法都在同一個 asyncio event loop 中執行，
    不需要 threading.Lock（與 ApprovalQueue 一致）。
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from museon.gateway.message import InteractionRequest, InteractionResponse

logger = logging.getLogger(__name__)


class InteractionQueue:
    """通用互動佇列：asyncio.Event 非阻塞等待使用者選擇.

    模式與 authorization.py 的 ApprovalQueue 一致：
    - submit() → 建立 pending + event
    - resolve() → event.set() 喚醒等待者
    - wait_for_response() → 回傳 InteractionResponse

    Usage:
        queue = InteractionQueue()

        # Brain side
        queue.submit(interaction_request)
        response = await queue.wait_for_response(request.question_id)

        # Adapter side (in callback handler)
        queue.resolve(question_id, interaction_response)
    """

    DEFAULT_TIMEOUT = 120  # seconds

    def __init__(self, default_timeout: int = None):
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._responses: Dict[str, InteractionResponse] = {}
        self._default_timeout = default_timeout or self.DEFAULT_TIMEOUT

    def submit(self, request: InteractionRequest) -> str:
        """提交互動請求，建立等待機制.

        Args:
            request: InteractionRequest 物件

        Returns:
            question_id（用於後續 resolve / wait_for_response）
        """
        qid = request.question_id
        self._pending[qid] = {
            "request": request,
            "created_at": datetime.now(),
            "resolved": False,
        }
        self._events[qid] = asyncio.Event()
        logger.debug(
            f"InteractionQueue: submitted {qid} "
            f"({len(request.options)} options, "
            f"timeout={request.timeout_seconds}s, "
            f"context={request.context})"
        )
        return qid

    def resolve(self, question_id: str, response: InteractionResponse) -> bool:
        """解決互動請求（由 adapter callback 觸發）.

        Args:
            question_id: 對應的 InteractionRequest.question_id
            response: 使用者的回應

        Returns:
            True if successfully resolved, False if question_id not found
        """
        if question_id not in self._pending:
            logger.warning(
                f"InteractionQueue: resolve called for unknown qid={question_id}"
            )
            return False

        entry = self._pending[question_id]
        if entry["resolved"]:
            logger.warning(
                f"InteractionQueue: qid={question_id} already resolved"
            )
            return False

        entry["resolved"] = True
        self._responses[question_id] = response

        # 觸發 asyncio.Event → 喚醒 wait_for_response()
        event = self._events.get(question_id)
        if event:
            event.set()

        logger.debug(
            f"InteractionQueue: resolved {question_id} → "
            f"selected={response.selected}, "
            f"free_text={response.free_text!r}"
        )
        return True

    async def wait_for_response(
        self, question_id: str, timeout: int = None
    ) -> InteractionResponse:
        """非阻塞等待使用者回應.

        Args:
            question_id: 等待的 InteractionRequest.question_id
            timeout: 超時秒數（預設使用 request.timeout_seconds）

        Returns:
            InteractionResponse（超時時 timed_out=True）
        """
        entry = self._pending.get(question_id)
        if not entry:
            return InteractionResponse(
                question_id=question_id,
                timed_out=True,
            )

        # 決定 timeout：優先用參數，其次用 request 的設定
        if timeout is None:
            request = entry.get("request")
            if request:
                timeout = request.timeout_seconds
            else:
                timeout = self._default_timeout

        event = self._events.get(question_id)
        if not event:
            return InteractionResponse(
                question_id=question_id,
                timed_out=True,
            )

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            response = self._responses.get(question_id)
            if response:
                return response
            return InteractionResponse(
                question_id=question_id,
                timed_out=True,
            )
        except asyncio.TimeoutError:
            logger.info(
                f"InteractionQueue: timeout for qid={question_id} "
                f"after {timeout}s"
            )
            # 標記為已解決（超時）
            if question_id in self._pending:
                self._pending[question_id]["resolved"] = True
            return InteractionResponse(
                question_id=question_id,
                timed_out=True,
            )

    def is_pending(self, question_id: str) -> bool:
        """檢查互動是否仍在等待中."""
        entry = self._pending.get(question_id)
        if not entry:
            return False
        return not entry["resolved"]

    def get_request(self, question_id: str) -> Optional[InteractionRequest]:
        """取得原始 InteractionRequest."""
        entry = self._pending.get(question_id)
        if entry:
            return entry.get("request")
        return None

    def cleanup_expired(self, max_age_hours: int = 2) -> int:
        """清理超時的 pending 項目.

        Returns:
            清理的項目數量
        """
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        to_delete = [
            qid
            for qid, entry in self._pending.items()
            if entry["created_at"] < cutoff
        ]
        for qid in to_delete:
            del self._pending[qid]
            self._events.pop(qid, None)
            self._responses.pop(qid, None)
        if to_delete:
            logger.debug(
                f"InteractionQueue: cleaned up {len(to_delete)} expired entries"
            )
        return len(to_delete)

    @property
    def pending_count(self) -> int:
        """目前等待中的互動數量."""
        return sum(
            1 for entry in self._pending.values() if not entry["resolved"]
        )

    def stats(self) -> Dict[str, int]:
        """取得佇列統計."""
        total = len(self._pending)
        pending = self.pending_count
        resolved = total - pending
        return {
            "total": total,
            "pending": pending,
            "resolved": resolved,
        }


# ── Singleton ──

_interaction_queue: Optional[InteractionQueue] = None


def get_interaction_queue() -> InteractionQueue:
    """取得全域 InteractionQueue 單例."""
    global _interaction_queue
    if _interaction_queue is None:
        _interaction_queue = InteractionQueue()
    return _interaction_queue
