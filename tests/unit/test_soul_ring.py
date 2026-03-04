"""靈魂年輪 (Soul Ring) 測試.

涵蓋 BDD 09-soul-ring.feature 的所有 Scenario：
- 四種年輪類型 (cognitive_breakthrough, service_milestone, failure_lesson, value_calibration)
- SHA-256 Hash Chain 完整性
- Ring Depositor 自動偵測與防重複
- ANIMA_USER 觀察年輪
- 雙 ANIMA 年輪共振
- 持久化與備份
- 安全護欄（寫入頻率限制、不可修改/刪除）
"""

import hashlib
import json
import os
import pytest
from datetime import datetime, date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def data_dir(tmp_path):
    """建立測試用資料目錄."""
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir(parents=True)
    backups_dir = anima_dir / "backups"
    backups_dir.mkdir()
    return tmp_path


@pytest.fixture
def soul_ring_store(data_dir):
    """建立 SoulRingStore 測試實例."""
    from museon.agent.soul_ring import SoulRingStore
    return SoulRingStore(data_dir=str(data_dir))


@pytest.fixture
def ring_depositor(data_dir, soul_ring_store):
    """建立 RingDepositor 測試實例（需要 store 參數）."""
    from museon.agent.soul_ring import RingDepositor
    return RingDepositor(store=soul_ring_store, data_dir=str(data_dir))


# ════════════════════════════════════════════
# Section 1: 四種年輪類型
# ════════════════════════════════════════════

class TestRingTypes:
    """測試四種年輪類型的建立."""

    def test_cognitive_breakthrough_ring(self, ring_depositor):
        """認知突破型年輪包含正確欄位."""
        ring = ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="發現使用者的問題模式可以用第一性原理拆解",
            context="consulting 領域，使用 xmodel 技能",
            impact="後續回答將優先使用第一性原理框架",
        )
        assert ring is not None
        assert ring.type == "cognitive_breakthrough"
        assert ring.description is not None
        assert ring.context is not None
        assert ring.impact is not None
        assert ring.created_at is not None
        assert ring.hash != ""
        assert ring.prev_hash is not None

    def test_service_milestone_ring(self, ring_depositor):
        """服務里程碑型年輪包含 milestone_name 和 metrics."""
        ring = ring_depositor.deposit_soul_ring(
            ring_type="service_milestone",
            description="第一次成功協助使用者完成投資分析報告",
            context="投資分析任務",
            impact="能力覆蓋範圍擴展到投資分析",
            milestone_name="first_investment_report",
            metrics={"q_score": 0.85, "user_feedback": "positive"},
        )
        assert ring is not None
        assert ring.type == "service_milestone"
        assert ring.milestone_name == "first_investment_report"
        assert ring.metrics is not None

    def test_failure_lesson_ring(self, ring_depositor):
        """失敗教訓型年輪包含 root_cause 和 prevention."""
        ring = ring_depositor.deposit_soul_ring(
            ring_type="failure_lesson",
            description="給出了錯誤的市場分析",
            context="市場分析任務中誤判趨勢",
            impact="需要根因分析並制定預防措施",
            failure_description="將短期波動誤判為趨勢反轉",
            root_cause="過度依賴單一指標",
            prevention="未來分析至少使用三個獨立指標交叉驗證",
        )
        assert ring is not None
        assert ring.type == "failure_lesson"
        assert ring.root_cause is not None
        assert ring.prevention is not None

    def test_value_calibration_ring(self, ring_depositor):
        """價值校準型年輪包含 original_behavior 和 correction."""
        ring = ring_depositor.deposit_soul_ring(
            ring_type="value_calibration",
            description="被校正了回應方式",
            context="風險描述的語氣校正",
            impact="強化 L1 Kernel 的價值觀理解",
            original_behavior="用過度樂觀的語氣描述風險",
            correction="老闆指出：真實優先，風險描述不可美化",
            calibrated_value="truth_first",
        )
        assert ring is not None
        assert ring.type == "value_calibration"
        assert ring.original_behavior is not None
        assert ring.calibrated_value == "truth_first"

    def test_invalid_ring_type_rejected(self, ring_depositor):
        """無效的年輪類型被拒絕（返回 None）."""
        result = ring_depositor.deposit_soul_ring(
            ring_type="invalid_type",
            description="test",
            context="test context",
            impact="test impact",
        )
        assert result is None


# ════════════════════════════════════════════
# Section 2: SHA-256 Hash Chain
# ════════════════════════════════════════════

