"""SelfDiagnosis BDD 測試.

驗證對話中自我診斷 + 自動修復。
"""

import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass

from museon.doctor.self_diagnosis import (
    SelfDiagnosis,
    DiagnosisIssue,
    DiagnosisReport,
    RepairResult,
    detect_self_check_intent,
    GREEN_ZONE_ACTIONS,
    YELLOW_ZONE_ACTIONS,
    RED_ZONE_ACTIONS,
    _SELF_CHECK_KEYWORDS,
)


# ═══════════════════════════════════════════
# 意圖偵測
# ═══════════════════════════════════════════


class TestSelfCheckIntent:
    """Scenario: 自我檢查意圖偵測."""

    def test_keyword_self_check(self):
        """「自我檢查」觸發."""
        assert detect_self_check_intent("自我檢查") is True

    def test_keyword_health_check(self):
        """「健康檢查」觸發."""
        assert detect_self_check_intent("健康檢查") is True

    def test_keyword_system_status(self):
        """「系統狀態」觸發."""
        assert detect_self_check_intent("系統狀態") is True

    def test_keyword_are_you_ok(self):
        """「你還好嗎」觸發."""
        assert detect_self_check_intent("你還好嗎") is True

    def test_keyword_whats_wrong(self):
        """「你哪裡壞了」觸發."""
        assert detect_self_check_intent("你哪裡壞了") is True

    def test_keyword_english(self):
        """英文 self check 觸發."""
        assert detect_self_check_intent("self check") is True

    def test_pattern_check_system(self):
        """「檢查一下系統」模式匹配."""
        assert detect_self_check_intent("幫我檢查一下系統") is True

    def test_no_trigger_normal_chat(self):
        """一般對話不觸發."""
        assert detect_self_check_intent("今天天氣好嗎") is False

    def test_no_trigger_empty(self):
        """空字串不觸發."""
        assert detect_self_check_intent("") is False

    def test_no_trigger_unrelated(self):
        """不相關的技術問題不觸發."""
        assert detect_self_check_intent("如何寫 Python decorator") is False

    def test_keyword_count(self):
        """至少有 20 個關鍵字."""
        assert len(_SELF_CHECK_KEYWORDS) >= 20

    def test_self_repair_keyword(self):
        """「自我修復」觸發."""
        assert detect_self_check_intent("自我修復") is True

    def test_diagnose_keyword(self):
        """「診斷一下」觸發."""
        assert detect_self_check_intent("幫我診斷一下") is True

    def test_case_insensitive_english(self):
        """英文關鍵字大小寫無關."""
        assert detect_self_check_intent("Self Check") is True
        assert detect_self_check_intent("HEALTH CHECK") is True


# ═══════════════════════════════════════════
# 安全分區
# ═══════════════════════════════════════════


