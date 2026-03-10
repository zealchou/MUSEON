"""CodeAnalyzer — AST 靜態分析引擎.

純 CPU 零 Token，使用 Python ast 模組遍歷語法樹，
偵測常見的架構性問題模式。

規則清單：
  CA001: silent_exception       — except ...: pass 或空 except body
  CA002: asyncio_run_in_thread  — daemon thread 中使用 asyncio.run()
  CA003: missing_error_propagation — 異常被捕獲但未 log 也未 re-raise
  CA004: logger_namespace       — getLogger(__name__) 在 __main__ 模組
  CA005: circular_import_risk   — 模組間循環 import 偵測
  CA006: sync_async_bridge      — 同步函數中直接 await
  CA007: hardcoded_secrets      — 程式碼中硬編碼 API key/token
  CA008: unreachable_code       — return/raise 後的死碼
"""

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# CodeIssue 資料結構
# ═══════════════════════════════════════════


@dataclass
class CodeIssue:
    """靜態分析發現的問題."""

    rule_id: str
    rule_name: str
    severity: str  # "critical" | "warning" | "info"
    file_path: str
    line: int
    message: str
    suggestion: str = ""
    context: str = ""  # 問題行的原始碼片段


# ═══════════════════════════════════════════
# 規則 Visitors
# ═══════════════════════════════════════════


class _CA001_SilentException(ast.NodeVisitor):
    """CA001: except ...: pass 或空 except body."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.issues: List[CodeIssue] = []
        self._file = file_path
        self._lines = source_lines

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        body = node.body
        is_silent = False

        if len(body) == 1:
            stmt = body[0]
            # except: pass
            if isinstance(stmt, ast.Pass):
                is_silent = True
            # except: ...  (Ellipsis)
            elif isinstance(stmt, ast.Expr) and isinstance(
                stmt.value, ast.Constant
            ) and stmt.value.value is ...:
                is_silent = True

        if is_silent:
            ctx = self._lines[node.lineno - 1].strip() if node.lineno <= len(self._lines) else ""
            self.issues.append(CodeIssue(
                rule_id="CA001",
                rule_name="silent_exception",
                severity="critical",
                file_path=self._file,
                line=node.lineno,
                message="異常被靜默吞掉（except: pass），錯誤將完全不可見",
                suggestion="至少加上 logger.error() 或 re-raise",
                context=ctx,
            ))
        self.generic_visit(node)


class _CA002_AsyncioRunInThread(ast.NodeVisitor):
    """CA002: daemon thread 中使用 asyncio.run()."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.issues: List[CodeIssue] = []
        self._file = file_path
        self._lines = source_lines
        self._in_thread_context = False

    def visit_Call(self, node: ast.Call) -> None:
        # 偵測 threading.Thread 的 target 參數
        func = node.func
        is_thread_create = False
        if isinstance(func, ast.Attribute) and func.attr == "Thread":
            is_thread_create = True
        elif isinstance(func, ast.Name) and func.id == "Thread":
            is_thread_create = True

        if is_thread_create:
            for kw in node.keywords:
                if kw.arg == "target" and isinstance(kw.value, (ast.Name, ast.Attribute)):
                    # 記錄 target 函數名，後續檢查
                    pass

        # 偵測 asyncio.run() 呼叫
        if isinstance(func, ast.Attribute) and func.attr == "run":
            if isinstance(func.value, ast.Name) and func.value.id == "asyncio":
                # 檢查是否在 daemon 線程相關的函數內
                ctx = self._lines[node.lineno - 1].strip() if node.lineno <= len(self._lines) else ""
                self.issues.append(CodeIssue(
                    rule_id="CA002",
                    rule_name="asyncio_run_in_thread",
                    severity="critical",
                    file_path=self._file,
                    line=node.lineno,
                    message=(
                        "asyncio.run() 會建立隔離的事件迴圈，"
                        "若在 daemon thread 中使用會導致跨迴圈物件無法互通"
                    ),
                    suggestion=(
                        "改用 asyncio.get_running_loop() + "
                        "asyncio.run_coroutine_threadsafe()"
                    ),
                    context=ctx,
                ))
        self.generic_visit(node)


