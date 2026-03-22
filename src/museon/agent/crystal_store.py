"""CrystalStore — SQLite WAL 模式的知識晶格持久化層.

取代原本的 LatticeStore（JSON 檔案存儲），使用 SQLite WAL 模式
實現讀寫分離，解決 crystals.json 的無鎖並發風險。

設計原則：
- WAL 模式：多讀單寫，不阻塞讀取
- 相容 API：與 LatticeStore 完全相同的公開介面
- Crystal/CrystalLink 序列化不變：to_dict / from_dict 保持一致
- 外部讀取者（nightly、evolution、guardian、doctor）統一接入

遷移來源：
- data/lattice/crystals.json  → crystals 表
- data/lattice/links.json     → links 表
- data/lattice/archive.json   → crystals 表（archived=1）
- data/lattice/cuid_counter.json → cuid_counters 表
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.core.data_bus import DataContract, StoreSpec, StoreEngine, TTLTier

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS crystals (
    cuid TEXT PRIMARY KEY,
    crystal_type TEXT NOT NULL,
    g1_summary TEXT NOT NULL,
    g2_structure TEXT NOT NULL DEFAULT '[]',
    g3_root_inquiry TEXT NOT NULL DEFAULT '',
    g4_insights TEXT NOT NULL DEFAULT '[]',
    assumption TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    limitation TEXT NOT NULL DEFAULT '',
    verification_level TEXT NOT NULL DEFAULT 'hypothetical',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0,
    ri_score REAL NOT NULL DEFAULT 0.0,
    reference_count INTEGER NOT NULL DEFAULT 0,
    last_referenced TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    domain TEXT NOT NULL DEFAULT '',
    success_count INTEGER NOT NULL DEFAULT 0,
    counter_evidence_count INTEGER NOT NULL DEFAULT 0,
    source_context TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    origin TEXT NOT NULL DEFAULT ''
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS links (
    from_cuid TEXT NOT NULL,
    to_cuid TEXT NOT NULL,
    link_type TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (from_cuid, to_cuid, link_type)
);

CREATE TABLE IF NOT EXISTS cuid_counters (
    type_abbr TEXT PRIMARY KEY,
    seq INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_crystals_type ON crystals(crystal_type);
CREATE INDEX IF NOT EXISTS idx_crystals_archived ON crystals(archived);
CREATE INDEX IF NOT EXISTS idx_crystals_status ON crystals(status);
CREATE INDEX IF NOT EXISTS idx_crystals_ri ON crystals(ri_score DESC);
CREATE INDEX IF NOT EXISTS idx_links_from ON links(from_cuid);
CREATE INDEX IF NOT EXISTS idx_links_to ON links(to_cuid);
"""


# ═══════════════════════════════════════════
# CrystalStore
# ═══════════════════════════════════════════

