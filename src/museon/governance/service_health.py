"""Service Health Monitor — 服務存活監控 + 自動恢復

監控對象：
- Qdrant (向量資料庫) — port 6333, 本地進程模式
- SearXNG (搜尋引擎) — port 8888, Docker 容器模式

恢復策略：
- Docker 模式：嘗試 docker restart
- 本地進程模式：透過 port 找 PID → kill → 等待進程管理器重啟
- Cooldown 機制 — 避免頻繁重啟
- 每小時重啟上限 — 防止無限重啟風暴
- 啟動寬限期 — 新啟動的服務給予額外時間

參考 Openclaw channel-health-monitor.ts 的設計模式。

中焦（服務級）的核心守衛。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 指數退避序列（秒）：30s → 1m → 2m → 5m → 15m 封頂
_RETRY_BACKOFF_SECONDS = [30, 60, 120, 300, 900]


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
    container_name: str  # Docker container 名稱（docker 模式用）
    health_url: str  # 健康檢查 URL
    port: int  # 監聽端口
    required: bool = True  # 是否為必要服務
    timeout_s: float = 5.0  # 健康檢查超時
    degraded_threshold_ms: float = 2000  # 回應超過此值視為 degraded
    restart_strategy: str = "docker"  # "docker" | "process"


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
    next_check_at: float = 0.0  # 指數退避：下次允許探測的時間戳


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
        restart_strategy="process",  # Qdrant 以本地進程運行，非 Docker
    ),
    # searxng 已移除 — container 不存在，不必要的健康檢查
    # 每 30 秒嘗試 docker restart 一個不存在的 container 會污染日誌
    # 未來實際部署 searxng 時再加回
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

        # P2 加固：啟動時偵測外部命令可用性，缺失時降級（不重複報錯）
        # launchd daemon PATH 可能不含 /usr/local/bin，加 fallback
        self._has_lsof = shutil.which("lsof") is not None
        _docker_path = (
            shutil.which("docker")
            or ("/usr/local/bin/docker" if os.path.isfile("/usr/local/bin/docker") else None)
            or ("/opt/homebrew/bin/docker" if os.path.isfile("/opt/homebrew/bin/docker") else None)
        )
        self._has_docker = _docker_path is not None
        self._docker_bin = _docker_path or "docker"
        if not self._has_lsof:
            logger.warning("ServiceHealthMonitor: lsof 不可用，process restart 將被跳過")
        if not self._has_docker:
            logger.warning("ServiceHealthMonitor: docker 不可用，docker restart 將被跳過")

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
            "next_check_at": state.next_check_at,
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
        """檢查單一服務，如果不健康則嘗試恢復。

        指數退避邏輯：
        - 服務失敗後，依 consecutive_failures 計算退避間隔
        - 退避期間跳過探測（節省資源，避免無意義輪詢）
        - 服務恢復後重置計數器與 next_check_at
        """
        state = self._states[name]
        now = time.time()

        # 指數退避：若尚未到下次允許探測時間，跳過本次
        if state.next_check_at > now:
            return

        old_status = state.status

        # 探測健康狀態
        new_status = await self._probe_service(config)
        state.status = new_status
        state.last_check_at = now

        if new_status == ServiceStatus.HEALTHY:
            state.last_healthy_at = now

            # 服務恢復 → 重置退避計數器
            if state.consecutive_failures > 0:
                logger.info(
                    f"[ServiceHealth] {name} 服務恢復，重置退避計數器 "
                    f"(was {state.consecutive_failures} failures)"
                )
            state.consecutive_failures = 0
            state.next_check_at = 0.0
            state.last_error = None

            # 狀態恢復 → 通知
            if old_status != ServiceStatus.HEALTHY and old_status != ServiceStatus.UNKNOWN:
                logger.info(f"[{name}] recovered → healthy")
                if self.on_status_change:
                    self.on_status_change(name, old_status, new_status)
            return

        # 不健康：遞增失敗計數，計算退避間隔
        state.consecutive_failures += 1
        n = state.consecutive_failures
        backoff = _RETRY_BACKOFF_SECONDS[min(n - 1, len(_RETRY_BACKOFF_SECONDS) - 1)]
        state.next_check_at = now + backoff

        logger.info(
            f"[ServiceHealth] {name} 重試退避: {backoff}s (attempt #{n})"
        )

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
            # urllib 把 socket.timeout 包裝成 URLError(reason=socket.timeout(...))
            # 必須在此分辨 timeout vs 其他連線錯誤
            reason = getattr(e, "reason", None)
            if isinstance(reason, (TimeoutError, OSError)) and "timed out" in str(reason):
                state.last_error = f"timeout after {config.timeout_s}s"
            else:
                state.last_error = f"connection error: {e.reason}"
            return ServiceStatus.UNHEALTHY
        except (TimeoutError, asyncio.TimeoutError):
            # asyncio.to_thread 層級的 timeout（罕見但可能）
            state.last_error = f"timeout after {config.timeout_s}s"
            return ServiceStatus.UNHEALTHY
        except Exception as e:
            state.last_error = str(e)
            return ServiceStatus.UNHEALTHY

    async def _try_restart(
        self, name: str, config: ServiceConfig, state: ServiceState
    ) -> None:
        """嘗試恢復服務（根據 restart_strategy 選擇策略）。"""
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

        if config.restart_strategy == "process":
            await self._try_restart_process(name, config, state)
        else:
            await self._try_restart_docker(name, config, state)

    async def _try_restart_process(
        self, name: str, config: ServiceConfig, state: ServiceState
    ) -> None:
        """透過 port 找 PID → kill → 等待進程管理器（launchd 等）重啟。"""
        if not self._has_lsof:
            return  # 已在啟動時警告過，不重複報錯

        now = time.time()

        try:
            # 找佔用 port 的 PID
            result = await asyncio.to_thread(
                subprocess.run,
                ["lsof", "-ti", f":{config.port}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            pids = [
                p.strip() for p in result.stdout.strip().split("\n") if p.strip()
            ]

            if not pids:
                logger.warning(
                    f"[{name}] no process found on port {config.port} — "
                    f"service may need manual start"
                )
                state.last_restart_at = now
                state.restart_timestamps.append(now)
                return

            logger.info(
                f"[{name}] attempting process restart "
                f"(PIDs: {', '.join(pids)})..."
            )

            # SIGTERM 優雅關閉
            for pid in pids:
                await asyncio.to_thread(
                    subprocess.run,
                    ["kill", "-TERM", pid],
                    capture_output=True,
                    timeout=5,
                )

            # 等待 5 秒讓進程關閉
            await asyncio.sleep(5)

            # 檢查是否已關閉
            result2 = await asyncio.to_thread(
                subprocess.run,
                ["lsof", "-ti", f":{config.port}"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            remaining = [
                p.strip()
                for p in result2.stdout.strip().split("\n")
                if p.strip()
            ]

            if remaining:
                # 強制終止
                for pid in remaining:
                    await asyncio.to_thread(
                        subprocess.run,
                        ["kill", "-9", pid],
                        capture_output=True,
                        timeout=5,
                    )
                logger.warning(
                    f"[{name}] sent SIGKILL to remaining PIDs: "
                    f"{', '.join(remaining)}"
                )

            state.total_restarts += 1
            state.last_restart_at = now
            state.restart_timestamps.append(now)
            logger.info(
                f"[{name}] process killed — waiting for process manager "
                f"to restart on port {config.port}"
            )

        except subprocess.TimeoutExpired:
            logger.error(f"[{name}] process restart timed out")
        except FileNotFoundError:
            logger.error(f"[{name}] lsof command not found")
        except Exception as e:
            logger.error(f"[{name}] process restart error: {e}")

    async def _ensure_docker_daemon(self) -> bool:
        """確認 Docker daemon 在跑；若未啟動則嘗試啟動 Docker Desktop。

        Returns:
            True = daemon 可用，False = 無法啟動
        """
        # 常見 socket 路徑
        _sockets = [
            os.path.expanduser("~/.docker/run/docker.sock"),
            "/var/run/docker.sock",
        ]
        if any(os.path.exists(s) for s in _sockets):
            return True

        # Docker daemon 不在跑 — 嘗試啟動 Docker Desktop（macOS）
        _now = time.time()
        _last = getattr(self, "_last_docker_desktop_launch", 0.0)
        if _now - _last < 300:  # 5 分鐘冷卻，避免瘋狂重啟
            return False

        logger.warning(
            "[DockerDaemon] docker.sock not found — "
            "attempting to launch Docker Desktop..."
        )
        self._last_docker_desktop_launch = _now

        try:
            await asyncio.to_thread(
                subprocess.run,
                ["open", "-a", "Docker"],
                capture_output=True,
                timeout=10,
            )
            # 等待 daemon 啟動（最多 60 秒）
            for _i in range(12):
                await asyncio.sleep(5)
                if any(os.path.exists(s) for s in _sockets):
                    logger.info(
                        "[DockerDaemon] Docker Desktop started successfully "
                        f"(waited {(_i + 1) * 5}s)"
                    )
                    return True
            logger.error(
                "[DockerDaemon] Docker Desktop launched but daemon "
                "not ready after 60s"
            )
            return False
        except Exception as e:
            logger.error(f"[DockerDaemon] failed to launch Docker Desktop: {e}")
            return False

    async def _try_restart_docker(
        self, name: str, config: ServiceConfig, state: ServiceState
    ) -> None:
        """Docker 容器重啟。"""
        if not self._has_docker:
            return  # 已在啟動時警告過，不重複報錯

        # ── 前置：確認 Docker daemon 在跑 ──
        if not await self._ensure_docker_daemon():
            return  # daemon 不可用，不嘗試 docker restart

        now = time.time()

        logger.info(f"[{name}] attempting docker restart...")

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [self._docker_bin, "restart", config.container_name],
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
