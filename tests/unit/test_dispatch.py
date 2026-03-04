"""Unit tests for dispatch.py — 資料結構 + 序列化 + 持久化."""

import json
import pytest
from pathlib import Path

from museon.agent.dispatch import (
    DispatchPlan,
    DispatchStatus,
    ExecutionMode,
    HandoffPackage,
    ResultPackage,
    TaskPackage,
    TaskStatus,
    dispatch_plan_to_dict,
    persist_dispatch_plan,
)


class TestEnums:
    """Enum 基本行為."""

    def test_dispatch_status_values(self):
        assert DispatchStatus.PLANNING.value == "planning"
        assert DispatchStatus.EXECUTING.value == "executing"
        assert DispatchStatus.SYNTHESIZING.value == "synthesizing"
        assert DispatchStatus.COMPLETED.value == "completed"
        assert DispatchStatus.FAILED.value == "failed"
        assert DispatchStatus.PARTIAL.value == "partial"

    def test_task_status_values(self):
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.RETRYING.value == "retrying"

    def test_execution_mode_values(self):
        assert ExecutionMode.SERIAL.value == "serial"
        assert ExecutionMode.PARALLEL.value == "parallel"
        assert ExecutionMode.MIXED.value == "mixed"

    def test_enums_are_str(self):
        """Enum 繼承 str，可直接用在 JSON."""
        assert isinstance(DispatchStatus.PLANNING, str)
        assert isinstance(TaskStatus.PENDING, str)
        assert isinstance(ExecutionMode.SERIAL, str)


class TestHandoffPackage:
    """HandoffPackage dataclass."""

    def test_create_minimal(self):
        hp = HandoffPackage(
            for_next_skill="brand-identity",
            compressed_context="品牌定位已確認：咖啡廳、文青風",
        )
        assert hp.for_next_skill == "brand-identity"
        assert hp.compressed_context == "品牌定位已確認：咖啡廳、文青風"
        assert hp.action_items_for_next == []
        assert hp.excluded_topics == []
        assert hp.user_implicit_preferences == []

    def test_create_full(self):
        hp = HandoffPackage(
            for_next_skill="storytelling-engine",
            compressed_context="品牌核心確定",
            action_items_for_next=["寫品牌故事"],
            excluded_topics=["政治", "宗教"],
            user_implicit_preferences=["文青風格", "不要太商業"],
        )
        assert len(hp.action_items_for_next) == 1
        assert len(hp.excluded_topics) == 2
        assert len(hp.user_implicit_preferences) == 2


class TestTaskPackage:
    """TaskPackage dataclass."""

    def test_create_with_defaults(self):
        tp = TaskPackage(
            task_id="dispatch_001_task_00",
            skill_name="brand-identity",
            skill_focus="品牌定位分析",
            skill_depth="standard",
        )
        assert tp.task_id == "dispatch_001_task_00"
        assert tp.model_preference == "haiku"
        assert tp.timeout_seconds == 300
        assert tp.input_data == {}
        assert tp.depends_on == []
        assert tp.execution_order == 0

    def test_create_full(self):
        tp = TaskPackage(
            task_id="dispatch_001_task_01",
            skill_name="storytelling-engine",
            skill_focus="品牌故事撰寫",
            skill_depth="deep",
            input_data={"user_request": "咖啡廳品牌行銷"},
            expected_output="品牌故事草稿",
            execution_order=1,
            depends_on=["dispatch_001_task_00"],
            model_preference="sonnet",
            timeout_seconds=600,
        )
        assert tp.model_preference == "sonnet"
        assert tp.depends_on == ["dispatch_001_task_00"]


class TestResultPackage:
    """ResultPackage dataclass."""

    def test_create_default(self):
        rp = ResultPackage(task_id="task_01")
        assert rp.status == TaskStatus.PENDING
        assert rp.result == {}
        assert rp.quality == {}
        assert rp.handoff_package is None
        assert rp.error_message is None

    def test_create_completed(self):
        rp = ResultPackage(
            task_id="task_01",
            status=TaskStatus.COMPLETED,
            result={"summary": "分析完成", "full_response": "..."},
            quality={"self_score": 0.85, "confidence": 0.9},
            execution_time_ms=3500,
        )
        assert rp.status == TaskStatus.COMPLETED
        assert rp.quality["self_score"] == 0.85

    def test_create_failed(self):
        rp = ResultPackage(
            task_id="task_01",
            status=TaskStatus.FAILED,
            error_message="API timeout",
        )
        assert rp.status == TaskStatus.FAILED
        assert rp.error_message == "API timeout"


