"""Tests for quality_gate.py — gold/silver/bronze 三級品質閘門.

依據 SIX_LAYER_MEMORY BDD Spec §4 的 BDD scenarios 驗證。
"""

import pytest

from museon.memory.quality_gate import (
    MIN_CONTENT_LENGTH,
    QUALITY_WEIGHTS,
    VALID_TIERS,
    _GOLD_SOURCES,
    _SIGNAL_KEYWORDS,
    _SYSTEM_SOURCES,
    apply_weight,
    assess_quality,
)


# ═══════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════


class TestConstants:
    """常數定義驗證."""

    def test_three_tiers(self):
        """BDD: 三個品質等級."""
        assert len(VALID_TIERS) == 3
        assert "gold" in VALID_TIERS
        assert "silver" in VALID_TIERS
        assert "bronze" in VALID_TIERS

    def test_gold_weight(self):
        """BDD: gold 權重 1.5."""
        assert QUALITY_WEIGHTS["gold"] == 1.5

    def test_silver_weight(self):
        """BDD: silver 權重 1.0."""
        assert QUALITY_WEIGHTS["silver"] == 1.0

    def test_bronze_weight(self):
        """BDD: bronze 權重 0.5."""
        assert QUALITY_WEIGHTS["bronze"] == 0.5

    def test_22_signal_keywords(self):
        """BDD: 22 個信號關鍵字."""
        assert len(_SIGNAL_KEYWORDS) == 22

    def test_9_system_sources(self):
        """BDD: 9 個系統來源."""
        assert len(_SYSTEM_SOURCES) == 9

    def test_min_content_length(self):
        """BDD: 最小內容長度 20."""
        assert MIN_CONTENT_LENGTH == 20


# ═══════════════════════════════════════════
# Quality Assessment Tests
# ═══════════════════════════════════════════


class TestAssessQuality:
    """品質評估測試（BDD Spec §4.5）."""

    def test_failure_distill_is_silver(self):
        """BDD: failure_distill → silver（特例）."""
        assert assess_quality("自動記錄", "failure_distill") == "silver"

    def test_failure_distill_with_signal_keyword(self):
        """BDD: failure_distill 覆蓋信號關鍵字."""
        assert assess_quality("學到新技能", "failure_distill") == "silver"

    def test_system_source_wee_auto(self):
        """BDD: wee_auto → bronze."""
        assert assess_quality("自動記錄", "wee_auto") == "bronze"

    def test_system_source_system(self):
        """BDD: system → bronze."""
        assert assess_quality("自動記錄", "system") == "bronze"

    def test_system_source_nightly(self):
        """BDD: nightly → bronze."""
        assert assess_quality("重要內容", "nightly") == "bronze"

    def test_system_source_heartbeat(self):
        """BDD: heartbeat → bronze."""
        assert assess_quality("心跳", "heartbeat") == "bronze"

    def test_all_system_sources_bronze(self):
        """BDD: 所有系統來源 → bronze."""
        for src in _SYSTEM_SOURCES:
            assert assess_quality("任何內容", src) == "bronze", (
                f"source={src} should be bronze"
            )

    def test_promoted_source_gold(self):
        """BDD: promoted → gold."""
        assert assess_quality("晉升後的記憶", "promoted") == "gold"

    def test_supersede_source_gold(self):
        """BDD: supersede → gold."""
        assert assess_quality("取代的記憶", "supersede") == "gold"

    def test_chat_session_source_gold(self):
        """BDD: chat_session → gold."""
        assert assess_quality("學到新技能", "chat_session") == "gold"

    def test_signal_keyword_gold(self):
        """BDD: 含信號關鍵字 → gold."""
        assert assess_quality("學到新技能", "") == "gold"

    def test_signal_keyword_complete(self):
        """BDD: 完成 → gold."""
        assert assess_quality("完成任務了哦哦哦哦哦哦哦哦哦", "") == "gold"

    def test_signal_keyword_failure(self):
        """BDD: 失敗 → gold."""
        assert assess_quality("這次失敗了，要記住教訓", "") == "gold"

    def test_signal_keyword_discover(self):
        """BDD: 發現 → gold."""
        assert assess_quality("我發現了一個重要的規律", "") == "gold"

    def test_short_content_bronze(self):
        """BDD: < 20 字元 → bronze."""
        assert assess_quality("短", "") == "bronze"

    def test_exactly_20_chars_not_bronze(self):
        """BDD: 恰好 20 字元不是 bronze."""
        text = "A" * 20
        assert assess_quality(text, "") == "silver"

    def test_19_chars_bronze(self):
        """BDD: 19 字元 → bronze."""
        text = "A" * 19
        assert assess_quality(text, "") == "bronze"

    def test_default_silver(self):
        """BDD: 無特殊匹配的普通長文字 → silver."""
        text = "這是一段很普通的長文字，今天天氣不錯在外面散步"
        assert assess_quality(text, "") == "silver"

    def test_empty_source_with_keyword(self):
        """BDD: 空 source 但含關鍵字 → gold."""
        assert assess_quality("我決定改進這個流程方案", "") == "gold"

    def test_priority_failure_distill_over_system(self):
        """BDD: failure_distill 優先於系統來源判斷."""
        assert assess_quality("系統自動記錄", "failure_distill") == "silver"


# ═══════════════════════════════════════════
# Quality Weight Tests
# ═══════════════════════════════════════════


class TestApplyWeight:
    """品質加權測試."""

    def test_gold_weight(self):
        """BDD: gold 加權 0.6 → 0.9."""
        result = apply_weight(0.6, "gold")
        assert result == pytest.approx(0.9, abs=0.01)

    def test_silver_weight(self):
        """BDD: silver 加權 0.7 → 0.7."""
        result = apply_weight(0.7, "silver")
        assert result == pytest.approx(0.7, abs=0.01)

    def test_bronze_weight(self):
        """BDD: bronze 加權 0.8 → 0.4."""
        result = apply_weight(0.8, "bronze")
        assert result == pytest.approx(0.4, abs=0.01)

    def test_recall_ranking(self):
        """BDD: 品質加權影響 recall 排序.

        A(gold, sim=0.6) → 0.9
        B(silver, sim=0.7) → 0.7
        C(bronze, sim=0.8) → 0.4
        排序：A > B > C
        """
        a = apply_weight(0.6, "gold")
        b = apply_weight(0.7, "silver")
        c = apply_weight(0.8, "bronze")
        assert a > b > c

    def test_unknown_tier_defaults_to_1(self):
        """BDD: 未知 tier 預設權重 1.0."""
        result = apply_weight(0.5, "unknown")
        assert result == pytest.approx(0.5, abs=0.01)
