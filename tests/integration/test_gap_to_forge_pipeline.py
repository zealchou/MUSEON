"""Integration test: GapAccumulator → morphenix/notes → SkillDraftForger._collect_sources()

這個測試驗證端到端管線的接頭：
1. GapAccumulator 寫入的 scout_*.json 檔名格式能被 SkillDraftForger._collect_sources() 匹配
2. 三種前綴（gap_cluster / skill_optimize / crystal_insight）都能被正確掃描
3. 重複過濾邏輯正確（已處理的 source_file 不重複讀取）
"""
import json
import pytest
from pathlib import Path


def test_gap_note_consumed_by_forger(tmp_path):
    """Verify SkillDraftForger can find and read gap accumulator notes."""
    # Setup: create morphenix/notes directory with a gap note
    # NOTE: SkillDraftForger.__init__ builds paths as workspace / "data/_system/..."
    # so workspace should be the MUSEON root (tmp_path), not tmp_path/data
    notes_dir = tmp_path / "data" / "_system" / "morphenix" / "notes"
    notes_dir.mkdir(parents=True)

    note = {
        "type": "scout_gap_cluster",
        "topic": "test gap topic",
        "gap_identified": "test gap",
        "sample_queries": ["q1", "q2"],
        "suggested_skill": "test-skill",
        "source": "gap_accumulator",
        "created_at": "2026-04-05T12:00:00+00:00",
        "auto_propose": True,
    }
    (notes_dir / "scout_gap_cluster_20260405120000.json").write_text(
        json.dumps(note, ensure_ascii=False), encoding="utf-8"
    )

    # Also create skills_draft dir (empty, no previous drafts)
    (tmp_path / "data" / "_system" / "skills_draft").mkdir(parents=True)

    # Act: call _collect_sources with tmp workspace (MUSEON root)
    from museon.nightly.skill_draft_forger import SkillDraftForger
    forger = SkillDraftForger(workspace=tmp_path)
    sources = forger._collect_sources()

    # Assert: our note should be found
    assert len(sources) >= 1
    found = any(s.get("_source_file", "").startswith("scout_gap_cluster") for s in sources)
    assert found, f"Gap note not found in sources: {[s.get('_source_file') for s in sources]}"


def test_all_three_gap_prefixes_matched(tmp_path):
    """三種 GapAccumulator 前綴（gap_cluster / skill_optimize / crystal_insight）全部被匹配."""
    notes_dir = tmp_path / "data" / "_system" / "morphenix" / "notes"
    notes_dir.mkdir(parents=True)
    (tmp_path / "data" / "_system" / "skills_draft").mkdir(parents=True)

    ts = "20260405120000"
    prefixes = [
        ("scout_gap_cluster", "scout_gap_cluster"),
        ("scout_skill_optimize", "scout_skill_optimize"),
        ("scout_crystal_insight", "scout_crystal_insight"),
    ]
    for prefix, _ in prefixes:
        note = {
            "type": prefix,
            "topic": f"topic for {prefix}",
            "source": "gap_accumulator",
            "created_at": "2026-04-05T12:00:00+00:00",
        }
        (notes_dir / f"{prefix}_{ts}.json").write_text(
            json.dumps(note, ensure_ascii=False), encoding="utf-8"
        )

    from museon.nightly.skill_draft_forger import SkillDraftForger
    forger = SkillDraftForger(workspace=tmp_path)
    sources = forger._collect_sources()

    assert len(sources) == 3, f"期望 3 個 source，實際 {len(sources)}: {[s.get('_source_file') for s in sources]}"
    source_files = {s.get("_source_file", "") for s in sources}
    for prefix, _ in prefixes:
        assert any(f.startswith(prefix) for f in source_files), f"前綴 {prefix} 沒被匹配到"


def test_dedup_already_processed(tmp_path):
    """已有對應草稿的 source_file 不重複讀取."""
    notes_dir = tmp_path / "data" / "_system" / "morphenix" / "notes"
    notes_dir.mkdir(parents=True)
    draft_dir = tmp_path / "data" / "_system" / "skills_draft"
    draft_dir.mkdir(parents=True)

    # 建立 1 個 scout note
    note = {
        "type": "scout_gap_cluster",
        "topic": "already processed",
        "source": "gap_accumulator",
        "created_at": "2026-04-05T12:00:00+00:00",
    }
    note_name = "scout_gap_cluster_20260405000000.json"
    (notes_dir / note_name).write_text(json.dumps(note), encoding="utf-8")

    # 建立對應的 draft（標記 source_file = 該 note 的檔名）
    draft = {
        "id": "draft_20260405000000_test-skill",
        "mode": "forge_new",
        "source_file": note_name,
        "skill_name": "test-skill",
        "created_at": "2026-04-05T12:00:00+00:00",
        "status": "pending_qa",
    }
    (draft_dir / f"{draft['id']}.json").write_text(
        json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    from museon.nightly.skill_draft_forger import SkillDraftForger
    forger = SkillDraftForger(workspace=tmp_path)
    sources = forger._collect_sources()

    # 已有草稿的 note 不應該出現在 sources 中
    assert len(sources) == 0, (
        f"已處理的 note 不應再次出現，但 sources={[s.get('_source_file') for s in sources]}"
    )


def test_source_type_set_correctly(tmp_path):
    """_source_type 欄位應正確設定為 scout_note."""
    notes_dir = tmp_path / "data" / "_system" / "morphenix" / "notes"
    notes_dir.mkdir(parents=True)
    (tmp_path / "data" / "_system" / "skills_draft").mkdir(parents=True)

    note = {"type": "scout_gap_cluster", "source": "gap_accumulator"}
    (notes_dir / "scout_gap_cluster_20260405090000.json").write_text(
        json.dumps(note), encoding="utf-8"
    )

    from museon.nightly.skill_draft_forger import SkillDraftForger
    forger = SkillDraftForger(workspace=tmp_path)
    sources = forger._collect_sources()

    assert len(sources) == 1
    assert sources[0]["_source_type"] == "scout_note"
    assert sources[0]["_source_file"] == "scout_gap_cluster_20260405090000.json"
