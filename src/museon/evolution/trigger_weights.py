"""Trigger Weights — 13 種演化觸發機制與權重系統.

設計原則：
  - 13 種觸發型態，涵蓋統計、時間、閾值、餘裕、異常、
    失敗、跨域、行為位移、環境壓力、休眠反彈、社交、季節、熵
  - 每個觸發器有獨立權重、閾值、冷卻時間
  - 最終分數 = Σ(weight_i × factor_i) × vitality_modifier
  - vitality_modifier 由 TokenBudget 健康度 + HealthCheck 共同決定
  - 零 LLM 依賴，純 CPU 啟發式
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 觸發類型
# ═══════════════════════════════════════════


class TriggerType(Enum):
    """13 種演化觸發型態."""

    # 原有 4 種
    STAT_ACCUMULATION = "stat_accumulation"      # 1. 量變→質變
    TIME_CYCLE = "time_cycle"                     # 2. 晝夜/週期節律
    THRESHOLD_BREACH = "threshold_breach"         # 3. 臨界值突破
    SURPLUS_BASED = "surplus_based"               # 4. 餘裕→探索

    # 新增 9 種
    ANOMALY_DRIVEN = "anomaly_driven"             # 5. 異常驅動→適應
    FAILURE_CASCADE = "failure_cascade"            # 6. 失敗連鎖→深層重構
    CROSS_DOMAIN = "cross_domain"                 # 7. 跨域共振→新組合
    USER_BEHAVIOR_SHIFT = "user_behavior_shift"   # 8. 使用者行為位移
    ENV_PRESSURE = "env_pressure"                 # 9. 環境壓力→優化
    DORMANCY_REBOUND = "dormancy_rebound"         # 10. 休眠反彈→學習加速
    SOCIAL_FEEDBACK = "social_feedback"           # 11. 社交反饋→行為調整
    SEASONAL_PATTERN = "seasonal_pattern"         # 12. 季節性模式預載
    ENTROPY_ALARM = "entropy_alarm"               # 13. 熵增警報→整理


# ═══════════════════════════════════════════
# 觸發器設定
# ═══════════════════════════════════════════


@dataclass
class TriggerConfig:
    """單個觸發器的設定."""

    trigger_type: str
    weight: float = 1.0           # 權重（影響最終分數）
    threshold: float = 0.5        # 啟動門檻
    cooldown_seconds: int = 3600  # 冷卻時間（秒）
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 預設權重表
DEFAULT_TRIGGER_CONFIGS: Dict[str, TriggerConfig] = {
    TriggerType.STAT_ACCUMULATION.value: TriggerConfig(
        trigger_type=TriggerType.STAT_ACCUMULATION.value,
        weight=1.2, threshold=0.6, cooldown_seconds=7200,
    ),
    TriggerType.TIME_CYCLE.value: TriggerConfig(
        trigger_type=TriggerType.TIME_CYCLE.value,
        weight=0.8, threshold=0.3, cooldown_seconds=14400,
    ),
    TriggerType.THRESHOLD_BREACH.value: TriggerConfig(
        trigger_type=TriggerType.THRESHOLD_BREACH.value,
        weight=1.5, threshold=0.8, cooldown_seconds=1800,
    ),
    TriggerType.SURPLUS_BASED.value: TriggerConfig(
        trigger_type=TriggerType.SURPLUS_BASED.value,
        weight=0.7, threshold=0.4, cooldown_seconds=3600,
    ),
    TriggerType.ANOMALY_DRIVEN.value: TriggerConfig(
        trigger_type=TriggerType.ANOMALY_DRIVEN.value,
        weight=1.3, threshold=0.5, cooldown_seconds=1800,
    ),
    TriggerType.FAILURE_CASCADE.value: TriggerConfig(
        trigger_type=TriggerType.FAILURE_CASCADE.value,
        weight=1.8, threshold=0.7, cooldown_seconds=3600,
    ),
    TriggerType.CROSS_DOMAIN.value: TriggerConfig(
        trigger_type=TriggerType.CROSS_DOMAIN.value,
        weight=1.4, threshold=0.6, cooldown_seconds=7200,
    ),
    TriggerType.USER_BEHAVIOR_SHIFT.value: TriggerConfig(
        trigger_type=TriggerType.USER_BEHAVIOR_SHIFT.value,
        weight=1.1, threshold=0.5, cooldown_seconds=86400,
    ),
    TriggerType.ENV_PRESSURE.value: TriggerConfig(
        trigger_type=TriggerType.ENV_PRESSURE.value,
        weight=1.6, threshold=0.7, cooldown_seconds=1800,
    ),
    TriggerType.DORMANCY_REBOUND.value: TriggerConfig(
        trigger_type=TriggerType.DORMANCY_REBOUND.value,
        weight=0.9, threshold=0.4, cooldown_seconds=43200,
    ),
    TriggerType.SOCIAL_FEEDBACK.value: TriggerConfig(
        trigger_type=TriggerType.SOCIAL_FEEDBACK.value,
        weight=0.8, threshold=0.3, cooldown_seconds=7200,
    ),
    TriggerType.SEASONAL_PATTERN.value: TriggerConfig(
        trigger_type=TriggerType.SEASONAL_PATTERN.value,
        weight=0.6, threshold=0.3, cooldown_seconds=86400,
    ),
    TriggerType.ENTROPY_ALARM.value: TriggerConfig(
        trigger_type=TriggerType.ENTROPY_ALARM.value,
        weight=1.5, threshold=0.6, cooldown_seconds=3600,
    ),
}


# ═══════════════════════════════════════════
# 觸發評估結果
# ═══════════════════════════════════════════


@dataclass
class TriggerResult:
    """觸發評估結果."""

    total_score: float = 0.0
    vitality_modifier: float = 1.0
    fired_triggers: List[str] = field(default_factory=list)
    details: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def should_evolve(self) -> bool:
        """是否應該觸發演化."""
        return self.total_score > 0 and len(self.fired_triggers) > 0


# ═══════════════════════════════════════════
# TriggerEngine — 觸發引擎
# ═══════════════════════════════════════════


class TriggerEngine:
    """13 種觸發機制的評估引擎.

    公式：trigger_score = Σ(weight_i × factor_i) × vitality_modifier

    vitality_modifier:
      - reserve 充足 + 健康良好 → > 1.0（積極演化）
      - reserve 枯竭 + 健康不佳 → < 1.0（保守模式）
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._configs: Dict[str, TriggerConfig] = {}
        self._last_fired: Dict[str, float] = {}  # trigger_type → last fired timestamp
        self._data_dir = data_dir

        # 載入設定（或使用預設值）
        self._load_configs()

        logger.info("TriggerEngine 初始化完成，%d 個觸發器", len(self._configs))

    def _load_configs(self) -> None:
        """載入觸發器設定（從檔案或預設值）."""
        config_path = self._data_dir / "_system" / "trigger_configs.json" if self._data_dir else None

        if config_path and config_path.exists():
            try:
                raw = json.loads(config_path.read_text(encoding="utf-8"))
                for key, val in raw.items():
                    self._configs[key] = TriggerConfig(**val)
                return
            except Exception as e:
                logger.warning("觸發器設定載入失敗，使用預設值: %s", e)

        # 使用預設值
        self._configs = {k: TriggerConfig(**asdict(v)) for k, v in DEFAULT_TRIGGER_CONFIGS.items()}

    def save_configs(self) -> None:
        """儲存觸發器設定到檔案."""
        if not self._data_dir:
            return
        config_path = self._data_dir / "_system" / "trigger_configs.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {k: v.to_dict() for k, v in self._configs.items()}
            config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("觸發器設定儲存失敗: %s", e)

    def evaluate(
        self,
        factors: Dict[str, float],
        vitality_modifier: float = 1.0,
    ) -> TriggerResult:
        """評估所有觸發器.

        Args:
            factors: 每個觸發器的因子值，key = TriggerType.value, value = 0.0 ~ 1.0
            vitality_modifier: 生命力係數
                - > 1.0: 積極演化（reserve 充足、健康良好）
                - < 1.0: 保守模式（reserve 枯竭、健康不佳）

        Returns:
            TriggerResult 包含總分數和已觸發的觸發器列表
        """
        now = datetime.now(timezone.utc).timestamp()
        fired: List[str] = []
        details: Dict[str, float] = {}
        weighted_sum = 0.0

        for trigger_type, config in self._configs.items():
            if not config.enabled:
                continue

            factor = factors.get(trigger_type, 0.0)
            if factor < config.threshold:
                continue

            # 冷卻檢查
            last = self._last_fired.get(trigger_type, 0.0)
            if now - last < config.cooldown_seconds:
                continue

            # 計算加權分數
            score = config.weight * factor
            weighted_sum += score
            fired.append(trigger_type)
            details[trigger_type] = round(score, 4)

            # 更新最後觸發時間
            self._last_fired[trigger_type] = now

        total = weighted_sum * vitality_modifier

        result = TriggerResult(
            total_score=round(total, 4),
            vitality_modifier=round(vitality_modifier, 4),
            fired_triggers=fired,
            details=details,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        if fired:
            logger.info(
                "TriggerEngine: %d 個觸發器啟動, total=%.4f, vitality=%.2f, triggers=%s",
                len(fired), total, vitality_modifier, fired,
            )

        return result

    def get_config(self, trigger_type: str) -> Optional[TriggerConfig]:
        """取得某個觸發器的設定."""
        return self._configs.get(trigger_type)

    def update_config(self, trigger_type: str, **kwargs) -> None:
        """更新觸發器設定（MUSEON 自我調整用）."""
        config = self._configs.get(trigger_type)
        if not config:
            return
        for key, val in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, val)
        self.save_configs()

    def reset_cooldown(self, trigger_type: str) -> None:
        """重置冷卻時間."""
        self._last_fired.pop(trigger_type, None)

    def get_status(self) -> Dict[str, Any]:
        """取得所有觸發器狀態."""
        now = datetime.now(timezone.utc).timestamp()
        status = {}
        for trigger_type, config in self._configs.items():
            last = self._last_fired.get(trigger_type, 0.0)
            remaining_cd = max(0, config.cooldown_seconds - (now - last)) if last else 0
            status[trigger_type] = {
                "enabled": config.enabled,
                "weight": config.weight,
                "threshold": config.threshold,
                "cooldown_remaining_s": int(remaining_cd),
            }
        return status
