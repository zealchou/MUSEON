"""Python 虛擬環境建置

對應 features/installation.feature Section 2
建立 venv、安裝依賴
"""

import subprocess
from pathlib import Path

from .models import StepResult, StepStatus


class PythonEnvironmentSetup:
    """Python 虛擬環境管理"""

    def venv_exists(self, venv_dir: Path) -> bool:
        """檢查 .venv 是否已存在且可用"""
        python_bin = venv_dir / "bin" / "python"
        return venv_dir.is_dir() and python_bin.exists()

    def create_venv(self, python_path: str, venv_dir: Path) -> StepResult:
        """建立 Python 虛擬環境

        Args:
            python_path: Python 執行檔路徑
            venv_dir: .venv 目錄路徑
        """
        try:
            result = subprocess.run(
                [python_path, "-m", "venv", str(venv_dir)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return StepResult(
                    step_name="虛擬環境",
                    status=StepStatus.SUCCESS,
                    message=f"已建立虛擬環境: {venv_dir}",
                )
            return StepResult(
                step_name="虛擬環境",
                status=StepStatus.FAILED,
                message=f"建立虛擬環境失敗: {result.stderr.strip()}",
            )
        except subprocess.TimeoutExpired:
            return StepResult(
                step_name="虛擬環境",
                status=StepStatus.FAILED,
                message="建立虛擬環境超時",
            )
        except OSError as e:
            return StepResult(
                step_name="虛擬環境",
                status=StepStatus.FAILED,
                message=f"建立虛擬環境失敗: {e}",
            )

    def install_dependencies(self, venv_python: Path, project_dir: Path) -> StepResult:
        """執行 pip install -e '.[dev]'

        Args:
            venv_python: .venv/bin/python 路徑
            project_dir: 專案根目錄
        """
        try:
            result = subprocess.run(
                [str(venv_python), "-m", "pip", "install", "-e", ".[dev]"],
                capture_output=True, text=True,
                cwd=str(project_dir),
                timeout=600,
            )
            if result.returncode == 0:
                return StepResult(
                    step_name="安裝依賴",
                    status=StepStatus.SUCCESS,
                    message="pip install 完成",
                    details={"stdout": result.stdout[-500:] if result.stdout else ""},
                )
            return StepResult(
                step_name="安裝依賴",
                status=StepStatus.FAILED,
                message=f"pip install 失敗，請檢查網路連線: {result.stderr.strip()[:200]}",
                details={"stderr": result.stderr},
            )
        except subprocess.TimeoutExpired:
            return StepResult(
                step_name="安裝依賴",
                status=StepStatus.FAILED,
                message="pip install 超時，請檢查網路連線",
            )
        except OSError as e:
            return StepResult(
                step_name="安裝依賴",
                status=StepStatus.FAILED,
                message=f"pip install 失敗: {e}",
            )
