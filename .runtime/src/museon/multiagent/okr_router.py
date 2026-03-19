"""OKR Router — 純 Python 關鍵字路由.

優先順序：
1. 指令偵測（/thunder 等）→ confidence 1.0
2. 後續對話偵測（短訊息 + 指示詞）→ 留在當前部門 0.8
3. 關鍵字評分 → 最高分部門 0.4~0.9
4. 預設 → core 0.3

依據 MULTI_AGENT_BDD_SPEC §3 實作。
"""

from typing import Dict, List, Optional, Tuple

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


# ═══════════════════════════════════════════
# 八原語 → 部門親和映射（v10.5）
# ═══════════════════════════════════════════

_PRIMAL_DEPT_AFFINITY: Dict[str, Dict[str, float]] = {
    "curiosity":        {"wind": 0.2},          # 風/創新
    "aspiration":       {"heaven": 0.2},         # 天/願景
    "action_power":     {"thunder": 0.2},        # 雷/執行
    "emotion_pattern":  {"lake": 0.15},          # 澤/客戶
    "accumulation":     {"earth": 0.15},         # 地/營運
    "boundary":         {"mountain": 0.15},      # 山/品管
    "relationship_depth": {"lake": 0.15},        # 澤/客戶
    "blindspot":        {"water": 0.1},          # 水/財務
}


def route(
    message: str,
    current_dept: str = "core",
    user_primals: Optional[Dict[str, int]] = None,
) -> Tuple[str, float]:
    """路由訊息至部門.

    Args:
        message: 使用者訊息
        current_dept: 當前部門
        user_primals: 八原語維度 {primal_key: level(0-100)}（可選）

    Returns:
        (dept_id, confidence)
    """
    result = route_extended(message, current_dept, user_primals)
    return result[0], result[1]


def route_extended(
    message: str,
    current_dept: str = "core",
    user_primals: Optional[Dict[str, int]] = None,
) -> Tuple[str, float, List[str]]:
    """路由訊息至部門（擴展版：含輔助部門列表）.

    Returns:
        (primary_dept_id, confidence, auxiliary_dept_ids)
        - confidence > 0.8 → 只啟動主部門
        - 0.5 <= confidence <= 0.8 → 主部門 + 1-2 個輔助
        - confidence < 0.5 → 主部門 + 3-4 個輔助
    """
    text = message.strip()

    # 1. 指令偵測
    first_token = text.split()[0].lower() if text else ""
    if first_token in _COMMAND_MAP:
        return _COMMAND_MAP[first_token], CONFIDENCE_COMMAND, []

    # 2. 後續對話偵測
    if len(text) <= FOLLOWUP_MAX_LEN and current_dept != "core":
        for indicator in _FOLLOWUP_INDICATORS:
            if indicator in text:
                return current_dept, CONFIDENCE_FOLLOWUP, []

    # 3. 關鍵字評分
    best_dept = "core"
    best_score = 0.0
    depts = get_all_departments()

    dept_scores: Dict[str, float] = {}
    for dept_id, dept in depts.items():
        score = 0.0
        for kw in dept.keywords:
            if kw in text:
                score += 1.0
        dept_scores[dept_id] = score

    # 3.5 ★ v10.5 八原語加權
    if user_primals:
        for primal_key, dept_map in _PRIMAL_DEPT_AFFINITY.items():
            level = user_primals.get(primal_key, 0)
            if level > 30:  # 至少有一定強度才加權
                for dept_id, boost in dept_map.items():
                    if dept_id in dept_scores:
                        dept_scores[dept_id] += boost * (level / 100.0)

    # 找最高分
    for dept_id, score in dept_scores.items():
        if score > best_score:
            best_score = score
            best_dept = dept_id

    if best_score > 0:
        # confidence: 1 hit=0.4, 2 hits=0.6, 3+=0.9
        if best_score >= 3:
            confidence = 0.9
        elif best_score >= 2:
            confidence = 0.6
        else:
            confidence = 0.4

        # 決定輔助部門
        auxiliaries = _select_auxiliaries(
            best_dept, confidence, dept_scores,
        )
        return best_dept, confidence, auxiliaries

    # 4. 預設 → core
    return "core", CONFIDENCE_DEFAULT, []


def _select_auxiliaries(
    primary: str,
    confidence: float,
    dept_scores: Dict[str, float],
) -> List[str]:
    """根據信心度選擇輔助部門.

    - confidence > 0.8 → 不需要輔助
    - 0.5 <= confidence <= 0.8 → 1-2 個輔助
    - confidence < 0.5 → 3-4 個輔助
    """
    if confidence > 0.8:
        return []

    # 按分數排序（排除主部門和 okr）
    candidates = sorted(
        [(d, s) for d, s in dept_scores.items()
         if d != primary and d != "okr" and s > 0],
        key=lambda x: x[1],
        reverse=True,
    )

    if confidence >= 0.5:
        max_aux = 2
    else:
        max_aux = 4

    return [d for d, _ in candidates[:max_aux]]


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
