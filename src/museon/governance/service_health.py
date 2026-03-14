"""Service Health Monitor — Docker 服務存活監控 + 自動恢復

監控對象：
- Qdrant (向量資料庫) — port 6333
- SearXNG (搜尋引擎) — port 8888
- Firecrawl (網頁爬蟲) — port 3002

恢復策略：
- 偵測到不健康 → 記錄 + 嘗試 docker restart
- Cooldown 機制 — 避免頻繁重啟
- 每小時重啟上限 — 防止無限重啟風暴
- 啟動寬限期 — 新啟動的服務給予額外時間

參考 Openclaw channel-health-monitor.ts 的設計模式。

中焦（服務級）的核心守衛。
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── 服務定義 ───


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"  # 回應慢但可用
    UNKNOWN = "unknown"


@dataclass
class ServiceConfig:
    """服務監控配置"""

    name: str  # 服務名稱
    container_name: str  # Docker container 名稱
    health_url: str  # 健康檢查 URL
    port: int  # 監聽端口
    required: bool = True  # 是否為必要服務
    timeout_s: float = 5.0  # 健康檢查超時
    degraded_threshold_ms: float = 2000  # 回應超過此值視為 degraded


@dataclass
class ServiceState:
    """服務運行狀態"""

    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_check_at: float = 0.0
    last_healthy_at: float = 0.0
    last_response_ms: float = 0.0
    consecutive_failures: int = 0
    total_restarts: int = 0
    last_restart_at: float = 0.0
    restart_timestamps: list = field(default_factory=list)
    last_error: Optional[str] = None


# ─── 預設服務配置 ───

DEFAULT_SERVICES = [
    ServiceConfig(
        name="qdrant",
        container_name="qdrant",
        health_url="http://127.0.0.1:6333/healthz",
        port=6333,
        required=True,
        timeout_s=5.0,
        degraded_threshold_ms=500,
    ),
    ServiceConfig(
        name="searxng",
        container_name="searxng",
        health_url="http://127.0.0.1:8888/healthz",
        port=8888,
        required=True,
        timeout_s=5.0,
        degraded_threshold_ms=3000,
    ),
    # firecrawl 已移除 — container 不存在，不必要的健康檢查
    # 每 30 秒嘗試 docker restart 一個不存在的 container 會污染日誌
    # 未來實際部署 firecrawl 時再加回
]


# ─── Service Health Monitor ───


class ServiceHealthMonitor:
    """Docker 服務健康監控器。

    運作模式：
    1. 定期（每 30s）檢查所有註冊服務的健康狀態
    2. 偵測到不健康 → 等待 cooldown → 嘗試 docker restart
    3. 超過每小時重啟上限 → 停止重啟，僅發出警報
    4. 收集運行統計供上焦（系統級）分析

    使用方式：
        monitor = ServiceHealthMonitor()
        await monitor.start()
        # ...
        status = monitor.get_all_status()
        await monitor.stop()
    """

    def __init__(
        self,
        services: Optional[List[ServiceConfig]] = None,
        check_interval_s: float = 30.0,
        startup_grace_s: float = 60.0,
        cooldown_s: float = 120.0,  # 2 分鐘冷卻
        max_restarts_per_hour: int = 3,
        on_status_change: Optional[Callable] = None,
    ):
        self.services = {
            svc.name: svc for svc in (services or DEFAULT_SERVICES)
        }
        self.check_interval_s = check_interval_s
        self.startup_grace_s = startup_grace_s
        self.cooldown_s = cooldown_s
        self.max_restarts_per_hour = max_restarts_per_hour
        self.on_status_change = on_status_change

        self._states: Dict[str, ServiceState] = {
            name: ServiceState() for name in self.services
        }
        self._running = False
        self._started_at = 0.0
        self._check_task: Optional[asyncio.Task] = None
        self._check_in_flight = False

    async def start(self) -> None:
        """啟動健康監控。"""
        if self._running:
            return

        self._running = True
        self._started_at = time.time()

        logger.info(
            f"ServiceHealthMonitor starting: "
            f"{len(self.services)} services, "
            f"interval={self.check_interval_s}s, "
            f"grace={self.startup_grace_s}s"
        )

        # 立即做一次初始檢查
        await self._run_check()

        # 啟動定期檢查
        self._check_task = asyncio.create_task(
            self._check_loop(), name="service-health-monitor"
        )

    async def stop(self) -> None:
        """停止健康監控。"""
        self._running = False
        if self._check_task and not self._check_task.done():
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError as e:
                logger.debug(f"[SERVICE_HEALTH] operation failed (degraded): {e}")
        logger.info("ServiceHealthMonitor stopped")

    async def check_service(self, name: str) -> ServiceStatus:
        """手動檢查單一服務。"""
        if name not in self.services:
            return ServiceStatus.UNKNOWN
        return await self._probe_service(self.services[name])

    def get_service_status(self, name: str) -> dict:
        """取得單一服務狀態。"""
        state = self._states.get(name)
        if not state:
            return {"status": "unknown", "error": "service not registered"}

        config = self.services.get(name)
        return {
            "name": name,
            "status": state.status.value,
            "required": config.required if config else False,
            "last_check_at": state.last_check_at,
            "last_healthy_at": state.last_healthy_at,
            "last_response_ms": round(state.last_response_ms, 1),
            "consecutive_failures": state.consecutive_failures,
            "total_restarts": state.total_restarts,
            "last_error": state.last_error,
        }

    def get_all_status(self) -> dict:
        """取得所有服務狀態（供 /health 端點使用）。"""
        services = {}
        all_healthy = True
        any_required_down = False

        for name in self.services:
            status = self.get_service_status(name)
            services[name] = status

            if status["status"] != "healthy":
                all_healthy = False
                if status.get("required"):
                    any_required_down = True

        return {
            "overall": (
                "critical"
                if any_required_down
                else "degraded" if not all_healthy else "healthy"
            ),
            "services": services,
            "monitor_uptime_s": round(time.time() - self._started_at, 1)
            if self._started_at
            else 0,
        }

    # ─── Internal ───

    async def _check_loop(self) -> None:
        """定期檢查迴圈。"""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval_s)
                if self._running:
                    await self._run_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ServiceHealthMonitor check error: {e}")

    async def _run_check(self) -> None:
        """執行一次全量健康檢查。"""
        now = time.time()

        # 啟動寬限期
        if now - self._started_at < self.startup_grace_s:
            return

        # 防止並發檢查
        if self._check_in_flight:
            return
        self._check_in_flight = True

        try:
            # 並行檢查所有服務
            tasks = [
                self._check_and_heal(name, config)
                for name, config in self.services.items()
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._check_in_flight = False

    async def _check_and_heal(
        self, name: str, config: ServiceConfig
    ) -> None:
        """檢查單一服務，如果不健康則嘗試恢復。"""
        state = self._states[name]
        old_status = state.status

        # 探測健康狀態
        new_status = await self._probe_service(config)
        state.status = new_status
        state.last_check_at = time.time()

        if new_status == ServiceStatus.HEALTHY:
            state.last_healthy_at = time.time()
            state.consecutive_failures = 0
            state.last_error = None

            # 狀態恢復 → 通知
            if old_status != ServiceStatus.HEALTHY and old_status != ServiceStatus.UNKNOWN:
                logger.info(f"[{name}] recovered → healthy")
                if self.on_status_change:
                    self.on_status_change(name, old_status, new_status)
            return

        # 不健康
        state.consecutive_failures += 1

        if new_status != old_status:
            logger.warning(
                f"[{name}] {old_status.value} → {new_status.value} "
                f"(failures: {state.consecutive_failures})"
            )
            if self.on_status_change:
                self.on_status_change(name, old_status, new_status)

        # 嘗試恢復（僅 UNHEALTHY，DEGRADED 不自動重啟）
        if new_status == ServiceStatus.UNHEALTHY:
            await self._try_restart(name, config, state)

    async def _probe_service(self, config: ServiceConfig) -> ServiceStatus:
        """探測服務健康狀態。

        望（看指標）+ 切（主動探測）
        使用標準庫 urllib 避免額外依賴，透過 asyncio.to_thread 非阻塞。
        """
        import urllib.request
        import urllib.error

        state = self._states[config.name]

        def _sync_probe():
            start = time.monotonic()
            req = urllib.request.Request(config.health_url, method="GET")
            resp = urllib.request.urlopen(req, timeout=config.timeout_s)
            elapsed_ms = (time.monotonic() - start) * 1000
            return resp.status, elapsed_ms

        try:
            status_code, elapsed_ms = await asyncio.to_thread(_sync_probe)
            state.last_response_ms = elapsed_ms

            if status_code == 200:
                if elapsed_ms > config.degraded_threshold_ms:
                    return ServiceStatus.DEGRADED
                return ServiceStatus.HEALTHY
            else:
                state.last_error = f"HTTP {status_code}"
                return ServiceStatus.UNHEALTHY

        except urllib.error.URLError as e:
            state.last_error = f"connection error: {e.reason}"
            return ServiceStatus.UNHEALTHY
        except TimeoutError:
            state.last_error = f"timeout after {config.timeout_s}s"
            return ServiceStatus.UNHEALTHY
        except Exception as e:
            state.last_error = str(e)
            return ServiceStatus.UNHEALTHY

    async def _try_restart(
        self, name: str, config: ServiceConfig, state: ServiceState
    ) -> None:
        """嘗試 docker restart 恢復服務。"""
        now = time.time()

        # Cooldown 檢查
        if now - state.last_restart_at < self.cooldown_s:
            return

        # 每小時重啟限制（滑動窗口）
        one_hour_ago = now - 3600
        state.restart_timestamps = [
            t for t in state.restart_timestamps if t > one_hour_ago
        ]
        if len(state.restart_timestamps) >= self.max_restarts_per_hour:
            logger.error(
                f"[{name}] hit {self.max_restarts_per_hour} restarts/hour "
                f"limit — manual intervention needed"
            )
            return

        logger.info(f"[{name}] attempting docker restart...")

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["docker", "restart", config.container_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                state.total_restarts += 1
                state.last_restart_at = now
                state.restart_timestamps.append(now)
                logger.info(f"[{name}] docker restart succeeded")
            else:
                logger.error(
                    f"[{name}] docker restart failed: {result.stderr.strip()}"
                )

        except subprocess.TimeoutExpired:
            logger.error(f"[{name}] docker restart timed out")
        except FileNotFoundError:
            logger.error(
                f"[{name}] docker command not found — "
                f"cannot auto-restart services"
            )
        except Exception as e:
            logger.error(f"[{name}] docker restart error: {e}")
