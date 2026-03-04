"""Tests for WorkflowEngine — 工作流生命週期引擎.

依據 SELF_ITERATION BDD Spec 驗證：
- FourDScore 四維分數計算
- 6 階段 lifecycle 自動遷轉
- SQLite 持久化 + 冪等 CRUD
- 加權滾動平均 + 高原偵測
- EventBus 事件發布
"""

import json
import math
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from museon.core.event_bus import EventBus
from museon.workflow.models import (
    BIRTH_TO_GROWTH_SUCCESS,
    GROWTH_TO_MATURITY_AVG,
    GROWTH_TO_MATURITY_SUCCESS,
    LIFECYCLE_STAGES,
    LIFECYCLE_TO_LAYER,
    PLATEAU_MAX_AVG,
    PLATEAU_MAX_VARIANCE,
    PLATEAU_MIN_RUNS,
    ROLLING_WINDOW,
    ExecutionRecord,
    FourDScore,
    WorkflowRecord,
)
from museon.workflow.workflow_engine import WorkflowEngine


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════


@pytest.fixture
def tmp_workspace(tmp_path):
    """提供暫時 workspace 目錄."""
    return tmp_path


@pytest.fixture
def event_bus():
    """提供乾淨的 EventBus 實例."""
    return EventBus()


@pytest.fixture
def engine(tmp_workspace, event_bus):
    """提供 WorkflowEngine 實例（附 EventBus）."""
    return WorkflowEngine(workspace=tmp_workspace, event_bus=event_bus)


@pytest.fixture
def engine_no_bus(tmp_workspace):
    """提供 WorkflowEngine 實例（無 EventBus）."""
    return WorkflowEngine(workspace=tmp_workspace, event_bus=None)


