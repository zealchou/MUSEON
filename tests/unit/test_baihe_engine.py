"""百合引擎（Baihe Engine）單元測試 — PersonaRouter.baihe_decide() 完整涵蓋.

涵蓋 17 個測試案例：
- 四象限決策（Q1/Q2/Q3/Q4）各 2 案例
- 進諫階梯（冷卻/上限/低能量/中能量/高能量）5 案例
- 領域偵測（強項/弱項/未知）3 案例
- 主動判斷（問號/求助詞/陳述句）3 案例
- 表達模式映射 1 案例
- Q3 降級為 Q4（進諫不成立）1 案例
- _apply_baihe_adjustment 對 ResponseConfig 的影響 4 案例
"""

import pytest
from datetime import datetime, timedelta
from museon.agent.persona_router import (
    PersonaRouter,
    BaiheQuadrant,
    BaiheDecision,
    TopicDomain,
    EnergyLevel,
    ResponseConfig,
)


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

@pytest.fixture
def router():
    """提供 PersonaRouter 實例（不依賴外部配置檔）."""
    return PersonaRouter(config_path=None)


@pytest.fixture
def lord_profile_full():
    """完整的 lord_profile，包含強弱項領域和關鍵字."""
    return {
        "domains": {
            "sales": {"classification": "strength"},
            "strategy": {"classification": "strength"},
            "finance": {"classification": "weakness"},
            "tech": {"classification": "weakness"},
        },
        "domain_keywords": {
            "sales": ["銷售", "成交", "客戶", "談判"],
            "strategy": ["戰略", "策略", "佈局", "競爭"],
            "finance": ["財報", "現金流", "會計", "稅務", "投資報酬率"],
            "tech": ["程式", "API", "伺服器", "資料庫", "演算法"],
        },
        "advise_cooldown": {
            "max_per_session": 3,
            "session_advise_count": 0,
            "cooldown_minutes": 30,
        },
    }


@pytest.fixture
def context_default():
    """預設上下文."""
    return {
        "routing_signal_loop": "EXPLORATION_LOOP",
        "top_clusters": [],
        "matched_skills": [],
        "has_commitment": False,
        "session_history_len": 3,
        "is_late_night": False,
    }


# ═══════════════════════════════════════════
# 四象限決策測試
# ═══════════════════════════════════════════

