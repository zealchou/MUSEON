#!/usr/bin/env python3
"""Claude Code PreToolUse Hook: Edit/Write 前自動查 blast-radius.md.

讀取 stdin JSON 的 tool_input.file_path，解析 blast-radius.md 找到
目標模組的安全分級、扇入、影響範圍，根據分級決定回應：
- 禁區模組 → permissionDecision: "ask"（要使用者確認）
- 紅區模組 → additionalContext 注入安全提醒 + 影響分析
- 黃/綠區 → additionalContext 注入輕量提醒

設計原則：
- 輕量解析，不 import museon 模組
- 無外部依賴（只用 stdlib）
- exit 0 = allow, stderr 用於 debug
"""

import json
import os
import sys

# 確保可以 import 同目錄的 _blast_utils
sys.path.insert(0, os.path.dirname(__file__))

from _blast_utils import ZONE_CONFIG, classify_module


def main():
    # Read hook input from stdin
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        # Can't parse → don't block, just exit
        sys.exit(0)

    # Extract file path from tool_input
    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    if not file_path:
        # No file path → nothing to check
        sys.exit(0)

    # Only check files in MUSEON project
    if "MUSEON" not in file_path and "museon" not in file_path:
        sys.exit(0)

    # Classify the module
    zone, detail = classify_module(file_path)
    config = ZONE_CONFIG[zone]

    if config["action"] == "ask":
        # Forbidden zone → require user confirmation
        output = {
            "decision": "ask",
            "reason": f"{config['emoji']} {config['label']}：{detail}\n{config['message']}",
        }
        print(json.dumps(output))
    else:
        # Context injection → don't block, just inform
        context = (
            f"{config['emoji']} Blast-Radius 安全提醒 [{config['label']}]: "
            f"{detail}\n{config['message']}"
        )
        output = {
            "decision": "allow",
            "additionalContext": context,
        }
        print(json.dumps(output))


if __name__ == "__main__":
    main()
