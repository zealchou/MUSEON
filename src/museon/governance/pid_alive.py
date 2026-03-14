"""PID 存活檢測模組

提供跨平台的進程存活性檢測，包含 zombie 進程偵測。
參考 Openclaw pid-alive.ts 的設計模式。

下焦（進程級）的基礎感測器。
"""

from __future__ import annotations

import logging
import os
import platform
import signal

logger = logging.getLogger(__name__)


def is_pid_alive(pid: int) -> bool:
    """檢測指定 PID 的進程是否存活。

    三層檢測：
    1. 基本驗證（PID 有效性）
    2. Signal 0 檢測（進程是否存在）
    3. Zombie 檢測（Linux: /proc/[pid]/status）

    Args:
        pid: 要檢測的進程 ID

    Returns:
        True if the process is alive and not a zombie, False otherwise.
    """
    # Layer 1: 基本驗證
    if not isinstance(pid, int) or pid <= 0:
        return False

    # Layer 2: Signal 0 檢測
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False  # 進程不存在
    except PermissionError:
        return True  # 進程存在但無權限（其他用戶的進程）
    except OSError:
        return False

    # Layer 3: Zombie 檢測 (Linux only)
    if _is_zombie(pid):
        return False

    return True


def get_process_start_time(pid: int) -> float | None:
    """取得進程啟動時間（用於防止 PID 複用誤判）。

    Linux: 讀取 /proc/[pid]/stat 的第 22 個欄位 (starttime)
    macOS: 使用 ps 命令

    Returns:
        啟動時間的 timestamp，如果無法取得則返回 None。
    """
    system = platform.system()

    if system == "Linux":
        return _get_start_time_linux(pid)
    elif system == "Darwin":
        return _get_start_time_macos(pid)
    return None


def get_process_cmdline(pid: int) -> str | None:
    """取得進程的命令行（用於驗證進程身份）。

    Returns:
        進程命令行字串，無法取得則返回 None。
    """
    system = platform.system()

    if system == "Linux":
        try:
            with open(f"/proc/{pid}/cmdline", "r") as f:
                return f.read().replace("\x00", " ").strip()
        except (FileNotFoundError, PermissionError):
            return None

    elif system == "Darwin":
        import subprocess

        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"[PID_ALIVE] PID check failed (degraded): {e}")

    return None


def is_gateway_process(pid: int) -> bool:
    """判斷指定 PID 是否為 MUSEON Gateway 進程。"""
    cmdline = get_process_cmdline(pid)
    if not cmdline:
        return False
    # 檢查命令行中是否包含 gateway 相關關鍵字
    lower = cmdline.lower()
    return "museon" in lower or "gateway" in lower or "uvicorn" in lower


# ─── Private helpers ───


def _is_zombie(pid: int) -> bool:
    """檢測進程是否為 zombie（僅 Linux）。"""
    if platform.system() != "Linux":
        return False
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("State:"):
                    return "Z" in line
    except (FileNotFoundError, PermissionError) as e:
        logger.debug(f"[PID_ALIVE] file stat failed (degraded): {e}")
    return False


def _get_start_time_linux(pid: int) -> float | None:
    """Linux: 從 /proc/[pid]/stat 讀取啟動時間。"""
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            stat = f.read()
        # stat 格式: pid (comm) state ... 第 22 個欄位是 starttime
        # 跳過 (comm) 中可能的空格
        close_paren = stat.rfind(")")
        if close_paren == -1:
            return None
        fields = stat[close_paren + 2 :].split()
        # starttime 是第 20 個欄位（從 state 開始算起，0-indexed 第 19 個）
        if len(fields) > 19:
            return float(fields[19])
    except (FileNotFoundError, PermissionError, ValueError, IndexError) as e:
        logger.debug(f"[PID_ALIVE] file stat failed (degraded): {e}")
    return None


def _get_start_time_macos(pid: int) -> float | None:
    """macOS: 使用 ps 取得進程啟動時間。"""
    import subprocess

    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            from datetime import datetime

            # 格式: "Mon Mar  3 09:25:01 2026"
            try:
                dt = datetime.strptime(
                    result.stdout.strip(), "%a %b %d %H:%M:%S %Y"
                )
                return dt.timestamp()
            except ValueError as e:
                logger.debug(f"[PID_ALIVE] operation failed (degraded): {e}")
    except Exception as e:
        logger.debug(f"[PID_ALIVE] operation failed (degraded): {e}")
    return None
