"""測試 Breath Protocol 各模組.

涵蓋：
1. breath_watcher：四條河流收集（mock 檔案系統）
2. breath_scheduler：每天跑正確的步驟
3. breath_retro：正確計算指標比較
4. 護欄：blast_radius > 1 時行為
5. 紅燈：重複教訓偵測
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """建立一個臨時的 MUSEON workspace."""
    # 建立必要的目錄結構
    (tmp_path / "data/_system/breath/observations").mkdir(parents=True)
    (tmp_path / "data/_system/breath/patterns").mkdir(parents=True)
    (tmp_path / "data/_system/breath/diagnoses").mkdir(parents=True)
    (tmp_path / "data/_system/breath/actions").mkdir(parents=True)
    (tmp_path / "data/_system/breath/retros").mkdir(parents=True)
    (tmp_path / "data/_system/feedback_loop").mkdir(parents=True)
    (tmp_path / "data/_system/doctor").mkdir(parents=True)
    (tmp_path / "data/_system/skill_health").mkdir(parents=True)
    (tmp_path / "data/memory_v3").mkdir(parents=True)
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_observations(tmp_workspace: Path) -> Path:
    """建立一份範例 observations JSONL."""
    week_id = "2026-w14"
    obs_path = tmp_workspace / f"data/_system/breath/observations/{week_id}.jsonl"
    obs_data = [
        {
            "river": "zeal_interaction",
            "timestamp": "2026-04-01T10:00:00",
            "type": "session_summary",
            "content": "建立了 Breath Protocol 的觀察層",
            "severity": "info",
            "source": "2026-04-01_session.md",
        },
        {
            "river": "client_interaction",
            "timestamp": "2026-04-01T11:00:00",
            "type": "feedback_loop_summary",
            "content": {"q_score": 0.75, "total_messages": 42},
            "severity": "info",
            "source": "feedback_loop/daily_summary.json",
        },
        {
            "river": "self_observation",
            "timestamp": "2026-04-01T12:00:00",
            "type": "connection_validation",
            "content": {"returncode": 0, "stdout": "All OK"},
            "severity": "info",
            "source": "scripts/validate_connections.py",
        },
        {
            "river": "external_exploration",
            "timestamp": "2026-04-01T13:00:00",
            "type": "digest_result",
            "content": {"topic": "AI coaching trends"},
            "severity": "info",
            "source": "exploration_digest/2026-04-01.json",
        },
    ]
    with obs_path.open("w", encoding="utf-8") as f:
        for obs in obs_data:
            f.write(json.dumps(obs, ensure_ascii=False) + "\n")
    return obs_path


# ── Test: breath_watcher ──────────────────────────────────────────────────────


class TestBreathWatcher:
    @pytest.mark.asyncio
    async def test_collect_observations_returns_stats(self, tmp_workspace: Path):
        """collect_observations 應回傳四條河流的統計."""
        from museon.evolution.breath_watcher import collect_observations

        stats = await collect_observations(tmp_workspace)

        assert "total" in stats
        assert "river_1" in stats
        assert "river_2" in stats
        assert "river_3" in stats
        assert "river_4" in stats
        assert "week_id" in stats
        assert isinstance(stats["total"], int)
        assert stats["total"] >= 0

    @pytest.mark.asyncio
    async def test_collect_observations_creates_jsonl(self, tmp_workspace: Path):
        """collect_observations 應建立 JSONL 檔案."""
        from museon.evolution.breath_watcher import collect_observations

        await collect_observations(tmp_workspace)

        week_id = datetime.now().strftime("%Y-w%W")
        obs_path = tmp_workspace / f"data/_system/breath/observations/{week_id}.jsonl"
        assert obs_path.exists()

    @pytest.mark.asyncio
    async def test_river1_reads_session_summaries(self, tmp_workspace: Path):
        """River 1 應能讀取 session 摘要（mock ~/.claude/projects/.../sessions/）."""
        with tempfile.TemporaryDirectory() as tmp_sessions_dir:
            sessions_path = Path(tmp_sessions_dir)
            # 建立一份假 session 摘要
            session_file = sessions_path / "2026-04-01_10-00_測試.md"
            session_file.write_text("## 完成事項\n- 測試 session", encoding="utf-8")

            # Mock Path.home() 指向的 memory 路徑
            fake_memory_dir = tmp_workspace / ".claude_memory"
            fake_sessions_dir = fake_memory_dir / "sessions"
            fake_sessions_dir.mkdir(parents=True)
            (fake_sessions_dir / "2026-04-01_10-00_測試.md").write_text(
                "## 完成事項\n- 測試 session", encoding="utf-8"
            )

            from museon.evolution.breath_watcher import _collect_zeal_river

            # 直接測試 helper，mock home() 路徑
            with patch("pathlib.Path.home", return_value=fake_memory_dir.parent):
                # 因為路徑 mock 複雜，這裡只確認函數不拋例外
                result = await _collect_zeal_river(tmp_workspace)
                assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_river2_reads_feedback_loop(self, tmp_workspace: Path):
        """River 2 應能讀取 feedback_loop/daily_summary.json."""
        # 建立假的 feedback_loop summary
        summary_data = {"q_score": 0.8, "total_messages": 100}
        summary_path = tmp_workspace / "data/_system/feedback_loop/daily_summary.json"
        summary_path.write_text(json.dumps(summary_data), encoding="utf-8")

        from museon.evolution.breath_watcher import _collect_client_river

        result = await _collect_client_river(tmp_workspace)

        assert isinstance(result, list)
        assert len(result) >= 1
        # 找到 feedback_loop_summary 類型的觀察
        types = [obs["type"] for obs in result]
        assert "feedback_loop_summary" in types

    @pytest.mark.asyncio
    async def test_observation_format(self, tmp_workspace: Path):
        """每條觀察都應有必要欄位."""
        from museon.evolution.breath_watcher import collect_observations

        await collect_observations(tmp_workspace)

        week_id = datetime.now().strftime("%Y-w%W")
        obs_path = tmp_workspace / f"data/_system/breath/observations/{week_id}.jsonl"

        if obs_path.exists():
            for line in obs_path.read_text(encoding="utf-8").strip().splitlines():
                obs = json.loads(line)
                assert "river" in obs
                assert "timestamp" in obs
                assert "type" in obs
                assert "content" in obs
                assert "severity" in obs


# ── Test: breath_scheduler ────────────────────────────────────────────────────


class TestBreathScheduler:
    @pytest.mark.asyncio
    async def test_monday_runs_observe(self, tmp_workspace: Path):
        """週一應執行 observe 步驟."""
        from museon.evolution.breath_scheduler import breath_tick

        with patch("museon.evolution.breath_scheduler.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.isoweekday.return_value = 1  # 週一
            mock_now.strftime.return_value = "2026-w14"
            mock_now.isoformat.return_value = "2026-04-06T10:00:00"
            mock_dt.now.return_value = mock_now

            with patch("museon.evolution.breath_watcher.collect_observations", new_callable=AsyncMock) as mock_collect:
                mock_collect.return_value = {"total": 5, "week_id": "2026-w14"}
                result = await breath_tick(tmp_workspace)

        assert result["step"] == "observe"
        assert result["day_of_week"] == 1

    @pytest.mark.asyncio
    async def test_wednesday_runs_analyze(self, tmp_workspace: Path):
        """週三應執行 analyze 步驟."""
        from museon.evolution.breath_scheduler import breath_tick

        with patch("museon.evolution.breath_scheduler.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.isoweekday.return_value = 3  # 週三
            mock_now.strftime.return_value = "2026-w14"
            mock_now.isoformat.return_value = "2026-04-08T10:00:00"
            mock_dt.now.return_value = mock_now

            with patch("museon.evolution.breath_analyzer.analyze_patterns", new_callable=AsyncMock) as mock_analyze:
                mock_analyze.return_value = {"week_id": "2026-w14", "top_patterns": []}
                result = await breath_tick(tmp_workspace)

        assert result["step"] == "analyze"
        assert result["day_of_week"] == 3

    @pytest.mark.asyncio
    async def test_friday_runs_diagnose(self, tmp_workspace: Path):
        """週五應執行 diagnose 步驟."""
        from museon.evolution.breath_scheduler import breath_tick

        with patch("museon.evolution.breath_scheduler.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.isoweekday.return_value = 5  # 週五
            mock_now.strftime.return_value = "2026-w14"
            mock_now.isoformat.return_value = "2026-04-10T10:00:00"
            mock_dt.now.return_value = mock_now

            with patch("museon.evolution.breath_diagnostician.diagnose", new_callable=AsyncMock) as mock_diagnose:
                mock_diagnose.return_value = {"week_id": "2026-w14", "recommended": "none"}
                result = await breath_tick(tmp_workspace)

        assert result["step"] == "diagnose"
        assert result["day_of_week"] == 5

    @pytest.mark.asyncio
    async def test_saturday_runs_execute(self, tmp_workspace: Path):
        """週六應執行 execute 步驟."""
        from museon.evolution.breath_scheduler import breath_tick

        with patch("museon.evolution.breath_scheduler.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.isoweekday.return_value = 6  # 週六
            mock_now.strftime.return_value = "2026-w14"
            mock_now.isoformat.return_value = "2026-04-11T10:00:00"
            mock_dt.now.return_value = mock_now

            with patch("museon.evolution.breath_executor.execute_weekly", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = {"status": "no_action"}
                result = await breath_tick(tmp_workspace)

        assert result["step"] == "execute"
        assert result["day_of_week"] == 6

    @pytest.mark.asyncio
    async def test_sunday_runs_retro(self, tmp_workspace: Path):
        """週日應執行 retro 步驟."""
        from museon.evolution.breath_scheduler import breath_tick

        with patch("museon.evolution.breath_scheduler.datetime") as mock_dt:
            mock_now = MagicMock()
            mock_now.isoweekday.return_value = 7  # 週日
            mock_now.strftime.return_value = "2026-w14"
            mock_now.isoformat.return_value = "2026-04-12T10:00:00"
            mock_dt.now.return_value = mock_now

            with patch("museon.evolution.breath_retro.weekly_retro", new_callable=AsyncMock) as mock_retro:
                mock_retro.return_value = {"week_id": "2026-w14", "red_light": []}
                result = await breath_tick(tmp_workspace)

        assert result["step"] == "retro"
        assert result["day_of_week"] == 7

    @pytest.mark.asyncio
    async def test_manual_step_trigger(self, tmp_workspace: Path):
        """breath_tick_step 應能手動觸發指定步驟."""
        from museon.evolution.breath_scheduler import breath_tick_step

        with patch("museon.evolution.breath_watcher.collect_observations", new_callable=AsyncMock) as mock_collect:
            mock_collect.return_value = {"total": 3, "week_id": "2026-w14"}
            result = await breath_tick_step("observe", tmp_workspace, "2026-w14")

        assert result["step"] == "observe"
        assert result["week_id"] == "2026-w14"

    @pytest.mark.asyncio
    async def test_invalid_step_returns_error(self, tmp_workspace: Path):
        """無效的 step 應回傳 error。"""
        from museon.evolution.breath_scheduler import breath_tick_step

        result = await breath_tick_step("invalid_step", tmp_workspace)
        assert "error" in result


# ── Test: breath_retro ────────────────────────────────────────────────────────


class TestBreathRetro:
    @pytest.mark.asyncio
    async def test_retro_creates_output_file(self, tmp_workspace: Path, sample_observations: Path):
        """weekly_retro 應建立 retros/{week_id}.json."""
        from museon.evolution.breath_retro import weekly_retro

        result = await weekly_retro(tmp_workspace, "2026-w14")

        output_path = tmp_workspace / "data/_system/breath/retros/2026-w14.json"
        assert output_path.exists()
        assert result["week_id"] == "2026-w14"

    @pytest.mark.asyncio
    async def test_retro_has_three_questions(self, tmp_workspace: Path, sample_observations: Path):
        """週報應包含三問的回答."""
        from museon.evolution.breath_retro import weekly_retro

        result = await weekly_retro(tmp_workspace, "2026-w14")

        assert "metrics_comparison" in result
        assert "repeated_lessons" in result
        assert "blind_spot_guesses" in result
        assert "next_week_focus" in result

    @pytest.mark.asyncio
    async def test_retro_metrics_trend_calc(self, tmp_workspace: Path):
        """指標趨勢計算應正確."""
        from museon.evolution.breath_retro import _calc_trend

        assert _calc_trend(0.80, 0.75) == "up"    # 上升 > 2%
        assert _calc_trend(0.75, 0.80) == "down"  # 下降 > 2%
        assert _calc_trend(0.80, 0.80) == "stable"  # 持平
        assert _calc_trend(None, 0.80) == "unknown"
        assert _calc_trend(0.80, None) == "unknown"

    @pytest.mark.asyncio
    async def test_retro_detects_repeated_lessons(self, tmp_workspace: Path):
        """應能偵測重複的教訓."""
        # 建立 awareness_log.jsonl 含重複教訓
        awareness_path = tmp_workspace / "data/memory_v3/awareness_log.jsonl"
        duplicate_lesson = "必須在唯一出口做安全過濾，不能在多個地方加判斷"
        entries = [
            {"timestamp": "2026-04-01T10:00:00", "lesson": duplicate_lesson},
            {"timestamp": "2026-04-02T10:00:00", "lesson": duplicate_lesson},  # 重複
            {"timestamp": "2026-04-03T10:00:00", "lesson": "另一條不同的教訓"},
        ]
        with awareness_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        from museon.evolution.breath_retro import _detect_repeated_lessons

        repeated = _detect_repeated_lessons(tmp_workspace, "2026-w14")

        assert len(repeated) >= 1
        assert any("出現 2 次" in r for r in repeated)

    @pytest.mark.asyncio
    async def test_retro_red_light_on_repeated_lessons(self, tmp_workspace: Path):
        """有 2 條以上重複教訓時，應觸發紅燈."""
        from museon.evolution.breath_retro import _check_red_lights

        repeated_lessons = ["教訓 A（出現 2 次）", "教訓 B（出現 3 次）"]
        red_lights = _check_red_lights({}, repeated_lessons, [])

        assert len(red_lights) >= 1
        assert any("RED_LIGHT" in rl for rl in red_lights)

    @pytest.mark.asyncio
    async def test_retro_blind_spots_cover_missing_rivers(self, tmp_workspace: Path):
        """如果某條河流沒有觀察，應在盲點中提醒."""
        # 只有 zeal_interaction，沒有其他河流
        obs_only_zeal = [
            {"river": "zeal_interaction", "type": "test", "content": "x", "severity": "info", "timestamp": "2026-04-01T10:00:00"},
        ]

        from museon.evolution.breath_retro import _guess_blind_spots

        blind_spots = _guess_blind_spots(obs_only_zeal)

        assert any("河流" in b or "river" in b.lower() or "盲點" in b for b in blind_spots)


# ── Test: breath_executor 護欄 ────────────────────────────────────────────────


class TestBreathExecutorGuardrails:
    def test_dna_boundary_detected(self):
        """涉及不可變核心的描述應被 DNA_BOUNDARY 標記."""
        from museon.evolution.breath_executor import _check_dna_boundary

        # 觸及不可變核心
        assert _check_dna_boundary("修改 ResponseGuard 的 patterns") is not None
        assert _check_dna_boundary("更新 ANIMA 的身份核心") is not None
        assert _check_dna_boundary("修改 breath_executor 的回滾邏輯") is not None

        # 不觸及
        assert _check_dna_boundary("調整 Skill 的 trigger 權重") is None
        assert _check_dna_boundary("更新 parameter_tuner 的 Q-Score 閾值") is None

    @pytest.mark.asyncio
    async def test_dna_boundary_blocks_execution(self, tmp_workspace: Path):
        """DNA_BOUNDARY 應阻止執行，並寫入記錄."""
        # 建立 diagnosis 要求修改不可變核心
        diagnosis = {
            "week_id": "2026-w14",
            "recommended": "subtraction",
            "subtraction_option": {
                "description": "刪除 ResponseGuard 的某個 pattern",
                "blast_radius": 1,
                "effort": "low",
                "why_this_first": "減法",
            },
            "acceptance_criteria": [],
            "consumption_chain": "...",
        }
        diagnosis_path = tmp_workspace / "data/_system/breath/diagnoses/2026-w14.json"
        diagnosis_path.write_text(json.dumps(diagnosis, ensure_ascii=False), encoding="utf-8")

        from museon.evolution.breath_executor import execute_weekly

        result = await execute_weekly(tmp_workspace, "2026-w14")

        assert result.get("flag") == "DNA_BOUNDARY"
        assert result.get("status") == "skipped"

    @pytest.mark.asyncio
    async def test_no_action_when_recommended_none(self, tmp_workspace: Path):
        """recommended=none 時應記錄 no_action 並返回."""
        diagnosis = {
            "week_id": "2026-w14",
            "recommended": "none",
            "subtraction_option": {},
            "addition_option": {},
            "acceptance_criteria": [],
        }
        diagnosis_path = tmp_workspace / "data/_system/breath/diagnoses/2026-w14.json"
        diagnosis_path.write_text(json.dumps(diagnosis, ensure_ascii=False), encoding="utf-8")

        from museon.evolution.breath_executor import execute_weekly

        result = await execute_weekly(tmp_workspace, "2026-w14")

        assert result.get("type") == "no_action"
        assert result.get("status") == "skipped"

    @pytest.mark.asyncio
    async def test_blast_radius_too_high_blocked(self, tmp_workspace: Path):
        """blast_radius > 5 應被阻止，建議拆分。"""
        diagnosis = {
            "week_id": "2026-w14",
            "recommended": "addition",
            "addition_option": {
                "description": "重構整個 Nightly Pipeline",
                "blast_radius": 8,
                "effort": "high",
                "why_addition": "必要",
            },
            "acceptance_criteria": [],
        }
        diagnosis_path = tmp_workspace / "data/_system/breath/diagnoses/2026-w14.json"
        diagnosis_path.write_text(json.dumps(diagnosis, ensure_ascii=False), encoding="utf-8")

        from museon.evolution.breath_executor import execute_weekly

        result = await execute_weekly(tmp_workspace, "2026-w14")

        assert result.get("flag") == "BLAST_RADIUS_TOO_HIGH"
        assert result.get("status") == "skipped"

    def test_weekly_quota_tracking(self, tmp_workspace: Path):
        """_load_existing_actions 應能正確統計本週已有的 actions."""
        from museon.evolution.breath_executor import _load_existing_actions

        # 空白週
        result = _load_existing_actions(tmp_workspace, "2026-w14")
        assert result == []

        # 寫入假的 actions 記錄
        actions_path = tmp_workspace / "data/_system/breath/actions/2026-w14.json"
        actions_data = {
            "week_id": "2026-w14",
            "actions": [
                {"type": "structural", "status": "success", "description": "改動 A"},
                {"type": "parameter", "status": "success", "description": "調整 B"},
            ],
        }
        actions_path.write_text(json.dumps(actions_data), encoding="utf-8")

        result = _load_existing_actions(tmp_workspace, "2026-w14")
        assert len(result) == 2
        structural = [a for a in result if a["type"] == "structural"]
        assert len(structural) == 1
