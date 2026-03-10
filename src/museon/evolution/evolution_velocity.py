"""EvolutionVelocity -- 演化速度度量引擎.

量化霓裳的演化速度：不只記錄「發生了什麼」，
而是量化「進步有多快」。

五項核心指標：
  1. 能力擴展率 -- 新增有效結晶 / 總互動數
  2. 修復速度 -- 問題發現到解決的平均時間
  3. 預判進步率 -- 元認知準確率的週間變化
  4. 技能命中率 -- Skill Router 精確度變化
  5. 迭代效率 -- Morphenix 成功率

趨勢偵測：
  - 連續 3 週上升 -> 演化加速中
  - 連續 3 週持平 -> 高原期（觸發突變策略）
  - 連續 3 週下降 -> 退化警報（觸發根因分析）

資料來源（全部從檔案系統讀取，零模組依賴）：
  - Knowledge Lattice: {workspace}/lattice/crystals.json
  - Immunity 事件: {workspace}/_system/immunity/events.jsonl
  - Metacognition 統計: {workspace}/_system/metacognition/accuracy_stats.json
  - Skill 使用紀錄: {workspace}/skill_usage_log.jsonl
  - Morphenix 提案: {workspace}/_system/morphenix/proposals/
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ═══════════════════════════════════════════
# 常數
# ═══════════════════════════════════════════

# 趨勢偵測：需要連續 N 週同方向才判定趨勢
TREND_MIN_WEEKS = 3

# 高原偵測：composite_velocity 週間變化小於此值視為持平
PLATEAU_EPSILON = 0.02

# 預設權重（五項指標的加權比例）
DEFAULT_WEIGHTS: Dict[str, float] = {
    "capability_expansion_rate": 0.25,
    "repair_speed_hours": 0.15,
    "prediction_improvement": 0.20,
    "skill_hit_rate_delta": 0.20,
    "iteration_efficiency": 0.20,
}

# 修復速度的正規化基準（24 小時內修復 = 1.0，超過則衰減）
REPAIR_SPEED_BASELINE_HOURS = 24.0

# JSONL 日誌最大保留週數
MAX_LOG_WEEKS = 52


# ═══════════════════════════════════════════
# 資料模型
# ═══════════════════════════════════════════


@dataclass
class VelocitySnapshot:
    """單週演化速度快照."""

    # 時間標記
    iso_week: str = ""                    # e.g. "2026-W10"
    timestamp: str = ""                   # ISO 8601

    # 五項核心指標（皆正規化至 0.0 ~ 1.0）
    capability_expansion_rate: float = 0.0
    repair_speed_hours: float = 0.0       # 原始值（小時），正規化後用於 composite
    repair_speed_normalized: float = 0.0  # 正規化至 0~1（越快越高）
    prediction_improvement: float = 0.0   # 可為負
    skill_hit_rate_delta: float = 0.0     # 可為負
    iteration_efficiency: float = 0.0

    # 綜合速度
    composite_velocity: float = 0.0

    # 原始數據摘要
    new_crystals: int = 0
    total_interactions: int = 0
    immunity_events_resolved: int = 0
    metacognition_accuracy_this_week: float = 0.0
    metacognition_accuracy_last_week: float = 0.0
    skill_hit_rate_this_week: float = 0.0
    skill_hit_rate_last_week: float = 0.0
    morphenix_total: int = 0
    morphenix_accepted: int = 0

    # 警報旗標
    plateau_alert: bool = False
    regression_alert: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VelocitySnapshot":
        """從字典還原."""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


# ═══════════════════════════════════════════
# 主類別
# ═══════════════════════════════════════════


class EvolutionVelocity:
    """演化速度度量引擎.

    量化五項核心演化指標，追蹤週間趨勢，
    在高原期或退化期自動觸發警報旗標。

    設計原則：
      - 零模組依賴（純檔案系統讀取）
      - 所有 IO 操作 try/except 包裝
      - 指標正規化至 0.0 ~ 1.0
      - JSONL 持久化週間快照
    """

    def __init__(
        self,
        workspace: Path,
        weights: Optional[Dict[str, float]] = None,
    ) -> None:
        """初始化演化速度引擎.

        Args:
            workspace: MUSEON 工作目錄根路徑
            weights: 五項指標的自訂權重（可選，預設使用 DEFAULT_WEIGHTS）
        """
        self._workspace = Path(workspace)
        self._weights = weights or dict(DEFAULT_WEIGHTS)

        # 確保權重總和 = 1.0
        total_w = sum(self._weights.values())
        if total_w > 0 and abs(total_w - 1.0) > 1e-6:
            for k in self._weights:
                self._weights[k] /= total_w

        # 日誌路徑
        self._log_dir = self._workspace / "_system" / "evolution"
        self._log_file = self._log_dir / "velocity_log.jsonl"

        # 快取歷史快照（從 JSONL 載入）
        self._history: List[VelocitySnapshot] = []
        self._load_history()

    # ═══════════════════════════════════════════
    # 核心計算
    # ═══════════════════════════════════════════

    def calculate_weekly(self) -> VelocitySnapshot:
        """計算本週的演化速度快照.

        逐一計算五項核心指標，合成綜合速度，
        並偵測趨勢設定警報旗標。

        Returns:
            VelocitySnapshot 本週快照
        """
        now = datetime.now(TZ8)
        iso_cal = now.isocalendar()
        iso_week = f"{iso_cal[0]}-W{iso_cal[1]:02d}"

        snapshot = VelocitySnapshot(
            iso_week=iso_week,
            timestamp=now.isoformat(),
        )

        # ─── 指標 1：能力擴展率 ───
        self._calc_capability_expansion(snapshot, now)

        # ─── 指標 2：修復速度 ───
        self._calc_repair_speed(snapshot, now)

        # ─── 指標 3：預判進步率 ───
        self._calc_prediction_improvement(snapshot)

        # ─── 指標 4：技能命中率變化 ───
        self._calc_skill_hit_rate_delta(snapshot, now)

        # ─── 指標 5：迭代效率 ───
        self._calc_iteration_efficiency(snapshot)

        # ─── 綜合速度 ───
        snapshot.composite_velocity = self._compute_composite(snapshot)

        # ─── 趨勢警報 ───
        self._update_alerts(snapshot)

        # ─── 持久化 ───
        self._append_snapshot(snapshot)

        logger.info(
            f"EvolutionVelocity: weekly snapshot {iso_week} "
            f"composite={snapshot.composite_velocity:.4f} "
            f"plateau={snapshot.plateau_alert} "
            f"regression={snapshot.regression_alert}"
        )

        return snapshot

    # ═══════════════════════════════════════════
    # 趨勢分析
    # ═══════════════════════════════════════════

    def get_trend(self, weeks: int = 4) -> str:
        """分析最近 N 週的演化趨勢.

        規則：
          - 連續 3+ 週 composite_velocity 上升 -> "accelerating"
          - 連續 3+ 週持平（變化 < PLATEAU_EPSILON）-> "plateau"
          - 連續 3+ 週下降 -> "decelerating"
          - 資料不足 -> "insufficient_data"

        Args:
            weeks: 分析的週數（預設 4）

        Returns:
            趨勢字串
        """
        if len(self._history) < TREND_MIN_WEEKS:
            return "insufficient_data"

        # 取最近 N 筆
        recent = self._history[-weeks:]
        if len(recent) < TREND_MIN_WEEKS:
            return "insufficient_data"

        # 計算週間差值
        deltas: List[float] = []
        for i in range(1, len(recent)):
            delta = recent[i].composite_velocity - recent[i - 1].composite_velocity
            deltas.append(delta)

        if not deltas:
            return "insufficient_data"

        # 判定趨勢（取最近 TREND_MIN_WEEKS - 1 個差值）
        check_deltas = deltas[-(TREND_MIN_WEEKS - 1):]

        all_rising = all(d > PLATEAU_EPSILON for d in check_deltas)
        all_flat = all(abs(d) <= PLATEAU_EPSILON for d in check_deltas)
        all_falling = all(d < -PLATEAU_EPSILON for d in check_deltas)

        if all_rising:
            return "accelerating"
        elif all_flat:
            return "plateau"
        elif all_falling:
            return "decelerating"

        return "insufficient_data"

    # ═══════════════════════════════════════════
    # 儀表板
    # ═══════════════════════════════════════════

    def get_dashboard(self) -> Dict[str, Any]:
        """取得人類可讀的演化速度儀表板.

        Returns:
            包含最新快照、趨勢、歷史摘要的字典
        """
        trend = self.get_trend()
        latest = self._history[-1] if self._history else None

        dashboard: Dict[str, Any] = {
            "trend": trend,
            "trend_description": self._trend_description(trend),
            "total_snapshots": len(self._history),
            "weights": dict(self._weights),
        }

        if latest:
            dashboard["latest"] = {
                "iso_week": latest.iso_week,
                "timestamp": latest.timestamp,
                "composite_velocity": round(latest.composite_velocity, 4),
                "metrics": {
                    "capability_expansion_rate": round(
                        latest.capability_expansion_rate, 4
                    ),
                    "repair_speed_hours": round(latest.repair_speed_hours, 2),
                    "repair_speed_normalized": round(
                        latest.repair_speed_normalized, 4
                    ),
                    "prediction_improvement": round(
                        latest.prediction_improvement, 4
                    ),
                    "skill_hit_rate_delta": round(
                        latest.skill_hit_rate_delta, 4
                    ),
                    "iteration_efficiency": round(
                        latest.iteration_efficiency, 4
                    ),
                },
                "raw_data": {
                    "new_crystals": latest.new_crystals,
                    "total_interactions": latest.total_interactions,
                    "immunity_events_resolved": latest.immunity_events_resolved,
                    "metacognition_accuracy_this_week": round(
                        latest.metacognition_accuracy_this_week, 4
                    ),
                    "metacognition_accuracy_last_week": round(
                        latest.metacognition_accuracy_last_week, 4
                    ),
                    "skill_hit_rate_this_week": round(
                        latest.skill_hit_rate_this_week, 4
                    ),
                    "skill_hit_rate_last_week": round(
                        latest.skill_hit_rate_last_week, 4
                    ),
                    "morphenix_total": latest.morphenix_total,
                    "morphenix_accepted": latest.morphenix_accepted,
                },
                "alerts": {
                    "plateau_alert": latest.plateau_alert,
                    "regression_alert": latest.regression_alert,
                },
            }

            # 歷史趨勢（最近 8 週 composite_velocity）
            history_points = self._history[-8:]
            dashboard["history"] = [
                {
                    "iso_week": s.iso_week,
                    "composite_velocity": round(s.composite_velocity, 4),
                }
                for s in history_points
            ]
        else:
            dashboard["latest"] = None
            dashboard["history"] = []

        return dashboard

    # ═══════════════════════════════════════════
    # 指標計算（私有方法）
    # ═══════════════════════════════════════════

    def _calc_capability_expansion(
        self, snapshot: VelocitySnapshot, now: datetime
    ) -> None:
        """指標 1：能力擴展率 = 本週新增結晶 / 本週總互動數.

        資料來源：
          - 結晶: {workspace}/lattice/crystals.json
          - 互動: 從結晶的時間戳推算
        """
        crystals_file = self._workspace / "lattice" / "crystals.json"
        week_start = now - timedelta(days=now.weekday(), hours=now.hour,
                                     minutes=now.minute, seconds=now.second)

        new_crystals = 0
        total_interactions = 0

        try:
            if crystals_file.exists():
                with open(crystals_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)

                # 支援 list 或 dict 格式
                crystal_list = data if isinstance(data, list) else data.get(
                    "crystals", []
                )

                for crystal in crystal_list:
                    total_interactions += 1
                    created = crystal.get(
                        "created_at",
                        crystal.get("crystallized_at", ""),
                    )
                    if created:
                        try:
                            ct = datetime.fromisoformat(created)
                            if ct.tzinfo is None:
                                ct = ct.replace(tzinfo=TZ8)
                            if ct >= week_start:
                                new_crystals += 1
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.warning(f"EvolutionVelocity: read crystals failed: {e}")

        snapshot.new_crystals = new_crystals
        snapshot.total_interactions = max(total_interactions, 1)
        snapshot.capability_expansion_rate = (
            new_crystals / snapshot.total_interactions
        )

    def _calc_repair_speed(
        self, snapshot: VelocitySnapshot, now: datetime
    ) -> None:
        """指標 2：修復速度 = 問題偵測到解決的平均時間（小時）.

        資料來源: {workspace}/_system/immunity/events.jsonl
        每行 JSON 格式: {"event_type": "...", "detected_at": "...",
                         "resolved_at": "...", ...}

        正規化：repair_speed_normalized = max(0, 1 - hours / baseline)
        """
        events_file = (
            self._workspace / "_system" / "immunity" / "events.jsonl"
        )
        repair_times: List[float] = []

        try:
            if events_file.exists():
                with open(events_file, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        detected = event.get("detected_at", "")
                        resolved = event.get("resolved_at", "")
                        if not detected or not resolved:
                            continue

                        try:
                            dt_detected = datetime.fromisoformat(detected)
                            dt_resolved = datetime.fromisoformat(resolved)
                            hours = (
                                dt_resolved - dt_detected
                            ).total_seconds() / 3600.0
                            if hours >= 0:
                                repair_times.append(hours)
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.warning(
                f"EvolutionVelocity: read immunity events failed: {e}"
            )

        if repair_times:
            avg_hours = statistics.mean(repair_times)
            snapshot.repair_speed_hours = avg_hours
            snapshot.immunity_events_resolved = len(repair_times)
            # 正規化：越快越好（24h 內 = 1.0，超過則衰減）
            snapshot.repair_speed_normalized = max(
                0.0, 1.0 - avg_hours / REPAIR_SPEED_BASELINE_HOURS
            )
        else:
            snapshot.repair_speed_hours = 0.0
            snapshot.repair_speed_normalized = 0.5  # 無資料時中性值
            snapshot.immunity_events_resolved = 0

    def _calc_prediction_improvement(self, snapshot: VelocitySnapshot) -> None:
        """指標 3：預判進步率 = 本週準確率 - 上週準確率.

        資料來源: {workspace}/_system/metacognition/accuracy_stats.json
        格式: {"this_week": float, "last_week": float, ...}
        """
        stats_file = (
            self._workspace
            / "_system"
            / "metacognition"
            / "accuracy_stats.json"
        )

        try:
            if stats_file.exists():
                with open(stats_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)

                this_week = float(data.get("this_week", data.get(
                    "current_accuracy", 0.0
                )))
                last_week = float(data.get("last_week", data.get(
                    "previous_accuracy", 0.0
                )))

                snapshot.metacognition_accuracy_this_week = this_week
                snapshot.metacognition_accuracy_last_week = last_week
                snapshot.prediction_improvement = this_week - last_week
            else:
                snapshot.prediction_improvement = 0.0
        except Exception as e:
            logger.warning(
                f"EvolutionVelocity: read metacognition stats failed: {e}"
            )
            snapshot.prediction_improvement = 0.0

    def _calc_skill_hit_rate_delta(
        self, snapshot: VelocitySnapshot, now: datetime
    ) -> None:
        """指標 4：技能命中率變化 = 本週命中率 - 上週命中率.

        資料來源: {workspace}/skill_usage_log.jsonl
        每行 JSON: {"timestamp": "...", "hit": true/false, ...}

        以 7 天為一週切分，比較本週與上週的 hit rate。
        """
        log_file = self._workspace / "skill_usage_log.jsonl"
        week_start = now - timedelta(days=now.weekday(), hours=now.hour,
                                     minutes=now.minute, seconds=now.second)
        last_week_start = week_start - timedelta(days=7)

        this_week_hits = 0
        this_week_total = 0
        last_week_hits = 0
        last_week_total = 0

        try:
            if log_file.exists():
                with open(log_file, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        ts_str = entry.get("timestamp", "")
                        if not ts_str:
                            continue

                        try:
                            ts = datetime.fromisoformat(ts_str)
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=TZ8)
                        except (ValueError, TypeError):
                            continue

                        hit = entry.get("hit", entry.get("matched", False))

                        if ts >= week_start:
                            this_week_total += 1
                            if hit:
                                this_week_hits += 1
                        elif ts >= last_week_start:
                            last_week_total += 1
                            if hit:
                                last_week_hits += 1
        except Exception as e:
            logger.warning(
                f"EvolutionVelocity: read skill usage log failed: {e}"
            )

        this_rate = (
            this_week_hits / this_week_total
            if this_week_total > 0
            else 0.0
        )
        last_rate = (
            last_week_hits / last_week_total
            if last_week_total > 0
            else 0.0
        )

        snapshot.skill_hit_rate_this_week = this_rate
        snapshot.skill_hit_rate_last_week = last_rate
        snapshot.skill_hit_rate_delta = this_rate - last_rate

    def _calc_iteration_efficiency(self, snapshot: VelocitySnapshot) -> None:
        """指標 5：迭代效率 = 成功提案 / 總提案.

        資料來源: {workspace}/_system/morphenix/proposals/
        每個 .json 檔案包含 {"status": "accepted"|"rejected"|"pending", ...}
        """
        proposals_dir = (
            self._workspace / "_system" / "morphenix" / "proposals"
        )

        total = 0
        accepted = 0

        try:
            if proposals_dir.exists() and proposals_dir.is_dir():
                for pf in proposals_dir.glob("*.json"):
                    try:
                        with open(pf, "r", encoding="utf-8") as fh:
                            proposal = json.load(fh)
                        total += 1
                        status = proposal.get("status", "").lower()
                        if status in ("accepted", "approved", "merged"):
                            accepted += 1
                    except (json.JSONDecodeError, OSError):
                        continue
        except Exception as e:
            logger.warning(
                f"EvolutionVelocity: read morphenix proposals failed: {e}"
            )

        snapshot.morphenix_total = total
        snapshot.morphenix_accepted = accepted
        snapshot.iteration_efficiency = (
            accepted / total if total > 0 else 0.0
        )

    # ═══════════════════════════════════════════
    # 綜合計算 & 警報
    # ═══════════════════════════════════════════

    def _compute_composite(self, snapshot: VelocitySnapshot) -> float:
        """計算加權綜合速度.

        五項指標正規化至 0~1 後加權平均：
          - capability_expansion_rate: 已在 0~1
          - repair_speed_normalized: 已在 0~1
          - prediction_improvement: 裁切至 [-1, 1]，映射至 [0, 1]
          - skill_hit_rate_delta: 裁切至 [-1, 1]，映射至 [0, 1]
          - iteration_efficiency: 已在 0~1

        Returns:
            composite_velocity (0.0 ~ 1.0)
        """
        # 正規化各指標至 0~1
        metrics: Dict[str, float] = {
            "capability_expansion_rate": max(
                0.0, min(1.0, snapshot.capability_expansion_rate)
            ),
            "repair_speed_hours": max(
                0.0, min(1.0, snapshot.repair_speed_normalized)
            ),
            "prediction_improvement": max(
                0.0, min(1.0, (snapshot.prediction_improvement + 1.0) / 2.0)
            ),
            "skill_hit_rate_delta": max(
                0.0, min(1.0, (snapshot.skill_hit_rate_delta + 1.0) / 2.0)
            ),
            "iteration_efficiency": max(
                0.0, min(1.0, snapshot.iteration_efficiency)
            ),
        }

        composite = 0.0
        for key, weight in self._weights.items():
            composite += metrics.get(key, 0.0) * weight

        return max(0.0, min(1.0, composite))

    def _update_alerts(self, snapshot: VelocitySnapshot) -> None:
        """根據歷史趨勢設定警報旗標.

        - plateau_alert: 連續 3+ 週持平
        - regression_alert: 連續 3+ 週下降
        """
        # 暫時加入當前快照以判定趨勢
        temp_history = list(self._history) + [snapshot]

        if len(temp_history) < TREND_MIN_WEEKS:
            return

        recent = temp_history[-TREND_MIN_WEEKS:]
        deltas = [
            recent[i].composite_velocity - recent[i - 1].composite_velocity
            for i in range(1, len(recent))
        ]

        # 高原偵測
        if all(abs(d) <= PLATEAU_EPSILON for d in deltas):
            snapshot.plateau_alert = True
            logger.warning(
                f"EvolutionVelocity: PLATEAU detected "
                f"({TREND_MIN_WEEKS} weeks flat)"
            )

        # 退化偵測
        if all(d < -PLATEAU_EPSILON for d in deltas):
            snapshot.regression_alert = True
            logger.warning(
                f"EvolutionVelocity: REGRESSION detected "
                f"({TREND_MIN_WEEKS} weeks declining)"
            )

    # ═══════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════

    def _load_history(self) -> None:
        """從 JSONL 載入歷史快照."""
        self._history = []
        try:
            if self._log_file.exists():
                with open(self._log_file, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            snapshot = VelocitySnapshot.from_dict(data)
                            self._history.append(snapshot)
                        except (json.JSONDecodeError, TypeError):
                            continue

                # 限制保留週數
                if len(self._history) > MAX_LOG_WEEKS:
                    self._history = self._history[-MAX_LOG_WEEKS:]

                logger.info(
                    f"EvolutionVelocity: loaded {len(self._history)} "
                    f"historical snapshots"
                )
        except Exception as e:
            logger.warning(
                f"EvolutionVelocity: load history failed: {e}"
            )

    def _append_snapshot(self, snapshot: VelocitySnapshot) -> None:
        """將快照追加到 JSONL 日誌並更新記憶體快取."""
        # 避免同週重複寫入：覆蓋同 iso_week 的舊紀錄
        self._history = [
            s for s in self._history if s.iso_week != snapshot.iso_week
        ]
        self._history.append(snapshot)

        # 限制保留週數
        if len(self._history) > MAX_LOG_WEEKS:
            self._history = self._history[-MAX_LOG_WEEKS:]

        # 寫入 JSONL（全量重寫以去重）
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            with open(self._log_file, "w", encoding="utf-8") as fh:
                for s in self._history:
                    fh.write(json.dumps(s.to_dict(), ensure_ascii=False))
                    fh.write("\n")
        except Exception as e:
            logger.error(
                f"EvolutionVelocity: write snapshot failed: {e}"
            )

    # ═══════════════════════════════════════════
    # 輔助方法
    # ═══════════════════════════════════════════

    @staticmethod
    def _trend_description(trend: str) -> str:
        """趨勢的人類可讀描述."""
        descriptions = {
            "accelerating": "演化加速中 -- 系統正在快速進步",
            "plateau": "高原期 -- 建議觸發突變策略以突破瓶頸",
            "decelerating": "退化警報 -- 建議進行根因分析",
            "insufficient_data": "資料不足 -- 需要更多週間快照才能判定趨勢",
        }
        return descriptions.get(trend, "未知趨勢")

    def get_history(self, weeks: int = 8) -> List[Dict[str, Any]]:
        """取得歷史快照列表.

        Args:
            weeks: 回傳最近 N 週的快照

        Returns:
            快照字典列表
        """
        recent = self._history[-weeks:]
        return [s.to_dict() for s in recent]

    def get_status(self) -> Dict[str, Any]:
        """取得引擎狀態摘要."""
        return {
            "workspace": str(self._workspace),
            "log_file": str(self._log_file),
            "total_snapshots": len(self._history),
            "weights": dict(self._weights),
            "trend": self.get_trend(),
            "latest_iso_week": (
                self._history[-1].iso_week if self._history else None
            ),
            "latest_composite": (
                round(self._history[-1].composite_velocity, 4)
                if self._history
                else None
            ),
        }


# ═══════════════════════════════════════════
# 模組級快捷函式
# ═══════════════════════════════════════════


def get_evolution_velocity(
    workspace: Path,
    weights: Optional[Dict[str, float]] = None,
) -> EvolutionVelocity:
    """取得 EvolutionVelocity 實例.

    便利函式，避免呼叫端需要直接 import 類別。

    Args:
        workspace: MUSEON 工作目錄根路徑
        weights: 五項指標的自訂權重（可選）

    Returns:
        EvolutionVelocity 實例
    """
    return EvolutionVelocity(workspace=Path(workspace), weights=weights)
