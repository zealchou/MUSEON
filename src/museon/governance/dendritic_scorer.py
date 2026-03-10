"""DendriticScorer — VIGIL EmoBank 式健康分數計算器.

仿生物免疫系統的樹突細胞層：
  - 持續巡邏所有模組的事件
  - 計算即時 Health Score（指數衰減加權）
  - 把問題結構化為 Incident Package
  - 分類後路由：Tier1（快速修復）/ Tier2（LLM 診斷研究）

設計原則：
  - 純 CPU，零 LLM Token
  - 唯讀——只觀察和呈現，從不修改任何東西
  - 幕式（episodic）觸發，不是每秒掃描

Health Score 公式（VIGIL EmoBank 指數衰減）：
  score = 100 + Σ(event.impact × e^(-0.693 × age_hours / half_life))
  半衰期 = 2 小時（近期事件權重更高）
"""

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 半衰期（小時）
HALF_LIFE_HOURS = 2.0
# ln(2) ≈ 0.693
LN2 = 0.693

# Health Score 閾值
THRESHOLD_HEALTHY = 70      # > 70 → 健康
THRESHOLD_DEGRADED = 40     # 40-70 → 降級（Tier 1）
                            # ≤ 40 → 危險（Tier 2）

# 事件滯留窗口（小時）— 超過此時間的事件權重趨近零
EVENT_WINDOW_HOURS = 24


@dataclass
class HealthEvent:
    """健康事件（正面或負面）."""

    timestamp: float              # Unix timestamp
    impact: float                 # 正=好事, 負=壞事 (例 -10, -5, +2)
    source: str = ""              # 來源模組
    message: str = ""             # 描述
    event_type: str = "unknown"   # "error"|"warning"|"recovery"|"success"


@dataclass
class IncidentPackage:
    """結構化事件包 — 樹突細胞呈現格式."""

    incident_id: str
    incident_type: str            # "soft_failure"|"hard_failure"|"degradation"
    module: str
    pattern: str                  # 問題模式描述
    frequency: int                # 過去 N 小時發生次數
    health_delta: float           # 對 Health Score 的影響
    suggested_tier: int           # 1=快速修復, 2=LLM 研究
    raw_log_snippet: str = ""     # 最相關的日誌片段
    similar_past: str = ""        # 歷史相似 patch ID
    created_at: str = ""


