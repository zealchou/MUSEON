"""Telegram Polling Guard — 單一實例保證 + 409 衝突自動退讓

核心機制：
1. 409 Conflict Detection — 偵測 "terminated by other getUpdates request"
2. Exponential Backoff — 指數退避重試 (2s → 30s, factor=1.8, jitter=±25%)
3. Singleton Guarantee — 確保只有一個 polling 實例
4. Webhook 清理 — 啟動前清理舊的 webhook 避免衝突

參考 Openclaw monitor.ts 的設計模式。

下焦（進程級）的通訊守衛。
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── Backoff 配置 ───

@dataclass
class BackoffPolicy:
    """指數退避策略配置"""

    initial_ms: float = 2000  # 初始延遲 2 秒
    max_ms: float = 30_000  # 最大延遲 30 秒
    factor: float = 1.8  # 指數因子
    jitter: float = 0.25  # 抖動 ±25%


TELEGRAM_POLL_BACKOFF = BackoffPolicy()


def compute_backoff(policy: BackoffPolicy, attempt: int) -> float:
    """計算指數退避延遲（毫秒）。

    延遲序列: 2s → 3.6s → 6.5s → 11.7s → 21s → 30s (上限)
    每次加入 ±25% 的隨機抖動，避免多實例同時重試。

    Args:
        policy: 退避策略配置
        attempt: 重試次數 (從 1 開始)

    Returns:
        延遲時間 (毫秒)
    """
    base = policy.initial_ms * (policy.factor ** (attempt - 1))
    capped = min(base, policy.max_ms)
    jitter_amount = capped * policy.jitter
    jitter_value = random.uniform(-jitter_amount, jitter_amount)
    return max(0, capped + jitter_value)


# ─── 409 Detection ───


def is_getupdates_conflict(error: BaseException) -> bool:
    """檢測是否為 Telegram getUpdates 409 衝突。

    當多個 bot 實例同時進行 long polling 時，
    Telegram API 會回傳 409 Conflict。

    Args:
        error: 捕獲到的異常

    Returns:
        True if this is a getUpdates conflict error.
    """
    # python-telegram-bot 的 Conflict error
    error_str = str(error).lower()
    if "409" not in error_str:
        return False

    return "getupdates" in error_str or "terminated by other" in error_str


def is_recoverable_telegram_error(error: BaseException) -> bool:
    """檢測是否為可恢復的 Telegram 網路錯誤。"""
    error_str = str(error).lower()
    recoverable_patterns = [
        "connection",
        "timeout",
        "network",
        "timed out",
        "reset by peer",
        "broken pipe",
        "eof occurred",
        "ssl",
        "temporary failure",
    ]
    return any(p in error_str for p in recoverable_patterns)


# ─── Telegram Polling Guard ───


@dataclass
class PollingStats:
    """Polling 運行統計"""

    started_at: float = 0.0
    total_restarts: int = 0
    consecutive_errors: int = 0
    last_error: Optional[str] = None
    last_error_at: float = 0.0
    last_successful_poll_at: float = 0.0
    conflict_count: int = 0
    network_error_count: int = 0


class TelegramPollingGuard:
    """Telegram Polling 守衛 — 確保穩定的單一實例長輪詢。

    職責：
    1. 啟動前清理舊的 webhook
    2. 管理 polling 生命週期（啟動、停止、重啟）
    3. 409 衝突偵測 + 指數退避重試
    4. 網路錯誤恢復
    5. 運行統計收集

    使用方式：
        guard = TelegramPollingGuard(bot_token="...")
        await guard.start()
        # ... 運行中 ...
        await guard.stop()
    """

    def __init__(
        self,
        bot_token: str,
        backoff_policy: Optional[BackoffPolicy] = None,
        max_restarts_per_hour: int = 10,
        startup_grace_s: float = 10.0,
        on_message: Optional[Callable] = None,
    ):
        self.bot_token = bot_token
        self.backoff_policy = backoff_policy or TELEGRAM_POLL_BACKOFF
        self.max_restarts_per_hour = max_restarts_per_hour
        self.startup_grace_s = startup_grace_s
        self.on_message = on_message

        self._running = False
        self._stop_event = asyncio.Event()
        self._polling_task: Optional[asyncio.Task] = None
        self._application: Any = None  # python-telegram-bot Application
        self.stats = PollingStats()

        # 滑動窗口：記錄過去 1 小時的重啟時間
        self._restart_timestamps: list[float] = []

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """啟動 Telegram polling 守衛。

        1. 清理舊的 webhook
        2. 建立 bot Application
        3. 啟動受保護的 polling 迴圈
        """
        if self._running:
            logger.warning("TelegramPollingGuard already running")
            return

        self._stop_event.clear()
        self._running = True
        self.stats.started_at = time.time()

        logger.info("TelegramPollingGuard starting...")

        # 啟動受保護的 polling 迴圈（在背景任務中）
        self._polling_task = asyncio.create_task(
            self._guarded_polling_loop(),
            name="telegram-polling-guard",
        )

    async def stop(self) -> None:
        """優雅停止 polling。"""
        if not self._running:
            return

        logger.info("TelegramPollingGuard stopping...")
        self._running = False
        self._stop_event.set()

        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        await self._stop_application()
        logger.info("TelegramPollingGuard stopped")

    async def _guarded_polling_loop(self) -> None:
        """受保護的 polling 主迴圈。

        外層迴圈負責重啟管理：
        - 409 衝突 → 指數退避後重試
        - 網路錯誤 → 指數退避後重試
        - 超過每小時重啟上限 → 停止
        """
        attempt = 0

        while self._running and not self._stop_event.is_set():
            try:
                # 建立並啟動 Application
                await self._start_application()

                # 重置連續錯誤計數
                attempt = 0
                self.stats.consecutive_errors = 0

                # 等待停止信號
                await self._stop_event.wait()
                break

            except asyncio.CancelledError:
                break

            except Exception as e:
                if not self._running:
                    break

                is_conflict = is_getupdates_conflict(e)
                is_recoverable = is_recoverable_telegram_error(e)

                if is_conflict:
                    self.stats.conflict_count += 1
                    reason = "getUpdates conflict (409)"
                elif is_recoverable:
                    self.stats.network_error_count += 1
                    reason = f"network error: {type(e).__name__}"
                else:
                    # 不可恢復的錯誤 — 記錄並停止
                    logger.error(
                        f"TelegramPollingGuard: unrecoverable error: {e}",
                        exc_info=True,
                    )
                    self.stats.last_error = str(e)
                    self.stats.last_error_at = time.time()
                    break

                # 檢查每小時重啟限制
                if not self._can_restart():
                    logger.error(
                        f"TelegramPollingGuard: hit {self.max_restarts_per_hour} "
                        f"restarts/hour limit — stopping"
                    )
                    break

                # 記錄重啟
                attempt += 1
                self.stats.total_restarts += 1
                self.stats.consecutive_errors += 1
                self.stats.last_error = str(e)
                self.stats.last_error_at = time.time()
                self._restart_timestamps.append(time.time())

                # 計算退避延遲
                delay_ms = compute_backoff(self.backoff_policy, attempt)
                delay_s = delay_ms / 1000.0

                logger.warning(
                    f"TelegramPollingGuard: {reason} — "
                    f"retry #{attempt} in {delay_s:.1f}s"
                )

                # 退避等待（可被 stop() 中斷）
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=delay_s
                    )
                    break  # stop_event 被設置 = 收到停止信號
                except asyncio.TimeoutError:
                    pass  # 正常超時 = 繼續重試

                # 確保舊 Application 已清理
                await self._stop_application()

    async def _start_application(self) -> None:
        """建立並啟動 python-telegram-bot Application。"""
        from telegram.ext import Application

        self._application = (
            Application.builder().token(self.bot_token).build()
        )

        # 清理舊的 webhook（防止 conflict）
        try:
            bot = self._application.bot
            await bot.delete_webhook(drop_pending_updates=False)
            logger.debug("Cleaned up old webhook")
        except Exception as e:
            logger.warning(f"Failed to clean webhook: {e}")

        await self._application.initialize()
        await self._application.start()
        await self._application.updater.start_polling(
            drop_pending_updates=False,
            allowed_updates=None,
        )

        self.stats.last_successful_poll_at = time.time()
        logger.info("Telegram polling started successfully")

    async def _stop_application(self) -> None:
        """優雅停止 Application。"""
        if self._application is None:
            return

        try:
            if self._application.updater and self._application.updater.running:
                await self._application.updater.stop()
            if self._application.running:
                await self._application.stop()
                await self._application.shutdown()
        except Exception as e:
            logger.debug(f"Error stopping telegram application: {e}")
        finally:
            self._application = None

    def _can_restart(self) -> bool:
        """檢查是否超過每小時重啟限制（滑動窗口）。"""
        now = time.time()
        one_hour_ago = now - 3600

        # 清理過期記錄
        self._restart_timestamps = [
            t for t in self._restart_timestamps if t > one_hour_ago
        ]

        return len(self._restart_timestamps) < self.max_restarts_per_hour

    def get_status(self) -> dict:
        """取得當前狀態（供 /health 端點使用）。"""
        now = time.time()
        uptime = now - self.stats.started_at if self.stats.started_at else 0

        return {
            "running": self._running,
            "uptime_s": round(uptime, 1),
            "total_restarts": self.stats.total_restarts,
            "consecutive_errors": self.stats.consecutive_errors,
            "conflict_count": self.stats.conflict_count,
            "network_error_count": self.stats.network_error_count,
            "last_error": self.stats.last_error,
            "restarts_last_hour": len(
                [t for t in self._restart_timestamps if t > now - 3600]
            ),
        }
