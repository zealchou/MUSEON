"""
Finding — MuseOff 診斷卡資料模型

每個 Finding 記錄一個系統問題：爆炸原點、爆炸範圍、應急處理、處方建議。
支援去重（PagerDuty 模式）和 baseline 異常偵測（Datadog 模式）。
"""

from __future__ import annotations

import json
import logging
import statistics
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Finding 資料模型
# ---------------------------------------------------------------------------

@dataclass
class BlastOrigin:
    file: str
    line: int | None = None
    error_type: str = ""
    traceback: str = ""


@dataclass
class BlastTarget:
    module: str
    impact: str
    fan_in: int | str = 0


@dataclass
class TriageAction:
    action: str
    reversible: bool = True
    timestamp: str = ""


@dataclass
class Prescription:
    diagnosis: str
    root_cause: str = ""
    suggested_fix: str = ""
    runbook_id: str = ""
    fix_complexity: str = "GREEN"  # GREEN / YELLOW / RED / FORBIDDEN
    pre_check: str = ""
    post_check: str = ""
    rollback: str = ""


@dataclass
class Finding:
    finding_id: str = ""
    timestamp: str = ""
    probe_layer: str = ""          # L0-L6
    severity: str = "MEDIUM"       # CRITICAL / HIGH / MEDIUM / LOW
    title: str = ""
    source: str = "museoff"        # museoff / museqa

    blast_origin: BlastOrigin | dict = field(default_factory=dict)
    blast_radius: list[BlastTarget | dict] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    triage_done: TriageAction | dict | None = None
    known_fix: dict | None = None
    prescription: Prescription | dict | None = None

    status: str = "open"  # open / fixed_by_musedoc / needs_human / ...

    def __post_init__(self):
        if not self.finding_id:
            date = datetime.now(timezone.utc).strftime("%Y%m%d")
            short_id = uuid.uuid4().hex[:6]
            prefix = "MO" if self.source == "museoff" else "QA"
            self.finding_id = f"{prefix}-{date}-{short_id}"
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = {}
        for k, v in asdict(self).items():
            d[k] = v
        return d


# ---------------------------------------------------------------------------
# FindingStore — 讀寫 findings 目錄
# ---------------------------------------------------------------------------

class FindingStore:
    """管理 findings 目錄的讀寫"""

    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._recent_origins: dict[str, float] = {}  # 去重用：origin -> timestamp

    def save(self, finding: Finding) -> Path:
        """儲存 finding 到日期目錄"""
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_dir = self.base_dir / date
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{finding.finding_id}.json"
        path.write_text(
            json.dumps(finding.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 記錄 origin 用於去重
        origin_key = self._origin_key(finding)
        self._recent_origins[origin_key] = time.monotonic()
        return path

    def load_open(self) -> list[Finding]:
        """載入所有 status=open 的 findings"""
        findings = []
        for json_file in sorted(self.base_dir.rglob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if data.get("status") == "open":
                    findings.append(self._dict_to_finding(data))
            except (json.JSONDecodeError, OSError):
                continue
        return findings

    def load_all(self, days: int = 7) -> list[Finding]:
        """載入最近 N 天的所有 findings"""
        findings = []
        for json_file in sorted(self.base_dir.rglob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                findings.append(self._dict_to_finding(data))
            except (json.JSONDecodeError, OSError):
                continue
        return findings

    def update_status(self, finding_id: str, new_status: str) -> bool:
        """更新 finding 狀態"""
        for json_file in self.base_dir.rglob(f"{finding_id}.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                data["status"] = new_status
                json_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return True
            except (json.JSONDecodeError, OSError):
                continue
        return False

    def is_duplicate(self, finding: Finding, window_seconds: int = 3600) -> bool:
        """去重：同一 origin 在 window 內不重複建 finding"""
        origin_key = self._origin_key(finding)
        last_time = self._recent_origins.get(origin_key)
        if last_time and (time.monotonic() - last_time) < window_seconds:
            return True
        self._recent_origins[origin_key] = time.monotonic()
        return False

    def _origin_key(self, finding: Finding) -> str:
        if isinstance(finding.blast_origin, dict):
            return finding.blast_origin.get("file", "") + ":" + finding.blast_origin.get("error_type", "")
        return finding.blast_origin.file + ":" + finding.blast_origin.error_type

    def _dict_to_finding(self, data: dict) -> Finding:
        f = Finding()
        for k, v in data.items():
            if hasattr(f, k):
                setattr(f, k, v)
        return f


# ---------------------------------------------------------------------------
# BaselineTracker — Datadog 風格 baseline 異常偵測
# ---------------------------------------------------------------------------

class BaselineTracker:
    """追蹤正常值，偏離 3-sigma 才報警"""

    def __init__(self, window_size: int = 168):  # 7 天 × 24 小時
        self._metrics: dict[str, deque] = {}
        self._window = window_size

    def record(self, metric_name: str, value: float) -> None:
        """記錄一筆數值"""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = deque(maxlen=self._window)
        self._metrics[metric_name].append(value)

    def is_anomaly(self, metric_name: str, current_value: float, sigma: float = 3.0) -> bool:
        """判斷是否為異常值（偏離 N 個標準差）"""
        history = self._metrics.get(metric_name)
        if not history or len(history) < 24:  # 不到 1 天不判斷
            return False
        try:
            mean = statistics.mean(history)
            stdev = statistics.stdev(history)
            if stdev == 0:
                return current_value != mean
            return abs(current_value - mean) > sigma * stdev
        except statistics.StatisticsError:
            return False

    def get_stats(self, metric_name: str) -> dict:
        """取得某指標的統計資訊"""
        history = self._metrics.get(metric_name)
        if not history or len(history) < 2:
            return {"count": len(history) if history else 0}
        return {
            "count": len(history),
            "mean": round(statistics.mean(history), 2),
            "stdev": round(statistics.stdev(history), 2),
            "min": round(min(history), 2),
            "max": round(max(history), 2),
        }

    def to_dict(self) -> dict:
        return {k: list(v) for k, v in self._metrics.items()}

    def load_from_dict(self, data: dict) -> None:
        for k, v in data.items():
            self._metrics[k] = deque(v, maxlen=self._window)
