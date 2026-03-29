"""Market Ares — 全域設定"""

from pathlib import Path

# ═══════════════════════ 路徑 ═══════════════════════
MUSEON_ROOT = Path.home() / "MUSEON"
MARKET_ARES_DATA = MUSEON_ROOT / "data" / "darwin"
MARKET_ARES_DB = MARKET_ARES_DATA / "darwin.db"

# ═══════════════════════ 八方位 ═══════════════════════
PRIMALS = ("天", "風", "水", "山", "地", "雷", "火", "澤")

PRIMAL_CYCLE_ORDER = ("天", "風", "水", "山", "地", "雷", "火", "澤")
"""順時針循環：天→風→水→山→地→雷→火→澤→天"""

PRIMAL_AXIS_PAIRS = (
    ("天", "地"),
    ("風", "雷"),
    ("火", "水"),
    ("山", "澤"),
)
"""四條對軸"""

# ═══════════════════════ 能量值域 ═══════════════════════
ENERGY_MIN = -4.0
ENERGY_MAX = 4.0
REVERSAL_THRESHOLD = 3.5  # |值| 超過此閾值，反轉壓力急劇增大

# ═══════════════════════ 模擬參數 ═══════════════════════
SIMULATION_WEEKS = 52
MAX_ROUNDS = 6  # 自駕模式最多跑幾輪

# 三股力量的預設係數
STRATEGY_SENSITIVITY_BASE = 0.15
SOCIAL_CONTAGION_BASE_RATE = 0.02
OSCILLATION_K = 0.08  # 阻尼振盪彈性係數
OSCILLATION_DAMPING = 0.15

# SIR 狀態轉移
AWARENESS_STATES = (
    "unaware",
    "aware",
    "considering",
    "decided",
    "loyal",
    "resistant",
)

# ═══════════════════════ 聚類 ═══════════════════════
ARCHETYPE_MIN = 64
ARCHETYPE_MAX = 512

# ═══════════════════════ LLM ═══════════════════════
INSIGHT_MODEL = "claude-sonnet-4-6"
REPORT_MODEL = "claude-opus-4-6"

# ═══════════════════════ 事件判斷閾值 ═══════════════════════
EVENT_THRESHOLD_ENERGY_DELTA = 0.5  # 能量變化超過此值才算「有事」
EVENT_THRESHOLD_STATE_CHANGE_PCT = 0.08  # 原型狀態遷移超過 8% 才算「有事」
