"""Tests for token_optimizer.py — LayeredContent + TokenBudget.

依據 DNA27 Neural Tract BDD Spec §5-6 的 BDD scenarios 驗證。
"""

import pytest

from museon.agent.token_optimizer import (
    LayeredContent,
    TokenBudget,
    _score_line,
    auto_extract_compact,
    auto_extract_essence,
    build_cached_system_blocks,
    build_layered_content,
    clear_token_cache,
    estimate_tokens,
    select_layer,
    _DEFAULT_ZONES,
    _DEFAULT_TOTAL_BUDGET,
    _ESSENCE_MAX_CHARS,
    _COMPACT_MAX_CHARS,
)


# ═══════════════════════════════════════════
# _score_line Tests
# ═══════════════════════════════════════════


class TestScoreLine:
    """語義重要性打分測試."""

    def test_heading_scores_high(self):
        """BDD: 標題行得分 0.9."""
        assert _score_line("## 核心規則", 0.0) >= 0.9

    def test_heading_with_position_bonus(self):
        """BDD: 位於前 10% 的標題."""
        score = _score_line("# 使命", 0.05)
        assert score == 1.0  # 0.9 + 0.2 = 1.1, capped at 1.0

    def test_label_scores(self):
        """BDD: 標籤行得分 0.8."""
        assert _score_line("【核心價值觀】永遠先止血", 0.5) >= 0.8

    def test_json_key_scores(self):
        """BDD: JSON key 得分 0.7."""
        assert _score_line('  "name": "MUSEON"', 0.5) >= 0.7

    def test_section_scores(self):
        """BDD: 區段標記得分 0.7."""
        assert _score_line("（一）策略規劃", 0.5) >= 0.7

    def test_list_item_scores(self):
        """BDD: 列表項得分 0.4."""
        score = _score_line("- 先判斷使用者能量狀態", 0.5)
        assert score >= 0.4

    def test_numbered_list(self):
        """BDD: 數字列表項得分 0.4."""
        score = _score_line("1. 真實優先", 0.5)
        assert score >= 0.4

    def test_definition_keyword(self):
        """BDD: 定義類關鍵字得分 0.3."""
        score = _score_line("核心目的是幫助使用者", 0.5)
        assert score >= 0.3

    def test_position_early_bonus(self):
        """BDD: 前 10% 位置 +0.2."""
        s1 = _score_line("普通句子", 0.05)
        s2 = _score_line("普通句子", 0.5)
        assert s1 > s2

    def test_position_mid_bonus(self):
        """BDD: 前 30% 位置 +0.1."""
        s1 = _score_line("普通句子", 0.2)
        s2 = _score_line("普通句子", 0.5)
        assert s1 > s2

    def test_long_line_penalty(self):
        """BDD: >200 字的行有 0.6 懲罰."""
        long_line = "## " + "A" * 250
        short_heading = "## Short"
        # 長行懲罰
        assert _score_line(long_line, 0.5) < _score_line(short_heading, 0.5)

    def test_empty_line_zero(self):
        """BDD: 空行得分 0."""
        assert _score_line("", 0.5) == 0.0

    def test_decoration_line_zero(self):
        """BDD: 裝飾線得分 0."""
        assert _score_line("---", 0.5) == 0.0
        assert _score_line("===", 0.5) == 0.0
        assert _score_line("```", 0.5) == 0.0

    def test_score_capped_at_1(self):
        """BDD: 分數上限 1.0."""
        # Heading(0.9) + definition(0.3) + position(<10%=0.2) = 1.4 → cap 1.0
        score = _score_line("## 核心定義", 0.05)
        assert score <= 1.0


# ═══════════════════════════════════════════
# auto_extract Tests
# ═══════════════════════════════════════════


