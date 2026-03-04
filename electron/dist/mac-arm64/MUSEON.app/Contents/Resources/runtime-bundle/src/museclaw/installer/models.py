"""安裝流程的資料模型"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Dict


class StepStatus(Enum):
    """安裝步驟的狀態"""
    PENDING = "pending"
    SUCCESS = "success"
    WARNING = "warning"      # 非致命問題，安裝可繼續
    SKIPPED = "skipped"      # 刻意跳過（例如沒有 Node.js 跳過 Dashboard）
    FAILED = "failed"        # 致命錯誤，需人工介入


@dataclass
class StepResult:
    """單一安裝步驟的結果"""
    step_name: str
    status: StepStatus
    message: str
    details: Optional[Dict] = None

    @property
    def is_ok(self) -> bool:
        """SUCCESS, WARNING, SKIPPED 都算「可繼續」"""
        return self.status in (StepStatus.SUCCESS, StepStatus.WARNING, StepStatus.SKIPPED)

    @property
    def is_fatal(self) -> bool:
        return self.status == StepStatus.FAILED


@dataclass
class SystemInfo:
    """系統環境資訊"""
    os_type: str = ""               # "darwin"
    arch: str = ""                  # "arm64" or "x86_64"
    python_path: Optional[str] = None
    python_version: Optional[str] = None
    node_path: Optional[str] = None
    node_version: Optional[str] = None
    has_npm: bool = False
    has_brew: bool = False
    disk_free_mb: int = 0


@dataclass
class InstallConfig:
    """安裝設定

    install_dir: 使用者看到的根目錄（~/MuseClaw）
                 包含 .env, data/, logs/
    project_dir: 系統核心目錄（~/MuseClaw/.runtime）
                 包含 src/, .venv/, electron/, pyproject.toml
    """
    install_dir: Path
    project_dir: Path = field(init=False)
    venv_dir: Path = field(init=False)
    electron_dir: Path = field(init=False)
    data_dir: Path = field(init=False)
    log_dir: Path = field(init=False)
    env_file: Path = field(init=False)
    plist_name: str = "com.museclaw.gateway"
    plist_dir: Path = field(init=False)
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8765
    min_disk_mb: int = 500

    def __post_init__(self):
        self.project_dir = self.install_dir / ".runtime"
        self.venv_dir = self.project_dir / ".venv"
        self.electron_dir = self.project_dir / "electron"
        self.data_dir = self.install_dir / "data"
        self.log_dir = self.install_dir / "logs"
        self.env_file = self.install_dir / ".env"
        self.plist_dir = Path.home() / "Library" / "LaunchAgents"

    @property
    def plist_path(self) -> Path:
        return self.plist_dir / f"{self.plist_name}.plist"

    @property
    def venv_python(self) -> Path:
        return self.venv_dir / "bin" / "python"

    @property
    def gateway_log(self) -> Path:
        return self.log_dir / "gateway.log"

    @property
    def gateway_err(self) -> Path:
        return self.log_dir / "gateway.err"
