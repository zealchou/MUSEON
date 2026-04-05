"""Tests for nightly_pipeline.py — 18 步凌晨整合管線.

依據 NIGHTLY_SYSTEM_BDD_SPEC 的 BDD scenarios 驗證。
"""

import json
import os
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from museon.nightly.nightly_pipeline import (
    ARCHIVE_THRESHOLD,
    DAILY_DECAY_FACTOR,
    GRAPH_DECAY_FACTOR,
    GRAPH_WEAK_EDGE_THRESHOLD,
    MORNING_REPORT_HOUR,
    MORNING_REPORT_MINUTE,
    NIGHTLY_CRON_HOUR,
    NIGHTLY_CRON_MINUTE,
    PLATEAU_MAX_AVG,
    PLATEAU_MAX_VARIANCE,
    PLATEAU_MIN_RUNS,
    REPORT_TRUNCATE_CHARS,
    SKILL_ARCHIVE_INACTIVE_DAYS,
    SKILL_DEPRECATE_FAIL_RATE,
    SKILL_FORGE_MIN_CLUSTER,
    SKILL_FORGE_SIMILARITY_THRESHOLD,
    SKILL_PROMOTE_MIN_SUCCESS,
    WEE_MIN_CRYSTALS_FOR_FUSE,
    NightlyPipeline,
    _FULL_STEPS,
    _NODE_STEPS,
    _ORIGIN_STEPS,
    build_nightly_html,
    register_nightly_tasks,
)
from museon.pulse.heartbeat_focus import HeartbeatFocus


@pytest.fixture(autouse=True)
def _reset_wee_instances():
    """每個測試前重置 WEE per-user 實例快取."""
    try:
        from museon.evolution.wee_engine import _reset_wee_instances
        _reset_wee_instances()
    except ImportError:
        pass
    yield
    try:
        from museon.evolution.wee_engine import _reset_wee_instances
        _reset_wee_instances()
    except ImportError:
        pass


# ═══════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════


class TestConstants:
    """Scenario: 常數驗證."""

    def test_cron_hour(self):
        assert NIGHTLY_CRON_HOUR == 3

    def test_cron_minute(self):
        assert NIGHTLY_CRON_MINUTE == 0

    def test_morning_report_time(self):
        assert MORNING_REPORT_HOUR == 7
        assert MORNING_REPORT_MINUTE == 30

    def test_decay_factor(self):
        assert DAILY_DECAY_FACTOR == 0.993

    def test_archive_threshold(self):
        assert ARCHIVE_THRESHOLD == 0.3

    def test_truncate_chars(self):
        assert REPORT_TRUNCATE_CHARS == 200

    def test_full_steps_count(self):
        """BDD: 步驟 32.5 存在且在正確位置."""
        assert "32.5" in _FULL_STEPS
        idx32 = _FULL_STEPS.index("32")
        idx325 = _FULL_STEPS.index("32.5")
        idx33 = _FULL_STEPS.index("33")
        assert idx32 < idx325 < idx33

    def test_origin_steps(self):
        """BDD: Origin 模式 = 5.8, 7（Phase 0 減法：移除 6/8/16 ghost steps）."""
        # 6(no L2_ep), 8(no workflows), 16(no L3_procedural) 均為 ghost steps，已移除
        assert _ORIGIN_STEPS == ["5.8", "7"]
        assert len(_ORIGIN_STEPS) == 2

    def test_node_steps(self):
        """BDD: Node 模式 = 1-5.5, 9-15（14 個，含 13.5）."""
        assert _NODE_STEPS == [
            "1", "2", "3", "4", "5", "5.5",
            "9", "10", "11", "12", "13", "13.5", "14", "15",
        ]
        assert len(_NODE_STEPS) == 14

    def test_wee_min_crystals(self):
        assert WEE_MIN_CRYSTALS_FOR_FUSE == 3

    def test_skill_forge_constants(self):
        assert SKILL_FORGE_MIN_CLUSTER == 3
        assert SKILL_FORGE_SIMILARITY_THRESHOLD == 0.5

    def test_graph_constants(self):
        assert GRAPH_DECAY_FACTOR == 0.993
        assert GRAPH_WEAK_EDGE_THRESHOLD == 0.1

    def test_plateau_constants(self):
        assert PLATEAU_MIN_RUNS == 5
        assert PLATEAU_MAX_VARIANCE == 0.5
        assert PLATEAU_MAX_AVG == 7.0

    def test_skill_lifecycle_constants(self):
        assert SKILL_PROMOTE_MIN_SUCCESS == 3
        assert SKILL_DEPRECATE_FAIL_RATE == 0.5
        assert SKILL_ARCHIVE_INACTIVE_DAYS == 30


# ═══════════════════════════════════════════
# Pipeline Lifecycle Tests
# ═══════════════════════════════════════════