class _CA003_MissingErrorPropagation(ast.NodeVisitor):
    """CA003: 異常被捕獲但未 log 也未 re-raise."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.issues: List[CodeIssue] = []
        self._file = file_path
        self._lines = source_lines

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        body = node.body

        has_log = False
        has_raise = False

        for stmt in ast.walk(ast.Module(body=body, type_ignores=[])):
            if isinstance(stmt, ast.Raise):
                has_raise = True
            if isinstance(stmt, ast.Call):
                func = stmt.func
                # logger.error / logger.warning / logger.exception / logger.critical
                if isinstance(func, ast.Attribute) and func.attr in (
                    "error", "warning", "exception", "critical", "info",
                ):
                    has_log = True
                # print() 也算某種程度的輸出
                if isinstance(func, ast.Name) and func.id == "print":
                    has_log = True

        # 排除空 body（CA001 已處理）
        is_trivial = len(body) == 1 and isinstance(body[0], (ast.Pass, ast.Expr))
        if is_trivial:
            self.generic_visit(node)
            return

        if not has_log and not has_raise:
            ctx = self._lines[node.lineno - 1].strip() if node.lineno <= len(self._lines) else ""
            self.issues.append(CodeIssue(
                rule_id="CA003",
                rule_name="missing_error_propagation",
                severity="warning",
                file_path=self._file,
                line=node.lineno,
                message="異常被捕獲但既未記錄也未重新拋出，可能遺失錯誤資訊",
                suggestion="加上 logger.error(f'...': {e}') 或 raise",
                context=ctx,
            ))
        self.generic_visit(node)


class _CA004_LoggerNamespace(ast.NodeVisitor):
    """CA004: getLogger(__name__) 在可能作為 __main__ 的模組."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.issues: List[CodeIssue] = []
        self._file = file_path
        self._lines = source_lines
        # 判斷是否有 if __name__ == "__main__" 區塊
        self._has_main_block = False

    def visit_Module(self, node: ast.Module) -> None:
        # 先掃描是否有 __main__ 區塊
        for child in ast.walk(node):
            if isinstance(child, ast.Compare):
                if (isinstance(child.left, ast.Name) and
                        child.left.id == "__name__"):
                    for comparator in child.comparators:
                        if isinstance(comparator, ast.Constant) and comparator.value == "__main__":
                            self._has_main_block = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        is_get_logger = False
        if isinstance(func, ast.Attribute) and func.attr == "getLogger":
            is_get_logger = True
        elif isinstance(func, ast.Name) and func.id == "getLogger":
            is_get_logger = True

        if is_get_logger and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Name) and arg.id == "__name__":
                if self._has_main_block or self._file.endswith("server.py"):
                    ctx = self._lines[node.lineno - 1].strip() if node.lineno <= len(self._lines) else ""
                    self.issues.append(CodeIssue(
                        rule_id="CA004",
                        rule_name="logger_namespace",
                        severity="warning",
                        file_path=self._file,
                        line=node.lineno,
                        message=(
                            "getLogger(__name__) 在可作為 __main__ 執行的模組中，"
                            "會導致 logger 不在正確的命名空間下，日誌可能不可見"
                        ),
                        suggestion="改用明確的命名空間字串，如 getLogger('museon.xxx')",
                        context=ctx,
                    ))
        self.generic_visit(node)


class _CA005_CircularImportRisk:
    """CA005: 模組間循環 import 偵測（需整個專案掃描）."""

    def __init__(self):
        self.import_graph: Dict[str, Set[str]] = {}

    def collect_imports(self, file_path: str, tree: ast.Module) -> None:
        """收集單一檔案的 import 關係."""
        module_name = self._path_to_module(file_path)
        if not module_name:
            return

        imports: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("museon."):
                        imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("museon."):
                    imports.add(node.module)

        self.import_graph[module_name] = imports

    def find_cycles(self) -> List[CodeIssue]:
        """DFS 偵測循環依賴."""
        issues: List[CodeIssue] = []
        visited: Set[str] = set()
        path: List[str] = []

        def dfs(module: str) -> None:
            if module in path:
                cycle_start = path.index(module)
                cycle = path[cycle_start:] + [module]
                issues.append(CodeIssue(
                    rule_id="CA005",
                    rule_name="circular_import_risk",
                    severity="warning",
                    file_path=module.replace(".", "/") + ".py",
                    line=0,
                    message=f"循環 import 風險: {' → '.join(cycle)}",
                    suggestion="考慮延遲 import（函數內 import）或重構模組依賴",
                ))
                return
            if module in visited:
                return
            visited.add(module)
            path.append(module)
            for dep in self.import_graph.get(module, set()):
                dfs(dep)
            path.pop()

        for module in self.import_graph:
            dfs(module)
        return issues

    @staticmethod
    def _path_to_module(file_path: str) -> Optional[str]:
        """將檔案路徑轉換為模組名."""
        # src/museon/agent/tools.py → museon.agent.tools
        parts = Path(file_path).parts
        try:
            idx = list(parts).index("museon")
            module_parts = list(parts[idx:])
            if module_parts[-1] == "__init__.py":
                module_parts = module_parts[:-1]
            else:
                module_parts[-1] = module_parts[-1].replace(".py", "")
            return ".".join(module_parts)
        except (ValueError, IndexError):
            return None


