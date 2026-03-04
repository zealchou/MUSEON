"""環境檢查元件

對應 features/installation.feature Section 1
檢查 macOS 系統、Python、Node.js、磁碟空間
"""

import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .models import StepResult, StepStatus, SystemInfo


class EnvironmentChecker:
    """系統環境檢查器"""

    # Python 候選路徑，依優先順序排列
    PYTHON_CANDIDATES = [
        "python3.13", "python3.12", "python3.11", "python3"
    ]

    MIN_PYTHON_VERSION = (3, 11)

    def check_os(self) -> StepResult:
        """檢查是否為 macOS"""
        os_name = platform.system()
        if os_name == "Darwin":
            return StepResult(
                step_name="環境檢查",
                status=StepStatus.SUCCESS,
                message=f"確認為 macOS ({os_name})",
            )
        return StepResult(
            step_name="環境檢查",
            status=StepStatus.FAILED,
            message=f"不支援的作業系統: {os_name}（僅支援 macOS）",
        )

    def detect_arch(self) -> str:
        """偵測處理器架構 (arm64 / x86_64)"""
        return platform.machine()

    def find_python(self) -> Tuple[Optional[str], Optional[str]]:
        """搜尋可用的 Python >= 3.11

        Returns:
            (python_path, version_string) 或 (None, None)
        """
        for candidate in self.PYTHON_CANDIDATES:
            path = shutil.which(candidate)
            if path is None:
                continue

            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    version_str = result.stdout.strip()  # "Python 3.13.12"
                    version_num = self._parse_version(version_str)
                    if version_num and version_num >= self.MIN_PYTHON_VERSION:
                        return path, version_str
            except (subprocess.TimeoutExpired, OSError):
                continue

        return None, None

    def find_node(self) -> Tuple[Optional[str], bool]:
        """搜尋 Node.js 和 npm

        Returns:
            (node_path, has_npm)
        """
        node_path = shutil.which("node")
        if node_path is None:
            return None, False

        try:
            result = subprocess.run(
                [node_path, "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return None, False
        except (subprocess.TimeoutExpired, OSError):
            return None, False

        has_npm = shutil.which("npm") is not None
        return node_path, has_npm

    def check_disk_space(self, path: Path, min_mb: int = 500) -> StepResult:
        """檢查磁碟可用空間

        Args:
            path: 要檢查的路徑
            min_mb: 最低需求 (MB)
        """
        usage = shutil.disk_usage(str(path))
        free_mb = usage.free // (1024 * 1024)

        if free_mb >= min_mb:
            return StepResult(
                step_name="磁碟空間",
                status=StepStatus.SUCCESS,
                message=f"可用空間 {free_mb} MB (最低需求 {min_mb} MB)",
            )
        return StepResult(
            step_name="磁碟空間",
            status=StepStatus.WARNING,
            message=f"磁碟空間不足: 可用 {free_mb} MB，建議至少 {min_mb} MB",
        )

    def collect_system_info(self) -> SystemInfo:
        """收集完整的系統環境資訊"""
        info = SystemInfo()
        info.os_type = platform.system().lower()
        info.arch = self.detect_arch()

        python_path, python_version = self.find_python()
        info.python_path = python_path
        info.python_version = python_version

        node_path, has_npm = self.find_node()
        info.node_path = node_path
        info.has_npm = has_npm

        info.has_brew = shutil.which("brew") is not None

        try:
            usage = shutil.disk_usage("/")
            info.disk_free_mb = int(usage.free // (1024 * 1024))
        except OSError:
            info.disk_free_mb = 0

        return info

    @staticmethod
    def _parse_version(version_str: str) -> Optional[Tuple[int, ...]]:
        """解析 'Python 3.13.12' → (3, 13, 12)"""
        try:
            parts = version_str.strip().split()[-1]  # "3.13.12"
            return tuple(int(x) for x in parts.split("."))
        except (ValueError, IndexError):
            return None
