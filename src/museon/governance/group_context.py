"""Group context manager for Telegram group interactions.

Provides:
- GroupContextStore: SQLite-based structured storage for group messages,
  client profiles, and group metadata.
- Loads recent group context when bot is @mentioned so it can follow
  the conversation intelligently.

Database schema:
  groups      — group_id (PK), title, type, joined_at, settings
  clients     — user_id (PK), display_name, username, first_seen, last_seen, interaction_count
  group_members — group_id + user_id (PK), role, joined_at
  messages    — id (auto), group_id, user_id, message_id, text, msg_type, created_at
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.core.data_bus import DataContract, StoreSpec, StoreEngine, TTLTier

logger = logging.getLogger(__name__)


class GroupContextStore(DataContract):
    """SQLite-backed structured storage for group conversations and client data."""

    @classmethod
    def store_spec(cls) -> StoreSpec:
        return StoreSpec(
            name="group_context_store",
            engine=StoreEngine.SQLITE,
            ttl=TTLTier.PERMANENT,
            description="Telegram 群組上下文 SQLite 儲存",
            tables=["groups", "clients", "group_members", "messages", "entity_aliases", "projects", "project_entities", "events"],
        )

    def health_check(self) -> Dict[str, Any]:
        try:
            conn = self._get_conn()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            ok = integrity and integrity[0] == "ok"
            msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            size = self.db_path.stat().st_size if self.db_path.exists() else 0
            return {
                "status": "ok" if ok else "degraded",
                "integrity": integrity[0] if integrity else "unknown",
                "messages": msg_count,
                "size_bytes": size,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def __init__(self, data_dir: Path):
        self.db_path = data_dir / "_system" / "group_context.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=10)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id    INTEGER PRIMARY KEY,
                title       TEXT,
                type        TEXT DEFAULT 'supergroup',
                joined_at   TEXT DEFAULT (datetime('now')),
                settings    TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS clients (
                user_id     TEXT PRIMARY KEY,
                display_name TEXT,
                username    TEXT,
                first_seen  TEXT DEFAULT (datetime('now')),
                last_seen   TEXT DEFAULT (datetime('now')),
                interaction_count INTEGER DEFAULT 0,
                notes       TEXT DEFAULT '',
                personality_notes TEXT DEFAULT '',
                communication_style TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS group_members (
                group_id    INTEGER,
                user_id     TEXT,
                role        TEXT DEFAULT 'member',
                joined_at   TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (group_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id    INTEGER NOT NULL,
                user_id     TEXT NOT NULL,
                message_id  INTEGER,
                text        TEXT,
                msg_type    TEXT DEFAULT 'text',
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_messages_group_time
                ON messages(group_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_messages_user
                ON messages(user_id, created_at);

            CREATE TABLE IF NOT EXISTS entity_aliases (
                alias       TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'telegram_uid',
                entity_id   TEXT NOT NULL,
                created_by  TEXT DEFAULT 'auto',
                created_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (alias, entity_type, entity_id)
            );
            CREATE INDEX IF NOT EXISTS idx_aliases_alias ON entity_aliases(alias COLLATE NOCASE);

            CREATE TABLE IF NOT EXISTS projects (
                project_id  TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT DEFAULT '',
                status      TEXT DEFAULT 'active',
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS project_entities (
                project_id  TEXT NOT NULL,
                entity_type TEXT NOT NULL DEFAULT 'telegram_uid',
                entity_id   TEXT NOT NULL,
                role        TEXT DEFAULT 'member',
                added_at    TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (project_id, entity_type, entity_id)
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id    TEXT PRIMARY KEY,
                entity_type TEXT,
                entity_id   TEXT,
                project_id  TEXT,
                event_type  TEXT NOT NULL,
                summary     TEXT NOT NULL,
                source      TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_type, entity_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, created_at);
        """)
        conn.commit()

        # Schema migration: add new columns to existing DB
        try:
            conn.execute("ALTER TABLE clients ADD COLUMN personality_notes TEXT DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE clients ADD COLUMN communication_style TEXT DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists

    # ── Group management ──

    def upsert_group(self, group_id: int, title: str = "", chat_type: str = "supergroup") -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO groups (group_id, title, type)
               VALUES (?, ?, ?)
               ON CONFLICT(group_id) DO UPDATE SET
                 title = COALESCE(NULLIF(excluded.title, ''), groups.title),
                 type = excluded.type""",
            (group_id, title, chat_type),
        )
        conn.commit()

    # ── Client management ──

    def upsert_client(self, user_id: str, display_name: str = "", username: str = "") -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO clients (user_id, display_name, username, interaction_count)
               VALUES (?, ?, ?, 1)
               ON CONFLICT(user_id) DO UPDATE SET
                 display_name = COALESCE(NULLIF(excluded.display_name, ''), clients.display_name),
                 username = COALESCE(NULLIF(excluded.username, ''), clients.username),
                 last_seen = datetime('now'),
                 interaction_count = clients.interaction_count + 1""",
            (user_id, display_name, username),
        )
        conn.commit()

    def upsert_group_member(self, group_id: int, user_id: str, role: str = "member") -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO group_members (group_id, user_id, role)
               VALUES (?, ?, ?)
               ON CONFLICT(group_id, user_id) DO UPDATE SET role = excluded.role""",
            (group_id, user_id, role),
        )
        conn.commit()

    # ── Message recording ──

    def record_message(
        self,
        group_id: int,
        user_id: str,
        text: str,
        message_id: int = 0,
        msg_type: str = "text",
        display_name: str = "",
        username: str = "",
    ) -> None:
        """Record a message (group or DM) and update client profile.

        group_id: Telegram chat_id (negative for groups, positive for DMs).
        """
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO messages (group_id, user_id, message_id, text, msg_type)
               VALUES (?, ?, ?, ?, ?)""",
            (group_id, user_id, message_id, text[:8000], msg_type),
        )
        conn.commit()

        # Update client and membership (fire-and-forget)
        try:
            self.upsert_client(user_id, display_name, username)
            self.upsert_group_member(group_id, user_id)
        except Exception as e:
            logger.debug(f"Client upsert error (non-critical): {e}")

    # ── Context retrieval ──

    def get_recent_context(self, group_id: int, limit: int = 30) -> List[Dict[str, Any]]:
        """Get recent messages from a group for context injection.

        Returns list of dicts with: user_id, display_name, text, created_at
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT m.user_id, c.display_name, m.text, m.created_at, m.msg_type
               FROM messages m
               LEFT JOIN clients c ON m.user_id = c.user_id
               WHERE m.group_id = ?
               ORDER BY m.created_at DESC
               LIMIT ?""",
            (group_id, limit),
        ).fetchall()
        # Return in chronological order
        return [
            {
                "user_id": r["user_id"],
                "name": r["display_name"] or r["user_id"],
                "text": r["text"],
                "time": r["created_at"],
                "type": r["msg_type"],
            }
            for r in reversed(rows)
        ]

    def format_context_for_prompt(
        self,
        group_id: int,
        limit: int = 20,
        owner_ids: Optional[set] = None,
        boss_name: str = "",
    ) -> str:
        """Format recent group messages as a context string for LLM prompt.

        Args:
            owner_ids: set of user_id strings that belong to the owner/boss.
                       Their messages will be tagged with boss_name.
            boss_name: the owner's known name (from ANIMA_MC boss.name).
        """
        messages = self.get_recent_context(group_id, limit)
        if not messages:
            return ""

        lines = ["[群組近期對話紀錄]"]
        for msg in messages:
            time_short = msg["time"].split("T")[-1][:5] if "T" in msg["time"] else msg["time"][-5:]
            # Tag owner messages so Brain recognizes the boss
            if owner_ids and msg.get("user_id") in owner_ids:
                display = boss_name or msg["name"]
                lines.append(f"  {time_short} {display}（老闆）: {msg['text'][:200]}")
            else:
                lines.append(f"  {time_short} {msg['name']}: {msg['text'][:200]}")
        lines.append("[/群組近期對話紀錄]")
        return "\n".join(lines)

    def get_client_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a client's profile data."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM clients WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None

    # ── Digest Service support ──

    def get_messages_since(self, group_id: int, since: str, limit: int = 200) -> List[Dict[str, Any]]:
        """取得某群組從某時間點之後的所有訊息.

        Args:
            group_id: 群組 ID（含負號）
            since: ISO 8601 時間字串（如 '2026-03-27T10:00:00'）
            limit: 最大筆數

        Returns:
            [{user_id, name, text, time, type}, ...]
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT m.user_id, c.display_name, m.text, m.created_at, m.msg_type "
            "FROM messages m LEFT JOIN clients c ON m.user_id = c.user_id "
            "WHERE m.group_id = ? AND m.created_at > ? "
            "ORDER BY m.created_at ASC LIMIT ?",
            (group_id, since, limit),
        ).fetchall()
        return [
            {"user_id": r["user_id"], "name": r["display_name"] or "Unknown", "text": r["text"], "time": r["created_at"], "type": r["msg_type"]}
            for r in rows
        ]

    def get_group_setting(self, group_id: int, key: str, default: Any = None) -> Any:
        """讀取群組設定（從 groups.settings JSON 欄位）."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT settings FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        if not row or not row["settings"]:
            return default
        try:
            settings = json.loads(row["settings"])
            return settings.get(key, default)
        except (json.JSONDecodeError, TypeError):
            return default

    def set_group_setting(self, group_id: int, key: str, value: Any) -> None:
        """寫入群組設定."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT settings FROM groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        settings: Dict[str, Any] = {}
        if row and row["settings"]:
            try:
                settings = json.loads(row["settings"])
            except (json.JSONDecodeError, TypeError):
                settings = {}
        settings[key] = value
        conn.execute(
            "UPDATE groups SET settings = ? WHERE group_id = ?",
            (json.dumps(settings, ensure_ascii=False), group_id),
        )
        conn.commit()

    def get_groups_with_owner(self, owner_user_id: str) -> List[Dict[str, Any]]:
        """取得某使用者所在的所有群組."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT g.group_id, g.title FROM groups g "
            "JOIN group_members gm ON g.group_id = gm.group_id "
            "WHERE gm.user_id = ?",
            (owner_user_id,),
        ).fetchall()
        return [{"group_id": r["group_id"], "title": r["title"] or ""} for r in rows]

    def get_group_members(self, group_id: int) -> List[Dict[str, Any]]:
        """Get all known members of a group."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT gm.user_id, gm.role, c.display_name, c.username,
                      c.interaction_count, c.last_seen
               FROM group_members gm
               LEFT JOIN clients c ON gm.user_id = c.user_id
               WHERE gm.group_id = ?
               ORDER BY c.last_seen DESC""",
            (group_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Entity Alias management ──

    def add_alias(self, alias: str, entity_id: str, entity_type: str = "telegram_uid", created_by: str = "manual") -> None:
        """新增人物別名映射."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO entity_aliases (alias, entity_type, entity_id, created_by)
               VALUES (?, ?, ?, ?)""",
            (alias, entity_type, entity_id, created_by),
        )
        conn.commit()

    def remove_alias(self, alias: str, entity_id: str, entity_type: str = "telegram_uid") -> None:
        """移除人物別名映射."""
        conn = self._get_conn()
        conn.execute(
            "DELETE FROM entity_aliases WHERE alias = ? AND entity_type = ? AND entity_id = ?",
            (alias, entity_type, entity_id),
        )
        conn.commit()

    def resolve_alias(self, keyword: str) -> List[Dict[str, Any]]:
        """根據關鍵字查找所有匹配的 entity（case-insensitive）."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT alias, entity_type, entity_id, created_by
               FROM entity_aliases WHERE alias LIKE ? COLLATE NOCASE""",
            (f"%{keyword}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_aliases(self, entity_id: str, entity_type: str = "telegram_uid") -> List[str]:
        """列出某個 entity 的所有別名."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT alias FROM entity_aliases WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        ).fetchall()
        return [r["alias"] for r in rows]

    # ── Project management ──

    def create_project(self, project_id: str, name: str, description: str = "") -> None:
        """建立新專案."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO projects (project_id, name, description)
               VALUES (?, ?, ?)""",
            (project_id, name, description),
        )
        conn.commit()

    def add_entity_to_project(self, project_id: str, entity_id: str, entity_type: str = "telegram_uid", role: str = "member") -> None:
        """將 entity 加入專案."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO project_entities (project_id, entity_type, entity_id, role)
               VALUES (?, ?, ?, ?)""",
            (project_id, entity_type, entity_id, role),
        )
        conn.commit()

    def get_project_entities(self, project_id: str) -> List[Dict[str, Any]]:
        """取得專案中的所有 entity."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT entity_type, entity_id, role, added_at FROM project_entities WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_entity_projects(self, entity_id: str, entity_type: str = "telegram_uid") -> List[Dict[str, Any]]:
        """取得某 entity 參與的所有專案."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT p.project_id, p.name, p.status, pe.role
               FROM projects p JOIN project_entities pe ON p.project_id = pe.project_id
               WHERE pe.entity_type = ? AND pe.entity_id = ?""",
            (entity_type, entity_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Event tracking ──

    def add_event(self, event_id: str, event_type: str, summary: str,
                  entity_type: str = "", entity_id: str = "",
                  project_id: str = "", source: str = "") -> None:
        """追加事件記錄."""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO events (event_id, event_type, summary, entity_type, entity_id, project_id, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id, event_type, summary, entity_type, entity_id, project_id, source),
        )
        conn.commit()

    def get_entity_events(self, entity_id: str, entity_type: str = "telegram_uid", limit: int = 20) -> List[Dict[str, Any]]:
        """取得某 entity 的事件時間線."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT event_id, event_type, summary, project_id, source, created_at
               FROM events WHERE entity_type = ? AND entity_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (entity_type, entity_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_project_events(self, project_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """取得某專案的事件時間線."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT event_id, event_type, summary, entity_type, entity_id, source, created_at
               FROM events WHERE project_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (project_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ── Singleton ──
_store: Optional[GroupContextStore] = None


def get_group_context_store(data_dir: Optional[Path] = None) -> GroupContextStore:
    global _store
    if _store is None:
        if data_dir is None:
            import os
            data_dir = Path(os.environ.get("MUSEON_HOME", "/tmp")) / "data"
        _store = GroupContextStore(data_dir)
    return _store
