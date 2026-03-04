"""計畫引擎 (Plan Engine) 測試.

涵蓋 BDD 12-plan-engine.feature 的所有 Scenario：
- 觸發評估（自動偵測 vs 直接執行）
- Stage 1 Research（事實收集 + 假設標記）
- Stage 2 Plan（方法說明 + 變更清單 + 風險分析）
- Stage 3 Annotate（AI 寫 -> 人批註 -> AI 更新、6 輪上限）
- Stage 4 Todo（原子任務、階段分組）
- Stage 5 Execute（機械執行、遇問題暫停）
- Stage 6 Close（摘要 + 結晶 + 刪除 plan.md）
- 硬閘門（NO-GUESS, NO-SKIP-ANNOTATE, REVERT-OVER-PATCH, NO-EXECUTE-WITHOUT-APPROVAL）
- 三迴圈適配（fast/exploration/slow）
- 跨對話持久化
"""

import json
import pytest
from datetime import datetime
from pathlib import Path


@pytest.fixture
def data_dir(tmp_path):
    """建立測試用資料目錄."""
    plans_dir = tmp_path / "plans" / "active"
    plans_dir.mkdir(parents=True)
    archive_dir = tmp_path / "plans" / "archive"
    archive_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def plan_engine(data_dir):
    """建立 PlanEngine 測試實例."""
    from museon.agent.plan_engine import PlanEngine
    return PlanEngine(data_dir=str(data_dir))


def _make_research(plan_engine, task="測試任務"):
    """輔助：執行 Stage 1 並返回 ResearchReport."""
    from museon.agent.plan_engine import ResearchFact, Assumption
    return plan_engine.stage_1_research(
        task_description=task,
        facts=[ResearchFact(content="事實 A", source="file.py:10")],
        assumptions=[Assumption(content="假設 A", verification_method="手動確認")],
        questions=["需要確認的問題 A？"],
    )


def _make_plan(plan_engine, task="測試任務"):
    """輔助：執行 Stage 1 + Stage 2 並返回 PlanDocument."""
    from museon.agent.plan_engine import ChangeItem, RiskItem
    research = _make_research(plan_engine, task)
    return plan_engine.stage_2_plan(
        research=research,
        task_description=task,
        method_explanation="使用方案 A，因為風險較低",
        change_list=[ChangeItem(action="修改", path="src/main.py", description="重構核心邏輯")],
        risk_analysis=[RiskItem(description="可能影響 API", impact="medium", mitigation="版本鎖定")],
    )


def _make_annotated_plan(plan_engine, task="測試任務"):
    """輔助：執行 Stage 1 + 2 + 3(annotate) 並返回 annotated PlanDocument."""
    plan = _make_plan(plan_engine, task)
    plan = plan_engine.stage_3_annotate(
        plan=plan,
        user_annotations="方案看起來不錯，風險評估需要加強",
    )
    return plan


def _make_approved_plan(plan_engine, task="測試任務"):
    """輔助：執行 Stage 1 + 2 + 3 + approve 並返回 approved PlanDocument."""
    plan = _make_annotated_plan(plan_engine, task)
    plan = plan_engine.approve_plan(plan)
    return plan


# ════════════════════════════════════════════
# Section 1: 觸發評估
# ════════════════════════════════════════════

