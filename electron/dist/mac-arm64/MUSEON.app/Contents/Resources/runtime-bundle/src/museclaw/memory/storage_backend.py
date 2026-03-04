"""StorageBackend — 原子寫入存儲後端.

依據 SIX_LAYER_MEMORY BDD Spec §6 實作：
  - 原子寫入：tmpfile + fsync + rename（POSIX 保證）
  - 軟刪除：移至 .trash/ 目錄
  - JSONL Append：審計日誌
  - 目錄自動建立
"""

import json
import logging
import os
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Abstract Base
# ═══════════════════════════════════════════


class StorageBackend(ABC):
    """存儲後端抽象介面."""

    @abstractmethod
    def read(self, user_id: str, category: str, filename: str) -> Optional[Any]:
        ...

    @abstractmethod
    def write(self, user_id: str, category: str, filename: str, data: Any) -> bool:
        ...

    @abstractmethod
    def delete(self, user_id: str, category: str, filename: str) -> bool:
        ...

    @abstractmethod
    def list_files(
        self, user_id: str, category: str, pattern: str = "*.json",
    ) -> List[str]:
        ...

    @abstractmethod
    def exists(self, user_id: str, category: str, filename: str) -> bool:
        ...


# ═══════════════════════════════════════════
# Local Filesystem Implementation
# ═══════════════════════════════════════════


class LocalStorageBackend(StorageBackend):
    """本地檔案系統原子寫入後端."""

    def __init__(self, workspace_root: str):
        self._root = Path(workspace_root)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def workspace_root(self) -> Path:
        return self._root

    def _resolve_path(
        self, user_id: str, category: str, filename: str,
    ) -> Path:
        """路徑解析.

        _system 用戶 → workspace/_system/category/filename
        一般用戶 → workspace/user_id/category/filename
        """
        if user_id == "_system":
            return self._root / "_system" / category / filename
        return self._root / user_id / category / filename

    def read(self, user_id: str, category: str, filename: str) -> Optional[Any]:
        """讀取 JSON 檔案."""
        path = self._resolve_path(user_id, category, filename)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"StorageBackend read error: {path} — {e}")
            return None

    def write(
        self, user_id: str, category: str, filename: str, data: Any,
    ) -> bool:
        """原子寫入 JSON 檔案.

        流程：tmpfile → fsync → rename（POSIX 保證原子性）
        """
        path = self._resolve_path(user_id, category, filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        fd = None
        tmp_path = None
        try:
            # 1. 建立暫存檔（同目錄，確保同 filesystem）
            fd, tmp_path = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp",
            )

            # 2. 寫入 + 強制落盤
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = None  # os.fdopen takes ownership
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # 3. 原子重命名
            os.rename(tmp_path, str(path))
            return True

        except Exception as e:
            logger.error(f"StorageBackend write error: {path} — {e}")
            # 清理暫存檔
            if fd is not None:
                os.close(fd)
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return False

    def delete(self, user_id: str, category: str, filename: str) -> bool:
        """軟刪除：移至 .trash/ 目錄."""
        path = self._resolve_path(user_id, category, filename)
        if not path.exists():
            return False

        trash_dir = self._root / ".trash"
        trash_dir.mkdir(exist_ok=True)

        trash_name = f"{int(time.time())}_{filename}"
        try:
            os.rename(str(path), str(trash_dir / trash_name))
            return True
        except OSError as e:
            logger.error(f"StorageBackend delete error: {path} — {e}")
            return False

    def list_files(
        self, user_id: str, category: str, pattern: str = "*.json",
    ) -> List[str]:
        """列出目錄中符合 pattern 的檔案名."""
        if user_id == "_system":
            dir_path = self._root / "_system" / category
        else:
            dir_path = self._root / user_id / category

        if not dir_path.exists():
            return []

        return [f.name for f in dir_path.glob(pattern)]

    def exists(self, user_id: str, category: str, filename: str) -> bool:
        """檢查檔案是否存在."""
        path = self._resolve_path(user_id, category, filename)
        return path.exists()

    def append(
        self, user_id: str, category: str, filename: str, entry: Dict,
    ) -> bool:
        """JSONL Append — 審計日誌用.

        每行一個 JSON 物件，append-only。
        """
        path = self._resolve_path(user_id, category, filename)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            return True
        except OSError as e:
            logger.error(f"StorageBackend append error: {path} — {e}")
            return False
