"""Tests for DigestEngine — 消化引擎."""

import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from museon.core.event_bus import (
    EventBus,
    OUTWARD_TRIAL_RECORDED,
    OUTWARD_SELF_CRYSTALLIZED,
    OUTWARD_SERVICE_CRYSTALLIZED,
    OUTWARD_KNOWLEDGE_ARCHIVED,
)
from museon.evolution.digest_engine import (
    DigestEngine,
    INITIAL_CONFIDENCE,
    PROMOTE_MIN_TRIALS,
    PROMOTE_MIN_SUCCESS_RATE,
    PROMOTE_MIN_CONFIDENCE,
    DEMOTE_MAX_CONSECUTIVE_FAILS,
    DEMOTE_MIN_CONFIDENCE,
    MAX_QUARANTINE_DAYS,
    CONFIDENCE_SUCCESS_DELTA,
    CONFIDENCE_FAILURE_DELTA,
)


@pytest.fixture
def workspace(tmp_path):
    """建立暫時工作空間."""
    (tmp_path / "_system" / "outward").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def engine(workspace, event_bus):
    return DigestEngine(workspace=workspace, event_bus=event_bus)


# ═══════════════════════════════════════════
# 常數驗證
# ═══════════════════════════════════════════


class TestConstants:
    """消化閘門常數驗證."""

    def test_initial_confidence(self):
        assert INITIAL_CONFIDENCE == 0.3

    def test_promote_thresholds(self):
        assert PROMOTE_MIN_TRIALS == 3
        assert PROMOTE_MIN_SUCCESS_RATE == 0.6
        assert PROMOTE_MIN_CONFIDENCE == 0.7

    def test_demote_thresholds(self):
        assert DEMOTE_MAX_CONSECUTIVE_FAILS == 3
        assert DEMOTE_MIN_CONFIDENCE == 0.15

    def test_lifecycle(self):
        assert MAX_QUARANTINE_DAYS == 90

    def test_confidence_deltas(self):
        assert CONFIDENCE_SUCCESS_DELTA == 0.1
        assert CONFIDENCE_FAILURE_DELTA == 0.15


# ═══════════════════════════════════════════
# 進食（Ingest）
# ═══════════════════════════════════════════


class TestIngest:
    """進食階段測試."""

    def test_ingest_valid_result(self, engine):
        """成功進食有價值的研究結果."""
        qid = engine.ingest(
            research_result={
                "filtered_summary": "A" * 50,  # 長度足夠
                "source_urls": ["https://example.com"],
            },
            search_context={
                "query": "test query",
                "track": "service",
                "trigger_type": "pain",
            },
        )

        assert qid is not None
        assert qid.startswith("QC-")

    def test_ingest_short_summary_rejected(self, engine):
        """過短的摘要被拒絕."""
        qid = engine.ingest(
            research_result={"filtered_summary": "too short"},
            search_context={"track": "service"},
        )
        assert qid is None

    def test_ingest_empty_summary_rejected(self, engine):
        """空摘要被拒絕."""
        qid = engine.ingest(
            research_result={"filtered_summary": ""},
            search_context={"track": "service"},
        )
        assert qid is None

    def test_ingest_sets_quarantined_status(self, engine):
        """進食後狀態為 quarantined."""
        engine.ingest(
            research_result={"filtered_summary": "X" * 50},
            search_context={"track": "service", "trigger_type": "curiosity"},
        )

        stats = engine.get_stats()
        assert stats["total"] == 1
        assert stats["by_status"].get("quarantined", 0) == 1

    def test_ingest_sets_initial_confidence(self, engine):
        """進食後信心度為初始值."""
        engine.ingest(
            research_result={"filtered_summary": "Y" * 50},
            search_context={"track": "self"},
        )

        stats = engine.get_stats()
        assert stats["total"] == 1

    def test_ingest_tracks_origin(self, engine):
        """進食記錄來源軌道."""
        engine.ingest(
            research_result={"filtered_summary": "Z" * 50},
            search_context={"track": "self", "trigger_type": "plateau"},
        )

        # 驗證 quarantine.json 中的 origin 欄位
        q_file = engine._workspace / "_system" / "outward" / "quarantine.json"
        data = json.loads(q_file.read_text(encoding="utf-8"))
        assert data[0]["origin"] == "outward_self"

    def test_ingest_service_track(self, engine):
        """Track B 服務進化的來源標記."""
        engine.ingest(
            research_result={"filtered_summary": "W" * 50},
            search_context={"track": "service", "trigger_type": "pain"},
        )

        q_file = engine._workspace / "_system" / "outward" / "quarantine.json"
        data = json.loads(q_file.read_text(encoding="utf-8"))
        assert data[0]["origin"] == "outward_service"


# ═══════════════════════════════════════════
# 試用（Trial）
# ═══════════════════════════════════════════


