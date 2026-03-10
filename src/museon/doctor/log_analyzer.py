"""LogAnalyzer — 日誌異常分析引擎.

純 CPU 零 Token，分析 logs/ 目錄下的日誌檔案，
偵測錯誤頻率突增、重複錯誤模式、HeartbeatEngine 狀態異常。
"""

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# LogAnomaly 資料結構
# ═══════════════════════════════════════════


@dataclass
class LogAnomaly:
    """日誌異常."""

    anomaly_type: str  # "error_spike" | "repeated_error" | "heartbeat_stale" | "heartbeat_error"
    severity: str  # "critical" | "warning" | "info"
    message: str
    details: Dict = field(default_factory=dict)
    source_file: str = ""
    first_seen: str = ""
    last_seen: str = ""
    count: int = 0


# ═══════════════════════════════════════════
# 日誌行解析
# ═══════════════════════════════════════════

# 標準日誌格式: 2026-03-09 22:30:00,123 - museon.xxx - ERROR - message
_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})[,.]?\d*\s*-\s*"
    r"([\w.]+)\s*-\s*(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s*-\s*(.+)$"
)

# 錯誤行的特徵模式（用於歸類重複錯誤）
_ERROR_FINGERPRINT_PATTERNS = [
    # 移除變動的數值（時間戳、ID、PID 等）
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"), "<TIMESTAMP>"),
    (re.compile(r"\b\d{5,}\b"), "<NUM>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "<HEX>"),
    (re.compile(r"pid[= ]\d+", re.IGNORECASE), "pid=<PID>"),
]


@dataclass
class _LogEntry:
    timestamp: str
    module: str
    level: str
    message: str

    @classmethod
    def parse(cls, line: str) -> Optional["_LogEntry"]:
        m = _LOG_PATTERN.match(line.strip())
        if not m:
            return None
        return cls(
            timestamp=m.group(1),
            module=m.group(2),
            level=m.group(3),
            message=m.group(4),
        )


def _fingerprint(message: str) -> str:
    """產生錯誤訊息的指紋（歸類用）."""
    fp = message
    for pattern, replacement in _ERROR_FINGERPRINT_PATTERNS:
        fp = pattern.sub(replacement, fp)
    return fp[:200]  # 截斷避免過長


# ═══════════════════════════════════════════
# LogAnalyzer
# ═══════════════════════════════════════════


class LogAnalyzer:
    """日誌異常分析引擎.

    分析：
    1. 錯誤頻率突增（滑動窗口比較）
    2. 重複錯誤模式識別
    3. HeartbeatEngine 狀態異常偵測
    """

    def __init__(
        self,
        logs_dir: Optional[Path] = None,
        heartbeat_state_path: Optional[Path] = None,
    ):
        self._logs_dir = logs_dir or Path("logs")
        self._heartbeat_path = heartbeat_state_path or Path(
            "data/pulse/heartbeat_engine.json"
        )

    def analyze(
        self, lookback_hours: int = 24
    ) -> List[LogAnomaly]:
        """執行完整日誌分析."""
        anomalies: List[LogAnomaly] = []

        # 1. 分析日誌檔案
        log_anomalies = self._analyze_log_files(lookback_hours)
        anomalies.extend(log_anomalies)

        # 2. 分析 HeartbeatEngine 狀態
        hb_anomalies = self._analyze_heartbeat_state()
        anomalies.extend(hb_anomalies)

        logger.info(
            f"LogAnalyzer: 分析完成 — {len(anomalies)} 個異常"
        )
        return anomalies

    def _analyze_log_files(
        self, lookback_hours: int
    ) -> List[LogAnomaly]:
        """分析 logs/ 下的日誌檔案."""
        anomalies: List[LogAnomaly] = []

        if not self._logs_dir.exists():
            logger.warning(f"LogAnalyzer: logs 目錄不存在: {self._logs_dir}")
            return anomalies

        log_files = sorted(self._logs_dir.glob("*.log"))
        if not log_files:
            return anomalies

        # 收集所有錯誤條目
        error_entries: List[_LogEntry] = []
        cutoff = datetime.now() - timedelta(hours=lookback_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        for log_file in log_files:
            try:
                text = log_file.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    entry = _LogEntry.parse(line)
                    if not entry:
                        continue
                    if entry.timestamp < cutoff_str:
                        continue
                    if entry.level in ("ERROR", "CRITICAL"):
                        error_entries.append(entry)
            except Exception as e:
                logger.warning(f"LogAnalyzer: 無法讀取 {log_file}: {e}")

        if not error_entries:
            return anomalies

        # 偵測 1: 重複錯誤模式
        fp_counter: Counter = Counter()
        fp_examples: Dict[str, _LogEntry] = {}
        for entry in error_entries:
            fp = _fingerprint(entry.message)
            fp_counter[fp] += 1
            if fp not in fp_examples:
                fp_examples[fp] = entry

        for fp, count in fp_counter.most_common(10):
            if count >= 3:
                example = fp_examples[fp]
                anomalies.append(LogAnomaly(
                    anomaly_type="repeated_error",
                    severity="warning" if count < 10 else "critical",
                    message=f"重複錯誤出現 {count} 次: {example.message[:100]}",
                    details={"fingerprint": fp, "count": count, "module": example.module},
                    source_file=example.module,
                    count=count,
                ))

        # 偵測 2: 錯誤頻率突增
        # 分成兩個時間段比較
        if lookback_hours >= 2:
            mid_point = (datetime.now() - timedelta(hours=lookback_hours / 2)).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            old_count = sum(1 for e in error_entries if e.timestamp < mid_point)
            new_count = sum(1 for e in error_entries if e.timestamp >= mid_point)

            if old_count > 0 and new_count > old_count * 3:
                anomalies.append(LogAnomaly(
                    anomaly_type="error_spike",
                    severity="critical",
                    message=(
                        f"錯誤頻率突增: 前半段 {old_count} 次 → "
                        f"後半段 {new_count} 次（{new_count / old_count:.1f}x）"
                    ),
                    details={
                        "old_count": old_count,
                        "new_count": new_count,
                        "ratio": new_count / old_count,
                    },
                ))
            elif old_count == 0 and new_count >= 5:
                anomalies.append(LogAnomaly(
                    anomaly_type="error_spike",
                    severity="warning",
                    message=f"新出現的錯誤集群: 近期 {new_count} 次錯誤",
                    details={"new_count": new_count},
                ))

        return anomalies

    def _analyze_heartbeat_state(self) -> List[LogAnomaly]:
        """分析 HeartbeatEngine 狀態."""
        anomalies: List[LogAnomaly] = []

        if not self._heartbeat_path.exists():
            return anomalies

        try:
            state = json.loads(
                self._heartbeat_path.read_text(encoding="utf-8")
            )
        except Exception as e:
            logger.warning(
                f"LogAnalyzer: 無法讀取 heartbeat 狀態: {e}"
            )
            return anomalies

        import time

        now = time.time()

        for task_id, task_state in state.items():
            last_run = task_state.get("last_run", 0)
            run_count = task_state.get("run_count", 0)
            last_error = task_state.get("last_error")

            # 偵測 1: 持續性錯誤
            if last_error:
                anomalies.append(LogAnomaly(
                    anomaly_type="heartbeat_error",
                    severity="critical",
                    message=(
                        f"HeartbeatTask '{task_id}' 最後執行有錯誤: "
                        f"{last_error}"
                    ),
                    details={
                        "task_id": task_id,
                        "last_error": last_error,
                        "run_count": run_count,
                    },
                    source_file="heartbeat_engine",
                ))

            # 偵測 2: 任務停滯（超過預期間隔的 3 倍未執行）
            if last_run > 0:
                stale_seconds = now - last_run
                # 假設正常間隔不超過 2 小時，超過 6 小時算停滯
                if stale_seconds > 21600:
                    hours = stale_seconds / 3600
                    anomalies.append(LogAnomaly(
                        anomaly_type="heartbeat_stale",
                        severity="warning",
                        message=(
                            f"HeartbeatTask '{task_id}' 已 {hours:.1f} 小時"
                            f"未執行（run_count={run_count}）"
                        ),
                        details={
                            "task_id": task_id,
                            "last_run": last_run,
                            "stale_hours": hours,
                            "run_count": run_count,
                        },
                        source_file="heartbeat_engine",
                    ))

        return anomalies

    @staticmethod
    def format_report(anomalies: List[LogAnomaly]) -> str:
        """格式化異常報告."""
        if not anomalies:
            return "LogAnalyzer: 未發現日誌異常 ✓"

        lines = [f"LogAnalyzer 報告 — 共 {len(anomalies)} 個異常\n"]
        lines.append("=" * 60)

        for anomaly in anomalies:
            sev_label = {
                "critical": "🔴", "warning": "🟡", "info": "ℹ️"
            }.get(anomaly.severity, "")
            lines.append(
                f"\n{sev_label} [{anomaly.anomaly_type}] "
                f"{anomaly.message}"
            )
            if anomaly.source_file:
                lines.append(f"    來源: {anomaly.source_file}")
            lines.append("")

        return "\n".join(lines)