class TestTriggerAssessment:
    """測試觸發評估."""

    def test_complex_task_triggers_plan(self, plan_engine):
        """複雜任務觸發計畫引擎."""
        from museon.agent.plan_engine import PlanDecision
        decision = plan_engine.assess_trigger(
            content="幫我重構整個認證系統",
            context={"estimated_files": 5, "estimated_minutes": 30},
        )
        assert isinstance(decision, PlanDecision)
        assert decision.should_plan is True

    def test_simple_task_skips_plan(self, plan_engine):
        """簡單任務跳過計畫引擎."""
        decision = plan_engine.assess_trigger(
            content="修正 README 的錯字",
            context={"estimated_files": 1, "estimated_minutes": 2},
        )
        assert decision.should_plan is False

    def test_user_explicit_skip(self, plan_engine):
        """使用者說「直接做」跳過計畫."""
        decision = plan_engine.assess_trigger(
            content="直接做，幫我改一下這個函數",
            context={},
        )
        assert decision.should_plan is False

    def test_keyword_trigger(self, plan_engine):
        """關鍵字觸發計畫引擎."""
        keywords = ["重構", "refactor", "migration", "redesign", "重新設計"]
        for kw in keywords:
            decision = plan_engine.assess_trigger(
                content=f"我想{kw}這個模組",
                context={"estimated_files": 3},
            )
            assert decision.should_plan is True, f"Keyword '{kw}' should trigger plan"

    def test_three_plus_files_triggers_plan(self, plan_engine):
        """3+ 檔案 + 其他信號觸發計畫引擎.

        assess_trigger 的閾值為 0.4，3+ 檔案加分 0.3，
        需要額外信號（如內容長度或執行時間）才能達到門檻。
        """
        decision = plan_engine.assess_trigger(
            content="修改這個功能需要調整多個模組的接口和實作，預計影響範圍較大",
            context={"estimated_files": 4, "estimated_minutes": 15},
        )
        assert decision.should_plan is True

    def test_complexity_score_range(self, plan_engine):
        """複雜度分數在 0-1 範圍."""
        decision = plan_engine.assess_trigger(
            content="大型專案重構",
            context={"estimated_files": 10, "estimated_minutes": 120},
        )
        assert 0 <= decision.complexity_score <= 1.0

    def test_force_plan_via_context(self, plan_engine):
        """force_plan 強制啟動計畫引擎."""
        decision = plan_engine.assess_trigger(
            content="做一件小事",
            context={"force_plan": True},
        )
        assert decision.should_plan is True
        assert decision.complexity_score == 1.0

    def test_suggested_loop_is_loop_type_enum(self, plan_engine):
        """suggested_loop 是 LoopType 枚舉."""
        from museon.agent.plan_engine import LoopType
        decision = plan_engine.assess_trigger(
            content="重新設計整個架構",
            context={"estimated_files": 10},
        )
        assert isinstance(decision.suggested_loop, LoopType)


# ════════════════════════════════════════════
# Section 2: Stage 1 -- Research
# ════════════════════════════════════════════

class TestStage1Research:
    """測試 Research 階段."""

    def test_research_report_has_facts(self, plan_engine):
        """研究報告包含事實."""
        from museon.agent.plan_engine import ResearchFact
        report = plan_engine.stage_1_research(
            task_description="重構記憶系統",
            facts=[ResearchFact(content="記憶層有 4 層", source="memory.py:20")],
        )
        assert report is not None
        assert hasattr(report, "facts")
        assert isinstance(report.facts, list)
        assert len(report.facts) == 1

    def test_research_marks_assumptions(self, plan_engine):
        """研究報告標記假設."""
        from museon.agent.plan_engine import Assumption
        report = plan_engine.stage_1_research(
            task_description="升級資料庫架構",
            assumptions=[Assumption(content="現有 API 不會中斷", verification_method="檢查 API 文件")],
        )
        assert hasattr(report, "assumptions")
        assert isinstance(report.assumptions, list)
        assert len(report.assumptions) == 1

    def test_research_has_questions(self, plan_engine):
        """研究報告包含問題."""
        report = plan_engine.stage_1_research(
            task_description="功能升級",
            questions=["是否需要向後相容？", "目標版本是什麼？"],
        )
        assert len(report.questions) == 2

    def test_hg_no_guess_demotes_sourceless_facts(self, plan_engine):
        """HG-PLAN-NO-GUESS: 無來源的事實會被降級為假設."""
        from museon.agent.plan_engine import ResearchFact
        report = plan_engine.stage_1_research(
            task_description="測試",
            facts=[ResearchFact(content="無來源事實", source="")],
        )
        # 無來源事實被移到 assumptions
        assert len(report.facts) == 0
        assert len(report.assumptions) >= 1

    def test_research_creates_plan_file(self, plan_engine, data_dir):
        """研究階段建立計畫文件."""
        _make_research(plan_engine)
        state_path = data_dir / "plans" / "active" / "state.json"
        assert state_path.exists()


