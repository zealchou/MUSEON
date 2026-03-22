"""測試 _observe_user 呼叫鏈的參數完整性.

防禦目標：
    確保 _observe_user() 呼叫的所有子方法都能正確接收
    所需的參數（特別是 anima_user），避免 NameError。

歷史教訓：
    2026-03-09 _observe_user_layers() 缺少 anima_user 參數，
    導致所有 Telegram 訊息回傳 NameError，修了三次才定位根因。
"""

import ast
import inspect
from pathlib import Path
from typing import Dict, Set

import pytest

BRAIN_PATH = Path(__file__).parent.parent.parent / "src" / "museon" / "agent" / "brain.py"
AGENT_DIR = BRAIN_PATH.parent

# L3-A2: Brain Mixin 拆分後，方法分散在 brain.py + brain_*.py 中
BRAIN_MIXIN_FILES = [
    BRAIN_PATH,
    AGENT_DIR / "brain_prompt_builder.py",
    AGENT_DIR / "brain_dispatch.py",
    AGENT_DIR / "brain_observation.py",
    AGENT_DIR / "brain_p3_fusion.py",
    AGENT_DIR / "brain_tools.py",
]


class TestObserveMethodSignatures:
    """確保 _observe_* 系列方法的參數簽名一致性."""

    @pytest.fixture
    def brain_source(self) -> str:
        return BRAIN_PATH.read_text(encoding="utf-8")

    @pytest.fixture
    def brain_tree(self, brain_source: str) -> ast.Module:
        return ast.parse(brain_source)

    @pytest.fixture
    def brain_class(self, brain_tree: ast.Module) -> ast.ClassDef:
        for node in brain_tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "MuseonBrain":
                return node
        pytest.fail("MuseonBrain class not found")

    @pytest.fixture
    def all_brain_methods(self) -> Dict[str, ast.FunctionDef]:
        """收集 brain.py + 所有 Mixin 中的方法（L3-A2 拆分相容）."""
        methods = {}
        for path in BRAIN_MIXIN_FILES:
            if not path.exists():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            methods[item.name] = item
        return methods

    def _get_method(self, brain_class_or_dict, name: str):
        # 支援 dict（all_brain_methods）或 ClassDef（向後相容）
        if isinstance(brain_class_or_dict, dict):
            return brain_class_or_dict.get(name)
        for item in brain_class_or_dict.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
                return item
        return None

    def _get_param_names(self, func_node) -> Set[str]:
        params = set()
        for arg in func_node.args.args:
            params.add(arg.arg)
        for arg in func_node.args.posonlyargs:
            params.add(arg.arg)
        for arg in func_node.args.kwonlyargs:
            params.add(arg.arg)
        return params

    def _get_bare_name_loads(self, func_node, var_name: str):
        """取得方法中對 var_name 的所有 Load 引用（排除子函式/lambda）."""
        loads = []
        for child in ast.walk(func_node):
            if (isinstance(child, ast.Name)
                    and child.id == var_name
                    and isinstance(child.ctx, ast.Load)):
                loads.append(child.lineno)
        return loads

    # ── 核心測試：每個引用 anima_user 的方法都必須有它在參數中 ──

    def test_observe_user_has_anima_user_param(self, all_brain_methods):
        """_observe_user() 必須有 anima_user 參數."""
        method = self._get_method(all_brain_methods, "_observe_user")
        assert method is not None, "_observe_user not found"
        params = self._get_param_names(method)
        assert "anima_user" in params

    def test_observe_user_layers_has_anima_user_param(self, all_brain_methods):
        """_observe_user_layers() 必須有 anima_user 參數（歷史 bug 回歸測試）."""
        method = self._get_method(all_brain_methods, "_observe_user_layers")
        assert method is not None, "_observe_user_layers not found"
        params = self._get_param_names(method)
        assert "anima_user" in params, (
            "_observe_user_layers 缺少 anima_user 參數！"
            "這會導致 NameError（2026-03-09 回歸 bug）"
        )

    def test_observe_preferences_has_anima_user_param(self, all_brain_methods):
        """_observe_preferences() 必須有 anima_user 參數."""
        method = self._get_method(all_brain_methods, "_observe_preferences")
        assert method is not None, "_observe_preferences not found"
        params = self._get_param_names(method)
        assert "anima_user" in params

    def test_observe_ring_events_has_anima_user_param(self, all_brain_methods):
        """_observe_ring_events() 必須有 anima_user 參數."""
        method = self._get_method(all_brain_methods, "_observe_ring_events")
        assert method is not None, "_observe_ring_events not found"
        params = self._get_param_names(method)
        assert "anima_user" in params

    def test_observe_patterns_has_anima_user_param(self, all_brain_methods):
        """_observe_patterns() 必須有 anima_user 參數."""
        method = self._get_method(all_brain_methods, "_observe_patterns")
        assert method is not None, "_observe_patterns not found"
        params = self._get_param_names(method)
        assert "anima_user" in params

    def test_calibrate_rc_has_anima_user_param(self, all_brain_methods):
        """_calibrate_rc() 必須有 anima_user 參數."""
        method = self._get_method(all_brain_methods, "_calibrate_rc")
        assert method is not None, "_calibrate_rc not found"
        params = self._get_param_names(method)
        assert "anima_user" in params

    # ── 泛型測試：任何引用 anima_user 的方法都必須有它在 scope 中 ──

    def test_no_undefined_anima_user_references(self, all_brain_methods):
        """所有引用 anima_user 的方法都必須有它在參數或本地變數中.

        這是最關鍵的泛型測試——它會自動偵測未來新增的方法
        如果忘記把 anima_user 加入參數，就會被抓到。
        掃描範圍：brain.py + 所有 Mixin 檔案（L3-A2 相容）。
        """
        violations = []
        for func_name, item in all_brain_methods.items():
            params = self._get_param_names(item)

            # 收集本地賦值
            stores = set()
            for child in ast.walk(item):
                if (isinstance(child, ast.Name)
                        and child.id == "anima_user"
                        and isinstance(child.ctx, ast.Store)):
                    stores.add(child.lineno)

            # 收集 Load 引用
            loads = self._get_bare_name_loads(item, "anima_user")

            # 如果有 Load 引用但不在參數也不在本地賦值中
            if loads and "anima_user" not in params and not stores:
                violations.append(
                    f"{func_name}() 第 {loads} 行引用 anima_user "
                    f"但它既不是參數也不是本地變數"
                )

        assert not violations, (
            "發現 anima_user 的 scope 漏洞（會導致 NameError）：\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


class TestExcInfoInErrorHandlers:
    """確保關鍵 exception handler 有 exc_info=True."""

    @pytest.fixture
    def server_tree(self) -> ast.Module:
        server_path = BRAIN_PATH.parent.parent / "gateway" / "server.py"
        source = server_path.read_text(encoding="utf-8")
        return ast.parse(source)

    @pytest.fixture
    def brain_trees(self) -> list:
        """L3-A2: brain.py + 所有 Mixin 檔案的 AST."""
        trees = []
        for path in BRAIN_MIXIN_FILES:
            if path.exists():
                trees.append((path.name, ast.parse(path.read_text(encoding="utf-8"))))
        return trees

    def _count_missing_exc_info(self, tree: ast.Module) -> list:
        missing = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                for child in ast.walk(node):
                    if (isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Attribute)
                            and child.func.attr == "error"):
                        has_ei = any(
                            kw.arg == "exc_info" for kw in child.keywords
                        )
                        if not has_ei:
                            missing.append(child.lineno)
        return missing

    def test_server_all_error_handlers_have_exc_info(self, server_tree):
        """server.py 的所有 logger.error 都必須有 exc_info=True."""
        missing = self._count_missing_exc_info(server_tree)
        assert not missing, (
            f"server.py 有 {len(missing)} 個 logger.error 缺少 exc_info=True: "
            f"行 {missing[:5]}..."
        )

    def test_brain_all_error_handlers_have_exc_info(self, brain_trees):
        """brain.py + Mixin 的所有 logger.error 都必須有 exc_info=True."""
        all_missing = []
        for filename, tree in brain_trees:
            missing = self._count_missing_exc_info(tree)
            for line in missing:
                all_missing.append(f"{filename}:{line}")
        assert not all_missing, (
            f"Brain 系列有 {len(all_missing)} 個 logger.error 缺少 exc_info=True: "
            f"{all_missing[:5]}..."
        )