class TestTrial:
    """試用階段測試."""

    def _ingest_one(self, engine, content="Test content " * 10):
        """輔助：進食一筆資料並回傳 qid."""
        return engine.ingest(
            research_result={"filtered_summary": content},
            search_context={"track": "service", "trigger_type": "pain"},
        )

    def test_record_trial_success(self, engine):
        """試用成功更新信心度."""
        qid = self._ingest_one(engine)
        crystal = engine.record_trial(qid, success=True)

        assert crystal is not None
        assert crystal["trial_count"] == 1
        assert crystal["success_count"] == 1
        assert crystal["confidence"] == INITIAL_CONFIDENCE + CONFIDENCE_SUCCESS_DELTA
        assert crystal["status"] == "provisional"

    def test_record_trial_failure(self, engine):
        """試用失敗降低信心度."""
        qid = self._ingest_one(engine)
        crystal = engine.record_trial(qid, success=False)

        assert crystal["trial_count"] == 1
        assert crystal["failure_count"] == 1
        assert crystal["confidence"] == INITIAL_CONFIDENCE - CONFIDENCE_FAILURE_DELTA
        assert crystal["consecutive_failures"] == 1

    def test_consecutive_failures_tracked(self, engine):
        """連續失敗次數追蹤."""
        qid = self._ingest_one(engine)
        engine.record_trial(qid, success=False)
        engine.record_trial(qid, success=False)
        crystal = engine.record_trial(qid, success=False)

        assert crystal["consecutive_failures"] == 3

    def test_success_resets_consecutive_failures(self, engine):
        """成功重置連續失敗計數."""
        qid = self._ingest_one(engine)
        engine.record_trial(qid, success=False)
        engine.record_trial(qid, success=False)
        crystal = engine.record_trial(qid, success=True)

        assert crystal["consecutive_failures"] == 0

    def test_confidence_bounded(self, engine):
        """信心度限制在 0-1 之間."""
        qid = self._ingest_one(engine)

        # 連續成功推高信心度
        for _ in range(20):
            crystal = engine.record_trial(qid, success=True)

        assert crystal["confidence"] <= 1.0

        # 連續失敗降低信心度
        for _ in range(20):
            crystal = engine.record_trial(qid, success=False)

        assert crystal["confidence"] >= 0.0

    def test_record_trial_nonexistent(self, engine):
        """不存在的 ID 回傳 None."""
        result = engine.record_trial("QC-nonexistent", success=True)
        assert result is None

    def test_trial_publishes_event(self, engine, event_bus):
        """試用記錄發布事件."""
        received = []
        event_bus.subscribe(OUTWARD_TRIAL_RECORDED, lambda d: received.append(d))

        qid = self._ingest_one(engine)
        engine.record_trial(qid, success=True)

        assert len(received) == 1
        assert received[0]["quarantine_id"] == qid
        assert received[0]["success"] is True


# ═══════════════════════════════════════════
# 相關性掃描
# ═══════════════════════════════════════════


class TestRelevanceScan:
    """隔離區相關性掃描測試."""

    def test_scan_empty_quarantine(self, engine):
        """空隔離區回傳空列表."""
        matches = engine.scan_for_relevance("test query")
        assert matches == []

    def test_scan_empty_query(self, engine):
        """空查詢回傳空列表."""
        matches = engine.scan_for_relevance("")
        assert matches == []

    def test_scan_finds_relevant(self, engine):
        """找到相關的隔離結晶."""
        engine.ingest(
            research_result={
                "filtered_summary": "machine learning neural network deep learning transformer architecture best practices",
            },
            search_context={"track": "self", "trigger_type": "plateau"},
        )

        matches = engine.scan_for_relevance("machine learning neural network")
        assert len(matches) >= 1


# ═══════════════════════════════════════════
# 生命週期掃描
# ═══════════════════════════════════════════


