"""Ares ProfileStore 單元測試."""

import json
import tempfile
from pathlib import Path

import pytest

from museon.ares.profile_store import ProfileStore, LEVERAGE_DIMENSIONS, VALID_DOMAINS


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path)


class TestCreateAndLoad:
    def test_create_profile(self, store):
        p = store.create("張總", domains=["business"])
        assert p["L1_facts"]["name"] == "張總"
        assert p["profile_id"]
        assert "business" in p["domains"]
        assert p["version"] == "1.0.0"

    def test_load_profile(self, store):
        p = store.create("李姐")
        loaded = store.load(p["profile_id"])
        assert loaded is not None
        assert loaded["L1_facts"]["name"] == "李姐"

    def test_load_nonexistent(self, store):
        assert store.load("nonexistent") is None

    def test_create_updates_index(self, store):
        p = store.create("王董")
        idx = store.list_all()
        assert p["profile_id"] in idx
        assert idx[p["profile_id"]]["name"] == "王董"

    def test_invalid_domain_filtered(self, store):
        p = store.create("Test", domains=["business", "invalid"])
        assert "business" in p["domains"]
        assert "invalid" not in p["domains"]


class TestUpdate:
    def test_update_facts(self, store):
        p = store.create("張總")
        updated = store.update(p["profile_id"], {
            "L1_facts": {"company": "連鎖餐飲", "title": "創辦人"},
        })
        assert updated["L1_facts"]["company"] == "連鎖餐飲"
        assert updated["L1_facts"]["title"] == "創辦人"
        assert updated["L1_facts"]["name"] == "張總"  # 保留原值

    def test_update_personality(self, store):
        p = store.create("Test")
        store.update(p["profile_id"], {
            "L2_personality": {
                "wan_miu_code": "PSRU",
                "wan_miu_name": "堅定實務者",
                "confidence": 65,
                "assessment_type": "proxy",
            },
        })
        loaded = store.load(p["profile_id"])
        assert loaded["L2_personality"]["wan_miu_code"] == "PSRU"
        assert loaded["L2_personality"]["confidence"] == 65

    def test_update_nonexistent(self, store):
        assert store.update("nonexistent", {"L1_facts": {"name": "X"}}) is None


class TestDelete:
    def test_delete_profile(self, store):
        p = store.create("刪除測試")
        assert store.delete(p["profile_id"])
        assert store.load(p["profile_id"]) is None
        assert p["profile_id"] not in store.list_all()


class TestSearch:
    def test_search_by_name(self, store):
        store.create("張總裁")
        store.create("李經理")
        results = store.search("張")
        assert len(results) == 1
        assert results[0]["L1_facts"]["name"] == "張總裁"

    def test_search_by_company(self, store):
        p = store.create("Test")
        store.update(p["profile_id"], {"L1_facts": {"company": "科技公司"}})
        results = store.search("科技")
        assert len(results) == 1

    def test_search_with_domain_filter(self, store):
        store.create("A", domains=["business"])
        store.create("B", domains=["personal"])
        results = store.search("", domain="business")
        # 空 keyword 比對所有，但只回 business 場域
        biz_results = [r for r in results if "business" in r.get("domains", [])]
        assert len(biz_results) >= 1


class TestInteractions:
    def test_add_interaction(self, store):
        p = store.create("互動測試")
        updated = store.add_interaction(
            p["profile_id"], "meeting", "討論合作方案", "positive",
        )
        assert updated["L4_interactions"]["total_count"] == 1
        assert updated["L4_interactions"]["positive_count"] == 1
        assert len(updated["L4_interactions"]["history"]) == 1

    def test_temperature_updates(self, store):
        p = store.create("溫度測試")
        assert p["temperature"]["level"] == "new"
        # 多次正面互動 → 升溫
        for _ in range(3):
            p = store.add_interaction(p["profile_id"], "call", "Good talk", "positive")
        assert p["temperature"]["level"] in ("hot", "warm")


class TestLeverage:
    def test_update_leverage(self, store):
        p = store.create("槓桿測試")
        updated = store.update_leverage(
            p["profile_id"], "channels", has="三家經銷商", needs=None,
        )
        assert updated["L5_leverage"]["channels"]["has"] == "三家經銷商"

    def test_invalid_dimension(self, store):
        p = store.create("Test")
        assert store.update_leverage(p["profile_id"], "invalid_dim") is None

    def test_all_dimensions_exist(self, store):
        p = store.create("Test")
        for dim in LEVERAGE_DIMENSIONS:
            assert dim in p["L5_leverage"]


