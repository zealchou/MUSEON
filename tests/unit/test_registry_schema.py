"""Unit tests for Registry Schema — SQLite DDL + Migration."""

import sqlite3
from pathlib import Path

import pytest

from museon.registry.schema import CURRENT_VERSION, RegistrySchema
from museon.registry.category_presets import count_presets, get_all_presets


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

@pytest.fixture
def db_path(tmp_path):
    """Provide a temporary DB path."""
    return str(tmp_path / "test_registry.db")


@pytest.fixture
def schema(db_path):
    """Create a RegistrySchema instance."""
    return RegistrySchema(db_path)


# ═══════════════════════════════════════
# Schema 建立
# ═══════════════════════════════════════

class TestSchemaCreation:
    """Schema 建立相關測試."""

    def test_initialize_creates_db_file(self, schema, db_path):
        """初始化後 DB 檔案應存在."""
        result = schema.initialize()
        assert result is True
        assert Path(db_path).exists()

    def test_initialize_creates_7_tables(self, schema):
        """初始化後應有 7 張表."""
        schema.initialize()
        tables = schema.get_table_names()
        expected = [
            "_categories",
            "_migrations",
            "action_items",
            "contacts",
            "events",
            "meetings",
            "transactions",
        ]
        assert sorted(tables) == expected

    def test_initialize_creates_parent_dirs(self, tmp_path):
        """初始化應自動建立父目錄."""
        deep_path = str(tmp_path / "a" / "b" / "c" / "registry.db")
        schema = RegistrySchema(deep_path)
        result = schema.initialize()
        assert result is True
        assert Path(deep_path).exists()


# ═══════════════════════════════════════
# Migration 冪等
# ═══════════════════════════════════════

class TestMigrationIdempotent:
    """Migration 冪等性測試."""

    def test_version_after_init(self, schema):
        """初始化後版本應為 CURRENT_VERSION."""
        schema.initialize()
        assert schema.get_version() == CURRENT_VERSION

    def test_double_init_is_idempotent(self, schema):
        """重複初始化不改變版本."""
        schema.initialize()
        v1 = schema.get_version()
        schema.initialize()
        v2 = schema.get_version()
        assert v1 == v2 == CURRENT_VERSION

    def test_double_init_preserves_data(self, schema, db_path):
        """重複初始化不丟失資料."""
        schema.initialize()

        # 手動插入一筆測試資料
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO contacts (id, user_id, name) "
            "VALUES ('test-001', 'user1', '測試聯絡人')"
        )
        conn.commit()
        conn.close()

        # 再次初始化
        schema.initialize()

        # 驗證資料仍在
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM contacts WHERE id = 'test-001'"
        )
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "測試聯絡人"

    def test_version_before_init_is_zero(self, tmp_path):
        """未初始化的 DB 版本應為 0."""
        db_path = str(tmp_path / "empty.db")
        schema = RegistrySchema(db_path)
        # 建立空檔案
        Path(db_path).touch()
        assert schema.get_version() == 0


# ═══════════════════════════════════════
# 分類灌入
# ═══════════════════════════════════════

class TestCategorySeeding:
    """預設分類灌入測試."""

    def test_presets_seeded(self, schema, db_path):
        """初始化後應灌入所有預設分類."""
        schema.initialize()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM _categories WHERE is_system = 1"
        )
        count = cursor.fetchone()[0]
        conn.close()

        expected = count_presets()
        assert count == expected

    def test_presets_at_least_20(self, schema, db_path):
        """預設分類應至少 20 個."""
        schema.initialize()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM _categories")
        count = cursor.fetchone()[0]
        conn.close()

        assert count >= 20

    def test_presets_cover_three_types(self, schema, db_path):
        """分類應涵蓋收入、支出、轉帳三大類."""
        schema.initialize()

        conn = sqlite3.connect(db_path)

        for cat_type in ["income", "expense", "transfer"]:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM _categories "
                "WHERE category_id = ? OR category_id LIKE ?",
                (cat_type, f"{cat_type}.%"),
            )
            count = cursor.fetchone()[0]
            assert count > 0, f"Missing category type: {cat_type}"

        conn.close()

    def test_expense_has_food_transport_housing(self, schema, db_path):
        """支出下應包含餐飲、交通、住宿子分類."""
        schema.initialize()

        conn = sqlite3.connect(db_path)

        for sub in ["expense.food", "expense.transport", "expense.housing"]:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM _categories "
                "WHERE category_id LIKE ?",
                (f"{sub}%",),
            )
            count = cursor.fetchone()[0]
            assert count > 0, f"Missing subcategory: {sub}"

        conn.close()

    def test_double_seed_no_duplicates(self, schema, db_path):
        """重複灌入不產生重複分類（INSERT OR IGNORE）."""
        schema.initialize()
        schema.initialize()

        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM _categories")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == count_presets()


# ═══════════════════════════════════════
# 完整性檢查
# ═══════════════════════════════════════

class TestIntegrity:
    """DB 完整性測試."""

    def test_integrity_check_passes(self, schema):
        """正常 DB 的完整性檢查應通過."""
        schema.initialize()
        assert schema.verify_integrity() is True

    def test_wal_mode_enabled(self, schema, db_path):
        """WAL 模式應被啟用."""
        schema.initialize()

        conn = sqlite3.connect(db_path)
        result = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        assert result[0] == "wal"