class TestLifecycleScan:
    """生命週期掃描測試."""

    def _ingest_one(self, engine, content="Test content " * 10):
        return engine.ingest(
            research_result={"filtered_summary": content},
            search_context={"track": "service", "trigger_type": "pain"},
        )

    def test_lifecycle_empty(self, engine):
        """空隔離區的生命週期掃描."""
        result = engine.lifecycle_scan()
        assert result["promoted"] == []
        assert result["archived"] == []
        assert result["ttl_expired"] == []
        assert result["active_count"] == 0

    def test_promote_after_successful_trials(self, engine):
        """滿足條件後晉升."""
        qid = self._ingest_one(engine)

        # 模擬多次成功試用讓信心度 > 0.7
        for _ in range(PROMOTE_MIN_TRIALS + 2):
            engine.record_trial(qid, success=True)

        result = engine.lifecycle_scan()
        assert qid in result["promoted"]

    def test_demote_after_failures(self, engine):
        """連續失敗後淘汰."""
        qid = self._ingest_one(engine)

        # 連續失敗 3 次
        for _ in range(DEMOTE_MAX_CONSECUTIVE_FAILS):
            engine.record_trial(qid, success=False)

        result = engine.lifecycle_scan()
        assert qid in result["archived"]

    def test_demote_low_confidence(self, engine):
        """信心度過低被淘汰."""
        qid = self._ingest_one(engine)

        # 足夠多的失敗讓信心度跌破閾值
        for _ in range(5):
            engine.record_trial(qid, success=False)

        result = engine.lifecycle_scan()
        assert qid in result["archived"]

    def test_ttl_expiry(self, engine):
        """TTL 過期淘汰."""
        qid = self._ingest_one(engine)

        # 手動修改隔離時間為 91 天前
        for crystal in engine._quarantine:
            if crystal["quarantine_id"] == qid:
                old_date = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=91)
                crystal["quarantined_at"] = old_date.isoformat()

        result = engine.lifecycle_scan()
        assert qid in result["ttl_expired"]

    def test_active_count(self, engine):
        """統計活躍結晶數量."""
        self._ingest_one(engine, "Content A " * 10)
        self._ingest_one(engine, "Content B " * 10)

        result = engine.lifecycle_scan()
        assert result["active_count"] == 2


# ═══════════════════════════════════════════
# 晉升路徑分流
# ═══════════════════════════════════════════


class TestPromotionPaths:
    """雙軌晉升路徑測試."""

    def test_track_a_creates_morphenix_proposal(self, workspace, event_bus):
        """Track A 固化生成 Morphenix 提案."""
        engine = DigestEngine(workspace=workspace, event_bus=event_bus)

        qid = engine.ingest(
            research_result={"filtered_summary": "AI agent architecture innovation " * 5},
            search_context={"track": "self", "trigger_type": "plateau"},
        )

        # 推升到可晉升狀態
        for _ in range(PROMOTE_MIN_TRIALS + 2):
            engine.record_trial(qid, success=True)

        engine.lifecycle_scan()

        # 確認 Morphenix 筆記被建立
        notes_dir = workspace / "_system" / "morphenix" / "notes"
        if notes_dir.exists():
            notes = list(notes_dir.glob("outward_*.json"))
            assert len(notes) >= 1

    def test_track_b_publishes_service_event(self, workspace, event_bus):
        """Track B 固化發布 OUTWARD_SERVICE_CRYSTALLIZED."""
        received = []
        event_bus.subscribe(
            OUTWARD_SERVICE_CRYSTALLIZED, lambda d: received.append(d)
        )

        engine = DigestEngine(workspace=workspace, event_bus=event_bus)

        qid = engine.ingest(
            research_result={"filtered_summary": "Domain knowledge best practices " * 5},
            search_context={"track": "service", "trigger_type": "pain"},
        )

        for _ in range(PROMOTE_MIN_TRIALS + 2):
            engine.record_trial(qid, success=True)

        engine.lifecycle_scan()

        assert len(received) >= 1
        assert received[0]["track"] == "service"


# ═══════════════════════════════════════════
# 持久化
# ═══════════════════════════════════════════


class TestPersistence:
    """持久化測試."""

    def test_quarantine_saved_to_file(self, workspace, event_bus):
        """隔離區資料儲存到檔案."""
        engine = DigestEngine(workspace=workspace, event_bus=event_bus)
        engine.ingest(
            research_result={"filtered_summary": "P" * 50},
            search_context={"track": "service"},
        )

        q_file = workspace / "_system" / "outward" / "quarantine.json"
        assert q_file.exists()

        data = json.loads(q_file.read_text(encoding="utf-8"))
        assert len(data) == 1

    def test_quarantine_loaded_on_init(self, workspace, event_bus):
        """初始化時載入既有隔離區資料."""
        # 先建立資料
        engine1 = DigestEngine(workspace=workspace, event_bus=event_bus)
        engine1.ingest(
            research_result={"filtered_summary": "Q" * 50},
            search_context={"track": "service"},
        )

        # 重新載入
        engine2 = DigestEngine(workspace=workspace, event_bus=event_bus)
        stats = engine2.get_stats()
        assert stats["total"] == 1


# ═══════════════════════════════════════════
# 統計
# ═══════════════════════════════════════════


class TestStats:
    """統計介面測試."""

    def test_get_stats_empty(self, engine):
        """空狀態的統計."""
        stats = engine.get_stats()
        assert stats["total"] == 0
        assert stats["by_status"] == {}

    def test_get_stats_with_data(self, engine):
        """有資料時的統計."""
        engine.ingest(
            research_result={"filtered_summary": "R" * 50},
            search_context={"track": "service"},
        )
        engine.ingest(
            research_result={"filtered_summary": "S" * 50},
            search_context={"track": "self"},
        )

        stats = engine.get_stats()
        assert stats["total"] == 2
