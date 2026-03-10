"""ParameterTuner — 啟發式參數自動調諧器.

基於累積反饋資料，自動微調系統中的硬編碼啟發式參數。

可調參數群組：
  1. Q-Score 四維權重（understanding/depth/clarity/actionability）
  2. Skill Router RC 乘數
  3. MetaCognition 近似類型映射
  4. Immunity 抗體調整速度

設計原則：
  - 每次調諧週期最多 ±20% 變動（per-cycle cap）
  - 累積漂移超過 15% 時暫停調諧並發出警報
  - 所有變更寫入 JSONL 稽核軌跡
  - 零 ML 依賴 — 純統計調整
  - 所有檔案讀取包裹 try/except
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# 每週期單一參數最大變動比例
PER_CYCLE_CAP = 0.20

# 累積漂移暫停閾值
DRIFT_PAUSE_THRESHOLD = 0.15

# Q-Score 預設權重
DEFAULT_QSCORE_WEIGHTS: Dict[str, float] = {
    "understanding": 0.30,
    "depth": 0.25,
    "clarity": 0.20,
    "actionability": 0.25,
}

# Q-Score 低分維度連續天數閾值
QSCORE_LOW_DIM_DAYS = 7

# Q-Score 權重調整增量
QSCORE_WEIGHT_INCREMENT = 0.02

# Skill Router 預設 RC 乘數
DEFAULT_RC_MULTIPLIER = 5.0
RC_MULTIPLIER_MIN = 2.0
RC_MULTIPLIER_MAX = 8.0
RC_MULTIPLIER_STEP = 0.5

# Skill hit rate 閾值
SKILL_HIT_RATE_LOW = 0.60
SKILL_HIT_RATE_HIGH = 0.85

# MetaCognition 近似類型預設映射
DEFAULT_SIMILAR_TYPES: Dict[str, List[str]] = {
    "acceptance": ["follow_up"],
    "follow_up": ["acceptance", "deepening"],
    "deepening": ["follow_up"],
    "emotional": ["acceptance"],
    "pushback": ["redirect"],
    "redirect": ["pushback", "deepening"],
}

# MetaCognition 調整閾值
METACOG_REMOVE_ACCURACY_THRESHOLD = 0.40
METACOG_ADD_INTERCHANGE_THRESHOLD = 0.60
METACOG_OBSERVATION_DAYS = 14

# Immunity 預設調整速度
DEFAULT_IMMUNITY_SUCCESS_BONUS = 0.10
DEFAULT_IMMUNITY_FAILURE_PENALTY = 0.15

# Immunity 調整閾值
IMMUNITY_FP_RATE_THRESHOLD = 0.30
IMMUNITY_TP_RATE_THRESHOLD = 0.90
IMMUNITY_ADJUSTED_FAILURE_PENALTY = 0.20
IMMUNITY_ADJUSTED_SUCCESS_BONUS = 0.05

# Skill hit rate 統計天數
SKILL_STATS_DAYS = 7


# ═══════════════════════════════════════════
# 資料結構
# ═══════════════════════════════════════════


@dataclass
class ParameterAdjustment:
    """單一參數的調整記錄."""

    parameter_group: str
    parameter_name: str
    old_value: Any
    new_value: Any
    reason: str
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TuningReport:
    """一次調諧週期的報告."""

    timestamp: str
    adjustments: List[ParameterAdjustment] = field(default_factory=list)
    drift_paused: bool = False
    drift_alerts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    skipped_groups: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "timestamp": self.timestamp,
            "adjustments": [a.to_dict() for a in self.adjustments],
            "drift_paused": self.drift_paused,
            "drift_alerts": self.drift_alerts,
            "errors": self.errors,
            "skipped_groups": self.skipped_groups,
            "total_adjustments": len(self.adjustments),
        }
        return result


@dataclass
class TunedParameters:
    """當前已調諧的參數快照."""

    version: int = 1
    last_tuned: str = ""
    qscore_weights: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_QSCORE_WEIGHTS)
    )
    skill_router_rc_multiplier: float = DEFAULT_RC_MULTIPLIER
    metacognition_similar_types: Dict[str, List[str]] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_SIMILAR_TYPES)
    )
    immunity_success_bonus: float = DEFAULT_IMMUNITY_SUCCESS_BONUS
    immunity_failure_penalty: float = DEFAULT_IMMUNITY_FAILURE_PENALTY
    drift_paused: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TunedParameters":
        """從字典建構 TunedParameters."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# ═══════════════════════════════════════════