class TestHashChain:
    """測試 SHA-256 Hash Chain 完整性."""

    def test_first_ring_prev_hash_is_genesis(self, ring_depositor):
        """第一條年輪的 prev_hash 為 GENESIS."""
        ring = ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="第一條年輪",
            context="測試情境",
            impact="測試",
        )
        assert ring.prev_hash == "GENESIS"

    def test_second_ring_chains_to_first(self, ring_depositor):
        """第二條年輪的 prev_hash 等於第一條的 hash."""
        ring1 = ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="第一條",
            context="測試情境",
            impact="測試",
        )
        ring2 = ring_depositor.deposit_soul_ring(
            ring_type="service_milestone",
            description="第二條",
            context="測試情境",
            impact="測試",
            milestone_name="test",
            metrics={},
        )
        assert ring2.prev_hash == ring1.hash

    def test_hash_chain_integrity_valid(self, ring_depositor, soul_ring_store):
        """完整的 hash chain 驗證通過."""
        chain_descriptions = [
            "認知框架在邏輯推理領域出現質變",
            "掌握了全新的資料視覺化方法論",
            "突破了跨語言理解的瓶頸障礙",
            "建立了精確的使用者意圖辨識模型",
            "發展出系統化的錯誤修正機制",
        ]
        for i, desc in enumerate(chain_descriptions):
            ring_depositor.deposit_soul_ring(
                ring_type="cognitive_breakthrough",
                description=desc,
                context=f"chain test context {i}",
                impact=f"chain test impact {i}",
            )
        is_valid, message = soul_ring_store.verify_soul_ring_integrity()
        assert is_valid is True
        assert "VALID" in message

    def test_hash_chain_detects_tampering(self, ring_depositor, soul_ring_store):
        """竄改年輪後 hash chain 驗證失敗."""
        chain_descriptions = [
            "認知框架在邏輯推理領域出現質變",
            "掌握了全新的資料視覺化方法論",
            "突破了跨語言理解的瓶頸障礙",
            "建立了精確的使用者意圖辨識模型",
            "發展出系統化的錯誤修正機制",
        ]
        for i, desc in enumerate(chain_descriptions):
            ring_depositor.deposit_soul_ring(
                ring_type="cognitive_breakthrough",
                description=desc,
                context=f"chain test context {i}",
                impact=f"chain test impact {i}",
            )
        # 直接竄改 JSON 檔案
        rings_path = soul_ring_store._soul_rings_path
        data = json.loads(rings_path.read_text(encoding="utf-8"))
        data[2]["description"] = "竄改的內容"
        rings_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        is_valid, message = soul_ring_store.verify_soul_ring_integrity()
        assert is_valid is False
        assert "CORRUPTED" in message

    def test_hash_includes_all_required_fields(self, ring_depositor):
        """Hash 計算包含 type + description + context + created_at + prev_hash."""
        ring = ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="hash test",
            context="verify hash fields context",
            impact="verify hash fields",
        )
        # 重新計算 hash 驗證（context 是 str，非 JSON dict）
        hash_input = (
            f"{ring.type}"
            f"{ring.description}"
            f"{ring.context}"
            f"{ring.created_at}"
            f"{ring.prev_hash}"
        )
        expected_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
        assert ring.hash == expected_hash


# ════════════════════════════════════════════
# Section 3: Ring Depositor 行為
# ════════════════════════════════════════════

