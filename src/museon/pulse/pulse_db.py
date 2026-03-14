"""PulseDB — SQLite 排程與探索日誌.

VITA 生命力引擎的結構層儲存。
管理排程任務、探索日誌、演化歷程。
"""

import json
import logging
import sqlite3
import threading
import time
import uuid
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
        # 防護：integrity check — 偵測 malformed DB 並自動重建
        if self._db_path.exists():
            self._integrity_check()
        self._init_db()

    def _integrity_check(self) -> None:
        """檢查 DB 完整性，損壞時自動從 dump 重建."""
        try:
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            if result and result[0] != "ok":
                logger.error(f"PulseDB: integrity_check FAILED: {result[0]}，嘗試重建")
                self._rebuild_from_dump()
        except sqlite3.DatabaseError as e:
            logger.error(f"PulseDB: integrity_check 異常: {e}，嘗試重建")
            self._rebuild_from_dump()

    def _rebuild_from_dump(self) -> None:
        """嘗試從損壞的 DB dump 可搶救的資料，重建乾淨的 DB."""
        bak = self._db_path.with_suffix(".db.malformed")
        try:
            # 嘗試 dump 可搶救的資料
            import subprocess
            dump_result = subprocess.run(
                ["sqlite3", str(self._db_path), ".dump"],
                capture_output=True, text=True, timeout=30,
            )
            # 備份損壞檔
            self._db_path.rename(bak)
            # 清除 WAL/SHM
            for suffix in (".db-wal", ".db-shm"):
                p = self._db_path.with_name(self._db_path.name.replace(".db", suffix))
                if p.exists():
                    p.unlink()
            if dump_result.returncode == 0 and dump_result.stdout.strip():
                # 從 dump 重建
                new_conn = sqlite3.connect(str(self._db_path))
                new_conn.executescript(dump_result.stdout)
                new_conn.close()
                logger.info("PulseDB: 從 dump 成功重建 DB")
            else:
                logger.warning("PulseDB: dump 失敗，將建立全新 DB")
        except Exception as e:
            logger.error(f"PulseDB: 重建失敗: {e}，將建立全新 DB")
            if self._db_path.exists():
                self._db_path.rename(bak)
            for suffix in (".db-wal", ".db-shm"):
                p = self._db_path.with_name(self._db_path.name.replace(".db", suffix))
                if p.exists():
                    p.unlink()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False, timeout=60
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=60000")
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

            -- ═══ Phase 2: JSON → SQLite 遷移 ═══

            -- Ceremony State（命名儀式狀態）
            CREATE TABLE IF NOT EXISTS ceremony_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            -- Eval: A/B Baselines（基線快照，一旦建立不可修改）
            CREATE TABLE IF NOT EXISTS eval_baselines (
                change_id TEXT PRIMARY KEY,
                baseline_json TEXT NOT NULL,     -- JSON blob
                created_at TEXT NOT NULL
            );

            -- Eval: Blindspots（盲點記錄）
            CREATE TABLE IF NOT EXISTS eval_blindspots (
                id TEXT PRIMARY KEY,
                blindspot_json TEXT NOT NULL,     -- JSON blob
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_eval_blindspots_ts
                ON eval_blindspots(created_at);

            -- Eval: Alerts（品質警報）
            CREATE TABLE IF NOT EXISTS eval_alerts (
                id TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                severity TEXT DEFAULT 'medium',
                message TEXT,
                details_json TEXT DEFAULT '{}',   -- JSON blob
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_eval_alerts_ts
                ON eval_alerts(created_at);
            CREATE INDEX IF NOT EXISTS idx_eval_alerts_type
                ON eval_alerts(alert_type, created_at);
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
        for attempt in range(3):
            try:
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
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < 2:
                    logger.warning(f"PulseDB: log_exploration locked, retry {attempt+1}/3")
                    time.sleep(1 + attempt)
                    continue
                logger.error(f"PulseDB: log_exploration failed: {e}")
                return -1
            except sqlite3.DatabaseError as e:
                logger.error(f"PulseDB: log_exploration DB error: {e}, reconnecting")
                self._local.conn = None
                if attempt < 2:
                    self._integrity_check()
                    continue
                return -1
        return -1

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

    def get_explorations_full(self, days: int = 14, limit: int = 50) -> List[Dict]:
        """Return recent explorations as full dicts (for SilentDigestion)."""
        conn = self._get_conn()
        cutoff = (datetime.now(TZ8) - timedelta(days=days)).isoformat()
        rows = conn.execute(
            "SELECT * FROM explorations WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]

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
        for attempt in range(3):
            try:
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
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < 2:
                    logger.warning(f"PulseDB: add_metacognition locked, retry {attempt+1}/3")
                    time.sleep(1 + attempt)
                    continue
                logger.error(f"PulseDB: add_metacognition failed: {e}")
                return {"id": metacog_id, "created": False, "error": str(e)}
            except sqlite3.DatabaseError as e:
                logger.error(f"PulseDB: add_metacognition DB error: {e}, reconnecting")
                self._local.conn = None
                if attempt < 2:
                    continue
                return {"id": metacog_id, "created": False, "error": str(e)}
        return {"id": metacog_id, "created": False, "error": "max retries"}

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

    # ══════════════════════════════════════════════
    # Phase 2: Ceremony State（命名儀式狀態）
    # ══════════════════════════════════════════════

    def get_ceremony_state(self) -> Dict[str, Any]:
        """取得命名儀式狀態."""
        conn = self._get_conn()
        rows = conn.execute("SELECT key, value FROM ceremony_state").fetchall()
        if not rows:
            return {}
        state = {}
        for r in rows:
            try:
                state[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                state[r["key"]] = r["value"]
        return state

    def save_ceremony_state(self, state: Dict[str, Any]) -> None:
        """儲存命名儀式狀態（全量覆寫）."""
        conn = self._get_conn()
        for key, value in state.items():
            conn.execute(
                "INSERT OR REPLACE INTO ceremony_state (key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=False)),
            )
        conn.commit()

    # ══════════════════════════════════════════════
    # Phase 2: Eval Baselines（A/B 基線）
    # ══════════════════════════════════════════════

    def load_eval_baselines(self) -> Dict[str, Any]:
        """載入所有 A/B 基線."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT change_id, baseline_json FROM eval_baselines "
            "ORDER BY created_at",
        ).fetchall()
        result = {}
        for r in rows:
            try:
                result[r["change_id"]] = json.loads(r["baseline_json"])
            except json.JSONDecodeError:
                logger.warning(f"eval_baselines JSON 解析失敗: {r['change_id']}")
        return result

    def save_eval_baseline(self, change_id: str, baseline: Dict[str, Any]) -> bool:
        """儲存 A/B 基線（HG-EVAL-BASELINE-LOCK: 已存在則拒絕）."""
        conn = self._get_conn()
        existing = conn.execute(
            "SELECT 1 FROM eval_baselines WHERE change_id = ?",
            (change_id,),
        ).fetchone()
        if existing:
            logger.warning(
                f"基線鎖定違規: 嘗試修改已存在的基線 {change_id} — "
                f"基線一旦建立不可修改，這是數據誠實的基礎"
            )
            return False
        now = datetime.now(TZ8).isoformat()
        conn.execute(
            "INSERT INTO eval_baselines (change_id, baseline_json, created_at) "
            "VALUES (?, ?, ?)",
            (change_id, json.dumps(baseline, ensure_ascii=False), now),
        )
        conn.commit()
        return True

    # ══════════════════════════════════════════════
    # Phase 2: Eval Blindspots（盲點記錄）
    # ══════════════════════════════════════════════

    def load_eval_blindspots(self) -> List[Dict[str, Any]]:
        """載入盲點記錄."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT blindspot_json FROM eval_blindspots ORDER BY created_at",
        ).fetchall()
        result = []
        for r in rows:
            try:
                result.append(json.loads(r["blindspot_json"]))
            except json.JSONDecodeError:
                logger.warning("eval_blindspots JSON 解析失敗")
        return result

    def save_eval_blindspots(self, blindspots: List[Dict[str, Any]]) -> None:
        """儲存盲點記錄（全量覆寫）."""
        conn = self._get_conn()
        conn.execute("DELETE FROM eval_blindspots")
        now = datetime.now(TZ8).isoformat()
        for bs in blindspots:
            bs_id = bs.get("id", str(uuid.uuid4()))
            conn.execute(
                "INSERT INTO eval_blindspots (id, blindspot_json, created_at) "
                "VALUES (?, ?, ?)",
                (bs_id, json.dumps(bs, ensure_ascii=False), now),
            )
        conn.commit()

    # ══════════════════════════════════════════════
    # Phase 2: Eval Alerts（品質警報）
    # ══════════════════════════════════════════════

    def load_eval_alerts(self) -> List[Dict[str, Any]]:
        """載入警報記錄."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM eval_alerts ORDER BY created_at",
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.pop("details_json", "{}"))
            except json.JSONDecodeError:
                d["details"] = {}
            result.append(d)
        return result

    def save_eval_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        """儲存警報記錄（全量覆寫）."""
        conn = self._get_conn()
        conn.execute("DELETE FROM eval_alerts")
        now = datetime.now(TZ8).isoformat()
        for alert in alerts:
            alert_id = alert.get("id", str(uuid.uuid4()))
            conn.execute(
                "INSERT INTO eval_alerts "
                "(id, alert_type, severity, message, details_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    alert_id,
                    alert.get("alert_type", "unknown"),
                    alert.get("severity", "medium"),
                    alert.get("message", ""),
                    json.dumps(alert.get("details", {}), ensure_ascii=False),
                    alert.get("timestamp", alert.get("created_at", now)),
                ),
            )
        conn.commit()

    def append_eval_alert(self, alert: Dict[str, Any]) -> None:
        """追加一筆警報."""
        conn = self._get_conn()
        now = datetime.now(TZ8).isoformat()
        alert_id = alert.get("id", str(uuid.uuid4()))
        conn.execute(
            "INSERT OR REPLACE INTO eval_alerts "
            "(id, alert_type, severity, message, details_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                alert_id,
                alert.get("alert_type", "unknown"),
                alert.get("severity", "medium"),
                alert.get("message", ""),
                json.dumps(alert.get("details", {}), ensure_ascii=False),
                alert.get("timestamp", alert.get("created_at", now)),
            ),
        )
        conn.commit()

    # ══════════════════════════════════════════════
    # Phase 2: JSON → SQLite 遷移工具
    # ══════════════════════════════════════════════

    def migrate_ceremony_from_json(self, json_path: Path) -> bool:
        """從 ceremony_state.json 遷移到 SQLite."""
        if not json_path.exists():
            return False
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.save_ceremony_state(state)
            logger.info(f"ceremony_state 遷移完成: {len(state)} 筆 key-value")
            return True
        except Exception as e:
            logger.error(f"ceremony_state 遷移失敗: {e}")
            return False

    def migrate_eval_from_json(self, eval_dir: Path) -> Dict[str, str]:
        """從 eval/ JSON 檔案遷移到 SQLite."""
        results = {}

        # ab_baselines.json
        ab_path = eval_dir / "ab_baselines.json"
        if ab_path.exists():
            try:
                with open(ab_path, "r", encoding="utf-8") as f:
                    baselines = json.load(f)
                for cid, bl in baselines.items():
                    self.save_eval_baseline(cid, bl)
                results["ab_baselines"] = f"ok ({len(baselines)} 筆)"
            except Exception as e:
                results["ab_baselines"] = f"error: {e}"
        else:
            results["ab_baselines"] = "not_found"

        # blindspots.json
        bs_path = eval_dir / "blindspots.json"
        if bs_path.exists():
            try:
                with open(bs_path, "r", encoding="utf-8") as f:
                    blindspots = json.load(f)
                self.save_eval_blindspots(blindspots)
                results["blindspots"] = f"ok ({len(blindspots)} 筆)"
            except Exception as e:
                results["blindspots"] = f"error: {e}"
        else:
            results["blindspots"] = "not_found"

        # alerts.json
        alerts_path = eval_dir / "alerts.json"
        if alerts_path.exists():
            try:
                with open(alerts_path, "r", encoding="utf-8") as f:
                    alerts = json.load(f)
                self.save_eval_alerts(alerts)
                results["alerts"] = f"ok ({len(alerts)} 筆)"
            except Exception as e:
                results["alerts"] = f"error: {e}"
        else:
            results["alerts"] = "not_found"

        logger.info(f"eval JSON 遷移結果: {results}")
        return results


# ══════════════════════════════════════════════════
# Singleton Factory — 全系統共用一個 PulseDB 連線
# ══════════════════════════════════════════════════
# 解決 11 個檔案各自 PulseDB() 造成的 DB locked / malformed 問題

_pulse_db_instances: Dict[str, "PulseDB"] = {}
_pulse_db_lock = threading.Lock()


def get_pulse_db(data_dir: Optional[Path] = None) -> "PulseDB":
    """取得 PulseDB 單例.

    全系統應使用此函數取得 PulseDB，而非直接 PulseDB()。
    同一個 db_path 只會建立一個 PulseDB 實例。

    Args:
        data_dir: 資料目錄（包含 pulse/ 子目錄的父目錄）
                  如果為 None，使用預設路徑 ~/MUSEON/data

    Returns:
        PulseDB 單例

    Example:
        from museon.pulse.pulse_db import get_pulse_db
        db = get_pulse_db(self.data_dir)
        db.log_exploration(...)
    """
    if data_dir is None:
        data_dir = Path.home() / "MUSEON" / "data"
    data_dir = Path(data_dir)
    db_path = str(data_dir / "pulse" / "pulse.db")

    with _pulse_db_lock:
        if db_path not in _pulse_db_instances:
            _pulse_db_instances[db_path] = PulseDB(db_path)
            logger.info(f"PulseDB singleton created: {db_path}")
        return _pulse_db_instances[db_path]