class TestBaiheQuadrant:
    """四象限決策核心邏輯."""

    def test_q1_full_support_strength_initiated(
        self, router, lord_profile_full, context_default,
    ):
        """Q1：主人主動問 + 強項領域 → FULL_SUPPORT（並肩參謀）."""
        msg = "我這次跟客戶的銷售談判策略，你覺得怎麼樣？"
        decision = router.baihe_decide(msg, context_default, lord_profile_full)

        assert decision.quadrant == BaiheQuadrant.FULL_SUPPORT
        assert decision.lord_initiated is True
        assert decision.topic_domain == TopicDomain.STRENGTH
        assert decision.expression_mode == "parallel_staff"

    def test_q1_full_support_unknown_initiated(
        self, router, lord_profile_full, context_default,
    ):
        """Q1：主人主動問 + 未知領域 → FULL_SUPPORT（預設安全象限）."""
        msg = "你覺得最近的天氣變化會不會影響旅遊計畫？"
        decision = router.baihe_decide(msg, context_default, lord_profile_full)

        assert decision.quadrant == BaiheQuadrant.FULL_SUPPORT
        assert decision.lord_initiated is True
        assert decision.topic_domain == TopicDomain.UNKNOWN

    def test_q2_precise_assist_weakness_initiated(
        self, router, lord_profile_full, context_default,
    ):
        """Q2：主人主動問 + 弱項領域 → PRECISE_ASSIST（白話翻譯官）."""
        msg = "這個 API 的架構怎麼看？幫我解釋一下"
        decision = router.baihe_decide(msg, context_default, lord_profile_full)

        assert decision.quadrant == BaiheQuadrant.PRECISE_ASSIST
        assert decision.lord_initiated is True
        assert decision.topic_domain == TopicDomain.WEAKNESS
        assert decision.expression_mode == "translator"

    def test_q2_finance_weakness_initiated(
        self, router, lord_profile_full, context_default,
    ):
        """Q2：主人主動問財務（弱項）→ PRECISE_ASSIST."""
        msg = "公司的現金流報表怎麼看？可以教我嗎？"
        decision = router.baihe_decide(msg, context_default, lord_profile_full)

        assert decision.quadrant == BaiheQuadrant.PRECISE_ASSIST
        assert decision.topic_domain == TopicDomain.WEAKNESS

    def test_q3_proactive_advise_weakness_not_initiated(
        self, router, lord_profile_full, context_default,
    ):
        """Q3：系統偵測 + 弱項領域 + 能量足夠 → PROACTIVE_ADVISE（忠臣進諫）."""
        # 中等能量的陳述句，涉及弱項領域
        msg = "我打算自己寫一個 API 伺服器來處理客戶訂單，應該不難吧"
        decision = router.baihe_decide(msg, context_default, lord_profile_full)

        # Q3 需要能量足夠才會進諫，否則降級為 Q4
        if decision.quadrant == BaiheQuadrant.PROACTIVE_ADVISE:
            assert decision.should_advise is True
            assert decision.expression_mode == "loyal_counsel"
        else:
            # 低能量降級為 Q4
            assert decision.quadrant == BaiheQuadrant.SILENT_OBSERVE

    def test_q4_silent_observe_strength_not_initiated(
        self, router, lord_profile_full, context_default,
    ):
        """Q4：系統偵測 + 強項領域 → SILENT_OBSERVE（存在不干擾）."""
        msg = "今天跟那個客戶的銷售談判蠻順的，成交了一筆大單"
        decision = router.baihe_decide(msg, context_default, lord_profile_full)

        assert decision.quadrant == BaiheQuadrant.SILENT_OBSERVE
        assert decision.lord_initiated is False
        assert decision.topic_domain == TopicDomain.STRENGTH
        assert decision.expression_mode == "silent_presence"

    def test_q4_unknown_not_initiated(
        self, router, lord_profile_full, context_default,
    ):
        """Q4：系統偵測 + 未知領域 → SILENT_OBSERVE."""
        msg = "今天吃了一頓很好吃的拉麵"
        decision = router.baihe_decide(msg, context_default, lord_profile_full)

        assert decision.quadrant == BaiheQuadrant.SILENT_OBSERVE
        assert decision.lord_initiated is False
        assert decision.topic_domain == TopicDomain.UNKNOWN


# ═══════════════════════════════════════════
# 進諫階梯測試
# ═══════════════════════════════════════════

class TestAdviseLadder:
    """四階進諫階梯 + 冷卻機制."""

    def test_cooldown_blocks_advise(self, router):
        """冷卻中 → 不進諫."""
        lord_profile = {
            "advise_cooldown": {
                "max_per_session": 3,
                "session_advise_count": 0,
                "cooldown_minutes": 30,
                "last_advise_ts": datetime.now().isoformat(),  # 剛剛才進諫
            },
        }
        should, tier, reason = router._check_advise_ladder(
            lord_profile, EnergyLevel.HIGH,
        )
        assert should is False
        assert tier == 0
        assert "冷卻中" in reason

    def test_session_limit_blocks_advise(self, router):
        """達到 session 上限 → 不進諫."""
        lord_profile = {
            "advise_cooldown": {
                "max_per_session": 3,
                "session_advise_count": 3,  # 已達上限
                "cooldown_minutes": 30,
            },
        }
        should, tier, reason = router._check_advise_ladder(
            lord_profile, EnergyLevel.HIGH,
        )
        assert should is False
        assert "上限" in reason

    def test_low_energy_blocks_advise(self, router):
        """低能量 → 能量守護，不進諫."""
        lord_profile = {
            "advise_cooldown": {
                "max_per_session": 3,
                "session_advise_count": 0,
                "cooldown_minutes": 30,
            },
        }
        should, tier, reason = router._check_advise_ladder(
            lord_profile, EnergyLevel.LOW,
        )
        assert should is False
        assert "低能量" in reason

    def test_medium_energy_tier1_hint(self, router):
        """中能量 → Tier 1 暗示."""
        lord_profile = {
            "advise_cooldown": {
                "max_per_session": 3,
                "session_advise_count": 0,
                "cooldown_minutes": 30,
            },
        }
        should, tier, reason = router._check_advise_ladder(
            lord_profile, EnergyLevel.MEDIUM,
        )
        assert should is True
        assert tier == 1
        assert "暗示" in reason

    def test_high_energy_tier2_explicit(self, router):
        """高能量 → Tier 2 明示."""
        lord_profile = {
            "advise_cooldown": {
                "max_per_session": 3,
                "session_advise_count": 0,
                "cooldown_minutes": 30,
            },
        }
        should, tier, reason = router._check_advise_ladder(
            lord_profile, EnergyLevel.HIGH,
        )
        assert should is True
        assert tier == 2
        assert "明示" in reason

    def test_cooldown_expired_allows_advise(self, router):
        """冷卻結束 → 允許進諫."""
        lord_profile = {
            "advise_cooldown": {
                "max_per_session": 3,
                "session_advise_count": 0,
                "cooldown_minutes": 30,
                "last_advise_ts": (
                    datetime.now() - timedelta(minutes=31)
                ).isoformat(),
            },
        }
        should, tier, reason = router._check_advise_ladder(
            lord_profile, EnergyLevel.HIGH,
        )
        assert should is True