class DendriticScorer:
    """VIGIL EmoBank 式健康分數計算器.

    純 CPU，零 LLM。維護一個事件窗口，即時計算 Health Score。
    """

    def __init__(
        self,
        event_bus: Any = None,
        half_life_hours: float = HALF_LIFE_HOURS,
        max_events: int = 500,
    ) -> None:
        self._event_bus = event_bus
        self._half_life = half_life_hours
        self._max_events = max_events
        self._events: List[HealthEvent] = []
        self._incidents: List[IncidentPackage] = []
        self._last_score: float = 100.0
        self._subscribe()

    def _subscribe(self) -> None:
        """訂閱治理事件流."""
        if not self._event_bus:
            return

        # 訂閱 Governor 的治理迴圈完成事件
        try:
            self._event_bus.subscribe(
                "GOVERNANCE_CYCLE_COMPLETED", self._on_governance_cycle
            )
            self._event_bus.subscribe(
                "GOVERNANCE_HEALTH_CHANGED", self._on_health_changed
            )
            self._event_bus.subscribe(
                "GOVERNANCE_ALGEDONIC_SIGNAL", self._on_algedonic
            )
        except Exception as e:
            logger.debug(f"DendriticScorer event subscription partial: {e}")

        # Phase 1: 訂閱 Skill 品質分數 + 工具健康事件
        try:
            from museon.core.event_bus import (
                SKILL_QUALITY_SCORED,
                TOOL_DEGRADED,
                TOOL_RECOVERED,
            )
            self._event_bus.subscribe(
                SKILL_QUALITY_SCORED, self._on_skill_quality
            )
            self._event_bus.subscribe(
                TOOL_DEGRADED, self._on_tool_degraded
            )
            self._event_bus.subscribe(
                TOOL_RECOVERED, self._on_tool_recovered
            )
        except Exception as e:
            logger.debug(f"DendriticScorer phase1 subscription partial: {e}")

    # ── 事件記錄 ──

    def record_event(
        self,
        impact: float,
        source: str = "",
        message: str = "",
        event_type: str = "unknown",
    ) -> None:
        """記錄一個健康事件."""
        event = HealthEvent(
            timestamp=time.time(),
            impact=impact,
            source=source,
            message=message[:200],
            event_type=event_type,
        )
        self._events.append(event)
        self._prune_events()

    def record_error(self, source: str, message: str, severity: float = -10) -> None:
        """快捷方法：記錄錯誤事件."""
        self.record_event(
            impact=severity,
            source=source,
            message=message,
            event_type="error",
        )

    def record_recovery(self, source: str, message: str = "") -> None:
        """快捷方法：記錄恢復事件."""
        self.record_event(
            impact=5,
            source=source,
            message=message or f"{source} recovered",
            event_type="recovery",
        )

    # ── Health Score 計算 ──

    def calculate_score(self) -> float:
        """計算當前 Health Score（VIGIL EmoBank 指數衰減）.

        公式：score = 100 + Σ(event.impact × e^(-0.693 × age_hours / half_life))
        結果限制在 [0, 100]
        """
        score = 100.0
        now = time.time()

        for event in self._events:
            age_hours = (now - event.timestamp) / 3600
            if age_hours > EVENT_WINDOW_HOURS:
                continue
            weight = math.exp(-LN2 * age_hours / self._half_life)
            score += event.impact * weight

        self._last_score = max(0.0, min(100.0, score))
        return self._last_score

    def get_tier(self) -> int:
        """根據 Health Score 判斷當前層級.

        Returns:
            0: 健康 (>70)
            1: 降級 (40-70) — Tier 1 快速修復
            2: 危險 (≤40)  — Tier 2 LLM 研究
        """
        score = self.calculate_score()
        if score > THRESHOLD_HEALTHY:
            return 0
        if score > THRESHOLD_DEGRADED:
            return 1
        return 2

    # ── Incident Package 生成 ──

    def generate_incident(
        self,
        module: str,
        pattern: str,
        incident_type: str = "soft_failure",
        log_snippet: str = "",
    ) -> IncidentPackage:
        """從當前事件流生成結構化 Incident Package."""
        now = time.time()
        # 計算該模組過去 6 小時的事件頻率
        window = 6 * 3600
        freq = sum(
            1 for e in self._events
            if e.source == module
            and (now - e.timestamp) < window
            and e.impact < 0
        )

        # 計算該模組對 Health Score 的累積影響
        delta = sum(
            e.impact * math.exp(-LN2 * (now - e.timestamp) / 3600 / self._half_life)
            for e in self._events
            if e.source == module
            and (now - e.timestamp) < EVENT_WINDOW_HOURS * 3600
        )

        # 判斷建議的處理層級（三級分層）
        if freq >= 7 and delta < -30:
            suggested_tier = 3  # 高頻 + 高影響 → 升級人工介入
        elif freq >= 5 or delta < -20:
            suggested_tier = 2  # 高頻或高影響 → LLM 研究
        elif freq >= 3 and delta < -10:
            suggested_tier = 1  # 中等 → 自動修復
        else:
            suggested_tier = 1  # 低頻低影響 → 快速修復

        incident = IncidentPackage(
            incident_id=f"INC-{datetime.now(TZ8).strftime('%Y-%m%d-%H%M')}-{uuid.uuid4().hex[:4]}",
            incident_type=incident_type,
            module=module,
            pattern=pattern,
            frequency=freq,
            health_delta=round(delta, 1),
            suggested_tier=suggested_tier,
            raw_log_snippet=log_snippet[:500],
            created_at=datetime.now(TZ8).isoformat(),
        )

        self._incidents.append(incident)
        # 保留最近 50 個 incidents
        if len(self._incidents) > 50:
            self._incidents = self._incidents[-50:]

        # 發布事件
        if self._event_bus:
            from museon.core.event_bus import INCIDENT_DETECTED
            self._event_bus.publish(INCIDENT_DETECTED, {
                "incident_id": incident.incident_id,
                "module": module,
                "pattern": pattern,
                "suggested_tier": suggested_tier,
                "health_delta": incident.health_delta,
            })

        return incident

    # ── Tick（定期呼叫）──

    def tick(self) -> Dict:
        """定期 tick — Governor 呼叫.

        Returns:
            當前健康狀態快照
        """
        score = self.calculate_score()
        tier = self.get_tier()

        # 發布 Health Score 更新事件
        if self._event_bus:
            from museon.core.event_bus import HEALTH_SCORE_UPDATED
            self._event_bus.publish(HEALTH_SCORE_UPDATED, {
                "score": round(score, 1),
                "tier": tier,
                "event_count": len(self._events),
                "incident_count": len(self._incidents),
            })

        return {
            "score": round(score, 1),
            "tier": tier,
            "tier_label": ["healthy", "degraded", "critical"][tier],
            "event_count": len(self._events),
            "recent_incidents": len([
                i for i in self._incidents
                if i.created_at and
                (datetime.now(TZ8) -
                 datetime.fromisoformat(i.created_at)).total_seconds() < 3600
            ]),
        }

    # ── 狀態查詢 ──

    def get_status(self) -> Dict:
        """取得完整狀態（供 /health 端點）."""
        score = self.calculate_score()
        return {
            "score": round(score, 1),
            "tier": self.get_tier(),
            "total_events": len(self._events),
            "total_incidents": len(self._incidents),
            "last_score": round(self._last_score, 1),
            "half_life_hours": self._half_life,
        }

    def get_recent_incidents(self, hours: float = 6) -> List[Dict]:
        """取得最近 N 小時的 Incidents."""
        cutoff = datetime.now(TZ8) - timedelta(hours=hours)
        results = []
        for inc in reversed(self._incidents):
            if inc.created_at:
                try:
                    created = datetime.fromisoformat(inc.created_at)
                    if created < cutoff:
                        break
                except (ValueError, TypeError):
                    continue
            results.append({
                "incident_id": inc.incident_id,
                "type": inc.incident_type,
                "module": inc.module,
                "pattern": inc.pattern,
                "frequency": inc.frequency,
                "health_delta": inc.health_delta,
                "tier": inc.suggested_tier,
                "created_at": inc.created_at,
            })
        return results

    # ── EventBus 回調 ──

    def _on_governance_cycle(self, data: Optional[Dict] = None) -> None:
        """Governor 治理迴圈完成時更新."""
        if not data:
            return
        health = data.get("health", "vital")
        is_healthy = data.get("is_healthy", True)

        if not is_healthy:
            symptom_count = data.get("symptom_count", 0)
            self.record_event(
                impact=-3 * symptom_count,
                source="governor",
                message=f"Governance cycle: {symptom_count} symptoms, health={health}",
                event_type="warning",
            )
        else:
            self.record_event(
                impact=1,
                source="governor",
                message=f"Governance cycle: healthy ({health})",
                event_type="success",
            )

    def _on_health_changed(self, data: Optional[Dict] = None) -> None:
        """健康等級變化."""
        if not data:
            return
        old_tier = data.get("old_tier", "")
        new_tier = data.get("new_tier", "")
        # 惡化
        if new_tier in ("degraded", "critical") and old_tier == "healthy":
            self.record_event(
                impact=-15,
                source="governor",
                message=f"Health tier degraded: {old_tier} → {new_tier}",
                event_type="error",
            )

    def _on_algedonic(self, data: Optional[Dict] = None) -> None:
        """警覺信號 — 嚴重問題."""
        if not data:
            return
        self.record_event(
            impact=-25,
            source="governor",
            message=f"Algedonic signal: {data}",
            event_type="error",
        )
        # 自動生成 Incident
        self.generate_incident(
            module="system",
            pattern="algedonic_signal",
            incident_type="hard_failure",
        )

    # ── Phase 1: Skill/Tool 閉環回調 ──

    def _on_skill_quality(self, data: Optional[Dict] = None) -> None:
        """WP-02: Skill 品質分數 → 影響 Health Score."""
        if not data:
            return
        score_dict = data.get("score", {})
        avg = score_dict.get("composite", 5.0)
        if avg < 4.0:
            self.record_event(
                impact=-5,
                source="wee",
                message=f"Low skill quality: avg={avg:.1f}",
                event_type="warning",
            )
        elif avg > 7.0:
            self.record_event(
                impact=2,
                source="wee",
                message=f"High skill quality: avg={avg:.1f}",
                event_type="success",
            )

    def _on_tool_degraded(self, data: Optional[Dict] = None) -> None:
        """WP-07: 工具降級 → Health Score -8."""
        if not data:
            return
        tool_name = data.get("tool_name", "unknown")
        self.record_event(
            impact=-8,
            source="tool_registry",
            message=f"Tool degraded: {tool_name}",
            event_type="error",
        )

    def _on_tool_recovered(self, data: Optional[Dict] = None) -> None:
        """WP-07: 工具恢復 → Health Score +5."""
        if not data:
            return
        tool_name = data.get("tool_name", "unknown")
        self.record_event(
            impact=5,
            source="tool_registry",
            message=f"Tool recovered: {tool_name}",
            event_type="recovery",
        )

    # ── 內部工具 ──

    def _prune_events(self) -> None:
        """清理過舊的事件."""
        now = time.time()
        cutoff = now - EVENT_WINDOW_HOURS * 3600
        self._events = [
            e for e in self._events if e.timestamp > cutoff
        ]
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
