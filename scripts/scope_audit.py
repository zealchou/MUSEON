#!/usr/bin/env python3
"""Scope Audit Tool — 偵測方法中未定義的變數引用.

用途：在建置或部署前執行，抓出 Python 方法中引用了
未作為參數或本地賦值的變數名稱（會導致 NameError 的 bug）。

這類 bug 的特徵：
  - 在方法 A 中有某個 local 變數 x
  - 方法 A 呼叫方法 B，但忘記把 x 傳給 B
  - 方法 B 卻直接引用了 x → NameError

靜態 linter（ruff F821）理論上能抓到，但 MUSEON 目前未安裝。
此腳本作為輕量替代方案，專注偵測此類 scope 漏洞。

Usage:
    python scripts/scope_audit.py                    # 掃描所有 src/
    python scripts/scope_audit.py src/museon/agent/brain.py  # 掃描指定檔案
"""

import ast
import sys
from pathlib import Path
from typing import Set


# 常見 built-in 名稱（不需要在 scope 中定義）
BUILTINS = {
    "True", "False", "None", "print", "len", "str", "int", "float",
    "dict", "list", "set", "tuple", "bool", "type", "range", "enumerate",
    "zip", "map", "filter", "sorted", "reversed", "min", "max", "sum",
    "abs", "round", "any", "all", "isinstance", "issubclass", "hasattr",
    "getattr", "setattr", "delattr", "super", "property", "staticmethod",
    "classmethod", "ValueError", "TypeError", "KeyError", "AttributeError",
    "RuntimeError", "Exception", "IndexError", "FileNotFoundError",
    "IOError", "OSError", "StopIteration", "NotImplementedError",
    "NameError", "ImportError", "ModuleNotFoundError", "StopAsyncIteration",
    "open", "input", "id", "hash", "repr", "format", "chr", "ord",
    "bytes", "bytearray", "memoryview", "object", "complex",
    "frozenset", "iter", "next", "slice", "globals", "locals",
    "vars", "dir", "callable", "exec", "eval", "compile",
    "breakpoint", "NotImplemented", "Ellipsis",
    "__name__", "__file__", "__doc__", "__class__", "__import__",
}


def collect_defined_names(func_node: ast.AST) -> Set[str]:
    """收集函式 scope 中所有已定義的名稱（參數 + 賦值 + import + for + with + except）."""
    defined = set()

    # 參數
    if isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for arg in func_node.args.args:
            defined.add(arg.arg)
        for arg in func_node.args.posonlyargs:
            defined.add(arg.arg)
        for arg in func_node.args.kwonlyargs:
            defined.add(arg.arg)
        if func_node.args.vararg:
            defined.add(func_node.args.vararg.arg)
        if func_node.args.kwarg:
            defined.add(func_node.args.kwarg.arg)

    for child in ast.walk(func_node):
        # 賦值目標
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            defined.add(child.id)
        # for 迴圈
        if isinstance(child, ast.For):
            if isinstance(child.target, ast.Name):
                defined.add(child.target.id)
            elif isinstance(child.target, ast.Tuple):
                for elt in child.target.elts:
                    if isinstance(elt, ast.Name):
                        defined.add(elt.id)
        # with-as
        if isinstance(child, ast.withitem) and child.optional_vars:
            if isinstance(child.optional_vars, ast.Name):
                defined.add(child.optional_vars.id)
        # import
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            for alias in child.names:
                name = alias.asname if alias.asname else alias.name.split(".")[0]
                defined.add(name)
        # except handler
        if isinstance(child, ast.ExceptHandler) and child.name:
            defined.add(child.name)
        # comprehension variable
        if isinstance(child, ast.comprehension):
            if isinstance(child.target, ast.Name):
                defined.add(child.target.id)
            elif isinstance(child.target, ast.Tuple):
                for elt in child.target.elts:
                    if isinstance(elt, ast.Name):
                        defined.add(elt.id)
        # lambda 參數（lambda 有自己的 scope）
        if isinstance(child, ast.Lambda):
            for arg in child.args.args:
                defined.add(arg.arg)
            for arg in child.args.kwonlyargs:
                defined.add(arg.arg)
            if child.args.vararg:
                defined.add(child.args.vararg.arg)
            if child.args.kwarg:
                defined.add(child.args.kwarg.arg)
        # 巢狀函式的參數（巢狀函式定義在此 scope 中，其參數在子 scope 有效）
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child is not func_node:
            defined.add(child.name)  # 函式名本身
            for arg in child.args.args:
                defined.add(arg.arg)
            for arg in child.args.kwonlyargs:
                defined.add(arg.arg)

    return defined


def collect_module_names(tree: ast.Module) -> Set[str]:
    """收集模組頂層定義的名稱."""
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname if alias.asname else alias.name.split(".")[0]
                names.add(name)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
    return names


def audit_file(filepath: Path) -> list:
    """掃描一個 Python 檔案，回傳所有 scope 異常."""
    issues = []

    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError) as e:
        return [{"file": str(filepath), "line": 0, "method": "", "var": "",
                 "message": f"Parse error: {e}"}]

    module_names = collect_module_names(tree)

    # 遍歷所有 class
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        class_name = node.name

        # 收集 class-level 名稱
        class_names = set()
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                class_names.add(item.name)
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_names.add(target.id)

        # 檢查每個方法
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            func_name = item.name
            defined = collect_defined_names(item)

            # 找所有 Load 引用
            for child in ast.walk(item):
                if not isinstance(child, ast.Name):
                    continue
                if not isinstance(child.ctx, ast.Load):
                    continue

                name = child.id

                # 跳過：已定義、built-in、模組級、class 級、私有/dunder
                if name in defined:
                    continue
                if name in BUILTINS:
                    continue
                if name in module_names:
                    continue
                if name in class_names:
                    continue
                if name.startswith("_"):
                    continue

                # 這個名稱在當前方法 scope 中未定義
                issues.append({
                    "file": str(filepath),
                    "line": child.lineno,
                    "class": class_name,
                    "method": func_name,
                    "var": name,
                    "message": (
                        f"{class_name}.{func_name}() 第 {child.lineno} 行: "
                        f"'{name}' 在此方法中未定義（非參數、非本地變數、非 import）"
                    ),
                })

    return issues


def main():
    """主入口."""
    if len(sys.argv) > 1:
        targets = [Path(p) for p in sys.argv[1:]]
    else:
        targets = list(Path("src").rglob("*.py"))

    total_issues = 0
    files_scanned = 0

    for filepath in sorted(targets):
        if not filepath.exists():
            print(f"  跳過（不存在）: {filepath}")
            continue
        if "__pycache__" in str(filepath):
            continue

        files_scanned += 1
        issues = audit_file(filepath)

        if issues:
            for issue in issues:
                total_issues += 1
                print(f"  SCOPE-WARN: {issue['message']}")

    print(f"\n{'=' * 60}")
    print(f"Scope Audit 完成: {files_scanned} 個檔案, {total_issues} 個警告")

    if total_issues > 0:
        print(f"\n注意：以上警告可能是 False Positive（例如 decorator 注入的變數）。")
        print(f"請人工確認每個警告是否為真正的 scope 漏洞。")
        sys.exit(1)
    else:
        print("未發現 scope 漏洞。")
        sys.exit(0)


if __name__ == "__main__":
    main()
