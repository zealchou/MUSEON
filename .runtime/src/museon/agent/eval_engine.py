"""Eval-Engine — Q-Score 品質儀表板、趨勢追蹤、A/B 比對與盲點雷達.

MUSEON 品質度量系統的核心模組，提供：
  1. Q-Score 即時品質儀 — 每次回答的品質量化
  2. 滿意度代理指標 — 行為信號推估
  3. 趨勢追蹤器 — 跨對話品質曲線
  4. A/B 比對器 — 迭代前後效果驗證
  5. 盲點雷達 — 系統性弱項偵測
  6. Skill 使用率熱力圖 — Skill 實際使用分布
  7. 背景運行 — 靜默記錄 + 每日/每週報告

安全護欄：
  - HG-EVAL-HONEST: 不美化數據，樣本不足時回報 insufficient_data
  - HG-EVAL-BASELINE-LOCK: A/B 基線一旦建立不可修改
  - SG-EVAL-PRIVACY: 品質數據不含對話原文
"""

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════
# 常數定義
# ════════════════════════════════════════════

# Q-Score 四維權重（精確比重，不可更改）
WEIGHT_UNDERSTANDING: float = 0.30
WEIGHT_DEPTH: float = 0.25
WEIGHT_CLARITY: float = 0.20
WEIGHT_ACTIONABILITY: float = 0.25

# 品質等級閾值
TIER_HIGH_THRESHOLD: float = 0.7
TIER_LOW_THRESHOLD: float = 0.5

# 滿意度代理負向偏權（negativity bias）
NEGATIVITY_BIAS: float = 1.5

# 連續低分警報閾值
CONSECUTIVE_LOW_ALERT_COUNT: int = 3

# A/B 比對觀察期（天）
AB_OBSERVATION_DAYS: int = 7

# A/B 維度退化閾值
AB_REGRESSION_THRESHOLD: float = 0.10

# 盲點偵測：低於全域平均的差距閾值
BLINDSPOT_DOMAIN_GAP_THRESHOLD: float = 0.15

# HG-EVAL-HONEST：最少樣本數
MIN_SAMPLE_SIZE: int = 10


# ════════════════════════════════════════════
# 資料類別
# ════════════════════════════════════════════

@dataclass
class QScore:
    """單次回答的品質評分.

    Q-Score = 0.30 * understanding + 0.25 * depth + 0.20 * clarity + 0.25 * actionability

    Attributes:
        id: 唯一識別碼
        session_id: 對話 ID
        timestamp: 評分時間戳
        domain: 所屬領域（投資/行銷/客服等）
        understanding: 理解度（0.0-1.0）— 使用者意圖準確度
        depth: 深度（0.0-1.0）— 分析完整度
        clarity: 清晰度（0.0-1.0）— 表達清晰可讀性
        actionability: 可行動性（0.0-1.0）— 是否包含具體下一步
        score: 加權後 Q-Score
        tier: 品質等級（high / medium / low）
        matched_skills: 本次匹配到的技能列表
        zero_dimensions: 值為 0 的維度清單（額外警告用）
    """

    id: str = ""
    session_id: str = ""
    timestamp: str = ""
    domain: str = "general"
    understanding: float = 0.0
    depth: float = 0.0
    clarity: float = 0.0
    actionability: float = 0.0
    score: float = 0.0
    tier: str = "low"
    matched_skills: List[str] = field(default_factory=list)
    zero_dimensions: List[str] = field(default_factory=list)

    def compute(self) -> "QScore":
        """計算 Q-Score 加權分數與品質等級.

        Returns:
            self — 方便鏈式呼叫
        """
        # 精確公式：Q-Score = 0.30*U + 0.25*D + 0.20*C + 0.25*A
        self.score = (
            WEIGHT_UNDERSTANDING * self.understanding
            + WEIGHT_DEPTH * self.depth
            + WEIGHT_CLARITY * self.clarity
            + WEIGHT_ACTIONABILITY * self.actionability
        )
        # 品質等級判定
        if self.score > TIER_HIGH_THRESHOLD:
            self.tier = "high"
        elif self.score >= TIER_LOW_THRESHOLD:
            self.tier = "medium"
        else:
            self.tier = "low"

        # 偵測零值維度（單一維度為 0 時額外警告）
        self.zero_dimensions = []
        if self.understanding == 0.0:
            self.zero_dimensions.append("understanding")
        if self.depth == 0.0:
            self.zero_dimensions.append("depth")
        if self.clarity == 0.0:
            self.zero_dimensions.append("clarity")
        if self.actionability == 0.0:
            self.zero_dimensions.append("actionability")

        return self

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可序列化字典.

        SG-EVAL-PRIVACY: 只儲存分數和 metadata，不含對話原文。
        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QScore":
        """從字典還原 QScore."""
        return cls(
            id=data.get("id", ""),
            session_id=data.get("session_id", ""),
            timestamp=data.get("timestamp", ""),
            domain=data.get("domain", "general"),
            understanding=data.get("understanding", 0.0),
            depth=data.get("depth", 0.0),
            clarity=data.get("clarity", 0.0),
            actionability=data.get("actionability", 0.0),
            score=data.get("score", 0.0),
            tier=data.get("tier", "low"),
            matched_skills=data.get("matched_skills", []),
            zero_dimensions=data.get("zero_dimensions", []),
        )


@dataclass
class SatisfactionSignal:
    """滿意度代理信號.

    正向信號權重 +1.0，負向信號權重 -1.5（negativity bias）。

    Attributes:
        id: 唯一識別碼
        session_id: 對話 ID
        timestamp: 信號時間戳
        signal_type: 信號類型（positive / negative）
        signal_value: 信號值（正向=+1.0, 負向=-1.5）
        context: 行為描述（如「使用者重複提問」），不含對話原文
        q_score_id: 關聯的 Q-Score ID
    """

    id: str = ""
    session_id: str = ""
    timestamp: str = ""
    signal_type: str = "positive"
    signal_value: float = 1.0
    context: str = ""
    q_score_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可序列化字典."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SatisfactionSignal":
        """從字典還原 SatisfactionSignal."""
        return cls(
            id=data.get("id", ""),
            session_id=data.get("session_id", ""),
            timestamp=data.get("timestamp", ""),
            signal_type=data.get("signal_type", "positive"),
            signal_value=data.get("signal_value", 1.0),
            context=data.get("context", ""),
            q_score_id=data.get("q_score_id", ""),
        )


@dataclass
class Alert:
    """品質警報.

    Attributes:
        id: 唯一識別碼
        timestamp: 警報時間戳
        alert_type: 警報類型（consecutive_low / zero_dimension / ab_regression / blindspot）
        severity: 嚴重度（warning / critical）
        message: 警報訊息
        details: 額外細節
    """

    id: str = ""
    timestamp: str = ""
    alert_type: str = ""
    severity: str = "warning"
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可序列化字典."""
        return asdict(self)


@dataclass
class TrendData:
    """趨勢資料.

    Attributes:
        period_days: 追蹤天數
        domain: 領域篩選（None = 全域）
        daily_averages: 每日平均 Q-Score {日期字串: 平均分}
        rolling_average: 滾動平均值
        direction: 趨勢方向（up / stable / down）
        sample_count: 樣本數
        insufficient_data: 是否樣本不足
    """

    period_days: int = 7
    domain: Optional[str] = None
    daily_averages: Dict[str, float] = field(default_factory=dict)
    rolling_average: float = 0.0
    direction: str = "stable"
    sample_count: int = 0
    insufficient_data: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可序列化字典."""
        return asdict(self)