class EventCollector:
    """輔助收集 EventBus 事件."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def __call__(self, data: Optional[Dict] = None):
        self.events.append(data or {})

    @property
    def count(self) -> int:
        return len(self.events)

    @property
    def last(self) -> Dict[str, Any]:
        return self.events[-1] if self.events else {}


# ═══════════════════════════════════════════
# TestFourDScore — 四維分數
# ═══════════════════════════════════════════


class TestFourDScore:
    """FourDScore 資料模型測試."""

    def test_default_composite(self):
        """預設分數的 composite: (5 * 5 * 5 * 4)^0.25."""
        s = FourDScore()
        expected = (5.0 * 5.0 * 5.0 * 4.0) ** 0.25
        assert abs(s.composite - expected) < 0.001

    def test_perfect_score(self):
        """滿分 composite: (10*10*10*10)^0.25 = 10."""
        s = FourDScore(speed=10, quality=10, alignment=10, leverage=10)
        assert abs(s.composite - 10.0) < 0.001

    def test_zero_score(self):
        """任一維度為 0，composite = 0."""
        s = FourDScore(speed=0, quality=5, alignment=5, leverage=5)
        assert s.composite == 0.0

    def test_negative_product(self):
        """負值也回傳 0."""
        s = FourDScore(speed=-1, quality=5, alignment=5, leverage=5)
        assert s.composite == 0.0

    def test_clamp_high(self):
        """clamp 將超過 10 的值限制在 10."""
        s = FourDScore(speed=15, quality=12, alignment=11, leverage=20)
        s.clamp()
        assert s.speed == 10.0
        assert s.quality == 10.0
        assert s.alignment == 10.0
        assert s.leverage == 10.0

    def test_clamp_low(self):
        """clamp 將低於 0 的值限制在 0."""
        s = FourDScore(speed=-3, quality=-1, alignment=-5, leverage=-2)
        s.clamp()
        assert s.speed == 0.0
        assert s.quality == 0.0
        assert s.alignment == 0.0
        assert s.leverage == 0.0

    def test_to_dict_roundtrip(self):
        """to_dict → from_dict 往返一致."""
        original = FourDScore(speed=7.5, quality=8.0, alignment=6.5, leverage=5.5)
        d = original.to_dict()
        restored = FourDScore.from_dict(d)
        assert abs(restored.speed - original.speed) < 0.001
        assert abs(restored.quality - original.quality) < 0.001
        assert abs(restored.composite - original.composite) < 0.001

    def test_from_dict_defaults(self):
        """from_dict 空 dict 使用預設值."""
        s = FourDScore.from_dict({})
        assert s.speed == 5.0
        assert s.leverage == 4.0


# ═══════════════════════════════════════════
# TestWorkflowRecord — 工作流記錄
# ═══════════════════════════════════════════


class TestWorkflowRecord:
    """WorkflowRecord 資料模型測試."""

    def test_default_lifecycle(self):
        """預設 lifecycle = birth."""
        r = WorkflowRecord()
        assert r.lifecycle == "birth"

    def test_memory_layer_mapping(self):
        """各 lifecycle 對應正確的 memory_layer."""
        for stage, layer in LIFECYCLE_TO_LAYER.items():
            r = WorkflowRecord(lifecycle=stage)
            assert r.memory_layer == layer, f"{stage} → {layer}"

    def test_unknown_lifecycle_fallback(self):
        """未知 lifecycle 回傳 L0_buffer."""
        r = WorkflowRecord(lifecycle="unknown_stage")
        assert r.memory_layer == "L0_buffer"

    def test_to_dict_contains_all_fields(self):
        """to_dict 包含所有必要欄位."""
        r = WorkflowRecord(
            workflow_id="wf-1",
            user_id="u-1",
            name="test",
            lifecycle="growth",
            tags=["tag1"],
        )
        d = r.to_dict()
        assert d["workflow_id"] == "wf-1"
        assert d["lifecycle"] == "growth"
        assert d["memory_layer"] == "L2_ep"
        assert d["tags"] == ["tag1"]


# ═══════════════════════════════════════════
# TestExecutionRecord — 執行記錄
# ═══════════════════════════════════════════


class TestExecutionRecord:
    """ExecutionRecord 資料模型測試."""

    def test_score_property(self):
        """score property 回傳正確的 FourDScore."""
        er = ExecutionRecord(speed=7, quality=8, alignment=6, leverage=5)
        s = er.score
        assert s.speed == 7
        assert s.quality == 8
        assert abs(s.composite - (7 * 8 * 6 * 5) ** 0.25) < 0.001

    def test_to_dict(self):
        """to_dict 回傳完整欄位."""
        er = ExecutionRecord(
            execution_id="e-1",
            workflow_id="wf-1",
            outcome="failed",
        )
        d = er.to_dict()
        assert d["execution_id"] == "e-1"
        assert d["outcome"] == "failed"


# ═══════════════════════════════════════════
# TestLifecycleConstants — 生命週期常數
# ═══════════════════════════════════════════


class TestLifecycleConstants:
    """生命週期常數驗證."""

    def test_lifecycle_stages_count(self):
        """6 個生命週期階段."""
        assert len(LIFECYCLE_STAGES) == 6

    def test_lifecycle_order(self):
        """正確順序: birth → growth → ... → archived."""
        assert LIFECYCLE_STAGES[0] == "birth"
        assert LIFECYCLE_STAGES[-1] == "archived"

    def test_all_stages_mapped(self):
        """每個 stage 都有對應的 memory layer."""
        for stage in LIFECYCLE_STAGES:
            assert stage in LIFECYCLE_TO_LAYER

    def test_threshold_values(self):
        """閾值符合 BDD spec."""
        assert BIRTH_TO_GROWTH_SUCCESS == 3
        assert GROWTH_TO_MATURITY_SUCCESS == 8
        assert GROWTH_TO_MATURITY_AVG == 7.0
        assert PLATEAU_MIN_RUNS == 5
        assert PLATEAU_MAX_VARIANCE == 0.5
        assert PLATEAU_MAX_AVG == 7.0
        assert ROLLING_WINDOW == 5


# ═══════════════════════════════════════════
# TestSQLiteStorage — SQLite 持久化
# ═══════════════════════════════════════════


class TestSQLiteStorage:
    """SQLite 持久化測試."""

    def test_db_file_created(self, engine, tmp_workspace):
        """初始化後建立 DB 檔案."""
        # Trigger DB init by calling a method
        engine.get_or_create("user-1", "test-wf")
        db_path = tmp_workspace / "_system" / "wee" / "workflow_state.db"
        assert db_path.exists()

    def test_tables_exist(self, engine, tmp_workspace):
        """建立 workflows 和 executions 兩個表."""
        engine.get_or_create("user-1", "test-wf")
        db_path = tmp_workspace / "_system" / "wee" / "workflow_state.db"
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "workflows" in table_names
        assert "executions" in table_names
        conn.close()

    def test_indexes_exist(self, engine, tmp_workspace):
        """建立必要的索引."""
        engine.get_or_create("user-1", "test-wf")
        db_path = tmp_workspace / "_system" / "wee" / "workflow_state.db"
        conn = sqlite3.connect(str(db_path))
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = {i[0] for i in indexes}
        assert "idx_wf_user" in index_names
        assert "idx_wf_lifecycle" in index_names
        assert "idx_exec_wf" in index_names
        conn.close()

    def test_idempotent_get_or_create(self, engine):
        """同一 user+name 只建立一個工作流."""
        wf1 = engine.get_or_create("user-1", "writing")
        wf2 = engine.get_or_create("user-1", "writing")
        assert wf1.workflow_id == wf2.workflow_id
        assert wf1.name == wf2.name

    def test_different_name_creates_new(self, engine):
        """不同 name 建立不同工作流."""
        wf1 = engine.get_or_create("user-1", "writing")
        wf2 = engine.get_or_create("user-1", "coding")
        assert wf1.workflow_id != wf2.workflow_id

    def test_different_user_creates_new(self, engine):
        """不同 user 建立不同工作流."""
        wf1 = engine.get_or_create("user-1", "writing")
        wf2 = engine.get_or_create("user-2", "writing")
        assert wf1.workflow_id != wf2.workflow_id

    def test_get_workflow_by_id(self, engine):
        """透過 workflow_id 查詢."""
        wf = engine.get_or_create("user-1", "test")
        fetched = engine.get_workflow(wf.workflow_id)
        assert fetched is not None
        assert fetched.workflow_id == wf.workflow_id
        assert fetched.name == "test"

    def test_get_workflow_not_found(self, engine):
        """查詢不存在的工作流回傳 None."""
        result = engine.get_workflow("nonexistent-id")
        assert result is None

    def test_list_workflows_by_user(self, engine):
        """列出指定用戶的工作流."""
        engine.get_or_create("user-1", "wf-a")
        engine.get_or_create("user-1", "wf-b")
        engine.get_or_create("user-2", "wf-c")

        user1_wfs = engine.list_workflows("user-1")
        assert len(user1_wfs) == 2

        user2_wfs = engine.list_workflows("user-2")
        assert len(user2_wfs) == 1

    def test_list_workflows_by_lifecycle(self, engine):
        """按 lifecycle 過濾."""
        engine.get_or_create("user-1", "wf-a")
        engine.get_or_create("user-1", "wf-b")

        birth_wfs = engine.list_workflows("user-1", lifecycle="birth")
        assert len(birth_wfs) == 2

        growth_wfs = engine.list_workflows("user-1", lifecycle="growth")
        assert len(growth_wfs) == 0

    def test_tags_persisted(self, engine):
        """tags 正確持久化."""
        wf = engine.get_or_create("user-1", "tagged", tags=["ai", "coding"])
        fetched = engine.get_workflow(wf.workflow_id)
        assert fetched is not None
        assert fetched.tags == ["ai", "coding"]

    def test_new_workflow_defaults(self, engine):
        """新建工作流的預設值."""
        wf = engine.get_or_create("user-1", "new")
        assert wf.lifecycle == "birth"
        assert wf.success_count == 0
        assert wf.total_runs == 0
        assert wf.avg_composite == 0.0
        assert wf.variance == 0.0
        assert wf.baseline_composite is None
        assert wf.created_at != ""
        assert wf.updated_at != ""


# ═══════════════════════════════════════════
# TestRecordExecution — 執行記錄
# ═══════════════════════════════════════════


class TestRecordExecution:
    """record_execution 測試."""

    def test_basic_record(self, engine):
        """基本記錄執行."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=7, quality=8, alignment=6, leverage=5)
        record = engine.record_execution(wf.workflow_id, score)

        assert record is not None
        assert record.workflow_id == wf.workflow_id
        assert record.speed == 7
        assert record.quality == 8
        assert record.outcome == "success"

    def test_total_runs_incremented(self, engine):
        """total_runs 遞增."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()

        engine.record_execution(wf.workflow_id, score)
        engine.record_execution(wf.workflow_id, score)
        engine.record_execution(wf.workflow_id, score)

        updated = engine.get_workflow(wf.workflow_id)
        assert updated.total_runs == 3

    def test_success_count_tracks_only_success(self, engine):
        """success_count 只計算 success."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()

        engine.record_execution(wf.workflow_id, score, outcome="success")
        engine.record_execution(wf.workflow_id, score, outcome="failed")
        engine.record_execution(wf.workflow_id, score, outcome="success")
        engine.record_execution(wf.workflow_id, score, outcome="partial")

        updated = engine.get_workflow(wf.workflow_id)
        assert updated.total_runs == 4
        assert updated.success_count == 2

    def test_nonexistent_workflow_returns_none(self, engine):
        """記錄不存在的工作流回傳 None."""
        score = FourDScore()
        result = engine.record_execution("nonexistent", score)
        assert result is None

    def test_context_truncated(self, engine):
        """context 超過 500 字元會被截斷."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()
        long_context = "x" * 1000
        record = engine.record_execution(wf.workflow_id, score, context=long_context)
        assert len(record.context) == 500

    def test_get_recent_executions(self, engine):
        """取得最近 N 次執行記錄."""
        wf = engine.get_or_create("user-1", "test")

        for i in range(7):
            score = FourDScore(speed=float(i + 1))
            engine.record_execution(wf.workflow_id, score)

        recent = engine.get_recent_executions(wf.workflow_id, limit=5)
        assert len(recent) == 5
        # oldest → newest 順序
        assert recent[0].speed < recent[-1].speed

    def test_get_recent_executions_less_than_limit(self, engine):
        """不足 limit 筆回傳全部."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()
        engine.record_execution(wf.workflow_id, score)
        engine.record_execution(wf.workflow_id, score)

        recent = engine.get_recent_executions(wf.workflow_id, limit=5)
        assert len(recent) == 2


