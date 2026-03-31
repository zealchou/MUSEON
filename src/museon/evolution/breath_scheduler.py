"""breath_scheduler — Breath Protocol 節律器.

根據今天是週幾，決定跑深呼吸的哪一步。
整合進 Nightly Pipeline 或 cron。
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 預設 MUSEON 根目錄
DEFAULT_WORKSPACE = Path.home() / "MUSEON"

# Day → 說明對照表
_DAY_LABELS = {
    1: "Day 1 (Mon) — 觀察：Inhale",
    2: "Day 2 (Tue) — 觀察：Inhale",
    3: "Day 3 (Wed) — 模式發現：Process",
    4: "Day 4 (Thu) — 模式發現：Process",
    5: "Day 5 (Fri) — 結構診斷：Diagnose",
    6: "Day 6 (Sat) — 精準行動：Exhale",
    7: "Day 7 (Sun) — 休息 + 效果觀察",
}


async def breath_tick(workspace: Path | None = None) -> dict[str, Any]:
    """根據今天是週幾，執行對應的 Breath 步驟.

    Args:
        workspace: MUSEON 根目錄，預設 ~/MUSEON

    Returns:
        dict 含 {day, week_id, step, result}
    """
    if workspace is None:
        workspace = DEFAULT_WORKSPACE

    now = datetime.now()
    day_of_week = now.isoweekday()  # 1=Mon, 7=Sun
    week_id = now.strftime("%Y-w%W")

    day_label = _DAY_LABELS.get(day_of_week, f"Day {day_of_week}")
    logger.info(f"[BreathScheduler] {day_label}，week_id={week_id}")

    result: Any = None
    step = "unknown"

    if day_of_week in (1, 2):  # Mon, Tue — 觀察
        step = "observe"
        from museon.evolution.breath_watcher import collect_observations  # noqa: PLC0415
        result = await collect_observations(workspace)

    elif day_of_week in (3, 4):  # Wed, Thu — 模式發現
        step = "analyze"
        from museon.evolution.breath_analyzer import analyze_patterns  # noqa: PLC0415
        result = await analyze_patterns(workspace, week_id)

    elif day_of_week == 5:  # Fri — 結構診斷
        step = "diagnose"
        from museon.evolution.breath_diagnostician import diagnose  # noqa: PLC0415
        result = await diagnose(workspace, week_id)

    elif day_of_week == 6:  # Sat — 精準行動
        step = "execute"
        from museon.evolution.breath_executor import execute_weekly  # noqa: PLC0415
        result = await execute_weekly(workspace, week_id)

    elif day_of_week == 7:  # Sun — 週報
        step = "retro"
        from museon.evolution.breath_retro import weekly_retro  # noqa: PLC0415
        result = await weekly_retro(workspace, week_id)

    return {
        "day_of_week": day_of_week,
        "day_label": day_label,
        "week_id": week_id,
        "step": step,
        "result": result,
        "timestamp": now.isoformat(),
    }


async def breath_tick_step(
    step: str,
    workspace: Path | None = None,
    week_id: str | None = None,
) -> dict[str, Any]:
    """手動觸發特定步驟（用於測試或補跑）.

    Args:
        step: "observe" | "analyze" | "diagnose" | "execute" | "retro"
        workspace: MUSEON 根目錄
        week_id: 指定週次 ID（預設本週）
    """
    if workspace is None:
        workspace = DEFAULT_WORKSPACE
    if week_id is None:
        week_id = datetime.now().strftime("%Y-w%W")

    logger.info(f"[BreathScheduler] 手動觸發 step={step}, week_id={week_id}")

    if step == "observe":
        from museon.evolution.breath_watcher import collect_observations  # noqa: PLC0415
        result = await collect_observations(workspace)
    elif step == "analyze":
        from museon.evolution.breath_analyzer import analyze_patterns  # noqa: PLC0415
        result = await analyze_patterns(workspace, week_id)
    elif step == "diagnose":
        from museon.evolution.breath_diagnostician import diagnose  # noqa: PLC0415
        result = await diagnose(workspace, week_id)
    elif step == "execute":
        from museon.evolution.breath_executor import execute_weekly  # noqa: PLC0415
        result = await execute_weekly(workspace, week_id)
    elif step == "retro":
        from museon.evolution.breath_retro import weekly_retro  # noqa: PLC0415
        result = await weekly_retro(workspace, week_id)
    else:
        return {"error": f"未知的 step: {step}，合法值: observe|analyze|diagnose|execute|retro"}

    return {
        "step": step,
        "week_id": week_id,
        "result": result,
        "timestamp": datetime.now().isoformat(),
    }
