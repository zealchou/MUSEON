"""Task Dispatch System — MUSEON 多 Skill 編排分派.

當使用者需求匹配 3+ Skills 或觸發分派條件時，
dispatch 系統將任務分解為獨立子任務，每個子任務在隔離的 context 中
帶完整 SKILL.md 執行，最後綜合所有結果回覆使用者。

核心協議：
  - TaskPackage: 主腦派出的任務定義
  - ResultPackage: Worker 回傳的執行結果
  - HandoffPackage: 子任務間的銜接上下文
  - DispatchPlan: 完整的分派計劃（含所有子任務和結果）
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════


class DispatchStatus(str, Enum):
    """Dispatch plan 生命週期狀態."""

    PLANNING = "planning"
    EXECUTING = "executing"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class TaskStatus(str, Enum):
    """個別子任務生命週期狀態."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class ExecutionMode(str, Enum):
    """執行模式."""

    SERIAL = "serial"
    PARALLEL = "parallel"
    MIXED = "mixed"


# ═══════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════


@dataclass
class HandoffPackage:
    """子任務間的銜接上下文.

    設計原則：讓下一個 Worker 不需要任何額外資訊就能開工。
    excluded_topics 和 user_implicit_preferences 是強制欄位。
    """

    for_next_skill: str
    compressed_context: str  # ≤200 tokens
    action_items_for_next: List[str] = field(default_factory=list)
    excluded_topics: List[str] = field(default_factory=list)
    user_implicit_preferences: List[str] = field(default_factory=list)


@dataclass
class TaskPackage:
    """主腦派出的子任務定義."""

    task_id: str
    skill_name: str
    skill_focus: str
    skill_depth: str  # "quick" | "standard" | "deep"
    input_data: Dict[str, Any] = field(default_factory=dict)
    expected_output: str = ""
    execution_order: int = 0
    depends_on: List[str] = field(default_factory=list)
    model_preference: str = "haiku"  # "haiku" | "sonnet"
    timeout_seconds: int = 300
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultPackage:
    """Worker 回傳的執行結果."""

    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    result: Dict[str, Any] = field(default_factory=dict)
    quality: Dict[str, Any] = field(default_factory=dict)
    handoff_package: Optional[HandoffPackage] = None
    token_usage: Dict[str, int] = field(default_factory=dict)
    execution_time_ms: int = 0
    error_message: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchPlan:
    """完整的分派計劃."""

    plan_id: str
    user_request: str
    session_id: str
    created_at: str = ""
    status: DispatchStatus = DispatchStatus.PLANNING
    execution_mode: ExecutionMode = ExecutionMode.SERIAL
    tasks: List[TaskPackage] = field(default_factory=list)
    results: List[ResultPackage] = field(default_factory=list)
    synthesis_result: Optional[str] = None
    total_token_usage: Dict[str, int] = field(default_factory=dict)
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════
# Serialization
# ═══════════════════════════════════════════


def dispatch_plan_to_dict(plan: DispatchPlan) -> Dict[str, Any]:
    """將 DispatchPlan 序列化為可 JSON 化的 dict."""
    data = asdict(plan)
    # Enum 值轉字串
    data["status"] = plan.status.value
    data["execution_mode"] = plan.execution_mode.value
    for i, task in enumerate(data.get("tasks", [])):
        if isinstance(task.get("status"), TaskStatus):
            task["status"] = task["status"].value
    for i, result in enumerate(data.get("results", [])):
        if isinstance(result.get("status"), TaskStatus):
            result["status"] = result["status"].value
        elif isinstance(result.get("status"), str):
            pass  # already string from asdict
    return data