@dataclass
class ABResult:
    """A/B 比對結果.

    Attributes:
        change_id: 迭代變更 ID
        description: 變更描述
        baseline_created: 基線建立時間
        observation_days: 已觀察天數
        observation_complete: 觀察期是否完成（需至少 7 天）
        baseline_scores: 基線各維度平均值
        current_scores: 目前各維度平均值
        dimension_changes: 各維度變化量
        regressions: 退化維度列表（退化 >10%）
        overall_verdict: 整體判定（improved / regressed / mixed / insufficient_data）
    """

    change_id: str = ""
    description: str = ""
    baseline_created: str = ""
    observation_days: int = 0
    observation_complete: bool = False
    baseline_scores: Dict[str, float] = field(default_factory=dict)
    current_scores: Dict[str, float] = field(default_factory=dict)
    dimension_changes: Dict[str, float] = field(default_factory=dict)
    regressions: List[str] = field(default_factory=list)
    overall_verdict: str = "insufficient_data"

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可序列化字典."""
        return asdict(self)


@dataclass
class Blindspot:
    """盲點偵測結果.

    四種盲點類型：
    - domain_gap: 某領域整體品質偏低
    - skill_mismatch: 特定技能持續表現不佳
    - user_pattern: 使用者在同一區域反覆修正
    - temporal_drift: 品質隨時間逐漸下滑

    Attributes:
        id: 唯一識別碼
        timestamp: 偵測時間戳
        blindspot_type: 盲點類型
        description: 描述
        severity: 嚴重度（low / medium / high）
        affected_area: 受影響區域
        avg_score: 該區域平均 Q-Score
        global_avg: 全域平均 Q-Score
        gap: 差距
        recommendation: 建議
    """

    id: str = ""
    timestamp: str = ""
    blindspot_type: str = ""
    description: str = ""
    severity: str = "medium"
    affected_area: str = ""
    avg_score: float = 0.0
    global_avg: float = 0.0
    gap: float = 0.0
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可序列化字典."""
        return asdict(self)


