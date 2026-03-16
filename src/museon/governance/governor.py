"""Governor — 三焦式分層治理主控制器

三焦對應：
┌─────────────────────────────────────────────────────┐
│  上焦 (Upper)  │ 系統級 │ 整體健康分數、趨勢分析     │  5-15 min  │
│  中焦 (Middle) │ 服務級 │ Docker 服務、API 回應品質   │  30-60 s   │
│  下焦 (Lower)  │ 進程級 │ PID、端口、Singleton 保證   │  5-10 s    │
└─────────────────────────────────────────────────────┘

設計原則 (PCT)：
  每個子系統都有一個「參考信號」（期望狀態），
  當「知覺信號」（實際狀態）偏離參考信號時，產生「誤差信號」，
  誤差信號驅動修正行為。

  Gateway 參考信號 = 唯一實例在監聽 8765
  Telegram 參考信號 = 一個且僅一個 polling 連線
  Qdrant 參考信號  = 回應 < 500ms 且可用

警覺信號 (Algedonic Signal)：
  重大問題跳過所有中間層，直接到最高治理層。
  例：SafetyAnchor 缺失、記憶體 > 90%、Gateway 進程消失。

Milestone #001 — 2026-03-03
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .gateway_lock import GatewayLock
from .context import GovernanceContext, HealthTier, health_to_tier
from .immunity import ImmunityEngine
from .perception import (
    DiagnosticReport,
    PerceptionEngine,
    SymptomSeverity,
)
from .regulation import ActionType, RegulationEngine
from .service_health import ServiceHealthMonitor, ServiceStatus
from .telegram_guard import TelegramPollingGuard

logger = logging.getLogger(__name__)


# ─── 系統健康等級 ───


class SystemHealth(Enum):
    """整體系統健康等級（望聞問切 → 診斷結果）"""

    VITAL = "vital"  # 一切正常
    STABLE = "stable"  # 有小問題但穩定運作
    DEGRADED = "degraded"  # 部分功能受損
    CRITICAL = "critical"  # 核心功能受損，需要介入
    EMERGENCY = "emergency"  # 警覺信號 — 系統瀕臨崩潰


@dataclass
class HealthSnapshot:
    """系統健康快照（定期產生，供趨勢分析）"""

    timestamp: float
    health: SystemHealth
    gateway_alive: bool
    telegram_status: dict
    services_status: dict
    memory_usage_mb: float = 0.0
    active_sessions: int = 0
    error_rate_per_min: float = 0.0


class Governor:
    """三焦式運行時治理主控制器。

    統合管理所有治理子系統：
    - 下焦: GatewayLock (進程唯一性)
    - 下焦: TelegramPollingGuard (通訊唯一性)
    - 中焦: ServiceHealthMonitor (Docker 服務健康)
    - 上焦: 趨勢分析 + 異穩態節律 (未來擴展)

    使用方式 (整合到 server.py):

        governor = Governor(
            port=8765,
            telegram_token="...",
        )

        # 在 startup 事件中
        governor.acquire_lock()  # 下焦: 確保唯一實例
        await governor.start()   # 啟動所有監控

        # 在 shutdown 事件中
        await governor.stop()
        governor.release_lock()
    """

    def __init__(
        self,
        port: int = 8765,
        telegram_token: Optional[str] = None,
        lock_timeout_s: float = 5.0,
        service_check_interval_s: float = 30.0,
        upper_check_interval_s: float = 300.0,  # 5 分鐘
        on_algedonic_signal: Optional[Callable] = None,
        data_dir: Optional[str] = None,
        immunity_path: Optional[str] = None,
    ):
        self.port = port
        self.telegram_token = telegram_token
        self.on_algedonic_signal = on_algedonic_signal

        # 下焦: Gateway Lock
        self._gateway_lock = GatewayLock(
            port=port, timeout_s=lock_timeout_s
        )

        # 下焦: Telegram Guard
        # 支援兩種模式:
        #   1. 自建模式 — 由 Guard 自行管理 Application (未來完整重構時使用)
        #   2. 外部模式 — 由 server.py 管理 TelegramAdapter，Guard 僅追蹤狀態
        self._telegram_guard: Optional[TelegramPollingGuard] = None
        self._telegram_status_fn: Optional[Callable[[], dict]] = None

        if telegram_token:
            self._telegram_guard = TelegramPollingGuard(
                bot_token=telegram_token,
            )

        # 中焦: Service Health Monitor
        self._service_monitor = ServiceHealthMonitor(
            check_interval_s=service_check_interval_s,
            on_status_change=self._on_service_status_change,
        )

        # 上焦: 趨勢分析
        self._upper_interval_s = upper_check_interval_s
        self._upper_task: Optional[asyncio.Task] = None
        self._health_history: List[HealthSnapshot] = []
        self._max_history = 288  # 24h × 12 (每 5 min)

        # ─── Phase 2: 察覺 → 調節 → 免疫 三部曲 ───
        self._perception = PerceptionEngine(
            governor=self,
            data_dir=data_dir,
        )
        self._regulation = RegulationEngine(
            on_action=self._on_regulation_action,
        )
        self._immunity = ImmunityEngine(
            memory_path=immunity_path,
        )
        self._last_diagnostic: Optional[DiagnosticReport] = None

        # ─── Phase 3: 治理 → 大腦橋樑 ───
        self._event_bus: Any = None           # Phase 3d: EventBus 引用
        self._growth_driver: Any = None       # Phase 3b: ANIMA 成長驅動
        self._prev_health_tier: Optional[HealthTier] = None  # Phase 3d: 健康等級變化偵測

        # ─── Dendritic Layer: VIGIL EmoBank 健康分數 ───
        self._dendritic: Any = None

        # ─── Autonomy Architecture: 後天免疫 + 自律神經 ───
        self._immune_memory: Any = None
        self._autonomic: Any = None
        try:
            from .immune_memory import ImmuneMemoryBank
            self._immune_memory = ImmuneMemoryBank(
                data_dir=Path(data_dir) if data_dir else None,
            )
            logger.info("Governor: ImmuneMemoryBank loaded")
        except Exception as e:
            logger.debug(f"Governor: ImmuneMemoryBank not available: {e}")

        try:
            from .autonomic import AutonomicLayer
            self._autonomic = AutonomicLayer(
                data_dir=Path(data_dir) if data_dir else None,
            )
            logger.info("Governor: AutonomicLayer loaded")
        except Exception as e:
            logger.debug(f"Governor: AutonomicLayer not available: {e}")

        self._running = False
        self._started_at = 0.0

    # ─── Lifecycle ───

    def acquire_lock(self) -> None:
        """下焦: 取得 Gateway 唯一實例鎖。

        應該在 uvicorn 啟動前呼叫。
        如果另一個 Gateway 已在運行，會丟出 GatewayLockError。
        """
        logger.info("Governor: acquiring gateway lock...")
        self._gateway_lock.acquire()
        logger.info("Governor: gateway lock acquired ✓")

    def release_lock(self) -> None:
        """下焦: 釋放 Gateway 鎖。"""
        self._gateway_lock.release()

    async def start(self) -> None:
        """啟動所有治理子系統。"""
        if self._running:
            return

        self._running = True
        self._started_at = time.time()

        logger.info("═══════════════════════════════════════")
        logger.info("  MUSEON Governor starting...")
        logger.info("  三焦式分層治理 (PCT-driven)")
        logger.info("═══════════════════════════════════════")

        # 中焦: 啟動服務健康監控
        await self._service_monitor.start()
        logger.info("  中焦 ✓ ServiceHealthMonitor active")

        # 下焦: 啟動 Telegram Guard
        if self._telegram_guard:
            await self._telegram_guard.start()
            logger.info("  下焦 ✓ TelegramPollingGuard active")

        # Phase 2: 載入免疫記憶
        try:
            self._immunity.load()
            logger.info("  免疫 ✓ Immunity memory loaded")
        except Exception as e:
            logger.warning(f"  免疫 ⚠ load failed (clean start): {e}")

        # Dendritic Layer: Health Score 計算器
        try:
            from .dendritic_scorer import DendriticScorer
            self._dendritic = DendriticScorer(event_bus=self._event_bus)
            logger.info("  樹突 ✓ DendriticScorer active")
        except Exception as e:
            logger.debug(f"  樹突 ⚠ DendriticScorer not available: {e}")

        # 生命徵象: 啟動 VitalSignsMonitor
        try:
            from .vital_signs import VitalSignsMonitor
            self._vital_signs = VitalSignsMonitor(
                data_dir=Path(os.environ.get("MUSEON_HOME", ".")) / "data",
            )
            self._vital_signs.register_governor_health(self.get_health)
            await self._vital_signs.start()
            logger.info("  生命 ✓ VitalSignsMonitor active")
        except Exception as e:
            logger.warning(f"  生命 ⚠ VitalSignsMonitor failed: {e}")
            self._vital_signs = None

        # 上焦: 啟動趨勢分析 + 察覺調節免疫迴圈
        self._upper_task = asyncio.create_task(
            self._upper_burner_loop(), name="governor-upper-burner"
        )
        logger.info("  上焦 ✓ Perception → Regulation → Immunity active")

        logger.info("═══════════════════════════════════════")
        logger.info("  MUSEON Governor ready")
        logger.info("═══════════════════════════════════════")

    async def stop(self) -> None:
        """停止所有治理子系統。"""
        if not self._running:
            return

        logger.info("Governor stopping...")
        self._running = False

        # 上焦
        if self._upper_task and not self._upper_task.done():
            self._upper_task.cancel()
            try:
                await self._upper_task
            except asyncio.CancelledError as e:
                logger.debug(f"[GOVERNOR] operation failed (degraded): {e}")

        # 生命徵象: 停止 VitalSignsMonitor
        if getattr(self, '_vital_signs', None):
            await self._vital_signs.stop()

        # Phase 2: 持久化免疫記憶
        try:
            self._immunity.save()
            logger.info("Immunity memory saved")
        except Exception as e:
            logger.warning(f"Failed to save immunity memory: {e}")

        # Autonomy: 持久化自律層歷史
        if self._autonomic:
            try:
                self._autonomic.save_history()
                logger.info("Autonomic history saved")
            except Exception as e:
                logger.warning(f"Failed to save autonomic history: {e}")

        # 下焦: Telegram
        if self._telegram_guard:
            await self._telegram_guard.stop()

        # 中焦: 服務監控
        await self._service_monitor.stop()

        logger.info("Governor stopped")

    # ─── External Telegram Status ───

    def register_telegram_status(self, fn: Callable[[], dict]) -> None:
        """註冊外部 Telegram 狀態回報函數。

        當 Telegram 由外部 TelegramAdapter 管理時（非 Guard 自建模式），
        使用此方法讓 Governor 能取得 Telegram 狀態。

        Args:
            fn: 無參數的 callable，回傳 dict 格式的 Telegram 狀態
        """
        self._telegram_status_fn = fn
        logger.debug("Governor: external telegram status function registered")

    def register_vital_signs_deps(self, llm_adapter: Any = None, brain: Any = None) -> None:
        """注入 LLM adapter 和 Brain 到 VitalSignsMonitor."""
        vs = getattr(self, '_vital_signs', None)
        if not vs:
            return
        if llm_adapter:
            vs.register_llm_adapter(llm_adapter)
        if brain:
            vs.register_brain(brain)
        logger.info("Governor: VitalSigns dependencies registered")

    async def run_vital_preflight(self):
        """執行啟動預檢（供 server.py 在所有子系統就緒後呼叫）."""
        vs = getattr(self, '_vital_signs', None)
        if vs:
            return await vs.run_preflight()
        return None

    def get_vital_signs(self):
        """取得 VitalSignsMonitor 實例."""
        return getattr(self, '_vital_signs', None)

    def register_event_bus(self, event_bus: Any) -> None:
        """連接 EventBus 到察覺引擎，開始被動聆聽事件流。

        應在 startup 事件中呼叫，讓 PerceptionEngine 的「聞診」能運作。
        Phase 3d: 同時保存引用以供治理事件廣播。

        Args:
            event_bus: 已初始化的 EventBus 實例
        """
        self._event_bus = event_bus  # Phase 3d
        self._perception.connect_event_bus(event_bus)
        # WP-04: 訂閱 AUDIT_COMPLETED → 根據結果觸發反應
        try:
            from museon.core.event_bus import (
                AUDIT_COMPLETED,
                MORPHENIX_AUTO_APPROVED,
                SOUL_IDENTITY_TAMPERED,
            )
            event_bus.subscribe(AUDIT_COMPLETED, self._on_audit_completed)
            event_bus.subscribe(
                SOUL_IDENTITY_TAMPERED, self._on_soul_identity_tampered
            )
            event_bus.subscribe(
                MORPHENIX_AUTO_APPROVED, self._on_morphenix_auto_approved
            )
        except Exception as e:
            logger.debug(f"Governor: event subscription failed: {e}")
        # WP-04: 注入 event_bus 到 ImmuneMemoryBank（延遲注入）
        if self._immune_memory and not getattr(self._immune_memory, "_event_bus", None):
            self._immune_memory._event_bus = event_bus
            self._immune_memory._subscribe()
        logger.debug("Governor: EventBus connected to PerceptionEngine")

    def _get_telegram_status(self) -> dict:
        """取得 Telegram 狀態（優先使用 Guard，否則用外部函數）。"""
        if self._telegram_guard:
            return self._telegram_guard.get_status()
        if self._telegram_status_fn:
            try:
                return self._telegram_status_fn()
            except Exception as e:
                return {"running": False, "error": str(e)}
        return {"running": False, "reason": "not configured"}

    # ─── Status & Health ───

    def get_health(self) -> dict:
        """取得整體系統健康狀態。

        聚合三焦所有子系統的狀態。
        供 /health 端點使用。
        """
        services = self._service_monitor.get_all_status()
        telegram = self._get_telegram_status()

        # 計算整體健康等級
        health = self._compute_health(services, telegram)

        # Phase 2 最新診斷
        last_diag = None
        if self._last_diagnostic:
            last_diag = {
                "symptom_count": self._last_diagnostic.symptom_count,
                "max_severity": self._last_diagnostic.max_severity.value,
                "is_healthy": self._last_diagnostic.is_healthy,
                "diagnosed_at": self._last_diagnostic.timestamp,
            }

        return {
            "health": health.value,
            "gateway": {
                "locked": self._gateway_lock.is_acquired(),
                "port": self.port,
                "pid": __import__("os").getpid(),
                "uptime_s": round(time.time() - self._started_at, 1)
                if self._started_at
                else 0,
            },
            "telegram": telegram,
            "services": services,
            "governor": {
                "running": self._running,
                "health_snapshots": len(self._health_history),
            },
            "perception": last_diag,
            "regulation": self._regulation.get_status(),
            "immunity": self._immunity.get_status(),
            "immune_memory": (
                self._immune_memory.get_stats()
                if self._immune_memory else None
            ),
            "autonomic": (
                self._autonomic.get_status()
                if self._autonomic else None
            ),
            "dendritic": (
                self._dendritic.get_status()
                if self._dendritic else None
            ),
            "vital_signs": (
                self._vital_signs.get_status()
                if getattr(self, '_vital_signs', None) else None
            ),
        }

    def get_trend(self, hours: float = 1.0) -> dict:
        """取得過去 N 小時的健康趨勢。"""
        cutoff = time.time() - hours * 3600
        recent = [s for s in self._health_history if s.timestamp > cutoff]

        if not recent:
            return {"trend": "no_data", "snapshots": 0}

        health_counts = {}
        for snap in recent:
            h = snap.health.value
            health_counts[h] = health_counts.get(h, 0) + 1

        total = len(recent)
        healthy_ratio = (
            health_counts.get("vital", 0) + health_counts.get("stable", 0)
        ) / total

        return {
            "trend": (
                "improving" if healthy_ratio > 0.8 else
                "stable" if healthy_ratio > 0.5 else
                "declining"
            ),
            "healthy_ratio": round(healthy_ratio, 2),
            "distribution": health_counts,
            "snapshots": total,
            "period_hours": hours,
        }

    # ─── Upper Burner: 趨勢分析迴圈 ───

    async def _upper_burner_loop(self) -> None:
        """上焦: 定期執行完整的治理迴圈。

        每 5 分鐘：
        1. 收集所有子系統狀態 (健康快照)
        2. 察覺 (望聞問切) → 診斷報告
        3. 調節 (PCT) → 修正行動
        4. 免疫 (先天+後天) → 防禦/學習
        5. 偵測趨勢惡化 → 觸發警覺信號
        6. 持久化免疫記憶
        """
        while self._running:
            try:
                await asyncio.sleep(self._upper_interval_s)
                if not self._running:
                    break

                # ── Step 1: 健康快照 ──
                snapshot = self._take_snapshot()
                self._health_history.append(snapshot)
                if len(self._health_history) > self._max_history:
                    self._health_history = self._health_history[
                        -self._max_history :
                    ]

                # ── Step 2: 察覺 (望聞問切) ──
                try:
                    report = await self._perception.perceive()
                    self._last_diagnostic = report
                except Exception as e:
                    logger.warning(f"Perception failed: {e}")
                    report = None

                # ── Step 3: 調節 (PCT) ──
                if report and report.symptoms:
                    try:
                        reg_result = self._regulation.regulate(report)
                        if reg_result.actions:
                            logger.info(
                                f"上焦調節: {reg_result.action_count} 個修正行動"
                            )
                    except Exception as e:
                        logger.warning(f"Regulation failed: {e}")

                # ── Step 4: 免疫 (先天+後天) ──
                if report:
                    try:
                        self._run_immunity_cycle(report)
                    except Exception as e:
                        logger.warning(f"Immunity cycle failed: {e}")

                # ── Step 4.1: Dendritic Layer tick ──
                if self._dendritic:
                    try:
                        dendritic_status = self._dendritic.tick()
                        logger.debug(
                            f"Dendritic: score={dendritic_status.get('score')}, "
                            f"tier={dendritic_status.get('tier_label')}"
                        )
                    except Exception as e:
                        logger.debug(f"Dendritic tick failed: {e}")

                # ── Step 4.2: Autonomic Layer tick ──
                if self._autonomic:
                    try:
                        repair_result = self._autonomic.tick()
                        if repair_result and self._event_bus:
                            from museon.core.event_bus import AUTONOMIC_REPAIR
                            self._event_bus.publish(AUTONOMIC_REPAIR, repair_result)
                    except Exception as e:
                        logger.debug(f"Autonomic tick failed: {e}")

                # ── Step 5: 警覺信號偵測 ──
                self._check_algedonic(snapshot)

                # ── Step 6: 持久化免疫記憶 ──
                try:
                    self._immunity.save()
                except Exception as e:
                    logger.debug(f"[GOVERNOR] operation failed (degraded): {e}")

                # ── Step 4.5: Phase 3b — ANIMA 成長驅動 ──
                if self._growth_driver:
                    try:
                        ctx = self.build_context()
                        self._growth_driver.on_governance_cycle(
                            context=ctx,
                            report=report,
                        )
                    except Exception as e:
                        logger.debug(f"ANIMA growth drive failed: {e}")

                # ── Step 5.5: Phase 3d — 治理事件廣播 ──
                if self._event_bus:
                    try:
                        current_tier = health_to_tier(snapshot.health.value)

                        # 每個迴圈完成都發布
                        self._event_bus.publish(
                            "GOVERNANCE_CYCLE_COMPLETED",
                            {
                                "health": snapshot.health.value,
                                "health_tier": current_tier.value,
                                "symptom_count": (
                                    report.symptom_count if report else 0
                                ),
                                "is_healthy": (
                                    report.is_healthy if report else True
                                ),
                                "trend": self.get_trend(hours=1.0).get(
                                    "trend", "no_data"
                                ),
                            },
                        )

                        # 健康等級變化時才發布
                        if (
                            self._prev_health_tier is not None
                            and current_tier != self._prev_health_tier
                        ):
                            self._event_bus.publish(
                                "GOVERNANCE_HEALTH_CHANGED",
                                {
                                    "old_tier": self._prev_health_tier.value,
                                    "new_tier": current_tier.value,
                                },
                            )
                            logger.info(
                                f"治理事件: 健康等級變化 "
                                f"{self._prev_health_tier.value} → "
                                f"{current_tier.value}"
                            )

                        # 警覺信號
                        if current_tier == HealthTier.CRITICAL:
                            self._event_bus.publish(
                                "GOVERNANCE_ALGEDONIC_SIGNAL",
                                {
                                    "health_tier": current_tier.value,
                                    "symptom_count": (
                                        report.symptom_count if report else 0
                                    ),
                                },
                            )

                        self._prev_health_tier = current_tier
                    except Exception as e:
                        logger.debug(f"Governance event publish failed: {e}")

                # ── 日誌摘要 ──
                diag_summary = ""
                if report:
                    diag_summary = (
                        f", perception={report.symptom_count} symptoms"
                        f"({report.max_severity.value})"
                    )
                logger.debug(
                    f"Upper burner: health={snapshot.health.value}, "
                    f"services={snapshot.services_status.get('overall', '?')}"
                    f"{diag_summary}"
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Upper burner error: {e}")

    def _take_snapshot(self) -> HealthSnapshot:
        """產生一份健康快照。"""
        services = self._service_monitor.get_all_status()
        telegram = self._get_telegram_status()
        health = self._compute_health(services, telegram)

        # 記憶體使用量
        memory_mb = 0.0
        try:
            import resource

            rusage = resource.getrusage(resource.RUSAGE_SELF)
            memory_mb = rusage.ru_maxrss / (1024 * 1024)  # macOS: bytes
        except Exception as e:
            logger.debug(f"[GOVERNOR] memory failed (degraded): {e}")

        return HealthSnapshot(
            timestamp=time.time(),
            health=health,
            gateway_alive=self._gateway_lock.is_acquired(),
            telegram_status=telegram,
            services_status=services,
            memory_usage_mb=memory_mb,
        )

    def _compute_health(
        self, services: dict, telegram: dict
    ) -> SystemHealth:
        """根據所有子系統狀態計算整體健康等級。"""
        issues = []

        # Gateway Lock
        if not self._gateway_lock.is_acquired():
            return SystemHealth.EMERGENCY

        # Telegram
        if telegram.get("running") is False and self.telegram_token:
            issues.append("telegram_down")

        # 服務
        svc_overall = services.get("overall", "unknown")
        if svc_overall == "critical":
            issues.append("services_critical")
        elif svc_overall == "degraded":
            issues.append("services_degraded")

        # Telegram 連續錯誤
        if telegram.get("consecutive_errors", 0) >= 5:
            issues.append("telegram_unstable")

        # 判定
        if "services_critical" in issues:
            return SystemHealth.CRITICAL
        if "telegram_down" in issues and "services_degraded" in issues:
            return SystemHealth.CRITICAL
        if "telegram_down" in issues or "services_degraded" in issues:
            return SystemHealth.DEGRADED
        if "telegram_unstable" in issues:
            return SystemHealth.STABLE

        return SystemHealth.VITAL

    def _check_algedonic(self, snapshot: HealthSnapshot) -> None:
        """偵測警覺信號 — 跳過所有中間層的緊急警報。"""
        if snapshot.health in (
            SystemHealth.CRITICAL,
            SystemHealth.EMERGENCY,
        ):
            logger.critical(
                f"⚠️ ALGEDONIC SIGNAL: system health = "
                f"{snapshot.health.value}"
            )
            if self.on_algedonic_signal:
                try:
                    self.on_algedonic_signal(snapshot)
                except Exception as e:
                    logger.error(f"Algedonic signal handler error: {e}")

        # 趨勢惡化偵測（治未病）
        if len(self._health_history) >= 3:
            recent_3 = self._health_history[-3:]
            if all(
                s.health
                in (SystemHealth.DEGRADED, SystemHealth.CRITICAL)
                for s in recent_3
            ):
                logger.warning(
                    "⚠️ 治未病警告: 連續 3 次健康快照均為 degraded/critical"
                )

    # ─── WP-04: 審計完成回調 ───

    def _on_audit_completed(self, data: Optional[Dict] = None) -> None:
        """審計完成 → 根據結果調整治理行為."""
        if not data:
            return
        overall = data.get("overall", "ok")
        summary = data.get("summary", {})

        if overall == "critical":
            # CRITICAL → 觸發 Algedonic Signal
            logger.warning(
                f"Governor: Audit CRITICAL — {summary}"
            )
            if self._event_bus:
                try:
                    self._event_bus.publish(
                        "GOVERNANCE_ALGEDONIC_SIGNAL",
                        {"source": "system_audit", "overall": overall, "summary": summary},
                    )
                except Exception as e:
                    logger.debug(f"[GOVERNOR] audit failed (degraded): {e}")

            # CRITICAL → 推送 Telegram 告警（限流：同類型每 10 分鐘最多 1 次）
            import time as _time
            _now = _time.time()
            _last_critical_ts = getattr(self, "_last_critical_alert_ts", 0.0)
            if _now - _last_critical_ts >= 600:  # 10 分鐘限流
                self._last_critical_alert_ts = _now
                vs = getattr(self, '_vital_signs', None)
                if vs:
                    import asyncio
                    alert_text = (
                        "🚨 *Governor 審計 CRITICAL*\n\n"
                        f"來源: system\\_audit\n"
                        f"摘要: {str(summary)[:300]}"
                    )
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.ensure_future(vs._push_alert(alert_text))
                        else:
                            loop.run_until_complete(vs._push_alert(alert_text))
                    except Exception as e:
                        logger.warning(f"Governor CRITICAL alert push failed: {e}")
        elif overall == "warning":
            # WARNING → 縮短巡檢間隔（加速感知）
            if hasattr(self, "_upper_check_interval_s"):
                self._upper_check_interval_s = min(
                    self._upper_check_interval_s, 180.0
                )
                logger.info(
                    f"Governor: Audit WARNING — 巡檢間隔縮短至 "
                    f"{self._upper_check_interval_s}s"
                )

    # ─── SOUL_IDENTITY_TAMPERED 告警 ───

    def _on_soul_identity_tampered(self, data: Optional[Dict] = None) -> None:
        """SOUL.md 完整性被篡改 → 觸發 CRITICAL 警覺信號."""
        logger.critical(
            f"🚨 SOUL IDENTITY TAMPERED — "
            f"embedded={data.get('embedded_hash', '?')[:8]}... "
            f"computed={data.get('computed_hash', '?')[:8]}... "
            f"severity={data.get('severity', 'CRITICAL')}"
        )
        # 發布 Algedonic Signal
        if self._event_bus:
            try:
                self._event_bus.publish(
                    "GOVERNANCE_ALGEDONIC_SIGNAL",
                    {
                        "source": "soul_identity_check",
                        "overall": "critical",
                        "summary": {
                            "event": "SOUL_IDENTITY_TAMPERED",
                            "embedded_hash": data.get("embedded_hash", ""),
                            "computed_hash": data.get("computed_hash", ""),
                        },
                    },
                )
            except Exception as e:
                logger.warning(f"Governor: Algedonic signal publish failed: {e}")

        # 推送 Telegram 告警
        vs = getattr(self, "_vital_signs", None)
        if vs:
            import asyncio

            alert_text = (
                "🚨 *CRITICAL: SOUL Identity Tampered*\n\n"
                f"Expected hash: `{data.get('embedded_hash', '?')[:16]}...`\n"
                f"Actual hash: `{data.get('computed_hash', '?')[:16]}...`\n\n"
                "SOUL.md 完整性已被篡改，請立即檢查。"
            )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(vs._push_alert(alert_text))
                else:
                    loop.run_until_complete(vs._push_alert(alert_text))
            except Exception as e:
                logger.warning(f"Governor: Soul tamper alert push failed: {e}")

    # ─── MORPHENIX_AUTO_APPROVED 執行者 ───

    def _on_morphenix_auto_approved(self, data: Optional[Dict] = None) -> None:
        """Morphenix 提案自動核准 → 觸發執行."""
        if not data:
            return
        proposal_ids = data.get("proposal_ids", [])
        count = data.get("count", 0)
        logger.info(
            f"Governor: Morphenix auto-approved {count} proposals: {proposal_ids}"
        )
        # 嘗試觸發 MorphenixExecutor 執行
        try:
            from museon.nightly.morphenix_executor import MorphenixExecutor

            executor = MorphenixExecutor(
                workspace=self._workspace,
                event_bus=self._event_bus,
            )
            for pid in proposal_ids:
                try:
                    result = executor.execute_proposal(pid)
                    logger.info(
                        f"Governor: Morphenix proposal {pid} executed: "
                        f"{result.get('status', 'unknown')}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Governor: Morphenix proposal {pid} execution failed: {e}"
                    )
        except ImportError as e:
            logger.debug(f"Governor: MorphenixExecutor not available: {e}")

    # ─── Phase 2: 免疫迴圈 ───

    def _run_immunity_cycle(self, report: DiagnosticReport) -> None:
        """對診斷報告中的每個嚴重症狀執行免疫檢查。

        流程：
        1. 對每個 moderate+ 症狀查詢免疫記憶
        2. 有已知防禦 → 記錄免疫反應
        3. 無已知防禦 → 記錄為新事件（未來可學習）
        """
        for symptom in report.symptoms:
            # 只處理 moderate 以上的症狀
            if symptom.severity in (
                SymptomSeverity.INFO,
                SymptomSeverity.MILD,
            ):
                continue

            # 查詢免疫記憶
            response = self._immunity.check(symptom)
            if response:
                logger.info(
                    f"免疫反應: [{response.antibody_type}] "
                    f"{response.response_description} "
                    f"(confidence={response.confidence:.0%})"
                )
                # 記錄事件（有免疫反應 = 自動處理）
                incident = self._immunity.record_incident(
                    symptom,
                    resolution=response.response_description,
                    auto_resolved=True,
                )
                # 從解決中學習，生成/強化抗體（P1 後天免疫修復）
                self._immunity.learn(incident)
                # 強化抗體
                self._immunity.reinforce(response.antibody_id, success=True)
            else:
                # 後天免疫（ImmuneMemoryBank）：檢查是否有學習到的防禦規則
                signature = f"{symptom.source}::{symptom.message[:80]}"
                defense = None
                if self._immune_memory:
                    try:
                        defense = self._immune_memory.check_defense(signature)
                    except Exception as e:
                        logger.debug(f"ImmuneMemory check_defense failed: {e}")

                if defense:
                    logger.info(
                        f"後天免疫反應: {defense[:100]} "
                        f"(signature={signature[:50]})"
                    )
                    inc_defense = self._immunity.record_incident(
                        symptom,
                        resolution=f"[ImmuneMemory] {defense}",
                        auto_resolved=True,
                    )
                    # 從解決中學習（P1 後天免疫修復）
                    self._immunity.learn(inc_defense)
                    self._immune_memory.reinforce(signature, success=True)
                else:
                    # 去重：已有同名未解決事件就不重複建立
                    if self._immunity.has_active_incident(symptom.name):
                        logger.debug(
                            f"跳過重複事件: {symptom.name} "
                            f"(已有未解決記錄)"
                        )
                    else:
                        # 未知模式 → 記錄事件（後續可學習）
                        self._immunity.record_incident(symptom)

                    # 記錄異常到 ImmuneMemoryBank（第一次記錄、第二次生成規則）
                    if self._immune_memory:
                        try:
                            self._immune_memory.record_anomaly(
                                signature=signature,
                                context=symptom.message[:200],
                            )
                        except Exception as e:
                            logger.debug(f"ImmuneMemory record failed: {e}")

    def _on_regulation_action(self, action: Any) -> None:
        """調節引擎的行動回調。

        目前僅記錄日誌。未來可連接到 AutoRepair 等自動修復系統。
        """
        logger.info(
            f"調節行動: [{action.action_type.value}] "
            f"{action.description} (priority={action.priority.value})"
        )

    # ─── Phase 3a: GovernanceContext Bridge ───

    def build_context(self) -> GovernanceContext:
        """建立治理上下文快照 — Brain 可讀取的唯讀信號。

        聚合當前健康狀態、診斷摘要、免疫命中率、趨勢等，
        產出 frozen GovernanceContext 供 Brain 注入到 system prompt。

        Returns:
            GovernanceContext: 不可變的治理快照
        """
        # 取得當前健康等級
        services = self._service_monitor.get_all_status()
        telegram = self._get_telegram_status()
        health = self._compute_health(services, telegram)
        tier = health_to_tier(health.value)

        # 症狀摘要
        symptom_count = 0
        critical_symptoms: List[str] = []
        if self._last_diagnostic:
            symptom_count = self._last_diagnostic.symptom_count
            for sym in self._last_diagnostic.symptoms:
                if sym.severity in (
                    SymptomSeverity.SEVERE,
                    SymptomSeverity.CRITICAL,
                ):
                    critical_symptoms.append(sym.message[:60])

        # 趨勢
        trend_data = self.get_trend(hours=1.0)
        trend = trend_data.get("trend", "no_data")
        healthy_ratio = trend_data.get("healthy_ratio", 1.0)

        # 免疫命中率
        immune_status = self._immunity.get_status()
        stats = immune_status.get("stats", {})
        check_count = stats.get("check_count", 0)
        innate_hits = stats.get("innate_hits", 0)
        adaptive_hits = stats.get("adaptive_hits", 0)
        total_hits = innate_hits + adaptive_hits
        immune_hit_rate = (
            total_hits / check_count if check_count > 0 else 0.0
        )

        # Uptime
        uptime = (
            time.time() - self._started_at if self._started_at > 0 else 0.0
        )

        return GovernanceContext(
            health_tier=tier,
            symptom_count=symptom_count,
            critical_symptoms=tuple(critical_symptoms[:5]),
            trend=trend,
            healthy_ratio=healthy_ratio,
            immune_hit_rate=immune_hit_rate,
            innate_defenses=innate_hits,
            adaptive_hits=adaptive_hits,
            uptime_s=uptime,
            snapshot_at=time.time(),
        )

    # ─── Phase 3b: ANIMA Growth Driver ───

    def register_anima_tracker(self, anima_tracker: Any) -> None:
        """註冊 AnimaTracker，讓治理事件能驅動 ANIMA 八元素成長。

        Args:
            anima_tracker: PulseEngine 的 AnimaTracker 實例
        """
        try:
            from .anima_bridge import GovernanceGrowthDriver
            self._growth_driver = GovernanceGrowthDriver(anima_tracker)
            logger.info("Governor: ANIMA GovernanceGrowthDriver registered")
        except Exception as e:
            logger.warning(f"Governor: ANIMA bridge registration failed: {e}")

    # ─── Callbacks ───

    def _on_service_status_change(
        self, name: str, old_status: Any, new_status: Any
    ) -> None:
        """中焦: 服務狀態變化回調。"""
        if new_status == ServiceStatus.UNHEALTHY:
            logger.warning(
                f"中焦信號: [{name}] 變為 unhealthy — "
                f"觸發自動恢復流程"
            )
        elif new_status == ServiceStatus.HEALTHY:
            logger.info(f"中焦信號: [{name}] 恢復健康")
            # 自動 resolve 該服務相關的未解決事件
            resolution = f"服務 {name} 已恢復健康"
            svc_symptom = f"service_{name}_unhealthy"
            count = self._immunity.resolve_by_symptom(svc_symptom, resolution)
            # 如果有服務恢復，也嘗試 resolve system_degraded/critical
            if count > 0:
                self._immunity.resolve_by_symptom(
                    "system_degraded", resolution
                )
                self._immunity.resolve_by_symptom(
                    "system_critical", resolution
                )
                self._immunity.save()

    # ─── Subsystem Access (供 server.py 使用) ───

    @property
    def telegram_guard(self) -> Optional[TelegramPollingGuard]:
        return self._telegram_guard

    @property
    def service_monitor(self) -> ServiceHealthMonitor:
        return self._service_monitor

    @property
    def perception(self) -> PerceptionEngine:
        return self._perception

    @property
    def regulation(self) -> RegulationEngine:
        return self._regulation

    @property
    def immunity(self) -> ImmunityEngine:
        return self._immunity

    @property
    def last_diagnostic(self) -> Optional[DiagnosticReport]:
        return self._last_diagnostic
