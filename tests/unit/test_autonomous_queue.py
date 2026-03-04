"""Tests for autonomous_queue.py — 自主任務佇列 + 授權策略.

依據 Autonomous Execution BDD Spec 驗證。
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from museon.core.event_bus import AUTONOMOUS_TASK_DONE, EventBus
from museon.pulse.autonomous_queue import (
    DEFAULT_POLICIES,
    MAX_QUEUE_SIZE,
    AuthLevel,
    AuthPolicy,
    AutonomousQueue,
    AutonomousTask,
    TaskPriority,
    TaskStatus,
)


# ═══════════════════════════════════════════
# AuthLevel Tests (§1)
# ═══════════════════════════════════════════


class TestAuthLevel:
    """授權等級測試."""

    def test_auto_value(self):
        assert AuthLevel.AUTO == "auto"

    def test_confirm_value(self):
        assert AuthLevel.CONFIRM == "confirm"

    def test_deny_value(self):
        assert AuthLevel.DENY == "deny"


# ═══════════════════════════════════════════
# Default Policies Tests (§2)
# ═══════════════════════════════════════════


class TestDefaultPolicies:
    """預設策略測試."""

    def test_notification_auto(self):
        """BDD: notification → AUTO."""
        assert DEFAULT_POLICIES["notification"] == AuthLevel.AUTO

    def test_skill_invoke_auto(self):
        """BDD: skill_invoke → AUTO."""
        assert DEFAULT_POLICIES["skill_invoke"] == AuthLevel.AUTO

    def test_tool_call_auto(self):
        """BDD: tool_call → AUTO."""
        assert DEFAULT_POLICIES["tool_call"] == AuthLevel.AUTO

    def test_data_modify_confirm(self):
        """BDD: data_modify → CONFIRM."""
        assert DEFAULT_POLICIES["data_modify"] == AuthLevel.CONFIRM

    def test_send_message_confirm(self):
        """BDD: send_message → CONFIRM."""
        assert DEFAULT_POLICIES["send_message"] == AuthLevel.CONFIRM

    def test_delete_deny(self):
        """BDD: delete → DENY."""
        assert DEFAULT_POLICIES["delete"] == AuthLevel.DENY

    def test_purchase_deny(self):
        """BDD: purchase → DENY."""
        assert DEFAULT_POLICIES["purchase"] == AuthLevel.DENY


# ═══════════════════════════════════════════
# AuthPolicy Tests
# ═══════════════════════════════════════════


class TestAuthPolicy:
    """授權策略引擎測試."""

    def test_check_default(self):
        """BDD: 未知操作 → CONFIRM."""
        policy = AuthPolicy()
        task = AutonomousTask(
            task_id="t1", source="test", action="unknown_action"
        )
        assert policy.check(task) == AuthLevel.CONFIRM

    def test_check_known_action(self):
        """BDD: 已知操作回傳正確等級."""
        policy = AuthPolicy()
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        assert policy.check(task) == AuthLevel.AUTO

    def test_grant_override(self):
        """BDD: grant() 覆寫預設."""
        policy = AuthPolicy()
        policy.grant("delete", AuthLevel.AUTO)
        task = AutonomousTask(
            task_id="t1", source="test", action="delete"
        )
        assert policy.check(task) == AuthLevel.AUTO

    def test_revoke_restore_default(self):
        """BDD: revoke() 回復預設."""
        policy = AuthPolicy()
        policy.grant("delete", AuthLevel.AUTO)
        policy.revoke("delete")
        task = AutonomousTask(
            task_id="t1", source="test", action="delete"
        )
        assert policy.check(task) == AuthLevel.DENY

    def test_revoke_custom_action(self):
        """BDD: revoke() 移除非預設操作."""
        policy = AuthPolicy()
        policy.grant("custom_op", AuthLevel.AUTO)
        assert policy.get_policy("custom_op") == AuthLevel.AUTO
        policy.revoke("custom_op")
        assert policy.get_policy("custom_op") == AuthLevel.CONFIRM

    def test_custom_initial_policies(self):
        """BDD: 初始化時自訂策略."""
        policy = AuthPolicy(custom_policies={"delete": AuthLevel.AUTO})
        task = AutonomousTask(
            task_id="t1", source="test", action="delete"
        )
        assert policy.check(task) == AuthLevel.AUTO

    def test_policies_property(self):
        """BDD: policies 屬性回傳序列化格式."""
        policy = AuthPolicy()
        result = policy.policies
        assert result["notification"] == "auto"
        assert result["delete"] == "deny"


# ═══════════════════════════════════════════
# AutonomousTask Tests
# ═══════════════════════════════════════════


class TestAutonomousTask:
    """自主任務測試."""

    def test_create_task(self):
        """BDD: 建立任務."""
        task = AutonomousTask(
            task_id="t1", source="heartbeat", action="notification"
        )
        assert task.task_id == "t1"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL

    def test_to_dict(self):
        """BDD: 序列化."""
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        d = task.to_dict()
        assert d["task_id"] == "t1"
        assert d["priority"] == "normal"
        assert d["status"] == "pending"

    def test_from_dict(self):
        """BDD: 反序列化."""
        d = {
            "task_id": "t1",
            "source": "test",
            "action": "notification",
            "priority": "high",
            "status": "completed",
            "payload": {"key": "val"},
            "created_at": 1000.0,
            "completed_at": 2000.0,
            "result": {"output": "ok"},
            "error": None,
        }
        task = AutonomousTask.from_dict(d)
        assert task.task_id == "t1"
        assert task.priority == TaskPriority.HIGH
        assert task.status == TaskStatus.COMPLETED

    def test_roundtrip(self):
        """BDD: 序列化/反序列化往返."""
        original = AutonomousTask(
            task_id="t1",
            source="heartbeat",
            action="skill_invoke",
            priority=TaskPriority.URGENT,
            payload={"skill": "test"},
        )
        restored = AutonomousTask.from_dict(original.to_dict())
        assert restored.task_id == original.task_id
        assert restored.priority == original.priority
        assert restored.payload == original.payload


# ═══════════════════════════════════════════
# Queue Enqueue Tests (§3)
# ═══════════════════════════════════════════


class TestQueueEnqueue:
    """任務入隊測試."""

    def test_enqueue_auto_task(self):
        """BDD: AUTO 操作直接入隊為 APPROVED."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        assert queue.enqueue(task)
        assert task.status == TaskStatus.APPROVED
        assert queue.queue_size == 1

    def test_enqueue_confirm_task(self):
        """BDD: CONFIRM 操作入隊為 WAITING_CONFIRM."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="data_modify"
        )
        assert queue.enqueue(task)
        assert task.status == TaskStatus.WAITING_CONFIRM
        assert queue.queue_size == 1

    def test_enqueue_deny_task(self):
        """BDD: DENY 操作被拒絕."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="delete"
        )
        assert not queue.enqueue(task)
        assert task.status == TaskStatus.DENIED
        assert queue.queue_size == 0

    def test_queue_full(self):
        """BDD: 佇列滿 → 拒絕."""
        queue = AutonomousQueue()
        for i in range(MAX_QUEUE_SIZE):
            queue.enqueue(AutonomousTask(
                task_id=f"t{i}", source="test", action="notification"
            ))
        overflow = AutonomousTask(
            task_id="overflow", source="test", action="notification"
        )
        assert not queue.enqueue(overflow)
        assert overflow.status == TaskStatus.CANCELLED

    def test_priority_sorting(self):
        """BDD: 佇列按優先級排序."""
        queue = AutonomousQueue()
        queue.enqueue(AutonomousTask(
            task_id="low", source="test", action="notification",
            priority=TaskPriority.LOW,
        ))
        queue.enqueue(AutonomousTask(
            task_id="urgent", source="test", action="notification",
            priority=TaskPriority.URGENT,
        ))
        queue.enqueue(AutonomousTask(
            task_id="normal", source="test", action="notification",
            priority=TaskPriority.NORMAL,
        ))
        pending = queue.get_pending()
        assert pending[0].task_id == "urgent"
        assert pending[1].task_id == "normal"
        assert pending[2].task_id == "low"


