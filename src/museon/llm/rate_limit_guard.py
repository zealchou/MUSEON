"""RateLimitGuard — MAX 訂閱方案的速率限制保護.

5 級降級策略，追蹤 claude -p 呼叫次數，防止超出週 rate limit。
Claude MAX ($200/月 20x) 有滾動式週額度，此模組確保 MUSEON
在額度用盡前智慧降級。
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RateLimitGuard:
    """
    5 級降級策略保護 MAX 訂閱的週 rate limit.

    Levels:
        L0 正常  — 週用量 < 60% → 全速運作
        L1 注意  — 60-75%      → breath_pulse 間隔加倍
        L2 節制  — 75-85%      → 暫停 exploration
        L3 緊縮  — 85-95%      → 暫停 Nightly LLM 步驟
        L4 生存  — > 95%       → 僅回應人類互動

    Priorities (高 → 低):
        human_interaction > nightly > breath_pulse > exploration
    """

    # 週估算上限（呼叫次數）— 保守估計
    # MAX 20x ≈ 140-280 小時 Sonnet/週，但呼叫次數更實用
    DEFAULT_WEEKLY_CALL_LIMIT = 5000

    LEVELS = {
        0: {"name": "normal", "threshold": 0.60, "description": "全速運作"},
        1: {"name": "caution", "threshold": 0.75, "description": "breath_pulse 間隔加倍"},
        2: {"name": "conserve", "threshold": 0.85, "description": "暫停 exploration"},
        3: {"name": "austerity", "threshold": 0.95, "description": "暫停 Nightly LLM 步驟"},
        4: {"name": "survival", "threshold": 1.00, "description": "僅回應人類互動"},
    }

    PRIORITY_RANKS = {
        "human_interaction": 0,  # 最高優先
        "nightly": 1,
        "breath_pulse": 2,
        "exploration": 3,        # 最低優先
    }

    # 每個 level 允許的最低 priority（數字越小 = 優先級越高）
    LEVEL_ALLOWED_PRIORITY = {
        0: 3,  # L0: 所有都允許
        1: 3,  # L1: 所有都允許（但 breath_pulse 間隔加倍由呼叫方處理）
        2: 1,  # L2: 暫停 exploration（priority >= 2 被擋）
        3: 0,  # L3: 僅 human_interaction
        4: 0,  # L4: 僅 human_interaction
    }

    def __init__(
        self,
        data_dir: Optional[str] = None,
        weekly_limit: int = 0,
    ):
        self._data_dir = Path(data_dir) if data_dir else None
        self._weekly_limit = weekly_limit or self.DEFAULT_WEEKLY_CALL_LIMIT

        # 呼叫記錄：每筆 {"ts": epoch, "priority": str, "model": str}
        self._calls = []
        self._load()

    # ── Persistence ──

    def _state_file(self) -> Optional[Path]:
        if not self._data_dir:
            return None
        d = self._data_dir / "_system" / "budget"
        d.mkdir(parents=True, exist_ok=True)
        return d / "rate_limit_guard.json"

    def _load(self) -> None:
        fp = self._state_file()
        if not fp or not fp.exists():
            return
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            self._calls = data.get("calls", [])
            if data.get("weekly_limit"):
                self._weekly_limit = data["weekly_limit"]
        except Exception:
            self._calls = []

    def _save(self) -> None:
        fp = self._state_file()
        if not fp:
            return
        # 只保留最近 7 天的記錄
        cutoff = time.time() - 7 * 86400
        self._calls = [c for c in self._calls if c.get("ts", 0) > cutoff]
        try:
            fp.write_text(
                json.dumps({
                    "calls": self._calls,
                    "weekly_limit": self._weekly_limit,
                    "updated": datetime.now().isoformat(),
                }, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"RateLimitGuard save failed: {e}")

    # ── Core ──

    def record_call(
        self, priority: str = "human_interaction", model: str = "sonnet"
    ) -> None:
        """記錄一次 claude -p 呼叫."""
        self._calls.append({
            "ts": time.time(),
            "priority": priority,
            "model": model,
        })
        self._save()

    def get_weekly_calls(self) -> int:
        """取得最近 7 天的呼叫次數."""
        cutoff = time.time() - 7 * 86400
        return sum(1 for c in self._calls if c.get("ts", 0) > cutoff)

    def get_usage_ratio(self) -> float:
        """取得週用量百分比 (0.0 ~ 1.0+)."""
        if self._weekly_limit <= 0:
            return 0.0
        return self.get_weekly_calls() / self._weekly_limit

    def get_level(self) -> int:
        """取得當前降級等級 (0-4)."""
        ratio = self.get_usage_ratio()
        # 從高到低檢查
        for level in (4, 3, 2, 1):
            if ratio >= self.LEVELS[level]["threshold"]:
                return level
        return 0

    def can_proceed(self, priority: str = "human_interaction") -> bool:
        """檢查指定優先級的呼叫是否被允許.

        Args:
            priority: 呼叫優先級 — human_interaction | nightly | breath_pulse | exploration

        Returns:
            True = 允許呼叫，False = 應暫停
        """
        level = self.get_level()
        priority_rank = self.PRIORITY_RANKS.get(priority, 3)
        max_allowed_rank = self.LEVEL_ALLOWED_PRIORITY.get(level, 0)
        return priority_rank <= max_allowed_rank

    def get_breath_multiplier(self) -> float:
        """取得 breath_pulse 間隔倍率.

        L0: 1.0x（正常）
        L1: 2.0x（加倍）
        L2+: N/A（已暫停）
        """
        level = self.get_level()
        if level >= 1:
            return 2.0
        return 1.0

    def get_status(self) -> Dict:
        """取得完整狀態."""
        level = self.get_level()
        info = self.LEVELS[level]
        weekly_calls = self.get_weekly_calls()

        # 各 priority 的呼叫分布
        cutoff = time.time() - 7 * 86400
        recent = [c for c in self._calls if c.get("ts", 0) > cutoff]
        by_priority = {}
        by_model = {}
        for c in recent:
            p = c.get("priority", "unknown")
            m = c.get("model", "unknown")
            by_priority[p] = by_priority.get(p, 0) + 1
            by_model[m] = by_model.get(m, 0) + 1

        return {
            "level": level,
            "level_name": info["name"],
            "description": info["description"],
            "weekly_calls": weekly_calls,
            "weekly_limit": self._weekly_limit,
            "usage_ratio": round(self.get_usage_ratio(), 4),
            "breath_multiplier": self.get_breath_multiplier(),
            "by_priority": by_priority,
            "by_model": by_model,
        }