class CrystalStore(DataContract):
    """SQLite WAL 模式的知識晶格持久化存儲.

    與原 LatticeStore 完全相同的公開 API，內部改用 SQLite。

    檔案結構：
    - data/lattice/crystal.db  -- SQLite WAL（含 crystals, links, cuid_counters 三表）
    """

    # JSON 序列欄位（儲存為 JSON 字串的 list 欄位）
    _JSON_FIELDS = frozenset({"g2_structure", "g4_insights", "tags"})

    @classmethod
    def store_spec(cls) -> StoreSpec:
        return StoreSpec(
            name="crystal_store",
            engine=StoreEngine.SQLITE,
            ttl=TTLTier.PERMANENT,
            description="知識晶格結晶化存儲（SQLite WAL）",
            tables=["crystals", "links", "cuid_counters"],
        )

    def __init__(self, data_dir: str = "data") -> None:
        """初始化存儲.

        Args:
            data_dir: 資料根目錄
        """
        self._base_path = Path(data_dir) / "lattice"
        self._base_path.mkdir(parents=True, exist_ok=True)
        self._db_path = self._base_path / "crystal.db"

        # 寫入鎖（只保護寫入操作；讀取由 WAL 模式保障不阻塞）
        self._write_lock = threading.Lock()

        # 初始化 DB
        self._init_db()

    def _init_db(self) -> None:
        """初始化 SQLite 資料庫（WAL 模式 + schema）."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()

    def _get_read_conn(self) -> sqlite3.Connection:
        """取得讀取用連線（WAL 模式下不阻塞寫入）."""
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=10,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _get_write_conn(self) -> sqlite3.Connection:
        """取得寫入用連線."""
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=10,
        )
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    # ─────────────────────────────────────
    # 序列化工具
    # ─────────────────────────────────────

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """將 SQLite Row 轉為 Crystal 相容的字典."""
        d = dict(row)
        # JSON 欄位反序列化
        for f in self._JSON_FIELDS:
            if f in d and isinstance(d[f], str):
                try:
                    d[f] = json.loads(d[f])
                except (json.JSONDecodeError, TypeError):
                    d[f] = []
        # archived: int → bool
        if "archived" in d:
            d["archived"] = bool(d["archived"])
        return d

    @staticmethod
    def _dict_to_params(d: Dict[str, Any]) -> Dict[str, Any]:
        """將 Crystal dict 轉為 SQLite 參數（JSON 欄位序列化）."""
        params = dict(d)
        for f in CrystalStore._JSON_FIELDS:
            if f in params and isinstance(params[f], list):
                params[f] = json.dumps(params[f], ensure_ascii=False)
        # archived: bool → int
        if "archived" in params:
            params["archived"] = int(params["archived"])
        return params

    # ─────────────────────────────────────
    # 結晶存取（與 LatticeStore API 相容）
    # ─────────────────────────────────────

    def load_crystals(self) -> Dict:
        """載入所有活躍結晶.

        Returns:
            結晶字典（cuid -> Crystal）

        注：回傳的是 Crystal 物件字典，與 LatticeStore 相同。
        延遲 import 避免循環依賴。
        """
        from museon.agent.knowledge_lattice import Crystal

        conn = self._get_read_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM crystals WHERE archived = 0"
            ).fetchall()
            crystals: Dict = {}
            for row in rows:
                try:
                    d = self._row_to_dict(row)
                    crystal = Crystal.from_dict(d)
                    crystals[crystal.cuid] = crystal
                except Exception as e:
                    logger.error(f"CrystalStore: 載入結晶失敗: {e}")
            return crystals
        finally:
            conn.close()

    def save_crystals(self, crystals: Dict) -> None:
        """儲存所有活躍結晶（全量覆寫）.

        Args:
            crystals: 結晶字典（cuid -> Crystal）
        """
        with self._write_lock:
            conn = self._get_write_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                # 刪除所有未歸檔結晶，再插入
                conn.execute("DELETE FROM crystals WHERE archived = 0")
                for crystal in crystals.values():
                    d = self._dict_to_params(crystal.to_dict())
                    cols = ", ".join(d.keys())
                    placeholders = ", ".join(f":{k}" for k in d.keys())
                    conn.execute(
                        f"INSERT OR REPLACE INTO crystals ({cols}) "
                        f"VALUES ({placeholders})",
                        d,
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"CrystalStore: 儲存結晶失敗: {e}")
            finally:
                conn.close()

    # ─────────────────────────────────────
    # 連結存取
    # ─────────────────────────────────────

    def load_links(self) -> List:
        """載入所有連結.

        Returns:
            CrystalLink 列表
        """
        from museon.agent.knowledge_lattice import CrystalLink

        conn = self._get_read_conn()
        try:
            rows = conn.execute("SELECT * FROM links").fetchall()
            links: List = []
            for row in rows:
                try:
                    links.append(CrystalLink.from_dict(dict(row)))
                except Exception as e:
                    logger.error(f"CrystalStore: 載入連結失敗: {e}")
            return links
        finally:
            conn.close()

    def save_links(self, links: List) -> None:
        """儲存所有連結（全量覆寫）.

        Args:
            links: CrystalLink 列表
        """
        with self._write_lock:
            conn = self._get_write_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM links")
                for link in links:
                    d = link.to_dict()
                    cols = ", ".join(d.keys())
                    placeholders = ", ".join(f":{k}" for k in d.keys())
                    conn.execute(
                        f"INSERT INTO links ({cols}) VALUES ({placeholders})",
                        d,
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"CrystalStore: 儲存連結失敗: {e}")
            finally:
                conn.close()

    # ─────────────────────────────────────
    # 歸檔存取
    # ─────────────────────────────────────

    def load_archive(self) -> Dict:
        """載入已歸檔結晶.

        Returns:
            歸檔結晶字典（cuid -> Crystal）
        """
        from museon.agent.knowledge_lattice import Crystal

        conn = self._get_read_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM crystals WHERE archived = 1"
            ).fetchall()
            archive: Dict = {}
            for row in rows:
                try:
                    d = self._row_to_dict(row)
                    crystal = Crystal.from_dict(d)
                    archive[crystal.cuid] = crystal
                except Exception as e:
                    logger.error(f"CrystalStore: 載入歸檔結晶失敗: {e}")
            return archive
        finally:
            conn.close()

    def save_archive(self, archive: Dict) -> None:
        """儲存歸檔結晶（全量覆寫）.

        Args:
            archive: 歸檔結晶字典（cuid -> Crystal）
        """
        with self._write_lock:
            conn = self._get_write_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("DELETE FROM crystals WHERE archived = 1")
                for crystal in archive.values():
                    d = self._dict_to_params(crystal.to_dict())
                    d["archived"] = 1
                    cols = ", ".join(d.keys())
                    placeholders = ", ".join(f":{k}" for k in d.keys())
                    conn.execute(
                        f"INSERT OR REPLACE INTO crystals ({cols}) "
                        f"VALUES ({placeholders})",
                        d,
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"CrystalStore: 儲存歸檔失敗: {e}")
            finally:
                conn.close()

    # ─────────────────────────────────────
    # CUID 計數器
    # ─────────────────────────────────────

    def load_counters(self) -> Dict[str, int]:
        """載入 CUID 序號計數器.

        Returns:
            計數器字典（type_abbr -> seq）
        """
        default = {"INS": 0, "PAT": 0, "LES": 0, "HYP": 0}
        conn = self._get_read_conn()
        try:
            rows = conn.execute(
                "SELECT type_abbr, seq FROM cuid_counters"
            ).fetchall()
            if not rows:
                return default
            result = dict(default)
            for row in rows:
                result[row["type_abbr"]] = row["seq"]
            return result
        finally:
            conn.close()

    def save_counters(self, counters: Dict[str, int]) -> None:
        """儲存 CUID 序號計數器.

        Args:
            counters: 計數器字典（type_abbr -> seq）
        """
        with self._write_lock:
            conn = self._get_write_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                for abbr, seq in counters.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO cuid_counters "
                        "(type_abbr, seq) VALUES (?, ?)",
                        (abbr, seq),
                    )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"CrystalStore: 儲存計數器失敗: {e}")
            finally:
                conn.close()

    # ─────────────────────────────────────
    # 外部讀取者便利方法
    # ─────────────────────────────────────

    def load_crystals_raw(self) -> List[Dict[str, Any]]:
        """載入所有活躍結晶（原始字典格式）.

        供 nightly_pipeline、evolution_velocity 等外部讀取者使用，
        不需要 import Crystal 類別。

        Returns:
            結晶字典列表
        """
        conn = self._get_read_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM crystals WHERE archived = 0"
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]
        finally:
            conn.close()

    def count_crystals(self, archived: bool = False) -> int:
        """計算結晶數量.

        Args:
            archived: True=歸檔結晶, False=活躍結晶

        Returns:
            結晶數量
        """
        conn = self._get_read_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM crystals WHERE archived = ?",
                (int(archived),),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def reset(self) -> int:
        """清空所有資料（用於 memory_reset）.

        Returns:
            被清除的結晶數量
        """
        with self._write_lock:
            conn = self._get_write_conn()
            try:
                conn.execute("BEGIN IMMEDIATE")
                count = conn.execute(
                    "SELECT COUNT(*) FROM crystals"
                ).fetchone()[0]
                conn.execute("DELETE FROM crystals")
                conn.execute("DELETE FROM links")
                conn.execute(
                    "DELETE FROM cuid_counters"
                )
                conn.commit()
                return count
            except Exception as e:
                conn.rollback()
                logger.error(f"CrystalStore: 重置失敗: {e}")
                return 0
            finally:
                conn.close()

    def is_healthy(self) -> bool:
        """快速健康檢查（用於 guardian/daemon）.

        Returns:
            True 表示資料庫可正常讀取
        """
        try:
            conn = self._get_read_conn()
            try:
                conn.execute(
                    "SELECT COUNT(*) FROM crystals"
                ).fetchone()
                return True
            finally:
                conn.close()
        except Exception:
            return False

    # ─────────────────────────────────────
    # DataContract 介面
    # ─────────────────────────────────────

    def health_check(self) -> Dict[str, Any]:
        """健康檢查."""
        try:
            conn = self._get_read_conn()
            try:
                crystal_count = conn.execute(
                    "SELECT COUNT(*) FROM crystals WHERE archived = 0"
                ).fetchone()[0]
                archive_count = conn.execute(
                    "SELECT COUNT(*) FROM crystals WHERE archived = 1"
                ).fetchone()[0]
                link_count = conn.execute(
                    "SELECT COUNT(*) FROM links"
                ).fetchone()[0]
                db_size = self._db_path.stat().st_size if self._db_path.exists() else 0
                return {
                    "status": "ok",
                    "engine": "sqlite_wal",
                    "db_path": str(self._db_path),
                    "crystal_count": crystal_count,
                    "archive_count": archive_count,
                    "link_count": link_count,
                    "db_size_bytes": db_size,
                }
            finally:
                conn.close()
        except Exception as e:
            return {"status": "error", "error": str(e)}
