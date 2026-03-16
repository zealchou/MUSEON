"""Memory Gate 單元測試.

測試 MemoryGate 的意圖分類與操作決策邏輯，
確保「越否認越強化」迴圈被正確攔截。
"""

import pytest

from museon.memory.memory_gate import MemoryGate, MemoryIntent, MemoryAction


@pytest.fixture
def gate():
    return MemoryGate()


# ═══════════════════════════════════════════
# classify_intent 測試
# ═══════════════════════════════════════════

class TestClassifyIntent:
    """測試意圖分類."""

    def test_assertion_normal_fact(self, gate: MemoryGate):
        """正常事實陳述 → assertion."""
        intent = gate.classify_intent("我們公司有 5 個員工")
        assert intent.type == "assertion"
        assert intent.confidence > 0

    def test_correction_with_fact_keyword(self, gate: MemoryGate):
        """糾正信號 + 事實關鍵字 → correction (高信心)."""
        intent = gate.classify_intent("沒有 7 個新同仁")
        assert intent.type == "correction"
        assert intent.confidence >= 0.8
        assert len(intent.correction_signals) > 0

    def test_correction_explicit(self, gate: MemoryGate):
        """明確糾正語句 → correction."""
        intent = gate.classify_intent("你記錯了，我沒有在那間公司工作")
        assert intent.type == "correction"
        assert intent.confidence >= 0.9

    def test_correction_repeated_frustration(self, gate: MemoryGate):
        """重複糾正的不耐 → correction."""
        intent = gate.classify_intent("要我講多少遍，沒有新員工")
        assert intent.type == "correction"
        assert intent.confidence >= 0.8

    def test_correction_number_negation(self, gate: MemoryGate):
        """數字否定 → correction."""
        intent = gate.classify_intent("不是12個，你搞錯了")
        assert intent.type == "correction"

    def test_denial_boundary_with_fact(self, gate: MemoryGate):
        """邊界信號 + 事實關鍵字 → denial."""
        # 用純邊界信號（不在 _CORRECTION_SIGNALS 裡）
        intent = gate.classify_intent("夠了，不要提家人")
        assert intent.type == "denial"
        assert intent.confidence >= 0.7

    def test_correction_stop_with_fact(self, gate: MemoryGate):
        """「別再說」(correction signal) + fact keyword → correction."""
        intent = gate.classify_intent("別再說員工的事")
        assert intent.type == "correction"
        assert intent.confidence >= 0.9

    def test_denial_single_correction_no_fact(self, gate: MemoryGate):
        """單個糾正信號但沒事實關鍵字 → denial (低信心)."""
        intent = gate.classify_intent("錯了吧")
        assert intent.type == "denial"
        assert intent.confidence <= 0.6

    def test_question(self, gate: MemoryGate):
        """問句 → question."""
        intent = gate.classify_intent("為什麼會這樣？")
        assert intent.type == "question"

    def test_normal_negation_no_fact(self, gate: MemoryGate):
        """日常否定不命中事實關鍵字 → 不觸發 correction."""
        intent = gate.classify_intent("今天天氣不錯")
        assert intent.type == "assertion"

    def test_short_content(self, gate: MemoryGate):
        """極短內容 → 低信心 assertion."""
        intent = gate.classify_intent("嗯")
        assert intent.type == "assertion"
        assert intent.confidence <= 0.2

    def test_multiple_correction_signals(self, gate: MemoryGate):
        """多重糾正信號 → 高信心 correction."""
        intent = gate.classify_intent("不對，你搞錯了，錯了啦")
        assert intent.type == "correction"
        assert intent.confidence >= 0.8

    def test_correction_you_misunderstand(self, gate: MemoryGate):
        """「你誤會」+ 事實 → correction."""
        intent = gate.classify_intent("你誤會了，我的工作不是這個")
        assert intent.type == "correction"
        assert intent.confidence >= 0.9

    def test_formal_correction(self, gate: MemoryGate):
        """正式糾正語句."""
        intent = gate.classify_intent("我糾正一下，我住在台中不是台北")
        assert intent.type == "correction"
        assert intent.confidence >= 0.9