# 初始值快照（用於漂移計算）
# ═══════════════════════════════════════════

_INITIAL_VALUES: Dict[str, Any] = {
    "qscore_weights.understanding": DEFAULT_QSCORE_WEIGHTS["understanding"],
    "qscore_weights.depth": DEFAULT_QSCORE_WEIGHTS["depth"],
    "qscore_weights.clarity": DEFAULT_QSCORE_WEIGHTS["clarity"],
    "qscore_weights.actionability": DEFAULT_QSCORE_WEIGHTS["actionability"],
    "skill_router_rc_multiplier": DEFAULT_RC_MULTIPLIER,
    "immunity_success_bonus": DEFAULT_IMMUNITY_SUCCESS_BONUS,
    "immunity_failure_penalty": DEFAULT_IMMUNITY_FAILURE_PENALTY,
}


# ═══════════════════════════════════════════
# ParameterTuner
# ═══════════════════════════════════════════


class ParameterTuner:
    """啟發式參數自動調諧器.

    讀取各子系統的歷史反饋資料，對硬編碼啟發式參數進行
    小幅度統計調整。所有調整受 per-cycle cap 和漂移上限保護。

    使用方式：
        tuner = ParameterTuner(workspace=Path("/path/to/workspace"))
        report = tuner.tune_weekly()
    """

    def __init__(self, workspace: Path) -> None:
        """初始化 ParameterTuner.

        Args:
            workspace: MUSEON 工作目錄路徑
        """
        self._workspace = Path(workspace)
        self._params: TunedParameters = TunedParameters()

        # 檔案路徑
        self._params_path = (
            self._workspace / "_system" / "evolution" / "tuned_parameters.json"
        )
        self._audit_path = (
            self._workspace / "_system" / "evolution" / "tuning_audit.jsonl"
        )

        # 載入已儲存的參數
        self._load_parameters()

    # ═══════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════

    def _load_parameters(self) -> None:
        """從磁碟載入已調諧的參數.

        若檔案不存在或讀取失敗，使用預設值。
        """
        try:
            if self._params_path.exists():
                raw = json.loads(
                    self._params_path.read_text(encoding="utf-8")
                )
                self._params = TunedParameters.from_dict(raw)
                logger.info(
                    "ParameterTuner: 載入已調諧參數，版本 %d，"
                    "上次調諧 %s",
                    self._params.version,
                    self._params.last_tuned,
                )
            else:
                logger.info("ParameterTuner: 無已儲存參數，使用預設值")
        except Exception as e:
            logger.warning("ParameterTuner: 參數載入失敗，使用預設值: %s", e)
            self._params = TunedParameters()

    def _save_parameters(self) -> None:
        """將當前參數寫入磁碟."""
        try:
            self._params_path.parent.mkdir(parents=True, exist_ok=True)
            self._params_path.write_text(
                json.dumps(
                    self._params.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("ParameterTuner: 參數儲存失敗: %s", e)

    def _append_audit(self, entry: Dict[str, Any]) -> None:
        """將一筆稽核記錄追加到 JSONL 檔案."""
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with open(self._audit_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.error("ParameterTuner: 稽核記錄寫入失敗: %s", e)

    # ═══════════════════════════════════════════
    # 資料讀取工具
    # ═══════════════════════════════════════════

    def _read_jsonl(self, path: Path, days: int = 7) -> List[Dict]:
        """讀取 JSONL 檔案，僅保留指定天數內的記錄.

        Args:
            path: JSONL 檔案路徑
            days: 保留最近幾天的記錄

        Returns:
            解析後的記錄列表
        """
        records: List[Dict] = []
        if not path.exists():
            logger.debug("ParameterTuner: 檔案不存在: %s", path)
            return records

        cutoff = datetime.now(TZ8) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # 嘗試用 timestamp 欄位過濾
                    ts = record.get("timestamp", "")
                    if isinstance(ts, str) and ts and ts >= cutoff_str:
                        records.append(record)
                    elif not ts:
                        # 無時間戳的記錄全部保留
                        records.append(record)
        except Exception as e:
            logger.warning(
                "ParameterTuner: JSONL 讀取失敗 %s: %s", path, e
            )

        return records

    def _read_json(self, path: Path) -> Dict:
        """讀取 JSON 檔案.

        Args:
            path: JSON 檔案路徑

        Returns:
            解析後的字典，失敗時回傳空字典
        """
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(
                "ParameterTuner: JSON 讀取失敗 %s: %s", path, e
            )
            return {}

    # ═══════════════════════════════════════════
    # 安全機制
    # ═══════════════════════════════════════════

    def _clamp_change(
        self,
        old_value: float,
        new_value: float,
        cap: float = PER_CYCLE_CAP,
    ) -> float:
        """限制單次變動不超過 ±cap 比例.

        Args:
            old_value: 原始值
            new_value: 期望新值
            cap: 最大變動比例（預設 0.20）

        Returns:
            受限後的新值
        """
        if old_value == 0:
            return new_value

        max_delta = abs(old_value) * cap
        delta = new_value - old_value

        if abs(delta) > max_delta:
            clamped = old_value + (max_delta if delta > 0 else -max_delta)
            logger.info(
                "ParameterTuner: 變動受限 %.4f → %.4f（原始目標 %.4f）",
                old_value,
                clamped,
                new_value,
            )
            return clamped

        return new_value

    def _check_drift(self, param_key: str, current_value: float) -> Optional[str]:
        """檢查單一參數的累積漂移是否超過閾值.

        Args:
            param_key: 參數鍵名（如 "qscore_weights.understanding"）
            current_value: 當前值

        Returns:
            漂移警報訊息，若未超標則回傳 None
        """
        initial = _INITIAL_VALUES.get(param_key)
        if initial is None or initial == 0:
            return None

        drift = abs(current_value - initial) / abs(initial)
        if drift > DRIFT_PAUSE_THRESHOLD:
            msg = (
                f"參數 {param_key} 累積漂移 {drift:.1%} "
                f"超過閾值 {DRIFT_PAUSE_THRESHOLD:.0%}"
                f"（初始={initial}, 當前={current_value}）"
            )
            logger.warning("ParameterTuner: %s", msg)
            return msg

        return None

    # ═══════════════════════════════════════════
    # 群組 1：Q-Score 權重調諧
    # ═══════════════════════════════════════════

    def _tune_qscore_weights(self, report: TuningReport) -> None:
        """根據 Q-Score 歷史調整四維權重.

        策略：若某維度連續 7+ 天都是最低分者，
        將該維度的權重微調 +0.02，並重新平衡使總和仍為 1.0。
        """
        history_path = (
            self._workspace / "_system" / "eval" / "qscore_history.jsonl"
        )
        records = self._read_jsonl(history_path, days=QSCORE_LOW_DIM_DAYS)

        if len(records) < QSCORE_LOW_DIM_DAYS:
            report.skipped_groups.append(
                f"qscore_weights: 資料不足（{len(records)} 筆，"
                f"需 {QSCORE_LOW_DIM_DAYS} 天）"
            )
            return

        # 按日期聚合：每天找出最低分維度
        daily_lowest: Dict[str, str] = {}  # date → lowest dimension
        daily_scores: Dict[str, Dict[str, List[float]]] = {}

        dimensions = ["understanding", "depth", "clarity", "actionability"]

        for rec in records:
            ts = rec.get("timestamp", "")
            if isinstance(ts, str) and len(ts) >= 10:
                day = ts[:10]
            else:
                continue

            if day not in daily_scores:
                daily_scores[day] = {d: [] for d in dimensions}

            for dim in dimensions:
                val = rec.get(dim)
                if isinstance(val, (int, float)):
                    daily_scores[day][dim].append(val)

        # 計算每日各維度均值，找出最低分維度
        for day, dim_scores in daily_scores.items():
            dim_means: Dict[str, float] = {}
            for dim, values in dim_scores.items():
                if values:
                    dim_means[dim] = sum(values) / len(values)

            if dim_means:
                lowest_dim = min(dim_means, key=dim_means.get)  # type: ignore[arg-type]
                daily_lowest[day] = lowest_dim

        if len(daily_lowest) < QSCORE_LOW_DIM_DAYS:
            report.skipped_groups.append(
                f"qscore_weights: 有效天數不足（{len(daily_lowest)} 天）"
            )
            return

        # 統計各維度成為最低分的天數
        lowest_counts: Dict[str, int] = {d: 0 for d in dimensions}
        for dim in daily_lowest.values():
            if dim in lowest_counts:
                lowest_counts[dim] += 1

        # 找出連續 7+ 天都是最低分的維度
        consistent_lowest: Optional[str] = None
        for dim, count in lowest_counts.items():
            if count >= QSCORE_LOW_DIM_DAYS:
                consistent_lowest = dim
                break

        if consistent_lowest is None:
            logger.info("ParameterTuner: Q-Score 權重無需調整（無持續最低維度）")
            return

        # 微調該維度權重 +0.02
        weights = dict(self._params.qscore_weights)
        old_weight = weights[consistent_lowest]
        new_weight = old_weight + QSCORE_WEIGHT_INCREMENT

        # 受限檢查
        new_weight = self._clamp_change(old_weight, new_weight)

        # 重新平衡：其他維度等比例縮減
        remaining_budget = 1.0 - new_weight
        other_dims = [d for d in dimensions if d != consistent_lowest]
        other_sum = sum(weights[d] for d in other_dims)

        if other_sum > 0:
            scale = remaining_budget / other_sum
            for d in other_dims:
                weights[d] = round(weights[d] * scale, 4)
        weights[consistent_lowest] = round(new_weight, 4)

        # 微修浮點誤差，確保加總精確為 1.0
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-6:
            diff = 1.0 - total
            # 把誤差加到最大的那個維度
            max_dim = max(weights, key=weights.get)  # type: ignore[arg-type]
            weights[max_dim] = round(weights[max_dim] + diff, 4)

        # 漂移檢查
        for dim in dimensions:
            alert = self._check_drift(
                f"qscore_weights.{dim}", weights[dim]
            )
            if alert:
                report.drift_alerts.append(alert)
                report.drift_paused = True

        if report.drift_paused:
            logger.warning(
                "ParameterTuner: Q-Score 權重漂移超標，暫停調諧"
            )
            return

        # 記錄調整
        adjustment = ParameterAdjustment(
            parameter_group="qscore_weights",
            parameter_name=consistent_lowest,
            old_value=dict(self._params.qscore_weights),
            new_value=weights,
            reason=(
                f"維度 '{consistent_lowest}' 連續 {lowest_counts[consistent_lowest]} 天"
                f"為最低分，權重 {old_weight:.4f} → {new_weight:.4f}"
            ),
            timestamp=datetime.now(TZ8).isoformat(),
        )
        report.adjustments.append(adjustment)

        self._params.qscore_weights = weights
        logger.info(
            "ParameterTuner: Q-Score 權重已調整，'%s' %s → %s",
            consistent_lowest,
            old_weight,
            new_weight,
        )

    # ═══════════════════════════════════════════
    # 群組 2：Skill Router RC 乘數調諧
    # ═══════════════════════════════════════════

    def _tune_rc_multiplier(self, report: TuningReport) -> None:
        """根據 skill_hit_rate 調整 RC 乘數.

        策略：
          - hit_rate < 60% 連續 7 天 → RC 乘數 -0.5（下限 2.0）
          - hit_rate > 85% 連續 7 天 → RC 乘數 +0.5（上限 8.0）
        """
        usage_log_path = self._workspace / "skill_usage_log.jsonl"
        records = self._read_jsonl(usage_log_path, days=SKILL_STATS_DAYS)

        if not records:
            report.skipped_groups.append(
                "skill_router_rc_multiplier: 無 skill_usage_log 資料"
            )
            return

        # 按日聚合 hit/miss
        daily_hits: Dict[str, Dict[str, int]] = {}  # date → {"hits": n, "total": n}

        for rec in records:
            ts = rec.get("timestamp", "")
            if isinstance(ts, str) and len(ts) >= 10:
                day = ts[:10]
            else:
                continue

            if day not in daily_hits:
                daily_hits[day] = {"hits": 0, "total": 0}

            daily_hits[day]["total"] += 1
            if rec.get("hit", False) or rec.get("matched", False):
                daily_hits[day]["hits"] += 1

        if len(daily_hits) < SKILL_STATS_DAYS:
            report.skipped_groups.append(
                f"skill_router_rc_multiplier: 有效天數不足"
                f"（{len(daily_hits)} 天，需 {SKILL_STATS_DAYS} 天）"
            )
            return

        # 計算每日 hit_rate
        daily_rates: List[float] = []
        for day_data in daily_hits.values():
            total = day_data["total"]
            if total > 0:
                daily_rates.append(day_data["hits"] / total)

        if not daily_rates:
            return

        avg_hit_rate = sum(daily_rates) / len(daily_rates)

        old_value = self._params.skill_router_rc_multiplier
        new_value = old_value

        reason = ""
        if avg_hit_rate < SKILL_HIT_RATE_LOW:
            new_value = max(RC_MULTIPLIER_MIN, old_value - RC_MULTIPLIER_STEP)
            reason = (
                f"skill_hit_rate 平均 {avg_hit_rate:.1%} "
                f"< {SKILL_HIT_RATE_LOW:.0%}，降低 RC 乘數"
            )
        elif avg_hit_rate > SKILL_HIT_RATE_HIGH:
            new_value = min(RC_MULTIPLIER_MAX, old_value + RC_MULTIPLIER_STEP)
            reason = (
                f"skill_hit_rate 平均 {avg_hit_rate:.1%} "
                f"> {SKILL_HIT_RATE_HIGH:.0%}，提高 RC 乘數"
            )

        if new_value == old_value:
            logger.info(
                "ParameterTuner: RC 乘數無需調整"
                "（hit_rate=%.1f%%）",
                avg_hit_rate * 100,
            )
            return

        # 受限檢查
        new_value = self._clamp_change(old_value, new_value)

        # 漂移檢查
        alert = self._check_drift("skill_router_rc_multiplier", new_value)
        if alert:
            report.drift_alerts.append(alert)
            report.drift_paused = True
            return

        adjustment = ParameterAdjustment(
            parameter_group="skill_router_rc_multiplier",
            parameter_name="rc_multiplier",
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            timestamp=datetime.now(TZ8).isoformat(),
        )
        report.adjustments.append(adjustment)

        self._params.skill_router_rc_multiplier = new_value
        logger.info(
            "ParameterTuner: RC 乘數 %.1f → %.1f（hit_rate=%.1f%%）",
            old_value,
            new_value,
            avg_hit_rate * 100,
        )

    # ═══════════════════════════════════════════
    # 群組 3：MetaCognition similar_types 調諧
    # ═══════════════════════════════════════════

    def _tune_similar_types(self, report: TuningReport) -> None:
        """根據預測準確率調整近似類型映射.

        策略：
          - 某配對準確率 < 40%（14 天）→ 從 similar set 移除
          - 兩類型互換率 > 60%（14 天）→ 加入 similar set
        """
        accuracy_path = (
            self._workspace
            / "_system"
            / "metacognition"
            / "accuracy_stats.json"
        )
        stats = self._read_json(accuracy_path)

        if not stats:
            report.skipped_groups.append(
                "metacognition_similar_types: 無 accuracy_stats 資料"
            )
            return

        pair_accuracies = stats.get("pair_accuracies", {})
        confusion_matrix = stats.get("confusion_matrix", {})
        observation_days = stats.get("observation_days", 0)

        if observation_days < METACOG_OBSERVATION_DAYS:
            report.skipped_groups.append(
                f"metacognition_similar_types: 觀察天數不足"
                f"（{observation_days} 天，需 {METACOG_OBSERVATION_DAYS} 天）"
            )
            return

        similar_types = copy.deepcopy(self._params.metacognition_similar_types)
        changed = False

        # 檢查需要移除的配對
        for predicted, similar_list in list(similar_types.items()):
            for actual_type in list(similar_list):
                pair_key = f"{predicted}->{actual_type}"
                accuracy = pair_accuracies.get(pair_key)

                if accuracy is not None and accuracy < METACOG_REMOVE_ACCURACY_THRESHOLD:
                    similar_list.remove(actual_type)
                    changed = True

                    adjustment = ParameterAdjustment(
                        parameter_group="metacognition_similar_types",
                        parameter_name=pair_key,
                        old_value="in_similar_set",
                        new_value="removed",
                        reason=(
                            f"配對 {pair_key} 準確率 {accuracy:.1%} "
                            f"< {METACOG_REMOVE_ACCURACY_THRESHOLD:.0%}，移除"
                        ),
                        timestamp=datetime.now(TZ8).isoformat(),
                    )
                    report.adjustments.append(adjustment)
                    logger.info(
                        "ParameterTuner: 移除近似類型 %s（準確率 %.1f%%）",
                        pair_key,
                        accuracy * 100,
                    )

        # 檢查需要新增的配對（從混淆矩陣中發現高互換率）
        for type_a, confusions in confusion_matrix.items():
            if not isinstance(confusions, dict):
                continue
            for type_b, interchange_rate in confusions.items():
                if type_a == type_b:
                    continue
                if not isinstance(interchange_rate, (int, float)):
                    continue
                if interchange_rate <= METACOG_ADD_INTERCHANGE_THRESHOLD:
                    continue

                # 檢查是否已在 similar set
                existing = similar_types.get(type_a, [])
                if type_b in existing:
                    continue

                # 新增到 similar set
                if type_a not in similar_types:
                    similar_types[type_a] = []
                similar_types[type_a].append(type_b)
                changed = True

                pair_key = f"{type_a}->{type_b}"
                adjustment = ParameterAdjustment(
                    parameter_group="metacognition_similar_types",
                    parameter_name=pair_key,
                    old_value="not_in_similar_set",
                    new_value="added",
                    reason=(
                        f"配對 {pair_key} 互換率 {interchange_rate:.1%} "
                        f"> {METACOG_ADD_INTERCHANGE_THRESHOLD:.0%}，新增"
                    ),
                    timestamp=datetime.now(TZ8).isoformat(),
                )
                report.adjustments.append(adjustment)
                logger.info(
                    "ParameterTuner: 新增近似類型 %s（互換率 %.1f%%）",
                    pair_key,
                    interchange_rate * 100,
                )

        if changed:
            self._params.metacognition_similar_types = similar_types

    # ═══════════════════════════════════════════
    # 群組 4：Immunity 抗體調整速度
    # ═══════════════════════════════════════════

    def _tune_immunity_speed(self, report: TuningReport) -> None:
        """根據免疫事件統計調整抗體調整速度.

        策略：
          - false positive rate > 30% → failure_penalty 增至 0.20
          - true positive rate > 90% → success_bonus 降至 0.05
        """
        events_path = (
            self._workspace / "_system" / "immunity" / "events.jsonl"
        )
        records = self._read_jsonl(events_path, days=SKILL_STATS_DAYS)

        if not records:
            report.skipped_groups.append(
                "immunity_speed: 無 immunity events 資料"
            )
            return

        # 統計 true positive / false positive
        true_positives = 0
        false_positives = 0
        total_detections = 0

        for rec in records:
            event_type = rec.get("event_type", "")
            if event_type in ("detection", "match", "trigger"):
                total_detections += 1
                resolved = rec.get("resolved", False)
                auto_resolved = rec.get("auto_resolved", False)
                was_valid = rec.get("was_valid_threat", True)

                if was_valid or resolved or auto_resolved:
                    true_positives += 1
                else:
                    false_positives += 1

        if total_detections < 5:
            report.skipped_groups.append(
                f"immunity_speed: 偵測事件不足"
                f"（{total_detections} 筆，需至少 5 筆）"
            )
            return

        fp_rate = false_positives / total_detections if total_detections > 0 else 0
        tp_rate = true_positives / total_detections if total_detections > 0 else 0

        adjustments_made = False

        # 檢查 false positive rate
        if fp_rate > IMMUNITY_FP_RATE_THRESHOLD:
            old_penalty = self._params.immunity_failure_penalty
            new_penalty = IMMUNITY_ADJUSTED_FAILURE_PENALTY

            new_penalty = self._clamp_change(old_penalty, new_penalty)

            # 漂移檢查
            alert = self._check_drift("immunity_failure_penalty", new_penalty)
            if alert:
                report.drift_alerts.append(alert)
                report.drift_paused = True
                return

            if new_penalty != old_penalty:
                adjustment = ParameterAdjustment(
                    parameter_group="immunity_speed",
                    parameter_name="failure_penalty",
                    old_value=old_penalty,
                    new_value=new_penalty,
                    reason=(
                        f"false positive rate {fp_rate:.1%} "
                        f"> {IMMUNITY_FP_RATE_THRESHOLD:.0%}，"
                        f"增加失敗懲罰 {old_penalty} → {new_penalty}"
                    ),
                    timestamp=datetime.now(TZ8).isoformat(),
                )
                report.adjustments.append(adjustment)
                self._params.immunity_failure_penalty = new_penalty
                adjustments_made = True
                logger.info(
                    "ParameterTuner: immunity failure_penalty "
                    "%.2f → %.2f（FP rate=%.1f%%）",
                    old_penalty,
                    new_penalty,
                    fp_rate * 100,
                )

        # 檢查 true positive rate
        if tp_rate > IMMUNITY_TP_RATE_THRESHOLD:
            old_bonus = self._params.immunity_success_bonus
            new_bonus = IMMUNITY_ADJUSTED_SUCCESS_BONUS

            new_bonus = self._clamp_change(old_bonus, new_bonus)

            # 漂移檢查
            alert = self._check_drift("immunity_success_bonus", new_bonus)
            if alert:
                report.drift_alerts.append(alert)
                report.drift_paused = True
                return

            if new_bonus != old_bonus:
                adjustment = ParameterAdjustment(
                    parameter_group="immunity_speed",
                    parameter_name="success_bonus",
                    old_value=old_bonus,
                    new_value=new_bonus,
                    reason=(
                        f"true positive rate {tp_rate:.1%} "
                        f"> {IMMUNITY_TP_RATE_THRESHOLD:.0%}，"
                        f"降低成功獎勵 {old_bonus} → {new_bonus}"
                    ),
                    timestamp=datetime.now(TZ8).isoformat(),
                )
                report.adjustments.append(adjustment)
                self._params.immunity_success_bonus = new_bonus
                adjustments_made = True
                logger.info(
                    "ParameterTuner: immunity success_bonus "
                    "%.2f → %.2f（TP rate=%.1f%%）",
                    old_bonus,
                    new_bonus,
                    tp_rate * 100,
                )

        if not adjustments_made:
            logger.info(
                "ParameterTuner: immunity 參數無需調整"
                "（FP=%.1f%%, TP=%.1f%%）",
                fp_rate * 100,
                tp_rate * 100,
            )

    # ═══════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════

    def tune_weekly(self) -> TuningReport:
        """執行一次完整的每週調諧循環.

        依序調整四個參數群組，受漂移保護。
        任一群組觸發漂移警報後，後續群組仍會繼續嘗試，
        但漂移狀態會被記錄且參數不會被修改。

        Returns:
            TuningReport 包含所有調整記錄和警報
        """
        now = datetime.now(TZ8)
        report = TuningReport(timestamp=now.isoformat())

        logger.info("ParameterTuner: 開始每週調諧 — %s", now.isoformat())

        # 若之前已暫停，檢查是否仍應暫停
        if self._params.drift_paused:
            drift_report = self.get_drift_report()
            has_excessive_drift = any(
                v.get("exceeded", False)
                for v in drift_report.get("parameters", {}).values()
            )
            if has_excessive_drift:
                report.drift_paused = True
                report.drift_alerts.append(
                    "上次調諧已暫停且漂移仍超標，跳過本次調諧"
                )
                logger.warning(
                    "ParameterTuner: 漂移仍超標，跳過本次調諧"
                )
                self._append_audit(report.to_dict())
                return report
            else:
                # 漂移已恢復，解除暫停
                self._params.drift_paused = False
                logger.info("ParameterTuner: 漂移已恢復正常，恢復調諧")

        # 依序執行四個群組調諧
        tuning_steps = [
            ("qscore_weights", self._tune_qscore_weights),
            ("skill_router_rc_multiplier", self._tune_rc_multiplier),
            ("metacognition_similar_types", self._tune_similar_types),
            ("immunity_speed", self._tune_immunity_speed),
        ]

        for group_name, tune_fn in tuning_steps:
            try:
                tune_fn(report)
            except Exception as e:
                error_msg = f"{group_name}: 調諧異常 — {e}"
                report.errors.append(error_msg)
                logger.error("ParameterTuner: %s", error_msg)

        # 更新元資料
        self._params.last_tuned = now.isoformat()
        self._params.version += 1

        if report.drift_paused:
            self._params.drift_paused = True

        # 儲存
        self._save_parameters()

        # 稽核記錄
        self._append_audit(report.to_dict())

        logger.info(
            "ParameterTuner: 調諧完成 — %d 項調整, %d 項警報, %d 項錯誤",
            len(report.adjustments),
            len(report.drift_alerts),
            len(report.errors),
        )

        return report

    # ═══════════════════════════════════════════
    # 查詢介面
    # ═══════════════════════════════════════════

    def get_current_parameters(self) -> Dict[str, Any]:
        """取得當前參數值.

        Returns:
            包含所有參數群組的字典
        """
        return self._params.to_dict()

    def get_drift_report(self) -> Dict[str, Any]:
        """取得各參數相對初始值的累積漂移報告.

        Returns:
            {
                "timestamp": str,
                "drift_paused": bool,
                "parameters": {
                    "param_key": {
                        "initial": float,
                        "current": float,
                        "drift_pct": float,
                        "exceeded": bool
                    }
                }
            }
        """
        params_report: Dict[str, Dict[str, Any]] = {}

        # 數值型參數漂移
        numeric_params: Dict[str, float] = {
            "qscore_weights.understanding": self._params.qscore_weights.get(
                "understanding", DEFAULT_QSCORE_WEIGHTS["understanding"]
            ),
            "qscore_weights.depth": self._params.qscore_weights.get(
                "depth", DEFAULT_QSCORE_WEIGHTS["depth"]
            ),
            "qscore_weights.clarity": self._params.qscore_weights.get(
                "clarity", DEFAULT_QSCORE_WEIGHTS["clarity"]
            ),
            "qscore_weights.actionability": self._params.qscore_weights.get(
                "actionability", DEFAULT_QSCORE_WEIGHTS["actionability"]
            ),
            "skill_router_rc_multiplier": self._params.skill_router_rc_multiplier,
            "immunity_success_bonus": self._params.immunity_success_bonus,
            "immunity_failure_penalty": self._params.immunity_failure_penalty,
        }

        for key, current in numeric_params.items():
            initial = _INITIAL_VALUES.get(key, current)
            drift = (
                abs(current - initial) / abs(initial)
                if initial != 0
                else 0.0
            )
            params_report[key] = {
                "initial": initial,
                "current": current,
                "drift_pct": round(drift, 4),
                "exceeded": drift > DRIFT_PAUSE_THRESHOLD,
            }

        return {
            "timestamp": datetime.now(TZ8).isoformat(),
            "drift_paused": self._params.drift_paused,
            "parameters": params_report,
        }

    def rollback(self, parameter_group: str) -> bool:
        """將指定參數群組重設為預設值.

        Args:
            parameter_group: 參數群組名稱，可為：
                - "qscore_weights"
                - "skill_router_rc_multiplier"
                - "metacognition_similar_types"
                - "immunity_speed"
                - "all"（重設所有群組）

        Returns:
            True = 重設成功, False = 群組名稱無效
        """
        now = datetime.now(TZ8).isoformat()
        rolled_back = False

        if parameter_group in ("qscore_weights", "all"):
            old = dict(self._params.qscore_weights)
            self._params.qscore_weights = dict(DEFAULT_QSCORE_WEIGHTS)
            self._append_audit({
                "action": "rollback",
                "parameter_group": "qscore_weights",
                "old_value": old,
                "new_value": dict(DEFAULT_QSCORE_WEIGHTS),
                "timestamp": now,
            })
            rolled_back = True

        if parameter_group in ("skill_router_rc_multiplier", "all"):
            old_val = self._params.skill_router_rc_multiplier
            self._params.skill_router_rc_multiplier = DEFAULT_RC_MULTIPLIER
            self._append_audit({
                "action": "rollback",
                "parameter_group": "skill_router_rc_multiplier",
                "old_value": old_val,
                "new_value": DEFAULT_RC_MULTIPLIER,
                "timestamp": now,
            })
            rolled_back = True

        if parameter_group in ("metacognition_similar_types", "all"):
            old_map = copy.deepcopy(self._params.metacognition_similar_types)
            self._params.metacognition_similar_types = copy.deepcopy(
                DEFAULT_SIMILAR_TYPES
            )
            self._append_audit({
                "action": "rollback",
                "parameter_group": "metacognition_similar_types",
                "old_value": old_map,
                "new_value": copy.deepcopy(DEFAULT_SIMILAR_TYPES),
                "timestamp": now,
            })
            rolled_back = True

        if parameter_group in ("immunity_speed", "all"):
            old_bonus = self._params.immunity_success_bonus
            old_penalty = self._params.immunity_failure_penalty
            self._params.immunity_success_bonus = DEFAULT_IMMUNITY_SUCCESS_BONUS
            self._params.immunity_failure_penalty = DEFAULT_IMMUNITY_FAILURE_PENALTY
            self._append_audit({
                "action": "rollback",
                "parameter_group": "immunity_speed",
                "old_value": {
                    "success_bonus": old_bonus,
                    "failure_penalty": old_penalty,
                },
                "new_value": {
                    "success_bonus": DEFAULT_IMMUNITY_SUCCESS_BONUS,
                    "failure_penalty": DEFAULT_IMMUNITY_FAILURE_PENALTY,
                },
                "timestamp": now,
            })
            rolled_back = True

        if not rolled_back:
            logger.warning(
                "ParameterTuner: 未知的參數群組 '%s'", parameter_group
            )
            return False

        # 重設漂移暫停狀態
        if parameter_group == "all":
            self._params.drift_paused = False

        self._save_parameters()
        logger.info(
            "ParameterTuner: 已重設參數群組 '%s' 為預設值",
            parameter_group,
        )
        return True

    # ═══════════════════════════════════════════
    # 狀態查詢
    # ═══════════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        """取得 ParameterTuner 狀態摘要."""
        return {
            "workspace": str(self._workspace),
            "params_path": str(self._params_path),
            "audit_path": str(self._audit_path),
            "version": self._params.version,
            "last_tuned": self._params.last_tuned,
            "drift_paused": self._params.drift_paused,
            "parameter_groups": [
                "qscore_weights",
                "skill_router_rc_multiplier",
                "metacognition_similar_types",
                "immunity_speed",
            ],
        }
