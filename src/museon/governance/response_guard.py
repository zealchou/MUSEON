"""ResponseGuard — 發送前二次驗證閘門.

防止跨群組訊息洩漏的最後一道防線。
任何回覆在發送到 Telegram 之前，都必須通過此閘門的 chat_id 一致性驗證。

原則：接收時記錄 origin_chat_id，發送時驗證 target_chat_id 一致。
不一致 → CRITICAL log + 阻擋發送。

2026-03-24: 因跨群組訊息洩漏事件建立（DSE 根因分析後的架構級修復）。
"""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 群組回覆中需要清除的內部術語模式
_INTERNAL_PATTERNS = [
    # chat_id / session_id 數字
    re.compile(r"(?:chat_id|session_id|group_id)[=:\s]*-?\d{5,}", re.IGNORECASE),
    # telegram_group_NNNN / telegram_dm_NNNN session 格式
    re.compile(r"telegram_(?:group|dm)_-?\d{5,}"),
    # 系統狀態訊息
    re.compile(r"(?:Gateway|PulseEngine|Nightly|ServiceHealth)\s*(?:啟動|停止|重啟|失敗|異常|crash|error)", re.IGNORECASE),
    # PID / lock 檔案路徑
    re.compile(r"(?:pid|lock)\s*[=:]\s*\d+", re.IGNORECASE),
    re.compile(r"/Users/\S+/\.museon/\S+"),
    # 內部模組路徑
    re.compile(r"museon\.(?:agent|gateway|pulse|governance|llm)\.\w+"),
    # L1/L2/L3 調度架構術語
    re.compile(r"L[123]\s*(?:調度員?|思考者|工人|dispatcher|subagent|spawn|prompt\s*範本)", re.IGNORECASE),
    re.compile(r"(?:三層架構|調度員模式|L1/L2|L2\s*回報|L2\s*思考)", re.IGNORECASE),
    # MCP 插件 / 工具內部名稱
    re.compile(r"(?:MCP\s*(?:插件|plugin|server|tool)|mcp__\w+)", re.IGNORECASE),
    # debug / 內部開發術語
    re.compile(r"(?:debug|traceback|stacktrace|exception|內部錯誤|內部架構)", re.IGNORECASE),
    # system prompt / prompt 工程術語
    re.compile(r"(?:system\s*prompt|prompt\s*(?:工程|injection|注入))", re.IGNORECASE),
    # Brain / ResponseGuard / 內部元件名
    re.compile(r"(?:ResponseGuard|EventBus|BrainModule|MemoryStore|sanitize_for_group)", re.IGNORECASE),
    # 內部檔案路徑 (通用)
    re.compile(r"(?:~/MUSEON/|/Users/\S+/MUSEON/)\S+"),
    # AI 內部思考標記（僅匹配特定 AI 術語，不誤殺一般中文【】用法）
    re.compile(r"【(?:思考路徑|順便一提|分析|備註|內部|系統|提示|思考|觀察|規劃|反思|總結)】"),
    # 「已成功發送/回覆...群組/訊息」等操作確認語句
    re.compile(r"已成功(?:發送|回覆|傳送).{0,30}(?:群組|訊息|頻道)"),
    # AI 後設描述（僅內部架構術語，保留教練模式合法詞彙如「深度思考」「思維轉化」）
    re.compile(r"(?:多維度審查|一階原則|後設認知|認知迴圈)"),
    # Skill 路由鏈洩漏（如「🎭 strategy → dharma → philo」）
    re.compile(r"[🎭🧠🔍💭⚡🎯🛡️📊]\s*\w[\w-]*\s*→\s*\w[\w-]*(?:\s*→\s*\w[\w-]*)*"),
    # 孤立的 [empty] 佔位符
    re.compile(r"^\[empty\]$", re.MULTILINE),
]


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
        self._origin_chat_id = origin_chat_id
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
        origin = self._normalize_id(self._origin_chat_id)
        target = self._normalize_id(target_chat_id)

        if not origin:
            logger.warning(
                f"[ResponseGuard] origin_chat_id is empty — "
                f"target={target} ctx={context} session={self._origin_session_id}"
            )
            return True

        if not target:
            logger.critical(
                f"[ResponseGuard] BLOCKED: target_chat_id is empty! "
                f"origin={origin} ctx={context} session={self._origin_session_id}"
            )
            return False

        if origin != target:
            logger.critical(
                f"[ResponseGuard] ⛔ BLOCKED cross-chat leak! "
                f"origin={origin} target={target} "
                f"ctx={context} session={self._origin_session_id}"
            )
            return False

        return True

    @staticmethod
    def _normalize_id(raw: Any) -> str:
        """正規化 chat_id / group_id — abs() 去負號，統一比對."""
        if not raw:
            return ""
        try:
            return str(abs(int(raw)))
        except (ValueError, TypeError):
            return str(raw).lstrip("-")

    @staticmethod
    def validate(
        origin_chat_id: Any,
        target_chat_id: Any,
        context: str = "",
    ) -> bool:
        """靜態驗證方法 — 不需要實例化.

        兩邊都做 abs() 正規化，避免 Telegram 群組 ID 的負號差異導致誤判。

        Args:
            origin_chat_id: 接收訊息時的 chat_id（或 session 提取的 group_id）
            target_chat_id: 即將發送的 chat_id（或 metadata 中的 chat_id）
            context: 額外上下文

        Returns:
            True = 允許, False = 阻擋
        """
        origin = ResponseGuard._normalize_id(origin_chat_id)
        target = ResponseGuard._normalize_id(target_chat_id)

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
    def strip_markdown(text: str) -> str:
        """將 Markdown 格式轉為 Telegram 友善的純文字.

        LLM 會自然產出 markdown，但 Telegram 純文字模式不渲染。
        在 _safe_send() 出口統一轉換，比在 prompt 裡叫 LLM 不用 markdown 更可靠。
        """
        if not text:
            return text

        # 1. 移除 markdown 標題 (##, ###, ####)，保留標題文字
        #    "## 七個問題重新整理" → "七個問題重新整理"
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

        # 2. 轉換 markdown 表格為簡單列表
        #    "| 問題 | 核心關注 |" → "問題 / 核心關注"
        #    先移除分隔線 "|---|---|"
        text = re.sub(r'^\|[\s\-:]+\|[\s\-:|]*$', '', text, flags=re.MULTILINE)
        #    再轉換資料行
        def _table_row_to_text(m):
            cells = [c.strip() for c in m.group(0).split('|') if c.strip()]
            return ' / '.join(cells) if cells else ''
        text = re.sub(r'^\|.+\|$', _table_row_to_text, text, flags=re.MULTILINE)

        # 3. 移除粗體/斜體標記，保留文字
        #    "**重要**" → "重要"，"*斜體*" → "斜體"
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)

        # 4. 移除行內代碼標記
        #    "`code`" → "code"
        text = re.sub(r'`([^`]+)`', r'\1', text)

        # 5. 移除代碼塊標記（保留內容）
        #    "```python\ncode\n```" → "code"
        text = re.sub(r'```\w*\n?', '', text)

        # 6. 轉換 markdown 連結
        #    "[text](url)" → "text"
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # 7. 移除水平線
        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\*\*\*+$', '', text, flags=re.MULTILINE)

        # 8. 清理多餘空行（連續 3+ 個空行 → 2 個）
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    @staticmethod
    def sanitize_for_group(response_text: str, is_group: bool = False) -> str:
        """回覆內容清理 — 移除內部術語和敏感資訊，並轉換 Markdown 為純文字.

        所有通道（群組 + 私訊）統一掃描並移除：
        - chat_id / session_id 等內部識別碼
        - 系統狀態訊息（Gateway/Pulse 等）
        - 內部檔案路徑和模組名稱
        - L1/L2/L3 架構術語、MCP 插件名、AI 思考標記
        - Markdown 格式（標題/表格/粗體等）→ 純文字

        Args:
            response_text: 原始回覆文本
            is_group: 是否為群組訊息（保留參數相容性，不再影響過濾行為）

        Returns:
            清理後的回覆文本
        """
        if not response_text:
            return response_text

        sanitized = response_text

        # 所有通道統一過濾全部 _INTERNAL_PATTERNS
        for pattern in _INTERNAL_PATTERNS:
            sanitized = pattern.sub("", sanitized)

        # 清理替換後殘留的連續空行
        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()

        # Markdown → 純文字轉換（LLM 自然產出 markdown，Telegram 不渲染）
        result = ResponseGuard.strip_markdown(sanitized)

        if result != response_text:
            logger.info(
                f"[ResponseGuard] sanitize_for_group: 已清理回覆中的內部資訊"
            )

        return result

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
        expected = ResponseGuard._normalize_id(expected_group_id)
        actual = ResponseGuard._normalize_id(actual_group_id)

        if not expected or not actual:
            return True  # 空值不阻擋

        if expected != actual:
            logger.critical(
                f"[ResponseGuard] ⛔ BLOCKED escalation cross-group! "
                f"eid={escalation_id} expected_gid={expected} actual_gid={actual} "
                f"ctx={context}"
            )
            return False

        return True