class TestSafetyZones:
    """Scenario: 修復動作安全分區."""

    def test_green_zone_count(self):
        """GREEN 區有 5 個動作."""
        assert len(GREEN_ZONE_ACTIONS) == 5

    def test_yellow_zone_count(self):
        """YELLOW 區有 3 個動作."""
        assert len(YELLOW_ZONE_ACTIONS) == 3

    def test_red_zone_count(self):
        """RED 區有 2 個動作."""
        assert len(RED_ZONE_ACTIONS) == 2

    def test_no_overlap(self):
        """三區不重疊."""
        assert GREEN_ZONE_ACTIONS & YELLOW_ZONE_ACTIONS == set()
        assert GREEN_ZONE_ACTIONS & RED_ZONE_ACTIONS == set()
        assert YELLOW_ZONE_ACTIONS & RED_ZONE_ACTIONS == set()

    def test_green_includes_start_gateway(self):
        """重啟 Gateway 是 GREEN."""
        assert "start_gateway" in GREEN_ZONE_ACTIONS

    def test_green_includes_rotate_logs(self):
        """清理日誌是 GREEN."""
        assert "rotate_logs" in GREEN_ZONE_ACTIONS

    def test_yellow_includes_recreate_venv(self):
        """重建 venv 是 YELLOW."""
        assert "recreate_venv" in YELLOW_ZONE_ACTIONS

    def test_red_includes_rebuild_dashboard(self):
        """重建 Dashboard 是 RED."""
        assert "rebuild_dashboard" in RED_ZONE_ACTIONS

    def test_classify_zone_green(self):
        diag = SelfDiagnosis()
        assert diag._classify_zone("start_gateway") == "green"

    def test_classify_zone_yellow(self):
        diag = SelfDiagnosis()
        assert diag._classify_zone("recreate_venv") == "yellow"

    def test_classify_zone_red(self):
        diag = SelfDiagnosis()
        assert diag._classify_zone("rebuild_dashboard") == "red"

    def test_classify_zone_empty(self):
        diag = SelfDiagnosis()
        assert diag._classify_zone("") == ""

    def test_classify_zone_restart_tool(self):
        """restart_tool:xxx 格式歸 GREEN."""
        diag = SelfDiagnosis()
        assert diag._classify_zone("restart_tool:searxng") == "green"

    def test_classify_zone_unknown(self):
        """未知動作返回空字串."""
        diag = SelfDiagnosis()
        assert diag._classify_zone("unknown_action") == ""


# ═══════════════════════════════════════════
# DiagnosisReport 資料模型
# ═══════════════════════════════════════════


class TestDiagnosisReport:
    """Scenario: 診斷報告."""

    def test_empty_report_is_ok(self):
        report = DiagnosisReport(all_ok=True)
        assert report.total_issues == 0
        assert report.critical_count == 0
        assert report.warning_count == 0

    def test_issue_counts(self):
        report = DiagnosisReport(issues=[
            DiagnosisIssue(name="A", severity="critical", message="bad"),
            DiagnosisIssue(name="B", severity="warning", message="meh"),
            DiagnosisIssue(name="C", severity="critical", message="worse"),
        ])
        assert report.total_issues == 3
        assert report.critical_count == 2
        assert report.warning_count == 1

    def test_to_dict(self):
        report = DiagnosisReport(
            timestamp="2026-02-28T10:00:00",
            all_ok=True,
        )
        d = report.to_dict()
        assert d["all_ok"] is True
        assert d["timestamp"] == "2026-02-28T10:00:00"
        assert "issues" in d
        assert "auto_repaired" in d

    def test_issue_to_dict(self):
        issue = DiagnosisIssue(
            name="test",
            severity="warning",
            message="test msg",
            repairable=True,
            repair_action="rotate_logs",
            zone="green",
        )
        d = issue.to_dict()
        assert d["name"] == "test"
        assert d["zone"] == "green"


# ═══════════════════════════════════════════
# SelfDiagnosis 核心
# ═══════════════════════════════════════════


