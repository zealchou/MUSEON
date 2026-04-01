"""AnimaChangelog 單元測試.

Project Epigenesis 迭代 1：ANIMA_USER 差分版本追蹤。
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from museon.pulse.anima_changelog import (
    AnimaChangelog,
    compute_diff,
    IGNORED_PATHS,
    MAX_DIFFS_PER_RECORD,
)


# ═══════════════════════════════════════════
# compute_diff 測試
# ═══════════════════════════════════════════


class TestComputeDiff:
    """compute_diff() 純函式測試."""

    def test_no_change(self):
        """完全相同的 dict → 空 diff."""
        old = {"a": 1, "b": "hello"}
        new = {"a": 1, "b": "hello"}
        assert compute_diff(old, new) == []

    def test_scalar_change(self):
        """標量欄位變化."""
        old = {"name": "Alice", "age": 30}
        new = {"name": "Alice", "age": 31}
        diffs = compute_diff(old, new)
        assert len(diffs) == 1
        assert diffs[0]["path"] == "age"
        assert diffs[0]["old"] == 30
        assert diffs[0]["new"] == 31

    def test_nested_change(self):
        """巢狀 dict 變化."""
        old = {"relationship": {"trust_level": "building", "total": 10}}
        new = {"relationship": {"trust_level": "growing", "total": 10}}
        diffs = compute_diff(old, new)
        assert len(diffs) == 1
        assert diffs[0]["path"] == "relationship.trust_level"
        assert diffs[0]["old"] == "building"
        assert diffs[0]["new"] == "growing"

    def test_new_field_added(self):
        """新增欄位."""
        old = {"a": 1}
        new = {"a": 1, "b": 2}
        diffs = compute_diff(old, new)
        assert len(diffs) == 1
        assert diffs[0]["path"] == "b"
        assert diffs[0]["old"] is None
        assert diffs[0]["new"] == 2

    def test_field_removed(self):
        """移除欄位."""
        old = {"a": 1, "b": 2}
        new = {"a": 1}
        diffs = compute_diff(old, new)
        assert len(diffs) == 1
        assert diffs[0]["path"] == "b"
        assert diffs[0]["old"] == 2
        assert diffs[0]["new"] is None

    def test_old_is_none(self):
        """old_data 為 None（首次寫入）."""
        new = {"a": 1, "b": "hello"}
        diffs = compute_diff(None, new)
        assert len(diffs) == 2

    def test_ignored_paths(self):
        """忽略的欄位路徑不記入 diff."""
        old = {"relationship": {"last_interaction": "2026-01-01", "trust_level": "building"}}
        new = {"relationship": {"last_interaction": "2026-03-23", "trust_level": "growing"}}
        diffs = compute_diff(old, new)
        paths = [d["path"] for d in diffs]
        assert "relationship.last_interaction" not in paths
        assert "relationship.trust_level" in paths

    def test_large_list_summarized(self):
        """大型 list 只記摘要."""
        old = {"tags": ["a", "b"]}
        new = {"tags": list(range(20))}
        diffs = compute_diff(old, new)
        assert len(diffs) == 1
        assert "list:20" in str(diffs[0]["new"])

    def test_truncation_at_max(self):
        """超過 MAX_DIFFS_PER_RECORD 截斷."""
        old = {f"field_{i}": i for i in range(MAX_DIFFS_PER_RECORD + 10)}
        new = {f"field_{i}": i + 1 for i in range(MAX_DIFFS_PER_RECORD + 10)}
        diffs = compute_diff(old, new)
        assert len(diffs) <= MAX_DIFFS_PER_RECORD + 1
        assert diffs[-1]["path"] == "_truncated"


# ═══════════════════════════════════════════
# AnimaChangelog 整合測試
# ═══════════════════════════════════════════


@pytest.fixture
def tmp_data_dir():
    """建立臨時資料目錄."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def changelog(tmp_data_dir):
    """建立 AnimaChangelog 實例."""
    return AnimaChangelog(data_dir=tmp_data_dir)


class TestAnimaChangelogRecord:
    """record() 寫入測試."""

    def test_record_basic_diff(self, changelog, tmp_data_dir):
        """基本差分記錄."""
        old = {"relationship": {"trust_level": "building"}}
        new = {"relationship": {"trust_level": "growing"}}
        count = changelog.record(old, new, trigger="observe_user")
        assert count == 1

        # 驗證 JSONL 檔案
        path = Path(tmp_data_dir) / "anima" / "anima_user_changelog.jsonl"
        assert path.exists()
        with open(path) as f:
            record = json.loads(f.readline())
        assert record["trigger"] == "observe_user"
        assert record["diff_count"] == 1
        assert record["diffs"][0]["path"] == "relationship.trust_level"

    def test_record_no_change(self, changelog):
        """無變化不寫入."""
        old = {"a": 1}
        new = {"a": 1}
        count = changelog.record(old, new)
        assert count == 0
        assert changelog.get_record_count() == 0

    def test_record_multiple(self, changelog):
        """多次記錄追加."""
        changelog.record({"a": 1}, {"a": 2})
        changelog.record({"a": 2}, {"a": 3})
        changelog.record({"a": 3}, {"a": 4})
        assert changelog.get_record_count() == 3

    def test_record_first_time(self, changelog):
        """首次寫入（old=None）."""
        count = changelog.record(None, {"name": "Zeal", "age": 30})
        assert count == 2  # name + age


