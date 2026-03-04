"""
MUSEON 一鍵安裝模組測試

對應 features/installation.feature 的 29 個 Scenario
嚴格 TDD：先寫測試，再寫實作
"""

import os
import plistlib
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest

from museon.installer.models import StepStatus, StepResult, SystemInfo, InstallConfig


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

@pytest.fixture
def install_config(tmp_path):
    """建立臨時的 InstallConfig"""
    return InstallConfig(install_dir=tmp_path)


@pytest.fixture
def temp_env_file(tmp_path):
    """臨時 .env 檔案路徑"""
    return tmp_path / ".env"


# ═══════════════════════════════════════
# Section 1: 環境檢查 (Scenarios 1-7)
# ═══════════════════════════════════════

class TestEnvironmentChecker:
    """對應 features/installation.feature Section 1"""

    def test_check_os_macos(self):
        """Scenario: macOS 環境確認"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        with patch("platform.system", return_value="Darwin"):
            result = checker.check_os()

        assert result.status == StepStatus.SUCCESS
        assert "macOS" in result.message

    def test_check_os_not_macos(self):
        """macOS 以外的系統應該失敗"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        with patch("platform.system", return_value="Linux"):
            result = checker.check_os()

        assert result.status == StepStatus.FAILED

    def test_detect_arch_arm64(self):
        """偵測 Apple Silicon"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        with patch("platform.machine", return_value="arm64"):
            arch = checker.detect_arch()

        assert arch == "arm64"

    def test_detect_arch_x86(self):
        """偵測 Intel Mac"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        with patch("platform.machine", return_value="x86_64"):
            arch = checker.detect_arch()

        assert arch == "x86_64"

    def test_find_python_success(self):
        """Scenario: Python 3.11+ 偵測 — 已安裝"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Python 3.13.12\n"

        with patch("shutil.which", return_value="/opt/homebrew/bin/python3.13"), \
             patch("subprocess.run", return_value=mock_result):
            path, version = checker.find_python()

        assert path is not None
        assert "3.13" in version

    def test_find_python_version_too_old(self):
        """Scenario: Python 版本不足 — 引導安裝"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        # 所有候選 Python 都找不到
        with patch("shutil.which", return_value=None):
            path, version = checker.find_python()

        assert path is None
        assert version is None

    def test_find_node_success(self):
        """Scenario: Node.js 偵測 — 已安裝"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "v20.11.0\n"

        with patch("shutil.which", side_effect=lambda cmd: "/usr/local/bin/node" if cmd == "node" else "/usr/local/bin/npm" if cmd == "npm" else None), \
             patch("subprocess.run", return_value=mock_result):
            node_path, has_npm = checker.find_node()

        assert node_path is not None
        assert has_npm is True

    def test_find_node_missing(self):
        """Scenario: Node.js 缺失 — 可降級繼續"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        with patch("shutil.which", return_value=None):
            node_path, has_npm = checker.find_node()

        assert node_path is None
        assert has_npm is False

    def test_check_disk_space_sufficient(self):
        """Scenario: 磁碟空間檢查 — 足夠"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        # 50GB free
        mock_usage = MagicMock()
        mock_usage.free = 50_000 * 1024 * 1024  # 50000 MB in bytes

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = checker.check_disk_space(Path("/"), min_mb=500)

        assert result.status == StepStatus.SUCCESS

    def test_check_disk_space_insufficient(self):
        """Scenario: 磁碟空間不足 — 警告"""
        from museon.installer.environment import EnvironmentChecker

        checker = EnvironmentChecker()
        # 200MB free
        mock_usage = MagicMock()
        mock_usage.free = 200 * 1024 * 1024

        with patch("shutil.disk_usage", return_value=mock_usage):
            result = checker.check_disk_space(Path("/"), min_mb=500)

        assert result.status == StepStatus.WARNING
        assert "200" in result.message or "500" in result.message


# ═══════════════════════════════════════
# Section 2: Python 環境建置 (Scenarios 8-11)
# ═══════════════════════════════════════

class TestPythonEnvironmentSetup:
    """對應 features/installation.feature Section 2"""

    def test_create_venv_new(self, install_config):
        """Scenario: 虛擬環境建立 — 全新安裝"""
        from museon.installer.python_env import PythonEnvironmentSetup

        setup = PythonEnvironmentSetup()
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = setup.create_venv("/opt/homebrew/bin/python3.13", install_config.venv_dir)

        assert result.status == StepStatus.SUCCESS

    def test_venv_exists(self, install_config):
        """Scenario: 虛擬環境已存在 — 重用"""
        from museon.installer.python_env import PythonEnvironmentSetup

        # 建立假的 .venv 目錄
        install_config.venv_dir.mkdir(parents=True)
        (install_config.venv_dir / "bin").mkdir()
        (install_config.venv_dir / "bin" / "python").touch()

        setup = PythonEnvironmentSetup()
        assert setup.venv_exists(install_config.venv_dir) is True

    def test_venv_not_exists(self, install_config):
        """沒有 .venv 目錄"""
        from museon.installer.python_env import PythonEnvironmentSetup

        setup = PythonEnvironmentSetup()
        assert setup.venv_exists(install_config.venv_dir) is False

    def test_install_dependencies_success(self, install_config):
        """Scenario: pip install 依賴安裝 — 成功"""
        from museon.installer.python_env import PythonEnvironmentSetup

        setup = PythonEnvironmentSetup()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Successfully installed museon"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = setup.install_dependencies(install_config.venv_python, install_config.project_dir)

        assert result.status == StepStatus.SUCCESS

    def test_install_dependencies_failure(self, install_config):
        """Scenario: pip install 失敗 — 網路問題"""
        from museon.installer.python_env import PythonEnvironmentSetup

        setup = PythonEnvironmentSetup()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "ERROR: Could not find a version that satisfies"

        with patch("subprocess.run", return_value=mock_result):
            result = setup.install_dependencies(install_config.venv_python, install_config.project_dir)

        assert result.status == StepStatus.FAILED
        assert "網路" in result.message or "pip" in result.message.lower()


# ═══════════════════════════════════════
# Section 3: 模組驗證 (Scenarios 12-13)
# ═══════════════════════════════════════

class TestModuleVerifier:
    """對應 features/installation.feature Section 3"""

    def test_verify_all_modules_success(self):
        """Scenario: 四大核心模組驗證 — 全部通過"""
        from museon.installer.module_verifier import ModuleVerifier

        verifier = ModuleVerifier()

        mock_module = MagicMock()
        with patch("importlib.import_module", return_value=mock_module):
            results = verifier.verify_all()

        assert len(results) == 4
        assert all(r.status == StepStatus.SUCCESS for r in results)

    def test_verify_partial_failure(self):
        """Scenario: 部分模組驗證失敗 — 不中斷安裝"""
        from museon.installer.module_verifier import ModuleVerifier

        verifier = ModuleVerifier()

        def mock_import(name):
            if "memory" in name:
                raise ImportError(f"No module named '{name}'")
            return MagicMock()

        with patch("importlib.import_module", side_effect=mock_import):
            results = verifier.verify_all()

        success_count = sum(1 for r in results if r.status == StepStatus.SUCCESS)
        warning_count = sum(1 for r in results if r.status == StepStatus.WARNING)

        assert success_count == 3
        assert warning_count == 1
        # 所有結果都不應該是 FAILED（WARNING 表示可繼續）
        assert all(r.is_ok for r in results)

    def test_verify_single_module(self):
        """單一模組驗證"""
        from museon.installer.module_verifier import ModuleVerifier

        verifier = ModuleVerifier()
        mock_module = MagicMock()

        with patch("importlib.import_module", return_value=mock_module):
            result = verifier.verify_module("museon.gateway.server", "create_app")

        assert result.status == StepStatus.SUCCESS

    def test_verify_single_module_import_error(self):
        """單一模組 import 失敗"""
        from museon.installer.module_verifier import ModuleVerifier

        verifier = ModuleVerifier()

        with patch("importlib.import_module", side_effect=ImportError("No module")):
            result = verifier.verify_module("museon.gateway.server", "create_app")

        assert result.status == StepStatus.WARNING


# ═══════════════════════════════════════
# Section 4: Electron Dashboard (Scenarios 14-17)
# ═══════════════════════════════════════

class TestElectronPackager:
    """對應 features/installation.feature Section 4"""

    def test_npm_install_success(self, install_config):
        """npm install 成功"""
        from museon.installer.electron import ElectronPackager

        packager = ElectronPackager()
        mock_result = MagicMock()
        mock_result.returncode = 0

        install_config.electron_dir.mkdir(parents=True)

        with patch("subprocess.run", return_value=mock_result):
            result = packager.npm_install(install_config.electron_dir)

        assert result.status == StepStatus.SUCCESS

    def test_build_app_success(self, install_config):
        """Scenario: Electron Dashboard 打包 — 成功"""
        from museon.installer.electron import ElectronPackager

        packager = ElectronPackager()
        mock_result = MagicMock()
        mock_result.returncode = 0

        install_config.electron_dir.mkdir(parents=True)

        with patch("subprocess.run", return_value=mock_result):
            result = packager.build_app(install_config.electron_dir)

        assert result.status == StepStatus.SUCCESS

    def test_build_app_failure(self, install_config):
        """Scenario: Electron 打包失敗 — 降級繼續"""
        from museon.installer.electron import ElectronPackager

        packager = ElectronPackager()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: electron-builder failed"

        install_config.electron_dir.mkdir(parents=True)

        with patch("subprocess.run", return_value=mock_result):
            result = packager.build_app(install_config.electron_dir)

        # WARNING 而非 FAILED — Gateway 不受影響
        assert result.status == StepStatus.WARNING

    def test_find_app_bundle(self, install_config):
        """找到 .app bundle"""
        from museon.installer.electron import ElectronPackager

        packager = ElectronPackager()

        # 建立假的 .app 目錄
        app_dir = install_config.electron_dir / "dist" / "mac-arm64" / "MUSEON Dashboard.app"
        app_dir.mkdir(parents=True)

        found = packager.find_app_bundle(install_config.electron_dir)
        assert found is not None

    def test_find_app_bundle_not_found(self, install_config):
        """找不到 .app bundle"""
        from museon.installer.electron import ElectronPackager

        packager = ElectronPackager()
        install_config.electron_dir.mkdir(parents=True)

        found = packager.find_app_bundle(install_config.electron_dir)
        assert found is None

    def test_check_existing_install(self):
        """Scenario: 已有安裝 — 詢問覆蓋"""
        from museon.installer.electron import ElectronPackager

        packager = ElectronPackager()

        with patch("pathlib.Path.exists", return_value=True):
            exists = packager.check_existing_install(Path("/Applications/MUSEON Dashboard.app"))

        assert exists is True


# ═══════════════════════════════════════
# Section 5: Gateway Daemon (Scenarios 18-22)
# ═══════════════════════════════════════

class TestDaemonConfigurator:
    """對應 features/installation.feature Section 5"""

    def test_generate_plist_structure(self, install_config):
        """Scenario: launchd plist 生成 — 結構正確"""
        from museon.installer.daemon import DaemonConfigurator

        configurator = DaemonConfigurator()
        plist_xml = configurator.generate_plist(install_config)

        # 用 plistlib 驗證是合法的 plist
        plist_data = plistlib.loads(plist_xml.encode("utf-8"))

        assert plist_data["Label"] == "com.museon.gateway"
        assert plist_data["RunAtLoad"] is True
        assert plist_data["ThrottleInterval"] == 5
        assert plist_data["ProcessType"] == "Background"

    def test_plist_program_arguments(self, install_config):
        """ProgramArguments 指向 .venv/bin/python"""
        from museon.installer.daemon import DaemonConfigurator

        configurator = DaemonConfigurator()
        plist_xml = configurator.generate_plist(install_config)
        plist_data = plistlib.loads(plist_xml.encode("utf-8"))

        args = plist_data["ProgramArguments"]
        assert str(install_config.venv_python) in args[0]
        assert "-m" in args
        assert "museon.gateway.server" in args

    def test_plist_environment_variables(self, install_config):
        """EnvironmentVariables 包含 PYTHONPATH 和 MUSEON_HOME"""
        from museon.installer.daemon import DaemonConfigurator

        configurator = DaemonConfigurator()
        plist_xml = configurator.generate_plist(install_config)
        plist_data = plistlib.loads(plist_xml.encode("utf-8"))

        env = plist_data["EnvironmentVariables"]
        assert "PYTHONPATH" in env
        assert "MUSEON_HOME" in env
        assert str(install_config.install_dir) in env["MUSEON_HOME"]

    def test_plist_path(self, install_config):
        """Scenario: launchd plist 路徑正確"""
        assert "Library/LaunchAgents" in str(install_config.plist_path)
        assert install_config.plist_name in str(install_config.plist_path)

    def test_unload_existing(self):
        """Scenario: 停止舊 daemon — 已有運行中"""
        from museon.installer.daemon import DaemonConfigurator

        configurator = DaemonConfigurator()
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = configurator.unload_existing("com.museon.gateway")

        assert result.status == StepStatus.SUCCESS
        call_args = mock_run.call_args[0][0]
        assert "launchctl" in call_args
        assert "unload" in call_args or "bootout" in call_args

    def test_load_daemon_success(self, install_config):
        """Scenario: Gateway daemon 啟動 — 成功"""
        from museon.installer.daemon import DaemonConfigurator

        configurator = DaemonConfigurator()
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = configurator.load_daemon(install_config.plist_path)

        assert result.status == StepStatus.SUCCESS

    def test_check_health_endpoint_success(self):
        """Gateway health endpoint 回應正常"""
        from museon.installer.daemon import DaemonConfigurator

        configurator = DaemonConfigurator()
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = configurator.check_health_endpoint(8765, timeout=3.0)

        # 不論成功或失敗都應該回傳結果（不拋例外）
        assert result.status in (StepStatus.SUCCESS, StepStatus.WARNING)


# ═══════════════════════════════════════
# Section 6: API Key 設定 (Scenarios 23-26)
# ═══════════════════════════════════════

class TestApiKeyConfigurator:
    """對應 features/installation.feature Section 6"""

    def test_write_telegram_token(self, temp_env_file):
        """Scenario: Telegram Bot Token 設定"""
        from museon.installer.api_keys import ApiKeyConfigurator

        config = ApiKeyConfigurator()
        result = config.write_key(temp_env_file, "TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")

        assert result.status == StepStatus.SUCCESS
        content = temp_env_file.read_text()
        assert "TELEGRAM_BOT_TOKEN=123456:ABC-DEF" in content

    def test_write_anthropic_key(self, temp_env_file):
        """Scenario: Anthropic API Key 設定"""
        from museon.installer.api_keys import ApiKeyConfigurator

        config = ApiKeyConfigurator()
        result = config.write_key(temp_env_file, "ANTHROPIC_API_KEY", "sk-ant-xxx")

        assert result.status == StepStatus.SUCCESS
        content = temp_env_file.read_text()
        assert "ANTHROPIC_API_KEY=sk-ant-xxx" in content

    def test_skip_api_key(self, temp_env_file):
        """Scenario: API Key 跳過 — 稍後設定"""
        from museon.installer.api_keys import ApiKeyConfigurator

        config = ApiKeyConfigurator()
        result = config.create_env_file(temp_env_file)

        assert result.status == StepStatus.SUCCESS
        assert temp_env_file.exists()

    def test_existing_env_preserved(self, temp_env_file):
        """Scenario: .env 檔案已存在 — 保留設定"""
        from museon.installer.api_keys import ApiKeyConfigurator

        # 預先寫入 token
        temp_env_file.write_text("TELEGRAM_BOT_TOKEN=existing-token\n")

        config = ApiKeyConfigurator()
        assert config.has_key(temp_env_file, "TELEGRAM_BOT_TOKEN") is True

    def test_env_key_not_exists(self, temp_env_file):
        """檢查不存在的 key"""
        from museon.installer.api_keys import ApiKeyConfigurator

        temp_env_file.write_text("# empty\n")

        config = ApiKeyConfigurator()
        assert config.has_key(temp_env_file, "TELEGRAM_BOT_TOKEN") is False


# ═══════════════════════════════════════
# Section 7: 編排器 (Scenarios 27-29)
# ═══════════════════════════════════════

class TestInstallationOrchestrator:
    """對應 features/installation.feature Section 7"""

    def test_full_install_all_success(self, install_config):
        """Scenario: 完整安裝流程 — 全部成功"""
        from museon.installer.orchestrator import InstallerOrchestrator

        # Mock 所有子元件
        orchestrator = InstallerOrchestrator(config=install_config, ui=None, interactive=False)

        with patch.object(orchestrator, "_step_environment", return_value=StepResult("環境檢查", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_python_env", return_value=StepResult("Python 環境", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_verify_modules", return_value=StepResult("模組驗證", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_electron", return_value=StepResult("Electron", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_daemon", return_value=StepResult("Daemon", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_api_keys", return_value=StepResult("API Keys", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_tools", return_value=StepResult("工具安裝", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_launch", return_value=StepResult("啟動", StepStatus.SUCCESS, "OK")):
            results = orchestrator.run()

        assert len(results) == 8
        assert all(r.status == StepStatus.SUCCESS for r in results)

    def test_partial_install_degraded(self, install_config):
        """Scenario: 部分安裝 — 降級完成"""
        from museon.installer.orchestrator import InstallerOrchestrator

        orchestrator = InstallerOrchestrator(config=install_config, ui=None, interactive=False)

        with patch.object(orchestrator, "_step_environment", return_value=StepResult("環境檢查", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_python_env", return_value=StepResult("Python 環境", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_verify_modules", return_value=StepResult("模組驗證", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_electron", return_value=StepResult("Electron", StepStatus.SKIPPED, "Node.js 不可用")), \
             patch.object(orchestrator, "_step_daemon", return_value=StepResult("Daemon", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_api_keys", return_value=StepResult("API Keys", StepStatus.SKIPPED, "使用者跳過")), \
             patch.object(orchestrator, "_step_tools", return_value=StepResult("工具安裝", StepStatus.SUCCESS, "OK")), \
             patch.object(orchestrator, "_step_launch", return_value=StepResult("啟動", StepStatus.SUCCESS, "OK")):
            results = orchestrator.run()

        # 全部都是「可繼續」的狀態
        assert all(r.is_ok for r in results)
        # 至少有兩個是 SKIPPED
        skipped = [r for r in results if r.status == StepStatus.SKIPPED]
        assert len(skipped) >= 2

    def test_fatal_error_stops_pipeline(self, install_config):
        """致命錯誤停止管線"""
        from museon.installer.orchestrator import InstallerOrchestrator

        orchestrator = InstallerOrchestrator(config=install_config, ui=None, interactive=False)

        with patch.object(orchestrator, "_step_environment", return_value=StepResult("環境檢查", StepStatus.FAILED, "不是 macOS")):
            results = orchestrator.run()

        # 只有第一步，後續被跳過
        assert len(results) == 1
        assert results[0].is_fatal

    def test_generate_summary(self, install_config):
        """最終報告生成"""
        from museon.installer.orchestrator import InstallerOrchestrator

        orchestrator = InstallerOrchestrator(config=install_config, ui=None, interactive=False)
        orchestrator.results = [
            StepResult("環境檢查", StepStatus.SUCCESS, "OK"),
            StepResult("Daemon", StepStatus.SUCCESS, "24/7 運行中"),
            StepResult("Electron", StepStatus.SKIPPED, "跳過"),
        ]

        summary = orchestrator.generate_summary()
        assert "成功" in summary or "安裝" in summary

    def test_day0_readiness(self, install_config):
        """Scenario: Day 0 就緒確認"""
        from museon.installer.orchestrator import InstallerOrchestrator

        orchestrator = InstallerOrchestrator(config=install_config, ui=None, interactive=False)
        orchestrator.results = [
            StepResult("Daemon", StepStatus.SUCCESS, "Gateway 運行中"),
        ]

        readiness = orchestrator.check_day0_readiness()
        assert "Telegram" in readiness or "命名儀式" in readiness