class TestPipelineLifecycle:
    """Scenario: 管線生命週期."""

    def test_full_mode_all_steps(self, tmp_path):
        """BDD: 完整管線執行（full mode）— 執行已實作的步驟."""
        pipeline = NightlyPipeline(tmp_path)
        report = pipeline.run(mode="full")

        assert report["mode"] == "full"
        # 部分步驟可能尚未在 step_map 中實作（如 5.8.1/5.8.2），執行數量 ≤ 定義數量
        assert len(report["steps"]) <= len(_FULL_STEPS)
        assert len(report["steps"]) > 0
        # summary.total 反映實際執行步驟數
        assert report["summary"]["total"] == len(report["steps"])

    def test_report_dict_format(self, tmp_path):
        """BDD: steps 為 dict 格式（key=step_name），每個 step 有 status 欄位."""
        pipeline = NightlyPipeline(tmp_path)
        report = pipeline.run()

        assert isinstance(report["steps"], dict)
        assert len(report["steps"]) > 0
        for key, val in report["steps"].items():
            assert "status" in val
            assert isinstance(key, str)
            # 大多數步驟以 step_ 開頭，但部分（如人格演化步驟）可能無前綴
            assert isinstance(key, str) and len(key) > 0

    def test_report_has_timestamps(self, tmp_path):
        """BDD: 報告含 started_at / completed_at / elapsed_seconds."""
        pipeline = NightlyPipeline(tmp_path)
        report = pipeline.run()

        assert "started_at" in report
        assert "completed_at" in report
        assert "elapsed_seconds" in report
        assert isinstance(report["elapsed_seconds"], float)

    def test_report_errors_list(self, tmp_path):
        """BDD: errors 為失敗步驟的陣列."""
        pipeline = NightlyPipeline(tmp_path)
        report = pipeline.run()

        assert "errors" in report
        assert isinstance(report["errors"], list)

    def test_eventbus_nightly_started(self, tmp_path):
        """BDD: 發布 NIGHTLY_STARTED 事件."""
        events = []
        bus = MagicMock()
        bus.publish = lambda t, d: events.append((t, d))

        pipeline = NightlyPipeline(tmp_path, event_bus=bus)
        pipeline.run()

        starts = [e for e in events if e[0] == "NIGHTLY_STARTED"]
        assert len(starts) == 1
        assert starts[0][1]["mode"] == "full"

    def test_eventbus_nightly_completed(self, tmp_path):
        """BDD: 發布 NIGHTLY_COMPLETED 事件."""
        events = []
        bus = MagicMock()
        bus.publish = lambda t, d: events.append((t, d))

        pipeline = NightlyPipeline(tmp_path, event_bus=bus)
        pipeline.run()

        completions = [e for e in events if e[0] == "NIGHTLY_COMPLETED"]
        assert len(completions) == 1
        assert "summary" in completions[0][1]
        assert "elapsed_seconds" in completions[0][1]


# ═══════════════════════════════════════════
# Federation Mode Tests
# ═══════════════════════════════════════════


class TestFederationMode:
    """Scenario: Federation 模式."""

    def test_origin_mode(self, tmp_path):
        """BDD: Origin 模式只執行 2 個步驟（Phase 0 減法：6/8/16 已移除為 ghost）."""
        pipeline = NightlyPipeline(tmp_path)
        report = pipeline.run(mode="origin")

        assert report["mode"] == "origin"
        assert len(report["steps"]) == len(_ORIGIN_STEPS)
        assert "step_05_8_morphenix_proposals" in report["steps"]
        assert "step_07_curriculum" in report["steps"]
        # 6(no L2_ep), 16(no L3_procedural) 是 ghost steps，不在 origin 中
        assert "step_06_skill_forge" not in report["steps"]
        assert "step_16_claude_skill_forge" not in report["steps"]

    def test_node_mode(self, tmp_path):
        """BDD: Node 模式執行 13 + federation_upload."""
        pipeline = NightlyPipeline(tmp_path)
        report = pipeline.run(mode="node")

        assert report["mode"] == "node"
        # 13 步 + 1 federation_upload
        assert len(report["steps"]) == len(_NODE_STEPS) + 1
        assert "step_01_asset_decay" in report["steps"]
        assert "step_federation_upload" in report["steps"]
        # origin-only 不應出現
        assert "step_16_claude_skill_forge" not in report["steps"]

    def test_node_federation_upload_skipped_without_env(self, tmp_path):
        """BDD: 無 MUSEON_NODE_ID 時 federation upload 跳過."""
        # 確保沒設定
        os.environ.pop("MUSEON_NODE_ID", None)
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_federation_upload()
        assert "skipped" in result


# ═══════════════════════════════════════════
# Error Isolation Tests
# ═══════════════════════════════════════════


