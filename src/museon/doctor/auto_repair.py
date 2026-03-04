"""MUSEON Doctor — 自動修復引擎（Layer 2）

純 CPU 修復動作，零 Token。
每個修復動作都是冪等的（可安全重複執行）。
"""

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from .health_check import HealthChecker


class RepairStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RepairResult:
    action: str
    status: RepairStatus
    message: str
    duration_ms: int = 0


class AutoRepair:
    """自動修復引擎 — 純 CPU"""

    def __init__(self, checker: Optional[HealthChecker] = None):
        self.checker = checker or HealthChecker()
        self.home = self.checker.home
        self.runtime_dir = self.checker.runtime_dir
        self.data_dir = self.checker.data_dir
        self.logs_dir = self.checker.logs_dir
        self.env_path = self.checker.env_path
        self.venv_dir = self.checker.venv_dir

    def _find_project_dir(self) -> Path:
        """找到 pyproject.toml 所在的目錄（支援 dev 和 production 佈局）.

        Production: pyproject.toml 在 .runtime/ 內
        Dev:        pyproject.toml 在 home 根目錄
        """
        if (self.runtime_dir / "pyproject.toml").exists():
            return self.runtime_dir
        if (self.home / "pyproject.toml").exists():
            return self.home
        return self.runtime_dir  # fallback

    def _find_src_dir(self) -> Path:
        """找到 src/ 目錄（支援 dev 和 production 佈局）."""
        if (self.runtime_dir / "src").exists():
            return self.runtime_dir / "src"
        if (self.home / "src").exists():
            return self.home / "src"
        return self.runtime_dir / "src"  # fallback

    def _find_venv_python(self) -> Optional[Path]:
        """找到 venv 的 python（支援 dev 和 production 佈局）."""
        for venv in [self.venv_dir, self.home / ".venv"]:
            p = venv / "bin" / "python"
            if p.exists():
                return p
        return None

    def _find_venv_pip(self) -> Optional[Path]:
        """找到 venv 的 pip（支援 dev 和 production 佈局）."""
        for venv in [self.venv_dir, self.home / ".venv"]:
            p = venv / "bin" / "pip"
            if p.exists():
                return p
        return None

    def execute(self, action: str) -> RepairResult:
        """執行指定修復動作"""
        start = datetime.now()
        handler = getattr(self, f"repair_{action}", None)
        if not handler:
            return RepairResult(
                action=action,
                status=RepairStatus.FAILED,
                message=f"未知的修復動作: {action}",
            )

        try:
            result = handler()
            result.duration_ms = int(
                (datetime.now() - start).total_seconds() * 1000
            )
            return result
        except Exception as e:
            return RepairResult(
                action=action,
                status=RepairStatus.FAILED,
                message=f"修復失敗: {e}",
                duration_ms=int(
                    (datetime.now() - start).total_seconds() * 1000
                ),
            )

    # ─── 修復動作 ───

    def repair_create_directories(self) -> RepairResult:
        """建立必要目錄結構"""
        dirs = [
            self.home,
            self.data_dir,
            self.logs_dir,
            self.data_dir / "anima",
            self.data_dir / "lattice",
            self.data_dir / "eval",
            self.data_dir / "memory",
            self.data_dir / "skills" / "native",
            self.data_dir / "skills" / "forged",
        ]
        created = []
        for d in dirs:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
                created.append(str(d.relative_to(self.home)))

        if not created:
            return RepairResult(
                action="create_directories",
                status=RepairStatus.SKIPPED,
                message="所有目錄已存在",
            )
        return RepairResult(
            action="create_directories",
            status=RepairStatus.SUCCESS,
            message=f"已建立 {len(created)} 個目錄: {', '.join(created)}",
        )

    def repair_create_env_file(self) -> RepairResult:
        """建立預設 .env 檔案"""
        if self.env_path.exists():
            return RepairResult(
                action="create_env_file",
                status=RepairStatus.SKIPPED,
                message=".env 已存在",
            )

        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        self.env_path.write_text(
            "# MUSEON 設定檔\n"
            "# 請填入你的 API Keys\n\n"
            "ANTHROPIC_API_KEY=\n"
            "TELEGRAM_BOT_TOKEN=\n"
            "TELEGRAM_TRUSTED_IDS=\n",
            encoding="utf-8",
        )
        os.chmod(str(self.env_path), 0o600)

        return RepairResult(
            action="create_env_file",
            status=RepairStatus.SUCCESS,
            message="已建立 .env（請填入 API Keys）",
        )

    def repair_fix_env_permissions(self) -> RepairResult:
        """修復 .env 權限為 600"""
        if not self.env_path.exists():
            return RepairResult(
                action="fix_env_permissions",
                status=RepairStatus.FAILED,
                message=".env 不存在",
            )

        os.chmod(str(self.env_path), 0o600)
        return RepairResult(
            action="fix_env_permissions",
            status=RepairStatus.SUCCESS,
            message=".env 權限已修正為 600",
        )

    def repair_recreate_venv(self) -> RepairResult:
        """重建 Python 虛擬環境"""
        # 找 Python >= 3.11
        python_path = None
        for candidate in ["python3.13", "python3.12", "python3.11", "python3"]:
            try:
                result = subprocess.run(
                    [candidate, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    parts = version.split()[-1].split(".")
                    if int(parts[0]) >= 3 and int(parts[1]) >= 11:
                        python_path = candidate
                        break
            except (subprocess.TimeoutExpired, OSError, ValueError):
                continue

        if not python_path:
            return RepairResult(
                action="recreate_venv",
                status=RepairStatus.FAILED,
                message="找不到 Python >= 3.11（請安裝: brew install python@3.13）",
            )

        # 刪除壞的 venv
        if self.venv_dir.exists():
            subprocess.run(
                ["rm", "-rf", str(self.venv_dir)],
                capture_output=True,
                timeout=30,
            )

        # 重建
        result = subprocess.run(
            [python_path, "-m", "venv", str(self.venv_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return RepairResult(
                action="recreate_venv",
                status=RepairStatus.FAILED,
                message=f"venv 建立失敗: {result.stderr[:200]}",
            )

        # 安裝依賴
        pip = self.venv_dir / "bin" / "pip"
        project_dir = self._find_project_dir()
        pyproject = project_dir / "pyproject.toml"
        if pyproject.exists():
            result = subprocess.run(
                [str(pip), "install", "-e", f"{project_dir}[dev]"],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=str(project_dir),
            )
            if result.returncode != 0:
                return RepairResult(
                    action="recreate_venv",
                    status=RepairStatus.FAILED,
                    message=f"pip install 失敗: {result.stderr[-500:]}",
                )

        return RepairResult(
            action="recreate_venv",
            status=RepairStatus.SUCCESS,
            message=f"已用 {python_path} 重建 venv",
        )

    def repair_start_gateway(self) -> RepairResult:
        """啟動 Gateway"""
        # 先檢查 port 是否被占用
        try:
            result = subprocess.run(
                ["lsof", "-i", f":{self.checker.gateway_port}", "-t"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                # 殺掉占用 port 的進程
                for pid in pids:
                    subprocess.run(
                        ["kill", "-9", pid.strip()],
                        capture_output=True,
                        timeout=5,
                    )
        except (subprocess.TimeoutExpired, OSError):
            pass

        # 嘗試 launchctl 啟動
        plist = self.checker.plist_path
        if plist.exists():
            subprocess.run(
                ["launchctl", "unload", str(plist)],
                capture_output=True,
                timeout=5,
            )
            result = subprocess.run(
                ["launchctl", "load", str(plist)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return RepairResult(
                    action="start_gateway",
                    status=RepairStatus.SUCCESS,
                    message="已透過 launchctl 啟動 Gateway",
                )

        # 直接啟動
        venv_python = self._find_venv_python()
        if venv_python:
            src_dir = self._find_src_dir()
            project_dir = self._find_project_dir()
            subprocess.Popen(
                [str(venv_python), "-m", "museon.gateway.server"],
                cwd=str(project_dir),
                env={
                    **os.environ,
                    "PYTHONPATH": str(src_dir),
                    "MUSEON_HOME": str(self.home),
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return RepairResult(
                action="start_gateway",
                status=RepairStatus.SUCCESS,
                message="已直接啟動 Gateway 進程",
            )

        return RepairResult(
            action="start_gateway",
            status=RepairStatus.FAILED,
            message="無法啟動（venv 不存在）",
        )

    def repair_load_daemon(self) -> RepairResult:
        """載入 launchd daemon"""
        plist = self.checker.plist_path
        if not plist.exists():
            return RepairResult(
                action="load_daemon",
                status=RepairStatus.FAILED,
                message="plist 不存在，需要重新安裝",
            )

        subprocess.run(
            ["launchctl", "unload", str(plist)],
            capture_output=True,
            timeout=5,
        )
        result = subprocess.run(
            ["launchctl", "load", str(plist)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return RepairResult(
                action="load_daemon",
                status=RepairStatus.SUCCESS,
                message="Daemon 已載入",
            )
        return RepairResult(
            action="load_daemon",
            status=RepairStatus.FAILED,
            message=f"launchctl load 失敗: {result.stderr[:100]}",
        )

    def repair_rotate_logs(self) -> RepairResult:
        """清理過大的日誌"""
        if not self.logs_dir.exists():
            return RepairResult(
                action="rotate_logs",
                status=RepairStatus.SKIPPED,
                message="logs/ 不存在",
            )

        rotated = []
        for f in self.logs_dir.iterdir():
            if f.is_file() and f.stat().st_size > 100 * 1024 * 1024:
                # 保留最後 1000 行
                try:
                    lines = f.read_text("utf-8", errors="replace").splitlines()
                    f.write_text("\n".join(lines[-1000:]) + "\n", "utf-8")
                    rotated.append(f.name)
                except OSError:
                    pass

        if not rotated:
            return RepairResult(
                action="rotate_logs",
                status=RepairStatus.SKIPPED,
                message="無需清理",
            )
        return RepairResult(
            action="rotate_logs",
            status=RepairStatus.SUCCESS,
            message=f"已清理: {', '.join(rotated)}",
        )

    def repair_reinstall_packages(self) -> RepairResult:
        """重新安裝 Python 依賴"""
        pip = self._find_venv_pip()
        if not pip:
            return RepairResult(
                action="reinstall_packages",
                status=RepairStatus.FAILED,
                message="venv 不存在，請先 recreate_venv",
            )

        project_dir = self._find_project_dir()
        result = subprocess.run(
            [str(pip), "install", "-e", f"{project_dir}[dev]"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(project_dir),
        )
        if result.returncode == 0:
            return RepairResult(
                action="reinstall_packages",
                status=RepairStatus.SUCCESS,
                message="依賴已重新安裝",
            )
        return RepairResult(
            action="reinstall_packages",
            status=RepairStatus.FAILED,
            message=f"pip install 失敗: {result.stderr[-500:]}",
        )

    def repair_reinstall_daemon(self) -> RepairResult:
        """重新建立 launchd plist"""
        # 需要 installer 模組
        try:
            from museon.installer.daemon import DaemonConfigurator
            from museon.installer.models import InstallConfig

            config = InstallConfig(install_dir=self.home)
            daemon = DaemonConfigurator()
            result = daemon.create_plist(config)
            if result.status.value == "success":
                daemon.load_daemon(config)
                return RepairResult(
                    action="reinstall_daemon",
                    status=RepairStatus.SUCCESS,
                    message="Daemon plist 已重建並載入",
                )
            return RepairResult(
                action="reinstall_daemon",
                status=RepairStatus.FAILED,
                message=f"建立 plist 失敗: {result.message}",
            )
        except Exception as e:
            return RepairResult(
                action="reinstall_daemon",
                status=RepairStatus.FAILED,
                message=f"修復失敗: {e}",
            )

    def repair_rebuild_dashboard(self) -> RepairResult:
        """重建 Dashboard App"""
        electron_dir = self.runtime_dir / "electron"
        if not electron_dir.exists():
            return RepairResult(
                action="rebuild_dashboard",
                status=RepairStatus.FAILED,
                message="electron/ 目錄不存在",
            )

        try:
            from museon.installer.electron import ElectronPackager

            packager = ElectronPackager()

            # npm install
            npm_result = packager.npm_install(electron_dir)
            if npm_result.status.value != "success":
                return RepairResult(
                    action="rebuild_dashboard",
                    status=RepairStatus.FAILED,
                    message=f"npm install 失敗: {npm_result.message}",
                )

            # Build
            build_result = packager.build(electron_dir)
            if build_result.status.value != "success":
                return RepairResult(
                    action="rebuild_dashboard",
                    status=RepairStatus.FAILED,
                    message=f"build 失敗: {build_result.message}",
                )

            # Install
            app_bundle = packager.find_app_bundle(electron_dir)
            if not app_bundle:
                return RepairResult(
                    action="rebuild_dashboard",
                    status=RepairStatus.FAILED,
                    message="找不到 .app bundle",
                )

            install_result = packager.install_to_applications(app_bundle)
            if install_result.status.value == "success":
                return RepairResult(
                    action="rebuild_dashboard",
                    status=RepairStatus.SUCCESS,
                    message="MUSEON.app 已重建並安裝",
                )

            return RepairResult(
                action="rebuild_dashboard",
                status=RepairStatus.FAILED,
                message=f"安裝失敗: {install_result.message}",
            )
        except Exception as e:
            return RepairResult(
                action="rebuild_dashboard",
                status=RepairStatus.FAILED,
                message=f"重建失敗: {e}",
            )
