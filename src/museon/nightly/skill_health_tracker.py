"""skill_health_tracker.py — Per-Skill 健康度追蹤器.

設計原則：
- 純 CPU 運算，不依賴 EventBus 或 Brain
- 三個資料來源：skill_usage_log.jsonl / q_scores.jsonl / daily_summary.json
- 三種退化信號：品質下降 / 使用者主動跳過 / 呼叫量週週遞減
- 結果持久化到 data/_system/skill_health/{skill_name}.json
- 所有 IO 操作 graceful：檔案不存在就跳過，不拋例外
"""

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 退化判定門檻
QUALITY_GOOD = 0.7      # 上月平均品質低於此值才算「曾經好過」（避免誤報）
QUALITY_BAD = 0.5       # 本月平均品質低於此值才判定退化
SKIP_RATIO_THRESHOLD = 0.3   # skip / call > 30% → 使用者主動迴避
DECLINING_WEEKS = 3          # 連續幾週呼叫量下降才判定

# 嚴重程度門檻
CRITICAL_QUALITY_THRESHOLD = 0.3   # 品質分低於此值 → critical
WARNING_QUALITY_THRESHOLD = 0.5    # 品質分低於此值 → warning


@dataclass
class SkillHealth:
    """單一 Skill 的健康度快照."""

    skill_name: str
    avg_quality_30d: float          # 近 30 天平均品質分
    avg_quality_prev_30d: float     # 前 30 天（31-60 天）平均品質分
    call_count_30d: int             # 近 30 天呼叫次數
    skip_count_30d: int             # 近 30 天被跳過次數
    trend: str                      # "improving" | "stable" | "declining"
    status: str                     # "healthy" | "degrading" | "critical"
    last_updated: str               # ISO 8601


@dataclass
class DegradationSignal:
    """退化信號，代表一個需要關注的 Skill."""

    skill_name: str
    signal_type: str    # "quality_drop" | "users_avoiding" | "declining_usage"
    severity: str       # "warning" | "critical"
    metric: Dict        # 具體數值（依 signal_type 不同）
    recommendation: str  # "optimize" | "review" | "retire"


