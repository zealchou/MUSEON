"""BulkheadRegistry — 艙壁隔離註冊表.

模擬潛艇的水密艙門機制：
  - 每個子系統獨立初始化
  - 一個子系統失敗不影響其他子系統
  - 失敗的子系統標記為 DEGRADED/FAILED
  - /health 端點反映整體降級狀態

與現有 Brain try/except 模式的關係：
  - Brain 內部已有 16+ 個 try/except 區塊做個別降級
  - BulkheadRegistry 將此模式提升為 Gateway 層級的集中式註冊
  - 提供統一的健康狀態查詢介面

未來可與 AutonomicLayer 整合：
  - FAILED 子系統自動入隊修復
  - 定期重試 DEGRADED 子系統

設計原則：
  - 零 LLM 依賴
  - 執行緒安全（使用 threading.Lock）
  - 不攔截現有啟動流程，只觀察並記錄
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 子系統狀態
# ═══════════════════════════════════════════


class SubsystemStatus(Enum):
    """子系統健康狀態."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class SubsystemInfo:
    """子系統資訊."""

    name: str
    status: SubsystemStatus
    critical: bool = False            # 核心子系統 = 整體降級
    error: Optional[str] = None
    started_at: Optional[float] = None
    failed_at: Optional[float] = None


# ═══════════════════════════════════════════
# BulkheadRegistry
# ═══════════════════════════════════════════


class BulkheadRegistry:
    """艙壁隔離註冊表 — 潛艇的水密艙門.

    每個子系統透過 register() 獨立初始化。
    失敗不影響其他子系統，只標記狀態。

    使用方式::

        bulkhead = BulkheadRegistry()

        # 註冊子系統（各自獨立 try/except）
        bulkhead.register("brain", init_brain, critical=True)
        bulkhead.register("telegram", init_telegram)
        bulkhead.register("cron", init_cron)

        # 查詢整體狀態
        print(bulkhead.overall_status)   # "healthy" / "degraded" / "critical"
        print(bulkhead.get_status())     # {"brain": "healthy", "telegram": "failed"}
    """

    def __init__(self) -> None:
        self._subsystems: Dict[str, SubsystemInfo] = {}
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        init_fn: Callable[[], Any],
        critical: bool = False,
    ) -> bool:
        """註冊並初始化一個子系統.

        Args:
            name: 子系統名稱
            init_fn: 初始化函數（無參數，可拋例外）
            critical: 是否為核心子系統（失敗會讓整體降級）

        Returns:
            True 如果初始化成功
        """
        try:
            init_fn()
            info = SubsystemInfo(
                name=name,
                status=SubsystemStatus.HEALTHY,
                critical=critical,
                started_at=time.time(),
            )
            with self._lock:
                self._subsystems[name] = info
            logger.info(f"Bulkhead: {name} — HEALTHY")
            return True
        except Exception as e:
            info = SubsystemInfo(
                name=name,
                status=SubsystemStatus.FAILED,
                critical=critical,
                error=str(e),
                failed_at=time.time(),
            )
            with self._lock:
                self._subsystems[name] = info
            logger.error(f"Bulkhead: {name} — FAILED: {e}")
            return False

    def mark_degraded(self, name: str, reason: str = "") -> None:
        """將子系統標記為降級.

        Args:
            name: 子系統名稱
            reason: 降級原因
        """
        with self._lock:
            if name in self._subsystems:
                self._subsystems[name].status = SubsystemStatus.DEGRADED
                self._subsystems[name].error = reason
                logger.warning(f"Bulkhead: {name} → DEGRADED: {reason}")

    def mark_healthy(self, name: str) -> None:
        """將子系統恢復為健康.

        Args:
            name: 子系統名稱
        """
        with self._lock:
            if name in self._subsystems:
                self._subsystems[name].status = SubsystemStatus.HEALTHY
                self._subsystems[name].error = None
                logger.info(f"Bulkhead: {name} → HEALTHY")

    @property
    def is_degraded(self) -> bool:
        """是否有任何子系統非健康."""
        with self._lock:
            return any(
                s.status != SubsystemStatus.HEALTHY
                for s in self._subsystems.values()
            )

    @property
    def overall_status(self) -> str:
        """整體健康狀態.

        Returns:
            "initializing" — 尚無子系統註冊
            "healthy" — 全部健康
            "degraded" — 部分失敗
            "critical" — 全部失敗
        """
        with self._lock:
            if not self._subsystems:
                return "initializing"
            failed = sum(
                1
                for s in self._subsystems.values()
                if s.status == SubsystemStatus.FAILED
            )
            if failed == len(self._subsystems):
                return "critical"
            if failed > 0:
                return "degraded"
            degraded = sum(
                1
                for s in self._subsystems.values()
                if s.status == SubsystemStatus.DEGRADED
            )
            if degraded > 0:
                return "degraded"
            return "healthy"

    def get_status(self) -> Dict[str, str]:
        """取得所有子系統狀態.

        Returns:
            {"brain": "healthy", "telegram": "failed", ...}
        """
        with self._lock:
            return {
                name: info.status.value
                for name, info in self._subsystems.items()
            }

    def get_failed_subsystems(self) -> List[str]:
        """取得失敗的子系統名稱列表."""
        with self._lock:
            return [
                name
                for name, info in self._subsystems.items()
                if info.status == SubsystemStatus.FAILED
            ]

    def get_details(self) -> Dict[str, Dict[str, Any]]:
        """取得所有子系統的詳細資訊（供除錯用）.

        Returns:
            {
                "brain": {
                    "status": "healthy",
                    "critical": True,
                    "started_at": 1709712000.0,
                    "error": None,
                },
                ...
            }
        """
        with self._lock:
            return {
                name: {
                    "status": info.status.value,
                    "critical": info.critical,
                    "started_at": info.started_at,
                    "failed_at": info.failed_at,
                    "error": info.error,
                }
                for name, info in self._subsystems.items()
            }