class TestSelfDiagnosis:
    """Scenario: 自我診斷引擎."""

    @patch("museon.doctor.self_diagnosis.SelfDiagnosis._publish_event")
    def test_diagnose_all_ok(self, mock_publish, tmp_path):
        """全部正常時 all_ok=True."""
        with patch(
            "museon.doctor.health_check.HealthChecker"
        ) as MockChecker:
            mock_report = MagicMock()
            mock_report.checks = []
            MockChecker.return_value.run_all.return_value = mock_report

            with patch(
                "museon.tools.tool_registry.ToolRegistry"
            ) as MockReg:
                MockReg.return_value.check_all_health.return_value = {}

                diag = SelfDiagnosis(data_dir=str(tmp_path))
                report = diag.diagnose()

                assert report.all_ok is True
                assert report.total_issues == 0

    @patch("museon.doctor.self_diagnosis.SelfDiagnosis._publish_event")
    def test_diagnose_with_green_issue(self, mock_publish, tmp_path):
        """GREEN 區問題自動修復."""
        mock_check = MagicMock()
        mock_check.status.value = "warning"
        mock_check.name = "日誌大小"
        mock_check.message = "日誌過大"
        mock_check.repairable = True
        mock_check.repair_action = "rotate_logs"

        with patch(
            "museon.doctor.health_check.HealthChecker"
        ) as MockChecker:
            mock_report = MagicMock()
            mock_report.checks = [mock_check]
            MockChecker.return_value.run_all.return_value = mock_report

            with patch(
                "museon.tools.tool_registry.ToolRegistry"
            ) as MockReg:
                MockReg.return_value.check_all_health.return_value = {}

                with patch(
                    "museon.doctor.auto_repair.AutoRepair"
                ) as MockRepair:
                    repair_result = MagicMock()
                    repair_result.status.value = "success"
                    repair_result.message = "已清理"
                    MockRepair.return_value.execute.return_value = repair_result

                    diag = SelfDiagnosis(data_dir=str(tmp_path))
                    report = diag.diagnose(auto_repair=True)

                    assert len(report.auto_repaired) == 1
                    assert report.auto_repaired[0].success is True

    @patch("museon.doctor.self_diagnosis.SelfDiagnosis._publish_event")
    def test_diagnose_yellow_needs_confirm(self, mock_publish, tmp_path):
        """YELLOW 區問題需要確認."""
        mock_check = MagicMock()
        mock_check.status.value = "critical"
        mock_check.name = "venv"
        mock_check.message = "venv 損毀"
        mock_check.repairable = True
        mock_check.repair_action = "recreate_venv"

        with patch(
            "museon.doctor.health_check.HealthChecker"
        ) as MockChecker:
            mock_report = MagicMock()
            mock_report.checks = [mock_check]
            MockChecker.return_value.run_all.return_value = mock_report

            with patch(
                "museon.tools.tool_registry.ToolRegistry"
            ) as MockReg:
                MockReg.return_value.check_all_health.return_value = {}

                diag = SelfDiagnosis(data_dir=str(tmp_path))
                report = diag.diagnose(auto_repair=True)

                assert len(report.needs_confirm) == 1
                assert report.needs_confirm[0].name == "venv"

    @patch("museon.doctor.self_diagnosis.SelfDiagnosis._publish_event")
    def test_diagnose_red_needs_manual(self, mock_publish, tmp_path):
        """RED 區問題需要手動處理."""
        mock_check = MagicMock()
        mock_check.status.value = "critical"
        mock_check.name = "Dashboard"
        mock_check.message = "App 損壞"
        mock_check.repairable = True
        mock_check.repair_action = "rebuild_dashboard"

        with patch(
            "museon.doctor.health_check.HealthChecker"
        ) as MockChecker:
            mock_report = MagicMock()
            mock_report.checks = [mock_check]
            MockChecker.return_value.run_all.return_value = mock_report

            with patch(
                "museon.tools.tool_registry.ToolRegistry"
            ) as MockReg:
                MockReg.return_value.check_all_health.return_value = {}

                diag = SelfDiagnosis(data_dir=str(tmp_path))
                report = diag.diagnose(auto_repair=True)

                assert len(report.needs_manual) == 1
                assert report.needs_manual[0].name == "Dashboard"

    @patch("museon.doctor.self_diagnosis.SelfDiagnosis._publish_event")
    def test_diagnose_no_auto_repair(self, mock_publish, tmp_path):
        """auto_repair=False 不自動修復."""
        mock_check = MagicMock()
        mock_check.status.value = "warning"
        mock_check.name = "logs"
        mock_check.message = "大"
        mock_check.repairable = True
        mock_check.repair_action = "rotate_logs"

        with patch(
            "museon.doctor.health_check.HealthChecker"
        ) as MockChecker:
            mock_report = MagicMock()
            mock_report.checks = [mock_check]
            MockChecker.return_value.run_all.return_value = mock_report

            with patch(
                "museon.tools.tool_registry.ToolRegistry"
            ) as MockReg:
                MockReg.return_value.check_all_health.return_value = {}

                diag = SelfDiagnosis(data_dir=str(tmp_path))
                report = diag.diagnose(auto_repair=False)

                assert len(report.auto_repaired) == 0

    def test_diagnose_quick(self, tmp_path):
        """快速診斷只跑 3 項."""
        with patch(
            "museon.doctor.health_check.HealthChecker"
        ) as MockChecker:
            mock_instance = MockChecker.return_value
            ok_check = MagicMock()
            ok_check.status.value = "ok"
            mock_instance.check_gateway_process.return_value = ok_check
            mock_instance.check_gateway_health.return_value = ok_check
            mock_instance.check_disk_space.return_value = ok_check

            diag = SelfDiagnosis(data_dir=str(tmp_path))
            report = diag.diagnose_quick()

            assert report.all_ok is True
            assert report.duration_ms >= 0

    @patch("museon.doctor.self_diagnosis.SelfDiagnosis._publish_event")
    def test_healthchecker_failure_graceful(self, mock_publish, tmp_path):
        """HealthChecker 爆炸時降級."""
        with patch(
            "museon.doctor.health_check.HealthChecker",
            side_effect=RuntimeError("boom"),
        ):
            with patch(
                "museon.tools.tool_registry.ToolRegistry"
            ) as MockReg:
                MockReg.return_value.check_all_health.return_value = {}

                diag = SelfDiagnosis(data_dir=str(tmp_path))
                report = diag.diagnose()

                assert report.total_issues >= 1
                assert "健檢引擎" in report.issues[0].name


