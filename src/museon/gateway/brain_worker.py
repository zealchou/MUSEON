"""BrainWorkerManager — 獨立 Process 的 Brain Worker.

將 Brain 思考從 Gateway process 分離到獨立 subprocess：
  - Brain crash 不影響 Gateway 收訊能力
  - Worker 自動重啟
  - 支援 fallback 回 in-process 模式

架構：
  Gateway (L1)  ──Pipe──>  BrainWorker (L2 subprocess)
       │                         │
   收訊/回覆               Brain.process()
       │                         │
  不受 Brain                自己的 event loop
  crash 影響                crash 只殺自己
"""
from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing
import os
import signal
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 30 秒啟動超時
_WORKER_INIT_TIMEOUT = 30
# 5 分鐘無回應視為卡死
_WORKER_RESPONSE_TIMEOUT = 300


def _worker_main(data_dir: str, req_conn, resp_conn):
    """Brain worker subprocess 入口.

    在獨立 process 中：
    1. 建立自己的 event loop
    2. 初始化 Brain
    3. 接收請求 → process → 回傳結果
    """
    # 忽略 SIGINT（讓主 process 處理 Ctrl+C）
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    pid = os.getpid()
    worker_logger = logging.getLogger(f"museon.brain_worker.{pid}")

    try:
        from museon.agent.brain import MuseonBrain
        brain = MuseonBrain(data_dir=data_dir)
        worker_logger.info(f"BrainWorker[{pid}] initialized, data_dir={data_dir}")

        # 通知主 process 初始化完成
        resp_conn.send({"type": "ready", "pid": pid})
    except Exception as e:
        resp_conn.send({"type": "init_error", "error": str(e)})
        return

    while True:
        try:
            if not req_conn.poll(timeout=60):
                continue  # 每 60 秒檢查一次連線（heartbeat）
            request = req_conn.recv()
            if request is None:  # Shutdown signal
                worker_logger.info(f"BrainWorker[{pid}] shutting down")
                break

            trace_id = request.get("trace_id", "no-trace")
            worker_logger.info(f"[{trace_id}] BrainWorker processing")

            result = loop.run_until_complete(
                brain.process(
                    content=request["content"],
                    session_id=request["session_id"],
                    user_id=request.get("user_id", "boss"),
                    source=request.get("source", "telegram"),
                    metadata=request.get("metadata"),
                )
            )

            # 序列化 result（跨 process 必須是基本型別）
            from museon.gateway.message import BrainResponse
            if isinstance(result, BrainResponse):
                resp_data = {
                    "text": result.text or "",
                    "has_artifacts": result.has_artifacts(),
                    "artifact_count": len(result.artifacts),
                }
            else:
                resp_data = {"text": str(result) if result else "", "has_artifacts": False}

            resp_conn.send({
                "type": "result",
                "trace_id": trace_id,
                "data": resp_data,
            })

        except EOFError:
            worker_logger.info(f"BrainWorker[{pid}] pipe closed, exiting")
            break
        except Exception as e:
            trace_id = "unknown"
            try:
                trace_id = request.get("trace_id", "unknown") if "request" in locals() else "unknown"
            except Exception:
                pass
            worker_logger.error(f"[{trace_id}] BrainWorker error: {e}", exc_info=True)
            try:
                resp_conn.send({
                    "type": "error",
                    "trace_id": trace_id,
                    "error": f"{type(e).__name__}: {str(e)[:500]}",
                })
            except Exception:
                break  # Pipe broken, exit

    loop.close()


