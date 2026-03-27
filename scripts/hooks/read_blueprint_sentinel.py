#!/usr/bin/env python3
"""
PostToolUse Hook (Read) — 讀完藍圖後寫 sentinel

當 Read 工具讀取 blast-radius.md 或 joint-map.md 時，
自動在 .claude/hook_state/ 下寫入 sentinel 檔案，
讓 pre_edit_blast_check.py 知道藍圖已被閱讀。
"""
import sys
import json
from pathlib import Path

MUSEON_HOME = Path.home() / "MUSEON"
SENTINEL_DIR = MUSEON_HOME / ".claude" / "hook_state"

BLUEPRINT_MAP = {
    "blast-radius.md": SENTINEL_DIR / "blast_radius_read",
    "joint-map.md": SENTINEL_DIR / "joint_map_read",
}


def main():
    try:
        stdin_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return 0

    file_path = stdin_data.get("tool_input", {}).get("file_path", "")

    for blueprint_name, sentinel_path in BLUEPRINT_MAP.items():
        if file_path.endswith(blueprint_name):
            SENTINEL_DIR.mkdir(parents=True, exist_ok=True)
            sentinel_path.write_text(file_path)
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