# ═══════════════════════════════════════════
# 自然語言格式化
# ═══════════════════════════════════════════


class TestFormatReport:
    """Scenario: 報告格式化為繁體中文."""

    def test_all_ok_message(self):
        report = DiagnosisReport(all_ok=True, duration_ms=42)
        diag = SelfDiagnosis()
        text = diag.format_report_zh(report)
        assert "正常" in text
        assert "42ms" in text

    def test_auto_repaired_message(self):
        report = DiagnosisReport(
            duration_ms=100,
            auto_repaired=[
                RepairResult(
                    action="rotate_logs",
                    success=True,
                    message="已清理日誌",
                ),
            ],
        )
        diag = SelfDiagnosis()
        text = diag.format_report_zh(report)
        assert "自動修復" in text
        assert "已清理日誌" in text

    def test_needs_confirm_message(self):
        report = DiagnosisReport(
            duration_ms=50,
            needs_confirm=[
                DiagnosisIssue(
                    name="venv",
                    severity="critical",
                    message="損毀",
                    repair_action="recreate_venv",
                ),
            ],
        )
        diag = SelfDiagnosis()
        text = diag.format_report_zh(report)
        assert "確認" in text
        assert "venv" in text

    def test_needs_manual_message(self):
        report = DiagnosisReport(
            duration_ms=50,
            needs_manual=[
                DiagnosisIssue(
                    name="磁碟",
                    severity="critical",
                    message="空間不足",
                ),
            ],
        )
        diag = SelfDiagnosis()
        text = diag.format_report_zh(report)
        assert "手動" in text
        assert "磁碟" in text

    def test_mixed_report(self):
        """混合報告包含所有區塊."""
        report = DiagnosisReport(
            duration_ms=200,
            auto_repaired=[
                RepairResult(action="x", success=True, message="ok"),
            ],
            needs_confirm=[
                DiagnosisIssue(
                    name="y", severity="warning", message="m",
                    repair_action="recreate_venv",
                ),
            ],
            needs_manual=[
                DiagnosisIssue(name="z", severity="critical", message="n"),
            ],
        )
        diag = SelfDiagnosis()
        text = diag.format_report_zh(report)
        assert "自動修復" in text
        assert "確認" in text
        assert "手動" in text


# ═══════════════════════════════════════════
# EventBus 整合
# ═══════════════════════════════════════════


