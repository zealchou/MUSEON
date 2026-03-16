"""Multi-Agent Executor — 並行 LLM 呼叫執行器.

依據施工計畫 Phase 4.2 實作。
多個部門的 LLM 呼叫並行發送，每個部門用獨立的 system prompt。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DepartmentResponse:
    """單一部門的回應結果."""

    dept_id: str
    dept_name: str
    emoji: str
    response: str
    model_used: str = "haiku"
    latency_ms: int = 0
    is_primary: bool = False
    error: Optional[str] = None


@dataclass
class MultiAgentResult:
    """多代理執行結果."""

    primary: DepartmentResponse
    auxiliaries: List[DepartmentResponse] = field(default_factory=list)
    total_latency_ms: int = 0
    departments_called: int = 1


class MultiAgentExecutor:
    """並行 LLM 呼叫執行器.

    接收主部門 + 輔助部門列表，並行呼叫各部門的 LLM，
    每個部門使用獨立的 system prompt。
    """

    def __init__(self, llm_adapter: Any) -> None:
        self._llm_adapter = llm_adapter

    async def execute(
        self,
        user_message: str,
        primary_dept_id: str,
        auxiliary_dept_ids: Optional[List[str]] = None,
        user_context: str = "",
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> MultiAgentResult:
        """並行呼叫多個部門的 LLM.

        Args:
            user_message: 使用者訊息
            primary_dept_id: 主部門 ID
            auxiliary_dept_ids: 輔助部門 ID 列表
            user_context: 共享的使用者上下文（八原語、畫像等）
            messages: 對話歷史

        Returns:
            MultiAgentResult 包含主部門和輔助部門的回應
        """
        from museon.multiagent.department_config import get_department

        auxiliary_dept_ids = auxiliary_dept_ids or []
        start = time.monotonic()

        # 建構主部門任務
        primary_dept = get_department(primary_dept_id)
        if not primary_dept:
            return MultiAgentResult(
                primary=DepartmentResponse(
                    dept_id=primary_dept_id,
                    dept_name="未知",
                    emoji="❓",
                    response="部門不存在",
                    error="department_not_found",
                ),
            )

        # 建構所有任務（主部門 + 輔助部門）
        tasks = []

        # 主部門（用 Sonnet）
        tasks.append(
            self._call_department(
                dept=primary_dept,
                user_message=user_message,
                user_context=user_context,
                messages=messages,
                is_primary=True,
            )
        )

        # 輔助部門（用 Haiku）
        for aux_id in auxiliary_dept_ids:
            aux_dept = get_department(aux_id)
            if aux_dept:
                tasks.append(
                    self._call_department(
                        dept=aux_dept,
                        user_message=user_message,
                        user_context=user_context,
                        messages=messages,
                        is_primary=False,
                    )
                )

        # 並行執行所有部門呼叫
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 分離主部門和輔助部門結果
        primary_result = None
        aux_results = []

        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Multi-Agent 部門呼叫失敗: {r}")
                continue
            if isinstance(r, DepartmentResponse):
                if r.is_primary:
                    primary_result = r
                else:
                    aux_results.append(r)

        # 如果主部門失敗，使用 fallback
        if primary_result is None:
            primary_result = DepartmentResponse(
                dept_id=primary_dept_id,
                dept_name=primary_dept.name,
                emoji=primary_dept.emoji,
                response="主部門回應失敗",
                error="primary_failed",
                is_primary=True,
            )

        elapsed = int((time.monotonic() - start) * 1000)

        return MultiAgentResult(
            primary=primary_result,
            auxiliaries=aux_results,
            total_latency_ms=elapsed,
            departments_called=1 + len(aux_results),
        )

    async def _call_department(
        self,
        dept: Any,
        user_message: str,
        user_context: str,
        messages: Optional[List[Dict[str, str]]],
        is_primary: bool,
    ) -> DepartmentResponse:
        """呼叫單一部門的 LLM.

        主部門用 dept.model_tier（通常 sonnet），輔助部門一律 haiku。
        """
        start = time.monotonic()

        # 選擇 system prompt
        system_prompt = dept.full_system_prompt or dept.prompt_section
        if user_context:
            system_prompt = f"{system_prompt}\n\n---\n{user_context}"

        # 決定模型
        model = dept.model_tier if is_primary else "haiku"

        # 建構簡化的 messages（輔助部門只需最近一條）
        if is_primary and messages:
            dept_messages = messages[-10:]  # 主部門保留最近 10 條
        else:
            dept_messages = [{"role": "user", "content": user_message}]

        try:
            resp = await self._llm_adapter.call(
                system_prompt=system_prompt,
                messages=dept_messages,
                model=model,
                max_tokens=4096 if is_primary else 1024,
            )

            elapsed = int((time.monotonic() - start) * 1000)

            if resp.stop_reason == "error":
                return DepartmentResponse(
                    dept_id=dept.dept_id,
                    dept_name=dept.name,
                    emoji=dept.emoji,
                    response="",
                    model_used=model,
                    latency_ms=elapsed,
                    is_primary=is_primary,
                    error=f"LLM error: {resp.text}",
                )

            return DepartmentResponse(
                dept_id=dept.dept_id,
                dept_name=dept.name,
                emoji=dept.emoji,
                response=resp.text,
                model_used=model,
                latency_ms=elapsed,
                is_primary=is_primary,
            )

        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error(f"部門 {dept.dept_id} LLM 呼叫失敗: {e}")
            return DepartmentResponse(
                dept_id=dept.dept_id,
                dept_name=dept.name,
                emoji=dept.emoji,
                response="",
                model_used=model,
                latency_ms=elapsed,
                is_primary=is_primary,
                error=str(e),
            )
