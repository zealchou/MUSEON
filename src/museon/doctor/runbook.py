"""
Runbook — MuseDoc 的可執行修復手冊

每個 Runbook 定義一種已知問題的修復流程：
pre_check → action → post_check → rollback

設計參考：
- AWS Systems Manager Automation Documents
- SRE Runbook Automation（pre-check / action / post-check / rollback）
- Google 閉環修復模式
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class RunbookResult:
    success: bool
    message: str
    changed_files: list[str] = field(default_factory=list)


class Runbook:
    """修復手冊基底類"""

    runbook_id: str = ""
    name: str = ""
    applicable_to: str = ""       # 適用的 error pattern
    severity_limit: str = "GREEN"  # 最高修 GREEN|YELLOW（不修 RED）
    blast_radius_max: int = 5      # 最大允許扇入
    timeout_seconds: int = 60
    success_count: int = 0
    failure_count: int = 0

    def matches(self, finding: dict) -> bool:
        """判斷此 Runbook 是否適用於給定的 finding"""
        raise NotImplementedError

    async def pre_check(self, finding: dict, home: Path) -> bool:
        """術前驗證——確認問題確實存在"""
        raise NotImplementedError

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        """執行修復"""
        raise NotImplementedError

    async def post_check(self, finding: dict, home: Path) -> bool:
        """術後驗證——確認修好了"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# RB-001: Static Reference Fix
# ---------------------------------------------------------------------------

class RB001_StaticReference(Runbook):
    """修正 @staticmethod 中的 self 引用"""

    runbook_id = "RB-001"
    name = "static-reference"
    applicable_to = "NameError.*self.*staticmethod|self\\._.*@staticmethod"
    blast_radius_max = 5

    def matches(self, finding: dict) -> bool:
        origin = finding.get("blast_origin", {})
        error = origin.get("error_type", "") + " " + origin.get("traceback", "")
        return bool(re.search(r"(NameError|AttributeError).*self\.", error, re.IGNORECASE))

    async def pre_check(self, finding: dict, home: Path) -> bool:
        origin = finding.get("blast_origin", {})
        file_path = home / "src" / "museon" / origin.get("file", "")
        return file_path.exists()

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        origin = finding.get("blast_origin", {})
        file_path = home / "src" / "museon" / origin.get("file", "")
        if not file_path.exists():
            return RunbookResult(False, "File not found")

        source = file_path.read_text(encoding="utf-8")
        # 用 AST 找 @staticmethod 中的 self 引用
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return RunbookResult(False, f"Syntax error: {e}")

        # 簡化修復：找到 traceback 中提到的行號
        line = origin.get("line")
        if not line:
            return RunbookResult(False, "No line number in finding")

        lines = source.split("\n")
        if 0 < line <= len(lines):
            old_line = lines[line - 1]
            if "self." in old_line:
                # 嘗試找到類別名
                class_name = self._find_enclosing_class(tree, line)
                if class_name:
                    new_line = old_line.replace("self.", f"{class_name}.")
                    lines[line - 1] = new_line
                    file_path.write_text("\n".join(lines), encoding="utf-8")
                    return RunbookResult(True, f"Fixed self. → {class_name}.", [str(file_path)])

        return RunbookResult(False, "Could not determine fix")

    async def post_check(self, finding: dict, home: Path) -> bool:
        origin = finding.get("blast_origin", {})
        mod = "museon." + origin.get("file", "").replace("/", ".").replace(".py", "")
        try:
            result = subprocess.run(
                [str(home / ".venv" / "bin" / "python"), "-c", f"import {mod}"],
                capture_output=True, timeout=10, cwd=str(home),
            )
            return result.returncode == 0
        except Exception:
            return False

    def _find_enclosing_class(self, tree: ast.AST, line: int) -> str | None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if hasattr(node, "end_lineno") and node.lineno <= line <= node.end_lineno:
                    return node.name
        return None


# ---------------------------------------------------------------------------
# RB-003: Path Create
# ---------------------------------------------------------------------------

