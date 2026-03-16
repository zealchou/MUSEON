"""群組會話後主動追問模組（v2.0 Phase 3.4）.

監聽 GROUP_SESSION_END 事件，分析 ANIMA_USER L8 層行為差異，
根據信心度決定追問時機與方式：
  - confidence > 0.8 → 即時追問（30 分鐘內 DM）
  - confidence 0.5-0.8 → 延遲追問（隔天早上帶入）
  - confidence < 0.5 → 只記錄，不追問
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 群組結束後多久開始分析（秒）
ANALYSIS_DELAY_SECONDS: int = 60

# 即時追問延遲（秒）
INSTANT_FOLLOWUP_DELAY: int = 30 * 60  # 30 分鐘

# L8 觀察門檻
HIGH_CONFIDENCE_THRESHOLD: float = 0.8
MEDIUM_CONFIDENCE_THRESHOLD: float = 0.5


class GroupSessionProactive:
    """群組會話後主動追問引擎.

    職責：
    1. 監聽 GROUP_SESSION_END 事件
    2. 分析 L8 層行為差異
    3. 根據信心度排程追問（即時/延遲/靜默）
    """

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = Path(data_dir)
        self._anima_dir = self._data_dir / "anima"
        self._pending_followups: List[Dict[str, Any]] = []

        logger.info("GroupSessionProactive initialized")

    def on_group_session_end(
        self,
        group_id: str,
        session_duration_seconds: int = 0,
        message_count: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """處理群組會話結束事件.

        分析 L8 層數據，決定是否需要追問。

        Args:
            group_id: 群組 ID
            session_duration_seconds: 會話持續時間（秒）
            message_count: 會話訊息數

        Returns:
            追問計畫（含問題、延遲、信心度）或 None
        """
        # 載入 ANIMA_USER
        anima_path = self._anima_dir / "anima_user.json"
        if not anima_path.exists():
            logger.debug("GroupSessionProactive: no anima_user.json")
            return None

        try:
            anima_user = json.loads(anima_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"GroupSessionProactive: load anima_user failed: {e}")
            return None

        l8 = anima_user.get("L8_context_behavior_notes", {})
        if not l8:
            return None

        # 分析最近的群組觀察
        observations = l8.get("observations", [])
        group_obs = [
            o for o in observations
            if o.get("group_id") == str(group_id)
        ]

        if len(group_obs) < 2:
            logger.debug(
                f"GroupSessionProactive: insufficient observations "
                f"for group {group_id} ({len(group_obs)})"
            )
            return None

        # 計算行為偏差
        analysis = self._analyze_behavioral_shift(group_obs, l8)

        if not analysis:
            return None

        confidence = analysis.get("confidence", 0.0)

        # 根據信心度決定追問策略
        if confidence >= HIGH_CONFIDENCE_THRESHOLD:
            # 即時追問（30 分鐘後 DM）
            followup = {
                "type": "instant",
                "delay_seconds": INSTANT_FOLLOWUP_DELAY,
                "group_id": group_id,
                "analysis": analysis,
                "question": self._generate_followup_question(analysis),
                "created_at": datetime.now().isoformat(),
            }
            self._pending_followups.append(followup)
            logger.info(
                f"GroupSessionProactive: instant followup scheduled | "
                f"group={group_id} confidence={confidence:.2f}"
            )
            return followup

        elif confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
            # 延遲追問（隔天早上）
            followup = {
                "type": "delayed",
                "delay_seconds": None,  # 由 heartbeat 在早上排程
                "group_id": group_id,
                "analysis": analysis,
                "question": self._generate_followup_question(analysis),
                "created_at": datetime.now().isoformat(),
            }
            self._pending_followups.append(followup)
            logger.info(
                f"GroupSessionProactive: delayed followup queued | "
                f"group={group_id} confidence={confidence:.2f}"
            )
            return followup

        else:
            # 靜默記錄
            logger.debug(
                f"GroupSessionProactive: low confidence, record only | "
                f"group={group_id} confidence={confidence:.2f}"
            )
            return None

    def get_pending_followups(self) -> List[Dict[str, Any]]:
        """取得待執行的追問列表."""
        return list(self._pending_followups)

    def pop_due_followups(self) -> List[Dict[str, Any]]:
        """取出已到期的即時追問（消費後移除）."""
        now = datetime.now()
        due = []
        remaining = []
        for f in self._pending_followups:
            if f.get("type") == "instant" and f.get("delay_seconds"):
                created = datetime.fromisoformat(f["created_at"])
                elapsed = (now - created).total_seconds()
                if elapsed >= f["delay_seconds"]:
                    due.append(f)
                    continue
            remaining.append(f)
        self._pending_followups = remaining
        return due

    def _analyze_behavioral_shift(
        self,
        group_obs: List[Dict[str, Any]],
        l8: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """分析群組行為偏差.

        比較群組中的行為指標 vs DM 基線。

        Returns:
            分析結果字典或 None
        """
        if not group_obs:
            return None

        # 群組平均值
        avg_formality = sum(
            o.get("formality_shift", 0.5) for o in group_obs
        ) / len(group_obs)
        avg_initiative = sum(
            o.get("initiative_ratio", 0.5) for o in group_obs
        ) / len(group_obs)

        # DM 基線（如果有）
        dm_formality = l8.get("formality_baseline_dm") or 0.5

        # 計算偏差
        formality_delta = abs(avg_formality - dm_formality)
        initiative_delta = abs(avg_initiative - 0.5)

        # 綜合信心度
        confidence = max(formality_delta, initiative_delta)

        # 主題分佈偏差
        topics = [o.get("topic", "general") for o in group_obs]
        topic_counts: Dict[str, int] = {}
        for t in topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1
        dominant_topic = max(topic_counts, key=lambda t: topic_counts[t])
        topic_concentration = topic_counts[dominant_topic] / len(topics)

        # 如果主題高度集中，提升信心度
        if topic_concentration > 0.7:
            confidence = min(1.0, confidence + 0.1)

        return {
            "avg_formality": round(avg_formality, 3),
            "avg_initiative": round(avg_initiative, 3),
            "dm_formality_baseline": dm_formality,
            "formality_delta": round(formality_delta, 3),
            "initiative_delta": round(initiative_delta, 3),
            "dominant_topic": dominant_topic,
            "topic_concentration": round(topic_concentration, 3),
            "observation_count": len(group_obs),
            "confidence": round(confidence, 3),
        }

    def _generate_followup_question(
        self, analysis: Dict[str, Any]
    ) -> str:
        """根據行為分析生成追問問題.

        使用模板生成好奇心驅動的問題。

        Args:
            analysis: 行為分析結果

        Returns:
            追問問題文字
        """
        formality_delta = analysis.get("formality_delta", 0)
        initiative_delta = analysis.get("initiative_delta", 0)
        dominant_topic = analysis.get("dominant_topic", "general")

        # 根據最大偏差維度生成問題
        if formality_delta > initiative_delta:
            avg_f = analysis.get("avg_formality", 0.5)
            if avg_f > 0.6:
                return (
                    "剛才在群組裡聊得挺正式的，"
                    "是因為群組裡有比較不熟的人嗎？"
                    "還是那個話題本身需要比較嚴肅地討論？"
                )
            else:
                return (
                    "在群組裡聊得很放鬆呢，"
                    "看起來那個群組的氛圍挺好的？"
                )
        else:
            avg_i = analysis.get("avg_initiative", 0.5)
            if avg_i > 0.6:
                return (
                    f"剛才在群組裡聊 {dominant_topic} 相關的話題"
                    "挺主動的，這個話題對你來說是不是特別有想法？"
                )
            else:
                return (
                    "我注意到你在群組裡比較安靜，"
                    "是在思考什麼嗎？還是那個話題不太感興趣？"
                )