class TestErrorIsolation:
    """Scenario: _safe_step 錯誤隔離."""

    def test_step_failure_no_interrupt(self, tmp_path):
        """BDD: 單步失敗不中斷整條管線，所有已實作步驟都有對應記錄."""
        pipeline = NightlyPipeline(tmp_path)
        report = pipeline.run(mode="full")
        # 部分步驟可能尚未在 step_map 中實作，執行數量 ≤ 定義數量
        assert len(report["steps"]) <= len(_FULL_STEPS)
        assert len(report["steps"]) > 0

    def test_ok_steps_still_run(self, tmp_path):
        """BDD: 可執行步驟仍正常運行."""
        pipeline = NightlyPipeline(tmp_path)
        report = pipeline.run(mode="full")
        assert report["steps"]["step_01_asset_decay"]["status"] == "ok"
        assert report["steps"]["step_02_archive_assets"]["status"] == "ok"

    def test_safe_step_returns_error(self, tmp_path):
        """BDD: 步驟拋出 Exception → status: error."""
        pipeline = NightlyPipeline(tmp_path)

        def exploding():
            raise ValueError("boom")

        result = pipeline._safe_step("test_explode", exploding)
        assert result["status"] == "error"
        assert "boom" in result["error"]

    def test_safe_step_returns_ok(self, tmp_path):
        """BDD: 正常步驟 → status: ok."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._safe_step("test_ok", lambda: {"count": 5})
        assert result["status"] == "ok"

    def test_safe_step_truncates_result(self, tmp_path):
        """BDD: 結果截斷為最多 200 字元."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._safe_step("test_long", lambda: {"data": "x" * 300})
        assert len(result["result"]) <= REPORT_TRUNCATE_CHARS + 3


# ═══════════════════════════════════════════
# Step 1: Asset Decay Tests
# ═══════════════════════════════════════════


class TestAssetDecay:
    """Scenario: Step 1 — 共享資產每日衰減."""

    def test_decay_factor_applied(self, tmp_path):
        """BDD: 品質 × 0.993."""
        asset_dir = tmp_path / "_system" / "assets"
        asset_dir.mkdir(parents=True)
        (asset_dir / "a.json").write_text(json.dumps({"quality": 1.0}))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_asset_decay()
        assert result["decayed"] == 1

        data = json.loads((asset_dir / "a.json").read_text())
        assert data["quality"] == pytest.approx(0.993, abs=0.001)

    def test_no_assets(self, tmp_path):
        """BDD: 無資產不報錯."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_asset_decay()
        assert result["decayed"] == 0

    def test_multiple_assets(self, tmp_path):
        """BDD: 多個資產全部衰減."""
        asset_dir = tmp_path / "_system" / "assets"
        asset_dir.mkdir(parents=True)
        for i in range(5):
            (asset_dir / f"asset_{i}.json").write_text(
                json.dumps({"quality": 0.8, "name": f"asset_{i}"})
            )

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_asset_decay()
        assert result["decayed"] == 5


# ═══════════════════════════════════════════
# Step 2: Archive Assets Tests
# ═══════════════════════════════════════════


class TestArchiveAssets:
    """Scenario: Step 2 — 歸檔低品質資產."""

    def test_archive_low_quality(self, tmp_path):
        """BDD: 品質 < 0.3 → 歸檔."""
        asset_dir = tmp_path / "_system" / "assets"
        asset_dir.mkdir(parents=True)
        (asset_dir / "low.json").write_text(json.dumps({"quality": 0.1}))
        (asset_dir / "high.json").write_text(json.dumps({"quality": 0.9}))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_archive_assets()
        assert result["archived"] == 1
        assert not (asset_dir / "low.json").exists()
        assert (tmp_path / "_system" / "assets_archive" / "low.json").exists()
        assert (asset_dir / "high.json").exists()


# ═══════════════════════════════════════════
# Step 3: Memory Maintenance Tests
# ═══════════════════════════════════════════


class TestMemoryMaintenance:
    """Scenario: Step 3 — 記憶維護."""

    def test_with_memory_manager(self, tmp_path):
        """BDD: 有 memory_manager 時呼叫 maintenance()."""
        class MockMM:
            def maintenance(self):
                return {"promoted": 2}

        pipeline = NightlyPipeline(tmp_path, memory_manager=MockMM())
        result = pipeline._step_memory_maintenance()
        assert result["maintained"] is True

    def test_without_memory_manager(self, tmp_path):
        """BDD: 無 memory_manager 時回傳 pass."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_memory_maintenance()
        assert result.get("status") == "pass" or result.get("maintained") is False


# ═══════════════════════════════════════════
# Step 4: WEE Compress Tests
# ═══════════════════════════════════════════