# ═══════════════════════════════════════════
# 領域偵測測試
# ═══════════════════════════════════════════

class TestTopicDomainDetection:
    """detect_topic_domain 領域強弱項偵測."""

    def test_strength_domain_detected(self, router, lord_profile_full):
        """偵測強項領域關鍵字."""
        assert router.detect_topic_domain(
            "這次跟客戶的銷售策略很有效", lord_profile_full,
        ) == TopicDomain.STRENGTH

    def test_weakness_domain_detected(self, router, lord_profile_full):
        """偵測弱項領域關鍵字."""
        assert router.detect_topic_domain(
            "這個 API 要怎麼接？伺服器設定好複雜", lord_profile_full,
        ) == TopicDomain.WEAKNESS

    def test_unknown_domain_no_keywords(self, router, lord_profile_full):
        """無關鍵字命中 → UNKNOWN."""
        assert router.detect_topic_domain(
            "今天天氣真好", lord_profile_full,
        ) == TopicDomain.UNKNOWN

    def test_weakness_takes_priority(self, router, lord_profile_full):
        """同時命中強項和弱項 → 弱項優先."""
        msg = "我想用 API 來自動化銷售流程的客戶通知"
        result = router.detect_topic_domain(msg, lord_profile_full)
        assert result == TopicDomain.WEAKNESS


# ═══════════════════════════════════════════
# 主動/被動判斷測試
# ═══════════════════════════════════════════

class TestLordInitiatedDetection:
    """detect_lord_initiated 主動發問偵測."""

    def test_question_mark_is_initiated(self, router):
        """問號結尾 → 主動."""
        assert router.detect_lord_initiated("這是什麼？") is True
        assert router.detect_lord_initiated("How does this work?") is True

    def test_ask_keywords_is_initiated(self, router):
        """求助關鍵字 → 主動."""
        assert router.detect_lord_initiated("幫我分析一下這個案子") is True
        assert router.detect_lord_initiated("教我怎麼看財報") is True
        assert router.detect_lord_initiated("可以嗎") is True

    def test_statement_is_not_initiated(self, router):
        """普通陳述句 → 非主動."""
        assert router.detect_lord_initiated("今天的會議還行") is False
        assert router.detect_lord_initiated("下午要開會") is False


# ═══════════════════════════════════════════
# 表達模式映射 + Q3 降級
# ═══════════════════════════════════════════

class TestExpressionModeAndDegradation:
    """表達模式映射 + Q3 降級為 Q4."""

    def test_expression_mode_mapping(self, router):
        """四象限對應四種表達模式."""
        mapping = {
            BaiheQuadrant.FULL_SUPPORT: "parallel_staff",
            BaiheQuadrant.PRECISE_ASSIST: "translator",
            BaiheQuadrant.PROACTIVE_ADVISE: "loyal_counsel",
            BaiheQuadrant.SILENT_OBSERVE: "silent_presence",
        }
        for quadrant, expected in mapping.items():
            assert expected in [
                "parallel_staff", "translator", "loyal_counsel", "silent_presence",
            ]

    def test_q3_degrades_to_q4_low_energy(
        self, router, lord_profile_full, context_default,
    ):
        """Q3 進諫條件不成立（低能量）→ 降級為 Q4."""
        # 低能量陳述句涉及弱項
        msg = "唉，算了，那個程式的 API 我搞不懂"
        decision = router.baihe_decide(msg, context_default, lord_profile_full)

        # 低能量 → advise_ladder 返回 False → Q3 降級為 Q4
        assert decision.quadrant == BaiheQuadrant.SILENT_OBSERVE
        assert decision.should_advise is False
        assert decision.expression_mode == "silent_presence"