# ═══════════════════════════════════════════
# TestRollingStats — 加權滾動平均
# ═══════════════════════════════════════════


class TestRollingStats:
    """加權滾動平均 + 方差測試."""

    def test_single_execution_avg(self, engine):
        """單次執行的 avg = 該次 composite."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=8, quality=8, alignment=8, leverage=8)
        engine.record_execution(wf.workflow_id, score)

        updated = engine.get_workflow(wf.workflow_id)
        assert abs(updated.avg_composite - score.composite) < 0.01

    def test_weighted_average_newer_heavier(self, engine):
        """加權平均：近期分數權重較高."""
        wf = engine.get_or_create("user-1", "test")

        # 前幾筆低分、後幾筆高分
        low_score = FourDScore(speed=3, quality=3, alignment=3, leverage=3)
        high_score = FourDScore(speed=9, quality=9, alignment=9, leverage=9)

        engine.record_execution(wf.workflow_id, low_score)
        engine.record_execution(wf.workflow_id, low_score)
        engine.record_execution(wf.workflow_id, high_score)

        updated = engine.get_workflow(wf.workflow_id)
        # 加權平均應偏向高分（因為 newest 權重最高）
        simple_avg = (low_score.composite * 2 + high_score.composite) / 3
        # 加權: w=[1,2,3], total=6
        weighted_avg = (
            1 * low_score.composite + 2 * low_score.composite + 3 * high_score.composite
        ) / 6
        assert abs(updated.avg_composite - weighted_avg) < 0.01
        # 加權平均 > 簡單平均（因為高分的權重更高）
        assert updated.avg_composite > simple_avg

    def test_rolling_window_5(self, engine):
        """滾動視窗 = 5，只取最近 5 筆."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=5, quality=5, alignment=5, leverage=5)

        # 先灌 3 筆低分
        low = FourDScore(speed=2, quality=2, alignment=2, leverage=2)
        for _ in range(3):
            engine.record_execution(wf.workflow_id, low)

        # 再灌 5 筆高分（滾動視窗 = 5，低分應被淘汰）
        high = FourDScore(speed=9, quality=9, alignment=9, leverage=9)
        for _ in range(5):
            engine.record_execution(wf.workflow_id, high)

        updated = engine.get_workflow(wf.workflow_id)
        # 只剩 5 筆高分，加權平均 = 高分 composite
        assert abs(updated.avg_composite - high.composite) < 0.01

    def test_variance_same_scores(self, engine):
        """完全相同的分數 → variance ≈ 0."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=6, quality=6, alignment=6, leverage=6)

        for _ in range(5):
            engine.record_execution(wf.workflow_id, score)

        updated = engine.get_workflow(wf.workflow_id)
        assert updated.variance < 0.001

    def test_variance_diverse_scores(self, engine):
        """分散的分數 → variance > 0."""
        wf = engine.get_or_create("user-1", "test")

        scores = [
            FourDScore(speed=2, quality=2, alignment=2, leverage=2),
            FourDScore(speed=9, quality=9, alignment=9, leverage=9),
            FourDScore(speed=3, quality=3, alignment=3, leverage=3),
            FourDScore(speed=8, quality=8, alignment=8, leverage=8),
            FourDScore(speed=5, quality=5, alignment=5, leverage=5),
        ]
        for s in scores:
            engine.record_execution(wf.workflow_id, s)

        updated = engine.get_workflow(wf.workflow_id)
        assert updated.variance > 0.5


# ═══════════════════════════════════════════
# TestWorkflowLifecycle — 生命週期遷轉
# ═══════════════════════════════════════════


class TestWorkflowLifecycle:
    """自動 lifecycle 遷轉測試."""

    def test_birth_to_growth(self, engine):
        """birth → growth：success_count >= 3."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()

        for _ in range(BIRTH_TO_GROWTH_SUCCESS):
            engine.record_execution(wf.workflow_id, score, outcome="success")

        updated = engine.get_workflow(wf.workflow_id)
        assert updated.lifecycle == "growth"

    def test_birth_stays_with_failures(self, engine):
        """birth 階段：失敗不計入 success_count."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()

        # 2 success + 3 failed = 仍然 birth
        engine.record_execution(wf.workflow_id, score, outcome="success")
        engine.record_execution(wf.workflow_id, score, outcome="success")
        engine.record_execution(wf.workflow_id, score, outcome="failed")
        engine.record_execution(wf.workflow_id, score, outcome="failed")
        engine.record_execution(wf.workflow_id, score, outcome="failed")

        updated = engine.get_workflow(wf.workflow_id)
        assert updated.lifecycle == "birth"
        assert updated.success_count == 2

    def test_growth_to_maturity(self, engine):
        """growth → maturity：success_count >= 8 AND avg_composite >= 7.0."""
        wf = engine.get_or_create("user-1", "test")
        # 高分足以讓 avg >= 7.0
        high_score = FourDScore(speed=9, quality=9, alignment=9, leverage=9)

        # 灌足夠的高分 success（先過 birth→growth，再過 growth→maturity）
        for _ in range(GROWTH_TO_MATURITY_SUCCESS):
            engine.record_execution(wf.workflow_id, high_score, outcome="success")

        updated = engine.get_workflow(wf.workflow_id)
        assert updated.lifecycle == "maturity"
        assert updated.success_count >= GROWTH_TO_MATURITY_SUCCESS

    def test_growth_stays_low_avg(self, engine):
        """growth 階段：avg 不夠高不會升 maturity."""
        wf = engine.get_or_create("user-1", "test")
        low_score = FourDScore(speed=3, quality=3, alignment=3, leverage=3)

        # 10 筆低分 success → 過了 birth→growth 但 avg 不夠高
        for _ in range(10):
            engine.record_execution(wf.workflow_id, low_score, outcome="success")

        updated = engine.get_workflow(wf.workflow_id)
        # Should be growth (not maturity) because avg_composite < 7.0
        assert updated.lifecycle == "growth"
        assert updated.avg_composite < GROWTH_TO_MATURITY_AVG


# ═══════════════════════════════════════════
# TestPlateauDetection — 高原偵測
# ═══════════════════════════════════════════


class TestPlateauDetection:
    """高原偵測測試."""

    def test_plateau_low_variance_low_avg(self, engine):
        """低 variance + 低 avg → is_plateau = True."""
        wf = engine.get_or_create("user-1", "test")
        # 分數穩定但低（composite ≈ 5）
        score = FourDScore(speed=5, quality=5, alignment=5, leverage=5)

        for _ in range(PLATEAU_MIN_RUNS):
            engine.record_execution(wf.workflow_id, score, outcome="success")

        result = engine.check_plateau(wf.workflow_id)
        assert result["is_plateau"] is True
        assert result["variance"] < PLATEAU_MAX_VARIANCE
        assert result["avg"] < PLATEAU_MAX_AVG

    def test_not_plateau_high_avg(self, engine):
        """高分穩定（avg >= 7.0）→ NOT plateau."""
        wf = engine.get_or_create("user-1", "test")
        high_score = FourDScore(speed=9, quality=9, alignment=9, leverage=9)

        for _ in range(PLATEAU_MIN_RUNS + 3):
            engine.record_execution(wf.workflow_id, high_score, outcome="success")

        result = engine.check_plateau(wf.workflow_id)
        assert result["is_plateau"] is False
        assert result["avg"] >= PLATEAU_MAX_AVG

    def test_not_plateau_insufficient_runs(self, engine):
        """不足 5 次 → 不偵測高原."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=5, quality=5, alignment=5, leverage=5)

        for _ in range(PLATEAU_MIN_RUNS - 1):
            engine.record_execution(wf.workflow_id, score, outcome="success")

        result = engine.check_plateau(wf.workflow_id)
        assert result["is_plateau"] is False
        assert result["run_count"] < PLATEAU_MIN_RUNS

    def test_not_plateau_high_variance(self, engine):
        """高 variance → NOT plateau."""
        wf = engine.get_or_create("user-1", "test")

        # 交替高低分製造高 variance
        scores = [
            FourDScore(speed=2, quality=2, alignment=2, leverage=2),
            FourDScore(speed=8, quality=8, alignment=8, leverage=8),
            FourDScore(speed=2, quality=2, alignment=2, leverage=2),
            FourDScore(speed=8, quality=8, alignment=8, leverage=8),
            FourDScore(speed=2, quality=2, alignment=2, leverage=2),
        ]
        for s in scores:
            engine.record_execution(wf.workflow_id, s, outcome="success")

        result = engine.check_plateau(wf.workflow_id)
        assert result["is_plateau"] is False
        assert result["variance"] >= PLATEAU_MAX_VARIANCE

    def test_plateau_sets_lifecycle(self, engine):
        """偵測到高原 → lifecycle 自動遷轉為 plateau."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=5, quality=5, alignment=5, leverage=5)

        for _ in range(PLATEAU_MIN_RUNS):
            engine.record_execution(wf.workflow_id, score, outcome="success")

        engine.check_plateau(wf.workflow_id)
        updated = engine.get_workflow(wf.workflow_id)
        assert updated.lifecycle == "plateau"

    def test_plateau_nonexistent_wf(self, engine):
        """不存在的工作流 → 安全回傳."""
        result = engine.check_plateau("nonexistent")
        assert result["is_plateau"] is False
        assert result["run_count"] == 0

    def test_plateau_skip_if_already_evolution(self, engine):
        """已在 evolution 階段不再遷轉."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=5, quality=5, alignment=5, leverage=5)

        for _ in range(PLATEAU_MIN_RUNS):
            engine.record_execution(wf.workflow_id, score, outcome="success")

        # 手動遷轉到 evolution
        engine.mutate(wf.workflow_id)
        updated = engine.get_workflow(wf.workflow_id)
        assert updated.lifecycle == "evolution"

        # check_plateau 不應再遷轉回 plateau
        engine.check_plateau(wf.workflow_id)
        final = engine.get_workflow(wf.workflow_id)
        assert final.lifecycle == "evolution"