# ════════════════════════════════════════════
# Section 3: Stage 2 -- Plan
# ════════════════════════════════════════════

class TestStage2Plan:
    """測試 Plan 階段."""

    def test_plan_document_structure(self, plan_engine):
        """計畫文件有完整結構."""
        from museon.agent.plan_engine import PlanStatus
        plan = _make_plan(plan_engine)
        assert plan is not None
        assert plan.status == PlanStatus.DRAFT
        assert plan.method_explanation != ""
        assert len(plan.change_list) >= 1
        assert len(plan.risk_analysis) >= 1

    def test_plan_saved_as_markdown(self, plan_engine, data_dir):
        """計畫儲存為 Markdown 檔案."""
        _make_plan(plan_engine)
        plan_path = data_dir / "plans" / "active" / "plan.md"
        assert plan_path.exists()
        content = plan_path.read_text(encoding="utf-8")
        assert "# " in content  # Markdown heading

    def test_plan_current_stage_is_plan(self, plan_engine):
        """Stage 2 後 current_stage 為 PLAN."""
        from museon.agent.plan_engine import StageType
        plan = _make_plan(plan_engine)
        assert plan.current_stage == StageType.PLAN


# ════════════════════════════════════════════
# Section 4: Stage 3 -- Annotate
# ════════════════════════════════════════════

class TestStage3Annotate:
    """測試 Annotate 階段."""

    def test_annotation_updates_plan(self, plan_engine):
        """批註更新計畫."""
        from museon.agent.plan_engine import PlanStatus
        plan = _make_plan(plan_engine)

        updated = plan_engine.stage_3_annotate(
            plan=plan,
            user_annotations="方案 A 看起來不錯，但風險評估需要加強",
        )
        assert updated.annotation_round == 1
        assert len(updated.annotations) == 1
        assert updated.status == PlanStatus.ANNOTATING

    def test_annotation_round_increments(self, plan_engine):
        """多輪批註輪次遞增."""
        plan = _make_plan(plan_engine)

        plan = plan_engine.stage_3_annotate(plan, "第 1 輪批註")
        assert plan.annotation_round == 1

        plan = plan_engine.stage_3_annotate(plan, "第 2 輪批註")
        assert plan.annotation_round == 2

        plan = plan_engine.stage_3_annotate(plan, "第 3 輪批註")
        assert plan.annotation_round == 3

    def test_annotation_max_6_rounds_warns_but_continues(self, plan_engine):
        """批註超過 6 輪會警告但不中止（僅記錄）."""
        plan = _make_plan(plan_engine)

        # 做 7 輪批註 -- 第 7 輪不會拋出例外，只記錄警告
        for i in range(7):
            plan = plan_engine.stage_3_annotate(
                plan=plan,
                user_annotations=f"第 {i + 1} 輪批註內容",
            )
        assert plan.annotation_round == 7

    def test_annotate_never_executes(self, plan_engine):
        """批註階段永遠只更新 plan.md，不執行."""
        from museon.agent.plan_engine import PlanStatus
        plan = _make_plan(plan_engine)

        updated = plan_engine.stage_3_annotate(
            plan=plan,
            user_annotations="看起來沒問題，全部執行",
        )
        # 即使使用者說「全部執行」，狀態也只是 annotating
        assert updated.status == PlanStatus.ANNOTATING
        assert updated.status != PlanStatus.EXECUTING


# ════════════════════════════════════════════
# Section 5: approve_plan
# ════════════════════════════════════════════

class TestApprovePlan:
    """測試計畫核准流程."""

    def test_approve_after_annotation(self, plan_engine):
        """經過至少一輪批註後可以核准."""
        from museon.agent.plan_engine import PlanStatus
        plan = _make_annotated_plan(plan_engine)
        approved = plan_engine.approve_plan(plan)
        assert approved.status == PlanStatus.APPROVED

    def test_approve_without_annotation_raises_error(self, plan_engine):
        """未經批註就核准會拋出 AnnotationSkippedError."""
        from museon.agent.plan_engine import AnnotationSkippedError
        plan = _make_plan(plan_engine)

        with pytest.raises(AnnotationSkippedError):
            plan_engine.approve_plan(plan)


