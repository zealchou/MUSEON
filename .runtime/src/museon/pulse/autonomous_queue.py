"""AutonomousQueue — 自主任務佇列 + 授權策略引擎.

讓 MUSEON 能自主觸發任務執行，不需使用者即時輸入。
配合 AuthPolicy 控制操作授權等級。

BDD Scenarios:
  §1 授權等級（AuthLevel）
    - AUTO: 直接執行
    - CONFIRM: 需使用者確認
    - DENY: 拒絕執行
  §2 預設策略（Default Policies）
    - notification → AUTO
    - skill_invoke → AUTO
    - data_modify → CONFIRM
    - delete → DENY
  §3 任務佇列（Queue）
    - enqueue() 加入任務
    - process_next() 處理下一個可執行任務
    - 佇列滿 → 拒絕新任務
  §4 緊急停止（Emergency Stop）
    - emergency_stop() 立即停止所有任務
    - 停止後 enqueue 被拒絕
    - resume() 恢復
  §5 預算控制（Budget Control）
    - 有 budget_monitor → 超限時拒絕
    - 無 budget_monitor → 不檢查
  §6 自訂授權（Custom Auth）
    - grant() 覆寫預設策略
    - revoke() 回復預設
  §7 歷史記錄（History）
    - 完成/失敗/拒絕 都記錄
    - get_history() 回傳最近 N 筆
  §8 持久化（Persistence）
    - 佇列狀態可存檔/恢復
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

MAX_QUEUE_SIZE = 50
MAX_HISTORY_SIZE = 100
TASK_TIMEOUT_SECONDS = 300  # 5 分鐘


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class AuthLevel(str, Enum):
    """授權等級."""

    AUTO = "auto"          # 直接執行，不問
    CONFIRM = "confirm"    # 需使用者確認
    DENY = "deny"          # 拒絕執行


class TaskPriority(str, Enum):
    """任務優先級."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


_PRIORITY_ORDER = {
    TaskPriority.URGENT: 0,
    TaskPriority.HIGH: 1,
    TaskPriority.NORMAL: 2,
    TaskPriority.LOW: 3,
}


class TaskStatus(str, Enum):
    """任務狀態."""

    PENDING = "pending"
    APPROVED = "approved"
    WAITING_CONFIRM = "waiting_confirm"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"
    CANCELLED = "cancelled"


# ═══════════════════════════════════════════
# AutonomousTask
# ═══════════════════════════════════════════


