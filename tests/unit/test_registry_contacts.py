"""Unit tests for Registry Manager — Contacts & Cross-type Search (Phase 5)."""

import pytest

from museon.registry.registry_manager import RegistryManager


@pytest.fixture
def data_dir(tmp_path):
    return str(tmp_path / "data")


@pytest.fixture
def m(data_dir):
    return RegistryManager(data_dir=data_dir, user_id="test_user")


# ═══════════════════════════════════════
# Contacts CRUD
# ═══════════════════════════════════════

class TestContacts:

    def test_add_contact(self, m):
        cid = m.add_contact(
            name="符大哥",
            phone="0912345678",
            birthday="05-15",
        )
        assert cid is not None
        assert cid.startswith("ct_")

    def test_get_contact(self, m):
        cid = m.add_contact(
            name="符大哥",
            phone="0912345678",
            email="fu@example.com",
            company="旅行社",
            title="老闆",
            birthday="05-15",
            note="Museon 合作夥伴",
            tags=["VIP", "合作"],
        )
        ct = m.get_contact(cid)
        assert ct is not None
        assert ct["name"] == "符大哥"
        assert ct["phone"] == "0912345678"
        assert ct["email"] == "fu@example.com"
        assert ct["company"] == "旅行社"
        assert ct["title"] == "老闆"
        assert ct["birthday"] == "05-15"

    def test_query_contacts_by_name(self, m):
        m.add_contact(name="符大哥", phone="0912345678")
        m.add_contact(name="王總", phone="0923456789")

        results = m.query_contacts(keyword="符")
        assert len(results) == 1
        assert results[0]["name"] == "符大哥"

    def test_query_contacts_by_company(self, m):
        m.add_contact(name="員工 A", company="Anthropic")
        m.add_contact(name="員工 B", company="Google")

        results = m.query_contacts(keyword="Anthropic")
        assert len(results) == 1

    def test_find_contact_by_name(self, m):
        m.add_contact(name="符大哥", phone="0912345678")
        ct = m.find_contact_by_name("符大哥")
        assert ct is not None
        assert ct["phone"] == "0912345678"

    def test_find_nonexistent_contact(self, m):
        ct = m.find_contact_by_name("不存在的人")
        assert ct is None

    def test_contact_pending_index(self, m):
        m.add_contact(name="索引測試", company="Test Corp")
        pending = m.get_pending_indexes()
        contact_indexes = [
            p for p in pending if p["doc_type"] == "contact"
        ]
        assert len(contact_indexes) == 1


# ═══════════════════════════════════════
# Cross-type Search
# ═══════════════════════════════════════

class TestCrossTypeSearch:

    def test_search_all_types(self, m):
        m.add_transaction(
            amount=-500, counterparty="符大哥", description="晚餐"
        )
        m.add_meeting(
            title="符大哥週會", summary="討論進度"
        )
        m.add_event(
            title="跟符大哥開會",
            datetime_start="2026-03-15T06:00:00",
        )
        m.add_contact(name="符大哥", phone="0912345678")

        results = m.search_all("符大哥")
        assert len(results) == 4
        types = {r["_type"] for r in results}
        assert types == {"ledger", "meeting", "event", "contact"}

    def test_search_partial_match(self, m):
        m.add_contact(name="符大哥")
        m.add_contact(name="王總")

        results = m.search_all("符")
        assert len(results) == 1

    def test_search_no_results(self, m):
        results = m.search_all("不存在的關鍵字")
        assert len(results) == 0

    def test_search_limit(self, m):
        for i in range(25):
            m.add_contact(name=f"測試用戶{i}")

        results = m.search_all("測試用戶", limit=10)
        assert len(results) <= 10