class TestConnections:
    def test_add_connection(self, store):
        a = store.create("A")
        b = store.create("B")
        assert store.add_connection(a["profile_id"], b["profile_id"], "business_partner")
        loaded_a = store.load(a["profile_id"])
        assert len(loaded_a["connections"]) == 1
        assert loaded_a["connections"][0]["target_name"] == "B"

    def test_bidirectional(self, store):
        a = store.create("A")
        b = store.create("B")
        store.add_connection(a["profile_id"], b["profile_id"], "partner", bidirectional=True)
        loaded_b = store.load(b["profile_id"])
        assert len(loaded_b["connections"]) == 1

    def test_no_duplicate_connections(self, store):
        a = store.create("A")
        b = store.create("B")
        store.add_connection(a["profile_id"], b["profile_id"], "partner")
        store.add_connection(a["profile_id"], b["profile_id"], "friend")
        loaded_a = store.load(a["profile_id"])
        assert len(loaded_a["connections"]) == 1
        assert loaded_a["connections"][0]["relation_type"] == "friend"


class TestPathFinder:
    def test_direct_path(self, store):
        a = store.create("A")
        b = store.create("B")
        store.add_connection(a["profile_id"], b["profile_id"], "partner")
        paths = store.find_paths(a["profile_id"], b["profile_id"])
        assert len(paths) >= 1
        assert len(paths[0]) == 2  # A → B

    def test_two_layer_path(self, store):
        a = store.create("A")
        b = store.create("B")
        c = store.create("C")
        store.add_connection(a["profile_id"], b["profile_id"], "colleague")
        store.add_connection(b["profile_id"], c["profile_id"], "friend")
        paths = store.find_paths(a["profile_id"], c["profile_id"])
        assert len(paths) >= 1
        assert len(paths[0]) == 3  # A → B → C

    def test_no_path(self, store):
        a = store.create("A")
        b = store.create("B")
        # No connection
        paths = store.find_paths(a["profile_id"], b["profile_id"])
        assert len(paths) == 0


class TestTopologyData:
    def test_generate_topology(self, store):
        a = store.create("A", domains=["business"])
        b = store.create("B", domains=["business"])
        store.add_connection(a["profile_id"], b["profile_id"], "partner")
        data = store.generate_topology_data()
        assert len(data["nodes"]) == 2
        assert len(data["links"]) == 1

    def test_domain_filter(self, store):
        store.create("Biz", domains=["business"])
        store.create("Personal", domains=["personal"])
        data = store.generate_topology_data(domain="business")
        assert len(data["nodes"]) == 1


class TestImpactSimulator:
    def test_simulate_impact(self, store):
        a = store.create("A")
        b = store.create("B")
        c = store.create("C")
        store.add_connection(a["profile_id"], b["profile_id"], "supplier")
        store.add_connection(a["profile_id"], c["profile_id"], "partner")
        impacts = store.simulate_impact(a["profile_id"], "拿到獨家代理")
        assert len(impacts) == 2
        names = {i["name"] for i in impacts}
        assert "B" in names
        assert "C" in names


class TestConfidenceAutoUpgrade:
    def test_confidence_increases_with_observations(self, store):
        p = store.create("信心測試")
        store.update(p["profile_id"], {
            "L2_personality": {
                "observations": ["觀察1", "觀察2", "觀察3"],
                "assessment_type": "proxy",
            },
        })
        loaded = store.load(p["profile_id"])
        assert loaded["L2_personality"]["confidence"] >= 45  # 30 + 3*5

    def test_confidence_increases_with_interactions(self, store):
        p = store.create("互動信心")
        store.add_interaction(p["profile_id"], "meeting", "Good", "positive")
        store.add_interaction(p["profile_id"], "call", "OK", "neutral")
        loaded = store.load(p["profile_id"])
        assert loaded["L2_personality"]["confidence"] >= 34  # 30 + 2*2

    def test_confidence_capped_at_95(self, store):
        p = store.create("上限測試")
        store.update(p["profile_id"], {
            "L2_personality": {
                "observations": [f"obs{i}" for i in range(20)],
                "assessment_type": "proxy",
            },
            "L3_energy": {"has_reading": True},
        })
        loaded = store.load(p["profile_id"])
        assert loaded["L2_personality"]["confidence"] <= 95


class TestSevenLayerStructure:
    def test_all_layers_present(self, store):
        p = store.create("結構測試")
        assert "L1_facts" in p
        assert "L2_personality" in p
        assert "L3_energy" in p
        assert "L4_interactions" in p
        assert "L5_leverage" in p
        assert "L6_communication" in p
        assert "L7_context_masks" in p
        assert "temperature" in p
        assert "connections" in p
