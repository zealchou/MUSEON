"""OKR Router — 純 Python 關鍵字路由.

優先順序：
1. 指令偵測（/thunder 等）→ confidence 1.0
2. 後續對話偵測（短訊息 + 指示詞）→ 留在當前部門 0.8
3. 關鍵字評分 → 最高分部門 0.4~0.9
4. 預設 → core 0.3

依據 MULTI_AGENT_BDD_SPEC §3 實作。
"""

from typing import Dict, List, Tuple

from museon.multiagent.department_config import (
    FLYWHEEL_ORDER,
    get_all_departments,
)

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

CONFIDENCE_COMMAND = 1.0
CONFIDENCE_FOLLOWUP = 0.8
CONFIDENCE_DEFAULT = 0.3
FOLLOWUP_MAX_LEN = 15       # 後續對話最大字元數
SOFT_ROUTE_SCORE = 0.25     # 每命中一關鍵字 +0.25

# 後續對話指示詞
_FOLLOWUP_INDICATORS = frozenset({
    "然後", "接著", "還有", "好的", "嗯", "對",
    "繼續", "ok", "OK", "好", "是", "對的",
})

# 指令前綴 → dept_id（支援中英文）
_COMMAND_MAP: Dict[str, str] = {}


def _build_command_map() -> None:
    """建立 /指令 → dept_id 映射."""
    for dept_id in get_all_departments():
        _COMMAND_MAP[f"/{dept_id}"] = dept_id
    # 中文單詞指令
    _CN_MAP = {
        "雷": "thunder", "火": "fire", "澤": "lake", "天": "heaven",
        "風": "wind", "水": "water", "山": "mountain", "地": "earth",
        "核心": "core", "目標": "okr",
    }
    for cn, dept_id in _CN_MAP.items():
        _COMMAND_MAP[f"/{cn}"] = dept_id


_build_command_map()


# ═══════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════


def route(message: str, current_dept: str = "core") -> Tuple[str, float]:
    """路由訊息至部門.

    Returns:
        (dept_id, confidence)
    """
    text = message.strip()

    # 1. 指令偵測
    first_token = text.split()[0].lower() if text else ""
    if first_token in _COMMAND_MAP:
        return _COMMAND_MAP[first_token], CONFIDENCE_COMMAND

    # 2. 後續對話偵測
    if len(text) <= FOLLOWUP_MAX_LEN and current_dept != "core":
        for indicator in _FOLLOWUP_INDICATORS:
            if indicator in text:
                return current_dept, CONFIDENCE_FOLLOWUP

    # 3. 關鍵字評分
    best_dept = "core"
    best_score = 0
    depts = get_all_departments()

    for dept_id, dept in depts.items():
        score = 0
        for kw in dept.keywords:
            if kw in text:
                score += 1
        if score > best_score:
            best_score = score
            best_dept = dept_id

    if best_score > 0:
        # confidence: 1 hit=0.4, 2 hits=0.6, 3+=0.9
        if best_score >= 3:
            confidence = 0.9
        elif best_score == 2:
            confidence = 0.6
        else:
            confidence = 0.4
        return best_dept, confidence

    # 4. 預設 → core
    return "core", CONFIDENCE_DEFAULT


def soft_route(message: str) -> Dict[str, float]:
    """回傳飛輪八部門的分數（用於 Trait Blend）.

    每命中一個關鍵字 +0.25，上限 1.0。
    """
    text = message.strip()
    scores: Dict[str, float] = {}
    depts = get_all_departments()

    for dept_id in FLYWHEEL_ORDER:
        dept = depts[dept_id]
        hit_count = sum(1 for kw in dept.keywords if kw in text)
        scores[dept_id] = min(1.0, hit_count * SOFT_ROUTE_SCORE)

    return scores
