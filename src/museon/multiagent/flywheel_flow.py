"""Flywheel Flow — 飛輪任務流動協調器.

依據施工計畫 Phase 4.4 實作。
管理部門間的任務交接，遵循八卦飛輪序列。
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FlowStatus(Enum):
    """任務流動狀態."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DepartmentOutput:
    """部門處理後的產出."""
    dept_id: str
    content: str
    recommendations: List[str] = field(default_factory=list)
    handoff_context: str = ""  # 交給下一個部門的上下文
    timestamp: float = 0.0


@dataclass
class FlywheelTask:
    """飛輪任務."""
    task_id: str
    content: str
    source_dept: str
    target_dept: str
    status: FlowStatus = FlowStatus.PENDING
    outputs: List[DepartmentOutput] = field(default_factory=list)
    created_at: float = 0.0
    completed_at: float = 0.0


class FlywheelCoordinator:
    """飛輪任務流動協調器.

    管理部門間的循環式任務流動：
    thunder → fire → lake → heaven → wind → water → mountain → earth → 迴圈
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, FlywheelTask] = {}
        self._task_counter = 0

    def initiate_flow(
        self,
        content: str,
        start_dept: str,
        max_steps: int = 3,
    ) -> FlywheelTask:
        """啟動飛輪流動.

        Args:
            content: 任務內容
            start_dept: 起始部門
            max_steps: 最多經過幾個部門（預設 3，避免無限流動）

        Returns:
            FlywheelTask
        """
        self._task_counter += 1
        task_id = f"fw-{self._task_counter:04d}"

        task = FlywheelTask(
            task_id=task_id,
            content=content,
            source_dept=start_dept,
            target_dept=start_dept,
            status=FlowStatus.PENDING,
            created_at=time.time(),
        )
        self._tasks[task_id] = task
        logger.info(f"Flywheel flow initiated: {task_id} @ {start_dept}")
        return task

    def record_output(
        self,
        task_id: str,
        dept_id: str,
        content: str,
        recommendations: Optional[List[str]] = None,
        handoff_context: str = "",
    ) -> None:
        """記錄部門處理結果."""
        task = self._tasks.get(task_id)
        if not task:
            return

        output = DepartmentOutput(
            dept_id=dept_id,
            content=content,
            recommendations=recommendations or [],
            handoff_context=handoff_context,
            timestamp=time.time(),
        )
        task.outputs.append(output)

    def handoff(
        self,
        task_id: str,
        from_dept: str,
        to_dept: str,
    ) -> bool:
        """部門間交接.

        Returns:
            True if handoff successful.
        """
        task = self._tasks.get(task_id)
        if not task:
            return False

        task.source_dept = from_dept
        task.target_dept = to_dept
        task.status = FlowStatus.IN_PROGRESS
        logger.info(f"Flywheel handoff: {task_id} {from_dept} → {to_dept}")
        return True

    def complete_flow(self, task_id: str) -> None:
        """完成流動."""
        task = self._tasks.get(task_id)
        if task:
            task.status = FlowStatus.COMPLETED
            task.completed_at = time.time()

    def get_flow_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """查看流動進度."""
        task = self._tasks.get(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "current_dept": task.target_dept,
            "steps_completed": len(task.outputs),
            "departments_visited": [o.dept_id for o in task.outputs],
            "elapsed_seconds": (
                (task.completed_at or time.time()) - task.created_at
            ),
        }

    def get_active_flows(self) -> List[Dict[str, Any]]:
        """取得所有進行中的流動."""
        return [
            self.get_flow_status(tid)
            for tid, t in self._tasks.items()
            if t.status in (FlowStatus.PENDING, FlowStatus.IN_PROGRESS)
        ]
