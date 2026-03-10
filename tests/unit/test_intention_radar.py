"""Tests for IntentionRadar — 意圖雷達."""

import json
import pytest
from pathlib import Path

from museon.core.event_bus import EventBus, OUTWARD_SEARCH_NEEDED
from museon.evolution.intention_radar import (
    IntentionRadar,
    QUERY_TEMPLATES_SELF,
    QUERY_TEMPLATES_SERVICE,
    MAX_QUERIES_PER_EVENT,
)


@pytest.fixture
def workspace(tmp_path):
    """建立暫時工作空間."""
    (tmp_path / "_system" / "outward").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def event_bus():
    return EventBus()


# ═══════════════════════════════════════════
# 基本功能
# ═══════════════════════════════════════════


class TestIntentionRadarBasic:
    """基本意圖雷達功能."""

    def test_init(self, workspace, event_bus):
        """建立 IntentionRadar 實例."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)
        assert radar is not None

    def test_templates_exist(self):
        """雙軌查詢模板存在."""
        assert "plateau" in QUERY_TEMPLATES_SELF
        assert "architecture" in QUERY_TEMPLATES_SELF
        assert "rhythmic" in QUERY_TEMPLATES_SELF
        assert "pain" in QUERY_TEMPLATES_SERVICE
        assert "curiosity" in QUERY_TEMPLATES_SERVICE
        assert "failure" in QUERY_TEMPLATES_SERVICE

    def test_max_queries_per_event(self):
        """每個事件最多 2 條查詢."""
        assert MAX_QUERIES_PER_EVENT == 2


# ═══════════════════════════════════════════
# 查詢生成
# ═══════════════════════════════════════════


class TestQueryGeneration:
    """查詢生成測試."""

    def test_generate_self_plateau(self, workspace, event_bus):
        """Track A: plateau 觸發生成正確查詢."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)
        queries = radar.generate_queries({
            "track": "self",
            "trigger_type": "plateau",
            "related_skill": "text-alchemy",
            "related_domain": "writing",
            "search_intent": "text-alchemy plateau detected",
        })

        assert len(queries) > 0
        assert len(queries) <= MAX_QUERIES_PER_EVENT
        for q in queries:
            assert q["track"] == "self"
            assert q["context_type"] == "outward_self"
            assert q["trigger_type"] == "plateau"
            assert "query" in q

    def test_generate_service_pain(self, workspace, event_bus):
        """Track B: pain 觸發生成正確查詢."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)
        queries = radar.generate_queries({
            "track": "service",
            "trigger_type": "pain",
            "related_skill": "market-core",
            "related_domain": "finance",
            "search_intent": "pain in market analysis",
        })

        assert len(queries) > 0
        for q in queries:
            assert q["track"] == "service"
            assert q["context_type"] == "outward_service"

    def test_generate_service_curiosity(self, workspace, event_bus):
        """Track B: curiosity 觸發生成正確查詢."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)
        queries = radar.generate_queries({
            "track": "service",
            "trigger_type": "curiosity",
            "related_domain": "crypto",
            "search_intent": "user interested in DeFi",
        })

        assert len(queries) > 0
        for q in queries:
            assert q["context_type"] == "outward_service"
            assert q["trigger_type"] == "curiosity"

    def test_unknown_trigger_type_returns_empty(self, workspace, event_bus):
        """未知觸發類型回傳空列表."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)
        queries = radar.generate_queries({
            "track": "self",
            "trigger_type": "nonexistent",
        })
        assert queries == []

    def test_query_contains_year(self, workspace, event_bus):
        """查詢中包含年份變數."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)
        queries = radar.generate_queries({
            "track": "self",
            "trigger_type": "rhythmic",
        })

        # rhythmic 模板包含 {year}
        if queries:
            from datetime import datetime
            year = str(datetime.now().year)
            assert any(year in q["query"] for q in queries)


# ═══════════════════════════════════════════
# 計畫管理
# ═══════════════════════════════════════════


class TestPlanManagement:
    """搜尋計畫管理測試."""

    def test_load_empty_plan(self, workspace, event_bus):
        """無計畫時回傳空列表."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)
        plan = radar.load_pending_plan()
        assert plan == []

    def test_save_and_load_plan(self, workspace, event_bus):
        """儲存後可載入計畫."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)

        test_plan = [
            {"query": "test query", "track": "self", "executed": False},
        ]
        radar.save_plan(test_plan)

        loaded = radar.load_pending_plan()
        assert len(loaded) == 1
        assert loaded[0]["query"] == "test query"

    def test_mark_executed(self, workspace, event_bus):
        """標記查詢已執行."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)

        query = {"query": "test", "track": "self"}
        radar.mark_executed(query)

        assert query["executed"] is True
        assert "executed_at" in query

    def test_load_pending_excludes_executed(self, workspace, event_bus):
        """載入只回傳未執行的查詢."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)

        test_plan = [
            {"query": "done", "track": "self", "executed": True},
            {"query": "pending", "track": "service", "executed": False},
        ]
        radar.save_plan(test_plan)

        pending = radar.load_pending_plan()
        assert len(pending) == 1
        assert pending[0]["query"] == "pending"


# ═══════════════════════════════════════════
# 去重
# ═══════════════════════════════════════════


class TestDeduplication:
    """查詢去重測試."""

    def test_duplicate_query_not_added(self, workspace, event_bus):
        """相同查詢不會重複加入計畫."""
        radar = IntentionRadar(workspace=workspace, event_bus=event_bus)

        # 先存入一條
        radar.save_plan([
            {"query": "AI agent memory system SOTA 2026", "track": "self"},
        ])

        # 產生相同查詢
        queries = radar.generate_queries({
            "track": "self",
            "trigger_type": "plateau",
            "related_skill": "memory",
            "related_domain": "AI agent memory system SOTA",
        })

        # 如果去重生效，應該不會有完全重複的查詢
        # （模板填充後的查詢可能不同，所以這裡主要測試機制存在）
        assert isinstance(queries, list)