# ═══════════════════════════════════════════
# BrainCircuitBreaker
# ═══════════════════════════════════════════


class CircuitState(Enum):
    """Circuit Breaker 狀態."""

    CLOSED = "closed"        # 正常運作
    OPEN = "open"            # 斷路（連續失敗過多）
    HALF_OPEN = "half_open"  # 試探恢復


class BrainCircuitBreaker:
    """Brain 專用 Circuit Breaker.

    連續失敗 >= failure_threshold 次 → OPEN（拒絕請求，返回降級回覆）
    OPEN 狀態持續 cooldown_seconds 後 → HALF_OPEN（放一個請求試探）
    HALF_OPEN 成功 → CLOSED；失敗 → 回到 OPEN

    使用方式::

        cb = BrainCircuitBreaker(failure_threshold=3, cooldown_seconds=60)

        if cb.is_open:
            # 返回降級回覆
            return cb.fallback_message
        try:
            result = await brain.process(...)
            cb.record_success()
            return result
        except Exception as e:
            cb.record_failure(e)
            raise
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        fallback_message: str = (
            "抱歉，目前處理能力受限，已記下你的訊息，恢復後會盡快回覆。"
        ),
    ) -> None:
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._notify_callback: Optional[Callable] = None
        self.fallback_message = fallback_message

    def set_notify_callback(self, callback: Callable) -> None:
        """設定斷路通知回調（用於 DM 老闆）."""
        self._notify_callback = callback

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        """是否應該拒絕請求（OPEN 且未到 cooldown）."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return False
            if self._state == CircuitState.OPEN:
                # 檢查 cooldown 是否已過
                if self._opened_at and (
                    time.time() - self._opened_at >= self._cooldown_seconds
                ):
                    # 轉入 HALF_OPEN，允許一個請求試探
                    self._state = CircuitState.HALF_OPEN
                    logger.info("BrainCircuitBreaker: OPEN -> HALF_OPEN (cooldown elapsed)")
                    return False
                return True
            # HALF_OPEN: 允許請求通過
            return False

    def record_success(self) -> None:
        """記錄成功 — 重置失敗計數，HALF_OPEN 恢復為 CLOSED."""
        _pending_notify = None
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("BrainCircuitBreaker: HALF_OPEN -> CLOSED (success)")
                self._state = CircuitState.CLOSED
                _pending_notify = ("recovered", "")
            self._failure_count = 0
        if _pending_notify:
            self._fire_notify(*_pending_notify)

    def record_failure(self, error: Optional[Exception] = None) -> None:
        """記錄失敗 — 累計計數，達閾值時斷路."""
        _pending_notify = None
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            err_msg = str(error)[:200] if error else "unknown"

            if self._state == CircuitState.HALF_OPEN:
                # HALF_OPEN 試探失敗 → 回到 OPEN
                self._state = CircuitState.OPEN
                self._opened_at = time.time()
                logger.warning(
                    f"BrainCircuitBreaker: HALF_OPEN -> OPEN (probe failed: {err_msg})"
                )
                _pending_notify = ("reopened", err_msg)
            elif self._failure_count >= self._failure_threshold:
                if self._state != CircuitState.OPEN:
                    self._state = CircuitState.OPEN
                    self._opened_at = time.time()
                    logger.error(
                        f"BrainCircuitBreaker: CLOSED -> OPEN "
                        f"({self._failure_count} consecutive failures, last: {err_msg})"
                    )
                    _pending_notify = ("opened", err_msg)
        if _pending_notify:
            self._fire_notify(*_pending_notify)

    def _fire_notify(self, event: str, detail: str = "") -> None:
        """觸發通知回調（在 lock 外呼叫，避免持鎖期間執行外部回調）."""
        if self._notify_callback:
            try:
                self._notify_callback(event, detail)
            except Exception as e:
                logger.debug(f"CircuitBreaker notify callback error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """取得 Circuit Breaker 狀態快照."""
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self._failure_threshold,
                "cooldown_seconds": self._cooldown_seconds,
                "last_failure_time": self._last_failure_time,
                "opened_at": self._opened_at,
            }


# ── Singleton ──

_brain_circuit_breaker: Optional[BrainCircuitBreaker] = None
_cb_lock = threading.Lock()


def get_brain_circuit_breaker() -> BrainCircuitBreaker:
    """取得 Brain Circuit Breaker 單例."""
    global _brain_circuit_breaker
    with _cb_lock:
        if _brain_circuit_breaker is None:
            _brain_circuit_breaker = BrainCircuitBreaker()
        return _brain_circuit_breaker
