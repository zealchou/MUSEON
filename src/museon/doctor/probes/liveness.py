"""
L0 Liveness Probe — 存活探測（每 60 秒）

K8s livenessProbe 模式：死了就重啟。
純 CPU，零 Token。

v2.0 改動：
- 查 /health/live（純 event loop 回應），不再查 /health（含 Brain/Telegram 深度檢查）
- 連續 3 次 HTTP 無回應才觸發重啟（防止暫時性 timeout 誤判）
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import aiohttp

logger = logging.getLogger(__name__)

# 連續失敗計數器（跨呼叫，模組級別）
_consecutive_failures: int = 0
FAILURE_THRESHOLD = 3  # 連續 N 次失敗才回傳 alive=False


class LivenessProbe:
    """L0: Gateway 活著嗎？"""

    # 改查 /health/live（純 event loop 回應），不查 /health（含 Brain 深度檢查）
    GATEWAY_URL = "http://127.0.0.1:8765/health/live"
    TIMEOUT = 5

    async def check(self) -> dict:
        """返回 {"alive": bool, "detail": str}

        連續 FAILURE_THRESHOLD 次 HTTP 無回應才宣告死亡，避免暫時性 timeout 誤判。
        """
        global _consecutive_failures

        http_ok = await self._check_http()

        if http_ok:
            # 恢復正常 → 重置計數器
            if _consecutive_failures > 0:
                logger.info("[LivenessProbe] HTTP 已恢復，重置失敗計數 (%d→0)", _consecutive_failures)
            _consecutive_failures = 0
            return {"alive": True, "detail": "OK"}

        # HTTP 失敗：增加計數
        _consecutive_failures += 1
        logger.warning(
            "[LivenessProbe] HTTP 無回應（%d/%d）",
            _consecutive_failures, FAILURE_THRESHOLD,
        )

        if _consecutive_failures < FAILURE_THRESHOLD:
            # 尚未達到閾值 → 暫時容忍，回傳 alive=True 不觸發重啟
            return {
                "alive": True,
                "detail": f"HTTP 暫時無回應（{_consecutive_failures}/{FAILURE_THRESHOLD}，等待確認）",
            }

        # 已達到閾值 → 確認是否進程真的死亡
        proc_ok = self._check_process()
        if not proc_ok:
            return {"alive": False, "detail": f"Gateway 進程不存在（連續 {_consecutive_failures} 次失敗）"}
        return {
            "alive": False,
            "detail": f"Gateway 進程存在但 HTTP 連續 {_consecutive_failures} 次無回應",
        }

    async def _check_http(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.GATEWAY_URL,
                    timeout=aiohttp.ClientTimeout(total=self.TIMEOUT),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def _check_process(self) -> bool:
        """確認 Gateway 進程（uvicorn worker 或 gunicorn master）是否存在。"""
        try:
            # 查 gunicorn master（新架構）
            result = subprocess.run(
                ["pgrep", "-f", "gunicorn.*museon"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                return True
            # 查 uvicorn worker（gunicorn 子進程，或舊架構直接啟動）
            result = subprocess.run(
                ["pgrep", "-f", "museon.gateway.server"],
                capture_output=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False
