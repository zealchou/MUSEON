"""PulseDB — SQLite 排程與探索日誌.

VITA 生命力引擎的結構層儲存。
管理排程任務、探索日誌、演化歷程。
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))


class PulseDB:
    """SQLite-based pulse schedule and exploration database."""

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # 防護：0-byte DB 檔 = 損壞，刪除後讓 _init_db 重建
        if self._db_path.exists() and self._db_path.stat().st_size == 0:
            logger.warning(f"PulseDB: 偵測到 0-byte DB 檔 {self._db_path}，刪除並重建")
            self._db_path.unlink()
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False, timeout=30
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schedules (
                id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,        -- 'reminder' | 'recurring' | 'cron'
                description TEXT NOT NULL,
                schedule TEXT NOT NULL,          -- ISO time / 'every 3h' / cron expr
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_run TEXT,
                run_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'       -- JSON
            );

            CREATE TABLE IF NOT EXISTS explorations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                topic TEXT NOT NULL,
                motivation TEXT NOT NULL,        -- 'curiosity'|'mission'|'skill'|'world'|'self'
                query TEXT,
                findings TEXT,
                crystallized INTEGER DEFAULT 0,
                crystal_id TEXT,
                tokens_used INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                duration_ms INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending'    -- 'pending'|'exploring'|'done'|'failed'
            );

            CREATE TABLE IF NOT EXISTS anima_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                element TEXT NOT NULL,           -- 'qian'|'kun'|'zhen'|'xun'|'kan'|'li'|'gen'|'dui'
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL,
                absolute_after INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evolution_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                threshold TEXT NOT NULL,         -- 'sprout_100'|'branch_500'|'tree_1000'|'phoenix_2000'|'star_5000'
                element TEXT,                   -- which element triggered (null for total thresholds)
                absolute_values TEXT NOT NULL,   -- JSON snapshot
                acknowledged INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS morphenix_proposals (
                id TEXT PRIMARY KEY,              -- proposal_{date}_{seq}
                level TEXT NOT NULL,              -- 'L1'|'L2'|'L3'
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                affected_files TEXT DEFAULT '[]', -- JSON array
                status TEXT DEFAULT 'pending',    -- 'pending'|'approved'|'rejected'|'executed'|'expired'
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by TEXT,                  -- 'auto'|'human'|'auto_72h'
                executed_at TEXT,
                source_notes TEXT DEFAULT '[]',   -- JSON array of note refs
                telegram_message_id INTEGER,      -- for inline keyboard tracking
                metadata TEXT DEFAULT '{}'        -- JSON
            );

            CREATE TABLE IF NOT EXISTS morphenix_rollbacks (
                id TEXT PRIMARY KEY,
                proposal_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                rollback_tag TEXT NOT NULL,
                rolled_back_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS commitments (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_message TEXT,
                our_response_snippet TEXT NOT NULL,
                promise_text TEXT NOT NULL,
                promise_type TEXT DEFAULT 'action', -- 'temporal'|'action'|'reminder'|'recurring'
                due_at TEXT,                         -- ISO datetime
                status TEXT DEFAULT 'pending',       -- 'pending'|'fulfilled'|'overdue'|'cancelled'
                created_at TEXT NOT NULL,
                fulfilled_at TEXT,
                follow_up_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'            -- JSON
            );

            CREATE INDEX IF NOT EXISTS idx_explorations_date
                ON explorations(timestamp);
            CREATE INDEX IF NOT EXISTS idx_anima_log_element
                ON anima_log(element, timestamp);
            CREATE INDEX IF NOT EXISTS idx_morphenix_status
                ON morphenix_proposals(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_commitments_status_due
                ON commitments(status, due_at);

            CREATE TABLE IF NOT EXISTS metacognition (
                id TEXT PRIMARY KEY,
                session_id TEXT,

                -- PreCognition
                pre_triggered INTEGER DEFAULT 0,
                pre_verdict TEXT,
                pre_feedback TEXT,
                pre_revision_applied INTEGER DEFAULT 0,
                pre_review_time_ms REAL,

                -- PostCognition: Prediction
                predicted_reaction_type TEXT,
                predicted_reaction TEXT,
                prediction_confidence REAL,

                -- PostCognition: Observation
                actual_reaction_type TEXT,
                prediction_accuracy REAL,
                accuracy_method TEXT,

                -- Meta
                routing_loop TEXT,
                routing_mode TEXT,
                matched_skills TEXT,
                user_message_snippet TEXT,
                response_snippet TEXT,
                created_at TEXT NOT NULL,
                observed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_metacognition_session
                ON metacognition(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_metacognition_unobserved
                ON metacognition(session_id, observed_at)
                WHERE observed_at IS NULL AND predicted_reaction_type IS NOT NULL;

            -- Scout 草稿表（SkillForgeScout 產出）
            CREATE TABLE IF NOT EXISTS scout_drafts (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                mode TEXT NOT NULL,              -- 'gap'|'upgrade'|'blank'
                research_summary TEXT,
                draft_content TEXT NOT NULL,
                target_skill TEXT,               -- 目標 Skill 檔案
                status TEXT DEFAULT 'pending',   -- 'pending'|'submitted'|'approved'|'rejected'
                created_at TEXT NOT NULL,
                submitted_at TEXT,
                metadata TEXT DEFAULT '{}'        -- JSON
            );
            CREATE INDEX IF NOT EXISTS idx_scout_drafts_status
                ON scout_drafts(status, created_at);

            -- Health Score 歷史表（DendriticScorer 產出）
            CREATE TABLE IF NOT EXISTS health_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                score REAL NOT NULL,
                tier INTEGER NOT NULL,           -- 0=healthy, 1=degraded, 2=critical
                event_count INTEGER DEFAULT 0,
                incident_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'        -- JSON
            );
            CREATE INDEX IF NOT EXISTS idx_health_scores_ts
                ON health_scores(timestamp);

            -- Incident 記錄表（DendriticScorer Incident Package）
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                incident_type TEXT NOT NULL,      -- 'soft_failure'|'hard_failure'|'degradation'
                module TEXT NOT NULL,
                pattern TEXT NOT NULL,
                frequency INTEGER DEFAULT 0,
                health_delta REAL DEFAULT 0.0,
                suggested_tier INTEGER DEFAULT 1,
                raw_log_snippet TEXT,
                research_status TEXT DEFAULT 'none', -- 'none'|'pending'|'done'|'no_value'
                research_summary TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                metadata TEXT DEFAULT '{}'        -- JSON
            );
            CREATE INDEX IF NOT EXISTS idx_incidents_module
                ON incidents(module, created_at);
            CREATE INDEX IF NOT EXISTS idx_incidents_status
                ON incidents(research_status, created_at);
        """)
        conn.commit()

    # ── Schedule CRUD ──

    def add_schedule(
        self, task_id: str, task_type: str, description: str, schedule: str,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO schedules (id, task_type, description, schedule, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, task_type, description, schedule, now, meta_json),
        )
        conn.commit()
        return {"id": task_id, "created": True}

    def remove_schedule(self, task_id: str) -> bool:
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM schedules WHERE id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0

    def list_schedules(self, enabled_only: bool = True) -> List[Dict]:
        conn = self._get_conn()
        query = "SELECT * FROM schedules"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY created_at"
        rows = conn.execute(query).fetchall()
        return [dict(r) for r in rows]

    def mark_schedule_run(self, task_id: str) -> None:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        conn.execute(
            "UPDATE schedules SET last_run = ?, run_count = run_count + 1 WHERE id = ?",
            (now, task_id),
        )
        conn.commit()

    # ── Exploration Log ──

    def log_exploration(
        self, topic: str, motivation: str, query: str = "",
        findings: str = "", crystallized: bool = False, crystal_id: str = "",
        tokens_used: int = 0, cost_usd: float = 0.0, duration_ms: int = 0,
        status: str = "done",
    ) -> int:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "INSERT INTO explorations "
            "(timestamp, topic, motivation, query, findings, crystallized, crystal_id, "
            "tokens_used, cost_usd, duration_ms, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, topic, motivation, query, findings,
             1 if crystallized else 0, crystal_id,
             tokens_used, cost_usd, duration_ms, status),
        )
        conn.commit()
        return cur.lastrowid

    def get_today_explorations(self) -> List[Dict]:
        conn = self._get_conn()
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT * FROM explorations WHERE timestamp LIKE ? ORDER BY timestamp",
            (f"{today}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_today_exploration_count(self) -> int:
        return len(self.get_today_explorations())

    def get_today_exploration_cost(self) -> float:
        exps = self.get_today_explorations()
        return sum(e.get("cost_usd", 0) for e in exps)

    def get_recent_explorations(self, days: int = 30, limit: int = 30) -> List[str]:
        """Return recent explored topic strings for deduplication."""
        conn = self._get_conn()
        cutoff = (datetime.now(TZ8) - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT topic FROM explorations WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [r["topic"] for r in rows]

    # ── ANIMA Log ──

    def log_anima_change(
        self, element: str, delta: int, reason: str, absolute_after: int,
    ) -> int:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "INSERT INTO anima_log (timestamp, element, delta, reason, absolute_after) "
            "VALUES (?, ?, ?, ?, ?)",
            (now, element, delta, reason, absolute_after),
        )
        conn.commit()
        return cur.lastrowid

    def get_anima_history(self, element: str = None, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        if element:
            rows = conn.execute(
                "SELECT * FROM anima_log WHERE element = ? ORDER BY timestamp DESC LIMIT ?",
                (element, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM anima_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Evolution Events ──

    def log_evolution_event(
        self, threshold: str, element: Optional[str],
        absolute_values: Dict[str, int],
    ) -> int:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "INSERT INTO evolution_events (timestamp, threshold, element, absolute_values) "
            "VALUES (?, ?, ?, ?)",
            (now, threshold, element, json.dumps(absolute_values, ensure_ascii=False)),
        )
        conn.commit()
        return cur.lastrowid

    def get_pending_evolutions(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM evolution_events WHERE acknowledged = 0 ORDER BY timestamp",
        ).fetchall()
        return [dict(r) for r in rows]

    def acknowledge_evolution(self, event_id: int) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE evolution_events SET acknowledged = 1 WHERE id = ?",
            (event_id,),
        )
        conn.commit()

    # ── Morphenix Proposals ──

    def save_proposal(
        self, proposal_id: str, level: str, title: str,
        description: str, affected_files: List[str] = None,
        source_notes: List[str] = None, metadata: Dict = None,
    ) -> str:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO morphenix_proposals "
            "(id, level, title, description, affected_files, status, "
            "created_at, source_notes, metadata) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
            (
                proposal_id, level, title, description,
                json.dumps(affected_files or [], ensure_ascii=False),
                now,
                json.dumps(source_notes or [], ensure_ascii=False),
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return proposal_id

    def get_pending_proposals(self) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM morphenix_proposals WHERE status = 'pending' "
            "ORDER BY created_at",
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_proposals(self, limit: int = 50) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM morphenix_proposals ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def approve_proposal(
        self, proposal_id: str, decided_by: str = "human",
    ) -> bool:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "UPDATE morphenix_proposals "
            "SET status = 'approved', decided_at = ?, decided_by = ? "
            "WHERE id = ? AND status = 'pending'",
            (now, decided_by, proposal_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def reject_proposal(
        self, proposal_id: str, decided_by: str = "human",
    ) -> bool:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "UPDATE morphenix_proposals "
            "SET status = 'rejected', decided_at = ?, decided_by = ? "
            "WHERE id = ? AND status IN ('pending', 'approved')",
            (now, decided_by, proposal_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def mark_proposal_executed(self, proposal_id: str) -> bool:
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "UPDATE morphenix_proposals "
            "SET status = 'executed', executed_at = ? "
            "WHERE id = ? AND status = 'approved'",
            (now, proposal_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def mark_proposal_rolled_back(
        self, proposal_id: str, reason: str = "",
    ) -> bool:
        """將提案標記為已回滾."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "UPDATE morphenix_proposals "
            "SET status = 'rolled_back', decided_at = ?, decided_by = ? "
            "WHERE id = ?",
            (now, f"rollback:{reason[:100]}", proposal_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def log_rollback(
        self, proposal_id: str, reason: str, rollback_tag: str,
    ) -> None:
        """寫入回滾記錄（不可刪除的審計軌跡）."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO morphenix_rollbacks
               (id, proposal_id, reason, rollback_tag, rolled_back_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                f"rb_{proposal_id}_{datetime.now(TZ8).strftime('%Y%m%d%H%M%S')}",
                proposal_id,
                reason[:500],
                rollback_tag,
                datetime.now(TZ8).isoformat(),
            ),
        )
        conn.commit()

    def count_rollbacks_today(self) -> int:
        """計算今天的回滾次數."""
        conn = self._get_conn()
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COUNT(*) FROM morphenix_rollbacks "
            "WHERE rolled_back_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return row[0] if row else 0

    def set_proposal_telegram_id(
        self, proposal_id: str, message_id: int,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE morphenix_proposals SET telegram_message_id = ? WHERE id = ?",
            (message_id, proposal_id),
        )
        conn.commit()

    def auto_approve_stale_proposals(self, hours: int = 72) -> List[str]:
        """72 小時未處理的提案自動批准."""
        conn = self._get_conn()
        cutoff = (datetime.now(TZ8) - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT id FROM morphenix_proposals "
            "WHERE status = 'pending' AND created_at < ?",
            (cutoff,),
        ).fetchall()
        approved_ids = []
        now = datetime.now(TZ8).isoformat()
        for row in rows:
            pid = row["id"]
            conn.execute(
                "UPDATE morphenix_proposals "
                "SET status = 'approved', decided_at = ?, decided_by = 'auto_72h' "
                "WHERE id = ?",
                (now, pid),
            )
            approved_ids.append(pid)
        conn.commit()
        return approved_ids

    # ── Commitment CRUD（承諾追蹤）──

    def add_commitment(
        self,
        commitment_id: str,
        session_id: str,
        promise_text: str,
        promise_type: str = "action",
        due_at: Optional[str] = None,
        user_message: Optional[str] = None,
        our_response_snippet: str = "",
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """新增一筆承諾記錄."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO commitments "
            "(id, session_id, user_message, our_response_snippet, promise_text, "
            "promise_type, due_at, status, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                commitment_id, session_id,
                (user_message or "")[:500],
                our_response_snippet[:500],
                promise_text,
                promise_type,
                due_at,
                now,
                meta_json,
            ),
        )
        conn.commit()
        logger.info(f"[Commitment] 新增承諾: {commitment_id} — {promise_text[:60]}")
        return {"id": commitment_id, "created": True}

    def get_pending_commitments(self) -> List[Dict]:
        """取得所有待兌現的承諾."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM commitments WHERE status = 'pending' "
            "ORDER BY due_at ASC NULLS LAST",
        ).fetchall()
        return [dict(r) for r in rows]

    def get_overdue_commitments(self) -> List[Dict]:
        """取得所有已逾期的承諾（due_at < now AND status = 'pending'）."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        rows = conn.execute(
            "SELECT * FROM commitments "
            "WHERE status = 'pending' AND due_at IS NOT NULL AND due_at < ? "
            "ORDER BY due_at ASC",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_due_soon_commitments(self, hours: int = 2) -> List[Dict]:
        """取得即將到期的承諾（在 N 小時內到期）."""
        conn = self._get_conn()
        now = datetime.now(TZ8)
        cutoff = (now + timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT * FROM commitments "
            "WHERE status = 'pending' AND due_at IS NOT NULL "
            "AND due_at > ? AND due_at <= ? "
            "ORDER BY due_at ASC",
            (now.isoformat(), cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    def fulfill_commitment(self, commitment_id: str) -> bool:
        """標記承諾已兌現."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "UPDATE commitments SET status = 'fulfilled', fulfilled_at = ? "
            "WHERE id = ? AND status IN ('pending', 'overdue')",
            (now, commitment_id),
        )
        conn.commit()
        if cur.rowcount > 0:
            logger.info(f"[Commitment] 承諾兌現: {commitment_id}")
        return cur.rowcount > 0

    def cancel_commitment(self, commitment_id: str, reason: str = "") -> bool:
        """取消承諾."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        meta = json.dumps({"cancel_reason": reason}, ensure_ascii=False)
        cur = conn.execute(
            "UPDATE commitments SET status = 'cancelled', fulfilled_at = ?, "
            "metadata = ? WHERE id = ? AND status = 'pending'",
            (now, meta, commitment_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def mark_overdue_commitments(self) -> List[str]:
        """將所有已逾期但仍 pending 的承諾標記為 overdue."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        rows = conn.execute(
            "SELECT id FROM commitments "
            "WHERE status = 'pending' AND due_at IS NOT NULL AND due_at < ?",
            (now,),
        ).fetchall()
        overdue_ids = []
        for row in rows:
            cid = row["id"]
            conn.execute(
                "UPDATE commitments SET status = 'overdue' WHERE id = ?",
                (cid,),
            )
            overdue_ids.append(cid)
        conn.commit()
        if overdue_ids:
            logger.info(f"[Commitment] 標記逾期: {overdue_ids}")
        return overdue_ids

    def increment_follow_up(self, commitment_id: str) -> None:
        """遞增承諾的跟進次數."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE commitments SET follow_up_count = follow_up_count + 1 "
            "WHERE id = ?",
            (commitment_id,),
        )
        conn.commit()

    def get_all_commitments(self, limit: int = 50) -> List[Dict]:
        """取得所有承諾記錄."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM commitments ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── MetaCognition CRUD（元認知引擎）──

    def add_metacognition(
        self,
        metacog_id: str,
        session_id: str,
        pre_triggered: bool = False,
        pre_verdict: Optional[str] = None,
        pre_feedback: Optional[str] = None,
        pre_revision_applied: bool = False,
        pre_review_time_ms: Optional[float] = None,
        predicted_reaction_type: Optional[str] = None,
        predicted_reaction: Optional[str] = None,
        prediction_confidence: Optional[float] = None,
        routing_loop: Optional[str] = None,
        routing_mode: Optional[str] = None,
        matched_skills: Optional[List[str]] = None,
        user_message_snippet: Optional[str] = None,
        response_snippet: Optional[str] = None,
    ) -> Dict:
        """新增一筆元認知記錄."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        skills_json = json.dumps(matched_skills or [], ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO metacognition "
            "(id, session_id, pre_triggered, pre_verdict, pre_feedback, "
            "pre_revision_applied, pre_review_time_ms, "
            "predicted_reaction_type, predicted_reaction, prediction_confidence, "
            "routing_loop, routing_mode, matched_skills, "
            "user_message_snippet, response_snippet, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                metacog_id, session_id,
                1 if pre_triggered else 0,
                pre_verdict, pre_feedback,
                1 if pre_revision_applied else 0,
                pre_review_time_ms,
                predicted_reaction_type, predicted_reaction, prediction_confidence,
                routing_loop, routing_mode, skills_json,
                (user_message_snippet or "")[:100],
                (response_snippet or "")[:100],
                now,
            ),
        )
        conn.commit()
        return {"id": metacog_id, "created": True}

    def get_latest_prediction(self, session_id: str) -> Optional[Dict]:
        """取得本 session 最後一筆有預測但未觀察的記錄."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM metacognition "
            "WHERE session_id = ? AND predicted_reaction_type IS NOT NULL "
            "AND observed_at IS NULL "
            "ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def update_observation(
        self,
        metacog_id: str,
        actual_reaction_type: str,
        prediction_accuracy: float,
        accuracy_method: str = "cpu_heuristic",
    ) -> bool:
        """填入觀察結果（下次互動時呼叫）."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "UPDATE metacognition SET "
            "actual_reaction_type = ?, prediction_accuracy = ?, "
            "accuracy_method = ?, observed_at = ? "
            "WHERE id = ?",
            (actual_reaction_type, prediction_accuracy, accuracy_method, now, metacog_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def get_prediction_accuracy_stats(self, days: int = 7) -> Dict:
        """取得預判準確率統計."""
        conn = self._get_conn()
        cutoff = (datetime.now(TZ8) - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT prediction_accuracy, predicted_reaction_type, actual_reaction_type "
            "FROM metacognition "
            "WHERE prediction_accuracy IS NOT NULL AND created_at > ?",
            (cutoff,),
        ).fetchall()
        if not rows:
            return {"total": 0, "avg_accuracy": None, "by_type": {}}
        accuracies = [r["prediction_accuracy"] for r in rows]
        by_type: Dict[str, List[float]] = {}
        for r in rows:
            rt = r["predicted_reaction_type"] or "unknown"
            by_type.setdefault(rt, []).append(r["prediction_accuracy"])
        return {
            "total": len(rows),
            "avg_accuracy": sum(accuracies) / len(accuracies),
            "by_type": {
                k: sum(v) / len(v) for k, v in by_type.items()
            },
        }

    def get_precognition_stats(self, days: int = 7) -> Dict:
        """取得 PreCognition 審查統計."""
        conn = self._get_conn()
        cutoff = (datetime.now(TZ8) - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT pre_triggered, pre_verdict, pre_revision_applied "
            "FROM metacognition WHERE created_at > ?",
            (cutoff,),
        ).fetchall()
        if not rows:
            return {"total": 0, "triggered": 0, "revision_rate": 0.0}
        total = len(rows)
        triggered = sum(1 for r in rows if r["pre_triggered"])
        revised = sum(1 for r in rows if r["pre_revision_applied"])
        verdicts: Dict[str, int] = {}
        for r in rows:
            v = r["pre_verdict"] or "skipped"
            verdicts[v] = verdicts.get(v, 0) + 1
        return {
            "total": total,
            "triggered": triggered,
            "trigger_rate": triggered / total if total else 0,
            "revised": revised,
            "revision_rate": revised / total if total else 0,
            "verdicts": verdicts,
        }

    # ── Scout Drafts CRUD（SkillForgeScout 草稿）──

    def save_scout_draft(
        self,
        draft_id: str,
        topic: str,
        mode: str,
        draft_content: str,
        target_skill: str = "",
        research_summary: str = "",
        metadata: Optional[Dict] = None,
    ) -> str:
        """儲存一筆 Scout 草稿."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO scout_drafts "
            "(id, topic, mode, research_summary, draft_content, target_skill, "
            "status, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (
                draft_id, topic, mode, research_summary, draft_content,
                target_skill, now,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return draft_id

    def get_pending_scout_drafts(self) -> List[Dict]:
        """取得待處理的 Scout 草稿."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM scout_drafts WHERE status = 'pending' "
            "ORDER BY created_at",
        ).fetchall()
        return [dict(r) for r in rows]

    def update_scout_draft_status(
        self, draft_id: str, status: str,
    ) -> bool:
        """更新草稿狀態."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "UPDATE scout_drafts SET status = ?, submitted_at = ? WHERE id = ?",
            (status, now, draft_id),
        )
        conn.commit()
        return cur.rowcount > 0

    # ── Health Scores CRUD（DendriticScorer 歷史）──

    def log_health_score(
        self,
        score: float,
        tier: int,
        event_count: int = 0,
        incident_count: int = 0,
        metadata: Optional[Dict] = None,
    ) -> int:
        """記錄一筆 Health Score."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "INSERT INTO health_scores "
            "(timestamp, score, tier, event_count, incident_count, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                now, score, tier, event_count, incident_count,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return cur.lastrowid

    def get_health_score_history(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """取得最近 N 小時的 Health Score 歷史."""
        conn = self._get_conn()
        cutoff = (datetime.now(TZ8) - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT * FROM health_scores WHERE timestamp > ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_health_score_trend(self, hours: int = 6) -> Dict:
        """取得 Health Score 趨勢摘要."""
        history = self.get_health_score_history(hours=hours, limit=200)
        if not history:
            return {"trend": "no_data", "avg_score": None, "samples": 0}

        scores = [h["score"] for h in history]
        avg = sum(scores) / len(scores)

        # 簡單趨勢：前半 vs 後半
        mid = len(scores) // 2
        if mid > 0:
            first_half = sum(scores[:mid]) / mid
            second_half = sum(scores[mid:]) / (len(scores) - mid)
            if second_half > first_half + 5:
                trend = "improving"
            elif second_half < first_half - 5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"

        return {
            "trend": trend,
            "avg_score": round(avg, 1),
            "min_score": round(min(scores), 1),
            "max_score": round(max(scores), 1),
            "samples": len(scores),
        }

    # ── Incidents CRUD（事件包記錄）──

    def save_incident(
        self,
        incident_id: str,
        incident_type: str,
        module: str,
        pattern: str,
        frequency: int = 0,
        health_delta: float = 0.0,
        suggested_tier: int = 1,
        raw_log_snippet: str = "",
        metadata: Optional[Dict] = None,
    ) -> str:
        """儲存一筆 Incident."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO incidents "
            "(id, incident_type, module, pattern, frequency, health_delta, "
            "suggested_tier, raw_log_snippet, created_at, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                incident_id, incident_type, module, pattern,
                frequency, health_delta, suggested_tier,
                raw_log_snippet[:1000], now,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        return incident_id

    def update_incident_research(
        self, incident_id: str, research_status: str,
        research_summary: str = "",
    ) -> bool:
        """更新 Incident 的研究狀態."""
        conn = self._get_conn()
        cur = conn.execute(
            "UPDATE incidents SET research_status = ?, research_summary = ? "
            "WHERE id = ?",
            (research_status, research_summary, incident_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def resolve_incident(self, incident_id: str) -> bool:
        """標記 Incident 已解決."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        cur = conn.execute(
            "UPDATE incidents SET resolved_at = ? WHERE id = ?",
            (now, incident_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def get_unresolved_incidents(self, module: str = None) -> List[Dict]:
        """取得未解決的 Incidents."""
        conn = self._get_conn()
        if module:
            rows = conn.execute(
                "SELECT * FROM incidents WHERE resolved_at IS NULL "
                "AND module = ? ORDER BY created_at DESC",
                (module,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM incidents WHERE resolved_at IS NULL "
                "ORDER BY created_at DESC",
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_incidents(self, hours: int = 24, limit: int = 50) -> List[Dict]:
        """取得最近 N 小時的 Incidents."""
        conn = self._get_conn()
        cutoff = (datetime.now(TZ8) - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT * FROM incidents WHERE created_at > ? "
            "ORDER BY created_at DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]
