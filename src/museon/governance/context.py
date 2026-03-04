"""GovernanceContext — 治理層 → 大腦的唯讀信號橋樑

Governor 每 5 分鐘產出診斷報告、調節行動、免疫反應，
但 Brain 無法直接存取這些資訊。

GovernanceContext 是一個 frozen dataclass，作為 Governor → Brain 的橋樑：
- Governor.build_context() 產出快照
- Brain._build_system_prompt() 注入健康自覺到 buffer zone
- 不同健康等級 → 不同濃度的 prompt fragment
  - THRIVING: ~15 tokens（極簡）
  - STABLE: ~20 tokens
  - STRAINED: ~80 tokens（提醒保守）
  - CRITICAL: ~150 tokens（影響回應策略）

設計原則：
- Frozen（不可變）：確保 Brain 拿到的是快照，不會被異步修改
- 輕量級：只帶摘要，不帶完整診斷報告
- 降級安全：任何欄位缺失都有合理預設值

Phase 3a — 2026-03-03
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple


class HealthTier(Enum):
    """系統健康等級（Governor 五級 → 四級映射）。

    VITAL + STABLE → THRIVING / STABLE
    DEGRADED → STRAINED
    CRITICAL + EMERGENCY → CRITICAL
    """

    THRIVING = "thriving"   # 一切正常，全速運行
    STABLE = "stable"       # 有小問題但穩定
    STRAINED = "strained"   # 部分受損，應保守行動
    CRITICAL = "critical"   # 核心功能受損，最小化回應


# ─── SystemHealth → HealthTier 映射 ───

_HEALTH_TO_TIER = {
    "vital": HealthTier.THRIVING,
    "stable": HealthTier.STABLE,
    "degraded": HealthTier.STRAINED,
    "critical": HealthTier.CRITICAL,
    "emergency": HealthTier.CRITICAL,
}


def health_to_tier(health_value: str) -> HealthTier:
    """將 Governor 的 SystemHealth.value 映射為 HealthTier。"""
    return _HEALTH_TO_TIER.get(health_value, HealthTier.STABLE)


@dataclass(frozen=True)
class GovernanceContext:
    """治理層快照 — Brain 可讀取的唯讀上下文。

    Attributes:
        health_tier: 當前系統健康等級
        symptom_count: 最近一次診斷的症狀數
        critical_symptoms: 嚴重症狀的簡述列表
        trend: 健康趨勢 ("improving" / "stable" / "declining" / "no_data")
        healthy_ratio: 過去一小時健康比率 (0.0-1.0)
        immune_hit_rate: 免疫命中率 (0.0-1.0)，已知模式佔比
        innate_defenses: 先天免疫防禦觸發次數
        adaptive_hits: 後天免疫命中次數
        uptime_s: 系統已運行秒數
        snapshot_at: 快照產生時間（Unix timestamp）
    """

    health_tier: HealthTier
    symptom_count: int = 0
    critical_symptoms: Tuple[str, ...] = ()
    trend: str = "no_data"
    healthy_ratio: float = 1.0
    immune_hit_rate: float = 0.0
    innate_defenses: int = 0
    adaptive_hits: int = 0
    uptime_s: float = 0.0
    snapshot_at: float = 0.0

    # ─── Properties ───

    @property
    def is_fresh(self) -> bool:
        """快照是否新鮮（< 10 分鐘）。"""
        return (time.time() - self.snapshot_at) < 600

    @property
    def needs_caution(self) -> bool:
        """系統是否需要保守行動（STRAINED / CRITICAL）。"""
        return self.health_tier in (HealthTier.STRAINED, HealthTier.CRITICAL)

    @property
    def is_healthy(self) -> bool:
        """系統是否健康（THRIVING / STABLE）。"""
        return self.health_tier in (HealthTier.THRIVING, HealthTier.STABLE)

    # ─── Prompt Fragment ───

    def to_prompt_fragment(self) -> str:
        """依健康等級產出不同濃度的自覺文本。

        設計目標：
        - THRIVING: 極簡提示，不佔 token
        - STABLE: 簡短告知
        - STRAINED: 提醒保守、列出問題
        - CRITICAL: 完整告知，影響回應策略
        """
        tier = self.health_tier

        if tier == HealthTier.THRIVING:
            # ~15 tokens — 極簡
            return (
                "## 系統自覺\n"
                "系統運作良好，全速回應。"
            )

        if tier == HealthTier.STABLE:
            # ~20 tokens
            return (
                "## 系統自覺\n"
                f"系統穩定運行（{self.symptom_count} 個輕微症狀），"
                "正常回應。"
            )

        if tier == HealthTier.STRAINED:
            # ~80 tokens — 提醒保守
            symptoms_text = ""
            if self.critical_symptoms:
                symptoms_list = "、".join(self.critical_symptoms[:3])
                symptoms_text = f"已知問題：{symptoms_list}。"

            trend_text = ""
            if self.trend == "declining":
                trend_text = "趨勢惡化中。"
            elif self.trend == "improving":
                trend_text = "趨勢改善中。"

            return (
                "## 系統自覺（注意）\n"
                f"系統處於壓力狀態（{self.symptom_count} 個症狀）。"
                f"{symptoms_text}{trend_text}\n"
                "建議：回應時優先簡潔，避免深度分析消耗過多資源。"
                "如需工具呼叫，優先使用快取結果。"
            )

        # CRITICAL — ~150 tokens
        symptoms_text = ""
        if self.critical_symptoms:
            symptoms_list = "、".join(self.critical_symptoms[:5])
            symptoms_text = f"\n嚴重問題：{symptoms_list}"

        immune_text = ""
        if self.immune_hit_rate > 0:
            immune_text = (
                f"\n免疫系統已知 {self.immune_hit_rate:.0%} 的問題模式。"
            )

        return (
            "## 系統自覺（警戒）\n"
            f"⚠️ 系統健康等級：CRITICAL（{self.symptom_count} 個症狀）"
            f"{symptoms_text}{immune_text}\n"
            "回應策略調整：\n"
            "- 使用最簡潔的回應格式\n"
            "- 避免觸發工具呼叫或外部 API\n"
            "- 不主動推送知識結晶\n"
            "- 若使用者問題可快速回答，直接回答；"
            "若需深度分析，告知使用者系統正在恢復中"
        )


def build_empty_context() -> GovernanceContext:
    """建立一個空的治理上下文（Governor 尚未初始化時使用）。"""
    return GovernanceContext(
        health_tier=HealthTier.STABLE,
        snapshot_at=time.time(),
    )