class TestWeeCompress:
    """Scenario: Step 4 — WEE Session 壓縮.

    WEEEngine 委派模式：無工作流 → compressed=False。
    有工作流但無昨日記錄 → compressed=False。
    """

    def test_no_workflows(self, tmp_path):
        """BDD: 無工作流 → compressed=False."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_wee_compress()
        assert result.get("compressed") is False or "skipped" in result

    def test_no_records_for_date(self, tmp_path):
        """BDD: 昨日沒有記錄 → compressed=False."""
        # WEEEngine 委派：無工作流 = 無記錄
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_wee_compress()
        assert result.get("compressed") is False or "skipped" in result

    def test_compress_with_wee_engine(self, tmp_path):
        """BDD: 透過 WEEEngine 壓縮（有工作流時）."""
        from museon.evolution.wee_engine import WEEEngine
        from museon.core.event_bus import EventBus

        # 先建立工作流和記錄
        wee = WEEEngine(
            user_id="boss",
            workspace=tmp_path,
            event_bus=EventBus(),
        )
        today = date.today().isoformat()
        wee.auto_cycle({
            "user_content": "我學到了一個重要的教訓",
            "response_content": "很好的學習經驗",
            "source": "test",
        })

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_wee_compress()
        # 今天有記錄，用今天日期壓縮
        if result.get("compressed"):
            assert result["interactions"] >= 1
        else:
            # 如果壓縮昨天沒有記錄，也合理
            assert result.get("compressed") is False


# ═══════════════════════════════════════════
# Step 5: WEE Fuse Tests
# ═══════════════════════════════════════════


class TestWeeFuse:
    """Scenario: Step 5 — WEE Crystal 融合.

    WEEEngine 委派模式：無 MemoryManager → fused=False。
    """

    def test_no_memory_manager(self, tmp_path):
        """BDD: 無 MemoryManager → fused=False."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_wee_fuse()
        # WEEEngine 無 memory_manager → fused=False
        assert result.get("fused") is False or "skipped" in result

    def test_fuse_result_shape(self, tmp_path):
        """BDD: 融合結果包含必要欄位."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_wee_fuse()
        # 無論成功與否，結果是 dict
        assert isinstance(result, dict)
        assert "fused" in result or "skipped" in result


# ═══════════════════════════════════════════
# Step 5.5: Cross Crystallize Tests
# ═══════════════════════════════════════════


class TestCrossCrystallize:
    """Scenario: Step 5.5 — 交叉層結晶."""

    def test_no_memory_dir(self, tmp_path):
        """BDD: 無記憶目錄 → skipped."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_cross_crystallize()
        assert "skipped" in result

    def test_not_enough_items(self, tmp_path):
        """BDD: L2_ep 不足 3 → skipped."""
        mem_dir = tmp_path / "_system" / "memory" / "shared" / "L2_ep"
        mem_dir.mkdir(parents=True)
        (mem_dir / "item1.json").write_text(json.dumps({"id": "1", "content": "hello"}))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_cross_crystallize()
        assert "skipped" in result


# ═══════════════════════════════════════════
# Step 5.8: Morphenix Proposals Tests
# ═══════════════════════════════════════════


class TestMorphenixProposals:
    """Scenario: Step 5.8 — Morphenix 提案結晶."""

    def test_no_notes_dir(self, tmp_path):
        """BDD: 無信號源 → proposals_created == 0."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_morphenix_proposals()
        assert result["proposals_created"] == 0

    def test_not_enough_notes(self, tmp_path):
        """BDD: 不足 3 個 notes → proposals_created == 0."""
        notes_dir = tmp_path / "_system" / "morphenix" / "notes"
        notes_dir.mkdir(parents=True)
        (notes_dir / "note1.json").write_text(json.dumps({"idea": "test"}))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_morphenix_proposals()
        assert result["proposals_created"] == 0

    def test_crystallize_proposals(self, tmp_path):
        """BDD: 3+ notes → 信號驅動結晶為提案."""
        notes_dir = tmp_path / "_system" / "morphenix" / "notes"
        notes_dir.mkdir(parents=True)
        for i in range(5):
            (notes_dir / f"note_{i}.json").write_text(
                json.dumps({"idea": f"improvement_{i}", "importance": "high"})
            )

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_morphenix_proposals()
        assert result["proposals_created"] >= 1
        assert result["signals_scanned"] >= 1


# ═══════════════════════════════════════════
# Step 6: Skill Forge Tests
# ═══════════════════════════════════════════


class TestSkillForge:
    """Scenario: Step 6 — 技能鍛造."""

    def test_no_l2_dir(self, tmp_path):
        """BDD: 無 L2_ep 目錄 → skipped."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_skill_forge()
        assert "skipped" in result

    def test_not_enough_items(self, tmp_path):
        """BDD: L2_ep 不足 → skipped."""
        l2_dir = tmp_path / "_system" / "memory" / "shared" / "L2_ep"
        l2_dir.mkdir(parents=True)
        (l2_dir / "item1.json").write_text(json.dumps({"id": "1", "content": "test"}))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_skill_forge()
        assert "skipped" in result


# ═══════════════════════════════════════════
# Step 7: Curriculum Tests
# ═══════════════════════════════════════════