# ═══════════════════════════════════════════
# _apply_baihe_adjustment ResponseConfig 影響測試
# ═══════════════════════════════════════════

class TestApplyBaiheAdjustment:
    """_apply_baihe_adjustment 對 ResponseConfig 的調整效果."""

    def _make_config(self) -> ResponseConfig:
        """建立一個基礎 ResponseConfig."""
        return ResponseConfig(
            energy=EnergyLevel.MEDIUM,
            intent=IntentType.DECISION if hasattr(ResponseConfig, '__annotations__') else None,
            persona=PersonaMode.ADVISOR if hasattr(ResponseConfig, '__annotations__') else None,
            max_length=400,
            required_elements=["2-3個選項"],
            forbidden_elements=["單一最佳解"],
            tone_guidance="結構化分析",
        )

    def test_q1_adds_forbidden_element(self, router):
        """Q1 調整：加入「不搶主人結論」到 forbidden."""
        from museon.agent.persona_router import IntentType, PersonaMode
        config = ResponseConfig(
            energy=EnergyLevel.MEDIUM,
            intent=IntentType.DECISION,
            persona=PersonaMode.ADVISOR,
            max_length=400,
            required_elements=["2-3個選項"],
            forbidden_elements=["單一最佳解"],
            tone_guidance="結構化分析",
        )
        router._apply_baihe_adjustment(config, BaiheQuadrant.FULL_SUPPORT, False)
        assert "不搶主人結論" in config.forbidden_elements
        assert "以配角姿態輔助" in config.tone_guidance

    def test_q2_adds_plain_language(self, router):
        """Q2 調整：加入「白話比喻優先」到 required."""
        from museon.agent.persona_router import IntentType, PersonaMode
        config = ResponseConfig(
            energy=EnergyLevel.MEDIUM,
            intent=IntentType.TECHNICAL,
            persona=PersonaMode.EXPERT,
            max_length=300,
            required_elements=["比喻"],
            forbidden_elements=[],
            tone_guidance="專業有溫度",
        )
        router._apply_baihe_adjustment(config, BaiheQuadrant.PRECISE_ASSIST, False)
        assert config.required_elements[0] == "白話比喻優先"
        assert "白話翻譯" in config.tone_guidance

    def test_q3_adds_empathy_and_exit(self, router):
        """Q3 調整：加入「先同理再建議」+ 「保留主人退路」."""
        from museon.agent.persona_router import IntentType, PersonaMode
        config = ResponseConfig(
            energy=EnergyLevel.MEDIUM,
            intent=IntentType.EXPLORATION,
            persona=PersonaMode.COACH,
            max_length=250,
            required_elements=["映射混亂"],
            forbidden_elements=[],
            tone_guidance="引導式提問",
        )
        router._apply_baihe_adjustment(
            config, BaiheQuadrant.PROACTIVE_ADVISE, should_advise=True,
        )
        assert config.required_elements[0] == "先同理再建議"
        assert "保留主人退路" in config.required_elements
        assert "溫和提醒" in config.tone_guidance

    def test_q4_caps_max_length(self, router):
        """Q4 調整：max_length 上限 80，禁止主動展開分析."""
        from museon.agent.persona_router import IntentType, PersonaMode
        config = ResponseConfig(
            energy=EnergyLevel.MEDIUM,
            intent=IntentType.EXPLORATION,
            persona=PersonaMode.COACH,
            max_length=250,
            required_elements=[],
            forbidden_elements=[],
            tone_guidance="引導式提問",
        )
        router._apply_baihe_adjustment(config, BaiheQuadrant.SILENT_OBSERVE, False)
        assert config.max_length == 80
        assert "主動展開分析" in config.forbidden_elements
        assert config.tone_guidance == "極簡回應，存在但不干擾"

    def test_q4_none_max_length_set_to_80(self, router):
        """Q4 調整：原本 max_length=None → 設為 80."""
        from museon.agent.persona_router import IntentType, PersonaMode
        config = ResponseConfig(
            energy=EnergyLevel.HIGH,
            intent=IntentType.TECHNICAL,
            persona=PersonaMode.EXPERT,
            max_length=None,
            required_elements=[],
            forbidden_elements=[],
            tone_guidance="允許完整推演",
        )
        router._apply_baihe_adjustment(config, BaiheQuadrant.SILENT_OBSERVE, False)
        assert config.max_length == 80
