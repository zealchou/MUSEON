"""Immunity Engine — 先天免疫 + 後天免疫記憶

免疫系統的兩層防禦：

1. 先天免疫 (Innate Immunity)
   - 硬編碼的防禦規則，不需要學習
   - 快速回應，但缺乏針對性
   - 例：Gateway Lock 丟失 → 立即重啟、服務崩潰 → docker restart

2. 後天免疫 (Adaptive Immunity)
   - 從過去的事件中學習
   - 建立「抗體」：問題模式 → 解決方案
   - 免疫記憶持久化到磁碟
   - 例：Telegram 409 衝突 → 學到「先清 webhook 再啟動」

免疫記憶的生命週期：
  事件發生 → 辨識模式 → 匹配已知抗體 → 執行/記錄
                ↓ (未知)
        記錄為新事件 → 人工/自動解決 → 建立新抗體

設計原則：
- 免疫不等於完美防禦 — 它是學習型的
- 先天免疫是「約束」，後天免疫是「經驗」
- 抗體有衰退機制 — 長久不用的防禦會減弱（但不會消失）

Milestone #001 — 2026-03-03
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .perception import Symptom, SymptomCategory, SymptomSeverity

logger = logging.getLogger(__name__)


# ─── 免疫記錄 ───


@dataclass
class Incident:
    """一次事件記錄 — 系統遇到的問題實例"""

    incident_id: str           # 唯一 ID
    timestamp: float
    symptom_name: str          # 觸發症狀
    category: str              # 症狀類別
    severity: str              # 症狀嚴重度
    description: str           # 事件描述
    resolution: str = ""       # 解決方式
    resolved: bool = False     # 是否已解決
    resolved_at: float = 0.0   # 解決時間
    auto_resolved: bool = False  # 是否自動解決
    resolution_duration_s: float = 0.0  # 解決耗時

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Incident":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Antibody:
    """抗體 — 學習到的防禦模式

    pattern: 症狀的辨識模式（症狀名稱前綴匹配）
    response: 建議的修正行動
    confidence: 信心度（0-1），隨成功/失敗動態調整
    """

    antibody_id: str
    pattern: str               # 匹配模式（症狀名稱前綴）
    category: str              # 症狀類別
    response_type: str         # 建議行動類型
    response_target: str       # 行動目標
    response_description: str  # 行動描述
    confidence: float = 0.5    # 信心度 (0-1)
    success_count: int = 0     # 成功次數
    failure_count: int = 0     # 失敗次數
    created_at: float = 0.0
    last_used_at: float = 0.0
    decay_rate: float = 0.01   # 每次未使用的衰退率

    @property
    def total_uses(self) -> int:
        return self.success_count + self.failure_count

    @property
    def success_rate(self) -> float:
        if self.total_uses == 0:
            return 0.5  # 初始假設
        return self.success_count / self.total_uses

    def reinforce(self, success: bool) -> None:
        """強化或弱化抗體。"""
        if success:
            self.success_count += 1
            self.confidence = min(1.0, self.confidence + 0.1)
        else:
            self.failure_count += 1
            self.confidence = max(0.1, self.confidence - 0.15)
        self.last_used_at = time.time()

    def decay(self) -> None:
        """時間衰退 — 長久不用的抗體信心度降低。"""
        days_since_use = (time.time() - self.last_used_at) / 86400
        if days_since_use > 7:  # 7 天沒用過才衰退
            decay = self.decay_rate * (days_since_use - 7)
            self.confidence = max(0.1, self.confidence - decay)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_uses"] = self.total_uses
        d["success_rate"] = round(self.success_rate, 2)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Antibody":
        # 排除衍生屬性
        valid_fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in valid_fields})


@dataclass
class ImmuneResponse:
    """免疫反應 — 匹配到的防禦"""

    antibody_id: str
    antibody_type: str         # "innate" or "adaptive"
    response_type: str
    response_target: str
    response_description: str
    confidence: float
    symptom_name: str

    def to_dict(self) -> dict:
        return asdict(self)


# ─── 先天免疫規則 ───


INNATE_RULES: List[Dict[str, Any]] = [
    {
        "pattern": "gateway_lock_lost",
        "response_type": "escalate",
        "response_target": "gateway",
        "response_description": "Gateway Lock 遺失 — 系統唯一性無法保證，需要立即介入",
    },
    {
        "pattern": "system_emergency",
        "response_type": "escalate",
        "response_target": "system",
        "response_description": "系統緊急狀態 — 觸發警覺信號",
    },
    {
        "pattern": "telegram_offline",
        "response_type": "alert",
        "response_target": "telegram",
        "response_description": "Telegram 離線 — 使用者無法通訊",
    },
    {
        "pattern": "service_qdrant_unhealthy",
        "response_type": "restart",
        "response_target": "qdrant",
        "response_description": "Qdrant 不健康 — 記憶檢索功能受損",
    },
    {
        "pattern": "service_searxng_unhealthy",
        "response_type": "restart",
        "response_target": "searxng",
        "response_description": "SearXNG 不健康 — 搜尋功能受損",
    },
    {
        "pattern": "systemic_degradation",
        "response_type": "escalate",
        "response_target": "system",
        "response_description": "多面向系統性退化 — 可能是基礎設施級問題",
    },
]


# ─── 免疫引擎主體 ───


class ImmunityEngine:
    """免疫引擎 — 先天免疫 + 後天免疫記憶。

    使用方式：
        immunity = ImmunityEngine(memory_path="~/.museon/immunity.json")
        immunity.load()  # 載入免疫記憶

        # 對症狀檢查是否有已知防禦
        response = immunity.check(symptom)
        if response:
            execute(response)
            immunity.reinforce(response.antibody_id, success=True)

        # 記錄新事件
        incident = immunity.record_incident(symptom, resolution="auto_restarted")

        # 從解決的事件中學習
        immunity.learn(incident)
        immunity.save()  # 持久化
    """

    def __init__(self, memory_path: Optional[str] = None):
        if memory_path:
            self._memory_path = Path(memory_path)
        else:
            self._memory_path = Path.home() / ".museon" / "immunity.json"

        # 先天免疫（不可變）
        self._innate_rules = INNATE_RULES

        # 後天免疫記憶
        self._antibodies: Dict[str, Antibody] = {}

        # 事件歷史（最近 100 筆）
        self._incidents: List[Incident] = []
        self._max_incidents = 100

        # 統計
        self._check_count = 0
        self._innate_hits = 0
        self._adaptive_hits = 0
        self._misses = 0

    def load(self) -> None:
        """從磁碟載入免疫記憶。"""
        if not self._memory_path.exists():
            return

        try:
            data = json.loads(self._memory_path.read_text("utf-8"))
            for ab_data in data.get("antibodies", []):
                ab = Antibody.from_dict(ab_data)
                self._antibodies[ab.antibody_id] = ab
            for inc_data in data.get("incidents", []):
                self._incidents.append(Incident.from_dict(inc_data))

            logger.info(
                f"Immunity loaded: {len(self._antibodies)} antibodies, "
                f"{len(self._incidents)} incidents"
            )
        except Exception as e:
            logger.warning(f"Failed to load immunity memory: {e}")

    def save(self) -> None:
        """持久化免疫記憶到磁碟。"""
        try:
            self._memory_path.parent.mkdir(parents=True, exist_ok=True)

            # 衰退所有抗體
            for ab in self._antibodies.values():
                ab.decay()

            data = {
                "version": 1,
                "saved_at": time.time(),
                "antibodies": [ab.to_dict() for ab in self._antibodies.values()],
                "incidents": [inc.to_dict() for inc in self._incidents[-self._max_incidents:]],
                "stats": {
                    "check_count": self._check_count,
                    "innate_hits": self._innate_hits,
                    "adaptive_hits": self._adaptive_hits,
                    "misses": self._misses,
                },
            }
            self._memory_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to save immunity memory: {e}")

    def check(self, symptom: Symptom) -> Optional[ImmuneResponse]:
        """檢查症狀是否有已知的免疫反應。

        先查先天免疫，再查後天免疫。
        """
        self._check_count += 1

        # 1. 先天免疫（快速、確定性高）
        innate = self._check_innate(symptom)
        if innate:
            self._innate_hits += 1
            return innate

        # 2. 後天免疫（學習來的，有信心度）
        adaptive = self._check_adaptive(symptom)
        if adaptive:
            self._adaptive_hits += 1
            return adaptive

        self._misses += 1
        return None

    def record_incident(
        self,
        symptom: Symptom,
        resolution: str = "",
        auto_resolved: bool = False,
    ) -> Incident:
        """記錄一次事件。"""
        import hashlib
        incident_id = hashlib.sha256(
            f"{time.time()}-{symptom.name}".encode()
        ).hexdigest()[:12]

        incident = Incident(
            incident_id=incident_id,
            timestamp=time.time(),
            symptom_name=symptom.name,
            category=symptom.category.value,
            severity=symptom.severity.value,
            description=symptom.message,
            resolution=resolution,
            resolved=bool(resolution),
            resolved_at=time.time() if resolution else 0.0,
            auto_resolved=auto_resolved,
        )

        self._incidents.append(incident)
        if len(self._incidents) > self._max_incidents:
            self._incidents = self._incidents[-self._max_incidents:]

        return incident

    def resolve_by_symptom(self, symptom_name: str, resolution: str) -> int:
        """批次 resolve 所有匹配 symptom_name 的未解決事件。

        當服務恢復健康時由 Governor 呼叫，避免殭屍事件堆積。
        Returns: 被 resolve 的事件數量。
        """
        import time as _time
        count = 0
        now = _time.time()
        for inc in self._incidents:
            if inc.symptom_name == symptom_name and not inc.resolved:
                inc.resolved = True
                inc.resolved_at = now
                inc.auto_resolved = True
                inc.resolution = resolution
                # 從事後解決中學習，生成抗體（P1 後天免疫修復）
                self.learn(inc)
                count += 1
        if count:
            logger.info(
                f"Immunity: resolved {count} incidents "
                f"for symptom [{symptom_name}]"
            )
        return count

    def has_active_incident(self, symptom_name: str) -> bool:
        """檢查是否已有同名症狀的未解決事件（用於去重）。"""
        return any(
            inc.symptom_name == symptom_name and not inc.resolved
            for inc in self._incidents
        )

    def learn(self, incident: Incident) -> Optional[Antibody]:
        """從已解決的事件中學習，建立新抗體。

        只有成功解決的事件才會產生抗體。
        """
        if not incident.resolved or not incident.resolution:
            return None

        # 檢查是否已有類似抗體
        existing = self._find_adaptive_antibody(incident.symptom_name)
        if existing:
            # 強化既有抗體
            existing.reinforce(success=True)
            logger.debug(
                f"Reinforced antibody {existing.antibody_id} "
                f"(confidence: {existing.confidence:.2f})"
            )
            return existing

        # 建立新抗體
        import hashlib
        ab_id = hashlib.sha256(
            f"ab-{incident.symptom_name}-{time.time()}".encode()
        ).hexdigest()[:12]

        antibody = Antibody(
            antibody_id=ab_id,
            pattern=incident.symptom_name,
            category=incident.category,
            response_type="log",  # 預設保守行動
            response_target=incident.category,
            response_description=f"學習自事件 {incident.incident_id}: {incident.resolution}",
            confidence=0.5,  # 初始信心度
            created_at=time.time(),
            last_used_at=time.time(),
        )

        self._antibodies[ab_id] = antibody
        logger.info(
            f"New antibody created: {ab_id} for pattern '{incident.symptom_name}'"
        )
        return antibody

    def reinforce(self, antibody_id: str, success: bool) -> None:
        """強化或弱化特定抗體。"""
        ab = self._antibodies.get(antibody_id)
        if ab:
            ab.reinforce(success)

    # ─── 先天免疫 ───

    def _check_innate(self, symptom: Symptom) -> Optional[ImmuneResponse]:
        """檢查先天免疫規則。"""
        for rule in self._innate_rules:
            if symptom.name.startswith(rule["pattern"]):
                return ImmuneResponse(
                    antibody_id=f"innate:{rule['pattern']}",
                    antibody_type="innate",
                    response_type=rule["response_type"],
                    response_target=rule["response_target"],
                    response_description=rule["response_description"],
                    confidence=1.0,  # 先天免疫信心度永遠是 1.0
                    symptom_name=symptom.name,
                )
        return None

    # ─── 後天免疫 ───

    def _check_adaptive(self, symptom: Symptom) -> Optional[ImmuneResponse]:
        """檢查後天免疫記憶。"""
        ab = self._find_adaptive_antibody(symptom.name)
        if ab and ab.confidence >= 0.3:  # 信心度 >= 30% 才回應
            ab.last_used_at = time.time()
            return ImmuneResponse(
                antibody_id=ab.antibody_id,
                antibody_type="adaptive",
                response_type=ab.response_type,
                response_target=ab.response_target,
                response_description=ab.response_description,
                confidence=ab.confidence,
                symptom_name=symptom.name,
            )
        return None

    def _find_adaptive_antibody(self, symptom_name: str) -> Optional[Antibody]:
        """尋找匹配症狀的後天抗體。"""
        best: Optional[Antibody] = None
        best_score = 0.0

        for ab in self._antibodies.values():
            # 精確匹配
            if ab.pattern == symptom_name:
                score = ab.confidence * 2.0  # 精確匹配加倍
                if score > best_score:
                    best = ab
                    best_score = score

            # 前綴匹配
            elif symptom_name.startswith(ab.pattern):
                score = ab.confidence
                if score > best_score:
                    best = ab
                    best_score = score

        return best

    # ─── 狀態查詢 ───

    def get_status(self) -> dict:
        """取得免疫引擎狀態。"""
        return {
            "antibody_count": len(self._antibodies),
            "incident_count": len(self._incidents),
            "innate_rules": len(self._innate_rules),
            "stats": {
                "check_count": self._check_count,
                "innate_hits": self._innate_hits,
                "adaptive_hits": self._adaptive_hits,
                "misses": self._misses,
                "hit_rate": (
                    round(
                        (self._innate_hits + self._adaptive_hits)
                        / max(self._check_count, 1),
                        2,
                    )
                ),
            },
            "antibodies": [
                {
                    "id": ab.antibody_id,
                    "pattern": ab.pattern,
                    "confidence": round(ab.confidence, 2),
                    "total_uses": ab.total_uses,
                    "success_rate": round(ab.success_rate, 2),
                }
                for ab in sorted(
                    self._antibodies.values(),
                    key=lambda a: a.confidence,
                    reverse=True,
                )[:10]  # Top 10
            ],
            "recent_incidents": [
                {
                    "id": inc.incident_id,
                    "symptom": inc.symptom_name,
                    "severity": inc.severity,
                    "resolved": inc.resolved,
                    "auto_resolved": inc.auto_resolved,
                }
                for inc in self._incidents[-5:]  # Last 5
            ],
        }