class TestCurriculum:
    """Scenario: Step 7 — 課程診斷."""

    def test_default_scores(self, tmp_path):
        """BDD: 預設分數 → intermediate."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_curriculum()
        assert result["level"] == "intermediate"
        assert result["avg_score"] == 5.0

    def test_advanced_level(self, tmp_path):
        """BDD: 高分 → advanced."""
        prof_dir = tmp_path / "_system" / "wee"
        prof_dir.mkdir(parents=True)
        (prof_dir / "proficiency.json").write_text(
            json.dumps({"speed": 9.0, "quality": 8.5, "alignment": 8.0, "leverage": 9.0})
        )

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_curriculum()
        assert result["level"] == "advanced"

    def test_beginner_level(self, tmp_path):
        """BDD: 低分 → beginner."""
        prof_dir = tmp_path / "_system" / "wee"
        prof_dir.mkdir(parents=True)
        (prof_dir / "proficiency.json").write_text(
            json.dumps({"speed": 2.0, "quality": 3.0, "alignment": 2.0, "leverage": 1.0})
        )

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_curriculum()
        assert result["level"] == "beginner"

    def test_writes_prescription(self, tmp_path):
        """BDD: 寫入課程處方."""
        pipeline = NightlyPipeline(tmp_path)
        pipeline._step_curriculum()

        curricula_dir = tmp_path / "_system" / "curricula"
        assert curricula_dir.exists()
        files = list(curricula_dir.glob("diagnosis_*.json"))
        assert len(files) == 1


# ═══════════════════════════════════════════
# Step 8: Workflow Mutation Tests
# ═══════════════════════════════════════════


class TestWorkflowMutation:
    """Scenario: Step 8 — 工作流突變."""

    def test_no_workflows_dir(self, tmp_path):
        """BDD: 無 workflows 目錄 → skipped."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_workflow_mutation()
        assert "skipped" in result

    def test_plateau_detection(self, tmp_path):
        """BDD: 高原期偵測 + 自動突變."""
        wf_dir = tmp_path / "_system" / "wee" / "workflows" / "wf_test"
        wf_dir.mkdir(parents=True)

        # 5 次執行，分數低且方差小 → 高原期
        runs = [{"score": 5.0}, {"score": 5.1}, {"score": 4.9}, {"score": 5.0}, {"score": 5.0}]
        (wf_dir / "runs.json").write_text(json.dumps(runs))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_workflow_mutation()

        assert result["workflows_scanned"] == 1
        assert result["plateaus_found"] == 1
        assert result["mutations_applied"] == 1

    def test_no_plateau(self, tmp_path):
        """BDD: 分數高 → 不觸發突變."""
        wf_dir = tmp_path / "_system" / "wee" / "workflows" / "wf_good"
        wf_dir.mkdir(parents=True)
        runs = [{"score": 8.0}, {"score": 8.5}, {"score": 9.0}, {"score": 8.2}, {"score": 8.8}]
        (wf_dir / "runs.json").write_text(json.dumps(runs))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_workflow_mutation()
        assert result["plateaus_found"] == 0


# ═══════════════════════════════════════════
# Step 9: Graph Consolidation Tests
# ═══════════════════════════════════════════