# ════════════════════════════════════════════
# Section 6: Stage 4 -- Todo
# ════════════════════════════════════════════

class TestStage4Todo:
    """測試 Todo 階段."""

    def test_todo_requires_approved_plan(self, plan_engine):
        """Stage 4 需要計畫已核准."""
        from museon.agent.plan_engine import PlanNotApprovedError, TodoItem
        plan = _make_plan(plan_engine)
        # plan.status 仍是 DRAFT

        with pytest.raises(PlanNotApprovedError):
            plan_engine.stage_4_todo(
                plan=plan,
                todos=[TodoItem(content="任務 A", phase=1)],
            )

    def test_todos_are_atomic(self, plan_engine):
        """Todo 項目是原子任務."""
        from museon.agent.plan_engine import TodoItem
        plan = _make_approved_plan(plan_engine)

        todo_items = [
            TodoItem(content="建立測試檔案", phase=1),
            TodoItem(content="實作核心函數", phase=1),
            TodoItem(content="執行測試", phase=2, dependencies=[0, 1]),
        ]
        todos = plan_engine.stage_4_todo(plan=plan, todos=todo_items)
        assert isinstance(todos, list)
        assert len(todos) == 3
        for todo in todos:
            assert hasattr(todo, "content")
            assert hasattr(todo, "phase")
            assert hasattr(todo, "done")

    def test_todos_grouped_by_phase(self, plan_engine):
        """Todo 按階段分組."""
        from museon.agent.plan_engine import TodoItem
        plan = _make_approved_plan(plan_engine)

        todo_items = [
            TodoItem(content="Phase 1 任務", phase=1),
            TodoItem(content="Phase 2 任務 A", phase=2),
            TodoItem(content="Phase 2 任務 B", phase=2),
        ]
        todos = plan_engine.stage_4_todo(plan=plan, todos=todo_items)
        phases = {t.phase for t in todos}
        assert phases == {1, 2}

    def test_todo_with_no_items(self, plan_engine):
        """空任務清單也可以建立."""
        plan = _make_approved_plan(plan_engine)
        todos = plan_engine.stage_4_todo(plan=plan, todos=[])
        assert todos == []


# ════════════════════════════════════════════
# Section 7: Stage 5 -- Execute
# ════════════════════════════════════════════

