"""Tests for storage_backend.py — 原子寫入存儲後端.

依據 SIX_LAYER_MEMORY BDD Spec §6 的 BDD scenarios 驗證。
"""

import json
import os
import pytest
import tempfile

from museon.memory.storage_backend import LocalStorageBackend


@pytest.fixture
def workspace(tmp_path):
    """臨時工作目錄."""
    return str(tmp_path / "workspace")


@pytest.fixture
def backend(workspace):
    """LocalStorageBackend 實例."""
    return LocalStorageBackend(workspace)


# ═══════════════════════════════════════════
# Write Tests
# ═══════════════════════════════════════════


class TestWrite:
    """原子寫入測試."""

    def test_write_creates_file(self, backend, workspace):
        """BDD: 寫入建立 JSON 檔案."""
        data = {"key": "value"}
        assert backend.write("user1", "L0_buffer", "test.json", data)
        path = os.path.join(workspace, "user1", "L0_buffer", "test.json")
        assert os.path.exists(path)

    def test_write_content_correct(self, backend, workspace):
        """BDD: 寫入內容正確."""
        data = {"key": "value", "nested": {"a": 1}}
        backend.write("user1", "L0_buffer", "test.json", data)
        path = os.path.join(workspace, "user1", "L0_buffer", "test.json")
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == data

    def test_write_creates_directories(self, backend, workspace):
        """BDD: 目錄自動建立."""
        data = {"test": True}
        assert backend.write("new_user", "deep/nested", "test.json", data)
        path = os.path.join(workspace, "new_user", "deep/nested", "test.json")
        assert os.path.exists(path)

    def test_write_overwrite(self, backend):
        """BDD: 覆寫已存在的檔案."""
        backend.write("user1", "L0_buffer", "test.json", {"v": 1})
        backend.write("user1", "L0_buffer", "test.json", {"v": 2})
        data = backend.read("user1", "L0_buffer", "test.json")
        assert data["v"] == 2

    def test_write_chinese_content(self, backend):
        """BDD: 中文內容正確寫入."""
        data = {"content": "這是中文測試"}
        backend.write("user1", "L0_buffer", "cn.json", data)
        loaded = backend.read("user1", "L0_buffer", "cn.json")
        assert loaded["content"] == "這是中文測試"

    def test_write_system_user(self, backend, workspace):
        """BDD: _system 用戶路徑特殊處理."""
        data = {"system": True}
        backend.write("_system", "config", "test.json", data)
        path = os.path.join(workspace, "_system", "config", "test.json")
        assert os.path.exists(path)

    def test_no_tmp_files_after_write(self, backend, workspace):
        """BDD: 寫入後無殘留 tmp 檔案."""
        backend.write("user1", "L0_buffer", "test.json", {"a": 1})
        dir_path = os.path.join(workspace, "user1", "L0_buffer")
        files = os.listdir(dir_path)
        assert all(not f.endswith(".tmp") for f in files)


# ═══════════════════════════════════════════
# Read Tests
# ═══════════════════════════════════════════


class TestRead:
    """讀取測試."""

    def test_read_existing(self, backend):
        """BDD: 讀取已存在的檔案."""
        backend.write("user1", "L0_buffer", "test.json", {"key": "val"})
        data = backend.read("user1", "L0_buffer", "test.json")
        assert data == {"key": "val"}

    def test_read_nonexistent(self, backend):
        """BDD: 讀取不存在的檔案 → None."""
        assert backend.read("user1", "L0_buffer", "nope.json") is None

    def test_read_system_user(self, backend):
        """BDD: _system 用戶讀取."""
        backend.write("_system", "config", "test.json", {"sys": True})
        data = backend.read("_system", "config", "test.json")
        assert data["sys"] is True


# ═══════════════════════════════════════════
# Delete Tests
# ═══════════════════════════════════════════


class TestDelete:
    """軟刪除測試."""

    def test_delete_moves_to_trash(self, backend, workspace):
        """BDD: 刪除移至 .trash/."""
        backend.write("user1", "L0_buffer", "test.json", {"a": 1})
        assert backend.delete("user1", "L0_buffer", "test.json")

        # 原位置不存在
        assert not backend.exists("user1", "L0_buffer", "test.json")

        # .trash/ 有檔案
        trash_dir = os.path.join(workspace, ".trash")
        assert os.path.exists(trash_dir)
        files = os.listdir(trash_dir)
        assert len(files) == 1
        assert files[0].endswith("_test.json")

    def test_delete_nonexistent(self, backend):
        """BDD: 刪除不存在的檔案 → False."""
        assert not backend.delete("user1", "L0_buffer", "nope.json")

    def test_delete_recoverable(self, backend, workspace):
        """BDD: 軟刪除可恢復."""
        data = {"important": True}
        backend.write("user1", "L0_buffer", "important.json", data)
        backend.delete("user1", "L0_buffer", "important.json")

        # 從 .trash/ 讀取
        trash_dir = os.path.join(workspace, ".trash")
        files = os.listdir(trash_dir)
        trash_path = os.path.join(trash_dir, files[0])
        with open(trash_path, "r", encoding="utf-8") as f:
            recovered = json.load(f)
        assert recovered == data


# ═══════════════════════════════════════════
# List / Exists Tests
# ═══════════════════════════════════════════


class TestListAndExists:
    """列出與存在檢查測試."""

    def test_list_files(self, backend):
        """BDD: 列出目錄中的檔案."""
        backend.write("user1", "L0_buffer", "a.json", {"a": 1})
        backend.write("user1", "L0_buffer", "b.json", {"b": 2})
        files = backend.list_files("user1", "L0_buffer")
        assert len(files) == 2
        assert "a.json" in files
        assert "b.json" in files

    def test_list_empty_dir(self, backend):
        """BDD: 空目錄 → 空列表."""
        files = backend.list_files("user1", "empty_dir")
        assert files == []

    def test_exists_true(self, backend):
        """BDD: 存在 → True."""
        backend.write("user1", "L0_buffer", "test.json", {"a": 1})
        assert backend.exists("user1", "L0_buffer", "test.json")

    def test_exists_false(self, backend):
        """BDD: 不存在 → False."""
        assert not backend.exists("user1", "L0_buffer", "nope.json")


# ═══════════════════════════════════════════
# Append Tests (JSONL)
# ═══════════════════════════════════════════


class TestAppend:
    """JSONL Append 測試."""

    def test_append_creates_file(self, backend, workspace):
        """BDD: append 建立 JSONL 檔案."""
        backend.append("_system", "audit", "log.jsonl", {"action": "test"})
        path = os.path.join(workspace, "_system", "audit", "log.jsonl")
        assert os.path.exists(path)

    def test_append_multiple_lines(self, backend, workspace):
        """BDD: 多次 append 產出多行."""
        backend.append("_system", "audit", "log.jsonl", {"n": 1})
        backend.append("_system", "audit", "log.jsonl", {"n": 2})
        backend.append("_system", "audit", "log.jsonl", {"n": 3})

        path = os.path.join(workspace, "_system", "audit", "log.jsonl")
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["n"] == 1
        assert json.loads(lines[2])["n"] == 3
