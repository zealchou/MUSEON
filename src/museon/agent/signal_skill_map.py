"""Signal-Skill Mapping — 訊號到 Skill 的靜態映射表.

定義每種使用者狀態訊號應該推薦哪些 Skill。
L4 訊號分析器用此表生成 suggested_skills。
"""

SIGNAL_SKILL_MAP = {
    "decision_anxiety": ["roundtable", "master-strategy", "xmodel"],
    "stuck_point": ["xmodel", "dharma", "meta-learning"],
    "emotional_intensity": ["resonance", "dharma"],
    "relationship_dynamic": ["shadow", "ssa-consultant"],
    "market_business": ["market-core", "business-12", "ssa-consultant"],
    "growth_seeking": ["meta-learning", "dse", "xmodel"],
    "planning_mode": ["master-strategy", "pdeif", "plan-engine"],
}

SIGNAL_DESCRIPTIONS = {
    "decision_anxiety": "決策焦慮（猶豫、兩難、怕做錯）",
    "stuck_point": "卡點（做不到、不知道怎麼辦）",
    "emotional_intensity": "情緒強度（壓力、焦慮、興奮）",
    "relationship_dynamic": "人際動態（他說她說、被操控）",
    "market_business": "商業/市場問題（報價、營收、競爭）",
    "growth_seeking": "成長渴望（想學、想突破）",
    "planning_mode": "規劃模式（計畫、策略、佈局）",
}


def get_suggested_skills(signals: dict, top_n: int = 5) -> list:
    """根據活躍訊號推薦 Skill（按訊號強度加權排序）."""
    skill_scores = {}
    for signal_name, info in signals.items():
        strength = info.get("strength", 0) if isinstance(info, dict) else float(info)
        if strength < 0.3:
            continue
        for skill in SIGNAL_SKILL_MAP.get(signal_name, []):
            skill_scores[skill] = skill_scores.get(skill, 0) + strength
    sorted_skills = sorted(skill_scores.items(), key=lambda x: x[1], reverse=True)
    return [s[0] for s in sorted_skills[:top_n]]
