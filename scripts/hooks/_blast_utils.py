#!/usr/bin/env python3
"""共用 blast-radius 分類邏輯.

供 pre_edit_blast_check.py、post_edit_tracker.py、stop_review_pass.py 共用。
"""

import os

# MUSEON 專案根目錄（相對於 scripts/hooks/）
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
BLAST_RADIUS_PATH = os.path.join(PROJECT_ROOT, "docs", "blast-radius.md")

# 安全分級對照
ZONE_CONFIG = {
    "forbidden": {
        "emoji": "\U0001f6d1",
        "label": "禁區",
        "action": "ask",
        "message": "此模組是禁區（扇入 ≥ 40），任何修改影響全系統。除非系統級重構計畫，否則禁止修改。",
    },
    "red": {
        "emoji": "\U0001f534",
        "label": "紅區",
        "action": "context",
        "message": "此模組是紅區（扇入 ≥ 10），修改影響多個子系統。必須回報使用者 + 全量 pytest + 影響分析。",
    },
    "yellow": {
        "emoji": "\U0001f7e1",
        "label": "黃區",
        "action": "context",
        "message": "此模組是黃區（扇入 2-9），查 blast-radius + joint-map，跑相關測試。",
    },
    "green": {
        "emoji": "\U0001f7e2",
        "label": "綠區",
        "action": "context",
        "message": "此模組是綠區（扇入 0-1），可直接修改，跑單元測試即可。",
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


def classify_module(file_path: str) -> tuple[str, str]:
    """Classify a file path into safety zone.

    Returns (zone_key, detail_message).
    """
    # Normalize path: extract relative path from src/museon/
    rel = file_path
    markers = ["src/museon/", "src\\museon\\"]
    for marker in markers:
        idx = rel.find(marker)
        if idx != -1:
            rel = rel[idx + len(marker) :]
            break

    # Quick match against known lists
    for fp in FORBIDDEN_PATHS:
        if rel.endswith(fp) or fp in rel:
            return "forbidden", f"模組: {fp}"

    for fp in RED_PATHS:
        if rel.endswith(fp) or fp in rel:
            return "red", f"模組: {fp}"

    # If file is outside src/museon/, it's likely green (scripts, docs, etc.)
    if "src/museon/" not in file_path and "src\\museon\\" not in file_path:
        return "green", f"非核心模組: {os.path.basename(file_path)}"

    # Try to parse blast-radius.md for more detail
    detail = _lookup_in_blast_radius(rel)
    if detail:
        return detail

    # Default: yellow for src/museon/ files not in known lists
    return "yellow", f"模組: {rel}（預設黃區）"


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
    forbidden_section = content.find("## \U0001f534 禁區模組")
    red_section = content.find("## \U0001f7e0 紅區模組")
    yellow_section = content.find("## \U0001f7e1 黃區重點模組")
    green_section = content.find("## \U0001f7e2 綠區安全模組")

    # Find which section contains the module
    module_pos = content.find(module_name)
    if module_pos < 0:
        return None

    # Determine zone by position
    if forbidden_section >= 0 and module_pos > forbidden_section and (
        red_section < 0 or module_pos < red_section
    ):
        return "forbidden", f"模組: {rel_path}"
    elif red_section >= 0 and module_pos > red_section and (
        yellow_section < 0 or module_pos < yellow_section
    ):
        return "red", f"模組: {rel_path}"
    elif yellow_section >= 0 and module_pos > yellow_section and (
        green_section < 0 or module_pos < green_section
    ):
        return "yellow", f"模組: {rel_path}"
    elif green_section >= 0 and module_pos > green_section:
        return "green", f"模組: {rel_path}"

    return None
