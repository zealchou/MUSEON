"""WorkflowEngine — 工作流生命週期引擎.

管理工作流 6 階段生命週期（birth → growth → maturity → plateau → evolution → archived），
搭配 SQLite 持久化、加權滾動平均、自動遷轉與高原偵測。

零 LLM 依賴。所有評分和偵測為純 Python 啟發式。
"""

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    BIRTH_TO_GROWTH_SUCCESS,
    GROWTH_TO_MATURITY_AVG,
    GROWTH_TO_MATURITY_SUCCESS,
    LIFECYCLE_STAGES,
    PLATEAU_MAX_AVG,
    PLATEAU_MAX_VARIANCE,
    PLATEAU_MIN_RUNS,
    ROLLING_WINDOW,
    ExecutionRecord,
    FourDScore,
    WorkflowRecord,
)

logger = logging.getLogger(__name__)

TZ_TAIPEI = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# SQL Schema
# ═══════════════════════════════════════════

_CREATE_WORKFLOWS_TABLE = """
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id   TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    name          TEXT NOT NULL,
    lifecycle     TEXT NOT NULL DEFAULT 'birth',
    success_count INTEGER DEFAULT 0,
    total_runs    INTEGER DEFAULT 0,
    avg_composite REAL DEFAULT 0.0,
    variance      REAL DEFAULT 0.0,
    baseline_composite REAL,
    tags_json     TEXT DEFAULT '[]',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""

_CREATE_WORKFLOWS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_wf_user ON workflows(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_wf_lifecycle ON workflows(lifecycle);",
    "CREATE INDEX IF NOT EXISTS idx_wf_name ON workflows(user_id, name);",
]

_CREATE_EXECUTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS executions (
    execution_id  TEXT PRIMARY KEY,
    workflow_id   TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    speed         REAL NOT NULL,
    quality       REAL NOT NULL,
    alignment     REAL NOT NULL,
    leverage      REAL NOT NULL,
    composite     REAL NOT NULL,
    outcome       TEXT DEFAULT 'success',
    context       TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);
"""

_CREATE_EXECUTIONS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_exec_wf ON executions(workflow_id);",
    "CREATE INDEX IF NOT EXISTS idx_exec_created ON executions(created_at);",
]