class SkillHealthTracker:
    """追蹤每個 Skill 的健康度，偵測退化信號.

    使用方式：
        tracker = SkillHealthTracker(workspace=Path("~/MUSEON").expanduser())
        health_map = tracker.scan_all_skills()
        signals = tracker.detect_degradation()
        tracker.persist()
    """

    def __init__(self, workspace: Path):
        """初始化健康度追蹤器.

        Args:
            workspace: MUSEON 根目錄（~/MUSEON）
        """
        self._workspace = workspace
        self._health_dir = workspace / "data" / "_system" / "skill_health"
        self._health_dir.mkdir(parents=True, exist_ok=True)

        # 三個資料來源路徑
        self._usage_log = workspace / "data" / "_system" / "skill_usage_log.jsonl"
        self._q_scores = workspace / "data" / "eval" / "q_scores.jsonl"
        self._daily_summary = (
            workspace / "data" / "_system" / "feedback_loop" / "daily_summary.json"
        )

        # 快取（scan_all_skills 填充，detect_degradation 使用）
        self._health_cache: Dict[str, SkillHealth] = {}

    # -------------------------------------------------------------------------
    # 公開介面
    # -------------------------------------------------------------------------

    def scan_all_skills(self) -> Dict[str, SkillHealth]:
        """掃描所有 Skill 的近 30 天使用數據.

        Returns:
            Dict[skill_name → SkillHealth]
        """
        now = datetime.now(timezone.utc)
        cutoff_30d = now - timedelta(days=30)
        cutoff_60d = now - timedelta(days=60)

        # 從三個資料來源匯總資料
        usage_data = self._load_usage_log(cutoff_60d)      # {skill: [{ts, skipped}, ...]}
        quality_data = self._load_quality_scores(cutoff_60d)  # {skill: [{ts, score}, ...]}

        # 合併所有 Skill 名稱（取聯集）
        all_skills = set(usage_data.keys()) | set(quality_data.keys())

        health_map: Dict[str, SkillHealth] = {}
        for skill_name in all_skills:
            health = self._compute_health(
                skill_name,
                usage_records=usage_data.get(skill_name, []),
                quality_records=quality_data.get(skill_name, []),
                cutoff_30d=cutoff_30d,
                now=now,
            )
            health_map[skill_name] = health

        self._health_cache = health_map
        logger.info("健康度掃描完成，共 %d 個 Skill", len(health_map))
        return health_map

    def detect_degradation(self) -> List[DegradationSignal]:
        """偵測正在退化的 Skill.

        需先呼叫 scan_all_skills()，否則使用快取（可能為空）。

        退化規則：
        - 規則 1：avg_quality 從上月 > 0.7 降到本月 < 0.5 → quality_drop
        - 規則 2：skip_count / call_count > 0.3 → users_avoiding
        - 規則 3：call_count 連續 3 週下降 → declining_usage

        Returns:
            退化信號列表
        """
        if not self._health_cache:
            self._health_cache = self.scan_all_skills()

        signals: List[DegradationSignal] = []

        # 連續週呼叫量需要更細粒度的資料
        weekly_usage = self._load_weekly_usage()

        for skill_name, health in self._health_cache.items():
            # 規則 1：品質下降
            if (
                health.avg_quality_prev_30d > QUALITY_GOOD
                and health.avg_quality_30d < QUALITY_BAD
            ):
                severity = (
                    "critical"
                    if health.avg_quality_30d < CRITICAL_QUALITY_THRESHOLD
                    else "warning"
                )
                signals.append(
                    DegradationSignal(
                        skill_name=skill_name,
                        signal_type="quality_drop",
                        severity=severity,
                        metric={
                            "prev_30d": round(health.avg_quality_prev_30d, 3),
                            "curr_30d": round(health.avg_quality_30d, 3),
                            "drop": round(
                                health.avg_quality_prev_30d - health.avg_quality_30d, 3
                            ),
                        },
                        recommendation=(
                            "retire"
                            if health.avg_quality_30d < CRITICAL_QUALITY_THRESHOLD
                            else "optimize"
                        ),
                    )
                )

            # 規則 2：使用者主動迴避
            if health.call_count_30d > 0:
                skip_ratio = health.skip_count_30d / health.call_count_30d
                if skip_ratio > SKIP_RATIO_THRESHOLD:
                    signals.append(
                        DegradationSignal(
                            skill_name=skill_name,
                            signal_type="users_avoiding",
                            severity=(
                                "critical" if skip_ratio > 0.6 else "warning"
                            ),
                            metric={
                                "skip_ratio": round(skip_ratio, 3),
                                "skip_count": health.skip_count_30d,
                                "call_count": health.call_count_30d,
                            },
                            recommendation="review",
                        )
                    )

            # 規則 3：呼叫量週週遞減
            if skill_name in weekly_usage:
                weeks = weekly_usage[skill_name]  # 最近 N 週，最新在後
                if self._is_declining(weeks, DECLINING_WEEKS):
                    signals.append(
                        DegradationSignal(
                            skill_name=skill_name,
                            signal_type="declining_usage",
                            severity="warning",
                            metric={
                                "weekly_counts": weeks[-DECLINING_WEEKS:],
                            },
                            recommendation=(
                                "retire"
                                if all(w == 0 for w in weeks[-2:])
                                else "review"
                            ),
                        )
                    )

        logger.info("退化偵測完成，共 %d 個退化信號", len(signals))
        return signals

    def persist(self) -> None:
        """將健康度數據持久化到 skill_health/ 目錄.

        每個 Skill 一個 JSON 檔：data/_system/skill_health/{skill_name}.json
        """
        if not self._health_cache:
            logger.warning("健康度快取為空，跳過持久化（請先呼叫 scan_all_skills）")
            return

        written = 0
        for skill_name, health in self._health_cache.items():
            output_path = self._health_dir / f"{skill_name}.json"
            try:
                output_path.write_text(
                    json.dumps(asdict(health), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                written += 1
            except OSError as exc:
                logger.error("寫入 %s 健康度失敗：%s", skill_name, exc)

        logger.info("健康度持久化完成，共寫入 %d 個檔案", written)

    # -------------------------------------------------------------------------
    # 資料載入（graceful，檔案不存在就回傳空集合）
    # -------------------------------------------------------------------------

    def _load_usage_log(self, since: datetime) -> Dict[str, List[Dict]]:
        """讀取 skill_usage_log.jsonl，返回 {skill_name: [{ts, skipped, ...}]}."""
        result: Dict[str, List[Dict]] = defaultdict(list)

        if not self._usage_log.exists():
            logger.debug("skill_usage_log.jsonl 不存在，跳過")
            return result

        try:
            for line in self._usage_log.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts = self._parse_ts(record.get("timestamp", ""))
                    if ts and ts >= since:
                        skill = record.get("skill_used") or record.get("skill", "")
                        if skill:
                            result[skill].append(record)
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError as exc:
            logger.warning("讀取 skill_usage_log 失敗：%s", exc)

        return result

    def _load_quality_scores(self, since: datetime) -> Dict[str, List[Dict]]:
        """讀取 data/eval/q_scores.jsonl，返回 {skill_name: [{ts, score, ...}]}."""
        result: Dict[str, List[Dict]] = defaultdict(list)

        if not self._q_scores.exists():
            logger.debug("q_scores.jsonl 不存在，跳過")
            return result

        try:
            for line in self._q_scores.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    ts = self._parse_ts(record.get("timestamp", ""))
                    if ts and ts >= since:
                        skill = record.get("skill_used") or record.get("skill", "")
                        if skill:
                            result[skill].append(record)
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError as exc:
            logger.warning("讀取 q_scores.jsonl 失敗：%s", exc)

        return result

    def _load_weekly_usage(self) -> Dict[str, List[int]]:
        """從 daily_summary.json 彙整近 6 週每週呼叫量.

        Returns:
            {skill_name: [week_-5_count, ..., week_-1_count, week_0_count]}
            最新週在列表末尾。
        """
        result: Dict[str, List[int]] = defaultdict(lambda: [0] * 6)

        if not self._daily_summary.exists():
            logger.debug("daily_summary.json 不存在，跳過週趨勢分析")
            return result

        try:
            summary = json.loads(
                self._daily_summary.read_text(encoding="utf-8")
            )
            weekly: Dict = summary.get("weekly_skill_usage", {})
            for skill_name, weeks_data in weekly.items():
                if isinstance(weeks_data, list):
                    # 取最後 6 週，不足補 0
                    trimmed = weeks_data[-6:]
                    padded = [0] * (6 - len(trimmed)) + trimmed
                    result[skill_name] = padded
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            logger.warning("讀取 daily_summary.json 失敗：%s", exc)

        return result

    # -------------------------------------------------------------------------
    # 計算邏輯
    # -------------------------------------------------------------------------

    def _compute_health(
        self,
        skill_name: str,
        usage_records: List[Dict],
        quality_records: List[Dict],
        cutoff_30d: datetime,
        now: datetime,
    ) -> SkillHealth:
        """計算單一 Skill 的健康度快照."""
        # 分成近 30 天和前 30 天兩個桶
        recent_quality: List[float] = []
        prev_quality: List[float] = []
        call_count_30d = 0
        skip_count_30d = 0

        for record in quality_records:
            ts = self._parse_ts(record.get("timestamp", ""))
            score = record.get("score", record.get("quality_score"))
            if score is None:
                continue
            try:
                score = float(score)
            except (ValueError, TypeError):
                continue

            if ts and ts >= cutoff_30d:
                recent_quality.append(score)
            elif ts:
                prev_quality.append(score)

        for record in usage_records:
            ts = self._parse_ts(record.get("timestamp", ""))
            if ts and ts >= cutoff_30d:
                call_count_30d += 1
                if record.get("skipped") or record.get("skip"):
                    skip_count_30d += 1

        avg_q_30d = (
            sum(recent_quality) / len(recent_quality) if recent_quality else 0.0
        )
        avg_q_prev = (
            sum(prev_quality) / len(prev_quality) if prev_quality else 0.0
        )

        # 趨勢判定（需要有足夠資料才判定）
        trend = self._compute_trend(avg_q_30d, avg_q_prev, recent_quality, prev_quality)

        # 狀態判定
        if avg_q_30d >= QUALITY_GOOD:
            status = "healthy"
        elif avg_q_30d >= WARNING_QUALITY_THRESHOLD:
            status = "degrading"
        else:
            status = "critical"

        return SkillHealth(
            skill_name=skill_name,
            avg_quality_30d=round(avg_q_30d, 4),
            avg_quality_prev_30d=round(avg_q_prev, 4),
            call_count_30d=call_count_30d,
            skip_count_30d=skip_count_30d,
            trend=trend,
            status=status,
            last_updated=now.isoformat(),
        )

    def _compute_trend(
        self,
        curr: float,
        prev: float,
        curr_list: List[float],
        prev_list: List[float],
    ) -> str:
        """判斷趨勢：improving / stable / declining."""
        # 資料不足時無法判斷
        if not curr_list or not prev_list:
            return "stable"

        delta = curr - prev
        if delta > 0.05:
            return "improving"
        elif delta < -0.05:
            return "declining"
        else:
            return "stable"

    def _is_declining(self, weekly_counts: List[int], n: int) -> bool:
        """判斷最近 n 週是否連續下降."""
        if len(weekly_counts) < n:
            return False
        tail = weekly_counts[-n:]
        return all(tail[i] > tail[i + 1] for i in range(len(tail) - 1))

    # -------------------------------------------------------------------------
    # 工具方法
    # -------------------------------------------------------------------------

    def _parse_ts(self, ts_str: str) -> Optional[datetime]:
        """解析 ISO 8601 時間戳字串為 aware datetime."""
        if not ts_str:
            return None
        try:
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