class TestDispatchPlan:
    """DispatchPlan dataclass."""

    def test_create_minimal(self):
        plan = DispatchPlan(
            plan_id="dispatch_20260101_120000_abcdefgh",
            user_request="幫我做品牌行銷全案",
            session_id="session-123",
        )
        assert plan.status == DispatchStatus.PLANNING
        assert plan.execution_mode == ExecutionMode.SERIAL
        assert plan.tasks == []
        assert plan.results == []
        assert plan.synthesis_result is None

    def test_lifecycle(self):
        """模擬完整生命週期：PLANNING → EXECUTING → SYNTHESIZING → COMPLETED."""
        plan = DispatchPlan(
            plan_id="test_plan",
            user_request="test",
            session_id="sess",
        )
        assert plan.status == DispatchStatus.PLANNING

        plan.status = DispatchStatus.EXECUTING
        plan.tasks.append(TaskPackage(
            task_id="t1", skill_name="brand-identity",
            skill_focus="focus", skill_depth="standard",
        ))
        assert len(plan.tasks) == 1

        plan.results.append(ResultPackage(
            task_id="t1", status=TaskStatus.COMPLETED,
        ))
        plan.status = DispatchStatus.SYNTHESIZING

        plan.synthesis_result = "最終回覆"
        plan.status = DispatchStatus.COMPLETED
        assert plan.status == DispatchStatus.COMPLETED


class TestDispatchPlanToDict:
    """dispatch_plan_to_dict() 序列化."""

    def test_basic_serialization(self):
        plan = DispatchPlan(
            plan_id="test_001",
            user_request="test request",
            session_id="sess-001",
            created_at="2026-01-01T12:00:00",
        )
        data = dispatch_plan_to_dict(plan)

        assert data["plan_id"] == "test_001"
        assert data["status"] == "planning"
        assert data["execution_mode"] == "serial"
        assert isinstance(data["tasks"], list)
        assert isinstance(data["results"], list)

    def test_serialization_with_tasks_and_results(self):
        plan = DispatchPlan(
            plan_id="test_002",
            user_request="品牌全案",
            session_id="sess-002",
            status=DispatchStatus.COMPLETED,
        )
        plan.tasks.append(TaskPackage(
            task_id="t1", skill_name="brand-identity",
            skill_focus="定位", skill_depth="standard",
        ))
        plan.results.append(ResultPackage(
            task_id="t1", status=TaskStatus.COMPLETED,
            result={"summary": "done"},
        ))

        data = dispatch_plan_to_dict(plan)
        assert data["status"] == "completed"
        assert len(data["tasks"]) == 1
        assert len(data["results"]) == 1
        # result status should be string
        assert data["results"][0]["status"] == "completed"

    def test_json_serializable(self):
        """序列化結果可以直接 json.dumps."""
        plan = DispatchPlan(
            plan_id="json_test",
            user_request="test",
            session_id="sess",
            status=DispatchStatus.EXECUTING,
        )
        plan.tasks.append(TaskPackage(
            task_id="t1", skill_name="test",
            skill_focus="f", skill_depth="quick",
        ))
        data = dispatch_plan_to_dict(plan)
        json_str = json.dumps(data, ensure_ascii=False, default=str)
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["plan_id"] == "json_test"


