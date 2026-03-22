"""Unit tests for brain_prompt_builder.py — 常數驗證 + Token 預算 + section builder.

覆蓋範圍：
- 常數化驗證：所有魔術值已收斂到類別常數
- _get_evolution_behavior_hints: 元素覺醒閾值邏輯
- _get_identity_prompt: ANIMA_MC 身份生成
- _offline edge cases
"""

import pytest
from unittest.mock import MagicMock
from pathlib import Path

from museon.agent.brain_prompt_builder import BrainPromptBuilderMixin


# ── Helpers ──

class FakePromptBuilder(BrainPromptBuilderMixin):
    """Minimal fake Brain with required attributes."""

    def __init__(self, tmp_path: Path):
        self.data_dir = tmp_path
        self.memory_manager = None
        self.knowledge_lattice = None
        self.skill_router = MagicMock()
        self.skill_router._index = []
        self.crystal_actuator = None
        self._governor = None
        self._context_switcher = None
        self._tool_executor = None
        self._anima_mc_store = None
        self._activity_logger = None
        self._anima_tracker = None
        self._is_group_session = False
        self._current_metadata = {}
        self._failure_distill_cache = {}
        self._multiagent_enabled = False
        self._self_modification_detected = False

    def _load_anima_mc(self):
        return {"identity": {"name": "test"}, "boss": {"name": "Zeal"}}


# ── 常數驗證 ──

class TestConstants:
    """驗證所有魔術值已收斂到類別常數."""

    def test_budget_zones_exist(self):
        assert BrainPromptBuilderMixin._BUDGET_CORE_SYSTEM == 3000
        assert BrainPromptBuilderMixin._BUDGET_PERSONA == 1500
        assert BrainPromptBuilderMixin._BUDGET_MODULES == 6000
        assert BrainPromptBuilderMixin._BUDGET_MEMORY == 2000
        assert BrainPromptBuilderMixin._BUDGET_BUFFER == 2000

    def test_budget_total(self):
        """五個 zone 的預設總預算."""
        total = (
            BrainPromptBuilderMixin._BUDGET_CORE_SYSTEM
            + BrainPromptBuilderMixin._BUDGET_PERSONA
            + BrainPromptBuilderMixin._BUDGET_MODULES
            + BrainPromptBuilderMixin._BUDGET_MEMORY
            + BrainPromptBuilderMixin._BUDGET_BUFFER
        )
        assert total == 14500

    def test_safety_multiplier(self):
        assert BrainPromptBuilderMixin._BUDGET_SAFETY_MULTIPLIER == 1.5

    def test_evolution_multiplier(self):
        assert BrainPromptBuilderMixin._BUDGET_EVOLUTION_MULTIPLIER == 1.2

    def test_crystal_staleness_days(self):
        assert BrainPromptBuilderMixin._CRYSTAL_STALENESS_DAYS == 14

    def test_crystal_compress_threshold(self):
        assert BrainPromptBuilderMixin._CRYSTAL_COMPRESS_THRESHOLD == 8

    def test_failure_dedup_seconds(self):
        assert BrainPromptBuilderMixin._FAILURE_DEDUP_SECONDS == 300

    def test_element_thresholds_ascending(self):
        """元素閾值必須遞增：萌芽 < 精通 < 化境."""
        assert (
            BrainPromptBuilderMixin._ELEMENT_SPROUT_THRESHOLD
            < BrainPromptBuilderMixin._ELEMENT_MASTERY_THRESHOLD
            < BrainPromptBuilderMixin._ELEMENT_REALM_THRESHOLD
        )

    def test_total_thresholds_ascending(self):
        """總量閾值必須遞增：鳳凰 < 星辰."""
        assert (
            BrainPromptBuilderMixin._TOTAL_PHOENIX_THRESHOLD
            < BrainPromptBuilderMixin._TOTAL_STAR_THRESHOLD
        )

    def test_crystal_thresholds_ascending(self):
        """結晶閾值必須遞增：積累 < 豐富."""
        assert (
            BrainPromptBuilderMixin._CRYSTAL_ACCUMULATE_THRESHOLD
            < BrainPromptBuilderMixin._CRYSTAL_RICH_THRESHOLD
        )

    def test_max_evolution_hints(self):
        assert BrainPromptBuilderMixin._MAX_EVOLUTION_HINTS == 5

    def test_soul_recent_counts(self):
        assert BrainPromptBuilderMixin._SOUL_RECENT_REFLECTIONS == 3
        assert BrainPromptBuilderMixin._SOUL_RECENT_OBSERVATIONS == 3
        assert BrainPromptBuilderMixin._SOUL_RECENT_GROWTHS == 2
        assert BrainPromptBuilderMixin._SOUL_RECENT_RELATIONS == 3

    def test_fact_correction_max(self):
        assert BrainPromptBuilderMixin._FACT_CORRECTION_MAX == 3