@dataclass
class DailySummary:
    """每日品質摘要.

    Attributes:
        date: 摘要日期
        total_interactions: 總互動次數
        avg_q_score: 平均 Q-Score
        satisfaction_proxy: 滿意度代理值
        tier_distribution: 各等級分布 {high: n, medium: n, low: n}
        best_score: 最佳 Q-Score
        worst_score: 最差 Q-Score
        domain_breakdown: 各領域平均 Q-Score
        skill_usage: 技能使用分布
        alerts: 當日警報
        insufficient_data: 是否樣本不足
    """

    date: str = ""
    total_interactions: int = 0
    avg_q_score: float = 0.0
    satisfaction_proxy: float = 0.0
    tier_distribution: Dict[str, int] = field(default_factory=dict)
    best_score: float = 0.0
    worst_score: float = 0.0
    domain_breakdown: Dict[str, float] = field(default_factory=dict)
    skill_usage: Dict[str, int] = field(default_factory=dict)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    insufficient_data: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可序列化字典."""
        return asdict(self)


@dataclass
class WeeklyReport:
    """每週品質報告.

    Attributes:
        week_start: 週起始日
        week_end: 週結束日
        total_interactions: 總互動次數
        avg_q_score: 週平均 Q-Score
        trend_direction: 趨勢方向
        satisfaction_proxy: 週滿意度代理值
        daily_summaries: 每日摘要列表
        blindspots: 盲點更新
        skill_changes: 技能使用變化
        alerts: 週內所有警報
        insufficient_data: 是否樣本不足
    """

    week_start: str = ""
    week_end: str = ""
    total_interactions: int = 0
    avg_q_score: float = 0.0
    trend_direction: str = "stable"
    satisfaction_proxy: float = 0.0
    daily_summaries: List[Dict[str, Any]] = field(default_factory=list)
    blindspots: List[Dict[str, Any]] = field(default_factory=list)
    skill_changes: Dict[str, Any] = field(default_factory=dict)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    insufficient_data: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """轉換為可序列化字典."""
        return asdict(self)


# ════════════════════════════════════════════
# 持久化層
# ════════════════════════════════════════════

class EvalStore:
    """Eval-Engine 持久化層.

    檔案結構：
      data/eval/q_scores.jsonl       — Q-Score 記錄（append-only JSONL）
      data/eval/satisfaction.jsonl   — 滿意度信號（append-only JSONL）
      data/eval/ab_baselines.json    — A/B 基線快照
      data/eval/blindspots.json      — 盲點記錄
      data/eval/alerts.json          — 警報記錄
      data/eval/daily/{date}.json    — 每日摘要
      data/eval/weekly/{week}.json   — 每週報告
    """

    def __init__(self, data_dir: str = "data"):
        """初始化持久化層.

        Args:
            data_dir: 資料根目錄
        """
        self.data_dir = Path(data_dir)
        self.eval_dir = self.data_dir / "eval"
        self.eval_dir.mkdir(parents=True, exist_ok=True)

        # 建立子目錄
        (self.eval_dir / "daily").mkdir(parents=True, exist_ok=True)
        (self.eval_dir / "weekly").mkdir(parents=True, exist_ok=True)

        # 檔案路徑
        self.q_scores_path = self.eval_dir / "q_scores.jsonl"
        self.satisfaction_path = self.eval_dir / "satisfaction.jsonl"
        self.ab_baselines_path = self.eval_dir / "ab_baselines.json"
        self.blindspots_path = self.eval_dir / "blindspots.json"
        self.alerts_path = self.eval_dir / "alerts.json"

        # 執行緒鎖（確保寫入原子性）
        self._write_lock = threading.Lock()

        logger.info(f"EvalStore 初始化完成 | 路徑: {self.eval_dir}")

    # ── JSONL append 寫入 ──

    def append_q_score(self, q_score: QScore) -> None:
        """追加一筆 Q-Score 記錄.

        Args:
            q_score: Q-Score 資料
        """
        with self._write_lock:
            try:
                with open(self.q_scores_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(q_score.to_dict(), ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"寫入 Q-Score 失敗: {e}")

    def append_satisfaction(self, signal: SatisfactionSignal) -> None:
        """追加一筆滿意度信號.

        Args:
            signal: 滿意度信號資料
        """
        with self._write_lock:
            try:
                with open(self.satisfaction_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(signal.to_dict(), ensure_ascii=False) + "\n")
            except Exception as e:
                logger.error(f"寫入滿意度信號失敗: {e}")

    # ── JSONL 讀取 ──

    def load_q_scores(
        self,
        since: Optional[datetime] = None,
        domain: Optional[str] = None,
    ) -> List[QScore]:
        """載入 Q-Score 記錄.

        Args:
            since: 只載入此時間之後的記錄
            domain: 只載入指定領域的記錄

        Returns:
            Q-Score 列表
        """
        scores: List[QScore] = []
        if not self.q_scores_path.exists():
            return scores

        try:
            with open(self.q_scores_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        qs = QScore.from_dict(data)

                        # 時間篩選
                        if since:
                            try:
                                ts = datetime.fromisoformat(qs.timestamp)
                                if ts < since:
                                    continue
                            except (ValueError, TypeError):
                                continue

                        # 領域篩選
                        if domain and qs.domain != domain:
                            continue

                        scores.append(qs)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Q-Score 記錄解析失敗: {e}")
                        continue
        except Exception as e:
            logger.error(f"載入 Q-Score 失敗: {e}")

        return scores

    def load_satisfaction_signals(
        self,
        since: Optional[datetime] = None,
        session_id: Optional[str] = None,
    ) -> List[SatisfactionSignal]:
        """載入滿意度信號記錄.

        Args:
            since: 只載入此時間之後的記錄
            session_id: 只載入指定 session 的記錄

        Returns:
            滿意度信號列表
        """
        signals: List[SatisfactionSignal] = []
        if not self.satisfaction_path.exists():
            return signals

        try:
            with open(self.satisfaction_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        sig = SatisfactionSignal.from_dict(data)

                        # 時間篩選
                        if since:
                            try:
                                ts = datetime.fromisoformat(sig.timestamp)
                                if ts < since:
                                    continue
                            except (ValueError, TypeError):
                                continue

                        # Session 篩選
                        if session_id and sig.session_id != session_id:
                            continue

                        signals.append(sig)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"滿意度信號解析失敗: {e}")
                        continue
        except Exception as e:
            logger.error(f"載入滿意度信號失敗: {e}")

        return signals

    # ── A/B 基線（JSON） ──

    def load_ab_baselines(self) -> Dict[str, Any]:
        """載入所有 A/B 基線.

        Returns:
            基線字典 {change_id: baseline_data}
        """
        if not self.ab_baselines_path.exists():
            return {}
        try:
            with open(self.ab_baselines_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"載入 A/B 基線失敗: {e}")
            return {}

    def save_ab_baseline(self, change_id: str, baseline: Dict[str, Any]) -> bool:
        """儲存 A/B 基線.

        HG-EVAL-BASELINE-LOCK: 已建立的基線不可修改。

        Args:
            change_id: 變更 ID
            baseline: 基線資料

        Returns:
            True 若儲存成功
        """
        with self._write_lock:
            baselines = self.load_ab_baselines()

            # HG-EVAL-BASELINE-LOCK: 基線一旦建立不可修改
            if change_id in baselines:
                logger.warning(
                    f"基線鎖定違規: 嘗試修改已存在的基線 {change_id} — "
                    f"基線一旦建立不可修改，這是數據誠實的基礎"
                )
                return False

            baselines[change_id] = baseline

            try:
                with open(self.ab_baselines_path, "w", encoding="utf-8") as f:
                    json.dump(baselines, f, indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                logger.error(f"儲存 A/B 基線失敗: {e}")
                return False

    # ── 盲點（JSON） ──

    def load_blindspots(self) -> List[Dict[str, Any]]:
        """載入盲點記錄.

        Returns:
            盲點列表
        """
        if not self.blindspots_path.exists():
            return []
        try:
            with open(self.blindspots_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"載入盲點失敗: {e}")
            return []

    def save_blindspots(self, blindspots: List[Dict[str, Any]]) -> None:
        """儲存盲點記錄.

        Args:
            blindspots: 盲點列表
        """
        with self._write_lock:
            try:
                with open(self.blindspots_path, "w", encoding="utf-8") as f:
                    json.dump(blindspots, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"儲存盲點失敗: {e}")

    # ── 警報（JSON） ──

    def load_alerts(self) -> List[Dict[str, Any]]:
        """載入警報記錄.

        Returns:
            警報列表
        """
        if not self.alerts_path.exists():
            return []
        try:
            with open(self.alerts_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"載入警報失敗: {e}")
            return []

    def save_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        """儲存警報記錄.

        Args:
            alerts: 警報列表
        """
        with self._write_lock:
            try:
                with open(self.alerts_path, "w", encoding="utf-8") as f:
                    json.dump(alerts, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"儲存警報失敗: {e}")

    def append_alert(self, alert: Alert) -> None:
        """追加一筆警報.

        Args:
            alert: 警報資料
        """
        with self._write_lock:
            alerts = self.load_alerts()
            alerts.append(alert.to_dict())
            try:
                with open(self.alerts_path, "w", encoding="utf-8") as f:
                    json.dump(alerts, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"追加警報失敗: {e}")

    # ── 每日摘要 ──

    def save_daily_summary(self, summary: DailySummary) -> None:
        """儲存每日品質摘要.

        Args:
            summary: 每日摘要
        """
        path = self.eval_dir / "daily" / f"{summary.date}.json"
        with self._write_lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(summary.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"儲存每日摘要失敗: {e}")

    def load_daily_summary(self, date_str: str) -> Optional[DailySummary]:
        """載入指定日期的每日摘要.

        Args:
            date_str: 日期字串（YYYY-MM-DD）

        Returns:
            每日摘要，或 None
        """
        path = self.eval_dir / "daily" / f"{date_str}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return DailySummary(**{
                k: v for k, v in data.items()
                if k in DailySummary.__dataclass_fields__
            })
        except Exception as e:
            logger.error(f"載入每日摘要失敗: {e}")
            return None

    # ── 每週報告 ──

    def save_weekly_report(self, report: WeeklyReport) -> None:
        """儲存每週品質報告.

        Args:
            report: 每週報告
        """
        # 使用週起始日作為檔名
        path = self.eval_dir / "weekly" / f"{report.week_start}.json"
        with self._write_lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"儲存每週報告失敗: {e}")


# ════════════════════════════════════════════
# 主引擎
# ════════════════════════════════════════════

class EvalEngine:
    """Eval-Engine 主引擎 — MUSEON 品質度量的中樞.

    整合 Q-Score、滿意度代理、趨勢追蹤、A/B 比對、盲點雷達、
    Skill 使用率熱力圖，以及背景運行的每日/每週報告生成。
    """

    def __init__(self, data_dir: str = "data"):
        """初始化 Eval-Engine.

        Args:
            data_dir: 資料根目錄
        """
        self.data_dir = Path(data_dir)
        self.store = EvalStore(data_dir=data_dir)

        # Skill 使用日誌路徑（與 Brain 共用）
        self.skill_usage_log_path = self.data_dir / "skill_usage_log.jsonl"

        logger.info("Eval-Engine 初始化完成")

    # ════════════════════════════════════════════
    # Section 1: Q-Score 計算
    # ════════════════════════════════════════════

    def evaluate(
        self,
        user_content: str,
        response_content: str,
        matched_skills: Optional[List[str]] = None,
        domain: str = "general",
        session_id: str = "",
        understanding: Optional[float] = None,
        depth: Optional[float] = None,
        clarity: Optional[float] = None,
        actionability: Optional[float] = None,
    ) -> QScore:
        """計算一次回答的 Q-Score.

        接收 deep-think Phase 2 四點審計的結果，計算加權 Q-Score。
        若未提供審計分數，則從回答內容啟發式推估。

        HG-EVAL-HONEST: 不美化數據，退化就說退化。
        SG-EVAL-PRIVACY: 不儲存對話原文，只儲存分數和 metadata。

        Args:
            user_content: 使用者訊息（僅用於啟發式評估，不會被儲存）
            response_content: 回覆內容（僅用於啟發式評估，不會被儲存）
            matched_skills: 匹配到的技能列表
            domain: 所屬領域
            session_id: 對話 ID
            understanding: deep-think 理解度分數（0.0-1.0）
            depth: deep-think 深度分數（0.0-1.0）
            clarity: deep-think 清晰度分數（0.0-1.0）
            actionability: deep-think 可行動性分數（0.0-1.0）

        Returns:
            計算完成的 QScore
        """
        now = datetime.now()

        # 如果 deep-think Phase 2 審計分數已提供，直接使用
        # 否則使用啟發式推估（不依賴外部 API）
        if all(v is not None for v in [understanding, depth, clarity, actionability]):
            u = max(0.0, min(1.0, understanding))
            d = max(0.0, min(1.0, depth))
            c = max(0.0, min(1.0, clarity))
            a = max(0.0, min(1.0, actionability))
        else:
            u, d, c, a = self._heuristic_evaluate(user_content, response_content)

        q_score = QScore(
            id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=now.isoformat(),
            domain=domain,
            understanding=u,
            depth=d,
            clarity=c,
            actionability=a,
            matched_skills=matched_skills or [],
        )
        q_score.compute()

        # 持久化（不含對話原文）
        self.store.append_q_score(q_score)

        # 零值維度額外警告
        if q_score.zero_dimensions:
            for dim in q_score.zero_dimensions:
                alert = Alert(
                    id=str(uuid.uuid4()),
                    timestamp=now.isoformat(),
                    alert_type="zero_dimension",
                    severity="warning",
                    message=f"維度 {dim} 為零",
                    details={
                        "dimension": dim,
                        "q_score_id": q_score.id,
                        "session_id": session_id,
                    },
                )
                self.store.append_alert(alert)
                logger.warning(f"零值維度警告: {dim} = 0.0 | Q-Score={q_score.score:.4f}")

        logger.info(
            f"Q-Score 計算完成 | score={q_score.score:.4f} | "
            f"tier={q_score.tier} | domain={domain} | "
            f"U={u:.2f} D={d:.2f} C={c:.2f} A={a:.2f}"
        )

        return q_score

    def _heuristic_evaluate(
        self,
        user_content: str,
        response_content: str,
    ) -> Tuple[float, float, float, float]:
        """啟發式品質推估（當 deep-think Phase 2 不可用時的降級方案）.

        基於回覆的結構特徵做簡單推估，不依賴 LLM。
        HG-EVAL-HONEST: 啟發式推估的分數會偏保守。

        Args:
            user_content: 使用者訊息
            response_content: 回覆內容

        Returns:
            (understanding, depth, clarity, actionability) 四維分數
        """
        resp_len = len(response_content)
        user_len = len(user_content)

        # ── 系統失敗偵測：區分「系統失敗」vs「合理短回覆」 ──
        _SAFETY_NET_MARKERS = (
            "抱歉，工具執行過程中", "請再試一次或換個方式",
            "[工具執行失敗]", "工具執行過程中遇到了問題",
        )
        _SYSTEM_ERROR_MARKERS = (
            "SDK Error", "Exception", "500", "timeout", "超時",
            "API 不可用", "離線模式",
        )
        is_safety_net = any(m in response_content for m in _SAFETY_NET_MARKERS)
        is_system_error = any(m in response_content for m in _SYSTEM_ERROR_MARKERS)

        # 合理短回覆偵測：某些情境本就不需要長回覆
        _SHORT_RESPONSE_OK = (
            "好的", "收到", "了解", "沒問題", "OK", "知道了",
            "已完成", "已記住", "已更新", "好啊", "嗯",
        )
        is_legit_short = (
            resp_len > 0
            and resp_len < 50
            and any(m in response_content for m in _SHORT_RESPONSE_OK)
        )

        # 理解度 — 回覆長度是否合理匹配使用者問題的複雜度
        if resp_len == 0:
            understanding = 0.0
        elif is_safety_net or is_system_error:
            # 系統層面問題 → 不懲罰 understanding，標記為系統問題
            understanding = 0.3
        elif is_legit_short:
            # 合理的簡短回覆（打招呼、確認等）→ 給正常分
            understanding = 0.6
        elif user_len > 0 and resp_len > user_len * 0.3:
            # 回覆長度與問題複雜度匹配 → 給較高分，上限 0.85
            ratio = resp_len / max(user_len * 3, 1)
            understanding = min(0.85, 0.5 + ratio * 0.25)
        elif resp_len > 0 and resp_len < 30 and user_len > 100:
            # 回覆過短但使用者問題很長 → 可能真的沒理解
            understanding = 0.25
        else:
            understanding = 0.4

        # 深度 — 基於回覆長度和段落結構
        paragraphs = [p for p in response_content.split("\n\n") if p.strip()]
        if is_legit_short:
            # 合理短回覆不應因「淺」被扣分
            depth_score = 0.5
        elif len(paragraphs) >= 5:
            depth_score = min(0.85, 0.5 + len(paragraphs) * 0.05)
        elif len(paragraphs) >= 3:
            depth_score = min(0.75, 0.4 + len(paragraphs) * 0.07)
        elif len(paragraphs) >= 1:
            depth_score = 0.4
        else:
            depth_score = 0.2

        # 清晰度 — 基於結構標記的豐富度（而非僅存在與否）
        # 注意："：" 在中文太常見，不當作結構標記
        _structure_markers = ["- ", "1.", "2.", "##", "**", "```", "→", "•"]
        structure_count = sum(
            1 for m in _structure_markers if m in response_content
        )
        has_headings = "##" in response_content or "**" in response_content
        has_lists = "- " in response_content or "1." in response_content
        has_code = "```" in response_content

        if is_legit_short:
            clarity_score = 0.6
        elif structure_count >= 4:
            clarity_score = 0.85
        elif structure_count >= 3 and has_headings:
            clarity_score = 0.8
        elif structure_count >= 2:
            clarity_score = 0.7
        elif has_lists or has_headings:
            clarity_score = 0.6
        elif resp_len > 100:
            clarity_score = 0.45
        else:
            clarity_score = 0.4

        # 可行動性 — 基於行動指引的深度，而非僅存在與否
        _action_strong = ["下一步", "步驟", "具體做法", "行動計畫", "TODO", "action plan"]
        _action_medium = ["建議", "可以", "試試", "方案", "考慮", "Plan"]
        _action_weak = ["或許", "也許", "參考", "思考", "next step"]
        strong_count = sum(1 for kw in _action_strong if kw in response_content)
        medium_count = sum(1 for kw in _action_medium if kw in response_content)
        weak_count = sum(1 for kw in _action_weak if kw in response_content)

        if is_legit_short:
            actionability_score = 0.5
        elif strong_count >= 2:
            actionability_score = 0.85
        elif strong_count >= 1:
            actionability_score = 0.75
        elif medium_count >= 2:
            actionability_score = 0.65
        elif medium_count >= 1:
            actionability_score = 0.55
        elif weak_count >= 1:
            actionability_score = 0.4
        else:
            actionability_score = 0.3

        return (understanding, depth_score, clarity_score, actionability_score)

    # ════════════════════════════════════════════
    # Section 2: 滿意度代理
    # ════════════════════════════════════════════

    def record_satisfaction(
        self,
        session_id: str,
        signal_type: str,
        signal_value: Optional[float] = None,
        context: str = "",
        q_score_id: str = "",
    ) -> SatisfactionSignal:
        """記錄滿意度代理信號.

        正向信號權重 +1.0，負向信號權重 -1.5（negativity bias）。
        SG-EVAL-PRIVACY: context 只描述行為類型，不含對話原文。

        Args:
            session_id: 對話 ID
            signal_type: 信號類型（"positive" 或 "negative"）
            signal_value: 信號值（若未提供則依 signal_type 自動設定）
            context: 行為描述
            q_score_id: 關聯的 Q-Score ID

        Returns:
            已記錄的 SatisfactionSignal
        """
        now = datetime.now()

        # 自動設定信號值（含 negativity bias）
        if signal_value is None:
            if signal_type == "positive":
                signal_value = 1.0
            else:
                signal_value = -NEGATIVITY_BIAS  # -1.5

        signal = SatisfactionSignal(
            id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=now.isoformat(),
            signal_type=signal_type,
            signal_value=signal_value,
            context=context,
            q_score_id=q_score_id,
        )

        self.store.append_satisfaction(signal)

        logger.info(
            f"滿意度信號記錄 | type={signal_type} | "
            f"value={signal_value} | context={context}"
        )

        return signal

    def compute_satisfaction_proxy(
        self,
        since: Optional[datetime] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """計算滿意度代理指標.

        公式：Satisfaction Proxy = (正向信號總和 + 負向信號總和) / 總互動次數
        - > 0.5 → 健康
        - 0 ~ 0.5 → 觀察中
        - < 0 → 警報

        HG-EVAL-HONEST: 樣本不足時回報 insufficient_data。

        Args:
            since: 計算起始時間
            session_id: 限定 session

        Returns:
            滿意度代理結果字典
        """
        signals = self.store.load_satisfaction_signals(
            since=since, session_id=session_id
        )

        total_count = len(signals)

        # HG-EVAL-HONEST: 樣本不足
        if total_count < MIN_SAMPLE_SIZE:
            return {
                "proxy_value": 0.0,
                "status": "insufficient_data",
                "total_signals": total_count,
                "positive_count": sum(1 for s in signals if s.signal_type == "positive"),
                "negative_count": sum(1 for s in signals if s.signal_type == "negative"),
                "note": f"僅供參考：樣本數 {total_count} < {MIN_SAMPLE_SIZE}",
            }

        positive_sum = sum(s.signal_value for s in signals if s.signal_type == "positive")
        negative_sum = sum(s.signal_value for s in signals if s.signal_type == "negative")
        proxy_value = (positive_sum + negative_sum) / total_count

        # 狀態判定
        if proxy_value > 0.5:
            status = "healthy"
        elif proxy_value >= 0:
            status = "observing"
        else:
            status = "alert"

        return {
            "proxy_value": round(proxy_value, 4),
            "status": status,
            "total_signals": total_count,
            "positive_count": sum(1 for s in signals if s.signal_type == "positive"),
            "negative_count": sum(1 for s in signals if s.signal_type == "negative"),
            "positive_sum": round(positive_sum, 4),
            "negative_sum": round(negative_sum, 4),
        }

    # ════════════════════════════════════════════
    # Section 3: 趨勢追蹤
    # ════════════════════════════════════════════

    def get_trend(
        self,
        days: int = 7,
        domain: Optional[str] = None,
    ) -> TrendData:
        """取得 Q-Score 趨勢資料.

        計算每日平均 Q-Score 與滾動平均，並判定趨勢方向。

        HG-EVAL-HONEST: 樣本不足時標記 insufficient_data。

        Args:
            days: 追蹤天數（預設 7 天）
            domain: 領域篩選

        Returns:
            TrendData 趨勢資料
        """
        since = datetime.now() - timedelta(days=days)
        scores = self.store.load_q_scores(since=since, domain=domain)

        trend = TrendData(
            period_days=days,
            domain=domain,
            sample_count=len(scores),
        )

        # HG-EVAL-HONEST: 樣本不足
        if len(scores) < MIN_SAMPLE_SIZE:
            trend.insufficient_data = True
            # 仍然計算可用數據，但標記為僅供參考
            if not scores:
                return trend

        # 按日分組計算每日平均
        daily_groups: Dict[str, List[float]] = {}
        for qs in scores:
            try:
                day_key = datetime.fromisoformat(qs.timestamp).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue
            if day_key not in daily_groups:
                daily_groups[day_key] = []
            daily_groups[day_key].append(qs.score)

        # 計算每日平均
        for day_key in sorted(daily_groups.keys()):
            values = daily_groups[day_key]
            trend.daily_averages[day_key] = round(
                sum(values) / len(values), 4
            )

        # 滾動平均
        all_scores = [qs.score for qs in scores]
        if all_scores:
            trend.rolling_average = round(
                sum(all_scores) / len(all_scores), 4
            )

        # 趨勢方向判定（比較前半段和後半段平均）
        sorted_days = sorted(trend.daily_averages.keys())
        if len(sorted_days) >= 3:
            mid = len(sorted_days) // 2
            first_half = [trend.daily_averages[d] for d in sorted_days[:mid]]
            second_half = [trend.daily_averages[d] for d in sorted_days[mid:]]

            avg_first = sum(first_half) / len(first_half) if first_half else 0
            avg_second = sum(second_half) / len(second_half) if second_half else 0

            diff = avg_second - avg_first
            if diff > 0.05:
                trend.direction = "up"
            elif diff < -0.05:
                trend.direction = "down"
            else:
                trend.direction = "stable"

        return trend

    # ════════════════════════════════════════════
    # Section 3 延伸: 警報系統
    # ════════════════════════════════════════════

    def check_alerts(self) -> List[Alert]:
        """檢查品質警報.

        目前偵測：
        1. 連續 3 次低分（Q-Score < 0.5）
        2. 連續 3 天趨勢下降

        Returns:
            觸發的警報列表
        """
        alerts: List[Alert] = []
        now = datetime.now()

        # ── 偵測 1: 連續低分 ──
        recent_scores = self.store.load_q_scores(
            since=now - timedelta(days=7)
        )

        if len(recent_scores) >= CONSECUTIVE_LOW_ALERT_COUNT:
            # 取最近 N 筆，檢查是否連續低於閾值
            tail = recent_scores[-CONSECUTIVE_LOW_ALERT_COUNT:]
            if all(qs.score < TIER_LOW_THRESHOLD for qs in tail):
                # 收集弱項維度
                weak_dims: Dict[str, List[float]] = {
                    "understanding": [],
                    "depth": [],
                    "clarity": [],
                    "actionability": [],
                }
                for qs in tail:
                    weak_dims["understanding"].append(qs.understanding)
                    weak_dims["depth"].append(qs.depth)
                    weak_dims["clarity"].append(qs.clarity)
                    weak_dims["actionability"].append(qs.actionability)

                # 找出最弱的維度
                dim_avgs = {
                    dim: sum(vals) / len(vals)
                    for dim, vals in weak_dims.items()
                    if vals
                }
                weakest = min(dim_avgs, key=dim_avgs.get) if dim_avgs else "unknown"

                alert = Alert(
                    id=str(uuid.uuid4()),
                    timestamp=now.isoformat(),
                    alert_type="consecutive_low",
                    severity="critical",
                    message=(
                        f"連續 {CONSECUTIVE_LOW_ALERT_COUNT} 次 Q-Score 低於 "
                        f"{TIER_LOW_THRESHOLD}，最弱維度: {weakest}"
                    ),
                    details={
                        "recent_scores": [qs.score for qs in tail],
                        "dimension_averages": {
                            k: round(v, 4) for k, v in dim_avgs.items()
                        },
                        "weakest_dimension": weakest,
                    },
                )
                alerts.append(alert)
                self.store.append_alert(alert)
                logger.warning(f"品質警報: 連續 {CONSECUTIVE_LOW_ALERT_COUNT} 次低分")

        # ── 偵測 2: 連續 3 天下降 ──
        trend = self.get_trend(days=7)
        sorted_days = sorted(trend.daily_averages.keys())
        if len(sorted_days) >= 3:
            last_3 = sorted_days[-3:]
            values = [trend.daily_averages[d] for d in last_3]
            if values[0] > values[1] > values[2]:
                alert = Alert(
                    id=str(uuid.uuid4()),
                    timestamp=now.isoformat(),
                    alert_type="trend_declining",
                    severity="warning",
                    message="連續 3 天 Q-Score 下降",
                    details={
                        "daily_scores": {d: trend.daily_averages[d] for d in last_3},
                    },
                )
                alerts.append(alert)
                self.store.append_alert(alert)
                logger.warning("品質警報: 連續 3 天下降趨勢")

        return alerts

    # ════════════════════════════════════════════
    # Section 4: A/B 比對器
    # ════════════════════════════════════════════

    def create_ab_baseline(
        self,
        change_id: str,
        description: str,
    ) -> Dict[str, Any]:
        """建立 A/B 比對基線快照.

        HG-EVAL-BASELINE-LOCK: 基線一旦建立不可事後修改。

        擷取最近 7 天的品質資料作為基線：
        - 平均 Q-Score
        - 各維度平均分數
        - Satisfaction Proxy
        - 匹配技能命中率

        Args:
            change_id: 變更識別碼（如版本號 v2.1.1 → v2.1.2）
            description: 變更描述

        Returns:
            基線資料字典
        """
        now = datetime.now()
        since = now - timedelta(days=7)
        scores = self.store.load_q_scores(since=since)

        # 建立基線統計
        if scores:
            avg_q = sum(qs.score for qs in scores) / len(scores)
            avg_understanding = sum(qs.understanding for qs in scores) / len(scores)
            avg_depth = sum(qs.depth for qs in scores) / len(scores)
            avg_clarity = sum(qs.clarity for qs in scores) / len(scores)
            avg_actionability = sum(qs.actionability for qs in scores) / len(scores)
        else:
            avg_q = 0.0
            avg_understanding = 0.0
            avg_depth = 0.0
            avg_clarity = 0.0
            avg_actionability = 0.0

        # 滿意度代理
        sat_proxy = self.compute_satisfaction_proxy(since=since)

        baseline = {
            "change_id": change_id,
            "description": description,
            "created_at": now.isoformat(),
            "locked": True,  # HG-EVAL-BASELINE-LOCK: 建立即鎖定
            "observation_start": now.isoformat(),
            "observation_end": (now + timedelta(days=AB_OBSERVATION_DAYS)).isoformat(),
            "sample_count": len(scores),
            "scores": {
                "q_score_avg": round(avg_q, 4),
                "understanding": round(avg_understanding, 4),
                "depth": round(avg_depth, 4),
                "clarity": round(avg_clarity, 4),
                "actionability": round(avg_actionability, 4),
            },
            "satisfaction_proxy": sat_proxy.get("proxy_value", 0.0),
        }

        # 儲存（含鎖定檢查）
        saved = self.store.save_ab_baseline(change_id, baseline)
        if not saved:
            logger.error(
                f"A/B 基線建立失敗: change_id={change_id} "
                f"（可能已存在且被鎖定）"
            )
            return {
                "error": "基線一旦建立不可修改，這是數據誠實的基礎",
                "change_id": change_id,
            }

        logger.info(
            f"A/B 基線已建立且鎖定 | change_id={change_id} | "
            f"baseline_q_score={avg_q:.4f} | samples={len(scores)}"
        )

        return baseline

    def compare_ab(self, change_id: str) -> ABResult:
        """執行 A/B 比對.

        比較基線（迭代前）與目前（迭代後）的各維度分數。
        若任何維度退化 > 10%，標記警告。
        觀察期不足 7 天時，回報參考值但不做正式判定。

        Args:
            change_id: 變更識別碼

        Returns:
            ABResult 比對結果
        """
        baselines = self.store.load_ab_baselines()
        result = ABResult(change_id=change_id)

        # 基線不存在
        if change_id not in baselines:
            result.overall_verdict = "insufficient_data"
            logger.warning(f"A/B 比對: 找不到基線 change_id={change_id}")
            return result

        baseline = baselines[change_id]
        result.description = baseline.get("description", "")
        result.baseline_created = baseline.get("created_at", "")
        result.baseline_scores = baseline.get("scores", {})

        # 計算已觀察天數
        try:
            created = datetime.fromisoformat(baseline["created_at"])
            observation_days = (datetime.now() - created).days
        except (ValueError, KeyError, TypeError):
            observation_days = 0

        result.observation_days = observation_days
        result.observation_complete = observation_days >= AB_OBSERVATION_DAYS

        # 載入基線建立後的 Q-Score
        try:
            since = datetime.fromisoformat(baseline["created_at"])
        except (ValueError, KeyError, TypeError):
            since = datetime.now() - timedelta(days=7)

        current_scores = self.store.load_q_scores(since=since)

        # HG-EVAL-HONEST: 樣本不足
        if not current_scores:
            result.overall_verdict = "insufficient_data"
            return result

        # 計算目前各維度平均
        result.current_scores = {
            "q_score_avg": round(
                sum(qs.score for qs in current_scores) / len(current_scores), 4
            ),
            "understanding": round(
                sum(qs.understanding for qs in current_scores) / len(current_scores), 4
            ),
            "depth": round(
                sum(qs.depth for qs in current_scores) / len(current_scores), 4
            ),
            "clarity": round(
                sum(qs.clarity for qs in current_scores) / len(current_scores), 4
            ),
            "actionability": round(
                sum(qs.actionability for qs in current_scores) / len(current_scores), 4
            ),
        }

        # 計算各維度變化
        dimensions = ["q_score_avg", "understanding", "depth", "clarity", "actionability"]
        regressions: List[str] = []

        for dim in dimensions:
            baseline_val = result.baseline_scores.get(dim, 0.0)
            current_val = result.current_scores.get(dim, 0.0)
            change = current_val - baseline_val
            result.dimension_changes[dim] = round(change, 4)

            # 退化偵測：基線值 > 0 且退化超過 10%
            if baseline_val > 0 and change < 0:
                regression_pct = abs(change) / baseline_val
                if regression_pct > AB_REGRESSION_THRESHOLD:
                    regressions.append(dim)

        result.regressions = regressions

        # 觀察期不足：只提供參考值，不做正式判定
        if not result.observation_complete:
            result.overall_verdict = "insufficient_data"
            logger.info(
                f"A/B 比對: 觀察期不足 | change_id={change_id} | "
                f"已觀察 {observation_days} 天（需至少 {AB_OBSERVATION_DAYS} 天）"
            )
            return result

        # 正式判定
        if regressions:
            if all(
                result.dimension_changes.get(d, 0) < 0 for d in dimensions
            ):
                result.overall_verdict = "regressed"
            else:
                result.overall_verdict = "mixed"

            # 生成退化警報
            for dim in regressions:
                baseline_val = result.baseline_scores.get(dim, 0.0)
                current_val = result.current_scores.get(dim, 0.0)
                change_pct = (
                    abs(current_val - baseline_val) / baseline_val * 100
                    if baseline_val > 0 else 0
                )
                alert = Alert(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.now().isoformat(),
                    alert_type="ab_regression",
                    severity="warning",
                    message=(
                        f"{dim} 自變更 {change_id} 以來下降了 "
                        f"{change_pct:.1f}%"
                    ),
                    details={
                        "change_id": change_id,
                        "dimension": dim,
                        "baseline_value": baseline_val,
                        "current_value": current_val,
                        "regression_pct": round(change_pct, 2),
                    },
                )
                self.store.append_alert(alert)
        else:
            result.overall_verdict = "improved"

        logger.info(
            f"A/B 比對完成 | change_id={change_id} | "
            f"verdict={result.overall_verdict} | regressions={regressions}"
        )

        return result

    # ════════════════════════════════════════════
    # Section 5: 盲點雷達
    # ════════════════════════════════════════════

    def scan_blindspots(self) -> List[Blindspot]:
        """執行盲點掃描.

        四種盲點類型：
        1. domain_gap — 某領域整體品質偏低（低於全域平均 0.15 以上）
        2. skill_mismatch — 特定技能持續表現不佳
        3. user_pattern — 使用者在同一區域反覆修正（負向滿意度集中）
        4. temporal_drift — 品質隨時間逐漸下滑

        HG-EVAL-HONEST: 樣本不足時不報虛假盲點。

        Returns:
            偵測到的盲點列表
        """
        blindspots: List[Blindspot] = []
        now = datetime.now()

        # 載入近 30 天數據
        since = now - timedelta(days=30)
        all_scores = self.store.load_q_scores(since=since)

        # HG-EVAL-HONEST: 樣本不足
        if len(all_scores) < MIN_SAMPLE_SIZE:
            logger.info(
                f"盲點掃描: 樣本不足 ({len(all_scores)} < {MIN_SAMPLE_SIZE})，跳過"
            )
            return blindspots

        # 全域平均
        global_avg = sum(qs.score for qs in all_scores) / len(all_scores)

        # ── 盲點 1: 領域差距 (domain_gap) ──
        domain_groups: Dict[str, List[QScore]] = {}
        for qs in all_scores:
            if qs.domain not in domain_groups:
                domain_groups[qs.domain] = []
            domain_groups[qs.domain].append(qs)

        for domain, scores in domain_groups.items():
            if len(scores) < 3:
                # 單一領域樣本太少，跳過
                continue
            domain_avg = sum(qs.score for qs in scores) / len(scores)
            gap = global_avg - domain_avg

            if gap >= BLINDSPOT_DOMAIN_GAP_THRESHOLD:
                blindspots.append(Blindspot(
                    id=str(uuid.uuid4()),
                    timestamp=now.isoformat(),
                    blindspot_type="domain_gap",
                    description=f"領域 {domain} 的品質低於全域平均 {gap:.2f}",
                    severity="high" if gap >= 0.25 else "medium",
                    affected_area=domain,
                    avg_score=round(domain_avg, 4),
                    global_avg=round(global_avg, 4),
                    gap=round(gap, 4),
                    recommendation=f"建議針對 {domain} 領域加強訓練或新增專屬技能",
                ))

        # ── 盲點 2: 技能不匹配 (skill_mismatch) ──
        skill_scores: Dict[str, List[float]] = {}
        for qs in all_scores:
            for skill in qs.matched_skills:
                if skill not in skill_scores:
                    skill_scores[skill] = []
                skill_scores[skill].append(qs.score)

        for skill, scores_list in skill_scores.items():
            if len(scores_list) < 3:
                continue
            skill_avg = sum(scores_list) / len(scores_list)
            gap = global_avg - skill_avg

            if gap >= BLINDSPOT_DOMAIN_GAP_THRESHOLD:
                blindspots.append(Blindspot(
                    id=str(uuid.uuid4()),
                    timestamp=now.isoformat(),
                    blindspot_type="skill_mismatch",
                    description=f"技能 {skill} 觸發時品質偏低（均分 {skill_avg:.2f}）",
                    severity="high" if gap >= 0.25 else "medium",
                    affected_area=skill,
                    avg_score=round(skill_avg, 4),
                    global_avg=round(global_avg, 4),
                    gap=round(gap, 4),
                    recommendation=f"檢查技能 {skill} 的觸發詞是否太寬泛，或內容需要更新",
                ))

        # ── 盲點 3: 使用者修正模式 (user_pattern) ──
        signals = self.store.load_satisfaction_signals(since=since)
        # 按 session 分組找負向信號集中的 domain
        neg_by_domain: Dict[str, int] = {}
        for sig in signals:
            if sig.signal_type == "negative":
                # 嘗試找對應的 Q-Score 的 domain
                for qs in all_scores:
                    if qs.id == sig.q_score_id:
                        domain = qs.domain
                        neg_by_domain[domain] = neg_by_domain.get(domain, 0) + 1
                        break

        total_negative = sum(neg_by_domain.values())
        for domain, neg_count in neg_by_domain.items():
            # 某領域的負向信號佔比超過 40%
            if total_negative > 0 and neg_count / total_negative > 0.4 and neg_count >= 3:
                blindspots.append(Blindspot(
                    id=str(uuid.uuid4()),
                    timestamp=now.isoformat(),
                    blindspot_type="user_pattern",
                    description=f"使用者在 {domain} 領域反覆修正（{neg_count} 次負向信號）",
                    severity="high",
                    affected_area=domain,
                    avg_score=0.0,
                    global_avg=round(global_avg, 4),
                    gap=0.0,
                    recommendation=f"分析 {domain} 領域的常見修正模式，調整回覆策略",
                ))

        # ── 盲點 4: 時間漂移 (temporal_drift) ──
        # 比較前 15 天與後 15 天的平均 Q-Score
        mid_date = now - timedelta(days=15)
        first_half = [
            qs for qs in all_scores
            if _safe_parse_ts(qs.timestamp, now) < mid_date
        ]
        second_half = [
            qs for qs in all_scores
            if _safe_parse_ts(qs.timestamp, now) >= mid_date
        ]

        if len(first_half) >= 5 and len(second_half) >= 5:
            avg_first = sum(qs.score for qs in first_half) / len(first_half)
            avg_second = sum(qs.score for qs in second_half) / len(second_half)
            drift = avg_first - avg_second

            if drift >= 0.10:
                blindspots.append(Blindspot(
                    id=str(uuid.uuid4()),
                    timestamp=now.isoformat(),
                    blindspot_type="temporal_drift",
                    description=f"品質在近 15 天下降了 {drift:.2f}（前半均 {avg_first:.2f} → 後半均 {avg_second:.2f}）",
                    severity="high" if drift >= 0.20 else "medium",
                    affected_area="overall",
                    avg_score=round(avg_second, 4),
                    global_avg=round(avg_first, 4),
                    gap=round(drift, 4),
                    recommendation="建議進行全面品質檢視，可能需要 Morphenix 介入迭代",
                ))

        # 持久化盲點
        self.store.save_blindspots([b.to_dict() for b in blindspots])

        logger.info(f"盲點掃描完成 | 偵測到 {len(blindspots)} 個盲點")
        return blindspots

    # ════════════════════════════════════════════
    # Section 6: Skill 使用率熱力圖
    # ════════════════════════════════════════════

    def get_skill_heatmap(self, days: int = 30) -> Dict[str, Any]:
        """取得 Skill 使用率熱力圖.

        統計每個技能的觸發次數、採用次數、採用率、共現頻率。
        識別閒置技能（超過 30 天未使用）和低採用率技能。

        Args:
            days: 統計天數（預設 30 天）

        Returns:
            熱力圖資料字典
        """
        since = datetime.now() - timedelta(days=days)

        # 從 Q-Score 記錄提取技能使用
        scores = self.store.load_q_scores(since=since)

        # 從 skill_usage_log.jsonl 讀取更詳細的觸發記錄
        usage_log = self._load_skill_usage_log(since=since)

        # 技能統計
        skill_stats: Dict[str, Dict[str, Any]] = {}

        # 從 Q-Score 統計採用（實際在回答中使用）
        for qs in scores:
            for skill in qs.matched_skills:
                if skill not in skill_stats:
                    skill_stats[skill] = {
                        "trigger_count": 0,
                        "adoption_count": 0,
                        "adoption_rate": 0.0,
                        "domains": {},
                        "co_occurrences": {},
                        "last_used": "",
                    }
                skill_stats[skill]["adoption_count"] += 1
                skill_stats[skill]["last_used"] = qs.timestamp

                # 領域分布
                domain = qs.domain
                domains = skill_stats[skill]["domains"]
                domains[domain] = domains.get(domain, 0) + 1

                # 共現統計
                for other_skill in qs.matched_skills:
                    if other_skill != skill:
                        co = skill_stats[skill]["co_occurrences"]
                        co[other_skill] = co.get(other_skill, 0) + 1

        # 從 skill_usage_log 統計觸發
        for entry in usage_log:
            skills = entry.get("skills", [])
            for skill in skills:
                if skill not in skill_stats:
                    skill_stats[skill] = {
                        "trigger_count": 0,
                        "adoption_count": 0,
                        "adoption_rate": 0.0,
                        "domains": {},
                        "co_occurrences": {},
                        "last_used": "",
                    }
                skill_stats[skill]["trigger_count"] += 1

        # 計算採用率
        idle_skills: List[str] = []
        low_adoption_skills: List[str] = []

        for skill, stats in skill_stats.items():
            trigger = stats["trigger_count"]
            adoption = stats["adoption_count"]

            # 觸發數至少等於採用數（觸發包含採用）
            if trigger < adoption:
                trigger = adoption

            stats["trigger_count"] = trigger
            stats["adoption_rate"] = (
                round(adoption / trigger, 4) if trigger > 0 else 0.0
            )

            # 低採用率警告（< 50%）
            if trigger >= 5 and stats["adoption_rate"] < 0.50:
                low_adoption_skills.append(skill)

            # 閒置判定
            if trigger == 0:
                idle_skills.append(skill)

        # 計算共現頻率（轉為百分比）
        for skill, stats in skill_stats.items():
            total = stats["adoption_count"]
            if total > 0:
                for co_skill in stats["co_occurrences"]:
                    stats["co_occurrences"][co_skill] = round(
                        stats["co_occurrences"][co_skill] / total, 4
                    )

        return {
            "period_days": days,
            "total_skills_tracked": len(skill_stats),
            "skills": skill_stats,
            "idle_skills": idle_skills,
            "low_adoption_skills": low_adoption_skills,
            "warnings": [
                f"技能 {s} 採用率偏低（{skill_stats[s]['adoption_rate']:.0%}），"
                f"可能觸發詞太寬泛"
                for s in low_adoption_skills
            ],
        }

    def _load_skill_usage_log(
        self,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """載入 Skill 使用日誌.

        Args:
            since: 只載入此時間之後的記錄

        Returns:
            使用記錄列表
        """
        entries: List[Dict[str, Any]] = []
        if not self.skill_usage_log_path.exists():
            return entries

        try:
            with open(self.skill_usage_log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)

                        # 時間篩選
                        if since:
                            ts_str = entry.get("timestamp", "")
                            try:
                                ts = datetime.fromisoformat(ts_str)
                                if ts < since:
                                    continue
                            except (ValueError, TypeError):
                                continue

                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"載入 Skill 使用日誌失敗: {e}")

        return entries

    # ════════════════════════════════════════════
    # Section 7: 背景運行 — 每日摘要 & 每週報告
    # ════════════════════════════════════════════

    def generate_daily_summary(
        self,
        target_date: Optional[date] = None,
    ) -> DailySummary:
        """生成每日品質摘要.

        彙總指定日期的所有 Q-Score、滿意度信號、警報。
        由 Nightly Job 在 00:00 呼叫。

        HG-EVAL-HONEST: 樣本不足時標記 insufficient_data。

        Args:
            target_date: 目標日期（預設昨天）

        Returns:
            DailySummary 每日摘要
        """
        if target_date is None:
            target_date = (datetime.now() - timedelta(days=1)).date()

        date_str = target_date.isoformat()

        # 載入當日 Q-Score
        day_start = datetime.combine(target_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        all_scores = self.store.load_q_scores(since=day_start)
        day_scores = [
            qs for qs in all_scores
            if _safe_parse_ts(qs.timestamp, day_start) < day_end
        ]

        summary = DailySummary(date=date_str)
        summary.total_interactions = len(day_scores)

        # HG-EVAL-HONEST: 樣本不足
        if len(day_scores) < 1:
            summary.insufficient_data = True
            self.store.save_daily_summary(summary)
            return summary

        if len(day_scores) < MIN_SAMPLE_SIZE:
            summary.insufficient_data = True

        # 平均 Q-Score
        scores_vals = [qs.score for qs in day_scores]
        summary.avg_q_score = round(sum(scores_vals) / len(scores_vals), 4)

        # 最佳/最差
        summary.best_score = round(max(scores_vals), 4)
        summary.worst_score = round(min(scores_vals), 4)

        # 等級分布
        tier_dist = {"high": 0, "medium": 0, "low": 0}
        for qs in day_scores:
            tier_dist[qs.tier] = tier_dist.get(qs.tier, 0) + 1
        summary.tier_distribution = tier_dist

        # 領域分析
        domain_groups: Dict[str, List[float]] = {}
        for qs in day_scores:
            if qs.domain not in domain_groups:
                domain_groups[qs.domain] = []
            domain_groups[qs.domain].append(qs.score)

        summary.domain_breakdown = {
            domain: round(sum(vals) / len(vals), 4)
            for domain, vals in domain_groups.items()
        }

        # Skill 使用統計
        skill_count: Dict[str, int] = {}
        for qs in day_scores:
            for skill in qs.matched_skills:
                skill_count[skill] = skill_count.get(skill, 0) + 1
        summary.skill_usage = skill_count

        # 滿意度代理
        sat = self.compute_satisfaction_proxy(since=day_start)
        summary.satisfaction_proxy = sat.get("proxy_value", 0.0)

        # 當日警報
        all_alerts = self.store.load_alerts()
        day_alerts = [
            a for a in all_alerts
            if a.get("timestamp", "").startswith(date_str)
        ]
        summary.alerts = day_alerts

        # 持久化
        self.store.save_daily_summary(summary)

        logger.info(
            f"每日摘要生成 | date={date_str} | "
            f"interactions={summary.total_interactions} | "
            f"avg_q_score={summary.avg_q_score}"
        )

        return summary

    def generate_weekly_report(
        self,
        week_end: Optional[date] = None,
    ) -> WeeklyReport:
        """生成每週品質報告.

        彙總過去 7 天的品質數據、趨勢、盲點、技能使用變化。
        由每週日 Nightly Job 觸發。

        HG-EVAL-HONEST: 樣本不足時標記 insufficient_data。

        Args:
            week_end: 週結束日（預設今天）

        Returns:
            WeeklyReport 每週報告
        """
        if week_end is None:
            week_end = datetime.now().date()

        week_start = week_end - timedelta(days=6)

        report = WeeklyReport(
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
        )

        # 載入週內 Q-Score
        since = datetime.combine(week_start, datetime.min.time())
        week_scores = self.store.load_q_scores(since=since)

        report.total_interactions = len(week_scores)

        # HG-EVAL-HONEST: 樣本不足
        if len(week_scores) < MIN_SAMPLE_SIZE:
            report.insufficient_data = True

        if not week_scores:
            self.store.save_weekly_report(report)
            return report

        # 週平均 Q-Score
        report.avg_q_score = round(
            sum(qs.score for qs in week_scores) / len(week_scores), 4
        )

        # 趨勢
        trend = self.get_trend(days=7)
        report.trend_direction = trend.direction

        # 滿意度
        sat = self.compute_satisfaction_proxy(since=since)
        report.satisfaction_proxy = sat.get("proxy_value", 0.0)

        # 每日摘要
        for i in range(7):
            day = week_start + timedelta(days=i)
            day_summary = self.store.load_daily_summary(day.isoformat())
            if day_summary:
                report.daily_summaries.append(day_summary.to_dict())

        # 盲點掃描
        blindspot_list = self.scan_blindspots()
        report.blindspots = [b.to_dict() for b in blindspot_list]

        # 技能使用變化
        heatmap = self.get_skill_heatmap(days=7)
        report.skill_changes = {
            "total_skills_tracked": heatmap.get("total_skills_tracked", 0),
            "idle_skills": heatmap.get("idle_skills", []),
            "low_adoption_skills": heatmap.get("low_adoption_skills", []),
        }

        # 週內警報
        all_alerts = self.store.load_alerts()
        week_start_str = week_start.isoformat()
        week_end_str = week_end.isoformat()
        report.alerts = [
            a for a in all_alerts
            if week_start_str <= a.get("timestamp", "")[:10] <= week_end_str
        ]

        # 持久化
        self.store.save_weekly_report(report)

        logger.info(
            f"每週報告生成 | {report.week_start} ~ {report.week_end} | "
            f"interactions={report.total_interactions} | "
            f"avg_q_score={report.avg_q_score} | "
            f"trend={report.trend_direction}"
        )

        return report

    # ════════════════════════════════════════════
    # 背景靜默記錄（供 Brain.process 呼叫）
    # ════════════════════════════════════════════

    def silent_record(
        self,
        session_id: str,
        user_content: str,
        response_content: str,
        matched_skills: Optional[List[str]] = None,
        domain: str = "general",
        understanding: Optional[float] = None,
        depth: Optional[float] = None,
        clarity: Optional[float] = None,
        actionability: Optional[float] = None,
    ) -> QScore:
        """Brain.process() 完成後的靜默品質記錄.

        不干擾使用者體驗，在背景計算和儲存品質信號。

        Args:
            session_id: 對話 ID
            user_content: 使用者訊息（不會被儲存）
            response_content: 回覆內容（不會被儲存）
            matched_skills: 匹配到的技能
            domain: 所屬領域
            understanding: deep-think 理解度分數
            depth: deep-think 深度分數
            clarity: deep-think 清晰度分數
            actionability: deep-think 可行動性分數

        Returns:
            計算完成的 QScore
        """
        return self.evaluate(
            user_content=user_content,
            response_content=response_content,
            matched_skills=matched_skills,
            domain=domain,
            session_id=session_id,
            understanding=understanding,
            depth=depth,
            clarity=clarity,
            actionability=actionability,
        )


# ════════════════════════════════════════════
# 工具函式
# ════════════════════════════════════════════

def _safe_parse_ts(ts_str: str, fallback: datetime) -> datetime:
    """安全解析 ISO 時間戳.

    Args:
        ts_str: ISO 格式時間戳字串
        fallback: 解析失敗時的回退值

    Returns:
        解析後的 datetime
    """
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return fallback
