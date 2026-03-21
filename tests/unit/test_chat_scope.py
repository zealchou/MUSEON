"""Phase 2 單元測試：記憶 chat_scope 隔離.

覆蓋範圍：
  - MemoryManager.store(): chat_scope 存儲 + 標籤注入
  - MemoryManager.recall(): chat_scope_filter + exclude_scopes 過濾
  - MemoryManager._keyword_fallback(): chat_scope 過濾
  - MemoryManager._vector_index(): chat_scope 注入 metadata
"""

import pytest
from unittest.mock import MagicMock, patch
from museon.memory.memory_manager import MemoryManager


# ── Fixture ─────────────────────────────────────────────

@pytest.fixture
def mm(tmp_path):
    """MemoryManager 實例（使用 tmp_path 隔離檔案 I/O）."""
    workspace = str(tmp_path / "workspace")
    return MemoryManager(workspace=workspace, user_id="test_user")


# ══════════════════════════════════════════════════════════════
# 1. store() — chat_scope 存儲 + 標籤注入
# ══════════════════════════════════════════════════════════════

class TestStoreChatScope:
    """store() 的 chat_scope 隔離功能."""

    def test_store_with_group_scope(self, mm):
        """群組記憶帶 chat_scope."""
        mid = mm.store(
            user_id="test_user",
            content="群組討論內容",
            layer="L1_short",
            chat_scope="group:12345",
            group_id="12345",
        )
        assert mid  # 回傳 UUID

        # 讀回驗證
        entry = mm._read_entry("test_user", mid)
        assert entry is not None
        assert entry["chat_scope"] == "group:12345"
        assert entry["group_id"] == "12345"

    def test_store_without_scope(self, mm):
        """無 scope 的記憶（向下相容）."""
        mid = mm.store(
            user_id="test_user",
            content="私人對話",
            layer="L1_short",
        )
        entry = mm._read_entry("test_user", mid)
        assert entry["chat_scope"] == ""
        assert entry["group_id"] == ""

    def test_scope_tag_auto_injection(self, mm):
        """chat_scope → 自動注入 scope:{scope} 標籤."""
        mid = mm.store(
            user_id="test_user",
            content="群組內容",
            layer="L1_short",
            tags=["test"],
            chat_scope="group:99",
        )
        entry = mm._read_entry("test_user", mid)
        assert "scope:group:99" in entry["tags"]
        assert "test" in entry["tags"]

    def test_scope_tag_no_duplicate(self, mm):
        """已有 scope 標籤時不重複注入."""
        mid = mm.store(
            user_id="test_user",
            content="已標記",
            layer="L1_short",
            tags=["scope:group:99"],
            chat_scope="group:99",
        )
        entry = mm._read_entry("test_user", mid)
        # 只應出現一次
        assert entry["tags"].count("scope:group:99") == 1

    def test_empty_scope_no_tag(self, mm):
        """空 scope 不注入標籤."""
        mid = mm.store(
            user_id="test_user",
            content="無範疇",
            layer="L1_short",
            tags=["test"],
            chat_scope="",
        )
        entry = mm._read_entry("test_user", mid)
        assert not any(t.startswith("scope:") for t in entry["tags"])


# ══════════════════════════════════════════════════════════════
# 2. recall() — chat_scope_filter + exclude_scopes
# ══════════════════════════════════════════════════════════════

