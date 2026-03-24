"""Rate Limiter — Anthropic API 速率控制與降級引擎.

純 CPU 模組，零 token 消耗。提供：
1. ExponentialBackoff — retry-after header 優先 + jitter
2. RateLimitMonitor — 追蹤 API 回應的 ratelimit headers
3. PerTenantLimiter — 群組級 token bucket 隔離
4. ModelDegrader — 撞 limit 時自動降級 Sonnet→Haiku

用法：
    from museon.llm.rate_limiter import (
        ExponentialBackoff,
        RateLimitMonitor,
        PerTenantLimiter,
        ModelDegrader,
    )
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 1. Exponential Backoff with Jitter
# ═══════════════════════════════════════════

@dataclass
class BackoffConfig:
    initial_delay: float = 1.0
    exponential_base: float = 2.0
    max_retries: int = 5
    max_delay: float = 60.0
    jitter_fraction: float = 0.25  # ±25%


class ExponentialBackoff:
    """計算下次重試的等待時間.

    優先使用 server 提供的 retry-after header，
    fallback 到 exponential backoff + jitter。
    """

    def __init__(self, config: Optional[BackoffConfig] = None):
        self._cfg = config or BackoffConfig()

    def compute_delay(
        self,
        attempt: int,
        retry_after: Optional[float] = None,
    ) -> float:
        """計算第 N 次重試的等待秒數.

        Args:
            attempt: 第幾次重試（0-based）
            retry_after: server 回傳的 retry-after 秒數（優先使用）

        Returns:
            等待秒數
        """
        if retry_after is not None and retry_after > 0:
            # Server 指定，直接用（加微量 jitter 避免雷群）
            jitter = random.uniform(0, min(retry_after * 0.1, 2.0))
            return min(retry_after + jitter, self._cfg.max_delay)

        # Exponential backoff
        delay = self._cfg.initial_delay * (self._cfg.exponential_base ** attempt)

        # Jitter: ±fraction
        jitter_range = delay * self._cfg.jitter_fraction
        delay += random.uniform(-jitter_range, jitter_range)

        return min(max(delay, 0.1), self._cfg.max_delay)

    def should_retry(self, attempt: int) -> bool:
        return attempt < self._cfg.max_retries


# ═══════════════════════════════════════════
# 2. Rate Limit Monitor
# ═══════════════════════════════════════════

@dataclass
class RateLimitState:
    """從 API response headers 解析的速率狀態."""
    requests_limit: int = 0
    requests_remaining: int = 0
    tokens_limit: int = 0
    tokens_remaining: int = 0
    retry_after: Optional[float] = None
    last_updated: float = 0.0

    @property
    def requests_usage_pct(self) -> float:
        if self.requests_limit <= 0:
            return 0.0
        return 1.0 - (self.requests_remaining / self.requests_limit)

    @property
    def tokens_usage_pct(self) -> float:
        if self.tokens_limit <= 0:
            return 0.0
        return 1.0 - (self.tokens_remaining / self.tokens_limit)

    @property
    def is_near_limit(self) -> bool:
        """是否接近限制（>80% 使用率）."""
        return self.requests_usage_pct > 0.8 or self.tokens_usage_pct > 0.8


class RateLimitMonitor:
    """追蹤 Anthropic API 回應中的 rate limit headers."""

    def __init__(self):
        self._state = RateLimitState()
        self._hit_count: int = 0
        self._last_hit: float = 0.0

    @property
    def state(self) -> RateLimitState:
        return self._state

    @property
    def hit_count(self) -> int:
        return self._hit_count

    def update_from_headers(self, headers: Dict[str, str]) -> None:
        """從 API response headers 更新狀態.

        Anthropic headers:
          anthropic-ratelimit-requests-limit
          anthropic-ratelimit-requests-remaining
          anthropic-ratelimit-tokens-limit
          anthropic-ratelimit-tokens-remaining
          retry-after
        """
        def _int(key: str) -> int:
            return int(headers.get(key, 0))

        self._state.requests_limit = _int("anthropic-ratelimit-requests-limit")
        self._state.requests_remaining = _int("anthropic-ratelimit-requests-remaining")
        self._state.tokens_limit = _int("anthropic-ratelimit-tokens-limit")
        self._state.tokens_remaining = _int("anthropic-ratelimit-tokens-remaining")
        self._state.last_updated = time.time()

        ra = headers.get("retry-after")
        if ra:
            try:
                self._state.retry_after = float(ra)
            except (ValueError, TypeError):
                self._state.retry_after = None

    def record_hit(self) -> None:
        """記錄一次 429 撞擊."""
        self._hit_count += 1
        self._last_hit = time.time()
        logger.warning(
            f"[RateMonitor] 429 hit #{self._hit_count} | "
            f"req_remaining={self._state.requests_remaining} "
            f"tok_remaining={self._state.tokens_remaining}"
        )

    def should_preempt_throttle(self) -> bool:
        """預判是否應該主動降速（接近 limit 時）."""
        if self._state.last_updated == 0:
            return False
        # 資料太舊（>2 分鐘）不可靠
        if time.time() - self._state.last_updated > 120:
            return False
        return self._state.is_near_limit


# ═══════════════════════════════════════════
# 3. Per-Tenant Rate Limiter (Token Bucket)
# ═══════════════════════════════════════════

@dataclass
class TenantBucket:
    """單一群組/使用者的 token bucket."""
    daily_limit: int = 50_000
    used_today: int = 0
    last_reset: str = ""  # YYYY-MM-DD

    @property
    def remaining(self) -> int:
        return max(self.daily_limit - self.used_today, 0)

    @property
    def usage_pct(self) -> float:
        if self.daily_limit <= 0:
            return 0.0
        return self.used_today / self.daily_limit


# 預設群組預算配置
DEFAULT_TENANT_LIMITS = {
    "owner_private": 100_000,   # Zeal 私訊：10 萬 token/天
    "group": 50_000,            # 一般群組：5 萬/天
    "nightly": 30_000,          # 夜間任務：3 萬/天
}


class PerTenantLimiter:
    """群組級 token 預算隔離.

    每個 session_id 維護獨立的 daily token bucket，
    防止單一群組佔滿全局 quota。
    """

    def __init__(
        self,
        limits: Optional[Dict[str, int]] = None,
        global_daily: int = 200_000,
    ):
        self._limits = limits or dict(DEFAULT_TENANT_LIMITS)
        self._global_daily = global_daily
        self._buckets: Dict[str, TenantBucket] = {}
        self._global_used: int = 0
        self._today: str = ""

    def _ensure_today(self) -> None:
        """每日重置."""
        from datetime import date
        today = date.today().isoformat()
        if today != self._today:
            self._today = today
            self._global_used = 0
            for b in self._buckets.values():
                b.used_today = 0
                b.last_reset = today
            logger.info(f"[TenantLimiter] daily reset: {today}")

    def _get_bucket(self, session_id: str) -> TenantBucket:
        self._ensure_today()
        if session_id not in self._buckets:
            # 根據 session 類型決定限額
            if "owner" in session_id or "dm_6969045906" in session_id:
                limit = self._limits.get("owner_private", 100_000)
            elif "group" in session_id:
                limit = self._limits.get("group", 50_000)
            else:
                limit = self._limits.get("nightly", 30_000)
            self._buckets[session_id] = TenantBucket(
                daily_limit=limit, last_reset=self._today
            )
        return self._buckets[session_id]

    def check(self, session_id: str, estimated_tokens: int = 1000) -> bool:
        """檢查是否允許此 session 消耗 token.

        Returns:
            True = 允許, False = 超額
        """
        self._ensure_today()
        bucket = self._get_bucket(session_id)

        # 群組級檢查
        if bucket.used_today + estimated_tokens > bucket.daily_limit:
            logger.warning(
                f"[TenantLimiter] {session_id} daily limit reached: "
                f"{bucket.used_today}/{bucket.daily_limit}"
            )
            return False

        # 全局檢查
        if self._global_used + estimated_tokens > self._global_daily:
            logger.warning(
                f"[TenantLimiter] global daily limit reached: "
                f"{self._global_used}/{self._global_daily}"
            )
            return False

        return True

    def consume(self, session_id: str, tokens: int) -> None:
        """記錄 token 消耗."""
        self._ensure_today()
        bucket = self._get_bucket(session_id)
        bucket.used_today += tokens
        self._global_used += tokens

    def get_status(self, session_id: str) -> Dict[str, Any]:
        """取得某 session 的預算狀態."""
        self._ensure_today()
        bucket = self._get_bucket(session_id)
        return {
            "session_id": session_id,
            "daily_limit": bucket.daily_limit,
            "used_today": bucket.used_today,
            "remaining": bucket.remaining,
            "usage_pct": round(bucket.usage_pct * 100, 1),
            "global_used": self._global_used,
            "global_limit": self._global_daily,
        }

    def get_all_status(self) -> Dict[str, Any]:
        """取得所有 session 的預算概覽."""
        self._ensure_today()
        return {
            "global": {
                "used": self._global_used,
                "limit": self._global_daily,
                "pct": round(self._global_used / self._global_daily * 100, 1)
                if self._global_daily > 0 else 0,
            },
            "tenants": {
                sid: {
                    "used": b.used_today,
                    "limit": b.daily_limit,
                    "pct": round(b.usage_pct * 100, 1),
                }
                for sid, b in self._buckets.items()
            },
        }


# ═══════════════════════════════════════════
# 4. Model Degrader
# ═══════════════════════════════════════════

# 降級路徑：更貴的 → 更便宜的
_DEGRADATION_PATH = {
    "claude-opus-4-6": "claude-sonnet-4-20250514",
    "claude-sonnet-4-20250514": "claude-haiku-4-5-20251001",
    "claude-haiku-4-5-20251001": None,  # 最底層，無法再降
}

# 優先度對應的允許降級深度
_PRIORITY_MAX_DEGRADE = {
    0: 1,  # P0 (owner): 最多降一級
    1: 2,  # P1 (group): 最多降兩級
    2: 2,  # P2 (nightly): 最多降兩級
}


class ModelDegrader:
    """撞 rate limit 或預算不足時的 model 降級策略."""

    def __init__(self):
        self._degradation_count: int = 0

    def degrade(
        self,
        current_model: str,
        priority: int = 1,
        reason: str = "rate_limit",
    ) -> Optional[str]:
        """嘗試降級到更便宜的模型.

        Args:
            current_model: 當前模型 ID
            priority: 訊息優先度（0=owner, 1=group, 2=nightly）
            reason: 降級原因

        Returns:
            降級後的模型 ID，None 表示無法再降
        """
        max_steps = _PRIORITY_MAX_DEGRADE.get(priority, 1)
        model = current_model
        steps = 0

        while steps < max_steps:
            next_model = _DEGRADATION_PATH.get(model)
            if next_model is None:
                break
            model = next_model
            steps += 1

        if model == current_model:
            logger.warning(
                f"[Degrader] cannot degrade further: {current_model} "
                f"(priority={priority}, reason={reason})"
            )
            return None

        self._degradation_count += 1
        logger.info(
            f"[Degrader] {current_model} → {model} "
            f"(priority={priority}, reason={reason}, "
            f"total_degradations={self._degradation_count})"
        )
        return model

    @property
    def degradation_count(self) -> int:
        return self._degradation_count


# ═══════════════════════════════════════════
# 5. 全局單例（Gateway 啟動時初始化一次）
# ═══════════════════════════════════════════

_backoff = ExponentialBackoff()
_monitor = RateLimitMonitor()
_tenant_limiter = PerTenantLimiter()
_degrader = ModelDegrader()


def get_backoff() -> ExponentialBackoff:
    return _backoff


def get_monitor() -> RateLimitMonitor:
    return _monitor


def get_tenant_limiter() -> PerTenantLimiter:
    return _tenant_limiter


def get_degrader() -> ModelDegrader:
    return _degrader