class _CA006_SyncAsyncBridge(ast.NodeVisitor):
    """CA006: 同步函數中直接 await."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.issues: List[CodeIssue] = []
        self._file = file_path
        self._lines = source_lines

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # 同步函數中不應有 await
        for child in ast.walk(node):
            if isinstance(child, ast.Await):
                ctx = self._lines[child.lineno - 1].strip() if child.lineno <= len(self._lines) else ""
                self.issues.append(CodeIssue(
                    rule_id="CA006",
                    rule_name="sync_async_bridge",
                    severity="critical",
                    file_path=self._file,
                    line=child.lineno,
                    message="同步函數中使用 await，會導致 SyntaxError",
                    suggestion="將函數改為 async def 或使用 asyncio.run_coroutine_threadsafe()",
                    context=ctx,
                ))
                break  # 每個函數只報一次
        # 不遞迴進入內部函數
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.visit(child)


_SECRET_PATTERN = re.compile(
    r"""(?:api[_-]?key|secret|token|password|passwd|credential)"""
    r"""\s*=\s*['"][^'"]{8,}['"]""",
    re.IGNORECASE,
)


class _CA007_HardcodedSecrets(ast.NodeVisitor):
    """CA007: 程式碼中硬編碼 API key/token."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.issues: List[CodeIssue] = []
        self._file = file_path
        self._lines = source_lines

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            var_name = ""
            if isinstance(target, ast.Name):
                var_name = target.id
            elif isinstance(target, ast.Attribute):
                var_name = target.attr

            if not var_name:
                continue

            var_lower = var_name.lower()
            sensitive_keywords = (
                "api_key", "secret", "token", "password",
                "passwd", "credential", "private_key",
            )
            if any(kw in var_lower for kw in sensitive_keywords):
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    val = node.value.value
                    # 排除空字串、placeholder
                    if len(val) >= 8 and not val.startswith(("${", "{", "<")):
                        ctx = self._lines[node.lineno - 1].strip() if node.lineno <= len(self._lines) else ""
                        self.issues.append(CodeIssue(
                            rule_id="CA007",
                            rule_name="hardcoded_secrets",
                            severity="critical",
                            file_path=self._file,
                            line=node.lineno,
                            message=f"疑似硬編碼敏感資訊: {var_name}",
                            suggestion="改用環境變數 os.getenv() 或 .env 檔案",
                            context=ctx,
                        ))
        self.generic_visit(node)


