"""Planner — 行程提醒掃描器.

與 CronEngine 整合，定期掃描即將到來的行程並觸發提醒。

使用方式：
    planner = EventPlanner(registry_manager=rm)
    # 註冊到 CronEngine
    cron.add_job(planner.scan_and_remind, trigger='interval',
                 minutes=5, job_id='event_reminder_scan')
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventPlanner:
    """行程提醒掃描器."""

    def __init__(
        self,
        registry_manager,
        notify_callback: Optional[Callable] = None,
        scan_window_minutes: int = 60,
    ):
        """初始化.

        Args:
            registry_manager: RegistryManager 實例
            notify_callback: 提醒回呼函式 (event_dict) -> None
            scan_window_minutes: 掃描窗口（分鐘）
        """
        self._rm = registry_manager
        self._notify = notify_callback
        self._scan_window = scan_window_minutes

    async def scan_and_remind(self) -> List[Dict[str, Any]]:
        """掃描並觸發提醒.

        Returns:
            已觸發提醒的事件列表
        """
        reminded = []

        try:
            events = self._rm.get_upcoming_reminders(
                within_minutes=self._scan_window
            )

            for event in events:
                # 計算是否到提醒時間
                start_str = event.get("datetime_start", "")
                reminder_min = event.get("reminder_minutes", 30)

                try:
                    start_dt = datetime.fromisoformat(start_str)
                    remind_at = start_dt - timedelta(minutes=reminder_min)
                    now = datetime.utcnow()

                    if now >= remind_at:
                        # 觸發提醒
                        if self._notify:
                            try:
                                self._notify(event)
                            except Exception as e:
                                logger.error(
                                    f"Reminder callback failed: {e}"
                                )

                        # 標記已提醒
                        self._rm.mark_reminder_sent(event["id"])
                        reminded.append(event)
                        logger.info(
                            f"Reminder sent for event: {event['title']}"
                        )

                except (ValueError, TypeError) as e:
                    logger.warning(
                        f"Invalid datetime for event {event.get('id')}: {e}"
                    )

        except Exception as e:
            logger.error(f"scan_and_remind failed: {e}")

        return reminded

    def format_reminder_message(self, event: Dict[str, Any]) -> str:
        """格式化提醒訊息.

        Args:
            event: 事件資料

        Returns:
            格式化的提醒文字
        """
        title = event.get("title", "未命名事件")
        start = event.get("datetime_start", "")
        location = event.get("location", "")
        tz = event.get("timezone", "Asia/Taipei")

        parts = [f"⏰ 行程提醒：{title}"]

        if start:
            try:
                dt = datetime.fromisoformat(start)
                parts.append(f"📅 時間：{dt.strftime('%Y-%m-%d %H:%M')} ({tz})")
            except ValueError:
                parts.append(f"📅 時間：{start}")

        if location:
            parts.append(f"📍 地點：{location}")

        return "\n".join(parts)


# ═══════════════════════════════════════
# 時區工具
# ═══════════════════════════════════════

# 常見地名 → IANA 時區對照
LOCATION_TIMEZONE_MAP = {
    "東京": "Asia/Tokyo",
    "tokyo": "Asia/Tokyo",
    "大阪": "Asia/Tokyo",
    "首爾": "Asia/Seoul",
    "seoul": "Asia/Seoul",
    "北京": "Asia/Shanghai",
    "上海": "Asia/Shanghai",
    "香港": "Asia/Hong_Kong",
    "新加坡": "Asia/Singapore",
    "singapore": "Asia/Singapore",
    "紐約": "America/New_York",
    "new york": "America/New_York",
    "洛杉磯": "America/Los_Angeles",
    "los angeles": "America/Los_Angeles",
    "舊金山": "America/Los_Angeles",
    "倫敦": "Europe/London",
    "london": "Europe/London",
    "巴黎": "Europe/Paris",
    "paris": "Europe/Paris",
    "雪梨": "Australia/Sydney",
    "sydney": "Australia/Sydney",
    "台北": "Asia/Taipei",
    "taipei": "Asia/Taipei",
    "曼谷": "Asia/Bangkok",
    "bangkok": "Asia/Bangkok",
}


def infer_timezone(location: str) -> Optional[str]:
    """從地名推斷時區.

    Args:
        location: 地名

    Returns:
        IANA 時區名稱，若無法推斷回傳 None
    """
    loc_lower = location.lower().strip()
    for key, tz in LOCATION_TIMEZONE_MAP.items():
        if key in loc_lower:
            return tz
    return None
