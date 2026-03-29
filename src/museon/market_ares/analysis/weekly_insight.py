"""Market Ares — 每週洞察生成

判斷本週是否有事，有事才呼叫 LLM 生成洞察（Sonnet）。
無事則用模板填充（零 token）。
"""

from __future__ import annotations

import logging

from museon.market_ares.config import (
    EVENT_THRESHOLD_ENERGY_DELTA,
    EVENT_THRESHOLD_STATE_CHANGE_PCT,
)
from museon.market_ares.storage.models import WeeklySnapshot

logger = logging.getLogger(__name__)


def is_eventful_week(snapshot: WeeklySnapshot, prev: WeeklySnapshot | None) -> bool:
    """判斷本週是否值得生成 LLM 洞察"""
    if snapshot.is_turning_point:
        return True

    if not prev:
        return True  # 第一週一定要

    # 滲透率變化 > 2%
    cur_pen = snapshot.business_metrics.get("penetration_rate", 0)
    prev_pen = prev.business_metrics.get("penetration_rate", 0)
    if abs(cur_pen - prev_pen) > 0.02:
        return True

    # NPS 變化 > 10
    cur_nps = snapshot.business_metrics.get("nps", 0)
    prev_nps = prev.business_metrics.get("nps", 0)
    if abs(cur_nps - prev_nps) > 10:
        return True

    # 有競爭者行動
    if snapshot.competitor_actions:
        return True

    # 有環境事件
    if snapshot.events:
        return True

    return False


def generate_static_insight(snapshot: WeeklySnapshot, prev: WeeklySnapshot | None) -> str:
    """靜態洞察（零 token）——無事件週用"""
    m = snapshot.business_metrics
    pen = m.get("penetration_rate", 0) * 100
    fans = m.get("fan_ratio", 0) * 100
    nps = m.get("nps", 0)

    if pen < 1:
        return "市場仍在觀望階段，策略尚未觸及主流群體。"
    elif pen < 10:
        return f"策略滲透率 {pen:.1f}%，正在早期採用者間擴散。保持策略一致性。"
    elif pen < 30:
        return f"滲透率 {pen:.1f}%，已跨越早期市場。鐵粉比例 {fans:.1f}%，NPS {nps:.0f}。持續擴散中。"
    elif pen < 60:
        return f"滲透率 {pen:.1f}%，進入主流市場。口碑效應開始發揮作用。"
    else:
        return f"滲透率 {pen:.1f}%，市場趨近飽和。關注鐵粉維護和競爭防禦。"


def build_insight_prompt(snapshot: WeeklySnapshot, prev: WeeklySnapshot | None, city: str, strategy: str) -> str:
    """為 LLM 準備洞察 prompt（Sonnet 用）"""
    m = snapshot.business_metrics
    sd = m.get("state_distribution", {})

    prev_data = ""
    if prev:
        pm = prev.business_metrics
        prev_data = f"""上週數據：
- 滲透率：{pm.get('penetration_rate', 0)*100:.1f}%
- 鐵粉比例：{pm.get('fan_ratio', 0)*100:.1f}%
- NPS：{pm.get('nps', 0):.0f}
- 營收指數：{pm.get('revenue_index', 0):.0f}"""

    events_text = ""
    if snapshot.events:
        events_text = "本週事件：" + "、".join(e.get("name", "") for e in snapshot.events)

    competitors_text = ""
    if snapshot.competitor_actions:
        competitors_text = "競爭者動態：" + "、".join(
            f"{c.get('competitor', '')}採取{c.get('type', '')}" for c in snapshot.competitor_actions
        )

    return f"""你是市場分析師。請用 2-3 句白話文分析本週的市場變化。
不要用術語，中小企業主要看得懂。

城市：{city}
策略：{strategy}
第 {snapshot.week} 週

本週數據：
- 滲透率：{m.get('penetration_rate', 0)*100:.1f}%
- 鐵粉比例：{m.get('fan_ratio', 0)*100:.1f}%
- NPS：{m.get('nps', 0):.0f}
- 營收指數：{m.get('revenue_index', 0):.0f}
- 狀態分布：未觸及{sd.get('unaware',0)*100:.0f}% | 注意到{sd.get('aware',0)*100:.0f}% | 考慮中{sd.get('considering',0)*100:.0f}% | 已決策{sd.get('decided',0)*100:.0f}% | 鐵粉{sd.get('loyal',0)*100:.0f}% | 抗拒{sd.get('resistant',0)*100:.0f}%
{prev_data}
{events_text}
{competitors_text}
{"⚡ 本週是關鍵轉折點" if snapshot.is_turning_point else ""}

直接輸出洞察文字，不要加標題或前綴。"""