class TestAutoExtract:
    """LayeredContent 自動萃取測試."""

    SAMPLE_TEXT = """# MUSEON DNA27 核心

## 使命
在不奪權、不失真、不成癮的前提下，打造人類對齊 AI 助理。

## 核心價值觀
1. 真實優先 — 寧可不舒服也不說假話
2. 演化至上 — 停滯比犯錯更危險
3. 代價透明 — 每個選擇都同框呈現甜頭和代價

---

這是一段很長很長很長的敘述文字，其實不太重要，只是用來填充的。

## Style Always
- 先判斷使用者能量狀態
- 每個建議都有 Plan B
"""

    def test_essence_max_chars(self):
        """BDD: essence 輸出 ≤ 250 chars."""
        result = auto_extract_essence(self.SAMPLE_TEXT)
        assert len(result) <= _ESSENCE_MAX_CHARS

    def test_essence_prioritizes_headings(self):
        """BDD: essence 優先保留標題."""
        result = auto_extract_essence(self.SAMPLE_TEXT)
        # 至少應包含最高分的標題
        assert "使命" in result or "核心" in result or "MUSEON" in result

    def test_essence_preserves_order(self):
        """BDD: essence 保持原始行順序."""
        result = auto_extract_essence(self.SAMPLE_TEXT)
        lines = result.splitlines()
        # 不能有重複行
        assert len(lines) == len(set(lines))

    def test_essence_empty_input(self):
        """BDD: 空輸入返回空字串."""
        assert auto_extract_essence("") == ""

    def test_compact_max_chars(self):
        """BDD: compact 輸出 ≤ 900 chars."""
        result = auto_extract_compact(self.SAMPLE_TEXT)
        assert len(result) <= _COMPACT_MAX_CHARS

    def test_compact_retains_structure(self):
        """BDD: compact 保留標題和列表項."""
        result = auto_extract_compact(self.SAMPLE_TEXT)
        # 應保留至少一個標題和列表項
        has_heading = any(
            line.strip().startswith("#") for line in result.splitlines()
        )
        has_list = any(
            line.strip().startswith("-") or line.strip()[0:1].isdigit()
            for line in result.splitlines()
            if line.strip()
        )
        assert has_heading or has_list

    def test_compact_empty_input(self):
        """BDD: 空輸入返回空字串."""
        assert auto_extract_compact("") == ""

    def test_compact_excludes_decoration(self):
        """BDD: compact 排除裝飾線."""
        result = auto_extract_compact(self.SAMPLE_TEXT)
        assert "---" not in result.splitlines()


# ═══════════════════════════════════════════
# LayeredContent + select_layer Tests
# ═══════════════════════════════════════════


class TestLayeredContent:
    """LayeredContent 建構與層選擇測試."""

    def test_build_layered_content(self):
        """BDD: build_layered_content 產出三層."""
        lc = build_layered_content("test", "# Title\nContent")
        assert lc.module_id == "test"
        assert lc.full == "# Title\nContent"
        assert len(lc.essence) <= _ESSENCE_MAX_CHARS
        assert len(lc.compact) <= _COMPACT_MAX_CHARS

    def test_select_layer_full(self):
        """BDD: score >= 1.0 → full."""
        lc = LayeredContent(
            module_id="test",
            essence="E",
            compact="C",
            full="FULL",
        )
        assert select_layer(lc, 1.0) == "FULL"
        assert select_layer(lc, 1.5) == "FULL"

    def test_select_layer_compact(self):
        """BDD: 0.5 <= score < 1.0 → compact."""
        lc = LayeredContent(
            module_id="test",
            essence="E",
            compact="C",
            full="FULL",
        )
        assert select_layer(lc, 0.5) == "C"
        assert select_layer(lc, 0.9) == "C"

    def test_select_layer_essence(self):
        """BDD: 0.2 <= score < 0.5 → essence."""
        lc = LayeredContent(
            module_id="test",
            essence="E",
            compact="C",
            full="FULL",
        )
        assert select_layer(lc, 0.2) == "E"
        assert select_layer(lc, 0.4) == "E"

    def test_select_layer_skip(self):
        """BDD: score < 0.2 → skip (empty)."""
        lc = LayeredContent(
            module_id="test",
            essence="E",
            compact="C",
            full="FULL",
        )
        assert select_layer(lc, 0.1) == ""
        assert select_layer(lc, 0.0) == ""


# ═══════════════════════════════════════════
# Token Estimation Tests
# ═══════════════════════════════════════════


class TestEstimateTokens:
    """Token 估算測試."""

    def setup_method(self):
        clear_token_cache()

    def test_empty_text(self):
        assert estimate_tokens("") == 0

    def test_chinese_text(self):
        """BDD: 中文用 len // 2."""
        text = "這是一段中文測試文字"
        tokens = estimate_tokens(text)
        expected = len(text) // 2
        assert abs(tokens - expected) <= 2

    def test_english_text(self):
        """BDD: 英文用 len // 4."""
        text = "This is an English test sentence"
        tokens = estimate_tokens(text)
        expected = len(text) // 4
        assert abs(tokens - expected) <= 2

    def test_mixed_text(self):
        """混合文本：介於 len//2 和 len//4 之間."""
        text = "Hello 你好世界 World"
        tokens = estimate_tokens(text)
        assert tokens >= len(text) // 4
        assert tokens <= len(text) // 2

    def test_cache_consistency(self):
        """BDD: token_cache 避免重複計算."""
        text = "test text"
        t1 = estimate_tokens(text)
        t2 = estimate_tokens(text)
        assert t1 == t2

    def test_clear_cache(self):
        """BDD: clear 後重新計算."""
        estimate_tokens("cached")
        clear_token_cache()
        # Should not raise


# ═══════════════════════════════════════════
# TokenBudget Tests
# ═══════════════════════════════════════════


