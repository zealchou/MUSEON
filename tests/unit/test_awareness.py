"""tests/unit/test_awareness.py — AwarenessSignal + SessionAdjustment + triage_step 單元測試."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from museon.core.awareness import (
    Actionability,
    AwarenessSignal,
    Severity,
    SignalType,
)
from museon.core.session_adjustment import (
    COMPRESS_OUTPUT,
    DEGRADE_SKILL,
    INCREASE_DEPTH,
    SIMPLIFY_LANGUAGE,
    SWITCH_APPROACH,
    SessionAdjustment,
    SessionAdjustmentManager,
    get_manager,
)
from museon.nightly.triage_step import (
    check_accumulation_upgrades,
    run_triage,
    write_signal,
)


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 1：AwarenessSignal 建立、to_dict、from_dict 往返
# ═══════════════════════════════════════════════════════════════════════════════


class TestAwarenessSignal:
    """AwarenessSignal 基本功能測試."""

    def _make_signal(self, **kwargs) -> AwarenessSignal:
        """建立測試用 AwarenessSignal."""
        defaults = dict(
            source="test_source",
            title="測試訊號標題",
            severity=Severity.MEDIUM,
            signal_type=SignalType.QUALITY_DROP,
            actionability=Actionability.PROMPT,
        )
        defaults.update(kwargs)
        return AwarenessSignal(**defaults)

    def test_create_minimal(self):
        """測試最小必填欄位建立."""
        sig = self._make_signal()
        assert sig.source == "test_source"
        assert sig.title == "測試訊號標題"
        assert sig.severity == Severity.MEDIUM
        assert sig.signal_type == SignalType.QUALITY_DROP
        assert sig.actionability == Actionability.PROMPT
        # 自動填充欄位
        assert len(sig.signal_id) == 8
        assert sig.created_at is not None
        assert sig.status == "pending"

    def test_create_full(self):
        """測試完整欄位建立."""
        sig = self._make_signal(
            skill_name="darwin",
            severity=Severity.CRITICAL,
            signal_type=SignalType.SKILL_DEGRADED,
            actionability=Actionability.HUMAN,
            suggested_action="立即停用 darwin Skill",
            metric_name="health_score",
            metric_value=0.32,
            metric_baseline=0.70,
            context={"reason": "連續 3 次失敗"},
        )
        assert sig.skill_name == "darwin"
        assert sig.metric_value == 0.32
        assert sig.context["reason"] == "連續 3 次失敗"

    def test_to_dict_contains_all_fields(self):
        """to_dict 應包含所有欄位."""
        sig = self._make_signal(
            skill_name="ares",
            metric_name="accuracy",
            metric_value=0.55,
            metric_baseline=0.80,
        )
        d = sig.to_dict()
        required_keys = [
            "signal_id", "created_at", "source", "skill_name",
            "severity", "signal_type", "title", "actionability",
            "suggested_action", "metric_name", "metric_value",
            "metric_baseline", "context", "status", "triage_action",
        ]
        for key in required_keys:
            assert key in d, f"to_dict 缺少欄位：{key}"

    def test_to_dict_enum_values_are_strings(self):
        """to_dict 的 enum 值應序列化為字串，而非 enum 物件."""
        sig = self._make_signal(
            severity=Severity.HIGH,
            signal_type=SignalType.BEHAVIOR_DRIFT,
            actionability=Actionability.AUTO,
        )
        d = sig.to_dict()
        assert d["severity"] == "HIGH"
        assert d["signal_type"] == "behavior_drift"
        assert d["actionability"] == "AUTO"
        # 確認可以 JSON 序列化
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

    def test_from_dict_roundtrip(self):
        """from_dict(to_dict()) 應完整往返，所有欄位一致."""
        original = self._make_signal(
            skill_name="shadow-muse",
            severity=Severity.HIGH,
            signal_type=SignalType.LEARNING_GAP,
            actionability=Actionability.AUTO,
            suggested_action="重新訓練 shadow-muse 評估邏輯",
            metric_name="pass_rate",
            metric_value=0.45,
            metric_baseline=0.75,
            context={"failed_cases": 12, "total_cases": 20},
        )
        reconstructed = AwarenessSignal.from_dict(original.to_dict())

        assert reconstructed.signal_id == original.signal_id
        assert reconstructed.source == original.source
        assert reconstructed.title == original.title
        assert reconstructed.severity == original.severity
        assert reconstructed.signal_type == original.signal_type
        assert reconstructed.actionability == original.actionability
        assert reconstructed.skill_name == original.skill_name
        assert reconstructed.metric_value == original.metric_value
        assert reconstructed.metric_baseline == original.metric_baseline
        assert reconstructed.context == original.context
        assert reconstructed.status == original.status

    def test_from_dict_with_string_enums(self):
        """from_dict 應能正確解析字串形式的 enum 值."""
        data = {
            "signal_id": "abc12345",
            "created_at": "2026-03-31T00:00:00+00:00",
            "source": "unit_test",
            "skill_name": None,
            "severity": "CRITICAL",
            "signal_type": "system_fault",
            "title": "系統錯誤",
            "actionability": "HUMAN",
            "suggested_action": None,
            "metric_name": None,
            "metric_value": None,
            "metric_baseline": None,
            "context": {},
            "status": "pending",
            "triage_action": None,
        }
        sig = AwarenessSignal.from_dict(data)
        assert sig.severity == Severity.CRITICAL
        assert sig.signal_type == SignalType.SYSTEM_FAULT
        assert sig.actionability == Actionability.HUMAN

    def test_str_does_not_leak_internals(self):
        """__str__ 不應洩漏完整 dict 或敏感內部結構."""
        sig = self._make_signal(
            severity=Severity.INFO,
            context={"internal_key": "secret_value"},
        )
        s = str(sig)
        assert "secret_value" not in s
        # 但應包含重要識別資訊
        assert sig.signal_id in s
        assert sig.source in s


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 2：SessionAdjustmentManager add、get_active、format_for_prompt
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionAdjustmentManager:
    """SessionAdjustmentManager 功能測試."""

    def _make_adj(
        self,
        trigger: str = "test_trigger",
        adjustment: str = COMPRESS_OUTPUT,
        expires_after_turns: int = 5,
        created_at_turn: int = 0,
        params: dict = None,
    ) -> SessionAdjustment:
        return SessionAdjustment(
            trigger=trigger,
            adjustment=adjustment,
            params=params or {},
            expires_after_turns=expires_after_turns,
            created_at_turn=created_at_turn,
        )

    def test_add_and_get_active(self):
        """add 後能用 get_active 取回."""
        mgr = SessionAdjustmentManager()
        adj = self._make_adj(created_at_turn=0, expires_after_turns=5)
        mgr.add("sess_001", adj)

        active = mgr.get_active("sess_001", current_turn=3)
        assert len(active) == 1
        assert active[0].adjustment == COMPRESS_OUTPUT

    def test_get_active_empty_session(self):
        """不存在的 session 應回傳空清單."""
        mgr = SessionAdjustmentManager()
        assert mgr.get_active("nonexistent_session", current_turn=0) == []

    def test_expiry_filter(self):
        """過期的調整不應出現在 get_active 結果中."""
        mgr = SessionAdjustmentManager()
        # 在第 0 輪建立，5 輪後過期（即第 5 輪開始不再有效）
        adj = self._make_adj(created_at_turn=0, expires_after_turns=5)
        mgr.add("sess_002", adj)

        # 第 4 輪：應有效（0 + 5 = 5 > 4）
        assert len(mgr.get_active("sess_002", current_turn=4)) == 1

        # 第 5 輪：應過期（0 + 5 = 5，current_turn=5 >= 5）
        assert len(mgr.get_active("sess_002", current_turn=5)) == 0

        # 第 10 輪：應過期
        assert len(mgr.get_active("sess_002", current_turn=10)) == 0

    def test_never_expires_when_zero(self):
        """expires_after_turns=0 表示永不過期."""
        mgr = SessionAdjustmentManager()
        adj = self._make_adj(created_at_turn=0, expires_after_turns=0)
        mgr.add("sess_003", adj)

        # 即使 1000 輪後也應有效
        assert len(mgr.get_active("sess_003", current_turn=1000)) == 1

    def test_same_trigger_replaces_old(self):
        """相同 trigger 的新調整應取代舊有調整."""
        mgr = SessionAdjustmentManager()
        adj1 = self._make_adj(trigger="confusion", adjustment=SIMPLIFY_LANGUAGE)
        adj2 = self._make_adj(trigger="confusion", adjustment=COMPRESS_OUTPUT)

        mgr.add("sess_004", adj1)
        mgr.add("sess_004", adj2)

        active = mgr.get_active("sess_004", current_turn=0)
        assert len(active) == 1
        # 應是新的那個
        assert active[0].adjustment == COMPRESS_OUTPUT

    def test_multiple_adjustments(self):
        """不同 trigger 的調整可共存."""
        mgr = SessionAdjustmentManager()
        mgr.add("sess_005", self._make_adj(trigger="t1", adjustment=COMPRESS_OUTPUT))
        mgr.add("sess_005", self._make_adj(trigger="t2", adjustment=SIMPLIFY_LANGUAGE))
        mgr.add("sess_005", self._make_adj(trigger="t3", adjustment=INCREASE_DEPTH))

        active = mgr.get_active("sess_005", current_turn=0)
        assert len(active) == 3

    def test_clear(self):
        """clear 後 get_active 應回傳空清單."""
        mgr = SessionAdjustmentManager()
        mgr.add("sess_006", self._make_adj())
        assert len(mgr.get_active("sess_006", current_turn=0)) == 1

        mgr.clear("sess_006")
        assert mgr.get_active("sess_006", current_turn=0) == []

    def test_format_for_prompt_empty(self):
        """無有效調整時 format_for_prompt 應回傳空字串."""
        mgr = SessionAdjustmentManager()
        result = mgr.format_for_prompt("empty_session", current_turn=0)
        assert result == ""

    def test_format_for_prompt_contains_adjustments(self):
        """format_for_prompt 應包含所有有效調整."""
        mgr = SessionAdjustmentManager()
        mgr.add(
            "sess_007",
            self._make_adj(
                trigger="long_output",
                adjustment=COMPRESS_OUTPUT,
                params={"max_sentences": 3},
            ),
        )
        mgr.add(
            "sess_007",
            self._make_adj(trigger="jargon", adjustment=SIMPLIFY_LANGUAGE),
        )

        result = mgr.format_for_prompt("sess_007", current_turn=0)

        assert "即時行為調整" in result
        assert COMPRESS_OUTPUT in result
        assert SIMPLIFY_LANGUAGE in result
        assert "long_output" in result
        assert "jargon" in result

    def test_format_for_prompt_excludes_expired(self):
        """format_for_prompt 不應包含已過期的調整."""
        mgr = SessionAdjustmentManager()
        # 在第 0 輪建立，2 輪後過期
        mgr.add(
            "sess_008",
            self._make_adj(
                trigger="expired_one",
                adjustment=SWITCH_APPROACH,
                expires_after_turns=2,
                created_at_turn=0,
            ),
        )

        # 第 1 輪：應包含
        result_turn1 = mgr.format_for_prompt("sess_008", current_turn=1)
        assert SWITCH_APPROACH in result_turn1

        # 第 2 輪：應不包含（已過期）
        result_turn2 = mgr.format_for_prompt("sess_008", current_turn=2)
        assert result_turn2 == ""

    def test_get_manager_singleton(self):
        """get_manager() 每次應回傳同一個實例."""
        m1 = get_manager()
        m2 = get_manager()
        assert m1 is m2

    def test_load_from_l4_reads_json(self, tmp_path: Path):
        """load_from_l4 應正確讀取 L4 寫入的 JSON 檔案並載入調整."""
        workspace = tmp_path / "MUSEON"
        adj_dir = workspace / "data" / "_system" / "session_adjustments"
        adj_dir.mkdir(parents=True)

        session_id = "test_session_l4"
        adj_file = adj_dir / f"{session_id}.json"
        payload = {
            "session_id": session_id,
            "adjustments": [
                {
                    "trigger": "response_too_long",
                    "adjustment": "compress_output",
                    "params": {"max_length": 800},
                    "expires_after_turns": 3,
                    "created_at_turn": 2,
                },
                {
                    "trigger": "uncertain_language",
                    "adjustment": "increase_depth",
                    "params": {},
                    "expires_after_turns": 5,
                    "created_at_turn": 2,
                },
            ],
            "updated_at": "2026-03-31T00:00:00Z",
        }
        adj_file.write_text(json.dumps(payload), encoding="utf-8")

        mgr = SessionAdjustmentManager()
        count = mgr.load_from_l4(workspace, session_id)

        assert count == 2
        active = mgr.get_active(session_id, current_turn=3)
        assert len(active) == 2
        triggers = {a.trigger for a in active}
        assert "response_too_long" in triggers
        assert "uncertain_language" in triggers

    def test_load_from_l4_file_not_exist_returns_zero(self, tmp_path: Path):
        """load_from_l4 檔案不存在時應返回 0，不拋出例外."""
        workspace = tmp_path / "MUSEON"
        workspace.mkdir()

        mgr = SessionAdjustmentManager()
        count = mgr.load_from_l4(workspace, "nonexistent_session")

        assert count == 0
        assert mgr.get_active("nonexistent_session", current_turn=0) == []


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 3：write_signal 寫入和讀取
# ═══════════════════════════════════════════════════════════════════════════════


class TestWriteSignal:
    """write_signal 功能測試."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        """建立模擬 workspace 目錄."""
        workspace = tmp_path / "MUSEON"
        workspace.mkdir()
        return workspace

    def test_write_signal_creates_file(self, tmp_path: Path):
        """write_signal 應建立 triage_queue.jsonl."""
        ws = self._make_workspace(tmp_path)
        sig = AwarenessSignal(
            source="test",
            title="測試寫入",
            severity=Severity.INFO,
            signal_type=SignalType.QUALITY_DROP,
            actionability=Actionability.AUTO,
        )
        write_signal(ws, sig)

        queue_path = ws / "data/_system/triage_queue.jsonl"
        assert queue_path.exists()

    def test_write_signal_valid_jsonl(self, tmp_path: Path):
        """寫入的每行應是合法 JSON."""
        ws = self._make_workspace(tmp_path)
        sig = AwarenessSignal(
            source="test",
            title="JSON 格式測試",
            severity=Severity.LOW,
            signal_type=SignalType.HEALTH_ANOMALY,
            actionability=Actionability.PROMPT,
        )
        write_signal(ws, sig)

        queue_path = ws / "data/_system/triage_queue.jsonl"
        lines = queue_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["source"] == "test"
        assert parsed["title"] == "JSON 格式測試"

    def test_write_signal_append_mode(self, tmp_path: Path):
        """多次 write_signal 應 append，而非覆寫."""
        ws = self._make_workspace(tmp_path)
        for i in range(3):
            sig = AwarenessSignal(
                source=f"source_{i}",
                title=f"訊號 {i}",
                severity=Severity.INFO,
                signal_type=SignalType.QUALITY_DROP,
                actionability=Actionability.AUTO,
            )
            write_signal(ws, sig)

        queue_path = ws / "data/_system/triage_queue.jsonl"
        lines = [
            l for l in queue_path.read_text(encoding="utf-8").strip().split("\n")
            if l.strip()
        ]
        assert len(lines) == 3

    def test_write_signal_roundtrip(self, tmp_path: Path):
        """write_signal 後讀取，from_dict 應還原完整資料."""
        ws = self._make_workspace(tmp_path)
        original = AwarenessSignal(
            source="skill_health_tracker",
            title="darwin 健康度過低",
            severity=Severity.HIGH,
            signal_type=SignalType.SKILL_DEGRADED,
            actionability=Actionability.HUMAN,
            skill_name="darwin",
            metric_name="health_score",
            metric_value=0.38,
            metric_baseline=0.60,
            context={"consecutive_failures": 5},
        )
        write_signal(ws, original)

        queue_path = ws / "data/_system/triage_queue.jsonl"
        line = queue_path.read_text(encoding="utf-8").strip()
        restored = AwarenessSignal.from_dict(json.loads(line))

        assert restored.signal_id == original.signal_id
        assert restored.source == original.source
        assert restored.skill_name == original.skill_name
        assert restored.metric_value == original.metric_value
        assert restored.context == original.context


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 4：triage_step 分診邏輯（mock event_bus）
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunTriage:
    """run_triage 分診邏輯測試."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "MUSEON"
        ws.mkdir()
        return ws

    def _write_signals(self, ws: Path, signals: list[AwarenessSignal]) -> None:
        """批量寫入 triage_queue.jsonl."""
        queue_path = ws / "data/_system/triage_queue.jsonl"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        with open(queue_path, "w", encoding="utf-8") as f:
            for sig in signals:
                f.write(json.dumps(sig.to_dict(), ensure_ascii=False) + "\n")

    def _make_signal(
        self,
        severity: Severity,
        actionability: Actionability = Actionability.PROMPT,
        signal_type: SignalType = SignalType.QUALITY_DROP,
    ) -> AwarenessSignal:
        return AwarenessSignal(
            source="test_source",
            title=f"{severity.value} 測試訊號",
            severity=severity,
            signal_type=signal_type,
            actionability=actionability,
        )

    @pytest.mark.asyncio
    async def test_empty_queue_returns_zero_stats(self, tmp_path: Path):
        """空隊列應回傳全零統計."""
        ws = self._make_workspace(tmp_path)
        stats = await run_triage(ws, event_bus=None)
        assert stats["total"] == 0
        assert all(v == 0 for v in stats.values())

    @pytest.mark.asyncio
    async def test_missing_queue_file_returns_zero(self, tmp_path: Path):
        """triage_queue.jsonl 不存在應回傳全零統計."""
        ws = self._make_workspace(tmp_path)
        stats = await run_triage(ws, event_bus=None)
        assert stats["total"] == 0

    @pytest.mark.asyncio
    async def test_critical_human_triggers_telegram(self, tmp_path: Path):
        """CRITICAL + HUMAN 應觸發 event_bus.publish(PROACTIVE_MESSAGE, ...)."""
        ws = self._make_workspace(tmp_path)
        sig = self._make_signal(Severity.CRITICAL, Actionability.HUMAN)
        self._write_signals(ws, [sig])

        mock_bus = MagicMock()
        mock_bus.publish = MagicMock()

        stats = await run_triage(ws, event_bus=mock_bus)

        assert stats["critical"] == 1
        assert stats["total"] == 1
        # 確認推播被呼叫
        mock_bus.publish.assert_called_once()
        call_args = mock_bus.publish.call_args
        assert call_args[0][0] == "PROACTIVE_MESSAGE"

    @pytest.mark.asyncio
    async def test_critical_auto_triggers_incident(self, tmp_path: Path):
        """CRITICAL + AUTO 應觸發 event_bus.publish(INCIDENT_DETECTED, ...)."""
        ws = self._make_workspace(tmp_path)
        sig = self._make_signal(Severity.CRITICAL, Actionability.AUTO)
        self._write_signals(ws, [sig])

        mock_bus = MagicMock()
        mock_bus.publish = MagicMock()

        stats = await run_triage(ws, event_bus=mock_bus)

        assert stats["critical"] == 1
        mock_bus.publish.assert_called_once()
        call_args = mock_bus.publish.call_args
        assert call_args[0][0] == "INCIDENT_DETECTED"

    @pytest.mark.asyncio
    async def test_high_written_to_priority_queue(self, tmp_path: Path):
        """HIGH 訊號應寫入 nightly_priority_queue.json."""
        ws = self._make_workspace(tmp_path)
        signals = [
            self._make_signal(Severity.HIGH),
            self._make_signal(Severity.HIGH),
        ]
        self._write_signals(ws, signals)

        stats = await run_triage(ws, event_bus=None)

        assert stats["high"] == 2
        priority_path = ws / "data/_system/nightly_priority_queue.json"
        assert priority_path.exists()
        entries = json.loads(priority_path.read_text(encoding="utf-8"))
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_medium_low_written_to_awareness_log(self, tmp_path: Path):
        """MEDIUM / LOW 訊號應寫入 awareness_log.jsonl."""
        ws = self._make_workspace(tmp_path)
        signals = [
            self._make_signal(Severity.MEDIUM),
            self._make_signal(Severity.LOW),
        ]
        self._write_signals(ws, signals)

        stats = await run_triage(ws, event_bus=None)

        assert stats["medium"] == 1
        assert stats["low"] == 1
        log_path = ws / "data/_system/awareness_log.jsonl"
        assert log_path.exists()
        lines = [
            l for l in log_path.read_text(encoding="utf-8").strip().split("\n")
            if l.strip()
        ]
        assert len(lines) == 2

    @pytest.mark.asyncio
    async def test_info_updates_counter(self, tmp_path: Path):
        """INFO 訊號應更新計數器，不寫 awareness_log."""
        ws = self._make_workspace(tmp_path)
        self._write_signals(ws, [self._make_signal(Severity.INFO)])

        stats = await run_triage(ws, event_bus=None)

        assert stats["info"] == 1
        counter_path = ws / "data/_system/awareness_info_counter.json"
        assert counter_path.exists()
        counter = json.loads(counter_path.read_text(encoding="utf-8"))
        assert counter["total"] == 1

    @pytest.mark.asyncio
    async def test_queue_cleared_after_triage(self, tmp_path: Path):
        """分診完成後 triage_queue.jsonl 應被清空."""
        ws = self._make_workspace(tmp_path)
        self._write_signals(ws, [self._make_signal(Severity.LOW)])

        await run_triage(ws, event_bus=None)

        queue_path = ws / "data/_system/triage_queue.jsonl"
        content = queue_path.read_text(encoding="utf-8").strip()
        assert content == ""

    @pytest.mark.asyncio
    async def test_mixed_severities_stats(self, tmp_path: Path):
        """多種 severity 的訊號應統計正確."""
        ws = self._make_workspace(tmp_path)
        signals = [
            self._make_signal(Severity.CRITICAL, Actionability.PROMPT),
            self._make_signal(Severity.HIGH),
            self._make_signal(Severity.HIGH),
            self._make_signal(Severity.MEDIUM),
            self._make_signal(Severity.LOW),
            self._make_signal(Severity.LOW),
            self._make_signal(Severity.INFO),
        ]
        self._write_signals(ws, signals)

        stats = await run_triage(ws, event_bus=None)

        assert stats["total"] == 7
        assert stats["critical"] == 1
        assert stats["high"] == 2
        assert stats["medium"] == 1
        assert stats["low"] == 2
        assert stats["info"] == 1

    @pytest.mark.asyncio
    async def test_no_event_bus_critical_falls_back_to_log(self, tmp_path: Path):
        """event_bus 為 None 時，CRITICAL 訊號應 fallback 寫入 awareness_log."""
        ws = self._make_workspace(tmp_path)
        self._write_signals(ws, [self._make_signal(Severity.CRITICAL, Actionability.HUMAN)])

        stats = await run_triage(ws, event_bus=None)

        assert stats["critical"] == 1
        log_path = ws / "data/_system/awareness_log.jsonl"
        assert log_path.exists()
        lines = [l for l in log_path.read_text(encoding="utf-8").strip().split("\n") if l.strip()]
        assert len(lines) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 測試：BrainPromptBuilderMixin code 層自動觸發