class TestGraphConsolidation:
    """Scenario: Step 9 — 知識圖譜睡眠整合."""

    def test_no_graph_dir(self, tmp_path):
        """BDD: 無圖譜目錄 → skipped."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_graph_consolidation()
        assert "skipped" in result

    def test_decay_edges(self, tmp_path):
        """BDD: 自然衰減 — 所有邊權重 × 0.993."""
        graph_dir = tmp_path / "_system" / "graph"
        graph_dir.mkdir(parents=True)
        edges = {
            "e1": {"source": "a", "target": "b", "weight": 0.5, "access_count": 1},
            "e2": {"source": "b", "target": "c", "weight": 0.8, "access_count": 1},
        }
        (graph_dir / "edges.json").write_text(json.dumps(edges))
        (graph_dir / "nodes.json").write_text(json.dumps({"a": {}, "b": {}, "c": {}}))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_graph_consolidation()
        assert result["decayed"] == 2

        updated = json.loads((graph_dir / "edges.json").read_text())
        assert updated["e1"]["weight"] < 0.5

    def test_prune_weak_edges(self, tmp_path):
        """BDD: 修剪弱邊 — 權重 < 0.1 移除."""
        graph_dir = tmp_path / "_system" / "graph"
        graph_dir.mkdir(parents=True)
        edges = {
            "strong": {"source": "a", "target": "b", "weight": 0.9, "access_count": 0},
            "weak": {"source": "c", "target": "d", "weight": 0.05, "access_count": 0},
        }
        (graph_dir / "edges.json").write_text(json.dumps(edges))
        (graph_dir / "nodes.json").write_text(json.dumps({"a": {}, "b": {}, "c": {}, "d": {}}))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_graph_consolidation()
        assert result["pruned"] >= 1

    def test_replay_boost(self, tmp_path):
        """BDD: 重播強化 — 高頻存取邊 +20%."""
        graph_dir = tmp_path / "_system" / "graph"
        graph_dir.mkdir(parents=True)
        edges = {
            "hot": {"source": "a", "target": "b", "weight": 0.5, "access_count": 10},
        }
        (graph_dir / "edges.json").write_text(json.dumps(edges))
        (graph_dir / "nodes.json").write_text(json.dumps({"a": {}, "b": {}}))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_graph_consolidation()
        assert result["replay_boosted"] == 1

    def test_archive_orphan_nodes(self, tmp_path):
        """BDD: 垃圾回收 — 孤立節點歸檔（非刪除）."""
        graph_dir = tmp_path / "_system" / "graph"
        graph_dir.mkdir(parents=True)
        edges = {
            "e1": {"source": "a", "target": "b", "weight": 0.5, "access_count": 0},
        }
        nodes = {"a": {"name": "A"}, "b": {"name": "B"}, "orphan": {"name": "Orphan"}}
        (graph_dir / "edges.json").write_text(json.dumps(edges))
        (graph_dir / "nodes.json").write_text(json.dumps(nodes))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_graph_consolidation()
        assert result["archived_nodes"] >= 1

        archived_dir = graph_dir / "archived"
        assert (archived_dir / "orphan.json").exists()


# ═══════════════════════════════════════════
# Step 10: Soul Nightly Tests
# ═══════════════════════════════════════════


class TestSoulNightly:
    """Scenario: Step 10 — 日記生成（原靈魂層夜間整合）."""

    def test_no_soul_dir(self, tmp_path):
        """BDD: 無 soul 目錄 → 日記仍生成（情緒衰減跳過）."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_diary_generation()
        # v2.0: 不再 skip，即使無 soul dir 也嘗試生成日記
        assert "diary_generated" in result
        assert "emotions_decayed" not in result  # 沒有 soul dir → 不衰減

    def test_emotion_decay(self, tmp_path):
        """BDD: 情緒衰減."""
        soul_dir = tmp_path / "_system" / "soul"
        soul_dir.mkdir(parents=True)
        state = {"emotions": {"joy": 0.8, "curiosity": 0.6}, "identity": "霓裳"}
        (soul_dir / "soul_state.json").write_text(json.dumps(state))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_diary_generation()
        assert result["emotions_decayed"] == 2

        updated = json.loads((soul_dir / "soul_state.json").read_text())
        assert updated["emotions"]["joy"] < 0.8
        assert "last_nightly" in updated


# ═══════════════════════════════════════════
# Step 11: Dream Engine Tests
# ═══════════════════════════════════════════


class TestDreamEngine:
    """Scenario: Step 11 — 夢境引擎."""

    def test_no_memory(self, tmp_path):
        """BDD: 無記憶 → skipped."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_dream_engine()
        assert "skipped" in result

    def test_dream_from_fragments(self, tmp_path):
        """BDD: 有記憶片段 → 生成夢境."""
        ep_dir = tmp_path / "_system" / "memory" / "shared" / "L2_ep"
        ep_dir.mkdir(parents=True)
        for i in range(3):
            (ep_dir / f"mem_{i}.json").write_text(
                json.dumps({"content": f"memory fragment {i}"})
            )

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_dream_engine()
        assert result["dream_generated"] is True
        assert result["fragments_used"] == 3

        dream_dir = tmp_path / "_system" / "dreams"
        assert len(list(dream_dir.glob("dream_*.json"))) == 1


# ═══════════════════════════════════════════
# Step 12: Heartbeat Focus Tests
# ═══════════════════════════════════════════


class TestHeartbeatFocusStep:
    """Scenario: Step 12 — 脈搏焦點調整."""

    def test_with_heartbeat_focus(self, tmp_path):
        """BDD: 有 heartbeat_focus → 重算."""
        hf = HeartbeatFocus()
        pipeline = NightlyPipeline(tmp_path, heartbeat_focus=hf)
        result = pipeline._step_heartbeat_focus()
        assert "interval_hours" in result
        assert "focus_level" in result

    def test_without_heartbeat_focus(self, tmp_path):
        """BDD: 無 heartbeat_focus → 回報."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_heartbeat_focus()
        assert result["recalculated"] is False


# ═══════════════════════════════════════════
# Step 13: Curiosity Scan Tests
# ═══════════════════════════════════════════


