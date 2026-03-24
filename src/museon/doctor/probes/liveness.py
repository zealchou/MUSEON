"""
L0 Liveness Probe — 存活探測（每 60 秒）

K8s livenessProbe 模式：死了就重啟。
純 CPU，零 Token。
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)


class LivenessProbe:
    """L0: Gateway 活著嗎？"""

    GATEWAY_URL = "http://127.0.0.1:8765/health"
    TIMEOUT = 5

    async def check(self) -> dict:
        """返回 {"alive": bool, "detail": str}"""
        # Check 1: HTTP health
        http_ok = await self._check_http()
        if not http_ok:
            # Check 2: Process alive (fallback)
            proc_ok = self._check_process()
            if not proc_ok:
                return {"alive": False, "detail": "Gateway process not found"}
            return {"alive": False, "detail": "Gateway process alive but HTTP unresponsive"}
        return {"alive": True, "detail": "OK"}

    async def _check_http(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.GATEWAY_URL, timeout=aiohttp.ClientTimeout(total=self.TIMEOUT)) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def _check_process(self) -> bool:
        try:
            result = subprocess.run(
                ["pgrep", "-f", "museon.gateway.server"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
