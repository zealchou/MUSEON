"""Gate Engine BDD 測試.

依據 MULTI_AGENT_BDD_SPEC §6 驗證。
"""

import pytest

from museon.multiagent.gate_engine import (
    GATE1_MIN_LENGTH,
    GATE3_MIN_QUALITY,
    GateEngine,
    GateResult,
)


@pytest.fixture
def engine():
    return GateEngine()


# ═══════════════════════════════════════════
# Gate 0: Legality（合法性）
# ═══════════════════════════════════════════

class TestGate0:
    """Scenario: Gate 0 攔截敏感資訊."""

    def test_blocks_api_key(self, engine):
        content = "# Config\n\nAPI Key: sk-abc123456789abcdef"
        result = engine.validate(content)
        assert not result.passed
        assert result.gate_level == -1
        assert any("prohibited" in i for i in result.issues)

    def test_blocks_eval(self, engine):
        content = "# Script\n\nUse eval(user_input) to execute"
        result = engine.validate(content)
        assert not result.passed
        assert result.gate_level == -1

    def test_passes_clean_content(self, engine):
        content = (
            "# 分析報告\n\n"
            "這是一份安全的分析報告。\n\n"
            "包含重要的商業數據 50% 成長。\n\n"
            "第一段分析內容。\n\n"
            "第二段結論。\n\n"
            "第三段建議。"
        )
        result = engine.validate(content)
        assert result.gate_level >= 0  # 至少通過 Gate 0


# ═══════════════════════════════════════════
# Gate 1: Feasibility（可行性）
# ═══════════════════════════════════════════

class TestGate1:
    """Scenario: Gate 1 要求最低長度."""

    def test_rejects_too_short(self, engine):
        result = engine.validate("太短")
        assert not result.passed
        assert result.gate_level == 0
        assert any("too short" in i for i in result.issues)

    def test_passes_min_length(self, engine):
        content = "# Title\n\n" + "x" * GATE1_MIN_LENGTH
        result = engine.validate(content)
        assert result.gate_level >= 1


# ═══════════════════════════════════════════
# Gate 2: Completeness（完整性）
# ═══════════════════════════════════════════

class TestGate2:
    """Scenario: Gate 2 要求標題."""

    def test_rejects_no_heading(self, engine):
        content = "這是一段沒有標題的長文本內容，超過二十個字元。"
        result = engine.validate(content)
        assert not result.passed
        assert result.gate_level == 1
        assert any("heading" in i for i in result.issues)

    def test_accepts_hash_heading(self, engine):
        content = "# 報告標題\n\n這是內容這是內容這是內容"
        result = engine.validate(content)
        assert result.gate_level >= 2

    def test_accepts_underline_heading(self, engine):
        content = "報告標題\n===\n\n這是內容這是內容這是內容"
        result = engine.validate(content)
        assert result.gate_level >= 2


# ═══════════════════════════════════════════
# Gate 3: Quality（品質）
# ═══════════════════════════════════════════

class TestGate3:
    """Scenario: Gate 3 品質評分."""

    def test_full_quality_score(self, engine):
        """標題 + 列表 + 數據 + 5 段落 → 滿分 1.0."""
        content = (
            "# 季度報告\n\n"
            "## 概要\n\n"
            "本季營收成長 50%，超出預期。\n\n"
            "- 重點一：用戶數增加\n"
            "- 重點二：留存率提升\n\n"
            "第三段分析內容。\n\n"
            "第四段數據解讀 100 萬用戶。\n\n"
            "第五段結論與展望。"
        )
        result = engine.validate(content)
        assert result.passed
        assert result.gate_level == 3
        assert result.score >= 0.9

    def test_low_quality_fails(self, engine):
        """只有標題 + 短段落 → 低分不通過."""
        content = "# 標題\n\n短內容但要超過二十個字元才行。"
        result = engine.validate(content)
        assert not result.passed
        assert result.gate_level == 2
        assert result.score < GATE3_MIN_QUALITY

    def test_medium_quality(self, engine):
        """標題 + 結構 + 數據 但段落不足."""
        content = (
            "# 分析\n\n"
            "- 數據一：成長 30%\n"
            "- 數據二：下降 10%\n\n"
            "總結段落。"
        )
        result = engine.validate(content)
        # structure=0.25, data=0.2, length varies, richness varies
        assert result.score > 0


# ═══════════════════════════════════════════
# GateResult 結構
# ═══════════════════════════════════════════

class TestGateResult:
    """Scenario: GateResult 資料結構."""

    def test_default_values(self):
        r = GateResult(passed=True, gate_level=3)
        assert r.score == 0.0
        assert r.issues == []

    def test_issues_list(self):
        r = GateResult(passed=False, gate_level=1, issues=["a", "b"])
        assert len(r.issues) == 2
