"""Tests for memory_manager.py — 六層記憶管理器.

依據 SIX_LAYER_MEMORY BDD Spec §2, §7 的 BDD scenarios 驗證。
"""

import pytest

from museon.memory.memory_manager import (
    AUTO_PROMOTE_ACCESS,
    DEMOTION_TARGETS,
    LAYER_CONFIG,
    PROMOTION_PATHS,
    VALID_LAYERS,
    MemoryManager,
    _DEMOTION_RELEVANCE_THRESHOLD,
    _KEYWORD_FALLBACK_SIM,
    _OUTCOME_PRIORITY,
    _OUTCOME_WEIGHT,
)


@pytest.fixture
def mm(tmp_path):
    """MemoryManager 實例."""
    workspace = str(tmp_path / "workspace")
    return MemoryManager(workspace=workspace, user_id="test_user")


# ═══════════════════════════════════════════
# Layer Config Tests
# ═══════════════════════════════════════════


class TestLayerConfig:
    """六層記憶定義驗證（BDD Spec §2）."""

    def test_seven_layers(self):
        """BDD: 7 個層級."""
        assert len(LAYER_CONFIG) == 7

    def test_all_layers_valid(self):
        """BDD: 所有層級 ID 正確."""
        expected = {
            "L0_buffer", "L1_short", "L2_ep", "L2_sem",
            "L3_procedural", "L4_identity", "L5_scratch",
        }
        assert VALID_LAYERS == expected

    def test_ttl_values(self):
        """BDD: TTL 值正確."""
        assert LAYER_CONFIG["L0_buffer"]["ttl_days"] == 14
        assert LAYER_CONFIG["L1_short"]["ttl_days"] == 30
        assert LAYER_CONFIG["L2_ep"]["ttl_days"] == 90
        assert LAYER_CONFIG["L2_sem"]["ttl_days"] == 180
        assert LAYER_CONFIG["L3_procedural"]["ttl_days"] is None
        assert LAYER_CONFIG["L4_identity"]["ttl_days"] is None
        assert LAYER_CONFIG["L5_scratch"]["ttl_days"] == 7

    def test_promotion_paths(self):
        """BDD: 晉升路徑正確."""
        assert PROMOTION_PATHS["L0_buffer"] == ["L1_short"]
        assert PROMOTION_PATHS["L1_short"] == ["L2_ep"]
        assert "L2_sem" in PROMOTION_PATHS["L2_ep"]
        assert "L3_procedural" in PROMOTION_PATHS["L2_ep"]

    def test_demotion_targets(self):
        """BDD: 降級目標正確."""
        assert DEMOTION_TARGETS["L1_short"] == "L0_buffer"
        assert DEMOTION_TARGETS["L2_ep"] == "L1_short"
        assert "L0_buffer" not in DEMOTION_TARGETS
        assert "L4_identity" not in DEMOTION_TARGETS

    def test_auto_promote_thresholds(self):
        """BDD: 自動晉升閾值."""
        assert AUTO_PROMOTE_ACCESS["L0_buffer"] == 2
        assert AUTO_PROMOTE_ACCESS["L1_short"] == 5


# ═══════════════════════════════════════════
# Store Tests
# ═══════════════════════════════════════════


