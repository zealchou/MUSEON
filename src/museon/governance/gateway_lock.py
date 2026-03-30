"""Gateway Lock — 確保全局唯一的 Gateway 實例

兩層 Stale Detection（簡化版）：
1. PID 存活 — kill(pid, 0)；PID 不存在 → dead
2. HTTP health probe — PID 存在但 health check 失敗 → dead（凍結進程亦視為 dead）

參考 Openclaw gateway-lock.ts，適配為 Python + macOS 環境。

下焦（進程級）的核心守衛。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .pid_alive import is_gateway_process, is_pid_alive

logger = logging.getLogger(__name__)

# ─── 配置常量 ───
DEFAULT_PORT = 8765
DEFAULT_TIMEOUT_S = 30.0  # acquire 總超時（與 stale_s 對齊，避免 crash loop）
DEFAULT_POLL_INTERVAL_S = 0.1  # 輪詢間隔
DEFAULT_STALE_S = 30.0  # 30 秒無活動視為 stale
PORT_PROBE_TIMEOUT_S = 1.0  # 端口探測超時


@dataclass
class LockPayload:
    """鎖文件的 JSON 內容"""

    pid: int
    created_at: str  # ISO 8601
    port: int = DEFAULT_PORT
    start_time: Optional[float] = None  # 進程啟動時間 (防止 PID 複用)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> Optional["LockPayload"]:
        try:
            data = json.loads(text)
            return cls(
                pid=data["pid"],
                created_at=data["created_at"],
                port=data.get("port", DEFAULT_PORT),
                start_time=data.get("start_time"),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            return None


class GatewayLockError(Exception):
    """Gateway 鎖取得失敗"""

    pass


class GatewayLock:
    """Gateway 全局唯一實例鎖。

    使用方式：
        lock = GatewayLock(port=8765)
        lock.acquire()  # 阻塞直到取得鎖或超時
        try:
            # ... 運行 gateway ...
        finally:
            lock.release()

    或用 context manager：
        with GatewayLock(port=8765) as lock:
            # ... 運行 gateway ...
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        stale_s: float = DEFAULT_STALE_S,
        lock_dir: Optional[str] = None,
    ):
        self.port = port
        self.timeout_s = timeout_s
        self.stale_s = stale_s

        # 鎖文件路徑: ~/.museon/locks/gateway.<hash>.lock
        if lock_dir is None:
            lock_dir = str(Path.home() / ".museon" / "locks")
        self._lock_dir = Path(lock_dir)
        self._lock_path = self._resolve_lock_path()

        self._acquired = False
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        """取得 Gateway 鎖。

        阻塞直到成功取得鎖或超時。
        如果偵測到鎖持有者已死亡，會自動清理 stale 鎖。

        Raises:
            GatewayLockError: 超時無法取得鎖（另一個 Gateway 正在運行）
        """
        self._lock_dir.mkdir(parents=True, exist_ok=True)

        started_at = time.monotonic()
        last_payload: Optional[LockPayload] = None

        while time.monotonic() - started_at < self.timeout_s:
            try:
                # 嘗試原子建立鎖文件 (O_CREAT | O_EXCL = 如果存在則失敗)
                fd = os.open(
                    str(self._lock_path),
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )

                # 寫入鎖內容
                payload = LockPayload(
                    pid=os.getpid(),
                    created_at=datetime.now(timezone.utc).isoformat(),
                    port=self.port,
                    start_time=self._get_own_start_time(),
                )
                os.write(fd, payload.to_json().encode("utf-8"))

                self._fd = fd
                self._acquired = True
                logger.info(
                    f"Gateway lock acquired: pid={os.getpid()}, "
                    f"port={self.port}, path={self._lock_path}"
                )
                return

            except FileExistsError:
                # 鎖文件已存在 — 檢測持有者狀態
                last_payload = self._read_lock_payload()
                owner_status = self._resolve_owner_status(last_payload)

                if owner_status == "dead":
                    # 持有者已死亡（PID 不存在或 health probe 失敗），清理 stale 鎖
                    owner_pid = last_payload.pid if last_payload else "?"
                    logger.warning(
                        f"Stale gateway lock detected (owner pid={owner_pid}), "
                        f"removing..."
                    )
                    self._force_remove_lock()
                    continue  # 重試

                # 持有者還活著（PID 存活且 health check 通過）— 等待
                time.sleep(DEFAULT_POLL_INTERVAL_S)

            except OSError as e:
                raise GatewayLockError(
                    f"Failed to acquire gateway lock at {self._lock_path}: {e}"
                ) from e

        # 超時
        owner_info = ""
        if last_payload:
            owner_info = f" (owner pid={last_payload.pid})"
        raise GatewayLockError(
            f"Gateway already running{owner_info}; "
            f"lock timeout after {self.timeout_s}s. "
            f"Lock file: {self._lock_path}"
        )

    def release(self) -> None:
        """釋放 Gateway 鎖。"""
        if not self._acquired:
            return

        try:
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None
        except OSError as e:
            logger.debug(f"[GATEWAY_LOCK] operation failed (degraded): {e}")

        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError as e:
            logger.debug(f"[GATEWAY_LOCK] lock failed (degraded): {e}")

        self._acquired = False
        logger.info("Gateway lock released")

    def is_acquired(self) -> bool:
        return self._acquired

    def __enter__(self) -> "GatewayLock":
        self.acquire()
        return self

    def __exit__(self, *args) -> None:
        self.release()

    # ─── Owner Status Detection ───

    def _resolve_owner_status(
        self, payload: Optional[LockPayload]
    ) -> str:
        """解析鎖持有者的狀態。

        兩層檢測（積極策略 — 凍結進程視為 dead，避免死鎖）：
        1. PID 存活檢測 — 如果 PID 不存在 → dead
        2. HTTP health probe — 如果 PID 存在但 health check 失敗 → dead

        Returns:
            "alive" | "dead"
        """
        if payload is None:
            return "dead"

        owner_pid = payload.pid

        # Layer 1: PID 存活檢測
        if not is_pid_alive(owner_pid):
            logger.debug(f"PID {owner_pid} is not alive — owner is dead")
            return "dead"

        # Layer 2: HTTP health probe — PID 存在但無回應（卡死/凍結）視為 dead
        try:
            with socket.create_connection(
                ("127.0.0.1", payload.port), timeout=PORT_PROBE_TIMEOUT_S
            ) as s:
                s.sendall(b"GET /health HTTP/1.0\r\nHost: localhost\r\n\r\n")
                s.settimeout(3.0)
                resp = s.recv(256).decode("utf-8", errors="replace")
                if "200" not in resp:
                    logger.warning(
                        f"PID {owner_pid} port {payload.port} open but "
                        f"health check failed — treating as dead"
                    )
                    return "dead"
        except (OSError, UnicodeDecodeError):
            logger.warning(
                f"PID {owner_pid} port {payload.port} health probe "
                f"failed — treating as dead"
            )
            return "dead"

        # PID 活著且 health check 通過
        return "alive"

    # ─── Helpers ───

    def _resolve_lock_path(self) -> Path:
        """根據 port 生成唯一鎖文件路徑。"""
        hash_input = f"museon-gateway-{self.port}"
        hash_suffix = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        return self._lock_dir / f"gateway.{hash_suffix}.lock"

    def _read_lock_payload(self) -> Optional[LockPayload]:
        """讀取鎖文件內容。"""
        try:
            text = self._lock_path.read_text("utf-8")
            return LockPayload.from_json(text)
        except (FileNotFoundError, PermissionError, OSError):
            return None

    def _is_port_free(self, port: int, host: str = "127.0.0.1") -> bool:
        """嘗試連接端口，判斷是否有監聽器。"""
        try:
            with socket.create_connection(
                (host, port), timeout=PORT_PROBE_TIMEOUT_S
            ):
                return False  # 連接成功 = 有監聽器
        except (ConnectionRefusedError, OSError):
            return True  # 連接失敗 = 端口空閒

    def _is_stale(self, payload: Optional[LockPayload]) -> bool:
        """檢測鎖文件是否過期。"""
        # 方法 1: 檢查 created_at 時間戳
        if payload and payload.created_at:
            try:
                created = datetime.fromisoformat(payload.created_at)
                age = (datetime.now(timezone.utc) - created).total_seconds()
                if age > self.stale_s:
                    return True
            except ValueError as e:
                logger.debug(f"[GATEWAY_LOCK] operation failed (degraded): {e}")

        # 方法 2: 檢查文件修改時間
        try:
            stat = self._lock_path.stat()
            age = time.time() - stat.st_mtime
            return age > self.stale_s
        except OSError:
            return False

    def _force_remove_lock(self) -> None:
        """強制移除鎖文件。"""
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"Failed to remove stale lock: {e}")

    def _get_own_start_time(self) -> Optional[float]:
        """取得自身進程的啟動時間。"""
        from .pid_alive import get_process_start_time

        return get_process_start_time(os.getpid())
