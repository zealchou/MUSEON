"""Signal Keywords — 零 LLM 即時訊號快篩.

用 regex 在 < 5ms 內偵測使用者訊息中的狀態訊號。
L1 主持人在讀取 signal_cache 後，用此模組做即時補充。
L4 的 Haiku 分析是「上一輪」的結果，keyword 快篩是「當下這一輪」的即時反應。
"""

from typing import Dict

SIGNAL_KEYWORDS: Dict[str, list] = {
    "decision_anxiety": [
        "要不要", "該怎麼選", "怎麼決定", "猶豫", "兩難", "怕",
        "不確定", "選擇困難", "做不了決定", "拿不定主意", "糾結",
        "利弊", "取捨", "值不值得",
    ],
    "stuck_point": [
        "卡住", "不知道怎麼辦", "做不到", "走不下去", "沒辦法",
        "困難", "瓶頸", "想不通", "沒有頭緒", "無從下手",
        "搞不定", "解決不了",
    ],
    "emotional_intensity": [
        "煩", "累", "崩潰", "壓力", "心累", "迷茫", "焦慮",
        "開心", "興奮", "感動", "難過", "生氣", "無力",
        "受不了", "快瘋了", "好煩",
    ],
    "relationship_dynamic": [
        "他說", "她說", "對方", "被操控", "不公平", "老闆",
        "同事", "客戶說", "合夥人", "被利用", "勒索",
        "不對等", "欺負",
    ],
    "market_business": [
        "報價", "營收", "成本", "客戶", "競爭", "市場",
        "定價", "毛利", "漲", "跌", "投資", "獲利",
        "業績", "轉換率", "流量",
    ],
    "growth_seeking": [
        "想學", "怎麼學", "提升", "突破", "進步", "成長",
        "學習", "精進", "進階", "升級", "怎麼變強",
    ],
    "planning_mode": [
        "計畫", "策略", "規劃", "佈局", "接下來", "下一步",
        "長期", "短期", "目標", "里程碑", "路線圖",
    ],
}


def quick_signal_scan(text: str) -> Dict[str, float]:
    """< 5ms keyword 掃描，回傳 {signal: strength}.

    每個命中關鍵字 +0.3，上限 1.0。
    """
    if not text:
        return {}
    results = {}
    for signal, keywords in SIGNAL_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            results[signal] = min(1.0, hits * 0.3)
    return results
