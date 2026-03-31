"""Feedback Loop — 使用者隱性訊號收集器.

被動收集互動品質訊號，驅動自我迭代：
- 記錄每次互動的隱性指標（回應長度、追問次數、表情符號等）
- 計算品質分數（0-1）
- 偵測品質趨勢顯著變化時發布 USER_FEEDBACK_SIGNAL 事件
- 每日彙整統計

設計原則：
- 被動收集，不主動向使用者索取反饋
- 隱性訊號推斷互動品質（非直接評分）
- 趨勢偵測使用滑動窗口 + 標準差
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# 品質趨勢偵測閾值
_TREND_WINDOW = 20  # 滑動窗口大小
_TREND_THRESHOLD = 0.15  # 品質分數均值變化閾值


class FeedbackLoop:
    """使用者隱性反饋迴路.

    被動收集互動信號，推斷回應品質趨勢，
    在趨勢顯著變化時透過 EventBus 通知演化引擎。

    信號來源：
    - response_length: 使用者回應長度（越長表示越投入）
    - follow_up_count: 追問次數（可能是困惑或深入探索）
    - emoji_count: 表情符號數量（正向情感信號）
    - response_time_ms: 回應時間（越快表示越急迫/越投入）
    """

    def __init__(
        self,
        workspace: Optional[str] = None,
        event_bus: Any = None,
    ) -> None:
        """
        Args:
            workspace: 工作區路徑（可選，用於持久化）
            event_bus: EventBus 實例（可選）
        """
        self._event_bus = event_bus
        self._workspace = workspace

        self._signals: List[Dict] = []
        self._daily_stats: Dict[str, Any] = {}
        self._quality_history: List[float] = []
        self._last_trend_mean: Optional[float] = None
        self._interaction_count: int = 0

        # 訂閱事件
        if self._event_bus is not None:
            self._subscribe()

    def _subscribe(self) -> None:
        """訂閱 EventBus 事件以被動收集信號."""
        try:
            from museon.core.event_bus import CHANNEL_MESSAGE_RECEIVED
            self._event_bus.subscribe(
                CHANNEL_MESSAGE_RECEIVED, self._on_message
            )
            logger.info("FeedbackLoop subscribed to CHANNEL_MESSAGE_RECEIVED")
        except Exception as e:
            logger.error(f"FeedbackLoop subscribe failed: {e}")

    def _on_message(self, data: Optional[Dict] = None) -> None:
        """從訊息事件中提取隱性信號.

        Args:
            data: CHANNEL_MESSAGE_RECEIVED 事件資料
        """
        if not data:
            return

        content_length = data.get("content_length", 0)
        content = data.get("content", "")

        # Phase 5: 從 event data 正確提取四維品質信號
        follow_up = data.get("follow_up_count", 0)
        emoji_count = 0
        if content:
            import re
            emoji_count = len(re.findall(
                r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
                r'\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF'
                r'\U00002702-\U000027B0\U0001FA00-\U0001FA6F]',
                content,
            ))
        response_time = data.get("response_time_ms", 0)

        self.record_interaction(
            response_length=content_length,
            follow_up_count=follow_up,
            emoji_count=emoji_count,
            response_time_ms=response_time,
        )

    def record_interaction(
        self,
        response_length: int,
        follow_up_count: int,
        emoji_count: int,
        response_time_ms: int,
    ) -> None:
        """記錄一次互動的隱性信號.

        Args:
            response_length: 使用者回應字元數
            follow_up_count: 追問次數
            emoji_count: 表情符號數量
            response_time_ms: MUSEON 回應時間（毫秒）
        """
        now = datetime.now(TZ8)
        self._interaction_count += 1

        interaction = {
            "timestamp": now.isoformat(),
            "response_length": response_length,
            "follow_up_count": follow_up_count,
            "emoji_count": emoji_count,
            "response_time_ms": response_time_ms,
        }

        # 計算品質分數
        quality = self._calculate_quality_signal(interaction)
        interaction["quality_score"] = quality

        self._signals.append(interaction)
        self._quality_history.append(quality)

        # 限制記憶（保留最近 500 筆）
        if len(self._signals) > 500:
            self._signals = self._signals[-500:]
        if len(self._quality_history) > 500:
            self._quality_history = self._quality_history[-500:]

        # 更新每日統計
        today = now.strftime("%Y-%m-%d")
        if today not in self._daily_stats:
            self._daily_stats[today] = {
                "count": 0,
                "total_quality": 0.0,
                "max_quality": 0.0,
                "min_quality": 1.0,
                "total_response_length": 0,
                "total_follow_ups": 0,
                "total_emojis": 0,
            }

        stats = self._daily_stats[today]
        stats["count"] += 1
        stats["total_quality"] += quality
        stats["max_quality"] = max(stats["max_quality"], quality)
        stats["min_quality"] = min(stats["min_quality"], quality)
        stats["total_response_length"] += response_length
        stats["total_follow_ups"] += follow_up_count
        stats["total_emojis"] += emoji_count

        # 清理過舊的每日統計（保留 30 天）
        cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        self._daily_stats = {
            k: v for k, v in self._daily_stats.items() if k >= cutoff
        }

        # 趨勢偵測
        self._check_trend_change()

        # 持久化摘要供 Nightly 讀取
        self._persist_summary()

    def _calculate_quality_signal(self, interaction: Dict) -> float:
        """計算單次互動的品質分數（0-1）.

        綜合考量多個隱性指標：
        - response_length: 較長回應表示更投入（但有上限）
        - follow_up_count: 適度追問是正面的（深入探索），過多可能表示困惑
        - emoji_count: 表情符號是正向情感信號
        - response_time_ms: 較快回應時間表示系統效能良好

        Args:
            interaction: 互動資料字典

        Returns:
            品質分數 0.0 ~ 1.0
        """
        scores: List[float] = []

        # 1. 回應長度分數 (0-1)
        # 20~200 字元是理想範圍，過短或超長都會衰減
        length = interaction.get("response_length", 0)
        if length <= 0:
            length_score = 0.2  # 空回應給予基準分
        elif length < 10:
            length_score = 0.3
        elif length < 50:
            length_score = 0.5 + (length - 10) / 80  # 10→0.5, 50→1.0
        elif length <= 300:
            length_score = 1.0  # 甜蜜區
        else:
            # 超過 300 開始衰減（可能是貼代碼）
            length_score = max(0.5, 1.0 - (length - 300) / 2000)
        scores.append(length_score)

        # 2. 追問次數分數 (0-1)
        # 0-1 次追問最佳，2-3 次尚可，4+ 次可能困惑
        follow_ups = interaction.get("follow_up_count", 0)
        if follow_ups <= 1:
            followup_score = 0.9
        elif follow_ups <= 3:
            followup_score = 0.7
        else:
            followup_score = max(0.3, 0.7 - (follow_ups - 3) * 0.1)
        scores.append(followup_score)

        # 3. 表情符號分數 (0-1)
        # 有表情是正面信號
        emojis = interaction.get("emoji_count", 0)
        if emojis == 0:
            emoji_score = 0.5  # 中性
        elif emojis <= 3:
            emoji_score = 0.8
        else:
            emoji_score = 0.9  # 很多表情 = 很投入
        scores.append(emoji_score)

        # 4. 回應時間分數 (0-1)
        # < 2s 優秀, 2-5s 良好, 5-15s 普通, 15s+ 較差
        resp_ms = interaction.get("response_time_ms", 0)
        if resp_ms <= 0:
            time_score = 0.5  # 無資料時給中性分
        elif resp_ms < 2000:
            time_score = 1.0
        elif resp_ms < 5000:
            time_score = 0.8
        elif resp_ms < 15000:
            time_score = 0.6
        else:
            time_score = max(0.2, 0.6 - (resp_ms - 15000) / 60000)
        scores.append(time_score)

        # 加權平均
        weights = [0.35, 0.25, 0.15, 0.25]
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        total_weight = sum(weights)

        return round(min(1.0, max(0.0, weighted_sum / total_weight)), 4)

    def _check_trend_change(self) -> None:
        """偵測品質趨勢是否有顯著變化.

        使用滑動窗口比較近期均值與前期均值，
        當差異超過閾值時發布 USER_FEEDBACK_SIGNAL。
        """
        if len(self._quality_history) < _TREND_WINDOW * 2:
            return  # 資料不足

        recent = self._quality_history[-_TREND_WINDOW:]
        previous = self._quality_history[-_TREND_WINDOW * 2:-_TREND_WINDOW]

        recent_mean = sum(recent) / len(recent)
        previous_mean = sum(previous) / len(previous)

        delta = recent_mean - previous_mean

        if abs(delta) < _TREND_THRESHOLD:
            return  # 變化不顯著

        # 計算標準差
        variance = sum((x - recent_mean) ** 2 for x in recent) / len(recent)
        std_dev = math.sqrt(variance) if variance > 0 else 0.01

        # 只在變化超過 1 個標準差時報告
        if abs(delta) < std_dev:
            return

        direction = "improving" if delta > 0 else "declining"
        signal_data = {
            "direction": direction,
            "delta": round(delta, 4),
            "recent_mean": round(recent_mean, 4),
            "previous_mean": round(previous_mean, 4),
            "std_dev": round(std_dev, 4),
            "sample_size": _TREND_WINDOW,
            "total_interactions": self._interaction_count,
            "timestamp": datetime.now(TZ8).isoformat(),
        }

        logger.info(
            f"Quality trend {direction}: "
            f"{previous_mean:.3f} -> {recent_mean:.3f} "
            f"(delta={delta:+.3f})"
        )

        # 發布事件
        try:
            if self._event_bus is not None:
                from museon.core.event_bus import USER_FEEDBACK_SIGNAL
                self._event_bus.publish(USER_FEEDBACK_SIGNAL, signal_data)
        except Exception as e:
            logger.error(f"EventBus publish USER_FEEDBACK_SIGNAL failed: {e}")

        # 品質持續下降 → 可能有學習空缺
        if delta < 0:
            try:
                from museon.nightly.triage_step import write_signal
                from museon.core.awareness import (
                    AwarenessSignal,
                    Severity,
                    SignalType,
                    Actionability,
                )
                if hasattr(self, '_workspace') and self._workspace:
                    write_signal(self._workspace, AwarenessSignal(
                        source="feedback_loop",
                        severity=Severity.MEDIUM,
                        signal_type=SignalType.LEARNING_GAP,
                        title=f"品質趨勢下降，可能存在學習空缺",
                        actionability=Actionability.AUTO,
                        suggested_action="trigger_insight_extraction",
                    ))
            except Exception:
                pass

        self._last_trend_mean = recent_mean

    def get_daily_summary(self) -> Dict[str, Any]:
        """取得每日彙整統計.

        Returns:
            包含各日統計的字典
        """
        today = datetime.now(TZ8).strftime("%Y-%m-%d")
        today_stats = self._daily_stats.get(today)

        summary: Dict[str, Any] = {
            "date": today,
            "total_interactions": self._interaction_count,
            "days_tracked": len(self._daily_stats),
        }

        if today_stats and today_stats["count"] > 0:
            count = today_stats["count"]
            summary["today"] = {
                "interactions": count,
                "avg_quality": round(
                    today_stats["total_quality"] / count, 4
                ),
                "max_quality": today_stats["max_quality"],
                "min_quality": today_stats["min_quality"],
                "avg_response_length": round(
                    today_stats["total_response_length"] / count, 1
                ),
                "total_follow_ups": today_stats["total_follow_ups"],
                "total_emojis": today_stats["total_emojis"],
            }
        else:
            summary["today"] = {"interactions": 0}

        # 近 7 天趨勢
        if len(self._quality_history) >= _TREND_WINDOW:
            recent = self._quality_history[-_TREND_WINDOW:]
            summary["recent_trend"] = {
                "mean": round(sum(recent) / len(recent), 4),
                "window_size": len(recent),
            }

        return summary

    def _persist_summary(self) -> None:
        """持久化每日摘要到檔案，供 Nightly Pipeline 讀取."""
        if not self._workspace:
            return
        try:
            import json
            from pathlib import Path

            out_dir = Path(self._workspace) / "_system" / "feedback_loop"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / "daily_summary.json"

            today = datetime.now(TZ8).strftime("%Y-%m-%d")
            today_stats = self._daily_stats.get(today, {})
            count = today_stats.get("count", 0)

            # 計算趨勢方向
            trend = "stable"
            if len(self._quality_history) >= _TREND_WINDOW * 2:
                recent = self._quality_history[-_TREND_WINDOW:]
                previous = self._quality_history[-_TREND_WINDOW * 2:-_TREND_WINDOW]
                delta = (sum(recent) / len(recent)) - (sum(previous) / len(previous))
                if delta > _TREND_THRESHOLD:
                    trend = "improving"
                elif delta < -_TREND_THRESHOLD:
                    trend = "declining"

            summary = {
                "date": today,
                "interaction_count": count,
                "avg_quality": round(today_stats.get("total_quality", 0) / count, 4) if count > 0 else 0.5,
                "trend_direction": trend,
                "total_interactions_lifetime": self._interaction_count,
                "persisted_at": datetime.now(TZ8).isoformat(),
            }

            # 原子寫入
            tmp = out_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(summary, fh, ensure_ascii=False, indent=2)
            tmp.rename(out_file)
        except Exception as e:
            logger.debug(f"FeedbackLoop persist failed: {e}")

    # ── Status ──

    def get_status(self) -> Dict[str, Any]:
        """取得反饋迴路狀態."""
        return {
            "total_interactions": self._interaction_count,
            "signals_buffered": len(self._signals),
            "quality_history_size": len(self._quality_history),
            "days_tracked": len(self._daily_stats),
            "has_event_bus": self._event_bus is not None,
            "last_trend_mean": self._last_trend_mean,
        }