def persist_dispatch_plan(
    plan: DispatchPlan,
    data_dir: Path,
    *,
    completed: bool = False,
    failed: bool = False,
) -> None:
    """將 dispatch plan 持久化到磁碟."""
    dispatch_dir = data_dir / "dispatch"

    if completed:
        target_dir = dispatch_dir / "completed"
    elif failed:
        target_dir = dispatch_dir / "failed"
    else:
        target_dir = dispatch_dir / "active"

    target_dir.mkdir(parents=True, exist_ok=True)

    # 完成或失敗時，從 active 移除
    active_path = dispatch_dir / "active" / f"{plan.plan_id}.json"
    if (completed or failed) and active_path.exists():
        try:
            active_path.unlink()
        except OSError:
            pass

    target_path = target_dir / f"{plan.plan_id}.json"
    try:
        data = dispatch_plan_to_dict(plan)
        target_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error(f"Failed to persist dispatch plan: {e}")


# ═══════════════════════════════════════════
# DAG Execution Utilities
# ═══════════════════════════════════════════


def build_execution_layers(
    tasks: List[TaskPackage],
) -> List[List[TaskPackage]]:
    """將 tasks 按 depends_on 建構 DAG 分層.

    同一層的 tasks 無互相依賴 → 可平行執行。
    層間為串行。

    Returns:
        List of layers, each layer is a list of tasks.
    """
    if not tasks:
        return []

    task_map = {t.task_id: t for t in tasks}
    completed = set()
    layers: List[List[TaskPackage]] = []
    remaining = list(tasks)

    max_iterations = len(tasks) + 1
    for _ in range(max_iterations):
        if not remaining:
            break

        # 找出所有依賴已滿足的 tasks
        ready = []
        still_waiting = []
        for task in remaining:
            deps = task.depends_on or []
            if all(d in completed for d in deps):
                ready.append(task)
            else:
                still_waiting.append(task)

        if not ready:
            # 有循環依賴或無效引用 → 把剩餘全部塞入最後一層
            logger.warning(
                f"DAG 有未解依賴，強制排入: "
                f"{[t.task_id for t in still_waiting]}"
            )
            layers.append(still_waiting)
            break

        layers.append(ready)
        for t in ready:
            completed.add(t.task_id)
        remaining = still_waiting

    return layers


def determine_execution_mode(
    tasks: List[TaskPackage],
) -> ExecutionMode:
    """根據 tasks 的 depends_on 決定執行模式.

    - 全部無依賴 → PARALLEL
    - 每個依賴前一個 → SERIAL
    - 混合 → MIXED
    """
    if not tasks:
        return ExecutionMode.SERIAL

    has_deps = any(t.depends_on for t in tasks)
    if not has_deps:
        return ExecutionMode.PARALLEL if len(tasks) > 1 else ExecutionMode.SERIAL

    # 檢查是否純串行（每個 task 只依賴前一個）
    for i, task in enumerate(tasks):
        if i == 0:
            if task.depends_on:
                return ExecutionMode.MIXED
        else:
            expected = [tasks[i - 1].task_id]
            if task.depends_on != expected:
                return ExecutionMode.MIXED

    return ExecutionMode.SERIAL


# ═══════════════════════════════════════════
# Recovery Utilities
# ═══════════════════════════════════════════


def recover_active_plans(data_dir: Path) -> int:
    """掃描 active/ 下的 dispatch plans，標記為 failed.

    Gateway 重啟時呼叫。回傳處理數量。
    """
    active_dir = data_dir / "dispatch" / "active"
    if not active_dir.exists():
        return 0

    failed_dir = data_dir / "dispatch" / "failed"
    failed_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for plan_file in active_dir.glob("*.json"):
        try:
            data = json.loads(plan_file.read_text(encoding="utf-8"))
            data["status"] = "failed"
            data["error_message"] = (
                data.get("error_message", "")
                or "Recovered after restart — execution interrupted"
            )

            target = failed_dir / plan_file.name
            target.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            plan_file.unlink()
            count += 1
            logger.info(f"Recovered dispatch plan: {plan_file.name}")
        except Exception as e:
            logger.error(f"Failed to recover plan {plan_file.name}: {e}")

    return count
