"""MessageQueueStore — SQLite 持久化訊息佇列.

Gateway 重啟不丟訊息：
  - 訊息進來 → enqueue() 寫入 SQLite (status=pending)
  - 處理完成 → mark_done(trace_id)
  - Gateway 重啟 → recover_pending() 取回未處理訊息
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS message_queue (
    trace_id    TEXT PRIMARY KEY,
    message_json TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
)
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_mq_status ON message_queue (status)
"""


class MessageQueueStore:
    """SQLite-backed message queue for crash recovery."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(db_path), check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_INDEX)
        self._conn.commit()
        logger.info(f"MessageQueueStore ready: {db_path}")

    def enqueue(self, trace_id: str, message_dict: Dict[str, Any]) -> None:
        """持久化一則待處理訊息."""
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO message_queue "
                "(trace_id, message_json, status, created_at, updated_at) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (trace_id, json.dumps(message_dict, ensure_ascii=False), now, now),
            )
            self._conn.commit()

    def mark_done(self, trace_id: str) -> None:
        """標記訊息已處理完成."""
        with self._lock:
            self._conn.execute(
                "UPDATE message_queue SET status='done', updated_at=? "
                "WHERE trace_id=?",
                (time.time(), trace_id),
            )
            self._conn.commit()

    def mark_failed(self, trace_id: str, error: str = "") -> None:
        """標記訊息處理失敗."""
        with self._lock:
            self._conn.execute(
                "UPDATE message_queue SET status='failed', updated_at=? "
                "WHERE trace_id=?",
                (time.time(), trace_id),
            )
            self._conn.commit()

    def recover_pending(self) -> List[Dict[str, Any]]:
        """取回所有未處理的訊息（Gateway 重啟時呼叫）."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT trace_id, message_json FROM message_queue "
                "WHERE status='pending' ORDER BY created_at ASC"
            )
            results = []
            for row in cursor.fetchall():
                try:
                    msg = json.loads(row[1])
                    msg["trace_id"] = row[0]
                    results.append(msg)
                except json.JSONDecodeError:
                    logger.warning(f"Corrupt message in queue: {row[0]}")
            return results

    def cleanup_old(self, days: int = 7) -> int:
        """清理 N 天前已完成的訊息."""
        cutoff = time.time() - days * 86400
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM message_queue "
                "WHERE status IN ('done', 'failed') AND updated_at < ?",
                (cutoff,),
            )
            self._conn.commit()
            return cursor.rowcount

    def get_stats(self) -> Dict[str, int]:
        """取得佇列統計."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT status, COUNT(*) FROM message_queue GROUP BY status"
            )
            return dict(cursor.fetchall())

    def close(self) -> None:
        """關閉資料庫連線."""
        self._conn.close()


# ── Singleton ──

_store: Optional[MessageQueueStore] = None
_store_lock = threading.Lock()


def get_message_queue_store(data_dir: Optional[Path] = None) -> MessageQueueStore:
    """取得 MessageQueueStore 單例."""
    global _store
    with _store_lock:
        if _store is None:
            if data_dir is None:
                raise RuntimeError("MessageQueueStore not initialized, data_dir required")
            db_path = data_dir / "_system" / "message_queue.db"
            _store = MessageQueueStore(db_path)
        return _store
