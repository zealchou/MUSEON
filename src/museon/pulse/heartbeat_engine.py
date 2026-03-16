"""HeartbeatEngine — 單例心跳引擎，守護線程運行.

依據 THREE_LAYER_PULSE BDD Spec §2 實作。
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

TICK_INTERVAL = 10.0  # 秒

# ═══════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════

_instance: Optional["HeartbeatEngine"] = None
_singleton_lock = threading.Lock()


def get_heartbeat_engine(state_path: Optional[str] = None) -> "HeartbeatEngine":
    """全域單例."""
    global _instance
    if _instance is None:
        with _singleton_lock:
            if _instance is None:
                _instance = HeartbeatEngine(state_path=state_path)
    return _instance


def _reset_heartbeat_engine() -> None:
    """重置單例（僅供測試用）."""
    global _instance
    with _singleton_lock:
        if _instance is not None:
            _instance.stop()
        _instance = None


# ═══════════════════════════════════════════
# HeartbeatTask
# ═══════════════════════════════════════════


@dataclass
class HeartbeatTask:
    """心跳任務."""

    task_id: str
    func: Callable[[], Any]
    interval_seconds: int
    enabled: bool = True
    last_run: float = 0.0
    run_count: int = 0
    last_error: Optional[str] = None


# ═══════════════════════════════════════════
# HeartbeatEngine
# ═══════════════════════════════════════════


class HeartbeatEngine:
    """單例心跳引擎，守護線程運行.

    tick() 每 TICK_INTERVAL 秒檢查所有註冊任務，
    到期的任務執行其 func()，並更新 run_count / last_run。
    單一任務錯誤不影響其他任務。
    """

    def __init__(self, state_path: Optional[str] = None) -> None:
        self._tasks: Dict[str, HeartbeatTask] = {}
        self._saved_state: Dict[str, Dict] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_interval = TICK_INTERVAL
        self._lock = threading.Lock()
        self._state_path = Path(state_path) if state_path else None
        self._load_state()

    # ── 任務管理 ──

    def register(
        self,
        task_id: str,
        func: Callable,
        interval_seconds: int,
        enabled: bool = True,
    ) -> None:
        """註冊心跳任務."""
        with self._lock:
            saved = self._saved_state.get(task_id, {})
            self._tasks[task_id] = HeartbeatTask(
                task_id=task_id,
                func=func,
                interval_seconds=interval_seconds,
                enabled=enabled,
                last_run=saved.get("last_run", 0.0),
                run_count=saved.get("run_count", 0),
            )

    def unregister(self, task_id: str) -> None:
        """移除心跳任務."""
        with self._lock:
            self._tasks.pop(task_id, None)

    # ── tick 核心 ──

    def tick(self) -> None:
        """檢查所有任務，執行到期的任務."""
        now = time.time()
        with self._lock:
            tasks = list(self._tasks.values())

        for task in tasks:
            if not task.enabled:
                continue
            if now - task.last_run >= task.interval_seconds:
                self._execute_task(task)

    # ── 守護線程 ──

    def start(self) -> None:
        """啟動守護線程."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._daemon_loop, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """停止守護線程."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._tick_interval + 1)
            self._thread = None

    def _daemon_loop(self) -> None:
        """守護線程主迴圈."""
        while self._running:
            try:
                self.tick()
            except Exception as e:
                logger.error(f"HeartbeatEngine tick error: {e}")
            time.sleep(self._tick_interval)

    # ── 延遲任務 ──

    def schedule_delayed_task(
        self,
        task_id: str,
        func: Callable,
        delay_seconds: int,
    ) -> None:
        """排程一次性延遲任務.

        任務在 delay_seconds 後的下一次 tick 執行一次，然後自動移除。
        """
        fire_at = time.time() + delay_seconds
        with self._lock:
            self._tasks[task_id] = HeartbeatTask(
                task_id=task_id,
                func=func,
                interval_seconds=0,  # 一次性
                enabled=True,
                last_run=fire_at,  # 借用 last_run 儲存 fire_at
                run_count=-1,  # 標記為一次性任務
            )

    def _execute_task(self, task: HeartbeatTask) -> None:
        """執行單一任務（錯誤隔離）."""
        is_one_shot = task.run_count == -1
        try:
            task.func()
            if is_one_shot:
                # 一次性任務執行後自動移除
                with self._lock:
                    self._tasks.pop(task.task_id, None)
                logger.info(f"One-shot task '{task.task_id}' completed and removed")
                return
            task.run_count += 1
            task.last_run = time.time()
            task.last_error = None
        except Exception as e:
            task.last_error = str(e)
            task.last_run = time.time()
            logger.error(f"HeartbeatTask '{task.task_id}' error: {e}")
            if is_one_shot:
                with self._lock:
                    self._tasks.pop(task.task_id, None)
        self._save_state()

    # ── 狀態 ──

    def status(self) -> Dict[str, Dict]:
        """回傳所有任務狀態."""
        with self._lock:
            return {
                tid: {
                    "run_count": t.run_count,
                    "last_run": t.last_run,
                    "last_error": t.last_error,
                    "enabled": t.enabled,
                    "interval_seconds": t.interval_seconds,
                }
                for tid, t in self._tasks.items()
            }

    # ── 持久化 ──

    def _save_state(self) -> None:
        """儲存任務狀態到 JSON."""
        if not self._state_path:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            state = {}
            with self._lock:
                for tid, task in self._tasks.items():
                    state[tid] = {
                        "last_run": task.last_run,
                        "run_count": task.run_count,
                        "last_error": task.last_error,
                    }
            tmp = self._state_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.rename(self._state_path)
        except Exception as e:
            logger.error(f"HeartbeatEngine save state failed: {e}")

    def _load_state(self) -> None:
        """從 JSON 載入任務狀態."""
        if not self._state_path or not self._state_path.exists():
            return
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                self._saved_state = json.load(f)
        except Exception as e:
            logger.error(f"HeartbeatEngine load state failed: {e}")