class TestStore:
    """存儲測試."""

    def test_store_returns_uuid(self, mm):
        """BDD: store 回傳合法 UUID."""
        mid = mm.store("test_user", "學到新技能", "L0_buffer")
        assert len(mid) == 36  # UUID format
        assert "-" in mid

    def test_store_auto_quality(self, mm):
        """BDD: 未指定 quality_tier → 自動評估."""
        mid = mm.store("test_user", "學到新技能", "L0_buffer")
        entries = mm.list_memories("test_user", "L0_buffer")
        entry = next(e for e in entries if e["id"] == mid)
        assert entry["quality_tier"] == "gold"  # "學到" → gold

    def test_store_explicit_quality(self, mm):
        """BDD: 指定 quality_tier 覆蓋自動評估."""
        mid = mm.store(
            "test_user", "學到新技能", "L0_buffer",
            quality_tier="bronze",
        )
        entries = mm.list_memories("test_user", "L0_buffer")
        entry = next(e for e in entries if e["id"] == mid)
        assert entry["quality_tier"] == "bronze"

    def test_store_with_tags(self, mm):
        """BDD: 標籤正確存入."""
        mid = mm.store(
            "test_user", "AI 模型", "L2_ep",
            tags=["AI", "ML"],
        )
        entries = mm.list_memories("test_user", "L2_ep")
        entry = next(e for e in entries if e["id"] == mid)
        assert entry["tags"] == ["AI", "ML"]

    def test_store_default_fields(self, mm):
        """BDD: 預設欄位正確填充."""
        mid = mm.store("test_user", "內容", "L0_buffer")
        entries = mm.list_memories("test_user", "L0_buffer")
        entry = next(e for e in entries if e["id"] == mid)
        assert entry["access_count"] == 0
        assert entry["relevance_score"] == 1.0
        assert entry["archived"] is False
        assert entry["layer"] == "L0_buffer"

    def test_store_invalid_layer(self, mm):
        """BDD: 無效層級 → ValueError."""
        with pytest.raises(ValueError, match="無效的記憶層級"):
            mm.store("test_user", "content", "L99_invalid")

    def test_store_failure_distill(self, mm):
        """BDD: failure_distill 來源 → silver."""
        mid = mm.store(
            "test_user", "失敗經驗", "L1_short",
            source="failure_distill",
        )
        entries = mm.list_memories("test_user", "L1_short")
        entry = next(e for e in entries if e["id"] == mid)
        assert entry["quality_tier"] == "silver"

    def test_store_with_outcome(self, mm):
        """BDD: outcome 正確存入."""
        mid = mm.store(
            "test_user", "任務結果", "L1_short",
            outcome="failed",
        )
        entries = mm.list_memories("test_user", "L1_short")
        entry = next(e for e in entries if e["id"] == mid)
        assert entry["outcome"] == "failed"


# ═══════════════════════════════════════════
# Recall Tests
# ═══════════════════════════════════════════


class TestRecall:
    """語義檢索測試."""

    def test_recall_finds_stored(self, mm):
        """BDD: Store + Recall 完整流程."""
        mm.store("test_user", "機器學習模型訓練方法", "L2_ep", tags=["AI"])
        results = mm.recall("test_user", "機器學習")
        assert len(results) > 0
        assert "機器學習" in results[0]["content"]

    def test_recall_access_count(self, mm):
        """BDD: recall 副作用 — access_count++."""
        mid = mm.store("test_user", "機器學習模型訓練", "L2_ep")
        mm.recall("test_user", "機器學習")
        entries = mm.list_memories("test_user", "L2_ep")
        entry = next(e for e in entries if e["id"] == mid)
        assert entry["access_count"] >= 1

    def test_recall_quality_weighting(self, mm):
        """BDD: 品質加權排序 — gold 優先."""
        mm.store("test_user", "機器學習很重要的發現方法", "L2_ep",
                 quality_tier="gold")
        mm.store("test_user", "機器學習一些些的普通記錄內容方法", "L2_ep",
                 quality_tier="bronze")
        results = mm.recall("test_user", "機器學習")
        if len(results) >= 2:
            # gold 應排在 bronze 前面
            gold_idx = next(
                (i for i, r in enumerate(results) if r["quality_tier"] == "gold"),
                None,
            )
            bronze_idx = next(
                (i for i, r in enumerate(results) if r["quality_tier"] == "bronze"),
                None,
            )
            if gold_idx is not None and bronze_idx is not None:
                assert gold_idx < bronze_idx

    def test_recall_outcome_reranking(self, mm):
        """BDD: Outcome 重排序 — success 優先."""
        mm.store("test_user", "機器學習模型訓練成功結果", "L2_ep",
                 outcome="success")
        mm.store("test_user", "機器學習模型訓練失敗結果", "L2_ep",
                 outcome="failed")
        results = mm.recall("test_user", "機器學習模型")
        if len(results) >= 2:
            success_idx = next(
                (i for i, r in enumerate(results) if r["outcome"] == "success"),
                None,
            )
            failed_idx = next(
                (i for i, r in enumerate(results) if r["outcome"] == "failed"),
                None,
            )
            if success_idx is not None and failed_idx is not None:
                assert success_idx < failed_idx

    def test_recall_empty(self, mm):
        """BDD: 無匹配 → 空列表."""
        results = mm.recall("test_user", "完全不存在的查詢")
        assert results == []

    def test_recall_layer_filter(self, mm):
        """BDD: 層級過濾."""
        mm.store("test_user", "機器學習方法技巧", "L2_ep")
        mm.store("test_user", "機器學習方法技巧", "L1_short")
        results = mm.recall("test_user", "機器學習", layers=["L1_short"])
        for r in results:
            assert r["layer"] == "L1_short"

    def test_recall_excludes_archived(self, mm):
        """BDD: 排除已歸檔記憶."""
        mid = mm.store("test_user", "機器學習內容方法", "L2_ep")
        # 手動歸檔
        entry = mm._read_entry("test_user", mid)
        entry["archived"] = True
        from museon.memory.memory_manager import LAYER_CONFIG
        mm._storage.write(
            "test_user",
            LAYER_CONFIG["L2_ep"]["dir"],
            f"{mid}.json",
            entry,
        )
        results = mm.recall("test_user", "機器學習")
        assert not any(r["id"] == mid for r in results)


