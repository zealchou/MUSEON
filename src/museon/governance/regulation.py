"""Regulation Engine — PCT 驅動的調節引擎

核心原理（Perceptual Control Theory）：
  參考信號 (reference) − 知覺信號 (perception) = 誤差信號 (error)
  誤差信號 → 驅動修正行為 (corrective action)

調節模式：
1. 比例修正 — 修正力度與誤差成正比
2. 冷卻抑制 — 避免過度修正（振盪）
3. 適應性閾值 — 異穩態 (allostasis)：根據持續狀態調整參考信號

約束式而非規則式：
  定義「什麼不可接受」（邊界），不定義「該怎麼做」（行為）。
  系統在邊界內自由運作，只在越界時介入。

治未病：
  趨勢惡化偵測 — 在問題真正發生前預警。
  不是修復問題，而是預防問題。

Milestone #001 — 2026-03-03
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .perception import (
    DiagnosticReport,
    Symptom,
    SymptomCategory,
    SymptomSeverity,
)

logger = logging.getLogger(__name__)


# ─── 修正行動 ───


class ActionType(Enum):
    """修正行動的類型"""

    OBSERVE = "observe"      # 僅觀察，不行動
    LOG = "log"              # 記錄到日誌
    ALERT = "alert"          # 發出警報
    RESTART = "restart"      # 重啟服務
    THROTTLE = "throttle"    # 降速/限流
    ESCALATE = "escalate"    # 升級到更高層級（人工介入）
    ADAPT = "adapt"          # 調整參考信號（異穩態）


class ActionPriority(Enum):
    """行動優先級"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


@dataclass
class CorrectionAction:
    """一個修正行動"""

    action_type: ActionType
    priority: ActionPriority
    target: str               # 修正目標（服務名、元件名）
    description: str           # 人類可讀描述
    symptom_name: str          # 觸發此行動的症狀
    cooldown_key: str = ""     # 冷卻鍵（同一 key 有冷卻期）
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "priority": self.priority.value,
            "target": self.target,
            "description": self.description,
            "symptom_name": self.symptom_name,
            "cooldown_key": self.cooldown_key,
            "metadata": self.metadata,
        }


@dataclass
class RegulationResult:
    """一次調節的結果"""

    timestamp: float
    actions: List[CorrectionAction]
    suppressed: List[str]       # 被冷卻抑制的行動
    adapted: List[str]          # 被調整的參考信號

    @property
    def action_count(self) -> int:
        return len(self.actions)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "action_count": self.action_count,
            "actions": [a.to_dict() for a in self.actions],
            "suppressed": self.suppressed,
            "adapted": self.adapted,
        }


# ─── 參考信號（期望狀態）───


@dataclass
class ReferenceSignal:
    """一個參考信號 — PCT 的核心概念。

    定義「什麼是正常」，當知覺信號偏離時產生誤差。
    異穩態特性：reference_value 可以根據持續狀態動態調整。
    """

    name: str
    category: SymptomCategory
    reference_value: float          # 期望值
    tolerance: float = 0.0         # 容許偏差範圍
    min_severity_to_act: SymptomSeverity = SymptomSeverity.MODERATE

    # 異穩態調整
    adaptive: bool = False          # 是否允許自適應
    adaptation_rate: float = 0.1    # 自適應速率（0-1）
    adaptation_min: float = 0.0     # 最小允許值
    adaptation_max: float = float("inf")  # 最大允許值


# ─── 預設參考信號 ───


