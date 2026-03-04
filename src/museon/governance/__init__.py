"""MUSEON 運行時治理層 (Runtime Governance Layer)

三焦式分層治理架構：
- 下焦 (Lower Burner): 進程級 — PID Lock、端口監控、Singleton 保證 (5-10s)
- 中焦 (Middle Burner): 服務級 — Channel Health、Docker 服務存活 (30-60s)
- 上焦 (Upper Burner): 系統級 — 整體健康分數、趨勢分析、異穩態節律 (5-15min)

設計原則：
- 察覺 → 調節 → 免疫 (PCT: 參考信號 − 知覺信號 = 誤差)
- 約束式而非規則式 (定義邊界，不定義行為)
- 治未病 (預測式治理，在問題發生前介入)

Milestone #001 — 2026-03-03
"""

from .anima_bridge import GovernanceGrowthDriver
from .context import GovernanceContext, HealthTier, health_to_tier
from .gateway_lock import GatewayLock
from .governor import Governor
from .immunity import ImmunityEngine
from .perception import PerceptionEngine
from .pid_alive import is_pid_alive
from .regulation import RegulationEngine
from .service_health import ServiceHealthMonitor
from .telegram_guard import TelegramPollingGuard

__all__ = [
    "GovernanceContext",
    "GovernanceGrowthDriver",
    "GatewayLock",
    "Governor",
    "HealthTier",
    "ImmunityEngine",
    "PerceptionEngine",
    "is_pid_alive",
    "health_to_tier",
    "RegulationEngine",
    "ServiceHealthMonitor",
    "TelegramPollingGuard",
]
