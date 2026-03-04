"""直覺引擎 — 五層感知架構（Intuition Engine）.

在 Brain.process() 的 Step -0.5 執行，先於 DNA27 信號分類。
工程化人類直覺的五層架構：
  L1 信號擷取 — 文字微表情、時間模式、行為偏差
  L2 啟發式庫 — 結晶化經驗的 IF-THEN 快速匹配（System 1）
  L3 情境建模 — 場域理解（參與者、利害關係、時間壓力）
  L4 異常偵測 — 預期 vs 實際偏差，含缺席偵測
  L5 預測層 — 多路徑情境模擬與建議行動

安全原則：
- 觀察是服務，不是監控 — 只記錄抽象化偏差指標，不記錄原文
- 所有預測帶有不確定性標記（信心度）
- DNA27 護欄永遠優先於直覺建議
- 不對外暴露原始直覺資料，只呈現抽象結論
"""

import asyncio
import json
import logging
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 常數定義
# ═══════════════════════════════════════════

# L4 異常級別閾值（百分比）
_NEUTRAL_THRESHOLD = 10       # < 10% 不動作
_NOTABLE_THRESHOLD = 30       # 10-30% 記錄，不干擾
_SIGNIFICANT_THRESHOLD = 60   # 30-60% 標記注意
# > 60% 為 emergency

# L2 啟發式品質門檻
_MIN_RI_SCORE = 0.2

# L5 預測路徑數量範圍
_MIN_PATHS = 3
_MAX_PATHS = 5

# 信號日誌保留天數
_SIGNAL_LOG_RETENTION_DAYS = 30

# 啟發式規則過期天數（RI 持續低於 0.1）
_HEURISTIC_EXPIRY_DAYS = 90


# ═══════════════════════════════════════════
# 列舉型別
# ═══════════════════════════════════════════

class SignalType(str, Enum):
    """L1 信號類型."""
    SENTENCE_LENGTH_DEVIATION = "sentence_length_deviation"
    CONFIDENCE_SHIFT = "confidence_shift"
    RESPONSE_DELAY = "response_delay"
    PATTERN_BREAK = "pattern_break"


class AnomalyLevel(str, Enum):
    """L4 異常級別 — 四級分類."""
    NEUTRAL = "neutral"         # 偏差 < 10%：不動作
    NOTABLE = "notable"         # 10-30%：記錄，不干擾
    SIGNIFICANT = "significant" # 30-60%：標記注意
    EMERGENCY = "emergency"     # > 60%：觸發立即關注協議


# ═══════════════════════════════════════════
# 資料類別 — L1 信號
# ═══════════════════════════════════════════

@dataclass
class Signal:
    """L1 原始信號 — 從每次互動中擷取.

    每個信號代表一個觀測到的行為偏差指標。
    注意：只記錄抽象化數值，不記錄使用者原文（隱私保護）。
    """
    signal_type: SignalType
    raw_value: float
    baseline: float
    deviation: float           # 偏離基線的百分比（0-1 之間，如 0.47 表示 47%）
    timestamp: str             # ISO 8601 格式

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "signal_type": self.signal_type.value,
            "raw_value": self.raw_value,
            "baseline": self.baseline,
            "deviation": self.deviation,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Signal":
        """從字典反序列化."""
        return cls(
            signal_type=SignalType(data["signal_type"]),
            raw_value=data["raw_value"],
            baseline=data["baseline"],
            deviation=data["deviation"],
            timestamp=data["timestamp"],
        )


# ═══════════════════════════════════════════
# 資料類別 — L2 啟發式規則
# ═══════════════════════════════════════════

@dataclass
class HeuristicRule:
    """L2 啟發式規則 — 從 knowledge-lattice 結晶壓縮的 IF-THEN 規則.

    只有 RI（共振指數）> 0.2 的規則才被保留。
    規則在心跳週期動態更新。
    """
    rule_id: str
    condition: str             # IF 條件描述
    prediction: str            # THEN 預測結果
    confidence: float          # 規則信心度 (0.0-1.0)
    ri_score: float            # Resonance Index 共振指數
    source_crystals: List[str] # 來源結晶 ID 列表
    last_updated: str          # ISO 8601 格式

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "rule_id": self.rule_id,
            "condition": self.condition,
            "prediction": self.prediction,
            "confidence": self.confidence,
            "ri_score": self.ri_score,
            "source_crystals": self.source_crystals,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HeuristicRule":
        """從字典反序列化."""
        return cls(
            rule_id=data["rule_id"],
            condition=data["condition"],
            prediction=data["prediction"],
            confidence=data.get("confidence", 0.5),
            ri_score=data.get("ri_score", 0.0),
            source_crystals=data.get("source_crystals", []),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
        )


@dataclass
class HeuristicMatch:
    """L2 啟發式匹配結果 — 信號命中某條規則時產生."""
    rule: HeuristicRule
    matched_signals: List[Signal]
    match_confidence: float    # 本次匹配的信心度

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "rule_id": self.rule.rule_id,
            "condition": self.rule.condition,
            "prediction": self.rule.prediction,
            "match_confidence": self.match_confidence,
            "matched_signal_types": [
                s.signal_type.value for s in self.matched_signals
            ],
        }


# ═══════════════════════════════════════════
# 資料類別 — L3 情境圖
# ═══════════════════════════════════════════