DEFAULT_REFERENCES = [
    ReferenceSignal(
        name="gateway_lock",
        category=SymptomCategory.PROCESS,
        reference_value=1.0,  # 1 = locked
        tolerance=0.0,        # 不容許偏差
        min_severity_to_act=SymptomSeverity.CRITICAL,
    ),
    ReferenceSignal(
        name="telegram_errors",
        category=SymptomCategory.COMMUNICATION,
        reference_value=0.0,  # 0 errors
        tolerance=2.0,        # 容許 2 次連續錯誤
        min_severity_to_act=SymptomSeverity.MODERATE,
        adaptive=True,
        adaptation_rate=0.05,
        adaptation_max=5.0,
    ),
    ReferenceSignal(
        name="service_response_ms",
        category=SymptomCategory.SERVICE,
        reference_value=500.0,  # 500ms
        tolerance=1000.0,       # 容許到 1500ms
        min_severity_to_act=SymptomSeverity.MILD,
        adaptive=True,
        adaptation_rate=0.1,
        adaptation_min=200.0,
        adaptation_max=5000.0,
    ),
    ReferenceSignal(
        name="memory_mb",
        category=SymptomCategory.RESOURCE,
        reference_value=300.0,  # 300 MB
        tolerance=200.0,        # 容許到 500 MB
        min_severity_to_act=SymptomSeverity.MODERATE,
        adaptive=True,
        adaptation_rate=0.05,
        adaptation_min=100.0,
        adaptation_max=1000.0,
    ),
    ReferenceSignal(
        name="error_rate",
        category=SymptomCategory.PROCESS,
        reference_value=0.5,   # 0.5 errors/min
        tolerance=1.0,         # 容許到 1.5/min
        min_severity_to_act=SymptomSeverity.MODERATE,
    ),
]


# ─── 調節引擎主體 ───


