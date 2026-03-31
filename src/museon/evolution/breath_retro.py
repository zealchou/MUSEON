"""breath_retro — Breath Protocol 回望層.

每週結束時產出回望報告。
三問：變好了嗎？重複教訓？盲點？
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def weekly_retro(workspace: Path, week_id: str) -> dict[str, Any]:
    """產出週度回望報告.

    Args:
        workspace: MUSEON 根目錄
        week_id: 週次 ID，格式 "YYYY-wNN"

    Returns:
        retro dict，同時寫入 retros/{week_id}.json
    """
    # 讀本週所有資料
    this_week_obs = _load_observations(workspace, week_id)
    this_week_actions = _load_actions(workspace, week_id)

    # 算上週 week_id
    last_week_id = _get_last_week_id(week_id)
    last_week_retro = _load_last_retro(workspace, last_week_id)

    # 三問分析
    q1_result = _analyze_metrics_comparison(workspace, week_id, last_week_retro)
    q2_result = _detect_repeated_lessons(workspace, week_id)
    q3_result = _guess_blind_spots(this_week_obs)

    # 下週重點
    next_week_focus = _derive_next_focus(q1_result, q2_result, q3_result, this_week_actions)

    result: dict[str, Any] = {
        "week_id": week_id,
        "generated_at": datetime.now().isoformat(),
        "observations_count": len(this_week_obs),
        "actions_taken": _summarize_actions(this_week_actions),
        "metrics_comparison": q1_result,
        "repeated_lessons": q2_result,
        "blind_spot_guesses": q3_result,
        "next_week_focus": next_week_focus,
        "red_light": _check_red_lights(q1_result, q2_result, this_week_actions),
    }

    # 寫入 retros 目錄
    output_dir = workspace / "data/_system/breath/retros"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{week_id}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"[BreathRetro] 週報已寫入: {output_path}")

    # 紅燈檢查
    if result["red_light"]:
        logger.warning(f"[BreathRetro] 🔴 紅燈觸發: {result['red_light']}")

    return result


# ── 三問分析 ─────────────────────────────────────────────────────────────────

def _analyze_metrics_comparison(
    workspace: Path,
    week_id: str,
    last_week_retro: dict | None,
) -> dict[str, Any]:
    """問 1：這週系統真的變好了嗎？（指標對比）"""
    metrics: dict[str, Any] = {}

    # 嘗試讀取系統指標
    system_dir = workspace / "data/_system"

    # Q-Score 趨勢（DendriticScorer 或 doctor）
    health_file = system_dir / "doctor/dendritic_health.json"
    if health_file.exists():
        try:
            data = json.loads(health_file.read_text(encoding="utf-8"))
            current_q = data.get("q_score") or data.get("health_score") or data.get("score")
            if current_q is not None:
                last_q = None
                if last_week_retro:
                    last_q = last_week_retro.get("metrics_comparison", {}).get(
                        "q_score", {}
                    ).get("this_week")
                metrics["q_score"] = {
                    "this_week": current_q,
                    "last_week": last_q,
                    "trend": _calc_trend(current_q, last_q),
                }
        except (json.JSONDecodeError, OSError):
            pass

    # Skill 命中率
    skill_health_dir = system_dir / "skill_health"
    if skill_health_dir.exists():
        hit_rates = []
        for f in sorted(skill_health_dir.glob("*.json"))[-5:]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                rate = data.get("hit_rate") or data.get("success_rate")
                if rate is not None:
                    hit_rates.append(float(rate))
            except (json.JSONDecodeError, OSError, ValueError):
                pass
        if hit_rates:
            current_hit = sum(hit_rates) / len(hit_rates)
            last_hit = None
            if last_week_retro:
                last_hit = last_week_retro.get("metrics_comparison", {}).get(
                    "skill_hit_rate", {}
                ).get("this_week")
            metrics["skill_hit_rate"] = {
                "this_week": round(current_hit, 3),
                "last_week": last_hit,
                "trend": _calc_trend(current_hit, last_hit),
                "sample_count": len(hit_rates),
            }

    # 改動成功率
    actions = _load_actions(workspace, week_id)
    if actions:
        successes = sum(1 for a in actions if "success" in a.get("status", ""))
        total = len(actions)
        metrics["action_success_rate"] = {
            "this_week": round(successes / total, 2) if total > 0 else None,
            "successes": successes,
            "total": total,
        }

    if not metrics:
        metrics["note"] = "指標檔案不存在或無法讀取，建議建立系統健康監控"

    return metrics


def _detect_repeated_lessons(workspace: Path, week_id: str) -> list[str]:
    """問 2：有什麼教訓被重複學到？（重複 = 上次沒學會 = 紅燈）"""
    repeated: list[str] = []

    # 讀 awareness_log.jsonl 中的教訓
    awareness_log = workspace / "data/memory_v3/awareness_log.jsonl"
    if not awareness_log.exists():
        return repeated

    lesson_count: dict[str, int] = {}
    try:
        lines = awareness_log.read_text(encoding="utf-8").strip().splitlines()
        # 只看最近 200 條
        for line in lines[-200:]:
            try:
                entry = json.loads(line)
                lesson = entry.get("lesson") or entry.get("content") or ""
                if isinstance(lesson, str) and len(lesson) > 20:
                    # 用前 80 字元作為 key（避免完全相同才算重複）
                    key = lesson[:80].strip()
                    lesson_count[key] = lesson_count.get(key, 0) + 1
            except json.JSONDecodeError:
                pass
    except OSError:
        pass

    # 出現 2 次以上的教訓
    for lesson, count in lesson_count.items():
        if count >= 2:
            repeated.append(f"[出現 {count} 次] {lesson}")

    # 也讀 heuristics.json 看有沒有重複建立的 heuristic
    heuristics_file = workspace / "data/_system/heuristics.json"
    if heuristics_file.exists():
        try:
            data = json.loads(heuristics_file.read_text(encoding="utf-8"))
            heuristics = data if isinstance(data, list) else data.get("heuristics", [])
            # 找相似的 heuristic（簡單的前 50 字元比對）
            seen: dict[str, str] = {}
            for h in heuristics:
                text = (h.get("content") or h.get("rule") or str(h))[:50]
                if text in seen:
                    repeated.append(f"[重複 heuristic] {text}... 與 {seen[text]}")
                else:
                    seen[text] = str(h)[:100]
        except (json.JSONDecodeError, OSError):
            pass

    return repeated[:10]  # 最多回傳 10 條


def _guess_blind_spots(observations: list[dict]) -> list[str]:
    """問 3：有什麼問題是觀察系統本身看不見的？（盲點猜測）"""
    blind_spots = []

    # 統計四條河流的覆蓋情況
    rivers = {obs.get("river", "unknown") for obs in observations}
    all_rivers = {"zeal_interaction", "client_interaction", "self_observation", "external_exploration"}
    missing_rivers = all_rivers - rivers

    if missing_rivers:
        blind_spots.append(
            f"本週以下河流無資料，可能存在盲點: {', '.join(missing_rivers)}"
        )

    # 如果 external_exploration 很少，可能對外部環境變化不敏感
    external_count = sum(1 for obs in observations if obs.get("river") == "external_exploration")
    if external_count < 3:
        blind_spots.append("外部探索資料不足（< 3 條），可能低估了競品或市場變化")

    # 如果只有 error severity，可能只看到問題沒看到成功
    severities = {obs.get("severity", "info") for obs in observations}
    if "info" not in severities and observations:
        blind_spots.append("觀察資料只有 error/warning，沒有 info —— 可能無法看清楚什麼在正常工作")

    # 固定盲點提醒
    blind_spots.extend([
        "使用者情緒狀態：對話品質指標可能無法捕捉使用者的真實感受",
        "沉默訊號：沒有抱怨不等於滿意，有沒有觀察到用戶靜默退場？",
        "系統外部依賴：Anthropic API 穩定性、Telegram Bot API 限流——這些不在自我觀察範圍內",
    ])

    return blind_spots[:6]


# ── 下週重點 ─────────────────────────────────────────────────────────────────

def _derive_next_focus(
    q1: dict,
    q2: list,
    q3: list,
    actions: list[dict],
) -> str:
    """從三問結果推導下週觀察重點."""
    focus_hints = []

    # 指標下降 → 重點觀察什麼在退步
    for metric_name, metric_data in q1.items():
        if isinstance(metric_data, dict):
            trend = metric_data.get("trend")
            if trend == "down":
                focus_hints.append(f"{metric_name} 本週下降，下週重點追蹤原因")

    # 重複教訓 → 重點確認上次修復是否生效
    if q2:
        focus_hints.append(f"有 {len(q2)} 條重複教訓，下週重點確認這些教訓的修復是否真的生效")

    # 有 failed 的 action → 下週重新診斷
    failed_actions = [a for a in actions if "failed" in a.get("status", "")]
    if failed_actions:
        focus_hints.append(f"有 {len(failed_actions)} 個改動失敗，下週需要重新診斷根因")

    if not focus_hints:
        return "本週系統狀態穩定，下週維持四條河流的正常觀察即可"

    return "；".join(focus_hints[:3])


# ── 紅燈機制 ─────────────────────────────────────────────────────────────────

def _check_red_lights(
    metrics: dict,
    repeated_lessons: list,
    actions: list[dict],
) -> list[str]:
    """檢查紅燈條件."""
    red_lights = []

    # 同一教訓重複學到
    if len(repeated_lessons) >= 2:
        red_lights.append(
            f"RED_LIGHT: {len(repeated_lessons)} 條教訓重複出現，上次修復可能沒有真正生效"
        )

    # 指標連續下降（需要歷史資料）
    downtrend_count = 0
    for metric_name, metric_data in metrics.items():
        if isinstance(metric_data, dict) and metric_data.get("trend") == "down":
            downtrend_count += 1
    if downtrend_count >= 2:
        red_lights.append(
            f"RED_LIGHT: {downtrend_count} 個指標同時下降，需要檢視近期所有改動"
        )

    # FV 連續失敗
    fv_failures = sum(
        1 for a in actions
        if "fv" in a.get("status", "").lower() and "fail" in a.get("status", "").lower()
    )
    if fv_failures >= 2:
        red_lights.append(
            f"RED_LIGHT: FV 連續 {fv_failures} 次失敗，需要重新診斷而非重複施工"
        )

    return red_lights


# ── 工具函數 ─────────────────────────────────────────────────────────────────

def _load_observations(workspace: Path, week_id: str) -> list[dict]:
    obs_path = workspace / f"data/_system/breath/observations/{week_id}.jsonl"
    if not obs_path.exists():
        return []
    observations = []
    for line in obs_path.read_text(encoding="utf-8").strip().splitlines():
        try:
            observations.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return observations


def _load_actions(workspace: Path, week_id: str) -> list[dict]:
    actions_path = workspace / f"data/_system/breath/actions/{week_id}.json"
    if not actions_path.exists():
        return []
    try:
        data = json.loads(actions_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return data.get("actions", [])
    except (json.JSONDecodeError, OSError):
        return []


def _load_last_retro(workspace: Path, last_week_id: str) -> dict | None:
    retro_path = workspace / f"data/_system/breath/retros/{last_week_id}.json"
    if not retro_path.exists():
        return None
    try:
        return json.loads(retro_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _get_last_week_id(week_id: str) -> str:
    """從 week_id 算出上週 week_id."""
    try:
        # week_id 格式：YYYY-wNN
        year_str, week_str = week_id.split("-w")
        year, week = int(year_str), int(week_str)

        # 找到本週一的日期，減 7 天
        from datetime import date  # noqa: PLC0415
        # ISO year-week to date
        first_day_of_week = date.fromisocalendar(year, week, 1)
        last_week_date = first_day_of_week - timedelta(days=7)
        return last_week_date.strftime("%Y-w%W")
    except (ValueError, AttributeError):
        return "unknown"


def _calc_trend(current: float | None, last: float | None) -> str:
    if current is None or last is None:
        return "unknown"
    if current > last * 1.02:  # 上升 2% 以上才算 up
        return "up"
    if current < last * 0.98:  # 下降 2% 以上才算 down
        return "down"
    return "stable"


def _summarize_actions(actions: list[dict]) -> list[dict]:
    """精簡 actions 列表用於回望."""
    return [
        {
            "description": a.get("description", a.get("reason", ""))[:100],
            "status": a.get("status", "unknown"),
            "type": a.get("type", "unknown"),
        }
        for a in actions
    ]
