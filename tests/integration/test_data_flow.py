"""端對端數據流測試 — 驗證 寫入→儲存→讀取→顯示 管線完整性.

DSE 第一性原理：每條關鍵數據管線都有測試覆蓋。
"""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Schema Registry 匯入驗證 ──


class TestSchemaRegistry:
    """驗證 Schema Registry 本身的完整性."""

    def test_mc_schema_importable(self):
        from museon.core.anima_schema import MC
        assert MC.EIGHT_PRIMALS == "eight_primal_energies"
        assert MC.IDENTITY == "identity"
        assert MC.Identity.DAYS_ALIVE == "days_alive"

    def test_user_schema_importable(self):
        from museon.core.anima_schema import USER
        assert USER.EIGHT_PRIMALS == "eight_primals"
        assert USER.Layers.L5_PREFERENCE == "L5_preference_crystals"
        assert USER.CommStyle.TONE == "tone"

    def test_drift_schema_importable(self):
        from museon.core.anima_schema import DRIFT
        assert DRIFT.MC_PRIMALS == "mc_primals"
        assert DRIFT.USER_L5 == "user_L5"

    def test_pulse_schema_importable(self):
        from museon.core.anima_schema import PULSE
        assert PULSE.RELATIONSHIP_JOURNAL == "## 💝 關係日誌"

    def test_get_nested(self):
        from museon.core.anima_schema import get_nested, MC
        data = {"identity": {"days_alive": 3, "name": "霓裳"}}
        assert get_nested(data, MC.IDENTITY, MC.Identity.DAYS_ALIVE) == 3
        assert get_nested(data, MC.IDENTITY, "missing", default="x") == "x"
        assert get_nested(data, "nonexistent", default=None) is None

    def test_set_nested(self):
        from museon.core.anima_schema import set_nested, MC
        data = {"identity": {"days_alive": 2}}
        set_nested(data, MC.IDENTITY, MC.Identity.DAYS_ALIVE, value=3)
        assert data["identity"]["days_alive"] == 3

    def test_set_nested_creates_intermediate(self):
        from museon.core.anima_schema import set_nested
        data = {}
        set_nested(data, "a", "b", "c", value=42)
        assert data["a"]["b"]["c"] == 42


# ── ANIMA_MC 數據流測試 ──


class TestAnimaMCDataFlow:
    """ANIMA_MC.json 的寫入→讀取一致性."""

    @pytest.fixture
    def tmp_anima_mc(self, tmp_path):
        mc_data = {
            "identity": {
                "name": "霓裳",
                "birth_date": "2026-03-06T23:26:25.689607",
                "growth_stage": "adult",
                "days_alive": 2,
            },
            "eight_primal_energies": {
                "乾": {"absolute": 100, "relative": 10.0},
                "坤": {"absolute": 0, "relative": 0.0},
            },
            "evolution": {
                "paused": False,
                "iteration_count": 100,
            },
            "memory_summary": {
                "total_interactions": 200,
                "knowledge_crystals": 100,
            },
            "self_awareness": {
                "expression_style": {
                    "tone_temperature": 0.5,
                },
            },
        }
        path = tmp_path / "ANIMA_MC.json"
        path.write_text(json.dumps(mc_data, ensure_ascii=False))
        return path, mc_data

    def test_eight_primals_field_name_consistency(self, tmp_anima_mc):
        """驗證 eight_primal_energies 是正式欄位名."""
        from museon.core.anima_schema import MC
        path, _ = tmp_anima_mc
        data = json.loads(path.read_text())

        # 正式名稱必須存在
        assert MC.EIGHT_PRIMALS in data
        # 舊名稱不應存在
        assert "eight_primals" not in data

    def test_drift_detector_reads_mc_primals(self, tmp_anima_mc):
        """驗證 DriftDetector.take_baseline 正確讀取 MC 八原語."""
        from museon.agent.drift_detector import DriftDetector

        path, mc_data = tmp_anima_mc
        data_dir = path.parent

        # 建立 anima 子目錄
        (data_dir / "anima").mkdir(exist_ok=True)
        (data_dir / "guardian").mkdir(exist_ok=True)

        detector = DriftDetector(data_dir=data_dir)
        user_data = {"eight_primals": {"乾": 0.5}}

        detector.take_baseline(mc_data, user_data)

        # 基線必須包含 MC primals
        assert detector._baseline is not None
        mc_primals = detector._baseline.get("mc_primals", {})
        assert mc_primals, "mc_primals 不應為空"
        assert "乾" in mc_primals

    def test_days_alive_update_in_micro_pulse(self, tmp_anima_mc):
        """驗證 MicroPulse 能正確更新 days_alive."""
        from museon.pulse.micro_pulse import MicroPulse

        path, _ = tmp_anima_mc
        workspace = path.parent
        hf = MagicMock()
        eb = MagicMock()

        pulse = MicroPulse(hf, eb, str(workspace))
        pulse._update_days_alive()

        # 重新讀取驗證
        updated = json.loads(path.read_text())
        birth = datetime.fromisoformat(updated["identity"]["birth_date"])
        expected_days = (datetime.now() - birth).days
        assert updated["identity"]["days_alive"] == expected_days


# ── ANIMA_USER 數據流測試 ──


