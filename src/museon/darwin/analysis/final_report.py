"""Market Ares — 最終戰情報告生成

八章結構的完整分析報告 prompt（Opus 用）。
"""

from __future__ import annotations

import json
import logging

from museon.darwin.analysis.turning_point import build_turning_point_summary
from museon.darwin.storage.models import StrategyVector, WeeklySnapshot

logger = logging.getLogger(__name__)


def build_final_report_prompt(
    snapshots: list[WeeklySnapshot],
    strategy: StrategyVector,
    city: str,
    round_number: int = 1,
) -> str:
    """產出最終報告的 LLM prompt（Opus）"""

    # 收集關鍵數據
    final = snapshots[-1].business_metrics
    first = snapshots[0].business_metrics
    mid = snapshots[25].business_metrics if len(snapshots) > 25 else snapshots[len(snapshots)//2].business_metrics

    tp_summary = build_turning_point_summary(snapshots)

    # 每 4 週的快照摘要
    quarterly = []
    for w in [4, 12, 20, 30, 40, 52]:
        if w <= len(snapshots):
            s = snapshots[w-1]
            m = s.business_metrics
            quarterly.append(f"W{w}: 滲透{m.get('penetration_rate',0)*100:.1f}% NPS:{m.get('nps',0):.0f} Rev:{m.get('revenue_index',0):.0f}")

    # 狀態分布變化
    final_dist = final.get("state_distribution", {})

    return f"""你是 MUSEON 的戰情分析師。請撰寫一份完整的市場策略模擬報告。

語言：繁體中文，白話文，中小企業主看得懂。
格式：用 Markdown，八章結構。

=== 模擬基本資訊 ===
城市：{city}
策略：{strategy.specific}
模擬期間：52 週
第 {round_number} 輪

=== 關鍵數據 ===
最終滲透率：{final.get('penetration_rate',0)*100:.1f}%
最終鐵粉比例：{final.get('fan_ratio',0)*100:.1f}%
最終 NPS：{final.get('nps',0):.0f}
最終營收指數：{final.get('revenue_index',0):.0f}
最終狀態分布：{json.dumps(final_dist, ensure_ascii=False)}

=== 時間軸快照 ===
{chr(10).join(quarterly)}

=== 轉折點 ===
{json.dumps(tp_summary, ensure_ascii=False, indent=2)}

=== 策略向量 ===
{json.dumps(strategy.impact.to_dict(), ensure_ascii=False)}

=== 報告結構（八章，每章必寫）===

第一章：Executive Summary
- 策略成敗判定：用 🟢可行 / 🟡有條件可行 / 🔴不建議
- 最終滲透率和 NPS
- 一句話結論

第二章：52 週演化全景
- 描述策略從觸發→擴散→抗拒→穩態的曲線
- 標出關鍵轉折點及原因

第三章：人群深度分析
- 最先接受的是哪種人（破風者？社群人？）
- 最抗拒的是哪種人（守舊者？）
- 從觀望變成鐵粉的關鍵條件

第四章：商業模式健檢（商模十二力）
- 基於模擬結果，判斷策略在哪些「力」上強、哪些弱
- 重點分析：產品力、成交力、品牌力、社群力

第五章：銷售路徑設計（SSA 顧問式銷售）
- 針對最有機會的群體，設計 3 步成交路徑
- 成交話術建議

第六章：風險與競爭分析
- 策略最大的 3 個風險
- 如果競爭對手降價怎麼辦
- 哪些環境變數最敏感

第七章：創新傳播曲線定位
- 52 週後策略到了 Rogers 曲線的哪個階段
- 下一步需要什麼條件才能進入下一階段

第八章：行動建議
- 立即可做的 3 件事
- 需要調整的策略方向
- 下一輪模擬建議的參數調整"""


def build_report_sections_data(snapshots: list[WeeklySnapshot]) -> dict:
    """為 HTML 報告模板準備結構化數據"""
    final = snapshots[-1].business_metrics
    tp = build_turning_point_summary(snapshots)

    # 判斷成敗
    penetration = final.get("penetration_rate", 0)
    nps = final.get("nps", 0)

    if penetration > 0.3 and nps > 30:
        verdict = "green"
        verdict_text = "可行"
    elif penetration > 0.1 and nps > 0:
        verdict = "yellow"
        verdict_text = "有條件可行"
    else:
        verdict = "red"
        verdict_text = "不建議"

    return {
        "verdict": verdict,
        "verdict_text": verdict_text,
        "final_penetration": round(penetration * 100, 1),
        "final_fans": round(final.get("fan_ratio", 0) * 100, 1),
        "final_nps": round(nps, 0),
        "final_revenue": round(final.get("revenue_index", 0), 0),
        "turning_points": tp,
        "total_turning_points": len(tp),
    }