# ═══════════════════════════════════════════
# decide_action 測試
# ═══════════════════════════════════════════

class TestDecideAction:
    """測試操作決策."""

    def test_correction_high_conf_triggers_correct(self, gate: MemoryGate):
        """高信心糾正 → CORRECT, suppress 全開."""
        intent = MemoryIntent(
            type="correction", confidence=0.9,
            correction_signals=["你記錯"], fact_keywords_hit=["工作"],
        )
        action = gate.decide_action(intent)
        assert action.action == "CORRECT"
        assert action.suppress_primals is True
        assert action.suppress_facts is True
        assert action.trigger_correction is True

    def test_correction_medium_conf_skip(self, gate: MemoryGate):
        """中等信心糾正 → SKIP."""
        intent = MemoryIntent(
            type="correction", confidence=0.6,
            correction_signals=["不是"], fact_keywords_hit=[],
        )
        action = gate.decide_action(intent)
        assert action.action == "SKIP"
        assert action.suppress_primals is True
        assert action.suppress_facts is True
        assert action.trigger_correction is False

    def test_denial_high_conf_skip(self, gate: MemoryGate):
        """高信心否認 → SKIP."""
        intent = MemoryIntent(
            type="denial", confidence=0.7,
            correction_signals=["別"], fact_keywords_hit=["員工"],
        )
        action = gate.decide_action(intent)
        assert action.action == "SKIP"
        assert action.suppress_primals is True
        assert action.suppress_facts is True

    def test_denial_low_conf_add(self, gate: MemoryGate):
        """低信心否認 → ADD (保守放行), 只 suppress 八原語."""
        intent = MemoryIntent(
            type="denial", confidence=0.5,
            correction_signals=["不是"], fact_keywords_hit=[],
        )
        action = gate.decide_action(intent)
        assert action.action == "ADD"
        assert action.suppress_primals is True
        assert action.suppress_facts is False

    def test_question_add(self, gate: MemoryGate):
        """問句 → ADD (正常寫入)."""
        intent = MemoryIntent(type="question", confidence=0.7)
        action = gate.decide_action(intent)
        assert action.action == "ADD"
        assert action.suppress_primals is False
        assert action.suppress_facts is False

    def test_assertion_add(self, gate: MemoryGate):
        """正常陳述 → ADD."""
        intent = MemoryIntent(
            type="assertion", confidence=0.6,
            fact_keywords_hit=["公司"],
        )
        action = gate.decide_action(intent)
        assert action.action == "ADD"
        assert action.suppress_primals is False
        assert action.suppress_facts is False


# ═══════════════════════════════════════════
# 端到端整合測試（classify + decide）
# ═══════════════════════════════════════════

class TestEndToEnd:
    """端到端：從原始文字到操作決策."""

    def test_e2e_normal_fact_add(self, gate: MemoryGate):
        """正常事實 → ADD."""
        intent = gate.classify_intent("我在台北一家科技公司上班")
        action = gate.decide_action(intent)
        assert action.action == "ADD"

    def test_e2e_correction_correct(self, gate: MemoryGate):
        """糾正事實 → CORRECT."""
        intent = gate.classify_intent("你記錯了，我沒有 7 個員工")
        action = gate.decide_action(intent)
        assert action.action == "CORRECT"
        assert action.trigger_correction is True

    def test_e2e_denial_skip(self, gate: MemoryGate):
        """否認 → SKIP."""
        intent = gate.classify_intent("停，不要說小孩了")
        action = gate.decide_action(intent)
        assert action.action == "SKIP"

    def test_e2e_question_add(self, gate: MemoryGate):
        """問句 → ADD."""
        intent = gate.classify_intent("為什麼我的系統這麼慢？")
        action = gate.decide_action(intent)
        assert action.action == "ADD"

    def test_e2e_casual_negation_not_blocked(self, gate: MemoryGate):
        """日常否定不阻擋."""
        intent = gate.classify_intent("這個方案不太好")
        action = gate.decide_action(intent)
        # 可能是低信心 denial 或 assertion，但不應該是 CORRECT
        assert action.action != "CORRECT"
