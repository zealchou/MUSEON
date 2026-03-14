"""DataWatchdog — 資料層健康監控與自癒.

Phase 4 的核心模組，建立在 DataContract + DataBus 之上：
1. 資料完整性自動檢查（每晚 Nightly Step 29 執行）
2. 儲存空間監控 + 閾值預警
3. Dead Write 偵測（寫入但長期無變化的 Store）
4. 健康快照持久化（供趨勢分析）

Usage:
    watchdog = DataWatchdog(data_dir=Path("data"))
    report = watchdog.run_health_check()
    # report = {
    #     "status": "ok" | "degraded" | "critical",
    #     "stores": {...},
    #     "alerts": [...],
    #     "storage": {"total_bytes": ..., "by_store": {...}},
    # }
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from museon.core.data_bus import DataBus, get_data_bus

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

# ════════════════════════════════════════════
# 閾值常數
# ════════════════════════════════════════════

# 儲存空間預警（bytes）
SIZE_WARN_SQLITE = 500 * 1024 * 1024   # 500 MB
SIZE_WARN_JSONL = 50 * 1024 * 1024     # 50 MB
SIZE_WARN_JSON = 10 * 1024 * 1024      # 10 MB
SIZE_WARN_TOTAL = 1024 * 1024 * 1024   # 1 GB 全系統

# Dead Write 閾值
DEAD_WRITE_DAYS = 30  # 30 天無變化視為可能的 Dead Write


class DataWatchdog:
    """資料層健康監控犬."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._snapshot_dir = self._data_dir / "_system" / "data_health"
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_path = self._snapshot_dir / "latest_snapshot.json"
        self._history_path = self._snapshot_dir / "snapshot_history.jsonl"

    # ════════════════════════════════════════════
    # 主入口
    # ════════════════════════════════════════════

    def run_health_check(self, bus: Optional[DataBus] = None) -> Dict[str, Any]:
        """執行完整健康檢查.

        Returns:
            {
                "timestamp": "...",
                "status": "ok" | "degraded" | "critical",
                "stores": {name: health_result},
                "alerts": [{"severity": ..., "store": ..., "message": ...}],
                "storage": {"total_bytes": ..., "by_store": {...}},
                "dead_write_suspects": [...],
            }
        """
        bus = bus or get_data_bus()
        now = datetime.now(TZ8).isoformat()
        alerts: List[Dict[str, str]] = []

        # 1. 全 Store 健康檢查
        health_results = bus.health_check_all()

        # 2. 分析健康狀態 + 收集儲存空間
        storage_by_store: Dict[str, int] = {}
        for name, result in health_results.items():
            status = result.get("status", "unknown")

            # 健康異常告警
            if status == "error":
                alerts.append({
                    "severity": "critical",
                    "store": name,
                    "message": f"Store '{name}' 健康檢查失敗: {result.get('error', 'unknown')}",
                })
            elif status == "degraded":
                alerts.append({
                    "severity": "warning",
                    "store": name,
                    "message": f"Store '{name}' 處於降級狀態: {result.get('integrity', '')}",
                })

            # 收集空間數據
            size = self._extract_size(result)
            if size > 0:
                storage_by_store[name] = size

        total_bytes = sum(storage_by_store.values())

        # 3. 儲存空間預警
        alerts.extend(self._check_storage_thresholds(bus, storage_by_store, total_bytes))

        # 4. Dead Write 偵測
        dead_suspects = self._detect_dead_writes(storage_by_store)

        # 5. 彙總狀態
        has_critical = any(a["severity"] == "critical" for a in alerts)
        has_warning = any(a["severity"] == "warning" for a in alerts)
        overall = "critical" if has_critical else ("degraded" if has_warning else "ok")

        report = {
            "timestamp": now,
            "status": overall,
            "stores": health_results,
            "alerts": alerts,
            "storage": {
                "total_bytes": total_bytes,
                "by_store": storage_by_store,
            },
            "dead_write_suspects": dead_suspects,
        }

        # 6. 持久化快照
        self._persist_snapshot(storage_by_store, now)

        logger.info(
            f"[DataWatchdog] 健康檢查完成: status={overall}, "
            f"stores={len(health_results)}, alerts={len(alerts)}, "
            f"total={self._human_size(total_bytes)}"
        )

        return report

    # ════════════════════════════════════════════
    # 儲存空間預警
    # ════════════════════════════════════════════

    def _check_storage_thresholds(
        self,
        bus: DataBus,
        sizes: Dict[str, int],
        total: int,
    ) -> List[Dict[str, str]]:
        """檢查各 Store 的空間是否超過閾值."""
        alerts: List[Dict[str, str]] = []

        # 全系統總量
        if total > SIZE_WARN_TOTAL:
            alerts.append({
                "severity": "warning",
                "store": "_total",
                "message": f"資料總量 {self._human_size(total)} 超過 1GB 預警線",
            })

        # 個別 Store
        for name, size in sizes.items():
            spec = bus.get_spec(name)
            if spec is None:
                continue

            engine = spec.engine.value
            threshold = {
                "sqlite": SIZE_WARN_SQLITE,
                "jsonl": SIZE_WARN_JSONL,
                "json": SIZE_WARN_JSON,
            }.get(engine, SIZE_WARN_JSON)

            if size > threshold:
                alerts.append({
                    "severity": "warning",
                    "store": name,
                    "message": (
                        f"Store '{name}' ({engine}) 佔用 {self._human_size(size)} "
                        f"超過 {self._human_size(threshold)} 預警線"
                    ),
                })

        return alerts

    # ════════════════════════════════════════════
    # Dead Write 偵測
    # ════════════════════════════════════════════

    def _detect_dead_writes(self, current_sizes: Dict[str, int]) -> List[Dict[str, Any]]:
        """比對歷史快照，偵測 30 天無變化的 Store.

        判斷邏輯：
        - 載入最近 30 天的快照
        - 如果某個 Store 的 size 在 30 天內完全沒變（且 size > 0），標記為嫌疑
        """
        suspects: List[Dict[str, Any]] = []

        if not self._history_path.exists():
            return suspects

        cutoff = datetime.now(TZ8) - timedelta(days=DEAD_WRITE_DAYS)

        # 讀取歷史快照
        oldest_sizes: Dict[str, int] = {}
        oldest_ts: Optional[str] = None
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        snap = json.loads(line)
                        ts = snap.get("timestamp", "")
                        # 找到 cutoff 之前最近的一筆
                        if ts and ts < cutoff.isoformat():
                            oldest_sizes = snap.get("sizes", {})
                            oldest_ts = ts
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return suspects

        if not oldest_sizes or not oldest_ts:
            return suspects

        # 比對
        for name, current_size in current_sizes.items():
            if current_size == 0:
                continue
            old_size = oldest_sizes.get(name, -1)
            if old_size == current_size:
                suspects.append({
                    "store": name,
                    "size_bytes": current_size,
                    "unchanged_since": oldest_ts,
                    "message": (
                        f"Store '{name}' ({self._human_size(current_size)}) "
                        f"自 {oldest_ts[:10]} 起無任何變化，可能為 Dead Write"
                    ),
                })

        return suspects

    # ════════════════════════════════════════════
    # 快照持久化
    # ════════════════════════════════════════════

    def _persist_snapshot(self, sizes: Dict[str, int], timestamp: str) -> None:
        """將本次空間快照寫入歷史（JSONL）+ 最新快照（JSON）."""
        snapshot = {
            "timestamp": timestamp,
            "sizes": sizes,
        }

        # 最新快照（覆寫）
        try:
            self._snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"[DataWatchdog] 寫入最新快照失敗: {e}")

        # 歷史記錄（追加）
        try:
            with open(self._history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[DataWatchdog] 寫入歷史快照失敗: {e}")

    # ════════════════════════════════════════════
    # 工具方法
    # ════════════════════════════════════════════

    @staticmethod
    def _extract_size(health_result: Dict[str, Any]) -> int:
        """從 health_check 結果中提取儲存空間."""
        # 直接的 size_bytes 欄位
        if "size_bytes" in health_result:
            return health_result["size_bytes"]

        # file_sizes dict（LatticeStore, FootprintStore）
        if "file_sizes" in health_result:
            return sum(health_result["file_sizes"].values())

        # 個別欄位加總（SoulRingStore, EvalStore）
        total = 0
        for key, val in health_result.items():
            if key.endswith("_bytes") and isinstance(val, (int, float)):
                total += int(val)
        return total

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        """將 bytes 轉換為人類可讀格式."""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f}MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"
