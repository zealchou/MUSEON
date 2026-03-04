"""MUSEON SelfDiagnosis — 對話中自我診斷 + 自動修復.

霓裳在對話過程中偵測到異常時（或用戶主動詢問），
可以執行自我診斷並自動修復安全區問題。

設計原則：
- 純 CPU，零 Token
- 安全分區：GREEN 自動修、YELLOW 問用戶、RED 拒絕
- 結果用自然語言回報（繁體中文）
- 透過 EventBus 整合到 Brain pipeline
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 自我檢查意圖偵測
# ═══════════════════════════════════════════

_SELF_CHECK_KEYWORDS = frozenset({
    "自我檢查", "自我診斷", "自檢", "系統狀態", "系統檢查",
    "你還好嗎", "你哪裡壞了", "你正常嗎", "健康檢查",
    "身體檢查", "自我修復", "修復自己", "檢查自己",
    "你怎麼了", "系統報告", "狀態回報", "health check",
    "self check", "self diagnosis", "診斷一下",
    # 壓力測試 W1-05 發現的缺漏
    "自我健檢", "全身健檢", "系統健檢", "跑健檢", "做健檢",
    "全面檢查", "全面健檢", "全面診斷", "跑一下診斷",
})

_SELF_CHECK_PATTERNS = [
    "你有沒有問題",
    "系統有問題嗎",
    "你是不是壞了",
    "哪裡出問題",
    "檢查一下系統",
    "跑一下健檢",
    "做一下健檢",
    "幫自己做健檢",
]


def detect_self_check_intent(content: str) -> bool:
    """偵測用戶是否要求自我檢查.

    純 CPU 關鍵字匹配，零 Token。
    注意：中文字元不受 .lower() 影響，但英文關鍵字需要。
    此函式同時處理中英文混合輸入。
    """
    stripped = content.strip()
    if not stripped:
        return False

    # 對英文部分做 lower，中文不受影響
    lower = stripped.lower()

    # 完整匹配關鍵字（中英文都在 lower 中檢索）
    for kw in _SELF_CHECK_KEYWORDS:
        if kw in lower:
            return True

    # 模式匹配
    for pattern in _SELF_CHECK_PATTERNS:
        if pattern in lower:
            return True

    # 額外模糊匹配：處理使用者加空格或標點的變體
    # 例如「自我 檢查」「自我-診斷」
    normalized = lower.replace(" ", "").replace("-", "").replace("_", "")
    if normalized != lower:
        for kw in _SELF_CHECK_KEYWORDS:
            if kw in normalized:
                return True

    return False


# ═══════════════════════════════════════════
# 安全分區
# ═══════════════════════════════════════════

# GREEN: 自動修復，不需確認
GREEN_ZONE_ACTIONS = frozenset({
    "create_directories",
    "fix_env_permissions",
    "rotate_logs",
    "start_gateway",
    "load_daemon",
})

# YELLOW: 需要用戶確認
YELLOW_ZONE_ACTIONS = frozenset({
    "recreate_venv",
    "reinstall_packages",
    "reinstall_daemon",
})

# RED: 拒絕自動修復（需人工介入）
RED_ZONE_ACTIONS = frozenset({
    "rebuild_dashboard",
    "create_env_file",
})


# ═══════════════════════════════════════════
# 資料模型
# ═══════════════════════════════════════════

@dataclass
class DiagnosisIssue:
    """單一診斷問題."""
    name: str
    severity: str  # "ok", "warning", "critical"
    message: str
    repairable: bool = False
    repair_action: str = ""
    zone: str = ""  # "green", "yellow", "red", ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "message": self.message,
            "repairable": self.repairable,
            "repair_action": self.repair_action,
            "zone": self.zone,
        }


@dataclass
class RepairResult:
    """修復結果."""
    action: str
    success: bool
    message: str


@dataclass
class DiagnosisReport:
    """完整診斷報告."""
    timestamp: str = ""
    duration_ms: int = 0
    issues: List[DiagnosisIssue] = field(default_factory=list)
    auto_repaired: List[RepairResult] = field(default_factory=list)
    needs_confirm: List[DiagnosisIssue] = field(default_factory=list)
    needs_manual: List[DiagnosisIssue] = field(default_factory=list)
    all_ok: bool = False

    @property
    def total_issues(self) -> int:
        return len(self.issues)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "all_ok": self.all_ok,
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
            "issues": [i.to_dict() for i in self.issues],
            "auto_repaired": [
                {"action": r.action, "success": r.success, "message": r.message}
                for r in self.auto_repaired
            ],
            "needs_confirm": [i.to_dict() for i in self.needs_confirm],
            "needs_manual": [i.to_dict() for i in self.needs_manual],
        }


# ═══════════════════════════════════════════
# SelfDiagnosis 核心引擎
# ═══════════════════════════════════════════

class SelfDiagnosis:
    """MUSEON 自我診斷引擎 — 純 CPU, 零 Token.

    整合 HealthChecker + AutoRepair + ToolRegistry，
    透過安全分區決定哪些問題自動修、哪些問用戶。
    """

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir

    def diagnose(self, auto_repair: bool = True) -> DiagnosisReport:
        """執行完整自我診斷.

        Args:
            auto_repair: 是否自動修復 GREEN 區問題

        Returns:
            DiagnosisReport 完整報告
        """
        from datetime import datetime
        start = time.monotonic()
        report = DiagnosisReport(timestamp=datetime.now().isoformat())

        # ── 1. HealthChecker 12 點健檢 ──
        try:
            from museon.doctor.health_check import HealthChecker
            checker = HealthChecker()
            health_report = checker.run_all()

            for check in health_report.checks:
                if check.status.value in ("warning", "critical"):
                    zone = self._classify_zone(check.repair_action)
                    issue = DiagnosisIssue(
                        name=check.name,
                        severity=check.status.value,
                        message=check.message,
                        repairable=check.repairable,
                        repair_action=check.repair_action,
                        zone=zone,
                    )
                    report.issues.append(issue)

                    if check.repairable:
                        if zone == "green":
                            pass  # 稍後自動修
                        elif zone == "yellow":
                            report.needs_confirm.append(issue)
                        elif zone == "red":
                            report.needs_manual.append(issue)
        except Exception as e:
            logger.warning(f"HealthChecker 執行失敗: {e}")
            report.issues.append(DiagnosisIssue(
                name="健檢引擎",
                severity="critical",
                message=f"HealthChecker 無法執行: {e}",
            ))

        # ── 2. Tool Registry 健康檢查 ──
        try:
            from museon.tools.tool_registry import ToolRegistry
            from pathlib import Path

            workspace = Path(self.data_dir) if self.data_dir else Path("data")
            registry = ToolRegistry(workspace=workspace)
            tool_health = registry.check_all_health()

            for name, result in tool_health.items():
                if not result.get("healthy", False):
                    state = registry._states.get(name)
                    # 只報告已安裝+已啟用但不健康的工具
                    if state and state.installed and state.enabled:
                        report.issues.append(DiagnosisIssue(
                            name=f"工具: {name}",
                            severity="warning",
                            message=result.get("reason", "不健康"),
                            repairable=True,
                            repair_action=f"restart_tool:{name}",
                            zone="green",
                        ))
        except Exception as e:
            logger.warning(f"ToolRegistry 健康檢查失敗: {e}")

        # ── 3. Guardian 最近報告 ──
        try:
            from pathlib import Path
            guardian_dir = (
                Path(self.data_dir) / "guardian"
                if self.data_dir
                else Path("data") / "guardian"
            )
            unresolved_path = guardian_dir / "unresolved.json"
            if unresolved_path.exists():
                import json
                unresolved = json.loads(
                    unresolved_path.read_text("utf-8")
                )
                if isinstance(unresolved, list) and unresolved:
                    report.issues.append(DiagnosisIssue(
                        name="Guardian 未解決問題",
                        severity="warning",
                        message=f"有 {len(unresolved)} 個 Guardian 未解決問題",
                    ))
        except Exception as e:
            logger.debug(f"Guardian 報告讀取失敗: {e}")

        # ── 4. 自動修復 GREEN 區 ──
        if auto_repair and report.issues:
            green_issues = [
                i for i in report.issues
                if i.repairable and i.zone == "green"
            ]
            for issue in green_issues:
                result = self._execute_repair(issue)
                report.auto_repaired.append(result)

        # ── 5. 彙總 ──
        report.all_ok = len(report.issues) == 0
        report.duration_ms = int(
            (time.monotonic() - start) * 1000
        )

        # ── 6. 發布事件 ──
        self._publish_event(report)

        return report

    def diagnose_quick(self) -> DiagnosisReport:
        """快速診斷（僅核心項目，不修復）."""
        from datetime import datetime
        start = time.monotonic()
        report = DiagnosisReport(timestamp=datetime.now().isoformat())

        try:
            from museon.doctor.health_check import HealthChecker
            checker = HealthChecker()

            # 只跑關鍵項目
            checks = [
                checker.check_gateway_process(),
                checker.check_gateway_health(),
                checker.check_disk_space(),
            ]
            for check in checks:
                if check.status.value in ("warning", "critical"):
                    report.issues.append(DiagnosisIssue(
                        name=check.name,
                        severity=check.status.value,
                        message=check.message,
                        repairable=check.repairable,
                        repair_action=check.repair_action,
                        zone=self._classify_zone(check.repair_action),
                    ))
        except Exception as e:
            logger.warning(f"Quick diagnosis failed: {e}")

        report.all_ok = len(report.issues) == 0
        report.duration_ms = int(
            (time.monotonic() - start) * 1000
        )
        return report

    def format_report_zh(self, report: DiagnosisReport) -> str:
        """將診斷報告格式化為霓裳的自然語言回覆（繁體中文）."""
        lines = []

        if report.all_ok and not report.auto_repaired:
            lines.append(
                "我剛做了自我檢查，所有系統都正常運作中。"
            )
            lines.append(f"（診斷耗時 {report.duration_ms}ms）")
            return "\n".join(lines)

        # 有問題
        lines.append("我做了一次自我診斷，以下是結果：\n")

        # 自動修復的
        if report.auto_repaired:
            lines.append("**已自動修復：**")
            for r in report.auto_repaired:
                emoji = "✅" if r.success else "❌"
                lines.append(f"  {emoji} {r.message}")
            lines.append("")

        # 需要確認的
        if report.needs_confirm:
            lines.append("**需要你確認才能修復：**")
            for issue in report.needs_confirm:
                lines.append(f"  ⚠️ {issue.name}：{issue.message}")
                lines.append(f"     → 修復方式：{issue.repair_action}")
            lines.append("")

        # 需要手動處理的
        if report.needs_manual:
            lines.append("**需要你手動處理：**")
            for issue in report.needs_manual:
                lines.append(f"  🔴 {issue.name}：{issue.message}")
            lines.append("")

        # 剩餘問題（未分類的 warning/critical）
        other_issues = [
            i for i in report.issues
            if not i.repairable
            and i not in report.needs_confirm
            and i not in report.needs_manual
        ]
        if other_issues:
            lines.append("**其他狀態：**")
            for issue in other_issues:
                emoji = "⚠️" if issue.severity == "warning" else "🔴"
                lines.append(f"  {emoji} {issue.name}：{issue.message}")
            lines.append("")

        lines.append(f"（診斷耗時 {report.duration_ms}ms）")
        return "\n".join(lines)

    # ─── 內部方法 ───

    def _classify_zone(self, repair_action: str) -> str:
        """分類修復動作的安全區."""
        if not repair_action:
            return ""
        # 處理 tool restart 格式
        base_action = repair_action.split(":")[0]
        if base_action == "restart_tool":
            return "green"
        if base_action in GREEN_ZONE_ACTIONS:
            return "green"
        if base_action in YELLOW_ZONE_ACTIONS:
            return "yellow"
        if base_action in RED_ZONE_ACTIONS:
            return "red"
        return ""

    def _execute_repair(self, issue: DiagnosisIssue) -> RepairResult:
        """執行單一修復動作."""
        action = issue.repair_action

        # 工具重啟
        if action.startswith("restart_tool:"):
            tool_name = action.split(":", 1)[1]
            return self._restart_tool(tool_name)

        # AutoRepair 標準動作
        try:
            from museon.doctor.auto_repair import AutoRepair
            repair = AutoRepair()
            result = repair.execute(action)
            return RepairResult(
                action=action,
                success=result.status.value == "success",
                message=result.message,
            )
        except Exception as e:
            return RepairResult(
                action=action,
                success=False,
                message=f"修復失敗: {e}",
            )

    def _restart_tool(self, tool_name: str) -> RepairResult:
        """重啟指定工具容器."""
        try:
            from museon.tools.tool_registry import ToolRegistry, TOOL_CONFIGS
            from pathlib import Path

            workspace = Path(self.data_dir) if self.data_dir else Path("data")
            registry = ToolRegistry(workspace=workspace)

            config = TOOL_CONFIGS.get(tool_name)
            if not config:
                return RepairResult(
                    action=f"restart_tool:{tool_name}",
                    success=False,
                    message=f"找不到工具設定: {tool_name}",
                )

            # 先停再啟
            registry._stop_tool(tool_name, config)
            start_result = registry._start_tool(tool_name, config)

            if start_result:
                return RepairResult(
                    action=f"restart_tool:{tool_name}",
                    success=True,
                    message=f"已重啟工具 {tool_name}",
                )
            return RepairResult(
                action=f"restart_tool:{tool_name}",
                success=False,
                message=f"重啟 {tool_name} 失敗",
            )
        except Exception as e:
            return RepairResult(
                action=f"restart_tool:{tool_name}",
                success=False,
                message=f"重啟失敗: {e}",
            )

    def _publish_event(self, report: DiagnosisReport) -> None:
        """發布診斷完成事件."""
        try:
            from museon.core.event_bus import (
                get_event_bus,
                SELF_DIAGNOSIS_COMPLETED,
            )
            event_bus = get_event_bus()
            event_bus.publish(SELF_DIAGNOSIS_COMPLETED, {
                "all_ok": report.all_ok,
                "total_issues": report.total_issues,
                "auto_repaired": len(report.auto_repaired),
                "duration_ms": report.duration_ms,
            })
        except Exception:
            pass