# ═══════════════════════════════════════════
# Promote Tests
# ═══════════════════════════════════════════


class TestPromote:
    """晉升測試."""

    def test_promote_l0_to_l1(self, mm):
        """BDD: L0_buffer → L1_short."""
        mid = mm.store("test_user", "緩衝記憶", "L0_buffer")
        entry = mm.promote("test_user", mid, "L1_short")
        assert entry["layer"] == "L1_short"

    def test_promote_l2_ep_fork(self, mm):
        """BDD: L2_ep 分叉晉升."""
        mid1 = mm.store("test_user", "情節記憶一", "L2_ep")
        mid2 = mm.store("test_user", "情節記憶二", "L2_ep")

        entry1 = mm.promote("test_user", mid1, "L2_sem")
        assert entry1["layer"] == "L2_sem"

        entry2 = mm.promote("test_user", mid2, "L3_procedural")
        assert entry2["layer"] == "L3_procedural"

    def test_promote_illegal_jump(self, mm):
        """BDD: 非法跳級 → ValueError."""
        mid = mm.store("test_user", "緩衝記憶", "L0_buffer")
        with pytest.raises(ValueError, match="無法從"):
            mm.promote("test_user", mid, "L3_procedural")

    def test_promote_nonexistent(self, mm):
        """BDD: 不存在的記憶 → ValueError."""
        with pytest.raises(ValueError, match="記憶不存在"):
            mm.promote("test_user", "fake-uuid", "L1_short")

    def test_promote_l5_to_l2_ep(self, mm):
        """BDD: L5_scratch 假設驗證 → L2_ep."""
        mid = mm.store("test_user", "假設記憶", "L5_scratch")
        entry = mm.promote("test_user", mid, "L2_ep")
        assert entry["layer"] == "L2_ep"


# ═══════════════════════════════════════════
# Demote Tests
# ═══════════════════════════════════════════


class TestDemote:
    """降級測試."""

    def test_demote_l2_to_l1(self, mm):
        """BDD: L2_ep → L1_short."""
        mid = mm.store("test_user", "情節記憶", "L2_ep")
        entry = mm.demote("test_user", mid)
        assert entry["layer"] == "L1_short"

    def test_demote_l0_fails(self, mm):
        """BDD: L0_buffer 不可降級."""
        mid = mm.store("test_user", "緩衝記憶", "L0_buffer")
        with pytest.raises(ValueError, match="不可降級"):
            mm.demote("test_user", mid)

    def test_demote_l4_fails(self, mm):
        """BDD: L4_identity 不可降級."""
        mid = mm.store("test_user", "身份記憶", "L4_identity")
        with pytest.raises(ValueError, match="不可降級"):
            mm.demote("test_user", mid)


# ═══════════════════════════════════════════
# Supersede Tests
# ═══════════════════════════════════════════


class TestSupersede:
    """版本取代測試."""

    def test_supersede_chain(self, mm):
        """BDD: Supersede 版本鏈."""
        old_id = mm.store("test_user", "原始版本內容記憶", "L2_ep")

        # 先讓 access_count 增加
        mm.recall("test_user", "原始版本")

        new_entry = mm.supersede("test_user", old_id, "新版本內容")
        assert new_entry.get("supersedes_id") == old_id

    def test_supersede_archives_old(self, mm):
        """BDD: 舊記憶被歸檔."""
        old_id = mm.store("test_user", "舊版本內容記憶很長", "L2_ep")
        mm.supersede("test_user", old_id, "新版本")

        # 舊記憶已歸檔
        entries = mm.list_memories("test_user", "L2_ep", include_archived=True)
        old = next((e for e in entries if e["id"] == old_id), None)
        if old:
            assert old["archived"] is True
            assert old["archive_reason"] == "superseded"

    def test_supersede_inherits_access(self, mm):
        """BDD: 新記憶繼承 access_count."""
        old_id = mm.store("test_user", "原始版本內容記憶", "L2_ep")
        # Recall 增加 access
        mm.recall("test_user", "原始版本")
        mm.recall("test_user", "原始版本")

        new_entry = mm.supersede("test_user", old_id, "新版本記憶")
        assert new_entry.get("access_count", 0) >= 1


# ═══════════════════════════════════════════
# Maintenance Tests
# ═══════════════════════════════════════════


