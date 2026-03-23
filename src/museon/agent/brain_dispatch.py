"""BrainDispatchMixin — 任務分派方法群.

從 brain.py 提取的 Mixin，負責 dispatch 路由、orchestration、
worker 分派、synthesize 彙整等任務分派邏輯。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BrainDispatchMixin:
    """Task Dispatch 方法群 — Mixin for MuseonBrain.

    # ═══════════════════════════════════════════
    # Task Dispatch System
    # ═══════════════════════════════════════════
    """

    # ═══════════════════════════════════════════
    # Dispatch 常數（從方法體內提升，便於調參）
    # ═══════════════════════════════════════════

    # 分派觸發條件
    _MIN_ACTIVE_SKILLS_FOR_DISPATCH = 2     # 最少 Skill 數
    _LARGE_SKILL_SET_THRESHOLD = 3          # 觸發「多 Skill 複雜」判定
    _LARGE_SKILL_CONTENT_TOKENS = 5000      # 認定 SKILL.md 為「大型」的 token 門檻
    _DISPATCH_TOKEN_OVERFLOW = 40000        # 合計 token 溢出臨界值
    _TOKEN_ESTIMATE_DIVISOR = 3             # 字元→Token 粗估除數

    # 預算估算
    _DISPATCH_BASE_BUDGET = 7000            # Orchestrator + synthesis 基礎預算
    _DISPATCH_PER_WORKER_BASE = 1500        # 每個 Worker 基礎 token 預算

    # 確定性路由
    _MAX_DETERMINISTIC_TASKS = 5            # DeterministicRouter 最多任務數

    # LLM 模型常數
    _ORCHESTRATOR_MODEL = "claude-sonnet-4-20250514"
    _SONNET_MODEL = "claude-sonnet-4-20250514"
    _HAIKU_MODEL = "claude-haiku-4-5-20251001"
    _SYNTHESIZE_MODEL = "claude-sonnet-4-20250514"
    _LLM_MAX_TOKENS = 16384                 # 所有 dispatch LLM 呼叫的 max_tokens

    # Orchestrator
    _ORCHESTRATOR_SKILL_CONTENT_LEN = 6000  # Orchestrator prompt 中 Skill 內容限制
    _ORCHESTRATOR_MAX_TASKS = 5             # 最多解析的任務數

    # 品質門檻
    _DEFAULT_QUALITY_SCORE = 0.7            # 品質分數預設值
    _QUALITY_GATE_THRESHOLD = 0.5           # 品質門檻：低於此值用 Sonnet 重試

    # Skill 深度對應分數
    _SKILL_DEPTH_SCORE_MAP = {
        "deep": 1.0,        # full
        "standard": 0.5,    # compact
        "quick": 0.2,       # essence
    }

    # 截斷長度
    _HANDOFF_CONTEXT_LEN = 600              # 交接上下文截斷
    _HANDOFF_SUMMARY_LEN = 400             # 依賴任務摘要截斷
    _WORKER_SUMMARY_LEN = 200              # Worker 摘要截斷
    _WORKER_RESPONSE_DIGEST_LEN = 1500     # Worker 回覆在 synthesis 中的截斷

    # Fallback
    _SESSION_HISTORY_TRIM = 40             # Session 歷史超過此值截斷

    # System leakage 過濾
    _LEAKAGE_FILTER_RATIO = 0.2            # 過濾後低於原文此比例 → 回傳原文
    _LEAKAGE_MIN_TEXT_LEN = 50             # 最小文本長度（避免誤殺短文）

    def _assess_dispatch(
        self,
        content: str,
        matched_skills: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """評估是否進入分派模式 — 純 CPU.

        分派條件（任一成立即觸發）：
        1. 3+ 非常駐 Skill 匹配 + 至少一個 SKILL.md > 5000 token
        2. 2 Skill 匹配但合計預估 > 40K token
        3. 使用者明確觸發 + 2+ Skill
        4. 預算檢查通過

        Returns:
            {should_dispatch: bool, reason: str}
        """
        # 過濾掉常駐 Skill
        active_skills = [
            s for s in matched_skills if not s.get("always_on")
        ]

        if len(active_skills) < self._MIN_ACTIVE_SKILLS_FOR_DISPATCH:
            return {"should_dispatch": False, "reason": "insufficient_skills"}

        # 使用者明確觸發
        explicit_triggers = [
            "完整流程", "全案", "從頭到尾", "一次搞定",
            "串起來", "整合分析", "全套", "完整診斷",
        ]
        user_explicit = any(t in content for t in explicit_triggers)

        if user_explicit and len(active_skills) >= self._MIN_ACTIVE_SKILLS_FOR_DISPATCH:
            if self._dispatch_budget_ok(active_skills):
                return {
                    "should_dispatch": True,
                    "reason": "user_explicit",
                }

        # 3+ Skill + 至少一個大型 SKILL.md
        if len(active_skills) >= self._LARGE_SKILL_SET_THRESHOLD:
            has_large = False
            for skill in active_skills:
                skill_text = self.skill_router.load_skill_content(skill)
                if len(skill_text) // self._TOKEN_ESTIMATE_DIVISOR > self._LARGE_SKILL_CONTENT_TOKENS:
                    has_large = True
                    break
            if has_large and self._dispatch_budget_ok(active_skills):
                return {
                    "should_dispatch": True,
                    "reason": "multi_skill_complex",
                }

        # 2 Skill 但合計 token 過高
        if len(active_skills) >= self._MIN_ACTIVE_SKILLS_FOR_DISPATCH:
            total_est = sum(
                len(self.skill_router.load_skill_content(s)) // self._TOKEN_ESTIMATE_DIVISOR
                for s in active_skills
            )
            if total_est > self._DISPATCH_TOKEN_OVERFLOW and self._dispatch_budget_ok(active_skills):
                return {
                    "should_dispatch": True,
                    "reason": "token_overflow",
                }

        return {"should_dispatch": False, "reason": "below_threshold"}

    def _dispatch_budget_ok(
        self, active_skills: List[Dict[str, Any]]
    ) -> bool:
        """檢查預算是否足夠執行 dispatch."""
        if not self.budget_monitor:
            return True
        # 粗估：orchestrator 3K + per-worker(base 1.5K + skill) + synthesis 4K
        estimated = self._DISPATCH_BASE_BUDGET
        for skill in active_skills:
            skill_text = self.skill_router.load_skill_content(skill)
            estimated += self._DISPATCH_PER_WORKER_BASE + len(skill_text) // self._TOKEN_ESTIMATE_DIVISOR
        return self.budget_monitor.check_budget(estimated)

    async def _dispatch_mode(
        self,
        content: str,
        session_id: str,
        user_id: str,
        matched_skills: List[Dict[str, Any]],
        anima_mc: Optional[Dict[str, Any]],
        anima_user: Optional[Dict[str, Any]],
        sub_agent_context: str,
    ) -> str:
        """執行分派模式：orchestrate → workers → synthesize.

        Returns:
            最終綜合回覆文字
        """
        import asyncio
        from museon.agent.dispatch import (
            DispatchPlan, DispatchStatus, TaskStatus,
            ExecutionMode, persist_dispatch_plan,
            build_execution_layers, determine_execution_mode,
        )

        plan_id = (
            f"dispatch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            f"_{session_id[:8]}"
        )
        active_skills = [
            s for s in matched_skills if not s.get("always_on")
        ]

        # ── 補齊同 Hub 的 Skill ──
        # 防止 top_n=5 導致同 Hub 的 Skill 被截斷，造成 Orchestrator 引用斷裂
        matched_hubs = {s.get("hub") for s in active_skills if s.get("hub")}
        if matched_hubs:
            existing_names = {s.get("name") for s in active_skills}
            for hub_name in matched_hubs:
                hub_skills = self.skill_router.get_skills_by_hub(hub_name)
                for hs in hub_skills:
                    if hs.get("name") not in existing_names and not hs.get("always_on"):
                        active_skills.append(hs)
                        existing_names.add(hs.get("name"))

        plan = DispatchPlan(
            plan_id=plan_id,
            user_request=content,
            session_id=session_id,
            created_at=datetime.now().isoformat(),
        )

        try:
            # Phase 1: Orchestrate — L3-A1 確定性路由優先，LLM fallback
            from museon.agent.deterministic_router import decompose as det_decompose
            det_tasks = det_decompose(
                user_request=content,
                matched_skills=active_skills,
                routing_signal=getattr(self, '_last_routing_signal', None),
                max_tasks=self._MAX_DETERMINISTIC_TASKS,
            )
            if det_tasks:
                # 確定性路由成功，直接構建 TaskPackage
                from museon.agent.dispatch import TaskPackage
                plan.tasks = [
                    TaskPackage(
                        task_id=f"{plan.plan_id}_task_{t['execution_order']:02d}",
                        skill_name=t["skill_name"],
                        skill_focus=t["skill_focus"],
                        skill_depth=t["skill_depth"],
                        expected_output=t["expected_output"],
                        execution_order=t["execution_order"],
                        depends_on=t.get("depends_on", []),
                        model_preference=t.get("model_preference", "haiku"),
                    )
                    for t in det_tasks
                ]
                plan.status = DispatchStatus.EXECUTING
                logger.info(
                    f"[DeterministicRouter] 直接路由: {len(plan.tasks)} tasks"
                )
            else:
                # 確定性路由無結果，fallback 到 LLM Orchestrator
                plan = await self._dispatch_orchestrate(
                    plan, active_skills, anima_mc,
                )
            persist_dispatch_plan(plan, self.data_dir)

            if not plan.tasks:
                logger.warning("Orchestrator 未產生任務，fallback")
                return await self._dispatch_fallback(
                    content, session_id, matched_skills,
                    anima_mc, anima_user, sub_agent_context,
                )

            # 決定執行模式
            plan.execution_mode = determine_execution_mode(
                plan.tasks,
            )

            # Phase 2: Workers — 根據模式執行
            plan.status = DispatchStatus.EXECUTING
            persist_dispatch_plan(plan, self.data_dir)

            for task in plan.tasks:
                task.input_data["user_request"] = content

            if plan.execution_mode == ExecutionMode.SERIAL:
                await self._dispatch_execute_serial(
                    plan, anima_mc,
                )
            elif plan.execution_mode == ExecutionMode.PARALLEL:
                await self._dispatch_execute_parallel(
                    plan, anima_mc,
                )
            else:  # MIXED
                await self._dispatch_execute_mixed(
                    plan, anima_mc,
                )

            persist_dispatch_plan(plan, self.data_dir)

            # Phase 3: Synthesize — 綜合回覆
            plan.status = DispatchStatus.SYNTHESIZING
            persist_dispatch_plan(plan, self.data_dir)

            final_text = await self._dispatch_synthesize(
                plan=plan,
                user_request=content,
                anima_mc=anima_mc,
                anima_user=anima_user,
            )

            plan.synthesis_result = final_text

            # 判斷完成狀態
            failed_count = sum(
                1 for r in plan.results
                if r.status == TaskStatus.FAILED
            )
            if failed_count == len(plan.results):
                plan.status = DispatchStatus.FAILED
            elif failed_count > 0:
                plan.status = DispatchStatus.PARTIAL
            else:
                plan.status = DispatchStatus.COMPLETED
            plan.completed_at = datetime.now().isoformat()

            # 統計 token 用量
            total_input = sum(
                r.token_usage.get("input", 0) for r in plan.results
            )
            total_output = sum(
                r.token_usage.get("output", 0) for r in plan.results
            )
            plan.total_token_usage = {
                "input": total_input, "output": total_output,
            }

            is_failed = plan.status == DispatchStatus.FAILED
            persist_dispatch_plan(
                plan, self.data_dir,
                completed=not is_failed,
                failed=is_failed,
            )

            logger.info(
                f"Dispatch {plan.status.value}: {plan.plan_id} | "
                f"mode={plan.execution_mode.value} | "
                f"tasks={len(plan.tasks)} | "
                f"failed={failed_count} | "
                f"token_in={total_input} token_out={total_output}"
            )
            return final_text

        except Exception as e:
            logger.error(f"Dispatch mode failed: {e}", exc_info=True)
            plan.status = DispatchStatus.FAILED
            plan.error_message = str(e)
            persist_dispatch_plan(
                plan, self.data_dir, failed=True,
            )
            return await self._dispatch_fallback(
                content, session_id, matched_skills,
                anima_mc, anima_user, sub_agent_context,
            )

    async def _dispatch_execute_serial(
        self,
        plan: Any,
        anima_mc: Optional[Dict[str, Any]],
    ) -> None:
        """串行執行所有 tasks，帶 timeout + quality gate."""
        import asyncio
        from museon.agent.dispatch import TaskStatus

        handoff_context = ""
        for task in plan.tasks:
            result = await self._dispatch_worker_with_guard(
                task=task,
                handoff_context=handoff_context,
                anima_mc=anima_mc,
            )
            plan.results.append(result)

            if result.handoff_package:
                handoff_context = (
                    result.handoff_package.compressed_context
                )
            elif result.status == TaskStatus.COMPLETED:
                handoff_context = result.result.get(
                    "summary", ""
                )[:self._HANDOFF_CONTEXT_LEN]

    async def _dispatch_execute_parallel(
        self,
        plan: Any,
        anima_mc: Optional[Dict[str, Any]],
    ) -> None:
        """全並行執行（所有 tasks 無依賴）."""
        import asyncio

        coros = [
            self._dispatch_worker_with_guard(
                task=task,
                handoff_context="",
                anima_mc=anima_mc,
            )
            for task in plan.tasks
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)

        from museon.agent.dispatch import ResultPackage, TaskStatus
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                plan.results.append(ResultPackage(
                    task_id=plan.tasks[i].task_id,
                    status=TaskStatus.FAILED,
                    error_message=str(result),
                ))
            else:
                plan.results.append(result)

    async def _dispatch_execute_mixed(
        self,
        plan: Any,
        anima_mc: Optional[Dict[str, Any]],
    ) -> None:
        """DAG 分層執行：層內並行，層間串行."""
        import asyncio
        from museon.agent.dispatch import (
            build_execution_layers, ResultPackage, TaskStatus,
        )

        layers = build_execution_layers(plan.tasks)
        result_map: Dict[str, Any] = {}  # task_id → result

        for layer_idx, layer in enumerate(layers):
            if len(layer) == 1:
                # 單一 task → 串行
                task = layer[0]
                handoff = self._get_handoff_from_deps(
                    task, result_map,
                )
                result = await self._dispatch_worker_with_guard(
                    task=task,
                    handoff_context=handoff,
                    anima_mc=anima_mc,
                )
                plan.results.append(result)
                result_map[task.task_id] = result
            else:
                # 多 tasks → 並行
                coros = []
                for task in layer:
                    handoff = self._get_handoff_from_deps(
                        task, result_map,
                    )
                    coros.append(
                        self._dispatch_worker_with_guard(
                            task=task,
                            handoff_context=handoff,
                            anima_mc=anima_mc,
                        )
                    )
                results = await asyncio.gather(
                    *coros, return_exceptions=True,
                )
                for i, result in enumerate(results):
                    t = layer[i]
                    if isinstance(result, Exception):
                        rp = ResultPackage(
                            task_id=t.task_id,
                            status=TaskStatus.FAILED,
                            error_message=str(result),
                        )
                        plan.results.append(rp)
                        result_map[t.task_id] = rp
                    else:
                        plan.results.append(result)
                        result_map[t.task_id] = result

            logger.info(
                f"DAG layer {layer_idx} complete: "
                f"{[t.skill_name for t in layer]}"
            )

    @staticmethod
    def _get_handoff_from_deps(
        task: Any, result_map: Dict[str, Any],
    ) -> str:
        """從依賴的 results 提取 handoff context."""
        from museon.agent.dispatch import TaskStatus

        parts = []
        for dep_id in (task.depends_on or []):
            dep_result = result_map.get(dep_id)
            if not dep_result:
                continue
            if dep_result.handoff_package:
                parts.append(
                    dep_result.handoff_package.compressed_context
                )
            elif dep_result.status == TaskStatus.COMPLETED:
                parts.append(
                    dep_result.result.get("summary", "")[:self._HANDOFF_SUMMARY_LEN]
                )
        return "\n---\n".join(parts) if parts else ""

    async def _dispatch_worker_with_guard(
        self,
        task: Any,
        handoff_context: str,
        anima_mc: Optional[Dict[str, Any]],
    ) -> Any:
        """Worker 執行 + timeout + quality gate + retry.

        1. asyncio.wait_for with task.timeout_seconds
        2. If self_score < 0.5 → retry once with Sonnet
        3. If still low → return result with degraded flag
        """
        import asyncio
        from museon.agent.dispatch import (
            ResultPackage, TaskStatus,
        )

        # 帶 timeout 的 worker 呼叫
        try:
            result = await asyncio.wait_for(
                self._dispatch_worker(
                    task=task,
                    handoff_context=handoff_context,
                    anima_mc=anima_mc,
                ),
                timeout=task.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Worker timeout: {task.skill_name} "
                f"({task.timeout_seconds}s)"
            , exc_info=True)
            return ResultPackage(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error_message=(
                    f"Timeout after {task.timeout_seconds}s"
                ),
            )

        # Quality gate: self_score < 0.5 → retry with Sonnet
        self_score = result.quality.get("self_score", self._DEFAULT_QUALITY_SCORE)
        if (
            result.status == TaskStatus.COMPLETED
            and self_score < self._QUALITY_GATE_THRESHOLD
            and task.model_preference != "sonnet"
        ):
            logger.warning(
                f"Quality gate: {task.skill_name} "
                f"score={self_score} < 0.5, retrying with Sonnet"
            )
            # 升級模型重試
            task.model_preference = "sonnet"
            try:
                retry_result = await asyncio.wait_for(
                    self._dispatch_worker(
                        task=task,
                        handoff_context=handoff_context,
                        anima_mc=anima_mc,
                    ),
                    timeout=task.timeout_seconds,
                )
                retry_score = retry_result.quality.get(
                    "self_score", self._DEFAULT_QUALITY_SCORE,
                )
                if retry_score >= self_score:
                    retry_result.meta["retried"] = True
                    return retry_result
                # 重試分數沒更好 → 用原結果
                result.meta["quality_degraded"] = True
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(
                    f"Retry failed: {task.skill_name} | {e}"
                )
                result.meta["quality_degraded"] = True

        return result

    async def _dispatch_orchestrate(
        self,
        plan: Any,
        active_skills: List[Dict[str, Any]],
        anima_mc: Optional[Dict[str, Any]],
    ) -> Any:
        """Orchestrator LLM 呼叫：分解使用者需求為子任務."""
        from museon.agent.dispatch import (
            TaskPackage, DispatchStatus,
        )

        # 載入 orchestrator SKILL.md
        orchestrator_content = ""
        for skill in self.skill_router._index:
            if skill.get("name") == "orchestrator":
                orchestrator_content = (
                    self.skill_router.load_skill_content(skill)
                )
                break

        # Skill 名單（summary + token 估算）
        # 排除 workflow 類 Skill：它們是編排範本，不是可被 Worker 執行的子任務
        skill_roster = ""
        worker_skills = []
        for skill in active_skills:
            if skill.get("type") == "workflow":
                continue
            worker_skills.append(skill)
            name = skill.get("name", "unknown")
            desc = skill.get("description", "")
            skill_text = self.skill_router.load_skill_content(skill)
            token_est = len(skill_text) // 3
            skill_roster += (
                f"- 【{name}】{desc} (~{token_est} tokens)\n"
            )

        system_prompt = (
            "你是 MUSEON 的 Orchestrator（編排引擎）。\n\n"
            "## 任務\n"
            "分析使用者的需求，將其分解為可由各 Skill 執行的子任務清單。\n\n"
            "## 可用 Skill\n"
            f"{skill_roster}\n"
            "## 編排方法論\n"
            f"{orchestrator_content[:self._ORCHESTRATOR_SKILL_CONTENT_LEN]}\n\n"
            "## 輸出格式\n"
            "你必須只回覆一個 JSON 陣列，每個元素代表一個子任務：\n"
            "```json\n"
            "[\n"
            "  {\n"
            '    "skill_name": "skill-name",\n'
            '    "skill_focus": "這個 skill 在此任務中要關注什麼",\n'
            '    "skill_depth": "quick|standard|deep",\n'
            '    "expected_output": "期望產出",\n'
            '    "model_preference": "haiku|sonnet"\n'
            "  }\n"
            "]\n"
            "```\n\n"
            "## 規則\n"
            "1. 子任務 2-5 個，按建議執行順序排列\n"
            "2. 如果有情緒承接類 Skill，排最前面\n"
            "3. 預設用 haiku，只有需要深度推理的用 sonnet\n"
            "4. skill_name 只能使用上方「可用 Skill」清單中出現的確切名稱，禁止引用清單外的任何 Skill\n"
            "5. 只回覆 JSON，不要其他文字\n"
            "\n⚠️ 你的回覆必須以 [ 開頭，以 ] 結尾。除了 JSON 陣列本身，不要包含任何其他文字。\n"
        )

        messages = [{"role": "user", "content": plan.user_request}]

        response_text = await self._call_llm_with_model(
            system_prompt=system_prompt,
            messages=messages,
            model=self._ORCHESTRATOR_MODEL,
            max_tokens=self._LLM_MAX_TOKENS,
        )

        # 解析 JSON（只驗證 worker_skills 名單，不含 workflow 類）
        tasks = self._parse_orchestrator_response(
            response_text, worker_skills or active_skills, plan.plan_id,
        )
        plan.tasks = tasks
        plan.status = (
            DispatchStatus.EXECUTING if tasks
            else DispatchStatus.FAILED
        )

        logger.info(
            f"Orchestrator decomposed: {len(tasks)} tasks from "
            f"{len(active_skills)} skills"
        )

        # L2-S3: 診斷數據收集
        try:
            from museon.pulse.pulse_db import get_pulse_db
            _pdb = get_pulse_db(Path(self.data_dir))
            _pdb.log_orchestrator_call(
                plan_id=plan.plan_id,
                skill_count=len(active_skills),
                task_count=len(tasks),
                success=bool(tasks),
                model=self._ORCHESTRATOR_MODEL,
                response_length=len(response_text),
            )
        except Exception as e:
            logger.warning(f"Orchestrator 診斷數據寫入失敗（不影響主流程）: {e}")

        return plan

    async def _dispatch_worker(
        self,
        task: Any,
        handoff_context: str,
        anima_mc: Optional[Dict[str, Any]],
    ) -> Any:
        """執行單一 Worker 子任務."""
        from museon.agent.dispatch import (
            ResultPackage, TaskStatus, HandoffPackage,
        )
        import time

        start_time = time.monotonic()

        # 載入 SKILL.md 並依深度選擇層
        # LayeredContent: deep=full, standard=compact, quick=essence
        skill_content = ""
        for skill in self.skill_router._index:
            if skill.get("name") == task.skill_name:
                full_content = (
                    self.skill_router.load_skill_content(skill)
                )
                # 依據 depth 選擇壓縮層（節省 token）
                try:
                    from museon.agent.token_optimizer import (
                        build_layered_content, select_layer,
                    )
                    layered = build_layered_content(
                        task.skill_name, full_content,
                    )
                    depth_score = self._SKILL_DEPTH_SCORE_MAP.get(
                        task.skill_depth, 0.5,
                    )
                    skill_content = select_layer(layered, depth_score)
                    # Fallback: 如果壓縮後為空，用 full
                    if not skill_content:
                        skill_content = full_content
                except Exception as e:
                    logger.warning(f"Skill 內容壓縮失敗（降級為完整版）: {e}")
                    skill_content = full_content
                break

        # 最小身份
        my_name = "MUSEON"
        boss_name = "老闆"
        if anima_mc:
            identity = anima_mc.get("identity", {})
            my_name = identity.get("name", "MUSEON")
            boss = anima_mc.get("boss", {})
            boss_name = boss.get("name", "老闆")

        handoff_section = ""
        if handoff_context:
            handoff_section = (
                f"\n## 前一步驟的交接\n{handoff_context}\n"
            )

        system_prompt = (
            f"你是 {my_name}，{boss_name} 的 AI 助理。\n\n"
            f"## 角色\n"
            f"你是專注的 Skill Worker，用 {task.skill_name} "
            f"的完整能力處理子任務。\n\n"
            f"## Skill 知識\n{skill_content}\n\n"
            f"## 子任務\n"
            f"- 焦點：{task.skill_focus}\n"
            f"- 深度：{task.skill_depth}\n"
            f"- 期望產出：{task.expected_output}\n"
            f"{handoff_section}\n"
            f"## 規則\n"
            f"1. 用繁體中文回覆\n"
            f"2. 只處理子任務範圍內的內容\n"
            f"3. 回覆結構：摘要（2-3句）→ 詳細內容 → "
            f"交接建議\n"
            f"4. 給建議時說甜頭和代價\n"
            f"5. 結尾附 JSON 自評：\n"
            f'```json\n{{"self_score": 0.0, "confidence": 0.0, '
            f'"limitations": "..."}}\n```\n'
        )

        messages = [
            {"role": "user", "content": task.input_data.get(
                "user_request", "",
            )}
        ]

        model = (
            self._SONNET_MODEL
            if task.model_preference == "sonnet"
            else self._HAIKU_MODEL
        )

        try:
            response_text = await self._call_llm_with_model(
                system_prompt=system_prompt,
                messages=messages,
                model=model,
                max_tokens=self._LLM_MAX_TOKENS,
            )

            elapsed_ms = int(
                (time.monotonic() - start_time) * 1000
            )

            quality = self._parse_worker_quality(response_text)

            handoff = HandoffPackage(
                for_next_skill="",
                compressed_context=response_text[:self._HANDOFF_CONTEXT_LEN],
                action_items_for_next=[],
                excluded_topics=[],
                user_implicit_preferences=[],
            )

            logger.info(
                f"Worker completed: {task.skill_name} | "
                f"score={quality.get('self_score', 'N/A')} | "
                f"{elapsed_ms}ms"
            )

            return ResultPackage(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                result={
                    "summary": response_text[:self._WORKER_SUMMARY_LEN],
                    "full_response": response_text,
                },
                quality=quality,
                handoff_package=handoff,
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = int(
                (time.monotonic() - start_time) * 1000
            )
            logger.error(
                f"Worker failed: {task.skill_name} | {e}"
            , exc_info=True)
            return ResultPackage(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                result={"error": str(e)},
                quality={
                    "self_score": 0,
                    "confidence": 0,
                    "limitations": str(e),
                },
                execution_time_ms=elapsed_ms,
                error_message=str(e),
            )

    async def _dispatch_synthesize(
        self,
        plan: Any,
        user_request: str,
        anima_mc: Optional[Dict[str, Any]],
        anima_user: Optional[Dict[str, Any]],
    ) -> str:
        """綜合所有 Worker 結果為最終回覆."""
        from museon.agent.dispatch import TaskStatus

        my_name = "MUSEON"
        boss_name = "老闆"
        if anima_mc:
            identity = anima_mc.get("identity", {})
            my_name = identity.get("name", "MUSEON")
            boss = anima_mc.get("boss", {})
            boss_name = boss.get("name", "老闆")

        # 組建結果摘要
        results_digest = ""
        for i, result in enumerate(plan.results):
            task = (
                plan.tasks[i] if i < len(plan.tasks) else None
            )
            skill_name = task.skill_name if task else "unknown"

            if result.status == TaskStatus.COMPLETED:
                full_resp = result.result.get(
                    "full_response", ""
                )[:self._WORKER_RESPONSE_DIGEST_LEN]
                score = result.quality.get("self_score", "N/A")
                results_digest += (
                    f"\n### 分析 {i + 1}: {skill_name} "
                    f"(品質: {score})\n{full_resp}\n"
                )
            else:
                results_digest += (
                    f"\n### 分析 {i + 1}: {skill_name} — 未完成\n"
                    f"原因：{result.error_message}\n"
                )

        failed_count = sum(
            1 for r in plan.results
            if r.status == TaskStatus.FAILED
        )
        degradation = ""
        if failed_count > 0:
            degradation = (
                f"\n注意：有 {failed_count} 個分析未成功，"
                f"回覆中適當提及限制。\n"
            )

        system_prompt = (
            f"你是 {my_name}，{boss_name} 的 AI 助理。\n\n"
            f"## 任務\n"
            f"你剛完成多步驟分析。以下是各步驟結果。\n"
            f"整合成一個連貫自然的回覆。\n\n"
            f"## DNA27 核心規則\n"
            f"- 先判斷使用者能量狀態\n"
            f"- 給建議時說甜頭和代價\n"
            f"- 不確定就說不確定\n"
            f"- 用繁體中文\n\n"
            f"## 分析結果\n{results_digest}\n{degradation}\n"
            f"## 整合規則\n"
            f"1. 不暴露「子任務」「Worker」「dispatch」等術語\n"
            f"2. 用自然段落，像一次想清楚的回覆\n"
            f"3. 保留關鍵洞見，去除重複\n"
            f"4. 結尾提供明確的「最小下一步」\n"
            f"5. 回覆 800-2000 字\n"
        )

        messages = [{"role": "user", "content": user_request}]

        final_text = await self._call_llm_with_model(
            system_prompt=system_prompt,
            messages=messages,
            model=self._SYNTHESIZE_MODEL,
            max_tokens=self._LLM_MAX_TOKENS,
        )

        final_text = self._strip_system_leakage(final_text)
        return final_text

    async def _dispatch_fallback(
        self,
        content: str,
        session_id: str,
        matched_skills: List[Dict[str, Any]],
        anima_mc: Optional[Dict[str, Any]],
        anima_user: Optional[Dict[str, Any]],
        sub_agent_context: str,
    ) -> str:
        """Dispatch 失敗時回到正常 pipeline."""
        logger.warning("Dispatch fallback → normal pipeline")
        system_prompt = self._build_system_prompt(
            anima_mc=anima_mc,
            anima_user=anima_user,
            matched_skills=matched_skills,
            sub_agent_context=sub_agent_context,
        )
        history = self._get_session_history(session_id)
        history.append({"role": "user", "content": content})
        if len(history) > self._SESSION_HISTORY_TRIM:
            history[:] = history[-self._SESSION_HISTORY_TRIM:]
        response_text = await self._call_llm(
            system_prompt=system_prompt,
            messages=history,
            anima_mc=anima_mc,
        )
        history.append({
            "role": "assistant", "content": response_text,
        })
        return response_text

    def _parse_orchestrator_response(
        self,
        response_text: str,
        active_skills: List[Dict[str, Any]],
        plan_id: str,
    ) -> list:
        """解析 Orchestrator JSON 回覆為 TaskPackage 列表."""
        import re
        from museon.agent.dispatch import TaskPackage

        # L1-2: 清理 markdown code fences（LLM 常用 ```json ... ``` 包裝）
        cleaned = response_text.strip()
        cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```\s*$', '', cleaned)

        json_match = re.search(r'\[[\s\S]*\]', cleaned)

        # L1-2: fallback — 嘗試匹配單一 JSON 物件，包成陣列
        if not json_match:
            obj_match = re.search(r'\{[\s\S]*\}', cleaned)
            if obj_match:
                try:
                    obj = json.loads(obj_match.group())
                    if "skill_name" in obj:
                        cleaned = json.dumps([obj])
                        json_match = re.search(r'\[[\s\S]*\]', cleaned)
                except json.JSONDecodeError:
                    pass

        if not json_match:
            logger.warning("Orchestrator 回覆中無 JSON 陣列")
            logger.debug(f"Orchestrator raw response: {response_text[:500]}")
            return []

        try:
            tasks_data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.error(f"Orchestrator JSON 解析失敗: {e}", exc_info=True)
            return []

        valid_names = {s.get("name") for s in active_skills}
        tasks = []
        for i, td in enumerate(tasks_data[:self._ORCHESTRATOR_MAX_TASKS]):
            skill_name = td.get("skill_name", "")
            if skill_name not in valid_names:
                logger.warning(
                    f"Orchestrator 引用不存在的 Skill: "
                    f"{skill_name}"
                )
                continue

            tasks.append(TaskPackage(
                task_id=f"{plan_id}_task_{i:02d}",
                skill_name=skill_name,
                skill_focus=td.get("skill_focus", ""),
                skill_depth=td.get("skill_depth", "standard"),
                expected_output=td.get("expected_output", ""),
                execution_order=i,
                depends_on=td.get("depends_on", []),
                model_preference=td.get(
                    "model_preference", "haiku",
                ),
            ))

        return tasks

    def _parse_worker_quality(
        self, response_text: str,
    ) -> Dict[str, Any]:
        """從 Worker 回覆中提取自評 JSON."""
        import re

        json_match = re.search(
            r'\{\s*"self_score"[\s\S]*?\}', response_text,
        )
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError as e:
                logger.debug(f"self-assessment JSON 解析失敗: {e}")

        return {
            "self_score": self._DEFAULT_QUALITY_SCORE,
            "confidence": 0.5,
            "limitations": "self-assessment not provided",
        }

    @staticmethod
    def _strip_system_leakage(text: str) -> str:
        """過濾回覆中可能洩漏的系統提示內容.

        偵測並移除：
        - 看起來像系統 section 標題的行（## 我的身份、## DNA27 核心 等）
        - 系統提示詞的直接複製（核心價值觀列表、Style Always 等）
        - 內部架構描述（如 ANIMA、MUSEON Brain 等）

        Args:
            text: LLM 原始回覆

        Returns:
            清理後的回覆
        """
        import re

        # 已知系統 section 標題模式
        system_headings = [
            r'^#{1,3}\s*(MUSEON|DNA27|我的身份|老闆的畫像|當前匹配的能力模組|成長階段行為|核心價值觀)',
            r'^#{1,3}\s*(Style Always|Style Never|三迴圈節奏路由|回應合約|盲點義務|語言規則)',
            r'^#{1,3}\s*(子代理回報)',
        ]

        # 系統內部關鍵字（出現在行首，高度可疑）
        system_line_patterns = [
            r'^-\s*(真實優先|演化至上|代價透明|長期複利|結構是照顧人的方式)\s*[—–\-(（]',
            r'^-\s*(fast_loop|exploration_loop|slow_loop)\s*[（(]',
            r'^\*?\*?成長階段\*?\*?：\s*(infant|child|teen|adult)',
            r'^信任等級：\w+\s*\|\s*總互動次數：\d+',
        ]

        # ── 內部思考標記（deep-think 模組的輸出，不應對外顯示）──
        internal_markers = [
            r'^\*?\*?\[內在思考審視\]\*?\*?',
            r'^\*?\*?\[Phase\s*\d+[:\s]',
            r'^\*?\*?\[訊號分流\]\*?\*?',
            r'^\*?\*?\[輸入審視\]\*?\*?',
            r'^\*?\*?\[輸出審計\]\*?\*?',
            r'^\*?\*?深度思考摘要\*?\*?',
        ]

        lines = text.split('\n')
        cleaned = []
        skip_section = False

        for line in lines:
            stripped = line.strip()

            # 檢查系統標題
            is_system_heading = False
            for pat in system_headings:
                if re.match(pat, stripped):
                    is_system_heading = True
                    skip_section = True
                    break

            if is_system_heading:
                continue

            # 檢查系統行
            is_system_line = False
            for pat in system_line_patterns:
                if re.match(pat, stripped):
                    is_system_line = True
                    break

            if is_system_line:
                continue

            # 檢查內部思考標記（deep-think 輸出）
            is_internal_marker = False
            for pat in internal_markers:
                if re.match(pat, stripped):
                    is_internal_marker = True
                    break

            if is_internal_marker:
                # 跳過標記行本身 + 緊接的思考內容（到下一個空行為止）
                skip_section = True
                continue

            # 如果前面跳過了系統 section，遇到空行或新段落時恢復
            if skip_section:
                if not stripped:
                    skip_section = False
                    continue
                # 如果還在系統 section 內（以 - 開頭的列表項），繼續跳過
                if stripped.startswith('-') or stripped.startswith('*'):
                    continue
                # 遇到正常內容，恢復
                skip_section = False

            cleaned.append(line)

        result = '\n'.join(cleaned).strip()

        # 如果過濾掉太多（超過 80%），回傳原文（避免誤殺）
        if len(result) < len(text) * BrainDispatchMixin._LEAKAGE_FILTER_RATIO and len(text) > BrainDispatchMixin._LEAKAGE_MIN_TEXT_LEN:
            result = text.strip()

        # ── 最終清理：移除不應出現在對外回覆中的系統術語 ──
        forbidden_output_terms = {
            'DNA27': '核心系統',
            'MUSEON Brain': '核心引擎',
            'ANIMA_MC': '個性設定',
            'ceremony_state': '狀態紀錄',
            'Style Always': '風格規則',
            'Style Never': '風格規則',
        }
        for term, replacement in forbidden_output_terms.items():
            if term in result:
                result = result.replace(term, replacement)

        return result
