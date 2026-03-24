"""
MuseWorker — 觀察員 + 紀錄員（護理師）

24/7 背景常駐，觀察 Museon 服務使用者的過程：
- 即時記錄 Skill 鍛造、Workflow 執行、拓撲變動
- 計算最新系統快照（扇入表、連線、共享狀態、路徑健康）
- 輸出 snapshot.json 供 MuseOff / MuseQA / MuseDoc 使用

設計參考：
- Datadog Watchdog baseline 建立
- Honeycomb 高基數事件記錄
- K8s 事件驅動 + 定時全量掃描

不修改任何東西，純觀察 + 記錄 + 計算。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from museon.doctor.fan_in_scanner import FanInScanner

logger = logging.getLogger(__name__)


class MuseWorker:
    """系統觀察員——計算並維護最新系統快照"""

    VERSION = "1.0.0"

    def __init__(self, museon_home: Path | str | None = None):
        self.home = Path(museon_home or "/Users/ZEALCHOU/MUSEON")
        self.src_dir = self.home / "src" / "museon"
        self.data_dir = self.home / "data" / "_system" / "museworker"
        self.snapshot_path = self.data_dir / "snapshot.json"
        self.history_dir = self.data_dir / "snapshot_history"
        self.change_log_path = self.data_dir / "change_log.jsonl"

        # 確保目錄存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)

        self._scanner = FanInScanner(self.src_dir)

    # -------------------------------------------------------------------
    # 公開 API
    # -------------------------------------------------------------------

    async def full_snapshot(self, trigger: str = "scheduled") -> dict:
        """全量快照——重算所有 216+ 模組"""
        t0 = time.monotonic()
        logger.info("[MuseWorker] Starting full snapshot (trigger=%s)", trigger)

        snapshot = {
            "snapshot_version": _now_iso(),
            "worker_version": self.VERSION,
            "trigger": trigger,
            "fan_in_table": self._compute_fan_in_table(),
            "zone_summary": self._compute_zone_summary(),
            "connections": self._compute_connections(),
            "shared_states": self._compute_shared_states(),
            "path_health": self._compute_path_health(),
            "recent_changes": self._get_recent_git_changes(),
            "compute_duration_ms": 0,
        }
        snapshot["compute_duration_ms"] = int((time.monotonic() - t0) * 1000)

        self._save_snapshot(snapshot)
        logger.info(
            "[MuseWorker] Snapshot complete: %d modules, %d ms",
            len(snapshot["fan_in_table"]),
            snapshot["compute_duration_ms"],
        )
        return snapshot

    async def incremental_update(self, changed_files: list[str], trigger: str = "file_change") -> dict:
        """增量更新——只重算受影響的模組"""
        snapshot = self.load_snapshot()
        if not snapshot:
            return await self.full_snapshot(trigger=trigger)

        affected = self._scanner.scan_affected(changed_files)
        for rel, info in affected.items():
            snapshot["fan_in_table"][rel] = {
                "fan_in": info.fan_in,
                "fan_out": info.fan_out,
                "zone": info.zone,
                "importers": info.importers,
            }

        snapshot["snapshot_version"] = _now_iso()
        snapshot["trigger"] = trigger
        snapshot["recent_changes"] = self._get_recent_git_changes()

        self._save_snapshot(snapshot)
        self._append_change_log(changed_files, trigger)
        return snapshot

    def load_snapshot(self) -> dict | None:
        """讀取最新快照"""
        if not self.snapshot_path.exists():
            return None
        try:
            return json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("[MuseWorker] Failed to load snapshot: %s", e)
            return None

    def record_event(self, event_type: str, data: dict[str, Any]) -> None:
        """記錄系統事件到 change_log"""
        entry = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "data": data,
        }
        with open(self.change_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -------------------------------------------------------------------
    # 計算引擎
    # -------------------------------------------------------------------

    def _compute_fan_in_table(self) -> dict:
        """計算所有模組的扇入表"""
        result = self._scanner.scan_all()
        table = {}
        for rel, info in result.items():
            table[rel] = {
                "fan_in": info.fan_in,
                "fan_out": info.fan_out,
                "zone": info.zone,
                "importers": info.importers,
            }
        return table

    def _compute_zone_summary(self) -> dict:
        """計算各安全等級的模組數"""
        zones = self._scanner.get_zone_summary()
        return {zone: len(modules) for zone, modules in zones.items()}

    def _compute_connections(self) -> dict:
        """呼叫 validate_connections.py 計算連線資訊"""
        script = self.home / "scripts" / "validate_connections.py"
        if not script.exists():
            return {"total": 0, "orphan_outputs": [], "errors": 0}

        try:
            proc = subprocess.run(
                [str(self.home / ".venv" / "bin" / "python"), str(script)],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.home),
            )
            output = proc.stdout
            # 解析關鍵數字
            total = 0
            orphans = []
            errors = 0
            for line in output.split("\n"):
                if "總連線數:" in line:
                    total = int(line.split(":")[1].strip())
                elif "孤立輸出:" in line:
                    orphans.append(line.strip().replace("孤立輸出: ", ""))
                elif "錯誤" in line and "0 錯誤" not in line:
                    errors += 1
            return {"total": total, "orphan_outputs": orphans, "errors": errors}
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.warning("[MuseWorker] validate_connections failed: %s", e)
            return {"total": 0, "orphan_outputs": [], "errors": -1, "error_msg": str(e)}

    def _compute_shared_states(self) -> dict:
        """掃描 data/ 目錄中的關鍵共享狀態檔案"""
        data_dir = self.home / "data"
        key_files = [
            "pulse/pulse.db",
            "_system/group_context.db",
            "_system/wee/workflow_state.db",
            "lattice/crystal.db",
            "registry/cli_user/registry.db",
            "ANIMA_MC.json",
            "ANIMA_USER.json",
            "_system/immunity.json",
            "anima/soul_rings.json",
            "_system/baihe_cache.json",
            "_system/lord_profile.json",
            "_system/museon-persona.md",
        ]
        states = {}
        for rel in key_files:
            path = data_dir / rel
            if path.exists():
                stat = path.stat()
                states[rel] = {
                    "exists": True,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            else:
                states[rel] = {"exists": False, "size_kb": 0, "last_modified": None}
        return states

    def _compute_path_health(self) -> dict:
        """檢查路徑健康度：殭屍檔案、缺失目錄、過期目錄"""
        data_dir = self.home / "data"
        missing = []
        zombies = []
        stale = []

        # 檢查必要目錄
        required_dirs = [
            "pulse", "lattice", "memory", "anima", "eval",
            "_system", "_system/budget", "_system/sessions",
        ]
        for d in required_dirs:
            if not (data_dir / d).exists():
                missing.append(d)

        # 檢查殭屍檔案（0 bytes 的 .db）
        for db in data_dir.rglob("*.db"):
            if db.stat().st_size == 0:
                zombies.append(str(db.relative_to(data_dir)))

        # 檢查合約標記為過期的目錄
        stale_candidates = ["dispatch", "plans", "inbox", "sub_agents", "vault", "wee", "secretary"]
        for d in stale_candidates:
            path = data_dir / d
            if path.exists() and path.is_dir():
                stale.append(d)

        return {
            "missing_paths": missing,
            "zombie_files": zombies,
            "stale_dirs": stale,
        }

    def _get_recent_git_changes(self, hours: int = 24) -> list[dict]:
        """取得最近 N 小時的 git 變動"""
        try:
            proc = subprocess.run(
                ["git", "log", f"--since={hours} hours ago", "--name-only", "--pretty=format:%H|%s|%ai"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(self.home),
            )
            changes = []
            current_commit = None
            for line in proc.stdout.strip().split("\n"):
                if not line:
                    continue
                if "|" in line and len(line.split("|")) >= 3:
                    parts = line.split("|", 2)
                    current_commit = {"hash": parts[0][:8], "message": parts[1], "time": parts[2].strip()}
                elif current_commit and line.strip():
                    changes.append({
                        "file": line.strip(),
                        "commit": current_commit["hash"],
                        "message": current_commit["message"],
                        "time": current_commit["time"],
                    })
            return changes[:50]  # 最多 50 筆
        except (subprocess.TimeoutExpired, OSError):
            return []

    # -------------------------------------------------------------------
    # 持久化
    # -------------------------------------------------------------------

    def _save_snapshot(self, snapshot: dict) -> None:
        """儲存快照 + 備份到歷史"""
        # 原子寫入
        tmp = self.snapshot_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.snapshot_path)

        # 備份（每 6 小時一份，保留 7 天 = 28 份）
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H")
        backup = self.history_dir / f"snapshot_{ts}.json"
        if not backup.exists():
            shutil.copy2(self.snapshot_path, backup)
            self._cleanup_history()

    def _cleanup_history(self, max_files: int = 28) -> None:
        """清理過舊的歷史快照"""
        files = sorted(self.history_dir.glob("snapshot_*.json"))
        while len(files) > max_files:
            files[0].unlink()
            files.pop(0)

    def _append_change_log(self, changed_files: list[str], trigger: str) -> None:
        """追加變動紀錄"""
        entry = {
            "timestamp": _now_iso(),
            "trigger": trigger,
            "files": changed_files,
        }
        with open(self.change_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio
    import sys

    async def main():
        worker = MuseWorker()
        if "--once" in sys.argv:
            snapshot = await worker.full_snapshot(trigger="manual")
            print(f"Snapshot saved: {len(snapshot['fan_in_table'])} modules")
            print(f"  Zones: {snapshot['zone_summary']}")
            print(f"  Connections: {snapshot['connections'].get('total', '?')}")
            print(f"  Shared states: {len(snapshot['shared_states'])} checked")
            print(f"  Path health: missing={len(snapshot['path_health']['missing_paths'])}, "
                  f"zombies={len(snapshot['path_health']['zombie_files'])}, "
                  f"stale={len(snapshot['path_health']['stale_dirs'])}")
            print(f"  Duration: {snapshot['compute_duration_ms']}ms")
        else:
            print("Usage: python -m museon.doctor.museworker --once")

    asyncio.run(main())
