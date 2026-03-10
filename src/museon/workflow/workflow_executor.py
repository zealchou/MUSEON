"""WorkflowExecutor — 軟工作流步驟執行引擎.

依序執行 SoftWorkflow 的每個 WorkflowStep，
透過 Brain.process() 呼叫對應 skill，
完成後由 WorkflowEngine 記錄執行統計。
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .models import FourDScore
from .soft_workflow import SoftWorkflow, WorkflowStore, WorkflowStep
from .workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════
# 步驟結果
# ═══════════════════════════════════════════


@dataclass
class StepResult:
    """單一步驟的執行結果."""

    step_id: str = ""
    skill_id: str = ""
    action: str = ""
    status: str = "success"  # "success" | "failed" | "skipped"
    output: str = ""
    error: str = ""
    tokens_used: int = 0
    elapsed_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "skill_id": self.skill_id,
            "action": self.action,
            "status": self.status,
            "output": self.output[:2000],  # 截斷
            "error": self.error,
            "tokens_used": self.tokens_used,
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass
class ExecutionSummary:
    """整次工作流執行的摘要."""

    workflow_id: str = ""
    workflow_name: str = ""
    trigger_source: str = ""
    status: str = "success"  # "success" | "partial" | "failed"
    step_results: List[StepResult] = field(default_factory=list)
    total_tokens: int = 0
    total_elapsed_ms: int = 0
    score: Optional[FourDScore] = None
    started_at: str = ""
    completed_at: str = ""
    session_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "trigger_source": self.trigger_source,
            "status": self.status,
            "step_results": [s.to_dict() for s in self.step_results],
            "total_tokens": self.total_tokens,
            "total_elapsed_ms": self.total_elapsed_ms,
            "score": self.score.to_dict() if self.score else None,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "session_id": self.session_id,
        }


# ═══════════════════════════════════════════
# WorkflowExecutor
# ═══════════════════════════════════════════


class WorkflowExecutor:
    """軟工作流執行引擎.

    每個 WorkflowStep 透過 Brain.process() 執行，
    步驟之間透過 output_key / input_from 串接。
    """

    def __init__(
        self,
        brain: Any,
        workflow_engine: WorkflowEngine,
        store: WorkflowStore,
        event_bus: Any = None,
    ) -> None:
        self._brain = brain
        self._workflow_engine = workflow_engine
        self._store = store
        self._event_bus = event_bus

    async def execute(
        self,
        workflow_id: str,
        trigger_source: str = "manual",
    ) -> ExecutionSummary:
        """執行整個工作流.

        1. 從 WorkflowStore 載入 SoftWorkflow
        2. 建立獨立 session
        3. 依序執行每個 WorkflowStep
        4. 啟發式 FourDScore 評分
        5. WorkflowEngine.record_execution()
        6. 寫入 executions/{timestamp}.json
        7. 發布 WORKFLOW_COMPLETED 事件

        Args:
            workflow_id: 工作流 ID
            trigger_source: 觸發來源 ("manual" | "cron" | "event")

        Returns:
            ExecutionSummary
        """
        started_at = datetime.now(TZ_TAIPEI)

        # 載入工作流定義
        wf = self._store.load(workflow_id)
        if not wf:
            logger.error(f"WorkflowExecutor: workflow {workflow_id} not found")
            return ExecutionSummary(
                workflow_id=workflow_id,
                status="failed",
                started_at=started_at.isoformat(),
                completed_at=datetime.now(TZ_TAIPEI).isoformat(),
            )

        # 建立獨立 session
        ts = started_at.strftime("%Y%m%d%H%M%S")
        session_id = f"workflow_{workflow_id}_{ts}"

        self._publish("WORKFLOW_EXECUTED", {
            "workflow_id": workflow_id,
            "workflow_name": wf.name,
            "trigger_source": trigger_source,
            "session_id": session_id,
        })

        # 執行步驟
        step_results: List[StepResult] = []
        outputs: Dict[str, str] = {}  # output_key → output_value
        overall_status = "success"
        total_start = time.monotonic()

        for step in wf.steps:
            result = await self._execute_step(step, outputs, session_id)
            step_results.append(result)

            if result.status == "success" and step.output_key:
                outputs[step.output_key] = result.output

            if result.status == "failed":
                overall_status = "partial"
                # 不中斷，繼續執行後續步驟（graceful degradation）

        total_elapsed = int((time.monotonic() - total_start) * 1000)
        total_tokens = sum(s.tokens_used for s in step_results)
        completed_at = datetime.now(TZ_TAIPEI)

        # 啟發式評分
        score = self._heuristic_score(wf, step_results)

        # 判斷整體狀態
        success_count = sum(1 for s in step_results if s.status == "success")
        if success_count == 0:
            overall_status = "failed"
        elif success_count == len(step_results):
            overall_status = "success"

        # 記錄到 WorkflowEngine SQLite
        outcome = overall_status
        self._workflow_engine.record_execution(
            workflow_id=workflow_id,
            score=score,
            outcome=outcome,
            context=f"trigger={trigger_source}, steps={len(step_results)}, "
                    f"success={success_count}/{len(step_results)}",
        )

        # 寫入 executions/ 快照
        summary = ExecutionSummary(
            workflow_id=workflow_id,
            workflow_name=wf.name,
            trigger_source=trigger_source,
            status=overall_status,
            step_results=step_results,
            total_tokens=total_tokens,
            total_elapsed_ms=total_elapsed,
            score=score,
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            session_id=session_id,
        )

        self._store.save_execution(workflow_id, summary.to_dict())

        # 發布完成事件
        event_type = "WORKFLOW_COMPLETED" if overall_status != "failed" else "WORKFLOW_FAILED"
        self._publish(event_type, {
            "workflow_id": workflow_id,
            "workflow_name": wf.name,
            "status": overall_status,
            "score_composite": score.composite,
            "total_tokens": total_tokens,
            "total_elapsed_ms": total_elapsed,
        })

        logger.info(
            f"WorkflowExecutor done: {wf.name} | status={overall_status} | "
            f"score={score.composite:.2f} | tokens={total_tokens} | {total_elapsed}ms"
        )

        return summary

    async def _execute_step(
        self,
        step: WorkflowStep,
        outputs: Dict[str, str],
        session_id: str,
    ) -> StepResult:
        """執行單一步驟.

        透過 Brain.process() 呼叫，注入 [WORKFLOW_STEP] 標記
        讓 Brain 知道這是工作流步驟（可跳過 DNA27 語義匹配）。
        """
        start_time = time.monotonic()

        # 組裝步驟指令
        input_data = ""
        if step.input_from and step.input_from in outputs:
            input_data = outputs[step.input_from]

        params_str = json.dumps(step.params, ensure_ascii=False) if step.params else "{}"
        step_content = (
            f"[WORKFLOW_STEP] skill:{step.skill_id} action:{step.action} "
            f"params:{params_str}"
        )
        if input_data:
            step_content += f"\n\n[INPUT]\n{input_data[:3000]}"

        try:
            result = await self._brain.process(
                content=step_content,
                session_id=session_id,
                user_id="boss",
                source="workflow_executor",
            )

            # 解析 BrainResponse
            from museon.gateway.message import BrainResponse
            if isinstance(result, BrainResponse):
                output_text = result.text or ""
            elif isinstance(result, str):
                output_text = result
            else:
                output_text = str(result) if result else ""

            elapsed = int((time.monotonic() - start_time) * 1000)

            return StepResult(
                step_id=step.step_id,
                skill_id=step.skill_id,
                action=step.action,
                status="success",
                output=output_text,
                tokens_used=step.estimated_tokens,  # 使用預估值
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = int((time.monotonic() - start_time) * 1000)
            logger.error(f"WorkflowExecutor step {step.step_id} failed: {e}")
            return StepResult(
                step_id=step.step_id,
                skill_id=step.skill_id,
                action=step.action,
                status="failed",
                error=str(e)[:500],
                elapsed_ms=elapsed,
            )

    def _heuristic_score(
        self,
        wf: SoftWorkflow,
        step_results: List[StepResult],
    ) -> FourDScore:
        """啟發式評分 — 不依賴 LLM.

        - speed: 基於實際耗時 vs 預估 token 的比例
        - quality: 基於成功率
        - alignment: 基於輸出是否非空
        - leverage: 基於步驟數和整合度
        """
        if not step_results:
            return FourDScore()

        total = len(step_results)
        success = sum(1 for s in step_results if s.status == "success")
        has_output = sum(1 for s in step_results if s.output.strip())

        # speed: 全部成功 → 8，有失敗 → 按比例
        speed = 5.0 + 3.0 * (success / total) if total else 5.0

        # quality: 成功率
        quality = 10.0 * (success / total) if total else 5.0

        # alignment: 有產出比例
        alignment = 5.0 + 5.0 * (has_output / total) if total else 5.0

        # leverage: 步驟越多且成功率高 → 越高
        leverage = min(10.0, 3.0 + success * 1.5)

        score = FourDScore(
            speed=min(10.0, speed),
            quality=min(10.0, quality),
            alignment=min(10.0, alignment),
            leverage=min(10.0, leverage),
        )
        return score.clamp()

    def _publish(self, event_type: str, data: Dict) -> None:
        """EventBus 發布（靜默失敗）."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception as e:
                logger.warning(f"EventBus publish '{event_type}' failed: {e}")
