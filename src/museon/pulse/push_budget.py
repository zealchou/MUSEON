"""PushBudget — 全局推送預算管理器.

所有推送通道（PulseEngine、ProactiveBridge）共用此限額和去重邏輯。
解決「三條管線各自計數、互不知道對方」的結構性問題。

設計原則：
- Single Source of Truth：所有推送都經過此管理器
- 持久化：透過 PulseDB push_log 表，跨 session 不歸零
- 語意去重：詞級 Jaccard（bigram + 空格分詞），取代字元級 80 字精確比對
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

GLOBAL_DAILY_LIMIT = 5   # 一天最多 5 條推送（含晨暮）
DEDUP_HOURS = 24          # 去重窗口 24 小時
DEDUP_JACCARD_THRESHOLD = 0.5  # 詞級 Jaccard > 0.5 視為重複

# 中文停用詞（去重時過濾）
_STOP_WORDS = frozenset({
    "的", "了", "在", "是", "我", "你", "他", "她", "它", "們",
    "這", "那", "有", "和", "與", "也", "都", "就", "但", "而",
    "不", "很", "會", "要", "把", "被", "讓", "給", "從", "到",
    "上", "下", "中", "大", "小", "多", "少", "個", "一", "兩",
    "又", "還", "已", "嗎", "呢", "吧", "啊", "哦", "喔", "耶",
    "可以", "可能", "應該", "需要", "因為", "所以", "如果", "雖然",
})


class PushBudget:
    """全局推送預算管理器 — 所有推送通道共用此限額."""

    def __init__(self, pulse_db: Any = None) -> None:
        self._db = pulse_db
        self._today: Optional[str] = None
        self._today_count: int = 0
        self._restore_from_db()

    # ── 限額管理 ──

    def can_push(self, source: str) -> bool:
        """判斷是否可以推送。

        Args:
            source: 推送來源（morning/evening/soul/proactive/idle/alert）

        Returns:
            True = 可推送
        """
        if source == "alert":
            return True  # 警報永遠放行
        self._maybe_reset()
        return self._today_count < GLOBAL_DAILY_LIMIT

    def record_push(self, source: str, message: str) -> None:
        """記錄一次推送（遞增計數 + 持久化）."""
        self._maybe_reset()
        self._today_count += 1
        preview = message.strip()[:200] if message else ""
        # 持久化到 PulseDB
        if self._db:
            try:
                self._db.log_push(source, preview)
            except Exception as e:
                logger.debug(f"PushBudget: log_push failed: {e}")

    def is_duplicate(self, message: str) -> bool:
        """語意去重：與最近 24 小時內所有推送比對。

        使用詞級 Jaccard（bigram + 空格分詞 + 停用詞過濾）。
        """
        recent = self._get_recent_pushes(hours=DEDUP_HOURS)
        if not recent:
            return False
        candidate_tokens = self._tokenize(message)
        if not candidate_tokens:
            return False
        for prev in recent:
            prev_tokens = self._tokenize(prev)
            if not prev_tokens:
                continue
            jaccard = self._jaccard(candidate_tokens, prev_tokens)
            if jaccard > DEDUP_JACCARD_THRESHOLD:
                logger.debug(
                    f"PushBudget dedup: Jaccard={jaccard:.2f} > {DEDUP_JACCARD_THRESHOLD}"
                )
                return True
        return False

    @property
    def remaining(self) -> int:
        """今日剩餘推送配額."""
        self._maybe_reset()
        return max(0, GLOBAL_DAILY_LIMIT - self._today_count)

    @property
    def today_count(self) -> int:
        """今日已推送次數."""
        self._maybe_reset()
        return self._today_count

    def get_recent_summaries(self, limit: int = 3) -> List[str]:
        """取得最近推送的摘要（供 LLM context 注入）."""
        if not self._db:
            return []
        try:
            rows = self._db.get_recent_pushes(hours=24)
            return [r[:150] for r in rows[:limit]]
        except Exception:
            return []

    # ── 語意去重工具 ──

    @staticmethod
    def _tokenize(text: str) -> set:
        """中文分詞：bigram + 空格分詞 混合，過濾停用詞."""
        if not text:
            return set()
        tokens = set()
        # 空格分詞（英文 + 被空格分隔的中文詞）
        for word in text.split():
            if len(word) >= 2 and word not in _STOP_WORDS:
                tokens.add(word.lower())
        # 中文 bigram
        clean = text.replace(" ", "").replace("\n", "")
        for i in range(len(clean) - 1):
            bg = clean[i:i+2]
            if bg not in _STOP_WORDS:
                tokens.add(bg)
        return tokens

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        """Jaccard 相似度."""
        if not a or not b:
            return 0.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    # ── 內部工具 ──

    def _maybe_reset(self) -> None:
        """跨日重置計數器."""
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        if self._today != today:
            self._today = today
            self._today_count = self._count_from_db(today)

    def _restore_from_db(self) -> None:
        """從 PulseDB 還原今日計數（跨 session 持久化）."""
        if not self._db:
            return
        try:
            self._today = datetime.now(TZ8).strftime("%Y-%m-%d")
            self._today_count = self._count_from_db(self._today)
        except Exception as e:
            logger.debug(f"PushBudget: restore failed: {e}")

    def _count_from_db(self, date_str: str) -> int:
        """從 PulseDB 查詢指定日期的推送次數."""
        if not self._db:
            return 0
        try:
            return self._db.get_push_count_for_date(date_str)
        except Exception:
            return 0

    def _get_recent_pushes(self, hours: int = 24) -> List[str]:
        """從 PulseDB 取得最近 N 小時的推送文字."""
        if not self._db:
            return []
        try:
            return self._db.get_recent_pushes(hours=hours)
        except Exception:
            return []
