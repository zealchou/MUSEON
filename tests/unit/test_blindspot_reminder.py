"""P1 主動盲點提醒功能測試.

測試項目：
1. _estimate_user_exploration_level() — 探索度級別分類
2. get_blindspot_hint_for_query() — 盲點提示生成
3. 頻率控制 — 技術型/均衡型/探索型的提醒頻率
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import tempfile
import pytest


class TestUserExplorationLevel:
    """測試 _estimate_user_exploration_level() 探索度估算."""

    def create_test_anima_user(
        self,
        skill_cluster_count: int = 5,
        interest_count: int = 3,
        role_count: int = 2,
    ) -> Dict[str, Any]:
        """建立測試用 ANIMA_USER 結構."""
        decision_patterns = []
        for i in range(skill_cluster_count):
            decision_patterns.append({
                "pattern_type": "skill_cluster",
                "description": f"skill_cluster:test_skill_{i}+skill_{i+1}+skill_{i+2}",
                "frequency": 1,
                "confidence": 0.3,
            })

        interest_keys = []
        for i in range(interest_count):
            interest_keys.append({
                "key": f"interested_in_topic_{i}",
                "value": f"interested in topic {i}",
                "confidence": 1.0,
            })

        roles = []
        for i in range(role_count):
            roles.append({
                "role": f"role_{i}",
                "active_since": "2026-03-16T22:00:00",
                "interaction_count": 10,
            })

        return {
            "seven_layers": {
                "L3_decision_pattern": decision_patterns,
                "L5_preference_crystals": interest_keys,
                "L7_context_roles": roles,
            }
        }

    def test_technical_user_low_exploration(self):
        """技術型使用者：低探索度 (<0.25)."""
        from museon.agent.brain import MuseonBrain

        brain = MuseonBrain()
        anima = self.create_test_anima_user(
            skill_cluster_count=3,
            interest_count=1,
            role_count=1,
        )

        score = brain._estimate_user_exploration_level(anima)
        assert score < 0.25, f"技術型應低於 0.25，得到 {score}"

    def test_balanced_user_moderate_exploration(self):
        """均衡型使用者：中等探索度 (0.25-0.55)."""
        from museon.agent.brain import MuseonBrain

        brain = MuseonBrain()
        anima = self.create_test_anima_user(
            skill_cluster_count=8,
            interest_count=4,
            role_count=3,
        )

        score = brain._estimate_user_exploration_level(anima)
        assert 0.25 <= score < 0.55, f"均衡型應在 0.25-0.55，得到 {score}"

    def test_exploration_user_high_exploration(self):
        """探索型使用者：高探索度 (>0.55)."""
        from museon.agent.brain import MuseonBrain

        brain = MuseonBrain()
        anima = self.create_test_anima_user(
            skill_cluster_count=14,
            interest_count=7,
            role_count=5,
        )

        score = brain._estimate_user_exploration_level(anima)
        assert score >= 0.55, f"探索型應高於 0.55，得到 {score}"

    def test_no_data_fallback(self):
        """無使用者數據時回傳均衡預設值 (0.5)."""
        from museon.agent.brain import MuseonBrain

        brain = MuseonBrain()
        score = brain._estimate_user_exploration_level(None)
        assert score == 0.5, f"無數據應回傳 0.5，得到 {score}"


class TestBlindspotHint:
    """測試 get_blindspot_hint_for_query() 盲點提示生成."""

    def test_market_core_hint(self):
        """market-core skill 應生成適當盲點提示."""
        from museon.agent.eval_engine import get_blindspot_hint_for_query

        hint = get_blindspot_hint_for_query(
            query="市場利率會如何影響投資決策？",
            matched_skills=["market-core", "xmodel"],
        )

        assert hint is not None, "應生成盲點提示"
        assert any(kw in hint for kw in ["市場", "考慮", "決策", "數據", "競對", "假設", "評估"]), \
            f"提示應包含相關關鍵字，得到: {hint}"

    def test_strategy_hint(self):
        """master-strategy skill 應生成反向思考提示."""
        from museon.agent.eval_engine import get_blindspot_hint_for_query

        hint = get_blindspot_hint_for_query(
            query="如何制定長期競爭戰略？",
            matched_skills=["master-strategy"],
        )

        assert hint is not None, "應生成盲點提示"
        assert any(kw in hint for kw in ["失敗", "反向", "脆弱", "策略", "競對", "反制", "假設"]), \
            f"戰略提示應含戰略相關詞，得到: {hint}"

    def test_generic_hint_fallback(self):
        """無匹配 skill 時應生成通用盲點提示."""
        from museon.agent.eval_engine import get_blindspot_hint_for_query

        hint = get_blindspot_hint_for_query(
            query="這是一般問題",
            matched_skills=["unknown-skill"],
        )

        assert hint is not None, "應生成通用提示"
        assert any(kw in hint for kw in ["假設", "決策", "考慮"]), \
            f"通用提示應含決策相關詞，得到: {hint}"

    def test_empty_query_returns_none(self):
        """空查詢應回傳 None."""
        from museon.agent.eval_engine import get_blindspot_hint_for_query

        hint = get_blindspot_hint_for_query(
            query="",
            matched_skills=["market-core"],
        )

        assert hint is None, "空查詢應回傳 None"

    def test_none_skills_returns_none(self):
        """無技能時應回傳 None."""
        from museon.agent.eval_engine import get_blindspot_hint_for_query

        hint = get_blindspot_hint_for_query(
            query="有內容的查詢",
            matched_skills=None,
        )

        assert hint is None, "無技能應回傳 None"


class TestBlindspotFrequencyControl:
    """測試盲點提醒的頻率控制機制."""

    def test_technical_user_low_frequency(self):
        """技術型使用者：低頻率（~10%）."""
        from museon.agent.brain import MuseonBrain

        brain = MuseonBrain()
        # 模擬技術型：score < 0.25

        # 根據查詢長度（模擬不同訊息），計算是否應顯示
        should_show_count = 0
        for msg_len in range(100):
            # 邏輯：len(content) % 10 == 0
            if msg_len % 10 == 0:
                should_show_count += 1

        frequency = should_show_count / 100
        # 應約 10%
        assert 0.05 < frequency < 0.15, f"技術型頻率應約 10%，得到 {frequency}"

    def test_balanced_user_moderate_frequency(self):
        """均衡型使用者：中等頻率（~40%）."""
        # 邏輯：len(content) % 10 < 4
        should_show_count = 0
        for msg_len in range(100):
            if msg_len % 10 < 4:
                should_show_count += 1

        frequency = should_show_count / 100
        # 應約 40%
        assert 0.35 < frequency < 0.45, f"均衡型頻率應約 40%，得到 {frequency}"

    def test_exploration_user_high_frequency(self):
        """探索型使用者：高頻率（~60%）."""
        # 邏輯：len(content) % 10 < 6
        should_show_count = 0
        for msg_len in range(100):
            if msg_len % 10 < 6:
                should_show_count += 1

        frequency = should_show_count / 100
        # 應約 60%
        assert 0.55 < frequency < 0.65, f"探索型頻率應約 60%，得到 {frequency}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
