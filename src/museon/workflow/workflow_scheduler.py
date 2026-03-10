"""WorkflowScheduler — 軟工作流排程整合.

將 SoftWorkflow 的 ScheduleConfig 轉換為 CronEngine job，
管理排程的註冊、移除、暫停/恢復、手動觸發。
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from .soft_workflow import SoftWorkflow, WorkflowStore

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


def _parse_cron_parts(cron_expr: str) -> Dict[str, str]:
    """解析 cron 表達式為 APScheduler CronTrigger 參數.

    標準 5 欄位：minute hour day_of_month month day_of_week
    例: "30 14 * * 1-5" → minute=30, hour=14, day_of_week=mon-fri
    """
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (need 5 fields): {cron_expr}")

    result: Dict[str, str] = {}

    if parts[0] != "*":
        result["minute"] = parts[0]
    if parts[1] != "*":
        result["hour"] = parts[1]
    if parts[2] != "*":
        result["day"] = parts[2]
    if parts[3] != "*":
        result["month"] = parts[3]
    if parts[4] != "*":
        # 轉換數字 day_of_week 為 APScheduler 格式
        dow = parts[4]
        dow_map = {"0": "sun", "1": "mon", "2": "tue", "3": "wed",
                   "4": "thu", "5": "fri", "6": "sat", "7": "sun"}
        # 處理範圍如 "1-5"
        for digit, name in dow_map.items():
            dow = dow.replace(digit, name)
        result["day_of_week"] = dow

    return result


class WorkflowScheduler:
    """軟工作流排程管理器.

    整合 CronEngine（APScheduler），管理工作流的 cron 排程。
    """

    def __init__(
        self,
        cron_engine: Any,
        store: WorkflowStore,
        event_bus: Any = None,
    ) -> None:
        self._cron_engine = cron_engine
        self._store = store
        self._event_bus = event_bus
        self._registered: Set[str] = set()
        self._executor: Optional[Any] = None  # 延遲注入

    def set_executor(self, executor: Any) -> None:
        """注入 WorkflowExecutor（避免循環依賴）."""
        self._executor = executor

    @property
    def registered_ids(self) -> Set[str]:
        """已註冊的工作流 ID."""
        return self._registered.copy()

    # ── 批量註冊 ──

    def register_all(self) -> int:
        """Gateway 啟動時：掃描所有 active cron 工作流，註冊到 CronEngine.

        Returns:
            成功註冊的數量
        """
        workflows = self._store.list_all()
        count = 0
        for wf in workflows:
            if (
                wf.schedule.schedule_type == "cron"
                and wf.schedule.cron_expression
                and wf.schedule.active
            ):
                try:
                    self.register(wf.workflow_id)
                    count += 1
                except Exception as e:
                    logger.error(
                        f"WorkflowScheduler register failed: {wf.workflow_id} ({wf.name}): {e}"
                    )
        logger.info(f"WorkflowScheduler register_all: {count} workflows registered")
        return count

    # ── 單一工作流排程 ──

    def register(self, workflow_id: str) -> None:
        """註冊單一工作流到 CronEngine."""
        wf = self._store.load(workflow_id)
        if not wf:
            raise ValueError(f"Workflow {workflow_id} not found")

        if wf.schedule.schedule_type != "cron" or not wf.schedule.cron_expression:
            logger.debug(f"Workflow {workflow_id} is not cron-type, skip register")
            return

        if not wf.schedule.active:
            logger.debug(f"Workflow {workflow_id} is inactive, skip register")
            return

        job_id = f"workflow-{workflow_id}"

        # 解析 cron 表達式
        try:
            trigger_args = _parse_cron_parts(wf.schedule.cron_expression)
        except ValueError as e:
            logger.error(f"Invalid cron for {workflow_id}: {e}")
            raise

        # 建立 async callback
        async def _fire() -> None:
            await self._on_schedule_fire(workflow_id)

        # 註冊到 CronEngine
        self._cron_engine.add_job(
            func=_fire,
            trigger="cron",
            job_id=job_id,
            **trigger_args,
        )

        self._registered.add(workflow_id)
        logger.info(
            f"WorkflowScheduler registered: {workflow_id} ({wf.name}) "
            f"cron={wf.schedule.cron_expression}"
        )

    def unregister(self, workflow_id: str) -> None:
        """移除工作流的 cron job."""
        job_id = f"workflow-{workflow_id}"
        try:
            self._cron_engine.remove_job(job_id)
        except Exception:
            pass  # job 可能不存在
        self._registered.discard(workflow_id)
        logger.info(f"WorkflowScheduler unregistered: {workflow_id}")

    def toggle(self, workflow_id: str, active: bool) -> None:
        """暫停/恢復工作流排程.

        Args:
            workflow_id: 工作流 ID
            active: True=啟用, False=暫停
        """
        wf = self._store.load(workflow_id)
        if not wf:
            return

        # 更新 ScheduleConfig
        wf.schedule.active = active
        wf.last_modified = datetime.now(TZ_TAIPEI).isoformat()
        self._store.save(wf)

        if active:
            self.register(workflow_id)
        else:
            self.unregister(workflow_id)

        self._publish("WORKFLOW_SCHEDULE_TOGGLED", {
            "workflow_id": workflow_id,
            "active": active,
        })

        logger.info(
            f"WorkflowScheduler toggle: {workflow_id} → {'active' if active else 'paused'}"
        )

    async def trigger_now(self, workflow_id: str) -> Any:
        """手動觸發執行（繞過排程）.

        Returns:
            ExecutionSummary 或 None
        """
        if not self._executor:
            logger.error("WorkflowScheduler: no executor set, cannot trigger")
            return None
        return await self._executor.execute(
            workflow_id=workflow_id,
            trigger_source="manual",
        )

    # ── 排程回調 ──

    async def _on_schedule_fire(self, workflow_id: str) -> None:
        """CronEngine 排程觸發時的回調."""
        logger.info(f"WorkflowScheduler cron fire: {workflow_id}")
        if not self._executor:
            logger.error("WorkflowScheduler: no executor set, skip cron fire")
            return

        try:
            await self._executor.execute(
                workflow_id=workflow_id,
                trigger_source="cron",
            )
        except Exception as e:
            logger.error(f"WorkflowScheduler cron execution failed: {workflow_id}: {e}")
            self._publish("WORKFLOW_FAILED", {
                "workflow_id": workflow_id,
                "trigger_source": "cron",
                "error": str(e)[:500],
            })

    def _publish(self, event_type: str, data: Dict) -> None:
        """EventBus 發布（靜默失敗）."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception as e:
                logger.warning(f"EventBus publish '{event_type}' failed: {e}")
