"""triage_step — Nightly 覺察訊號分診.

讀取 data/_system/triage_queue.jsonl → 按 severity 排序 →
CRITICAL 立即推播 Telegram → HIGH 加入優先隊列 → MEDIUM 以下記錄。

分診邏輯用 code 不用 LLM：LLM 掛了時 CRITICAL 訊號更需要送出去。

覺察後的預設動作是「調整」不是「記住」：
- 每個訊號都先問「能不能立即做什麼不同的事？」
- 只有「需要改 code 或需要人類決策」時才降級為「記住」
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.core.awareness import (
    Actionability,
    AwarenessSignal,
    Severity,
)

# 頂層 import 事件常數，方便測試 mock
try:
    from museon.core.event_bus import INCIDENT_DETECTED, PROACTIVE_MESSAGE
except ImportError:
    # 讓單元測試在不啟動完整 Gateway 的情況下也能執行
    PROACTIVE_MESSAGE = "PROACTIVE_MESSAGE"
    INCIDENT_DETECTED = "INCIDENT_DETECTED"

logger = logging.getLogger(__name__)

# ── 路徑常數 ──────────────────────────────────────────────────────────────────

_TRIAGE_QUEUE = "data/_system/triage_queue.jsonl"
_PRIORITY_QUEUE = "data/_system/nightly_priority_queue.json"
_AWARENESS_LOG = "data/_system/awareness_log.jsonl"
_INFO_COUNTER = "data/_system/awareness_info_counter.json"
_PENDING_ADJUSTMENTS = "data/_system/pending_adjustments.json"
_HUMAN_QUEUE = "data/_system/triage_human_queue.json"

# Severity 排序權重（數字越大優先度越高）
_SEVERITY_ORDER: Dict[str, int] = {
    Severity.CRITICAL.value: 5,
    Severity.HIGH.value: 4,
    Severity.MEDIUM.value: 3,
    Severity.LOW.value: 2,
    Severity.INFO.value: 1,
}


# ── 公開 helper：其他模組用來產出訊號 ─────────────────────────────────────────


def write_signal(workspace: Path, signal: AwarenessSignal) -> None:
    """將 AwarenessSignal 寫入 triage_queue.jsonl（append mode）.

    給所有覺察源（DendriticScorer、SkillHealthTracker、WEE 等）呼叫。
    每行一個 JSON object，符合 JSONL 格式。

    參數：
        workspace: MUSEON 根目錄路徑（~/MUSEON）
        signal: 要寫入的 AwarenessSignal

    範例：
        from museon.nightly.triage_step import write_signal
        from museon.core.awareness import AwarenessSignal, Severity, SignalType, Actionability

        write_signal(
            Path("~/MUSEON").expanduser(),
            AwarenessSignal(
                source="skill_health_tracker",
                skill_name="darwin",
                severity=Severity.HIGH,
                signal_type=SignalType.SKILL_DEGRADED,
                title="darwin Skill 健康度 0.42，低於門檻 0.6",
                actionability=Actionability.PROMPT,
            )
        )
    """
    queue_path = workspace / _TRIAGE_QUEUE
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    with open(queue_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(signal.to_dict(), ensure_ascii=False) + "\n")

    logger.debug(
        "write_signal: %s [%s] id=%s",
        signal.title,
        signal.severity.value if isinstance(signal.severity, Severity) else signal.severity,
        signal.signal_id,
    )


# ── 主分診函數 ─────────────────────────────────────────────────────────────────


async def run_triage(
    workspace: Path,
    event_bus: Optional[Any] = None,
) -> Dict[str, int]:
    """Nightly 覺察訊號分診主函數.

    讀取 triage_queue.jsonl → 按 severity 排序 → 依規則分流 → 清空隊列。

    分診規則：
    - CRITICAL + HUMAN  → 推播 Telegram（event_bus PROACTIVE_MESSAGE）
    - CRITICAL + AUTO   → 觸發 INCIDENT_DETECTED 事件
    - HIGH              → 寫入 nightly_priority_queue.json
    - MEDIUM / LOW      → 寫入 awareness_log.jsonl
    - INFO              → 只更新計數器

    參數：
        workspace:  MUSEON 根目錄（~/MUSEON）
        event_bus:  可選，museon.core.event_bus 的 EventBus 實例
                    若為 None，CRITICAL 訊號無法推播（會記錄 warning）

    回傳：
        {
            "total": int,
            "critical": int,
            "high": int,
            "medium": int,
            "low": int,
            "info": int,
        }
    """
    stats: Dict[str, int] = {
        "total": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0,
        "dropped": 0,
    }

    queue_path = workspace / _TRIAGE_QUEUE

    # ── 讀取隊列 ──────────────────────────────────────────────────────────────
    if not queue_path.exists():
        logger.info("triage_step: triage_queue.jsonl 不存在，無訊號需分診")
        return stats

    signals: List[AwarenessSignal] = []
    parse_errors = 0

    with open(queue_path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                signals.append(AwarenessSignal.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                parse_errors += 1
                logger.warning(
                    "triage_step: 第 %d 行解析失敗（%s），已略過", lineno, e
                )

    if parse_errors:
        logger.warning("triage_step: 共 %d 行解析失敗", parse_errors)

    if not signals:
        # 清空空檔案
        queue_path.write_text("", encoding="utf-8")
        return stats

    # ── 按 severity 排序（CRITICAL 優先處理）─────────────────────────────────
    signals.sort(
        key=lambda s: _SEVERITY_ORDER.get(
            s.severity.value if isinstance(s.severity, Severity) else s.severity, 0
        ),
        reverse=True,
    )

    stats["total"] = len(signals)

    # ── 高優先隊列（HIGH）累積後寫入 ─────────────────────────────────────────
    priority_entries: List[Dict[str, Any]] = []

    # ── 認知紀錄（MEDIUM / LOW）───────────────────────────────────────────────
    awareness_log_path = workspace / _AWARENESS_LOG
    awareness_log_path.parent.mkdir(parents=True, exist_ok=True)

    # 記錄本輪分診開始前，awareness_log 已有的行數
    # check_accumulation_upgrades 只看這個行數以前的「歷史」紀錄，不含本輪新寫入的
    _log_lines_before_triage = 0
    if awareness_log_path.exists():
        try:
            _log_lines_before_triage = sum(
                1 for l in awareness_log_path.read_text(encoding="utf-8").splitlines() if l.strip()
            )
        except OSError:
            _log_lines_before_triage = 0

    # INFO 計數器
    info_counter_path = workspace / _INFO_COUNTER

    for signal in signals:
        sev = signal.severity.value if isinstance(signal.severity, Severity) else signal.severity
        act = signal.actionability.value if isinstance(signal.actionability, Actionability) else signal.actionability

        # 標記為已分診
        signal.status = "triaged"

        if sev == Severity.CRITICAL.value:
            stats["critical"] += 1
            signal.triage_action = _handle_critical(signal, event_bus, workspace)

        elif sev == Severity.HIGH.value:
            stats["high"] += 1
            signal.triage_action = "queued_for_priority_review"
            priority_entries.append(signal.to_dict())

        elif sev == Severity.MEDIUM.value:
            stats["medium"] += 1

            if act == Actionability.AUTO.value and signal.suggested_action:
                # 補線 C：MEDIUM+AUTO → 寫入 pending_adjustments（隔天生效）
                signal.triage_action = "pending_adjustment_queued"
                _pending = _load_pending_adjustments(workspace)
                _signal_type_val = signal.signal_type.value if not isinstance(signal.signal_type, str) else signal.signal_type
                _pending.append({
                    "trigger": f"{signal.source}:{_signal_type_val}",
                    "adjustment": signal.suggested_action,
                    "params": signal.context,
                    "expires_after_turns": 5,
                    "created_at": signal.created_at,
                })
                _save_pending_adjustments(workspace, _pending)
                # 同時記入 awareness_log
                _append_to_log(awareness_log_path, signal)

            elif act == Actionability.HUMAN.value:
                # 補線 H：MEDIUM+HUMAN → 積壓計數，滿 3 條摘要推播
                signal.triage_action = "human_queue_batched"
                _human_queue = _load_human_queue(workspace)
                _human_queue.append({
                    "signal_id": signal.signal_id,
                    "title": signal.title,
                    "source": signal.source,
                    "timestamp": signal.created_at,
                })
                _save_human_queue(workspace, _human_queue)

                if len(_human_queue) >= 3:
                    summary_lines = [f"• {item['title']}" for item in _human_queue[-5:]]
                    summary_text = "📋 累積待處理事項（需要你看一下）\n\n" + "\n".join(summary_lines)
                    if event_bus:
                        try:
                            event_bus.publish(PROACTIVE_MESSAGE, {
                                "text": summary_text,
                                "source": "triage_human_batch",
                            })
                            logger.info(
                                "triage_step: MEDIUM+HUMAN 積壓推播 %d 條", len(_human_queue)
                            )
                        except Exception as e:
                            logger.error("triage_step: MEDIUM+HUMAN 推播失敗 (%s)", e)
                    # 清空隊列
                    _save_human_queue(workspace, [])
                # 也寫入 awareness_log
                _append_to_log(awareness_log_path, signal)

            else:
                signal.triage_action = "logged_to_awareness"
                _append_to_log(awareness_log_path, signal)

        elif sev == Severity.LOW.value:
            stats["low"] += 1
            signal.triage_action = "logged_to_awareness"
            _append_to_log(awareness_log_path, signal)

        elif sev == Severity.INFO.value:
            stats["info"] += 1
            signal.triage_action = "counter_updated"
            _increment_info_counter(
                info_counter_path,
                signal.signal_type if isinstance(signal.signal_type, str) else signal.signal_type.value,
            )
            # 補線 D：INFO 有意識放下的審計紀錄
            _append_raw_to_log(awareness_log_path, {
                "signal_id": signal.signal_id,
                "status": "dropped",
                "reason": "info_severity",
                "title": signal.title,
                "timestamp": signal.created_at,
            })
            stats["dropped"] += 1

    # ── 寫入高優先隊列 ────────────────────────────────────────────────────────
    if priority_entries:
        _write_priority_queue(workspace / _PRIORITY_QUEUE, priority_entries)

    # ── 清空原始隊列（已處理完畢）────────────────────────────────────────────
    queue_path.write_text("", encoding="utf-8")

    # ── 補線 E：累積升級檢查 ─────────────────────────────────────────────────
    # 只看本輪分診「之前」已存在的歷史紀錄，不把剛分診的訊號算進去
    upgraded = check_accumulation_upgrades(workspace, max_lines=_log_lines_before_triage)
    if upgraded:
        logger.info("triage_step: 累積升級 %d 條訊號，重新分診", len(upgraded))
        for sig in upgraded:
            sev = sig.severity.value if isinstance(sig.severity, Severity) else sig.severity
            act = sig.actionability.value if isinstance(sig.actionability, Actionability) else sig.actionability
            sig.status = "triaged"

            if sev == Severity.MEDIUM.value:
                stats["medium"] += 1
                stats["total"] += 1
                if act == Actionability.AUTO.value and sig.suggested_action:
                    sig.triage_action = "pending_adjustment_queued"
                    _pending = _load_pending_adjustments(workspace)
                    _pending.append({
                        "trigger": f"{sig.source}:{sig.signal_type.value if not isinstance(sig.signal_type, str) else sig.signal_type}",
                        "adjustment": sig.suggested_action,
                        "params": sig.context,
                        "expires_after_turns": 5,
                        "created_at": sig.created_at,
                    })
                    _save_pending_adjustments(workspace, _pending)
                    _append_to_log(awareness_log_path, sig)
                else:
                    sig.triage_action = "logged_to_awareness"
                    _append_to_log(awareness_log_path, sig)

    logger.info(
        "triage_step 完成：total=%d critical=%d high=%d medium=%d low=%d info=%d dropped=%d",
        stats["total"],
        stats["critical"],
        stats["high"],
        stats["medium"],
        stats["low"],
        stats["info"],
        stats["dropped"],
    )

    return stats


# ── 內部輔助函數 ───────────────────────────────────────────────────────────────


def _handle_critical(
    signal: AwarenessSignal,
    event_bus: Optional[Any],
    workspace: Path,
) -> str:
    """處理 CRITICAL 訊號，依 actionability 分流."""
    act = signal.actionability.value if isinstance(signal.actionability, Actionability) else signal.actionability

    if act == Actionability.HUMAN.value:
        # 推播 Telegram 通知人類
        if event_bus is not None:
            try:
                event_bus.publish(
                    PROACTIVE_MESSAGE,
                    {
                        "message": _format_critical_message(signal),
                        "priority": "critical",
                        "signal_id": signal.signal_id,
                    },
                )
                logger.warning(
                    "triage_step: CRITICAL 訊號已推播 Telegram — %s", signal.title
                )
                return "telegram_notified"
            except Exception as e:
                logger.error(
                    "triage_step: CRITICAL 推播失敗（%s）— %s", e, signal.title
                )
                # 推播失敗也要寫入 awareness_log，確保不漏失
                _append_to_log(workspace / _AWARENESS_LOG, signal)
                return "telegram_failed_logged"
        else:
            # event_bus 不可用，記錄到 awareness_log
            logger.warning(
                "triage_step: event_bus 不可用，CRITICAL 訊號改寫 awareness_log — %s",
                signal.title,
            )
            _append_to_log(workspace / _AWARENESS_LOG, signal)
            return "no_event_bus_logged"

    elif act == Actionability.AUTO.value:
        # 觸發系統自動處理事件
        if event_bus is not None:
            try:
                event_bus.publish(
                    INCIDENT_DETECTED,
                    {
                        "signal": signal.to_dict(),
                        "auto_handle": True,
                    },
                )
                logger.warning(
                    "triage_step: CRITICAL AUTO 已觸發 INCIDENT_DETECTED — %s",
                    signal.title,
                )
                return "incident_event_published"
            except Exception as e:
                logger.error(
                    "triage_step: INCIDENT_DETECTED 發布失敗（%s）— %s", e, signal.title
                )
                _append_to_log(workspace / _AWARENESS_LOG, signal)
                return "incident_event_failed_logged"
        else:
            _append_to_log(workspace / _AWARENESS_LOG, signal)
            return "no_event_bus_logged"

    else:
        # PROMPT：需要 LLM 判斷，記錄到 awareness_log
        _append_to_log(workspace / _AWARENESS_LOG, signal)
        return "logged_for_llm_review"


def _format_critical_message(signal: AwarenessSignal) -> str:
    """格式化 CRITICAL 訊號為 Telegram 推播訊息."""
    sev = signal.severity.value if isinstance(signal.severity, Severity) else signal.severity
    lines = [
        f"🚨 CRITICAL 覺察訊號",
        f"訊號 ID：{signal.signal_id}",
        f"來源：{signal.source}",
        f"標題：{signal.title}",
    ]
    if signal.skill_name:
        lines.append(f"Skill：{signal.skill_name}")
    if signal.metric_name and signal.metric_value is not None:
        baseline_str = (
            f"（基準 {signal.metric_baseline:.3f}）"
            if signal.metric_baseline is not None
            else ""
        )
        lines.append(
            f"指標：{signal.metric_name} = {signal.metric_value:.3f}{baseline_str}"
        )
    if signal.suggested_action:
        lines.append(f"建議動作：{signal.suggested_action}")
    return "\n".join(lines)


def _append_to_log(log_path: Path, signal: AwarenessSignal) -> None:
    """將訊號 append 到 JSONL 認知紀錄."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(signal.to_dict(), ensure_ascii=False) + "\n")