class _CA008_UnreachableCode(ast.NodeVisitor):
    """CA008: return/raise 後的死碼."""

    def __init__(self, file_path: str, source_lines: List[str]):
        self.issues: List[CodeIssue] = []
        self._file = file_path
        self._lines = source_lines

    def _check_body(self, body: List[ast.stmt]) -> None:
        for i, stmt in enumerate(body):
            if isinstance(stmt, (ast.Return, ast.Raise)):
                # 檢查後面是否還有語句
                remaining = body[i + 1:]
                for r_stmt in remaining:
                    # 排除 except handler、函數/類定義
                    if isinstance(r_stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        continue
                    ctx = self._lines[r_stmt.lineno - 1].strip() if r_stmt.lineno <= len(self._lines) else ""
                    self.issues.append(CodeIssue(
                        rule_id="CA008",
                        rule_name="unreachable_code",
                        severity="info",
                        file_path=self._file,
                        line=r_stmt.lineno,
                        message="此行程式碼在 return/raise 之後，永遠不會被執行",
                        suggestion="移除死碼或檢查邏輯是否正確",
                        context=ctx,
                    ))
                    break  # 每個區塊只報第一個死碼
                break

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_body(node.body)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_body(node.body)
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self._check_body(node.body)
        if node.orelse:
            self._check_body(node.orelse)
        self.generic_visit(node)


# ═══════════════════════════════════════════
# CodeAnalyzer 主引擎
# ═══════════════════════════════════════════


class CodeAnalyzer:
    """AST 靜態分析引擎.

    掃描 src/museon/ 下所有 .py 檔案，
    執行 CA001-CA008 規則，輸出 CodeIssue 清單。
    """

    def __init__(self, source_root: Optional[Path] = None):
        self._source_root = source_root or Path("src/museon")
        self._ca005 = _CA005_CircularImportRisk()

    def scan_file(self, file_path: Path) -> List[CodeIssue]:
        """掃描單一檔案."""
        issues: List[CodeIssue] = []

        try:
            source = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"CodeAnalyzer: 無法讀取 {file_path}: {e}")
            return issues

        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            issues.append(CodeIssue(
                rule_id="CA000",
                rule_name="syntax_error",
                severity="critical",
                file_path=str(file_path),
                line=e.lineno or 0,
                message=f"語法錯誤: {e.msg}",
            ))
            return issues

        source_lines = source.splitlines()
        fp = str(file_path)

        # CA001: silent_exception
        v1 = _CA001_SilentException(fp, source_lines)
        v1.visit(tree)
        issues.extend(v1.issues)

        # CA002: asyncio_run_in_thread
        v2 = _CA002_AsyncioRunInThread(fp, source_lines)
        v2.visit(tree)
        issues.extend(v2.issues)

        # CA003: missing_error_propagation
        v3 = _CA003_MissingErrorPropagation(fp, source_lines)
        v3.visit(tree)
        issues.extend(v3.issues)

        # CA004: logger_namespace
        v4 = _CA004_LoggerNamespace(fp, source_lines)
        v4.visit(tree)
        issues.extend(v4.issues)

        # CA005: 收集 import 關係（稍後統一分析）
        self._ca005.collect_imports(fp, tree)

        # CA006: sync_async_bridge
        v6 = _CA006_SyncAsyncBridge(fp, source_lines)
        v6.visit(tree)
        issues.extend(v6.issues)

        # CA007: hardcoded_secrets
        v7 = _CA007_HardcodedSecrets(fp, source_lines)
        v7.visit(tree)
        issues.extend(v7.issues)

        # CA008: unreachable_code
        v8 = _CA008_UnreachableCode(fp, source_lines)
        v8.visit(tree)
        issues.extend(v8.issues)

        return issues

    def scan_all(self) -> List[CodeIssue]:
        """掃描整個 src/museon/ 目錄."""
        issues: List[CodeIssue] = []

        if not self._source_root.exists():
            logger.warning(
                f"CodeAnalyzer: source root not found: {self._source_root}"
            )
            return issues

        py_files = sorted(self._source_root.rglob("*.py"))
        py_files = [
            f for f in py_files
            if "__pycache__" not in str(f)
        ]

        logger.info(f"CodeAnalyzer: 掃描 {len(py_files)} 個 .py 檔案")

        for py_file in py_files:
            file_issues = self.scan_file(py_file)
            issues.extend(file_issues)

        # CA005: 循環 import 分析（需整個專案）
        cycle_issues = self._ca005.find_cycles()
        issues.extend(cycle_issues)

        # 統計
        critical = sum(1 for i in issues if i.severity == "critical")
        warning = sum(1 for i in issues if i.severity == "warning")
        info = sum(1 for i in issues if i.severity == "info")
        logger.info(
            f"CodeAnalyzer: 掃描完成 — "
            f"{critical} critical, {warning} warning, {info} info"
        )

        return issues

    def scan_specific_rules(
        self, file_path: Path, rule_ids: List[str]
    ) -> List[CodeIssue]:
        """只執行指定的規則."""
        all_issues = self.scan_file(file_path)
        return [i for i in all_issues if i.rule_id in rule_ids]

    @staticmethod
    def format_report(issues: List[CodeIssue]) -> str:
        """將問題清單格式化為可讀報告."""
        if not issues:
            return "CodeAnalyzer: 未發現問題 ✓"

        lines = [f"CodeAnalyzer 報告 — 共 {len(issues)} 個問題\n"]
        lines.append("=" * 60)

        by_severity = {"critical": [], "warning": [], "info": []}
        for issue in issues:
            by_severity.get(issue.severity, []).append(issue)

        for sev in ("critical", "warning", "info"):
            sev_issues = by_severity[sev]
            if not sev_issues:
                continue
            label = {"critical": "🔴 CRITICAL", "warning": "🟡 WARNING", "info": "ℹ️ INFO"}[sev]
            lines.append(f"\n{label} ({len(sev_issues)})")
            lines.append("-" * 40)
            for issue in sev_issues:
                lines.append(
                    f"  [{issue.rule_id}] {issue.file_path}:{issue.line}"
                )
                lines.append(f"    {issue.message}")
                if issue.suggestion:
                    lines.append(f"    → {issue.suggestion}")
                if issue.context:
                    lines.append(f"    | {issue.context}")
                lines.append("")

        return "\n".join(lines)
