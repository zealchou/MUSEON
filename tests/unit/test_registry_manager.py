"""Unit tests for Registry Manager — 結構化資料層統一門面."""

from pathlib import Path

import pytest

from museon.registry.registry_manager import RegistryManager


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════

@pytest.fixture
def data_dir(tmp_path):
    """Provide a temporary data directory."""
    return str(tmp_path / "data")


@pytest.fixture
def manager(data_dir):
    """Create a RegistryManager instance."""
    return RegistryManager(data_dir=data_dir, user_id="test_user")


# ═══════════════════════════════════════
# 初始化
# ═══════════════════════════════════════

class TestInitialization:
    """初始化相關測試."""

    def test_creates_registry_dir(self, manager, data_dir):
        """初始化應建立 registry/{user_id}/ 目錄."""
        assert Path(data_dir, "registry", "test_user").is_dir()

    def test_creates_db_file(self, manager, data_dir):
        """初始化應建立 registry.db."""
        assert Path(data_dir, "registry", "test_user", "registry.db").exists()

    def test_creates_vault_dirs(self, manager, data_dir):
        """初始化應建立 vault/ 子目錄."""
        vault = Path(data_dir, "vault", "test_user")
        assert (vault / "meetings").is_dir()
        assert (vault / "receipts").is_dir()
        assert (vault / "imports").is_dir()

    def test_creates_inbox_dir(self, manager, data_dir):
        """初始化應建立 inbox/ 目錄."""
        assert Path(data_dir, "inbox").is_dir()

    def test_migration_version(self, manager):
        """初始化後 migration 版本應為 1."""
        assert manager.get_migration_version() == 1

    def test_7_tables_created(self, manager):
        """初始化後應有 7 張表."""
        tables = manager.get_table_names()
        assert len(tables) == 7

    def test_properties(self, manager, data_dir):
        """屬性值正確."""
        assert manager.user_id == "test_user"
        assert "test_user" in manager.db_path
        assert "test_user" in manager.registry_dir
        assert "test_user" in manager.vault_dir
        assert "inbox" in manager.inbox_dir


# ═══════════════════════════════════════
# 分類操作
# ═══════════════════════════════════════

class TestCategories:
    """分類操作測試."""

    def test_list_all_categories(self, manager):
        """列出所有分類."""
        categories = manager.list_categories()
        assert len(categories) >= 20

    def test_list_by_parent(self, manager):
        """按父分類篩選."""
        income_cats = manager.list_categories(parent_id="income")
        assert len(income_cats) > 0
        for cat in income_cats:
            assert cat["parent_id"] == "income"

    def test_category_count(self, manager):
        """分類計數."""
        count = manager.get_category_count()
        assert count >= 20

    def test_system_category_count(self, manager):
        """系統分類計數."""
        system_count = manager.get_category_count(system_only=True)
        total_count = manager.get_category_count()
        assert system_count == total_count  # 初始只有系統分類

    def test_add_custom_category(self, manager):
        """新增自訂分類."""
        result = manager.add_category(
            category_id="expense.pets",
            parent_id="expense",
            name_zh="寵物",
            name_en="Pets",
        )
        assert result is True

        # 驗證系統分類數量不變
        system_count = manager.get_category_count(system_only=True)
        total_count = manager.get_category_count()
        assert total_count == system_count + 1

    def test_add_duplicate_category_fails(self, manager):
        """新增重複分類應失敗."""
        manager.add_category("expense.pets", "expense", "寵物")
        result = manager.add_category("expense.pets", "expense", "寵物2")
        assert result is False


# ═══════════════════════════════════════
# 交易 CRUD
# ═══════════════════════════════════════