class BrainWorkerManager:
    """管理 Brain subprocess 的生命週期.

    使用方式::

        manager = BrainWorkerManager(data_dir="/path/to/data")
        manager.start()  # 啟動 subprocess

        # 在 async context 中：
        result = await manager.process(
            content="hello",
            session_id="test",
            trace_id="abc123",
        )
        # result = {"text": "...", "has_artifacts": False}

        manager.stop()
    """

    def __init__(self, data_dir: str) -> None:
        self._data_dir = str(data_dir)
        self._process: Optional[multiprocessing.Process] = None
        self._req_conn = None
        self._resp_conn = None
        self._lock = asyncio.Lock()
        self._started = False
        self._restart_count = 0

    def start(self) -> bool:
        """啟動 worker subprocess. Returns True if started successfully."""
        try:
            parent_req, child_req = multiprocessing.Pipe()
            child_resp, parent_resp = multiprocessing.Pipe()

            self._process = multiprocessing.Process(
                target=_worker_main,
                args=(self._data_dir, child_req, child_resp),
                daemon=True,
                name="museon-brain-worker",
            )
            self._process.start()
            self._req_conn = parent_req
            self._resp_conn = parent_resp

            # 等待初始化完成
            if parent_resp.poll(timeout=_WORKER_INIT_TIMEOUT):
                init_msg = parent_resp.recv()
                if init_msg.get("type") == "ready":
                    self._started = True
                    logger.info(
                        f"BrainWorkerManager: worker started, PID={init_msg.get('pid')}"
                    )
                    return True
                else:
                    error = init_msg.get("error", "unknown")
                    logger.error(f"BrainWorkerManager: worker init failed: {error}")
                    self._cleanup()
                    return False
            else:
                logger.error("BrainWorkerManager: worker init timeout")
                self._cleanup()
                return False

        except Exception as e:
            logger.error(f"BrainWorkerManager: start failed: {e}", exc_info=True)
            self._cleanup()
            return False

    async def process(self, **kwargs) -> Dict[str, Any]:
        """發送請求到 worker 並等待結果.

        Args:
            content, session_id, user_id, source, metadata, trace_id

        Returns:
            {"text": str, "has_artifacts": bool}

        Raises:
            RuntimeError: worker 回傳錯誤或不可用
        """
        async with self._lock:
            if not self._started or not self._is_alive():
                if not self._try_restart():
                    raise RuntimeError("BrainWorker not available")

            trace_id = kwargs.get("trace_id", "no-trace")
            self._req_conn.send(kwargs)

            # 非同步等待回應（在 thread 中 blocking recv）
            loop = asyncio.get_event_loop()
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(None, self._resp_conn.recv),
                    timeout=_WORKER_RESPONSE_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(f"[{trace_id}] BrainWorker response timeout ({_WORKER_RESPONSE_TIMEOUT}s)")
                self._cleanup()
                raise RuntimeError("BrainWorker response timeout")

            if response.get("type") == "error":
                raise RuntimeError(response.get("error", "unknown worker error"))

            return response.get("data", {"text": "", "has_artifacts": False})

    def _is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def _try_restart(self) -> bool:
        """嘗試重啟 worker."""
        self._restart_count += 1
        if self._restart_count > 5:
            logger.error("BrainWorkerManager: too many restarts (>5), giving up")
            return False
        logger.warning(f"BrainWorkerManager: restarting worker (attempt #{self._restart_count})")
        self._cleanup()
        return self.start()

    def _cleanup(self) -> None:
        """清理 subprocess 資源."""
        if self._process and self._process.is_alive():
            try:
                self._req_conn.send(None)  # Shutdown signal
                self._process.join(timeout=5)
            except Exception:
                pass
            if self._process.is_alive():
                self._process.kill()
                self._process.join(timeout=2)
        self._process = None
        self._req_conn = None
        self._resp_conn = None
        self._started = False

    def stop(self) -> None:
        """停止 worker."""
        logger.info("BrainWorkerManager: stopping worker")
        self._cleanup()

    def get_status(self) -> Dict[str, Any]:
        """取得 worker 狀態."""
        return {
            "started": self._started,
            "alive": self._is_alive(),
            "pid": self._process.pid if self._process else None,
            "restart_count": self._restart_count,
        }


# ── Singleton ──

_manager: Optional[BrainWorkerManager] = None


def get_brain_worker_manager() -> Optional[BrainWorkerManager]:
    """取得 BrainWorkerManager（可能為 None 如果未啟用）."""
    return _manager


def init_brain_worker_manager(data_dir: str) -> Optional[BrainWorkerManager]:
    """初始化並啟動 BrainWorkerManager."""
    global _manager
    _manager = BrainWorkerManager(data_dir=data_dir)
    if _manager.start():
        return _manager
    else:
        logger.warning("BrainWorkerManager: failed to start, will use in-process fallback")
        _manager = None
        return None
