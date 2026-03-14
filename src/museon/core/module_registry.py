"""ModuleRegistry — 聲明式模組註冊與統一降級管理.

解決 MUSEON 的模組接入結構債：
- 將 try/except import 集中管理
- 區分 CORE / OPTIONAL / EDGE 三層信任等級
- 提供統一降級策略與健康報告

Usage:
    registry = ModuleRegistry()
    registry.register("intuition", ModuleSpec(
        import_path="museon.agent.intuition",
        class_name="IntuitionEngine",
        tier=ModuleTier.OPTIONAL,
        init_kwargs={"data_dir": str(data_dir)},
    ))
    registry.init_all()

    # Access module:
    intuition = registry.get("intuition")  # returns instance or None
"""

import importlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ModuleTier(Enum):
    """模組信任等級.

    CORE: 核心層 — 失敗 = 系統不可用，應 raise
    OPTIONAL: 功能層 — 失敗 = 功能降級，log warning + set None
    EDGE: 邊緣層 — 失敗 = 跳過，log debug
    """

    CORE = "core"
    OPTIONAL = "optional"
    EDGE = "edge"


@dataclass
class ModuleSpec:
    """模組註冊規格."""

    import_path: str  # e.g. "museon.agent.intuition"
    class_name: str  # e.g. "IntuitionEngine"
    tier: ModuleTier = ModuleTier.OPTIONAL
    init_kwargs: Optional[Dict[str, Any]] = None
    init_factory: Optional[Callable] = None  # 自定義初始化函數
    attr_name: Optional[str] = None  # 在宿主上的屬性名（可選）
    description: str = ""


@dataclass
class ModuleStatus:
    """模組運行狀態."""

    name: str
    tier: ModuleTier
    loaded: bool = False
    instance: Any = None
    error: Optional[str] = None


class ModuleRegistry:
    """聲明式模組註冊表.

    集中管理所有可選模組的載入、降級與健康監控。
    """

    def __init__(self) -> None:
        self._specs: Dict[str, ModuleSpec] = {}
        self._status: Dict[str, ModuleStatus] = {}

    def register(self, name: str, spec: ModuleSpec) -> None:
        """註冊一個模組."""
        self._specs[name] = spec
        self._status[name] = ModuleStatus(name=name, tier=spec.tier)

    def register_many(self, specs: Dict[str, ModuleSpec]) -> None:
        """批量註冊模組."""
        for name, spec in specs.items():
            self.register(name, spec)

    def init_all(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, bool]:
        """初始化所有已註冊模組.

        Args:
            context: 共享上下文（data_dir, event_bus 等），
                     會與每個 ModuleSpec.init_kwargs 合併

        Returns:
            {module_name: success} 映射
        """
        results = {}
        context = context or {}

        # 按 tier 排序：CORE 先載入
        tier_order = {ModuleTier.CORE: 0, ModuleTier.OPTIONAL: 1, ModuleTier.EDGE: 2}
        sorted_specs = sorted(
            self._specs.items(), key=lambda x: tier_order.get(x[1].tier, 1)
        )

        for name, spec in sorted_specs:
            success = self._init_module(name, spec, context)
            results[name] = success

        # 報告
        loaded = sum(1 for s in self._status.values() if s.loaded)
        total = len(self._status)
        failed_core = [
            s.name
            for s in self._status.values()
            if s.tier == ModuleTier.CORE and not s.loaded
        ]
        failed_optional = [
            s.name
            for s in self._status.values()
            if s.tier == ModuleTier.OPTIONAL and not s.loaded
        ]

        logger.info(
            f"[ModuleRegistry] {loaded}/{total} modules loaded"
            + (f" | CORE failures: {failed_core}" if failed_core else "")
            + (
                f" | OPTIONAL degraded: {failed_optional}"
                if failed_optional
                else ""
            )
        )

        if failed_core:
            raise RuntimeError(
                f"CORE modules failed to load: {failed_core}. "
                "System cannot operate without core modules."
            )

        return results

    def _init_module(
        self, name: str, spec: ModuleSpec, context: Dict[str, Any]
    ) -> bool:
        """初始化單個模組."""
        status = self._status[name]
        try:
            if spec.init_factory:
                # 自定義工廠函數
                kwargs = {**(spec.init_kwargs or {}), **context}
                instance = spec.init_factory(**kwargs)
            else:
                # 標準 import + instantiate
                module = importlib.import_module(spec.import_path)
                cls = getattr(module, spec.class_name)
                kwargs = {**(spec.init_kwargs or {})}
                # 從 context 中注入已知的參數
                instance = cls(**kwargs)

            status.loaded = True
            status.instance = instance
            if spec.tier == ModuleTier.EDGE:
                logger.debug(f"[ModuleRegistry] {name} loaded")
            else:
                logger.info(f"[ModuleRegistry] {name} loaded")
            return True

        except ImportError as e:
            status.error = str(e)
            if spec.tier == ModuleTier.CORE:
                logger.critical(f"[ModuleRegistry] CORE module {name} import failed: {e}")
                raise
            elif spec.tier == ModuleTier.OPTIONAL:
                logger.warning(f"[ModuleRegistry] {name} import failed (degraded): {e}")
            else:
                logger.debug(f"[ModuleRegistry] {name} import failed (skipped): {e}")
            return False

        except Exception as e:
            status.error = str(e)
            if spec.tier == ModuleTier.CORE:
                logger.critical(f"[ModuleRegistry] CORE module {name} init failed: {e}")
                raise
            elif spec.tier == ModuleTier.OPTIONAL:
                logger.warning(f"[ModuleRegistry] {name} init failed (degraded): {e}")
            else:
                logger.debug(f"[ModuleRegistry] {name} init failed (skipped): {e}")
            return False

    def get(self, name: str) -> Any:
        """取得模組實例（未載入則返回 None）."""
        status = self._status.get(name)
        return status.instance if status else None

    def is_loaded(self, name: str) -> bool:
        """檢查模組是否已載入."""
        status = self._status.get(name)
        return status.loaded if status else False

    def get_health_report(self) -> Dict[str, Any]:
        """取得所有模組的健康報告."""
        report = {
            "total": len(self._status),
            "loaded": sum(1 for s in self._status.values() if s.loaded),
            "degraded": sum(
                1
                for s in self._status.values()
                if not s.loaded and s.tier == ModuleTier.OPTIONAL
            ),
            "modules": {},
        }
        for name, status in self._status.items():
            report["modules"][name] = {
                "tier": status.tier.value,
                "loaded": status.loaded,
                "error": status.error,
            }
        return report

    def get_degraded_modules(self) -> List[str]:
        """取得所有降級中的模組名稱."""
        return [
            s.name for s in self._status.values() if not s.loaded
        ]

    def inject_to(self, host: Any) -> None:
        """將所有已載入模組注入到宿主物件（如 Brain）.

        使用 ModuleSpec.attr_name 作為屬性名，
        未指定 attr_name 的模組使用註冊名。
        """
        for name, spec in self._specs.items():
            status = self._status[name]
            attr = spec.attr_name or name
            setattr(host, attr, status.instance)  # None if not loaded