def _append_raw_to_log(log_path: Path, entry: Dict[str, Any]) -> None:
    """將任意 dict append 到 JSONL 認知紀錄（補線 D 用）."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _write_priority_queue(
    queue_path: Path, entries: List[Dict[str, Any]]
) -> None:
    """將 HIGH 訊號寫入優先隊列 JSON 檔.

    使用覆寫模式（每次 Nightly 重新生成），不累積舊訊號。
    """
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    existing: List[Dict[str, Any]] = []
    if queue_path.exists():
        try:
            existing = json.loads(queue_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, ValueError):
            existing = []

    # 合併：保留舊有未處理條目 + 新增的
    existing.extend(entries)

    queue_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("triage_step: %d 條 HIGH 訊號寫入優先隊列", len(entries))


def _increment_info_counter(counter_path: Path, signal_type: str) -> None:
    """遞增 INFO 訊號計數器."""
    counter_path.parent.mkdir(parents=True, exist_ok=True)

    counter: Dict[str, Any] = {}
    if counter_path.exists():
        try:
            counter = json.loads(counter_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            counter = {}

    today = datetime.now(timezone.utc).date().isoformat()
    if "by_date" not in counter:
        counter["by_date"] = {}
    if today not in counter["by_date"]:
        counter["by_date"][today] = {}

    counter["by_date"][today][signal_type] = (
        counter["by_date"][today].get(signal_type, 0) + 1
    )
    counter["total"] = counter.get("total", 0) + 1
    counter["updated_at"] = datetime.now(timezone.utc).isoformat()

    counter_path.write_text(
        json.dumps(counter, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 補線 C helpers ─────────────────────────────────────────────────────────────


def _load_pending_adjustments(workspace: Path) -> List[Dict[str, Any]]:
    """讀取 pending_adjustments.json."""
    path = workspace / _PENDING_ADJUSTMENTS
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def _save_pending_adjustments(workspace: Path, items: List[Dict[str, Any]]) -> None:
    """寫入 pending_adjustments.json."""
    path = workspace / _PENDING_ADJUSTMENTS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 補線 H helpers ─────────────────────────────────────────────────────────────


def _load_human_queue(workspace: Path) -> List[Dict[str, Any]]:
    """讀取 triage_human_queue.json."""
    path = workspace / _HUMAN_QUEUE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, ValueError):
        return []


def _save_human_queue(workspace: Path, items: List[Dict[str, Any]]) -> None:
    """寫入 triage_human_queue.json."""
    path = workspace / _HUMAN_QUEUE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 補線 E：累積升級 ────────────────────────────────────────────────────────────


def check_accumulation_upgrades(
    workspace: Path,
    max_lines: Optional[int] = None,
) -> List[AwarenessSignal]:
    """掃描 awareness_log，同類訊號累積 ≥3 次 → 自動升級為 MEDIUM.

    「記住」不是終點——累積到一定量就觸發行動。

    Args:
        workspace: MUSEON 根目錄
        max_lines: 只掃描前 N 行（用於排除本輪剛寫入的訊號）。
                   None 表示掃描全部。

    Returns: 升級後的新訊號列表（會被加入 triage_queue 重新分診）
    """
    log_path = workspace / _AWARENESS_LOG
    if not log_path.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    counts: Dict[str, int] = {}
    # 記錄每個 key 的代表性 source 和 signal_type（用於產出新訊號）
    key_meta: Dict[str, Dict[str, str]] = {}

    try:
        all_lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    # 只掃描前 max_lines 行（排除本輪剛寫入的訊號）
    if max_lines is not None:
        lines = all_lines[:max_lines]
    else:
        lines = all_lines

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        # 只統計完整的訊號（有 source 和 signal_type 欄位），忽略 dropped 審計行
        source = entry.get("source")
        signal_type = entry.get("signal_type")
        if not source or not signal_type:
            continue

        # 只看最近 7 天
        created_at_str = entry.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(created_at_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at < cutoff:
                continue
        except (ValueError, TypeError):
            continue

        key = f"{source}:{signal_type}"
        counts[key] = counts.get(key, 0) + 1
        if key not in key_meta:
            key_meta[key] = {"source": source, "signal_type": signal_type}

    upgraded: List[AwarenessSignal] = []
    for key, count in counts.items():
        if count >= 3:
            meta = key_meta[key]
            # 嘗試解析 signal_type
            try:
                from museon.core.awareness import SignalType  # noqa: PLC0415
                sig_type = SignalType(meta["signal_type"])
            except ValueError:
                sig_type = SignalType.BEHAVIOR_DRIFT  # 預設

            new_sig = AwarenessSignal(
                source=meta["source"],
                title=f"累積升級：{meta['source']} / {meta['signal_type']} 最近 7 天出現 {count} 次",
                severity=Severity.MEDIUM,
                signal_type=sig_type,
                actionability=Actionability.PROMPT,
                context={"accumulated_count": count, "original_key": key},
            )
            upgraded.append(new_sig)
            logger.info(
                "check_accumulation_upgrades: %s 累積 %d 次 → 升級為 MEDIUM", key, count
            )

    return upgraded