# ═══════════════════════════════════════════
# TestMutate — 突變
# ═══════════════════════════════════════════


class TestMutate:
    """mutate() 突變測試."""

    def test_mutate_lifecycle_to_evolution(self, engine):
        """mutate → lifecycle = 'evolution'."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=7, quality=7, alignment=7, leverage=7)
        engine.record_execution(wf.workflow_id, score)

        result = engine.mutate(wf.workflow_id)
        assert result is not None
        assert result.lifecycle == "evolution"

    def test_mutate_freezes_baseline(self, engine):
        """mutate 凍結當前 avg_composite 為 baseline."""
        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=7, quality=7, alignment=7, leverage=7)

        for _ in range(3):
            engine.record_execution(wf.workflow_id, score)

        before = engine.get_workflow(wf.workflow_id)
        assert before.baseline_composite is None

        result = engine.mutate(wf.workflow_id)
        assert result.baseline_composite is not None
        assert abs(result.baseline_composite - before.avg_composite) < 0.01

    def test_mutate_nonexistent(self, engine):
        """mutate 不存在的工作流 → None."""
        result = engine.mutate("nonexistent")
        assert result is None


# ═══════════════════════════════════════════
# TestProficiency — 用戶熟練度
# ═══════════════════════════════════════════


class TestProficiency:
    """get_proficiency 用戶熟練度測試."""

    def test_no_executions(self, engine):
        """無執行記錄 → 預設值."""
        result = engine.get_proficiency("user-1")
        assert result["total_executions"] == 0
        assert result["speed"] == 5.0
        assert result["leverage"] == 4.0

    def test_with_executions(self, engine):
        """有執行記錄 → 平均分數."""
        wf = engine.get_or_create("user-1", "test")
        score1 = FourDScore(speed=6, quality=8, alignment=7, leverage=5)
        score2 = FourDScore(speed=8, quality=6, alignment=5, leverage=7)

        engine.record_execution(wf.workflow_id, score1)
        engine.record_execution(wf.workflow_id, score2)

        result = engine.get_proficiency("user-1")
        assert result["total_executions"] == 2
        assert abs(result["speed"] - 7.0) < 0.01
        assert abs(result["quality"] - 7.0) < 0.01

    def test_excludes_archived(self, engine):
        """archived 工作流不計入熟練度."""
        wf = engine.get_or_create("user-1", "active")
        score = FourDScore(speed=8, quality=8, alignment=8, leverage=8)
        engine.record_execution(wf.workflow_id, score)

        wf2 = engine.get_or_create("user-1", "old")
        engine.record_execution(wf2.workflow_id, score)
        # 手動 archive
        conn = engine._get_conn()
        conn.execute(
            "UPDATE workflows SET lifecycle = 'archived' WHERE workflow_id = ?",
            (wf2.workflow_id,),
        )
        conn.commit()

        result = engine.get_proficiency("user-1")
        assert result["total_executions"] == 1


# ═══════════════════════════════════════════
# TestEventBus — 事件發布
# ═══════════════════════════════════════════


class TestEventBusIntegration:
    """EventBus 事件發布整合測試."""

    def test_wee_recorded_event(self, engine, event_bus):
        """record_execution → 發布 WEE_RECORDED."""
        collector = EventCollector()
        event_bus.subscribe("WEE_RECORDED", collector)

        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()
        engine.record_execution(wf.workflow_id, score)

        assert collector.count == 1
        assert collector.last["workflow_id"] == wf.workflow_id
        assert "composite" in collector.last

    def test_lifecycle_changed_event(self, engine, event_bus):
        """lifecycle 遷轉 → 發布 WEE_LIFECYCLE_CHANGED."""
        collector = EventCollector()
        event_bus.subscribe("WEE_LIFECYCLE_CHANGED", collector)

        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()

        # 觸發 birth → growth
        for _ in range(BIRTH_TO_GROWTH_SUCCESS):
            engine.record_execution(wf.workflow_id, score, outcome="success")

        assert collector.count >= 1
        assert collector.last["old_lifecycle"] == "birth"
        assert collector.last["new_lifecycle"] == "growth"

    def test_plateau_detected_event(self, engine, event_bus):
        """check_plateau 偵測到高原 → 發布 WEE_PLATEAU_DETECTED."""
        collector = EventCollector()
        event_bus.subscribe("WEE_PLATEAU_DETECTED", collector)

        wf = engine.get_or_create("user-1", "test")
        score = FourDScore(speed=5, quality=5, alignment=5, leverage=5)

        for _ in range(PLATEAU_MIN_RUNS):
            engine.record_execution(wf.workflow_id, score, outcome="success")

        engine.check_plateau(wf.workflow_id)

        assert collector.count >= 1
        assert "avg" in collector.last
        assert "variance" in collector.last

    def test_mutate_lifecycle_changed_event(self, engine, event_bus):
        """mutate → 發布 WEE_LIFECYCLE_CHANGED."""
        collector = EventCollector()
        event_bus.subscribe("WEE_LIFECYCLE_CHANGED", collector)

        wf = engine.get_or_create("user-1", "test")
        engine.mutate(wf.workflow_id)

        assert collector.count >= 1
        assert collector.last["new_lifecycle"] == "evolution"
        assert "strategy" in collector.last

    def test_no_event_without_bus(self, engine_no_bus):
        """無 EventBus 時不拋異常."""
        wf = engine_no_bus.get_or_create("user-1", "test")
        score = FourDScore()

        # 應正常執行，不拋異常
        record = engine_no_bus.record_execution(wf.workflow_id, score)
        assert record is not None

    def test_event_bus_error_graceful(self, engine):
        """EventBus 訂閱者拋異常 → 不影響引擎運作."""
        def bad_handler(data):
            raise RuntimeError("boom!")

        engine._event_bus.subscribe("WEE_RECORDED", bad_handler)

        wf = engine.get_or_create("user-1", "test")
        score = FourDScore()
        # 不應拋異常
        record = engine.record_execution(wf.workflow_id, score)
        assert record is not None


# ═══════════════════════════════════════════
# TestEdgeCases — 邊界情況
# ═══════════════════════════════════════════


class TestEdgeCases:
    """邊界情況測試."""

    def test_empty_tags(self, engine):
        """空 tags 不造成問題."""
        wf = engine.get_or_create("user-1", "test", tags=[])
        assert wf.tags == []

    def test_none_tags(self, engine):
        """None tags 預設為空列表."""
        wf = engine.get_or_create("user-1", "test", tags=None)
        assert wf.tags == []

    def test_unicode_name(self, engine):
        """Unicode 工作流名稱."""
        wf = engine.get_or_create("user-1", "寫作練習")
        assert wf.name == "寫作練習"
        fetched = engine.get_workflow(wf.workflow_id)
        assert fetched.name == "寫作練習"

    def test_unicode_tags(self, engine):
        """Unicode 標籤."""
        wf = engine.get_or_create("user-1", "test", tags=["人工智慧", "程式設計"])
        fetched = engine.get_workflow(wf.workflow_id)
        assert "人工智慧" in fetched.tags

    def test_multiple_engines_same_db(self, tmp_workspace, event_bus):
        """同一 DB 多個引擎實例正常運作."""
        e1 = WorkflowEngine(workspace=tmp_workspace, event_bus=event_bus)
        e2 = WorkflowEngine(workspace=tmp_workspace, event_bus=event_bus)

        wf = e1.get_or_create("user-1", "shared")
        score = FourDScore()
        e1.record_execution(wf.workflow_id, score)

        # e2 可以讀到同一筆資料
        fetched = e2.get_workflow(wf.workflow_id)
        assert fetched is not None
        assert fetched.total_runs == 1