class TestStage5Execute:
    """測試 Execute 階段."""

    def test_execute_marks_task_done(self, plan_engine):
        """執行成功標記任務完成."""
        from museon.agent.plan_engine import TodoItem
        plan = _make_approved_plan(plan_engine)
        plan_engine.stage_4_todo(
            plan=plan,
            todos=[TodoItem(content="任務 A", phase=1)],
        )

        result = plan_engine.stage_5_execute_item(
            plan=plan,
            task_index=0,
            success=True,
            output="執行成功",
        )
        assert result.success is True
        assert plan.todos[0].done is True

    def test_execute_without_approval_raises_error(self, plan_engine):
        """未核准計畫嘗試執行會拋出 PlanNotApprovedError."""
        from museon.agent.plan_engine import PlanNotApprovedError, TodoItem
        plan = _make_plan(plan_engine)
        plan.todos = [TodoItem(content="未批准的任務", phase=1)]

        with pytest.raises(PlanNotApprovedError):
            plan_engine.stage_5_execute_item(
                plan=plan,
                task_index=0,
                success=True,
            )

    def test_execute_invalid_index(self, plan_engine):
        """無效任務索引返回失敗結果."""
        from museon.agent.plan_engine import TodoItem
        plan = _make_approved_plan(plan_engine)
        plan_engine.stage_4_todo(
            plan=plan,
            todos=[TodoItem(content="唯一任務", phase=1)],
        )

        result = plan_engine.stage_5_execute_item(
            plan=plan,
            task_index=99,
            success=True,
        )
        assert result.success is False

    def test_execute_failed_task(self, plan_engine):
        """執行失敗不標記為完成."""
        from museon.agent.plan_engine import TodoItem
        plan = _make_approved_plan(plan_engine)
        plan_engine.stage_4_todo(
            plan=plan,
            todos=[TodoItem(content="會失敗的任務", phase=1)],
        )

        result = plan_engine.stage_5_execute_item(
            plan=plan,
            task_index=0,
            success=False,
            error="編譯錯誤",
        )
        assert result.success is False
        assert plan.todos[0].done is False

    def test_execute_out_of_plan_raises_error(self, plan_engine):
        """計畫外問題觸發 OutOfPlanError."""
        from museon.agent.plan_engine import TodoItem, OutOfPlanError
        plan = _make_approved_plan(plan_engine)
        plan_engine.stage_4_todo(
            plan=plan,
            todos=[TodoItem(content="會遇到意外的任務", phase=1)],
        )

        with pytest.raises(OutOfPlanError):
            plan_engine.stage_5_execute_item(
                plan=plan,
                task_index=0,
                out_of_plan=True,
                out_of_plan_description="發現需要額外的依賴",
            )

    def test_execute_respects_dependencies(self, plan_engine):
        """未完成的依賴任務阻止執行."""
        from museon.agent.plan_engine import TodoItem
        plan = _make_approved_plan(plan_engine)
        plan_engine.stage_4_todo(
            plan=plan,
            todos=[
                TodoItem(content="前置任務", phase=1),
                TodoItem(content="依賴任務", phase=2, dependencies=[0]),
            ],
        )

        # 嘗試執行依賴任務（前置任務未完成）
        result = plan_engine.stage_5_execute_item(
            plan=plan,
            task_index=1,
            success=True,
        )
        assert result.success is False
        assert "依賴" in result.error or "0" in result.error


# ════════════════════════════════════════════
# Section 8: Stage 6 -- Close
# ════════════════════════════════════════════

class TestStage6Close:
    """測試 Close 階段."""

    def test_close_generates_summary(self, plan_engine):
        """Close 生成摘要."""
        from museon.agent.plan_engine import PlanStatus, TodoItem
        plan = _make_approved_plan(plan_engine)
        plan_engine.stage_4_todo(
            plan=plan,
            todos=[TodoItem(content="已完成任務", phase=1, done=True)],
        )

        close_report = plan_engine.stage_6_close(
            plan=plan,
            summary="測試計畫執行完成",
        )
        assert close_report is not None
        assert close_report.summary == "測試計畫執行完成"
        assert close_report.completed_tasks == 1
        assert close_report.total_tasks == 1

    def test_close_deletes_plan_md(self, plan_engine, data_dir):
        """Close 刪除 plan.md."""
        plan = _make_approved_plan(plan_engine)

        plan_path = data_dir / "plans" / "active" / "plan.md"
        assert plan_path.exists()

        plan_engine.stage_6_close(plan=plan, delete_plan=True)
        assert not plan_path.exists()

    def test_close_archives_plan(self, plan_engine, data_dir):
        """Close 存檔計畫."""
        plan = _make_approved_plan(plan_engine, task="歸檔測試計畫")

        plan_engine.stage_6_close(
            plan=plan,
            archive=True,
            delete_plan=True,
        )

        archive_dir = data_dir / "plans" / "archive"
        archive_files = list(archive_dir.glob("*.md"))
        assert len(archive_files) >= 1

    def test_close_with_lessons_and_crystals(self, plan_engine):
        """Close 包含教訓和知識結晶."""
        from museon.agent.plan_engine import KnowledgeCrystal
        plan = _make_approved_plan(plan_engine)

        close_report = plan_engine.stage_6_close(
            plan=plan,
            summary="包含教訓的結案",
            lessons_learned=["不要跳過測試", "先做原型"],
            knowledge_crystals=[
                KnowledgeCrystal(
                    content="重構前先寫測試",
                    crystal_type="lesson",
                    source_plan="測試計畫",
                )
            ],
        )
        assert len(close_report.lessons_learned) >= 2
        assert len(close_report.knowledge_crystals) == 1

    def test_close_sets_status_closed(self, plan_engine):
        """Close 將狀態設為 CLOSED."""
        from museon.agent.plan_engine import PlanStatus
        plan = _make_approved_plan(plan_engine)
        plan_engine.stage_6_close(plan=plan)
        assert plan.status == PlanStatus.CLOSED


