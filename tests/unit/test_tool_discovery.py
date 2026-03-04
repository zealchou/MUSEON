"""Tool Discovery BDD 測試.

驗證每日自動發現新工具的邏輯。
"""

import json
import pytest

from museon.tools.tool_discovery import (
    BLACKLISTED_TOOLS,
    KNOWN_TOOLS,
    MIN_SCORE,
    SEARCH_QUERIES,
    ToolDiscovery,
)


@pytest.fixture
def discovery(tmp_path):
    return ToolDiscovery(workspace=tmp_path)


class TestSearchConfig:
    """Scenario: 搜尋設定."""

    def test_search_queries_exist(self):
        assert len(SEARCH_QUERIES) >= 3

    def test_known_tools_include_our_tools(self):
        our_tools = {"searxng", "ollama", "qdrant", "whisper.cpp", "firecrawl"}
        assert our_tools.issubset(KNOWN_TOOLS)

    def test_openclaw_blacklisted(self):
        assert "openclaw" in BLACKLISTED_TOOLS

    def test_min_score_reasonable(self):
        assert 3 <= MIN_SCORE <= 8


class TestDiscoveryInit:
    """Scenario: 初始化."""

    def test_creates_dir(self, discovery, tmp_path):
        assert (tmp_path / "_system" / "tools").is_dir()

    def test_no_initial_discoveries(self, discovery):
        result = discovery.get_latest_discoveries()
        assert result["searched"] == 0
        assert result["recommended"] == []


class TestFiltering:
    """Scenario: 搜尋結果過濾."""

    def test_filter_known_tools(self, discovery):
        results = [
            {"url": "https://github.com/searxng/searxng", "title": "SearXNG", "content": ""},
            {"url": "https://github.com/new/tool", "title": "NewTool AI", "content": ""},
        ]
        filtered = discovery._filter_results(results)
        # searxng should be filtered out
        assert all("searxng" not in c["title"].lower() for c in filtered)

    def test_filter_blacklisted(self, discovery):
        results = [
            {"url": "https://github.com/openclaw/core", "title": "OpenClaw", "content": ""},
            {"url": "https://github.com/new/tool", "title": "SafeTool", "content": ""},
        ]
        filtered = discovery._filter_results(results)
        assert all("openclaw" not in c["title"].lower() for c in filtered)

    def test_filter_dedup(self, discovery):
        results = [
            {"url": "https://github.com/foo/bar", "title": "FooBar", "content": ""},
            {"url": "https://github.com/foo/bar", "title": "FooBar", "content": ""},
        ]
        filtered = discovery._filter_results(results)
        assert len(filtered) == 1

    def test_filter_prefers_github(self, discovery):
        results = [
            {"url": "https://github.com/new/tool", "title": "NewTool", "content": "AI"},
            {"url": "https://random-blog.com/article", "title": "Blog", "content": "AI"},
        ]
        filtered = discovery._filter_results(results)
        # 只保留 GitHub 等技術來源
        urls = [c["url"] for c in filtered]
        assert "https://github.com/new/tool" in urls


class TestScoring:
    """Scenario: DSE 風格評分."""

    def test_github_url_bonus(self, discovery):
        score = discovery._score_candidate({
            "title": "Something",
            "url": "https://github.com/foo/bar",
            "content": "",
        })
        assert score >= 2

    def test_self_hosted_bonus(self, discovery):
        s1 = discovery._score_candidate({
            "title": "Self-hosted AI tool",
            "url": "https://github.com/foo/bar",
            "content": "free open source docker",
        })
        s2 = discovery._score_candidate({
            "title": "Some tool",
            "url": "https://github.com/foo/bar",
            "content": "",
        })
        assert s1 > s2

    def test_security_concern_penalty(self, discovery):
        s1 = discovery._score_candidate({
            "title": "Good tool",
            "url": "https://github.com/foo/bar",
            "content": "self-hosted free",
        })
        s2 = discovery._score_candidate({
            "title": "Bad tool vulnerability",
            "url": "https://github.com/foo/bar",
            "content": "CVE exploit malicious",
        })
        assert s1 > s2

    def test_max_score_is_10(self, discovery):
        score = discovery._score_candidate({
            "title": "Self-hosted AI LLM docker tool 2026",
            "url": "https://github.com/foo/bar",
            "content": "free open source Apple Silicon M4 ARM",
        })
        assert score <= 10


class TestPersistence:
    """Scenario: 發現結果持久化."""

    def test_save_and_load(self, discovery):
        record = {
            "timestamp": "2026-02-28T05:00:00",
            "searched": 6,
            "found": 3,
            "recommended": [
                {"title": "NewTool", "score": 8},
            ],
        }
        discovery._save_discovery(record)

        latest = discovery.get_latest_discoveries()
        assert latest["searched"] == 6
        assert len(latest["recommended"]) == 1

    def test_max_30_records(self, discovery):
        for i in range(35):
            discovery._save_discovery({
                "timestamp": f"2026-02-{i:02d}",
                "searched": 1,
                "found": 0,
                "recommended": [],
            })
        all_records = discovery.get_all_discoveries()
        assert len(all_records) <= 30

    def test_get_all_discoveries(self, discovery):
        discovery._save_discovery({"timestamp": "1", "searched": 1, "found": 0, "recommended": []})
        discovery._save_discovery({"timestamp": "2", "searched": 2, "found": 0, "recommended": []})
        all_records = discovery.get_all_discoveries()
        assert len(all_records) == 2
