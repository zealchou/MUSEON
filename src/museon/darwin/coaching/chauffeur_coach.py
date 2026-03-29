"""Market Ares — 代駕模式教練引導

融合 SSA 12 步驟 + 麥肯錫假設驅動 + BCG 事實基礎 + One Muse 一次一問。
三層結構：目標錨定(2-3題) → 現況盤點(3-4題) → 約束條件(2-3題)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from museon.darwin.crawler.tw_demographics import list_available_cities


@dataclass
class ChauffeurState:
    """代駕模式教練引導的進度狀態"""

    step: int = 0
    layer: str = "目標錨定"  # 目標錨定 / 現況盤點 / 約束條件

    # 第一層：目標錨定
    city: str = ""
    desired_outcome: str = ""   # 52 週後的畫面
    priority: str = ""          # 優先順序
    minimum_acceptable: str = ""  # 最低可接受目標

    # 第二層：現況盤點
    current_revenue: str = ""   # 當前營收結構
    customer_source: str = ""   # 客戶來源
    assets: str = ""            # 現有資源
    stuck_point: str = ""       # 主觀卡點

    # 第三層：約束條件
    never_do: str = ""          # 絕對不做的事
    weekly_hours: str = ""      # 每週可投入時間
    marketing_budget: str = ""  # 行銷預算

    confirmed: bool = False


# 三層問題定義
LAYERS = {
    "目標錨定": [
        {
            "question": "你想在哪個城市拓展事業？",
            "field": "city",
            "method": "BCG 事實基礎",
        },
        {
            "question": "你希望 52 週後，你的事業變成什麼樣子？\n（不用完美，給我一個畫面就好）",
            "field": "desired_outcome",
            "method": "SSA 痛點挖掘 + One Muse 畫面感",
        },
        {
            "question": "如果模擬顯示最理想的目標很難達到，你能接受的最低目標是什麼？",
            "field": "minimum_acceptable",
            "method": "麥肯錫 邊界定義",
        },
    ],
    "現況盤點": [
        {
            "question": "目前月營收大概多少？主要來自什麼？\n（幾個客戶 × 客單價多少 = 月營收）",
            "field": "current_revenue",
            "method": "BCG 事實基礎（要數字不要感覺）",
        },
        {
            "question": "這些客戶是怎麼來的？",
            "field": "customer_source",
            "method": "SSA 關係盤分析",
        },
        {
            "question": "除了現有客戶，你手上還有什麼資源？\n（名單、社群、品牌知名度、合作關係、專業認證...任何你覺得是資產的）",
            "field": "assets",
            "method": "SSA 籌碼盤點",
        },
        {
            "question": "你覺得目前最卡你的是什麼？\n（不用分析，直覺回答就好）",
            "field": "stuck_point",
            "method": "One Muse 直覺探索",
        },
    ],
    "約束條件": [
        {
            "question": "有沒有什麼是你絕對不做的？\n（比如不想做低價、不想拍影片、不想跑實體活動）",
            "field": "never_do",
            "method": "麥肯錫 邊界定義",
        },
        {
            "question": "每週你能投入多少時間在新客開發上？",
            "field": "weekly_hours",
            "method": "BCG 80/20 聚焦",
        },
        {
            "question": "你願意投入多少預算在行銷上？（月）",
            "field": "marketing_budget",
            "method": "BCG 事實基礎",
        },
    ],
}

_ALL_STEPS = []
for layer_name, questions in LAYERS.items():
    for q in questions:
        _ALL_STEPS.append({**q, "layer": layer_name})


def get_current_question(state: ChauffeurState) -> Optional[dict]:
    """取得當前應該問的問題"""
    if state.step >= len(_ALL_STEPS):
        return None

    step_config = _ALL_STEPS[state.step]
    layer = step_config["layer"]
    method = step_config["method"]

    # 特殊處理城市問題
    if step_config["field"] == "city":
        cities = "、".join(list_available_cities())
        hint = f"目前支援：{cities}"
    else:
        hint = f"（{method}）"

    return {
        "question": step_config["question"],
        "hint": hint,
        "layer": layer,
        "step": state.step + 1,
        "total_steps": len(_ALL_STEPS) + 1,
    }


def process_answer(state: ChauffeurState, answer: str) -> dict:
    """處理使用者的回答"""
    if state.step >= len(_ALL_STEPS):
        if answer.strip() in ("好", "對", "OK", "ok", "是", "確認", "沒問題", "Y", "y"):
            state.confirmed = True
            return {"valid": True, "confirmed": True}
        return {"valid": True, "next_question": get_current_question(state)}

    step_config = _ALL_STEPS[state.step]
    field = step_config["field"]
    setattr(state, field, answer.strip())
    state.layer = step_config["layer"]
    state.step += 1

    if state.step >= len(_ALL_STEPS):
        summary = build_summary(state)
        return {
            "valid": True,
            "next_question": {
                "question": f"收到，讓我確認一下：\n\n{summary}\n\n這些資訊正確嗎？",
                "hint": "回覆「好」確認，或告訴我要修改什麼。",
                "layer": "確認",
                "step": len(_ALL_STEPS) + 1,
                "total_steps": len(_ALL_STEPS) + 1,
            },
            "summary": summary,
        }

    return {"valid": True, "next_question": get_current_question(state)}


def build_summary(state: ChauffeurState) -> str:
    """產出結構化摘要"""
    return f"""【目標】
城市：{state.city}
期望結果：{state.desired_outcome}
最低可接受：{state.minimum_acceptable}

【現況】
月營收結構：{state.current_revenue}
客戶來源：{state.customer_source}
現有資源：{state.assets}
卡點：{state.stuck_point}

【約束】
不做的事：{state.never_do}
每週可投入：{state.weekly_hours}
月行銷預算：{state.marketing_budget}"""


def generate_strategy_design_prompt(state: ChauffeurState) -> str:
    """產出策略設計 prompt，交給 LLM（Opus）設計策略

    此 prompt 會觸發 PDEIF + xmodel + business-12 + brand-builder 的整合分析。
    """
    summary = build_summary(state)

    return f"""你是 MUSEON 的策略設計引擎。以下是客戶的完整背景資料。

{summary}

請依序執行：
1. 商模十二力快速健檢：從以上資訊判斷 12 力中哪些偏弱
2. PDEIF 逆熵設計：從「{state.desired_outcome}」反推行動路徑
3. xmodel 破框：生成 3-5 組不同策略候選

每組策略需包含：
- 策略名稱（白話文）
- 核心行動（3-5 步）
- 對八方位的刺激強度（-1~+1，每個方位）
- 預期見效時間
- 風險評估

輸出 JSON 格式。"""
