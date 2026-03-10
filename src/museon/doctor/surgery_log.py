"""SurgeryLog — 手術記錄持久化.

將手術的完整生命週期（觸發 → 診斷 → 提案 → 審查 → 執行 → 結果）
持久化到 data/doctor/surgery_log.json。
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SurgeryRecord:
    """單次手術記錄."""

    id: str  # surgery-YYYYMMDD-NNN
    trigger: str  # 觸發來源描述
    diagnosis: str  # 診斷層級（D1/D2/D3）
    affected_files: List[str] = field(default_factory=list)
    diff_summary: str = ""
    safety_review: Dict[str, Any] = field(default_factory=dict)
    git_tag: str = ""
    result: str = "pending"  # "pending" | "applied" | "success" | "rollback" | "failed"
    error: Optional[str] = None
    timestamp: str = ""
    completed_at: str = ""
    duration_seconds: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class SurgeryLog:
    """手術記錄管理器.

    持久化到 data/doctor/surgery_log.json，
    支援新增、更新、查詢、統計。
    """

    MAX_RECORDS = 200  # 最多保留 200 筆

    def __init__(self, data_dir: Optional[Path] = None):
        self._data_dir = data_dir or Path("data/doctor")
        self._log_path = self._data_dir / "surgery_log.json"
        self._records: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        """載入記錄."""
        if not self._log_path.exists():
            self._records = []
            return
        try:
            data = json.loads(
                self._log_path.read_text(encoding="utf-8")
            )
            self._records = data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"SurgeryLog: 載入失敗: {e}")
            self._records = []

    def _save(self) -> None:
        """儲存記錄（原子寫入）."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            # 保留最近 MAX_RECORDS 筆
            if len(self._records) > self.MAX_RECORDS:
                self._records = self._records[-self.MAX_RECORDS:]

            tmp = self._log_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.rename(self._log_path)
        except Exception as e:
            logger.error(f"SurgeryLog: 儲存失敗: {e}")

    def generate_id(self) -> str:
        """產生手術 ID."""
        today = datetime.now().strftime("%Y%m%d")
        # 計算今天的序號
        today_count = sum(
            1 for r in self._records
            if r.get("id", "").startswith(f"surgery-{today}")
        )
        return f"surgery-{today}-{today_count + 1:03d}"

    def create(self, record: SurgeryRecord) -> str:
        """建立手術記錄，回傳 ID."""
        if not record.id:
            record.id = self.generate_id()
        self._records.append(asdict(record))
        self._save()
        logger.info(f"SurgeryLog: 建立記錄 {record.id}")
        return record.id

    def update(self, surgery_id: str, **kwargs: Any) -> bool:
        """更新手術記錄."""
        for rec in self._records:
            if rec.get("id") == surgery_id:
                rec.update(kwargs)
                if "result" in kwargs and kwargs["result"] in ("success", "rollback", "failed"):
                    rec["completed_at"] = datetime.now().isoformat()
                    if rec.get("timestamp"):
                        try:
                            start = datetime.fromisoformat(rec["timestamp"])
                            rec["duration_seconds"] = (
                                datetime.now() - start
                            ).total_seconds()
                        except Exception:
                            pass
                self._save()
                logger.info(
                    f"SurgeryLog: 更新 {surgery_id} → {kwargs}"
                )
                return True
        logger.warning(f"SurgeryLog: 找不到記錄 {surgery_id}")
        return False

    def get(self, surgery_id: str) -> Optional[Dict[str, Any]]:
        """查詢單筆記錄."""
        for rec in reversed(self._records):
            if rec.get("id") == surgery_id:
                return rec
        return None

    def recent(self, count: int = 10) -> List[Dict[str, Any]]:
        """取最近 N 筆記錄."""
        return list(reversed(self._records[-count:]))

    def today_count(self) -> int:
        """今天的手術次數."""
        today = datetime.now().strftime("%Y%m%d")
        return sum(
            1 for r in self._records
            if r.get("id", "").startswith(f"surgery-{today}")
            and r.get("result") in ("applied", "success")
        )

    def last_surgery_time(self) -> Optional[float]:
        """最後一次手術的時間戳（用於最小間隔計算）."""
        for rec in reversed(self._records):
            if rec.get("result") in ("applied", "success"):
                try:
                    ts = rec.get("timestamp", "")
                    dt = datetime.fromisoformat(ts)
                    return dt.timestamp()
                except Exception:
                    pass
        return None

    def stats(self) -> Dict[str, Any]:
        """統計摘要."""
        total = len(self._records)
        by_result = {}
        for rec in self._records:
            result = rec.get("result", "unknown")
            by_result[result] = by_result.get(result, 0) + 1
        return {
            "total": total,
            "by_result": by_result,
            "today_count": self.today_count(),
        }
