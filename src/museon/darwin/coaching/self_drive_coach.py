"""Market Ares — 自駕模式教練引導

一次一個問題，5-6 題收斂出符合 SMART 原則的策略。
至少要有明確的「期間 + 數字」，其他三項至少一個清晰。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from museon.darwin.crawler.tw_demographics import list_available_cities
from museon.darwin.storage.models import EnergyVector, StrategyVector


@dataclass
class CoachingState:
    """教練引導的進度狀態"""
    step: int = 0
    city: str = ""
    strategy_desc: str = ""
    target_number: str = ""
    target_period: str = ""
    unit_price: str = ""
    existing_base: str = ""
    confirmed: bool = False


# 每一步的問題和驗證規則
STEPS = [
    {
        "question": "你想在哪個城市測試你的策略？",
        "hint": "目前支援：{cities}",
        "field": "city",
        "validate": lambda v, _: v in list_available_cities(),
        "error": "目前還不支援這個城市。可用的有：{cities}",
    },
    {
        "question": "你的策略用一句話描述是什麼？",
        "hint": "例如：「推廣高單價 AI 顧問服務」「開一間特色咖啡廳」",
        "field": "strategy_desc",
        "validate": lambda v, _: len(v) >= 4,
        "error": "描述太短了，至少 4 個字。",
    },
    {
        "question": "你期望在多久內看到什麼結果？\n（請給我一個時間和一個數字，例如「12 個月內簽到 20 個客戶」）",
        "hint": "時間 + 數字是必填的。",
        "field": "target_number",
        "validate": lambda v, _: any(c.isdigit() for c in v),
        "error": "需要至少包含一個數字。例如「6 個月內月營收到 30 萬」。",
    },
    {
        "question": "這個服務/產品的單價大概多少？",
        "hint": "如果是月費型的，告訴我月費。",
        "field": "unit_price",
        "validate": lambda v, _: True,  # 選填
        "error": "",
    },
    {
        "question": "你目前有多少既有客戶或名單？",
        "hint": "包含潛在客戶、Line 群、Email 名單、社群追蹤者都算。",
        "field": "existing_base",
        "validate": lambda v, _: True,  # 選填
        "error": "",
    },
]


def get_current_question(state: CoachingState) -> Optional[dict]:
    """取得當前應該問的問題"""
    if state.step >= len(STEPS):
        return None

    step_config = STEPS[state.step]
    question = step_config["question"]

    # 替換動態內容
    if "{cities}" in step_config.get("hint", ""):
        cities = "、".join(list_available_cities())
        hint = step_config["hint"].format(cities=cities)
    else:
        hint = step_config.get("hint", "")

    return {
        "question": question,
        "hint": hint,
        "step": state.step + 1,
        "total_steps": len(STEPS) + 1,  # +1 for confirmation
    }


def process_answer(state: CoachingState, answer: str) -> dict:
    """處理使用者的回答

    Returns:
        {"valid": bool, "error": str, "next_question": dict|None, "summary": str|None}
    """
    if state.step >= len(STEPS):
        # 確認階段
        if answer.strip() in ("好", "對", "OK", "ok", "是", "確認", "沒問題", "Y", "y"):
            state.confirmed = True
            return {"valid": True, "next_question": None, "summary": None, "confirmed": True}
        else:
            # 使用者想修改
            return {"valid": True, "next_question": get_current_question(state), "summary": _build_summary(state)}

    step_config = STEPS[state.step]
    field = step_config["field"]

    # 驗證
    if not step_config["validate"](answer.strip(), state):
        cities = "、".join(list_available_cities())
        error = step_config["error"].format(cities=cities)
        return {"valid": False, "error": error, "next_question": get_current_question(state)}

    # 存入
    setattr(state, field, answer.strip())
    state.step += 1

    # 檢查是否所有必填都完成
    if state.step >= len(STEPS):
        summary = _build_summary(state)
        return {
            "valid": True,
            "next_question": {
                "question": f"OK，我整理一下——\n\n{summary}\n\n這樣對嗎？有要修正的嗎？",
                "hint": "回覆「好」確認，或告訴我要修改什麼。",
                "step": len(STEPS) + 1,
                "total_steps": len(STEPS) + 1,
            },
            "summary": summary,
        }

    return {"valid": True, "next_question": get_current_question(state)}


def _build_summary(state: CoachingState) -> str:
    """產出策略摘要"""
    parts = [f"在{state.city}，"]

    if state.strategy_desc:
        parts.append(f"透過「{state.strategy_desc}」策略，")

    if state.target_number:
        parts.append(f"目標是{state.target_number}。")

    if state.unit_price:
        parts.append(f"單價約 {state.unit_price}。")

    if state.existing_base:
        parts.append(f"現有基礎：{state.existing_base}。")

    return "".join(parts)


def build_strategy_vector(state: CoachingState) -> StrategyVector:
    """從教練引導結果建構策略向量

    TODO: 用 LLM 分析策略描述，自動填入八方位刺激強度
    目前用預設值
    """
    return StrategyVector(
        impact=EnergyVector(雷=0.6, 火=0.4, 天=0.3, 澤=0.3, 風=0.2, 地=-0.3),
        specific=state.strategy_desc,
        measurable=state.target_number,
        time_bound="52 週",
        city=state.city,
        country="台灣",
    )
