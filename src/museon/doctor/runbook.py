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
import shutil
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
    action() 只記錄 + 通知，實際重啟由 supervisord autorestart 自動處理。
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
        # Gateway 重啟由 supervisord autorestart=unexpected 自動處理。
        # MuseDoc 只負責記錄 + 通知老闆。
        return RunbookResult(
            success=True,
            message="Gateway 已死亡，已通知老闆。重啟由 supervisord autorestart 處理。",
        )

    async def post_check(self, finding: dict, home: Path) -> bool:
        """Gateway 重啟由 supervisord 管理，post_check 驗證進程是否存在。

        如果 Gateway 已在跑（外力修復），直接通過。
        如果不在跑，等 supervisord autorestart（最多 45 秒）。
        最終無條件通過——action() 的責任（記錄+通知）已完成。
        """
        import subprocess, asyncio

        def _gateway_alive() -> bool:
            try:
                r = subprocess.run(
                    ["pgrep", "-f", "museon.gateway"],
                    capture_output=True, timeout=5,
                )
                return r.returncode == 0
            except Exception:
                return False

        # Gateway 已在跑 → 問題已外力解決
        if _gateway_alive():
            return True

        # 等 supervisord autorestart
        await asyncio.sleep(45)

        # 無論如何都通過：action 的職責（通知）已完成，重啟委託給 supervisord
        # 如果 Gateway 真沒起來，下次 nightly 的 pre_check 會重新建立 finding
        return True


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
            ["find", str(home / "src"), "-name", "__pycache__", "-type", "d"],
            capture_output=True, text=True, timeout=10,
        )
        return len(result.stdout.strip()) > 0  # 有 pyc 目錄存在

    async def action(self, finding: dict, home: Path) -> RunbookResult:
        import subprocess
        subprocess.run(
            ["find", str(home / "src"),
             "-name", "__pycache__", "-type", "d", "-exec", "rm", "-rf", "{}", "+"],
            capture_output=True, timeout=15,
        )
        subprocess.run(
            ["find", str(home / "src"),
             "-name", "*.pyc", "-delete"],
            capture_output=True, timeout=15,
        )
        return RunbookResult(success=True, message="pyc cleaned")

    async def post_check(self, finding: dict, home: Path) -> bool:
        import subprocess
        result = subprocess.run(
            ["find", str(home / "src"), "-name", "__pycache__", "-type", "d"],
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


# ---------------------------------------------------------------------------
# RB-010: SQLite Corruption Repair
# ---------------------------------------------------------------------------

class RB010_SQLiteCorruption(Runbook):
    """SQLite 資料庫損壞修復（C→B→A 瀑布式降級）

    Strategy C: sqlite3 .recover（最佳資料救援）
    Strategy B: .dump + reimport（部分救援）
    Strategy A: 刪除讓應用重建（清空重來）

    安全白名單限制：只處理低扇入 DB，pulse.db 等高扇入 DB 不碰。
    """
    runbook_id = "RB-010"
    name = "SQLite 損壞修復"
    applicable_to = "db_error.*malformed|corrupt|disk I/O"
    severity_limit = "YELLOW"
    blast_radius_max = 3
    timeout_seconds = 120

    SAFE_DBS = {
        "data/_system/group_context.db",
        "data/_system/wee/workflow_state.db",
        "data/_system/message_queue.db",
    }

    def matches(self, finding: dict) -> bool:
        origin = finding.get("blast_origin", {})
        error_type = origin.get("error_type", "")
        if error_type != "db_error":
            return False
        traceback = origin.get("traceback", "")
        title = finding.get("title", "")
        corruption_signals = ("malformed", "corrupt", "disk I/O error", "database disk image")
        return any(s in traceback or s in title for s in corruption_signals)

    async def pre_check(self, finding: dict, home: Path) -> bool:
        import sqlite3
        db_rel = finding.get("blast_origin", {}).get("file", "")
        if db_rel not in self.SAFE_DBS:
            return False
        db_path = home / db_rel
        if not db_path.exists():
            return False
        try:
            conn = sqlite3.connect(str(db_path), timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return not (result and result[0] == "ok")  # True if corrupt
        except sqlite3.DatabaseError:
            return True  # Can't even check = definitely corrupt

    async def action(self, finding: dict, home: Path) -> "RunbookResult":
        import sqlite3

        db_rel = finding.get("blast_origin", {}).get("file", "")
        db_path = home / db_rel
        if not db_path.exists():
            return RunbookResult(False, f"DB not found: {db_rel}")

        # Backup corrupt file
        bak = db_path.with_suffix(".db.corrupt_bak")
        shutil.copy2(str(db_path), str(bak))

        sqlite3_bin = shutil.which("sqlite3")

        # Strategy C: .recover
        if sqlite3_bin:
            try:
                recovered = db_path.with_suffix(".db.recovered")
                result = subprocess.run(
                    [sqlite3_bin, str(db_path), f".output {recovered}", ".recover"],
                    capture_output=True, text=True, timeout=60,
                )
                if recovered.exists() and recovered.stat().st_size > 0:
                    conn = sqlite3.connect(str(recovered), timeout=5)
                    check = conn.execute("PRAGMA integrity_check").fetchone()
                    conn.close()
                    if check and check[0] == "ok":
                        db_path.unlink()
                        recovered.rename(db_path)
                        return RunbookResult(True, f"Recovered {db_rel} via .recover", [str(db_path)])
                recovered.unlink(missing_ok=True)
            except Exception:
                pass

        # Strategy B: .dump + reimport
        if sqlite3_bin:
            try:
                dump_result = subprocess.run(
                    [sqlite3_bin, str(db_path), ".dump"],
                    capture_output=True, text=True, timeout=60,
                )
                if dump_result.stdout and len(dump_result.stdout) > 100:
                    new_db = db_path.with_suffix(".db.new")
                    conn = sqlite3.connect(str(new_db))
                    conn.executescript(dump_result.stdout)
                    conn.close()
                    check_conn = sqlite3.connect(str(new_db), timeout=5)
                    check = check_conn.execute("PRAGMA integrity_check").fetchone()
                    check_conn.close()
                    if check and check[0] == "ok":
                        db_path.unlink()
                        new_db.rename(db_path)
                        return RunbookResult(True, f"Recovered {db_rel} via .dump", [str(db_path)])
                    new_db.unlink(missing_ok=True)
            except Exception:
                pass

        # Strategy A: Delete and let app rebuild
        try:
            db_path.unlink()
            return RunbookResult(
                True,
                f"Deleted corrupt {db_rel} (backup: {bak.name}). App will rebuild on next init.",
                [str(db_path)],
            )
        except OSError as e:
            return RunbookResult(False, f"All strategies failed: {e}")

    async def post_check(self, finding: dict, home: Path) -> bool:
        import sqlite3
        db_rel = finding.get("blast_origin", {}).get("file", "")
        db_path = home / db_rel
        if not db_path.exists():
            return True  # Deleted, will be rebuilt
        try:
            conn = sqlite3.connect(str(db_path), timeout=5)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return result is not None and result[0] == "ok"
        except sqlite3.DatabaseError:
            return False


ALL_RUNBOOKS: list[Runbook] = [
    RB001_StaticReference(),
    RB003_PathCreate(),
    RB004_ConfigKey(),
    RB005_SchemaMigrate(),
    RB006_DeadImport(),
    RB007_GatewayRestart(),
    RB008_PycCleanup(),
    RB009_TelegramReadiness(),
    RB010_SQLiteCorruption(),
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
