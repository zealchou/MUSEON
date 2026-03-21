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
import re
import sys

# MUSEON 專案根目錄（相對於 scripts/hooks/）
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
BLAST_RADIUS_PATH = os.path.join(PROJECT_ROOT, "docs", "blast-radius.md")

# 安全分級對照
ZONE_CONFIG = {
    "forbidden": {
        "emoji": "\U0001f6d1",
        "label": "\u7981\u5340",
        "action": "ask",
        "message": "\u6b64\u6a21\u7d44\u662f\u7981\u5340\uff08\u6247\u5165 \u2265 40\uff09\uff0c\u4efb\u4f55\u4fee\u6539\u5f71\u97ff\u5168\u7cfb\u7d71\u3002\u9664\u975e\u7cfb\u7d71\u7d1a\u91cd\u69cb\u8a08\u756b\uff0c\u5426\u5247\u7981\u6b62\u4fee\u6539\u3002",
    },
    "red": {
        "emoji": "\U0001f534",
        "label": "\u7d05\u5340",
        "action": "context",
        "message": "\u6b64\u6a21\u7d44\u662f\u7d05\u5340\uff08\u6247\u5165 \u2265 10\uff09\uff0c\u4fee\u6539\u5f71\u97ff\u591a\u500b\u5b50\u7cfb\u7d71\u3002\u5fc5\u9808\u56de\u5831\u4f7f\u7528\u8005 + \u5168\u91cf pytest + \u5f71\u97ff\u5206\u6790\u3002",
    },
    "yellow": {
        "emoji": "\U0001f7e1",
        "label": "\u9ec3\u5340",
        "action": "context",
        "message": "\u6b64\u6a21\u7d44\u662f\u9ec3\u5340\uff08\u6247\u5165 2-9\uff09\uff0c\u67e5 blast-radius + joint-map\uff0c\u8dd1\u76f8\u95dc\u6e2c\u8a66\u3002",
    },
    "green": {
        "emoji": "\U0001f7e2",
        "label": "\u7da0\u5340",
        "action": "context",
        "message": "\u6b64\u6a21\u7d44\u662f\u7da0\u5340\uff08\u6247\u5165 0-1\uff09\uff0c\u53ef\u76f4\u63a5\u4fee\u6539\uff0c\u8dd1\u55ae\u5143\u6e2c\u8a66\u5373\u53ef\u3002",
    },
}

# 已知禁區模組路徑（快速匹配，不需解析 markdown）
FORBIDDEN_PATHS = [
    "core/event_bus.py",
]

# 已知紅區模組路徑
RED_PATHS = [
    "gateway/server.py",
    "gateway/message.py",
    "tools/tool_registry.py",
    "core/data_bus.py",
    "pulse/pulse_db.py",
    "agent/brain.py",
    "agent/dispatch.py",
]


def _classify_module(file_path: str) -> tuple[str, str]:
    """Classify a file path into safety zone.

    Returns (zone_key, detail_message).
    """
    # Normalize path: extract relative path from src/museon/
    rel = file_path
    markers = ["src/museon/", "src\\museon\\"]
    for marker in markers:
        idx = rel.find(marker)
        if idx != -1:
            rel = rel[idx + len(marker):]
            break

    # Quick match against known lists
    for fp in FORBIDDEN_PATHS:
        if rel.endswith(fp) or fp in rel:
            return "forbidden", f"\u6a21\u7d44: {fp}"

    for fp in RED_PATHS:
        if rel.endswith(fp) or fp in rel:
            return "red", f"\u6a21\u7d44: {fp}"

    # If file is outside src/museon/, it's likely green (scripts, docs, etc.)
    if "src/museon/" not in file_path and "src\\museon\\" not in file_path:
        return "green", f"\u975e\u6838\u5fc3\u6a21\u7d44: {os.path.basename(file_path)}"

    # Try to parse blast-radius.md for more detail
    detail = _lookup_in_blast_radius(rel)
    if detail:
        return detail

    # Default: yellow for src/museon/ files not in known lists
    return "yellow", f"\u6a21\u7d44: {rel}\uff08\u9810\u8a2d\u9ec3\u5340\uff09"


def _lookup_in_blast_radius(rel_path: str) -> tuple[str, str] | None:
    """Parse blast-radius.md to find module classification."""
    if not os.path.exists(BLAST_RADIUS_PATH):
        return None

    try:
        with open(BLAST_RADIUS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None

    # Search for the module name in the file
    module_name = os.path.basename(rel_path)
    if module_name not in content:
        return None

    # Check which zone section it's in
    # Sections are marked with ## headers containing zone emojis
    forbidden_section = content.find("## \U0001f534 \u7981\u5340\u6a21\u7d44")
    red_section = content.find("## \U0001f7e0 \u7d05\u5340\u6a21\u7d44")
    yellow_section = content.find("## \U0001f7e1 \u9ec3\u5340\u91cd\u9ede\u6a21\u7d44")
    green_section = content.find("## \U0001f7e2 \u7da0\u5340\u5b89\u5168\u6a21\u7d44")

    # Find which section contains the module
    module_pos = content.find(module_name)
    if module_pos < 0:
        return None

    # Determine zone by position
    if forbidden_section >= 0 and module_pos > forbidden_section and (
        red_section < 0 or module_pos < red_section
    ):
        return "forbidden", f"\u6a21\u7d44: {rel_path}"
    elif red_section >= 0 and module_pos > red_section and (
        yellow_section < 0 or module_pos < yellow_section
    ):
        return "red", f"\u6a21\u7d44: {rel_path}"
    elif yellow_section >= 0 and module_pos > yellow_section and (
        green_section < 0 or module_pos < green_section
    ):
        return "yellow", f"\u6a21\u7d44: {rel_path}"
    elif green_section >= 0 and module_pos > green_section:
        return "green", f"\u6a21\u7d44: {rel_path}"

    return None


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
    zone, detail = _classify_module(file_path)
    config = ZONE_CONFIG[zone]

    if config["action"] == "ask":
        # Forbidden zone → require user confirmation
        output = {
            "decision": "ask",
            "reason": f"{config['emoji']} {config['label']}\uff1a{detail}\n{config['message']}",
        }
        print(json.dumps(output))
    else:
        # Context injection → don't block, just inform
        context = (
            f"{config['emoji']} Blast-Radius \u5b89\u5168\u63d0\u9192 [{config['label']}]: "
            f"{detail}\n{config['message']}"
        )
        output = {
            "decision": "allow",
            "additionalContext": context,
        }
        print(json.dumps(output))


if __name__ == "__main__":
    main()