class TestPersistDispatchPlan:
    """persist_dispatch_plan() 持久化."""

    def test_persist_active(self, tmp_path):
        plan = DispatchPlan(
            plan_id="persist_test_001",
            user_request="test",
            session_id="sess",
        )
        persist_dispatch_plan(plan, tmp_path)

        target = tmp_path / "dispatch" / "active" / "persist_test_001.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["plan_id"] == "persist_test_001"
        assert data["status"] == "planning"

    def test_persist_completed(self, tmp_path):
        plan = DispatchPlan(
            plan_id="persist_test_002",
            user_request="test",
            session_id="sess",
            status=DispatchStatus.COMPLETED,
        )
        persist_dispatch_plan(plan, tmp_path, completed=True)

        target = tmp_path / "dispatch" / "completed" / "persist_test_002.json"
        assert target.exists()

    def test_persist_failed(self, tmp_path):
        plan = DispatchPlan(
            plan_id="persist_test_003",
            user_request="test",
            session_id="sess",
            status=DispatchStatus.FAILED,
            error_message="test error",
        )
        persist_dispatch_plan(plan, tmp_path, failed=True)

        target = tmp_path / "dispatch" / "failed" / "persist_test_003.json"
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["error_message"] == "test error"

    def test_completed_removes_active(self, tmp_path):
        """完成時應從 active/ 移除."""
        plan = DispatchPlan(
            plan_id="lifecycle_001",
            user_request="test",
            session_id="sess",
        )
        # 先存到 active
        persist_dispatch_plan(plan, tmp_path)
        active_path = tmp_path / "dispatch" / "active" / "lifecycle_001.json"
        assert active_path.exists()

        # 再標記完成
        plan.status = DispatchStatus.COMPLETED
        persist_dispatch_plan(plan, tmp_path, completed=True)

        # active 應被刪除
        assert not active_path.exists()
        # completed 應存在
        completed_path = tmp_path / "dispatch" / "completed" / "lifecycle_001.json"
        assert completed_path.exists()

    def test_failed_removes_active(self, tmp_path):
        """失敗時也應從 active/ 移除."""
        plan = DispatchPlan(
            plan_id="lifecycle_002",
            user_request="test",
            session_id="sess",
        )
        persist_dispatch_plan(plan, tmp_path)
        active_path = tmp_path / "dispatch" / "active" / "lifecycle_002.json"
        assert active_path.exists()

        plan.status = DispatchStatus.FAILED
        persist_dispatch_plan(plan, tmp_path, failed=True)

        assert not active_path.exists()
        failed_path = tmp_path / "dispatch" / "failed" / "lifecycle_002.json"
        assert failed_path.exists()

    def test_persist_creates_directories(self, tmp_path):
        """自動建立不存在的目錄."""
        plan = DispatchPlan(
            plan_id="dir_test",
            user_request="test",
            session_id="sess",
        )
        nested = tmp_path / "deep" / "nested"
        persist_dispatch_plan(plan, nested)

        target = nested / "dispatch" / "active" / "dir_test.json"
        assert target.exists()


# ═══════════════════════════════════════════
# Phase B: DAG Execution
# ═══════════════════════════════════════════


class TestBuildExecutionLayers:
    """build_execution_layers() — DAG 分層."""

    def test_empty_tasks(self):
        from museon.agent.dispatch import build_execution_layers
        assert build_execution_layers([]) == []

    def test_no_dependencies_single_layer(self):
        from museon.agent.dispatch import build_execution_layers
        tasks = [
            TaskPackage(task_id="t1", skill_name="a", skill_focus="f", skill_depth="standard"),
            TaskPackage(task_id="t2", skill_name="b", skill_focus="f", skill_depth="standard"),
            TaskPackage(task_id="t3", skill_name="c", skill_focus="f", skill_depth="standard"),
        ]
        layers = build_execution_layers(tasks)
        assert len(layers) == 1
        assert len(layers[0]) == 3

    def test_serial_chain(self):
        from museon.agent.dispatch import build_execution_layers
        tasks = [
            TaskPackage(task_id="t1", skill_name="a", skill_focus="f", skill_depth="standard"),
            TaskPackage(task_id="t2", skill_name="b", skill_focus="f", skill_depth="standard", depends_on=["t1"]),
            TaskPackage(task_id="t3", skill_name="c", skill_focus="f", skill_depth="standard", depends_on=["t2"]),
        ]
        layers = build_execution_layers(tasks)
        assert len(layers) == 3
        assert [layers[0][0].task_id] == ["t1"]
        assert [layers[1][0].task_id] == ["t2"]
        assert [layers[2][0].task_id] == ["t3"]

    def test_diamond_dag(self):
        """A → B,C → D (diamond shape)."""
        from museon.agent.dispatch import build_execution_layers
        tasks = [
            TaskPackage(task_id="A", skill_name="a", skill_focus="f", skill_depth="standard"),
            TaskPackage(task_id="B", skill_name="b", skill_focus="f", skill_depth="standard", depends_on=["A"]),
            TaskPackage(task_id="C", skill_name="c", skill_focus="f", skill_depth="standard", depends_on=["A"]),
            TaskPackage(task_id="D", skill_name="d", skill_focus="f", skill_depth="standard", depends_on=["B", "C"]),
        ]
        layers = build_execution_layers(tasks)
        assert len(layers) == 3
        assert layers[0][0].task_id == "A"
        layer1_ids = sorted(t.task_id for t in layers[1])
        assert layer1_ids == ["B", "C"]
        assert layers[2][0].task_id == "D"

    def test_circular_dep_forced(self):
        """Circular dependency → forced into last layer."""
        from museon.agent.dispatch import build_execution_layers
        tasks = [
            TaskPackage(task_id="t1", skill_name="a", skill_focus="f", skill_depth="standard", depends_on=["t2"]),
            TaskPackage(task_id="t2", skill_name="b", skill_focus="f", skill_depth="standard", depends_on=["t1"]),
        ]
        layers = build_execution_layers(tasks)
        # Should still produce layers (forced)
        assert len(layers) >= 1
        total = sum(len(layer) for layer in layers)
        assert total == 2