class TestAnimaUserDataFlow:
    """ANIMA_USER.json 的 L5/L6 數據完整性."""

    @pytest.fixture
    def user_data(self):
        return {
            "seven_layers": {
                "L5_preference_crystals": [
                    {
                        "key": "prefers_long_response",
                        "confidence": 0.5,
                        "observed_count": 5,
                    },
                    {
                        "key": "prefers_short_response",
                        "confidence": 0.5,
                        "observed_count": 5,
                    },
                ],
                "L6_communication_style": {
                    "tone": "casual",
                    "detail_level": "concise",
                },
            },
            "_pref_buffer": {
                "prefers_long_response": {"count": 135, "last": "2026-03-09"},
                "prefers_short_response": {"count": 80, "last": "2026-03-09"},
            },
            "eight_primals": {},
        }

    def test_l5_crystals_read_write_consistency(self, user_data):
        """驗證 L5 偏好結晶能正確更新."""
        from museon.core.anima_schema import USER, get_nested

        prefs = get_nested(
            user_data,
            USER.SEVEN_LAYERS,
            USER.Layers.L5_PREFERENCE,
            default=[],
        )
        assert len(prefs) == 2
        assert prefs[0]["key"] == "prefers_long_response"

    def test_contradictory_prefs_detected(self, user_data):
        """驗證矛盾偏好能被掃描器偵測."""
        from museon.doctor.field_scanner import FieldScanner

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            data_dir = workspace / "data"
            data_dir.mkdir()
            (workspace / "src" / "museon").mkdir(parents=True)
            (data_dir / "anima").mkdir()

            # 寫入測試數據
            (data_dir / "ANIMA_USER.json").write_text(
                json.dumps(user_data, ensure_ascii=False)
            )
            (data_dir / "ANIMA_MC.json").write_text(
                json.dumps({"eight_primal_energies": {}})
            )
            (data_dir / "anima" / "drift_baseline.json").write_text(
                json.dumps({"mc_primals": {"test": 1}})
            )
            (data_dir / "anima" / "soul_rings.json").write_text("[]")
            (data_dir / "PULSE.md").write_text(
                "## 🌊 成長反思\n## 🔭 今日觀察\n"
                "## 🌱 成長軌跡\n## 💝 關係日誌\n## 📊 今日狀態"
            )

            scanner = FieldScanner(workspace)
            report = scanner.scan()

            contradictions = [
                m for m in report.mismatches
                if m.category == "contradictory"
            ]
            assert len(contradictions) >= 1
            assert "prefers_short" in contradictions[0].message


# ── Drift Baseline 數據流測試 ──


class TestDriftBaselineDataFlow:
    """drift_baseline.json 的欄位一致性."""

    def test_baseline_includes_mc_primals(self, tmp_path):
        """基線快照必須包含 MC 八原語."""
        from museon.agent.drift_detector import DriftDetector

        (tmp_path / "anima").mkdir()
        (tmp_path / "guardian").mkdir()

        detector = DriftDetector(data_dir=tmp_path)
        mc_data = {
            "eight_primal_energies": {"乾": {"absolute": 100}},
            "self_awareness": {"expression_style": {"tone": 0.5}},
        }
        user_data = {
            "eight_primals": {"乾": 0.5},
            "seven_layers": {
                "L5_preference_crystals": [],
                "L6_communication_style": {},
                "L7_context_roles": [],
            },
        }

        detector.take_baseline(mc_data, user_data)

        baseline_path = tmp_path / "anima" / "drift_baseline.json"
        assert baseline_path.exists()

        baseline = json.loads(baseline_path.read_text())
        assert baseline["mc_primals"], "mc_primals 不應為空"
        assert "乾" in baseline["mc_primals"]
        assert baseline["user_primals"], "user_primals 不應為空"


# ── Soul Ring 數據流測試 ──


class TestSoulRingDataFlow:
    """soul_rings.json 的寫入管線測試."""

    def test_ring_depositor_writes_to_store(self, tmp_path):
        """驗證 RingDepositor → SoulRingStore 管線暢通."""
        from museon.agent.soul_ring import SoulRingStore, RingDepositor

        (tmp_path / "anima").mkdir()
        (tmp_path / "anima" / "backups").mkdir()

        store = SoulRingStore(data_dir=str(tmp_path))
        depositor = RingDepositor(store=store, data_dir=str(tmp_path))

        # 嘗試沉積一條年輪
        depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="測試用認知突破",
            context="測試上下文",
            impact="測試影響",
        )

        # 驗證寫入
        rings_path = tmp_path / "anima" / "soul_rings.json"
        rings = json.loads(rings_path.read_text())
        assert len(rings) >= 1
        assert rings[0]["type"] == "cognitive_breakthrough"


# ── Field Scanner 自身測試 ──


class TestFieldScanner:
    """掃描器功能測試."""

    def test_scanner_runs_without_crash(self, tmp_path):
        """掃描器在空專案中不會崩潰."""
        from museon.doctor.field_scanner import FieldScanner

        (tmp_path / "data").mkdir()
        (tmp_path / "src" / "museon").mkdir(parents=True)

        scanner = FieldScanner(tmp_path)
        report = scanner.scan()
        assert report.total_accesses == 0

    def test_scanner_detects_missing_json(self, tmp_path):
        """掃描器偵測缺失的 JSON 檔案."""
        from museon.doctor.field_scanner import FieldScanner

        (tmp_path / "data").mkdir()
        (tmp_path / "src" / "museon").mkdir(parents=True)

        scanner = FieldScanner(tmp_path)
        report = scanner.scan()

        missing = [m for m in report.mismatches if m.category == "missing_file"]
        assert len(missing) >= 1
