"""PulseTools — Brain 的脈搏管理工具.

讓霓裳可以自主管理排程、讀寫 PULSE.md、觸發探索、更新 ANIMA。
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Tool Definitions (Brain Skill Format)
# ═══════════════════════════════════════════

PULSE_TOOLS = [
    {
        "name": "pulse_add_reminder",
        "description": "新增一次性提醒。time 支援 ISO 8601 或自然語言如 '明天 14:00'。",
        "parameters": {
            "message": {"type": "string", "description": "提醒內容"},
            "time": {"type": "string", "description": "觸發時間"},
        },
        "required": ["message", "time"],
    },
    {
        "name": "pulse_add_recurring",
        "description": "新增週期任務。interval 支援 'every 3h' / 'daily 07:30' / cron 表達式。",
        "parameters": {
            "task": {"type": "string", "description": "任務描述"},
            "interval": {"type": "string", "description": "週期表達式"},
        },
        "required": ["task", "interval"],
    },
    {
        "name": "pulse_remove",
        "description": "移除排程任務。",
        "parameters": {
            "task_id": {"type": "string", "description": "任務 ID"},
        },
        "required": ["task_id"],
    },
    {
        "name": "pulse_list",
        "description": "列出所有排程任務。",
        "parameters": {},
        "required": [],
    },
    {
        "name": "pulse_read",
        "description": "讀取 PULSE.md 全文（霓裳的意識流）。",
        "parameters": {},
        "required": [],
    },
    {
        "name": "pulse_update_section",
        "description": "更新 PULSE.md 的特定區塊。section 可為: observations, explorations, reflections, growth。",
        "parameters": {
            "section": {"type": "string", "description": "區塊名稱"},
            "content": {"type": "string", "description": "新內容"},
        },
        "required": ["section", "content"],
    },
    {
        "name": "pulse_explore",
        "description": "觸發一次自主探索。motivation 可為: curiosity/mission/skill/world/self。每日上限 3 次，每次 ≤$0.50。",
        "parameters": {
            "topic": {"type": "string", "description": "探索主題"},
            "motivation": {"type": "string", "description": "觸發動機"},
        },
        "required": ["topic", "motivation"],
    },
    {
        "name": "pulse_anima_grow",
        "description": "更新 ANIMA 八元素。element: qian/kun/zhen/xun/kan/li/gen/dui。",
        "parameters": {
            "element": {"type": "string", "description": "八元素代碼"},
            "delta": {"type": "integer", "description": "增量（正整數）"},
            "reason": {"type": "string", "description": "增長原因"},
        },
        "required": ["element", "delta", "reason"],
    },
]

# ═══════════════════════════════════════════
# PULSE.md Section Markers
# ═══════════════════════════════════════════

SECTION_MAP = {
    "rhythm": "🌅 今日節律",
    "reminders": "🔔 提醒",
    "observations": "👀 觀察筆記",
    "explorations": "🧭 探索佇列",
    "reflections": "🪞 教練反思",
    "growth": "🌱 成長紀錄",
    "status": "📊 今日狀態",
}


# ═══════════════════════════════════════════
# Tool Executor
# ═══════════════════════════════════════════


class PulseToolExecutor:
    """執行 Brain 的脈搏管理工具呼叫."""

    def __init__(self, data_dir: str, pulse_db=None, explorer=None, anima_tracker=None):
        self._data_dir = Path(data_dir)
        self._pulse_md = self._data_dir / "PULSE.md"
        self._db = pulse_db
        self._explorer = explorer
        self._anima = anima_tracker

    async def execute(self, tool_name: str, args: Dict[str, Any]) -> str:
        """執行工具並回傳結果字串."""
        handler = getattr(self, f"_exec_{tool_name}", None)
        if not handler:
            return f"未知工具: {tool_name}"
        try:
            result = await handler(args)
            return json.dumps(result, ensure_ascii=False, indent=2) if isinstance(result, (dict, list)) else str(result)
        except Exception as e:
            logger.error(f"PulseTool {tool_name} failed: {e}")
            return f"執行失敗: {e}"

    async def _exec_pulse_add_reminder(self, args: Dict) -> Dict:
        if not self._db:
            return {"error": "PulseDB not initialized"}
        task_id = f"rem-{uuid.uuid4().hex[:8]}"
        return self._db.add_schedule(
            task_id=task_id,
            task_type="reminder",
            description=args["message"],
            schedule=args["time"],
        )

    async def _exec_pulse_add_recurring(self, args: Dict) -> Dict:
        if not self._db:
            return {"error": "PulseDB not initialized"}
        task_id = f"rec-{uuid.uuid4().hex[:8]}"
        return self._db.add_schedule(
            task_id=task_id,
            task_type="recurring",
            description=args["task"],
            schedule=args["interval"],
        )

    async def _exec_pulse_remove(self, args: Dict) -> Dict:
        if not self._db:
            return {"error": "PulseDB not initialized"}
        removed = self._db.remove_schedule(args["task_id"])
        return {"removed": removed, "task_id": args["task_id"]}

    async def _exec_pulse_list(self, args: Dict) -> List[Dict]:
        if not self._db:
            return []
        return self._db.list_schedules()

    async def _exec_pulse_read(self, args: Dict) -> str:
        if not self._pulse_md.exists():
            return "(PULSE.md 尚未建立)"
        return self._pulse_md.read_text(encoding="utf-8")

    async def _exec_pulse_update_section(self, args: Dict) -> Dict:
        section = args["section"]
        content = args["content"]
        marker = SECTION_MAP.get(section)
        if not marker:
            return {"error": f"未知區塊: {section}，可用: {list(SECTION_MAP.keys())}"}

        if not self._pulse_md.exists():
            return {"error": "PULSE.md 不存在"}

        text = self._pulse_md.read_text(encoding="utf-8")
        lines = text.split("\n")
        result_lines = []
        in_section = False
        section_replaced = False

        for line in lines:
            if line.startswith("## ") and marker in line:
                in_section = True
                result_lines.append(line)
                result_lines.append(content.strip())
                section_replaced = True
                continue
            elif line.startswith("## ") and in_section:
                in_section = False
                result_lines.append("")
                result_lines.append(line)
                continue

            if not in_section:
                result_lines.append(line)

        if not section_replaced:
            result_lines.append(f"\n## {marker}\n{content.strip()}\n")

        self._pulse_md.write_text("\n".join(result_lines), encoding="utf-8")
        return {"updated": True, "section": section}

    async def _exec_pulse_explore(self, args: Dict) -> Dict:
        if not self._explorer:
            return {"error": "Explorer not initialized"}
        if not self._db:
            return {"error": "PulseDB not initialized"}

        # Check daily limits
        count = self._db.get_today_exploration_count()
        if count >= 3:
            return {"error": "今日探索次數已達上限 (3/3)", "count": count}
        cost = self._db.get_today_exploration_cost()
        if cost >= 1.50:
            return {"error": f"今日探索預算已達上限 (${cost:.2f}/$1.50)", "cost": cost}

        result = await self._explorer.explore(
            topic=args["topic"],
            motivation=args.get("motivation", "curiosity"),
        )
        # Log to DB
        self._db.log_exploration(
            topic=args["topic"],
            motivation=args.get("motivation", "curiosity"),
            query=result.get("query", ""),
            findings=result.get("findings", "")[:2000],
            crystallized=result.get("crystallized", False),
            crystal_id=result.get("crystal_id", ""),
            tokens_used=result.get("tokens_used", 0),
            cost_usd=result.get("cost_usd", 0),
            duration_ms=result.get("duration_ms", 0),
            status=result.get("status", "done"),
        )
        return result

    async def _exec_pulse_anima_grow(self, args: Dict) -> Dict:
        if not self._anima:
            return {"error": "AnimaTracker not initialized"}
        element = args["element"]
        delta = int(args["delta"])
        reason = args["reason"]
        return self._anima.grow(element, delta, reason)