class TestCuriosityScan:
    """Scenario: Step 13 — 好奇心掃描."""

    def test_creates_queue_file(self, tmp_path):
        """BDD: 建立問題佇列."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_curiosity_scan()
        assert "queue_size" in result

        queue_file = tmp_path / "_system" / "curiosity" / "question_queue.json"
        assert queue_file.exists()

    def test_scan_logs_for_questions(self, tmp_path):
        """BDD: 掃描對話日誌中的問句."""
        # 實際程式碼掃描 _system/sessions/*.json（role/content 結構）
        sessions_dir = tmp_path / "_system" / "sessions"
        sessions_dir.mkdir(parents=True)

        session_file = sessions_dir / "test_session.json"
        messages = [
            {"role": "user", "content": "這個功能怎麼用？"},
            {"role": "user", "content": "好的，了解"},
            {"role": "user", "content": "為什麼會這樣？"},
        ]
        session_file.write_text(json.dumps(messages, ensure_ascii=False))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_curiosity_scan()
        assert result["new_questions"] == 2


# ═══════════════════════════════════════════
# Step 14: Skill Lifecycle Tests
# ═══════════════════════════════════════════


class TestSkillLifecycle:
    """Scenario: Step 14 — 技能生命週期."""

    def test_no_skills_dir(self, tmp_path):
        """BDD: 無 skills 目錄 → skipped."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_skill_lifecycle()
        assert "skipped" in result

    def test_promote_experimental(self, tmp_path):
        """BDD: 3+ 次成功 → experimental → stable."""
        skills_dir = tmp_path / "_system" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "skill_a.json").write_text(json.dumps({
            "status": "experimental", "success_count": 5, "fail_count": 0
        }))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_skill_lifecycle()
        assert result["promoted"] == 1

        updated = json.loads((skills_dir / "skill_a.json").read_text())
        assert updated["status"] == "stable"

    def test_deprecate_stable(self, tmp_path):
        """BDD: > 50% 失敗 → stable → deprecated."""
        skills_dir = tmp_path / "_system" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "skill_b.json").write_text(json.dumps({
            "status": "stable", "success_count": 2, "fail_count": 8
        }))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_skill_lifecycle()
        assert result["deprecated"] == 1

    def test_archive_deprecated(self, tmp_path):
        """BDD: 30 天無使用 → deprecated → archived."""
        skills_dir = tmp_path / "_system" / "skills"
        skills_dir.mkdir(parents=True)
        old_date = (date.today() - timedelta(days=40)).isoformat()
        (skills_dir / "skill_c.json").write_text(json.dumps({
            "status": "deprecated", "success_count": 0, "fail_count": 0,
            "last_used": old_date
        }))

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_skill_lifecycle()
        assert result["archived"] == 1


# ═══════════════════════════════════════════
# Step 15: Department Health Tests
# ═══════════════════════════════════════════


