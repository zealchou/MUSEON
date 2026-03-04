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
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
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
            "WHERE id = ? AND status = 'pending'",
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
