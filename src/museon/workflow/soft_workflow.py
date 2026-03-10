"""SoftWorkflow — 軟工作流資料模型 + 儲存層.

使用者透過對話式助理建構工作流草案，Brain 組合技能成工作流，
Pulse 排程執行，WEE 追蹤演化。

儲存採雙軌制：
- workflow.md — 人類可讀（PlanEngine 格式）
- state.json — 機器可讀（SoftWorkflow 序列化）
- WorkflowEngine SQLite — 執行統計與生命週期（複用）
"""

import json
import logging
import shutil
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════
# 資料模型
# ═══════════════════════════════════════════


@dataclass
class WorkflowStep:
    """工作流步驟 — 綁定具體技能."""

    step_id: str = ""
    skill_id: str = ""
    action: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    input_from: Optional[str] = None
    output_key: str = ""
    estimated_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "skill_id": self.skill_id,
            "action": self.action,
            "params": self.params,
            "input_from": self.input_from,
            "output_key": self.output_key,
            "estimated_tokens": self.estimated_tokens,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkflowStep":
        return cls(
            step_id=d.get("step_id", ""),
            skill_id=d.get("skill_id", ""),
            action=d.get("action", ""),
            params=d.get("params", {}),
            input_from=d.get("input_from"),
            output_key=d.get("output_key", ""),
            estimated_tokens=int(d.get("estimated_tokens", 0)),
        )


@dataclass
class ScheduleConfig:
    """排程設定."""

    schedule_type: str = "once"  # "cron" | "once" | "event"
    cron_expression: Optional[str] = None
    once_at: Optional[str] = None
    event_trigger: Optional[str] = None
    timezone: str = "Asia/Taipei"
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_type": self.schedule_type,
            "cron_expression": self.cron_expression,
            "once_at": self.once_at,
            "event_trigger": self.event_trigger,
            "timezone": self.timezone,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ScheduleConfig":
        return cls(
            schedule_type=d.get("schedule_type", "once"),
            cron_expression=d.get("cron_expression"),
            once_at=d.get("once_at"),
            event_trigger=d.get("event_trigger"),
            timezone=d.get("timezone", "Asia/Taipei"),
            active=d.get("active", True),
        )


