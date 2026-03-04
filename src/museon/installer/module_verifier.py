"""核心模組驗證

對應 features/installation.feature Section 3
驗證四大核心模組是否可載入
"""

import importlib
from typing import List

from .models import StepResult, StepStatus


class ModuleVerifier:
    """驗證核心模組可被 import"""

    # 四大核心模組定義
    CORE_MODULES = [
        ("Gateway", "museon.gateway.server", "create_app"),
        ("LLM Router", "museon.llm.router", "Router"),
        ("Memory Engine", "museon.memory.channels", "ChannelManager"),
        ("Security", "museon.security.sanitizer", "InputSanitizer"),
    ]

    def verify_module(self, module_path: str, attr_name: str) -> StepResult:
        """驗證單一模組

        Args:
            module_path: import 路徑 (e.g. "museon.gateway.server")
            attr_name: 應存在的屬性名 (e.g. "create_app")
        """
        try:
            mod = importlib.import_module(module_path)
            if hasattr(mod, attr_name):
                return StepResult(
                    step_name=f"模組驗證:{module_path}",
                    status=StepStatus.SUCCESS,
                    message=f"{module_path}.{attr_name} 載入成功",
                )
            return StepResult(
                step_name=f"模組驗證:{module_path}",
                status=StepStatus.WARNING,
                message=f"{module_path} 已載入但找不到 {attr_name}",
            )
        except ImportError as e:
            return StepResult(
                step_name=f"模組驗證:{module_path}",
                status=StepStatus.WARNING,
                message=f"無法載入 {module_path}: {e}",
            )
        except Exception as e:
            return StepResult(
                step_name=f"模組驗證:{module_path}",
                status=StepStatus.WARNING,
                message=f"載入 {module_path} 時發生錯誤: {e}",
            )

    def verify_all(self) -> List[StepResult]:
        """驗證所有核心模組

        Returns:
            4 個 StepResult 組成的列表
        """
        results = []
        for name, module_path, attr_name in self.CORE_MODULES:
            result = self.verify_module(module_path, attr_name)
            results.append(result)
        return results