# ═══════════════════════════════════════════
# Approve / Deny Tests
# ═══════════════════════════════════════════


class TestApproveDeny:
    """使用者確認/拒絕測試."""

    def test_approve_task(self):
        """BDD: 確認任務 → APPROVED."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="data_modify"
        )
        queue.enqueue(task)
        assert task.status == TaskStatus.WAITING_CONFIRM
        assert queue.approve_task("t1")
        assert task.status == TaskStatus.APPROVED

    def test_deny_task(self):
        """BDD: 拒絕任務 → DENIED."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="data_modify"
        )
        queue.enqueue(task)
        assert queue.deny_task("t1")
        assert task.status == TaskStatus.DENIED
        assert queue.queue_size == 0

    def test_approve_nonexistent(self):
        """BDD: 確認不存在的任務 → False."""
        queue = AutonomousQueue()
        assert not queue.approve_task("nonexistent")

    def test_deny_nonexistent(self):
        """BDD: 拒絕不存在的任務 → False."""
        queue = AutonomousQueue()
        assert not queue.deny_task("nonexistent")


# ═══════════════════════════════════════════
# Emergency Stop Tests (§4)
# ═══════════════════════════════════════════


class TestEmergencyStop:
    """緊急停止測試."""

    def test_emergency_stop(self):
        """BDD: emergency_stop() 取消所有任務."""
        queue = AutonomousQueue()
        for i in range(5):
            queue.enqueue(AutonomousTask(
                task_id=f"t{i}", source="test", action="notification"
            ))
        cancelled = queue.emergency_stop()
        assert cancelled == 5
        assert queue.queue_size == 0
        assert queue.is_stopped

    def test_stop_rejects_new_tasks(self):
        """BDD: 停止後 enqueue 被拒絕."""
        queue = AutonomousQueue()
        queue.emergency_stop()
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        assert not queue.enqueue(task)
        assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_stop_rejects_process(self):
        """BDD: 停止後 process_next 回傳 None."""
        queue = AutonomousQueue()
        queue.emergency_stop()
        result = await queue.process_next()
        assert result is None

    def test_resume(self):
        """BDD: resume() 恢復."""
        queue = AutonomousQueue()
        queue.emergency_stop()
        assert queue.is_stopped
        queue.resume()
        assert not queue.is_stopped
        # 恢復後可以入隊
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        assert queue.enqueue(task)

    def test_empty_stop(self):
        """BDD: 空佇列停止."""
        queue = AutonomousQueue()
        cancelled = queue.emergency_stop()
        assert cancelled == 0


