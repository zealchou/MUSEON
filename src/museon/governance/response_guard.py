"""ResponseGuard — 發送前二次驗證閘門.

防止跨群組訊息洩漏的最後一道防線。
任何回覆在發送到 Telegram 之前，都必須通過此閘門的 chat_id 一致性驗證。

原則：接收時記錄 origin_chat_id，發送時驗證 target_chat_id 一致。
不一致 → CRITICAL log + 阻擋發送。

2026-03-24: 因跨群組訊息洩漏事件建立（DSE 根因分析後的架構級修復）。
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ResponseGuard:
    """發送前二次驗證閘門 — 防止跨群組訊息洩漏.

    使用方式：
        guard = ResponseGuard(origin_chat_id=incoming_msg.metadata["chat_id"])
        if guard.allow_send(target_chat_id=response_msg.metadata["chat_id"]):
            await adapter.send(response_msg)
        else:
            # 已被阻擋，不發送

    或使用靜態方法：
        if ResponseGuard.validate(origin_cid, target_cid, context="..."):
            ...
    """

    def __init__(self, origin_chat_id: Any, origin_session_id: str = ""):
        """初始化守衛，綁定本次訊息的 origin chat_id.

        Args:
            origin_chat_id: 接收訊息時的 chat_id（Telegram chat ID）
            origin_session_id: 用於日誌的 session_id
        """
        self._origin_chat_id = str(origin_chat_id) if origin_chat_id else ""
        self._origin_session_id = origin_session_id

    def allow_send(self, target_chat_id: Any, context: str = "") -> bool:
        """驗證發送目標 chat_id 與接收 origin 一致.

        Args:
            target_chat_id: 即將發送的 chat_id
            context: 額外的上下文描述（用於日誌）

        Returns:
            True = 一致，允許發送
            False = 不一致，阻擋發送
        """
        target = str(target_chat_id) if target_chat_id else ""

        if not self._origin_chat_id:
            logger.warning(
                f"[ResponseGuard] origin_chat_id is empty — "
                f"target={target} ctx={context} session={self._origin_session_id}"
            )
            # origin 為空時不阻擋（可能是系統推送等非回覆場景）
            return True

        if not target:
            logger.critical(
                f"[ResponseGuard] BLOCKED: target_chat_id is empty! "
                f"origin={self._origin_chat_id} ctx={context} session={self._origin_session_id}"
            )
            return False

        if self._origin_chat_id != target:
            logger.critical(
                f"[ResponseGuard] ⛔ BLOCKED cross-chat leak! "
                f"origin={self._origin_chat_id} target={target} "
                f"ctx={context} session={self._origin_session_id}"
            )
            return False

        return True

    @staticmethod
    def validate(
        origin_chat_id: Any,
        target_chat_id: Any,
        context: str = "",
    ) -> bool:
        """靜態驗證方法 — 不需要實例化.

        Args:
            origin_chat_id: 接收訊息時的 chat_id
            target_chat_id: 即將發送的 chat_id
            context: 額外上下文

        Returns:
            True = 允許, False = 阻擋
        """
        origin = str(origin_chat_id) if origin_chat_id else ""
        target = str(target_chat_id) if target_chat_id else ""

        if not origin:
            return True  # 系統推送等場景，不阻擋

        if not target:
            logger.critical(
                f"[ResponseGuard] BLOCKED: target_chat_id is empty! "
                f"origin={origin} ctx={context}"
            )
            return False

        if origin != target:
            logger.critical(
                f"[ResponseGuard] ⛔ BLOCKED cross-chat leak! "
                f"origin={origin} target={target} ctx={context}"
            )
            return False

        return True

    @staticmethod
    def validate_escalation(
        escalation_id: str,
        expected_group_id: Any,
        actual_group_id: Any,
        context: str = "",
    ) -> bool:
        """Escalation 專用驗證 — 確認 escalation entry 的 group_id 一致.

        Args:
            escalation_id: escalation 的唯一 ID
            expected_group_id: 從 escalation queue 取出的 group_id
            actual_group_id: 即將發送的 group_id

        Returns:
            True = 一致, False = 阻擋
        """
        expected = str(expected_group_id) if expected_group_id else ""
        actual = str(actual_group_id) if actual_group_id else ""

        if expected != actual:
            logger.critical(
                f"[ResponseGuard] ⛔ BLOCKED escalation cross-group! "
                f"eid={escalation_id} expected_gid={expected} actual_gid={actual} "
                f"ctx={context}"
            )
            return False

        return True
