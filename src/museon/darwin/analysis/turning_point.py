"""Market Ares — 關鍵轉折點偵測與分析"""

from __future__ import annotations

from museon.darwin.storage.models import WeeklySnapshot


def detect_turning_points(snapshots: list[WeeklySnapshot]) -> list[int]:
    """偵測所有轉折週"""
    return [s.week for s in snapshots if s.is_turning_point]


def classify_turning_point(snapshot: WeeklySnapshot, prev: WeeklySnapshot | None) -> str:
    """分類轉折點類型"""
    if not prev:
        return "launch"  # 策略啟動

    cur = snapshot.business_metrics
    prv = prev.business_metrics

    pen_delta = cur.get("penetration_rate", 0) - prv.get("penetration_rate", 0)
    nps_delta = cur.get("nps", 0) - prv.get("nps", 0)

    if pen_delta > 0.05:
        return "breakthrough"  # 突破——大量人群狀態躍遷
    elif pen_delta < -0.03:
        return "regression"  # 退化——人群回流或抗拒
    elif nps_delta > 15:
        return "reputation_surge"  # 口碑爆發
    elif nps_delta < -15:
        return "reputation_crash"  # 口碑崩盤
    elif snapshot.competitor_actions:
        return "competitive_shock"  # 競爭衝擊
    else:
        return "structural_shift"  # 結構性轉變


def build_turning_point_summary(snapshots: list[WeeklySnapshot]) -> list[dict]:
    """產出轉折點摘要"""
    results = []
    for i, s in enumerate(snapshots):
        if not s.is_turning_point:
            continue
        prev = snapshots[i - 1] if i > 0 else None
        tp_type = classify_turning_point(s, prev)

        results.append({
            "week": s.week,
            "type": tp_type,
            "penetration": round(s.business_metrics.get("penetration_rate", 0) * 100, 1),
            "nps": round(s.business_metrics.get("nps", 0), 0),
            "insight": s.insight,
        })

    return results