class TestEventBusIntegration:
    """Scenario: 事件發布."""

    def test_self_diagnosis_events_defined(self):
        from museon.core.event_bus import (
            SELF_DIAGNOSIS_TRIGGERED,
            SELF_DIAGNOSIS_COMPLETED,
            SELF_REPAIR_EXECUTED,
        )
        assert SELF_DIAGNOSIS_TRIGGERED == "SELF_DIAGNOSIS_TRIGGERED"
        assert SELF_DIAGNOSIS_COMPLETED == "SELF_DIAGNOSIS_COMPLETED"
        assert SELF_REPAIR_EXECUTED == "SELF_REPAIR_EXECUTED"

    def test_diagnosis_publishes_completed_event(self, tmp_path):
        """diagnose() 結束後發布 SELF_DIAGNOSIS_COMPLETED."""
        from museon.core.event_bus import (
            _reset_event_bus, get_event_bus,
            SELF_DIAGNOSIS_COMPLETED,
        )
        _reset_event_bus()
        bus = get_event_bus()
        received = []
        bus.subscribe(SELF_DIAGNOSIS_COMPLETED, lambda d: received.append(d))

        with patch(
            "museon.doctor.health_check.HealthChecker"
        ) as MockChecker:
            mock_report = MagicMock()
            mock_report.checks = []
            MockChecker.return_value.run_all.return_value = mock_report

            with patch(
                "museon.tools.tool_registry.ToolRegistry"
            ) as MockReg:
                MockReg.return_value.check_all_health.return_value = {}

                diag = SelfDiagnosis(data_dir=str(tmp_path))
                diag.diagnose()

        assert len(received) == 1
        assert received[0]["all_ok"] is True
        _reset_event_bus()


# ═══════════════════════════════════════════
# Tool Restart
# ═══════════════════════════════════════════


class TestToolRestart:
    """Scenario: 工具重啟."""

    def test_restart_tool_success(self, tmp_path):
        """成功重啟工具容器."""
        diag = SelfDiagnosis(data_dir=str(tmp_path))

        with patch(
            "museon.tools.tool_registry.ToolRegistry"
        ) as MockReg:
            mock_reg = MockReg.return_value
            mock_reg._stop_tool.return_value = None
            mock_reg._start_tool.return_value = True

            result = diag._restart_tool("searxng")
            assert result.success is True
            assert "searxng" in result.message

    def test_restart_tool_failure(self, tmp_path):
        """重啟失敗."""
        diag = SelfDiagnosis(data_dir=str(tmp_path))

        with patch(
            "museon.tools.tool_registry.ToolRegistry"
        ) as MockReg:
            mock_reg = MockReg.return_value
            mock_reg._stop_tool.return_value = None
            mock_reg._start_tool.return_value = False

            result = diag._restart_tool("searxng")
            assert result.success is False

    def test_restart_tool_exception(self, tmp_path):
        """重啟拋異常."""
        diag = SelfDiagnosis(data_dir=str(tmp_path))

        with patch(
            "museon.tools.tool_registry.ToolRegistry",
            side_effect=RuntimeError("boom"),
        ):
            result = diag._restart_tool("searxng")
            assert result.success is False
            assert "boom" in result.message


# ═══════════════════════════════════════════
# Brain 整合
# ═══════════════════════════════════════════


class TestBrainIntegration:
    """Scenario: Brain 自我檢查意圖整合."""

    def test_brain_imports_self_diagnosis(self):
        """brain.py 可以 import self_diagnosis 模組."""
        from museon.doctor.self_diagnosis import (
            detect_self_check_intent,
            SelfDiagnosis,
        )
        assert callable(detect_self_check_intent)
        assert callable(SelfDiagnosis)

    def test_detect_self_check_in_conversation(self):
        """對話中的自我檢查語句被正確辨識."""
        test_cases = [
            ("幫我做個自我檢查", True),
            ("系統狀態如何？", True),
            ("你是不是壞了，幫我看看", True),
            ("今天的天氣怎麼樣", False),
            ("幫我寫一段程式碼", False),
        ]
        for msg, expected in test_cases:
            result = detect_self_check_intent(msg)
            assert result == expected, f"Failed for: {msg}"
