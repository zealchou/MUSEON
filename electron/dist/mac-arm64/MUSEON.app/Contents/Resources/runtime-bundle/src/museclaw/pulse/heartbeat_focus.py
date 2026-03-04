"""HeartbeatFocus — 自適應焦點.

依據 THREE_LAYER_PULSE BDD Spec §4 實作。
根據 6 小時內的互動次數動態調整 Rhythm-Pulse 間隔。
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

FOCUS_HIGH_THRESHOLD = 10   # 6hr 內 ≥10 次互動 → high
FOCUS_MEDIUM_THRESHOLD = 3  # 6hr 內 ≥3 次互動 → medium
FOCUS_WINDOW_HOURS = 6      # 觀察窗口（小時）
INTERACTION_EXPIRY_HOURS = 24  # 互動紀錄保留時間

MIN_INTERVAL_HOURS = 1.5
MAX_INTERVAL_HOURS = 6.0


class HeartbeatFocus:
    """自適應焦點 — 根據用戶活躍度調整脈搏頻率.

    高活躍 (≥10 互動/6hr) → 1.5 小時間隔
    中活躍 (3-9 互動/6hr) → 線性插值 6.0→1.5
    低活躍 (<3 互動/6hr)  → 6.0 小時間隔
    """

    def __init__(self, state_path: Optional[str] = None) -> None:
        self._state_path = Path(state_path) if state_path else None
        self._interactions: List[float] = []
        self._beat_count: int = 0
        self._last_beat: Optional[str] = None
        self._focus_level: str = "low"
        self._load_state()

    # ── 自適應間隔 ──

    def compute_adaptive_interval(self) -> float:
        """回傳自適應間隔（小時）."""
        window = time.time() - FOCUS_WINDOW_HOURS * 3600
        recent = [t for t in self._interactions if t > window]
        count = len(recent)

        if count >= FOCUS_HIGH_THRESHOLD:
            return MIN_INTERVAL_HOURS
        elif count >= FOCUS_MEDIUM_THRESHOLD:
            ratio = (count - FOCUS_MEDIUM_THRESHOLD) / (
                FOCUS_HIGH_THRESHOLD - FOCUS_MEDIUM_THRESHOLD
            )
            return MAX_INTERVAL_HOURS - ratio * (
                MAX_INTERVAL_HOURS - MIN_INTERVAL_HOURS
            )
        else:
            return MAX_INTERVAL_HOURS

    # ── 互動記錄 ──

    def record_interaction(self) -> None:
        """記錄一次用戶互動."""
        now = time.time()
        self._interactions.append(now)

        # 清除過期紀錄（>24hr）
        cutoff = now - INTERACTION_EXPIRY_HOURS * 3600
        self._interactions = [t for t in self._interactions if t > cutoff]

        # 重新計算焦點等級
        self._update_focus_level()
        self._save_state()

    def record_beat(self) -> None:
        """記錄一次心跳."""
        self._beat_count += 1
        from datetime import datetime, timezone, timedelta
        tz = timezone(timedelta(hours=8))
        self._last_beat = datetime.now(tz).isoformat()
        self._save_state()

    # ── 焦點等級 ──

    def _update_focus_level(self) -> None:
        """根據互動次數更新焦點等級."""
        window = time.time() - FOCUS_WINDOW_HOURS * 3600
        count = len([t for t in self._interactions if t > window])

        if count >= FOCUS_HIGH_THRESHOLD:
            self._focus_level = "high"
        elif count >= FOCUS_MEDIUM_THRESHOLD:
            self._focus_level = "medium"
        else:
            self._focus_level = "low"

    @property
    def focus_level(self) -> str:
        return self._focus_level

    @property
    def beat_count(self) -> int:
        return self._beat_count

    @property
    def interaction_count(self) -> int:
        window = time.time() - FOCUS_WINDOW_HOURS * 3600
        return len([t for t in self._interactions if t > window])

    # ── 持久化 ──

    def _save_state(self) -> None:
        """儲存狀態到 JSON."""
        if not self._state_path:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "beat_count": self._beat_count,
                "last_beat": self._last_beat,
                "interaction_count": self.interaction_count,
                "focus_level": self._focus_level,
                "interactions": self._interactions,
            }
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.rename(self._state_path)
        except Exception as e:
            logger.error(f"HeartbeatFocus save state failed: {e}")

    def _load_state(self) -> None:
        """從 JSON 載入狀態."""
        if not self._state_path or not self._state_path.exists():
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._beat_count = state.get("beat_count", 0)
            self._last_beat = state.get("last_beat")
            self._interactions = state.get("interactions", [])
            self._focus_level = state.get("focus_level", "low")
        except Exception as e:
            logger.error(f"HeartbeatFocus load state failed: {e}")
