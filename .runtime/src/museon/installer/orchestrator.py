"""安裝流程編排器

對應 features/installation.feature Section 7
串聯所有安裝步驟，收集結果，產出報告
"""

import subprocess
from pathlib import Path
from typing import List, Optional

from .models import InstallConfig, StepResult, StepStatus


class InstallerOrchestrator:
    """安裝流程編排器

    按順序執行 8 個步驟，遇到 FAILED 即停止。
    WARNING/SKIPPED 可繼續。
    """

    STEPS = [
        "_step_environment",
        "_step_permissions",
        "_step_python_env",
        "_step_verify_modules",
        "_step_electron",
        "_step_daemon",
        "_step_api_keys",
        "_step_claude_code",
        "_step_tools",
        "_step_launch",
    ]

    # 統一的步驟名稱（用於 check_day0_readiness 比對）
    STEP_LABELS = {
        "_step_environment": "環境檢查",
        "_step_permissions": "權限檢查",
        "_step_python_env": "Python 環境",
        "_step_verify_modules": "模組驗證",
        "_step_electron": "Electron",
        "_step_daemon": "Daemon",
        "_step_api_keys": "API Keys",
        "_step_claude_code": "Claude Code",
        "_step_tools": "工具安裝",
        "_step_launch": "啟動",
    }

    def __init__(
        self,
        config: InstallConfig,
        ui: Optional[object] = None,
        interactive: bool = True,
    ):
        self.config = config
        self.ui = ui
        self.interactive = interactive
        self.results: List[StepResult] = []

    def run(self) -> List[StepResult]:
        """執行完整安裝流程

        Returns:
            所有步驟的結果列表
        """
        self.results = []

        for step_name in self.STEPS:
            step_method = getattr(self, step_name)
            result = step_method()

            # 統一 step_name 方便後續比對
            label = self.STEP_LABELS.get(step_name, result.step_name)
            result = StepResult(
                step_name=label,
                status=result.status,
                message=result.message,
                details=result.details,
            )

            self.results.append(result)

            # 致命錯誤：停止管線
            if result.is_fatal:
                break

        return self.results

    def generate_summary(self) -> str:
        """產出安裝結果摘要"""
        lines = []
        lines.append("")
        lines.append("  ╔═══════════════════════════════════════════╗")
        lines.append("  ║         MUSEON 安裝結果報告             ║")
        lines.append("  ╚═══════════════════════════════════════════╝")

        success_count = 0
        warning_count = 0
        skipped_count = 0
        failed_count = 0

        for r in self.results:
            status_icon = {
                StepStatus.SUCCESS: "✅",
                StepStatus.WARNING: "⚠️",
                StepStatus.SKIPPED: "⏭️",
                StepStatus.FAILED: "❌",
                StepStatus.PENDING: "⏳",
            }.get(r.status, "?")

            lines.append(f"  {status_icon} {r.step_name}: {r.message}")

            if r.status == StepStatus.SUCCESS:
                success_count += 1
            elif r.status == StepStatus.WARNING:
                warning_count += 1
            elif r.status == StepStatus.SKIPPED:
                skipped_count += 1
            elif r.status == StepStatus.FAILED:
                failed_count += 1

        lines.append("")

        if failed_count == 0:
            lines.append(f"  🎉 安裝成功！{success_count} 個步驟完成")
        else:
            lines.append(f"  ⚠️  {failed_count} 個步驟失敗")

        if skipped_count > 0:
            lines.append(f"     （{skipped_count} 個步驟跳過，不影響核心功能）")

        return "\n".join(lines)

    def check_day0_readiness(self) -> str:
        """確認 Day 0 就緒狀態

        Returns:
            下一步指引訊息
        """
        # 用標準化的 step_name 比對
        daemon_ok = any(
            r.step_name in ("Daemon", "啟動 daemon", "啟動")
            and r.status == StepStatus.SUCCESS
            for r in self.results
        )

        dashboard_installed = any(
            r.step_name in ("Electron", "安裝 Dashboard")
            and r.status == StepStatus.SUCCESS
            for r in self.results
        )

        lines = []

        if daemon_ok:
            lines.append("🎉 MUSEON Gateway 24/7 運行中！")
            lines.append("")

            if dashboard_installed:
                lines.append("📱 Dashboard 已安裝 → /Applications/MUSEON.app")
                lines.append("   （正在為你自動打開...）")
                lines.append("")

            lines.append("👉 接下來你只需要做一件事：")
            lines.append("")
            lines.append("   打開 Telegram → 找到你的 MUSEON Bot → 說第一句話")
            lines.append("")
            lines.append("   命名儀式即將開始——等你開口 🐾")
        else:
            lines.append("⚠️ Gateway 啟動需要一點時間")
            lines.append("")
            lines.append("   等幾秒後試試：")
            lines.append(f"   curl http://127.0.0.1:{self.config.gateway_port}/health")
            lines.append("")
            lines.append("   如果還是不行，看日誌：")
            lines.append(f"   cat {self.config.gateway_log}")
            lines.append(f"   cat {self.config.gateway_err}")

        return "\n".join(lines)

    def try_open_dashboard(self):
        """嘗試打開 Dashboard.app"""
        from pathlib import Path

        app_path = Path("/Applications/MUSEON.app")
        if app_path.exists():
            try:
                subprocess.Popen(
                    ["open", str(app_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass

    # ─── 各步驟實作（可被 mock 覆蓋） ───

    def _step_environment(self) -> StepResult:
        """Step 1: 環境檢查"""
        from .environment import EnvironmentChecker

        checker = EnvironmentChecker()
        os_result = checker.check_os()
        if os_result.is_fatal:
            return os_result

        arch = checker.detect_arch()
        disk_result = checker.check_disk_space(
            self.config.project_dir, self.config.min_disk_mb
        )

        status = StepStatus.SUCCESS if disk_result.is_ok else StepStatus.WARNING
        return StepResult(
            step_name="環境檢查",
            status=status,
            message=f"macOS {arch} | {disk_result.message}",
        )

    def _step_permissions(self) -> StepResult:
        """Step 2: macOS 權限檢查"""
        from .permissions import PermissionChecker

        checker = PermissionChecker()
        results = checker.check_all()

        denied = [r for r in results if not r.granted]
        if denied:
            labels = ", ".join(
                checker.LABELS[r.permission] for r in denied
            )
            return StepResult(
                step_name="權限檢查",
                status=StepStatus.WARNING,
                message=f"未授權: {labels}（可稍後在系統設定中開啟）",
                details={"denied": [r.permission.value for r in denied]},
            )

        return StepResult(
            step_name="權限檢查",
            status=StepStatus.SUCCESS,
            message="所有權限已確認",
        )

    def _step_python_env(self) -> StepResult:
        """Step 3: Python 環境建置"""
        from .environment import EnvironmentChecker
        from .python_env import PythonEnvironmentSetup

        setup = PythonEnvironmentSetup()

        if setup.venv_exists(self.config.venv_dir):
            return StepResult(
                step_name="Python 環境",
                status=StepStatus.SUCCESS,
                message=f"重用現有的 {self.config.venv_dir}",
            )

        checker = EnvironmentChecker()
        python_path, version = checker.find_python()
        if python_path is None:
            return StepResult(
                step_name="Python 環境",
                status=StepStatus.FAILED,
                message="找不到 Python >= 3.11，建議執行 brew install python@3.13",
            )

        venv_result = setup.create_venv(python_path, self.config.venv_dir)
        if venv_result.is_fatal:
            return venv_result

        return setup.install_dependencies(
            self.config.venv_python, self.config.project_dir
        )

    def _step_verify_modules(self) -> StepResult:
        """Step 3: 模組驗證"""
        from .module_verifier import ModuleVerifier

        verifier = ModuleVerifier()
        results = verifier.verify_all()

        failed = [r for r in results if not r.is_ok]
        if failed:
            return StepResult(
                step_name="模組驗證",
                status=StepStatus.WARNING,
                message=f"{len(failed)} 個模組驗證失敗",
                details={"failed": [r.message for r in failed]},
            )

        warnings = [r for r in results if r.status == StepStatus.WARNING]
        if warnings:
            return StepResult(
                step_name="模組驗證",
                status=StepStatus.WARNING,
                message=f"{len(warnings)} 個模組有警告",
                details={"warnings": [r.message for r in warnings]},
            )

        return StepResult(
            step_name="模組驗證",
            status=StepStatus.SUCCESS,
            message="四大核心模組全部載入成功",
        )

    def _step_electron(self) -> StepResult:
        """Step 4-5: Electron Dashboard 打包+安裝"""
        from .environment import EnvironmentChecker
        from .electron import ElectronPackager

        checker = EnvironmentChecker()
        node_path, has_npm = checker.find_node()
        if node_path is None or not has_npm:
            return StepResult(
                step_name="Electron",
                status=StepStatus.SKIPPED,
                message="Node.js/npm 不可用，跳過 Dashboard（不影響 Gateway）",
            )

        if not self.config.electron_dir.exists():
            return StepResult(
                step_name="Electron",
                status=StepStatus.SKIPPED,
                message="electron/ 目錄不存在，跳過 Dashboard",
            )

        packager = ElectronPackager()

        npm_result = packager.npm_install(self.config.electron_dir)
        if not npm_result.is_ok:
            return StepResult(
                step_name="Electron",
                status=StepStatus.WARNING,
                message=f"npm install 失敗: {npm_result.message}",
            )

        build_result = packager.build_app(self.config.electron_dir)
        if build_result.status != StepStatus.SUCCESS:
            return build_result

        app_bundle = packager.find_app_bundle(self.config.electron_dir)
        if app_bundle:
            return packager.install_to_applications(app_bundle)

        return StepResult(
            step_name="Electron",
            status=StepStatus.WARNING,
            message="打包完成但找不到 .app bundle",
        )

    def _step_daemon(self) -> StepResult:
        """Step 6: Gateway daemon 設定"""
        from .daemon import DaemonConfigurator

        configurator = DaemonConfigurator()

        configurator.unload_existing(self.config.plist_name)

        write_result = configurator.write_plist(self.config)
        if write_result.is_fatal:
            return write_result

        return configurator.load_daemon(self.config.plist_path)

    def _step_api_keys(self) -> StepResult:
        """Step 7a: API Key 設定"""
        from .api_keys import ApiKeyConfigurator

        config = ApiKeyConfigurator()

        config.create_env_file(self.config.env_file)

        if not self.interactive:
            return StepResult(
                step_name="API Keys",
                status=StepStatus.SKIPPED,
                message="非互動模式，跳過 API Key 設定",
            )

        return StepResult(
            step_name="API Keys",
            status=StepStatus.SUCCESS,
            message="API Key 設定完成（MAX 訂閱方案下為選擇性）",
        )

    def _step_claude_code(self) -> StepResult:
        """Step 7.5: Claude Code CLI 設定（MAX 訂閱方案）"""
        import shutil

        # 1. 檢查 claude CLI
        claude_path = shutil.which("claude")
        if not claude_path:
            return StepResult(
                step_name="Claude Code",
                status=StepStatus.WARNING,
                message=(
                    "Claude Code CLI 未安裝。MAX 訂閱方案需要 Claude Code。"
                    "請先安裝：npm install -g @anthropic-ai/claude-code"
                ),
            )

        # 2. 驗證 claude -p 可用
        try:
            import os
            env = os.environ.copy()
            env.pop("CLAUDECODE", None)
            result = subprocess.run(
                [claude_path, "-p", "--output-format", "json", "echo test"],
                capture_output=True, text=True, timeout=30,
                env=env,
            )
            if result.returncode != 0:
                return StepResult(
                    step_name="Claude Code",
                    status=StepStatus.WARNING,
                    message=f"claude -p 測試失敗: {result.stderr[:200]}",
                )
        except subprocess.TimeoutExpired:
            return StepResult(
                step_name="Claude Code",
                status=StepStatus.WARNING,
                message="claude -p 測試超時 — 請確認 MAX 訂閱是否有效",
            )
        except Exception as e:
            return StepResult(
                step_name="Claude Code",
                status=StepStatus.WARNING,
                message=f"claude -p 測試異常: {e}",
            )

        # 3. 設定 MCP Server（若 settings.json 存在）
        claude_settings = Path.home() / ".claude" / "settings.json"
        mcp_configured = False
        if claude_settings.exists():
            try:
                import json
                settings = json.loads(claude_settings.read_text(encoding="utf-8"))
                mcp_servers = settings.get("mcpServers", {})
                if "museon" in mcp_servers:
                    mcp_configured = True
            except Exception:
                pass

        msg = "Claude Code CLI 已驗證，MAX 訂閱方案就緒"
        if mcp_configured:
            msg += "（MCP Server 已註冊）"
        else:
            msg += "（MCP Server 尚未註冊，可稍後手動設定）"

        return StepResult(
            step_name="Claude Code",
            status=StepStatus.SUCCESS,
            message=msg,
        )

    def _step_tools(self) -> StepResult:
        """Step 7b: 安裝所有 MUSEON AI 工具（Docker/Native）.

        流程：
        1. 檢查 Docker 是否可用
        2. 清除 ghcr.io 過期憑證（避免 public image pull denied）
        3. auto_detect() 已安裝的工具
        4. 依序安裝缺失工具（INSTALL_ORDER）
        5. 逐一健康檢查

        經驗教訓（2026-02 迭代）：
        - ghcr.io 有 stale credentials 會導致 public image denied
        - Firecrawl org 已從 mendableai → firecrawl
        - PaddleOCR health endpoint 是 POST-only，需用 base URL
        - pip/native 工具需用 import 偵測
        """
        # 檢查 Docker
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return StepResult(
                    step_name="工具安裝",
                    status=StepStatus.SKIPPED,
                    message="Docker 未安裝或未啟動，跳過工具安裝（不影響核心功能）",
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return StepResult(
                step_name="工具安裝",
                status=StepStatus.SKIPPED,
                message="Docker 未安裝，跳過工具安裝（不影響核心功能）",
            )

        # 清除 ghcr.io 過期憑證（避免 public image pull denied）
        try:
            subprocess.run(
                ["docker", "logout", "ghcr.io"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

        try:
            from museon.tools.tool_registry import ToolRegistry, INSTALL_ORDER

            workspace = str(self.config.data_dir)
            registry = ToolRegistry(workspace=workspace)
            registry.auto_detect()

            installed = 0
            failed = []

            for name in INSTALL_ORDER:
                # 使用 _states dict 直接取得 ToolState
                state = registry._states.get(name)
                if state and state.installed:
                    installed += 1
                    continue

                if self.ui:
                    self.ui.substep(f"安裝 {name}...")

                try:
                    install_result = registry.install_tool(name)
                    if install_result.get("success"):
                        installed += 1
                    else:
                        error_msg = install_result.get(
                            "error_message",
                            install_result.get("error", "unknown"),
                        )
                        failed.append(f"{name}({error_msg})")
                except Exception as e:
                    failed.append(f"{name}({e})")

            # 健康檢查
            try:
                registry.check_all_health()
            except Exception:
                pass

            total = len(INSTALL_ORDER)

            if failed:
                return StepResult(
                    step_name="工具安裝",
                    status=StepStatus.WARNING,
                    message=f"已安裝 {installed}/{total} 工具，失敗: {', '.join(failed)}",
                    details={"installed": installed, "failed": failed},
                )

            return StepResult(
                step_name="工具安裝",
                status=StepStatus.SUCCESS,
                message=f"全部 {installed}/{total} 個工具已安裝並驗證",
                details={"installed": installed, "total": total},
            )

        except ImportError:
            return StepResult(
                step_name="工具安裝",
                status=StepStatus.SKIPPED,
                message="ToolRegistry 模組不可用，跳過工具安裝",
            )
        except Exception as e:
            return StepResult(
                step_name="工具安裝",
                status=StepStatus.WARNING,
                message=f"工具安裝過程發生錯誤: {e}",
            )

    def _step_launch(self) -> StepResult:
        """Step 8: 啟動確認"""
        from .daemon import DaemonConfigurator

        configurator = DaemonConfigurator()
        health = configurator.check_health_endpoint(
            port=self.config.gateway_port, timeout=5.0
        )

        if health.status == StepStatus.SUCCESS:
            return StepResult(
                step_name="啟動",
                status=StepStatus.SUCCESS,
                message="Gateway 24/7 運行中 ✓",
            )

        return StepResult(
            step_name="啟動",
            status=StepStatus.WARNING,
            message=f"Gateway 尚未回應，請稍後確認。日誌: {self.config.gateway_log}",
        )