@dataclass
class AutonomousTask:
    """自主任務."""

    task_id: str
    source: str                 # "heartbeat" / "schedule" / "event" / "proactive"
    action: str                 # "notification" / "skill_invoke" / "tool_call" / ...
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化."""
        d = asdict(self)
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AutonomousTask":
        """反序列化."""
        d = dict(d)
        d["priority"] = TaskPriority(d.get("priority", "normal"))
        d["status"] = TaskStatus(d.get("status", "pending"))
        return cls(**d)


# ═══════════════════════════════════════════
# AuthPolicy
# ═══════════════════════════════════════════

# 預設授權策略
DEFAULT_POLICIES: Dict[str, AuthLevel] = {
    "notification": AuthLevel.AUTO,
    "skill_invoke": AuthLevel.AUTO,
    "tool_call": AuthLevel.AUTO,
    "system_check": AuthLevel.AUTO,
    "data_read": AuthLevel.AUTO,
    "data_modify": AuthLevel.CONFIRM,
    "send_message": AuthLevel.CONFIRM,
    "delete": AuthLevel.DENY,
    "purchase": AuthLevel.DENY,
    "account_modify": AuthLevel.DENY,
}


class AuthPolicy:
    """授權策略引擎.

    三級授權 + 場景感知：
    - AUTO: 信任操作，直接執行
    - CONFIRM: 敏感操作，需使用者確認
    - DENY: 危險操作，拒絕執行
    """

    def __init__(
        self,
        custom_policies: Optional[Dict[str, AuthLevel]] = None,
    ) -> None:
        self._policies: Dict[str, AuthLevel] = dict(DEFAULT_POLICIES)
        if custom_policies:
            self._policies.update(custom_policies)

    def check(self, task: AutonomousTask) -> AuthLevel:
        """檢查任務的授權等級."""
        return self._policies.get(task.action, AuthLevel.CONFIRM)

    def grant(self, action: str, level: AuthLevel) -> None:
        """授予特定操作的授權等級."""
        self._policies[action] = level

    def revoke(self, action: str) -> None:
        """撤銷自訂授權，回復預設."""
        if action in DEFAULT_POLICIES:
            self._policies[action] = DEFAULT_POLICIES[action]
        else:
            self._policies.pop(action, None)

    def get_policy(self, action: str) -> AuthLevel:
        """取得特定操作的授權等級."""
        return self._policies.get(action, AuthLevel.CONFIRM)

    @property
    def policies(self) -> Dict[str, str]:
        """回傳所有策略（序列化格式）."""
        return {k: v.value for k, v in self._policies.items()}


# ═══════════════════════════════════════════
# AutonomousQueue
# ═══════════════════════════════════════════


class AutonomousQueue:
    """自主任務佇列 + 執行引擎.

    核心流程：
      觸發源 → enqueue(task) → AuthPolicy.check()
        → AUTO → 直接執行
        → CONFIRM → 等待使用者確認
        → DENY → 拒絕
      process_next() → 執行佇列中可執行的下一個任務
      emergency_stop() → 緊急停止所有任務
    """

    def __init__(
        self,
        auth_policy: Optional[AuthPolicy] = None,
        budget_monitor: Any = None,
        event_bus: Any = None,
        state_path: Optional[str] = None,
    ) -> None:
        self._queue: List[AutonomousTask] = []
        self._auth_policy = auth_policy or AuthPolicy()
        self._budget_monitor = budget_monitor
        self._event_bus = event_bus
        self._emergency_stop_flag = False
        self._completed: List[AutonomousTask] = []
        self._state_path = Path(state_path) if state_path else None

        # 任務執行器（action → callable）
        self._executors: Dict[str, Callable] = {}

        self._load_state()

    # ── 任務入隊 ──

    def enqueue(self, task: AutonomousTask) -> bool:
        """加入任務到佇列.

        Returns:
            True if enqueued, False if rejected.
        """
        # 緊急停止時拒絕
        if self._emergency_stop_flag:
            logger.warning(
                f"Emergency stop active, rejecting task: {task.task_id}"
            )
            task.status = TaskStatus.CANCELLED
            self._completed.append(task)
            return False

        # 佇列滿時拒絕
        if len(self._queue) >= MAX_QUEUE_SIZE:
            logger.warning(
                f"Queue full ({MAX_QUEUE_SIZE}), rejecting task: {task.task_id}"
            )
            task.status = TaskStatus.CANCELLED
            self._completed.append(task)
            return False

        # 授權檢查
        auth_level = self._auth_policy.check(task)

        if auth_level == AuthLevel.DENY:
            logger.info(f"Task denied by policy: {task.task_id} ({task.action})")
            task.status = TaskStatus.DENIED
            self._completed.append(task)
            self._save_state()
            return False

        if auth_level == AuthLevel.CONFIRM:
            task.status = TaskStatus.WAITING_CONFIRM
        else:
            task.status = TaskStatus.APPROVED

        # 預算檢查
        if self._budget_monitor and not self._check_budget(task):
            logger.warning(f"Budget exceeded, rejecting task: {task.task_id}")
            task.status = TaskStatus.DENIED
            task.error = "budget_exceeded"
            self._completed.append(task)
            self._save_state()
            return False

        self._queue.append(task)
        self._sort_queue()
        self._save_state()
        return True

    def approve_task(self, task_id: str) -> bool:
        """使用者確認任務."""
        for task in self._queue:
            if task.task_id == task_id and task.status == TaskStatus.WAITING_CONFIRM:
                task.status = TaskStatus.APPROVED
                self._save_state()
                return True
        return False

    def deny_task(self, task_id: str) -> bool:
        """使用者拒絕任務."""
        for task in self._queue:
            if task.task_id == task_id and task.status == TaskStatus.WAITING_CONFIRM:
                task.status = TaskStatus.DENIED
                self._queue.remove(task)
                self._completed.append(task)
                self._save_state()
                return True
        return False

    # ── 任務處理 ──

    async def process_next(self) -> Optional[AutonomousTask]:
        """處理佇列中下一個可執行的任務.

        Returns:
            處理的任務，或 None 如果沒有可執行任務。
        """
        if self._emergency_stop_flag:
            return None

        task = self._find_next_approved()
        if not task:
            return None

        task.status = TaskStatus.RUNNING
        self._save_state()

        try:
            executor = self._executors.get(task.action)
            if executor:
                result = await executor(task.payload) if _is_coroutine(executor) else executor(task.payload)
                task.result = result if isinstance(result, dict) else {"output": result}
            else:
                task.result = {"output": "no_executor"}

            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            logger.error(f"Task {task.task_id} failed: {e}")

        self._queue.remove(task)
        self._completed.append(task)
        self._trim_history()
        self._save_state()

        # 發布事件
        if self._event_bus and task.status == TaskStatus.COMPLETED:
            from museon.core.event_bus import AUTONOMOUS_TASK_DONE
            self._event_bus.publish(AUTONOMOUS_TASK_DONE, {
                "task_id": task.task_id,
                "action": task.action,
                "status": task.status.value,
            })

        return task

    def register_executor(self, action: str, executor: Callable) -> None:
        """註冊任務執行器."""
        self._executors[action] = executor

    # ── 緊急停止 ──

    def emergency_stop(self) -> int:
        """緊急停止：取消所有佇列中的任務.

        Returns:
            被取消的任務數量。
        """
        self._emergency_stop_flag = True
        cancelled = 0
        for task in list(self._queue):
            task.status = TaskStatus.CANCELLED
            task.completed_at = time.time()
            self._completed.append(task)
            cancelled += 1
        self._queue.clear()
        self._save_state()
        logger.warning(f"Emergency stop: {cancelled} tasks cancelled")
        return cancelled

    def resume(self) -> None:
        """從緊急停止恢復."""
        self._emergency_stop_flag = False
        logger.info("AutonomousQueue resumed from emergency stop")

    @property
    def is_stopped(self) -> bool:
        return self._emergency_stop_flag

    # ── 查詢 ──

    def get_pending(self) -> List[AutonomousTask]:
        """取得所有待處理任務."""
        return [t for t in self._queue if t.status in (
            TaskStatus.PENDING, TaskStatus.APPROVED, TaskStatus.WAITING_CONFIRM
        )]

    def get_waiting_confirm(self) -> List[AutonomousTask]:
        """取得等待使用者確認的任務."""
        return [t for t in self._queue if t.status == TaskStatus.WAITING_CONFIRM]

    def get_history(self, limit: int = 20) -> List[AutonomousTask]:
        """取得歷史記錄（最近 N 筆）."""
        return list(self._completed[-limit:])

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    # ── 授權管理代理 ──

    def grant_action(self, action: str, level: AuthLevel) -> None:
        """授予操作授權."""
        self._auth_policy.grant(action, level)

    def revoke_action(self, action: str) -> None:
        """撤銷操作授權."""
        self._auth_policy.revoke(action)

    # ── 內部工具 ──

    def _find_next_approved(self) -> Optional[AutonomousTask]:
        """找到下一個已核准的任務（按優先級）."""
        for task in self._queue:
            if task.status == TaskStatus.APPROVED:
                return task
        return None

    def _sort_queue(self) -> None:
        """按優先級排序佇列."""
        self._queue.sort(
            key=lambda t: _PRIORITY_ORDER.get(t.priority, 99)
        )

    def _check_budget(self, task: AutonomousTask) -> bool:
        """預算檢查."""
        if not self._budget_monitor:
            return True
        try:
            return self._budget_monitor.check_budget(0.01)  # 估算最小成本
        except Exception:
            return True

    def _trim_history(self) -> None:
        """修剪歷史記錄."""
        if len(self._completed) > MAX_HISTORY_SIZE:
            self._completed = self._completed[-MAX_HISTORY_SIZE:]

    # ── 持久化 ──

    def _save_state(self) -> None:
        """儲存佇列狀態."""
        if not self._state_path:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "queue": [t.to_dict() for t in self._queue],
                "completed": [t.to_dict() for t in self._completed[-20:]],
                "emergency_stop": self._emergency_stop_flag,
            }
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.rename(self._state_path)
        except Exception as e:
            logger.error(f"AutonomousQueue save state failed: {e}")

    def _load_state(self) -> None:
        """載入佇列狀態."""
        if not self._state_path or not self._state_path.exists():
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._queue = [
                AutonomousTask.from_dict(d) for d in state.get("queue", [])
            ]
            self._completed = [
                AutonomousTask.from_dict(d) for d in state.get("completed", [])
            ]
            self._emergency_stop_flag = state.get("emergency_stop", False)
        except Exception as e:
            logger.error(f"AutonomousQueue load state failed: {e}")


def _is_coroutine(func: Callable) -> bool:
    """檢查是否為 coroutine function."""
    import asyncio
    return asyncio.iscoroutinefunction(func)
