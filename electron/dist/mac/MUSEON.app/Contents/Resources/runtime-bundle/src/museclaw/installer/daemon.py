"""Gateway 24/7 Daemon 設定

對應 features/installation.feature Section 5
生成 launchd plist、載入/卸載 daemon、健康檢查
"""

import plistlib
import subprocess
from pathlib import Path

from .models import InstallConfig, StepResult, StepStatus


class DaemonConfigurator:
    """macOS launchd daemon 設定與管理"""

    def generate_plist(self, config: InstallConfig) -> str:
        """生成 launchd plist XML

        Args:
            config: 安裝設定

        Returns:
            plist XML 字串
        """
        plist_dict = {
            "Label": config.plist_name,
            "ProgramArguments": [
                str(config.venv_python),
                "-m",
                "museclaw.gateway.server",
            ],
            "WorkingDirectory": str(config.project_dir),
            "RunAtLoad": True,
            "KeepAlive": {
                "SuccessfulExit": False,
            },
            "ThrottleInterval": 5,
            "ProcessType": "Background",
            "EnvironmentVariables": {
                "PYTHONPATH": str(config.project_dir / "src"),
                "MUSECLAW_HOME": str(config.install_dir),
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            },
            "StandardOutPath": str(config.gateway_log),
            "StandardErrorPath": str(config.gateway_err),
        }

        plist_bytes = plistlib.dumps(plist_dict, fmt=plistlib.FMT_XML)
        return plist_bytes.decode("utf-8")

    def write_plist(self, config: InstallConfig) -> StepResult:
        """將 plist 寫入磁碟

        Args:
            config: 安裝設定
        """
        try:
            # 確保目標目錄存在
            config.plist_dir.mkdir(parents=True, exist_ok=True)
            # 確保日誌目錄存在
            config.log_dir.mkdir(parents=True, exist_ok=True)

            plist_xml = self.generate_plist(config)
            config.plist_path.write_text(plist_xml, encoding="utf-8")

            return StepResult(
                step_name="寫入 plist",
                status=StepStatus.SUCCESS,
                message=f"已寫入 {config.plist_path}",
            )
        except OSError as e:
            return StepResult(
                step_name="寫入 plist",
                status=StepStatus.FAILED,
                message=f"寫入 plist 失敗: {e}",
            )

    def unload_existing(self, label: str) -> StepResult:
        """停止舊的 daemon

        Args:
            label: launchd label (e.g. "com.museclaw.gateway")
        """
        try:
            # 嘗試 bootout (macOS 10.10+)
            result = subprocess.run(
                ["launchctl", "bootout", f"gui/{__import__('os').getuid()}/{label}"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return StepResult(
                    step_name="停止舊 daemon",
                    status=StepStatus.SUCCESS,
                    message=f"已停止 {label}",
                )

            # 備用: launchctl unload
            plist_path = (
                Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
            )
            result = subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True, text=True, timeout=30,
            )
            return StepResult(
                step_name="停止舊 daemon",
                status=StepStatus.SUCCESS,
                message=f"已停止 {label}" if result.returncode == 0 else f"未找到運行中的 {label}",
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return StepResult(
                step_name="停止舊 daemon",
                status=StepStatus.SUCCESS,
                message=f"無舊 daemon 需要停止 ({e})",
            )

    def load_daemon(self, plist_path: Path) -> StepResult:
        """啟動 daemon

        Args:
            plist_path: plist 檔案路徑
        """
        try:
            result = subprocess.run(
                ["launchctl", "load", str(plist_path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return StepResult(
                    step_name="啟動 daemon",
                    status=StepStatus.SUCCESS,
                    message="Gateway daemon 已啟動",
                )
            return StepResult(
                step_name="啟動 daemon",
                status=StepStatus.FAILED,
                message=f"啟動 daemon 失敗: {result.stderr.strip()}",
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return StepResult(
                step_name="啟動 daemon",
                status=StepStatus.FAILED,
                message=f"啟動 daemon 失敗: {e}",
            )

    def check_health_endpoint(
        self, port: int = 8765, timeout: float = 3.0
    ) -> StepResult:
        """檢查 Gateway 健康端點

        Args:
            port: Gateway 端口
            timeout: 超時秒數
        """
        try:
            result = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 f"http://127.0.0.1:{port}/health"],
                capture_output=True, text=True, timeout=timeout + 2,
            )
            if result.returncode == 0 and result.stdout.strip() == "200":
                return StepResult(
                    step_name="健康檢查",
                    status=StepStatus.SUCCESS,
                    message=f"Gateway 在 localhost:{port} 回應正常",
                )
            return StepResult(
                step_name="健康檢查",
                status=StepStatus.WARNING,
                message=f"Gateway 尚未就緒 (HTTP {result.stdout.strip()})",
            )
        except (subprocess.TimeoutExpired, OSError):
            return StepResult(
                step_name="健康檢查",
                status=StepStatus.WARNING,
                message=f"無法連線到 Gateway (localhost:{port})",
            )