class TestAnimaChangelogQuery:
    """查詢 API 測試."""

    def test_get_changes_by_field(self, changelog):
        """按欄位查詢變化歷史."""
        changelog.record(
            {"relationship": {"trust_level": "initial"}},
            {"relationship": {"trust_level": "building"}},
        )
        changelog.record(
            {"relationship": {"trust_level": "building"}},
            {"relationship": {"trust_level": "growing"}},
        )

        changes = changelog.get_changes("relationship.trust_level")
        assert len(changes) == 2
        assert changes[0]["old"] == "initial"
        assert changes[0]["new"] == "building"
        assert changes[1]["old"] == "building"
        assert changes[1]["new"] == "growing"

    def test_get_changes_by_prefix(self, changelog):
        """按路徑前綴查詢."""
        changelog.record(
            {"eight_primals": {"curiosity": 30, "boundary": 50}},
            {"eight_primals": {"curiosity": 35, "boundary": 50}},
        )
        changes = changelog.get_changes_by_prefix("eight_primals")
        assert len(changes) == 1
        assert changes[0]["path"] == "eight_primals.curiosity"

    def test_get_changes_respects_days(self, changelog):
        """回看天數限制."""
        # 手動寫入一筆舊記錄
        old_ts = (datetime.now() - timedelta(days=60)).isoformat()
        old_record = {
            "ts": old_ts,
            "trigger": "test",
            "diff_count": 1,
            "diffs": [{"path": "name", "old": "A", "new": "B"}],
        }
        path = changelog._changelog_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(old_record) + "\n")

        # 新記錄
        changelog.record({"name": "B"}, {"name": "C"})

        # 30 天內只有 1 筆
        changes = changelog.get_changes("name", days=30)
        assert len(changes) == 1
        assert changes[0]["new"] == "C"

        # 90 天內有 2 筆
        changes = changelog.get_changes("name", days=90)
        assert len(changes) == 2


class TestAnimaChangelogEvolution:
    """演化摘要測試."""

    def test_evolution_summary_basic(self, changelog):
        """基本演化摘要."""
        # 信任升級
        changelog.record(
            {"relationship": {"trust_level": "initial", "total_interactions": 0}},
            {"relationship": {"trust_level": "building", "total_interactions": 5}},
        )
        # 八原語變化
        changelog.record(
            {"eight_primals": {"curiosity": 30}, "relationship": {"total_interactions": 5}},
            {"eight_primals": {"curiosity": 45}, "relationship": {"total_interactions": 50}},
        )

        summary = changelog.get_evolution_summary(months=1)
        assert summary["total_changes"] > 0
        assert len(summary["trust_evolution"]) == 1
        assert summary["trust_evolution"][0]["from"] == "initial"
        assert summary["trust_evolution"][0]["to"] == "building"
        # 50 次互動里程碑
        assert any(
            n.get("type") == "milestone"
            for n in summary["notable_transitions"]
        )


class TestAnimaChangelogCompression:
    """壓縮測試."""

    def test_compress_old_records(self, changelog):
        """壓縮超過閾值的舊記錄."""
        # 手動寫入 5 筆舊記錄（120 天前）
        old_base = datetime.now() - timedelta(days=120)
        path = changelog._changelog_path
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "a") as f:
            for i in range(5):
                ts = (old_base + timedelta(hours=i)).isoformat()
                record = {
                    "ts": ts,
                    "trigger": "test",
                    "diff_count": 1,
                    "diffs": [{"path": f"field_{i}", "old": i, "new": i + 1}],
                }
                f.write(json.dumps(record) + "\n")

        # 加一筆新記錄
        changelog.record({"recent": 1}, {"recent": 2})

        # 壓縮前 6 筆
        assert changelog.get_record_count() == 6

        removed = changelog.compress_old_records(threshold_days=90)
        assert removed > 0

        # 壓縮後：舊記錄按天合併（5 筆可能跨 1-2 天）+ 1 筆新記錄
        # 因執行時間不同，舊記錄可能落在 1 或 2 個日期，所以是 2 或 3 筆
        count = changelog.get_record_count()
        assert 2 <= count <= 3
