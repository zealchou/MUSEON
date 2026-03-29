"""Market Ares — 代駕模式策略優化器

在 3 輪模擬之間，分析結果並優化策略。
"""

from __future__ import annotations

import json
import logging

from museon.market_ares.storage.models import StrategyVector, WeeklySnapshot

logger = logging.getLogger(__name__)


def analyze_round_result(snapshots: list[WeeklySnapshot]) -> dict:
    """分析一輪模擬結果，產出優化建議的素材"""
    final = snapshots[-1].business_metrics
    mid = snapshots[25].business_metrics if len(snapshots) > 25 else snapshots[-1].business_metrics

    # 狀態分布分析
    final_dist = final.get("state_distribution", {})
    resistant_ratio = final_dist.get("resistant", 0)
    loyal_ratio = final_dist.get("loyal", 0)
    unaware_ratio = final_dist.get("unaware", 0)

    # 轉折點分析
    turning_weeks = [s.week for s in snapshots if s.is_turning_point]

    # 問題診斷
    issues = []
    if unaware_ratio > 0.3:
        issues.append("觸及率不足：超過 30% 的市場未被觸及，策略曝光力度不夠")
    if resistant_ratio > 0.2:
        issues.append("抗拒率過高：超過 20% 的市場轉為抗拒，策略可能觸痛了某些群體")
    if loyal_ratio < 0.05:
        issues.append("鐵粉轉化不足：忠誠客戶比例低於 5%，缺乏深度連結")
    if len(turning_weeks) < 3:
        issues.append("市場反應平淡：轉折點過少，策略衝擊力不足")
    if final.get("nps", 0) < 0:
        issues.append("口碑為負：反對聲量超過支持聲量")

    return {
        "penetration": round(final.get("penetration_rate", 0) * 100, 1),
        "fans": round(loyal_ratio * 100, 1),
        "nps": round(final.get("nps", 0), 0),
        "revenue_index": round(final.get("revenue_index", 0), 0),
        "resistant_pct": round(resistant_ratio * 100, 1),
        "turning_points": turning_weeks,
        "issues": issues,
        "mid_penetration": round(mid.get("penetration_rate", 0) * 100, 1),
    }


def build_optimization_prompt(
    round_num: int,
    analysis: dict,
    original_strategy: StrategyVector,
    prev_analyses: list[dict] | None = None,
) -> str:
    """產出策略優化 prompt（Opus 用）"""
    issues_text = "\n".join(f"  - {issue}" for issue in analysis["issues"]) if analysis["issues"] else "  無明顯問題"

    prev_text = ""
    if prev_analyses:
        for i, pa in enumerate(prev_analyses):
            prev_text += f"\n第 {i+1} 輪結果：滲透 {pa['penetration']}%, NPS {pa['nps']}, 問題：{', '.join(pa['issues'][:2])}"

    return f"""你是 MUSEON 的策略優化引擎。以下是第 {round_num} 輪模擬的結果。

策略：{original_strategy.specific}
城市：{original_strategy.city}

本輪結果：
- 最終滲透率：{analysis['penetration']}%
- 鐵粉比例：{analysis['fans']}%
- NPS：{analysis['nps']}
- 營收指數：{analysis['revenue_index']}
- 抗拒比例：{analysis['resistant_pct']}%
- 半年(W26)滲透率：{analysis['mid_penetration']}%
- 轉折週：{analysis['turning_points']}

問題診斷：
{issues_text}
{prev_text}

當前策略向量（八方位刺激強度）：
{json.dumps(original_strategy.impact.to_dict(), ensure_ascii=False)}

請基於商模十二力分析和結果數據，建議：
1. 哪些方位的刺激要加強、哪些要減弱
2. 新的策略向量（八方位 -1~+1）
3. 一句話說明調整理由

回覆 JSON 格式：
{{
  "adjusted_impact": {{"天": 0.3, "風": 0.5, ...}},
  "reasoning": "...",
  "specific_actions": ["行動1", "行動2", "行動3"]
}}"""
