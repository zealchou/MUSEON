"""
待說清單 — Layer 1 與 Layer 2 之間的唯一介面。

Layer 2（背景觀察）寫入洞察 → Layer 1（即時回覆）讀取並融入。
In-memory dict，程序重啟時清空（過期洞察不保留反而是優點）。

設計原則：三個方法，不多不少。
"""

from __future__ import annotations

import time
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 全域單例
_store: dict[str, list[dict]] = {}

# 洞察 TTL（秒）
DEFAULT_TTL = 1800  # 30 分鐘


def add_insight(
    session_id: str,
    content: str,
    priority: str = "medium",
    insight_type: str = "insight",
    ttl: int = DEFAULT_TTL,
) -> str:
    """Layer 2 寫入一條洞察。返回 insight_id。"""
    if session_id not in _store:
        _store[session_id] = []

    insight_id = str(uuid.uuid4())[:8]
    _store[session_id].append({
        "id": insight_id,
        "content": content,
        "priority": priority,
        "type": insight_type,
        "created_at": time.time(),
        "expires_at": time.time() + ttl,
        "used": False,
    })
    logger.info(f"[PendingSayings] added: {insight_id} ({insight_type}) for {session_id}")
    return insight_id


def get_pending(session_id: str, max_items: int = 3) -> list[dict]:
    """Layer 1 讀取未使用且未過期的洞察（最多 max_items 條）。

    讀取後自動標記 used=True。
    """
    items = _store.get(session_id, [])
    now = time.time()

    # 過濾：未使用 + 未過期
    pending = [
        item for item in items
        if not item["used"] and item["expires_at"] > now
    ]

    # 按 priority 排序（high > medium > low）
    priority_order = {"high": 0, "medium": 1, "low": 2}
    pending.sort(key=lambda x: priority_order.get(x["priority"], 1))

    # 取前 max_items
    result = pending[:max_items]

    # 標記 used
    for item in result:
        item["used"] = True

    # 順便清理過期的
    _store[session_id] = [
        item for item in items
        if item["expires_at"] > now
    ]

    return result


def clear(session_id: str) -> None:
    """清空指定 session 的所有洞察。"""
    _store.pop(session_id, None)
