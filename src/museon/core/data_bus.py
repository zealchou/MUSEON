"""DataBus — 資料層路由與 Store 統一治理.

類比 EventBus 的資料層對應物：
- EventBus 管事件流，DataBus 管資料流
- 所有 Store 註冊到 DataBus，提供統一的發現、健康檢查、TTL 治理

設計原則：
- 輕量 mixin：DataContract 不強迫改寫內部邏輯，只要求聲明元資料
- 漸進接入：Store 可逐步實現 DataContract，未實現的仍可註冊
- 運行時發現：Phase 4 的監控與自癒建立在此基礎上

Usage:
    from museon.core.data_bus import DataBus, DataContract, StoreSpec

    class MyStore(DataContract):
        @classmethod
        def store_spec(cls) -> StoreSpec:
            return StoreSpec(
                name="my_store",
                engine="sqlite",
                ttl="permanent",
                description="My store description",
            )

        def health_check(self) -> Dict[str, Any]:
            return {"status": "ok", "records": 42}

    # 註冊
    bus = get_data_bus()
    bus.register("my_store", my_store_instance)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════
# TTL 分級（與 persistence-contract.md 對齊）
# ════════════════════════════════════════════

class TTLTier(Enum):
    """資料生命週期等級."""

    PERMANENT = "permanent"       # 永久保留
    LONG = "long_90d"             # 90 天
    MEDIUM = "medium_30d"         # 30 天
    SHORT = "short_14d"           # 14 天
    EPHEMERAL = "ephemeral_24h"   # 24 小時
    ROLLING = "rolling_5mb"       # 檔案 > 5MB 輪替


class StoreEngine(Enum):
    """儲存引擎類型."""

    SQLITE = "sqlite"
    JSON = "json"
    JSONL = "jsonl"
    MARKDOWN = "markdown"
    MIXED = "mixed"               # 多引擎混合（如 PlanStore: JSON + MD）


# ════════════════════════════════════════════
# Store 規格聲明
# ════════════════════════════════════════════

@dataclass
class StoreSpec:
    """Store 的靜態元資料聲明.

    每個 DataContract 實現者必須提供此規格。
    """

    name: str                              # 唯一名稱（如 "pulse_db"）
    engine: StoreEngine                    # 儲存引擎
    ttl: TTLTier = TTLTier.PERMANENT       # 預設 TTL
    write_mode: str = "replace"            # "replace" | "append_only"
    description: str = ""
    tables: List[str] = field(default_factory=list)  # SQLite tables / JSON files


# ════════════════════════════════════════════
# DataContract — Store 介面協議
# ════════════════════════════════════════════

class DataContract(ABC):
    """資料 Store 的統一介面協議.

    設計為輕量 mixin：
    - 只要求 2 個方法：store_spec() 和 health_check()
    - 不干預 Store 的內部讀寫邏輯
    - 為 Phase 4 的監控與自癒提供基礎
    """

    @classmethod
    @abstractmethod
    def store_spec(cls) -> StoreSpec:
        """聲明此 Store 的靜態規格.

        Returns:
            StoreSpec 元資料
        """
        ...

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """執行健康檢查.

        Returns:
            至少包含 {"status": "ok"|"degraded"|"error", ...}
            可額外包含 records / size_bytes / last_write 等指標
        """
        ...


# ════════════════════════════════════════════
# DataBus — Store 統一路由與治理
# ════════════════════════════════════════════

class DataBus:
    """資料層路由器 — 所有 Store 的統一進入點.

    職責：
    1. Store 註冊與發現
    2. 健康檢查聚合
    3. Store 元資料查詢
    4. 為 Phase 4 監控提供基礎

    不負責：
    - Store 的實際讀寫（各 Store 自行處理）
    - Store 的初始化（由 ModuleRegistry 或調用方處理）
    """

    def __init__(self) -> None:
        self._stores: Dict[str, Any] = {}             # name → instance
        self._specs: Dict[str, StoreSpec] = {}         # name → spec

    def register(self, name: str, store: Any, spec: Optional[StoreSpec] = None) -> None:
        """註冊一個 Store.

        Args:
            name: Store 唯一名稱
            store: Store 實例
            spec: Store 規格（如果 store 實現 DataContract 則自動取得）
        """
        self._stores[name] = store

        # 自動從 DataContract 取得 spec
        if spec is None and isinstance(store, DataContract):
            spec = store.__class__.store_spec()

        if spec is not None:
            self._specs[name] = spec

        logger.debug(f"DataBus: 註冊 Store '{name}' "
                     f"(engine={spec.engine.value if spec else 'unknown'})")

    def unregister(self, name: str) -> bool:
        """移除一個 Store."""
        removed = name in self._stores
        self._stores.pop(name, None)
        self._specs.pop(name, None)
        return removed

    def get(self, name: str) -> Optional[Any]:
        """取得 Store 實例."""
        return self._stores.get(name)

    def get_spec(self, name: str) -> Optional[StoreSpec]:
        """取得 Store 規格."""
        return self._specs.get(name)

    def list_stores(self) -> List[str]:
        """列舉所有已註冊的 Store 名稱."""
        return list(self._stores.keys())

    def list_specs(self) -> List[StoreSpec]:
        """列舉所有已註冊的 Store 規格."""
        return list(self._specs.values())

    def health_check_all(self) -> Dict[str, Dict[str, Any]]:
        """對所有 Store 執行健康檢查.

        Returns:
            {store_name: health_result}
        """
        results = {}
        for name, store in self._stores.items():
            if isinstance(store, DataContract):
                try:
                    results[name] = store.health_check()
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}
            else:
                results[name] = {"status": "unknown", "reason": "no DataContract"}
        return results

    def summary(self) -> Dict[str, Any]:
        """產出 DataBus 總覽摘要.

        Returns:
            包含 store 數量、引擎分布、健康狀態等
        """
        engine_counts: Dict[str, int] = {}
        ttl_counts: Dict[str, int] = {}

        for spec in self._specs.values():
            eng = spec.engine.value
            engine_counts[eng] = engine_counts.get(eng, 0) + 1
            ttl = spec.ttl.value
            ttl_counts[ttl] = ttl_counts.get(ttl, 0) + 1

        health = self.health_check_all()
        status_counts: Dict[str, int] = {}
        for h in health.values():
            s = h.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "total_stores": len(self._stores),
            "with_contract": sum(
                1 for s in self._stores.values() if isinstance(s, DataContract)
            ),
            "engines": engine_counts,
            "ttl_tiers": ttl_counts,
            "health": status_counts,
        }


# ════════════════════════════════════════════
# Singleton
# ════════════════════════════════════════════

_data_bus_instance: Optional[DataBus] = None


def get_data_bus() -> DataBus:
    """取得 DataBus 單例."""
    global _data_bus_instance
    if _data_bus_instance is None:
        _data_bus_instance = DataBus()
        logger.info("DataBus singleton created")
    return _data_bus_instance
