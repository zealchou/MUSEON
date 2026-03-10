"""Registry Manager — 結構化資料層統一門面.

職責：
- 初始化 registry.db（含 migration）
- 建立 vault/、inbox/ 目錄結構
- CRUD 路由（精確查詢走 SQLite，語義查詢走 Qdrant）
- Graceful Degradation（Qdrant 不可用不影響 SQLite 寫入）
- Pending index queue（Qdrant 恢復後自動補索引）

設計原則：
- Lazy Init：首次存取時才建立 SQLite 連線
- 所有操作 try/except 包裝
- 每個 user_id 獨立一份 registry.db
"""

import json
import logging
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from museon.registry.schema import RegistrySchema

logger = logging.getLogger(__name__)


class RegistryManager:
    """結構化資料層統一門面."""

    def __init__(
        self,
        data_dir: str,
        user_id: str = "cli_user",
    ):
        """初始化 RegistryManager.

        Args:
            data_dir: MUSEON 資料根目錄（通常是 data/）
            user_id: 使用者 ID（每個 user_id 獨立一份 DB）
        """
        self._data_dir = Path(data_dir)
        self._user_id = user_id
        self._conn: Optional[sqlite3.Connection] = None

        # 路徑定義
        self._registry_dir = self._data_dir / "registry" / user_id
        self._db_path = self._registry_dir / "registry.db"
        self._vault_dir = self._data_dir / "vault" / user_id
        self._inbox_dir = self._data_dir / "inbox"

        # Pending index queue（Qdrant 離線時暫存）
        self._pending_indexes: List[Dict[str, Any]] = []

        # Schema 管理器
        self._schema = RegistrySchema(str(self._db_path))

        # 初始化
        self._ensure_directories()
        self._schema.initialize()

    # ═══════════════════════════════════════
    # 初始化
    # ═══════════════════════════════════════

    def _ensure_directories(self) -> None:
        """確保所有必要目錄存在."""
        dirs = [
            self._registry_dir,
            self._vault_dir / "meetings",
            self._vault_dir / "receipts",
            self._vault_dir / "imports",
            self._inbox_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    # ═══════════════════════════════════════
    # 連線管理（Lazy Init）
    # ═══════════════════════════════════════

    def _get_conn(self) -> sqlite3.Connection:
        """Lazy 取得 SQLite 連線."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """關閉連線."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ═══════════════════════════════════════
    # 屬性
    # ═══════════════════════════════════════

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def db_path(self) -> str:
        return str(self._db_path)

    @property
    def registry_dir(self) -> str:
        return str(self._registry_dir)

    @property
    def vault_dir(self) -> str:
        return str(self._vault_dir)

    @property
    def inbox_dir(self) -> str:
        return str(self._inbox_dir)

    # ═══════════════════════════════════════
    # 分類操作
    # ═══════════════════════════════════════

    def list_categories(
        self,
        parent_id: Optional[str] = None,
        include_system: bool = True,
    ) -> List[Dict[str, Any]]:
        """列出分類.

        Args:
            parent_id: 篩選特定父分類下的子分類
            include_system: 是否包含系統預設分類

        Returns:
            分類列表
        """
        try:
            conn = self._get_conn()
            query = "SELECT * FROM _categories WHERE 1=1"
            params: list = []

            if parent_id is not None:
                query += " AND parent_id = ?"
                params.append(parent_id)

            if not include_system:
                query += " AND is_system = 0"

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"list_categories failed: {e}")
            return []

    def add_category(
        self,
        category_id: str,
        parent_id: str,
        name_zh: str,
        name_en: str = "",
    ) -> bool:
        """新增使用者自訂分類.

        Args:
            category_id: 分類 ID（如 expense.pets）
            parent_id: 父分類 ID（如 expense）
            name_zh: 中文名稱
            name_en: 英文名稱

        Returns:
            True if success.
        """
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO _categories "
                "(category_id, parent_id, name_zh, name_en, is_system) "
                "VALUES (?, ?, ?, ?, 0)",
                (category_id, parent_id, name_zh, name_en),
            )
            conn.commit()
            return True

        except Exception as e:
            logger.error(f"add_category failed: {e}")
            return False

    # ═══════════════════════════════════════
    # 交易 CRUD
    # ═══════════════════════════════════════

    def add_transaction(
        self,
        amount: float,
        category: str = "expense.other",
        currency: str = "TWD",
        counterparty: str = "",
        description: str = "",
        note: str = "",
        transaction_date: Optional[str] = None,
        source: str = "manual",
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """新增交易記錄.

        Args:
            amount: 金額（正數=收入，負數=支出）
            category: 分類 ID
            currency: 幣別
            counterparty: 交易對象
            description: 描述
            note: 備註
            transaction_date: 交易日期（YYYY-MM-DD）
            source: 來源（manual, telegram, voice）
            tags: 標籤

        Returns:
            交易 ID，失敗回傳 None。
        """
        try:
            conn = self._get_conn()
            tx_id = f"tx_{uuid.uuid4().hex[:12]}"
            now = datetime.utcnow().isoformat()

            if transaction_date is None:
                transaction_date = datetime.utcnow().strftime("%Y-%m-%d")

            import json
            tags_json = json.dumps(tags or [], ensure_ascii=False)

            conn.execute(
                "INSERT INTO transactions "
                "(id, user_id, amount, currency, category, counterparty, "
                "description, note, transaction_date, created_at, "
                "updated_at, source, tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tx_id, self._user_id, amount, currency, category,
                    counterparty, description, note, transaction_date,
                    now, now, source, tags_json,
                ),
            )
            conn.commit()

            # 排入 Qdrant pending index
            self._pending_indexes.append({
                "doc_type": "ledger",
                "source_id": tx_id,
                "text": f"{counterparty} {description} {note} {amount} {currency}",
                "metadata": {
                    "doc_type": "ledger",
                    "user_id": self._user_id,
                    "source_id": tx_id,
                    "created_at": int(datetime.utcnow().timestamp()),
                },
            })

            return tx_id

        except Exception as e:
            logger.error(f"add_transaction failed: {e}")
            return None

    def get_transaction(self, tx_id: str) -> Optional[Dict[str, Any]]:
        """取得單筆交易."""
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT * FROM transactions WHERE id = ? AND user_id = ?",
                (tx_id, self._user_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"get_transaction failed: {e}")
            return None

    def query_transactions(
        self,
        category_prefix: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查詢交易記錄.

        Args:
            category_prefix: 分類前綴篩選（如 expense.food）
            date_from: 起始日期（YYYY-MM-DD）
            date_to: 結束日期（YYYY-MM-DD）
            limit: 回傳上限

        Returns:
            交易列表
        """
        try:
            conn = self._get_conn()
            query = (
                "SELECT * FROM transactions WHERE user_id = ?"
            )
            params: list = [self._user_id]

            if category_prefix:
                query += " AND category LIKE ?"
                params.append(f"{category_prefix}%")

            if date_from:
                query += " AND transaction_date >= ?"
                params.append(date_from)

            if date_to:
                query += " AND transaction_date <= ?"
                params.append(date_to)

            query += " ORDER BY transaction_date DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"query_transactions failed: {e}")
            return []

    def sum_transactions(
        self,
        category_prefix: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> float:
        """加總交易金額.

        Args:
            category_prefix: 分類前綴篩選
            date_from: 起始日期
            date_to: 結束日期

        Returns:
            加總金額
        """
        try:
            conn = self._get_conn()
            query = (
                "SELECT COALESCE(SUM(amount), 0) FROM transactions "
                "WHERE user_id = ?"
            )
            params: list = [self._user_id]

            if category_prefix:
                query += " AND category LIKE ?"
                params.append(f"{category_prefix}%")

            if date_from:
                query += " AND transaction_date >= ?"
                params.append(date_from)

            if date_to:
                query += " AND transaction_date <= ?"
                params.append(date_to)

            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            return float(row[0]) if row else 0.0

        except Exception as e:
            logger.error(f"sum_transactions failed: {e}")
            return 0.0

    # ═══════════════════════════════════════
    # 會議 CRUD (Phase 3)
    # ═══════════════════════════════════════

    def add_meeting(
        self,
        title: str = "",
        summary: str = "",
        file_path: str = "",
        meeting_date: Optional[str] = None,
        duration_min: int = 0,
        participants: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        source: str = "manual",
    ) -> Optional[str]:
        """新增會議記錄.

        Args:
            title: 會議標題
            summary: 會議摘要
            file_path: 逐字稿檔案路徑
            meeting_date: 會議日期（YYYY-MM-DD）
            duration_min: 會議時長（分鐘）
            participants: 參與者列表
            tags: 標籤
            source: 來源（manual, telegram, whisper, zoom, meet）

        Returns:
            會議 ID
        """
        try:
            conn = self._get_conn()
            meeting_id = f"mtg_{uuid.uuid4().hex[:12]}"
            now = datetime.utcnow().isoformat()

            if meeting_date is None:
                meeting_date = datetime.utcnow().strftime("%Y-%m-%d")

            participants_json = json.dumps(
                participants or [], ensure_ascii=False
            )
            tags_json = json.dumps(tags or [], ensure_ascii=False)

            conn.execute(
                "INSERT INTO meetings "
                "(id, user_id, title, summary, file_path, meeting_date, "
                "duration_min, participants, tags, created_at, "
                "updated_at, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    meeting_id, self._user_id, title, summary,
                    file_path, meeting_date, duration_min,
                    participants_json, tags_json, now, now, source,
                ),
            )
            conn.commit()

            # Pending index
            self._pending_indexes.append({
                "doc_type": "meeting",
                "source_id": meeting_id,
                "text": f"{title} {summary}",
                "metadata": {
                    "doc_type": "meeting",
                    "user_id": self._user_id,
                    "source_id": meeting_id,
                    "created_at": int(datetime.utcnow().timestamp()),
                },
            })

            return meeting_id

        except Exception as e:
            logger.error(f"add_meeting failed: {e}")
            return None

    def get_meeting(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        """取得單筆會議."""
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT * FROM meetings WHERE id = ? AND user_id = ?",
                (meeting_id, self._user_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"get_meeting failed: {e}")
            return None

    def query_meetings(
        self,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查詢會議記錄."""
        try:
            conn = self._get_conn()
            query = "SELECT * FROM meetings WHERE user_id = ?"
            params: list = [self._user_id]

            if date_from:
                query += " AND meeting_date >= ?"
                params.append(date_from)
            if date_to:
                query += " AND meeting_date <= ?"
                params.append(date_to)
            if keyword:
                query += " AND (title LIKE ? OR summary LIKE ?)"
                params.extend([f"%{keyword}%", f"%{keyword}%"])

            query += " ORDER BY meeting_date DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"query_meetings failed: {e}")
            return []

    def store_meeting_file(
        self,
        source_path: str,
        meeting_id: Optional[str] = None,
    ) -> Optional[str]:
        """將會議檔案複製到 vault/meetings/.

        Args:
            source_path: 來源檔案路徑
            meeting_id: 關聯的會議 ID（可選）

        Returns:
            vault 中的檔案路徑
        """
        try:
            src = Path(source_path)
            if not src.exists():
                return None

            dest_dir = self._vault_dir / "meetings"
            dest_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            dest_name = f"{timestamp}_{src.name}"
            dest = dest_dir / dest_name

            shutil.copy2(str(src), str(dest))
            return str(dest)

        except Exception as e:
            logger.error(f"store_meeting_file failed: {e}")
            return None

    # ═══════════════════════════════════════
    # Action Items CRUD (Phase 3)
    # ═══════════════════════════════════════

    def add_action_item(
        self,
        task: str,
        meeting_id: Optional[str] = None,
        assignee: str = "",
        due_date: Optional[str] = None,
        priority: int = 0,
    ) -> Optional[str]:
        """新增待辦事項.

        Args:
            task: 任務描述
            meeting_id: 來源會議 ID
            assignee: 負責人
            due_date: 到期日（YYYY-MM-DD）
            priority: 優先度（0=normal, 1=high, 2=urgent）

        Returns:
            待辦事項 ID
        """
        try:
            conn = self._get_conn()
            item_id = f"ai_{uuid.uuid4().hex[:12]}"
            now = datetime.utcnow().isoformat()

            conn.execute(
                "INSERT INTO action_items "
                "(id, user_id, meeting_id, task, assignee, due_date, "
                "status, priority, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
                (
                    item_id, self._user_id, meeting_id, task,
                    assignee, due_date, priority, now, now,
                ),
            )
            conn.commit()
            return item_id

        except Exception as e:
            logger.error(f"add_action_item failed: {e}")
            return None

    def get_action_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """取得單筆待辦事項."""
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT * FROM action_items WHERE id = ? AND user_id = ?",
                (item_id, self._user_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"get_action_item failed: {e}")
            return None

    def update_action_item_status(
        self,
        item_id: str,
        status: str,
    ) -> bool:
        """更新待辦事項狀態.

        Args:
            item_id: 待辦事項 ID
            status: 新狀態（pending, in_progress, done, cancelled）

        Returns:
            True if success.
        """
        try:
            conn = self._get_conn()
            now = datetime.utcnow().isoformat()

            update_fields = "status = ?, updated_at = ?"
            params: list = [status, now]

            if status == "done":
                update_fields += ", completed_at = ?"
                params.append(now)

            params.extend([item_id, self._user_id])

            conn.execute(
                f"UPDATE action_items SET {update_fields} "
                "WHERE id = ? AND user_id = ?",
                params,
            )
            conn.commit()
            return conn.total_changes > 0

        except Exception as e:
            logger.error(f"update_action_item_status failed: {e}")
            return False

    def query_action_items(
        self,
        status: Optional[str] = None,
        meeting_id: Optional[str] = None,
        assignee: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查詢待辦事項."""
        try:
            conn = self._get_conn()
            query = "SELECT * FROM action_items WHERE user_id = ?"
            params: list = [self._user_id]

            if status:
                query += " AND status = ?"
                params.append(status)
            if meeting_id:
                query += " AND meeting_id = ?"
                params.append(meeting_id)
            if assignee:
                query += " AND assignee LIKE ?"
                params.append(f"%{assignee}%")

            query += " ORDER BY due_date ASC NULLS LAST LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"query_action_items failed: {e}")
            return []

    # ═══════════════════════════════════════
    # 行程 CRUD (Phase 4)
    # ═══════════════════════════════════════

    def add_event(
        self,
        title: str,
        datetime_start: str,
        datetime_end: Optional[str] = None,
        description: str = "",
        location: str = "",
        timezone: str = "Asia/Taipei",
        recurrence: str = "",
        reminder_minutes: int = 30,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """新增行程事件.

        Args:
            title: 事件標題
            datetime_start: 開始時間（ISO 8601 UTC）
            datetime_end: 結束時間（ISO 8601 UTC）
            description: 描述
            location: 地點
            timezone: 時區（IANA 格式）
            recurrence: 重複規則（RRULE 格式）
            reminder_minutes: 提前提醒分鐘數
            tags: 標籤

        Returns:
            事件 ID
        """
        try:
            conn = self._get_conn()
            event_id = f"evt_{uuid.uuid4().hex[:12]}"
            now = datetime.utcnow().isoformat()
            tags_json = json.dumps(tags or [], ensure_ascii=False)

            conn.execute(
                "INSERT INTO events "
                "(id, user_id, title, description, location, "
                "datetime_start, datetime_end, timezone, status, "
                "recurrence, reminder_minutes, reminder_sent, "
                "tags, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'upcoming', "
                "?, ?, 0, ?, ?, ?)",
                (
                    event_id, self._user_id, title, description,
                    location, datetime_start, datetime_end, timezone,
                    recurrence, reminder_minutes,
                    tags_json, now, now,
                ),
            )
            conn.commit()

            # Pending index
            self._pending_indexes.append({
                "doc_type": "event",
                "source_id": event_id,
                "text": f"{title} {description} {location}",
                "metadata": {
                    "doc_type": "event",
                    "user_id": self._user_id,
                    "source_id": event_id,
                    "created_at": int(datetime.utcnow().timestamp()),
                },
            })

            return event_id

        except Exception as e:
            logger.error(f"add_event failed: {e}")
            return None

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """取得單筆行程."""
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT * FROM events WHERE id = ? AND user_id = ?",
                (event_id, self._user_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"get_event failed: {e}")
            return None

    def update_event_status(
        self,
        event_id: str,
        status: str,
    ) -> bool:
        """更新行程狀態.

        Args:
            event_id: 事件 ID
            status: 新狀態（upcoming, cancelled, completed）
        """
        try:
            conn = self._get_conn()
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE events SET status = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (status, now, event_id, self._user_id),
            )
            conn.commit()
            return conn.total_changes > 0

        except Exception as e:
            logger.error(f"update_event_status failed: {e}")
            return False

    def mark_reminder_sent(self, event_id: str) -> bool:
        """標記提醒已發送."""
        try:
            conn = self._get_conn()
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE events SET reminder_sent = 1, updated_at = ? "
                "WHERE id = ? AND user_id = ?",
                (now, event_id, self._user_id),
            )
            conn.commit()
            return True

        except Exception as e:
            logger.error(f"mark_reminder_sent failed: {e}")
            return False

    def query_events(
        self,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查詢行程事件."""
        try:
            conn = self._get_conn()
            query = "SELECT * FROM events WHERE user_id = ?"
            params: list = [self._user_id]

            if status:
                query += " AND status = ?"
                params.append(status)
            if date_from:
                query += " AND datetime_start >= ?"
                params.append(date_from)
            if date_to:
                query += " AND datetime_start <= ?"
                params.append(date_to)

            query += " ORDER BY datetime_start ASC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"query_events failed: {e}")
            return []

    def get_upcoming_reminders(
        self,
        within_minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """取得即將到來且尚未提醒的行程.

        Args:
            within_minutes: 多少分鐘內的行程

        Returns:
            需要提醒的行程列表
        """
        try:
            conn = self._get_conn()
            now = datetime.utcnow().isoformat()
            future = (
                datetime.utcnow() + timedelta(minutes=within_minutes)
            ).isoformat()

            cursor = conn.execute(
                "SELECT * FROM events "
                "WHERE user_id = ? "
                "AND status = 'upcoming' "
                "AND reminder_sent = 0 "
                "AND datetime_start <= ? "
                "AND datetime_start >= ? "
                "ORDER BY datetime_start ASC",
                (self._user_id, future, now),
            )
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"get_upcoming_reminders failed: {e}")
            return []

    # ═══════════════════════════════════════
    # 聯絡人 CRUD (Phase 5)
    # ═══════════════════════════════════════

    def add_contact(
        self,
        name: str,
        phone: str = "",
        email: str = "",
        company: str = "",
        title: str = "",
        birthday: str = "",
        note: str = "",
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """新增聯絡人.

        Args:
            name: 姓名
            phone: 電話
            email: 電子郵件
            company: 公司
            title: 職稱
            birthday: 生日（MM-DD 或 YYYY-MM-DD）
            note: 備註
            tags: 標籤

        Returns:
            聯絡人 ID
        """
        try:
            conn = self._get_conn()
            contact_id = f"ct_{uuid.uuid4().hex[:12]}"
            now = datetime.utcnow().isoformat()
            tags_json = json.dumps(tags or [], ensure_ascii=False)

            conn.execute(
                "INSERT INTO contacts "
                "(id, user_id, name, phone, email, company, title, "
                "birthday, note, tags, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    contact_id, self._user_id, name, phone, email,
                    company, title, birthday, note,
                    tags_json, now, now,
                ),
            )
            conn.commit()

            # Pending index
            self._pending_indexes.append({
                "doc_type": "contact",
                "source_id": contact_id,
                "text": f"{name} {company} {title} {note}",
                "metadata": {
                    "doc_type": "contact",
                    "user_id": self._user_id,
                    "source_id": contact_id,
                    "created_at": int(datetime.utcnow().timestamp()),
                },
            })

            return contact_id

        except Exception as e:
            logger.error(f"add_contact failed: {e}")
            return None

    def get_contact(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """取得單筆聯絡人."""
        try:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT * FROM contacts WHERE id = ? AND user_id = ?",
                (contact_id, self._user_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"get_contact failed: {e}")
            return None

    def query_contacts(
        self,
        keyword: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """查詢聯絡人.

        Args:
            keyword: 搜尋關鍵字（姓名、公司、備註）
            limit: 回傳上限
        """
        try:
            conn = self._get_conn()
            query = "SELECT * FROM contacts WHERE user_id = ?"
            params: list = [self._user_id]

            if keyword:
                query += (
                    " AND (name LIKE ? OR company LIKE ? "
                    "OR note LIKE ? OR phone LIKE ?)"
                )
                kw = f"%{keyword}%"
                params.extend([kw, kw, kw, kw])

            query += " ORDER BY name ASC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"query_contacts failed: {e}")
            return []

    def find_contact_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """依姓名模糊搜尋聯絡人（回傳第一筆）."""
        results = self.query_contacts(keyword=name, limit=1)
        return results[0] if results else None

    # ═══════════════════════════════════════
    # 跨類型搜尋 (Phase 5)
    # ═══════════════════════════════════════

    def search_all(
        self,
        keyword: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """跨類型 SQLite LIKE 搜尋（Qdrant 降級備案）.

        Args:
            keyword: 搜尋關鍵字
            limit: 回傳上限

        Returns:
            帶 _type 標記的結果列表
        """
        results: List[Dict[str, Any]] = []
        kw = f"%{keyword}%"

        try:
            conn = self._get_conn()

            # 交易
            for row in conn.execute(
                "SELECT *, 'ledger' as _type FROM transactions "
                "WHERE user_id = ? AND "
                "(counterparty LIKE ? OR description LIKE ? OR note LIKE ?) "
                "LIMIT ?",
                (self._user_id, kw, kw, kw, limit),
            ):
                results.append(dict(row))

            # 會議
            for row in conn.execute(
                "SELECT *, 'meeting' as _type FROM meetings "
                "WHERE user_id = ? AND "
                "(title LIKE ? OR summary LIKE ?) LIMIT ?",
                (self._user_id, kw, kw, limit),
            ):
                results.append(dict(row))

            # 行程
            for row in conn.execute(
                "SELECT *, 'event' as _type FROM events "
                "WHERE user_id = ? AND "
                "(title LIKE ? OR description LIKE ? OR location LIKE ?) "
                "LIMIT ?",
                (self._user_id, kw, kw, kw, limit),
            ):
                results.append(dict(row))

            # 聯絡人
            for row in conn.execute(
                "SELECT *, 'contact' as _type FROM contacts "
                "WHERE user_id = ? AND "
                "(name LIKE ? OR company LIKE ? OR note LIKE ?) "
                "LIMIT ?",
                (self._user_id, kw, kw, kw, limit),
            ):
                results.append(dict(row))

        except Exception as e:
            logger.error(f"search_all failed: {e}")

        return results[:limit]

    # ═══════════════════════════════════════
    # 狀態查詢
    # ═══════════════════════════════════════

    def get_migration_version(self) -> int:
        """取得當前 migration 版本."""
        return self._schema.get_version()

    def get_table_names(self) -> list:
        """取得所有表名."""
        return self._schema.get_table_names()

    def get_category_count(self, system_only: bool = False) -> int:
        """取得分類數量.

        Args:
            system_only: 是否只計算系統預設分類

        Returns:
            分類數量
        """
        try:
            conn = self._get_conn()
            query = "SELECT COUNT(*) FROM _categories"
            if system_only:
                query += " WHERE is_system = 1"
            cursor = conn.execute(query)
            row = cursor.fetchone()
            return int(row[0]) if row else 0

        except Exception as e:
            logger.error(f"get_category_count failed: {e}")
            return 0

    def verify_integrity(self) -> bool:
        """驗證 DB 完整性."""
        return self._schema.verify_integrity()

    def get_pending_index_count(self) -> int:
        """取得待索引數量."""
        return len(self._pending_indexes)

    def get_pending_indexes(self) -> List[Dict[str, Any]]:
        """取得待索引項目."""
        return list(self._pending_indexes)

    def clear_pending_indexes(self) -> None:
        """清空待索引佇列."""
        self._pending_indexes.clear()

    def get_status(self) -> Dict[str, Any]:
        """取得 Registry Layer 狀態摘要."""
        return {
            "user_id": self._user_id,
            "db_path": str(self._db_path),
            "db_exists": self._db_path.exists(),
            "migration_version": self.get_migration_version(),
            "tables": self.get_table_names(),
            "category_count": self.get_category_count(),
            "pending_indexes": self.get_pending_index_count(),
            "integrity_ok": self.verify_integrity(),
        }
