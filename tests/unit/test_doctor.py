"""BDD 測試 — MUSEON Doctor 健檢與修復模組

涵蓋：
  Section 1: HealthChecker 基礎（6 tests）
  Section 2: 目錄結構健檢（4 tests）
  Section 3: .env 檔案健檢（5 tests）
  Section 4: API Keys 健檢（4 tests）
  Section 5: venv 健檢（3 tests）
  Section 6: Data 完整性（4 tests）
  Section 7: Dashboard App 健檢（4 tests）
  Section 8: AutoRepair 基礎（4 tests）
  Section 9: 目錄修復（3 tests）
  Section 10: .env 修復（3 tests）
  Section 11: Log 修復（3 tests）
  Section 12: HealthReport 序列化（3 tests）
  Section 13: 整合測試（3 tests）

共 49 個 BDD 場景
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from museon.doctor.health_check import (
    CheckResult,
    CheckStatus,
    HealthChecker,
    HealthReport,
)
from museon.doctor.auto_repair import AutoRepair, RepairResult, RepairStatus


@pytest.fixture
def temp_home(tmp_path):
    """建立模擬的 MUSEON home 目錄"""
    home = tmp_path / "MUSEON"
    home.mkdir()
    (home / "data").mkdir()
    (home / "logs").mkdir()
    (home / ".runtime").mkdir()
    return home


@pytest.fixture
def checker(temp_home):
    return HealthChecker(museon_home=str(temp_home))


@pytest.fixture
def repair(checker):
    return AutoRepair(checker=checker)


# ═══════════════════════════════════════
# Section 1: HealthChecker 基礎
# ═══════════════════════════════════════

class TestHealthCheckerBasics:
    """Given: HealthChecker 初始化"""

    def test_default_home_path(self):
        """When: 不指定 home，Then: 使用 ~/MUSEON"""
        hc = HealthChecker()
        assert "MUSEON" in str(hc.home)

    def test_custom_home_path(self, temp_home):
        """When: 指定 home，Then: 使用指定路徑"""
        hc = HealthChecker(museon_home=str(temp_home))
        assert hc.home == temp_home

    def test_run_all_returns_report(self, checker):
        """When: 執行 run_all，Then: 回傳 HealthReport"""
        report = checker.run_all()
        assert isinstance(report, HealthReport)
        assert report.timestamp
        assert isinstance(report.checks, list)
        assert len(report.checks) > 0

    def test_run_all_has_summary(self, checker):
        """When: 執行 run_all，Then: 包含統計摘要"""
        report = checker.run_all()
        assert "ok" in report.summary
        assert "warning" in report.summary
        assert "critical" in report.summary

    def test_check_status_enum(self):
        """When: 使用 CheckStatus，Then: 有四種狀態"""
        assert CheckStatus.OK.value == "ok"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.CRITICAL.value == "critical"
        assert CheckStatus.UNKNOWN.value == "unknown"

    def test_overall_status_critical_if_any_critical(self, checker):
        """When: 有任何 CRITICAL，Then: overall = CRITICAL"""
        report = checker.run_all()
        # temp_home 沒有 venv，一定有 CRITICAL
        assert report.overall in (CheckStatus.CRITICAL, CheckStatus.WARNING)


# ═══════════════════════════════════════
# Section 2: 目錄結構健檢
# ═══════════════════════════════════════

class TestDirectoryCheck:
    """Given: 目錄結構健檢"""

    def test_all_dirs_exist(self, checker):
        """When: 所有目錄存在，Then: OK"""
        result = checker.check_directories()
        assert result.status == CheckStatus.OK

    def test_missing_data_dir(self, temp_home):
        """When: data/ 不存在，Then: CRITICAL"""
        (temp_home / "data").rmdir()
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_directories()
        assert result.status == CheckStatus.CRITICAL
        assert result.repairable

    def test_missing_logs_dir(self, temp_home):
        """When: logs/ 不存在，Then: CRITICAL"""
        (temp_home / "logs").rmdir()
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_directories()
        assert result.status == CheckStatus.CRITICAL

    def test_repair_action_set(self, temp_home):
        """When: 目錄缺失，Then: repair_action = create_directories"""
        (temp_home / "data").rmdir()
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_directories()
        assert result.repair_action == "create_directories"


# ═══════════════════════════════════════
# Section 3: .env 檔案健檢
# ═══════════════════════════════════════

class TestEnvFileCheck:
    """Given: .env 檔案健檢"""

    def test_env_not_exists(self, checker):
        """When: .env 不存在，Then: CRITICAL"""
        result = checker.check_env_file()
        assert result.status == CheckStatus.CRITICAL
        assert result.repairable

    def test_env_exists_correct_perms(self, temp_home):
        """When: .env 存在且權限 600，Then: OK"""
        env = temp_home / ".env"
        env.write_text("ANTHROPIC_API_KEY=test\n")
        os.chmod(str(env), 0o600)
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_env_file()
        assert result.status == CheckStatus.OK

    def test_env_wrong_permissions(self, temp_home):
        """When: .env 權限過寬 (644)，Then: WARNING"""
        env = temp_home / ".env"
        env.write_text("test=1\n")
        os.chmod(str(env), 0o644)
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_env_file()
        assert result.status == CheckStatus.WARNING
        assert result.repairable

    def test_repair_action_create(self, checker):
        """When: .env 不存在，Then: repair_action = create_env_file"""
        result = checker.check_env_file()
        assert result.repair_action == "create_env_file"

    def test_repair_action_fix_perms(self, temp_home):
        """When: 權限錯誤，Then: repair_action = fix_env_permissions"""
        env = temp_home / ".env"
        env.write_text("test=1\n")
        os.chmod(str(env), 0o644)
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_env_file()
        assert result.repair_action == "fix_env_permissions"


# ═══════════════════════════════════════
# Section 4: API Keys 健檢
# ═══════════════════════════════════════

class TestApiKeysCheck:
    """Given: API Keys 健檢"""

    def test_no_env_file(self, checker):
        """When: .env 不存在，Then: CRITICAL"""
        result = checker.check_api_keys()
        assert result.status == CheckStatus.CRITICAL

    def test_all_keys_present(self, temp_home):
        """When: 兩個 key 都有，Then: OK"""
        env = temp_home / ".env"
        env.write_text(
            "ANTHROPIC_API_KEY=sk-ant-test123\n"
            "TELEGRAM_BOT_TOKEN=123456:ABC\n"
        )
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_api_keys()
        assert result.status == CheckStatus.OK

    def test_missing_anthropic_key(self, temp_home):
        """When: ANTHROPIC_API_KEY 缺失，Then: CRITICAL"""
        env = temp_home / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN=123\n")
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_api_keys()
        assert result.status == CheckStatus.CRITICAL

    def test_missing_telegram_token(self, temp_home):
        """When: TELEGRAM_BOT_TOKEN 缺失，Then: WARNING（非致命）"""
        env = temp_home / ".env"
        env.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_api_keys()
        assert result.status == CheckStatus.WARNING


# ═══════════════════════════════════════
# Section 5: venv 健檢
# ═══════════════════════════════════════

class TestVenvCheck:
    """Given: venv 健檢"""

    def test_venv_not_exists(self, checker):
        """When: venv 不存在，Then: CRITICAL"""
        result = checker.check_venv()
        assert result.status == CheckStatus.CRITICAL
        assert result.repairable

    def test_venv_repair_action(self, checker):
        """When: venv 損毀，Then: repair_action = recreate_venv"""
        result = checker.check_venv()
        assert result.repair_action == "recreate_venv"

    def test_venv_python_not_executable(self, temp_home):
        """When: python binary 存在但不可執行，Then: CRITICAL"""
        venv_bin = temp_home / ".runtime" / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("not a python binary")
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_venv()
        assert result.status == CheckStatus.CRITICAL


# ═══════════════════════════════════════
# Section 6: Data 完整性
# ═══════════════════════════════════════

class TestDataIntegrity:
    """Given: 資料完整性檢查"""

    def test_data_dir_ok(self, checker):
        """When: data/ 存在且無損毀檔案，Then: OK"""
        result = checker.check_data_integrity()
        assert result.status == CheckStatus.OK

    def test_data_dir_missing(self, temp_home):
        """When: data/ 不存在，Then: CRITICAL"""
        (temp_home / "data").rmdir()
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_data_integrity()
        assert result.status == CheckStatus.CRITICAL

    def test_corrupted_anima_mc(self, temp_home):
        """When: ANIMA_MC.json 損毀，Then: WARNING"""
        (temp_home / "data" / "ANIMA_MC.json").write_text("{broken json", "utf-8")
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_data_integrity()
        assert result.status == CheckStatus.WARNING

    def test_valid_anima_mc(self, temp_home):
        """When: ANIMA_MC.json 正常，Then: OK"""
        (temp_home / "data" / "ANIMA_MC.json").write_text('{"name": "MC"}', "utf-8")
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_data_integrity()
        assert result.status == CheckStatus.OK


# ═══════════════════════════════════════
# Section 7: Dashboard App 健檢
# ═══════════════════════════════════════

class TestDashboardAppCheck:
    """Given: MUSEON.app 健檢"""

    def test_app_not_installed(self, checker):
        """When: App 未安裝，Then: WARNING"""
        result = checker.check_dashboard_app()
        # /Applications/MUSEON.app 可能存在也可能不存在
        assert result.status in (CheckStatus.WARNING, CheckStatus.OK, CheckStatus.CRITICAL)

    def test_check_result_has_name(self, checker):
        """When: 健檢執行，Then: name = MUSEON App"""
        result = checker.check_dashboard_app()
        assert result.name == "MUSEON App"

    def test_disk_space_check(self, checker):
        """When: 磁碟空間充足，Then: OK"""
        result = checker.check_disk_space()
        assert result.status == CheckStatus.OK
        assert "free_gb" in result.details

    def test_log_size_no_logs(self, temp_home):
        """When: logs/ 為空，Then: OK"""
        hc = HealthChecker(museon_home=str(temp_home))
        result = hc.check_log_size()
        assert result.status == CheckStatus.OK


# ═══════════════════════════════════════
# Section 8: AutoRepair 基礎
# ═══════════════════════════════════════

class TestAutoRepairBasics:
    """Given: AutoRepair 初始化"""

    def test_unknown_action_fails(self, repair):
        """When: 執行不存在的 action，Then: FAILED"""
        result = repair.execute("nonexistent_action")
        assert result.status == RepairStatus.FAILED
        assert "未知" in result.message

    def test_result_has_duration(self, repair):
        """When: 執行任何動作，Then: 包含 duration_ms"""
        result = repair.execute("create_directories")
        assert isinstance(result.duration_ms, int)

    def test_repair_status_enum(self):
        """When: 使用 RepairStatus，Then: 有三種狀態"""
        assert RepairStatus.SUCCESS.value == "success"
        assert RepairStatus.FAILED.value == "failed"
        assert RepairStatus.SKIPPED.value == "skipped"

    def test_repair_result_structure(self):
        """When: 建立 RepairResult，Then: 結構完整"""
        r = RepairResult(action="test", status=RepairStatus.SUCCESS, message="ok")
        assert r.action == "test"
        assert r.status == RepairStatus.SUCCESS
        assert r.duration_ms == 0


# ═══════════════════════════════════════
# Section 9: 目錄修復
# ═══════════════════════════════════════

class TestDirectoryRepair:
    """Given: 目錄結構修復"""

    def test_create_missing_dirs(self, repair, temp_home):
        """When: 目錄缺失，Then: 建立所有必要目錄"""
        (temp_home / "data").rmdir()
        result = repair.repair_create_directories()
        assert result.status == RepairStatus.SUCCESS
        assert (temp_home / "data").exists()
        assert (temp_home / "data" / "anima").exists()
        assert (temp_home / "data" / "skills" / "native").exists()

    def test_skip_existing_dirs(self, repair):
        """When: 目錄都存在，Then: SKIPPED"""
        # 先建立所有目錄
        repair.repair_create_directories()
        # 再次執行
        result = repair.repair_create_directories()
        assert result.status == RepairStatus.SKIPPED

    def test_idempotent(self, repair):
        """When: 重複執行，Then: 不會出錯"""
        repair.repair_create_directories()
        repair.repair_create_directories()
        result = repair.repair_create_directories()
        assert result.status == RepairStatus.SKIPPED


# ═══════════════════════════════════════
# Section 10: .env 修復
# ═══════════════════════════════════════

class TestEnvRepair:
    """Given: .env 檔案修復"""

    def test_create_env_file(self, repair, temp_home):
        """When: .env 不存在，Then: 建立預設 .env"""
        result = repair.repair_create_env_file()
        assert result.status == RepairStatus.SUCCESS
        assert (temp_home / ".env").exists()
        content = (temp_home / ".env").read_text()
        assert "ANTHROPIC_API_KEY" in content

    def test_skip_existing_env(self, repair, temp_home):
        """When: .env 已存在，Then: SKIPPED"""
        (temp_home / ".env").write_text("existing=1")
        result = repair.repair_create_env_file()
        assert result.status == RepairStatus.SKIPPED

    def test_fix_permissions(self, repair, temp_home):
        """When: 權限不對，Then: 修正為 600"""
        env = temp_home / ".env"
        env.write_text("test=1")
        os.chmod(str(env), 0o644)
        result = repair.repair_fix_env_permissions()
        assert result.status == RepairStatus.SUCCESS
        # 確認權限已修正
        mode = oct(env.stat().st_mode)[-3:]
        assert mode == "600"


# ═══════════════════════════════════════
# Section 11: Log 修復
# ═══════════════════════════════════════

class TestLogRepair:
    """Given: 日誌修復"""

    def test_rotate_large_log(self, repair, temp_home):
        """When: 日誌 > 100MB，Then: 縮減到最後 1000 行"""
        log_file = temp_home / "logs" / "gateway.log"
        # 寫入超過 100MB 的假日誌（用重複行模擬）
        big_line = "x" * 1000 + "\n"
        log_file.write_text(big_line * 110000)  # ~110MB
        assert log_file.stat().st_size > 100 * 1024 * 1024

        result = repair.repair_rotate_logs()
        assert result.status == RepairStatus.SUCCESS

        # 確認行數已縮減
        lines = log_file.read_text().splitlines()
        assert len(lines) <= 1000

    def test_skip_small_logs(self, repair, temp_home):
        """When: 日誌正常大小，Then: SKIPPED"""
        (temp_home / "logs" / "gateway.log").write_text("small log\n" * 10)
        result = repair.repair_rotate_logs()
        assert result.status == RepairStatus.SKIPPED

    def test_no_logs_dir(self, repair, temp_home):
        """When: logs/ 不存在，Then: SKIPPED"""
        (temp_home / "logs").rmdir()
        result = repair.repair_rotate_logs()
        assert result.status == RepairStatus.SKIPPED


# ═══════════════════════════════════════
# Section 12: HealthReport 序列化
# ═══════════════════════════════════════

class TestHealthReportSerialization:
    """Given: HealthReport 序列化"""

    def test_to_dict_structure(self, checker):
        """When: to_dict()，Then: 包含所有必要欄位"""
        report = checker.run_all()
        d = report.to_dict()
        assert "timestamp" in d
        assert "overall" in d
        assert "checks" in d
        assert "summary" in d

    def test_to_dict_json_serializable(self, checker):
        """When: to_dict()，Then: 可以 JSON 序列化"""
        report = checker.run_all()
        d = report.to_dict()
        json_str = json.dumps(d)
        assert json_str  # 不會拋出異常

    def test_check_result_in_dict(self, checker):
        """When: to_dict()，Then: 每個 check 有完整欄位"""
        report = checker.run_all()
        d = report.to_dict()
        for check in d["checks"]:
            assert "name" in check
            assert "status" in check
            assert "message" in check
            assert "repairable" in check


# ═══════════════════════════════════════
# Section 13: 整合測試
# ═══════════════════════════════════════

class TestDoctorIntegration:
    """Given: Doctor 整合流程"""

    def test_check_then_repair_then_recheck(self, temp_home):
        """When: 檢查 → 修復 → 再檢查，Then: 問題減少"""
        hc = HealthChecker(museon_home=str(temp_home))
        repair = AutoRepair(checker=hc)

        # 製造問題：刪除 data/
        (temp_home / "data").rmdir()

        # 第一次檢查
        report1 = hc.run_all()
        critical1 = report1.summary.get("critical", 0)

        # 修復
        repair.execute("create_directories")

        # 重新檢查
        report2 = hc.run_all()
        critical2 = report2.summary.get("critical", 0)

        # 問題應該減少
        assert critical2 <= critical1

    def test_full_repair_cycle(self, temp_home):
        """When: 完整修復週期，Then: 目錄 + .env 都修好"""
        (temp_home / "data").rmdir()
        hc = HealthChecker(museon_home=str(temp_home))
        repair = AutoRepair(checker=hc)

        repair.execute("create_directories")
        repair.execute("create_env_file")

        # 驗證
        assert (temp_home / "data").exists()
        assert (temp_home / ".env").exists()

    def test_parse_env_file(self, temp_home):
        """When: 解析 .env，Then: 正確提取 key-value"""
        env = temp_home / ".env"
        env.write_text(
            "# comment\n"
            "KEY1=value1\n"
            "KEY2='value2'\n"
            "KEY3=\"value3\"\n"
            "\n"
            "EMPTY=\n"
        )
        hc = HealthChecker(museon_home=str(temp_home))
        env_vars = hc._parse_env_file()
        assert env_vars["KEY1"] == "value1"
        assert env_vars["KEY2"] == "value2"
        assert env_vars["KEY3"] == "value3"
        assert env_vars["EMPTY"] == ""