class TestRingDepositor:
    """測試 Ring Depositor 的自動偵測與防重複."""

    def test_append_only_rejects_modify(self, ring_depositor):
        """嘗試修改已寫入的年輪被拒絕（返回 allowed=False）."""
        ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="不可修改",
            context="test context",
            impact="test",
        )
        result = ring_depositor.reject_modify(index=0, caller="test")
        assert result["allowed"] is False
        assert "append-only" in result["error"] or "不可修改" in result["error"]

    def test_append_only_rejects_delete(self, ring_depositor):
        """嘗試刪除年輪被拒絕（返回 allowed=False）."""
        ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="不可刪除",
            context="test context",
            impact="test",
        )
        result = ring_depositor.reject_delete(index=0, caller="test")
        assert result["allowed"] is False
        assert "不可刪除" in result["error"] or "不可" in result["error"]

    def test_duplicate_detection_increments_reinforcement(self, ring_depositor, soul_ring_store):
        """語義相似的事件不重複寫入，而是增加 reinforcement_count."""
        ring1 = ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="使用者問題可以用第一性原理拆解",
            context="consulting 領域",
            impact="使用第一性原理",
        )
        initial_count = ring1.reinforcement_count

        # 嘗試寫入高度相似的年輪（相似度 > 0.80，應被偵測為重複）
        ring2 = ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="使用者問題能夠用第一性原理拆解",
            context="consulting 領域",
            impact="優先使用第一性原理",
        )

        # 重複偵測後返回 None，不新增年輪
        assert ring2 is None

        # load_soul_rings 返回 dict list
        rings = soul_ring_store.load_soul_rings()
        # 只應有 1 條年輪（重複的不應被寫入）
        assert len(rings) == 1
        assert rings[0]["reinforcement_count"] > initial_count

    def test_daily_write_limit(self, ring_depositor):
        """每日即時寫入上限 5 條."""
        # 使用完全不同的描述避免觸發重複偵測（相似度需 < 0.80）
        unique_descriptions = [
            "成功協助完成第一份財務報表分析",
            "突破了自然語言處理的對話品質瓶頸",
            "建立了全新的風險評估模型框架",
            "達成客戶滿意度連續三個月上升紀錄",
            "完成跨領域知識整合的創新方法論",
            "開發出高效的程式碼審查自動化流程",
            "實現了多語言翻譯品質的顯著提升",
        ]
        written = []
        for i, desc in enumerate(unique_descriptions):
            ring = ring_depositor.deposit_soul_ring(
                ring_type="service_milestone",
                description=desc,
                context=f"milestone context {i}",
                impact=f"milestone impact {i}",
                milestone_name=f"milestone_{i}",
                metrics={"q_score": 0.5 + i * 0.05},
            )
            if ring is not None:
                written.append(ring)

        # 最多 5 條即時寫入
        assert len(written) <= 5

    def test_queued_rings_for_nightly(self, ring_depositor):
        """超過每日限制的年輪被排入 Nightly Job 佇列."""
        # 使用完全不同的描述避免觸發重複偵測
        unique_descriptions = [
            "成功協助完成第一份財務報表分析",
            "突破了自然語言處理的對話品質瓶頸",
            "建立了全新的風險評估模型框架",
            "達成客戶滿意度連續三個月上升紀錄",
            "完成跨領域知識整合的創新方法論",
            "開發出高效的程式碼審查自動化流程",
            "實現了多語言翻譯品質的顯著提升",
        ]
        for i, desc in enumerate(unique_descriptions):
            ring_depositor.deposit_soul_ring(
                ring_type="service_milestone",
                description=desc,
                context=f"milestone context {i}",
                impact=f"milestone impact {i}",
                milestone_name=f"milestone_{i}",
                metrics={"q_score": 0.5 + i * 0.05},
            )

        queued = ring_depositor.get_pending_queue()
        assert len(queued) >= 2  # 超過 5 條限制的應被排入佇列

    def test_nightly_batch_deposit(self, ring_depositor):
        """Nightly Job 從佇列篩選最多 3 條年輪寫入."""
        # 使用完全不同的描述避免觸發重複偵測
        unique_descriptions = [
            "發現使用者偏好結構化的回答方式",
            "領悟到同理心在技術溝通中的重要性",
            "掌握了複雜問題的多角度分析技巧",
            "理解了使用者隱含需求的識別方法",
            "建立了更精確的情境理解框架",
            "發展出適應不同溝通風格的能力",
            "突破了長文本理解的認知限制",
        ]
        for i, desc in enumerate(unique_descriptions):
            ring_depositor.deposit_soul_ring(
                ring_type="cognitive_breakthrough",
                description=desc,
                context=f"unique context {i}",
                impact=f"unique impact {i}",
            )

        # 執行 Nightly batch（無額外 candidates 參數）
        deposited = ring_depositor.nightly_batch_deposit()
        assert len(deposited) <= 3  # 每日最多新增 3 條


# ════════════════════════════════════════════
# Section 4: ANIMA_USER 觀察年輪
# ════════════════════════════════════════════

