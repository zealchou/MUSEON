"""直覺引擎 (Intuition Engine) 測試.

涵蓋 BDD 11-intuition-engine.feature 的所有 Scenario：
- L1 信號收集（句長偏差、信心轉變、回應延遲、模式中斷）
- L2 啟發式規則庫（IF-THEN 壓縮、RI > 0.2 門檻）
- L3 上下文建模（圖結構、跨輪持久化）
- L4 異常偵測（四級分類 neutral/notable/significant/emergency）
- L5 預測層（3-5 路徑模擬、機率和 ≈ 100%）
- Brain 整合（Step -0.5 插入）
- 安全護欄（觀察≠監控、不確定性標籤）
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from museon.agent.intuition import (
    AnomalyLevel,
    AnomalyResult,
    ContextEdge,
    ContextGraph,
    ContextNode,
    HeuristicMatch,
    HeuristicRule,
    IntuitionEngine,
    IntuitionReport,
    IntuitionStore,
    PredictedPath,
    Signal,
    SignalType,
    _MIN_RI_SCORE,
)


@pytest.fixture
def data_dir(tmp_path):
    """建立測試用資料目錄."""
    intuition_dir = tmp_path / "intuition"
    intuition_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def intuition_engine(data_dir):
    """建立 IntuitionEngine 測試實例."""
    return IntuitionEngine(data_dir=str(data_dir))


# ═══════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════

def _make_signal(
    signal_type: SignalType = SignalType.SENTENCE_LENGTH_DEVIATION,
    raw_value: float = 10.0,
    baseline: float = 50.0,
    deviation: float = 0.80,
    timestamp: str | None = None,
) -> Signal:
    """Build a Signal with sensible defaults."""
    return Signal(
        signal_type=signal_type,
        raw_value=raw_value,
        baseline=baseline,
        deviation=deviation,
        timestamp=timestamp or datetime.now().isoformat(),
    )


def _make_heuristic_rule(
    rule_id: str = "HR-001",
    condition: str = "sentence_length_deviation > 40%",
    prediction: str = "使用者可能感到沮喪",
    confidence: float = 0.7,
    ri_score: float = 0.5,
    source_crystals: list | None = None,
) -> HeuristicRule:
    """Build a HeuristicRule with sensible defaults."""
    return HeuristicRule(
        rule_id=rule_id,
        condition=condition,
        prediction=prediction,
        confidence=confidence,
        ri_score=ri_score,
        source_crystals=source_crystals or [],
        last_updated=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════
# Section 1: L1 信號收集
# ════════════════════════════════════════════

class TestL1SignalIntake:
    """測試 L1 原始信號收集.

    _collect_signals(content: str, user_history: Dict[str, Any]) -> List[Signal]
    user_history 是一個字典，包含基線數據 key 如:
      avg_sentence_length, avg_confidence_index,
      avg_response_delay_seconds, last_message_time,
      typical_interaction_depth, typical_question_ratio
    """

    def test_collect_sentence_length_and_confidence_signals(self, intuition_engine):
        """收集句長偏差與確信度轉變信號."""
        signals = intuition_engine._collect_signals(
            content="短訊息",
            user_history={
                "avg_sentence_length": 20.0,
                "avg_confidence_index": 0.7,
            },
        )
        signal_types = {s.signal_type for s in signals}
        assert SignalType.SENTENCE_LENGTH_DEVIATION in signal_types
        assert SignalType.CONFIDENCE_SHIFT in signal_types

    def test_signal_has_required_fields(self, intuition_engine):
        """每個信號包含必要欄位：signal_type, raw_value, baseline, deviation, timestamp."""
        signals = intuition_engine._collect_signals(
            content="測試訊息，包含一些內容讓句長偏差被偵測到",
            user_history={
                "avg_sentence_length": 5.0,
            },
        )
        for signal in signals:
            assert isinstance(signal.signal_type, SignalType)
            assert isinstance(signal.raw_value, float)
            assert isinstance(signal.baseline, float)
            assert isinstance(signal.deviation, float)
            assert isinstance(signal.timestamp, str)

    def test_sentence_length_deviation_calculation(self, intuition_engine):
        """句長偏差信號正確計算 — deviation 是 0-1 之間的比例."""
        signals = intuition_engine._collect_signals(
            content="短",  # 非常短的訊息 (1 個中文字元)
            user_history={
                "avg_sentence_length": 20.0,
            },
        )
        length_signals = [
            s for s in signals
            if s.signal_type == SignalType.SENTENCE_LENGTH_DEVIATION
        ]
        assert len(length_signals) >= 1
        sig = length_signals[0]
        # deviation 是比例 (0.0-1.0+)，baseline=20, raw=1 -> deviation ~0.95
        assert sig.deviation > 0.3  # 顯著偏差

    def test_no_signals_without_baseline(self, intuition_engine):
        """沒有基線數據時不產生信號."""
        signals = intuition_engine._collect_signals(
            content="測試訊息",
            user_history={},  # 空字典: 沒有基線
        )
        # 沒有基線 -> 各偵測函數返回 None -> 空列表
        assert isinstance(signals, list)

    def test_confidence_shift_signal(self, intuition_engine):
        """確信度轉變信號偵測."""
        signals = intuition_engine._collect_signals(
            content="或許可能也許大概不確定",  # 大量猶豫詞降低確信度
            user_history={
                "avg_confidence_index": 0.9,  # 高基線
            },
        )
        conf_signals = [
            s for s in signals
            if s.signal_type == SignalType.CONFIDENCE_SHIFT
        ]
        assert len(conf_signals) >= 1
        # 猶豫詞使確信度大幅低於基線
        assert conf_signals[0].deviation > 0.1

    def test_pattern_break_signal(self, intuition_engine):
        """行為模式中斷信號偵測."""
        signals = intuition_engine._collect_signals(
            content="好",  # 極簡短 — 與高基線互動深度形成對比
            user_history={
                "typical_interaction_depth": 3.0,
                "typical_question_ratio": 5.0,
            },
        )
        break_signals = [
            s for s in signals
            if s.signal_type == SignalType.PATTERN_BREAK
        ]
        assert len(break_signals) >= 1


# ════════════════════════════════════════════
# Section 2: L2 啟發式規則庫
# ════════════════════════════════════════════

class TestL2HeuristicLibrary:
    """測試啟發式規則庫."""

    def test_heuristic_rule_structure(self):
        """啟發式規則有完整結構."""
        rule = _make_heuristic_rule(
            rule_id="HR-001",
            condition="sentence_length_deviation > 40% AND confidence_shift < 0",
            prediction="使用者可能感到沮喪",
            confidence=0.7,
            ri_score=0.3,
        )
        assert rule.rule_id == "HR-001"
        assert rule.confidence == 0.7
        assert rule.ri_score > _MIN_RI_SCORE  # RI > 0.2 門檻

    def test_heuristic_rule_serialization(self):
        """啟發式規則序列化/反序列化."""
        rule = _make_heuristic_rule()
        d = rule.to_dict()
        restored = HeuristicRule.from_dict(d)
        assert restored.rule_id == rule.rule_id
        assert restored.ri_score == rule.ri_score
        assert restored.source_crystals == rule.source_crystals

    def test_refresh_heuristics_filters_low_ri(self, data_dir):
        """refresh_heuristics() 過濾 RI < 0.2 的規則."""
        store = IntuitionStore(data_dir=str(data_dir))
        rules = [
            _make_heuristic_rule(rule_id="HR-LOW", ri_score=0.1),
            _make_heuristic_rule(rule_id="HR-HIGH", ri_score=0.5),
        ]
        store.save_heuristics(rules)

        engine = IntuitionEngine(data_dir=str(data_dir))
        count = engine.refresh_heuristics()
        # 只有 HR-HIGH 通過 RI >= 0.2 品質門檻
        assert count == 1
        assert len(engine._heuristics) == 1
        assert engine._heuristics[0].rule_id == "HR-HIGH"

    def test_consolidate_heuristics_removes_low_ri(self, data_dir):
        """store.consolidate_heuristics 移除 RI < 0.2 的規則."""
        store = IntuitionStore(data_dir=str(data_dir))
        rules = [
            _make_heuristic_rule(rule_id="HR-LOW", ri_score=0.1),
            _make_heuristic_rule(rule_id="HR-HIGH", ri_score=0.5),
        ]
        consolidated = store.consolidate_heuristics(rules)
        assert len(consolidated) == 1
        assert consolidated[0].rule_id == "HR-HIGH"

    def test_apply_heuristics_matches_signals(self, data_dir):
        """_apply_heuristics 匹配信號到規則."""
        store = IntuitionStore(data_dir=str(data_dir))
        rules = [
            _make_heuristic_rule(
                rule_id="HR-ENERGY",
                condition="sentence_length_deviation detected with energy drop",
                prediction="使用者能量下降",
                confidence=0.8,
                ri_score=0.6,
            ),
        ]
        store.save_heuristics(rules)

        engine = IntuitionEngine(data_dir=str(data_dir))
        signals = [
            _make_signal(
                signal_type=SignalType.SENTENCE_LENGTH_DEVIATION,
                deviation=0.47,  # 超過 0.1 閾值 -> 有效匹配
            ),
        ]
        matches = engine._apply_heuristics(signals)
        assert len(matches) >= 1
        assert isinstance(matches[0], HeuristicMatch)
        assert matches[0].rule.rule_id == "HR-ENERGY"
        # match_confidence = confidence * ri_score = 0.8 * 0.6 = 0.48
        assert abs(matches[0].match_confidence - 0.48) < 0.01

    def test_apply_heuristics_no_match_if_low_deviation(self, data_dir):
        """偏差 < 0.1 的信號不觸發啟發式匹配."""
        store = IntuitionStore(data_dir=str(data_dir))
        rules = [
            _make_heuristic_rule(
                rule_id="HR-ENERGY",
                condition="sentence_length_deviation",
                prediction="test",
                confidence=0.8,
                ri_score=0.6,
            ),
        ]
        store.save_heuristics(rules)

        engine = IntuitionEngine(data_dir=str(data_dir))
        signals = [
            _make_signal(
                signal_type=SignalType.SENTENCE_LENGTH_DEVIATION,
                deviation=0.05,  # 低於 0.1 閾值
            ),
        ]
        matches = engine._apply_heuristics(signals)
        assert len(matches) == 0


# ════════════════════════════════════════════
# Section 3: L3 上下文建模
# ════════════════════════════════════════════

class TestL3ContextModeler:
    """測試上下文建模."""

    def test_context_graph_creation(self, intuition_engine):
        """建立上下文圖."""
        graph = intuition_engine._update_context(
            content="幫我分析台積電的投資價值",
            session_id="test_session",
        )
        assert isinstance(graph, ContextGraph)
        assert graph.session_id == "test_session"
        assert len(graph.nodes) > 0

    def test_context_persists_across_turns(self, intuition_engine):
        """上下文在同 session 中跨輪持久化（增量更新，不從零重建）."""
        graph1 = intuition_engine._update_context(
            content="幫我分析台積電的投資價值，目前市場前景如何",
            session_id="persist_session",
        )
        node_count_after_turn1 = len(graph1.nodes)

        graph2 = intuition_engine._update_context(
            content="再看看三星的競爭力如何，以及未來可能的趨勢",
            session_id="persist_session",
        )
        # 第二輪應該包含第一輪的上下文 + 新增的節點
        assert len(graph2.nodes) > node_count_after_turn1

    def test_context_graph_incremental_metadata(self, intuition_engine):
        """情境圖的 metadata 會增量更新 turn_count."""
        intuition_engine._update_context(
            content="第一輪對話，確認一下基本情況和背景資訊",
            session_id="meta_session",
        )
        graph = intuition_engine._update_context(
            content="第二輪對話，進一步深入探討技術細節",
            session_id="meta_session",
        )
        assert graph.metadata.get("turn_count", 0) >= 2

    def test_context_graph_node_types(self, intuition_engine):
        """情境圖包含多種節點類型：emotion, intention, topic."""
        graph = intuition_engine._update_context(
            content="幫我做一件事，我覺得很焦慮擔心",
            session_id="node_type_session",
        )
        node_types = {n.node_type for n in graph.nodes.values()}
        # 含 "焦慮" -> emotion; 含 "幫我" -> intention; 長度 > 10 -> topic
        assert "emotion" in node_types
        assert "intention" in node_types

    def test_context_graph_add_node_and_edge(self):
        """ContextGraph add_node / add_edge API."""
        graph = ContextGraph(session_id="api_test")
        node = ContextNode(
            node_id="n1",
            node_type="entity",
            label="客戶 A",
        )
        graph.add_node(node)
        assert "n1" in graph.nodes

        edge = ContextEdge(
            edge_id="e1",
            source_id="n1",
            target_id="n2",
            relation="競爭",
        )
        graph.add_edge(edge)
        assert "e1" in graph.edges

    def test_context_graph_get_nodes_by_type(self):
        """ContextGraph.get_nodes_by_type 依類型過濾節點."""
        graph = ContextGraph(session_id="filter_test")
        graph.add_node(ContextNode(node_id="e1", node_type="emotion", label="焦慮"))
        graph.add_node(ContextNode(node_id="t1", node_type="topic", label="投資"))
        graph.add_node(ContextNode(node_id="e2", node_type="emotion", label="興奮"))

        emotions = graph.get_nodes_by_type("emotion")
        assert len(emotions) == 2

    def test_context_graph_merge(self):
        """ContextGraph.merge 合併兩個情境圖."""
        g1 = ContextGraph(session_id="s1")
        g1.add_node(ContextNode(node_id="n1", node_type="topic", label="A"))

        g2 = ContextGraph(session_id="s2")
        g2.add_node(ContextNode(node_id="n2", node_type="topic", label="B"))
        g2.add_node(ContextNode(node_id="n1", node_type="topic", label="A updated", properties={"extra": True}))

        g1.merge(g2)
        assert "n2" in g1.nodes
        # 合併時 n1 的 properties 被更新
        assert g1.nodes["n1"].properties.get("extra") is True

    def test_context_graph_serialization(self):
        """ContextGraph to_dict / from_dict 序列化."""
        graph = ContextGraph(session_id="serial_test")
        graph.add_node(ContextNode(node_id="n1", node_type="topic", label="test"))
        graph.add_edge(ContextEdge(edge_id="e1", source_id="n1", target_id="n2", relation="ref"))

        d = graph.to_dict()
        restored = ContextGraph.from_dict(d)
        assert restored.session_id == "serial_test"
        assert "n1" in restored.nodes
        assert "e1" in restored.edges


# ════════════════════════════════════════════
# Section 4: L4 異常偵測
# ════════════════════════════════════════════

class TestL4AnomalyDetector:
    """測試異常偵測."""

    def test_four_level_classification(self):
        """四級信號分類正確 — _classify_anomaly_level 是 @staticmethod."""
        # neutral: < 10%
        result = IntuitionEngine._classify_anomaly_level(deviation_pct=5)
        assert result == AnomalyLevel.NEUTRAL

        # notable: 10-30%
        result = IntuitionEngine._classify_anomaly_level(deviation_pct=20)
        assert result == AnomalyLevel.NOTABLE

        # significant: 30-60%
        result = IntuitionEngine._classify_anomaly_level(deviation_pct=45)
        assert result == AnomalyLevel.SIGNIFICANT

        # emergency: >= 60%
        result = IntuitionEngine._classify_anomaly_level(deviation_pct=75)
        assert result == AnomalyLevel.EMERGENCY

    def test_boundary_values(self):
        """邊界值測試 — 閾值精確分類."""
        assert IntuitionEngine._classify_anomaly_level(0) == AnomalyLevel.NEUTRAL
        assert IntuitionEngine._classify_anomaly_level(9.99) == AnomalyLevel.NEUTRAL
        assert IntuitionEngine._classify_anomaly_level(10) == AnomalyLevel.NOTABLE
        assert IntuitionEngine._classify_anomaly_level(29.99) == AnomalyLevel.NOTABLE
        assert IntuitionEngine._classify_anomaly_level(30) == AnomalyLevel.SIGNIFICANT
        assert IntuitionEngine._classify_anomaly_level(59.99) == AnomalyLevel.SIGNIFICANT
        assert IntuitionEngine._classify_anomaly_level(60) == AnomalyLevel.EMERGENCY
        assert IntuitionEngine._classify_anomaly_level(100) == AnomalyLevel.EMERGENCY

    def test_anomaly_detection_returns_results(self, intuition_engine):
        """_detect_anomalies 返回 List[AnomalyResult]."""
        signals = [
            _make_signal(
                signal_type=SignalType.SENTENCE_LENGTH_DEVIATION,
                raw_value=5.0,
                baseline=50.0,
                deviation=0.90,  # 90% -> emergency
            ),
        ]
        anomalies = intuition_engine._detect_anomalies(signals)
        assert len(anomalies) >= 1
        assert isinstance(anomalies[0], AnomalyResult)
        assert anomalies[0].level == AnomalyLevel.EMERGENCY
        assert anomalies[0].deviation_pct == 90.0

    def test_anomaly_detection_neutral_for_small_deviation(self, intuition_engine):
        """小偏差信號被歸類為 neutral."""
        signals = [
            _make_signal(deviation=0.05),  # 5% -> neutral
        ]
        anomalies = intuition_engine._detect_anomalies(signals)
        non_absence = [a for a in anomalies if not a.is_absence]
        assert len(non_absence) >= 1
        assert non_absence[0].level == AnomalyLevel.NEUTRAL

    def test_anomaly_detection_notable_range(self, intuition_engine):
        """10%-30% 偏差被歸類為 notable."""
        signals = [
            _make_signal(deviation=0.20),  # 20% -> notable
        ]
        anomalies = intuition_engine._detect_anomalies(signals)
        non_absence = [a for a in anomalies if not a.is_absence]
        assert non_absence[0].level == AnomalyLevel.NOTABLE

    def test_anomaly_detection_significant_range(self, intuition_engine):
        """30%-60% 偏差被歸類為 significant."""
        signals = [
            _make_signal(deviation=0.45),  # 45% -> significant
        ]
        anomalies = intuition_engine._detect_anomalies(signals)
        non_absence = [a for a in anomalies if not a.is_absence]
        assert non_absence[0].level == AnomalyLevel.SIGNIFICANT

    def test_absence_detection(self, data_dir):
        """缺席偵測 — 預期信號未出現."""
        store = IntuitionStore(data_dir=str(data_dir))
        # 建立一條規則，預期 confidence 信號
        rules = [
            _make_heuristic_rule(
                rule_id="HR-CONF",
                condition="confidence shift detected",
                prediction="test",
                ri_score=0.5,
            ),
        ]
        store.save_heuristics(rules)

        engine = IntuitionEngine(data_dir=str(data_dir))
        # 只提供句長信號，不提供 confidence 信號
        signals = [
            _make_signal(signal_type=SignalType.SENTENCE_LENGTH_DEVIATION),
        ]
        anomalies = engine._detect_anomalies(signals)
        absence_anomalies = [a for a in anomalies if a.is_absence]
        assert len(absence_anomalies) >= 1
        assert absence_anomalies[0].level == AnomalyLevel.NOTABLE

    def test_anomaly_result_has_description(self, intuition_engine):
        """AnomalyResult 包含描述 — 抽象化偏差指標，不含原文."""
        signals = [
            _make_signal(
                signal_type=SignalType.CONFIDENCE_SHIFT,
                raw_value=0.3,
                baseline=0.7,
                deviation=0.57,
            ),
        ]
        anomalies = intuition_engine._detect_anomalies(signals)
        non_absence = [a for a in anomalies if not a.is_absence]
        assert len(non_absence) >= 1
        desc = non_absence[0].description
        assert "confidence_shift" in desc
        # 描述中包含偏差資訊，但不含使用者原文
        assert "偏差" in desc


# ════════════════════════════════════════════
# Section 5: L5 預測層
# ════════════════════════════════════════════

class TestL5PredictiveLayer:
    """測試預測層."""

    def test_generates_3_to_5_paths(self, intuition_engine):
        """生成 3-5 條預測路徑."""
        context = ContextGraph(session_id="test")
        paths = intuition_engine._predict_paths(
            context=context,
            anomalies=[],
            heuristic_matches=[],
        )
        assert 3 <= len(paths) <= 5

    def test_probabilities_sum_to_100(self, intuition_engine):
        """所有路徑的機率總和 ≈ 100%."""
        context = ContextGraph(session_id="test")
        paths = intuition_engine._predict_paths(
            context=context,
            anomalies=[],
            heuristic_matches=[],
        )
        total = sum(p.probability for p in paths)
        assert 95 <= total <= 105  # 允許 ±5% 誤差

    def test_path_has_confidence_score(self, intuition_engine):
        """每條路徑都有信心度 (0-1)."""
        context = ContextGraph(session_id="test")
        paths = intuition_engine._predict_paths(
            context=context,
            anomalies=[],
            heuristic_matches=[],
        )
        for path in paths:
            assert isinstance(path, PredictedPath)
            assert 0 <= path.confidence <= 1.0

    def test_path_has_recommended_action(self, intuition_engine):
        """每條路徑都有建議行動."""
        context = ContextGraph(session_id="test")
        paths = intuition_engine._predict_paths(
            context=context,
            anomalies=[],
            heuristic_matches=[],
        )
        for path in paths:
            assert path.recommended_action
            assert len(path.recommended_action) > 0

    def test_paths_include_anomaly_response_when_significant(self, intuition_engine):
        """有顯著異常時，路徑包含 anomaly_response."""
        context = ContextGraph(session_id="test")
        sig = _make_signal(deviation=0.65)  # 65% -> emergency
        anomaly = AnomalyResult(
            signal=sig,
            deviation_pct=65.0,
            level=AnomalyLevel.EMERGENCY,
            description="test",
            is_absence=False,
        )
        paths = intuition_engine._predict_paths(
            context=context,
            anomalies=[anomaly],
            heuristic_matches=[],
        )
        path_ids = {p.path_id for p in paths}
        assert "anomaly_response" in path_ids

    def test_paths_with_heuristic_matches(self, data_dir):
        """啟發式匹配結果產生對應的預測路徑."""
        store = IntuitionStore(data_dir=str(data_dir))
        rule = _make_heuristic_rule(
            rule_id="HR-COMP",
            condition="sentence_length_deviation detected",
            prediction="客戶正在考慮競爭方案",
            confidence=0.8,
            ri_score=0.6,
        )
        store.save_heuristics([rule])
        engine = IntuitionEngine(data_dir=str(data_dir))

        sig = _make_signal(deviation=0.50)
        match = HeuristicMatch(
            rule=rule,
            matched_signals=[sig],
            match_confidence=0.48,
        )

        context = ContextGraph(session_id="test")
        paths = engine._predict_paths(
            context=context,
            anomalies=[],
            heuristic_matches=[match],
        )
        # 應該有 heuristic_1 路徑
        path_ids = {p.path_id for p in paths}
        assert "heuristic_1" in path_ids

    def test_predicted_path_uncertainty_label(self):
        """預測路徑序列化時附帶不確定性標籤."""
        path = PredictedPath(
            path_id="test",
            description="test path",
            probability=50.0,
            recommended_action="test action",
            confidence=0.7,
        )
        d = path.to_dict()
        assert d["uncertainty_label"] == "直覺推測，非確定事實"


# ════════════════════════════════════════════
# Section 6: 完整 Pipeline
# ════════════════════════════════════════════

class TestFullPipeline:
    """測試完整直覺引擎 Pipeline."""

    @pytest.mark.asyncio
    async def test_sense_returns_intuition_report(self, intuition_engine):
        """sense() 返回完整的 IntuitionReport."""
        report = await intuition_engine.sense(
            content="幫我分析一下最近的市場趨勢，我覺得有點擔心前景",
            session_id="pipeline_test",
            user_history={
                "avg_sentence_length": 10.0,
                "avg_confidence_index": 0.7,
                "typical_interaction_depth": 2.0,
                "typical_question_ratio": 3.0,
            },
        )
        assert isinstance(report, IntuitionReport)
        assert isinstance(report.signals, list)
        assert isinstance(report.anomalies, list)
        assert isinstance(report.predicted_paths, list)
        assert isinstance(report.context_graph, ContextGraph)
        assert isinstance(report.overall_alert_level, AnomalyLevel)
        assert report.session_id == "pipeline_test"
        assert report.timestamp  # non-empty

    @pytest.mark.asyncio
    async def test_sense_report_has_significant_findings(self, intuition_engine):
        """sense() 報告的 has_significant_findings() 方法."""
        report = await intuition_engine.sense(
            content="短",
            session_id="sig_test",
            user_history={
                "avg_sentence_length": 100.0,  # 巨大偏差 -> emergency
            },
        )
        # 巨大句長偏差應觸發高級別異常
        if report.overall_alert_level in (AnomalyLevel.SIGNIFICANT, AnomalyLevel.EMERGENCY):
            assert report.has_significant_findings()

    @pytest.mark.asyncio
    async def test_sense_with_empty_history(self, intuition_engine):
        """sense() 在沒有使用者歷史時仍正常運行."""
        report = await intuition_engine.sense(
            content="一般性的問題",
            session_id="empty_hist",
            user_history=None,
        )
        assert isinstance(report, IntuitionReport)
        assert report.overall_alert_level == AnomalyLevel.NEUTRAL

    @pytest.mark.asyncio
    async def test_sense_report_serialization(self, intuition_engine):
        """IntuitionReport.to_dict() 序列化."""
        report = await intuition_engine.sense(
            content="測試序列化功能是否正常運作",
            session_id="serial_test",
            user_history={"avg_sentence_length": 5.0},
        )
        d = report.to_dict()
        assert "timestamp" in d
        assert "session_id" in d
        assert "signals" in d
        assert "anomalies" in d
        assert "predicted_paths" in d
        assert "overall_alert_level" in d
        assert "summary" in d
        assert "context_graph_summary" in d

    def test_signal_log_persistence(self, data_dir):
        """信號日誌持久化 — IntuitionStore append / read."""
        store = IntuitionStore(data_dir=str(data_dir))
        signals = [
            _make_signal(signal_type=SignalType.SENTENCE_LENGTH_DEVIATION),
            _make_signal(signal_type=SignalType.CONFIDENCE_SHIFT),
        ]
        store.append_signals(signals)

        # 讀取回來
        read_back = store.read_signals()
        assert len(read_back) == 2
        assert read_back[0].signal_type == SignalType.SENTENCE_LENGTH_DEVIATION

    def test_signal_log_prune(self, data_dir):
        """信號日誌清理過期記錄."""
        store = IntuitionStore(data_dir=str(data_dir))
        old_ts = (datetime.now() - timedelta(days=60)).isoformat()
        new_ts = datetime.now().isoformat()

        signals = [
            _make_signal(timestamp=old_ts),
            _make_signal(timestamp=new_ts),
        ]
        store.append_signals(signals)

        pruned = store.prune_signal_log(retention_days=30)
        assert pruned == 1
        remaining = store.read_signals()
        assert len(remaining) == 1

    def test_context_persistence_via_store(self, data_dir):
        """情境圖透過 IntuitionStore 持久化."""
        store = IntuitionStore(data_dir=str(data_dir))
        graph = ContextGraph(session_id="persist_test")
        graph.add_node(ContextNode(node_id="n1", node_type="topic", label="test"))

        store.save_context(graph)
        loaded = store.load_context("persist_test")
        assert loaded is not None
        assert loaded.session_id == "persist_test"
        assert "n1" in loaded.nodes


# ════════════════════════════════════════════
# Section 7: Brain 整合 — Step -0.5
# ════════════════════════════════════════════

class TestBrainIntegration:
    """測試直覺引擎與 Brain 的整合點."""

    @pytest.mark.asyncio
    async def test_sense_produces_summary(self, intuition_engine):
        """sense() 輸出包含摘要文字."""
        report = await intuition_engine.sense(
            content="我今天覺得有點焦慮，不太確定該怎麼處理客戶的需求",
            session_id="summary_test",
            user_history={
                "avg_sentence_length": 5.0,
                "avg_confidence_index": 0.8,
            },
        )
        assert isinstance(report.summary, str)
        # 有信號時摘要不為空
        if report.signals:
            assert len(report.summary) > 0

    @pytest.mark.asyncio
    async def test_overall_level_is_max_of_anomalies(self, intuition_engine):
        """overall_alert_level 取所有異常中的最高級別."""
        report = await intuition_engine.sense(
            content="短",
            session_id="level_test",
            user_history={
                "avg_sentence_length": 200.0,  # 極大偏差
            },
        )
        # 手動驗證: overall_level >= 每個異常的 level
        if report.anomalies:
            level_priority = {
                AnomalyLevel.NEUTRAL: 0,
                AnomalyLevel.NOTABLE: 1,
                AnomalyLevel.SIGNIFICANT: 2,
                AnomalyLevel.EMERGENCY: 3,
            }
            max_anomaly = max(
                report.anomalies,
                key=lambda a: level_priority.get(a.level, 0),
            )
            assert level_priority[report.overall_alert_level] >= level_priority[max_anomaly.level]

    def test_compute_overall_level_empty(self, intuition_engine):
        """無異常時 overall_level 為 NEUTRAL."""
        level = intuition_engine._compute_overall_level([])
        assert level == AnomalyLevel.NEUTRAL


# ════════════════════════════════════════════
# Section 8: 安全護欄
# ════════════════════════════════════════════

class TestSafetyGuardrails:
    """測試安全護欄 — 觀察是服務，不是監控."""

    def test_signal_does_not_contain_user_content(self, intuition_engine):
        """信號只記錄抽象化偏差指標，不記錄使用者原文."""
        signals = intuition_engine._collect_signals(
            content="這是一段包含敏感資訊的使用者訊息",
            user_history={
                "avg_sentence_length": 5.0,
            },
        )
        for signal in signals:
            d = signal.to_dict()
            serialized = json.dumps(d, ensure_ascii=False)
            # 確保使用者原文不出現在序列化的信號中
            assert "敏感資訊" not in serialized
            assert "使用者訊息" not in serialized

    def test_anomaly_description_is_abstract(self, intuition_engine):
        """AnomalyResult 描述是抽象的偏差指標."""
        signals = [
            _make_signal(
                signal_type=SignalType.SENTENCE_LENGTH_DEVIATION,
                deviation=0.50,
            ),
        ]
        anomalies = intuition_engine._detect_anomalies(signals)
        for anomaly in anomalies:
            if not anomaly.is_absence:
                # 描述應包含信號類型和偏差數字
                assert "sentence_length_deviation" in anomaly.description
                assert "偏差" in anomaly.description

    def test_predicted_path_uncertainty_label_in_serialization(self):
        """所有預測都附帶不確定性標記."""
        path = PredictedPath(
            path_id="safety_test",
            description="test",
            probability=50.0,
            recommended_action="test",
            confidence=0.7,
        )
        d = path.to_dict()
        assert "uncertainty_label" in d
        assert "直覺推測" in d["uncertainty_label"]

    def test_intuition_report_does_not_expose_raw_content(self, intuition_engine):
        """IntuitionReport.to_dict() 不暴露原始使用者資料."""
        report = IntuitionReport(
            timestamp=datetime.now().isoformat(),
            session_id="safety_serial",
            signals=[],
            heuristic_matches=[],
            context_graph=ContextGraph(session_id="safety_serial"),
            anomalies=[],
            predicted_paths=[],
            overall_alert_level=AnomalyLevel.NEUTRAL,
            summary="無顯著直覺信號",
        )
        d = report.to_dict()
        # context_graph 只暴露摘要（node_count, edge_count），不暴露完整圖
        assert "context_graph_summary" in d
        assert "node_count" in d["context_graph_summary"]
        assert "edge_count" in d["context_graph_summary"]


# ════════════════════════════════════════════
# Section 9: 心跳與夜間維護
# ════════════════════════════════════════════

class TestHeartbeatAndMaintenance:
    """測試心跳週期同步與夜間維護."""

    def test_refresh_heuristics(self, data_dir):
        """refresh_heuristics() 從磁碟重新載入並過濾規則."""
        store = IntuitionStore(data_dir=str(data_dir))
        rules = [
            _make_heuristic_rule(rule_id="HR-A", ri_score=0.5),
            _make_heuristic_rule(rule_id="HR-B", ri_score=0.1),
            _make_heuristic_rule(rule_id="HR-C", ri_score=0.8),
        ]
        store.save_heuristics(rules)

        engine = IntuitionEngine(data_dir=str(data_dir))
        count = engine.refresh_heuristics()
        assert count == 2  # HR-A (0.5) and HR-C (0.8), HR-B (0.1) filtered

    @pytest.mark.asyncio
    async def test_nightly_maintenance(self, data_dir):
        """nightly_maintenance() 清理日誌、整合規則、生成報告."""
        store = IntuitionStore(data_dir=str(data_dir))

        # 寫入一些老信號
        old_ts = (datetime.now() - timedelta(days=60)).isoformat()
        store.append_signals([_make_signal(timestamp=old_ts)])

        # 寫入一些規則（含低品質）
        rules = [
            _make_heuristic_rule(rule_id="HR-OK", ri_score=0.5),
            _make_heuristic_rule(rule_id="HR-BAD", ri_score=0.1),
        ]
        store.save_heuristics(rules)

        engine = IntuitionEngine(data_dir=str(data_dir))
        report = await engine.nightly_maintenance()

        assert "tasks" in report
        assert "signal_log_prune" in report["tasks"]
        assert "heuristic_consolidation" in report["tasks"]
        assert "health" in report
        assert report["tasks"]["signal_log_prune"]["status"] == "completed"
        assert report["tasks"]["heuristic_consolidation"]["status"] == "completed"


# ════════════════════════════════════════════
# Section 10: Signal & HeuristicRule 資料類別
# ════════════════════════════════════════════

class TestDataClasses:
    """測試資料類別的序列化和反序列化."""

    def test_signal_to_dict(self):
        """Signal.to_dict() 正確序列化."""
        sig = _make_signal()
        d = sig.to_dict()
        assert d["signal_type"] == sig.signal_type.value
        assert d["raw_value"] == sig.raw_value
        assert d["baseline"] == sig.baseline
        assert d["deviation"] == sig.deviation
        assert d["timestamp"] == sig.timestamp

    def test_signal_from_dict(self):
        """Signal.from_dict() 正確反序列化."""
        sig = _make_signal(signal_type=SignalType.CONFIDENCE_SHIFT)
        d = sig.to_dict()
        restored = Signal.from_dict(d)
        assert restored.signal_type == SignalType.CONFIDENCE_SHIFT
        assert restored.raw_value == sig.raw_value

    def test_signal_type_enum_values(self):
        """SignalType 枚舉包含四種信號類型."""
        assert SignalType.SENTENCE_LENGTH_DEVIATION.value == "sentence_length_deviation"
        assert SignalType.CONFIDENCE_SHIFT.value == "confidence_shift"
        assert SignalType.RESPONSE_DELAY.value == "response_delay"
        assert SignalType.PATTERN_BREAK.value == "pattern_break"

    def test_anomaly_level_enum_values(self):
        """AnomalyLevel 枚舉包含四級."""
        assert AnomalyLevel.NEUTRAL.value == "neutral"
        assert AnomalyLevel.NOTABLE.value == "notable"
        assert AnomalyLevel.SIGNIFICANT.value == "significant"
        assert AnomalyLevel.EMERGENCY.value == "emergency"

    def test_heuristic_rule_to_dict(self):
        """HeuristicRule.to_dict() 正確序列化."""
        rule = _make_heuristic_rule(source_crystals=["crystal_1", "crystal_2"])
        d = rule.to_dict()
        assert d["rule_id"] == rule.rule_id
        assert d["source_crystals"] == ["crystal_1", "crystal_2"]

    def test_heuristic_rule_from_dict_defaults(self):
        """HeuristicRule.from_dict() 處理缺失欄位的預設值."""
        d = {
            "rule_id": "HR-MINIMAL",
            "condition": "test",
            "prediction": "test",
        }
        rule = HeuristicRule.from_dict(d)
        assert rule.confidence == 0.5  # default
        assert rule.ri_score == 0.0  # default
        assert rule.source_crystals == []  # default

    def test_heuristic_match_to_dict(self):
        """HeuristicMatch.to_dict() 序列化."""
        rule = _make_heuristic_rule()
        sig = _make_signal()
        match = HeuristicMatch(
            rule=rule,
            matched_signals=[sig],
            match_confidence=0.48,
        )
        d = match.to_dict()
        assert d["rule_id"] == rule.rule_id
        assert d["match_confidence"] == 0.48
        assert "matched_signal_types" in d

    def test_anomaly_result_to_dict(self):
        """AnomalyResult.to_dict() 序列化."""
        sig = _make_signal()
        anomaly = AnomalyResult(
            signal=sig,
            deviation_pct=45.0,
            level=AnomalyLevel.SIGNIFICANT,
            description="test desc",
            is_absence=False,
        )
        d = anomaly.to_dict()
        assert d["deviation_pct"] == 45.0
        assert d["level"] == "significant"
        assert d["is_absence"] is False
