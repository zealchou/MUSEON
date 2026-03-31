"""triage_to_morphenix — 將 triage HIGH 訊號轉為 Morphenix 迭代筆記.

覺察→行動的「修復」路徑：
triage 分診出 HIGH 級別問題 → 轉為 Morphenix 迭代筆記 → 累積後由 Step 5.8
信號源 5（傳統迭代筆記）結晶為正式提案。

不直接建立 Morphenix 提案（那是 L3 級變更需要人類核准），
而是寫入迭代筆記（iteration notes），讓 Morphenix Step 5.8 的結晶流程自己
判斷何時升級（≥3 條筆記即觸發 L2 結晶提案）。

整合方式：在 Nightly Step 5.8（_step_morphenix_proposals）開頭呼叫：
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes
    drain_priority_queue_to_notes(self._workspace)

這樣 HIGH 訊號在信號源 5 掃描前就已轉為 notes，直接被消費。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_PRIORITY_QUEUE = "data/_system/nightly_priority_queue.json"
_NOTES_DIR = "_system/morphenix/notes"

# AwarenessSignal severity → Morphenix note priority 對映
_SEV_TO_PRIORITY = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "info": "low",
}


def drain_priority_queue_to_notes(workspace: Path) -> Dict[str, int]:
    """讀取 nightly_priority_queue.json，轉為 Morphenix 迭代筆記後清空隊列.

    轉換邏輯：
    - 每個 HIGH 訊號 → 一份 morphenix/notes/{date}_{signal_id}_triage.json
    - 筆記格式與現有 mc_*_metacog_insight.json 一致（category / content / source / ...）
    - 處理完後清空 queue（已轉為筆記，不重複處理）

    Args:
        workspace: MUSEON 根目錄（Path 物件，例如 Path("~/MUSEON").expanduser()）

    Returns:
        {"processed": int, "notes_created": int}
    """
    queue_file = workspace / _PRIORITY_QUEUE
    if not queue_file.exists():
        logger.debug("triage_to_morphenix: priority_queue 不存在，略過")
        return {"processed": 0, "notes_created": 0}

    try:
        raw = queue_file.read_text(encoding="utf-8").strip()
        items: List[Dict[str, Any]] = json.loads(raw) if raw else []
    except Exception as e:
        logger.warning("triage_to_morphenix: 讀取 priority_queue 失敗 (%s)", e)
        return {"processed": 0, "notes_created": 0}

    if not items:
        return {"processed": 0, "notes_created": 0}

    notes_dir = workspace / _NOTES_DIR
    notes_dir.mkdir(parents=True, exist_ok=True)

    notes_created = 0
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y%m%d")

    for item in items:
        signal_id = item.get("signal_id", now.strftime("%H%M%S"))
        title = item.get("title", "")
        source = item.get("source", "triage")
        skill_name = item.get("skill_name") or ""
        severity = item.get("severity", "high")
        signal_type = item.get("signal_type", "unknown")
        suggested_action = item.get("suggested_action") or ""
        context = item.get("context", {})
        created_at = item.get("created_at", now.isoformat())

        # 組成 content：結構化文字方便 Step 5.6.5 萃取規則
        content_parts = [f"**覺察**：{title}"]
        if suggested_action:
            content_parts.append(f"**建議行動**：{suggested_action}")
        if skill_name:
            content_parts.append(f"**相關 Skill**：{skill_name}")
        if signal_type:
            content_parts.append(f"**訊號類型**：{signal_type}")
        if context:
            # 只取關鍵 context（避免筆記過大）
            ctx_summary = {k: v for k, v in list(context.items())[:5]}
            content_parts.append(f"**上下文**：{json.dumps(ctx_summary, ensure_ascii=False)}")

        note: Dict[str, Any] = {
            "id": f"triage_{date_str}_{signal_id}",
            "category": "triage_high",
            "content": "\n".join(content_parts),
            "source": f"triage:{source}",
            "signal_id": signal_id,
            "signal_type": signal_type,
            "skill_name": skill_name,
            "severity": severity,
            "suggested_action": suggested_action,
            "triage_action": item.get("triage_action", "queued_for_priority_review"),
            "original_source": source,
            "created_at": created_at,
            "priority": _SEV_TO_PRIORITY.get(severity, "high"),
        }

        note_file = notes_dir / f"triage_{date_str}_{signal_id}.json"
        try:
            note_file.write_text(
                json.dumps(note, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            notes_created += 1
            logger.debug(
                "triage_to_morphenix: 寫入筆記 %s (%s)", note_file.name, title
            )
        except Exception as e:
            logger.warning("triage_to_morphenix: 寫入筆記失敗 (%s) — %s", e, title)

    # 清空 queue（已轉為筆記，不重複處理）
    try:
        queue_file.write_text("[]", encoding="utf-8")
        logger.info(
            "triage_to_morphenix: %d 條 HIGH 訊號 → %d 條 Morphenix 迭代筆記，queue 已清空",
            len(items),
            notes_created,
        )
    except Exception as e:
        logger.warning("triage_to_morphenix: 清空 priority_queue 失敗 (%s)", e)

    return {"processed": len(items), "notes_created": notes_created}