# ════════════════════════════════════════════
# Section 9: 硬閘門
# ════════════════════════════════════════════

class TestHardGates:
    """測試硬閘門."""

    def test_hg_no_execute_without_approval(self, plan_engine):
        """HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: 未批准不可執行."""
        from museon.agent.plan_engine import PlanNotApprovedError, TodoItem
        plan = _make_plan(plan_engine)
        plan.todos = [TodoItem(content="未批准的任務", phase=1)]

        with pytest.raises(PlanNotApprovedError):
            plan_engine.stage_5_execute_item(
                plan=plan,
                task_index=0,
                success=True,
            )

    def test_hg_no_skip_annotate(self, plan_engine):
        """HG-PLAN-NO-SKIP-ANNOTATE: 不可跳過批註階段."""
        from museon.agent.plan_engine import PlanNotApprovedError, TodoItem
        plan = _make_plan(plan_engine)
        # plan.status 仍是 DRAFT，嘗試建立 Todo 應被拒絕

        with pytest.raises(PlanNotApprovedError):
            plan_engine.stage_4_todo(
                plan=plan,
                todos=[TodoItem(content="跳過批註的任務", phase=1)],
            )

    def test_hg_no_skip_annotate_on_approve(self, plan_engine):
        """HG-PLAN-NO-SKIP-ANNOTATE: 未批註就核准被拒絕."""
        from museon.agent.plan_engine import AnnotationSkippedError
        plan = _make_plan(plan_engine)

        with pytest.raises(AnnotationSkippedError):
            plan_engine.approve_plan(plan)

    def test_hg_revert_over_patch(self, plan_engine):
        """HG-PLAN-REVERT-OVER-PATCH: 回退任務而非修補."""
        from museon.agent.plan_engine import TodoItem, PlanStatus
        plan = _make_approved_plan(plan_engine)
        plan_engine.stage_4_todo(
            plan=plan,
            todos=[TodoItem(content="會被回退的任務", phase=1, done=True)],
        )

        entry = plan_engine.revert_task(
            plan=plan,
            task_index=0,
            reason="方向性錯誤",
            affected_scope="核心模組",
            lesson="需要先做原型驗證",
        )
        assert entry.reason == "方向性錯誤"
        assert plan.todos[0].done is False
        assert plan.status == PlanStatus.PAUSED
        assert len(plan.revert_log) == 1

    def test_check_all_hard_gates(self, plan_engine):
        """check_all_hard_gates 返回所有違規."""
        plan = _make_plan(plan_engine)
        violations = plan_engine.check_all_hard_gates(plan)
        # DRAFT 計畫不會有 execute 相關違規
        assert isinstance(violations, list)

    def test_hg_no_guess_check(self, plan_engine):
        """HG-PLAN-NO-GUESS: 事實必須有來源."""
        from museon.agent.plan_engine import ResearchFact
        fact_ok = ResearchFact(content="有來源", source="file.py:1")
        fact_bad = ResearchFact(content="無來源", source="")

        assert plan_engine.check_hard_gate_no_guess(fact_ok) is True
        assert plan_engine.check_hard_gate_no_guess(fact_bad) is False


# ════════════════════════════════════════════
# Section 10: 三迴圈適配
# ════════════════════════════════════════════

