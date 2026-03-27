#!/usr/bin/env python3
"""
Pre-Edit Hook — 強制藍圖檢查

攔截對 src/, docs/, features/, CLAUDE.md 的 Edit/Write 操作。
用 sentinel 檔案追蹤本 session 是否已讀過 blast-radius.md 和 joint-map.md。

機制：
1. PostToolUse hook（read_blueprint_sentinel.py）在讀完藍圖後寫 sentinel
2. 本 hook 在 Edit/Write 前檢查 sentinel 是否存在且未過期（4 小時內）
3. 如果沒讀過 → block edit，強制先讀藍圖
"""
import sys
import json
import time
from pathlib import Path

MUSEON_HOME = Path.home() / "MUSEON"
SENTINEL_DIR = MUSEON_HOME / ".claude" / "hook_state"
BLAST_SENTINEL = SENTINEL_DIR / "blast_radius_read"
JOINT_SENTINEL = SENTINEL_DIR / "joint_map_read"
MAX_AGE_SECONDS = 4 * 3600  # 4 小時過期

GUARDED_PREFIXES = [
    str(MUSEON_HOME / "src"),
    str(MUSEON_HOME / "docs"),
    str(MUSEON_HOME / "features"),
]
GUARDED_FILES = [
    str(MUSEON_HOME / "CLAUDE.md"),
]


def sentinel_valid(path: Path) -> bool:
    if not path.exists():
        return False
    return (time.time() - path.stat().st_mtime) < MAX_AGE_SECONDS


def is_guarded_path(file_path: str) -> bool:
    for prefix in GUARDED_PREFIXES:
        if file_path.startswith(prefix):
            return True
    return file_path in GUARDED_FILES


def main():
    try:
        stdin_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0

    file_path = stdin_data.get("tool_input", {}).get("file_path", "")

    if not file_path or not is_guarded_path(file_path):
        return 0

    blast_ok = sentinel_valid(BLAST_SENTINEL)
    joint_ok = sentinel_valid(JOINT_SENTINEL)

    if blast_ok and joint_ok:
        return 0

    missing = []
    if not blast_ok:
        missing.append("docs/blast-radius.md")
    if not joint_ok:
        missing.append("docs/joint-map.md")

    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"⛔ 施工前強制檢查：你還沒讀過 {' 和 '.join(missing)}。"
                f" 請先用 Read 工具讀取這些藍圖，確認影響範圍後再動手修改。"
                f" （讀完後 sentinel 會自動更新，再次嘗試 Edit/Write 即可通過。）"
            ),
        }
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
