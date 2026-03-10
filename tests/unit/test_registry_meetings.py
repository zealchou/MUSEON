"""Unit tests for Registry Manager — Meetings & Action Items (Phase 3)."""

import os
import tempfile
from pathlib import Path

import pytest

from museon.registry.registry_manager import RegistryManager


@pytest.fixture
def data_dir(tmp_path):
    return str(tmp_path / "data")


@pytest.fixture
def m(data_dir):
    return RegistryManager(data_dir=data_dir, user_id="test_user")


# ═══════════════════════════════════════
# Meetings CRUD
# ═══════════════════════════════════════

class TestMeetings:

    def test_add_meeting(self, m):
        mid = m.add_meeting(
            title="符大哥討論 Museon 功能",
            summary="討論了 Skill Hub 與 CRM 整合",
            meeting_date="2026-03-09",
            participants=["符大哥", "Zeal"],
            source="whisper",
        )
        assert mid is not None
        assert mid.startswith("mtg_")

    def test_get_meeting(self, m):
        mid = m.add_meeting(
            title="每週站會",
            summary="進度追蹤",
            duration_min=30,
        )
        mtg = m.get_meeting(mid)
        assert mtg is not None
        assert mtg["title"] == "每週站會"
        assert mtg["duration_min"] == 30
        assert mtg["source"] == "manual"

    def test_query_meetings_by_date(self, m):
        m.add_meeting(title="一月會議", meeting_date="2026-01-15")
        m.add_meeting(title="三月會議", meeting_date="2026-03-09")
        m.add_meeting(title="四月會議", meeting_date="2026-04-01")

        march = m.query_meetings(
            date_from="2026-03-01", date_to="2026-03-31"
        )
        assert len(march) == 1
        assert march[0]["title"] == "三月會議"

    def test_query_meetings_by_keyword(self, m):
        m.add_meeting(title="Skill Hub 架構", summary="討論技能樹")
        m.add_meeting(title="行銷策略", summary="品牌定位")

        results = m.query_meetings(keyword="Skill")
        assert len(results) == 1
        assert "Skill" in results[0]["title"]

    def test_meeting_pending_index(self, m):
        m.add_meeting(title="索引測試會議")
        pending = m.get_pending_indexes()
        meeting_indexes = [
            p for p in pending if p["doc_type"] == "meeting"
        ]
        assert len(meeting_indexes) == 1

    def test_store_meeting_file(self, m, tmp_path):
        # 建立一個假的逐字稿
        transcript = tmp_path / "transcript.txt"
        transcript.write_text("逐字稿內容", encoding="utf-8")

        dest = m.store_meeting_file(str(transcript))
        assert dest is not None
        assert Path(dest).exists()
        assert "meetings" in dest

    def test_store_missing_file(self, m):
        dest = m.store_meeting_file("/nonexistent/file.txt")
        assert dest is None


# ═══════════════════════════════════════
# Action Items CRUD
# ═══════════════════════════════════════

class TestActionItems:

    def test_add_action_item(self, m):
        mid = m.add_meeting(title="來源會議")
        aid = m.add_action_item(
            task="完成旅行社工作流 prototype",
            meeting_id=mid,
            assignee="符大哥",
            due_date="2026-03-12",
        )
        assert aid is not None
        assert aid.startswith("ai_")

    def test_get_action_item(self, m):
        aid = m.add_action_item(
            task="完成報告",
            assignee="Zeal",
            due_date="2026-03-15",
            priority=1,
        )
        item = m.get_action_item(aid)
        assert item is not None
        assert item["task"] == "完成報告"
        assert item["assignee"] == "Zeal"
        assert item["status"] == "pending"
        assert item["priority"] == 1

    def test_update_action_item_done(self, m):
        aid = m.add_action_item(task="測試任務")
        result = m.update_action_item_status(aid, "done")
        assert result is True

        item = m.get_action_item(aid)
        assert item["status"] == "done"
        assert item["completed_at"] is not None

    def test_update_action_item_in_progress(self, m):
        aid = m.add_action_item(task="進行中任務")
        m.update_action_item_status(aid, "in_progress")

        item = m.get_action_item(aid)
        assert item["status"] == "in_progress"
        assert item["completed_at"] is None

    def test_query_action_items_by_status(self, m):
        m.add_action_item(task="待辦 1")
        aid2 = m.add_action_item(task="待辦 2")
        m.update_action_item_status(aid2, "done")

        pending = m.query_action_items(status="pending")
        assert len(pending) == 1
        assert pending[0]["task"] == "待辦 1"

    def test_query_action_items_by_assignee(self, m):
        m.add_action_item(task="A 的事", assignee="符大哥")
        m.add_action_item(task="B 的事", assignee="Zeal")

        results = m.query_action_items(assignee="符大哥")
        assert len(results) == 1
        assert results[0]["assignee"] == "符大哥"

    def test_query_action_items_by_meeting(self, m):
        mid = m.add_meeting(title="來源會議")
        m.add_action_item(task="會議中任務", meeting_id=mid)
        m.add_action_item(task="獨立任務")

        results = m.query_action_items(meeting_id=mid)
        assert len(results) == 1
        assert results[0]["task"] == "會議中任務"