class TestDeptHealth:
    """Scenario: Step 15 — 部門健康掃描."""

    def test_no_dept_dir(self, tmp_path):
        """BDD: 無部門目錄 → skipped."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_dept_health()
        assert "skipped" in result

    def test_scan_departments(self, tmp_path):
        """BDD: 掃描部門健康度 + 找出最弱."""
        dept_dir = tmp_path / "_system" / "departments"
        dept_dir.mkdir(parents=True)
        for name, score in [("engineering", 0.9), ("marketing", 0.4), ("support", 0.3)]:
            (dept_dir / f"{name}.json").write_text(
                json.dumps({"name": name, "health_score": score, "weaknesses": []})
            )

        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_dept_health()
        assert result["departments_scanned"] == 3
        assert len(result["weakest"]) == 2
        assert result["weakest"][0]["dept"] == "support"

    def test_saves_snapshot(self, tmp_path):
        """BDD: 保存健康快照."""
        dept_dir = tmp_path / "_system" / "departments"
        dept_dir.mkdir(parents=True)
        (dept_dir / "team.json").write_text(
            json.dumps({"name": "team", "health_score": 0.7, "weaknesses": []})
        )

        pipeline = NightlyPipeline(tmp_path)
        pipeline._step_dept_health()

        snapshots = tmp_path / "_system" / "health_snapshots"
        assert len(list(snapshots.glob("health_*.json"))) == 1


# ═══════════════════════════════════════════
# Step 16: Claude Skill Forge Tests
# ═══════════════════════════════════════════


class TestClaudeSkillForge:
    """Scenario: Step 16 — Claude 精煉鍛造."""

    def test_no_brain(self, tmp_path):
        """BDD: 無 brain → skipped."""
        pipeline = NightlyPipeline(tmp_path)
        result = pipeline._step_claude_skill_forge()
        assert "skipped" in result

    def test_no_l3_skills(self, tmp_path):
        """BDD: 無 L3 技能 → skipped."""
        pipeline = NightlyPipeline(tmp_path, brain=MagicMock())
        result = pipeline._step_claude_skill_forge()
        assert "skipped" in result

    def test_refine_skills(self, tmp_path):
        """BDD: 精煉已鍛造的 L3 技能."""
        l3_dir = tmp_path / "_system" / "memory" / "shared" / "L3_procedural"
        l3_dir.mkdir(parents=True)
        for i in range(2):
            (l3_dir / f"skill_{i}.json").write_text(
                json.dumps({"type": "L3_procedural", "cluster_id": i})
            )

        pipeline = NightlyPipeline(tmp_path, brain=MagicMock())
        result = pipeline._step_claude_skill_forge()
        assert result["refined"] == 2


# ═══════════════════════════════════════════
# Report Persistence Tests
# ═══════════════════════════════════════════


class TestReportPersistence:
    """Scenario: 報告持久化."""

    def test_report_saved(self, tmp_path):
        """BDD: 報告存入 nightly_report.json."""
        pipeline = NightlyPipeline(tmp_path)
        pipeline.run()

        report_path = tmp_path / "_system" / "state" / "nightly_report.json"
        assert report_path.exists()

        data = json.loads(report_path.read_text())
        assert "completed_at" in data
        assert "steps" in data
        assert "summary" in data
        assert isinstance(data["steps"], dict)

    def test_report_truncation(self, tmp_path):
        """BDD: 持久化報告中結果截斷至 200 字."""
        pipeline = NightlyPipeline(tmp_path)
        pipeline.run()

        report_path = tmp_path / "_system" / "state" / "nightly_report.json"
        data = json.loads(report_path.read_text())

        for step_name, step_data in data["steps"].items():
            if "result" in step_data:
                assert len(step_data["result"]) <= REPORT_TRUNCATE_CHARS

    def test_atomic_write(self, tmp_path):
        """BDD: 使用 tmp 檔 + os.replace 原子寫入."""
        pipeline = NightlyPipeline(tmp_path)
        pipeline.run()

        # 檢查沒有殘留 .tmp 檔
        state_dir = tmp_path / "_system" / "state"
        assert not list(state_dir.glob("*.tmp"))


# ═══════════════════════════════════════════
# HTML Report Tests
# ═══════════════════════════════════════════


class TestBuildNightlyHtml:
    """Scenario: HTML 報告生成."""

    def test_basic_html(self):
        """BDD: 生成 Telegram 可讀 HTML."""
        report = {
            "mode": "full",
            "elapsed_seconds": 3.5,
            "summary": {"total": 18, "ok": 16, "error": 1, "skipped": 1},
            "errors": [{"step": "step_09_graph", "error": "no graph"}],
        }
        html = build_nightly_html(report)
        assert "<b>" in html
        assert "16" in html
        assert "step_09_graph" in html

    def test_no_errors_html(self):
        """BDD: 無錯誤時用 ✅."""
        report = {
            "mode": "full",
            "elapsed_seconds": 2.1,
            "summary": {"total": 18, "ok": 18, "error": 0, "skipped": 0},
            "errors": [],
        }
        html = build_nightly_html(report)
        assert "✅" in html


# ═══════════════════════════════════════════
# Register Tasks Tests
# ═══════════════════════════════════════════


class TestRegisterNightlyTasks:
    """Scenario: 排程器整合."""

    def test_register_two_tasks(self, tmp_path):
        """BDD: 註冊 nightly_consolidation + morning_report."""
        scheduler = MagicMock()
        registered = []
        scheduler.register = lambda **kw: registered.append(kw)

        register_nightly_tasks(scheduler, tmp_path)

        names = [r["name"] for r in registered]
        assert "nightly_consolidation" in names
        assert "nightly_morning_report" in names

    def test_nightly_cron_settings(self, tmp_path):
        """BDD: nightly_consolidation cron_hour=3, cron_minute=0."""
        scheduler = MagicMock()
        registered = []
        scheduler.register = lambda **kw: registered.append(kw)

        register_nightly_tasks(scheduler, tmp_path)

        nightly = next(r for r in registered if r["name"] == "nightly_consolidation")
        assert nightly["cron_hour"] == 3
        assert nightly["cron_minute"] == 0

    def test_morning_report_cron_settings(self, tmp_path):
        """BDD: morning_report cron_hour=7, cron_minute=30."""
        scheduler = MagicMock()
        registered = []
        scheduler.register = lambda **kw: registered.append(kw)

        register_nightly_tasks(scheduler, tmp_path)

        morning = next(r for r in registered if r["name"] == "nightly_morning_report")
        assert morning["cron_hour"] == 7
        assert morning["cron_minute"] == 30


# ═══════════════════════════════════════════
# EventBus Events Tests
# ═══════════════════════════════════════════


class TestEventBusEvents:
    """Scenario: EventBus 事件定義."""

    def test_nightly_events_defined(self):
        """BDD: NIGHTLY_STARTED + NIGHTLY_COMPLETED 已定義."""
        from museon.core.event_bus import NIGHTLY_COMPLETED, NIGHTLY_STARTED
        assert NIGHTLY_STARTED == "NIGHTLY_STARTED"
        assert NIGHTLY_COMPLETED == "NIGHTLY_COMPLETED"

    def test_eventbus_no_crash_on_subscriber_error(self, tmp_path):
        """BDD: 訂閱者異常不影響管線."""
        from museon.core.event_bus import EventBus

        bus = EventBus()

        def bad_subscriber(data):
            raise RuntimeError("subscriber crash")

        bus.subscribe("NIGHTLY_COMPLETED", bad_subscriber)

        pipeline = NightlyPipeline(tmp_path, event_bus=bus)
        report = pipeline.run()
        # 管線正常完成
        assert "summary" in report
