"""
L1 Readiness Probe — 就緒探測（每 5 分鐘）

K8s readinessProbe 模式：沒 ready 就降級，不重啟。
純 CPU（HTTP 呼叫），零 Token。
"""

from __future__ import annotations

import logging
import subprocess

import aiohttp

logger = logging.getLogger(__name__)


class ReadinessProbe:
    """L1: Brain 能正常處理嗎？DB 都連得上嗎？"""

    GATEWAY_URL = "http://127.0.0.1:8765"
    TIMEOUT = 10

    async def check(self) -> dict:
        """返回 {"ready": bool, "checks": {...}, "detail": str}"""
        checks = {}

        # Check 1: Brain health
        checks["brain"] = await self._check_brain()

        # Check 2: Qdrant
        checks["qdrant"] = await self._check_service("http://127.0.0.1:6333/healthz", "Qdrant")

        # Check 3: SearXNG
        checks["searxng"] = await self._check_service("http://127.0.0.1:8888/healthz", "SearXNG")

        # Check 4: SQLite DBs (via file existence + non-zero size)
        checks["pulse_db"] = self._check_db("/Users/ZEALCHOU/MUSEON/data/pulse/pulse.db")
        checks["crystal_db"] = self._check_db("/Users/ZEALCHOU/MUSEON/data/lattice/crystal.db")

        # Check 5: Telegram bot reachable
        checks["telegram"] = await self._check_telegram_bot()

        failed = [k for k, v in checks.items() if not v]
        ready = len(failed) == 0

        return {
            "ready": ready,
            "checks": checks,
            "failed": failed,
            "detail": "OK" if ready else f"Failed: {', '.join(failed)}",
        }

    async def _check_brain(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.GATEWAY_URL}/health",
                    timeout=aiohttp.ClientTimeout(total=self.TIMEOUT),
                ) as resp:
                    if resp.status != 200:
                        return False
                    data = await resp.json()
                    return data.get("brain") != "not_initialized"
        except Exception:
            return False

    async def _check_service(self, url: str, name: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status in (200, 204)
        except Exception:
            return False

    async def _check_telegram_bot(self) -> bool:
        """檢查 Telegram adapter 狀態（透過 Gateway HTTP endpoint）"""
        try:
            import aiohttp
            url = "http://127.0.0.1:8765/api/telegram/status"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("running", False)
            return False
        except Exception:
            return False

    def _check_db(self, path: str) -> bool:
        from pathlib import Path
        p = Path(path)
        return p.exists() and p.stat().st_size > 0
