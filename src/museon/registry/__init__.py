"""Registry Layer — 結構化資料層.

以 SQLite 為結構化真相來源，Qdrant documents collection 為語義索引輔助，
提供記帳查帳、會議記錄追蹤、行程提醒、聯絡人管理等結構化資料能力。

每個 user_id 獨立一份 registry.db，搭配 vault/（原始檔案）與 inbox/（待處理區）。

設計原則：
- Graceful Degradation：Qdrant 不可用不影響 SQLite 寫入
- Lazy Init：首次存取時才建立 SQLite 連線
- 原子寫入：SQLite 用 transaction；Qdrant 失敗記入 pending queue
"""

from museon.registry.registry_manager import RegistryManager
from museon.registry.schema import RegistrySchema
from museon.registry.planner import EventPlanner, infer_timezone

__all__ = [
    "RegistryManager",
    "RegistrySchema",
    "EventPlanner",
    "infer_timezone",
]