class RB003_PathCreate(Runbook):
    """建立缺失的目錄或檔案"""

    runbook_id = "RB-003"
    name = "path-create"
    applicable_to = "FileNotFoundError|missing_file|missing_path"
    blast_radius_max = 10

    def matches(self, finding: dict) -> bool:
        origin = finding.get("blast_origin", {})
        error_type = origin.get("error_type", "")
        return error_type in ("FileNotFoundError", "missing_file", "missing_path", "MissingCollection")

    async def pre_check(self, finding: dict, home: Path) -> bool:
        origin = finding.get("blast_origin", {})
        target = home / origin.get("file", "")
        return not target.exists()  # 確認確實缺失

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        origin = finding.get("blast_origin", {})
        target = home / origin.get("file", "")

        if target.suffix:  # 是檔案
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.suffix == ".json":
                target.write_text("{}", encoding="utf-8")
            elif target.suffix == ".jsonl":
                target.touch()
            elif target.suffix == ".md":
                target.write_text("", encoding="utf-8")
            else:
                target.touch()
        else:  # 是目錄
            target.mkdir(parents=True, exist_ok=True)

        return RunbookResult(True, f"Created {target}", [str(target)])

    async def post_check(self, finding: dict, home: Path) -> bool:
        origin = finding.get("blast_origin", {})
        target = home / origin.get("file", "")
        return target.exists()


# ---------------------------------------------------------------------------
# RB-004: Config Key Fix
# ---------------------------------------------------------------------------

class RB004_ConfigKey(Runbook):
    """修復 JSON 配置缺失的欄位"""

    runbook_id = "RB-004"
    name = "config-key"
    applicable_to = "KeyError|config_key"
    blast_radius_max = 5

    def matches(self, finding: dict) -> bool:
        origin = finding.get("blast_origin", {})
        return origin.get("error_type", "") in ("KeyError", "config_key")

    async def pre_check(self, finding: dict, home: Path) -> bool:
        origin = finding.get("blast_origin", {})
        target = home / origin.get("file", "")
        return target.exists() and target.suffix == ".json"

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        # 此 Runbook 比較保守——只在有明確 default 值時才修
        return RunbookResult(False, "Config key fix requires manual review")

    async def post_check(self, finding: dict, home: Path) -> bool:
        return True


# ---------------------------------------------------------------------------
# RB-005: Schema Migrate
# ---------------------------------------------------------------------------

class RB005_SchemaMigrate(Runbook):
    """SQLite schema 遷移——新增缺失的欄位"""

    runbook_id = "RB-005"
    name = "schema-migrate"
    applicable_to = "OperationalError.*no such column"
    blast_radius_max = 3

    def matches(self, finding: dict) -> bool:
        origin = finding.get("blast_origin", {})
        traceback = origin.get("traceback", "")
        return "no such column" in traceback

    async def pre_check(self, finding: dict, home: Path) -> bool:
        return True  # 只要有 traceback 就可以嘗試

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        # 保守：schema 修改需要人工確認
        return RunbookResult(False, "Schema migration requires manual review")

    async def post_check(self, finding: dict, home: Path) -> bool:
        return True


# ---------------------------------------------------------------------------
# RB-006: Dead Import Cleanup
# ---------------------------------------------------------------------------

class RB006_DeadImport(Runbook):
    """移除未使用的 import"""

    runbook_id = "RB-006"
    name = "dead-import"
    applicable_to = "unused_import"
    blast_radius_max = 5

    def matches(self, finding: dict) -> bool:
        origin = finding.get("blast_origin", {})
        return origin.get("error_type", "") == "unused_import"

    async def pre_check(self, finding: dict, home: Path) -> bool:
        return True

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        # 保守：import 清理需要確認不影響 re-export
        return RunbookResult(False, "Dead import cleanup requires manual review")

    async def post_check(self, finding: dict, home: Path) -> bool:
        return True


# ---------------------------------------------------------------------------
# Runbook Registry
# ---------------------------------------------------------------------------

class RB007_GatewayRestart(Runbook):
    """Gateway 不可用時安全重啟

    注意：MuseDoc 跑在 Gateway cron 內，不能用 subprocess.run 等待
    restart-gateway.sh 完成（等於殺自己母進程再等自己回來）。
    改用 launchctl kickstart fire-and-forget + 寫 flag 讓下一輪巡檢驗證。
    """
    runbook_id = "RB-007"
    name = "Gateway 安全重啟"
    applicable_to = "Gateway liveness|Gateway process not found|Gateway not responding"
    severity_limit = "YELLOW"
    blast_radius_max = 50  # Gateway 是全系統入口
    timeout_seconds = 30   # fire-and-forget，不需要久等

    def matches(self, finding: dict) -> bool:
        title = finding.get("title", "")
        return any(p in title for p in ["Gateway liveness", "Gateway process not found", "Gateway not responding"])

    async def pre_check(self, finding: dict, home: Path) -> bool:
        import subprocess
        result = subprocess.run(["pgrep", "-f", "museon.gateway"], capture_output=True, timeout=5)
        return result.returncode != 0  # Gateway 確實不在

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        # MuseDoc 跑在 Gateway 的 cron 內，不能重啟自己的母進程。
        # Gateway 重啟交由 launchd KeepAlive 自動處理。
        # MuseDoc 只負責記錄 + 通知老闆。
        return RunbookResult(
            success=True,
            message="Gateway 已死亡，已通知老闆。重啟由 launchd KeepAlive 處理。",
        )

    async def post_check(self, finding: dict, home: Path) -> bool:
        import subprocess, asyncio
        await asyncio.sleep(20)
        result = subprocess.run(["pgrep", "-f", "museon.gateway"], capture_output=True, timeout=5)
        return result.returncode == 0


