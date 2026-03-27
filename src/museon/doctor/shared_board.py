"""五虎將共享看板 — 讀寫工具函數.

每位虎將執行完後寫入 entry，啟動時讀取看板了解其他虎將狀態。
看板位置: data/_system/doctor/shared_board.json
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def update_shared_board(
    data_dir: Path | str,
    source: str,
    summary: str,
    findings_count: int,
    actions: list[str],
    status: str,
) -> None:
    """更新五虎將共享看板.

    Args:
        data_dir: MUSEON data 目錄 (~/MUSEON/data)
        source: 虎將名稱 (museoff|museqa|musedoc|museworker|nightly)
        summary: 一句話摘要 (最多 200 字)
        findings_count: 發現的問題數
        actions: 採取的行動列表 (最多 5 項)
        status: 狀態 (ok|warning|critical)
    """
    try:
        board_path = Path(data_dir) / "_system" / "doctor" / "shared_board.json"
        board_path.parent.mkdir(parents=True, exist_ok=True)

        # 讀取現有看板
        board: dict[str, Any] = {"entries": []}
        if board_path.exists():
            try:
                board = json.loads(board_path.read_text(encoding="utf-8"))
            except Exception:
                board = {"entries": []}

        # 新增 entry
        entry = {
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "summary": summary[:200],
            "findings_count": findings_count,
            "actions_taken": actions[:5],
            "status": status,
        }
        board["entries"].append(entry)

        # 只保留最近 50 筆
        board["entries"] = board["entries"][-50:]
        board["last_updated"] = datetime.now().isoformat()

        # 原子寫入
        content = json.dumps(board, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(board_path.parent), suffix=".tmp")
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, str(board_path))
        except Exception:
            os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
    except Exception as e:
        logger.debug(f"Shared board update failed: {e}")


def read_shared_board(data_dir: Path | str, limit: int = 10) -> list[dict]:
    """讀取共享看板最近的 entries.

    Args:
        data_dir: MUSEON data 目錄 (~/MUSEON/data)
        limit: 最多返回幾筆 (預設 10)

    Returns:
        最近的 entry 列表
    """
    try:
        board_path = Path(data_dir) / "_system" / "doctor" / "shared_board.json"
        if board_path.exists():
            board = json.loads(board_path.read_text(encoding="utf-8"))
            return board.get("entries", [])[-limit:]
    except Exception:
        pass
    return []
