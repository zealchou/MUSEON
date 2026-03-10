"""Registry Schema — SQLite DDL + Migration 引擎.

職責：
- 定義 registry.db 的 7 張表（transactions, meetings, action_items,
  events, contacts, _categories, _migrations）
- 提供冪等 migration 機制（版本控制）
- 首次建立時自動灌入預設分類

設計原則：
- 使用 Python 內建 sqlite3（零依賴）
- 所有操作 try/except 包裝，不拋異常
- migration 冪等：已套用的版本不重複執行
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from museon.registry.category_presets import get_all_presets

logger = logging.getLogger(__name__)

# 當前 schema 版本
CURRENT_VERSION = 1


# ═══════════════════════════════════════════
# DDL 定義
# ═══════════════════════════════════════════

MIGRATION_V1 = """
-- Migration v1: Initial schema
-- 7 tables: transactions, meetings, action_items, events, contacts, _categories, _migrations

-- ── _migrations（版本控制）──
CREATE TABLE IF NOT EXISTS _migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

-- ── _categories（分類體系）──
CREATE TABLE IF NOT EXISTS _categories (
    category_id TEXT PRIMARY KEY,
    parent_id   TEXT NOT NULL DEFAULT '',
    name_zh     TEXT NOT NULL,
    name_en     TEXT NOT NULL DEFAULT '',
    is_system   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── transactions（交易記錄）──
CREATE TABLE IF NOT EXISTS transactions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    amount          REAL NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'TWD',
    category        TEXT NOT NULL DEFAULT 'expense.other',
    counterparty    TEXT NOT NULL DEFAULT '',
    description     TEXT NOT NULL DEFAULT '',
    note            TEXT NOT NULL DEFAULT '',
    transaction_date TEXT NOT NULL DEFAULT (date('now')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    source          TEXT NOT NULL DEFAULT 'manual',
    tags            TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (category) REFERENCES _categories(category_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);

-- ── meetings（會議記錄）──
CREATE TABLE IF NOT EXISTS meetings (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    file_path   TEXT NOT NULL DEFAULT '',
    meeting_date TEXT NOT NULL DEFAULT (date('now')),
    duration_min INTEGER NOT NULL DEFAULT 0,
    participants TEXT NOT NULL DEFAULT '[]',
    tags        TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    source      TEXT NOT NULL DEFAULT 'manual'
);

CREATE INDEX IF NOT EXISTS idx_meetings_user ON meetings(user_id);
CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(meeting_date);

-- ── action_items（待辦事項）──
CREATE TABLE IF NOT EXISTS action_items (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    meeting_id  TEXT,
    task        TEXT NOT NULL,
    assignee    TEXT NOT NULL DEFAULT '',
    due_date    TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    priority    INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (meeting_id) REFERENCES meetings(id)
);

CREATE INDEX IF NOT EXISTS idx_action_items_user ON action_items(user_id);
CREATE INDEX IF NOT EXISTS idx_action_items_status ON action_items(status);
CREATE INDEX IF NOT EXISTS idx_action_items_due ON action_items(due_date);

-- ── events（行程事件）──
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    location        TEXT NOT NULL DEFAULT '',
    datetime_start  TEXT NOT NULL,
    datetime_end    TEXT,
    timezone        TEXT NOT NULL DEFAULT 'Asia/Taipei',
    status          TEXT NOT NULL DEFAULT 'upcoming',
    recurrence      TEXT NOT NULL DEFAULT '',
    reminder_minutes INTEGER NOT NULL DEFAULT 30,
    reminder_sent   INTEGER NOT NULL DEFAULT 0,
    tags            TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(datetime_start);
CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);

-- ── contacts（聯絡人）──
CREATE TABLE IF NOT EXISTS contacts (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    phone       TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    company     TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL DEFAULT '',
    birthday    TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id);
CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name);
"""


# ═══════════════════════════════════════════
# Migration 引擎
# ═══════════════════════════════════════════

class RegistrySchema:
    """SQLite schema 管理與 migration 引擎."""

    def __init__(self, db_path: str):
        """初始化 schema 管理器.

        Args:
            db_path: registry.db 的完整路徑
        """
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self) -> str:
        return str(self._db_path)

    def initialize(self) -> bool:
        """初始化 registry.db — 建立 schema + 灌入預設分類.

        冪等：已存在的表不會重建，已套用的 migration 不重複執行。

        Returns:
            True if success, False otherwise.
        """
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")

            current_version = self._get_version(conn)

            if current_version < 1:
                logger.info("Applying registry migration v1...")
                conn.executescript(MIGRATION_V1)
                self._set_version(conn, 1, "Initial schema — 7 tables")
                self._seed_categories(conn)
                conn.commit()
                logger.info("Registry schema v1 applied successfully")
            else:
                logger.debug(
                    f"Registry schema already at v{current_version}, "
                    "skipping migration"
                )

            conn.close()
            return True

        except Exception as e:
            logger.error(f"Registry schema init failed: {e}")
            return False

    def get_version(self) -> int:
        """取得當前 migration 版本.

        Returns:
            版本號，若無法讀取回傳 0。
        """
        try:
            conn = sqlite3.connect(str(self._db_path))
            version = self._get_version(conn)
            conn.close()
            return version
        except Exception:
            return 0

    def get_table_names(self) -> list:
        """取得所有表名.

        Returns:
            表名列表。
        """
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            return tables
        except Exception:
            return []

    def verify_integrity(self) -> bool:
        """驗證 SQLite 完整性.

        Returns:
            True if integrity check passes.
        """
        try:
            conn = sqlite3.connect(str(self._db_path))
            result = conn.execute("PRAGMA integrity_check").fetchone()
            conn.close()
            return result[0] == "ok"
        except Exception:
            return False

    # ── 私有方法 ──

    def _get_version(self, conn: sqlite3.Connection) -> int:
        """從 _migrations 表取得最新版本."""
        try:
            cursor = conn.execute(
                "SELECT MAX(version) FROM _migrations"
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
        except sqlite3.OperationalError:
            # _migrations 表不存在
            return 0

    def _set_version(
        self,
        conn: sqlite3.Connection,
        version: int,
        description: str = "",
    ) -> None:
        """記錄 migration 版本."""
        conn.execute(
            "INSERT OR IGNORE INTO _migrations (version, description) "
            "VALUES (?, ?)",
            (version, description),
        )

    def _seed_categories(self, conn: sqlite3.Connection) -> None:
        """灌入系統預設分類."""
        presets = get_all_presets()
        for cat_id, parent_id, name_zh, name_en in presets:
            conn.execute(
                "INSERT OR IGNORE INTO _categories "
                "(category_id, parent_id, name_zh, name_en, is_system) "
                "VALUES (?, ?, ?, ?, 1)",
                (cat_id, parent_id, name_zh, name_en),
            )
        logger.info(f"Seeded {len(presets)} preset categories")