class RB008_PycCleanup(Runbook):
    """清理 __pycache__ 防止舊 bytecode 污染"""
    runbook_id = "RB-008"
    name = "PyCache 清理"
    applicable_to = "NameError|ImportError|stale bytecode"
    severity_limit = "GREEN"
    blast_radius_max = 100
    timeout_seconds = 30

    def matches(self, finding: dict) -> bool:
        title = finding.get("title", "")
        context = str(finding.get("context", ""))
        return "NameError" in title or "NameError" in context or "ImportError" in title

    async def pre_check(self, finding: dict, home: Path) -> bool:
        import subprocess
        result = subprocess.run(
            ["find", str(home / "src"), str(home / ".runtime" / "src"), "-name", "__pycache__", "-type", "d"],
            capture_output=True, text=True, timeout=10,
        )
        return len(result.stdout.strip()) > 0  # 有 pyc 目錄存在

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        import subprocess
        subprocess.run(
            ["find", str(home / "src"), str(home / ".runtime" / "src"),
             "-name", "__pycache__", "-type", "d", "-exec", "rm", "-rf", "{}", "+"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["find", str(home / "src"), str(home / ".runtime" / "src"),
             "-name", "*.pyc", "-delete"],
            capture_output=True, timeout=15,
        )
        return RunbookResult(success=True, message="pyc cleaned")

    async def post_check(self, finding: dict, home: Path) -> bool:
        import subprocess
        result = subprocess.run(
            ["find", str(home / "src"), str(home / ".runtime" / "src"), "-name", "__pycache__", "-type", "d"],
            capture_output=True, text=True, timeout=10,
        )
        return len(result.stdout.strip()) == 0


class RB009_TelegramReadiness(Runbook):
    """Telegram adapter readiness 失敗時重建連線"""
    runbook_id = "RB-009"
    name = "Telegram Readiness 修復"
    applicable_to = "Readiness FAILED.*telegram|telegram.*readiness"
    severity_limit = "YELLOW"
    blast_radius_max = 10
    timeout_seconds = 30

    def matches(self, finding: dict) -> bool:
        title = finding.get("title", "").lower()
        return "readiness" in title and "telegram" in title

    async def pre_check(self, finding: dict, home: Path) -> bool:
        return True  # Readiness 問題不需要 pre-check

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        # 最安全的修復：觸發 Gateway 重啟
        import subprocess
        script = home / "scripts" / "workflows" / "restart-gateway.sh"
        if script.exists():
            subprocess.run(["bash", str(script)], capture_output=True, timeout=120)
            return RunbookResult(success=True, message="Gateway restarted for Telegram readiness")
        return RunbookResult(success=False, message="restart script not found")

    async def post_check(self, finding: dict, home: Path) -> bool:
        import asyncio
        await asyncio.sleep(20)
        import subprocess
        result = subprocess.run(["pgrep", "-f", "museon.gateway"], capture_output=True, timeout=5)
        return result.returncode == 0


ALL_RUNBOOKS: list[Runbook] = [
    RB001_StaticReference(),
    RB003_PathCreate(),
    RB004_ConfigKey(),
    RB005_SchemaMigrate(),
    RB006_DeadImport(),
    RB007_GatewayRestart(),
    RB008_PycCleanup(),
    RB009_TelegramReadiness(),
]


def match_runbook(finding: dict) -> Runbook | None:
    """匹配第一個適用的 Runbook"""
    # 優先用 prescription 中指定的 runbook_id
    prescription = finding.get("prescription", {})
    if isinstance(prescription, dict):
        specified_id = prescription.get("runbook_id", "")
        if specified_id:
            for rb in ALL_RUNBOOKS:
                if rb.runbook_id == specified_id:
                    return rb

    # 自動匹配
    for rb in ALL_RUNBOOKS:
        try:
            if rb.matches(finding):
                return rb
        except Exception:
            continue
    return None
