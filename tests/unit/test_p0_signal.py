"""Phase 1D 單元測試：P0 訊號分流 + 事實更正偵測 + cognitive_trace 修復.

覆蓋範圍：
  - _classify_p0_signal(): 六類信號判定
  - _detect_fact_correction(): 啟發式事實糾正偵測
  - _P0_SIGNAL_KEYWORDS: 關鍵字覆蓋率
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


# ── Fixture: 最小化 Brain 實例 ─────────────────────────

@pytest.fixture
def brain(tmp_path):
    """建立最小化 MuseonBrain 實例（只初始化測試所需屬性）."""
    from museon.agent.brain import MuseonBrain

    with patch.object(MuseonBrain, "__init__", lambda self: None):
        b = MuseonBrain()
    b.data_dir = tmp_path
    return b


# ══════════════════════════════════════════════════════════════
# 1. _classify_p0_signal 六類信號判定
# ══════════════════════════════════════════════════════════════

class TestP0SignalClassification:
    """Phase 0 訊號分流 — 六類判定."""

    def test_empty_content_returns_rational(self, brain):
        """空字串 → 理性（預設值）."""
        assert brain._classify_p0_signal("", None, None) == "理性"

    def test_none_content_returns_rational(self, brain):
        """None → 理性（falsy 預設）."""
        assert brain._classify_p0_signal(None, None, None) == "理性"

    # ── 感性 ──

    def test_emotional_keyword_single(self, brain):
        """單一感性關鍵字 → 感性."""
        assert brain._classify_p0_signal("我好焦慮", None, None) == "感性"

    def test_emotional_keyword_multiple(self, brain):
        """多個感性關鍵字 → 感性."""
        result = brain._classify_p0_signal("我好焦慮又擔心", None, None)
        assert result == "感性"

    def test_emotional_positive(self, brain):
        """正面情緒也是感性."""
        assert brain._classify_p0_signal("今天超開心！太棒了！", None, None) == "感性"

    # ── 思維轉化 ──

    def test_transformation_keyword(self, brain):
        """思維轉化關鍵字 → 思維轉化."""
        assert brain._classify_p0_signal("我一直卡住，想不通", None, None) == "思維轉化"

    def test_transformation_dilemma(self, brain):
        """兩難抉擇 → 思維轉化."""
        assert brain._classify_p0_signal("該不該接受這個offer？好猶豫", None, None) == "思維轉化"

    # ── 哲學 ──

    def test_philosophical_keyword(self, brain):
        """哲學關鍵字 → 哲學."""
        assert brain._classify_p0_signal("人生的意義到底是什麼", None, None) == "哲學"

    def test_philosophical_ethics(self, brain):
        """倫理議題 → 哲學."""
        result = brain._classify_p0_signal("這個決定涉及道德和倫理層面", None, None)
        assert result == "哲學"

    # ── 戰略 ──

    def test_strategic_keyword(self, brain):
        """戰略關鍵字 → 戰略."""
        assert brain._classify_p0_signal("市場競爭的佈局策略", None, None) == "戰略"

    def test_strategic_business(self, brain):
        """商業博弈 → 戰略."""
        result = brain._classify_p0_signal("護城河和壁壘的建立", None, None)
        assert result == "戰略"

    # ── 理性（預設） ──

    def test_rational_default(self, brain):
        """無特殊關鍵字 → 理性."""
        assert brain._classify_p0_signal("今天天氣不錯", None, None) == "理性"

    def test_rational_factual(self, brain):
        """事實性陳述 → 理性."""
        assert brain._classify_p0_signal("我上次會議是在週三", None, None) == "理性"

    # ── 混合 ──

    def test_mixed_emotional_and_strategic(self, brain):
        """同時命中感性+戰略（各 ≥2 hits）→ 混合."""
        # 感性: "焦慮", "擔心" (2 hits) + 戰略: "市場", "競爭" (2 hits)
        content = "我好焦慮又擔心市場競爭太激烈"
        result = brain._classify_p0_signal(content, None, None)
        assert result == "混合"

    def test_mixed_requires_two_significant(self, brain):
        """只有一個類別 ≥2 → 不是混合，回傳該類別."""
        # 感性: "焦慮", "擔心" (2 hits) + 戰略: "市場" (1 hit)
        content = "我好焦慮又擔心這個市場"
        result = brain._classify_p0_signal(content, None, None)
        # 感性有 2 hits 但戰略只有 1 hit → significant 只有感性 → 不是混合
        assert result != "混合"

    # ── Skill 輔助判定 ──

    def test_skill_resonance_boosts_emotional(self, brain):
        """resonance skill → 感性 +3."""
        result = brain._classify_p0_signal("一般文字", None, ["resonance"])
        assert result == "感性"

    def test_skill_dharma_boosts_transformation(self, brain):
        """dharma skill → 思維轉化 +3."""
        result = brain._classify_p0_signal("一般文字", None, ["dharma"])
        assert result == "思維轉化"

    def test_skill_philo_dialectic_boosts_philosophy(self, brain):
        """philo-dialectic skill → 哲學 +3."""
        result = brain._classify_p0_signal("一般文字", None, ["philo-dialectic"])
        assert result == "哲學"

    def test_skill_master_strategy_boosts_strategic(self, brain):
        """master-strategy skill → 戰略 +3."""
        result = brain._classify_p0_signal("一般文字", None, ["master-strategy"])
        assert result == "戰略"

    def test_skill_shadow_boosts_strategic(self, brain):
        """shadow skill → 戰略 +3."""
        result = brain._classify_p0_signal("一般文字", None, ["shadow"])
        assert result == "戰略"

    def test_skill_with_keyword_amplification(self, brain):
        """Skill + 關鍵字 → 加強效果."""
        # resonance(+3) + "焦慮"(1 keyword hit) = 4 for 感性
        result = brain._classify_p0_signal("我好焦慮", None, ["resonance"])
        assert result == "感性"

    def test_no_skills_no_keywords_returns_rational(self, brain):
        """無 skill + 無關鍵字 → 理性."""
        result = brain._classify_p0_signal("普通的問候", None, [])
        assert result == "理性"


# ══════════════════════════════════════════════════════════════
# 2. _detect_fact_correction 啟發式偵測
# ══════════════════════════════════════════════════════════════

class TestFactCorrectionDetection:
    """事實更正啟發式偵測."""

    def test_short_content_returns_false(self, brain):
        """字串長度 < 4 → False."""
        assert brain._detect_fact_correction("不是") is False
        assert brain._detect_fact_correction("abc") is False

    def test_explicit_correction_keywords(self, brain):
        """明確糾正關鍵字 → True."""
        assert brain._detect_fact_correction("你記錯了，不是這樣") is True
        assert brain._detect_fact_correction("你搞錯了吧") is True
        assert brain._detect_fact_correction("我糾正一下") is True
        assert brain._detect_fact_correction("我更正一下") is True

    def test_frustration_correction(self, brain):
        """沮喪語氣的糾正 → True."""
        assert brain._detect_fact_correction("要我講多少遍，不是這樣") is True
        assert brain._detect_fact_correction("你怎麼又搞錯了") is True

    def test_previous_statement_reference(self, brain):
        """引用先前陳述的糾正 → True."""
        assert brain._detect_fact_correction("跟你說過了不是12個") is True
        assert brain._detect_fact_correction("我已經說過了不是這樣") is True

    def test_denial_patterns(self, brain):
        """否認模式 → True."""
        assert brain._detect_fact_correction("哪來的啊，沒有這回事") is True
        assert brain._detect_fact_correction("沒那回事啦你在說什麼") is True

    def test_misunderstanding_keywords(self, brain):
        """誤解關鍵字 → True."""
        assert brain._detect_fact_correction("你誤會我的意思了") is True
        assert brain._detect_fact_correction("你弄錯了，修正一下") is True
        assert brain._detect_fact_correction("你搞混了兩件事") is True

    def test_normal_content_returns_false(self, brain):
        """一般內容 → False."""
        assert brain._detect_fact_correction("今天天氣很好") is False
        assert brain._detect_fact_correction("我覺得這個方案不錯") is False
        assert brain._detect_fact_correction("幫我查一下明天的行程") is False

    def test_case_insensitive(self, brain):
        """英文糾正關鍵字不區分大小寫（目前關鍵字都是中文）."""
        # 確認中文關鍵字不受 lower() 影響
        assert brain._detect_fact_correction("你記錯了，不是這樣的") is True


# ══════════════════════════════════════════════════════════════
# 3. _P0_SIGNAL_KEYWORDS 覆蓋率
# ══════════════════════════════════════════════════════════════

class TestP0SignalKeywords:
    """關鍵字列表完整性."""

    def test_four_categories_exist(self, brain):
        """四個關鍵字類別: 感性、思維轉化、哲學、戰略."""
        kw = brain._P0_SIGNAL_KEYWORDS
        assert "感性" in kw
        assert "思維轉化" in kw
        assert "哲學" in kw
        assert "戰略" in kw
        assert len(kw) == 4

    def test_each_category_has_keywords(self, brain):
        """每個類別至少有 10 個關鍵字."""
        for cat, keywords in brain._P0_SIGNAL_KEYWORDS.items():
            assert len(keywords) >= 10, f"{cat} 只有 {len(keywords)} 個關鍵字"

    def test_fact_correction_patterns_not_empty(self, brain):
        """事實更正模式列表不為空."""
        assert len(brain._FACT_CORRECTION_PATTERNS) >= 20
