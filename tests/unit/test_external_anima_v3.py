"""Phase 3 單元測試：Per-Client ANIMA v3.0 + 外部用戶觀察升級.

覆蓋範圍：
  - ExternalAnimaManager: v3.0 schema, v2→v3 遷移, 搜尋功能
  - _observe_external_user(): 信任演化, L6 溝通風格, L1 事實提取, 八原語
  - SensitivityChecker: L1/L2/L3 敏感度分類（Phase 1A 驗證）
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from museon.governance.multi_tenant import (
    ExternalAnimaManager,
    SensitivityChecker,
    EscalationQueue,
    SENSITIVE_L1,
    SENSITIVE_L2,
    SENSITIVE_L3,
)


# ── Fixture ─────────────────────────────────────────────

@pytest.fixture
def data_dir(tmp_path):
    """建立測試用資料目錄."""
    return tmp_path


@pytest.fixture
def ext_mgr(data_dir):
    """ExternalAnimaManager 實例."""
    return ExternalAnimaManager(data_dir)


@pytest.fixture
def brain(tmp_path):
    """最小化 MuseonBrain 實例（用於 _observe_external_user 測試）."""
    from museon.agent.brain import MuseonBrain

    with patch.object(MuseonBrain, "__init__", lambda self: None):
        b = MuseonBrain()
    b.data_dir = tmp_path
    b._primal_detector = None
    return b


# ══════════════════════════════════════════════════════════════
# 1. ExternalAnimaManager v3.0 Schema
# ══════════════════════════════════════════════════════════════

class TestExternalAnimaV3Schema:
    """v3.0 預設結構驗證."""

    def test_default_anima_version(self, ext_mgr):
        """預設 ANIMA 版本為 3.0.0."""
        anima = ext_mgr._default_anima("user_001")
        assert anima["version"] == "3.0.0"

    def test_default_has_profile(self, ext_mgr):
        """v3.0 包含 profile 區塊."""
        anima = ext_mgr._default_anima("user_001")
        assert "profile" in anima
        assert anima["profile"]["name"] is None
        assert anima["profile"]["role"] is None
        assert anima["profile"]["business_type"] == "unknown"

    def test_default_has_relationship(self, ext_mgr):
        """v3.0 包含 relationship 區塊."""
        anima = ext_mgr._default_anima("user_001")
        assert "relationship" in anima
        rel = anima["relationship"]
        assert rel["trust_level"] == "initial"
        assert rel["total_interactions"] == 0
        assert rel["positive_signals"] == 0
        assert rel["negative_signals"] == 0

    def test_default_has_seven_layers(self, ext_mgr):
        """v3.0 包含 seven_layers 區塊."""
        anima = ext_mgr._default_anima("user_001")
        assert "seven_layers" in anima
        layers = anima["seven_layers"]
        assert "L1_facts" in layers
        assert "L2_personality" in layers
        assert "L6_communication_style" in layers

    def test_default_l6_communication_style(self, ext_mgr):
        """L6 溝通風格預設值."""
        anima = ext_mgr._default_anima("user_001")
        l6 = anima["seven_layers"]["L6_communication_style"]
        assert l6["detail_level"] == "moderate"
        assert l6["emoji_usage"] == "none"
        assert l6["language_mix"] == "mixed"
        assert l6["avg_msg_length"] == 0
        assert l6["question_style"] == "open"
        assert l6["tone"] == "casual"

    def test_default_has_eight_primals(self, ext_mgr):
        """v3.0 包含 eight_primals 區塊."""
        anima = ext_mgr._default_anima("user_001")
        assert "eight_primals" in anima
        assert isinstance(anima["eight_primals"], dict)

    def test_default_has_legacy_fields(self, ext_mgr):
        """v3.0 保留向下相容欄位."""
        anima = ext_mgr._default_anima("user_001")
        assert "preferences" in anima
        assert "recent_topics" in anima
        assert "groups_seen_in" in anima
        assert "relationship_to_owner" in anima


# ══════════════════════════════════════════════════════════════
# 2. Schema Migration v2 → v3
# ══════════════════════════════════════════════════════════════

class TestSchemaMigration:
    """v2 → v3 Schema 遷移."""

    def test_v2_migrated_to_v3(self, ext_mgr):
        """v2.0.0 檔案載入後自動升級為 v3.0.0."""
        v2_data = {
            "version": "2.0.0",
            "user_id": "user_002",
            "created_at": "2025-01-01T00:00:00",
            "interaction_count": 15,
            "last_seen": "2025-06-01T12:00:00",
            "display_name": "Alice",
            "context_summary": "常問技術問題",
            "eight_primals": {"Interesting": 0.6},
            "preferences": {"lang": "zh"},
            "recent_topics": ["AI", "React"],
            "groups_seen_in": [-100123],
            "relationship_to_owner": "客戶",
        }
        path = ext_mgr._path("user_002")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(v2_data, ensure_ascii=False), encoding="utf-8")

        loaded = ext_mgr.load("user_002")
        assert loaded["version"] == "3.0.0"
        assert "profile" in loaded
        assert "relationship" in loaded
        assert "seven_layers" in loaded

    def test_v2_migration_preserves_display_name(self, ext_mgr):
        """遷移時 display_name 映射到 profile.name."""
        v2_data = {
            "version": "2.0.0",
            "user_id": "user_003",
            "display_name": "Bob",
            "created_at": "2025-01-01T00:00:00",
            "interaction_count": 5,
        }
        path = ext_mgr._path("user_003")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(v2_data, ensure_ascii=False), encoding="utf-8")

        loaded = ext_mgr.load("user_003")
        assert loaded["profile"]["name"] == "Bob"

    def test_v2_migration_preserves_interaction_count(self, ext_mgr):
        """遷移時 interaction_count 映射到 relationship.total_interactions."""
        v2_data = {
            "version": "2.0.0",
            "user_id": "user_004",
            "created_at": "2025-01-01T00:00:00",
            "interaction_count": 42,
            "last_seen": "2025-06-01T12:00:00",
        }
        path = ext_mgr._path("user_004")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(v2_data, ensure_ascii=False), encoding="utf-8")

        loaded = ext_mgr.load("user_004")
        assert loaded["relationship"]["total_interactions"] == 42

    def test_v1_migrated_to_v3(self, ext_mgr):
        """無 version 欄位的 v1 檔案 → 自動升級至 v3.0.0."""
        v1_data = {
            "user_id": "user_005",
            "created_at": "2024-06-01T00:00:00",
            "interaction_count": 3,
            "display_name": "Charlie",
        }
        path = ext_mgr._path("user_005")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(v1_data, ensure_ascii=False), encoding="utf-8")

        loaded = ext_mgr.load("user_005")
        assert loaded["version"] == "3.0.0"
        assert "profile" in loaded
        assert "relationship" in loaded
        assert "seven_layers" in loaded

    def test_v3_no_migration(self, ext_mgr):
        """v3 檔案不再遷移."""
        v3_data = ext_mgr._default_anima("user_006")
        ext_mgr.save("user_006", v3_data)

        loaded = ext_mgr.load("user_006")
        assert loaded["version"] == "3.0.0"


# ══════════════════════════════════════════════════════════════
# 3. ExternalAnimaManager CRUD
# ══════════════════════════════════════════════════════════════

class TestExternalAnimaCRUD:
    """基本 CRUD 操作."""

    def test_load_nonexistent_returns_default(self, ext_mgr):
        """不存在的用戶 → 回傳預設 v3 結構."""
        anima = ext_mgr.load("new_user")
        assert anima["version"] == "3.0.0"
        assert anima["user_id"] == "new_user"

    def test_save_and_reload(self, ext_mgr):
        """save → load 一致性."""
        anima = ext_mgr._default_anima("user_save")
        anima["display_name"] = "SaveTest"
        anima["context_summary"] = "測試儲存"
        ext_mgr.save("user_save", anima)

        loaded = ext_mgr.load("user_save")
        assert loaded["display_name"] == "SaveTest"
        assert loaded["context_summary"] == "測試儲存"

    def test_update_increments_interaction(self, ext_mgr):
        """update() 增加 interaction_count."""
        ext_mgr.update("user_upd", display_name="Updater")
        anima = ext_mgr.load("user_upd")
        assert anima["interaction_count"] == 1
        assert anima["display_name"] == "Updater"

        ext_mgr.update("user_upd")
        anima = ext_mgr.load("user_upd")
        assert anima["interaction_count"] == 2

    def test_update_records_group(self, ext_mgr):
        """update() 記錄 group_id."""
        ext_mgr.update("user_grp", group_id=-100999)
        anima = ext_mgr.load("user_grp")
        assert -100999 in anima["groups_seen_in"]

    def test_search_by_keyword(self, ext_mgr):
        """search_by_keyword() 搜尋 display_name."""
        anima = ext_mgr._default_anima("user_search")
        anima["display_name"] = "Alice Wang"
        anima["context_summary"] = "常問 AI 相關問題"
        ext_mgr.save("user_search", anima)

        results = ext_mgr.search_by_keyword("Alice")
        assert len(results) >= 1
        assert any(r["display_name"] == "Alice Wang" for r in results)

    def test_search_by_context_summary(self, ext_mgr):
        """search_by_keyword() 搜尋 context_summary."""
        anima = ext_mgr._default_anima("user_topic")
        anima["context_summary"] = "常討論 React 效能優化"
        ext_mgr.save("user_topic", anima)

        results = ext_mgr.search_by_keyword("React")
        assert len(results) >= 1


# ══════════════════════════════════════════════════════════════
# 4. _observe_external_user() — 信任演化 + L6 + L1
# ══════════════════════════════════════════════════════════════

class TestObserveExternalUser:
    """brain._observe_external_user() v3.0 完整觀察."""

    def _make_ext_mgr_mock(self, brain, anima_data=None):
        """建立可控的 ExternalAnimaManager mock."""
        if anima_data is None:
            anima_data = ExternalAnimaManager._default_anima("ext_001")

        mock_mgr = MagicMock()
        mock_mgr.load.return_value = anima_data
        mock_mgr.save = MagicMock()

        return mock_mgr

    def test_empty_user_id_returns(self, brain):
        """空 user_id → 直接返回."""
        brain._observe_external_user("test", "", "Alice")
        # 無例外即通過

    def test_owner_skipped(self, brain):
        """Owner 發言 → 跳過觀察."""
        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            MockMgr.return_value = mock_instance
            brain._observe_external_user(
                "test", "owner_id", "Zeal",
                metadata={"is_owner": True},
            )
            # load 不應被呼叫（因為 owner 被跳過）
            mock_instance.load.assert_not_called()

    def test_trust_evolution_initial_to_building(self, brain):
        """5 次互動 → trust: initial → building."""
        anima = ExternalAnimaManager._default_anima("ext_trust")
        anima["relationship"]["total_interactions"] = 4  # 觀察後會 +1 = 5

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user("你好", "ext_trust", "Trust")

            saved = mock_instance.save.call_args[0][1]
            assert saved["relationship"]["trust_level"] == "building"
            assert saved["relationship"]["total_interactions"] == 5

    def test_trust_evolution_building_to_growing(self, brain):
        """30 次互動 → trust: building → growing."""
        anima = ExternalAnimaManager._default_anima("ext_grow")
        anima["relationship"]["total_interactions"] = 29
        anima["relationship"]["trust_level"] = "building"

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user("你好", "ext_grow", "Grow")

            saved = mock_instance.save.call_args[0][1]
            assert saved["relationship"]["trust_level"] == "growing"

    def test_trust_evolution_to_established(self, brain):
        """100 次互動 → trust: → established."""
        anima = ExternalAnimaManager._default_anima("ext_est")
        anima["relationship"]["total_interactions"] = 99
        anima["relationship"]["trust_level"] = "growing"

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user("你好", "ext_est", "Est")

            saved = mock_instance.save.call_args[0][1]
            assert saved["relationship"]["trust_level"] == "established"

    def test_l6_message_length_rolling_avg(self, brain):
        """L6 訊息長度 rolling average (0.85 * old + 0.15 * new)."""
        anima = ExternalAnimaManager._default_anima("ext_l6")
        anima["seven_layers"]["L6_communication_style"]["avg_msg_length"] = 100

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            content = "x" * 200  # 200 字元
            brain._observe_external_user(content, "ext_l6", "L6Test")

            saved = mock_instance.save.call_args[0][1]
            l6 = saved["seven_layers"]["L6_communication_style"]
            expected = int(100 * 0.85 + 200 * 0.15)  # 115
            assert l6["avg_msg_length"] == expected

    def test_l6_detail_level_detailed(self, brain):
        """msg_len > 200 → detail_level = detailed."""
        anima = ExternalAnimaManager._default_anima("ext_detail")

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            content = "x" * 250
            brain._observe_external_user(content, "ext_detail", "Detail")

            saved = mock_instance.save.call_args[0][1]
            assert saved["seven_layers"]["L6_communication_style"]["detail_level"] == "detailed"

    def test_l6_detail_level_concise(self, brain):
        """msg_len < 40 → detail_level = concise."""
        anima = ExternalAnimaManager._default_anima("ext_concise")

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user("短訊息", "ext_concise", "Concise")

            saved = mock_instance.save.call_args[0][1]
            assert saved["seven_layers"]["L6_communication_style"]["detail_level"] == "concise"

    def test_l6_question_style_open(self, brain):
        """≥2 個問號 → question_style = open."""
        anima = ExternalAnimaManager._default_anima("ext_qs")

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "這個功能怎麼用？能不能幫我看一下？", "ext_qs", "QsTest",
            )

            saved = mock_instance.save.call_args[0][1]
            assert saved["seven_layers"]["L6_communication_style"]["question_style"] == "open"

    def test_l6_question_style_closed(self, brain):
        """1 個問號 → question_style = closed."""
        anima = ExternalAnimaManager._default_anima("ext_closed")

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "這個功能什麼時候上線？", "ext_closed", "Closed",
            )

            saved = mock_instance.save.call_args[0][1]
            assert saved["seven_layers"]["L6_communication_style"]["question_style"] == "closed"

    def test_l6_question_style_directive(self, brain):
        """0 個問號 → question_style = directive."""
        anima = ExternalAnimaManager._default_anima("ext_dir")

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "幫我安排一下明天的會議", "ext_dir", "Dir",
            )

            saved = mock_instance.save.call_args[0][1]
            assert saved["seven_layers"]["L6_communication_style"]["question_style"] == "directive"

    def test_l1_fact_extraction_occupation(self, brain):
        """職業關鍵字 → L1 事實提取."""
        anima = ExternalAnimaManager._default_anima("ext_fact")

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "我在台積電工作，做的是半導體製程", "ext_fact", "Fact",
            )

            saved = mock_instance.save.call_args[0][1]
            facts = saved["seven_layers"]["L1_facts"]
            assert len(facts) >= 1
            assert facts[0]["category"] == "occupation"

    def test_l1_fact_extraction_family(self, brain):
        """家人關鍵字 → L1 事實提取."""
        anima = ExternalAnimaManager._default_anima("ext_family")

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "我老婆下週要出差一個禮拜", "ext_family", "Family",
            )

            saved = mock_instance.save.call_args[0][1]
            facts = saved["seven_layers"]["L1_facts"]
            assert len(facts) >= 1
            assert facts[0]["category"] == "family"

    def test_l1_facts_max_30(self, brain):
        """L1 事實最多保留 30 筆."""
        anima = ExternalAnimaManager._default_anima("ext_max30")
        # 預填 30 筆事實
        anima["seven_layers"]["L1_facts"] = [
            {"category": "occupation", "snippet": f"test_{i}", "date": "2025-01-01"}
            for i in range(30)
        ]

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "我最近在公司負責新專案", "ext_max30", "Max",
            )

            saved = mock_instance.save.call_args[0][1]
            facts = saved["seven_layers"]["L1_facts"]
            assert len(facts) <= 30

    def test_recent_topics_recorded(self, brain):
        """近期主題記錄."""""
        anima = ExternalAnimaManager._default_anima("ext_topic")

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "我們來討論一下 Q2 的行銷策略", "ext_topic", "Topic",
            )

            saved = mock_instance.save.call_args[0][1]
            topics = saved["recent_topics"]
            assert len(topics) >= 1
            assert "行銷策略" in topics[-1]["snippet"]

    def test_recent_topics_max_20(self, brain):
        """近期主題最多保留 20 筆."""
        anima = ExternalAnimaManager._default_anima("ext_topics20")
        anima["recent_topics"] = [
            {"snippet": f"topic_{i}", "date": "2025-01-01"}
            for i in range(20)
        ]

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "新的討論主題", "ext_topics20", "Topics",
            )

            saved = mock_instance.save.call_args[0][1]
            topics = saved["recent_topics"]
            assert len(topics) <= 20

    def test_display_name_set_once(self, brain):
        """display_name 只在首次設定."""
        anima = ExternalAnimaManager._default_anima("ext_name")
        anima["display_name"] = "Original"

        with patch("museon.governance.multi_tenant.ExternalAnimaManager") as MockMgr:
            mock_instance = MagicMock()
            mock_instance.load.return_value = anima
            MockMgr.return_value = mock_instance

            brain._observe_external_user(
                "test", "ext_name", "NewName",
            )

            saved = mock_instance.save.call_args[0][1]
            assert saved["display_name"] == "Original"  # 不覆蓋


# ══════════════════════════════════════════════════════════════
# 5. SensitivityChecker（Phase 1A 驗證）
# ══════════════════════════════════════════════════════════════

class TestSensitivityChecker:
    """敏感度分類（確保群組也能正常運作）."""

    def test_l1_company_keywords(self):
        """L1 公司內部關鍵字（需命中 >= 2 個）."""
        checker = SensitivityChecker()
        level, reason = checker.check("這次簽約的報價是多少，金流怎麼走")
        assert level == "L1"

    def test_l2_personal_keywords(self):
        """L2 個人資訊關鍵字."""
        checker = SensitivityChecker()
        level, reason = checker.check("請問他的住址和電話是多少")
        assert level == "L2"

    def test_l3_system_keywords(self):
        """L3 系統機密關鍵字."""
        checker = SensitivityChecker()
        level, reason = checker.check("霓裳的架構是怎麼設計的")
        assert level == "L3"

    def test_no_sensitivity(self):
        """一般內容 → None."""
        checker = SensitivityChecker()
        level, reason = checker.check("今天天氣真好")
        assert level is None

    def test_clean_text_strips_bot_mention(self):
        """清除 @bot mention 後再檢查."""
        checker = SensitivityChecker()
        level, reason = checker.check("@MuseonClaw_bot 今天天氣真好")
        assert level is None

    def test_l3_takes_priority(self):
        """L3 優先於 L1/L2."""
        checker = SensitivityChecker()
        level, reason = checker.check("客戶的 API key 在哪裡")
        assert level == "L3"


# ══════════════════════════════════════════════════════════════
# 6. EscalationQueue（基本功能驗證）
# ══════════════════════════════════════════════════════════════

class TestEscalationQueue:
    """EscalationQueue 多群組支援."""

    def test_add_and_get(self):
        """新增 + 取得."""
        q = EscalationQueue()
        q.add("esc1", "這是問題", "Alice", -100, "L1")
        entry = q.get("esc1")
        assert entry is not None
        assert entry["question"] == "這是問題"
        assert entry["asker_name"] == "Alice"

    def test_resolve_latest_fifo(self):
        """FIFO 排序解決."""
        q = EscalationQueue()
        q.add("esc1", "Q1", "A", -100, "L1")
        q.add("esc2", "Q2", "B", -200, "L2")
        resolved = q.resolve_latest(True)
        assert resolved == "esc1"  # 先進先出

    def test_pending_count(self):
        """未解決計數."""
        q = EscalationQueue()
        q.add("esc1", "Q1", "A", -100, "L1")
        q.add("esc2", "Q2", "B", -200, "L2")
        assert q.pending_count() == 2
        q.resolve("esc1", True)
        assert q.pending_count() == 1