# ═══════════════════════════════════════════════════════════════════════════════


class TestAutoAdjustFromHistory:
    """BrainPromptBuilderMixin._auto_adjust_from_history code 層底線觸發測試."""

    def _make_mixin(self):
        """建立最小化 Mixin 實例（不需要完整 Brain）."""
        from museon.agent.brain_prompt_builder import BrainPromptBuilderMixin

        instance = BrainPromptBuilderMixin.__new__(BrainPromptBuilderMixin)
        return instance

    def test_no_history_does_not_crash(self):
        """沒有歷史狀態時，_auto_adjust_from_history 不應崩潰."""
        mixin = self._make_mixin()
        # 完全沒有任何屬性，應該靜默跳過
        mixin._auto_adjust_from_history("test_session")

    def test_record_response_metrics_stores_values(self):
        """record_response_metrics 應正確記錄 response/query 長度."""
        mixin = self._make_mixin()
        mixin.record_response_metrics(response_length=2000, query_length=80)
        assert mixin._last_response_length == 2000
        assert mixin._last_query_length == 80

    def test_compress_output_triggered_on_long_response(self):
        """回覆過長（>1500 chars，query <150 chars，比例 >10x）應觸發 COMPRESS_OUTPUT."""
        from museon.core.session_adjustment import COMPRESS_OUTPUT, get_manager

        # 重置 manager 狀態
        manager = get_manager()

        mixin = self._make_mixin()
        mixin._last_response_length = 2000
        mixin._last_query_length = 50  # 2000/50 = 40x > 10x
        mixin._current_query = "測試問題"

        mixin._auto_adjust_from_history("session_compress_test")

        adjs = manager.get_active("session_compress_test", current_turn=0)
        triggers = [a.trigger for a in adjs]
        assert "response_too_long" in triggers
        adj = next(a for a in adjs if a.trigger == "response_too_long")
        assert adj.adjustment == COMPRESS_OUTPUT
        assert adj.params["max_length"] == 800

    def test_switch_approach_triggered_on_repeated_query(self):
        """相似度 >0.7 的重複問題應觸發 SWITCH_APPROACH."""
        from museon.core.session_adjustment import SWITCH_APPROACH, get_manager

        manager = get_manager()

        mixin = self._make_mixin()
        mixin._last_user_query = "請幫我分析一下這個問題的根本原因是什麼"
        mixin._current_query = "請幫我分析這個問題的根本原因到底是什麼"

        mixin._auto_adjust_from_history("session_repeat_test")

        adjs = manager.get_active("session_repeat_test", current_turn=0)
        triggers = [a.trigger for a in adjs]
        assert "repeated_query" in triggers
        adj = next(a for a in adjs if a.trigger == "repeated_query")
        assert adj.adjustment == SWITCH_APPROACH

    def test_no_trigger_when_queries_different(self):
        """問題差異大時，不應觸發 SWITCH_APPROACH."""
        from museon.core.session_adjustment import get_manager

        manager = get_manager()

        mixin = self._make_mixin()
        mixin._last_user_query = "今天天氣如何？台北有沒有下雨？"
        mixin._current_query = "幫我寫一段 Python 程式碼排序列表"

        mixin._auto_adjust_from_history("session_different_test")

        adjs = manager.get_active("session_different_test", current_turn=0)
        triggers = [a.trigger for a in adjs]
        assert "repeated_query" not in triggers


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 B2：record_outcome 寫入 awareness_log 並計數
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecordOutcome:
    """補線 B：SessionAdjustmentManager.record_outcome 功能測試."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "MUSEON"
        ws.mkdir()
        return ws

    def _make_adj(
        self,
        trigger: str = "q_score_low",
        adjustment: str = COMPRESS_OUTPUT,
    ) -> SessionAdjustment:
        return SessionAdjustment(trigger=trigger, adjustment=adjustment)

    def test_record_outcome_writes_to_log(self, tmp_path: Path):
        """record_outcome 應寫入 awareness_log.jsonl."""
        ws = self._make_workspace(tmp_path)
        mgr = SessionAdjustmentManager()
        adj = self._make_adj()

        mgr.record_outcome("sess_b01", adj, worked=True, context="測試情境", workspace=ws)

        log_path = ws / "data/_system/awareness_log.jsonl"
        assert log_path.exists()
        line = log_path.read_text(encoding="utf-8").strip()
        entry = json.loads(line)
        assert entry["trigger"] == "q_score_low"
        assert entry["adjustment"] == COMPRESS_OUTPUT
        assert entry["worked"] is True
        assert entry["context"] == "測試情境"
        assert entry["session_id"] == "sess_b01"

    def test_record_outcome_counts_successes(self, tmp_path: Path):
        """record_outcome worked=True 應累積計數."""
        ws = self._make_workspace(tmp_path)
        mgr = SessionAdjustmentManager()
        adj = self._make_adj(trigger="test_trigger", adjustment=COMPRESS_OUTPUT)

        mgr.record_outcome("sess_b02", adj, worked=True, workspace=ws)
        mgr.record_outcome("sess_b02", adj, worked=True, workspace=ws)

        key = "test_trigger:compress_output"
        assert mgr._outcome_counts.get(key, 0) == 2

    def test_record_outcome_failure_does_not_count(self, tmp_path: Path):
        """record_outcome worked=False 不應累積成功計數."""
        ws = self._make_workspace(tmp_path)
        mgr = SessionAdjustmentManager()
        adj = self._make_adj(trigger="fail_trigger", adjustment=COMPRESS_OUTPUT)

        mgr.record_outcome("sess_b03", adj, worked=False, workspace=ws)
        mgr.record_outcome("sess_b03", adj, worked=False, workspace=ws)

        key = "fail_trigger:compress_output"
        assert mgr._outcome_counts.get(key, 0) == 0

    def test_record_outcome_promotes_lesson_after_3_successes(self, tmp_path: Path):
        """累積 3 次 worked=True → 應觸發 _promote_to_lesson."""
        ws = self._make_workspace(tmp_path)
        mgr = SessionAdjustmentManager()
        adj = self._make_adj(trigger="score_low", adjustment=COMPRESS_OUTPUT)

        for _ in range(3):
            mgr.record_outcome("sess_b04", adj, worked=True, workspace=ws)

        # 3 次後計數應重置為 0（已升級）
        key = "score_low:compress_output"
        assert mgr._outcome_counts.get(key, 0) == 0

        # general_lessons.json 應存在（trigger 無法推導出 skill_name）
        lessons_path = ws / "data/_system/general_lessons.json"
        assert lessons_path.exists()
        lessons = json.loads(lessons_path.read_text(encoding="utf-8"))
        assert len(lessons) == 1
        assert lessons[0]["trigger"] == "score_low"
        assert lessons[0]["adjustment"] == COMPRESS_OUTPUT

    def test_promote_to_lesson_writes_to_skill_specific_file(self, tmp_path: Path):
        """trigger 包含已知 skill 名稱時，應寫入對應 Skill 的 _lessons.json."""
        ws = self._make_workspace(tmp_path)
        mgr = SessionAdjustmentManager()
        # trigger 包含 "darwin"
        adj = self._make_adj(trigger="darwin:health_drop", adjustment="degrade_skill")

        for _ in range(3):
            mgr.record_outcome("sess_b05", adj, worked=True, workspace=ws)

        skill_lessons = (
            ws / "data" / "skills" / "native" / "darwin" / "_lessons.json"
        )
        assert skill_lessons.exists()
        lessons = json.loads(skill_lessons.read_text(encoding="utf-8"))
        assert len(lessons) == 1
        assert lessons[0]["trigger"] == "darwin:health_drop"


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 C2：pending_adjustments 寫入/讀取/清空 + load_pending_from_nightly
# ═══════════════════════════════════════════════════════════════════════════════


class TestPendingAdjustments:
    """補線 C：pending_adjustments 閉環測試."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "MUSEON"
        ws.mkdir()
        return ws

    def _make_signal_medium_auto(self) -> AwarenessSignal:
        return AwarenessSignal(
            source="skill_health_tracker",
            title="darwin 品質下降",
            severity=Severity.MEDIUM,
            signal_type=SignalType.QUALITY_DROP,
            actionability=Actionability.AUTO,
            suggested_action=COMPRESS_OUTPUT,
            context={"max_sentences": 3},
        )

    @pytest.mark.asyncio
    async def test_medium_auto_writes_pending(self, tmp_path: Path):
        """MEDIUM+AUTO 訊號應寫入 pending_adjustments.json."""
        ws = self._make_workspace(tmp_path)
        sig = self._make_signal_medium_auto()

        queue_path = ws / "data/_system/triage_queue.jsonl"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(
            json.dumps(sig.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8"
        )

        await run_triage(ws, event_bus=None)

        pending_path = ws / "data/_system/pending_adjustments.json"
        assert pending_path.exists()
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        assert len(pending) == 1
        assert pending[0]["adjustment"] == COMPRESS_OUTPUT

    @pytest.mark.asyncio
    async def test_load_pending_from_nightly_loads_and_clears(self, tmp_path: Path):
        """load_pending_from_nightly 應載入並清空 pending_adjustments.json."""
        ws = self._make_workspace(tmp_path)

        pending_path = ws / "data/_system/pending_adjustments.json"
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        items = [
            {
                "trigger": "skill_health_tracker:quality_drop",
                "adjustment": COMPRESS_OUTPUT,
                "params": {"max_sentences": 3},
                "expires_after_turns": 5,
                "created_at": "2026-03-31T00:00:00+00:00",
            },
            {
                "trigger": "test_source:behavior_drift",
                "adjustment": SWITCH_APPROACH,
                "params": {},
                "expires_after_turns": 3,
                "created_at": "2026-03-31T01:00:00+00:00",
            },
        ]
        pending_path.write_text(json.dumps(items), encoding="utf-8")

        mgr = SessionAdjustmentManager()
        count = mgr.load_pending_from_nightly(ws, "sess_c01")

        assert count == 2
        active = mgr.get_active("sess_c01", current_turn=0)
        assert len(active) == 2

        # 檔案應被清空
        cleared = json.loads(pending_path.read_text(encoding="utf-8"))
        assert cleared == []

    @pytest.mark.asyncio
    async def test_load_pending_from_nightly_missing_file(self, tmp_path: Path):
        """pending_adjustments.json 不存在時，load_pending_from_nightly 應回傳 0."""
        ws = self._make_workspace(tmp_path)

        mgr = SessionAdjustmentManager()
        count = mgr.load_pending_from_nightly(ws, "sess_c02")
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 D2：INFO 訊號的 dropped 審計紀錄
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfoDroppedAudit:
    """補線 D：INFO 訊號放下的審計紀錄測試."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "MUSEON"
        ws.mkdir()
        return ws

    @pytest.mark.asyncio
    async def test_info_signal_writes_dropped_audit(self, tmp_path: Path):
        """INFO 訊號分診後，awareness_log 應有 dropped 審計記錄."""
        ws = self._make_workspace(tmp_path)

        sig = AwarenessSignal(
            source="test_source",
            title="INFO 測試訊號",
            severity=Severity.INFO,
            signal_type=SignalType.QUALITY_DROP,
            actionability=Actionability.AUTO,
        )
        queue_path = ws / "data/_system/triage_queue.jsonl"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue_path.write_text(
            json.dumps(sig.to_dict(), ensure_ascii=False) + "\n", encoding="utf-8"
        )

        stats = await run_triage(ws, event_bus=None)

        assert stats["info"] == 1
        assert stats["dropped"] == 1

        log_path = ws / "data/_system/awareness_log.jsonl"
        assert log_path.exists()
        lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["status"] == "dropped"
        assert entry["reason"] == "info_severity"
        assert entry["title"] == "INFO 測試訊號"


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 E2：check_accumulation_upgrades 累積升級
# ═══════════════════════════════════════════════════════════════════════════════


class TestAccumulationUpgrades:
    """補線 E：同類訊號累積 ≥3 次 → 升級為 MEDIUM 測試."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "MUSEON"
        ws.mkdir()
        return ws

    def _write_log_entries(self, ws: Path, entries: list) -> None:
        """直接寫入 awareness_log.jsonl."""
        from datetime import datetime, timezone
        log_path = ws / "data/_system/awareness_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        with open(log_path, "w", encoding="utf-8") as f:
            for entry in entries:
                if "created_at" not in entry:
                    entry["created_at"] = now
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def test_three_same_type_signals_upgrade(self, tmp_path: Path):
        """3 個同類訊號 → check_accumulation_upgrades 應升級為 MEDIUM."""
        ws = self._make_workspace(tmp_path)
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        entries = [
            {
                "source": "skill_health_tracker",
                "signal_type": "quality_drop",
                "title": f"品質下降 {i}",
                "created_at": now,
            }
            for i in range(3)
        ]
        self._write_log_entries(ws, entries)

        upgraded = check_accumulation_upgrades(ws)

        assert len(upgraded) == 1
        assert upgraded[0].severity == Severity.MEDIUM
        assert "累積升級" in upgraded[0].title
        assert upgraded[0].context["accumulated_count"] == 3

    def test_less_than_3_does_not_upgrade(self, tmp_path: Path):
        """少於 3 個同類訊號不應升級."""
        ws = self._make_workspace(tmp_path)
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        entries = [
            {
                "source": "skill_health_tracker",
                "signal_type": "quality_drop",
                "title": f"品質下降 {i}",
                "created_at": now,
            }
            for i in range(2)
        ]
        self._write_log_entries(ws, entries)

        upgraded = check_accumulation_upgrades(ws)
        assert len(upgraded) == 0

    def test_old_entries_excluded(self, tmp_path: Path):
        """超過 7 天的舊訊號不應計入累積."""
        ws = self._make_workspace(tmp_path)
        from datetime import datetime, timedelta, timezone

        old_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        entries = [
            {
                "source": "skill_health_tracker",
                "signal_type": "quality_drop",
                "title": f"舊訊號 {i}",
                "created_at": old_time,
            }
            for i in range(5)
        ]
        self._write_log_entries(ws, entries)

        upgraded = check_accumulation_upgrades(ws)
        assert len(upgraded) == 0

    def test_different_types_do_not_merge(self, tmp_path: Path):
        """不同類型的訊號不應合併計數."""
        ws = self._make_workspace(tmp_path)
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        entries = (
            [
                {
                    "source": "src_a",
                    "signal_type": "quality_drop",
                    "title": f"品質 {i}",
                    "created_at": now,
                }
                for i in range(2)
            ]
            + [
                {
                    "source": "src_b",
                    "signal_type": "behavior_drift",
                    "title": f"偏移 {i}",
                    "created_at": now,
                }
                for i in range(2)
            ]
        )
        self._write_log_entries(ws, entries)

        upgraded = check_accumulation_upgrades(ws)
        assert len(upgraded) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 測試 H2：MEDIUM+HUMAN 積壓 3 條 → 推播
# ═══════════════════════════════════════════════════════════════════════════════


class TestHumanQueueBatch:
    """補線 H：MEDIUM+HUMAN 積壓計數達 3 條時推播測試."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "MUSEON"
        ws.mkdir()
        return ws

    def _make_medium_human_signal(self, title: str) -> AwarenessSignal:
        return AwarenessSignal(
            source="test_source",
            title=title,
            severity=Severity.MEDIUM,
            signal_type=SignalType.BEHAVIOR_DRIFT,
            actionability=Actionability.HUMAN,
        )

    def _write_signals(self, ws: Path, signals: list) -> None:
        queue_path = ws / "data/_system/triage_queue.jsonl"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        with open(queue_path, "w", encoding="utf-8") as f:
            for sig in signals:
                f.write(json.dumps(sig.to_dict(), ensure_ascii=False) + "\n")

    @pytest.mark.asyncio
    async def test_less_than_3_human_no_batch_publish(self, tmp_path: Path):
        """不足 3 條 MEDIUM+HUMAN 時，不應觸發 batch 推播."""
        ws = self._make_workspace(tmp_path)
        signals = [
            self._make_medium_human_signal("待處理事項 1"),
            self._make_medium_human_signal("待處理事項 2"),
        ]
        self._write_signals(ws, signals)

        mock_bus = MagicMock()
        mock_bus.publish = MagicMock()

        await run_triage(ws, event_bus=mock_bus)

        batch_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "PROACTIVE_MESSAGE"
            and c[0][1].get("source") == "triage_human_batch"
        ]
        assert len(batch_calls) == 0

    @pytest.mark.asyncio
    async def test_exactly_3_human_triggers_publish(self, tmp_path: Path):
        """恰好 3 條 MEDIUM+HUMAN → 應觸發 PROACTIVE_MESSAGE 推播."""
        ws = self._make_workspace(tmp_path)
        signals = [
            self._make_medium_human_signal(f"待處理事項 {i}") for i in range(3)
        ]
        self._write_signals(ws, signals)

        mock_bus = MagicMock()
        mock_bus.publish = MagicMock()

        await run_triage(ws, event_bus=mock_bus)

        batch_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "PROACTIVE_MESSAGE"
            and c[0][1].get("source") == "triage_human_batch"
        ]
        assert len(batch_calls) == 1
        payload = batch_calls[0][0][1]
        assert "待處理事項" in payload["text"]

    @pytest.mark.asyncio
    async def test_human_queue_cleared_after_publish(self, tmp_path: Path):
        """推播後 triage_human_queue.json 應被清空."""
        ws = self._make_workspace(tmp_path)
        signals = [
            self._make_medium_human_signal(f"待處理 {i}") for i in range(3)
        ]
        self._write_signals(ws, signals)

        mock_bus = MagicMock()
        mock_bus.publish = MagicMock()

        await run_triage(ws, event_bus=mock_bus)

        human_queue_path = ws / "data/_system/triage_human_queue.json"
        assert human_queue_path.exists()
        queue = json.loads(human_queue_path.read_text(encoding="utf-8"))
        assert queue == []

    @pytest.mark.asyncio
    async def test_human_queue_accumulates_across_runs(self, tmp_path: Path):
        """跨多次 run_triage 累積，滿 3 條才推播."""
        ws = self._make_workspace(tmp_path)
        mock_bus = MagicMock()
        mock_bus.publish = MagicMock()

        # 第一輪：2 條
        self._write_signals(ws, [
            self._make_medium_human_signal("事項 A"),
            self._make_medium_human_signal("事項 B"),
        ])
        await run_triage(ws, event_bus=mock_bus)

        batch_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "PROACTIVE_MESSAGE"
            and c[0][1].get("source") == "triage_human_batch"
        ]
        assert len(batch_calls) == 0

        # 第二輪：再加 1 條（累積 3 條）
        self._write_signals(ws, [self._make_medium_human_signal("事項 C")])
        await run_triage(ws, event_bus=mock_bus)

        batch_calls = [
            c for c in mock_bus.publish.call_args_list
            if c[0][0] == "PROACTIVE_MESSAGE"
            and c[0][1].get("source") == "triage_human_batch"
        ]
        assert len(batch_calls) == 1
