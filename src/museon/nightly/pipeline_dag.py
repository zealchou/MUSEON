"""PipelineDAG -- 有向無環圖管線排程器.

取代線性步驟清單，以 DAG 拓撲排序決定執行順序。
節點間的邊代表資料相依性：B 依賴 A → A 必須先於 B 完成。

設計原則：
  - 純 CPU，零 Token
  - 依賴失敗時，下游步驟自動跳過（非靜默失敗）
  - 拓撲排序保證正確執行順序
  - 完整執行報告（DAGExecutionReport）
  - ASCII 視覺化 DAG 結構供日誌使用
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════


@dataclass
class DAGStep:
    """DAG 中的單一步驟節點.

    Attributes:
        id: 步驟識別碼，如 "5.8"
        name: 步驟名稱，如 "step_05_8_morphenix_proposals"
        func: 實際執行的可呼叫物件
        depends_on: 此步驟所依賴的步驟 ID 清單
        group: 邏輯分組（供未來平行執行參考）
    """
    id: str
    name: str
    func: Callable
    depends_on: List[str] = field(default_factory=list)
    group: str = ""


@dataclass
class StepResult:
    """單一步驟的執行結果."""
    step_id: str
    name: str
    status: str  # "ok", "error", "skipped", "skipped_dependency_failed"
    elapsed_seconds: float = 0.0
    result: str = ""
    error: str = ""
    skipped_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "step_id": self.step_id,
            "name": self.name,
            "status": self.status,
            "elapsed_seconds": self.elapsed_seconds,
        }
        if self.result:
            d["result"] = self.result
        if self.error:
            d["error"] = self.error
        if self.skipped_reason:
            d["skipped_reason"] = self.skipped_reason
        return d


@dataclass
class DAGExecutionReport:
    """完整的 DAG 管線執行報告."""
    started_at: str = ""
    completed_at: str = ""
    elapsed_seconds: float = 0.0
    steps: Dict[str, StepResult] = field(default_factory=dict)
    skipped_due_to_dependency: List[str] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for s in self.steps.values() if s.status == "ok")

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.steps.values() if s.status == "error")

    @property
    def skipped_count(self) -> int:
        return sum(
            1 for s in self.steps.values()
            if s.status in ("skipped", "skipped_dependency_failed")
        )

    @property
    def total(self) -> int:
        return len(self.steps)

    def summary(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "ok": self.ok_count,
            "error": self.error_count,
            "skipped": self.skipped_count,
            "elapsed_seconds": self.elapsed_seconds,
            "skipped_due_to_dependency": self.skipped_due_to_dependency,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "steps": {
                sid: sr.to_dict() for sid, sr in self.steps.items()
            },
            "skipped_due_to_dependency": self.skipped_due_to_dependency,
            "execution_order": self.execution_order,
            "summary": self.summary(),
        }


# ═══════════════════════════════════════════
# DAG Validation Errors
# ═══════════════════════════════════════════


class DAGValidationError(Exception):
    """DAG 結構驗證失敗."""


# ═══════════════════════════════════════════
# MUSEON 預設依賴圖
# ═══════════════════════════════════════════

MUSEON_DEPENDENCIES: Dict[str, List[str]] = {
    # Phase 0: Budget & Cleanup（無依賴）
    "0": [],
    "0.1": [],

    # Phase 1: Asset maintenance（無依賴）
    "1": [],
    "2": ["1"],               # archive 依賴 decay
    "3": [],

    # Phase 2: WEE & Knowledge
    "4": [],                  # WEE compress
    "5": ["4"],               # WEE fuse 依賴 compress
    "5.5": ["5"],             # cross-crystallize 依賴 fuse
    "5.6": ["5.5"],           # knowledge lattice 依賴 cross-crystallize
    "5.7": ["5.6"],           # crystal actuator 依賴 knowledge lattice

    # Phase 3: Morphenix（依賴 knowledge）
    "5.8": ["5.7"],           # proposals 依賴 crystal actuator
    "5.9": ["5.8"],           # gate 依賴 proposals
    "5.9.5": ["5.9"],         # Docker validate 依賴 gate
    "5.10": ["5.9.5"],        # execute 依賴 Docker validate

    # Phase 4: Skill & Learning（依賴 morphenix）
    "6": ["5.10"],            # skill forge 依賴 morphenix
    "6.5": ["6"],             # skill scout 依賴 skill forge
    "7": ["6"],               # curriculum 依賴 skill forge
    "7.5": ["7"],             # auto course 依賴 curriculum
    "8": [],                  # workflow mutation（獨立）
    "8.5": [],                # DNA27 reindex（獨立）

    # Phase 5: Integration（依賴 knowledge）
    "9": ["5.6"],             # graph consolidation 依賴 knowledge lattice
    "10": [],                 # soul nightly（獨立）
    "10.5": ["10"],           # ring review 依賴 soul nightly
    "11": ["10"],             # dream engine 依賴 soul nightly
    "12": [],                 # heartbeat focus（獨立）
    "13": [],                 # curiosity scan（獨立）
    "13.5": ["13"],           # curiosity research 依賴 scan
    "13.6": [],               # outward trigger scan（獨立）
    "13.7": ["13.6"],         # outward research 依賴 trigger scan
    "13.8": ["13.7"],         # digest lifecycle 依賴 outward research

    # Phase 6: Lifecycle & Health
    "14": ["6"],              # skill lifecycle 依賴 skill forge
    "15": [],                 # dept health（獨立）
    "16": ["5.10", "6"],      # claude skill forge 依賴 morphenix + skill forge
    "17": [],                 # tool discovery（獨立）
    "18": [],                 # daily summary（獨立，通常最後執行）

    # Phase 7: Autonomy
    "20": [],                 # synapse decay（獨立）
    "21": [],                 # muscle atrophy（獨立）
    "22": [],                 # immune prune（獨立）
    "23": [],                 # trigger evaluation（獨立）

    # Phase 8: Evolution
    "24": [],                 # evolution velocity（獨立，讀取既有資料計算）
    "25": ["18"],             # periodic cycle check（依賴 daily summary 完成後再觸發）

    # Phase 5+8: Persona Evolution
    "34": ["10", "33"],       # persona_reflection 依賴 diary(10) + crystal_promotion(33)
    "34.5": ["34"],           # trait_metabolize 依賴 persona_reflection
    "34.7": ["34.5"],         # drift_direction_check 依賴 trait_metabolize
}


# ═══════════════════════════════════════════
# PipelineDAG
# ═══════════════════════════════════════════

# 截斷結果字串的最大長度
_REPORT_TRUNCATE_CHARS = 200


class PipelineDAG:
    """有向無環圖管線排程器.

    以 DAG 拓撲排序決定執行順序，自動處理依賴失敗的跳過邏輯。

    用法::

        dag = PipelineDAG()
        dag.add_step(DAGStep(id="4", name="wee_compress", func=compress_fn))
        dag.add_step(DAGStep(id="5", name="wee_fuse", func=fuse_fn, depends_on=["4"]))

        errors = dag.validate()
        if errors:
            raise DAGValidationError(errors)

        report = dag.execute()
    """

    def __init__(self) -> None:
        self._steps: Dict[str, DAGStep] = {}
        # adjacency list: parent → set of children
        self._children: Dict[str, Set[str]] = defaultdict(set)
        # reverse adjacency: child → set of parents
        self._parents: Dict[str, Set[str]] = defaultdict(set)

    # ───────────────────────────────────────
    # Step Management
    # ───────────────────────────────────────

    def add_step(self, step: DAGStep) -> None:
        """新增步驟到 DAG.

        Args:
            step: DAGStep 實例

        Raises:
            ValueError: 步驟 ID 重複
        """
        if step.id in self._steps:
            raise ValueError(f"步驟 ID 重複: {step.id!r}")
        self._steps[step.id] = step
        for dep_id in step.depends_on:
            self._children[dep_id].add(step.id)
            self._parents[step.id].add(dep_id)

    def remove_step(self, step_id: str) -> None:
        """移除步驟及其所有邊.

        Args:
            step_id: 要移除的步驟 ID

        Raises:
            KeyError: 步驟不存在
        """
        if step_id not in self._steps:
            raise KeyError(f"步驟不存在: {step_id!r}")
        # 移除正向邊
        for child_id in list(self._children.get(step_id, set())):
            self._parents[child_id].discard(step_id)
        self._children.pop(step_id, None)
        # 移除反向邊
        for parent_id in list(self._parents.get(step_id, set())):
            self._children[parent_id].discard(step_id)
        self._parents.pop(step_id, None)
        del self._steps[step_id]

    @property
    def step_ids(self) -> List[str]:
        """回傳所有已註冊的步驟 ID."""
        return list(self._steps.keys())

    def __len__(self) -> int:
        return len(self._steps)

    # ───────────────────────────────────────
    # Validation
    # ───────────────────────────────────────

    def validate(self) -> List[str]:
        """驗證 DAG 結構完整性.

        檢查項目：
          1. 所有依賴的步驟都已註冊
          2. 無環（cycle detection）

        Returns:
            錯誤訊息清單，空清單代表通過驗證
        """
        errors: List[str] = []

        # 1. 檢查缺失的依賴
        for step_id, step in self._steps.items():
            for dep_id in step.depends_on:
                if dep_id not in self._steps:
                    errors.append(
                        f"步驟 {step_id!r} 依賴 {dep_id!r}，但 {dep_id!r} 未註冊"
                    )

        # 2. 檢查環（Kahn's algorithm attempt）
        cycle_errors = self._detect_cycles()
        errors.extend(cycle_errors)

        return errors

    def _detect_cycles(self) -> List[str]:
        """使用 Kahn's algorithm 偵測環."""
        in_degree: Dict[str, int] = {sid: 0 for sid in self._steps}
        for step_id, step in self._steps.items():
            for dep_id in step.depends_on:
                if dep_id in self._steps:
                    in_degree[step_id] += 1

        queue = deque(sid for sid, deg in in_degree.items() if deg == 0)
        visited_count = 0

        while queue:
            node = queue.popleft()
            visited_count += 1
            for child in self._children.get(node, set()):
                if child in in_degree:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        queue.append(child)

        if visited_count < len(self._steps):
            # 找出環中的節點
            cycle_nodes = [
                sid for sid, deg in in_degree.items() if deg > 0
            ]
            return [
                f"偵測到環（cycle），涉及步驟: {cycle_nodes}"
            ]
        return []

    # ───────────────────────────────────────
    # Topological Sort
    # ───────────────────────────────────────

    def get_execution_order(self) -> List[str]:
        """取得拓撲排序後的執行順序.

        使用 Kahn's algorithm。同層級的節點以步驟 ID 的數值順序排列，
        確保相同依賴圖在不同執行間產生一致的順序。

        Returns:
            步驟 ID 清單（拓撲排序）

        Raises:
            DAGValidationError: DAG 含環或有缺失依賴
        """
        errors = self.validate()
        if errors:
            raise DAGValidationError(
                "DAG 驗證失敗:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        in_degree: Dict[str, int] = {sid: 0 for sid in self._steps}
        for step_id, step in self._steps.items():
            for dep_id in step.depends_on:
                if dep_id in self._steps:
                    in_degree[step_id] += 1

        # 使用 _sort_key 保證穩定排序
        queue: List[str] = sorted(
            (sid for sid, deg in in_degree.items() if deg == 0),
            key=self._sort_key,
        )
        order: List[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            # 收集可解鎖的子節點，排序後加入
            unlocked: List[str] = []
            for child in self._children.get(node, set()):
                if child in in_degree:
                    in_degree[child] -= 1
                    if in_degree[child] == 0:
                        unlocked.append(child)
            unlocked.sort(key=self._sort_key)
            queue.extend(unlocked)
            queue.sort(key=self._sort_key)

        return order

    @staticmethod
    def _sort_key(step_id: str) -> float:
        """將步驟 ID 轉為浮點數以進行數值排序.

        Examples:
            "0" → 0.0, "5.8" → 5.8, "13.5" → 13.5
        """
        try:
            return float(step_id)
        except ValueError:
            return float("inf")

    # ───────────────────────────────────────
    # Execution
    # ───────────────────────────────────────

    def execute(
        self,
        skip_on_dependency_failure: bool = True,
    ) -> DAGExecutionReport:
        """執行 DAG 中所有步驟.

        依拓撲排序順序逐步執行。若某步驟失敗且
        skip_on_dependency_failure=True，則所有下游步驟自動標記為
        "skipped_dependency_failed"。

        Args:
            skip_on_dependency_failure: 依賴失敗時是否跳過下游步驟

        Returns:
            DAGExecutionReport 完整報告
        """
        started_at = datetime.now(TZ_TAIPEI)
        wall_start = time.monotonic()

        report = DAGExecutionReport(
            started_at=started_at.isoformat(),
        )

        execution_order = self.get_execution_order()
        report.execution_order = list(execution_order)

        # 追蹤失敗的步驟 ID
        failed_ids: Set[str] = set()

        for step_id in execution_order:
            step = self._steps[step_id]

            # 檢查依賴是否有任何失敗
            if skip_on_dependency_failure:
                failed_deps = [
                    dep_id for dep_id in step.depends_on
                    if dep_id in failed_ids
                ]
                if failed_deps:
                    reason = (
                        f"dependency {', '.join(sorted(failed_deps, key=self._sort_key))} failed"
                    )
                    logger.warning(
                        f"[DAG] Step {step_id} ({step.name}) SKIPPED: {reason}"
                    )
                    report.steps[step_id] = StepResult(
                        step_id=step_id,
                        name=step.name,
                        status="skipped_dependency_failed",
                        skipped_reason=reason,
                    )
                    report.skipped_due_to_dependency.append(step_id)
                    # 傳遞失敗：此步驟也視為失敗，影響下游
                    failed_ids.add(step_id)
                    continue

            # 執行步驟
            result = self._execute_step(step)
            report.steps[step_id] = result

            if result.status == "error":
                failed_ids.add(step_id)

        # 填寫報告收尾欄位
        completed_at = datetime.now(TZ_TAIPEI)
        report.completed_at = completed_at.isoformat()
        report.elapsed_seconds = round(time.monotonic() - wall_start, 2)

        # 日誌摘要
        logger.info(
            f"[DAG] Pipeline completed: "
            f"{report.ok_count} ok, {report.error_count} error, "
            f"{report.skipped_count} skipped "
            f"({report.elapsed_seconds}s)"
        )

        return report

    def _execute_step(self, step: DAGStep) -> StepResult:
        """單步執行 + 錯誤隔離.

        Args:
            step: 要執行的 DAGStep

        Returns:
            StepResult 包含狀態與結果
        """
        logger.info(f"[DAG] Step {step.id} ({step.name}) START")
        t0 = time.monotonic()

        try:
            raw_result = step.func()
            elapsed = round(time.monotonic() - t0, 3)

            # 截斷結果字串
            result_str = str(raw_result)
            if len(result_str) > _REPORT_TRUNCATE_CHARS:
                result_str = result_str[:_REPORT_TRUNCATE_CHARS] + "..."

            logger.info(
                f"[DAG] Step {step.id} ({step.name}) OK ({elapsed}s)"
            )
            return StepResult(
                step_id=step.id,
                name=step.name,
                status="ok",
                elapsed_seconds=elapsed,
                result=result_str,
            )

        except NotImplementedError:
            elapsed = round(time.monotonic() - t0, 3)
            logger.info(
                f"[DAG] Step {step.id} ({step.name}) SKIPPED: "
                f"subsystem not available"
            )
            return StepResult(
                step_id=step.id,
                name=step.name,
                status="skipped",
                elapsed_seconds=elapsed,
                skipped_reason="subsystem not available",
            )

        except Exception as e:
            elapsed = round(time.monotonic() - t0, 3)
            logger.error(
                f"[DAG] Step {step.id} ({step.name}) FAILED: {e}"
            )
            return StepResult(
                step_id=step.id,
                name=step.name,
                status="error",
                elapsed_seconds=elapsed,
                error=str(e),
            )

    # ───────────────────────────────────────
    # Downstream Query
    # ───────────────────────────────────────

    def get_all_downstream(self, step_id: str) -> Set[str]:
        """取得某步驟的所有（遞迴）下游步驟.

        Args:
            step_id: 起始步驟 ID

        Returns:
            下游步驟 ID 集合（不含自身）
        """
        downstream: Set[str] = set()
        queue = deque(self._children.get(step_id, set()))
        while queue:
            child = queue.popleft()
            if child not in downstream:
                downstream.add(child)
                queue.extend(self._children.get(child, set()))
        return downstream

    def get_all_upstream(self, step_id: str) -> Set[str]:
        """取得某步驟的所有（遞迴）上游步驟.

        Args:
            step_id: 起始步驟 ID

        Returns:
            上游步驟 ID 集合（不含自身）
        """
        upstream: Set[str] = set()
        queue = deque(self._parents.get(step_id, set()))
        while queue:
            parent = queue.popleft()
            if parent not in upstream:
                upstream.add(parent)
                queue.extend(self._parents.get(parent, set()))
        return upstream

    # ───────────────────────────────────────
    # Visualization
    # ───────────────────────────────────────

    def visualize(self) -> str:
        """產生 DAG 的 ASCII 視覺化字串.

        將步驟依拓撲層級排列，顯示依賴關係。
        獨立步驟（無依賴也無下游）顯示在最上層。

        Returns:
            多行 ASCII 字串
        """
        if not self._steps:
            return "(empty DAG)"

        errors = self.validate()
        if errors:
            return "(invalid DAG: " + "; ".join(errors) + ")"

        # 計算每個節點的拓撲深度（最長路徑長度）
        depth: Dict[str, int] = {}
        order = self.get_execution_order()
        for sid in order:
            step = self._steps[sid]
            if not step.depends_on:
                depth[sid] = 0
            else:
                depth[sid] = max(
                    depth.get(dep, 0) for dep in step.depends_on
                    if dep in self._steps
                ) + 1

        # 按深度分層
        max_depth = max(depth.values()) if depth else 0
        layers: Dict[int, List[str]] = defaultdict(list)
        for sid, d in depth.items():
            layers[d].append(sid)

        # 每層排序
        for d in layers:
            layers[d].sort(key=self._sort_key)

        # 建構輸出
        lines: List[str] = []
        lines.append("=== Pipeline DAG ===")
        lines.append("")

        for d in range(max_depth + 1):
            layer_ids = layers.get(d, [])
            if not layer_ids:
                continue

            # 節點行
            node_labels = [f"[{sid}]" for sid in layer_ids]
            node_line = "  " * d + "  ".join(node_labels)
            lines.append(f"Layer {d}: {node_line}")

            # 依賴標註行
            dep_notes: List[str] = []
            for sid in layer_ids:
                step = self._steps[sid]
                if step.depends_on:
                    dep_str = ", ".join(
                        sorted(step.depends_on, key=self._sort_key)
                    )
                    dep_notes.append(f"  {sid} <- {dep_str}")
            if dep_notes:
                for note in dep_notes:
                    lines.append("  " * d + note)

            lines.append("")

        # 附加依賴鏈摘要
        lines.append("--- Dependency Chains ---")
        chains = self._find_chains()
        for chain in chains:
            lines.append("  " + " -> ".join(chain))

        return "\n".join(lines)

    def _find_chains(self) -> List[List[str]]:
        """找出所有從根到葉的最長依賴鏈.

        Returns:
            每條鏈是步驟 ID 清單
        """
        # 找根節點（無依賴）
        roots = [
            sid for sid, step in self._steps.items()
            if not step.depends_on or all(
                d not in self._steps for d in step.depends_on
            )
        ]
        roots.sort(key=self._sort_key)

        # 找葉節點（無下游）
        leaves = set()
        for sid in self._steps:
            children_in_dag = self._children.get(sid, set()) & set(self._steps)
            if not children_in_dag:
                leaves.add(sid)

        # DFS 找所有根→葉路徑
        chains: List[List[str]] = []

        def _dfs(node: str, path: List[str]) -> None:
            if node in leaves:
                chains.append(list(path))
                return
            children = sorted(
                self._children.get(node, set()) & set(self._steps),
                key=self._sort_key,
            )
            if not children:
                chains.append(list(path))
                return
            for child in children:
                path.append(child)
                _dfs(child, path)
                path.pop()

        for root in roots:
            _dfs(root, [root])

        # 去重（保留最長鏈，移除子集）
        unique: List[List[str]] = []
        chain_sets = [set(c) for c in chains]
        for i, chain in enumerate(chains):
            cs = chain_sets[i]
            is_subset = any(
                cs < chain_sets[j]
                for j in range(len(chains))
                if i != j
            )
            if not is_subset:
                unique.append(chain)

        return unique


# ═══════════════════════════════════════════
# Factory Helper
# ═══════════════════════════════════════════


def build_museon_dag(
    step_map: Dict[str, tuple],
    step_ids: Optional[List[str]] = None,
    dependencies: Optional[Dict[str, List[str]]] = None,
) -> PipelineDAG:
    """根據 NightlyPipeline 的 step_map 建構 PipelineDAG.

    這是從線性管線遷移到 DAG 的銜接函式。
    接受 NightlyPipeline._step_map 格式的字典，
    自動套用 MUSEON_DEPENDENCIES 中的依賴關係。

    Args:
        step_map: {step_id: (step_name, callable)} 格式的步驟對應表
        step_ids: 要納入的步驟 ID 清單（None 表示全部）
        dependencies: 自訂依賴圖（None 使用 MUSEON_DEPENDENCIES）

    Returns:
        已建構完成的 PipelineDAG

    Raises:
        DAGValidationError: 依賴圖有環或缺失依賴

    Example::

        from museon.nightly.pipeline_dag import build_museon_dag

        dag = build_museon_dag(pipeline._step_map, step_ids=_FULL_STEPS)
        report = dag.execute()
    """
    deps = dependencies or MUSEON_DEPENDENCIES
    ids_to_include = set(step_ids) if step_ids else set(step_map.keys())

    dag = PipelineDAG()

    for step_id in ids_to_include:
        if step_id not in step_map:
            logger.warning(f"[DAG] step_id {step_id!r} 不在 step_map 中，跳過")
            continue

        name, func = step_map[step_id]

        # 只保留在本次執行範圍內的依賴
        raw_deps = deps.get(step_id, [])
        filtered_deps = [d for d in raw_deps if d in ids_to_include]

        # 推斷分組
        group = _infer_group(step_id)

        dag.add_step(DAGStep(
            id=step_id,
            name=name,
            func=func,
            depends_on=filtered_deps,
            group=group,
        ))

    # 驗證
    errors = dag.validate()
    if errors:
        raise DAGValidationError(
            "DAG 建構後驗證失敗:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return dag


def _infer_group(step_id: str) -> str:
    """根據步驟 ID 推斷邏輯分組.

    Args:
        step_id: 步驟 ID

    Returns:
        分組名稱
    """
    try:
        num = float(step_id)
    except ValueError:
        return "unknown"

    if num < 1:
        return "budget_cleanup"
    elif num < 4:
        return "asset_maintenance"
    elif num < 5.7:
        return "wee_knowledge"
    elif num < 6:
        return "morphenix"
    elif num < 9:
        return "skill_learning"
    elif num < 14:
        return "integration"
    elif num < 19:
        return "lifecycle_health"
    elif num < 24:
        return "autonomy"
    elif num < 26:
        return "evolution"
    else:
        return "unknown"
