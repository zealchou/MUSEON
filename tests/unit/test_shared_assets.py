"""Shared Assets BDD 測試.

依據 MULTI_AGENT_BDD_SPEC §5 驗證。
"""

import json
import pytest

from museon.multiagent.shared_assets import (
    ARCHIVE_THRESHOLD,
    DECAY_BY_TYPE,
    DEFAULT_DECAY,
    SharedAsset,
    SharedAssetLibrary,
)


@pytest.fixture
def lib(tmp_path):
    return SharedAssetLibrary(workspace=tmp_path)


class TestPublish:
    """Scenario: 發布資產."""

    def test_publish_creates_file(self, lib, tmp_path):
        asset = lib.publish(
            title="測試報告",
            content="# 報告\n\n內容",
            asset_type="report",
            source_dept="thunder",
            gate_level=3,
            quality_score=0.8,
            tags=["Q1", "行銷"],
        )
        assert asset.asset_id
        assert len(asset.asset_id) == 12
        assert asset.title == "測試報告"
        assert asset.source_dept == "thunder"
        # 檔案存在
        path = tmp_path / "_system" / "shared_assets" / f"{asset.asset_id}.json"
        assert path.exists()

    def test_publish_default_values(self, lib):
        asset = lib.publish("t", "c", "report", "core")
        assert asset.version == 1
        assert asset.quality_score == 0.5
        assert asset.tags == []
        assert asset.archived is False


class TestGet:
    """Scenario: 取得資產."""

    def test_get_by_full_id(self, lib):
        asset = lib.publish("a", "b", "report", "fire")
        found = lib.get(asset.asset_id)
        assert found is not None
        assert found.title == "a"

    def test_get_by_prefix(self, lib):
        """8 字元前綴取得."""
        asset = lib.publish("前綴測試", "c", "report", "fire")
        prefix = asset.asset_id[:8]
        found = lib.get(prefix)
        assert found is not None
        assert found.asset_id == asset.asset_id

    def test_get_nonexistent(self, lib):
        assert lib.get("nonexistent123") is None


class TestSearch:
    """Scenario: 搜尋資產."""

    def test_search_by_title(self, lib):
        lib.publish("行銷策略", "content", "plan", "fire", tags=["行銷"])
        lib.publish("技術報告", "content", "report", "wind")
        results = lib.search("行銷")
        assert len(results) == 1
        assert results[0].title == "行銷策略"

    def test_search_by_tag(self, lib):
        lib.publish("a", "content", "report", "fire", tags=["Q1"])
        results = lib.search("Q1")
        assert len(results) == 1

    def test_search_dept_filter(self, lib):
        lib.publish("a", "行銷", "report", "fire")
        lib.publish("b", "行銷", "report", "thunder")
        results = lib.search("行銷", dept_filter="fire")
        assert len(results) == 1
        assert results[0].source_dept == "fire"

    def test_search_type_filter(self, lib):
        lib.publish("a", "content", "report", "fire")
        lib.publish("b", "content", "plan", "fire")
        results = lib.search("content", asset_type="plan")
        assert len(results) == 1
        assert results[0].asset_type == "plan"

    def test_cross_dept_search(self, lib):
        """跨部門搜尋."""
        lib.publish("fire行銷", "行銷策略內容", "plan", "fire")
        # thunder 也能找到 fire 的資產
        results = lib.search("行銷")
        assert any(r.source_dept == "fire" for r in results)

    def test_archived_not_in_search(self, lib):
        asset = lib.publish("old", "content", "report", "fire", quality_score=0.1)
        lib.archive_low_quality(threshold=0.2)
        results = lib.search("content")
        assert len(results) == 0


class TestDecay:
    """Scenario: 每日品質衰退."""

    def test_decay_reduces_score(self, lib):
        asset = lib.publish("a", "b", "report", "fire", quality_score=0.5)
        affected = lib.decay_all()
        assert affected == 1
        updated = lib.get(asset.asset_id)
        expected = round(0.5 * DECAY_BY_TYPE["report"], 6)
        assert updated.quality_score == expected

    def test_vision_no_decay(self, lib):
        """願景類型不衰退."""
        asset = lib.publish("v", "c", "vision", "heaven", quality_score=0.8)
        lib.decay_all()
        updated = lib.get(asset.asset_id)
        assert updated.quality_score == 0.8

    def test_brand_no_decay(self, lib):
        """品牌類型不衰退."""
        asset = lib.publish("b", "c", "brand", "fire", quality_score=0.9)
        lib.decay_all()
        updated = lib.get(asset.asset_id)
        assert updated.quality_score == 0.9

    def test_strategy_slow_decay(self, lib):
        """策略衰退比報告慢."""
        r = lib.publish("r", "c", "report", "fire", quality_score=0.5)
        s = lib.publish("s", "c", "strategy", "heaven", quality_score=0.5)
        lib.decay_all()
        report = lib.get(r.asset_id)
        strategy = lib.get(s.asset_id)
        assert strategy.quality_score > report.quality_score


class TestArchive:
    """Scenario: 低品質歸檔."""

    def test_archive_below_threshold(self, lib):
        lib.publish("low", "c", "report", "fire", quality_score=0.25)
        lib.publish("ok", "c", "report", "fire", quality_score=0.5)
        archived = lib.archive_low_quality(threshold=ARCHIVE_THRESHOLD)
        assert archived == 1

    def test_archive_sets_reason(self, lib):
        asset = lib.publish("low", "c", "report", "fire", quality_score=0.1)
        lib.archive_low_quality()
        updated = lib.get(asset.asset_id)
        assert updated.archived is True
        assert "quality_score" in updated.archive_reason


class TestListAll:
    """Scenario: 列出資產."""

    def test_list_excludes_archived(self, lib):
        lib.publish("a", "c", "report", "fire", quality_score=0.1)
        lib.publish("b", "c", "report", "fire", quality_score=0.5)
        lib.archive_low_quality(threshold=0.2)
        results = lib.list_all()
        assert len(results) == 1

    def test_list_includes_archived(self, lib):
        lib.publish("a", "c", "report", "fire", quality_score=0.1)
        lib.archive_low_quality(threshold=0.2)
        results = lib.list_all(include_archived=True)
        assert len(results) == 1


class TestDecayByType:
    """Scenario: per-type 衰退因子設計."""

    def test_vision_factor_is_1(self):
        assert DECAY_BY_TYPE["vision"] == 1.0

    def test_brand_factor_is_1(self):
        assert DECAY_BY_TYPE["brand"] == 1.0

    def test_report_factor_default(self):
        assert DECAY_BY_TYPE["report"] == DEFAULT_DECAY

    def test_strategy_slower_than_report(self):
        assert DECAY_BY_TYPE["strategy"] > DECAY_BY_TYPE["report"]
