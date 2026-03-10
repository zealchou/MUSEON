"""Perception Engine — 望聞問切四診合參的系統察覺引擎

望（觀察指標）：直接讀取 Governor 健康快照、服務狀態、資源使用
聞（聆聽模式）：訂閱 EventBus，被動蒐集近期事件流
問（查詢自評）：主動詢問各子系統（Doctor、HeartbeatFocus、AnimaTracker）
切（脈診合參）：綜合所有訊號，產出結構化的 DiagnosticReport

設計原則：
- 不重複造輪子 — 消費既有的 Doctor、Pulse、EventBus 信號
- 零 LLM — 純邏輯判斷，快速可靠
- 時間序列感知 — 不只看當下，也看趨勢

中焦（服務級）→ 上焦（系統級）的感知橋樑。

Milestone #001 — 2026-03-03
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── 症狀分類 ───


class SymptomCategory(Enum):
    """症狀類別 — 對應治理的不同面向"""

    PROCESS = "process"        # 進程級（下焦）
    SERVICE = "service"        # 服務級（中焦）
    COMMUNICATION = "comm"     # 通訊（Telegram 等）
    RESOURCE = "resource"      # 資源（記憶體、磁碟等）
    EVOLUTION = "evolution"    # 演化狀態（ANIMA、WEE 等）
    RHYTHM = "rhythm"          # 節律（心跳、焦點等）


class SymptomSeverity(Enum):
    """症狀嚴重度"""

    INFO = "info"          # 純資訊，無需處理
    MILD = "mild"          # 輕微偏離，持續觀察
    MODERATE = "moderate"  # 中度偏離，建議調節
    SEVERE = "severe"      # 嚴重偏離，需要介入
    CRITICAL = "critical"  # 危急，觸發警覺信號


@dataclass
class Symptom:
    """單一症狀（知覺信號偏離參考信號的具體表現）"""

    name: str                          # 症狀名稱（機器可讀）
    category: SymptomCategory          # 分類
    severity: SymptomSeverity          # 嚴重度
    message: str                       # 人類可讀描述
    source: str                        # 信號來源（望/聞/問/切）
    metric_value: Optional[float] = None  # 實際值（可選）
    reference_value: Optional[float] = None  # 參考值（可選）
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def error_magnitude(self) -> float:
        """PCT 誤差量：知覺信號 − 參考信號"""
        if self.metric_value is not None and self.reference_value is not None:
            return abs(self.metric_value - self.reference_value)
        # 根據嚴重度估算
        severity_map = {
            SymptomSeverity.INFO: 0.0,
            SymptomSeverity.MILD: 0.2,
            SymptomSeverity.MODERATE: 0.5,
            SymptomSeverity.SEVERE: 0.8,
            SymptomSeverity.CRITICAL: 1.0,
        }
        return severity_map.get(self.severity, 0.5)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        d["error_magnitude"] = self.error_magnitude
        return d


@dataclass
class DiagnosticReport:
    """四診合參後的系統診斷報告"""

    timestamp: float
    symptoms: List[Symptom]
    diagnosis_duration_ms: float
    event_counts: Dict[str, int] = field(default_factory=dict)
    raw_signals: Dict[str, Any] = field(default_factory=dict)
    prescriptions: List["Prescription"] = field(default_factory=list)

    @property
    def symptom_count(self) -> int:
        return len(self.symptoms)

    @property
    def critical_count(self) -> int:
        return sum(
            1 for s in self.symptoms
            if s.severity == SymptomSeverity.CRITICAL
        )

    @property
    def severe_count(self) -> int:
        return sum(
            1 for s in self.symptoms
            if s.severity == SymptomSeverity.SEVERE
        )

    @property
    def max_severity(self) -> SymptomSeverity:
        if not self.symptoms:
            return SymptomSeverity.INFO
        return max(self.symptoms, key=lambda s: list(SymptomSeverity).index(s.severity)).severity

    @property
    def is_healthy(self) -> bool:
        """沒有 moderate 以上的症狀"""
        return all(
            s.severity in (SymptomSeverity.INFO, SymptomSeverity.MILD)
            for s in self.symptoms
        )

    @property
    def has_prescriptions(self) -> bool:
        """是否有處方建議"""
        return len(self.prescriptions) > 0

    @property
    def auto_prescriptions(self) -> List["Prescription"]:
        """可自動執行的處方列表"""
        return [p for p in self.prescriptions if p.auto_executable]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "symptom_count": self.symptom_count,
            "critical_count": self.critical_count,
            "severe_count": self.severe_count,
            "max_severity": self.max_severity.value,
            "is_healthy": self.is_healthy,
            "has_prescriptions": self.has_prescriptions,
            "diagnosis_duration_ms": round(self.diagnosis_duration_ms, 1),
            "symptoms": [s.to_dict() for s in self.symptoms],
            "prescriptions": [p.to_dict() for p in self.prescriptions],
            "event_counts": self.event_counts,
        }


# ─── 處方系統 ───


@dataclass
class Prescription:
    """診斷後的處方 — 建議的修復行動."""

    name: str                           # 處方名稱（機器可讀）
    action_type: str                    # 行動類型: "restart" | "alert" | "tune" | "escalate" | "observe"
    description: str                    # 人類可讀描述
    target: str                         # 目標子系統
    priority: int                       # 優先級 (1=最高, 5=最低)
    auto_executable: bool               # 是否可自動執行
    triggered_by: List[str]             # 觸發此處方的症狀名稱列表
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "action_type": self.action_type,
            "description": self.description,
            "target": self.target,
            "priority": self.priority,
            "auto_executable": self.auto_executable,
            "triggered_by": self.triggered_by,
            "metadata": self.metadata,
        }


class PrescriptionEngine:
    """處方引擎 — 根據症狀組合生成修復處方.

    處方規則矩陣（不是 if-else，而是結構化的規則）：
    - 單一症狀 → 對應處方
    - 症狀組合 → 複合處方
    - 嚴重度升級 → 處方升級
    """

    # 規則矩陣：症狀 → 處方映射
    RULES: List[Dict[str, Any]] = [
        # ── 單一症狀規則 ──
        {
            "symptoms": ["gateway_lock_lost"],
            "prescription": "restart_gateway",
            "action": "restart",
            "description": "Gateway lock 遺失，需重啟 Gateway 恢復進程唯一性",
            "target": "gateway",
            "auto": True,
            "priority": 1,
        },
        {
            "symptoms": ["telegram_offline"],
            "prescription": "restart_telegram",
            "action": "restart",
            "description": "Telegram 離線，需重啟通訊模組",
            "target": "telegram",
            "auto": True,
            "priority": 1,
        },
        {
            "symptoms": ["high_error_rate"],
            "prescription": "reduce_load",
            "action": "tune",
            "description": "錯誤率過高，降低系統負載以恢復穩定",
            "target": "system",
            "auto": True,
            "priority": 2,
        },
        {
            "symptoms": ["anima_imbalance"],
            "prescription": "balance_training",
            "action": "observe",
            "description": "ANIMA 元素失衡，建議調整訓練策略以平衡弱勢元素",
            "target": "anima",
            "auto": False,
            "priority": 4,
        },
        {
            "symptoms": ["systemic_degradation"],
            "prescription": "emergency_triage",
            "action": "escalate",
            "description": "系統性退化，啟動緊急分診流程，需人類介入",
            "target": "system",
            "auto": False,
            "priority": 1,
        },
        {
            "symptoms": ["high_memory"],
            "prescription": "memory_cleanup",
            "action": "restart",
            "description": "記憶體使用偏高，清理快取或重啟高記憶體服務",
            "target": "resource",
            "auto": True,
            "priority": 2,
        },
        {
            "symptoms": ["service_qdrant_unhealthy"],
            "prescription": "restart_qdrant",
            "action": "restart",
            "description": "Qdrant 服務不健康，需重啟向量資料庫",
            "target": "qdrant",
            "auto": True,
            "priority": 1,
        },
        {
            "symptoms": ["no_interactions"],
            "prescription": "proactive_check_in",
            "action": "alert",
            "description": "長時間無使用者互動，主動發送問候訊息",
            "target": "telegram",
            "auto": True,
            "priority": 5,
        },
        # ── 症狀組合規則（複合處方）──
        {
            "symptoms": ["telegram_offline", "high_error_rate"],
            "prescription": "comm_crisis_protocol",
            "action": "escalate",
            "description": "通訊中斷合併高錯誤率，啟動通訊危機處理協議",
            "target": "system",
            "auto": False,
            "priority": 1,
        },
    ]

    def prescribe(self, report: DiagnosticReport) -> List[Prescription]:
        """根據診斷報告中的症狀組合生成處方列表.

        匹配邏輯：
        1. 收集報告中所有症狀名稱
        2. 對每條規則檢查其所需症狀是否全部出現
        3. 生成對應處方
        4. 去重（同名處方保留優先級最高的）
        5. 按優先級排序返回
        """
        symptom_names = {s.name for s in report.symptoms}
        matched: List[Prescription] = []

        for rule in self.RULES:
            required = set(rule["symptoms"])
            if required.issubset(symptom_names):
                matched.append(Prescription(
                    name=rule["prescription"],
                    action_type=rule["action"],
                    description=rule["description"],
                    target=rule["target"],
                    priority=rule["priority"],
                    auto_executable=rule["auto"],
                    triggered_by=rule["symptoms"],
                ))

        # 去重：同名處方保留優先級最高（數字最小）的
        seen: Dict[str, Prescription] = {}
        for p in matched:
            if p.name not in seen or p.priority < seen[p.name].priority:
                seen[p.name] = p
        deduplicated = list(seen.values())

        # 按優先級排序（1=最高，數字越小越前）
        deduplicated.sort(key=lambda p: p.priority)
        return deduplicated

    def get_auto_prescriptions(
        self, prescriptions: List[Prescription]
    ) -> List[Prescription]:
        """篩選可自動執行的處方.

        Returns:
            按優先級排序的可自動執行處方列表。
        """
        auto = [p for p in prescriptions if p.auto_executable]
        auto.sort(key=lambda p: p.priority)
        return auto


# ─── 事件收集器（聞）───


class EventCollector:
    """被動蒐集 EventBus 事件流，供「聞」診使用。

    維護一個滑動窗口，記錄最近 N 分鐘的事件統計。
    不儲存事件內容，只統計頻率和模式。
    """

    def __init__(self, window_minutes: float = 30.0):
        self.window_minutes = window_minutes
        self._events: List[Dict[str, Any]] = []
        self._max_events = 1000

    def record(self, event_type: str, data: Optional[Dict] = None) -> None:
        """記錄一個事件。"""
        self._events.append({
            "type": event_type,
            "timestamp": time.time(),
            "severity": (data or {}).get("severity", "info"),
        })
        # 保持窗口大小
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]

    def get_counts(self) -> Dict[str, int]:
        """取得窗口內的事件計數。"""
        cutoff = time.time() - self.window_minutes * 60
        counts: Dict[str, int] = {}
        for evt in self._events:
            if evt["timestamp"] > cutoff:
                t = evt["type"]
                counts[t] = counts.get(t, 0) + 1
        return counts

    def get_error_rate(self, minutes: float = 5.0) -> float:
        """取得最近 N 分鐘的錯誤率（每分鐘錯誤數）。"""
        cutoff = time.time() - minutes * 60
        error_count = sum(
            1 for evt in self._events
            if evt["timestamp"] > cutoff
            and evt.get("severity") in ("error", "critical", "warning")
        )
        return error_count / max(minutes, 0.1)

    def clear_old(self) -> None:
        """清理窗口外的舊事件。"""
        cutoff = time.time() - self.window_minutes * 60
        self._events = [e for e in self._events if e["timestamp"] > cutoff]


# ─── 察覺引擎主體 ───


class PerceptionEngine:
    """望聞問切 — 四診合參的系統察覺引擎。

    整合來源：
    - Governor 健康快照 (get_health)
    - ServiceHealthMonitor 服務狀態
    - TelegramPollingGuard 統計
    - Doctor 自我診斷
    - Pulse 心跳狀態
    - EventBus 事件流

    使用方式：
        perception = PerceptionEngine(governor=gov)
        perception.connect_event_bus(event_bus)  # 開始聆聽
        report = await perception.perceive()     # 執行四診
    """

    def __init__(
        self,
        governor: Any = None,
        data_dir: Optional[str] = None,
        event_window_minutes: float = 30.0,
    ):
        self._governor = governor
        self._data_dir = Path(data_dir) if data_dir else None
        self._event_collector = EventCollector(
            window_minutes=event_window_minutes
        )
        self._prescription_engine = PrescriptionEngine()
        self._connected_to_bus = False

    def connect_event_bus(self, event_bus: Any) -> None:
        """連接 EventBus，開始被動聆聽事件流。"""
        if self._connected_to_bus:
            return

        # 訂閱關鍵事件
        event_types = [
            "SELF_DIAGNOSIS_COMPLETED",
            "PULSE_MICRO_BEAT",
            "EVOLUTION_HEARTBEAT",
            "BRAIN_RESPONSE_COMPLETE",
            "AUTONOMOUS_TASK_DONE",
            "MORPHENIX_EXECUTION_COMPLETED",
        ]

        for evt_name in event_types:
            evt_const = getattr(event_bus, evt_name, None) or evt_name

            def _make_handler(name):
                def _handler(data):
                    self._event_collector.record(name, data)
                return _handler

            try:
                event_bus.subscribe(evt_const, _make_handler(evt_name))
            except Exception:
                pass

        self._connected_to_bus = True
        logger.debug("PerceptionEngine connected to EventBus")

    async def perceive(self) -> DiagnosticReport:
        """執行一次完整的四診合參。

        望（觀察指標）→ 聞（聆聽模式）→ 問（查詢自評）→ 切（脈診合參）
        """
        start = time.monotonic()
        symptoms: List[Symptom] = []
        raw_signals: Dict[str, Any] = {}

        # ═══ 望（Observe）：觀察系統指標 ═══
        wang_symptoms, wang_signals = self._wang()
        symptoms.extend(wang_symptoms)
        raw_signals["wang"] = wang_signals

        # ═══ 聞（Listen）：聆聽近期事件模式 ═══
        wen_symptoms, wen_signals = self._wen()
        symptoms.extend(wen_symptoms)
        raw_signals["wen"] = wen_signals

        # ═══ 問（Inquire）：查詢子系統自評 ═══
        wen2_symptoms, wen2_signals = await self._wen2()
        symptoms.extend(wen2_symptoms)
        raw_signals["wen2"] = wen2_signals

        # ═══ 切（Diagnose）：脈診合參 ═══
        qie_symptoms = self._qie(symptoms)
        symptoms.extend(qie_symptoms)

        elapsed_ms = (time.monotonic() - start) * 1000

        report = DiagnosticReport(
            timestamp=time.time(),
            symptoms=symptoms,
            diagnosis_duration_ms=elapsed_ms,
            event_counts=self._event_collector.get_counts(),
            raw_signals=raw_signals,
        )

        # ═══ 處方生成：根據症狀開立處方 ═══
        prescriptions = self._prescription_engine.prescribe(report)
        report.prescriptions = prescriptions

        if prescriptions:
            auto_rx = self._prescription_engine.get_auto_prescriptions(
                prescriptions
            )
            logger.info(
                f"Prescriptions generated: {len(prescriptions)} total, "
                f"{len(auto_rx)} auto-executable"
            )
            for rx in prescriptions:
                logger.debug(
                    f"  Rx[{rx.priority}] {rx.name} ({rx.action_type}) "
                    f"-> {rx.target} | auto={rx.auto_executable}"
                )

        logger.debug(
            f"Perception complete: {report.symptom_count} symptoms, "
            f"{len(report.prescriptions)} prescriptions, "
            f"max_severity={report.max_severity.value}, "
            f"{elapsed_ms:.1f}ms"
        )
        return report

    # ─── 望：觀察指標 ───

    def _wang(self) -> tuple[List[Symptom], Dict]:
        """望診 — 直接觀察系統可量測的指標。

        不做主動探測，只讀取已有的狀態數據。
        像中醫看氣色、舌苔、面部表情。
        """
        symptoms: List[Symptom] = []
        signals: Dict[str, Any] = {}

        if not self._governor:
            return symptoms, signals

        try:
            health = self._governor.get_health()
            signals["governor_health"] = health

            # Gateway Lock 狀態
            gw = health.get("gateway", {})
            if not gw.get("locked"):
                symptoms.append(Symptom(
                    name="gateway_lock_lost",
                    category=SymptomCategory.PROCESS,
                    severity=SymptomSeverity.CRITICAL,
                    message="Gateway lock 遺失 — 進程唯一性無法保證",
                    source="望",
                ))

            # 整體健康
            overall = health.get("health", "unknown")
            if overall == "emergency":
                symptoms.append(Symptom(
                    name="system_emergency",
                    category=SymptomCategory.PROCESS,
                    severity=SymptomSeverity.CRITICAL,
                    message="系統健康為 EMERGENCY 狀態",
                    source="望",
                ))
            elif overall == "critical":
                symptoms.append(Symptom(
                    name="system_critical",
                    category=SymptomCategory.SERVICE,
                    severity=SymptomSeverity.SEVERE,
                    message="系統健康為 CRITICAL 狀態",
                    source="望",
                ))
            elif overall == "degraded":
                symptoms.append(Symptom(
                    name="system_degraded",
                    category=SymptomCategory.SERVICE,
                    severity=SymptomSeverity.MODERATE,
                    message="系統健康為 DEGRADED 狀態",
                    source="望",
                ))

            # Telegram 狀態
            tg = health.get("telegram", {})
            if tg.get("running") is False:
                symptoms.append(Symptom(
                    name="telegram_offline",
                    category=SymptomCategory.COMMUNICATION,
                    severity=SymptomSeverity.SEVERE,
                    message="Telegram 離線 — 無法接收使用者訊息",
                    source="望",
                ))
            tg_errors = tg.get("consecutive_errors", 0)
            if tg_errors >= 3:
                symptoms.append(Symptom(
                    name="telegram_unstable",
                    category=SymptomCategory.COMMUNICATION,
                    severity=SymptomSeverity.MODERATE,
                    message=f"Telegram 連續 {tg_errors} 次錯誤",
                    source="望",
                    metric_value=float(tg_errors),
                    reference_value=0.0,
                ))
            tg_conflicts = tg.get("conflict_count", 0)
            if tg_conflicts > 0:
                symptoms.append(Symptom(
                    name="telegram_conflicts",
                    category=SymptomCategory.COMMUNICATION,
                    severity=SymptomSeverity.MILD,
                    message=f"Telegram 發生 {tg_conflicts} 次 409 衝突",
                    source="望",
                    metric_value=float(tg_conflicts),
                    reference_value=0.0,
                ))

            # 服務狀態
            svcs = health.get("services", {})
            svc_detail = svcs.get("services", {})
            for svc_name, svc_info in svc_detail.items():
                svc_status = svc_info.get("status", "unknown")
                if svc_status == "unhealthy":
                    sev = (
                        SymptomSeverity.SEVERE
                        if svc_info.get("required")
                        else SymptomSeverity.MODERATE
                    )
                    symptoms.append(Symptom(
                        name=f"service_{svc_name}_unhealthy",
                        category=SymptomCategory.SERVICE,
                        severity=sev,
                        message=f"服務 {svc_name} 不健康: {svc_info.get('last_error', '?')}",
                        source="望",
                        metadata={"service": svc_name, "restarts": svc_info.get("total_restarts", 0)},
                    ))
                elif svc_status == "degraded":
                    resp_ms = svc_info.get("last_response_ms", 0)
                    symptoms.append(Symptom(
                        name=f"service_{svc_name}_slow",
                        category=SymptomCategory.SERVICE,
                        severity=SymptomSeverity.MILD,
                        message=f"服務 {svc_name} 回應緩慢 ({resp_ms:.0f}ms)",
                        source="望",
                        metric_value=resp_ms,
                    ))

            # Uptime
            uptime_s = gw.get("uptime_s", 0)
            signals["uptime_s"] = uptime_s

        except Exception as e:
            logger.debug(f"望診異常: {e}")
            symptoms.append(Symptom(
                name="wang_error",
                category=SymptomCategory.PROCESS,
                severity=SymptomSeverity.MILD,
                message=f"望診無法取得完整指標: {e}",
                source="望",
            ))

        # 記憶體使用
        try:
            import resource
            rusage = resource.getrusage(resource.RUSAGE_SELF)
            memory_mb = rusage.ru_maxrss / (1024 * 1024)  # macOS: bytes
            signals["memory_mb"] = memory_mb
            if memory_mb > 2000:  # > 2 GB（64 GB 機器的合理閾值）
                symptoms.append(Symptom(
                    name="high_memory",
                    category=SymptomCategory.RESOURCE,
                    severity=SymptomSeverity.MODERATE if memory_mb > 4000 else SymptomSeverity.MILD,
                    message=f"記憶體使用偏高: {memory_mb:.0f} MB",
                    source="望",
                    metric_value=memory_mb,
                    reference_value=2000.0,
                ))
        except Exception:
            pass

        return symptoms, signals

    # ─── 聞：聆聽事件模式 ───

    def _wen(self) -> tuple[List[Symptom], Dict]:
        """聞診 — 分析近期事件流的模式。

        不主動探測，而是聽取已發生的事件。
        像中醫聽呼吸、咳嗽、語聲。
        """
        symptoms: List[Symptom] = []
        counts = self._event_collector.get_counts()
        error_rate = self._event_collector.get_error_rate(minutes=5.0)
        signals = {"event_counts": counts, "error_rate_5min": error_rate}

        # 錯誤率過高
        if error_rate > 2.0:  # > 2 errors/min
            symptoms.append(Symptom(
                name="high_error_rate",
                category=SymptomCategory.PROCESS,
                severity=SymptomSeverity.MODERATE if error_rate > 5.0 else SymptomSeverity.MILD,
                message=f"近 5 分鐘錯誤率偏高: {error_rate:.1f}/min",
                source="聞",
                metric_value=error_rate,
                reference_value=0.5,
            ))

        # 微脈異常（最近應該有微脈事件）
        micro_beat_count = counts.get("PULSE_MICRO_BEAT", 0)
        signals["micro_beat_count"] = micro_beat_count

        # 自診斷事件
        diag_count = counts.get("SELF_DIAGNOSIS_COMPLETED", 0)
        signals["diagnosis_count"] = diag_count

        # 進化心跳
        evo_count = counts.get("EVOLUTION_HEARTBEAT", 0)
        signals["evolution_heartbeat_count"] = evo_count

        return symptoms, signals

    # ─── 問：查詢子系統自評 ───

    async def _wen2(self) -> tuple[List[Symptom], Dict]:
        """問診 — 主動查詢各子系統的自我評估。

        不同於望（被動觀察）和聞（被動聆聽），
        問診主動向子系統「詢問」它們的狀態。
        像中醫詢問患者的主觀感受。
        """
        symptoms: List[Symptom] = []
        signals: Dict[str, Any] = {}

        # HeartbeatFocus 自評
        try:
            if self._data_dir:
                from museon.pulse.heartbeat_focus import HeartbeatFocus
                focus_path = str(self._data_dir / "pulse" / "heartbeat_focus.json")
                focus = HeartbeatFocus(state_path=focus_path)
                signals["focus_level"] = focus.focus_level
                signals["interaction_count"] = focus.interaction_count
                signals["beat_count"] = focus.beat_count

                # 焦點過低可能表示系統長時間沒有互動
                if focus.focus_level == "low" and focus.interaction_count == 0:
                    symptoms.append(Symptom(
                        name="no_interactions",
                        category=SymptomCategory.RHYTHM,
                        severity=SymptomSeverity.INFO,
                        message="近 6 小時沒有使用者互動",
                        source="問",
                        metric_value=0.0,
                        reference_value=3.0,
                    ))
        except Exception as e:
            logger.debug(f"問診 HeartbeatFocus 失敗: {e}")

        # ANIMA 八元素自評
        try:
            if self._data_dir:
                anima_path = self._data_dir / "ANIMA_MC.json"
                if anima_path.exists():
                    import json
                    anima_data = json.loads(anima_path.read_text("utf-8"))
                    absolute = anima_data.get("absolute", {})
                    total = sum(absolute.values())
                    signals["anima_total"] = total
                    signals["anima_absolute"] = absolute

                    # 檢測元素失衡
                    if absolute:
                        max_val = max(absolute.values())
                        min_val = min(absolute.values())
                        if max_val > 0 and min_val / max(max_val, 1) < 0.1:
                            weak_elements = [
                                k for k, v in absolute.items()
                                if v < max_val * 0.1
                            ]
                            if weak_elements:
                                symptoms.append(Symptom(
                                    name="anima_imbalance",
                                    category=SymptomCategory.EVOLUTION,
                                    severity=SymptomSeverity.INFO,
                                    message=f"ANIMA 元素失衡: {', '.join(weak_elements)} 偏弱",
                                    source="問",
                                    metadata={"weak_elements": weak_elements},
                                ))
        except Exception as e:
            logger.debug(f"問診 ANIMA 失敗: {e}")

        return symptoms, signals

    # ─── 切：脈診合參 ───

    def _qie(self, existing_symptoms: List[Symptom]) -> List[Symptom]:
        """切診 — 綜合所有信號的交叉分析。

        不是收集新信號，而是分析望聞問三診的信號組合。
        像中醫的脈診 — 綜合判斷，尋找信號之間的關聯。
        """
        symptoms: List[Symptom] = []

        # 多重症狀組合偵測
        categories = {}
        for s in existing_symptoms:
            cat = s.category.value
            categories[cat] = categories.get(cat, 0) + 1

        # 多面向同時出問題 → 系統性問題
        problem_categories = {
            k: v for k, v in categories.items()
            if k not in ("rhythm", "evolution")  # 排除非核心類別
        }
        if len(problem_categories) >= 3:
            symptoms.append(Symptom(
                name="systemic_degradation",
                category=SymptomCategory.PROCESS,
                severity=SymptomSeverity.SEVERE,
                message=f"系統性退化：{len(problem_categories)} 個面向同時異常 ({', '.join(problem_categories.keys())})",
                source="切",
                metadata={"affected_categories": problem_categories},
            ))

        # 通訊 + 服務同時異常 → 可能是基礎設施問題
        has_comm_issue = any(
            s.category == SymptomCategory.COMMUNICATION
            and s.severity.value in ("moderate", "severe", "critical")
            for s in existing_symptoms
        )
        has_service_issue = any(
            s.category == SymptomCategory.SERVICE
            and s.severity.value in ("moderate", "severe", "critical")
            for s in existing_symptoms
        )
        if has_comm_issue and has_service_issue:
            symptoms.append(Symptom(
                name="infrastructure_stress",
                category=SymptomCategory.PROCESS,
                severity=SymptomSeverity.MODERATE,
                message="通訊與服務同時異常 — 可能是基礎設施層問題（網路/Docker/主機）",
                source="切",
            ))

        # 高記憶體 + 服務緩慢 → 資源競爭
        has_memory_issue = any(
            s.name == "high_memory" for s in existing_symptoms
        )
        has_slow_service = any(
            s.name.endswith("_slow") for s in existing_symptoms
        )
        if has_memory_issue and has_slow_service:
            symptoms.append(Symptom(
                name="resource_contention",
                category=SymptomCategory.RESOURCE,
                severity=SymptomSeverity.MODERATE,
                message="記憶體偏高 + 服務緩慢 — 可能存在資源競爭",
                source="切",
            ))

        return symptoms