class WorkflowEngine:
    """工作流生命週期引擎.

    SQLite-backed，支援 6 階段生命週期管理。
    所有公開方法皆 try/except 包裝，失敗不拋異常（graceful degradation）。
    """

    def __init__(
        self,
        workspace: Path,
        event_bus: Optional[Any] = None,
    ) -> None:
        """初始化 WorkflowEngine.

        Args:
            workspace: 工作目錄（DB 存放位置）
            event_bus: EventBus 實例（可選，用於發布事件）
        """
        self._workspace = Path(workspace)
        self._event_bus = event_bus
        self._db_path = self._workspace / "_system" / "wee" / "workflow_state.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        self._initialized = False

    # ═══════════════════════════════════════════
    # SQLite 連線管理
    # ═══════════════════════════════════════════

    def _get_conn(self) -> sqlite3.Connection:
        """取得 thread-local SQLite 連線."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")

        if not self._initialized:
            self._init_db(self._local.conn)

        return self._local.conn

    def _init_db(self, conn: sqlite3.Connection) -> None:
        """建立 tables + indexes."""
        with self._lock:
            if self._initialized:
                return
            conn.execute(_CREATE_WORKFLOWS_TABLE)
            for idx_sql in _CREATE_WORKFLOWS_INDEXES:
                conn.execute(idx_sql)
            conn.execute(_CREATE_EXECUTIONS_TABLE)
            for idx_sql in _CREATE_EXECUTIONS_INDEXES:
                conn.execute(idx_sql)
            conn.commit()
            self._initialized = True

    # ═══════════════════════════════════════════
    # 工作流 CRUD
    # ═══════════════════════════════════════════

    def get_or_create(
        self,
        user_id: str,
        name: str,
        tags: Optional[List[str]] = None,
    ) -> WorkflowRecord:
        """取得或建立工作流.

        同一 user_id + name 只會建立一個工作流（冪等）。
        新建立的工作流 lifecycle = 'birth'。

        Args:
            user_id: 用戶 ID
            name: 工作流名稱
            tags: 標籤列表

        Returns:
            WorkflowRecord
        """
        conn = self._get_conn()

        # 查詢現有
        row = conn.execute(
            "SELECT * FROM workflows WHERE user_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()

        if row:
            return self._row_to_record(row)

        # 建立新工作流
        now = datetime.now(TZ_TAIPEI).isoformat()
        wf_id = str(uuid.uuid4())
        tags_json = json.dumps(tags or [], ensure_ascii=False)

        conn.execute(
            """INSERT INTO workflows
               (workflow_id, user_id, name, lifecycle, success_count,
                total_runs, avg_composite, variance, baseline_composite,
                tags_json, created_at, updated_at)
               VALUES (?, ?, ?, 'birth', 0, 0, 0.0, 0.0, NULL, ?, ?, ?)""",
            (wf_id, user_id, name, tags_json, now, now),
        )
        conn.commit()

        return WorkflowRecord(
            workflow_id=wf_id,
            user_id=user_id,
            name=name,
            lifecycle="birth",
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRecord]:
        """取得單一工作流."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM workflows WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        return self._row_to_record(row) if row else None

    def list_workflows(
        self,
        user_id: str,
        lifecycle: Optional[str] = None,
    ) -> List[WorkflowRecord]:
        """列出用戶工作流."""
        conn = self._get_conn()
        if lifecycle:
            rows = conn.execute(
                "SELECT * FROM workflows WHERE user_id = ? AND lifecycle = ? ORDER BY updated_at DESC",
                (user_id, lifecycle),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM workflows WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    # ═══════════════════════════════════════════
    # 記錄執行
    # ═══════════════════════════════════════════

    def record_execution(
        self,
        workflow_id: str,
        score: FourDScore,
        outcome: str = "success",
        context: str = "",
    ) -> Optional[ExecutionRecord]:
        """記錄一次執行.

        1. 寫入 executions 表
        2. 更新 workflows 的 rolling stats
        3. 檢查自動 lifecycle 遷轉
        4. 發布 WEE_RECORDED 事件

        Args:
            workflow_id: 工作流 ID
            score: 4D 分數
            outcome: "success" | "partial" | "failed"
            context: 上下文描述

        Returns:
            ExecutionRecord 或 None
        """
        conn = self._get_conn()

        # 確認工作流存在
        wf = self.get_workflow(workflow_id)
        if not wf:
            logger.warning(f"Workflow {workflow_id} not found")
            return None

        # 建立執行記錄
        now = datetime.now(TZ_TAIPEI).isoformat()
        exec_id = str(uuid.uuid4())
        composite = score.composite
        is_success = outcome == "success"

        conn.execute(
            """INSERT INTO executions
               (execution_id, workflow_id, user_id, speed, quality,
                alignment, leverage, composite, outcome, context, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                exec_id, workflow_id, wf.user_id,
                score.speed, score.quality, score.alignment, score.leverage,
                composite, outcome, context[:500], now,
            ),
        )

        # 更新 workflows 統計
        new_total = wf.total_runs + 1
        new_success = wf.success_count + (1 if is_success else 0)

        conn.execute(
            """UPDATE workflows
               SET total_runs = ?, success_count = ?, updated_at = ?
               WHERE workflow_id = ?""",
            (new_total, new_success, now, workflow_id),
        )
        conn.commit()

        # 更新 rolling stats
        self._update_rolling_stats(workflow_id)

        # 重新讀取最新狀態
        wf = self.get_workflow(workflow_id)

        # 檢查自動遷轉
        if wf:
            self._check_transition(wf)

        # 建立回傳物件
        record = ExecutionRecord(
            execution_id=exec_id,
            workflow_id=workflow_id,
            user_id=wf.user_id if wf else "",
            speed=score.speed,
            quality=score.quality,
            alignment=score.alignment,
            leverage=score.leverage,
            composite=composite,
            outcome=outcome,
            context=context[:500],
            created_at=now,
        )

        # 發布事件
        self._publish("WEE_RECORDED", {
            "workflow_id": workflow_id,
            "execution_id": exec_id,
            "composite": composite,
            "outcome": outcome,
            "lifecycle": wf.lifecycle if wf else "birth",
        })

        return record

    # ═══════════════════════════════════════════
    # 高原偵測
    # ═══════════════════════════════════════════

    def check_plateau(self, workflow_id: str) -> Dict[str, Any]:
        """高原偵測.

        條件：最近 5 次 composite 的 variance < 0.5 AND avg < 7.0。
        avg >= 7.0 的穩定表現 = 非高原（高分穩定是好事）。

        Args:
            workflow_id: 工作流 ID

        Returns:
            {"is_plateau": bool, "avg": float, "variance": float, "run_count": int}
        """
        wf = self.get_workflow(workflow_id)
        if not wf:
            return {"is_plateau": False, "avg": 0.0, "variance": 0.0, "run_count": 0}

        if wf.total_runs < PLATEAU_MIN_RUNS:
            return {
                "is_plateau": False,
                "avg": wf.avg_composite,
                "variance": wf.variance,
                "run_count": wf.total_runs,
            }

        is_plateau = (
            wf.variance < PLATEAU_MAX_VARIANCE
            and wf.avg_composite < PLATEAU_MAX_AVG
        )

        if is_plateau and wf.lifecycle not in ("plateau", "evolution", "archived"):
            # 遷轉到 plateau
            self._set_lifecycle(workflow_id, "plateau")
            self._publish("WEE_PLATEAU_DETECTED", {
                "workflow_id": workflow_id,
                "avg": wf.avg_composite,
                "variance": wf.variance,
                "run_count": wf.total_runs,
            })

        return {
            "is_plateau": is_plateau,
            "avg": round(wf.avg_composite, 4),
            "variance": round(wf.variance, 4),
            "run_count": wf.total_runs,
        }

    # ═══════════════════════════════════════════
    # 突變
    # ═══════════════════════════════════════════

    def mutate(
        self,
        workflow_id: str,
        strategy: str = "reorder",
    ) -> Optional[WorkflowRecord]:
        """套用突變策略.

        lifecycle → 'evolution'，凍結當前 avg_composite 為 baseline。

        Args:
            workflow_id: 工作流 ID
            strategy: 突變策略

        Returns:
            更新後的 WorkflowRecord 或 None
        """
        wf = self.get_workflow(workflow_id)
        if not wf:
            return None

        conn = self._get_conn()
        now = datetime.now(TZ_TAIPEI).isoformat()

        conn.execute(
            """UPDATE workflows
               SET lifecycle = 'evolution',
                   baseline_composite = avg_composite,
                   updated_at = ?
               WHERE workflow_id = ?""",
            (now, workflow_id),
        )
        conn.commit()

        self._publish("WEE_LIFECYCLE_CHANGED", {
            "workflow_id": workflow_id,
            "old_lifecycle": wf.lifecycle,
            "new_lifecycle": "evolution",
            "strategy": strategy,
        })

        return self.get_workflow(workflow_id)

    # ═══════════════════════════════════════════
    # 查詢
    # ═══════════════════════════════════════════

    def get_recent_executions(
        self,
        workflow_id: str,
        limit: int = 5,
    ) -> List[ExecutionRecord]:
        """取得最近 N 次執行記錄（按時間升序，oldest first）."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM executions
               WHERE workflow_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (workflow_id, limit),
        ).fetchall()

        # 反轉為升序（oldest → newest）
        records = [self._row_to_execution(r) for r in reversed(rows)]
        return records

    def get_proficiency(self, user_id: str) -> Dict[str, Any]:
        """取得用戶整體 4D 熟練度.

        計算所有活躍工作流（非 archived）的平均 4D 分數。
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT AVG(e.speed), AVG(e.quality), AVG(e.alignment), AVG(e.leverage),
                      AVG(e.composite), COUNT(*)
               FROM executions e
               JOIN workflows w ON e.workflow_id = w.workflow_id
               WHERE w.user_id = ? AND w.lifecycle != 'archived'""",
            (user_id,),
        ).fetchone()

        if not rows or rows[5] == 0:
            return {
                "speed": 5.0, "quality": 5.0,
                "alignment": 5.0, "leverage": 4.0,
                "composite": 0.0, "total_executions": 0,
            }

        return {
            "speed": round(rows[0] or 5.0, 2),
            "quality": round(rows[1] or 5.0, 2),
            "alignment": round(rows[2] or 5.0, 2),
            "leverage": round(rows[3] or 4.0, 2),
            "composite": round(rows[4] or 0.0, 2),
            "total_executions": rows[5],
        }

    # ═══════════════════════════════════════════
    # 私有方法
    # ═══════════════════════════════════════════

    def _update_rolling_stats(self, workflow_id: str) -> None:
        """更新加權滾動平均和方差.

        Window=5，權重 [1,2,3,4,5]（oldest → newest，近期權重越高）。
        """
        recent = self.get_recent_executions(workflow_id, limit=ROLLING_WINDOW)
        if not recent:
            return

        n = len(recent)
        weights = list(range(1, n + 1))
        total_weight = sum(weights)

        composites = [e.composite for e in recent]

        # 加權平均
        weighted_sum = sum(w * c for w, c in zip(weights, composites))
        avg = weighted_sum / total_weight

        # 加權方差
        weighted_var_sum = sum(
            w * (c - avg) ** 2 for w, c in zip(weights, composites)
        )
        variance = weighted_var_sum / total_weight

        conn = self._get_conn()
        now = datetime.now(TZ_TAIPEI).isoformat()
        conn.execute(
            """UPDATE workflows
               SET avg_composite = ?, variance = ?, updated_at = ?
               WHERE workflow_id = ?""",
            (round(avg, 6), round(variance, 6), now, workflow_id),
        )
        conn.commit()

    def _check_transition(self, wf: WorkflowRecord) -> None:
        """檢查自動 lifecycle 遷轉.

        - birth → growth：success_count >= 3
        - growth → maturity：success_count >= 8 AND avg_composite >= 7.0
        """
        new_lifecycle = None

        if wf.lifecycle == "birth" and wf.success_count >= BIRTH_TO_GROWTH_SUCCESS:
            new_lifecycle = "growth"

        elif wf.lifecycle == "growth":
            if (
                wf.success_count >= GROWTH_TO_MATURITY_SUCCESS
                and wf.avg_composite >= GROWTH_TO_MATURITY_AVG
            ):
                new_lifecycle = "maturity"

        if new_lifecycle:
            self._set_lifecycle(wf.workflow_id, new_lifecycle)
            self._publish("WEE_LIFECYCLE_CHANGED", {
                "workflow_id": wf.workflow_id,
                "old_lifecycle": wf.lifecycle,
                "new_lifecycle": new_lifecycle,
            })

    def _set_lifecycle(self, workflow_id: str, lifecycle: str) -> None:
        """更新 lifecycle."""
        conn = self._get_conn()
        now = datetime.now(TZ_TAIPEI).isoformat()
        conn.execute(
            "UPDATE workflows SET lifecycle = ?, updated_at = ? WHERE workflow_id = ?",
            (lifecycle, now, workflow_id),
        )
        conn.commit()

    def _publish(self, event_type: str, data: Dict) -> None:
        """EventBus 發布（靜默失敗）."""
        if self._event_bus:
            try:
                self._event_bus.publish(event_type, data)
            except Exception as e:
                logger.warning(f"EventBus publish '{event_type}' failed: {e}")

    def _row_to_record(self, row: sqlite3.Row) -> WorkflowRecord:
        """SQLite Row → WorkflowRecord."""
        tags = []
        try:
            tags = json.loads(row["tags_json"])
        except (json.JSONDecodeError, KeyError):
            pass

        return WorkflowRecord(
            workflow_id=row["workflow_id"],
            user_id=row["user_id"],
            name=row["name"],
            lifecycle=row["lifecycle"],
            success_count=row["success_count"],
            total_runs=row["total_runs"],
            avg_composite=row["avg_composite"],
            variance=row["variance"],
            baseline_composite=row["baseline_composite"],
            tags=tags,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_execution(self, row: sqlite3.Row) -> ExecutionRecord:
        """SQLite Row → ExecutionRecord."""
        return ExecutionRecord(
            execution_id=row["execution_id"],
            workflow_id=row["workflow_id"],
            user_id=row["user_id"],
            speed=row["speed"],
            quality=row["quality"],
            alignment=row["alignment"],
            leverage=row["leverage"],
            composite=row["composite"],
            outcome=row["outcome"],
            context=row["context"],
            created_at=row["created_at"],
        )