# ═══════════════════════════════════════════
# Budget Control Tests (§5)
# ═══════════════════════════════════════════


class TestBudgetControl:
    """預算控制測試."""

    def test_budget_passed(self):
        """BDD: 預算充足 → 入隊."""
        monitor = MagicMock()
        monitor.check_budget.return_value = True
        queue = AutonomousQueue(budget_monitor=monitor)
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        assert queue.enqueue(task)

    def test_budget_exceeded(self):
        """BDD: 預算不足 → 拒絕."""
        monitor = MagicMock()
        monitor.check_budget.return_value = False
        queue = AutonomousQueue(budget_monitor=monitor)
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        assert not queue.enqueue(task)
        assert task.status == TaskStatus.DENIED
        assert task.error == "budget_exceeded"

    def test_no_budget_monitor(self):
        """BDD: 無 budget_monitor → 不檢查."""
        queue = AutonomousQueue(budget_monitor=None)
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        assert queue.enqueue(task)


# ═══════════════════════════════════════════
# Process Next Tests
# ═══════════════════════════════════════════


class TestProcessNext:
    """任務處理測試."""

    @pytest.mark.asyncio
    async def test_process_approved_task(self):
        """BDD: 處理 APPROVED 任務."""
        queue = AutonomousQueue()
        queue.register_executor(
            "notification", lambda p: {"sent": True}
        )
        task = AutonomousTask(
            task_id="t1", source="test", action="notification",
            payload={"text": "hello"},
        )
        queue.enqueue(task)
        result = await queue.process_next()
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.result == {"sent": True}
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_process_async_executor(self):
        """BDD: 處理 async 執行器."""
        queue = AutonomousQueue()

        async def async_exec(payload):
            return {"async": True}

        queue.register_executor("notification", async_exec)
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        queue.enqueue(task)
        result = await queue.process_next()
        assert result.status == TaskStatus.COMPLETED
        assert result.result == {"async": True}

    @pytest.mark.asyncio
    async def test_process_no_executor(self):
        """BDD: 無執行器 → 完成但回傳 no_executor."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        queue.enqueue(task)
        result = await queue.process_next()
        assert result.status == TaskStatus.COMPLETED
        assert result.result == {"output": "no_executor"}

    @pytest.mark.asyncio
    async def test_process_executor_error(self):
        """BDD: 執行器錯誤 → FAILED."""
        queue = AutonomousQueue()
        queue.register_executor(
            "notification", lambda p: (_ for _ in ()).throw(RuntimeError("fail"))
        )
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        queue.enqueue(task)
        result = await queue.process_next()
        assert result.status == TaskStatus.FAILED
        assert "fail" in result.error

    @pytest.mark.asyncio
    async def test_process_empty_queue(self):
        """BDD: 空佇列 → None."""
        queue = AutonomousQueue()
        result = await queue.process_next()
        assert result is None

    @pytest.mark.asyncio
    async def test_skip_waiting_confirm(self):
        """BDD: 跳過 WAITING_CONFIRM 任務."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="data_modify"
        )
        queue.enqueue(task)
        assert task.status == TaskStatus.WAITING_CONFIRM
        result = await queue.process_next()
        assert result is None
        assert queue.queue_size == 1