class TestDetermineExecutionMode:
    """determine_execution_mode() — 模式判定."""

    def test_empty(self):
        from museon.agent.dispatch import determine_execution_mode
        assert determine_execution_mode([]) == ExecutionMode.SERIAL

    def test_single_task(self):
        from museon.agent.dispatch import determine_execution_mode
        tasks = [TaskPackage(task_id="t1", skill_name="a", skill_focus="f", skill_depth="standard")]
        assert determine_execution_mode(tasks) == ExecutionMode.SERIAL

    def test_no_deps_parallel(self):
        from museon.agent.dispatch import determine_execution_mode
        tasks = [
            TaskPackage(task_id="t1", skill_name="a", skill_focus="f", skill_depth="standard"),
            TaskPackage(task_id="t2", skill_name="b", skill_focus="f", skill_depth="standard"),
        ]
        assert determine_execution_mode(tasks) == ExecutionMode.PARALLEL

    def test_pure_serial(self):
        from museon.agent.dispatch import determine_execution_mode
        tasks = [
            TaskPackage(task_id="t1", skill_name="a", skill_focus="f", skill_depth="standard"),
            TaskPackage(task_id="t2", skill_name="b", skill_focus="f", skill_depth="standard", depends_on=["t1"]),
            TaskPackage(task_id="t3", skill_name="c", skill_focus="f", skill_depth="standard", depends_on=["t2"]),
        ]
        assert determine_execution_mode(tasks) == ExecutionMode.SERIAL

    def test_mixed_mode(self):
        from museon.agent.dispatch import determine_execution_mode
        tasks = [
            TaskPackage(task_id="t1", skill_name="a", skill_focus="f", skill_depth="standard"),
            TaskPackage(task_id="t2", skill_name="b", skill_focus="f", skill_depth="standard"),
            TaskPackage(task_id="t3", skill_name="c", skill_focus="f", skill_depth="standard", depends_on=["t1", "t2"]),
        ]
        assert determine_execution_mode(tasks) == ExecutionMode.MIXED


# ═══════════════════════════════════════════
# Phase B: Recovery
# ═══════════════════════════════════════════


class TestRecoverActivePlans:
    """recover_active_plans() — 重啟恢復."""

    def test_no_active_dir(self, tmp_path):
        from museon.agent.dispatch import recover_active_plans
        assert recover_active_plans(tmp_path) == 0

    def test_recover_single_plan(self, tmp_path):
        from museon.agent.dispatch import recover_active_plans

        active_dir = tmp_path / "dispatch" / "active"
        active_dir.mkdir(parents=True)
        plan_data = {
            "plan_id": "test_plan",
            "status": "executing",
            "user_request": "test",
        }
        (active_dir / "test_plan.json").write_text(
            json.dumps(plan_data), encoding="utf-8",
        )

        count = recover_active_plans(tmp_path)
        assert count == 1
        assert not (active_dir / "test_plan.json").exists()

        failed_dir = tmp_path / "dispatch" / "failed"
        assert (failed_dir / "test_plan.json").exists()
        recovered = json.loads((failed_dir / "test_plan.json").read_text())
        assert recovered["status"] == "failed"
        assert "restart" in recovered["error_message"].lower()

    def test_recover_multiple_plans(self, tmp_path):
        from museon.agent.dispatch import recover_active_plans

        active_dir = tmp_path / "dispatch" / "active"
        active_dir.mkdir(parents=True)
        for i in range(3):
            (active_dir / f"plan_{i}.json").write_text(
                json.dumps({"plan_id": f"plan_{i}", "status": "executing"}),
                encoding="utf-8",
            )

        count = recover_active_plans(tmp_path)
        assert count == 3
        assert len(list(active_dir.glob("*.json"))) == 0
        failed_dir = tmp_path / "dispatch" / "failed"
        assert len(list(failed_dir.glob("*.json"))) == 3

    def test_preserve_existing_error_message(self, tmp_path):
        from museon.agent.dispatch import recover_active_plans

        active_dir = tmp_path / "dispatch" / "active"
        active_dir.mkdir(parents=True)
        (active_dir / "plan_x.json").write_text(
            json.dumps({
                "plan_id": "plan_x",
                "status": "executing",
                "error_message": "Worker 2 timeout",
            }),
            encoding="utf-8",
        )

        recover_active_plans(tmp_path)
        failed = json.loads(
            (tmp_path / "dispatch" / "failed" / "plan_x.json").read_text()
        )
        assert failed["error_message"] == "Worker 2 timeout"
