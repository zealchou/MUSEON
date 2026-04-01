"""AlgedonicAlert — 治理警報 Telegram 推播.

訂閱 GOVERNANCE_ALGEDONIC_SIGNAL，將最高等級的治理警報推播到 Telegram。
這是免疫系統的「疼痛神經」——系統在痛的時候，主人必須知道。

設計原則：
- 不依賴 LLM（LLM 掛了時更需要這個推播）
- 有防洪機制（同一類型的警報 30 分鐘內只推一次）
- Fire-and-forget，不阻塞 Governor 主流程
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

COOLDOWN = 1800  # 30 分鐘冷卻（秒）

TZ8_OFFSET = timezone(datetime.now().astimezone().utcoffset() or __import__("datetime").timedelta(hours=8))


class AlgedonicAlert:
    """治理警報 Telegram 推播訂閱者.

    訂閱 GOVERNANCE_ALGEDONIC_SIGNAL，有防洪機制，
    透過 PROACTIVE_MESSAGE 事件推播到 Telegram。
    """

    COOLDOWN = COOLDOWN
    _SILENT_START = 23  # 23:00
    _SILENT_END = 7     # 07:00

    def __init__(self, event_bus: Any) -> None:
        self._event_bus = event_bus
        self._recent_alerts: Dict[str, float] = {}  # alert_type → last_sent_timestamp

        if event_bus is not None:
            self._subscribe()

    def _is_in_silent_hours(self) -> bool:
        """夜間靜默時段（23:00-07:00），降級為 log only."""
        hour = datetime.now().hour
        if self._SILENT_START > self._SILENT_END:
            return hour >= self._SILENT_START or hour < self._SILENT_END
        return self._SILENT_START <= hour < self._SILENT_END

    def _subscribe(self) -> None:
        """訂閱 GOVERNANCE_ALGEDONIC_SIGNAL."""
        try:
            from museon.core.event_bus import GOVERNANCE_ALGEDONIC_SIGNAL
            self._event_bus.subscribe(GOVERNANCE_ALGEDONIC_SIGNAL, self._on_algedonic)
            logger.info("AlgedonicAlert: 已訂閱 GOVERNANCE_ALGEDONIC_SIGNAL")
        except Exception as e:
            logger.warning(f"AlgedonicAlert: 訂閱失敗 (degraded): {e}")

    def _on_algedonic(self, data: Optional[dict] = None) -> None:
        """GOVERNANCE_ALGEDONIC_SIGNAL 事件處理器.

        Args:
            data: 事件資料，包含 source、severity、description 等欄位
        """
        if data is None:
            data = {}

        # ── 1. 決定 alert_type（防洪 key）──
        alert_type = data.get("source", data.get("health_tier", "unknown"))
        if not isinstance(alert_type, str):
            alert_type = str(alert_type)

        # ── 2. 防洪檢查 ──
        now = time.time()
        last_sent = self._recent_alerts.get(alert_type, 0.0)
        if now - last_sent < self.COOLDOWN:
            remaining = int(self.COOLDOWN - (now - last_sent))
            logger.debug(
                f"AlgedonicAlert: [{alert_type}] 冷卻中，"
                f"剩餘 {remaining}s，略過推播"
            )
            return

        # ── 3. 更新防洪時間戳 ──
        self._recent_alerts[alert_type] = now

        # ── 4. 格式化告警訊息 ──
        message = self._format_alert(data, alert_type)

        # ── 4.5. 靜默時段檢查（23:00-07:00 降級為 log only）──
        description = data.get("summary", data.get("description", alert_type))
        if self._is_in_silent_hours():
            logger.warning(
                f"[AlgedonicAlert] 靜默時段，降級為 log: {description}"
            )
            return

        # ── 5. 透過 PROACTIVE_MESSAGE 推播（Fire-and-forget）──
        try:
            from museon.core.event_bus import PROACTIVE_MESSAGE
            self._event_bus.publish(
                PROACTIVE_MESSAGE,
                {
                    "message": message,
                    "source": "alert",
                    "timestamp": now,
                },
            )
            logger.warning(f"AlgedonicAlert: 治理警報已推播 [{alert_type}]")
        except Exception as e:
            logger.error(f"AlgedonicAlert: 推播失敗 (degraded): {e}")

    def _format_alert(self, data: dict, alert_type: str) -> str:
        """格式化告警訊息（純文字，不依賴 LLM）."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        severity = data.get("severity", data.get("overall", "CRITICAL")).upper()
        source = data.get("source", alert_type)
        summary = data.get("summary", data.get("description", ""))
        health_tier = data.get("health_tier", "")

        # 組裝描述
        if summary and isinstance(summary, dict):
            description = ", ".join(f"{k}={v}" for k, v in list(summary.items())[:3])
        elif summary:
            description = str(summary)[:200]
        elif health_tier:
            description = f"健康等級降至 {health_tier}"
        else:
            description = "系統偵測到嚴重異常"

        # 根據來源產生建議動作
        suggested_action = _suggest_action(source)

        return (
            f"🚨 治理警報\n\n"
            f"嚴重度：{severity}\n"
            f"來源：{source}\n"
            f"描述：{description}\n"
            f"時間：{now_str}\n\n"
            f"建議動作：{suggested_action}"
        )


def _suggest_action(source: str) -> str:
    """根據警報來源產生建議動作."""
    source_lower = source.lower()
    if "soul_identity" in source_lower or "tampered" in source_lower:
        return "立即檢查 SOUL.md 完整性，確認是否遭到篡改"
    if "system_audit" in source_lower or "audit" in source_lower:
        return "執行 python -m museon.doctor.system_audit 查看詳細診斷"
    if "health_tier" in source_lower or "critical" in source_lower:
        return "檢查 Governor 健康報告，確認系統服務狀態"
    if "gateway" in source_lower:
        return "重啟 Gateway daemon，確認端口 8765 可用"
    if "memory" in source_lower:
        return "檢查系統記憶體用量，必要時重啟 MUSEON"
    return "查看 ~/MUSEON/logs/ 取得詳細診斷資訊"
