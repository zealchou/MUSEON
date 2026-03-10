"""MicroPulse — 微脈搏（30 分鐘），4 項零 LLM 健康檢查.

依據 THREE_LAYER_PULSE BDD Spec §3 實作。
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional

from museon.core.event_bus import PULSE_MICRO_BEAT, EventBus
from museon.pulse.heartbeat_focus import HeartbeatFocus

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════

MICRO_PULSE_INTERVAL = 1800  # 30 分鐘（秒）
MAX_FILE_COUNT_WARNING = 10000  # 記憶體檔案數警告閾值
ERROR_THRESHOLD_5MIN = 3  # 5 分鐘內錯誤閾值


class MicroPulse:
    """微脈搏 — 4 項零 LLM 健康檢查.

    | # | 名稱            | 判定                              |
    |---|-----------------|----------------------------------|
    | 1 | Beat Count      | 永遠 pass                         |
    | 2 | System Uptime   | 永遠 pass                         |
    | 3 | Memory File Count | >10,000 → warning               |
    | 4 | Recent Errors   | 5 分鐘內 ≥3 ERROR → warning       |
    """

    def __init__(
        self,
        heartbeat_focus: HeartbeatFocus,
        event_bus: EventBus,
        workspace: Optional[str] = None,
    ) -> None:
        self._heartbeat_focus = heartbeat_focus
        self._event_bus = event_bus
        self._beat_counter: int = 0
        self._start_time: float = time.time()
        self._workspace = Path(workspace) if workspace else None

    def run(self) -> Dict:
        """執行 4 項零 LLM 健康檢查 + 輔助更新."""
        self._beat_counter += 1
        self._heartbeat_focus.record_beat()

        checks_passed = 4
        status = "healthy"
        warnings = []

        # Check 1: Beat Count（永遠 pass）
        beat_count = self._beat_counter

        # Check 2: System Uptime（永遠 pass）
        uptime_hours = (time.time() - self._start_time) / 3600

        # Check 3: Memory File Count
        file_count = self._count_memory_files()
        if file_count > MAX_FILE_COUNT_WARNING:
            checks_passed -= 1
            warnings.append(
                f"memory_files={file_count} > {MAX_FILE_COUNT_WARNING}"
            )

        # Check 4: Recent Errors
        recent_errors = self._count_recent_errors()
        if recent_errors >= ERROR_THRESHOLD_5MIN:
            checks_passed -= 1
            warnings.append(
                f"recent_errors={recent_errors} >= {ERROR_THRESHOLD_5MIN}"
            )

        if checks_passed < 4:
            status = "warning"

        # 輔助更新：days_alive（確保無互動日也會更新）
        self._update_days_alive()

        result = {
            "beat_count": beat_count,
            "uptime_hours": round(uptime_hours, 2),
            "status": status,
            "checks_passed": checks_passed,
            "file_count": file_count,
            "recent_errors": recent_errors,
            "warnings": warnings,
        }

        # 發布事件
        self._event_bus.publish(PULSE_MICRO_BEAT, {
            "beat_count": beat_count,
            "uptime_hours": round(uptime_hours, 2),
            "status": status,
        })

        return result

    def _update_days_alive(self) -> None:
        """更新 ANIMA_MC.json 中的 days_alive（確保無互動日也能更新）."""
        if not self._workspace:
            return
        import json
        from datetime import datetime as _dt
        anima_path = self._workspace / "ANIMA_MC.json"
        if not anima_path.exists():
            return
        try:
            data = json.loads(anima_path.read_text(encoding="utf-8"))
            identity = data.get("identity", {})
            birth_str = identity.get("birth_date")
            if not birth_str:
                return
            birth = _dt.fromisoformat(birth_str)
            new_days = (_dt.now() - birth).days
            if new_days != identity.get("days_alive", 0):
                identity["days_alive"] = new_days
                data["identity"] = identity
                anima_path.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                logger.info(f"MicroPulse updated days_alive → {new_days}")
        except Exception as e:
            logger.debug(f"days_alive update failed: {e}")

    def _count_memory_files(self) -> int:
        """計算 memory/ 下檔案數."""
        if not self._workspace:
            return 0
        memory_dir = self._workspace / "memory"
        if not memory_dir.exists():
            return 0
        count = 0
        for root, _dirs, files in os.walk(memory_dir):
            count += len(files)
        return count

    def _count_recent_errors(self) -> int:
        """掃描最近 5 分鐘 log 中的 ERROR 數量."""
        if not self._workspace:
            return 0
        log_dir = self._workspace / "logs"
        if not log_dir.exists():
            return 0

        cutoff = time.time() - 300  # 5 分鐘
        error_count = 0

        # 掃描最新的 log 檔案
        log_files = sorted(log_dir.glob("*.log"), key=os.path.getmtime)
        for log_file in log_files[-3:]:  # 只看最新 3 個 log 檔案
            try:
                mtime = os.path.getmtime(log_file)
                if mtime < cutoff:
                    continue
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "ERROR" in line:
                            error_count += 1
            except Exception:
                pass

        return error_count

    @property
    def beat_count(self) -> int:
        return self._beat_counter


def register_micro_pulse(
    heartbeat_focus: HeartbeatFocus,
    event_bus: EventBus,
    workspace: Optional[str] = None,
) -> "MicroPulse":
    """建立 MicroPulse 實例並註冊到 HeartbeatEngine."""
    from museon.pulse.heartbeat_engine import get_heartbeat_engine

    pulse = MicroPulse(heartbeat_focus, event_bus, workspace)
    engine = get_heartbeat_engine()
    engine.register("micro_pulse", pulse.run, interval_seconds=MICRO_PULSE_INTERVAL)
    return pulse