class TestTokenBudget:
    """TokenBudget 預算管理器測試."""

    def test_default_zones(self):
        """BDD: 預設五區預算."""
        budget = TokenBudget()
        assert budget.get_zone_budget("core_system") == 3000
        assert budget.get_zone_budget("persona") == 1500
        assert budget.get_zone_budget("modules") == 6000
        assert budget.get_zone_budget("memory") == 800
        assert budget.get_zone_budget("buffer") == 2000

    def test_track_usage(self):
        """BDD: 追蹤使用量."""
        budget = TokenBudget()
        budget.track_usage("modules", 1200)
        assert budget.get_usage("modules") == 1200
        assert budget.remaining("modules") == 4800

    def test_accumulate_usage(self):
        """BDD: 三次 track_usage 累積."""
        budget = TokenBudget()
        budget.track_usage("modules", 1200)
        budget.track_usage("modules", 1200)
        budget.track_usage("modules", 1200)
        assert budget.get_usage("modules") == 3600
        assert budget.remaining("modules") == 2400

    def test_exhausted(self):
        """BDD: 區預算耗盡."""
        budget = TokenBudget()
        budget.track_usage("modules", 6000)
        assert budget.is_exhausted("modules")

    def test_dynamic_allocation_over_threshold(self):
        """BDD: max_tier > 1.0 → modules +20% from buffer."""
        budget = TokenBudget()
        original_modules = budget.get_zone_budget("modules")  # 6000
        original_buffer = budget.get_zone_budget("buffer")  # 2000
        bonus = min(original_buffer, original_modules // 5)  # min(2000, 1200) = 1200

        budget.apply_dynamic_allocation(1.5)
        assert budget.get_zone_budget("modules") == original_modules + bonus
        assert budget.get_zone_budget("buffer") == original_buffer - bonus

    def test_dynamic_allocation_under_threshold(self):
        """BDD: max_tier <= 1.0 → 不變."""
        budget = TokenBudget()
        budget.apply_dynamic_allocation(0.8)
        assert budget.get_zone_budget("modules") == 6000
        assert budget.get_zone_budget("buffer") == 2000

    def test_fit_text_to_zone(self):
        """BDD: 文本適配到區預算."""
        budget = TokenBudget()
        text = "短文本"
        fitted = budget.fit_text_to_zone("persona", text)
        assert fitted == text

    def test_fit_text_truncation(self):
        """BDD: 超出預算時截斷."""
        budget = TokenBudget(zones={"test": 10})  # 極小預算
        long_text = "A" * 1000
        fitted = budget.fit_text_to_zone("test", long_text)
        assert len(fitted) < len(long_text)

    def test_fit_text_exhausted(self):
        """BDD: 區已耗盡時返回空字串."""
        budget = TokenBudget(zones={"test": 10})
        budget.track_usage("test", 10)
        assert budget.fit_text_to_zone("test", "text") == ""

    def test_get_all_zones(self):
        """BDD: 取得所有區資訊."""
        budget = TokenBudget()
        budget.track_usage("core_system", 500)
        zones = budget.get_all_zones()
        assert zones["core_system"]["budget"] == 3000
        assert zones["core_system"]["used"] == 500
        assert zones["core_system"]["remaining"] == 2500

    def test_reset(self):
        """BDD: 重置使用量."""
        budget = TokenBudget()
        budget.track_usage("modules", 3000)
        budget.reset()
        assert budget.get_usage("modules") == 0
        assert budget.remaining("modules") == 6000


# ═══════════════════════════════════════════
# Prompt Caching Tests
# ═══════════════════════════════════════════


class TestBuildCachedSystemBlocks:
    """Prompt caching content blocks 測試."""

    def test_static_core_has_cache_control(self):
        """BDD: static_core 有 cache_control."""
        blocks = build_cached_system_blocks(
            static_core="DNA27 core content",
            dynamic_sections=[],
        )
        assert len(blocks) == 1
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert blocks[0]["text"] == "DNA27 core content"

    def test_dynamic_no_cache_control(self):
        """BDD: 動態區段不標記 cache_control."""
        blocks = build_cached_system_blocks(
            static_core="core",
            dynamic_sections=[{"label": "skills", "text": "skill data"}],
        )
        assert len(blocks) == 2
        assert "cache_control" in blocks[0]
        assert "cache_control" not in blocks[1]

    def test_empty_static_core(self):
        """BDD: 空 static_core."""
        blocks = build_cached_system_blocks(
            static_core="",
            dynamic_sections=[{"text": "data"}],
        )
        assert len(blocks) == 1
        assert "cache_control" not in blocks[0]

    def test_empty_dynamic(self):
        """BDD: 空動態區段."""
        blocks = build_cached_system_blocks(
            static_core="core",
            dynamic_sections=[{"text": ""}],
        )
        # 空 text 的動態區段應被跳過
        assert len(blocks) == 1

    def test_multiple_dynamic_sections(self):
        """BDD: 多個動態區段."""
        blocks = build_cached_system_blocks(
            static_core="core",
            dynamic_sections=[
                {"text": "section1"},
                {"text": "section2"},
                {"text": "section3"},
            ],
        )
        assert len(blocks) == 4  # 1 static + 3 dynamic