class RegulationEngine:
    """PCT 驅動的調節引擎。

    根據 PerceptionEngine 的診斷報告，計算修正行動。

    使用方式：
        regulation = RegulationEngine()
        result = regulation.regulate(diagnostic_report)
        for action in result.actions:
            execute(action)
    """

    def __init__(
        self,
        references: Optional[List[ReferenceSignal]] = None,
        cooldown_s: float = 120.0,  # 2 分鐘冷卻
        on_action: Optional[Callable[[CorrectionAction], None]] = None,
    ):
        self._references = {
            r.name: r for r in (references or DEFAULT_REFERENCES)
        }
        self._cooldown_s = cooldown_s
        self._on_action = on_action

        # 冷卻追蹤
        self._cooldown_map: Dict[str, float] = {}

        # 歷史趨勢（治未病用）
        self._severity_history: List[Dict] = []
        self._max_history = 100

    def regulate(self, report: DiagnosticReport) -> RegulationResult:
        """根據診斷報告計算修正行動。

        流程：
        1. 對每個症狀計算誤差信號
        2. 選擇對應的修正行動
        3. 套用冷卻抑制（避免振盪）
        4. 檢測趨勢惡化（治未病）
        5. 異穩態調整（自適應參考信號）
        """
        actions: List[CorrectionAction] = []
        suppressed: List[str] = []
        adapted: List[str] = []

        # 記錄趨勢
        self._record_trend(report)

        for symptom in report.symptoms:
            # 計算修正行動
            action = self._compute_action(symptom)
            if action is None:
                continue

            # 冷卻檢查
            cooldown_key = action.cooldown_key or f"{action.target}:{action.action_type.value}"
            if self._is_cooling_down(cooldown_key):
                suppressed.append(
                    f"{cooldown_key} (cooldown until "
                    f"{self._cooldown_map.get(cooldown_key, 0):.0f})"
                )
                continue

            # 記錄冷卻
            self._cooldown_map[cooldown_key] = time.time() + self._cooldown_s
            actions.append(action)

            # 通知
            if self._on_action:
                try:
                    self._on_action(action)
                except Exception as e:
                    logger.debug(f"Action callback error: {e}")

        # 治未病：趨勢惡化偵測
        trend_actions = self._check_trend_degradation()
        actions.extend(trend_actions)

        # 異穩態：自適應參考信號調整
        adapted = self._adapt_references(report)

        result = RegulationResult(
            timestamp=time.time(),
            actions=actions,
            suppressed=suppressed,
            adapted=adapted,
        )

        if actions:
            logger.info(
                f"Regulation: {len(actions)} actions, "
                f"{len(suppressed)} suppressed, "
                f"{len(adapted)} adapted"
            )

        return result

    # ─── 誤差計算 + 行動選擇 ───

    def _compute_action(self, symptom: Symptom) -> Optional[CorrectionAction]:
        """根據症狀計算修正行動。

        比例原則：修正力度與誤差成正比。
        """
        severity = symptom.severity

        # INFO 和 MILD 不需要行動
        if severity in (SymptomSeverity.INFO, SymptomSeverity.MILD):
            return None

        # 根據嚴重度和類別選擇行動
        if severity == SymptomSeverity.CRITICAL:
            return CorrectionAction(
                action_type=ActionType.ESCALATE,
                priority=ActionPriority.URGENT,
                target=symptom.category.value,
                description=f"🚨 {symptom.message}",
                symptom_name=symptom.name,
                cooldown_key=f"escalate:{symptom.name}",
            )

        if severity == SymptomSeverity.SEVERE:
            # 服務不健康 → 嘗試重啟
            if symptom.category == SymptomCategory.SERVICE:
                svc_name = symptom.metadata.get("service", "unknown")
                return CorrectionAction(
                    action_type=ActionType.RESTART,
                    priority=ActionPriority.HIGH,
                    target=svc_name,
                    description=f"重啟服務 {svc_name}: {symptom.message}",
                    symptom_name=symptom.name,
                    cooldown_key=f"restart:{svc_name}",
                )

            # 通訊離線 → 升級
            if symptom.category == SymptomCategory.COMMUNICATION:
                return CorrectionAction(
                    action_type=ActionType.ALERT,
                    priority=ActionPriority.HIGH,
                    target="telegram",
                    description=f"⚠️ {symptom.message}",
                    symptom_name=symptom.name,
                    cooldown_key=f"alert:telegram",
                )

            # 其他嚴重症狀 → 警報
            return CorrectionAction(
                action_type=ActionType.ALERT,
                priority=ActionPriority.HIGH,
                target=symptom.category.value,
                description=f"⚠️ {symptom.message}",
                symptom_name=symptom.name,
            )

        # MODERATE → 記錄 + 觀察
        return CorrectionAction(
            action_type=ActionType.LOG,
            priority=ActionPriority.MEDIUM,
            target=symptom.category.value,
            description=symptom.message,
            symptom_name=symptom.name,
        )

    # ─── 冷卻機制 ───

    def _is_cooling_down(self, key: str) -> bool:
        """檢查某個行動是否在冷卻期內。"""
        expiry = self._cooldown_map.get(key)
        if expiry is None:
            return False
        if time.time() > expiry:
            del self._cooldown_map[key]
            return False
        return True

    def cleanup_cooldowns(self) -> None:
        """清理過期的冷卻記錄。"""
        now = time.time()
        expired = [k for k, v in self._cooldown_map.items() if now > v]
        for k in expired:
            del self._cooldown_map[k]

    # ─── 治未病：趨勢惡化偵測 ───

    def _record_trend(self, report: DiagnosticReport) -> None:
        """記錄診斷趨勢。"""
        self._severity_history.append({
            "timestamp": report.timestamp,
            "max_severity": report.max_severity.value,
            "symptom_count": report.symptom_count,
            "critical_count": report.critical_count,
            "severe_count": report.severe_count,
        })
        if len(self._severity_history) > self._max_history:
            self._severity_history = self._severity_history[-self._max_history:]

    def _check_trend_degradation(self) -> List[CorrectionAction]:
        """治未病 — 偵測趨勢惡化。

        不是看當下嚴不嚴重，而是看「是否越來越糟」。
        連續 3 次症狀數上升 → 趨勢惡化預警。
        """
        actions: List[CorrectionAction] = []

        if len(self._severity_history) < 3:
            return actions

        recent_3 = self._severity_history[-3:]
        counts = [h["symptom_count"] for h in recent_3]

        # 連續上升
        if counts[0] < counts[1] < counts[2] and counts[2] > 3:
            if not self._is_cooling_down("trend:degradation"):
                actions.append(CorrectionAction(
                    action_type=ActionType.ALERT,
                    priority=ActionPriority.MEDIUM,
                    target="system",
                    description=(
                        f"治未病預警：症狀數連續上升 "
                        f"({counts[0]}→{counts[1]}→{counts[2]})"
                    ),
                    symptom_name="trend_degradation",
                    cooldown_key="trend:degradation",
                ))
                self._cooldown_map["trend:degradation"] = (
                    time.time() + 600  # 10 分鐘冷卻
                )

        # 連續出現嚴重症狀
        severe_counts = [h["severe_count"] + h["critical_count"] for h in recent_3]
        if all(c > 0 for c in severe_counts):
            if not self._is_cooling_down("trend:persistent_severe"):
                actions.append(CorrectionAction(
                    action_type=ActionType.ESCALATE,
                    priority=ActionPriority.HIGH,
                    target="system",
                    description=(
                        f"治未病警告：連續 3 次診斷均有嚴重症狀 — "
                        f"可能存在未被自動修復的深層問題"
                    ),
                    symptom_name="persistent_severe",
                    cooldown_key="trend:persistent_severe",
                ))
                self._cooldown_map["trend:persistent_severe"] = (
                    time.time() + 1800  # 30 分鐘冷卻
                )

        return actions

    # ─── 異穩態：自適應參考信號 ───

    def _adapt_references(self, report: DiagnosticReport) -> List[str]:
        """異穩態調整 — 根據持續狀態動態調整參考信號。

        不是簡單地恢復到固定基準，而是讓系統適應新常態。
        例如：如果服務回應時間持續偏高但穩定，放寬閾值。
        如果系統持續健康，收緊閾值（提高標準）。
        """
        adapted: List[str] = []

        for symptom in report.symptoms:
            if symptom.metric_value is None or symptom.reference_value is None:
                continue

            # 尋找對應的參考信號
            ref = self._find_matching_reference(symptom)
            if ref is None or not ref.adaptive:
                continue

            actual = symptom.metric_value
            reference = ref.reference_value

            # 如果實際值持續高於參考值，緩慢上調
            if actual > reference + ref.tolerance:
                new_ref = reference + (actual - reference) * ref.adaptation_rate
                new_ref = min(new_ref, ref.adaptation_max)
                if new_ref != reference:
                    ref.reference_value = new_ref
                    adapted.append(
                        f"{ref.name}: {reference:.1f} → {new_ref:.1f} "
                        f"(actual={actual:.1f})"
                    )

        # 如果報告健康，緩慢收緊標準
        if report.is_healthy and len(self._severity_history) >= 5:
            recent_5 = self._severity_history[-5:]
            if all(h["max_severity"] in ("info", "mild") for h in recent_5):
                for ref in self._references.values():
                    if ref.adaptive and ref.tolerance > 0:
                        old_tol = ref.tolerance
                        ref.tolerance = max(
                            ref.tolerance * 0.95,  # 收緊 5%
                            ref.tolerance * 0.5,   # 不低於原始的一半
                        )
                        if ref.tolerance != old_tol:
                            adapted.append(
                                f"{ref.name} tolerance: {old_tol:.1f} → "
                                f"{ref.tolerance:.1f} (healthy streak)"
                            )

        return adapted

    def _find_matching_reference(self, symptom: Symptom) -> Optional[ReferenceSignal]:
        """尋找症狀對應的參考信號。"""
        # 精確匹配
        if symptom.name in self._references:
            return self._references[symptom.name]

        # 類別匹配
        for ref in self._references.values():
            if ref.category == symptom.category:
                return ref

        return None

    # ─── 外部存取 ───

    def get_references(self) -> Dict[str, dict]:
        """取得所有參考信號的當前值。"""
        return {
            name: {
                "reference_value": ref.reference_value,
                "tolerance": ref.tolerance,
                "category": ref.category.value,
                "adaptive": ref.adaptive,
            }
            for name, ref in self._references.items()
        }

    def get_status(self) -> dict:
        """取得調節引擎狀態。"""
        return {
            "references": self.get_references(),
            "active_cooldowns": len(self._cooldown_map),
            "trend_points": len(self._severity_history),
        }