# ── 演化覺醒 ──

class TestEvolutionBehavior:
    """_get_evolution_behavior_hints 邏輯測試."""

    def test_empty_anima_returns_empty(self, tmp_path):
        builder = FakePromptBuilder(tmp_path)
        result = builder._get_evolution_behavior_hints({})
        assert result == ""

    def test_sprout_level(self, tmp_path):
        """元素 >= 100 → 萌芽."""
        builder = FakePromptBuilder(tmp_path)
        anima = {
            "eight_primal_energies": {
                "乾": {"absolute": 150},
            },
            "identity": {"memory": {"knowledge_crystals": 0}},
        }
        result = builder._get_evolution_behavior_hints(anima)
        assert "覺醒" in result or "萌芽" in result

    def test_mastery_level(self, tmp_path):
        """元素 >= 500 → 精通."""
        builder = FakePromptBuilder(tmp_path)
        anima = {
            "eight_primal_energies": {
                "乾": {"absolute": 600},
            },
            "identity": {"memory": {"knowledge_crystals": 0}},
        }
        result = builder._get_evolution_behavior_hints(anima)
        assert "精通" in result

    def test_realm_level(self, tmp_path):
        """元素 >= 1000 → 化境."""
        builder = FakePromptBuilder(tmp_path)
        anima = {
            "eight_primal_energies": {
                "坎": {"absolute": 1200},
            },
            "identity": {"memory": {"knowledge_crystals": 0}},
        }
        result = builder._get_evolution_behavior_hints(anima)
        assert "化境" in result

    def test_phoenix_total(self, tmp_path):
        """總量 >= 2000 → 鳳凰（用少量高值元素避免覺醒提示佔滿上限）."""
        builder = FakePromptBuilder(tmp_path)
        # 只用 2 個元素達到鳳凰級，這樣覺醒提示只有 2 條，鳳凰提示能進去
        anima = {
            "eight_primal_energies": {
                "乾": {"absolute": 1100}, "坤": {"absolute": 1100},
            },
            "identity": {"memory": {"knowledge_crystals": 0}},
        }
        result = builder._get_evolution_behavior_hints(anima)
        assert "鳳凰" in result

    def test_crystal_rich(self, tmp_path):
        """結晶 >= 50 → 知識豐富（需有元素避免提前返回）."""
        builder = FakePromptBuilder(tmp_path)
        anima = {
            "eight_primal_energies": {
                "乾": {"absolute": 10},  # 低值不觸發覺醒，但避免空 dict 提前返回
            },
            "identity": {"memory": {"knowledge_crystals": 60}},
        }
        result = builder._get_evolution_behavior_hints(anima)
        assert "知識豐富" in result

    def test_max_hints_capped(self, tmp_path):
        """演化提示不超過 _MAX_EVOLUTION_HINTS."""
        builder = FakePromptBuilder(tmp_path)
        # 所有元素都精通 + 鳳凰 + 結晶豐富 → 可能產生 >5 條
        anima = {
            "eight_primal_energies": {
                "乾": {"absolute": 600}, "坤": {"absolute": 600},
                "震": {"absolute": 600}, "巽": {"absolute": 600},
                "坎": {"absolute": 600}, "離": {"absolute": 600},
                "艮": {"absolute": 600}, "兌": {"absolute": 600},
            },
            "identity": {"memory": {"knowledge_crystals": 60}},
        }
        result = builder._get_evolution_behavior_hints(anima)
        hint_lines = [l for l in result.split("\n") if l.startswith("- ")]
        assert len(hint_lines) <= builder._MAX_EVOLUTION_HINTS


# ── Identity Prompt ──

class TestIdentityPrompt:
    """_get_identity_prompt 邏輯測試."""

    def test_with_valid_anima(self, tmp_path):
        builder = FakePromptBuilder(tmp_path)
        anima = {
            "identity": {"name": "霓裳", "days_alive": 5},
            "boss": {"name": "Zeal"},
        }
        result = builder._get_identity_prompt(anima)
        assert "霓裳" in result

    def test_with_empty_anima(self, tmp_path):
        builder = FakePromptBuilder(tmp_path)
        result = builder._get_identity_prompt({})
        # 不應拋異常
        assert isinstance(result, str)