class TestObservationRings:
    """測試使用者觀察年輪."""

    def test_observation_ring_types(self, ring_depositor):
        """觀察年輪有四種類型."""
        valid_types = {"growth_observation", "pattern_shift",
                       "preference_evolution", "milestone_witnessed"}

        for obs_type in valid_types:
            ring = ring_depositor.deposit_observation_ring(
                ring_type=obs_type,
                description=f"觀察到 {obs_type} 的獨特事件",
                context=f"{obs_type} 的測試情境",
                impact=f"{obs_type} 的影響",
            )
            assert ring is not None
            assert ring.type == obs_type

    def test_observation_ring_has_hash_chain(self, ring_depositor):
        """觀察年輪同樣有 SHA-256 hash chain."""
        ring1 = ring_depositor.deposit_observation_ring(
            ring_type="growth_observation",
            description="使用者決策信心提升",
            context="使用者互動觀察",
            impact="更好地理解使用者成長軌跡",
        )
        ring2 = ring_depositor.deposit_observation_ring(
            ring_type="pattern_shift",
            description="使用者開始先思考再提問",
            context="互動模式觀察",
            impact="使用者主動性提升",
        )
        assert ring1.prev_hash == "GENESIS"
        assert ring2.prev_hash == ring1.hash

    def test_observation_ring_privacy(self, ring_depositor):
        """觀察年輪只記錄抽象結論，不包含具體對話內容."""
        ring = ring_depositor.deposit_observation_ring(
            ring_type="growth_observation",
            description="使用者的決策信心指數從 0.5 提升到 0.7",
            context="decision_confidence metric 觀察",
            impact="使用者信心持續提升",
        )
        # description 不應包含具體對話文字
        assert "使用者說" not in ring.description
        assert len(ring.description) < 200  # 應該是簡短的結論


# ════════════════════════════════════════════
# Section 5: 持久化
# ════════════════════════════════════════════

class TestPersistence:
    """測試年輪持久化."""

    def test_soul_rings_saved_to_json(self, ring_depositor, data_dir):
        """Soul rings 儲存在 data/anima/soul_rings.json."""
        ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="持久化測試",
            context="持久化測試情境",
            impact="test",
        )
        rings_path = data_dir / "anima" / "soul_rings.json"
        assert rings_path.exists()
        data = json.loads(rings_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1

    def test_observation_rings_saved_to_json(self, ring_depositor, data_dir):
        """Observation rings 儲存在 data/anima/observation_rings.json."""
        ring_depositor.deposit_observation_ring(
            ring_type="growth_observation",
            description="觀察持久化測試",
            context="觀察持久化測試情境",
            impact="觀察持久化影響",
        )
        obs_path = data_dir / "anima" / "observation_rings.json"
        assert obs_path.exists()
        data = json.loads(obs_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1

    def test_backup_creates_dated_file(self, soul_ring_store, ring_depositor):
        """備份建立日期標記的檔案."""
        ring_depositor.deposit_soul_ring(
            ring_type="cognitive_breakthrough",
            description="備份測試",
            context="備份測試情境",
            impact="test",
        )
        soul_ring_store.create_backup()
        backup_dir = soul_ring_store._backup_dir
        backups = list(backup_dir.glob("soul_rings_*.json"))
        assert len(backups) >= 1

    def test_backup_rotation_removes_old_backups(self, soul_ring_store, data_dir):
        """備份輪替會刪除超過保留天數的舊備份."""
        backup_dir = data_dir / "anima" / "backups"
        # 建立 35 個假備份
        # rotate_backups 的檔名解析使用 rsplit("_", 3)，
        # 需要至少 4 個 underscore-separated 部分，
        # 最後 3 部分為 YYYY, MM, DD（用 underscore 分隔日期組件）
        for i in range(35):
            d = date.today() - timedelta(days=i)
            fname = f"soul_rings_{d.year}_{d.month:02d}_{d.day:02d}.json"
            (backup_dir / fname).write_text("[]")

        removed = soul_ring_store.rotate_backups(retention_days=30)
        remaining = list(backup_dir.glob("soul_rings_*.json"))
        # cutoff = today - 30 days; files strictly before cutoff are removed
        # days 0..30 = 31 files kept, days 31..34 = 4 files removed
        assert removed > 0
        assert len(remaining) < 35


# ════════════════════════════════════════════
# Section 6: 安全護欄
# ════════════════════════════════════════════

class TestSafety:
    """測試安全護欄."""

    def test_morphenix_cannot_modify_soul_rings(self, ring_depositor):
        """Morphenix 不可修改 L4 靈魂年輪."""
        result = ring_depositor.reject_morphenix_modify(caller="morphenix")
        assert result["allowed"] is False
        assert "Kernel 保護" in result["error"] or "不可" in result["error"]

    def test_modification_attempt_logged(self, ring_depositor, data_dir):
        """修改嘗試被記錄到安全日誌."""
        ring_depositor.reject_modify(index=0, caller="test_caller")
        # 檢查安全日誌
        log_path = data_dir / "anima" / "security_audit.jsonl"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "modify_attempt" in content

    def test_delete_attempt_logged(self, ring_depositor, data_dir):
        """刪除嘗試被記錄到安全日誌."""
        ring_depositor.reject_delete(index=0, caller="test_caller")
        log_path = data_dir / "anima" / "security_audit.jsonl"
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "delete_attempt" in content
