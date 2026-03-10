"""Dify REST API Scheduler -- MUSEON Phase 3 EXT-07.

排程管理 Dify 工作流：
- 列出可用工作流
- 手動/排程觸發工作流
- 追蹤執行狀態
- cron 排程（存於 _system/dify_schedules.json）

設計原則：
- MUSEON 是大腦，Dify 是手腳
- 所有外部呼叫 try/except + graceful degradation
- EventBus 發布 DIFY_WORKFLOW_TRIGGERED / DIFY_WORKFLOW_COMPLETED
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════
# Constants
# ═══════════════════════════════════════

SCHEDULE_FILE = "_system/dify_schedules.json"

# EventBus event names (import guard)
DIFY_WORKFLOW_TRIGGERED = "DIFY_WORKFLOW_TRIGGERED"
DIFY_WORKFLOW_COMPLETED = "DIFY_WORKFLOW_COMPLETED"

# ═══════════════════════════════════════
# Lazy import aiohttp
# ═══════════════════════════════════════

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    _HAS_AIOHTTP = False


class DifyScheduler:
    """Dify 工作流排程器.

    管理工作流的排程觸發與狀態追蹤。

    Args:
        dify_url: Dify API 基底 URL
        api_key: Dify API Key（也可透過 DIFY_API_KEY 環境變數設定）
        event_bus: EventBus 實例，用於發布工作流事件
    """

    def __init__(
        self,
        dify_url: str = "http://127.0.0.1:3000",
        api_key: Optional[str] = None,
        event_bus: Any = None,
    ) -> None:
        self._dify_url = dify_url.rstrip("/")
        self._api_key = api_key or os.getenv("DIFY_API_KEY", "")
        self._event_bus = event_bus

        # workflow_id -> {cron_expression, last_run, next_run}
        self._schedules: Dict[str, Dict] = {}

        # 載入既有排程
        self._load_schedules()

    # ─── Headers ─────────────────────────

    def _headers(self) -> Dict[str, str]:
        """建構 API 請求標頭."""
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    # ─── API Methods ─────────────────────

    async def list_workflows(self) -> List[Dict]:
        """列出 Dify 上可用的工作流.

        GET /v1/workflows

        Returns:
            工作流清單，失敗時回傳空列表。
        """
        if not _HAS_AIOHTTP:
            logger.warning("[DifyScheduler] aiohttp 未安裝，無法呼叫 Dify API")
            return []

        url = f"{self._dify_url}/v1/workflows"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("data", data.get("workflows", []))
                    logger.warning(
                        f"[DifyScheduler] list_workflows HTTP {resp.status}"
                    )
                    return []
        except Exception as e:
            logger.error(f"[DifyScheduler] list_workflows failed: {e}")
            return []

    async def trigger_workflow(
        self,
        workflow_id: str,
        inputs: Optional[Dict] = None,
    ) -> Dict:
        """觸發 Dify 工作流.

        POST /v1/workflows/run

        Args:
            workflow_id: 工作流 ID 或其 API Key
            inputs: 工作流輸入參數

        Returns:
            API 回應 dict，失敗時含 error 欄位。
        """
        if not _HAS_AIOHTTP:
            return {"error": "aiohttp 未安裝"}

        url = f"{self._dify_url}/v1/workflows/run"
        payload = {
            "inputs": inputs or {},
            "response_mode": "blocking",
            "user": "museon-scheduler",
        }
        # 若 workflow_id 看起來像 API Key，用它作 Authorization
        headers = dict(self._headers())
        if workflow_id.startswith("app-"):
            headers["Authorization"] = f"Bearer {workflow_id}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    result = await resp.json()

            # 發布事件
            try:
                if self._event_bus:
                    self._event_bus.publish(DIFY_WORKFLOW_TRIGGERED, {
                        "workflow_id": workflow_id,
                        "inputs": inputs or {},
                        "timestamp": datetime.now(TZ8).isoformat(),
                    })
            except Exception as e:
                logger.debug(f"[DifyScheduler] event_bus publish error: {e}")

            # 若同步完成，也發布 COMPLETED
            status = result.get("data", {}).get("status", "")
            if status in ("succeeded", "completed"):
                try:
                    if self._event_bus:
                        self._event_bus.publish(DIFY_WORKFLOW_COMPLETED, {
                            "workflow_id": workflow_id,
                            "status": status,
                            "result": result,
                            "timestamp": datetime.now(TZ8).isoformat(),
                        })
                except Exception as e:
                    logger.debug(
                        f"[DifyScheduler] event_bus publish error: {e}"
                    )

            logger.info(
                f"[DifyScheduler] trigger_workflow {workflow_id}: "
                f"status={status or 'unknown'}"
            )
            return result

        except Exception as e:
            logger.error(f"[DifyScheduler] trigger_workflow failed: {e}")
            return {"error": str(e)}

    async def get_workflow_status(self, run_id: str) -> Dict:
        """查詢工作流執行狀態.

        GET /v1/workflows/runs/{run_id}

        Args:
            run_id: 工作流執行 ID

        Returns:
            執行狀態 dict，失敗時含 error 欄位。
        """
        if not _HAS_AIOHTTP:
            return {"error": "aiohttp 未安裝"}

        url = f"{self._dify_url}/v1/workflows/runs/{run_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=self._headers(),
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"[DifyScheduler] get_workflow_status failed: {e}")
            return {"error": str(e)}

    # ─── Schedule Management ─────────────

    def add_schedule(self, workflow_id: str, cron_expression: str) -> None:
        """新增排程.

        Args:
            workflow_id: 工作流 ID
            cron_expression: cron 表達式（如 "0 9 * * *" = 每天 09:00）
        """
        now = datetime.now(TZ8)
        self._schedules[workflow_id] = {
            "cron_expression": cron_expression,
            "last_run": None,
            "next_run": self._compute_next_run(cron_expression, now),
            "created_at": now.isoformat(),
        }
        self._save_schedules()
        logger.info(
            f"[DifyScheduler] schedule added: {workflow_id} "
            f"cron={cron_expression}"
        )

    def remove_schedule(self, workflow_id: str) -> bool:
        """移除排程.

        Returns:
            True 表示成功移除，False 表示不存在。
        """
        if workflow_id in self._schedules:
            del self._schedules[workflow_id]
            self._save_schedules()
            logger.info(f"[DifyScheduler] schedule removed: {workflow_id}")
            return True
        return False

    async def sync_schedules(self) -> Dict:
        """檢查並觸發到期的排程工作流.

        Returns:
            {triggered: [...], errors: [...], checked_at: ...}
        """
        now = datetime.now(TZ8)
        triggered: List[str] = []
        errors: List[str] = []

        for wf_id, sched in list(self._schedules.items()):
            next_run_str = sched.get("next_run")
            if not next_run_str:
                continue

            try:
                next_run = datetime.fromisoformat(next_run_str)
            except (ValueError, TypeError):
                continue

            if now >= next_run:
                result = await self.trigger_workflow(wf_id)
                if "error" in result:
                    errors.append(f"{wf_id}: {result['error']}")
                else:
                    triggered.append(wf_id)

                # 更新排程
                sched["last_run"] = now.isoformat()
                sched["next_run"] = self._compute_next_run(
                    sched["cron_expression"], now,
                )

        if triggered or errors:
            self._save_schedules()

        return {
            "triggered": triggered,
            "errors": errors,
            "checked_at": now.isoformat(),
        }

    # ─── Persistence ─────────────────────

    def _schedule_path(self) -> Path:
        """排程檔案路徑."""
        museon_home = os.getenv("MUSEON_HOME", str(Path.home() / "MUSEON"))
        return Path(museon_home) / SCHEDULE_FILE

    def _load_schedules(self) -> None:
        """從檔案載入排程."""
        path = self._schedule_path()
        if path.exists():
            try:
                self._schedules = json.loads(path.read_text(encoding="utf-8"))
                logger.info(
                    f"[DifyScheduler] loaded {len(self._schedules)} schedules"
                )
            except Exception as e:
                logger.error(f"[DifyScheduler] load schedules failed: {e}")
                self._schedules = {}

    def _save_schedules(self) -> None:
        """將排程寫入檔案."""
        path = self._schedule_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._schedules, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[DifyScheduler] save schedules failed: {e}")

    # ─── Cron Helpers ────────────────────

    @staticmethod
    def _compute_next_run(cron_expression: str, after: datetime) -> str:
        """簡易 cron 下次執行時間計算.

        支援格式：minute hour * * *（每日排程）
        完整 cron 解析可日後引入 croniter。

        Returns:
            ISO 格式的下次執行時間字串。
        """
        parts = cron_expression.strip().split()
        if len(parts) < 2:
            # 無法解析，預設一小時後
            return (after + timedelta(hours=1)).isoformat()

        try:
            minute = int(parts[0])
            hour = int(parts[1])
        except ValueError:
            return (after + timedelta(hours=1)).isoformat()

        candidate = after.replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )
        if candidate <= after:
            candidate += timedelta(days=1)

        return candidate.isoformat()