@dataclass
class SoftWorkflow:
    """軟工作流 — Brain 原生執行的可重複工作流."""

    workflow_id: str = ""
    name: str = ""
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    lifecycle: str = "birth"
    tags: List[str] = field(default_factory=list)
    created_at: str = ""
    created_from_session: str = ""
    last_modified: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "schedule": self.schedule.to_dict(),
            "lifecycle": self.lifecycle,
            "tags": self.tags,
            "created_at": self.created_at,
            "created_from_session": self.created_from_session,
            "last_modified": self.last_modified,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SoftWorkflow":
        return cls(
            workflow_id=d.get("workflow_id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            steps=[WorkflowStep.from_dict(s) for s in d.get("steps", [])],
            schedule=ScheduleConfig.from_dict(d.get("schedule", {})),
            lifecycle=d.get("lifecycle", "birth"),
            tags=d.get("tags", []),
            created_at=d.get("created_at", ""),
            created_from_session=d.get("created_from_session", ""),
            last_modified=d.get("last_modified", ""),
        )

    @property
    def total_estimated_tokens(self) -> int:
        return sum(s.estimated_tokens for s in self.steps)

    @property
    def is_recurring(self) -> bool:
        return self.schedule.schedule_type == "cron"


# ═══════════════════════════════════════════
# WorkflowStore — 儲存層
# ═══════════════════════════════════════════


class WorkflowStore:
    """軟工作流的檔案系統儲存層.

    目錄結構：
        base_dir/
        ├── registry.json
        └── {workflow_id}/
            ├── workflow.md
            ├── state.json
            └── executions/
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._registry_path = self._base_dir / "registry.json"

    # ── CRUD ──

    def save(self, wf: SoftWorkflow) -> None:
        """儲存工作流（建立或更新）."""
        with self._lock:
            wf_dir = self._base_dir / wf.workflow_id
            wf_dir.mkdir(parents=True, exist_ok=True)
            (wf_dir / "executions").mkdir(exist_ok=True)

            # state.json（機器讀）
            state_path = wf_dir / "state.json"
            state_path.write_text(
                json.dumps(wf.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # workflow.md（人看）
            md_path = wf_dir / "workflow.md"
            md_path.write_text(
                self.generate_markdown(wf),
                encoding="utf-8",
            )

            self._update_registry()
            logger.info(f"WorkflowStore saved: {wf.workflow_id} ({wf.name})")

    def load(self, workflow_id: str) -> Optional[SoftWorkflow]:
        """載入單一工作流."""
        state_path = self._base_dir / workflow_id / "state.json"
        if not state_path.exists():
            return None
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            return SoftWorkflow.from_dict(data)
        except Exception as e:
            logger.error(f"WorkflowStore load error ({workflow_id}): {e}")
            return None

    def list_all(self) -> List[SoftWorkflow]:
        """列出所有工作流（從 registry 快取 + 回退掃描）."""
        if self._registry_path.exists():
            try:
                registry = json.loads(
                    self._registry_path.read_text(encoding="utf-8")
                )
                result = []
                for entry in registry:
                    wf = self.load(entry["workflow_id"])
                    if wf:
                        result.append(wf)
                return result
            except Exception:
                pass
        # 回退：掃描所有子目錄
        result = []
        for d in sorted(self._base_dir.iterdir()):
            if d.is_dir() and (d / "state.json").exists():
                wf = self.load(d.name)
                if wf:
                    result.append(wf)
        return result

    def delete(self, workflow_id: str) -> bool:
        """刪除工作流."""
        with self._lock:
            wf_dir = self._base_dir / workflow_id
            if not wf_dir.exists():
                return False
            shutil.rmtree(wf_dir)
            self._update_registry()
            logger.info(f"WorkflowStore deleted: {workflow_id}")
            return True

    def save_execution(
        self, workflow_id: str, execution_data: Dict[str, Any]
    ) -> None:
        """儲存單次執行紀錄到 executions/ 目錄."""
        exec_dir = self._base_dir / workflow_id / "executions"
        exec_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(TZ_TAIPEI).strftime("%Y%m%d-%H%M%S")
        exec_path = exec_dir / f"{ts}.json"
        exec_path.write_text(
            json.dumps(execution_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Markdown 生成 ──

    def generate_markdown(self, wf: SoftWorkflow) -> str:
        """生成人類可讀的 workflow.md."""
        lines = [
            f"# {wf.name}",
            "",
            f"**狀態:** {wf.lifecycle}",
            f"**建立:** {wf.created_at[:10] if wf.created_at else 'N/A'}",
            f"**最後修改:** {wf.last_modified[:10] if wf.last_modified else 'N/A'}",
        ]

        # 排程資訊
        if wf.schedule.schedule_type == "cron" and wf.schedule.cron_expression:
            lines.append(f"**排程:** `{wf.schedule.cron_expression}` ({wf.schedule.timezone})")
        elif wf.schedule.schedule_type == "once" and wf.schedule.once_at:
            lines.append(f"**執行時間:** {wf.schedule.once_at}")
        lines.append(f"**預估 Token:** ~{wf.total_estimated_tokens:,}/次")
        if wf.tags:
            lines.append(f"**標籤:** {', '.join(wf.tags)}")

        # 需求描述
        lines.extend(["", "## 需求描述", wf.description or "(無描述)"])

        # 執行步驟
        lines.extend([
            "",
            "## 執行步驟",
            "| # | 技能 | 動作 | 輸入 | 輸出 |",
            "|---|------|------|------|------|",
        ])
        for i, step in enumerate(wf.steps, 1):
            input_src = step.input_from or "—"
            lines.append(
                f"| {i} | {step.skill_id} | {step.action} | {input_src} | {step.output_key} |"
            )

        # 排程設定
        lines.extend([
            "",
            "## 排程設定",
            f"- 類型：{wf.schedule.schedule_type}",
        ])
        if wf.schedule.cron_expression:
            lines.append(f"- 表達式：`{wf.schedule.cron_expression}`")
        lines.append(f"- 時區：{wf.schedule.timezone}")
        status_icon = "✅ 啟用中" if wf.schedule.active else "⏸️ 已暫停"
        lines.append(f"- 狀態：{status_icon}")

        return "\n".join(lines) + "\n"

    # ── 內部方法 ──

    def _update_registry(self) -> None:
        """更新 registry.json 索引."""
        entries = []
        for d in sorted(self._base_dir.iterdir()):
            if d.is_dir() and (d / "state.json").exists():
                try:
                    data = json.loads((d / "state.json").read_text(encoding="utf-8"))
                    entries.append({
                        "workflow_id": data.get("workflow_id", d.name),
                        "name": data.get("name", ""),
                        "lifecycle": data.get("lifecycle", "birth"),
                        "schedule_type": data.get("schedule", {}).get("schedule_type", "once"),
                    })
                except Exception:
                    continue
        self._registry_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ═══════════════════════════════════════════
# 工廠函數
# ═══════════════════════════════════════════


def create_soft_workflow(
    name: str,
    description: str,
    steps: List[Dict[str, Any]],
    schedule: Dict[str, Any],
    session_id: str = "",
    tags: Optional[List[str]] = None,
) -> SoftWorkflow:
    """從對話草案建立 SoftWorkflow 實例."""
    now = datetime.now(TZ_TAIPEI).isoformat()
    workflow_id = str(uuid.uuid4())[:8]

    return SoftWorkflow(
        workflow_id=workflow_id,
        name=name,
        description=description,
        steps=[
            WorkflowStep(
                step_id=f"step_{i:03d}",
                skill_id=s.get("skill_id", ""),
                action=s.get("action", ""),
                params=s.get("params", {}),
                input_from=s.get("input_from"),
                output_key=s.get("output_key", f"output_{i}"),
                estimated_tokens=int(s.get("estimated_tokens", 500)),
            )
            for i, s in enumerate(steps, 1)
        ],
        schedule=ScheduleConfig.from_dict(schedule),
        lifecycle="birth",
        tags=tags or [],
        created_at=now,
        created_from_session=session_id,
        last_modified=now,
    )
