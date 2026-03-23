"""Session Cleanup - Release dormant sessions automatically.

v1.55: 時間戳基準改為 session JSON 中的 metadata.last_active（若無則 fallback 到 mtime）
清理閾值：3 天未互動即刪除
觸發時機：每小時自動掃描（透過 cron engine）
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Session 檔案存放目錄
SESSIONS_DIR = Path.home() / "MUSEON" / "data" / "_system" / "sessions"

# 最大不互動時間（秒），3 天 = 259200 秒
MAX_INACTIVE_SECONDS = 3 * 24 * 60 * 60


def get_session_root() -> Path:
    """取得 session 目錄路徑（支援開發/打包環境）。"""
    # 優先查找 MUSEON 開發目錄
    if SESSIONS_DIR.exists():
        return SESSIONS_DIR

    # Fallback 到打包環境
    runtime_root = Path(__file__).resolve()
    for parent in runtime_root.parents:
        if parent.name == ".runtime" and (parent.parent / "data" / "_system" / "sessions").exists():
            return parent.parent / "data" / "_system" / "sessions"

    return SESSIONS_DIR


def _get_session_last_active(session_file: Path) -> Optional[float]:
    """
    取得 session 的最後互動時間戳（秒），優先從 JSON metadata 讀取。

    v1.55: 支援新格式 (metadata + messages) 和舊格式 (pure list)
    """
    try:
        content = session_file.read_text(encoding="utf-8")
        data = json.loads(content)

        # 新格式：{ "metadata": { "last_active": "2026-03-23T..." }, "messages": [...] }
        if isinstance(data, dict) and "metadata" in data:
            last_active_str = data.get("metadata", {}).get("last_active")
            if last_active_str:
                dt = datetime.fromisoformat(last_active_str)
                return dt.timestamp()

        # 舊格式或無 metadata：Fallback 到檔案 mtime
        return None
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.debug(f"Failed to parse last_active from {session_file.name}: {e}")
        return None


async def cleanup_dormant_sessions(max_inactive_seconds: Optional[int] = None) -> dict:
    """
    掃描並刪除超過設定時長未互動的 session 檔案。

    v1.55: 優先使用 metadata.last_active，fallback 到檔案 mtime。

    Args:
        max_inactive_seconds: 不互動秒數閾值，預設 3 天（259200 秒）

    Returns:
        {"deleted": int, "scanned": int, "errors": int}
    """
    if max_inactive_seconds is None:
        max_inactive_seconds = MAX_INACTIVE_SECONDS

    sessions_dir = get_session_root()

    if not sessions_dir.exists():
        logger.warning(f"Sessions directory not found: {sessions_dir}")
        return {"deleted": 0, "scanned": 0, "errors": 0}

    now = time.time()
    stats = {"deleted": 0, "scanned": 0, "errors": 0}

    try:
        # 掃描所有 .json 檔案
        for session_file in sessions_dir.glob("*.json"):
            stats["scanned"] += 1

            try:
                # v1.55: 優先讀 metadata.last_active
                last_active_ts = _get_session_last_active(session_file)
                if last_active_ts is None:
                    # Fallback 到檔案 mtime
                    last_active_ts = session_file.stat().st_mtime

                age_seconds = now - last_active_ts

                if age_seconds > max_inactive_seconds:
                    session_file.unlink()
                    age_days = age_seconds / (24 * 60 * 60)
                    logger.info(
                        f"Deleted dormant session: {session_file.name} "
                        f"(inactive {age_days:.1f} days)"
                    )
                    stats["deleted"] += 1
            except OSError as e:
                logger.error(f"Failed to process session {session_file.name}: {e}")
                stats["errors"] += 1

        logger.info(
            f"Session cleanup complete: {stats['deleted']} deleted, "
            f"{stats['scanned']} scanned, {stats['errors']} errors"
        )
    except Exception as e:
        logger.error(f"Session cleanup failed: {e}")
        stats["errors"] += 1

    return stats
