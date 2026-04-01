"""
SignalLite — 輕量信號器（取代 reflex_router 1221 行）.

設計原則：
- 純算術，零語意判斷，零 LLM 呼叫
- < 1ms 執行時間
- 只做兩件事：決定結晶注入量 + 安全偵測
- 人格/風格判斷全部交給 LLM（在 persona_digest.md 中）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from museon.core.message_constants import (
    SIGNAL_LENGTH_SHORT, SIGNAL_LENGTH_LONG,
    LOOP_FAST, LOOP_SLOW, LOOP_EXPLORATION,
)

logger = logging.getLogger(__name__)

# 高風險安全關鍵字（Tier A：能量耗竭、情緒過熱、不可逆決策）
_SAFETY_KEYWORDS = frozenset({
    "自殺", "想死", "不想活", "結束生命", "跳樓", "割腕",
    "崩潰", "撐不住", "活不下去", "沒有意義",
    "離婚", "刪除所有", "放棄一切", "全部賣掉", "all in",
    "恐慌", "panic", "emergency", "緊急",
})

# 主權保護關鍵字（Tier B：決策外包、依賴傾向）
_SOVEREIGNTY_KEYWORDS = frozenset({
    "幫我決定", "替我做主", "你決定就好", "隨便你", "都聽你的",
})


@dataclass
class SignalLite:
    """輕量路由信號 — 取代 reflex_router 的 RoutingSignal."""
    max_crystal_push: int = 10
    safety_triggered: bool = False
    sovereignty_triggered: bool = False
    loop: str = "EXPLORATION_LOOP"

    @property
    def is_safety_triggered(self) -> bool:
        return self.safety_triggered

    @property
    def mode(self) -> str:
        return "CIVIL_MODE"

    @property
    def tier_scores(self) -> dict:
        return {"A": 1.0 if self.safety_triggered else 0.0}

    @property
    def route_time_ms(self) -> float:
        return 0.0

    def to_dict(self) -> dict:
        return {"loop": self.loop, "max_crystal_push": self.max_crystal_push, "safety": self.safety_triggered}


def compute_signal(message: str, is_simple: bool = False) -> SignalLite:
    """純算術信號計算，< 1ms.

    Args:
        message: 使用者訊息
        is_simple: 是否為簡單訊息（由 caller 判定）

    Returns:
        SignalLite 信號
    """
    msg_len = len(message.strip())
    msg_lower = message.lower()

    # 安全偵測
    safety = any(kw in msg_lower for kw in _SAFETY_KEYWORDS)
    sovereignty = any(kw in msg_lower for kw in _SOVEREIGNTY_KEYWORDS)

    # 結晶注入量：純算術
    if is_simple or msg_len <= SIGNAL_LENGTH_SHORT:
        max_push = 5
    elif msg_len <= SIGNAL_LENGTH_LONG:
        max_push = 10
    else:
        max_push = 20

    # 安全觸發時壓低結晶量（加速回覆）
    if safety:
        max_push = min(max_push, 5)

    # loop 判斷
    if is_simple or msg_len <= SIGNAL_LENGTH_SHORT:
        loop = LOOP_FAST
    elif safety:
        loop = LOOP_FAST
    elif msg_len > SIGNAL_LENGTH_LONG:
        loop = LOOP_SLOW
    else:
        loop = LOOP_EXPLORATION

    signal = SignalLite(
        max_crystal_push=max_push,
        safety_triggered=safety,
        sovereignty_triggered=sovereignty,
        loop=loop,
    )

    logger.debug(
        f"[SignalLite] len={msg_len}, push={max_push}, "
        f"safety={safety}, sovereignty={sovereignty}, loop={loop}"
    )

    return signal
