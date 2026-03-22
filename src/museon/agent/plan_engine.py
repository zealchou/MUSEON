"""Plan Engine — 六階段工作流引擎，物理隔離「想」與「做」.

基於 Boris Tane 的 Annotation Cycle 方法論。
六階段流程：Research -> Plan -> Annotate -> Todo -> Execute -> Close
plan.md 作為人機共享的可變狀態，將混沌起點收斂為清晰計畫後交棒。

核心命題：AI 協作中最貴的失敗不是做錯，是基於錯誤假設往前衝。

硬閘規則（Hard Gates）：
- HG-PLAN-NO-GUESS: 不猜測，要查證
- HG-PLAN-NO-SKIP-ANNOTATE: 不跳過批註階段
- HG-PLAN-REVERT-OVER-PATCH: 方向錯了就回退而非修補
- HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: 未核准不執行

DNA27 三迴圈適配：
- fast_loop: 跳過計畫引擎，直接執行
- exploration_loop: 精簡版（僅 Research + Plan）
- slow_loop: 完整六階段
"""

import json
import logging
import re
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════
# 常數定義
# ════════════════════════════════════════════

# 觸發計畫引擎的關鍵字
PLAN_TRIGGER_KEYWORDS: List[str] = [
    "重構", "refactor", "refactoring",
    "migration", "遷移", "migrate",
    "redesign", "重新設計",
    "新功能", "new feature",
    "整合", "integrate", "integration",
    "架構", "architecture",
]

# 跳過計畫引擎的關鍵字
SKIP_PLAN_KEYWORDS: List[str] = [
    "直接做", "別計畫了", "不用計畫",
    "just do it", "skip plan",
]

# 批註輪次上限
MAX_ANNOTATION_ROUNDS: int = 6

# 預估每個原子任務的分鐘數上限
ATOMIC_TASK_MINUTES: int = 10


# ════════════════════════════════════════════
# 列舉類型
# ════════════════════════════════════════════

class PlanStatus(str, Enum):
    """計畫狀態."""
    DRAFT = "draft"
    ANNOTATING = "annotating"
    APPROVED = "approved"
    EXECUTING = "executing"
    PAUSED = "paused"
    CLOSED = "closed"


class LoopType(str, Enum):
    """DNA27 三迴圈類型."""
    FAST = "fast_loop"
    EXPLORATION = "exploration_loop"
    SLOW = "slow_loop"


class StageType(str, Enum):
    """六階段類型."""
    RESEARCH = "research"
    PLAN = "plan"
    ANNOTATE = "annotate"
    TODO = "todo"
    EXECUTE = "execute"
    CLOSE = "close"


# ════════════════════════════════════════════
# 資料類別
# ════════════════════════════════════════════

@dataclass
class PlanDecision:
    """觸發評估結果 — 是否需要啟動計畫引擎.

    Attributes:
        should_plan: 是否建議啟動計畫引擎
        reason: 判斷理由
        complexity_score: 複雜度分數 (0.0-1.0)
        suggested_loop: 建議的迴圈類型 (fast/exploration/slow)
    """
    should_plan: bool
    reason: str
    complexity_score: float
    suggested_loop: LoopType = LoopType.SLOW

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "should_plan": self.should_plan,
            "reason": self.reason,
            "complexity_score": self.complexity_score,
            "suggested_loop": self.suggested_loop.value,
        }


@dataclass
class ResearchFact:
    """研究階段的事實 — 必須有來源標註.

    Attributes:
        content: 事實內容
        source: 來源（檔案路徑:行號 / 文件 URL / 命令輸出）
        verified: 是否已驗證
    """
    content: str
    source: str
    verified: bool = True

    def to_markdown(self) -> str:
        """轉為 Markdown checkbox 格式."""
        check = "x" if self.verified else " "
        return f"- [{check}] {self.content} — 來源：{self.source}"


@dataclass
class Assumption:
    """未驗證的假設 — 必須附帶驗證方式.

    Attributes:
        content: 假設內容
        verification_method: 如何驗證此假設
        verified: 是否已驗證
        verified_at: 驗證時間（如已驗證）
    """
    content: str
    verification_method: str
    verified: bool = False
    verified_at: Optional[str] = None

    def to_markdown(self) -> str:
        """轉為 Markdown checkbox 格式."""
        check = "x" if self.verified else " "
        status = f"（已驗證 {self.verified_at}）" if self.verified else "（未驗證）"
        return (
            f"- [{check}] 假設：{self.content} {status}\n"
            f"  - 驗證方式：{self.verification_method}"
        )


@dataclass
class ResearchReport:
    """研究階段輸出 — 包含事實、假設、問題.

    Attributes:
        facts: 已確認的事實列表
        assumptions: 未驗證的假設列表
        questions: 需要使用者回答的問題
        timestamp: 研究時間
    """
    facts: List[ResearchFact] = field(default_factory=list)
    assumptions: List[Assumption] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "facts": [asdict(f) for f in self.facts],
            "assumptions": [asdict(a) for a in self.assumptions],
            "questions": self.questions,
            "timestamp": self.timestamp,
        }

    def to_markdown(self) -> str:
        """轉為 Markdown 格式."""
        lines = ["## 研究紀錄\n"]

        # 事實
        if self.facts:
            lines.append("### 已確認事實\n")
            for fact in self.facts:
                lines.append(fact.to_markdown())
            lines.append("")

        # 假設
        if self.assumptions:
            lines.append("### 假設（待驗證）\n")
            for assumption in self.assumptions:
                lines.append(assumption.to_markdown())
            lines.append("")

        # 問題
        if self.questions:
            lines.append("### 待釐清問題\n")
            for q in self.questions:
                lines.append(f"- [ ] {q}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class ChangeItem:
    """變更清單項目 — 什麼 + 在哪裡 + 為什麼.

    Attributes:
        action: 操作（新增/修改/刪除/移動）
        path: 檔案或資源路徑
        description: 說明
    """
    action: str
    path: str
    description: str

    def to_markdown_row(self) -> str:
        """轉為 Markdown 表格行."""
        return f"| {self.action} | {self.path} | {self.description} |"


@dataclass
class RiskItem:
    """風險分析項目 — 甜頭 + 代價 + 回滾計畫.

    Attributes:
        description: 風險描述
        impact: 影響程度 (low/medium/high/critical)
        mitigation: 緩解或回滾計畫
    """
    description: str
    impact: str
    mitigation: str


@dataclass
class Annotation:
    """使用者批註.

    Attributes:
        round_number: 批註輪次
        content: 批註內容
        timestamp: 批註時間
        resolved: 是否已處理
    """
    round_number: int
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved: bool = False


@dataclass
class TodoItem:
    """原子化任務項目 — 可在約 10 分鐘內完成.

    Attributes:
        content: 任務內容
        phase: 所屬階段
        done: 是否已完成
        started_at: 開始執行時間
        completed_at: 完成時間
        dependencies: 依賴的其他任務索引
    """
    content: str
    phase: int = 1
    done: bool = False
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    dependencies: List[int] = field(default_factory=list)

    def to_markdown(self) -> str:
        """轉為 Markdown checkbox 格式."""
        check = "x" if self.done else " "
        deps_str = ""
        if self.dependencies:
            deps_str = f" (依賴: {', '.join(str(d) for d in self.dependencies)})"
        return f"- [{check}] Phase {self.phase}: {self.content}{deps_str}"


@dataclass
class RevertEntry:
    """回退紀錄 — Revert > Patch.

    Attributes:
        timestamp: 回退時間
        reason: 回退原因
        affected_scope: 影響範圍
        lesson: 教訓
        reverted_tasks: 被回退的任務索引
    """
    timestamp: str
    reason: str
    affected_scope: str
    lesson: str
    reverted_tasks: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return asdict(self)


@dataclass
class ExecutionResult:
    """單一任務的執行結果.

    Attributes:
        task_index: 任務索引
        success: 是否成功
        output: 執行輸出
        error: 錯誤訊息（如有）
        out_of_plan: 是否遇到計畫外問題
        out_of_plan_description: 計畫外問題描述
        timestamp: 執行時間
    """
    task_index: int
    success: bool
    output: str = ""
    error: Optional[str] = None
    out_of_plan: bool = False
    out_of_plan_description: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return asdict(self)


@dataclass
class KnowledgeCrystal:
    """知識結晶 — 從計畫中提煉的可複用知識.

    Attributes:
        content: 知識內容
        crystal_type: 結晶類型 (lesson/pattern/guardrail)
        source_plan: 來源計畫標題
        timestamp: 結晶時間
    """
    content: str
    crystal_type: str
    source_plan: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class CloseReport:
    """收尾報告 — 完成內容、問題、教訓.

    Attributes:
        summary: 執行摘要
        completed_tasks: 已完成任務數
        total_tasks: 總任務數
        problems_encountered: 遇到的問題
        lessons_learned: 學到的教訓
        knowledge_crystals: 建議結晶的知識
        revert_entries: 回退紀錄
        timestamp: 收尾時間
    """
    summary: str
    completed_tasks: int
    total_tasks: int
    problems_encountered: List[str] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)
    knowledge_crystals: List[KnowledgeCrystal] = field(default_factory=list)
    revert_entries: List[RevertEntry] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "summary": self.summary,
            "completed_tasks": self.completed_tasks,
            "total_tasks": self.total_tasks,
            "problems_encountered": self.problems_encountered,
            "lessons_learned": self.lessons_learned,
            "knowledge_crystals": [asdict(k) for k in self.knowledge_crystals],
            "revert_entries": [r.to_dict() for r in self.revert_entries],
            "timestamp": self.timestamp,
        }