@dataclass
class ContextNode:
    """L3 情境圖節點 — 代表對話中的實體、主題、情緒或意圖.

    節點類型：entity（實體）、topic（主題）、emotion（情緒）、intention（意圖）
    """
    node_id: str
    node_type: str             # "entity" | "topic" | "emotion" | "intention"
    label: str                 # 節點標籤（如「客戶 A」、「焦慮」）
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "label": self.label,
            "properties": self.properties,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextNode":
        """從字典反序列化."""
        return cls(
            node_id=data["node_id"],
            node_type=data["node_type"],
            label=data["label"],
            properties=data.get("properties", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )


@dataclass
class ContextEdge:
    """L3 情境圖邊 — 代表節點之間的關係.

    例如：客戶 A --[競爭]--> B 公司
    """
    edge_id: str
    source_id: str             # 起始節點 ID
    target_id: str             # 目標節點 ID
    relation: str              # 關係類型（如「競爭」、「合作」、「影響」）
    weight: float = 1.0        # 關係強度
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "weight": self.weight,
            "properties": self.properties,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextEdge":
        """從字典反序列化."""
        return cls(
            edge_id=data["edge_id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation=data["relation"],
            weight=data.get("weight", 1.0),
            properties=data.get("properties", {}),
        )


@dataclass
class ContextGraph:
    """L3 情境圖 — 以圖結構建模當前對話場域.

    跨輪次持續：同一 session 內的情境圖不從零重建，而是增量更新。
    """
    session_id: str
    nodes: Dict[str, ContextNode] = field(default_factory=dict)
    edges: Dict[str, ContextEdge] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_node(self, node: ContextNode) -> None:
        """新增或更新節點（增量更新）."""
        if node.node_id in self.nodes:
            # 增量更新：合併屬性，不覆蓋
            existing = self.nodes[node.node_id]
            existing.properties.update(node.properties)
            existing.updated_at = datetime.now().isoformat()
        else:
            self.nodes[node.node_id] = node
        self.last_updated = datetime.now().isoformat()

    def add_edge(self, edge: ContextEdge) -> None:
        """新增或更新邊."""
        self.edges[edge.edge_id] = edge
        self.last_updated = datetime.now().isoformat()

    def get_nodes_by_type(self, node_type: str) -> List[ContextNode]:
        """依類型取得節點."""
        return [n for n in self.nodes.values() if n.node_type == node_type]

    def merge(self, other: "ContextGraph") -> None:
        """合併另一個情境圖（用於歷史整合）."""
        for node_id, node in other.nodes.items():
            if node_id not in self.nodes:
                self.nodes[node_id] = node
            else:
                # 合併屬性
                self.nodes[node_id].properties.update(node.properties)
        for edge_id, edge in other.edges.items():
            if edge_id not in self.edges:
                self.edges[edge_id] = edge
        self.last_updated = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "session_id": self.session_id,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "edges": {k: v.to_dict() for k, v in self.edges.items()},
            "metadata": self.metadata,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextGraph":
        """從字典反序列化."""
        graph = cls(
            session_id=data["session_id"],
            metadata=data.get("metadata", {}),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
        )
        for node_id, node_data in data.get("nodes", {}).items():
            graph.nodes[node_id] = ContextNode.from_dict(node_data)
        for edge_id, edge_data in data.get("edges", {}).items():
            graph.edges[edge_id] = ContextEdge.from_dict(edge_data)
        return graph


# ═══════════════════════════════════════════
# 資料類別 — L4 異常偵測結果
# ═══════════════════════════════════════════

@dataclass
class AnomalyResult:
    """L4 異常偵測結果.

    四級分類：
    - neutral (< 10%): 不動作
    - notable (10-30%): 記錄，不干擾
    - significant (30-60%): 標記注意
    - emergency (> 60%): 觸發立即關注協議
    """
    signal: Signal
    deviation_pct: float       # 偏差百分比 (0-100)
    level: AnomalyLevel
    description: str = ""      # 異常描述（抽象化，不含原文）
    is_absence: bool = False   # 是否為「缺席偵測」（預期出現但未出現）

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "signal_type": self.signal.signal_type.value,
            "deviation_pct": self.deviation_pct,
            "level": self.level.value,
            "description": self.description,
            "is_absence": self.is_absence,
            "timestamp": self.signal.timestamp,
        }


# ═══════════════════════════════════════════
# 資料類別 — L5 預測路徑
# ═══════════════════════════════════════════

@dataclass
class PredictedPath:
    """L5 預測路徑 — 對話可能的發展方向.

    所有預測都附帶不確定性標記（信心度）。
    直覺預測是提供更好的「問題」，不是提供「答案」。
    """
    path_id: str
    description: str           # 可能發生的情境
    probability: float         # 機率 (0-100)，所有路徑合計約 100%
    recommended_action: str    # 建議行動
    confidence: float          # 對此預測的信心度 (0.0-1.0)

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典."""
        return {
            "path_id": self.path_id,
            "description": self.description,
            "probability": self.probability,
            "recommended_action": self.recommended_action,
            "confidence": self.confidence,
            "uncertainty_label": "直覺推測，非確定事實",
        }


# ═══════════════════════════════════════════
# IntuitionReport — 五層感知聚合輸出
# ═══════════════════════════════════════════

@dataclass
class IntuitionReport:
    """直覺報告 — Step -0.5 的完整輸出.

    Brain 使用此報告調整：
    - 三迴圈路由優先順序
    - Skill 選擇權重
    - 回應語氣與深度
    """
    timestamp: str
    session_id: str

    # L1: 原始信號
    signals: List[Signal] = field(default_factory=list)

    # L2: 啟發式匹配結果
    heuristic_matches: List[HeuristicMatch] = field(default_factory=list)

    # L3: 情境圖
    context_graph: Optional[ContextGraph] = None

    # L4: 異常偵測結果
    anomalies: List[AnomalyResult] = field(default_factory=list)

    # L5: 預測路徑
    predicted_paths: List[PredictedPath] = field(default_factory=list)

    # 聚合摘要
    overall_alert_level: AnomalyLevel = AnomalyLevel.NEUTRAL
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化為字典（不含原始使用者資料）."""
        return {
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "signals": [s.to_dict() for s in self.signals],
            "heuristic_matches": [h.to_dict() for h in self.heuristic_matches],
            "context_graph_summary": {
                "node_count": len(self.context_graph.nodes) if self.context_graph else 0,
                "edge_count": len(self.context_graph.edges) if self.context_graph else 0,
            },
            "anomalies": [a.to_dict() for a in self.anomalies],
            "predicted_paths": [p.to_dict() for p in self.predicted_paths],
            "overall_alert_level": self.overall_alert_level.value,
            "summary": self.summary,
        }

    def has_significant_findings(self) -> bool:
        """是否有需要關注的發現."""
        return self.overall_alert_level in (
            AnomalyLevel.SIGNIFICANT,
            AnomalyLevel.EMERGENCY,
        )


# ═══════════════════════════════════════════
# IntuitionStore — 持久化層
# ═══════════════════════════════════════════

class IntuitionStore:
    """直覺引擎持久化層 — 線程安全的檔案操作.

    儲存結構：
    - data/intuition/signal_log.jsonl  — 信號日誌（append-only）
    - data/intuition/heuristics.json   — 啟發式規則庫
    - data/intuition/contexts/{session_id}.json — 情境模型
    """

    def __init__(self, data_dir: str = "data"):
        """初始化持久化層.

        Args:
            data_dir: 資料根目錄
        """
        self.base_dir = Path(data_dir) / "intuition"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.signal_log_path = self.base_dir / "signal_log.jsonl"
        self.heuristics_path = self.base_dir / "heuristics.json"
        self.contexts_dir = self.base_dir / "contexts"
        self.contexts_dir.mkdir(parents=True, exist_ok=True)

        # 線程安全鎖
        self._signal_lock = threading.Lock()
        self._heuristic_lock = threading.Lock()
        self._context_lock = threading.Lock()

    # ── 信號日誌（append-only JSONL）──

    def append_signals(self, signals: List[Signal]) -> None:
        """追加信號到日誌檔案.

        Args:
            signals: 要記錄的信號列表
        """
        if not signals:
            return
        with self._signal_lock:
            try:
                with open(self.signal_log_path, "a", encoding="utf-8") as f:
                    for signal in signals:
                        line = json.dumps(signal.to_dict(), ensure_ascii=False)
                        f.write(line + "\n")
            except Exception as e:
                logger.error(f"寫入信號日誌失敗: {e}")

    def read_signals(self, since: Optional[datetime] = None) -> List[Signal]:
        """讀取信號日誌.

        Args:
            since: 只讀取此時間之後的信號（預設讀取全部）

        Returns:
            信號列表
        """
        signals: List[Signal] = []
        if not self.signal_log_path.exists():
            return signals

        with self._signal_lock:
            try:
                with open(self.signal_log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            signal = Signal.from_dict(data)
                            if since is not None:
                                sig_time = datetime.fromisoformat(signal.timestamp)
                                if sig_time < since:
                                    continue
                            signals.append(signal)
                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            logger.warning(f"解析信號日誌行失敗: {e}")
            except Exception as e:
                logger.error(f"讀取信號日誌失敗: {e}")
        return signals

    def prune_signal_log(self, retention_days: int = _SIGNAL_LOG_RETENTION_DAYS) -> int:
        """清理過期信號日誌.

        Args:
            retention_days: 保留天數

        Returns:
            清理的記錄數量
        """
        cutoff = datetime.now() - timedelta(days=retention_days)
        kept: List[str] = []
        pruned = 0

        with self._signal_lock:
            if not self.signal_log_path.exists():
                return 0
            try:
                with open(self.signal_log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            ts = datetime.fromisoformat(data.get("timestamp", ""))
                            if ts >= cutoff:
                                kept.append(line)
                            else:
                                pruned += 1
                        except (json.JSONDecodeError, ValueError):
                            pruned += 1

                # 原子寫入：先寫臨時檔再重命名
                tmp_path = self.signal_log_path.with_suffix(".tmp")
                with open(tmp_path, "w", encoding="utf-8") as f:
                    for line in kept:
                        f.write(line + "\n")
                tmp_path.replace(self.signal_log_path)

            except Exception as e:
                logger.error(f"清理信號日誌失敗: {e}")
        return pruned

    # ── 啟發式規則庫 ──

    def load_heuristics(self) -> List[HeuristicRule]:
        """載入啟發式規則庫.

        Returns:
            規則列表
        """
        if not self.heuristics_path.exists():
            return []

        with self._heuristic_lock:
            try:
                data = json.loads(
                    self.heuristics_path.read_text(encoding="utf-8")
                )
                return [
                    HeuristicRule.from_dict(rule)
                    for rule in data.get("rules", [])
                ]
            except Exception as e:
                logger.error(f"載入啟發式規則庫失敗: {e}")
                return []

    def save_heuristics(self, rules: List[HeuristicRule]) -> None:
        """儲存啟發式規則庫.

        Args:
            rules: 規則列表
        """
        with self._heuristic_lock:
            try:
                data = {
                    "version": "1.0.0",
                    "updated_at": datetime.now().isoformat(),
                    "rules": [rule.to_dict() for rule in rules],
                }
                # 原子寫入
                tmp_path = self.heuristics_path.with_suffix(".tmp")
                tmp_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp_path.replace(self.heuristics_path)
            except Exception as e:
                logger.error(f"儲存啟發式規則庫失敗: {e}")

    def consolidate_heuristics(
        self,
        rules: List[HeuristicRule],
        expiry_days: int = _HEURISTIC_EXPIRY_DAYS,
    ) -> List[HeuristicRule]:
        """整合啟發式規則 — 清理低品質與過期規則.

        清除條件：
        - RI < 0.1 且超過 expiry_days 天未更新
        - RI < _MIN_RI_SCORE 的規則不被保留

        Args:
            rules: 現有規則列表
            expiry_days: 過期天數

        Returns:
            整合後的規則列表
        """
        cutoff = datetime.now() - timedelta(days=expiry_days)
        consolidated: List[HeuristicRule] = []

        for rule in rules:
            # 品質門檻
            if rule.ri_score < _MIN_RI_SCORE:
                continue
            # 過期清理：RI < 0.1 且長時間未更新
            if rule.ri_score < 0.1:
                try:
                    last_up = datetime.fromisoformat(rule.last_updated)
                    if last_up < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue
            consolidated.append(rule)

        return consolidated

    # ── 情境模型 ──

    def load_context(self, session_id: str) -> Optional[ContextGraph]:
        """載入 session 的情境圖.

        Args:
            session_id: 會話 ID

        Returns:
            情境圖，若不存在則返回 None
        """
        ctx_path = self.contexts_dir / f"{session_id}.json"
        if not ctx_path.exists():
            return None

        with self._context_lock:
            try:
                data = json.loads(ctx_path.read_text(encoding="utf-8"))
                return ContextGraph.from_dict(data)
            except Exception as e:
                logger.error(f"載入情境模型失敗 (session={session_id}): {e}")
                return None

    def save_context(self, graph: ContextGraph) -> None:
        """儲存情境圖.

        Args:
            graph: 要儲存的情境圖
        """
        ctx_path = self.contexts_dir / f"{graph.session_id}.json"

        with self._context_lock:
            try:
                tmp_path = ctx_path.with_suffix(".tmp")
                tmp_path.write_text(
                    json.dumps(graph.to_dict(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                tmp_path.replace(ctx_path)
            except Exception as e:
                logger.error(
                    f"儲存情境模型失敗 (session={graph.session_id}): {e}"
                )


# ═══════════════════════════════════════════
# IntuitionEngine — 主引擎
# ═══════════════════════════════════════════

class IntuitionEngine:
    """直覺引擎 — 五層感知架構的核心處理器.

    在 Brain.process() 的 Step -0.5 執行，
    提供前意識模式偵測，讓 MuseClaw 能「先感覺再思考」。

    使用方式：
        engine = IntuitionEngine(data_dir="data")
        report = await engine.sense(content, session_id, user_history)
    """

    def __init__(self, data_dir: str = "data"):
        """初始化直覺引擎.

        Args:
            data_dir: 資料根目錄（預設 "data"）
        """
        self.data_dir = Path(data_dir)
        self.store = IntuitionStore(data_dir=data_dir)

        # 載入啟發式規則庫到記憶體
        self._heuristics: List[HeuristicRule] = self.store.load_heuristics()

        # Session 情境圖快取（避免每次都從磁碟讀取）
        self._context_cache: Dict[str, ContextGraph] = {}

        logger.info(
            f"直覺引擎初始化完成 | "
            f"啟發式規則: {len(self._heuristics)} 條 | "
            f"資料目錄: {self.data_dir}"
        )

    # ═══════════════════════════════════════
    # 主入口 — sense()
    # ═══════════════════════════════════════

    async def sense(
        self,
        content: str,
        session_id: str,
        user_history: Optional[Dict[str, Any]] = None,
    ) -> IntuitionReport:
        """執行完整五層感知管道 — Brain.process() 的 Step -0.5.

        流程：
        1. L1 信號擷取 — 收集原始信號
        2. L2 啟發式匹配 — 快速模式匹配
        3. L3 情境建模 — 更新場域理解
        4. L4 異常偵測 — 計算偏差與分類
        5. L5 預測層 — 多路徑模擬

        Args:
            content: 使用者訊息文字
            session_id: 會話 ID
            user_history: 使用者歷史資料（基線數據）

        Returns:
            IntuitionReport — 五層感知的聚合輸出
        """
        now = datetime.now().isoformat()
        # 防禦：Brain 可能傳入 List[Dict]（對話歷史），
        # 但本引擎需要 Dict（基線指標），不匹配時降級為空 dict
        if isinstance(user_history, dict):
            history = user_history
        else:
            history = {}

        # ── L1: 信號擷取 ──
        signals = self._collect_signals(content, history)

        # ── L2: 啟發式匹配 ──
        heuristic_matches = self._apply_heuristics(signals)

        # ── L3: 情境建模 ──
        context_graph = self._update_context(content, session_id)

        # ── L4: 異常偵測 ──
        anomalies = self._detect_anomalies(signals)

        # ── L5: 預測層 ──
        predicted_paths = self._predict_paths(
            context_graph, anomalies, heuristic_matches
        )

        # ── 聚合報告 ──
        overall_level = self._compute_overall_level(anomalies)
        summary = self._build_summary(
            signals, heuristic_matches, anomalies, predicted_paths
        )

        report = IntuitionReport(
            timestamp=now,
            session_id=session_id,
            signals=signals,
            heuristic_matches=heuristic_matches,
            context_graph=context_graph,
            anomalies=anomalies,
            predicted_paths=predicted_paths,
            overall_alert_level=overall_level,
            summary=summary,
        )

        # ── 持久化信號日誌 ──
        self.store.append_signals(signals)

        # ── 持久化情境圖 ──
        if context_graph:
            self.store.save_context(context_graph)

        logger.info(
            f"直覺感知完成 | session={session_id} | "
            f"信號={len(signals)} | 異常={len(anomalies)} | "
            f"級別={overall_level.value}"
        )

        return report

    # ═══════════════════════════════════════
    # L1: 信號擷取
    # ═══════════════════════════════════════

    def _collect_signals(
        self,
        content: str,
        user_history: Dict[str, Any],
    ) -> List[Signal]:
        """L1 信號擷取 — 從互動中收集原始信號.

        收集四種信號：
        1. sentence_length_deviation: 句長偏差
        2. confidence_shift: 確信度轉變
        3. response_delay: 回應延遲
        4. pattern_break: 行為模式中斷

        Args:
            content: 使用者訊息文字
            user_history: 使用者歷史基線資料

        Returns:
            信號列表（0-4 個）
        """
        now = datetime.now().isoformat()
        signals: List[Signal] = []

        # ── 1. 句長偏差 ──
        sig = self._detect_sentence_length_deviation(content, user_history, now)
        if sig is not None:
            signals.append(sig)

        # ── 2. 確信度轉變 ──
        sig = self._detect_confidence_shift(content, user_history, now)
        if sig is not None:
            signals.append(sig)

        # ── 3. 回應延遲 ──
        sig = self._detect_response_delay(user_history, now)
        if sig is not None:
            signals.append(sig)

        # ── 4. 行為模式中斷 ──
        sig = self._detect_pattern_break(content, user_history, now)
        if sig is not None:
            signals.append(sig)

        return signals

    def _detect_sentence_length_deviation(
        self,
        content: str,
        user_history: Dict[str, Any],
        timestamp: str,
    ) -> Optional[Signal]:
        """偵測句長偏差.

        將當前訊息的詞數與使用者歷史平均比較。

        Args:
            content: 使用者訊息
            user_history: 歷史基線
            timestamp: 時間戳

        Returns:
            Signal 或 None（無有效基線時）
        """
        baseline_avg = user_history.get("avg_sentence_length", 0.0)
        if baseline_avg <= 0:
            return None

        # 計算當前訊息詞數（中文以字元數估算，英文以空格分詞）
        current_length = self._estimate_word_count(content)
        if current_length <= 0:
            return None

        deviation = abs(current_length - baseline_avg) / baseline_avg

        return Signal(
            signal_type=SignalType.SENTENCE_LENGTH_DEVIATION,
            raw_value=current_length,
            baseline=baseline_avg,
            deviation=round(deviation, 4),
            timestamp=timestamp,
        )

    def _detect_confidence_shift(
        self,
        content: str,
        user_history: Dict[str, Any],
        timestamp: str,
    ) -> Optional[Signal]:
        """偵測確信度轉變 — 透過語言標記分析.

        分析方式：
        - 猶豫詞（或許、可能、大概、也許、不確定）降低信心
        - 問號增加不確定性
        - 斷言詞（一定、確定、必須、絕對）增加信心

        Args:
            content: 使用者訊息
            user_history: 歷史基線
            timestamp: 時間戳

        Returns:
            Signal 或 None
        """
        baseline_confidence = user_history.get("avg_confidence_index", 0.0)
        if baseline_confidence <= 0:
            return None

        current_confidence = self._calculate_confidence_index(content)

        deviation = abs(current_confidence - baseline_confidence) / max(
            baseline_confidence, 0.01
        )

        return Signal(
            signal_type=SignalType.CONFIDENCE_SHIFT,
            raw_value=round(current_confidence, 4),
            baseline=baseline_confidence,
            deviation=round(deviation, 4),
            timestamp=timestamp,
        )

    def _detect_response_delay(
        self,
        user_history: Dict[str, Any],
        timestamp: str,
    ) -> Optional[Signal]:
        """偵測回應延遲 — 上次訊息到本次訊息的時間間隔.

        Args:
            user_history: 歷史基線（需包含 last_message_time、avg_response_delay_seconds）
            timestamp: 時間戳

        Returns:
            Signal 或 None
        """
        avg_delay = user_history.get("avg_response_delay_seconds", 0.0)
        last_time_str = user_history.get("last_message_time")
        if avg_delay <= 0 or not last_time_str:
            return None

        try:
            last_time = datetime.fromisoformat(last_time_str)
            current_delay = (datetime.now() - last_time).total_seconds()
        except (ValueError, TypeError):
            return None

        if current_delay <= 0:
            return None

        deviation = abs(current_delay - avg_delay) / max(avg_delay, 1.0)

        return Signal(
            signal_type=SignalType.RESPONSE_DELAY,
            raw_value=round(current_delay, 2),
            baseline=avg_delay,
            deviation=round(deviation, 4),
            timestamp=timestamp,
        )

    def _detect_pattern_break(
        self,
        content: str,
        user_history: Dict[str, Any],
        timestamp: str,
    ) -> Optional[Signal]:
        """偵測行為模式中斷 — 脫離使用者常態.

        分析維度：
        - 使用者通常的互動深度（追問 vs 簡短回應）
        - 話題轉換頻率
        - 表情符號使用變化

        Args:
            content: 使用者訊息
            user_history: 歷史基線
            timestamp: 時間戳

        Returns:
            Signal 或 None
        """
        # 使用者通常的互動模式基線
        typical_depth = user_history.get("typical_interaction_depth", 0.0)
        typical_question_ratio = user_history.get("typical_question_ratio", 0.0)

        if typical_depth <= 0 and typical_question_ratio <= 0:
            return None

        # 計算當前互動深度指標
        current_depth = self._calculate_interaction_depth(content)
        current_question_ratio = content.count("?") + content.count("？")

        # 綜合偏差：深度偏差 + 追問頻率偏差
        depth_dev = 0.0
        question_dev = 0.0

        if typical_depth > 0:
            depth_dev = abs(current_depth - typical_depth) / max(typical_depth, 0.01)
        if typical_question_ratio > 0 and current_question_ratio >= 0:
            question_dev = abs(
                current_question_ratio - typical_question_ratio
            ) / max(typical_question_ratio, 0.01)

        combined_deviation = (depth_dev + question_dev) / 2.0

        # 只有偏差超過一定閾值才產生信號
        if combined_deviation < 0.05:
            return None

        return Signal(
            signal_type=SignalType.PATTERN_BREAK,
            raw_value=round(current_depth, 4),
            baseline=typical_depth,
            deviation=round(combined_deviation, 4),
            timestamp=timestamp,
        )

    # ═══════════════════════════════════════
    # L2: 啟發式匹配
    # ═══════════════════════════════════════

    def _apply_heuristics(
        self,
        signals: List[Signal],
    ) -> List[HeuristicMatch]:
        """L2 啟發式匹配 — 用 IF-THEN 規則快速判斷.

        掃描所有信號，比對啟發式庫中的規則。
        匹配不需經過完整推理（System 1 快速匹配）。

        Args:
            signals: L1 產出的信號列表

        Returns:
            匹配結果列表
        """
        matches: List[HeuristicMatch] = []

        if not self._heuristics or not signals:
            return matches

        for rule in self._heuristics:
            # 檢查規則條件是否被當前信號滿足
            matched_signals = self._check_rule_condition(rule, signals)
            if matched_signals:
                # 匹配信心度 = 規則信心度 * RI 分數
                match_confidence = rule.confidence * rule.ri_score
                matches.append(
                    HeuristicMatch(
                        rule=rule,
                        matched_signals=matched_signals,
                        match_confidence=round(match_confidence, 4),
                    )
                )

        # 按信心度排序
        matches.sort(key=lambda m: m.match_confidence, reverse=True)
        return matches

    def _check_rule_condition(
        self,
        rule: HeuristicRule,
        signals: List[Signal],
    ) -> List[Signal]:
        """檢查規則條件是否被信號滿足.

        使用簡單的關鍵字匹配：如果規則條件中提到某信號類型，
        且該信號的偏差超過閾值，視為匹配。

        Args:
            rule: 啟發式規則
            signals: 當前信號列表

        Returns:
            匹配到的信號列表（空列表表示不匹配）
        """
        matched: List[Signal] = []
        condition_lower = rule.condition.lower()

        for signal in signals:
            signal_name = signal.signal_type.value.lower()
            # 如果條件文字中包含信號類型名稱（或其關鍵詞），視為相關
            if (signal_name in condition_lower
                    or self._signal_type_alias_match(signal.signal_type, condition_lower)):
                # 偏差超過 10% 才算有效匹配
                if signal.deviation >= 0.1:
                    matched.append(signal)

        return matched

    @staticmethod
    def _signal_type_alias_match(
        signal_type: SignalType,
        condition: str,
    ) -> bool:
        """檢查信號類型的別名是否出現在條件中.

        Args:
            signal_type: 信號類型
            condition: 規則條件文字（已轉小寫）

        Returns:
            是否匹配
        """
        aliases = {
            SignalType.SENTENCE_LENGTH_DEVIATION: [
                "sentence_length", "句長", "能量", "energy",
            ],
            SignalType.CONFIDENCE_SHIFT: [
                "confidence", "確信", "信心", "猶豫",
            ],
            SignalType.RESPONSE_DELAY: [
                "delay", "延遲", "回應時間", "沉默",
            ],
            SignalType.PATTERN_BREAK: [
                "pattern", "模式", "行為", "常態",
            ],
        }
        for alias in aliases.get(signal_type, []):
            if alias in condition:
                return True
        return False

    # ═══════════════════════════════════════
    # L3: 情境建模
    # ═══════════════════════════════════════

    def _update_context(
        self,
        content: str,
        session_id: str,
    ) -> ContextGraph:
        """L3 情境建模 — 建構或增量更新情境圖.

        從對話中提取場域要素（實體、主題、情緒、意圖），
        以圖結構儲存，跨輪次持續更新。

        Args:
            content: 使用者訊息
            session_id: 會話 ID

        Returns:
            更新後的情境圖
        """
        # 從快取或磁碟載入既有圖
        graph = self._context_cache.get(session_id)
        if graph is None:
            graph = self.store.load_context(session_id)
        if graph is None:
            graph = ContextGraph(session_id=session_id)

        # 提取並增量更新節點
        self._extract_and_add_nodes(content, graph)

        # 更新快取
        self._context_cache[session_id] = graph

        return graph

    def _extract_and_add_nodes(
        self,
        content: str,
        graph: ContextGraph,
    ) -> None:
        """從訊息中提取場域要素，加入情境圖.

        簡化的實體/情緒提取邏輯（不依賴外部 NLP 模型）。
        未來可替換為 LLM-based extraction。

        Args:
            content: 使用者訊息
            graph: 要更新的情境圖
        """
        now = datetime.now().isoformat()

        # ── 情緒偵測（簡化版）──
        emotion = self._detect_emotion_label(content)
        if emotion:
            node_id = f"emotion_{emotion}"
            graph.add_node(
                ContextNode(
                    node_id=node_id,
                    node_type="emotion",
                    label=emotion,
                    properties={"detected_at": now, "source": "text_analysis"},
                )
            )

        # ── 意圖偵測（簡化版）──
        intention = self._detect_intention_label(content)
        if intention:
            node_id = f"intention_{intention}"
            graph.add_node(
                ContextNode(
                    node_id=node_id,
                    node_type="intention",
                    label=intention,
                    properties={"detected_at": now},
                )
            )

        # ── 主題偵測 ──
        # 若訊息足夠長，提取一個主題節點
        if len(content) > 10:
            # 使用前 20 字元（抽象化）作為主題標記
            topic_label = f"turn_{len(graph.nodes)}"
            topic_id = f"topic_{topic_label}"
            graph.add_node(
                ContextNode(
                    node_id=topic_id,
                    node_type="topic",
                    label=topic_label,
                    properties={
                        "content_length": len(content),
                        "detected_at": now,
                    },
                )
            )

        # ── 更新圖的元資料 ──
        turn_count = graph.metadata.get("turn_count", 0) + 1
        graph.metadata["turn_count"] = turn_count
        graph.metadata["last_content_length"] = len(content)
        graph.last_updated = now

    # ═══════════════════════════════════════
    # L4: 異常偵測
    # ═══════════════════════════════════════

    def _detect_anomalies(
        self,
        signals: List[Signal],
    ) -> List[AnomalyResult]:
        """L4 異常偵測 — 計算偏差分數並分類.

        四級分類（嚴格閾值）：
        - neutral: 偏差 < 10%
        - notable: 10% <= 偏差 < 30%
        - significant: 30% <= 偏差 < 60%
        - emergency: 偏差 >= 60%

        也包含「缺席偵測」：預期出現但未出現的信號。

        Args:
            signals: L1 產出的信號列表

        Returns:
            異常偵測結果列表
        """
        anomalies: List[AnomalyResult] = []

        for signal in signals:
            deviation_pct = signal.deviation * 100.0  # 轉為百分比
            level = self._classify_anomaly_level(deviation_pct)

            description = (
                f"{signal.signal_type.value}: "
                f"偏差 {deviation_pct:.1f}% (原始值={signal.raw_value}, 基線={signal.baseline})"
            )

            anomalies.append(
                AnomalyResult(
                    signal=signal,
                    deviation_pct=round(deviation_pct, 2),
                    level=level,
                    description=description,
                    is_absence=False,
                )
            )

        # ── 缺席偵測 ──
        absence_anomalies = self._detect_absence_anomalies(signals)
        anomalies.extend(absence_anomalies)

        return anomalies

    @staticmethod
    def _classify_anomaly_level(deviation_pct: float) -> AnomalyLevel:
        """依偏差百分比分類異常級別.

        閾值嚴格定義：
        - < 10%: neutral
        - 10% ~ 30%: notable
        - 30% ~ 60%: significant
        - >= 60%: emergency

        Args:
            deviation_pct: 偏差百分比 (0-100+)

        Returns:
            AnomalyLevel
        """
        if deviation_pct < _NEUTRAL_THRESHOLD:
            return AnomalyLevel.NEUTRAL
        elif deviation_pct < _NOTABLE_THRESHOLD:
            return AnomalyLevel.NOTABLE
        elif deviation_pct < _SIGNIFICANT_THRESHOLD:
            return AnomalyLevel.SIGNIFICANT
        else:
            return AnomalyLevel.EMERGENCY

    def _detect_absence_anomalies(
        self,
        signals: List[Signal],
    ) -> List[AnomalyResult]:
        """缺席偵測 — 預期出現但未出現的信號.

        檢查啟發式庫中是否有規則預期某種信號出現，
        但在本次互動中完全缺失。

        Args:
            signals: 本次收集到的信號

        Returns:
            缺席型異常列表
        """
        absences: List[AnomalyResult] = []
        present_types = {s.signal_type for s in signals}

        for rule in self._heuristics:
            condition_lower = rule.condition.lower()
            # 檢查規則是否預期某種信號出現
            for signal_type in SignalType:
                if signal_type in present_types:
                    continue  # 已經出現，不算缺席
                if self._signal_type_alias_match(signal_type, condition_lower):
                    # 規則預期此信號但未出現 — 記錄為缺席偵測
                    now = datetime.now().isoformat()
                    absent_signal = Signal(
                        signal_type=signal_type,
                        raw_value=0.0,
                        baseline=0.0,
                        deviation=0.0,
                        timestamp=now,
                    )
                    absences.append(
                        AnomalyResult(
                            signal=absent_signal,
                            deviation_pct=0.0,
                            level=AnomalyLevel.NOTABLE,
                            description=f"缺席偵測: 預期 {signal_type.value} 信號未出現",
                            is_absence=True,
                        )
                    )
                    break  # 每種缺席信號只記錄一次

        return absences

    # ═══════════════════════════════════════
    # L5: 預測層
    # ═══════════════════════════════════════

    def _predict_paths(
        self,
        context: ContextGraph,
        anomalies: List[AnomalyResult],
        heuristic_matches: List[HeuristicMatch],
    ) -> List[PredictedPath]:
        """L5 預測層 — 生成 3-5 條可能的對話發展路徑.

        結合情境圖、異常偵測和啟發式匹配結果，
        推演對話的多種可能走向。
        所有路徑機率合計約 100%。

        Args:
            context: L3 情境圖
            anomalies: L4 異常偵測結果
            heuristic_matches: L2 啟發式匹配結果

        Returns:
            預測路徑列表（3-5 條）
        """
        paths: List[PredictedPath] = []

        # ── 基於異常產生路徑 ──
        significant_anomalies = [
            a for a in anomalies
            if a.level in (AnomalyLevel.SIGNIFICANT, AnomalyLevel.EMERGENCY)
            and not a.is_absence
        ]

        # ── 基於啟發式匹配產生路徑 ──
        if heuristic_matches:
            for i, match in enumerate(heuristic_matches[:2]):
                paths.append(
                    PredictedPath(
                        path_id=f"heuristic_{i+1}",
                        description=match.rule.prediction,
                        probability=0.0,  # 稍後正規化
                        recommended_action=self._derive_action_from_prediction(
                            match.rule.prediction
                        ),
                        confidence=match.match_confidence,
                    )
                )

        # ── 基於異常產生路徑 ──
        if significant_anomalies:
            anomaly_desc = "、".join(
                a.signal.signal_type.value for a in significant_anomalies[:2]
            )
            paths.append(
                PredictedPath(
                    path_id="anomaly_response",
                    description=f"使用者行為出現顯著偏差（{anomaly_desc}），可能需要情緒承接",
                    probability=0.0,
                    recommended_action="啟動 resonance 情緒承接技能，縮短回覆，提高溫暖度",
                    confidence=0.6,
                )
            )

        # ── 預設路徑：正常對話延續 ──
        paths.append(
            PredictedPath(
                path_id="default_continue",
                description="對話按既有方向正常延續",
                probability=0.0,
                recommended_action="維持當前回應策略",
                confidence=0.7,
            )
        )

        # ── 預設路徑：話題轉換 ──
        paths.append(
            PredictedPath(
                path_id="topic_shift",
                description="使用者可能轉換話題或結束當前討論",
                probability=0.0,
                recommended_action="準備收尾摘要，保持開放性",
                confidence=0.5,
            )
        )

        # 確保路徑數量在 3-5 之間
        if len(paths) < _MIN_PATHS:
            paths.append(
                PredictedPath(
                    path_id="exploration",
                    description="使用者可能想深入探索當前主題",
                    probability=0.0,
                    recommended_action="準備延伸資料與深度分析",
                    confidence=0.4,
                )
            )

        paths = paths[:_MAX_PATHS]

        # ── 正規化機率（合計約 100%）──
        self._normalize_probabilities(paths, significant_anomalies)

        return paths

    def _normalize_probabilities(
        self,
        paths: List[PredictedPath],
        significant_anomalies: List[AnomalyResult],
    ) -> None:
        """正規化路徑機率使合計約 100%.

        基於信心度與異常情況分配機率。

        Args:
            paths: 路徑列表（會原地修改）
            significant_anomalies: 顯著異常列表
        """
        if not paths:
            return

        # 以信心度為基礎權重
        raw_weights = [max(p.confidence, 0.1) for p in paths]

        # 如果有顯著異常，提高異常相關路徑的權重
        if significant_anomalies:
            for i, path in enumerate(paths):
                if "anomaly" in path.path_id or "偏差" in path.description:
                    raw_weights[i] *= 1.5

        total_weight = sum(raw_weights)
        if total_weight <= 0:
            # 均分
            equal_prob = round(100.0 / len(paths), 1)
            for p in paths:
                p.probability = equal_prob
            return

        for i, path in enumerate(paths):
            path.probability = round((raw_weights[i] / total_weight) * 100.0, 1)

        # 微調確保合計精確到 100%
        diff = 100.0 - sum(p.probability for p in paths)
        if paths:
            paths[0].probability = round(paths[0].probability + diff, 1)

    @staticmethod
    def _derive_action_from_prediction(prediction: str) -> str:
        """從預測描述推導建議行動.

        Args:
            prediction: 規則預測文字

        Returns:
            建議行動
        """
        # 簡化版：根據關鍵字產生建議
        prediction_lower = prediction.lower()
        if any(kw in prediction_lower for kw in ["frustrated", "挫折", "沮喪", "困擾"]):
            return "啟動情緒承接模式，先用 1-3 句接住情緒再進行分析"
        elif any(kw in prediction_lower for kw in ["competitor", "競爭", "方案"]):
            return "提供差異化分析與具體案例支持"
        elif any(kw in prediction_lower for kw in ["budget", "預算", "成本"]):
            return "準備簡潔的成本效益摘要"
        elif any(kw in prediction_lower for kw in ["lost interest", "失去興趣"]):
            return "主動跟進，直接確認意向"
        else:
            return "依據預測調整回應策略，保持觀察"

    # ═══════════════════════════════════════
    # 聚合與摘要
    # ═══════════════════════════════════════

    def _compute_overall_level(
        self,
        anomalies: List[AnomalyResult],
    ) -> AnomalyLevel:
        """計算整體警報級別 — 取所有異常中的最高級別.

        Args:
            anomalies: 異常列表

        Returns:
            最高級別
        """
        if not anomalies:
            return AnomalyLevel.NEUTRAL

        level_priority = {
            AnomalyLevel.NEUTRAL: 0,
            AnomalyLevel.NOTABLE: 1,
            AnomalyLevel.SIGNIFICANT: 2,
            AnomalyLevel.EMERGENCY: 3,
        }

        max_level = AnomalyLevel.NEUTRAL
        for anomaly in anomalies:
            if level_priority.get(anomaly.level, 0) > level_priority.get(max_level, 0):
                max_level = anomaly.level

        return max_level

    @staticmethod
    def _build_summary(
        signals: List[Signal],
        matches: List[HeuristicMatch],
        anomalies: List[AnomalyResult],
        paths: List[PredictedPath],
    ) -> str:
        """建構直覺報告摘要.

        Args:
            signals: 信號列表
            matches: 啟發式匹配
            anomalies: 異常列表
            paths: 預測路徑

        Returns:
            摘要文字
        """
        parts: List[str] = []

        # 信號摘要
        if signals:
            sig_types = ", ".join(s.signal_type.value for s in signals)
            parts.append(f"偵測到 {len(signals)} 個信號: {sig_types}")

        # 異常摘要
        non_neutral = [
            a for a in anomalies
            if a.level != AnomalyLevel.NEUTRAL and not a.is_absence
        ]
        if non_neutral:
            levels = ", ".join(f"{a.level.value}({a.deviation_pct:.0f}%)" for a in non_neutral)
            parts.append(f"異常: {levels}")

        # 啟發式匹配
        if matches:
            predictions = ", ".join(m.rule.prediction[:30] for m in matches[:2])
            parts.append(f"啟發式判斷: {predictions}")

        # 最高機率路徑
        if paths:
            top = max(paths, key=lambda p: p.probability)
            parts.append(
                f"最可能路徑: {top.description[:40]}... ({top.probability:.0f}%)"
            )

        return " | ".join(parts) if parts else "無顯著直覺信號"

    # ═══════════════════════════════════════
    # 心跳與維護
    # ═══════════════════════════════════════

    def refresh_heuristics(self) -> int:
        """心跳週期刷新啟發式庫 — 從 knowledge-lattice 同步新結晶.

        在每個心跳週期（60 分鐘）由 Brain 或 Heartbeat 呼叫。
        重新載入啟發式規則，過濾 RI < 0.2 的規則。

        Returns:
            刷新後的規則數量
        """
        # 重新載入
        rules = self.store.load_heuristics()

        # 品質過濾：只保留 RI >= 0.2
        self._heuristics = [r for r in rules if r.ri_score >= _MIN_RI_SCORE]

        logger.info(
            f"啟發式庫刷新完成 | "
            f"載入: {len(rules)} 條 | "
            f"有效 (RI >= {_MIN_RI_SCORE}): {len(self._heuristics)} 條"
        )

        return len(self._heuristics)

    async def nightly_maintenance(self) -> Dict[str, Any]:
        """夜間維護 — 清理過期日誌、整合啟發式規則.

        由 NightlyJob 在 00:00 呼叫。
        - 清理超過 30 天的信號日誌
        - 整合啟發式規則（清除 RI < 0.2 或過期規則）
        - 生成直覺引擎健康報告

        Returns:
            維護報告
        """
        report: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "tasks": {},
        }

        # ── 1. 清理過期信號日誌 ──
        try:
            pruned = self.store.prune_signal_log(
                retention_days=_SIGNAL_LOG_RETENTION_DAYS
            )
            report["tasks"]["signal_log_prune"] = {
                "status": "completed",
                "records_pruned": pruned,
            }
        except Exception as e:
            logger.error(f"信號日誌清理失敗: {e}")
            report["tasks"]["signal_log_prune"] = {
                "status": "failed",
                "error": str(e),
            }

        # ── 2. 整合啟發式規則 ──
        try:
            rules = self.store.load_heuristics()
            consolidated = self.store.consolidate_heuristics(rules)
            self.store.save_heuristics(consolidated)
            self._heuristics = consolidated

            report["tasks"]["heuristic_consolidation"] = {
                "status": "completed",
                "before": len(rules),
                "after": len(consolidated),
                "removed": len(rules) - len(consolidated),
            }
        except Exception as e:
            logger.error(f"啟發式整合失敗: {e}")
            report["tasks"]["heuristic_consolidation"] = {
                "status": "failed",
                "error": str(e),
            }

        # ── 3. 健康報告 ──
        report["health"] = {
            "heuristic_count": len(self._heuristics),
            "context_cache_sessions": len(self._context_cache),
            "signal_log_exists": self.store.signal_log_path.exists(),
        }

        logger.info(f"直覺引擎夜間維護完成 | {report}")
        return report

    # ═══════════════════════════════════════
    # 工具方法
    # ═══════════════════════════════════════

    @staticmethod
    def _estimate_word_count(text: str) -> float:
        """估算文字詞數.

        中文以字元數（不含空白與標點）估算，
        英文以空格分詞。

        Args:
            text: 輸入文字

        Returns:
            估算詞數
        """
        if not text:
            return 0.0

        # 分離中文字元與英文詞
        import re
        # 中文字元數
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        # 英文詞數（移除中文後以空格分詞）
        english_text = re.sub(r"[\u4e00-\u9fff]", " ", text)
        english_words = len([w for w in english_text.split() if w.strip()])

        return float(chinese_chars + english_words)

    @staticmethod
    def _calculate_confidence_index(text: str) -> float:
        """計算文字的確信度指數 (0.0 - 1.0).

        分析方式：
        - 猶豫詞降低分數
        - 問號增加不確定性
        - 斷言詞提高分數

        Args:
            text: 使用者訊息

        Returns:
            確信度指數
        """
        if not text:
            return 0.5  # 預設中性

        score = 0.5  # 基礎分數

        # 猶豫詞（降低確信度）
        hedge_words = [
            "或許", "可能", "大概", "也許", "不確定", "不太確定",
            "應該", "好像", "似乎", "maybe", "perhaps", "probably",
            "not sure", "might", "could be",
        ]
        for word in hedge_words:
            if word in text.lower():
                score -= 0.08

        # 問號（降低確信度）
        question_count = text.count("?") + text.count("？")
        score -= question_count * 0.05

        # 斷言詞（提高確信度）
        assert_words = [
            "一定", "確定", "必須", "絕對", "肯定", "當然",
            "definitely", "certainly", "absolutely", "must", "sure",
        ]
        for word in assert_words:
            if word in text.lower():
                score += 0.08

        # 限制在 0.0 - 1.0 之間
        return max(0.0, min(1.0, score))

    @staticmethod
    def _calculate_interaction_depth(text: str) -> float:
        """計算互動深度指標.

        考量因素：
        - 文字長度
        - 問號數量（追問傾向）
        - 列表結構（結構化思考）

        Args:
            text: 使用者訊息

        Returns:
            深度指標 (0.0+)
        """
        if not text:
            return 0.0

        length_factor = min(len(text) / 200.0, 3.0)
        question_factor = (text.count("?") + text.count("？")) * 0.3
        # 簡易列表偵測
        list_factor = (text.count("\n-") + text.count("\n*") + text.count("\n1.")) * 0.2

        return round(length_factor + question_factor + list_factor, 4)

    @staticmethod
    def _detect_emotion_label(text: str) -> Optional[str]:
        """簡易情緒偵測.

        Args:
            text: 使用者訊息

        Returns:
            情緒標籤或 None
        """
        text_lower = text.lower()

        # 負面情緒指標
        negative_markers = {
            "焦慮": ["焦慮", "擔心", "緊張", "anxiety", "worried"],
            "挫折": ["挫折", "沮喪", "frustrat", "無奈"],
            "憤怒": ["生氣", "憤怒", "angry", "太扯"],
            "疲憊": ["累", "疲", "好煩", "tired", "exhausted"],
        }
        for emotion, markers in negative_markers.items():
            for marker in markers:
                if marker in text_lower:
                    return emotion

        # 正面情緒指標
        positive_markers = {
            "興奮": ["太棒", "超讚", "excited", "amazing", "太好了"],
            "感謝": ["謝謝", "感謝", "thanks", "grateful"],
            "滿意": ["滿意", "不錯", "good", "satisfied"],
        }
        for emotion, markers in positive_markers.items():
            for marker in markers:
                if marker in text_lower:
                    return emotion

        return None

    @staticmethod
    def _detect_intention_label(text: str) -> Optional[str]:
        """簡易意圖偵測.

        Args:
            text: 使用者訊息

        Returns:
            意圖標籤或 None
        """
        text_lower = text.lower()

        intention_markers = {
            "求助": ["幫我", "怎麼辦", "help", "怎麼做"],
            "決策": ["該不該", "選哪個", "比較", "要不要", "decide"],
            "資訊查詢": ["是什麼", "什麼是", "what is", "為什麼", "why"],
            "任務委派": ["幫我做", "請處理", "安排", "執行", "run", "do this"],
            "閒聊": ["哈哈", "lol", "嘻嘻", "呵呵"],
        }
        for intention, markers in intention_markers.items():
            for marker in markers:
                if marker in text_lower:
                    return intention

        return None
