"""ANIMA Schema Registry — 欄位定義的 Single Source of Truth.

所有模組存取 ANIMA_MC/ANIMA_USER/drift_baseline 欄位時，
應透過此模組的常數或輔助方法，而非硬編碼字串。

DSE 第一性原理：消滅魔術字串。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# ANIMA_MC 欄位名常數
# ═══════════════════════════════════════════

class MC:
    """ANIMA_MC.json 欄位名定義."""

    # 頂層
    IDENTITY = "identity"
    SELF_AWARENESS = "self_awareness"
    PERSONALITY = "personality"
    CAPABILITIES = "capabilities"
    EVOLUTION = "evolution"
    MEMORY_SUMMARY = "memory_summary"
    BOSS = "boss"
    CEREMONY = "ceremony"
    EIGHT_PRIMALS = "eight_primal_energies"  # ★ 正式名稱
    VITA_THRESHOLDS = "_vita_triggered_thresholds"

    # identity 子欄位
    class Identity:
        NAME = "name"
        BIRTH_DATE = "birth_date"
        GROWTH_STAGE = "growth_stage"
        DAYS_ALIVE = "days_alive"
        NAMING_DONE = "naming_ceremony_completed"

    # self_awareness 子欄位
    class SelfAwareness:
        WHO_AM_I = "who_am_i"
        PURPOSE = "my_purpose"
        WHY_EXIST = "why_i_exist"
        EXPRESSION_STYLE = "expression_style"

    # evolution 子欄位
    class Evolution:
        STAGE = "current_stage"
        ITERATION_COUNT = "iteration_count"
        PAUSED = "paused"
        PAUSED_REASON = "paused_reason"
        PAUSED_AT = "paused_at"
        RESUMED_AT = "resumed_at"
        RESUMED_REASON = "resumed_reason"
        L3_MATCH_SCORE = "l3_match_score"
        L3_MATCH_UPDATED = "l3_match_updated"

    # capabilities 子欄位
    class Capabilities:
        LOADED_SKILLS = "loaded_skills"
        FORGED_SKILLS = "forged_skills"
        SKILL_PROFICIENCY = "skill_proficiency"

    # memory_summary 子欄位
    class MemorySummary:
        TOTAL_INTERACTIONS = "total_interactions"
        SESSIONS_COUNT = "sessions_count"
        KNOWLEDGE_CRYSTALS = "knowledge_crystals"


# ═══════════════════════════════════════════
# ANIMA_USER 欄位名常數
# ═══════════════════════════════════════════

class USER:
    """ANIMA_USER.json 欄位名定義."""

    EIGHT_PRIMALS = "eight_primals"
    SEVEN_LAYERS = "seven_layers"
    PROFILE = "profile"
    RELATIONSHIP = "relationship"

    # seven_layers 子欄位
    class Layers:
        L1_FACTS = "L1_facts"
        L2_PERSONALITY = "L2_personality"
        L3_DECISION = "L3_decision_pattern"
        L4_INTERACTION = "L4_interaction_rings"
        L5_PREFERENCE = "L5_preference_crystals"
        L6_COMMUNICATION = "L6_communication_style"
        L7_CONTEXT = "L7_context_roles"

    # L6 子欄位
    class CommStyle:
        DETAIL_LEVEL = "detail_level"
        EMOJI_USAGE = "emoji_usage"
        LANGUAGE_MIX = "language_mix"
        AVG_MSG_LENGTH = "avg_msg_length"
        TONE = "tone"
        QUESTION_STYLE = "question_style"

    # 隱藏緩衝欄位
    class Internal:
        PREF_BUFFER = "_pref_buffer"
        TONE_HISTORY = "_tone_history"
        RC_CALIBRATION = "_rc_calibration"


# ═══════════════════════════════════════════
# Drift Baseline 欄位名常數
# ═══════════════════════════════════════════

class DRIFT:
    """drift_baseline.json 欄位名定義."""

    TAKEN_AT = "taken_at"
    MC_PRIMALS = "mc_primals"
    MC_EXPRESSION = "mc_expression"
    USER_PRIMALS = "user_primals"
    USER_L5 = "user_L5"
    USER_L6 = "user_L6"
    USER_L7 = "user_L7"


# ═══════════════════════════════════════════
# PULSE.md 區段名常數
# ═══════════════════════════════════════════

class PULSE:
    """PULSE.md 區段標記定義."""

    GROWTH_REFLECTION = "## 🌊 成長反思"
    TODAY_OBSERVATION = "## 🔭 今日觀察"
    GROWTH_TRACK = "## 🌱 成長軌跡"
    RELATIONSHIP_JOURNAL = "## 💝 關係日誌"
    TODAY_STATUS = "## 📊 今日狀態"


# ═══════════════════════════════════════════
# 安全存取輔助函數
# ═══════════════════════════════════════════

def get_nested(
    data: Dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    """安全的巢狀 key 存取（取代多層 .get() 鏈）.

    用法:
        get_nested(anima_mc, MC.IDENTITY, MC.Identity.DAYS_ALIVE, default=0)
        get_nested(anima_user, USER.SEVEN_LAYERS, USER.Layers.L5_PREFERENCE, default=[])
    """
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def set_nested(
    data: Dict[str, Any],
    *keys: str,
    value: Any,
) -> None:
    """安全的巢狀 key 寫入.

    用法:
        set_nested(anima_mc, MC.IDENTITY, MC.Identity.DAYS_ALIVE, value=3)
    """
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    """安全載入 JSON 檔案."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"載入失敗: {path} — {e}")
        return None


def save_json(path: Path, data: Dict[str, Any]) -> bool:
    """安全寫入 JSON 檔案（保留格式）."""
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception as e:
        logger.error(f"寫入失敗: {path} — {e}")
        return False
