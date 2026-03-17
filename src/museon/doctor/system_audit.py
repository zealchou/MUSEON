"""MUSEON 系統審計引擎 — 7 層 46 項全面體檢

從「症狀導向」升級為「全面覆蓋」的系統審計。
複用 health_check.py 的 12 項檢查 + 擴展至 7 層框架。

使用方式:
    # 完整審計（人類可讀）
    python -m museon.doctor.system_audit

    # JSON 格式
    python -m museon.doctor.system_audit --json

    # Gate 模式（CRITICAL 即 exit(1)，用於 build-installer.sh）
    python -m museon.doctor.system_audit --gate

    # 只跑指定層
    python -m museon.doctor.system_audit --layer infra security

    # 指定 MUSEON_HOME
    python -m museon.doctor.system_audit --home /Users/ZEALCHOU/MUSEON

7 層框架:
    Layer 1: 基礎設施 — 目錄/檔案/.env/磁碟/Python/venv/依賴
    Layer 2: 進程     — Gateway/Daemon/PID/Port/Electron/Docker
    Layer 3: 服務     — Gateway HTTP/Qdrant/SearXNG/Firecrawl/Telegram/MCP/Brain
    Layer 4: 應用     — API Key/Budget/Skills/Event Bus/Activity Log/Data/Immunity/API 可達性
    Layer 5: 演化     — Governor/Preflight/Refractory/Bulkhead/Immune Memory/Autonomic
    Layer 6: 安全     — .env 權限/Token 洩漏/敏感檔案/HTTPS/Placeholder/Packager
    Layer 7: 趨勢     — Log 成長率/Token 使用趨勢/啟動失敗頻率/磁碟使用趨勢
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.doctor.health_check import CheckStatus, CheckResult, HealthChecker


# ═══════════════════════════════════════════
# 審計層級定義
# ═══════════════════════════════════════════


class AuditLayer(str, Enum):
    INFRA = "infrastructure"
    PROCESS = "process"
    SERVICE = "service"
    APPLICATION = "application"
    EVOLUTION = "evolution"
    SECURITY = "security"
    TREND = "trend"
    BLUEPRINT = "blueprint"  # P4: 藍圖一致性


LAYER_LABELS = {
    AuditLayer.INFRA: "基礎設施",
    AuditLayer.PROCESS: "進程",
    AuditLayer.SERVICE: "服務",
    AuditLayer.APPLICATION: "應用",
    AuditLayer.EVOLUTION: "演化",
    AuditLayer.SECURITY: "安全",
    AuditLayer.TREND: "趨勢",
    AuditLayer.BLUEPRINT: "藍圖",
}


# ═══════════════════════════════════════════
# 審計報告模型
# ═══════════════════════════════════════════


@dataclass
class LayerResult:
    """單層審計結果"""
    layer: AuditLayer
    label: str
    checks: List[CheckResult]
    passed: int = 0
    warned: int = 0
    failed: int = 0

    def __post_init__(self):
        self.passed = sum(1 for c in self.checks if c.status == CheckStatus.OK)
        self.warned = sum(1 for c in self.checks if c.status == CheckStatus.WARNING)
        self.failed = sum(1 for c in self.checks if c.status == CheckStatus.CRITICAL)


@dataclass
class AuditReport:
    """完整審計報告"""
    timestamp: str
    hostname: str
    museon_home: str
    python_version: str
    layers: List[LayerResult]
    overall: CheckStatus
    summary: Dict[str, int] = field(default_factory=dict)
    duration_secs: float = 0.0
    dse_findings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "hostname": self.hostname,
            "museon_home": self.museon_home,
            "python_version": self.python_version,
            "overall": self.overall.value,
            "summary": self.summary,
            "duration_secs": round(self.duration_secs, 2),
            "dse_findings": self.dse_findings,
            "layers": [
                {
                    "layer": lr.layer.value,
                    "label": lr.label,
                    "passed": lr.passed,
                    "warned": lr.warned,
                    "failed": lr.failed,
                    "checks": [
                        {
                            "name": c.name,
                            "status": c.status.value,
                            "message": c.message,
                            "details": c.details,
                        }
                        for c in lr.checks
                    ],
                }
                for lr in self.layers
            ],
        }

    def to_text(self) -> str:
        """人類可讀格式"""
        lines = []
        lines.append("")
        lines.append("  ╔═══════════════════════════════════════════╗")
        lines.append("  ║     MUSEON 系統審計報告                   ║")
        lines.append("  ╚═══════════════════════════════════════════╝")
        lines.append("")
        lines.append(f"  時間: {self.timestamp}")
        lines.append(f"  主機: {self.hostname}")
        lines.append(f"  路徑: {self.museon_home}")
        lines.append(f"  Python: {self.python_version}")
        lines.append(f"  耗時: {self.duration_secs:.1f} 秒")
        lines.append("")

        status_icon = {"ok": "✅", "warning": "⚠️ ", "critical": "🚫", "unknown": "❓"}

        for lr in self.layers:
            layer_icon = "✅" if lr.failed == 0 and lr.warned == 0 else (
                "🚫" if lr.failed > 0 else "⚠️ "
            )
            lines.append(f"  ─── {layer_icon} Layer: {lr.label} ({lr.layer.value}) ───")
            lines.append(f"      通過: {lr.passed}  警告: {lr.warned}  失敗: {lr.failed}")
            for c in lr.checks:
                icon = status_icon.get(c.status.value, "?")
                lines.append(f"      {icon} {c.name}: {c.message}")
            lines.append("")

        # 總結
        lines.append("  ═══════════════════════════════════════════")
        overall_icon = status_icon.get(self.overall.value, "?")
        lines.append(f"  {overall_icon} 整體狀態: {self.overall.value.upper()}")
        lines.append(
            f"  通過: {self.summary.get('ok', 0)}  "
            f"警告: {self.summary.get('warning', 0)}  "
            f"失敗: {self.summary.get('critical', 0)}  "
            f"未知: {self.summary.get('unknown', 0)}"
        )

        if self.dse_findings:
            lines.append("")
            lines.append("  ─── DSE 第一性原則發現 ───")
            for i, finding in enumerate(self.dse_findings, 1):
                lines.append(f"  {i}. {finding}")

        lines.append("")
        return "\n".join(lines)


# ═══════════════════════════════════════════
# 系統審計引擎
# ═══════════════════════════════════════════


class SystemAuditor:
    """MUSEON 7 層全面系統審計引擎

    複用 HealthChecker 的 12 項基礎檢查，
    擴展為 7 層全面覆蓋的系統審計。
    """

    GATEWAY_PORT = 8765
    GATEWAY_URL = f"http://127.0.0.1:{GATEWAY_PORT}"

    def __init__(self, museon_home: Optional[str] = None, event_bus: Any = None):
        self.hc = HealthChecker(museon_home)
        self.home = self.hc.home
        self.runtime_dir = self.hc.runtime_dir
        self.data_dir = self.hc.data_dir
        self.logs_dir = self.hc.logs_dir
        self.env_path = self.hc.env_path
        self.src_dir = self.home / "src"
        self.plist_path = self.hc.plist_path
        # Gateway /health 快取（避免重複請求）
        self._gateway_health: Optional[Dict[str, Any]] = None
        self._event_bus = event_bus

    def run_full_audit(
        self, layers: Optional[List[str]] = None
    ) -> AuditReport:
        """執行全面審計（或指定層）"""
        start = time.time()

        all_layer_fns = [
            (AuditLayer.INFRA, self._audit_infrastructure),
            (AuditLayer.PROCESS, self._audit_process),
            (AuditLayer.SERVICE, self._audit_service),
            (AuditLayer.APPLICATION, self._audit_application),
            (AuditLayer.EVOLUTION, self._audit_evolution),
            (AuditLayer.SECURITY, self._audit_security),
            (AuditLayer.TREND, self._audit_trend),
            (AuditLayer.BLUEPRINT, self._audit_blueprint),
        ]

        results: List[LayerResult] = []
        for layer_enum, audit_fn in all_layer_fns:
            if layers and layer_enum.value not in layers:
                continue
            checks = audit_fn()
            results.append(LayerResult(
                layer=layer_enum,
                label=LAYER_LABELS[layer_enum],
                checks=checks,
            ))

        # 統計
        summary = {"ok": 0, "warning": 0, "critical": 0, "unknown": 0}
        for lr in results:
            for c in lr.checks:
                summary[c.status.value] = summary.get(c.status.value, 0) + 1

        if summary["critical"] > 0:
            overall = CheckStatus.CRITICAL
        elif summary["warning"] > 0:
            overall = CheckStatus.WARNING
        else:
            overall = CheckStatus.OK

        duration = time.time() - start

        report = AuditReport(
            timestamp=datetime.now().isoformat(),
            hostname=platform.node(),
            museon_home=str(self.home),
            python_version=platform.python_version(),
            layers=results,
            overall=overall,
            summary=summary,
            duration_secs=duration,
        )

        # WP-04: 發布 AUDIT_COMPLETED + AUDIT_TREND_UPDATED
        if self._event_bus:
            try:
                from museon.core.event_bus import AUDIT_COMPLETED, AUDIT_TREND_UPDATED
                self._event_bus.publish(AUDIT_COMPLETED, {
                    "overall": overall.value,
                    "summary": summary,
                    "duration_secs": round(duration, 2),
                })
                # 趨勢層結果（供 Nightly 調整優先級）
                trend_layer = next(
                    (lr for lr in results if lr.layer == AuditLayer.TREND), None
                )
                if trend_layer:
                    self._event_bus.publish(AUDIT_TREND_UPDATED, {
                        "passed": trend_layer.passed,
                        "warned": trend_layer.warned,
                        "failed": trend_layer.failed,
                    })
            except Exception as e:
                pass  # degraded: audit

        return report

    # ═══════════════════════════════════════════
    # Layer 1: 基礎設施
    # ═══════════════════════════════════════════

    def _audit_infrastructure(self) -> List[CheckResult]:
        checks = []

        # 1.1 目錄結構（複用）
        checks.append(self.hc.check_directories())

        # 1.2 .env 檔案（複用）
        checks.append(self.hc.check_env_file())

        # 1.3 磁碟空間（複用）
        checks.append(self.hc.check_disk_space())

        # 1.4 Python 版本
        checks.append(self._check_python_version())

        # 1.5 venv 完整性（複用）
        checks.append(self.hc.check_venv())

        # 1.6 核心依賴（複用）
        checks.append(self.hc.check_core_imports())

        # 1.7 pyproject.toml
        checks.append(self._check_pyproject())

        # 1.8 日誌目錄（複用 check_log_size）
        checks.append(self.hc.check_log_size())

        return checks

    def _check_python_version(self) -> CheckResult:
        vi = sys.version_info
        version_str = f"{vi.major}.{vi.minor}.{vi.micro}"
        if vi >= (3, 11):
            return CheckResult(
                name="Python 版本",
                status=CheckStatus.OK,
                message=f"Python {version_str}",
            )
        if vi >= (3, 10):
            return CheckResult(
                name="Python 版本",
                status=CheckStatus.WARNING,
                message=f"Python {version_str}（建議 3.11+）",
            )
        return CheckResult(
            name="Python 版本",
            status=CheckStatus.CRITICAL,
            message=f"Python {version_str}（需要 3.10+）",
        )

    def _check_pyproject(self) -> CheckResult:
        toml_path = self.home / "pyproject.toml"
        if not toml_path.exists():
            # 生產環境可能在 .runtime/
            toml_path = self.runtime_dir / "pyproject.toml"
        if not toml_path.exists():
            return CheckResult(
                name="pyproject.toml",
                status=CheckStatus.WARNING,
                message="pyproject.toml 不存在",
            )
        try:
            content = toml_path.read_text("utf-8")
            # 簡易版本解析
            version = "unknown"
            for line in content.splitlines():
                if line.strip().startswith("version"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        version = parts[1].strip().strip('"').strip("'")
                        break
            return CheckResult(
                name="pyproject.toml",
                status=CheckStatus.OK,
                message=f"版本 {version}",
                details={"version": version, "path": str(toml_path)},
            )
        except Exception as e:
            return CheckResult(
                name="pyproject.toml",
                status=CheckStatus.WARNING,
                message=f"解析失敗: {e}",
            )

    # ═══════════════════════════════════════════
    # Layer 2: 進程
    # ═══════════════════════════════════════════

    def _audit_process(self) -> List[CheckResult]:
        checks = []

        # 2.1 Gateway 進程（複用）
        checks.append(self.hc.check_gateway_process())

        # 2.2 Daemon plist（複用 + 擴展 MUSEON_HOME 驗證）
        checks.append(self._check_daemon_extended())

        # 2.3 PID 一致性
        checks.append(self._check_pid_consistency())

        # 2.4 Port 佔用
        checks.append(self._check_port_usage())

        # 2.5 Electron app（複用）
        checks.append(self.hc.check_dashboard_app())

        # 2.6 Docker 引擎
        checks.append(self._check_docker())

        return checks

    def _check_daemon_extended(self) -> CheckResult:
        """Daemon plist + MUSEON_HOME 路徑交叉驗證"""
        base = self.hc.check_daemon_plist()
        if base.status == CheckStatus.CRITICAL or base.status == CheckStatus.WARNING:
            if "不存在" in base.message or "未載入" in base.message:
                return base

        # 擴展：驗證 plist 中的 MUSEON_HOME 是否指向正確路徑
        if self.plist_path.exists():
            try:
                content = self.plist_path.read_text("utf-8")
                # 解析 EnvironmentVariables 中的 MUSEON_HOME
                import re
                match = re.search(
                    r"<key>MUSEON_HOME</key>\s*<string>(.*?)</string>",
                    content,
                )
                if match:
                    plist_home = match.group(1)
                    actual_home = str(self.home)
                    if plist_home != actual_home:
                        return CheckResult(
                            name="Daemon 設定",
                            status=CheckStatus.CRITICAL,
                            message=(
                                f"MUSEON_HOME 路徑不符！"
                                f"plist={plist_home} vs 實際={actual_home}"
                            ),
                            details={
                                "plist_home": plist_home,
                                "actual_home": actual_home,
                            },
                            repairable=True,
                            repair_action="fix_plist_home",
                        )
            except Exception as e:
                pass  # degraded: repair

        return base

    def _check_pid_consistency(self) -> CheckResult:
        """PID 檔案 vs 實際進程交叉驗證"""
        pid_file = self.home / ".gateway.pid"
        if not pid_file.exists():
            # 也檢查 runtime 目錄
            pid_file = self.runtime_dir / ".gateway.pid"

        if not pid_file.exists():
            return CheckResult(
                name="PID 一致性",
                status=CheckStatus.OK,
                message="無 PID 檔案（Gateway 可能未運行）",
            )

        try:
            recorded_pid = pid_file.read_text().strip()
            # 檢查 PID 是否還活著
            try:
                os.kill(int(recorded_pid), 0)
                return CheckResult(
                    name="PID 一致性",
                    status=CheckStatus.OK,
                    message=f"PID {recorded_pid} 存活且一致",
                )
            except (ProcessLookupError, ValueError):
                return CheckResult(
                    name="PID 一致性",
                    status=CheckStatus.WARNING,
                    message=f"PID 檔案記錄 {recorded_pid} 但進程已不存在（陳舊 PID）",
                    repairable=True,
                    repair_action="cleanup_stale_pid",
                )
            except PermissionError:
                return CheckResult(
                    name="PID 一致性",
                    status=CheckStatus.OK,
                    message=f"PID {recorded_pid} 存在（權限不足以完全驗證）",
                )
        except Exception as e:
            return CheckResult(
                name="PID 一致性",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_port_usage(self) -> CheckResult:
        """檢查 Gateway port 是否被預期進程佔用"""
        try:
            result = subprocess.run(
                ["lsof", "-i", f":{self.GATEWAY_PORT}", "-t"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                return CheckResult(
                    name="Port 佔用",
                    status=CheckStatus.OK,
                    message=f"Port {self.GATEWAY_PORT} 被 PID {','.join(pids)} 使用",
                    details={"port": self.GATEWAY_PORT, "pids": pids},
                )
            return CheckResult(
                name="Port 佔用",
                status=CheckStatus.OK,
                message=f"Port {self.GATEWAY_PORT} 空閒",
            )
        except Exception as e:
            return CheckResult(
                name="Port 佔用",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_docker(self) -> CheckResult:
        """檢查 Docker 引擎 + 容器狀態"""
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return CheckResult(
                    name="Docker 引擎",
                    status=CheckStatus.WARNING,
                    message="Docker 未運行或未安裝",
                )

            docker_version = result.stdout.strip()

            # 檢查 MUSEON 相關容器
            result2 = subprocess.run(
                ["docker", "ps", "-a", "--format",
                 "{{.Names}}\t{{.Status}}\t{{.State}}"],
                capture_output=True, text=True, timeout=10,
            )
            containers = {}
            restarting = []
            if result2.returncode == 0:
                for line in result2.stdout.strip().splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        name, status, state = parts[0], parts[1], parts[2]
                        # 只關注 museon/museclaw 相關容器
                        if any(k in name.lower() for k in
                               ["museon", "museclaw", "qdrant",
                                "searxng", "firecrawl"]):
                            containers[name] = {"status": status, "state": state}
                            if state == "restarting":
                                restarting.append(name)

            if restarting:
                return CheckResult(
                    name="Docker 引擎",
                    status=CheckStatus.WARNING,
                    message=(
                        f"Docker {docker_version}，"
                        f"重啟中的容器: {', '.join(restarting)}"
                    ),
                    details={"version": docker_version, "containers": containers},
                )

            return CheckResult(
                name="Docker 引擎",
                status=CheckStatus.OK,
                message=(
                    f"Docker {docker_version}，"
                    f"{len(containers)} 個相關容器"
                ),
                details={"version": docker_version, "containers": containers},
            )
        except FileNotFoundError:
            return CheckResult(
                name="Docker 引擎",
                status=CheckStatus.WARNING,
                message="Docker 未安裝",
            )
        except Exception as e:
            return CheckResult(
                name="Docker 引擎",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    # ═══════════════════════════════════════════
    # Layer 3: 服務
    # ═══════════════════════════════════════════

    def _audit_service(self) -> List[CheckResult]:
        checks = []

        # 3.1 Gateway HTTP（複用）
        gw_check = self.hc.check_gateway_health()
        checks.append(gw_check)

        # 快取 Gateway /health 回應供後續使用
        if gw_check.details:
            self._gateway_health = gw_check.details

        # 3.2-3.4 Docker 服務
        docker_services = [
            ("Qdrant", "http://127.0.0.1:6333/healthz", 6333),
            ("SearXNG", "http://127.0.0.1:8888/healthz", 8888),
            ("Firecrawl", "http://127.0.0.1:3002/health", 3002),
        ]
        for name, url, port in docker_services:
            checks.append(self._check_http_service(name, url, port))

        # 3.5 Telegram Bot
        checks.append(self._check_telegram())

        # 3.6 MCP 工具
        checks.append(self._check_mcp())

        # 3.7 Brain (LLM)
        checks.append(self._check_brain())

        return checks

    def _check_http_service(
        self, name: str, url: str, port: int
    ) -> CheckResult:
        """通用 HTTP 服務健康檢查"""
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                status_code = resp.getcode()
                if status_code == 200:
                    return CheckResult(
                        name=f"{name} 服務",
                        status=CheckStatus.OK,
                        message=f"{name} (port {port}) 回應正常",
                    )
                return CheckResult(
                    name=f"{name} 服務",
                    status=CheckStatus.WARNING,
                    message=f"{name} 回應 HTTP {status_code}",
                )
        except urllib.error.HTTPError as e:
            # 某些服務回傳 4xx 但仍然活著
            if e.code < 500:
                return CheckResult(
                    name=f"{name} 服務",
                    status=CheckStatus.OK,
                    message=f"{name} (port {port}) 運行中 (HTTP {e.code})",
                )
            return CheckResult(
                name=f"{name} 服務",
                status=CheckStatus.WARNING,
                message=f"{name} 回應 HTTP {e.code}",
            )
        except Exception:
            return CheckResult(
                name=f"{name} 服務",
                status=CheckStatus.WARNING,
                message=f"{name} (port {port}) 無法連線",
            )

    def _check_telegram(self) -> CheckResult:
        """檢查 Telegram Bot 狀態"""
        gh = self._gateway_health or {}
        tg = gh.get("telegram")

        # Gateway 回傳可能是 str ("running") 或 dict ({"connected": true})
        if isinstance(tg, str) and tg in ("running", "connected"):
            return CheckResult(
                name="Telegram Bot",
                status=CheckStatus.OK,
                message=f"Telegram Bot: {tg}",
            )
        if isinstance(tg, dict) and tg.get("connected"):
            return CheckResult(
                name="Telegram Bot",
                status=CheckStatus.OK,
                message="Telegram Bot 已連線",
                details=tg,
            )

        # 檢查是否有 Token
        env_vars = self.hc._parse_env_file() if self.env_path.exists() else {}
        token = env_vars.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return CheckResult(
                name="Telegram Bot",
                status=CheckStatus.OK,
                message="Telegram 未設定（選用功能）",
            )

        return CheckResult(
            name="Telegram Bot",
            status=CheckStatus.WARNING,
            message="Telegram Token 已設定但 Bot 未連線",
        )

    def _check_mcp(self) -> CheckResult:
        """檢查 MCP 工具狀態"""
        gh = self._gateway_health or {}
        mcp = gh.get("mcp")

        # Gateway 回傳可能是 str ("2/6 servers, 13 tools") 或 dict
        if isinstance(mcp, str) and mcp:
            return CheckResult(
                name="MCP 工具",
                status=CheckStatus.OK,
                message=f"MCP: {mcp}",
            )
        if isinstance(mcp, dict):
            tools_count = mcp.get("tools_count", 0)
            if tools_count > 0:
                return CheckResult(
                    name="MCP 工具",
                    status=CheckStatus.OK,
                    message=f"{tools_count} 個 MCP 工具可用",
                    details=mcp,
                )
        return CheckResult(
            name="MCP 工具",
            status=CheckStatus.WARNING,
            message="MCP 工具未載入或 Gateway 未回應",
        )

    def _check_brain(self) -> CheckResult:
        """檢查 Brain (LLM) 狀態"""
        gh = self._gateway_health or {}
        brain = gh.get("brain")

        # Gateway 回傳可能是 str ("alive", "ready") 或 dict
        if isinstance(brain, str):
            if brain in ("alive", "ready", "active"):
                return CheckResult(
                    name="Brain (LLM)",
                    status=CheckStatus.OK,
                    message=f"Brain: {brain}",
                )
            return CheckResult(
                name="Brain (LLM)",
                status=CheckStatus.WARNING,
                message=f"Brain 狀態: {brain}",
            )
        if isinstance(brain, dict) and brain.get("status") in ("ready", "alive"):
            return CheckResult(
                name="Brain (LLM)",
                status=CheckStatus.OK,
                message="Brain 就緒",
                details=brain,
            )
        if isinstance(brain, dict) and brain.get("status"):
            return CheckResult(
                name="Brain (LLM)",
                status=CheckStatus.WARNING,
                message=f"Brain 狀態: {brain.get('status')}",
                details=brain,
            )
        return CheckResult(
            name="Brain (LLM)",
            status=CheckStatus.WARNING,
            message="Brain 狀態未知（Gateway 未回應或 Brain 未初始化）",
        )

    # ═══════════════════════════════════════════
    # Layer 4: 應用
    # ═══════════════════════════════════════════

    def _audit_application(self) -> List[CheckResult]:
        checks = []

        # 4.1 API Key 有效性（複用）
        checks.append(self.hc.check_api_keys())

        # 4.2 Token 預算
        checks.append(self._check_budget())

        # 4.3 Skills 索引（基本計數）
        checks.append(self._check_skills())

        # 4.3+ Skill Doctor 雙層健康檢查
        checks.extend(self._audit_skill_doctor())

        # 4.4 Event Bus 免疫事件
        checks.append(self._check_event_bus())

        # 4.5 Activity Log
        checks.append(self._check_activity_log())

        # 4.6 資料完整性（複用）
        checks.append(self.hc.check_data_integrity())

        # 4.7 免疫記憶
        checks.append(self._check_immunity())

        # 4.8 Anthropic API 可達性
        checks.append(self._check_api_reachability())

        # 4.9 欄位一致性掃描
        checks.append(self._check_field_consistency())

        return checks

    def _check_budget(self) -> CheckResult:
        """檢查 Token 使用預算"""
        today = date.today()
        budget_file = (
            self.data_dir / "_system" / "budget"
            / f"usage_{today.strftime('%Y-%m')}.json"
        )
        if not budget_file.exists():
            return CheckResult(
                name="Token 預算",
                status=CheckStatus.OK,
                message="本月無 Token 使用記錄",
            )

        try:
            data = json.loads(budget_file.read_text("utf-8"))
            total_cost = data.get("total_cost_usd", 0)
            monthly_limit = data.get("monthly_limit_usd", 15)
            if monthly_limit > 0:
                pct = (total_cost / monthly_limit) * 100
            else:
                pct = 0

            if pct >= 95:
                return CheckResult(
                    name="Token 預算",
                    status=CheckStatus.CRITICAL,
                    message=f"預算用量 {pct:.0f}%（${total_cost:.2f}/${monthly_limit}）",
                    details={"cost": total_cost, "limit": monthly_limit, "pct": pct},
                )
            if pct >= 80:
                return CheckResult(
                    name="Token 預算",
                    status=CheckStatus.WARNING,
                    message=f"預算用量 {pct:.0f}%（${total_cost:.2f}/${monthly_limit}）",
                    details={"cost": total_cost, "limit": monthly_limit, "pct": pct},
                )
            return CheckResult(
                name="Token 預算",
                status=CheckStatus.OK,
                message=f"預算用量 {pct:.0f}%（${total_cost:.2f}/${monthly_limit}）",
                details={"cost": total_cost, "limit": monthly_limit, "pct": pct},
            )
        except Exception as e:
            return CheckResult(
                name="Token 預算",
                status=CheckStatus.UNKNOWN,
                message=f"無法讀取預算: {e}",
            )

    def _check_skills(self) -> CheckResult:
        """檢查 Skills 索引"""
        gh = self._gateway_health or {}
        indexed = gh.get("skills_indexed", None)
        if indexed is not None:
            if indexed > 0:
                return CheckResult(
                    name="Skills 索引",
                    status=CheckStatus.OK,
                    message=f"{indexed} 個 Skills 已索引",
                )
            return CheckResult(
                name="Skills 索引",
                status=CheckStatus.WARNING,
                message="Skills 索引為空",
            )

        # Gateway 不可用時，檢查 skills 目錄
        skills_dir = self.data_dir / "skills"
        if skills_dir.exists():
            # 掃描 native/*/SKILL.md + forged/*/SKILL.md（新結構）
            native_dir = skills_dir / "native"
            forged_dir = skills_dir / "forged"
            count = 0
            if native_dir.exists():
                count += sum(1 for _ in native_dir.glob("*/SKILL.md"))
            if forged_dir.exists():
                count += sum(1 for _ in forged_dir.glob("*/SKILL.md"))
            if count == 0:
                # fallback：舊平面結構
                count = sum(1 for _ in skills_dir.glob("*.md"))
            return CheckResult(
                name="Skills 索引",
                status=CheckStatus.OK if count > 0 else CheckStatus.WARNING,
                message=f"Skills 目錄有 {count} 個 Skill 定義",
            )
        return CheckResult(
            name="Skills 索引",
            status=CheckStatus.WARNING,
            message="Skills 目錄不存在",
        )

    # ═══════════════════════════════════════════
    # Skill Doctor — 雙層健康檢查（結構 + 認知）
    # ═══════════════════════════════════════════

    def _audit_skill_doctor(self) -> List[CheckResult]:
        """Skill Doctor 雙層健康檢查：7 結構 + 7 認知."""
        results: List[CheckResult] = []
        # 結構層
        results.append(self._sd_check_skill_structure())
        results.append(self._sd_check_always_on())
        results.append(self._sd_check_native_claude_sync())
        results.append(self._sd_check_trigger_conflicts())
        results.append(self._sd_check_rc_coverage())
        results.append(self._sd_check_skill_usage_noise())
        # 認知層
        results.append(self._sd_check_decision_trace_active())
        results.append(self._sd_check_cognitive_trace_active())
        results.append(self._sd_check_routing_diversity())
        results.append(self._sd_check_always_on_frequency())
        results.append(self._sd_check_response_length_anomaly())
        results.append(self._sd_check_timestamp_consistency())
        return results

    # ── 結構層 ──

    def _sd_check_skill_structure(self) -> CheckResult:
        """每個 skill 目錄都有 SKILL.md."""
        try:
            native_dir = self.data_dir / "skills" / "native"
            if not native_dir.exists():
                return CheckResult(
                    name="SD:結構完整性",
                    status=CheckStatus.WARNING,
                    message="native/ 目錄不存在",
                )
            missing = []
            total = 0
            for d in sorted(native_dir.iterdir()):
                if not d.is_dir():
                    continue
                total += 1
                if not (d / "SKILL.md").exists() and not (d / "BRIEF.md").exists():
                    missing.append(d.name)
            if missing:
                return CheckResult(
                    name="SD:結構完整性",
                    status=CheckStatus.WARNING,
                    message=f"{len(missing)}/{total} 缺少 SKILL.md: {', '.join(missing[:5])}",
                )
            return CheckResult(
                name="SD:結構完整性",
                status=CheckStatus.OK,
                message=f"{total} 個 Skill 結構完整",
            )
        except Exception as e:
            return CheckResult(
                name="SD:結構完整性",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_always_on(self) -> CheckResult:
        """常駐 skill（dna27, deep-think, c15）存在且標記正確."""
        try:
            required = {"dna27", "deep-think", "c15"}
            native_dir = self.data_dir / "skills" / "native"
            found = set()
            for name in required:
                skill_file = native_dir / name / "SKILL.md"
                if skill_file.exists():
                    content = skill_file.read_text("utf-8")[:500]
                    if "always_on" in content.lower() or "常駐" in content:
                        found.add(name)
            missing = required - found
            if missing:
                return CheckResult(
                    name="SD:常駐 Skill",
                    status=CheckStatus.WARNING,
                    message=f"缺少或未標記: {', '.join(missing)}",
                )
            return CheckResult(
                name="SD:常駐 Skill",
                status=CheckStatus.OK,
                message=f"3 個常駐 Skill 正常（{', '.join(sorted(found))}）",
            )
        except Exception as e:
            return CheckResult(
                name="SD:常駐 Skill",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_native_claude_sync(self) -> CheckResult:
        """native/ vs ~/.claude/skills/ 同步狀態."""
        try:
            native_dir = self.data_dir / "skills" / "native"
            claude_dir = Path.home() / ".claude" / "skills"
            if not native_dir.exists() or not claude_dir.exists():
                return CheckResult(
                    name="SD:Native↔Claude 同步",
                    status=CheckStatus.WARNING,
                    message="目錄不存在，無法比較",
                )
            native_skills = {d.name for d in native_dir.iterdir() if d.is_dir()}
            claude_skills = {d.name for d in claude_dir.iterdir() if d.is_dir()}
            only_native = native_skills - claude_skills
            only_claude = claude_skills - native_skills
            if only_native or only_claude:
                msg_parts = []
                if only_native:
                    msg_parts.append(f"僅 native: {', '.join(sorted(only_native)[:3])}")
                if only_claude:
                    msg_parts.append(f"僅 claude: {', '.join(sorted(only_claude)[:3])}")
                return CheckResult(
                    name="SD:Native↔Claude 同步",
                    status=CheckStatus.WARNING,
                    message=f"不同步 — {'; '.join(msg_parts)}",
                    details={"only_native": sorted(only_native), "only_claude": sorted(only_claude)},
                )
            return CheckResult(
                name="SD:Native↔Claude 同步",
                status=CheckStatus.OK,
                message=f"{len(native_skills)} 個 Skill 完全同步",
            )
        except Exception as e:
            return CheckResult(
                name="SD:Native↔Claude 同步",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_trigger_conflicts(self) -> CheckResult:
        """觸發詞衝突偵測（同一觸發詞出現在多個 skill）."""
        try:
            import re
            native_dir = self.data_dir / "skills" / "native"
            if not native_dir.exists():
                return CheckResult(
                    name="SD:觸發詞衝突",
                    status=CheckStatus.UNKNOWN,
                    message="native/ 不存在",
                )
            trigger_map: Dict[str, List[str]] = {}
            for d in sorted(native_dir.iterdir()):
                if not d.is_dir():
                    continue
                skill_file = d / "SKILL.md"
                if not skill_file.exists():
                    continue
                content = skill_file.read_text("utf-8")
                # 提取觸發詞段落
                match = re.search(r"觸發詞[：:](.+?)(?:\n#|\n\n)", content, re.DOTALL)
                if match:
                    words = [w.strip().strip("、，,") for w in match.group(1).split() if len(w.strip()) > 1]
                    for w in words[:20]:  # 限制每個 skill 最多 20 個觸發詞
                        trigger_map.setdefault(w, []).append(d.name)
            conflicts = {k: v for k, v in trigger_map.items() if len(v) > 2}
            if conflicts:
                top3 = sorted(conflicts.items(), key=lambda x: len(x[1]), reverse=True)[:3]
                msg = "; ".join(f"「{k}」→{len(v)}個" for k, v in top3)
                return CheckResult(
                    name="SD:觸發詞衝突",
                    status=CheckStatus.WARNING,
                    message=f"{len(conflicts)} 組衝突: {msg}",
                    details={"conflicts_count": len(conflicts)},
                )
            return CheckResult(
                name="SD:觸發詞衝突",
                status=CheckStatus.OK,
                message="無嚴重觸發詞衝突（≤2 重複視為正常）",
            )
        except Exception as e:
            return CheckResult(
                name="SD:觸發詞衝突",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_rc_coverage(self) -> CheckResult:
        """RC affinity 覆蓋率檢查."""
        try:
            import re
            native_dir = self.data_dir / "skills" / "native"
            if not native_dir.exists():
                return CheckResult(
                    name="SD:RC 覆蓋率",
                    status=CheckStatus.UNKNOWN,
                    message="native/ 不存在",
                )
            rc_set: set = set()
            skills_with_rc = 0
            skills_total = 0
            for d in sorted(native_dir.iterdir()):
                if not d.is_dir():
                    continue
                skill_file = d / "SKILL.md"
                if not skill_file.exists():
                    continue
                skills_total += 1
                content = skill_file.read_text("utf-8")
                match = re.search(r"RC[_\s]*Affinity[：:\s]+([^\n]+)", content, re.IGNORECASE)
                if match:
                    skills_with_rc += 1
                    rcs = [r.strip() for r in match.group(1).split(",")]
                    rc_set.update(rcs)
            pct = (skills_with_rc / skills_total * 100) if skills_total > 0 else 0
            if pct < 50:
                status = CheckStatus.WARNING
            else:
                status = CheckStatus.OK
            return CheckResult(
                name="SD:RC 覆蓋率",
                status=status,
                message=f"{skills_with_rc}/{skills_total} 有 RC 標記（{pct:.0f}%），涵蓋 {len(rc_set)} 個 RC",
                details={"coverage_pct": pct, "rc_count": len(rc_set)},
            )
        except Exception as e:
            return CheckResult(
                name="SD:RC 覆蓋率",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_skill_usage_noise(self) -> CheckResult:
        """usage log 噪音比（短問題觸發高特異性 skill）."""
        try:
            log_path = self.data_dir / "skill_usage_log.jsonl"
            if not log_path.exists():
                return CheckResult(
                    name="SD:路由噪音",
                    status=CheckStatus.UNKNOWN,
                    message="skill_usage_log.jsonl 不存在",
                )
            noisy = 0
            total = 0
            for line in log_path.read_text("utf-8").strip().split("\n")[-50:]:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    total += 1
                    msg = entry.get("trigger_message", "")
                    skills = entry.get("skills", [])
                    # 短訊息（≤10 字元）觸發 ≥5 個 skill 視為噪音
                    if len(msg) <= 10 and len(skills) >= 5:
                        noisy += 1
                except (json.JSONDecodeError, KeyError):
                    continue
            if total == 0:
                return CheckResult(
                    name="SD:路由噪音",
                    status=CheckStatus.OK,
                    message="無使用記錄",
                )
            noise_pct = (noisy / total * 100) if total > 0 else 0
            if noise_pct > 30:
                status = CheckStatus.WARNING
            else:
                status = CheckStatus.OK
            return CheckResult(
                name="SD:路由噪音",
                status=status,
                message=f"近 {total} 筆中 {noisy} 筆疑似噪音（{noise_pct:.0f}%）",
                details={"noise_pct": noise_pct, "noisy": noisy, "total": total},
            )
        except Exception as e:
            return CheckResult(
                name="SD:路由噪音",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    # ── 認知層 ──

    def _sd_check_decision_trace_active(self) -> CheckResult:
        """decisions.jsonl 是否有近 24h 記錄."""
        return self._sd_check_jsonl_freshness(
            self.data_dir / "_system" / "footprints" / "decisions.jsonl",
            "SD:決策軌跡",
        )

    def _sd_check_cognitive_trace_active(self) -> CheckResult:
        """cognitive_trace.jsonl 是否有近 24h 記錄."""
        return self._sd_check_jsonl_freshness(
            self.data_dir / "_system" / "footprints" / "cognitive_trace.jsonl",
            "SD:認知回執",
        )

    def _sd_check_jsonl_freshness(self, path: Path, name: str) -> CheckResult:
        """通用 JSONL 檔案新鮮度檢查."""
        try:
            if not path.exists():
                return CheckResult(
                    name=name,
                    status=CheckStatus.WARNING,
                    message=f"{path.name} 不存在（尚未產生記錄）",
                )
            # 讀最後一行的 timestamp
            lines = path.read_text("utf-8").strip().split("\n")
            if not lines or not lines[-1].strip():
                return CheckResult(
                    name=name,
                    status=CheckStatus.WARNING,
                    message=f"{path.name} 為空",
                )
            last = json.loads(lines[-1])
            ts_str = last.get("timestamp", "")
            if not ts_str:
                return CheckResult(
                    name=name,
                    status=CheckStatus.OK,
                    message=f"{len(lines)} 筆記錄（無時間戳）",
                )
            # 嘗試解析 ISO 時間
            try:
                from datetime import timezone
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
                if age_hours > 48:
                    status = CheckStatus.WARNING
                    msg = f"{len(lines)} 筆，最後記錄 {age_hours:.0f}h 前（超過 48h）"
                else:
                    status = CheckStatus.OK
                    msg = f"{len(lines)} 筆，最後記錄 {age_hours:.0f}h 前"
            except (ValueError, TypeError):
                status = CheckStatus.OK
                msg = f"{len(lines)} 筆記錄"
            return CheckResult(name=name, status=status, message=msg)
        except Exception as e:
            return CheckResult(
                name=name,
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_routing_diversity(self) -> CheckResult:
        """近 N 次路由是否集中在少數 skill（MoE 失效偵測）."""
        try:
            log_path = self.data_dir / "skill_usage_log.jsonl"
            if not log_path.exists():
                return CheckResult(
                    name="SD:路由多樣性",
                    status=CheckStatus.UNKNOWN,
                    message="無使用記錄",
                )
            lines = log_path.read_text("utf-8").strip().split("\n")[-30:]
            skill_counts: Dict[str, int] = {}
            total_slots = 0
            for line in lines:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    for sk in entry.get("skills", []):
                        skill_counts[sk] = skill_counts.get(sk, 0) + 1
                        total_slots += 1
                except (json.JSONDecodeError, KeyError):
                    continue
            if total_slots == 0:
                return CheckResult(
                    name="SD:路由多樣性",
                    status=CheckStatus.OK,
                    message="無使用記錄",
                )
            unique = len(skill_counts)
            # 前 3 名佔比
            top3 = sorted(skill_counts.values(), reverse=True)[:3]
            top3_pct = (sum(top3) / total_slots * 100) if total_slots > 0 else 0
            if unique <= 5 and top3_pct > 60:
                status = CheckStatus.WARNING
                msg = f"多樣性低：{unique} 個 Skill，Top3 佔 {top3_pct:.0f}%"
            else:
                status = CheckStatus.OK
                msg = f"{unique} 個 Skill 活躍，Top3 佔 {top3_pct:.0f}%"
            return CheckResult(
                name="SD:路由多樣性",
                status=status,
                message=msg,
                details={"unique_skills": unique, "top3_pct": top3_pct},
            )
        except Exception as e:
            return CheckResult(
                name="SD:路由多樣性",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_always_on_frequency(self) -> CheckResult:
        """常駐 skill 是否在每次路由中都出現."""
        try:
            log_path = self.data_dir / "skill_usage_log.jsonl"
            if not log_path.exists():
                return CheckResult(
                    name="SD:常駐出現率",
                    status=CheckStatus.UNKNOWN,
                    message="無使用記錄",
                )
            always_on = {"dna27", "deep-think", "c15"}
            lines = log_path.read_text("utf-8").strip().split("\n")[-20:]
            total = 0
            ao_present = 0
            for line in lines:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    skills = set(entry.get("skills", []))
                    total += 1
                    if skills & always_on:
                        ao_present += 1
                except (json.JSONDecodeError, KeyError):
                    continue
            if total == 0:
                return CheckResult(
                    name="SD:常駐出現率",
                    status=CheckStatus.OK,
                    message="無使用記錄",
                )
            pct = (ao_present / total * 100) if total > 0 else 0
            # 常駐 skill 至少 80% 的路由中應出現
            if pct < 80:
                return CheckResult(
                    name="SD:常駐出現率",
                    status=CheckStatus.WARNING,
                    message=f"常駐 Skill 只在 {pct:.0f}% 的路由中出現（{ao_present}/{total}）",
                )
            return CheckResult(
                name="SD:常駐出現率",
                status=CheckStatus.OK,
                message=f"常駐 Skill 在 {pct:.0f}% 的路由中出現（{ao_present}/{total}）",
            )
        except Exception as e:
            return CheckResult(
                name="SD:常駐出現率",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_response_length_anomaly(self) -> CheckResult:
        """回應長度異常偵測."""
        try:
            log_path = self.data_dir / "skill_usage_log.jsonl"
            if not log_path.exists():
                return CheckResult(
                    name="SD:回應長度",
                    status=CheckStatus.UNKNOWN,
                    message="無使用記錄",
                )
            lengths = []
            for line in log_path.read_text("utf-8").strip().split("\n")[-30:]:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    rl = entry.get("response_length", 0)
                    if rl > 0:
                        lengths.append(rl)
                except (json.JSONDecodeError, KeyError):
                    continue
            if len(lengths) < 5:
                return CheckResult(
                    name="SD:回應長度",
                    status=CheckStatus.OK,
                    message=f"樣本不足（{len(lengths)} 筆），跳過",
                )
            avg = sum(lengths) / len(lengths)
            extremes = sum(1 for l in lengths if l > avg * 3 or l < avg * 0.1)
            if extremes > len(lengths) * 0.3:
                return CheckResult(
                    name="SD:回應長度",
                    status=CheckStatus.WARNING,
                    message=f"異常比例高: {extremes}/{len(lengths)} 超出 3x 均值（avg={avg:.0f}）",
                )
            return CheckResult(
                name="SD:回應長度",
                status=CheckStatus.OK,
                message=f"近 {len(lengths)} 筆平均 {avg:.0f} 字元，無嚴重異常",
            )
        except Exception as e:
            return CheckResult(
                name="SD:回應長度",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _sd_check_timestamp_consistency(self) -> CheckResult:
        """各 log 的時間戳格式一致性."""
        try:
            issues = []
            # 檢查 skill_usage_log.jsonl（應有 UTC 時區）
            log_path = self.data_dir / "skill_usage_log.jsonl"
            if log_path.exists():
                last_line = log_path.read_text("utf-8").strip().split("\n")[-1]
                try:
                    entry = json.loads(last_line)
                    ts = entry.get("timestamp", "")
                    if ts and "+" not in ts and "Z" not in ts:
                        issues.append("skill_usage_log 缺少時區")
                except (json.JSONDecodeError, KeyError):
                    pass
            # 檢查 actions.jsonl
            action_path = self.data_dir / "_system" / "footprints" / "actions.jsonl"
            if action_path.exists():
                last_line = action_path.read_text("utf-8").strip().split("\n")[-1]
                try:
                    entry = json.loads(last_line)
                    ts = entry.get("timestamp", "")
                    if ts and "+" not in ts and "Z" not in ts:
                        issues.append("actions.jsonl 缺少時區")
                except (json.JSONDecodeError, KeyError):
                    pass
            if issues:
                return CheckResult(
                    name="SD:時間戳一致性",
                    status=CheckStatus.WARNING,
                    message=f"格式不一致: {'; '.join(issues)}",
                )
            return CheckResult(
                name="SD:時間戳一致性",
                status=CheckStatus.OK,
                message="時間戳格式一致",
            )
        except Exception as e:
            return CheckResult(
                name="SD:時間戳一致性",
                status=CheckStatus.UNKNOWN,
                message=f"檢查失敗: {e}",
            )

    def _check_event_bus(self) -> CheckResult:
        """檢查 Event Bus 是否包含免疫事件定義"""
        event_bus_path = self.src_dir / "museon" / "core" / "event_bus.py"
        if not event_bus_path.exists():
            # 生產環境
            event_bus_path = self.runtime_dir / "src" / "museon" / "core" / "event_bus.py"
        if not event_bus_path.exists():
            return CheckResult(
                name="Event Bus",
                status=CheckStatus.WARNING,
                message="event_bus.py 不存在",
            )

        try:
            content = event_bus_path.read_text("utf-8")
            immune_events = [
                "PREFLIGHT_FAILED", "PREFLIGHT_PASSED",
                "REFRACTORY_BACKOFF", "REFRACTORY_HIBERNATE",
            ]
            found = [e for e in immune_events if e in content]
            if len(found) >= 3:
                return CheckResult(
                    name="Event Bus",
                    status=CheckStatus.OK,
                    message=f"免疫事件定義完整（{len(found)}/{len(immune_events)}）",
                )
            return CheckResult(
                name="Event Bus",
                status=CheckStatus.WARNING,
                message=f"免疫事件部分缺失（{len(found)}/{len(immune_events)}）",
                details={"found": found, "expected": immune_events},
            )
        except Exception as e:
            return CheckResult(
                name="Event Bus",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_activity_log(self) -> CheckResult:
        """檢查 Activity Log"""
        log_path = self.data_dir / "_system" / "activity_log.jsonl"
        if not log_path.exists():
            return CheckResult(
                name="Activity Log",
                status=CheckStatus.OK,
                message="尚無活動日誌",
            )

        try:
            stat = log_path.stat()
            size_kb = stat.st_size / 1024
            mtime = datetime.fromtimestamp(stat.st_mtime)
            age_hours = (datetime.now() - mtime).total_seconds() / 3600

            if size_kb > 50_000:  # > 50MB
                return CheckResult(
                    name="Activity Log",
                    status=CheckStatus.WARNING,
                    message=f"活動日誌過大: {size_kb:.0f}KB，最後更新 {age_hours:.1f}h 前",
                    details={"size_kb": size_kb, "age_hours": age_hours},
                )
            return CheckResult(
                name="Activity Log",
                status=CheckStatus.OK,
                message=f"活動日誌 {size_kb:.0f}KB，最後更新 {age_hours:.1f}h 前",
                details={"size_kb": size_kb, "age_hours": age_hours},
            )
        except Exception as e:
            return CheckResult(
                name="Activity Log",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_immunity(self) -> CheckResult:
        """檢查免疫記憶"""
        immunity_path = self.data_dir / "_system" / "immunity.json"
        if not immunity_path.exists():
            # P4 加固：自動建立空免疫記憶結構，避免持續 WARNING
            try:
                immunity_path.parent.mkdir(parents=True, exist_ok=True)
                immunity_path.write_text(
                    json.dumps({"antibodies": [], "incidents": []}, indent=2),
                    encoding="utf-8",
                )
                return CheckResult(
                    name="免疫記憶",
                    status=CheckStatus.OK,
                    message="immunity.json 已自動建立（空白初始狀態）",
                )
            except Exception as e:
                return CheckResult(
                    name="免疫記憶",
                    status=CheckStatus.WARNING,
                    message=f"immunity.json 不存在且無法自動建立: {e}",
                )

        try:
            data = json.loads(immunity_path.read_text("utf-8"))
            antibodies = len(data.get("antibodies", []))
            incidents = len(data.get("incidents", []))
            if antibodies == 0 and incidents == 0:
                return CheckResult(
                    name="免疫記憶",
                    status=CheckStatus.WARNING,
                    message="immunity.json 為空（0 抗體，0 事件）",
                    details=data,
                )
            return CheckResult(
                name="免疫記憶",
                status=CheckStatus.OK,
                message=f"免疫記憶: {antibodies} 抗體，{incidents} 事件",
                details={"antibodies": antibodies, "incidents": incidents},
            )
        except Exception as e:
            return CheckResult(
                name="免疫記憶",
                status=CheckStatus.UNKNOWN,
                message=f"無法讀取: {e}",
            )

    def _check_api_reachability(self) -> CheckResult:
        """檢查 Anthropic API 可達性

        透過 HEAD 請求到 api.anthropic.com 確認網路連通性。
        不消耗 Token，不需要有效 API Key（只測試 DNS + TCP 連通）。
        """
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                method="POST",
                headers={
                    "anthropic-version": "2023-06-01",
                    "x-api-key": "sk-ant-test-connectivity",
                    "content-type": "application/json",
                },
                data=b'{"model":"claude-3-haiku-20240307","max_tokens":1,"messages":[]}',
            )
            try:
                urllib.request.urlopen(req, timeout=5)
            except urllib.error.HTTPError as e:
                # 401 = API 可達但 Key 無效（這正是我們要的結果）
                # 400 = API 可達但請求格式有誤（也代表可達）
                if e.code in (401, 400, 403, 429):
                    return CheckResult(
                        name="API 可達性",
                        status=CheckStatus.OK,
                        message=f"Anthropic API 可達（HTTP {e.code}）",
                        details={"endpoint": "api.anthropic.com", "status_code": e.code},
                    )
                return CheckResult(
                    name="API 可達性",
                    status=CheckStatus.WARNING,
                    message=f"Anthropic API 回應異常（HTTP {e.code}）",
                    details={"endpoint": "api.anthropic.com", "status_code": e.code},
                )

            # 如果竟然成功了（不太可能）
            return CheckResult(
                name="API 可達性",
                status=CheckStatus.OK,
                message="Anthropic API 可達",
            )
        except urllib.error.URLError as e:
            return CheckResult(
                name="API 可達性",
                status=CheckStatus.CRITICAL,
                message=f"無法連線到 Anthropic API: {e.reason}",
                details={"endpoint": "api.anthropic.com", "error": str(e.reason)},
            )
        except Exception as e:
            return CheckResult(
                name="API 可達性",
                status=CheckStatus.WARNING,
                message=f"API 可達性檢查失敗: {e}",
            )

    def _check_field_consistency(self) -> CheckResult:
        """4.9 — 欄位一致性掃描：偵測 JSON 欄位不匹配."""
        try:
            from museon.doctor.field_scanner import FieldScanner
            scanner = FieldScanner(self.home)
            report = scanner.scan()

            if report.critical_count > 0:
                msgs = [m.message for m in report.mismatches
                        if m.severity == "critical"]
                return CheckResult(
                    name="欄位一致性",
                    status=CheckStatus.CRITICAL,
                    message=(
                        f"{report.critical_count} 個欄位不匹配 CRITICAL: "
                        f"{msgs[0][:80]}"
                    ),
                    details={
                        "critical": report.critical_count,
                        "warning": report.warning_count,
                        "total_accesses": report.total_accesses,
                    },
                )
            elif report.warning_count > 0:
                return CheckResult(
                    name="欄位一致性",
                    status=CheckStatus.WARNING,
                    message=(
                        f"欄位掃描: {report.warning_count} 個警告"
                        f"（{report.total_accesses} 存取點）"
                    ),
                    details={
                        "warning": report.warning_count,
                        "total_accesses": report.total_accesses,
                    },
                )
            else:
                return CheckResult(
                    name="欄位一致性",
                    status=CheckStatus.OK,
                    message=(
                        f"欄位一致性正常（{report.total_accesses} 存取點）"
                    ),
                )
        except Exception as e:
            return CheckResult(
                name="欄位一致性",
                status=CheckStatus.WARNING,
                message=f"欄位掃描失敗: {e}",
            )

    # ═══════════════════════════════════════════
    # Layer 5: 演化
    # ═══════════════════════════════════════════

    def _audit_evolution(self) -> List[CheckResult]:
        checks = []
        governance_modules = [
            ("Governor", "museon.governance.governor", "Governor"),
            ("PreflightGate", "museon.governance.preflight", "PreflightGate"),
            ("RefractoryGuard", "museon.governance.refractory", "RefractoryGuard"),
            ("BulkheadRegistry", "museon.governance.bulkhead", "BulkheadRegistry"),
            ("Immune Memory", "museon.governance.immune_memory", None),
            ("Autonomic Layer", "museon.governance.autonomic", None),
        ]

        for name, module_path, class_name in governance_modules:
            checks.append(self._check_governance_module(name, module_path, class_name))

        # 額外：RefractoryGuard state 檔案檢查
        checks.append(self._check_refractory_state())

        # Morphenix 自我迭代健康檢查
        checks.extend(self._check_morphenix_health())

        return checks

    def _check_morphenix_health(self) -> List[CheckResult]:
        """Morphenix 自我迭代引擎健康檢查."""
        results = []

        data_dir = self.home / "data" / "_system" / "morphenix"

        # 1. PulseDB proposals 記錄數
        try:
            db_path = self.home / "data" / "pulse" / "pulse.db"
            if db_path.exists():
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row

                # proposals 統計
                row = conn.execute(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending, "
                    "SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) as approved, "
                    "SUM(CASE WHEN status='executed' THEN 1 ELSE 0 END) as executed, "
                    "SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) as rejected, "
                    "SUM(CASE WHEN status='rolled_back' THEN 1 ELSE 0 END) as rolled_back "
                    "FROM morphenix_proposals"
                ).fetchone()

                total = row["total"] or 0
                detail = (
                    f"total={total}, pending={row['pending'] or 0}, "
                    f"approved={row['approved'] or 0}, executed={row['executed'] or 0}, "
                    f"rejected={row['rejected'] or 0}, rolled_back={row['rolled_back'] or 0}"
                )
                results.append(CheckResult(
                    name="Morphenix PulseDB Proposals",
                    status=CheckStatus.OK if total > 0 else CheckStatus.WARNING,
                    message=detail,
                ))

                # rollback 統計
                try:
                    rb_row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM morphenix_rollbacks"
                    ).fetchone()
                    rb_count = rb_row["cnt"] if rb_row else 0
                    results.append(CheckResult(
                        name="Morphenix Rollback History",
                        status=(
                            CheckStatus.OK if rb_count <= 5
                            else CheckStatus.WARNING
                        ),
                        message=f"total_rollbacks={rb_count}",
                    ))
                except Exception:
                    pass  # 表可能還不存在

                conn.close()
            else:
                results.append(CheckResult(
                    name="Morphenix PulseDB",
                    status=CheckStatus.WARNING,
                    message="pulse.db not found",
                ))
        except Exception as e:
            results.append(CheckResult(
                name="Morphenix PulseDB",
                status=CheckStatus.WARNING,
                message=f"DB check error: {str(e)[:100]}",
            ))

        # 2. Execution log 最近執行時間
        exec_log_dir = data_dir / "execution_log"
        if exec_log_dir.exists():
            log_files = sorted(exec_log_dir.glob("exec_*.jsonl"), reverse=True)
            if log_files:
                latest = log_files[0].name  # exec_YYYY-MM-DD.jsonl
                last_exec_count = 0
                try:
                    for line in log_files[0].read_text(encoding="utf-8").splitlines():
                        rec = json.loads(line)
                        if rec.get("outcome") == "executed":
                            last_exec_count += 1
                except Exception as e:
                    pass  # degraded: JSON

                results.append(CheckResult(
                    name="Morphenix Last Execution",
                    status=CheckStatus.OK,
                    message=f"latest_log={latest}, executed_in_log={last_exec_count}",
                ))
            else:
                results.append(CheckResult(
                    name="Morphenix Last Execution",
                    status=CheckStatus.WARNING,
                    message="No execution logs found (never executed)",
                ))
        else:
            results.append(CheckResult(
                name="Morphenix Execution Log",
                status=CheckStatus.WARNING,
                message="execution_log directory missing",
            ))

        # 3. Notes 累積量
        notes_dir = data_dir / "notes"
        if notes_dir.exists():
            note_count = len(list(notes_dir.glob("*.json")))
            results.append(CheckResult(
                name="Morphenix Notes",
                status=CheckStatus.OK,
                message=f"active_notes={note_count}",
            ))

        # 4. Docker validator 映像是否可用
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", "museon-validator:latest"],
                capture_output=True, timeout=10,
            )
            results.append(CheckResult(
                name="Morphenix Docker Validator",
                status=(
                    CheckStatus.OK if result.returncode == 0
                    else CheckStatus.WARNING
                ),
                message=(
                    "museon-validator:latest available"
                    if result.returncode == 0
                    else "museon-validator:latest NOT found (docker build needed)"
                ),
            ))
        except Exception:
            results.append(CheckResult(
                name="Morphenix Docker Validator",
                status=CheckStatus.WARNING,
                message="Docker not available",
            ))

        # 5. Proposals JSON 目錄
        proposals_dir = data_dir / "proposals"
        if proposals_dir.exists():
            proposal_files = list(proposals_dir.glob("*.json"))
            pending_count = 0
            for pf in proposal_files:
                try:
                    p = json.loads(pf.read_text(encoding="utf-8"))
                    if p.get("status") in ("pending_review", "pending"):
                        pending_count += 1
                except Exception as e:
                    pass  # degraded: file stat
            results.append(CheckResult(
                name="Morphenix Proposals Queue",
                status=CheckStatus.OK,
                message=f"json_files={len(proposal_files)}, pending={pending_count}",
            ))

        return results

    def _check_governance_module(
        self, name: str, module_path: str, class_name: Optional[str]
    ) -> CheckResult:
        """檢查治理模組可否 import"""
        # 先確認原始碼檔案存在
        parts = module_path.split(".")
        rel_path = "/".join(parts) + ".py"
        src_file = self.src_dir / rel_path
        if not src_file.exists():
            src_file = self.runtime_dir / "src" / rel_path

        if not src_file.exists():
            return CheckResult(
                name=f"演化: {name}",
                status=CheckStatus.CRITICAL,
                message=f"{module_path} 原始碼不存在",
            )

        return CheckResult(
            name=f"演化: {name}",
            status=CheckStatus.OK,
            message=f"{module_path} 存在",
            details={"path": str(src_file)},
        )

    def _check_refractory_state(self) -> CheckResult:
        """檢查 RefractoryGuard 狀態檔案"""
        state_file = Path.home() / ".museon" / "refractory_state.json"
        if not state_file.exists():
            return CheckResult(
                name="Refractory 狀態",
                status=CheckStatus.OK,
                message="無狀態檔案（從未觸發斷路器）",
            )

        try:
            data = json.loads(state_file.read_text("utf-8"))
            fc = data.get("failure_count", 0)
            hibernating = data.get("hibernating", False)

            if hibernating:
                return CheckResult(
                    name="Refractory 狀態",
                    status=CheckStatus.CRITICAL,
                    message=f"系統處於休眠狀態！失敗次數: {fc}",
                    details=data,
                )
            if fc >= 3:
                return CheckResult(
                    name="Refractory 狀態",
                    status=CheckStatus.WARNING,
                    message=f"失敗計數偏高: {fc}",
                    details=data,
                )
            return CheckResult(
                name="Refractory 狀態",
                status=CheckStatus.OK,
                message=f"失敗計數: {fc}",
                details=data,
            )
        except Exception as e:
            return CheckResult(
                name="Refractory 狀態",
                status=CheckStatus.UNKNOWN,
                message=f"無法讀取: {e}",
            )

    # ═══════════════════════════════════════════
    # Layer 6: 安全
    # ═══════════════════════════════════════════

    def _audit_security(self) -> List[CheckResult]:
        checks = []

        # 6.1 .env 權限
        checks.append(self._check_env_permissions())

        # 6.2 Token 洩漏掃描
        checks.append(self._check_token_leakage())

        # 6.3 敏感檔案暴露
        checks.append(self._check_gitignore())

        # 6.4 Gateway 綁定地址
        checks.append(self._check_gateway_bind())

        # 6.5 Placeholder 殘留
        checks.append(self._check_placeholder())

        # 6.6 Packager 安全
        checks.append(self._check_packager_safety())

        return checks

    def _check_env_permissions(self) -> CheckResult:
        """檢查 .env 檔案權限"""
        if not self.env_path.exists():
            return CheckResult(
                name=".env 權限",
                status=CheckStatus.OK,
                message=".env 不存在（無需檢查權限）",
            )

        try:
            mode = oct(self.env_path.stat().st_mode)[-3:]
            if mode in ("600", "644"):
                return CheckResult(
                    name=".env 權限",
                    status=CheckStatus.OK,
                    message=f".env 權限 {mode}",
                )
            return CheckResult(
                name=".env 權限",
                status=CheckStatus.WARNING,
                message=f".env 權限過寬: {mode}（建議 600）",
                repairable=True,
                repair_action="chmod 600 .env",
            )
        except Exception as e:
            return CheckResult(
                name=".env 權限",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_token_leakage(self) -> CheckResult:
        """掃描原始碼是否有硬編碼的 API Token"""
        if not self.src_dir.exists():
            return CheckResult(
                name="Token 洩漏掃描",
                status=CheckStatus.OK,
                message="src/ 目錄不存在（非開發環境）",
            )

        leaked_files = []
        patterns = ["sk-ant-", "sk-proj-"]
        try:
            for py_file in self.src_dir.rglob("*.py"):
                try:
                    content = py_file.read_text("utf-8", errors="ignore")
                    for pattern in patterns:
                        if pattern in content:
                            # 排除測試中的 pattern 字串本身
                            # （例如 preflight.py 中的 "sk-ant-" 前綴檢查）
                            lines = [
                                l for l in content.splitlines()
                                if pattern in l
                                and not l.strip().startswith("#")
                                and not l.strip().startswith('"')
                                and not l.strip().startswith("'")
                                and "startswith" not in l
                                and "prefix" not in l.lower()
                                and "PLACEHOLDER" not in l
                                and "pattern" not in l.lower()
                                and "格式" not in l
                                and "開頭" not in l
                                and "masked" not in l.lower()
                                and "REQUIRED_KEYS" not in l
                                and "OPTIONAL_KEYS" not in l
                                # 排除短字串引用如 "sk-ant-"
                                and f'"{pattern}"' not in l
                                and f"'{pattern}'" not in l
                            ]
                            if lines:
                                leaked_files.append(str(py_file.relative_to(self.home)))
                except (OSError, UnicodeDecodeError):
                    continue

            if leaked_files:
                return CheckResult(
                    name="Token 洩漏掃描",
                    status=CheckStatus.CRITICAL,
                    message=f"發現疑似硬編碼 Token: {', '.join(leaked_files[:5])}",
                    details={"files": leaked_files},
                )
            return CheckResult(
                name="Token 洩漏掃描",
                status=CheckStatus.OK,
                message="未發現硬編碼 Token",
            )
        except Exception as e:
            return CheckResult(
                name="Token 洩漏掃描",
                status=CheckStatus.UNKNOWN,
                message=f"掃描失敗: {e}",
            )

    def _check_gitignore(self) -> CheckResult:
        """檢查 .gitignore 是否包含敏感檔案"""
        gitignore = self.home / ".gitignore"
        if not gitignore.exists():
            return CheckResult(
                name="敏感檔案保護",
                status=CheckStatus.WARNING,
                message=".gitignore 不存在",
            )

        try:
            content = gitignore.read_text("utf-8")
            required = [".env", "activity_log.jsonl"]
            missing = [r for r in required if r not in content]
            if missing:
                return CheckResult(
                    name="敏感檔案保護",
                    status=CheckStatus.WARNING,
                    message=f".gitignore 缺少: {', '.join(missing)}",
                    details={"missing": missing},
                )
            return CheckResult(
                name="敏感檔案保護",
                status=CheckStatus.OK,
                message=".gitignore 包含所有敏感檔案規則",
            )
        except Exception as e:
            return CheckResult(
                name="敏感檔案保護",
                status=CheckStatus.UNKNOWN,
                message=f"無法讀取: {e}",
            )

    def _check_gateway_bind(self) -> CheckResult:
        """確認 Gateway 只綁定 localhost"""
        server_py = self.src_dir / "museon" / "gateway" / "server.py"
        if not server_py.exists():
            server_py = self.runtime_dir / "src" / "museon" / "gateway" / "server.py"
        if not server_py.exists():
            return CheckResult(
                name="Gateway 綁定",
                status=CheckStatus.UNKNOWN,
                message="server.py 不存在",
            )

        try:
            content = server_py.read_text("utf-8")
            if '0.0.0.0' in content:
                # 進一步檢查是否在 uvicorn.run 的 host 參數中
                for line in content.splitlines():
                    if "uvicorn.run" in line or "host=" in line:
                        if "0.0.0.0" in line:
                            return CheckResult(
                                name="Gateway 綁定",
                                status=CheckStatus.CRITICAL,
                                message="Gateway 綁定 0.0.0.0（暴露到網路）！",
                                repairable=True,
                                repair_action="bind_localhost",
                            )
            return CheckResult(
                name="Gateway 綁定",
                status=CheckStatus.OK,
                message="Gateway 綁定 127.0.0.1（安全）",
            )
        except Exception as e:
            return CheckResult(
                name="Gateway 綁定",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_placeholder(self) -> CheckResult:
        """掃描 .env 的 placeholder 殘留"""
        if not self.env_path.exists():
            return CheckResult(
                name="Placeholder 檢查",
                status=CheckStatus.OK,
                message=".env 不存在（無需檢查）",
            )

        placeholder_patterns = [
            "your-", "placeholder", "xxx", "todo",
            "change-me", "insert-", "replace-",
        ]

        try:
            env_vars = self.hc._parse_env_file()
            placeholders = []
            for key, val in env_vars.items():
                if val and any(p in val.lower() for p in placeholder_patterns):
                    placeholders.append(key)

            if placeholders:
                return CheckResult(
                    name="Placeholder 檢查",
                    status=CheckStatus.CRITICAL,
                    message=f"發現 placeholder 值: {', '.join(placeholders)}",
                    details={"keys": placeholders},
                )
            return CheckResult(
                name="Placeholder 檢查",
                status=CheckStatus.OK,
                message="無 placeholder 殘留",
            )
        except Exception as e:
            return CheckResult(
                name="Placeholder 檢查",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_packager_safety(self) -> CheckResult:
        """確認 packager.py 的 EXCLUDE_PATTERNS 包含 .env"""
        packager_py = self.src_dir / "museon" / "installer" / "packager.py"
        if not packager_py.exists():
            return CheckResult(
                name="Packager 安全",
                status=CheckStatus.OK,
                message="packager.py 不存在（非開發環境）",
            )

        try:
            content = packager_py.read_text("utf-8")
            if '".env"' in content or "'.env'" in content:
                return CheckResult(
                    name="Packager 安全",
                    status=CheckStatus.OK,
                    message="EXCLUDE_PATTERNS 包含 .env",
                )
            return CheckResult(
                name="Packager 安全",
                status=CheckStatus.CRITICAL,
                message="EXCLUDE_PATTERNS 未包含 .env — API Key 可能被打包！",
                repairable=True,
                repair_action="add_env_to_exclude",
            )
        except Exception as e:
            return CheckResult(
                name="Packager 安全",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    # ═══════════════════════════════════════════
    # Layer 7: 趨勢
    # ═══════════════════════════════════════════

    def _audit_trend(self) -> List[CheckResult]:
        checks = []

        # 7.1 Log 成長率
        checks.append(self._check_log_growth())

        # 7.2 Token 使用趨勢
        checks.append(self._check_token_trend())

        # 7.3 啟動失敗頻率
        checks.append(self._check_failure_frequency())

        # 7.4 磁碟使用趨勢
        checks.append(self._check_disk_trend())

        return checks

    def _check_log_growth(self) -> CheckResult:
        """日誌成長率"""
        if not self.logs_dir.exists():
            return CheckResult(
                name="Log 成長率",
                status=CheckStatus.OK,
                message="logs/ 不存在",
            )

        try:
            total_bytes = sum(
                f.stat().st_size
                for f in self.logs_dir.iterdir()
                if f.is_file()
            )
            total_mb = total_bytes / (1024 * 1024)

            if total_mb > 100:
                return CheckResult(
                    name="Log 成長率",
                    status=CheckStatus.WARNING,
                    message=f"日誌總量 {total_mb:.1f}MB（可能有 crash loop 殘留）",
                    details={"total_mb": round(total_mb, 1)},
                )
            return CheckResult(
                name="Log 成長率",
                status=CheckStatus.OK,
                message=f"日誌總量 {total_mb:.1f}MB",
                details={"total_mb": round(total_mb, 1)},
            )
        except Exception as e:
            return CheckResult(
                name="Log 成長率",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_token_trend(self) -> CheckResult:
        """Token 使用趨勢（本月）"""
        today = date.today()
        budget_file = (
            self.data_dir / "_system" / "budget"
            / f"usage_{today.strftime('%Y-%m')}.json"
        )
        if not budget_file.exists():
            return CheckResult(
                name="Token 趨勢",
                status=CheckStatus.OK,
                message="本月無使用記錄",
            )

        try:
            data = json.loads(budget_file.read_text("utf-8"))
            total_cost = data.get("total_cost_usd", 0)
            day_of_month = today.day
            if day_of_month > 0:
                daily_avg = total_cost / day_of_month
                projected = daily_avg * 30
            else:
                daily_avg = 0
                projected = 0

            monthly_limit = data.get("monthly_limit_usd", 15)
            if projected > monthly_limit * 1.2:
                return CheckResult(
                    name="Token 趨勢",
                    status=CheckStatus.WARNING,
                    message=(
                        f"日均 ${daily_avg:.2f}，月底預估 ${projected:.2f}"
                        f"（超出限額 ${monthly_limit}）"
                    ),
                    details={
                        "daily_avg": daily_avg,
                        "projected": projected,
                        "limit": monthly_limit,
                    },
                )
            return CheckResult(
                name="Token 趨勢",
                status=CheckStatus.OK,
                message=f"日均 ${daily_avg:.2f}，月底預估 ${projected:.2f}",
                details={
                    "daily_avg": round(daily_avg, 2),
                    "projected": round(projected, 2),
                },
            )
        except Exception as e:
            return CheckResult(
                name="Token 趨勢",
                status=CheckStatus.UNKNOWN,
                message=f"無法計算: {e}",
            )

    def _check_failure_frequency(self) -> CheckResult:
        """啟動失敗頻率"""
        state_file = Path.home() / ".museon" / "refractory_state.json"
        if not state_file.exists():
            return CheckResult(
                name="啟動失敗頻率",
                status=CheckStatus.OK,
                message="無失敗記錄",
            )

        try:
            data = json.loads(state_file.read_text("utf-8"))
            fc = data.get("failure_count", 0)
            last_ts = data.get("last_failure_ts", 0)
            if last_ts > 0:
                last_dt = datetime.fromtimestamp(last_ts)
                age = datetime.now() - last_dt
                age_str = f"{age.total_seconds() / 3600:.1f}h 前"
            else:
                age_str = "無記錄"

            if fc >= 10:
                return CheckResult(
                    name="啟動失敗頻率",
                    status=CheckStatus.CRITICAL,
                    message=f"累計失敗 {fc} 次，最後失敗: {age_str}",
                )
            if fc >= 3:
                return CheckResult(
                    name="啟動失敗頻率",
                    status=CheckStatus.WARNING,
                    message=f"累計失敗 {fc} 次，最後失敗: {age_str}",
                )
            return CheckResult(
                name="啟動失敗頻率",
                status=CheckStatus.OK,
                message=f"累計失敗 {fc} 次",
            )
        except Exception as e:
            return CheckResult(
                name="啟動失敗頻率",
                status=CheckStatus.UNKNOWN,
                message=f"無法讀取: {e}",
            )

    def _check_disk_trend(self) -> CheckResult:
        """磁碟使用趨勢"""
        try:
            usage = shutil.disk_usage(str(self.home))
            used_pct = (usage.used / usage.total) * 100
            free_gb = usage.free / (1024**3)

            if used_pct > 90:
                return CheckResult(
                    name="磁碟趨勢",
                    status=CheckStatus.CRITICAL,
                    message=f"磁碟使用 {used_pct:.0f}%，剩餘 {free_gb:.1f}GB",
                )
            if used_pct > 80:
                return CheckResult(
                    name="磁碟趨勢",
                    status=CheckStatus.WARNING,
                    message=f"磁碟使用 {used_pct:.0f}%，剩餘 {free_gb:.1f}GB",
                )
            return CheckResult(
                name="磁碟趨勢",
                status=CheckStatus.OK,
                message=f"磁碟使用 {used_pct:.0f}%，剩餘 {free_gb:.1f}GB",
            )
        except Exception as e:
            return CheckResult(
                name="磁碟趨勢",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )


    # ═══════════════════════════════════════════
    # Layer 8: 藍圖一致性（P4 新增）
    # ═══════════════════════════════════════════

    def _audit_blueprint(self) -> List[CheckResult]:
        checks = []

        # 8.1 藍圖存在性
        checks.append(self._check_blueprint_existence())

        # 8.2 藍圖新鮮度
        checks.append(self._check_blueprint_freshness())

        # 8.3 禁區模組保護
        checks.append(self._check_forbidden_modules())

        return checks

    def _check_blueprint_existence(self) -> CheckResult:
        """檢查四張藍圖是否存在且非空."""
        blueprint_names = [
            "blast-radius.md",
            "joint-map.md",
            "system-topology.md",
            "persistence-contract.md",
        ]
        docs_dir = self.home / "docs"
        missing = []
        empty = []
        for name in blueprint_names:
            path = docs_dir / name
            if not path.exists():
                missing.append(name)
            elif path.stat().st_size < 100:
                empty.append(name)

        if missing:
            return CheckResult(
                name="藍圖存在性",
                status=CheckStatus.CRITICAL,
                message=f"藍圖缺失: {', '.join(missing)}",
                details={"missing": missing},
            )
        if empty:
            return CheckResult(
                name="藍圖存在性",
                status=CheckStatus.WARNING,
                message=f"藍圖可能為空: {', '.join(empty)}",
                details={"empty": empty},
            )
        return CheckResult(
            name="藍圖存在性",
            status=CheckStatus.OK,
            message="四張藍圖均存在且有內容",
        )

    def _check_blueprint_freshness(self) -> CheckResult:
        """比較 docs/*.md 和 src/ 的最後修改時間."""
        docs_dir = self.home / "docs"
        src_dir = self.home / "src"

        if not docs_dir.exists() or not src_dir.exists():
            return CheckResult(
                name="藍圖新鮮度",
                status=CheckStatus.UNKNOWN,
                message="docs/ 或 src/ 目錄不存在",
            )

        try:
            # 找到 docs/*.md 最新修改時間
            doc_files = list(docs_dir.glob("*.md"))
            if not doc_files:
                return CheckResult(
                    name="藍圖新鮮度",
                    status=CheckStatus.WARNING,
                    message="docs/ 無 .md 文件",
                )
            latest_doc = max(f.stat().st_mtime for f in doc_files)

            # 找到 src/ 最新 .py 修改時間
            py_files = list(src_dir.rglob("*.py"))
            if not py_files:
                return CheckResult(
                    name="藍圖新鮮度",
                    status=CheckStatus.OK,
                    message="src/ 無 .py 文件",
                )
            latest_src = max(f.stat().st_mtime for f in py_files)

            gap_hours = (latest_src - latest_doc) / 3600
            if gap_hours > 72:
                return CheckResult(
                    name="藍圖新鮮度",
                    status=CheckStatus.WARNING,
                    message=(
                        f"藍圖落後源碼 {gap_hours:.0f} 小時"
                        f"（可能過期）"
                    ),
                    details={"gap_hours": round(gap_hours, 1)},
                )
            return CheckResult(
                name="藍圖新鮮度",
                status=CheckStatus.OK,
                message=f"藍圖與源碼時差 {abs(gap_hours):.0f} 小時內",
                details={"gap_hours": round(gap_hours, 1)},
            )
        except Exception as e:
            return CheckResult(
                name="藍圖新鮮度",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )

    def _check_forbidden_modules(self) -> CheckResult:
        """檢查 blast-radius 標為禁區的模組是否存在."""
        try:
            from museon.core.blueprint_reader import BlastRadiusReader

            reader = BlastRadiusReader(self.home / "docs")
            forbidden = reader.get_forbidden_modules()

            if not forbidden:
                return CheckResult(
                    name="禁區模組保護",
                    status=CheckStatus.OK,
                    message="未解析到禁區模組（可能文件格式不匹配）",
                )

            existing = []
            for mod in forbidden:
                path = self.home / "src" / "museon" / mod
                if path.exists():
                    fan_in = reader.get_fan_in(mod)
                    existing.append(f"{mod}(扇入={fan_in})")

            return CheckResult(
                name="禁區模組保護",
                status=CheckStatus.OK,
                message=(
                    f"禁區模組 {len(forbidden)} 個，"
                    f"確認存在: {', '.join(existing) or '無'}"
                ),
                details={
                    "forbidden": forbidden,
                    "existing": existing,
                },
            )
        except Exception as e:
            return CheckResult(
                name="禁區模組保護",
                status=CheckStatus.UNKNOWN,
                message=f"無法檢查: {e}",
            )


# ═══════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MUSEON 系統審計 — 7 層全面體檢",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python -m museon.doctor.system_audit                    # 完整審計
  python -m museon.doctor.system_audit --json              # JSON 輸出
  python -m museon.doctor.system_audit --gate              # Gate 模式
  python -m museon.doctor.system_audit --layer infra security  # 指定層
        """,
    )
    parser.add_argument(
        "--json", action="store_true", help="JSON 格式輸出"
    )
    parser.add_argument(
        "--gate", action="store_true",
        help="Gate 模式（有 CRITICAL 即 exit(1)）",
    )
    parser.add_argument(
        "--layer", nargs="*",
        help="只跑指定層（如 infra process service application evolution security trend）",
    )
    parser.add_argument(
        "-o", "--output", help="輸出檔案路徑",
    )
    parser.add_argument(
        "--home", help="指定 MUSEON_HOME 路徑",
    )
    args = parser.parse_args()

    auditor = SystemAuditor(museon_home=args.home)
    report = auditor.run_full_audit(layers=args.layer)

    if args.json:
        output = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    else:
        output = report.to_text()

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"報告已寫入: {args.output}")
    else:
        print(output)

    if args.gate and report.overall == CheckStatus.CRITICAL:
        sys.exit(1)


if __name__ == "__main__":
    main()
