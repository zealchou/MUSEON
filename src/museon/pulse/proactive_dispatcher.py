"""ProactiveDispatcher — 推播大總管（Phase 1）.

統一管理所有主動推播（晨感、暮感、自主探索、ProactiveBridge、Idle 關心、系統通知），
解決推播來源互不知道彼此說了什麼的結構性問題。

職責：
- 維護 24hr 滾動推播日誌（JSON 持久化）
- Haiku 語意去重（取代 Jaccard 的粗粒度比對）
- 內容完整性檢查（截斷偵測、嵌套語法崩壞）
- 推播分級標記（info / action / urgent）
- 群組對話原文過濾
"""

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 推播分級關鍵詞
_ACTION_KEYWORDS = frozenset({
    "承諾到期", "提案待審", "客戶",
})

# 完整性檢查
_NESTED_QUOTE_OPEN = set("「『")
_NESTED_QUOTE_CLOSE = set("」』")
_GROUP_LEAK_MARKER = "[群組近期對話紀錄]"

# 日誌檔案路徑
_JOURNAL_FILENAME = "push_journal_24h.json"


class ProactiveDispatcher:
    """推播大總管 — 所有推播通道的統一品質閘門."""

    def __init__(self, data_dir: str, llm_adapter=None):
        """初始化 ProactiveDispatcher.

        Args:
            data_dir: MUSEON data 根目錄（如 ~/MUSEON/data）
            llm_adapter: LLM 呼叫介面（需有 async complete(prompt) -> str 方法），
                         None 時語意去重降級為跳過
        """
        self._data_dir = Path(data_dir)
        self._llm_adapter = llm_adapter
        self._journal_path = self._data_dir / "_system" / "pulse" / _JOURNAL_FILENAME

        # 確保目錄存在
        self._journal_path.parent.mkdir(parents=True, exist_ok=True)

        # 載入日誌到記憶體
        self._entries: List[dict] = []
        self._load_journal()

    # ═══════════════════════════════════════════
    # 核心 API
    # ═══════════════════════════════════════════

    async def should_allow(
        self, message: str, source: str
    ) -> Tuple[bool, str]:
        """判斷是否放行推播。

        檢查順序：
        1. alert 類型永遠放行
        2. 群組對話原文偵測（含「[群組近期對話紀錄]」→ 攔截）
        3. 內容完整性（截斷、嵌套崩壞 → 攔截）
        4. Haiku 語意去重（跟 24hr 內說過的比 → 重複則攔截）
        5. 放行

        Returns:
            (allowed, reason) — allowed=True 時 reason 為空字串
        """
        if not message or not message.strip():
            return False, "empty_message"

        # 1. alert 永遠放行
        if source == "alert":
            return True, ""

        # 2. 群組對話原文洩漏偵測
        if _GROUP_LEAK_MARKER in message:
            return False, "group_conversation_leak"

        # 3. 內容完整性
        truncated, reason = self._check_integrity(message)
        if truncated:
            return False, reason

        # 4. Haiku 語意去重
        try:
            is_dup = await self._semantic_dedup(message)
            if is_dup:
                return False, "semantic_duplicate"
        except Exception as e:
            # 去重失敗 → 靜默放行（不能因為去重失敗就擋住推播）
            logger.debug(f"[Dispatcher] semantic dedup error, pass-through: {e}")

        # 5. 放行
        return True, ""

    def record_push(self, message: str, source: str) -> None:
        """記錄已發送的推播到 24hr 日誌."""
        now = datetime.now(TZ8)
        entry = {
            "ts": now.isoformat(),
            "source": source,
            "summary": message.strip()[:100],
            "full_text_hash": hashlib.sha256(
                message.encode("utf-8")
            ).hexdigest()[:16],
            "topics": [],  # Phase 2 可擴充用 Haiku 抽取標籤
            "grade": self.get_push_grade(message, source),
            "blocked": False,
            "block_reason": "",
        }
        self._entries.append(entry)
        self._prune_old_entries()
        self._save_journal()

    def get_push_grade(self, message: str, source: str) -> str:
        """判斷推播級別：info / action / urgent."""
        if source == "alert":
            return "urgent"
        for kw in _ACTION_KEYWORDS:
            if kw in message:
                return "action"
        return "info"

    def get_journal_summaries(self, hours: int = 24) -> List[str]:
        """取得最近 N 小時的推播摘要列表."""
        cutoff = time.time() - hours * 3600
        summaries = []
        for entry in self._entries:
            try:
                ts = datetime.fromisoformat(entry["ts"]).timestamp()
                if ts >= cutoff and not entry.get("blocked", False):
                    summaries.append(entry.get("summary", ""))
            except (ValueError, KeyError):
                continue
        return summaries

    # ═══════════════════════════════════════════
    # 內容完整性檢查
    # ═══════════════════════════════════════════

    @staticmethod
    def _check_integrity(message: str) -> Tuple[bool, str]:
        """檢查訊息完整性。

        Returns:
            (has_problem, reason)
        """
        text = message.strip()
        if not text:
            return True, "empty_after_strip"

        # 截斷偵測：最後一個字元不是標點或換行
        # 中英文句末標點
        end_puncts = set("。！？…」』）】!?.)\n\r")
        if len(text) > 50 and text[-1] not in end_puncts:
            # 額外確認：如果最後是英文字母或中文字，且不是短訊息，判定為截斷
            last_char = text[-1]
            if last_char.isalpha() or "\u4e00" <= last_char <= "\u9fff":
                return True, "truncated_message"

        # 嵌套引號崩壞：計算巢狀深度，>= 3 層視為崩壞
        depth = 0
        max_depth = 0
        for ch in text:
            if ch in _NESTED_QUOTE_OPEN:
                depth += 1
                max_depth = max(max_depth, depth)
            elif ch in _NESTED_QUOTE_CLOSE:
                depth = max(0, depth - 1)
        if max_depth >= 3:
            return True, "nested_quote_corruption"

        return False, ""

    # ═══════════════════════════════════════════
    # Haiku 語意去重
    # ═══════════════════════════════════════════

    async def _semantic_dedup(self, message: str) -> bool:
        """用 Haiku 判斷新訊息是否與最近 24hr 推播語意重複。

        Returns:
            True = 重複，應攔截
        """
        if not self._llm_adapter:
            return False  # 無 LLM → 跳過語意去重

        summaries = self.get_journal_summaries(hours=24)
        if not summaries:
            return False  # 沒有歷史 → 不可能重複

        summaries_text = "\n".join(f"- {s}" for s in summaries[-10:])  # 最多取最近 10 條
        prompt = (
            f"以下是過去 24 小時已發送給使用者的訊息摘要：\n"
            f"{summaries_text}\n\n"
            f"新訊息：\n"
            f"{message[:500]}\n\n"
            f"這條新訊息是否在談論跟已發送訊息相同或高度相似的話題？\n"
            f"只回答一個詞：DUPLICATE 或 PASS"
        )

        try:
            response = await self._llm_adapter.complete(prompt)
            result = response.strip().upper()
            if "DUPLICATE" in result:
                logger.info(
                    f"[Dispatcher] Haiku semantic dedup: DUPLICATE detected"
                )
                return True
            return False
        except Exception as e:
            logger.debug(f"[Dispatcher] Haiku call failed, pass-through: {e}")
            return False  # LLM 失敗 → 不阻擋

    # ═══════════════════════════════════════════
    # 日誌持久化（原子寫入）
    # ═══════════════════════════════════════════

    def _load_journal(self) -> None:
        """從磁碟載入 24hr 日誌."""
        if not self._journal_path.exists():
            self._entries = []
            return
        try:
            with open(self._journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._entries = data.get("entries", [])
            self._prune_old_entries()
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[Dispatcher] journal load failed, starting fresh: {e}")
            self._entries = []

    def _save_journal(self) -> None:
        """原子寫入日誌到磁碟（tmp → rename）."""
        data = {"entries": self._entries}
        try:
            # 寫到 tmp 檔
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._journal_path.parent),
                prefix=".push_journal_",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                # 原子 rename
                os.replace(tmp_path, str(self._journal_path))
            except Exception:
                # 清理 tmp 檔
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.warning(f"[Dispatcher] journal save failed: {e}")

    def _prune_old_entries(self) -> None:
        """清除超過 24 小時的舊條目."""
        cutoff = time.time() - 24 * 3600
        pruned = []
        for entry in self._entries:
            try:
                ts = datetime.fromisoformat(entry["ts"]).timestamp()
                if ts >= cutoff:
                    pruned.append(entry)
            except (ValueError, KeyError):
                continue
        self._entries = pruned
