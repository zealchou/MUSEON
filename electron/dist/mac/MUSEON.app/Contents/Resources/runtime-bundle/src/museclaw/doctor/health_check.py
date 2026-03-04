"""MuseClaw Doctor — 健檢引擎（Layer 1 + 2）

純 CPU 健康檢查，零 Token。
涵蓋 8 大項快速健檢 + 自動修復建議。
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class CheckStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class CheckResult:
    """單項健檢結果"""

    name: str
    status: CheckStatus
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    repairable: bool = False
    repair_action: str = ""


@dataclass
class HealthReport:
    """完整健檢報告"""

    timestamp: str
    overall: CheckStatus
    checks: List[CheckResult]
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall": self.overall.value,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "details": c.details,
                    "repairable": c.repairable,
                    "repair_action": c.repair_action,
                }
                for c in self.checks
            ],
            "summary": self.summary,
        }


class HealthChecker:
    """MuseClaw 系統健檢引擎 — 純 CPU"""

    def __init__(self, museclaw_home: Optional[str] = None):
        self.home = Path(
            museclaw_home
            or os.environ.get("MUSECLAW_HOME")
            or Path.home() / "MuseClaw"
        )
        self.runtime_dir = self.home / ".runtime"
        self.data_dir = self.home / "data"
        self.logs_dir = self.home / "logs"
        self.env_path = self.home / ".env"
        self.venv_dir = self.runtime_dir / ".venv"
        self.gateway_port = 8765
        self.plist_path = (
            Path.home()
            / "Library"
            / "LaunchAgents"
            / "com.museclaw.gateway.plist"
        )

    def run_all(self) -> HealthReport:
        """執行全部健檢 — 純 CPU"""
        checks: List[CheckResult] = []

        checks.append(self.check_directories())
        checks.append(self.check_env_file())
        checks.append(self.check_api_keys())
        checks.append(self.check_venv())
        checks.append(self.check_core_imports())
        checks.append(self.check_gateway_process())
        checks.append(self.check_gateway_health())
        checks.append(self.check_data_integrity())
        checks.append(self.check_daemon_plist())
        checks.append(self.check_disk_space())
        checks.append(self.check_log_size())
        checks.append(self.check_dashboard_app())

        # 計算統計
        summary = {"ok": 0, "warning": 0, "critical": 0, "unknown": 0}
        for c in checks:
            summary[c.status.value] = summary.get(c.status.value, 0) + 1

        # 整體狀態
        if summary["critical"] > 0:
            overall = CheckStatus.CRITICAL
        elif summary["warning"] > 0:
            overall = CheckStatus.WARNING
        else:
            overall = CheckStatus.OK

        return HealthReport(
            timestamp=datetime.now().isoformat(),
            overall=overall,
            checks=checks,
            summary=summary,
        )

    # ─── 1. 目錄結構 ───

    def check_directories(self) -> CheckResult:
        required = {
            "home": self.home,
            "data": self.data_dir,
            "logs": self.logs_dir,
        }
        missing = [k for k, v in required.items() if not v.exists()]

        if not missing:
            return CheckResult(
                name="目錄結構",
                status=CheckStatus.OK,
                message="所有必要目錄存在",
                details={"home": str(self.home)},
            )
        return CheckResult(
            name="目錄結構",
            status=CheckStatus.CRITICAL,
            message=f"缺少目錄: {', '.join(missing)}",
            details={"missing": missing},
            repairable=True,
            repair_action="create_directories",
        )

    # ─── 2. .env 檔案 ───

    def check_env_file(self) -> CheckResult:
        if not self.env_path.exists():
            return CheckResult(
                name=".env 設定檔",
                status=CheckStatus.CRITICAL,
                message=f"{self.env_path} 不存在",
                repairable=True,
                repair_action="create_env_file",
            )

        # 檢查權限
        stat = self.env_path.stat()
        mode = oct(stat.st_mode)[-3:]
        if mode != "600":
            return CheckResult(
                name=".env 設定檔",
                status=CheckStatus.WARNING,
                message=f".env 權限過寬: {mode}（建議 600）",
                repairable=True,
                repair_action="fix_env_permissions",
            )

        return CheckResult(
            name=".env 設定檔",
            status=CheckStatus.OK,
            message=".env 存在且權限正確",
        )

    # ─── 3. API Keys ───

    def check_api_keys(self) -> CheckResult:
        if not self.env_path.exists():
            return CheckResult(
                name="API Keys",
                status=CheckStatus.CRITICAL,
                message=".env 不存在，無法檢查 keys",
            )

        env_vars = self._parse_env_file()
        issues = []

        anthropic_key = env_vars.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key:
            issues.append("ANTHROPIC_API_KEY 未設定")
        elif not anthropic_key.startswith("sk-ant-"):
            issues.append("ANTHROPIC_API_KEY 格式可能不正確")

        telegram_token = env_vars.get("TELEGRAM_BOT_TOKEN", "")
        if not telegram_token:
            issues.append("TELEGRAM_BOT_TOKEN 未設定（Telegram 功能無法使用）")

        if not issues:
            return CheckResult(
                name="API Keys",
                status=CheckStatus.OK,
                message="API keys 已設定",
            )

        has_critical = any("ANTHROPIC" in i for i in issues)
        return CheckResult(
            name="API Keys",
            status=CheckStatus.CRITICAL if has_critical else CheckStatus.WARNING,
            message="; ".join(issues),
            details={"issues": issues},
        )

    # ─── 4. Python venv ───

    def check_venv(self) -> CheckResult:
        # 用 _find_usable_venv() 統一驗證，避免殭屍 venv 通過檢查
        usable = self._find_usable_venv()
        if usable is None:
            # 細分原因：binary 存在但依賴缺失 vs 完全不存在
            any_exists = (
                (self.venv_dir / "bin" / "python").exists()
                or (self.home / ".venv" / "bin" / "python").exists()
            )
            if any_exists:
                return CheckResult(
                    name="Python 虛擬環境",
                    status=CheckStatus.CRITICAL,
                    message="venv 存在但核心依賴缺失（需重建或 pip install）",
                    repairable=True,
                    repair_action="reinstall_packages",
                )
            return CheckResult(
                name="Python 虛擬環境",
                status=CheckStatus.CRITICAL,
                message="venv 不存在",
                repairable=True,
                repair_action="recreate_venv",
            )

        try:
            result = subprocess.run(
                [str(usable), "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = result.stdout.strip() if result.returncode == 0 else "unknown"
            return CheckResult(
                name="Python 虛擬環境",
                status=CheckStatus.OK,
                message=f"venv 正常 ({version})",
                details={"python_version": version, "path": str(usable)},
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return CheckResult(
                name="Python 虛擬環境",
                status=CheckStatus.CRITICAL,
                message=f"venv 損毀: {e}",
                repairable=True,
                repair_action="recreate_venv",
            )

    # ─── 5. 核心模組 import ───

    def check_core_imports(self) -> CheckResult:
        # 支援兩種佈局：
        #   production: .runtime/.venv/bin/python + .runtime/src
        #   dev:        .venv/bin/python          + ./src
        #
        # 重要：不能只檢查 binary 存在，必須驗證 venv 有安裝核心依賴（fastapi）。
        # 否則殭屍 venv（只有 pip）會導致所有 import 失敗。
        venv_python = self._find_usable_venv()
        if venv_python is None:
            return CheckResult(
                name="核心模組",
                status=CheckStatus.UNKNOWN,
                message="找不到可用的 venv（需要安裝 fastapi）",
            )

        # PYTHONPATH: 先嘗試 .runtime/src（production），再嘗試 ./src（dev）
        src_dir = self.runtime_dir / "src"
        if not src_dir.exists():
            src_dir = self.home / "src"

        modules = [
            "museclaw.gateway.server",
            "museclaw.agent.brain",
            "museclaw.agent.skills",
        ]
        failed = []
        for mod in modules:
            try:
                result = subprocess.run(
                    [str(venv_python), "-c", f"import {mod}"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    env={
                        **os.environ,
                        "PYTHONPATH": str(src_dir),
                    },
                )
                if result.returncode != 0:
                    failed.append(mod)
            except (subprocess.TimeoutExpired, OSError):
                failed.append(mod)

        if not failed:
            return CheckResult(
                name="核心模組",
                status=CheckStatus.OK,
                message=f"全部 {len(modules)} 個核心模組可 import",
            )
        return CheckResult(
            name="核心模組",
            status=CheckStatus.CRITICAL,
            message=f"模組 import 失敗: {', '.join(failed)}",
            details={"failed": failed},
            repairable=True,
            repair_action="reinstall_packages",
        )

    # ─── 6. Gateway 進程 ───

    def check_gateway_process(self) -> CheckResult:
        try:
            result = subprocess.run(
                ["pgrep", "-f", "museclaw.gateway.server"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                pids = result.stdout.strip().split("\n")
                return CheckResult(
                    name="Gateway 進程",
                    status=CheckStatus.OK,
                    message=f"Gateway 運行中 (PID: {', '.join(pids)})",
                    details={"pids": pids},
                )
            return CheckResult(
                name="Gateway 進程",
                status=CheckStatus.WARNING,
                message="Gateway 未運行",
                repairable=True,
                repair_action="start_gateway",
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            return CheckResult(
                name="Gateway 進程",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查進程: {e}",
            )

    # ─── 7. Gateway HTTP 健康 ───

    def check_gateway_health(self) -> CheckResult:
        try:
            import urllib.request

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.gateway_port}/health"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                status_str = data.get("status", "unknown")
                if status_str == "healthy":
                    return CheckResult(
                        name="Gateway 健康",
                        status=CheckStatus.OK,
                        message="Gateway 回應正常",
                        details=data,
                    )
                return CheckResult(
                    name="Gateway 健康",
                    status=CheckStatus.WARNING,
                    message=f"Gateway 回應異常: {status_str}",
                    details=data,
                )
        except Exception as e:
            return CheckResult(
                name="Gateway 健康",
                status=CheckStatus.WARNING,
                message=f"Gateway 無法連線: {e}",
                repairable=True,
                repair_action="start_gateway",
            )

    # ─── 8. data/ 完整性 ───

    def check_data_integrity(self) -> CheckResult:
        if not self.data_dir.exists():
            return CheckResult(
                name="資料完整性",
                status=CheckStatus.CRITICAL,
                message="data/ 目錄不存在",
                repairable=True,
                repair_action="create_directories",
            )

        issues = []
        anima_mc = self.data_dir / "ANIMA_MC.json"
        if anima_mc.exists():
            try:
                json.loads(anima_mc.read_text("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                issues.append(f"ANIMA_MC.json 損毀: {e}")

        anima_user = self.data_dir / "ANIMA_USER.json"
        if anima_user.exists():
            try:
                json.loads(anima_user.read_text("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                issues.append(f"ANIMA_USER.json 損毀: {e}")

        if not issues:
            return CheckResult(
                name="資料完整性",
                status=CheckStatus.OK,
                message="核心資料檔案正常",
            )
        return CheckResult(
            name="資料完整性",
            status=CheckStatus.WARNING,
            message="; ".join(issues),
            details={"issues": issues},
        )

    # ─── 9. Daemon plist ───

    def check_daemon_plist(self) -> CheckResult:
        if not self.plist_path.exists():
            return CheckResult(
                name="Daemon 設定",
                status=CheckStatus.WARNING,
                message="launchd plist 不存在（Gateway 不會自動啟動）",
                repairable=True,
                repair_action="reinstall_daemon",
            )

        # 檢查 plist 語法
        try:
            result = subprocess.run(
                ["plutil", "-lint", str(self.plist_path)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return CheckResult(
                    name="Daemon 設定",
                    status=CheckStatus.WARNING,
                    message=f"plist 格式有誤: {result.stderr.strip()[:100]}",
                    repairable=True,
                    repair_action="reinstall_daemon",
                )
        except (subprocess.TimeoutExpired, OSError):
            pass

        # 檢查 daemon 是否 loaded
        try:
            result = subprocess.run(
                ["launchctl", "list", "com.museclaw.gateway"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return CheckResult(
                    name="Daemon 設定",
                    status=CheckStatus.WARNING,
                    message="Daemon 未載入（需要 launchctl load）",
                    repairable=True,
                    repair_action="load_daemon",
                )
        except (subprocess.TimeoutExpired, OSError):
            pass

        return CheckResult(
            name="Daemon 設定",
            status=CheckStatus.OK,
            message="Daemon plist 正常",
        )

    # ─── 10. 磁碟空間 ───

    def check_disk_space(self) -> CheckResult:
        try:
            usage = shutil.disk_usage(str(self.home))
            free_gb = usage.free / (1024**3)
            if free_gb < 1.0:
                return CheckResult(
                    name="磁碟空間",
                    status=CheckStatus.CRITICAL,
                    message=f"磁碟空間不足: {free_gb:.1f} GB",
                    details={"free_gb": round(free_gb, 1)},
                )
            if free_gb < 5.0:
                return CheckResult(
                    name="磁碟空間",
                    status=CheckStatus.WARNING,
                    message=f"磁碟空間偏低: {free_gb:.1f} GB",
                    details={"free_gb": round(free_gb, 1)},
                )
            return CheckResult(
                name="磁碟空間",
                status=CheckStatus.OK,
                message=f"磁碟空間充足: {free_gb:.1f} GB",
                details={"free_gb": round(free_gb, 1)},
            )
        except OSError as e:
            return CheckResult(
                name="磁碟空間",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    # ─── 11. Log 大小 ───

    def check_log_size(self) -> CheckResult:
        if not self.logs_dir.exists():
            return CheckResult(
                name="日誌大小",
                status=CheckStatus.OK,
                message="logs/ 不存在（尚無日誌）",
            )

        total_size = 0
        large_files = []
        for f in self.logs_dir.iterdir():
            if f.is_file():
                size = f.stat().st_size
                total_size += size
                if size > 100 * 1024 * 1024:  # > 100MB
                    large_files.append(f"{f.name} ({size // (1024*1024)} MB)")

        if large_files:
            return CheckResult(
                name="日誌大小",
                status=CheckStatus.WARNING,
                message=f"日誌過大: {', '.join(large_files)}",
                details={"large_files": large_files},
                repairable=True,
                repair_action="rotate_logs",
            )

        return CheckResult(
            name="日誌大小",
            status=CheckStatus.OK,
            message=f"日誌總量: {total_size // 1024} KB",
            details={"total_kb": total_size // 1024},
        )

    # ─── 12. Dashboard App ───

    def check_dashboard_app(self) -> CheckResult:
        app_path = Path("/Applications/MUSEON.app")
        if not app_path.exists():
            return CheckResult(
                name="MUSEON App",
                status=CheckStatus.WARNING,
                message="MUSEON.app 未安裝",
                repairable=True,
                repair_action="rebuild_dashboard",
            )

        # 檢查巢狀結構（舊 bug）
        nested = list(app_path.glob("*.app"))
        if nested:
            return CheckResult(
                name="MUSEON App",
                status=CheckStatus.CRITICAL,
                message=f"App 結構損壞（巢狀 .app: {[a.name for a in nested]}）",
                repairable=True,
                repair_action="rebuild_dashboard",
            )

        # 檢查 asar 存在
        asar = app_path / "Contents" / "Resources" / "app.asar"
        if not asar.exists():
            return CheckResult(
                name="MUSEON App",
                status=CheckStatus.CRITICAL,
                message="app.asar 不存在（App 損壞）",
                repairable=True,
                repair_action="rebuild_dashboard",
            )

        return CheckResult(
            name="MUSEON App",
            status=CheckStatus.OK,
            message="MUSEON.app 已安裝且結構正常",
        )

    # ─── Helpers ───

    def _find_usable_venv(self) -> Optional[Path]:
        """找到第一個可用的 venv python（必須能 import fastapi）。

        優先順序：.runtime/.venv → .venv
        每個候選都會驗證 fastapi 可匯入，避免殭屍 venv。
        """
        candidates = [
            self.venv_dir / "bin" / "python",           # .runtime/.venv
            self.home / ".venv" / "bin" / "python",     # dev .venv
        ]
        for python_path in candidates:
            if not python_path.exists():
                continue
            try:
                result = subprocess.run(
                    [str(python_path), "-c", "import fastapi"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return python_path
            except (subprocess.TimeoutExpired, OSError):
                continue
        return None

    def _parse_env_file(self) -> Dict[str, str]:
        """解析 .env 檔案 — 純 CPU"""
        env_vars: Dict[str, str] = {}
        try:
            for line in self.env_path.read_text("utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip().strip("'\"")
        except (OSError, UnicodeDecodeError):
            pass
        return env_vars