class TestTransactions:
    """交易 CRUD 測試."""

    def test_add_transaction_returns_id(self, manager):
        """新增交易應回傳 ID."""
        tx_id = manager.add_transaction(
            amount=-180,
            category="expense.food.dining_out",
            counterparty="拉麵店",
            description="午餐吃拉麵",
        )
        assert tx_id is not None
        assert tx_id.startswith("tx_")

    def test_get_transaction(self, manager):
        """取得單筆交易."""
        tx_id = manager.add_transaction(
            amount=-180,
            category="expense.food.dining_out",
            counterparty="拉麵店",
        )
        tx = manager.get_transaction(tx_id)
        assert tx is not None
        assert tx["amount"] == -180
        assert tx["category"] == "expense.food.dining_out"
        assert tx["counterparty"] == "拉麵店"
        assert tx["currency"] == "TWD"

    def test_add_income_transaction(self, manager):
        """新增收入交易."""
        tx_id = manager.add_transaction(
            amount=50000,
            category="income.freelance",
            description="專案尾款",
        )
        tx = manager.get_transaction(tx_id)
        assert tx["amount"] == 50000

    def test_query_by_category(self, manager):
        """按分類查詢."""
        manager.add_transaction(amount=-180, category="expense.food.dining_out")
        manager.add_transaction(amount=-50, category="expense.transport.taxi")
        manager.add_transaction(amount=-200, category="expense.food.delivery")

        food = manager.query_transactions(category_prefix="expense.food")
        assert len(food) == 2

    def test_query_by_date_range(self, manager):
        """按日期範圍查詢."""
        manager.add_transaction(
            amount=-100,
            transaction_date="2026-03-01",
        )
        manager.add_transaction(
            amount=-200,
            transaction_date="2026-03-15",
        )
        manager.add_transaction(
            amount=-300,
            transaction_date="2026-04-01",
        )

        march = manager.query_transactions(
            date_from="2026-03-01",
            date_to="2026-03-31",
        )
        assert len(march) == 2

    def test_sum_transactions(self, manager):
        """加總交易金額."""
        manager.add_transaction(amount=-180, category="expense.food.dining_out")
        manager.add_transaction(amount=-120, category="expense.food.delivery")
        manager.add_transaction(amount=-50, category="expense.transport.taxi")

        food_total = manager.sum_transactions(category_prefix="expense.food")
        assert food_total == -300

    def test_pending_index_created(self, manager):
        """新增交易應產生 pending index 項目."""
        assert manager.get_pending_index_count() == 0

        manager.add_transaction(amount=-100, counterparty="測試店家")
        assert manager.get_pending_index_count() == 1

        pending = manager.get_pending_indexes()
        assert pending[0]["doc_type"] == "ledger"

    def test_clear_pending_indexes(self, manager):
        """清空 pending indexes."""
        manager.add_transaction(amount=-100)
        manager.add_transaction(amount=-200)
        assert manager.get_pending_index_count() == 2

        manager.clear_pending_indexes()
        assert manager.get_pending_index_count() == 0


# ═══════════════════════════════════════
# 狀態查詢
# ═══════════════════════════════════════

class TestStatus:
    """狀態查詢測試."""

    def test_get_status(self, manager):
        """get_status 應回傳完整狀態."""
        status = manager.get_status()
        assert status["user_id"] == "test_user"
        assert status["db_exists"] is True
        assert status["migration_version"] == 1
        assert len(status["tables"]) == 7
        assert status["category_count"] >= 20
        assert status["integrity_ok"] is True

    def test_verify_integrity(self, manager):
        """完整性檢查應通過."""
        assert manager.verify_integrity() is True

    def test_close_and_reopen(self, data_dir):
        """關閉後重開應正常."""
        m1 = RegistryManager(data_dir=data_dir, user_id="test_user")
        m1.add_transaction(amount=-100, counterparty="測試")
        m1.close()

        m2 = RegistryManager(data_dir=data_dir, user_id="test_user")
        txs = m2.query_transactions()
        assert len(txs) == 1
        m2.close()


# ═══════════════════════════════════════
# 多使用者隔離
# ═══════════════════════════════════════

class TestMultiUser:
    """多使用者隔離測試."""

    def test_separate_dbs(self, data_dir):
        """不同 user_id 應使用不同 DB."""
        m1 = RegistryManager(data_dir=data_dir, user_id="user_a")
        m2 = RegistryManager(data_dir=data_dir, user_id="user_b")

        assert m1.db_path != m2.db_path

        m1.add_transaction(amount=-100, counterparty="A 的交易")
        m2.add_transaction(amount=-200, counterparty="B 的交易")

        assert len(m1.query_transactions()) == 1
        assert len(m2.query_transactions()) == 1

        m1.close()
        m2.close()
