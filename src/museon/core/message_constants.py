"""統一訊息分類常數源。

所有模組的「簡單訊息」判斷常數從此處取用，
避免 brain / signal_lite / metacognition 各自硬編碼。
"""

# ── 簡單訊息長度閾值 ──
SIMPLE_MESSAGE_LENGTH = 15       # brain._is_simple 使用（< 此值視為簡單）
SIGNAL_LENGTH_SHORT = 30         # signal_lite FAST_LOOP 閾值（<= 此值）
SIGNAL_LENGTH_LONG = 300         # signal_lite SLOW_LOOP 閾值（> 此值）

# ── 簡單訊息排除關鍵字（含這些 → 不算簡單）──
SIMPLE_EXCLUDE_KEYWORDS = frozenset({
    "/", "分析", "報告", "計畫", "策略", "研究", "評估",
})

# ── 簡單問候/確認（直接跳過審查，零成本）──
SIMPLE_GREETINGS = frozenset({
    "你好", "嗨", "哈囉", "早安", "晚安", "午安",
    "好的", "了解", "收到", "謝謝", "感謝", "讚",
    "拜拜", "再見", "掰掰", "OK", "ok", "嗯",
    "對", "沒錯", "是", "好", "行",
})

# ── Loop 類型常數 ──
LOOP_FAST = "FAST_LOOP"
LOOP_SLOW = "SLOW_LOOP"
LOOP_EXPLORATION = "EXPLORATION_LOOP"