class TestThreeLoopAdaptation:
    """測試三迴圈適配."""

    def test_fast_loop_skips_plan(self, plan_engine):
        """fast_loop 跳過計畫引擎."""
        decision = plan_engine.assess_trigger(
            content="修正一個小 bug",
            context={},
        )
        assert decision.should_plan is False

    def test_slow_loop_full_workflow(self, plan_engine):
        """slow_loop 走完整流程."""
        from museon.agent.plan_engine import LoopType
        decision = plan_engine.assess_trigger(
            content="重新設計整個架構",
            context={"estimated_files": 10},
        )
        assert decision.should_plan is True
        assert decision.suggested_loop == LoopType.SLOW

    def test_execute_with_fast_loop(self, plan_engine):
        """fast_loop 直接返回已核准的空計畫."""
        from museon.agent.plan_engine import LoopType, PlanStatus
        plan, msg = plan_engine.execute_with_loop(
            loop_type=LoopType.FAST,
            task_description="快速修復",
        )
        assert plan.status == PlanStatus.APPROVED
        assert "fast_loop" in msg

    def test_execute_with_exploration_loop(self, plan_engine):
        """exploration_loop 只做 Research + Plan."""
        from museon.agent.plan_engine import LoopType, PlanStatus
        plan, msg = plan_engine.execute_with_loop(
            loop_type=LoopType.EXPLORATION,
            task_description="探索性任務",
        )
        assert plan.status == PlanStatus.DRAFT
        assert "exploration_loop" in msg

    def test_execute_with_slow_loop(self, plan_engine):
        """slow_loop 做 Research + Plan 後等待批註."""
        from museon.agent.plan_engine import LoopType, PlanStatus
        plan, msg = plan_engine.execute_with_loop(
            loop_type=LoopType.SLOW,
            task_description="完整流程任務",
        )
        assert plan.status == PlanStatus.DRAFT
        assert "slow_loop" in msg


# ════════════════════════════════════════════
# Section 11: 跨對話持久化
# ════════════════════════════════════════════

class TestCrossConversationPersistence:
    """測試跨對話持久化."""

    def test_load_existing_plan(self, plan_engine, data_dir):
        """載入既有計畫."""
        _make_plan(plan_engine, task="跨對話測試")

        # 模擬新對話載入
        from museon.agent.plan_engine import PlanEngine
        new_engine = PlanEngine(data_dir=str(data_dir))
        loaded = new_engine.get_current_plan()
        assert loaded is not None
        assert "跨對話測試" in loaded.title

    def test_resume_from_saved_stage(self, plan_engine, data_dir):
        """從儲存的階段恢復."""
        from museon.agent.plan_engine import StageType
        plan = _make_plan(plan_engine, task="恢復測試")

        # 確認恢復的階段
        stage = plan_engine.get_current_stage()
        assert stage == StageType.PLAN.value

    def test_resume_from_previous_provides_guidance(self, plan_engine):
        """resume_from_previous 提供恢復指引."""
        _make_plan(plan_engine, task="指引測試")

        plan, guidance = plan_engine.resume_from_previous()
        assert plan is not None
        assert "指引測試" in guidance

    def test_no_plan_returns_none(self, data_dir):
        """無計畫時返回 None."""
        from museon.agent.plan_engine import PlanEngine
        engine = PlanEngine(data_dir=str(data_dir))
        assert engine.get_current_plan() is None
        assert engine.get_current_stage() is None


# ════════════════════════════════════════════
# Section 12: PlanDocument 序列化
# ════════════════════════════════════════════

class TestPlanDocumentSerialization:
    """測試 PlanDocument 序列化與反序列化."""

    def test_to_dict_and_from_dict(self, plan_engine):
        """to_dict 和 from_dict 可逆."""
        from museon.agent.plan_engine import PlanDocument
        plan = _make_approved_plan(plan_engine)
        data = plan.to_dict()
        restored = PlanDocument.from_dict(data)

        assert restored.title == plan.title
        assert restored.status == plan.status
        assert restored.annotation_round == plan.annotation_round

    def test_to_markdown(self, plan_engine):
        """to_markdown 產生有效 Markdown."""
        plan = _make_approved_plan(plan_engine)
        md = plan.to_markdown()
        assert "# " in md
        assert plan.title in md