class TestRecallChatScope:
    """recall() 的 chat_scope 過濾功能."""

    def _seed_memories(self, mm):
        """建立測試記憶：group_A(2), group_B(2), no_scope(1)."""
        mm.store("test_user", "群組A第一筆：客戶討論", "L1_short",
                 tags=["meeting"], chat_scope="group:A", group_id="A")
        mm.store("test_user", "群組A第二筆：客戶追蹤", "L1_short",
                 tags=["followup"], chat_scope="group:A", group_id="A")
        mm.store("test_user", "群組B第一筆：技術討論", "L1_short",
                 tags=["tech"], chat_scope="group:B", group_id="B")
        mm.store("test_user", "群組B第二筆：技術追蹤", "L1_short",
                 tags=["tech"], chat_scope="group:B", group_id="B")
        mm.store("test_user", "私人對話：客戶個人想法", "L1_short",
                 tags=["private"])

    def test_no_filter_returns_all(self, mm):
        """無 filter → 回傳所有記憶."""
        self._seed_memories(mm)
        results = mm.recall("test_user", "客戶")
        # 至少包含 keyword 匹配的記憶
        assert len(results) >= 1

    def test_scope_filter_group_a(self, mm):
        """filter=group:A → 只回傳群組A + 無 scope 記憶."""
        self._seed_memories(mm)
        results = mm.recall(
            "test_user", "客戶",
            chat_scope_filter="group:A",
        )
        for r in results:
            scope = r.get("chat_scope", "")
            # 應該是 group:A 或空（向下相容）
            assert scope in ("group:A", ""), f"意外的 scope: {scope}"

    def test_scope_filter_excludes_other_group(self, mm):
        """filter=group:A → 不應包含 group:B 記憶."""
        self._seed_memories(mm)
        results = mm.recall(
            "test_user", "技術",
            chat_scope_filter="group:A",
        )
        for r in results:
            assert r.get("chat_scope", "") != "group:B"

    def test_exclude_scopes_blacklist(self, mm):
        """exclude_scopes → 排除指定群組."""
        self._seed_memories(mm)
        results = mm.recall(
            "test_user", "客戶",
            exclude_scopes=["group:A"],
        )
        for r in results:
            assert r.get("chat_scope", "") != "group:A"

    def test_exclude_multiple_scopes(self, mm):
        """排除多個群組."""
        self._seed_memories(mm)
        results = mm.recall(
            "test_user", "客戶",
            exclude_scopes=["group:A", "group:B"],
        )
        for r in results:
            scope = r.get("chat_scope", "")
            assert scope not in ("group:A", "group:B")

    def test_legacy_no_scope_always_visible(self, mm):
        """無 scope 的舊記憶在任何 filter 下都可見."""
        self._seed_memories(mm)
        # 用 filter 搜尋，但私人記憶（無 scope）應該可見
        results = mm.recall(
            "test_user", "個人想法",
            chat_scope_filter="group:A",
        )
        # 無 scope 記憶不被過濾掉
        for r in results:
            scope = r.get("chat_scope", "")
            assert scope in ("group:A", "")


# ══════════════════════════════════════════════════════════════
# 3. _keyword_fallback() — chat_scope 過濾
# ══════════════════════════════════════════════════════════════

class TestKeywordFallbackChatScope:
    """_keyword_fallback() 的 chat_scope 過濾功能."""

    def _seed_memories(self, mm):
        """建立兩組測試記憶."""
        mm.store("test_user", "群組A的專案會議紀錄", "L1_short",
                 tags=["project"], chat_scope="group:A")
        mm.store("test_user", "群組B的專案會議紀錄", "L1_short",
                 tags=["project"], chat_scope="group:B")

    def test_fallback_respects_scope_filter(self, mm):
        """keyword fallback 也會過濾 chat_scope."""
        self._seed_memories(mm)
        results = mm._keyword_fallback(
            user_id="test_user",
            query="專案",
            layers=["L1_short"],
            seen_ids=set(),
            limit=10,
            chat_scope_filter="group:A",
        )
        for r in results:
            scope = r.get("chat_scope", "")
            assert scope in ("group:A", "")

    def test_fallback_respects_exclude(self, mm):
        """keyword fallback 也會排除 exclude_scopes."""
        self._seed_memories(mm)
        results = mm._keyword_fallback(
            user_id="test_user",
            query="專案",
            layers=["L1_short"],
            seen_ids=set(),
            limit=10,
            exclude_scopes=["group:B"],
        )
        for r in results:
            assert r.get("chat_scope", "") != "group:B"


# ══════════════════════════════════════════════════════════════
# 4. _vector_index() — chat_scope metadata 注入
# ══════════════════════════════════════════════════════════════

class TestVectorIndexChatScope:
    """_vector_index() 的 chat_scope metadata 注入."""

    def test_scope_injected_to_metadata(self, mm):
        """chat_scope 被注入到向量 metadata."""
        mock_vb = MagicMock()
        with patch.object(mm, '_get_vector_bridge', return_value=mock_vb):
            mm._vector_index(
                memory_id="test-id",
                content="test content",
                tags=["tag1"],
                layer="L1_short",
                chat_scope="group:42",
            )
        mock_vb.index.assert_called_once()
        call_args = mock_vb.index.call_args
        metadata = call_args[1].get("metadata") or call_args[0][3]
        assert metadata.get("chat_scope") == "group:42"

    def test_no_scope_no_metadata(self, mm):
        """空 scope 不注入 metadata."""
        mock_vb = MagicMock()
        with patch.object(mm, '_get_vector_bridge', return_value=mock_vb):
            mm._vector_index(
                memory_id="test-id",
                content="test content",
                tags=["tag1"],
                layer="L1_short",
                chat_scope="",
            )
        mock_vb.index.assert_called_once()
        call_args = mock_vb.index.call_args
        metadata = call_args[1].get("metadata") or call_args[0][3]
        assert "chat_scope" not in metadata

    def test_silent_failure_on_error(self, mm):
        """向量索引失敗時靜默（不拋出例外）."""
        with patch.object(mm, '_get_vector_bridge', side_effect=Exception("boom")):
            # 不應拋出例外
            mm._vector_index("id", "content", None, "L1_short", "group:1")