@dataclass
class PlanDocument:
    """計畫文件 — plan.md 的結構化表示.

    Attributes:
        title: 計畫標題
        status: 計畫狀態
        created_at: 建立時間
        updated_at: 最後更新時間
        method_explanation: 方法說明（為何選這個方案）
        change_list: 變更清單
        risk_analysis: 風險分析
        skill_suggestions: 建議使用的技能
        research: 研究報告
        annotations: 使用者批註
        annotation_round: 目前批註輪次
        todos: 任務清單
        revert_log: 回退紀錄
        close_report: 收尾報告（如已收尾）
        current_stage: 目前所在階段
        loop_type: 迴圈類型
        project_name: 專案名稱（多專案管理用）
    """
    title: str = ""
    status: PlanStatus = PlanStatus.DRAFT
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    method_explanation: str = ""
    change_list: List[ChangeItem] = field(default_factory=list)
    risk_analysis: List[RiskItem] = field(default_factory=list)
    skill_suggestions: List[str] = field(default_factory=list)
    research: Optional[ResearchReport] = None
    annotations: List[Annotation] = field(default_factory=list)
    annotation_round: int = 0
    todos: List[TodoItem] = field(default_factory=list)
    revert_log: List[RevertEntry] = field(default_factory=list)
    close_report: Optional[CloseReport] = None
    current_stage: StageType = StageType.RESEARCH
    loop_type: LoopType = LoopType.SLOW
    project_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典（供 state.json 使用）."""
        return {
            "title": self.title,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "method_explanation": self.method_explanation,
            "change_list": [asdict(c) for c in self.change_list],
            "risk_analysis": [asdict(r) for r in self.risk_analysis],
            "skill_suggestions": self.skill_suggestions,
            "research": self.research.to_dict() if self.research else None,
            "annotations": [asdict(a) for a in self.annotations],
            "annotation_round": self.annotation_round,
            "todos": [asdict(t) for t in self.todos],
            "revert_log": [r.to_dict() for r in self.revert_log],
            "close_report": self.close_report.to_dict() if self.close_report else None,
            "current_stage": self.current_stage.value,
            "loop_type": self.loop_type.value,
            "project_name": self.project_name,
        }

    def to_markdown(self) -> str:
        """轉為人類可讀的 Markdown 格式（plan.md 內容）."""
        lines: List[str] = []

        # 標題與狀態
        lines.append(f"# {self.title}\n")
        lines.append(f"**Status:** {self.status.value}")
        lines.append(f"**Created:** {self.created_at}")
        lines.append(f"**Updated:** {self.updated_at}")
        lines.append(f"**Annotation Round:** {self.annotation_round}/{MAX_ANNOTATION_ROUNDS}")
        lines.append(f"**Stage:** {self.current_stage.value}")
        lines.append(f"**Loop:** {self.loop_type.value}")
        if self.project_name:
            lines.append(f"**Project:** {self.project_name}")
        lines.append("")

        # 研究紀錄
        if self.research:
            lines.append(self.research.to_markdown())

        # 方法說明
        lines.append("## 方法說明\n")
        lines.append(self.method_explanation if self.method_explanation else "_尚未填寫_")
        lines.append("")

        # 變更清單
        lines.append("## 變更清單\n")
        if self.change_list:
            lines.append("| 操作 | 路徑 | 說明 |")
            lines.append("|------|------|------|")
            for item in self.change_list:
                lines.append(item.to_markdown_row())
        else:
            lines.append("_尚未規劃_")
        lines.append("")

        # 風險分析
        lines.append("## 風險分析\n")
        if self.risk_analysis:
            for i, risk in enumerate(self.risk_analysis, 1):
                lines.append(f"### 風險 {i}: {risk.description}\n")
                lines.append(f"- **影響程度:** {risk.impact}")
                lines.append(f"- **緩解/回滾:** {risk.mitigation}")
                lines.append("")
        else:
            lines.append("_尚未分析_")
        lines.append("")

        # 技能建議
        if self.skill_suggestions:
            lines.append("## 技能建議\n")
            for skill in self.skill_suggestions:
                lines.append(f"- {skill}")
            lines.append("")

        # 批註
        if self.annotations:
            lines.append("## 批註\n")
            for ann in self.annotations:
                resolved = " [已處理]" if ann.resolved else ""
                lines.append(
                    f"### Round {ann.round_number}{resolved}\n"
                )
                lines.append(f"_{ann.timestamp}_\n")
                lines.append(ann.content)
                lines.append("")

        # Todo
        if self.todos:
            lines.append("## Todo\n")
            # 按 phase 分組
            phases: Dict[int, List[TodoItem]] = {}
            for todo in self.todos:
                phases.setdefault(todo.phase, []).append(todo)
            for phase_num in sorted(phases.keys()):
                lines.append(f"### Phase {phase_num}\n")
                for todo in phases[phase_num]:
                    lines.append(todo.to_markdown())
                lines.append("")

        # 回退紀錄
        if self.revert_log:
            lines.append("## 回退紀錄\n")
            for entry in self.revert_log:
                lines.append(f"### {entry.timestamp}\n")
                lines.append(f"- **原因:** {entry.reason}")
                lines.append(f"- **影響範圍:** {entry.affected_scope}")
                lines.append(f"- **教訓:** {entry.lesson}")
                lines.append("")

        # 收尾報告
        if self.close_report:
            lines.append("## 收尾摘要\n")
            lines.append(self.close_report.summary)
            lines.append("")
            lines.append(
                f"完成 {self.close_report.completed_tasks}/"
                f"{self.close_report.total_tasks} 項任務"
            )
            if self.close_report.problems_encountered:
                lines.append("\n### 遇到的問題\n")
                for p in self.close_report.problems_encountered:
                    lines.append(f"- {p}")
            if self.close_report.lessons_learned:
                lines.append("\n### 教訓\n")
                for lesson in self.close_report.lessons_learned:
                    lines.append(f"- {lesson}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanDocument":
        """從字典還原（載入 state.json 用）.

        Args:
            data: 序列化的字典

        Returns:
            PlanDocument 實例
        """
        doc = cls()
        doc.title = data.get("title", "")
        doc.status = PlanStatus(data.get("status", "draft"))
        doc.created_at = data.get("created_at", datetime.now().isoformat())
        doc.updated_at = data.get("updated_at", datetime.now().isoformat())
        doc.method_explanation = data.get("method_explanation", "")
        doc.current_stage = StageType(data.get("current_stage", "research"))
        doc.loop_type = LoopType(data.get("loop_type", "slow_loop"))
        doc.annotation_round = data.get("annotation_round", 0)
        doc.skill_suggestions = data.get("skill_suggestions", [])
        doc.project_name = data.get("project_name")

        # 還原變更清單
        for c in data.get("change_list", []):
            doc.change_list.append(ChangeItem(**c))

        # 還原風險分析
        for r in data.get("risk_analysis", []):
            doc.risk_analysis.append(RiskItem(**r))

        # 還原研究報告
        research_data = data.get("research")
        if research_data:
            report = ResearchReport(
                timestamp=research_data.get("timestamp", ""),
                questions=research_data.get("questions", []),
            )
            for f in research_data.get("facts", []):
                report.facts.append(ResearchFact(**f))
            for a in research_data.get("assumptions", []):
                report.assumptions.append(Assumption(**a))
            doc.research = report

        # 還原批註
        for a in data.get("annotations", []):
            doc.annotations.append(Annotation(**a))

        # 還原 todos
        for t in data.get("todos", []):
            doc.todos.append(TodoItem(**t))

        # 還原回退紀錄
        for r in data.get("revert_log", []):
            doc.revert_log.append(RevertEntry(**r))

        # 還原收尾報告
        close_data = data.get("close_report")
        if close_data:
            crystals = [
                KnowledgeCrystal(**k)
                for k in close_data.get("knowledge_crystals", [])
            ]
            reverts = [
                RevertEntry(**r)
                for r in close_data.get("revert_entries", [])
            ]
            doc.close_report = CloseReport(
                summary=close_data.get("summary", ""),
                completed_tasks=close_data.get("completed_tasks", 0),
                total_tasks=close_data.get("total_tasks", 0),
                problems_encountered=close_data.get("problems_encountered", []),
                lessons_learned=close_data.get("lessons_learned", []),
                knowledge_crystals=crystals,
                revert_entries=reverts,
                timestamp=close_data.get("timestamp", ""),
            )

        return doc


# ════════════════════════════════════════════
# 硬閘例外
# ════════════════════════════════════════════

class HardGateViolation(Exception):
    """硬閘違規 — 不可繞過的安全約束."""
    pass


class PlanNotApprovedError(HardGateViolation):
    """HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: 計畫未核准就嘗試執行."""
    pass


class AnnotationSkippedError(HardGateViolation):
    """HG-PLAN-NO-SKIP-ANNOTATE: 試圖跳過批註階段."""
    pass


class OutOfPlanError(Exception):
    """執行中遇到計畫外問題 — 暫停等待人類決定."""
    def __init__(self, description: str):
        self.description = description
        super().__init__(f"計畫外問題：{description}")


# ════════════════════════════════════════════
# PlanStore — 持久化層
# ════════════════════════════════════════════

class PlanStore:
    """計畫持久化層 — 管理 plan.md、state.json、archive、revert_log.

    目錄結構：
        data/plans/active/plan.md      — 人類可讀的 Markdown
        data/plans/active/state.json   — 機器可讀的狀態
        data/plans/archive/            — 已完成計畫的存檔
        data/plans/revert_log.json     — 全域回退紀錄
    """

    def __init__(self, data_dir: str = "data"):
        """初始化持久化層.

        Args:
            data_dir: 資料根目錄
        """
        self.base_dir = Path(data_dir) / "plans"
        self.active_dir = self.base_dir / "active"
        self.archive_dir = self.base_dir / "archive"

        # 確保目錄存在
        self.active_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # 執行緒鎖 — 保護檔案操作
        self._lock = threading.Lock()

        logger.info(f"PlanStore initialized | base_dir: {self.base_dir}")

    @property
    def plan_md_path(self) -> Path:
        """活動計畫的 Markdown 路徑."""
        return self.active_dir / "plan.md"

    @property
    def state_json_path(self) -> Path:
        """活動計畫的狀態 JSON 路徑."""
        return self.active_dir / "state.json"

    @property
    def revert_log_path(self) -> Path:
        """全域回退紀錄路徑."""
        return self.base_dir / "revert_log.json"

    def has_active_plan(self) -> bool:
        """檢查是否有活動中的計畫.

        Returns:
            True 如果存在活動計畫
        """
        return self.state_json_path.exists()

    def save(self, plan: PlanDocument) -> None:
        """儲存計畫 — 同時寫入 plan.md 和 state.json.

        使用執行緒鎖保護檔案操作，確保原子性寫入。

        Args:
            plan: 計畫文件
        """
        with self._lock:
            plan.updated_at = datetime.now().isoformat()

            # 寫入 state.json（機器可讀）
            state_data = plan.to_dict()
            tmp_state = self.state_json_path.with_suffix(".json.tmp")
            try:
                tmp_state.write_text(
                    json.dumps(state_data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp_state.replace(self.state_json_path)
            except Exception as e:
                logger.error(f"儲存 state.json 失敗: {e}")
                # 清理暫存檔
                if tmp_state.exists():
                    tmp_state.unlink()
                raise

            # 寫入 plan.md（人類可讀）
            tmp_md = self.plan_md_path.with_suffix(".md.tmp")
            try:
                tmp_md.write_text(plan.to_markdown(), encoding="utf-8")
                tmp_md.replace(self.plan_md_path)
            except Exception as e:
                logger.error(f"儲存 plan.md 失敗: {e}")
                if tmp_md.exists():
                    tmp_md.unlink()
                raise

            logger.info(
                f"計畫已儲存 | title: {plan.title} | "
                f"status: {plan.status.value} | stage: {plan.current_stage.value}"
            )

    def load(self) -> Optional[PlanDocument]:
        """載入活動計畫.

        優先從 state.json 載入（結構化），失敗時退化到 plan.md。

        Returns:
            PlanDocument 或 None
        """
        with self._lock:
            if not self.state_json_path.exists():
                return None

            try:
                state_text = self.state_json_path.read_text(encoding="utf-8")
                state_data = json.loads(state_text)
                plan = PlanDocument.from_dict(state_data)
                logger.info(
                    f"計畫已載入 | title: {plan.title} | "
                    f"status: {plan.status.value}"
                )
                return plan
            except Exception as e:
                logger.error(f"載入 state.json 失敗: {e}")
                return None

    def delete(self) -> None:
        """刪除活動計畫的所有檔案.

        用於 Close 階段完成後清理工作區。
        """
        with self._lock:
            for path in [self.plan_md_path, self.state_json_path]:
                if path.exists():
                    path.unlink()
                    logger.info(f"已刪除: {path}")

    def archive(self, plan: PlanDocument) -> Path:
        """將計畫存檔到 archive 目錄.

        Args:
            plan: 要存檔的計畫

        Returns:
            存檔檔案的路徑
        """
        with self._lock:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            # 清理標題作為檔名（移除不安全字元）
            safe_title = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", plan.title)[:50]
            archive_name = f"{timestamp}-{safe_title}.md"
            archive_path = self.archive_dir / archive_name

            try:
                archive_path.write_text(
                    plan.to_markdown(), encoding="utf-8"
                )
                logger.info(f"計畫已存檔: {archive_path}")

                # 同時存一份 JSON
                json_path = archive_path.with_suffix(".json")
                json_path.write_text(
                    json.dumps(plan.to_dict(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.error(f"存檔失敗: {e}")
                raise

            return archive_path

    def append_revert_entry(self, entry: RevertEntry) -> None:
        """新增回退紀錄到全域 revert_log.

        Args:
            entry: 回退紀錄
        """
        with self._lock:
            entries: List[Dict[str, Any]] = []
            if self.revert_log_path.exists():
                try:
                    entries = json.loads(
                        self.revert_log_path.read_text(encoding="utf-8")
                    )
                except Exception:
                    entries = []

            entries.append(entry.to_dict())

            self.revert_log_path.write_text(
                json.dumps(entries, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(f"回退紀錄已新增: {entry.reason}")

    def load_revert_log(self) -> List[RevertEntry]:
        """載入全域回退紀錄.

        Returns:
            回退紀錄列表
        """
        if not self.revert_log_path.exists():
            return []

        try:
            entries = json.loads(
                self.revert_log_path.read_text(encoding="utf-8")
            )
            return [RevertEntry(**e) for e in entries]
        except Exception as e:
            logger.error(f"載入回退紀錄失敗: {e}")
            return []

    def list_archives(self) -> List[Path]:
        """列出所有已存檔的計畫.

        Returns:
            存檔檔案路徑列表（按時間排序）
        """
        archives = sorted(self.archive_dir.glob("*.md"))
        return archives


# ════════════════════════════════════════════
# PlanEngine — 六階段工作流引擎
# ════════════════════════════════════════════

class PlanEngine:
    """Plan Engine — 六階段工作流引擎.

    將混沌起點收斂為清晰計畫，物理隔離「想」與「做」。
    核心命題：AI 協作中最貴的失敗不是做錯，是基於錯誤假設往前衝。

    六階段：
    1. Research — 研究：讀取相關檔案，收集事實，標記假設
    2. Plan — 計畫：方法說明、變更清單、風險分析、技能建議
    3. Annotate — 批註：AI 寫 → 人類批註 → AI 更新（最多 6 輪）
    4. Todo — 任務拆解：轉為原子化任務
    5. Execute — 執行：按 Todo 順序機械執行
    6. Close — 收尾：摘要、結晶、清理
    """

    def __init__(self, data_dir: str = "data"):
        """初始化計畫引擎.

        Args:
            data_dir: 資料根目錄
        """
        self.data_dir = Path(data_dir)
        self.store = PlanStore(data_dir=data_dir)

        logger.info("PlanEngine initialized")

    # ═══════════════════════════════════════════
    # 觸發評估
    # ═══════════════════════════════════════════

    def assess_trigger(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> PlanDecision:
        """評估是否需要啟動計畫引擎.

        根據任務內容和上下文判斷複雜度，決定是否建議使用計畫引擎，
        以及建議使用哪種迴圈類型。

        判斷條件（啟動）：
        - 涉及 3+ 個檔案修改
        - 預估執行時間 > 10 分鐘
        - 涉及不可逆操作
        - 包含觸發關鍵字（重構/遷移/重新設計...）
        - 範圍模糊需要釐清

        判斷條件（跳過）：
        - 單一檔案 <= 30 行修改
        - 原因明確、範圍確定
        - 格式調整
        - 使用者明確說不要計畫

        Args:
            content: 使用者訊息內容
            context: 額外上下文（可選），可包含：
                - estimated_files: 預估涉及檔案數
                - estimated_minutes: 預估執行分鐘數
                - has_irreversible_ops: 是否涉及不可逆操作
                - force_plan: 強制啟動（/plan 指令）

        Returns:
            PlanDecision 評估結果
        """
        context = context or {}
        content_lower = content.lower()
        score = 0.0
        reasons: List[str] = []

        # ── 強制啟動 ──
        if context.get("force_plan"):
            return PlanDecision(
                should_plan=True,
                reason="使用者以 /plan 指令強制啟動計畫引擎",
                complexity_score=1.0,
                suggested_loop=LoopType.SLOW,
            )

        # ── 使用者明確拒絕 ──
        for keyword in SKIP_PLAN_KEYWORDS:
            if keyword in content_lower:
                return PlanDecision(
                    should_plan=False,
                    reason=f"使用者明確拒絕計畫：偵測到「{keyword}」",
                    complexity_score=0.1,
                    suggested_loop=LoopType.FAST,
                )

        # ── 關鍵字觸發 ──
        matched_keywords: List[str] = []
        for keyword in PLAN_TRIGGER_KEYWORDS:
            if keyword in content_lower:
                matched_keywords.append(keyword)
                score += 0.25

        if matched_keywords:
            reasons.append(f"觸發關鍵字：{', '.join(matched_keywords)}")

        # ── 預估涉及檔案數 ──
        estimated_files = context.get("estimated_files", 0)
        if estimated_files >= 3:
            score += 0.3
            reasons.append(f"涉及 {estimated_files} 個檔案修改")

        # ── 預估執行時間 ──
        estimated_minutes = context.get("estimated_minutes", 0)
        if estimated_minutes > 10:
            score += 0.2
            reasons.append(f"預估執行時間 {estimated_minutes} 分鐘")

        # ── 不可逆操作 ──
        if context.get("has_irreversible_ops"):
            score += 0.3
            reasons.append("涉及不可逆操作")

        # ── 內容長度啟發 — 長描述通常代表複雜任務 ──
        if len(content) > 200:
            score += 0.1
            reasons.append("任務描述較長，可能需要釐清")

        # ── 模糊性啟發 — 問句或不確定語氣 ──
        vague_patterns = ["怎麼", "如何", "可以", "應該", "更好", "更快", "optimize"]
        vague_matches = [p for p in vague_patterns if p in content_lower]
        if len(vague_matches) >= 2:
            score += 0.15
            reasons.append("範圍可能需要釐清")

        # 正規化分數到 0-1
        score = min(score, 1.0)

        # 決定迴圈類型
        if score >= 0.6:
            suggested_loop = LoopType.SLOW
        elif score >= 0.3:
            suggested_loop = LoopType.EXPLORATION
        else:
            suggested_loop = LoopType.FAST

        should_plan = score >= 0.4

        reason = "；".join(reasons) if reasons else "任務簡單，不需要計畫"

        decision = PlanDecision(
            should_plan=should_plan,
            reason=reason,
            complexity_score=round(score, 2),
            suggested_loop=suggested_loop,
        )

        logger.info(
            f"觸發評估 | should_plan: {should_plan} | "
            f"score: {score:.2f} | loop: {suggested_loop.value}"
        )

        return decision

    # ═══════════════════════════════════════════
    # Stage 1: Research — 研究
    # ═══════════════════════════════════════════

    def stage_1_research(
        self,
        task_description: str,
        facts: Optional[List[ResearchFact]] = None,
        assumptions: Optional[List[Assumption]] = None,
        questions: Optional[List[str]] = None,
    ) -> ResearchReport:
        """Stage 1: 研究階段 — 收集事實，標記假設.

        HG-PLAN-NO-GUESS: 不確定的資訊標記為假設，絕不猜測。
        每項事實必須有來源標註。

        Args:
            task_description: 任務描述
            facts: 已確認的事實（由呼叫者提供，通常是 Brain/LLM 研究後的結果）
            assumptions: 未驗證的假設
            questions: 需要使用者回答的問題

        Returns:
            ResearchReport 研究報告
        """
        report = ResearchReport(
            facts=facts or [],
            assumptions=assumptions or [],
            questions=questions or [],
        )

        # HG-PLAN-NO-GUESS 驗證：所有事實必須有來源
        for fact in report.facts:
            if not fact.source or fact.source.strip() == "":
                logger.warning(
                    f"HG-PLAN-NO-GUESS 違規：事實缺少來源標註 — {fact.content[:50]}"
                )
                # 降級為假設
                report.assumptions.append(Assumption(
                    content=fact.content,
                    verification_method="需要查證來源",
                    verified=False,
                ))
                report.facts.remove(fact)

        # 載入或建立計畫文件
        plan = self.store.load() or PlanDocument()

        if not plan.title:
            plan.title = task_description[:80]

        plan.research = report
        plan.current_stage = StageType.RESEARCH
        plan.status = PlanStatus.DRAFT

        self.store.save(plan)

        logger.info(
            f"Stage 1 Research 完成 | "
            f"facts: {len(report.facts)} | "
            f"assumptions: {len(report.assumptions)} | "
            f"questions: {len(report.questions)}"
        )

        return report

    # ═══════════════════════════════════════════
    # Stage 2: Plan — 計畫
    # ═══════════════════════════════════════════

    def stage_2_plan(
        self,
        research: ResearchReport,
        task_description: str,
        method_explanation: str = "",
        change_list: Optional[List[ChangeItem]] = None,
        risk_analysis: Optional[List[RiskItem]] = None,
        skill_suggestions: Optional[List[str]] = None,
    ) -> PlanDocument:
        """Stage 2: 計畫階段 — 建立計畫文件.

        計畫必須包含：方法說明、變更清單、風險分析、技能建議。
        所有假設必須可追溯，未驗證假設不可作為計畫的唯一依據。

        Args:
            research: Stage 1 的研究報告
            task_description: 任務描述
            method_explanation: 方法說明（為何選這個方案 + 替代方案 + 取捨）
            change_list: 變更清單
            risk_analysis: 風險分析
            skill_suggestions: 建議使用的技能

        Returns:
            PlanDocument 計畫文件
        """
        plan = self.store.load() or PlanDocument()

        plan.title = plan.title or task_description[:80]
        plan.research = research
        plan.method_explanation = method_explanation
        plan.change_list = change_list or []
        plan.risk_analysis = risk_analysis or []
        plan.skill_suggestions = skill_suggestions or []
        plan.current_stage = StageType.PLAN
        plan.status = PlanStatus.DRAFT

        # 驗證：引用未驗證假設時標記警告
        unverified = [
            a for a in research.assumptions if not a.verified
        ]
        if unverified:
            logger.warning(
                f"計畫依賴 {len(unverified)} 個未驗證假設，"
                f"需在批註階段確認"
            )

        self.store.save(plan)

        logger.info(
            f"Stage 2 Plan 完成 | "
            f"changes: {len(plan.change_list)} | "
            f"risks: {len(plan.risk_analysis)}"
        )

        return plan

    # ═══════════════════════════════════════════
    # Stage 3: Annotate — 批註循環
    # ═══════════════════════════════════════════

    def stage_3_annotate(
        self,
        plan: PlanDocument,
        user_annotations: str,
    ) -> PlanDocument:
        """Stage 3: 批註階段 — AI 寫 plan.md -> 人類批註 -> AI 更新.

        HG-PLAN-NO-SKIP-ANNOTATE: 不可跳過批註階段。
        最多 6 輪批註，超過建議拆分任務。
        plan.md 是此階段的唯一可變工件——絕不開始執行。

        Args:
            plan: 目前的計畫文件
            user_annotations: 使用者的批註內容

        Returns:
            更新後的 PlanDocument

        Raises:
            HardGateViolation: 超過批註輪次上限時的警告
        """
        # 檢查批註輪次
        if plan.annotation_round >= MAX_ANNOTATION_ROUNDS:
            logger.warning(
                f"已批註 {MAX_ANNOTATION_ROUNDS} 輪，"
                f"建議評估任務是否需要拆分成更小的範圍"
            )
            # 不強制中止，但記錄警告

        plan.annotation_round += 1
        plan.status = PlanStatus.ANNOTATING
        plan.current_stage = StageType.ANNOTATE

        # 記錄批註
        annotation = Annotation(
            round_number=plan.annotation_round,
            content=user_annotations,
        )
        plan.annotations.append(annotation)

        # 檢查批註是否推翻了研究事實
        if plan.research:
            self._process_annotation_corrections(plan, user_annotations)

        self.store.save(plan)

        logger.info(
            f"Stage 3 Annotate 完成 | "
            f"round: {plan.annotation_round}/{MAX_ANNOTATION_ROUNDS}"
        )

        return plan

    def _process_annotation_corrections(
        self,
        plan: PlanDocument,
        annotation_content: str,
    ) -> None:
        """處理批註中對研究事實的更正.

        人類批註優先，但標記矛盾。

        Args:
            plan: 計畫文件
            annotation_content: 批註內容
        """
        if not plan.research:
            return

        # 檢查是否有假設被批註確認或推翻
        for assumption in plan.research.assumptions:
            # 簡單啟發式：批註中提到假設內容時，標記為需要關注
            if assumption.content[:20] in annotation_content:
                logger.info(
                    f"批註可能涉及假設：{assumption.content[:50]}"
                )

    def approve_plan(self, plan: PlanDocument) -> PlanDocument:
        """核准計畫 — 從 Annotate 進入 Todo 階段.

        HG-PLAN-NO-SKIP-ANNOTATE: 必須至少經過一輪批註。
        HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: 必須明確核准。

        Args:
            plan: 計畫文件

        Returns:
            核准後的計畫文件

        Raises:
            AnnotationSkippedError: 未經過任何批註就嘗試核准
        """
        # 硬閘檢查：必須至少一輪批註
        if plan.annotation_round < 1:
            raise AnnotationSkippedError(
                "HG-PLAN-NO-SKIP-ANNOTATE: "
                "計畫必須至少經過一輪批註才能核准。"
                "即使使用者說「就這樣做」，也請先確認。"
            )

        plan.status = PlanStatus.APPROVED
        plan.current_stage = StageType.TODO

        self.store.save(plan)

        logger.info(
            f"計畫已核准 | title: {plan.title} | "
            f"annotation_rounds: {plan.annotation_round}"
        )

        return plan

    def annotation_round_exceeded(self, plan: PlanDocument) -> bool:
        """檢查批註輪次是否已超過上限.

        Args:
            plan: 計畫文件

        Returns:
            True 如果已超過 6 輪
        """
        return plan.annotation_round >= MAX_ANNOTATION_ROUNDS

    # ═══════════════════════════════════════════
    # Stage 4: Todo — 任務拆解
    # ═══════════════════════════════════════════

    def stage_4_todo(
        self,
        plan: PlanDocument,
        todos: Optional[List[TodoItem]] = None,
    ) -> List[TodoItem]:
        """Stage 4: 任務拆解 — 將核准的計畫轉為原子化任務.

        每個任務約 10 分鐘可完成，按階段分組，依賴關係明確。

        HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: 計畫必須先核准。

        Args:
            plan: 已核准的計畫文件
            todos: 任務清單（由呼叫者提供，通常是 Brain/LLM 拆解的結果）

        Returns:
            TodoItem 列表

        Raises:
            PlanNotApprovedError: 計畫未核准就嘗試建立 Todo
        """
        # 硬閘檢查：計畫必須已核准
        if plan.status not in (PlanStatus.APPROVED, PlanStatus.EXECUTING):
            raise PlanNotApprovedError(
                "HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: "
                f"計畫狀態為 {plan.status.value}，必須先核准才能建立 Todo。"
            )

        plan.todos = todos or []
        plan.current_stage = StageType.TODO

        # DNA-Inspired mRNA 剪接（Intron Splicing）：
        # 自動偵測並移除與計畫範圍無關的子任務，
        # 合併重複步驟，保留外顯子（真正需要執行的）。
        if plan.todos:
            original_count = len(plan.todos)
            plan.todos = self._splice_todos(plan)
            spliced = original_count - len(plan.todos)
            if spliced > 0:
                logger.info(
                    f"[PlanEngine] mRNA splicing: {spliced} intron tasks "
                    f"removed ({original_count} → {len(plan.todos)})"
                )

        self.store.save(plan)

        logger.info(
            f"Stage 4 Todo 完成 | tasks: {len(plan.todos)}"
        )

        return plan.todos

    def _splice_todos(self, plan: PlanDocument) -> List[TodoItem]:
        """mRNA 剪接：移除/合併與計畫目標不相關的子任務.

        DNA 類比：
        - 外顯子（Exon）= 與計畫 changes 直接相關的任務 → 保留
        - 內含子（Intron）= 與計畫範圍無交集的任務 → 標記移除
        - 剪接位點（Splice Site）= 重複/冗餘步驟 → 合併

        剪接規則（保守策略，寧多勿少）：
        1. 空白/佔位任務 → 移除
        2. 完全重複的任務描述 → 去重保留第一個
        3. 如果計畫有明確 changes 範圍，檢查任務是否落在範圍內
        """
        if not plan.todos:
            return []

        # Pass 1: 移除空白任務
        filtered = [t for t in plan.todos if t.content.strip()]

        # Pass 2: 去重（保守——只對完全相同的描述去重）
        seen_contents: set = set()
        deduped = []
        for t in filtered:
            normalized = t.content.strip().lower()
            if normalized not in seen_contents:
                seen_contents.add(normalized)
                deduped.append(t)
            else:
                logger.debug(f"[PlanEngine] Spliced duplicate intron: {t.content[:60]}")

        # Pass 3: 如果計畫有 changes 清單，標記超出範圍的任務
        # （保守策略：只 log 警告，不自動移除，避免誤判）
        if plan.change_list:
            change_keywords = set()
            for c in plan.change_list:
                # 從 change 描述中提取關鍵詞
                words = re.findall(r"[\w\u4e00-\u9fff]+", c.path or "")
                words += re.findall(r"[\w\u4e00-\u9fff]+", c.description or "")
                change_keywords.update(w.lower() for w in words if len(w) > 2)

            if change_keywords:
                for t in deduped:
                    task_words = set(
                        w.lower() for w in re.findall(r"[\w\u4e00-\u9fff]+", t.content)
                        if len(w) > 2
                    )
                    overlap = task_words & change_keywords
                    if not overlap:
                        logger.info(
                            f"[PlanEngine] Potential intron task (no overlap with "
                            f"changes): {t.content[:60]}"
                        )

        return deduped

    # ═══════════════════════════════════════════
    # Stage 5: Execute — 執行
    # ═══════════════════════════════════════════

    def stage_5_execute_item(
        self,
        plan: PlanDocument,
        task_index: int,
        success: bool = True,
        output: str = "",
        error: Optional[str] = None,
        out_of_plan: bool = False,
        out_of_plan_description: Optional[str] = None,
    ) -> ExecutionResult:
        """Stage 5: 執行單一任務項目.

        按 Todo 順序機械執行，每完成一項就在 plan.md 標記 [x]。

        硬閘規則：
        - HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: 計畫必須已核准
        - HG-PLAN-REVERT-OVER-PATCH: 遇到方向性錯誤時建議回退
        - 計畫外問題 -> 暫停等待人類決定

        Args:
            plan: 計畫文件
            task_index: 任務索引（0-based）
            success: 是否成功
            output: 執行輸出
            error: 錯誤訊息
            out_of_plan: 是否遇到計畫外問題
            out_of_plan_description: 計畫外問題描述

        Returns:
            ExecutionResult 執行結果

        Raises:
            PlanNotApprovedError: 計畫未核准
            OutOfPlanError: 遇到計畫外問題
        """
        # 硬閘檢查：計畫必須已核准
        if plan.status not in (PlanStatus.APPROVED, PlanStatus.EXECUTING):
            raise PlanNotApprovedError(
                "HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: "
                f"計畫狀態為 {plan.status.value}，無法執行。"
            )

        # 檢查任務索引
        if task_index < 0 or task_index >= len(plan.todos):
            return ExecutionResult(
                task_index=task_index,
                success=False,
                error=f"無效的任務索引：{task_index}",
            )

        # 檢查依賴是否都已完成
        todo = plan.todos[task_index]
        for dep_idx in todo.dependencies:
            if dep_idx < len(plan.todos) and not plan.todos[dep_idx].done:
                return ExecutionResult(
                    task_index=task_index,
                    success=False,
                    error=f"依賴任務 {dep_idx} 尚未完成",
                )

        # 更新計畫狀態
        plan.status = PlanStatus.EXECUTING
        plan.current_stage = StageType.EXECUTE

        # 計畫外問題 -> 暫停
        if out_of_plan:
            plan.status = PlanStatus.PAUSED
            result = ExecutionResult(
                task_index=task_index,
                success=False,
                out_of_plan=True,
                out_of_plan_description=out_of_plan_description,
            )

            self.store.save(plan)

            logger.warning(
                f"執行暫停 — 計畫外問題：{out_of_plan_description}"
            )

            raise OutOfPlanError(
                out_of_plan_description or "遇到計畫外問題"
            )

        # 標記任務開始時間
        now = datetime.now().isoformat()
        if not todo.started_at:
            todo.started_at = now

        # 執行結果
        if success:
            todo.done = True
            todo.completed_at = now
        else:
            logger.warning(
                f"任務 {task_index} 執行失敗: {error}"
            )

        result = ExecutionResult(
            task_index=task_index,
            success=success,
            output=output,
            error=error,
        )

        self.store.save(plan)

        logger.info(
            f"Stage 5 Execute | task {task_index} | "
            f"success: {success} | "
            f"done: {sum(1 for t in plan.todos if t.done)}/{len(plan.todos)}"
        )

        return result

    def revert_task(
        self,
        plan: PlanDocument,
        task_index: int,
        reason: str,
        affected_scope: str,
        lesson: str,
    ) -> RevertEntry:
        """HG-PLAN-REVERT-OVER-PATCH: 回退任務而非修補.

        方向性錯誤時，回退比修補更安全。
        回退紀錄寫入計畫和全域 revert_log。

        Args:
            plan: 計畫文件
            task_index: 要回退的任務索引
            reason: 回退原因
            affected_scope: 影響範圍
            lesson: 教訓

        Returns:
            RevertEntry 回退紀錄
        """
        entry = RevertEntry(
            timestamp=datetime.now().isoformat(),
            reason=reason,
            affected_scope=affected_scope,
            lesson=lesson,
            reverted_tasks=[task_index],
        )

        # 標記任務為未完成
        if 0 <= task_index < len(plan.todos):
            plan.todos[task_index].done = False
            plan.todos[task_index].completed_at = None

        # 新增到計畫的回退紀錄
        plan.revert_log.append(entry)

        # 暫停計畫
        plan.status = PlanStatus.PAUSED

        self.store.save(plan)

        # 同時寫入全域回退紀錄
        self.store.append_revert_entry(entry)

        logger.info(
            f"HG-PLAN-REVERT-OVER-PATCH | task {task_index} | "
            f"reason: {reason}"
        )

        return entry

    # ═══════════════════════════════════════════
    # Stage 6: Close — 收尾
    # ═══════════════════════════════════════════

    def stage_6_close(
        self,
        plan: PlanDocument,
        summary: str = "",
        problems_encountered: Optional[List[str]] = None,
        lessons_learned: Optional[List[str]] = None,
        knowledge_crystals: Optional[List[KnowledgeCrystal]] = None,
        archive: bool = True,
        delete_plan: bool = True,
    ) -> CloseReport:
        """Stage 6: 收尾 — 摘要、結晶、清理.

        生成執行摘要，提煉知識結晶（供 Knowledge-Lattice），
        處理回退紀錄，最後清理 plan.md。

        Args:
            plan: 計畫文件
            summary: 執行摘要
            problems_encountered: 遇到的問題
            lessons_learned: 學到的教訓
            knowledge_crystals: 建議結晶的知識
            archive: 是否存檔（預設 True）
            delete_plan: 是否刪除 plan.md（預設 True）

        Returns:
            CloseReport 收尾報告
        """
        completed = sum(1 for t in plan.todos if t.done)
        total = len(plan.todos)

        # 自動從回退紀錄提取教訓
        revert_lessons = [
            entry.lesson for entry in plan.revert_log
            if entry.lesson
        ]

        all_lessons = (lessons_learned or []) + revert_lessons

        # 建立收尾報告
        close_report = CloseReport(
            summary=summary or f"計畫「{plan.title}」執行完成",
            completed_tasks=completed,
            total_tasks=total,
            problems_encountered=problems_encountered or [],
            lessons_learned=all_lessons,
            knowledge_crystals=knowledge_crystals or [],
            revert_entries=plan.revert_log,
        )

        # 更新計畫
        plan.close_report = close_report
        plan.status = PlanStatus.CLOSED
        plan.current_stage = StageType.CLOSE

        # 先儲存完整計畫（含收尾報告）
        self.store.save(plan)

        # 存檔
        if archive:
            try:
                archive_path = self.store.archive(plan)
                logger.info(f"計畫已存檔至: {archive_path}")
            except Exception as e:
                logger.error(f"存檔失敗: {e}")

        # 刪除活動計畫
        if delete_plan:
            self.store.delete()
            logger.info("活動計畫已刪除")

        logger.info(
            f"Stage 6 Close 完成 | "
            f"completed: {completed}/{total} | "
            f"lessons: {len(all_lessons)}"
        )

        return close_report

    # ═══════════════════════════════════════════
    # 計畫管理
    # ═══════════════════════════════════════════

    def get_current_plan(self) -> Optional[PlanDocument]:
        """取得當前活動計畫.

        跨對話持久化：如果上一次對話留下了未完成的計畫，
        新對話可以從中斷處繼續。

        Returns:
            PlanDocument 或 None
        """
        return self.store.load()

    def get_current_stage(self) -> Optional[str]:
        """取得當前計畫所在階段.

        Returns:
            階段名稱字串，或 None（無活動計畫）
        """
        plan = self.store.load()
        if plan is None:
            return None
        return plan.current_stage.value

    def save_plan(self, plan: PlanDocument) -> None:
        """儲存計畫到持久化層.

        Args:
            plan: 計畫文件
        """
        self.store.save(plan)

    def load_plan(self) -> Optional[PlanDocument]:
        """從持久化層載入計畫.

        Returns:
            PlanDocument 或 None
        """
        return self.store.load()

    def delete_plan(self) -> None:
        """刪除活動計畫 — 用於 Close 階段完成後."""
        self.store.delete()

    # ═══════════════════════════════════════════
    # DNA27 三迴圈適配
    # ═══════════════════════════════════════════

    def execute_with_loop(
        self,
        loop_type: LoopType,
        task_description: str,
        facts: Optional[List[ResearchFact]] = None,
        assumptions: Optional[List[Assumption]] = None,
        questions: Optional[List[str]] = None,
        method_explanation: str = "",
        change_list: Optional[List[ChangeItem]] = None,
        risk_analysis: Optional[List[RiskItem]] = None,
        skill_suggestions: Optional[List[str]] = None,
    ) -> Tuple[PlanDocument, str]:
        """依據 DNA27 迴圈類型執行對應的計畫流程.

        - fast_loop: 跳過計畫引擎，回傳空計畫（由 Brain 直接執行）
        - exploration_loop: 精簡版 — 只做 Research + Plan（跳過批註循環）
        - slow_loop: 完整六階段流程

        Args:
            loop_type: 迴圈類型
            task_description: 任務描述
            facts: 研究事實
            assumptions: 假設
            questions: 問題
            method_explanation: 方法說明
            change_list: 變更清單
            risk_analysis: 風險分析
            skill_suggestions: 技能建議

        Returns:
            (PlanDocument, 階段指引訊息) 元組
        """
        if loop_type == LoopType.FAST:
            # fast_loop: 不啟動計畫引擎
            logger.info("DNA27 fast_loop — 跳過計畫引擎")
            plan = PlanDocument(
                title=task_description[:80],
                status=PlanStatus.APPROVED,
                current_stage=StageType.EXECUTE,
                loop_type=LoopType.FAST,
            )
            return plan, "fast_loop：直接執行，不需要計畫"

        elif loop_type == LoopType.EXPLORATION:
            # exploration_loop: 只做 Research + Plan
            logger.info("DNA27 exploration_loop — 精簡版計畫")
            research = self.stage_1_research(
                task_description=task_description,
                facts=facts,
                assumptions=assumptions,
                questions=questions,
            )
            plan = self.stage_2_plan(
                research=research,
                task_description=task_description,
                method_explanation=method_explanation,
                change_list=change_list,
                risk_analysis=risk_analysis,
                skill_suggestions=skill_suggestions,
            )
            plan.loop_type = LoopType.EXPLORATION
            self.store.save(plan)
            return plan, (
                "exploration_loop：已完成 Research + Plan。"
                "使用者口頭確認即可進入執行。"
            )

        else:
            # slow_loop: 完整六階段
            logger.info("DNA27 slow_loop — 完整六階段流程")
            research = self.stage_1_research(
                task_description=task_description,
                facts=facts,
                assumptions=assumptions,
                questions=questions,
            )
            plan = self.stage_2_plan(
                research=research,
                task_description=task_description,
                method_explanation=method_explanation,
                change_list=change_list,
                risk_analysis=risk_analysis,
                skill_suggestions=skill_suggestions,
            )
            plan.loop_type = LoopType.SLOW
            self.store.save(plan)
            return plan, (
                "slow_loop：已完成 Research + Plan。"
                "請檢閱 plan.md 並進行批註（Annotate 階段）。"
            )

    # ═══════════════════════════════════════════
    # 跨對話恢復
    # ═══════════════════════════════════════════

    def resume_from_previous(self) -> Tuple[Optional[PlanDocument], str]:
        """從上次中斷的計畫恢復.

        跨對話持久化：讀取 plan.md 和 state.json，
        從上次中斷的階段繼續。

        Returns:
            (PlanDocument 或 None, 恢復指引訊息) 元組
        """
        plan = self.store.load()

        if plan is None:
            return None, "沒有發現進行中的計畫"

        stage = plan.current_stage
        status = plan.status

        # 根據狀態提供恢復指引
        if status == PlanStatus.CLOSED:
            return plan, (
                f"計畫「{plan.title}」已完成收尾。"
                f"如果需要，可以在 archive 中查看歷史。"
            )

        if status == PlanStatus.PAUSED:
            return plan, (
                f"計畫「{plan.title}」已暫停。"
                f"上次暫停原因：需要你的決定才能繼續。"
                f"目前在 {stage.value} 階段。"
            )

        stage_guidance = {
            StageType.RESEARCH: (
                f"計畫「{plan.title}」正在研究階段。"
                f"已收集 {len(plan.research.facts) if plan.research else 0} 項事實。"
            ),
            StageType.PLAN: (
                f"計畫「{plan.title}」正在計畫階段。"
                f"已規劃 {len(plan.change_list)} 項變更。"
            ),
            StageType.ANNOTATE: (
                f"計畫「{plan.title}」正在批註階段。"
                f"目前第 {plan.annotation_round}/{MAX_ANNOTATION_ROUNDS} 輪。"
                f"請繼續在 plan.md 中加入批註。"
            ),
            StageType.TODO: (
                f"計畫「{plan.title}」已拆解為 {len(plan.todos)} 項任務。"
                f"等待確認後開始執行。"
            ),
            StageType.EXECUTE: (
                f"計畫「{plan.title}」正在執行。"
                f"已完成 {sum(1 for t in plan.todos if t.done)}/{len(plan.todos)} 項。"
            ),
            StageType.CLOSE: (
                f"計畫「{plan.title}」準備收尾。"
            ),
        }

        guidance = stage_guidance.get(
            stage,
            f"計畫「{plan.title}」狀態：{status.value}，階段：{stage.value}"
        )

        logger.info(f"從上次中斷恢復 | {plan.title} | {stage.value}")

        return plan, guidance

    # ═══════════════════════════════════════════
    # 硬閘檢查
    # ═══════════════════════════════════════════

    def check_hard_gate_no_guess(self, fact: ResearchFact) -> bool:
        """HG-PLAN-NO-GUESS: 檢查事實是否有來源標註.

        Args:
            fact: 研究事實

        Returns:
            True 如果通過（有來源標註）
        """
        if not fact.source or fact.source.strip() == "":
            logger.warning(
                f"HG-PLAN-NO-GUESS 違規：缺少來源 — {fact.content[:50]}"
            )
            return False
        return True

    def check_hard_gate_no_skip_annotate(
        self, plan: PlanDocument
    ) -> bool:
        """HG-PLAN-NO-SKIP-ANNOTATE: 檢查是否已通過批註.

        Args:
            plan: 計畫文件

        Returns:
            True 如果通過（已有至少一輪批註）
        """
        if plan.annotation_round < 1:
            logger.warning(
                "HG-PLAN-NO-SKIP-ANNOTATE 違規：尚未進行任何批註"
            )
            return False
        return True

    def check_hard_gate_no_execute_without_approval(
        self, plan: PlanDocument
    ) -> bool:
        """HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL: 檢查計畫是否已核准.

        Args:
            plan: 計畫文件

        Returns:
            True 如果通過（計畫已核准）
        """
        if plan.status not in (PlanStatus.APPROVED, PlanStatus.EXECUTING):
            logger.warning(
                f"HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL 違規："
                f"計畫狀態為 {plan.status.value}"
            )
            return False
        return True

    def check_all_hard_gates(self, plan: PlanDocument) -> List[str]:
        """檢查所有硬閘，回傳違規列表.

        Args:
            plan: 計畫文件

        Returns:
            違規描述列表（空列表表示全部通過）
        """
        violations: List[str] = []

        # HG-PLAN-NO-GUESS: 檢查所有事實
        if plan.research:
            for fact in plan.research.facts:
                if not self.check_hard_gate_no_guess(fact):
                    violations.append(
                        f"HG-PLAN-NO-GUESS: 事實缺少來源「{fact.content[:30]}...」"
                    )

        # HG-PLAN-NO-SKIP-ANNOTATE: 若計畫已核准但未批註
        if plan.status in (PlanStatus.APPROVED, PlanStatus.EXECUTING):
            if not self.check_hard_gate_no_skip_annotate(plan):
                violations.append(
                    "HG-PLAN-NO-SKIP-ANNOTATE: 計畫未經批註就被核准"
                )

        return violations

    # ═══════════════════════════════════════════
    # 多專案管理
    # ═══════════════════════════════════════════

    def switch_project(self, project_name: str) -> Tuple[Optional[PlanDocument], str]:
        """切換到指定專案的計畫.

        多個計畫以專案名稱區分：plan-{project}.md
        此方法會儲存當前計畫，載入目標專案計畫。

        Args:
            project_name: 專案名稱

        Returns:
            (PlanDocument 或 None, 切換結果訊息) 元組
        """
        # 儲存當前計畫（如有）
        current = self.store.load()
        if current and current.project_name:
            self.store.save(current)
            logger.info(f"已儲存當前專案計畫：{current.project_name}")

        # 嘗試載入目標專案
        # 在 active 目錄下尋找對應的 state-{project}.json
        project_state = self.store.active_dir / f"state-{project_name}.json"

        if project_state.exists():
            try:
                data = json.loads(
                    project_state.read_text(encoding="utf-8")
                )
                plan = PlanDocument.from_dict(data)
                plan.project_name = project_name

                # 設為活動計畫
                self.store.save(plan)

                return plan, f"已切換到專案「{project_name}」"
            except Exception as e:
                logger.error(f"載入專案計畫失敗: {e}")
                return None, f"載入專案「{project_name}」失敗：{e}"
        else:
            # 建立新專案計畫
            plan = PlanDocument(
                project_name=project_name,
                title=f"專案：{project_name}",
            )
            self.store.save(plan)
            return plan, f"已建立新專案「{project_name}」"
