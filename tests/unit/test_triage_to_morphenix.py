"""tests/unit/test_triage_to_morphenix.py

測試 triage_to_morphenix.drain_priority_queue_to_notes()：
1. 有 queue 時正確轉為 notes
2. queue 為空時返回 0
3. queue 檔案不存在時返回 0
4. 處理完後 queue 被清空
5. note 格式與現有 morphenix notes 一致
"""

import json
import pytest
from pathlib import Path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """建立模擬 MUSEON workspace。"""
    (tmp_path / "data" / "_system").mkdir(parents=True)
    return tmp_path


def _make_signal(signal_id: str = "abc12345", severity: str = "high") -> dict:
    return {
        "signal_id": signal_id,
        "created_at": "2026-03-31T00:00:00+00:00",
        "source": "skill_health_tracker",
        "skill_name": "darwin",
        "severity": severity,
        "signal_type": "skill_degraded",
        "title": f"darwin Skill 健康度低（{signal_id}）",
        "actionability": "prompt",
        "suggested_action": "降低輸出複雜度",
        "triage_action": "queued_for_priority_review",
        "context": {"health_score": 0.42, "threshold": 0.6},
    }


def _write_queue(workspace: Path, items: list) -> Path:
    queue_file = workspace / "data" / "_system" / "nightly_priority_queue.json"
    queue_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return queue_file


# ── 測試一：有 queue 時正確轉為 notes ──────────────────────────────────────────


def test_drains_queue_and_creates_notes(workspace):
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes

    signals = [_make_signal("aaa11111"), _make_signal("bbb22222")]
    _write_queue(workspace, signals)

    result = drain_priority_queue_to_notes(workspace)

    assert result["processed"] == 2
    assert result["notes_created"] == 2

    notes_dir = workspace / "_system" / "morphenix" / "notes"
    note_files = list(notes_dir.glob("triage_*.json"))
    assert len(note_files) == 2


def test_note_format_matches_existing_morphenix_schema(workspace):
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes

    _write_queue(workspace, [_make_signal("ccc33333")])
    drain_priority_queue_to_notes(workspace)

    notes_dir = workspace / "_system" / "morphenix" / "notes"
    note_file = next(notes_dir.glob("triage_*.json"))
    note = json.loads(note_file.read_text(encoding="utf-8"))

    # 必要欄位（與現有 mc_*_metacog_insight.json 一致）
    assert "id" in note
    assert "category" in note
    assert "content" in note
    assert "source" in note
    assert "created_at" in note
    assert "priority" in note

    # triage 特有欄位
    assert note["category"] == "triage_high"
    assert note["signal_id"] == "ccc33333"
    assert note["skill_name"] == "darwin"
    assert note["severity"] == "high"
    assert note["priority"] == "high"

    # content 應包含 title 和 suggested_action
    assert "darwin Skill 健康度低" in note["content"]
    assert "降低輸出複雜度" in note["content"]


# ── 測試二：queue 為空時返回 0 ────────────────────────────────────────────────


def test_empty_queue_returns_zero(workspace):
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes

    _write_queue(workspace, [])
    result = drain_priority_queue_to_notes(workspace)

    assert result["processed"] == 0
    assert result["notes_created"] == 0


# ── 測試三：queue 檔案不存在時返回 0 ──────────────────────────────────────────


def test_missing_queue_file_returns_zero(workspace):
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes

    # 確認 queue 檔案不存在
    queue_file = workspace / "data" / "_system" / "nightly_priority_queue.json"
    assert not queue_file.exists()

    result = drain_priority_queue_to_notes(workspace)

    assert result["processed"] == 0
    assert result["notes_created"] == 0


# ── 測試四：處理完後 queue 被清空 ─────────────────────────────────────────────


def test_queue_cleared_after_processing(workspace):
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes

    signals = [_make_signal("ddd44444"), _make_signal("eee55555")]
    queue_file = _write_queue(workspace, signals)

    drain_priority_queue_to_notes(workspace)

    remaining = json.loads(queue_file.read_text(encoding="utf-8"))
    assert remaining == []


# ── 測試五：多次呼叫不重複（queue 已清空則 notes 不增加）────────────────────


def test_idempotent_after_queue_cleared(workspace):
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes

    _write_queue(workspace, [_make_signal("fff66666")])

    result1 = drain_priority_queue_to_notes(workspace)
    result2 = drain_priority_queue_to_notes(workspace)

    assert result1["notes_created"] == 1
    assert result2["processed"] == 0
    assert result2["notes_created"] == 0

    notes_dir = workspace / "_system" / "morphenix" / "notes"
    assert len(list(notes_dir.glob("triage_*.json"))) == 1


# ── 測試六：severity → priority 對映正確 ─────────────────────────────────────


@pytest.mark.parametrize("severity,expected_priority", [
    ("critical", "critical"),
    ("high", "high"),
    ("medium", "medium"),
    ("low", "low"),
    ("info", "low"),
    ("unknown_sev", "high"),  # 未知 severity 預設 high
])
def test_severity_to_priority_mapping(workspace, severity, expected_priority):
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes

    signal = _make_signal("ggg77777", severity=severity)
    _write_queue(workspace, [signal])

    drain_priority_queue_to_notes(workspace)

    notes_dir = workspace / "_system" / "morphenix" / "notes"
    note_files = list(notes_dir.glob("triage_*.json"))
    if note_files:
        note = json.loads(note_files[0].read_text(encoding="utf-8"))
        assert note["priority"] == expected_priority


# ── 測試七：破損的 queue JSON 不崩潰 ─────────────────────────────────────────


def test_corrupted_queue_returns_zero(workspace):
    from museon.nightly.triage_to_morphenix import drain_priority_queue_to_notes

    queue_file = workspace / "data" / "_system" / "nightly_priority_queue.json"
    queue_file.write_text("{ not valid json {{", encoding="utf-8")

    result = drain_priority_queue_to_notes(workspace)

    assert result["processed"] == 0
    assert result["notes_created"] == 0
