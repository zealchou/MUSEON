#!/usr/bin/env python3
"""Claude Code PostToolUse Hook: Edit/Write 後記錄修改檔案.

每次 Edit/Write 完成後，將修改的檔案路徑 + 安全分級寫入
session 追蹤檔（/tmp/museon_edit_tracker_{session_id}.jsonl）。

Stop hook (stop_review_pass.py) 會讀取此追蹤檔來產生覆審 prompt。

設計原則：
- 純記錄，不阻斷、不注入 context
- 用 fcntl.flock() 保證並行寫入安全
- exit 0 = allow
"""

import fcntl
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from _blast_utils import classify_module


def _get_tracker_path(session_id: str) -> str:
    """Get the tracker file path for a session."""
    safe_id = session_id.replace("/", "_").replace("\\", "_") if session_id else "unknown"
    return f"/tmp/museon_edit_tracker_{safe_id}.jsonl"


def main():
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    # Extract info
    session_id = hook_input.get("session_id", "unknown")
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        sys.exit(0)

    # Classify the module
    zone, detail = classify_module(file_path)

    # Build record
    record = {
        "ts": datetime.now().isoformat(),
        "file": file_path,
        "zone": zone,
        "tool": tool_name,
    }

    # Append to tracker file with file locking
    tracker_path = _get_tracker_path(session_id)
    try:
        with open(tracker_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        # 寫入失敗不阻斷工作流
        pass

    # 純記錄，不注入 context
    print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()
