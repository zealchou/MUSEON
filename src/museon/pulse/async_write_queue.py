"""AsyncWriteQueue — 非同步寫入佇列.

所有非關鍵路徑的寫入（PulseDB、ANIMA JSON、KnowledgeLattice）
統一排隊，由單一背景執行緒依序執行，避免 SQLite 鎖競爭。

設計原則：
  - Singleton（整個 process 只有一個 writer thread）
  - 非阻塞 enqueue（佇列滿時丟棄並警告）
  - daemon thread（主程序結束時自動收尾）
  - 每個任務獨立 try/except（一個失敗不影響後續）
"""

import logging
import queue
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)


class AsyncWriteQueue:
    """單一寫入執行緒佇列 — 序列化所有非關鍵寫入."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instance = inst
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._queue: queue.Queue = queue.Queue(maxsize=500)
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="museon-write-queue"
        )
        self._running = True
        self._drop_count = 0
        self._total_processed = 0
        self._thread.start()
        self._initialized = True
        logger.info("AsyncWriteQueue started (single-writer thread)")

    # ── Public API ──

    def enqueue(self, label: str, fn: Callable, *args: Any, **kwargs: Any) -> bool:
        """將寫入任務加入佇列（非阻塞）.

        Args:
            label: 任務標籤（用於日誌追蹤）
            fn: 要執行的寫入函式
            *args, **kwargs: 傳給 fn 的參數

        Returns:
            True 若成功入列，False 若佇列已滿而被丟棄
        """
        try:
            self._queue.put_nowait((label, fn, args, kwargs))
            return True
        except queue.Full:
            self._drop_count += 1
            logger.warning(
                f"WriteQueue full (size={self._queue.maxsize}), "
                f"dropping: {label} (total dropped: {self._drop_count})"
            )
            return False

    @property
    def pending(self) -> int:
        """目前佇列中待處理的任務數."""
        return self._queue.qsize()

    @property
    def stats(self) -> dict:
        """佇列統計資訊."""
        return {
            "pending": self.pending,
            "total_processed": self._total_processed,
            "total_dropped": self._drop_count,
            "running": self._running,
        }

    def shutdown(self, timeout: float = 5.0) -> None:
        """優雅關閉佇列（等待剩餘任務完成）."""
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)
        remaining = self._queue.qsize()
        if remaining > 0:
            logger.warning(f"WriteQueue shutdown with {remaining} tasks remaining")
        logger.info(
            f"AsyncWriteQueue stopped "
            f"(processed={self._total_processed}, dropped={self._drop_count})"
        )

    # ── Worker ──

    def _worker(self) -> None:
        """單一寫入執行緒 — 依序消化佇列."""
        while self._running:
            try:
                label, fn, args, kwargs = self._queue.get(timeout=1.0)
                try:
                    fn(*args, **kwargs)
                    self._total_processed += 1
                except Exception as e:
                    logger.error(f"WriteQueue [{label}] failed: {e}")
                    self._total_processed += 1  # 計入已處理（即使失敗）
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"WriteQueue worker unexpected error: {e}")


def get_write_queue() -> AsyncWriteQueue:
    """取得全域 AsyncWriteQueue 實例."""
    return AsyncWriteQueue()