# ═══════════════════════════════════════════
# Custom Auth Tests (§6)
# ═══════════════════════════════════════════


class TestCustomAuth:
    """自訂授權測試."""

    def test_grant_auto(self):
        """BDD: 授予 AUTO 後直接入隊."""
        queue = AutonomousQueue()
        queue.grant_action("data_modify", AuthLevel.AUTO)
        task = AutonomousTask(
            task_id="t1", source="test", action="data_modify"
        )
        queue.enqueue(task)
        assert task.status == TaskStatus.APPROVED

    def test_revoke_restore(self):
        """BDD: 撤銷後回復預設."""
        queue = AutonomousQueue()
        queue.grant_action("data_modify", AuthLevel.AUTO)
        queue.revoke_action("data_modify")
        task = AutonomousTask(
            task_id="t1", source="test", action="data_modify"
        )
        queue.enqueue(task)
        assert task.status == TaskStatus.WAITING_CONFIRM


# ═══════════════════════════════════════════
# History Tests (§7)
# ═══════════════════════════════════════════


class TestHistory:
    """歷史記錄測試."""

    @pytest.mark.asyncio
    async def test_completed_in_history(self):
        """BDD: 完成的任務記錄到歷史."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="notification"
        )
        queue.enqueue(task)
        await queue.process_next()
        history = queue.get_history()
        assert len(history) == 1
        assert history[0].task_id == "t1"
        assert history[0].status == TaskStatus.COMPLETED

    def test_denied_in_history(self):
        """BDD: 被拒絕的任務記錄到歷史."""
        queue = AutonomousQueue()
        task = AutonomousTask(
            task_id="t1", source="test", action="delete"
        )
        queue.enqueue(task)
        history = queue.get_history()
        assert len(history) == 1
        assert history[0].status == TaskStatus.DENIED

    def test_history_limit(self):
        """BDD: 歷史上限."""
        queue = AutonomousQueue()
        for i in range(30):
            task = AutonomousTask(
                task_id=f"t{i}", source="test", action="delete"
            )
            queue.enqueue(task)
        history = queue.get_history(limit=10)
        assert len(history) == 10

    def test_cancelled_in_history(self):
        """BDD: 被取消的任務記錄到歷史."""
        queue = AutonomousQueue()
        for i in range(3):
            queue.enqueue(AutonomousTask(
                task_id=f"t{i}", source="test", action="notification"
            ))
        queue.emergency_stop()
        history = queue.get_history()
        assert len(history) == 3
        assert all(h.status == TaskStatus.CANCELLED for h in history)


# ═══════════════════════════════════════════
# Persistence Tests (§8)
# ═══════════════════════════════════════════


class TestPersistence:
    """持久化測試."""

    def test_save_and_load(self, tmp_path):
        """BDD: 儲存 + 載入往返."""
        path = str(tmp_path / "queue_state.json")

        q1 = AutonomousQueue(state_path=path)
        q1.enqueue(AutonomousTask(
            task_id="t1", source="test", action="notification"
        ))
        q1.enqueue(AutonomousTask(
            task_id="t2", source="test", action="data_modify"
        ))

        q2 = AutonomousQueue(state_path=path)
        assert q2.queue_size == 2

    def test_emergency_stop_persisted(self, tmp_path):
        """BDD: 緊急停止狀態持久化."""
        path = str(tmp_path / "queue_state.json")

        q1 = AutonomousQueue(state_path=path)
        q1.emergency_stop()

        q2 = AutonomousQueue(state_path=path)
        assert q2.is_stopped

    def test_no_state_path(self):
        """BDD: 無 state_path 不報錯."""
        queue = AutonomousQueue(state_path=None)
        queue.enqueue(AutonomousTask(
            task_id="t1", source="test", action="notification"
        ))

    def test_load_nonexistent(self, tmp_path):
        """BDD: 不存在的檔案不報錯."""
        path = str(tmp_path / "missing" / "state.json")
        queue = AutonomousQueue(state_path=path)
        assert queue.queue_size == 0


# ═══════════════════════════════════════════
# EventBus Integration Tests
# ═══════════════════════════════════════════


class TestEventBusIntegration:
    """EventBus 整合測試."""

    @pytest.mark.asyncio
    async def test_publishes_task_done(self):
        """BDD: 完成任務後發布 AUTONOMOUS_TASK_DONE."""
        bus = EventBus()
        received = []
        bus.subscribe(AUTONOMOUS_TASK_DONE, lambda d: received.append(d))

        queue = AutonomousQueue(event_bus=bus)
        queue.enqueue(AutonomousTask(
            task_id="t1", source="test", action="notification"
        ))
        await queue.process_next()

        assert len(received) == 1
        assert received[0]["task_id"] == "t1"
        assert received[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_no_event_on_failure(self):
        """BDD: 失敗任務不發布事件."""
        bus = EventBus()
        received = []
        bus.subscribe(AUTONOMOUS_TASK_DONE, lambda d: received.append(d))

        queue = AutonomousQueue(event_bus=bus)
        queue.register_executor(
            "notification", lambda p: (_ for _ in ()).throw(RuntimeError("fail"))
        )
        queue.enqueue(AutonomousTask(
            task_id="t1", source="test", action="notification"
        ))
        await queue.process_next()

        assert len(received) == 0


# ═══════════════════════════════════════════
# Waiting Confirm Query Tests
# ═══════════════════════════════════════════


class TestWaitingConfirm:
    """等待確認查詢測試."""

    def test_get_waiting_confirm(self):
        """BDD: 取得等待確認的任務."""
        queue = AutonomousQueue()
        queue.enqueue(AutonomousTask(
            task_id="t1", source="test", action="notification"
        ))
        queue.enqueue(AutonomousTask(
            task_id="t2", source="test", action="data_modify"
        ))
        waiting = queue.get_waiting_confirm()
        assert len(waiting) == 1
        assert waiting[0].task_id == "t2"
