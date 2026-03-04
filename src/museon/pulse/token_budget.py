"""TokenBudget — MUSEON 的薪水制 Token 經濟系統.

設計哲學：
  - Token = 薪水。使用者設定月度預算上限（monthly_ceiling）
  - MUSEON 自動管理每日動態配置
  - 省下來的 token 是 MUSEON 自己的錢（reserve_pool）
  - reserve_pool 每日輕微代謝（模擬脂肪消耗）
  - conservation mode：快沒錢時自動降級模型、減少探索

三種預算層級：
  SURVIVAL  ~$5/mo   → 心跳 + 被動回應
  NORMAL    ~$15/mo  → + 主動推送 + 探索 + 技能鍛造
  AFFLUENT  ~$30+/mo → + 深度學習 + 架構重構

零 LLM 依賴，純 CPU 啟發式。
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 預算層級
# ═══════════════════════════════════════════


class BudgetTier(Enum):
    """三種預算層級."""

    SURVIVAL = "survival"    # ~$5/mo: 心跳 + 被動回應
    NORMAL = "normal"        # ~$15/mo: + 主動推送 + 探索 + 技能鍛造
    AFFLUENT = "affluent"    # ~$30+/mo: + 深度學習 + 架構重構


# 層級閾值（月度 USD）
TIER_THRESHOLDS = {
    BudgetTier.SURVIVAL: 0.0,
    BudgetTier.NORMAL: 10.0,
    BudgetTier.AFFLUENT: 25.0,
}


class SpendCategory(Enum):
    """花費類別."""

    RESPONSE = "response"           # 回應使用者
    EXPLORATION = "exploration"     # 探索 / 學習
    PROACTIVE = "proactive"         # 主動推送
    SKILL_FORGE = "skill_forge"     # 技能鍛造
    NIGHTLY = "nightly"             # 夜間管線
    HEARTBEAT = "heartbeat"         # 心跳自省
    SELF_REPAIR = "self_repair"     # 自律神經修復
    METABOLISM = "metabolism"        # 基礎代謝


# ═══════════════════════════════════════════
# 預算狀態
# ═══════════════════════════════════════════


@dataclass
class BudgetState:
    """Token 預算持久化狀態."""

    monthly_ceiling_usd: float = 15.0   # 使用者設定的月度上限（USD）
    reserve_pool_usd: float = 0.0       # 脂肪儲備（累積結餘）
    today_spent_usd: float = 0.0        # 今日已花費
    today_date: str = ""                # 今日日期（YYYY-MM-DD）
    month_spent_usd: float = 0.0        # 本月已花費
    month_key: str = ""                 # 當前月份（YYYY-MM）
    metabolic_rate: float = 0.02        # 每日代謝率（reserve *= 1 - rate）
    max_reserve_months: float = 3.0     # 最大儲備月數
    daily_log: Dict[str, float] = field(default_factory=dict)  # {category: spent}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BudgetState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ═══════════════════════════════════════════
# TokenBudgetManager — 薪水制管理器
# ═══════════════════════════════════════════


class TokenBudgetManager:
    """MUSEON 的 Token 經濟管理器.

    核心概念：
      - 使用者設月度預算上限 → MUSEON 自動管理
      - 每日配額 = monthly / 30
      - 每日結餘 → reserve_pool（脂肪儲備）
      - reserve 每日代謝 2%（模擬脂肪消耗）
      - conservation mode：日預算用完 + reserve 不足時觸發

    能量分配：
      - 表層（Cortex）：回應、探索、主動推送
      - 自律層（Autonomic）：心跳、修復 → 主要 CPU，極少用 token
      - 自律層可從 daily 借 15%（reserve 不足時）
    """

    AUTONOMIC_BORROW_RATIO = 0.15  # 自律層最多借表層 15%

    def __init__(self, data_dir: Optional[Path] = None):
        self._data_dir = data_dir
        self._state = BudgetState()
        self._state_path: Optional[Path] = None

        if data_dir:
            self._state_path = Path(data_dir) / "_system" / "token_budget.json"
            self._state_path.parent.mkdir(parents=True, exist_ok=True)

        self._load_state()
        self._check_day_rollover()

        logger.info(
            "TokenBudgetManager 初始化: ceiling=%.2f/mo, reserve=%.4f, tier=%s",
            self._state.monthly_ceiling_usd,
            self._state.reserve_pool_usd,
            self.current_tier.value,
        )

    # ─── 核心操作 ─────────────────────────

    def spend(self, amount_usd: float, category: str = "response") -> bool:
        """花費 token.

        Args:
            amount_usd: 花費金額（USD）
            category: 花費類別（SpendCategory.value）

        Returns:
            True = 允許花費, False = 預算不足（conservation mode）
        """
        self._check_day_rollover()

        # 檢查是否能負擔
        if not self._can_spend(amount_usd, category):
            logger.warning(
                "TokenBudget: 預算不足，拒絕 %.4f USD (%s), "
                "daily_remaining=%.4f, reserve=%.4f",
                amount_usd, category,
                self.daily_remaining, self._state.reserve_pool_usd,
            )
            return False

        # 扣費
        self._state.today_spent_usd += amount_usd
        self._state.month_spent_usd += amount_usd

        # 分類記帳
        cat_key = category
        self._state.daily_log[cat_key] = (
            self._state.daily_log.get(cat_key, 0.0) + amount_usd
        )

        self._save_state()
        return True

    def daily_metabolism(self) -> float:
        """每日代謝 — reserve 輕微消耗.

        模擬生物脂肪的自然代謝。
        由 NightlyPipeline step_00 呼叫。

        Returns:
            代謝量（USD）
        """
        if self._state.reserve_pool_usd <= 0:
            return 0.0

        cost = self._state.reserve_pool_usd * self._state.metabolic_rate
        self._state.reserve_pool_usd = max(
            0.0, self._state.reserve_pool_usd - cost
        )
        self._save_state()

        logger.info(
            "TokenBudget 代謝: -%.4f USD, reserve=%.4f",
            cost, self._state.reserve_pool_usd,
        )
        return cost

    def daily_settlement(self) -> float:
        """每日結算 — 結餘進入 reserve.

        由 NightlyPipeline step_00 呼叫（在 metabolism 之後）。

        Returns:
            結餘金額（USD）
        """
        self._check_day_rollover()

        surplus = max(0.0, self.daily_allowance - self._state.today_spent_usd)

        if surplus > 0:
            max_reserve = self._state.monthly_ceiling_usd * self._state.max_reserve_months
            new_reserve = min(
                self._state.reserve_pool_usd + surplus,
                max_reserve,
            )
            actual_saved = new_reserve - self._state.reserve_pool_usd
            self._state.reserve_pool_usd = new_reserve

            logger.info(
                "TokenBudget 日結: surplus=%.4f, saved=%.4f, reserve=%.4f",
                surplus, actual_saved, self._state.reserve_pool_usd,
            )
        else:
            actual_saved = 0.0

        # 重置日計數（明天重新開始）
        self._state.today_spent_usd = 0.0
        self._state.daily_log = {}
        self._state.today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._save_state()

        return actual_saved

    # ─── 查詢方法 ─────────────────────────

    @property
    def daily_allowance(self) -> float:
        """每日配額（USD）."""
        return self._state.monthly_ceiling_usd / 30.0

    @property
    def daily_remaining(self) -> float:
        """今日剩餘配額（USD）."""
        return max(0.0, self.daily_allowance - self._state.today_spent_usd)

    @property
    def monthly_remaining(self) -> float:
        """本月剩餘預算（USD）."""
        return max(0.0, self._state.monthly_ceiling_usd - self._state.month_spent_usd)

    @property
    def current_tier(self) -> BudgetTier:
        """當前預算層級."""
        ceiling = self._state.monthly_ceiling_usd
        if ceiling >= TIER_THRESHOLDS[BudgetTier.AFFLUENT]:
            return BudgetTier.AFFLUENT
        elif ceiling >= TIER_THRESHOLDS[BudgetTier.NORMAL]:
            return BudgetTier.NORMAL
        else:
            return BudgetTier.SURVIVAL

    @property
    def is_conservation_mode(self) -> bool:
        """是否處於節約模式.

        條件：日配額用完 80% 且 reserve 低於一日配額。
        """
        daily_usage_ratio = (
            self._state.today_spent_usd / self.daily_allowance
            if self.daily_allowance > 0 else 1.0
        )
        low_reserve = self._state.reserve_pool_usd < self.daily_allowance
        return daily_usage_ratio >= 0.8 and low_reserve

    @property
    def reserve_health(self) -> str:
        """儲備健康度.

        Returns:
            "healthy" / "moderate" / "low" / "critical"
        """
        ratio = (
            self._state.reserve_pool_usd / self.daily_allowance
            if self.daily_allowance > 0 else 0.0
        )
        if ratio >= 7.0:       # 一週以上
            return "healthy"
        elif ratio >= 3.0:     # 三天以上
            return "moderate"
        elif ratio >= 1.0:     # 一天以上
            return "low"
        else:
            return "critical"

    def can_afford_exploration(self) -> bool:
        """是否能負擔探索.

        探索只在 NORMAL+ 層級且非節約模式時允許。
        """
        if self.current_tier == BudgetTier.SURVIVAL:
            return False
        if self.is_conservation_mode:
            return False
        # 至少剩 30% 日配額
        return self.daily_remaining >= self.daily_allowance * 0.3

    def can_afford_proactive(self) -> bool:
        """是否能負擔主動推送."""
        if self.current_tier == BudgetTier.SURVIVAL:
            return False
        if self.is_conservation_mode:
            return False
        return self.daily_remaining >= self.daily_allowance * 0.2

    def get_model_recommendation(self) -> str:
        """根據預算推薦模型.

        Returns:
            "sonnet" / "haiku"
        """
        if self.is_conservation_mode:
            return "haiku"
        if self.current_tier == BudgetTier.SURVIVAL:
            return "haiku"
        # NORMAL / AFFLUENT 且非節約模式
        # 日配額用超過 60% 時降級
        daily_usage_ratio = (
            self._state.today_spent_usd / self.daily_allowance
            if self.daily_allowance > 0 else 1.0
        )
        if daily_usage_ratio >= 0.6:
            return "haiku"
        return "sonnet"

    def get_exploration_budget(self) -> float:
        """取得今日可用於探索的預算（USD）.

        探索預算 = 日配額的 20%（NORMAL）或 30%（AFFLUENT）。
        """
        if not self.can_afford_exploration():
            return 0.0
        ratio = 0.3 if self.current_tier == BudgetTier.AFFLUENT else 0.2
        return self.daily_allowance * ratio

    def get_autonomic_budget(self) -> float:
        """取得自律層可用預算（USD）.

        自律層優先用 reserve，不足時最多借表層 15%。
        """
        reserve_available = self._state.reserve_pool_usd
        borrow_limit = self.daily_allowance * self.AUTONOMIC_BORROW_RATIO
        return reserve_available + borrow_limit

    def get_risk_budget(self) -> float:
        """取得風險預算（USD）— 供 PulseEngine 探索用.

        取代舊的 EXPLORATION_DAILY_BUDGET 硬編碼。
        """
        return self.get_exploration_budget()

    # ─── 預算設定 ─────────────────────────

    def set_monthly_ceiling(self, ceiling_usd: float) -> None:
        """使用者設定月度預算上限.

        Args:
            ceiling_usd: 月度上限（USD），必須 > 0
        """
        if ceiling_usd <= 0:
            raise ValueError("月度預算必須大於 0")
        self._state.monthly_ceiling_usd = ceiling_usd
        self._save_state()
        logger.info("TokenBudget: 月度上限更新為 %.2f USD", ceiling_usd)

    def add_to_reserve(self, amount_usd: float, source: str = "bonus") -> None:
        """直接增加儲備（獎金、賺到的錢）.

        Args:
            amount_usd: 金額
            source: 來源描述
        """
        max_reserve = self._state.monthly_ceiling_usd * self._state.max_reserve_months
        self._state.reserve_pool_usd = min(
            self._state.reserve_pool_usd + amount_usd,
            max_reserve,
        )
        self._save_state()
        logger.info(
            "TokenBudget: reserve +%.4f (%s), total=%.4f",
            amount_usd, source, self._state.reserve_pool_usd,
        )

    # ─── 狀態查詢 ─────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """取得完整預算狀態."""
        self._check_day_rollover()
        return {
            "tier": self.current_tier.value,
            "monthly_ceiling_usd": self._state.monthly_ceiling_usd,
            "daily_allowance_usd": round(self.daily_allowance, 4),
            "today_spent_usd": round(self._state.today_spent_usd, 4),
            "daily_remaining_usd": round(self.daily_remaining, 4),
            "month_spent_usd": round(self._state.month_spent_usd, 4),
            "monthly_remaining_usd": round(self.monthly_remaining, 4),
            "reserve_pool_usd": round(self._state.reserve_pool_usd, 4),
            "reserve_health": self.reserve_health,
            "conservation_mode": self.is_conservation_mode,
            "model_recommendation": self.get_model_recommendation(),
            "can_explore": self.can_afford_exploration(),
            "can_proactive": self.can_afford_proactive(),
            "exploration_budget_usd": round(self.get_exploration_budget(), 4),
            "autonomic_budget_usd": round(self.get_autonomic_budget(), 4),
            "daily_breakdown": {
                k: round(v, 4) for k, v in self._state.daily_log.items()
            },
        }

    def get_vitality_modifier(self) -> float:
        """取得生命力係數 — 供 TriggerEngine 使用.

        根據 reserve 健康度和預算層級計算：
          - healthy + AFFLUENT → 1.3（積極演化）
          - moderate + NORMAL → 1.0（正常）
          - low + SURVIVAL → 0.6（保守）
          - critical → 0.3（極度保守）

        Returns:
            0.3 ~ 1.3 之間的係數
        """
        health = self.reserve_health
        tier = self.current_tier

        base = {
            "healthy": 1.2,
            "moderate": 1.0,
            "low": 0.7,
            "critical": 0.3,
        }.get(health, 1.0)

        tier_bonus = {
            BudgetTier.AFFLUENT: 0.1,
            BudgetTier.NORMAL: 0.0,
            BudgetTier.SURVIVAL: -0.1,
        }.get(tier, 0.0)

        return max(0.3, min(1.3, base + tier_bonus))

    # ─── 月度重置 ─────────────────────────

    def monthly_reset(self) -> Dict[str, Any]:
        """月度重置 — 記錄上月統計並清零.

        由 NightlyPipeline 在月初第一天呼叫。

        Returns:
            上月統計摘要
        """
        summary = {
            "month": self._state.month_key,
            "total_spent_usd": round(self._state.month_spent_usd, 4),
            "ceiling_usd": self._state.monthly_ceiling_usd,
            "utilization": round(
                self._state.month_spent_usd / self._state.monthly_ceiling_usd
                if self._state.monthly_ceiling_usd > 0 else 0.0,
                4,
            ),
            "reserve_at_reset": round(self._state.reserve_pool_usd, 4),
        }

        self._state.month_spent_usd = 0.0
        self._state.month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        self._save_state()

        logger.info("TokenBudget 月度重置: %s", summary)
        return summary

    # ─── 內部方法 ─────────────────────────

    def _can_spend(self, amount_usd: float, category: str) -> bool:
        """判斷是否能花費."""
        # 自律層類別：可借 reserve
        autonomic_categories = {
            SpendCategory.HEARTBEAT.value,
            SpendCategory.SELF_REPAIR.value,
            SpendCategory.METABOLISM.value,
        }

        if category in autonomic_categories:
            return amount_usd <= self.get_autonomic_budget()

        # 表層類別：先用日配額，不足時不用 reserve
        # （reserve 是 MUSEON 自己的錢，不應被日常消耗吃掉）
        if self.daily_remaining >= amount_usd:
            return True

        # 日配額不足 — conservation mode
        # 但回應使用者永遠允許（品質可能降級，但不能不回）
        if category == SpendCategory.RESPONSE.value:
            return True

        return False

    def _check_day_rollover(self) -> None:
        """檢查日期翻轉."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")

        if not self._state.today_date:
            self._state.today_date = today
            self._state.month_key = current_month
            self._save_state()
            return

        if self._state.today_date != today:
            # 日翻轉 — 結餘自動存入 reserve
            surplus = max(0.0, self.daily_allowance - self._state.today_spent_usd)
            if surplus > 0:
                max_reserve = (
                    self._state.monthly_ceiling_usd * self._state.max_reserve_months
                )
                self._state.reserve_pool_usd = min(
                    self._state.reserve_pool_usd + surplus, max_reserve
                )

            self._state.today_spent_usd = 0.0
            self._state.daily_log = {}
            self._state.today_date = today

            # 月翻轉
            if self._state.month_key != current_month:
                self._state.month_spent_usd = 0.0
                self._state.month_key = current_month

            self._save_state()

    def _load_state(self) -> None:
        """從檔案載入狀態."""
        if not self._state_path or not self._state_path.exists():
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._state = BudgetState.from_dict(raw)
        except Exception as e:
            logger.warning("TokenBudget 狀態載入失敗: %s", e)

    def _save_state(self) -> None:
        """持久化狀態到檔案."""
        if not self._state_path:
            return
        try:
            self._state_path.write_text(
                json.dumps(self._state.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("TokenBudget 狀態儲存失敗: %s", e)
