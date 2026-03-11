"""Vital Signs Monitor — 生命徵象監測系統

三層偵測架構：
┌───────────────────────────────────────────────────────────┐
│ Layer 1: Preflight   │ 啟動時  │ LLM/Telegram/環境/Session │
│ Layer 2: Pulse       │ 定期    │ LLM 存活 + 資源水位 + 治理自檢 │
│ Layer 3: Sentinel    │ 即時    │ 離線觸發 → Telegram 告警     │
└───────────────────────────────────────────────────────────┘

設計原則：
  - 驗真不驗表（實際呼叫，不只看 process alive）
  - 沉默即異常（超時無產出 → 警報）
  - 治理治理者（meta-governance）
  - 會開口說話（critical → Telegram 推送）
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════
# Data Types
# ═══════════════════════════════════════

class CheckStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    duration_ms: float = 0.0
    details: Optional[Dict[str, Any]] = None


@dataclass
class VitalReport:
    """一次完整的生命徵象報告."""
    timestamp: float = field(default_factory=time.time)
    layer: str = ""  # "preflight" | "pulse" | "sentinel"
    checks: List[CheckResult] = field(default_factory=list)
    overall: CheckStatus = CheckStatus.PASS

    @property
    def failed_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == CheckStatus.FAIL]

    @property
    def warn_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if c.status == CheckStatus.WARN]

    def summary(self) -> str:
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.status == CheckStatus.PASS)
        failed = len(self.failed_checks)
        warned = len(self.warn_checks)
        return f"{self.layer}: {passed}/{total} pass, {warned} warn, {failed} fail"


# ═══════════════════════════════════════
# Vital Signs Monitor
# ═══════════════════════════════════════

class VitalSignsMonitor:
    """MUSEON 生命徵象監測器.

    整合到 Governor，提供三層偵測：
    - preflight: 啟動時驗證所有關鍵子系統
    - pulse: 定期探針（每 30 分鐘）
    - sentinel: 即時告警（離線模式觸發）
    """

    PULSE_INTERVAL_S = 1800  # 30 min
    LLM_PROBE_TIMEOUT_S = 30
    SESSION_MAX_CONTENT_LEN = 5000
    SESSION_REPEAT_THRESHOLD = 3
    RESOURCE_DISK_WARN_MB = 500
    RESOURCE_SESSION_WARN_COUNT = 200

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        bot_token: Optional[str] = None,
        trusted_user_id: Optional[int] = None,
    ):
        self._data_dir = data_dir or Path("data")
        self._bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._trusted_user_id = trusted_user_id
        if not self._trusted_user_id:
            ids_str = os.environ.get("TELEGRAM_TRUSTED_IDS", "")
            if ids_str:
                try:
                    self._trusted_user_id = int(ids_str.split(",")[0].strip())
                except ValueError:
                    pass

        # 外部注入的引用
        self._llm_adapter = None  # set by register_llm_adapter()
        self._governor_health_fn: Optional[Callable] = None
        self._brain_ref = None

        # Recovery callback（由 Brain 註冊，LLM 恢復時呼叫）
        self._recovery_callbacks: List[Callable] = []

        # 狀態
        self._running = False
        self._pulse_task: Optional[asyncio.Task] = None
        self._last_preflight: Optional[VitalReport] = None
        self._last_pulse: Optional[VitalReport] = None
        self._sentinel_count = 0
        self._last_sentinel_ts = 0.0
        self._consecutive_llm_failures = 0

    # ─── Dependency Injection ───

    def register_llm_adapter(self, adapter: Any) -> None:
        self._llm_adapter = adapter

    def register_governor_health(self, fn: Callable) -> None:
        self._governor_health_fn = fn

    def register_brain(self, brain: Any) -> None:
        self._brain_ref = brain

    def register_recovery_callback(self, callback: Callable) -> None:
        """註冊 LLM 恢復時的回呼函式（由 Brain 呼叫）."""
        self._recovery_callbacks.append(callback)

    # ─── Lifecycle ───

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._pulse_task = asyncio.create_task(
            self._pulse_loop(), name="vital-signs-pulse"
        )
        logger.info("VitalSignsMonitor started (pulse every %ds)", self.PULSE_INTERVAL_S)

    async def stop(self) -> None:
        self._running = False
        if self._pulse_task and not self._pulse_task.done():
            self._pulse_task.cancel()
            try:
                await self._pulse_task
            except asyncio.CancelledError:
                pass
        logger.info("VitalSignsMonitor stopped")

    # ═══════════════════════════════════════
    # Layer 1: Preflight（啟動時）
    # ═══════════════════════════════════════

    async def run_preflight(self) -> VitalReport:
        """啟動時執行完整預檢."""
        report = VitalReport(layer="preflight")
        logger.info("🩺 Vital Signs Preflight starting...")

        # Check 1: LLM Adapter 可用性（實際呼叫）
        report.checks.append(await self._check_llm_alive())

        # Check 2: 環境變數一致性
        report.checks.append(self._check_env_consistency())

        # Check 3: Session 資料完整性
        report.checks.append(self._check_session_integrity())

        # Check 4: Telegram 能送訊息
        report.checks.append(await self._check_telegram_sendable())

        # Check 5: 治理模組初始化
        report.checks.append(self._check_governance_modules())

        # Check 6: 主動推送鏈路完整性
        report.checks.append(self._check_proactive_pipeline())

        # 計算 overall
        if any(c.status == CheckStatus.FAIL for c in report.checks):
            report.overall = CheckStatus.FAIL
        elif any(c.status == CheckStatus.WARN for c in report.checks):
            report.overall = CheckStatus.WARN

        self._last_preflight = report
        logger.info("🩺 Preflight: %s", report.summary())

        # 如果有 FAIL，推送 Telegram 告警
        if report.overall == CheckStatus.FAIL:
            await self._push_alert(
                "🚨 *MUSEON 啟動預檢失敗*\n\n" + self._format_report(report)
            )

        return report

    # ═══════════════════════════════════════
    # Layer 2: Pulse（定期探針）
    # ═══════════════════════════════════════

    async def _pulse_loop(self) -> None:
        """定期執行生命徵象檢查."""
        # 首次等待 120 秒讓系統完全啟動（含 LLM API 冷啟動暖機）
        await asyncio.sleep(120)

        while self._running:
            try:
                report = await self.run_pulse()

                if report.overall == CheckStatus.FAIL:
                    await self._push_alert(
                        "⚠️ *MUSEON 定期檢查發現異常*\n\n" + self._format_report(report)
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Pulse check error: %s", e)

            await asyncio.sleep(self.PULSE_INTERVAL_S)

    async def run_pulse(self) -> VitalReport:
        """執行一次完整的 pulse 檢查."""
        report = VitalReport(layer="pulse")

        # Check 1: LLM 存活
        report.checks.append(await self._check_llm_alive())

        # Check 2: 資源水位
        report.checks.append(self._check_resources())

        # Check 3: Session 數量與完整性
        report.checks.append(self._check_session_integrity())

        # Check 4: 治理層自檢（meta-governance）
        report.checks.append(self._check_governance_self_health())

        # Check 5: 端到端自測
        report.checks.append(await self._check_e2e_flow())

        if any(c.status == CheckStatus.FAIL for c in report.checks):
            report.overall = CheckStatus.FAIL
        elif any(c.status == CheckStatus.WARN for c in report.checks):
            report.overall = CheckStatus.WARN

        self._last_pulse = report
        logger.info("💓 Pulse: %s", report.summary())
        return report

    # ═══════════════════════════════════════
    # Layer 3: Sentinel（即時告警）
    # ═══════════════════════════════════════

    async def on_offline_triggered(self, error_msg: str = "") -> None:
        """Brain 進入離線模式時觸發.

        由 Brain._offline_response() 呼叫。
        限流：同一分鐘內最多推送 1 次。
        """
        now = time.time()
        if now - self._last_sentinel_ts < 60:
            return  # 限流

        self._sentinel_count += 1
        self._last_sentinel_ts = now
        self._consecutive_llm_failures += 1

        # 組裝修復指引
        guidance = self._diagnose_offline_cause(error_msg)

        alert = (
            "🔴 *MUSEON 進入離線模式*\n\n"
            f"原因：{error_msg[:200]}\n\n"
            f"📋 *修復指引：*\n{guidance}\n\n"
            f"連續離線次數：{self._consecutive_llm_failures}"
        )
        await self._push_alert(alert)

    def on_llm_success(self) -> None:
        """LLM 呼叫成功時重置計數器，並觸發恢復信號."""
        was_failing = self._consecutive_llm_failures > 0
        if was_failing:
            logger.info(
                "LLM recovered after %d consecutive failures",
                self._consecutive_llm_failures,
            )
        self._consecutive_llm_failures = 0

        # 觸發恢復回呼（通知 Brain 離開離線模式）
        if was_failing and self._recovery_callbacks:
            for cb in self._recovery_callbacks:
                try:
                    cb()
                except Exception as e:
                    logger.warning("Recovery callback error: %s", e)

    # ═══════════════════════════════════════
    # Individual Checks
    # ═══════════════════════════════════════

    async def _check_llm_alive(self) -> CheckResult:
        """實際呼叫 LLM 驗證可用性（驗真不驗表）."""
        if not self._llm_adapter:
            return CheckResult(
                name="llm_alive",
                status=CheckStatus.SKIP,
                message="LLM adapter not registered",
            )

        t0 = time.time()
        try:
            resp = await asyncio.wait_for(
                self._llm_adapter.call(
                    system_prompt="You are a health check probe. Reply with exactly: OK",
                    messages=[{"role": "user", "content": "health check"}],
                    model="haiku",
                    max_tokens=10,
                ),
                timeout=self.LLM_PROBE_TIMEOUT_S,
            )
            duration_ms = (time.time() - t0) * 1000

            if resp.stop_reason == "error":
                return CheckResult(
                    name="llm_alive",
                    status=CheckStatus.FAIL,
                    message=f"LLM returned error: {resp.text[:200]}",
                    duration_ms=duration_ms,
                )

            # LLM 恢復偵測：若之前有連續失敗，觸發恢復信號
            was_failing = self._consecutive_llm_failures > 0
            self._consecutive_llm_failures = 0
            if was_failing:
                logger.info("🟢 LLM probe recovered — triggering recovery signal")
                for cb in self._recovery_callbacks:
                    try:
                        cb()
                    except Exception as e:
                        logger.warning("Recovery callback error: %s", e)

            return CheckResult(
                name="llm_alive",
                status=CheckStatus.PASS,
                message=f"LLM responded in {duration_ms:.0f}ms",
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            self._consecutive_llm_failures += 1
            return CheckResult(
                name="llm_alive",
                status=CheckStatus.FAIL,
                message=f"LLM probe timed out after {self.LLM_PROBE_TIMEOUT_S}s",
                duration_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            self._consecutive_llm_failures += 1
            return CheckResult(
                name="llm_alive",
                status=CheckStatus.FAIL,
                message=f"LLM probe error: {e}",
                duration_ms=(time.time() - t0) * 1000,
            )

    def _check_env_consistency(self) -> CheckResult:
        """檢查環境變數衝突（如 ANTHROPIC_API_KEY vs OAuth）."""
        issues = []

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if api_key:
            # 驗證 API key 格式
            if not api_key.startswith("sk-ant-"):
                issues.append("ANTHROPIC_API_KEY format invalid")
            # 警告：有 API Key 可能干擾 CLI OAuth
            issues.append("ANTHROPIC_API_KEY present — ensure CLI env isolation")

        if not os.environ.get("TELEGRAM_BOT_TOKEN"):
            issues.append("TELEGRAM_BOT_TOKEN not set")

        if not os.environ.get("TELEGRAM_TRUSTED_IDS"):
            issues.append("TELEGRAM_TRUSTED_IDS not set (no push targets)")

        if issues:
            return CheckResult(
                name="env_consistency",
                status=CheckStatus.WARN,
                message="; ".join(issues),
            )
        return CheckResult(
            name="env_consistency",
            status=CheckStatus.PASS,
            message="Environment variables consistent",
        )

    def _check_session_integrity(self) -> CheckResult:
        """掃描 session 檔案，偵測汙染或異常."""
        session_dir = self._data_dir / "_system" / "sessions"
        if not session_dir.exists():
            return CheckResult(
                name="session_integrity",
                status=CheckStatus.PASS,
                message="No sessions directory",
            )

        session_files = list(session_dir.glob("*.json"))
        total = len(session_files)
        polluted = 0
        oversized = 0

        for f in session_files:
            try:
                size = f.stat().st_size
                if size > 1_000_000:  # > 1MB
                    oversized += 1
                    continue

                data = json.loads(f.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    continue

                for msg in data:
                    content = msg.get("content", "")
                    if len(content) > self.SESSION_MAX_CONTENT_LEN:
                        sample = content[:50]
                        if content.count(sample) > self.SESSION_REPEAT_THRESHOLD:
                            polluted += 1
                            break
            except Exception:
                continue

        if polluted > 0:
            return CheckResult(
                name="session_integrity",
                status=CheckStatus.FAIL,
                message=f"{polluted} polluted sessions detected (of {total})",
                details={"total": total, "polluted": polluted, "oversized": oversized},
            )
        if oversized > 0:
            return CheckResult(
                name="session_integrity",
                status=CheckStatus.WARN,
                message=f"{oversized} oversized sessions (of {total})",
                details={"total": total, "polluted": 0, "oversized": oversized},
            )
        return CheckResult(
            name="session_integrity",
            status=CheckStatus.PASS,
            message=f"{total} sessions clean",
        )

    async def _check_telegram_sendable(self) -> CheckResult:
        """驗證 Telegram Bot 能否成功送訊息."""
        if not self._bot_token or not self._trusted_user_id:
            return CheckResult(
                name="telegram_sendable",
                status=CheckStatus.SKIP,
                message="Telegram not configured",
            )

        t0 = time.time()
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self._bot_token}/getMe",
                )
                duration_ms = (time.time() - t0) * 1000

                if resp.status_code == 200:
                    bot_info = resp.json().get("result", {})
                    return CheckResult(
                        name="telegram_sendable",
                        status=CheckStatus.PASS,
                        message=f"Bot @{bot_info.get('username', '?')} reachable ({duration_ms:.0f}ms)",
                        duration_ms=duration_ms,
                    )
                return CheckResult(
                    name="telegram_sendable",
                    status=CheckStatus.FAIL,
                    message=f"Telegram API returned {resp.status_code}",
                    duration_ms=duration_ms,
                )
        except Exception as e:
            return CheckResult(
                name="telegram_sendable",
                status=CheckStatus.FAIL,
                message=f"Telegram check failed: {e}",
                duration_ms=(time.time() - t0) * 1000,
            )

    def _check_governance_modules(self) -> CheckResult:
        """檢查治理模組是否正常初始化."""
        if not self._governor_health_fn:
            return CheckResult(
                name="governance_modules",
                status=CheckStatus.SKIP,
                message="Governor health function not registered",
            )

        try:
            health = self._governor_health_fn()
            issues = []

            if not health.get("governor", {}).get("running"):
                issues.append("Governor not running")

            svc = health.get("services", {})
            if svc.get("overall") not in ("healthy",):
                issues.append(f"Services: {svc.get('overall', 'unknown')}")

            tg = health.get("telegram", {})
            if not tg.get("running"):
                issues.append("Telegram not running")

            if issues:
                return CheckResult(
                    name="governance_modules",
                    status=CheckStatus.WARN,
                    message="; ".join(issues),
                )
            return CheckResult(
                name="governance_modules",
                status=CheckStatus.PASS,
                message="All governance modules healthy",
            )
        except Exception as e:
            return CheckResult(
                name="governance_modules",
                status=CheckStatus.FAIL,
                message=f"Governance check error: {e}",
            )

    def _check_proactive_pipeline(self) -> CheckResult:
        """Check 6: 主動推送鏈路完整性 — HeartbeatEngine → ProactiveBridge → Telegram.

        驗真不驗表：不只看物件存在，而是確認 HeartbeatEngine 有在跑、
        ProactiveBridge 有註冊為任務、aiohttp 可 import。
        """
        issues = []

        # 1) HeartbeatEngine 是否存在且 running
        try:
            from museon.pulse.heartbeat_engine import _instance as hb_instance
            if hb_instance is None:
                issues.append("HeartbeatEngine singleton not created")
            elif not hb_instance._running:
                issues.append("HeartbeatEngine not running")
            else:
                # 2) proactive_bridge 是否有註冊
                status = hb_instance.status()
                if "proactive_bridge" not in status:
                    issues.append("ProactiveBridge not registered in HeartbeatEngine")
        except ImportError:
            issues.append("HeartbeatEngine module not found")
        except Exception as e:
            issues.append(f"HeartbeatEngine check error: {e}")

        # 3) aiohttp 可用性（推送底層依賴）
        try:
            import aiohttp  # noqa: F401
        except ImportError:
            issues.append("aiohttp not installed (Telegram push dependency)")

        if issues:
            return CheckResult(
                name="proactive_pipeline",
                status=CheckStatus.WARN,
                message="; ".join(issues),
            )
        return CheckResult(
            name="proactive_pipeline",
            status=CheckStatus.PASS,
            message="Proactive pipeline: HeartbeatEngine → ProactiveBridge → Telegram OK",
        )

    def _check_governance_self_health(self) -> CheckResult:
        """Phase 3: Meta-governance — 治理層自身的健康檢查."""
        if not self._governor_health_fn:
            return CheckResult(
                name="meta_governance",
                status=CheckStatus.SKIP,
                message="Governor not registered",
            )

        try:
            health = self._governor_health_fn()
            issues = []

            # 檢查免疫系統
            immunity = health.get("immunity", {})
            if immunity:
                recent = immunity.get("recent_incidents", [])
                unresolved = [i for i in recent if not i.get("resolved")]
                if len(unresolved) > 10:
                    issues.append(f"Immunity: {len(unresolved)} unresolved incidents")

            # 檢查自律神經
            autonomic = health.get("autonomic", {})
            if autonomic:
                if autonomic.get("recent_failed", 0) > 3:
                    issues.append(f"Autonomic: {autonomic['recent_failed']} recent failures")

            # 檢查 Bulkhead
            # (bulkhead info is in /health top level, not inside governance)

            if issues:
                return CheckResult(
                    name="meta_governance",
                    status=CheckStatus.WARN,
                    message="; ".join(issues),
                )
            return CheckResult(
                name="meta_governance",
                status=CheckStatus.PASS,
                message="Governance layer self-check OK",
            )
        except Exception as e:
            return CheckResult(
                name="meta_governance",
                status=CheckStatus.FAIL,
                message=f"Meta-governance error: {e}",
            )

    def _check_resources(self) -> CheckResult:
        """檢查系統資源水位."""
        issues = []
        details = {}

        # 磁碟空間
        try:
            import shutil
            usage = shutil.disk_usage(str(self._data_dir))
            free_mb = usage.free / (1024 * 1024)
            details["disk_free_mb"] = round(free_mb)
            if free_mb < self.RESOURCE_DISK_WARN_MB:
                issues.append(f"Disk low: {free_mb:.0f}MB free")
        except Exception:
            pass

        # Session 檔案數量
        session_dir = self._data_dir / "_system" / "sessions"
        if session_dir.exists():
            count = len(list(session_dir.glob("*.json")))
            details["session_count"] = count
            if count > self.RESOURCE_SESSION_WARN_COUNT:
                issues.append(f"Too many sessions: {count}")

        # Log 檔案大小
        log_dir = self._data_dir.parent / "logs"
        if log_dir.exists():
            total_log_mb = sum(
                f.stat().st_size for f in log_dir.glob("*") if f.is_file()
            ) / (1024 * 1024)
            details["log_total_mb"] = round(total_log_mb, 1)
            if total_log_mb > 100:
                issues.append(f"Logs large: {total_log_mb:.0f}MB")

        if issues:
            return CheckResult(
                name="resources",
                status=CheckStatus.WARN,
                message="; ".join(issues),
                details=details,
            )
        return CheckResult(
            name="resources",
            status=CheckStatus.PASS,
            message="Resources OK",
            details=details,
        )

    async def _check_e2e_flow(self) -> CheckResult:
        """Phase 3: 端到端自測 — 模擬一條訊息走完 Brain.process()."""
        if not self._brain_ref:
            return CheckResult(
                name="e2e_flow",
                status=CheckStatus.SKIP,
                message="Brain not registered",
            )

        t0 = time.time()
        try:
            result = await asyncio.wait_for(
                self._brain_ref.process(
                    content="vital signs health check",
                    session_id="__vital_signs_probe__",
                    user_id="system",
                    source="vital_signs",
                ),
                timeout=60,
            )
            duration_ms = (time.time() - t0) * 1000

            # 檢查是否得到離線回覆
            text = str(result.text if hasattr(result, "text") else result)
            if "無法連線" in text or "離線" in text:
                return CheckResult(
                    name="e2e_flow",
                    status=CheckStatus.FAIL,
                    message=f"E2E returned offline response ({duration_ms:.0f}ms)",
                    duration_ms=duration_ms,
                )

            return CheckResult(
                name="e2e_flow",
                status=CheckStatus.PASS,
                message=f"E2E flow OK ({duration_ms:.0f}ms)",
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            return CheckResult(
                name="e2e_flow",
                status=CheckStatus.FAIL,
                message="E2E flow timed out (60s)",
                duration_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return CheckResult(
                name="e2e_flow",
                status=CheckStatus.WARN,
                message=f"E2E flow error: {e}",
                duration_ms=(time.time() - t0) * 1000,
            )

    # ═══════════════════════════════════════
    # Telegram Alert Push
    # ═══════════════════════════════════════

    async def _push_alert(self, text: str) -> bool:
        """推送告警到 Telegram（使用 httpx 避免依賴 aiohttp）."""
        if not self._bot_token or not self._trusted_user_id:
            logger.warning("Cannot push alert: Telegram not configured")
            return False

        try:
            import httpx

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
                    json={
                        "chat_id": self._trusted_user_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
                if resp.status_code == 200:
                    logger.info("📨 Vital alert pushed to Telegram")
                    return True
                logger.error("Telegram push failed: %d", resp.status_code)
                return False
        except Exception as e:
            logger.error("Telegram push error: %s", e)
            return False

    # ═══════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════

    def _diagnose_offline_cause(self, error_msg: str) -> str:
        """根據錯誤訊息推斷原因並提供修復指引."""
        msg = error_msg.lower()

        if "oauth" in msg or "expired" in msg:
            return (
                "1. OAuth token 過期\n"
                "2. 請在終端機執行：`claude auth login`\n"
                "3. 重新登入後重啟 Gateway"
            )
        if "invalid x-api-key" in msg or "authentication" in msg:
            return (
                "1. API Key 無效或過期\n"
                "2. 若使用 Max 訂閱，確認 CLI 環境未被 ANTHROPIC_API_KEY 汙染\n"
                "3. 檢查 adapters.py 是否有 env.pop('ANTHROPIC_API_KEY')"
            )
        if "timeout" in msg:
            return (
                "1. LLM 服務回應超時\n"
                "2. 檢查網路連線\n"
                "3. 可能是 Anthropic 服務暫時不可用"
            )
        return (
            "1. 檢查 Gateway 日誌：`tail -50 ~/MUSEON/logs/gateway.err`\n"
            "2. 測試 CLI：`claude -p 'hi' --output-format json --model haiku`\n"
            "3. 重啟 Gateway：`launchctl bootout/bootstrap`"
        )

    def _format_report(self, report: VitalReport) -> str:
        """格式化報告為 Telegram Markdown."""
        lines = []
        for c in report.checks:
            icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭"}[c.status.value]
            lines.append(f"{icon} *{c.name}*: {c.message}")
        return "\n".join(lines)

    # ─── Status for /health ───

    def get_status(self) -> Dict[str, Any]:
        """供 Governor.get_health() 使用."""
        return {
            "running": self._running,
            "consecutive_llm_failures": self._consecutive_llm_failures,
            "sentinel_count": self._sentinel_count,
            "last_preflight": (
                {
                    "overall": self._last_preflight.overall.value,
                    "summary": self._last_preflight.summary(),
                    "timestamp": self._last_preflight.timestamp,
                }
                if self._last_preflight
                else None
            ),
            "last_pulse": (
                {
                    "overall": self._last_pulse.overall.value,
                    "summary": self._last_pulse.summary(),
                    "timestamp": self._last_pulse.timestamp,
                }
                if self._last_pulse
                else None
            ),
        }
