"""EventBus — 全域事件匯流排（發布/訂閱模式）.

依據 THREE_LAYER_PULSE BDD Spec §8 實作。
"""

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Pulse-related event types
# ═══════════════════════════════════════════

PULSE_MICRO_BEAT = "PULSE_MICRO_BEAT"
PULSE_RHYTHM_CHECK = "PULSE_RHYTHM_CHECK"
PULSE_NIGHTLY_DONE = "PULSE_NIGHTLY_DONE"
EVOLUTION_HEARTBEAT = "EVOLUTION_HEARTBEAT"
PROACTIVE_MESSAGE = "PROACTIVE_MESSAGE"
AUTONOMOUS_TASK_DONE = "AUTONOMOUS_TASK_DONE"

# Nightly pipeline events
NIGHTLY_STARTED = "NIGHTLY_STARTED"
NIGHTLY_COMPLETED = "NIGHTLY_COMPLETED"

# WEE / Workflow 自我迭代事件
BRAIN_RESPONSE_COMPLETE = "BRAIN_RESPONSE_COMPLETE"
WEE_RECORDED = "WEE_RECORDED"
WEE_LIFECYCLE_CHANGED = "WEE_LIFECYCLE_CHANGED"
WEE_PLATEAU_DETECTED = "WEE_PLATEAU_DETECTED"

# Self-Diagnosis 自我診斷事件
SELF_DIAGNOSIS_TRIGGERED = "SELF_DIAGNOSIS_TRIGGERED"
SELF_DIAGNOSIS_COMPLETED = "SELF_DIAGNOSIS_COMPLETED"
SELF_REPAIR_EXECUTED = "SELF_REPAIR_EXECUTED"

# Morphenix 演化提案事件
MORPHENIX_L3_PROPOSAL = "MORPHENIX_L3_PROPOSAL"
MORPHENIX_AUTO_APPROVED = "MORPHENIX_AUTO_APPROVED"
MORPHENIX_EXECUTION_COMPLETED = "MORPHENIX_EXECUTION_COMPLETED"

# ═══════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════

_instance: Optional["EventBus"] = None
_lock = threading.Lock()


def get_event_bus() -> "EventBus":
    """全域單例."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = EventBus()
    return _instance


def _reset_event_bus() -> None:
    """重置單例（僅供測試用）."""
    global _instance
    with _lock:
        if _instance is not None:
            _instance.clear()
        _instance = None


# ═══════════════════════════════════════════
# EventBus
# ═══════════════════════════════════════════


class EventBus:
    """全域事件匯流排 — 發布/訂閱模式.

    設計原則：
    - 訂閱者異常不影響其他訂閱者
    - 執行緒安全
    - 同步呼叫（訂閱者應快速完成，重工作請另起執行緒）
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable) -> None:
        """訂閱事件."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        """取消訂閱."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback)
                except ValueError:
                    pass

    def publish(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """發布事件 — 呼叫所有訂閱者."""
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                logger.error(
                    f"EventBus subscriber error on '{event_type}': {e}"
                )

    def subscriber_count(self, event_type: str) -> int:
        """回傳指定事件的訂閱者數量."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))

    def clear(self) -> None:
        """清除所有訂閱."""
        with self._lock:
            self._subscribers.clear()