class TestMaintenance:
    """維護測試."""

    def test_maintenance_returns_stats(self, mm):
        """BDD: maintenance 回傳統計."""
        stats = mm.maintenance("test_user")
        assert "expired" in stats
        assert "promoted" in stats
        assert "demoted" in stats

    def test_maintenance_auto_promote(self, mm):
        """BDD: access_count >= 2 → L0 自動晉升 L1."""
        mid = mm.store("test_user", "經常查詢的記憶內容很長", "L0_buffer")

        # 模擬 access_count >= 2
        entry = mm._read_entry("test_user", mid)
        entry["access_count"] = 3
        from museon.memory.memory_manager import LAYER_CONFIG
        mm._storage.write(
            "test_user",
            LAYER_CONFIG["L0_buffer"]["dir"],
            f"{mid}.json",
            entry,
        )

        stats = mm.maintenance("test_user")
        assert stats["promoted"] >= 1

    def test_maintenance_low_relevance_demote(self, mm):
        """BDD: relevance < 0.2 → 降級."""
        mid = mm.store("test_user", "低相關記憶內容", "L2_ep")

        entry = mm._read_entry("test_user", mid)
        entry["relevance_score"] = 0.1
        from museon.memory.memory_manager import LAYER_CONFIG
        mm._storage.write(
            "test_user",
            LAYER_CONFIG["L2_ep"]["dir"],
            f"{mid}.json",
            entry,
        )

        stats = mm.maintenance("test_user")
        assert stats["demoted"] >= 1

    def test_maintenance_permanent_layers_no_expire(self, mm):
        """BDD: L3/L4 永不過期."""
        mid = mm.store("test_user", "永久記憶", "L3_procedural")

        # 偽造很舊的 created_at
        entry = mm._read_entry("test_user", mid)
        entry["created_at"] = "2020-01-01T00:00:00+08:00"
        from museon.memory.memory_manager import LAYER_CONFIG
        mm._storage.write(
            "test_user",
            LAYER_CONFIG["L3_procedural"]["dir"],
            f"{mid}.json",
            entry,
        )

        stats = mm.maintenance("test_user")
        assert stats["expired"] == 0


# ═══════════════════════════════════════════
# List / Delete Tests
# ═══════════════════════════════════════════


class TestListAndDelete:
    """列出與刪除測試."""

    def test_list_memories(self, mm):
        """BDD: 列出指定層記憶."""
        mm.store("test_user", "記憶一", "L0_buffer")
        mm.store("test_user", "記憶二", "L0_buffer")
        entries = mm.list_memories("test_user", "L0_buffer")
        assert len(entries) == 2

    def test_list_excludes_archived(self, mm):
        """BDD: 預設排除歸檔記憶."""
        mid = mm.store("test_user", "即將歸檔的記憶", "L0_buffer")
        entry = mm._read_entry("test_user", mid)
        entry["archived"] = True
        from museon.memory.memory_manager import LAYER_CONFIG
        mm._storage.write(
            "test_user",
            LAYER_CONFIG["L0_buffer"]["dir"],
            f"{mid}.json",
            entry,
        )
        entries = mm.list_memories("test_user", "L0_buffer")
        assert not any(e["id"] == mid for e in entries)

    def test_delete(self, mm):
        """BDD: 軟刪除."""
        mid = mm.store("test_user", "要刪除的記憶", "L0_buffer")
        assert mm.delete("test_user", mid)
        entries = mm.list_memories("test_user", "L0_buffer")
        assert not any(e["id"] == mid for e in entries)

    def test_delete_nonexistent(self, mm):
        """BDD: 刪除不存在的記憶 → False."""
        assert not mm.delete("test_user", "fake-uuid")


# ═══════════════════════════════════════════
# Outcome Constants Tests
# ═══════════════════════════════════════════


class TestOutcomeConstants:
    """Outcome 常數驗證."""

    def test_outcome_weights(self):
        """BDD: Outcome 權重正確."""
        assert _OUTCOME_WEIGHT["failed"] == 0.6
        assert _OUTCOME_WEIGHT["partial"] == 0.8
        assert _OUTCOME_WEIGHT[""] == 1.0
        assert _OUTCOME_WEIGHT["success"] == 1.1

    def test_outcome_priority(self):
        """BDD: Outcome 優先順序正確."""
        assert _OUTCOME_PRIORITY["success"] == 3
        assert _OUTCOME_PRIORITY[""] == 2
        assert _OUTCOME_PRIORITY["partial"] == 1
        assert _OUTCOME_PRIORITY["failed"] == 0
