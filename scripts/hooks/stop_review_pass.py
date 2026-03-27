#!/usr/bin/env python3
"""Claude Code Stop Hook: Sonnet 雙過覆審引擎.

整合原 stop_checklist.py 功能 + 新增覆審 prompt。

流程：
1. 讀取 session 追蹤檔（post_edit_tracker.py 產生的 JSONL）
2. 如有修改記錄 → 產生結構化覆審 prompt 注入 additionalContext
3. 覆審 prompt 會讓 Claude 繼續（不停止），重新檢視修改的檔案
4. 同時保留原有的未 commit 變更提醒

設計原則：
- 輕量，只用 stdlib
- 不 import museon 模組
- exit 0 = allow（Stop hook 不阻斷）
- 覆審後自動清除追蹤檔，避免重複觸發
"""

import glob
import json
import os
import subprocess
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))

from _blast_utils import PROJECT_ROOT, ZONE_CONFIG


# --- 原 stop_checklist.py 功能 ---


def _get_uncommitted_src_changes() -> list[str]:
    """Get list of uncommitted changes in src/ directory."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "src/"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        return lines
    except Exception:
        return []


def _check_docs_changes() -> list[str]:
    """Check if docs/ blueprint files have uncommitted changes."""
    blueprints = [
        "docs/blast-radius.md",
        "docs/joint-map.md",
        "docs/system-topology.md",
        "docs/persistence-contract.md",
        "docs/memory-router.md",
    ]
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"] + blueprints,
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        return lines
    except Exception:
        return []


def _build_checklist_reminder() -> list[str]:
    """Build the original stop checklist (from stop_checklist.py)."""
    src_changes = _get_uncommitted_src_changes()
    if not src_changes:
        return []

    reminders = []
    reminders.append(f"⚠️ 偵測到 {len(src_changes)} 個未 commit 的 src/ 變更：")
    for change in src_changes[:5]:
        reminders.append(f"  {change}")
    if len(src_changes) > 5:
        reminders.append(f"  ...(另有 {len(src_changes) - 5} 個)")

    reminders.append("")
    reminders.append("📋 施工後檢查清單：")
    reminders.append("  1. 跑 scripts/validate_connections.py 確認無孤立連線")
    reminders.append("  2. 檢查五張藍圖是否需要同步更新")
    reminders.append("  3. 跑 pytest 確認無回歸問題")
    reminders.append("  4. Git commit（藍圖 + 程式碼在同一個 commit）")

    docs_changes = _check_docs_changes()
    if docs_changes:
        reminders.append("")
        reminders.append("📐 已偵測到藍圖變更：")
        for change in docs_changes:
            reminders.append(f"  {change}")

    return reminders


# --- 新增：雙過覆審引擎 ---


def _find_tracker_file(session_id: str) -> str | None:
    """Find the tracker file for this session."""
    if session_id and session_id != "unknown":
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        path = f"/tmp/museon_edit_tracker_{safe_id}.jsonl"
        if os.path.exists(path):
            return path

    # Fallback: find any recent tracker file
    candidates = glob.glob("/tmp/museon_edit_tracker_*.jsonl")
    if candidates:
        # Return the most recently modified one
        return max(candidates, key=os.path.getmtime)

    return None


def _read_tracker(tracker_path: str) -> list[dict]:
    """Read all records from the tracker JSONL file."""
    records = []
    try:
        with open(tracker_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception:
        pass
    return records


def _build_review_prompt(records: list[dict]) -> list[str]:
    """Build the double-pass review prompt from tracked edits."""
    if not records:
        return []

    # Deduplicate and count edits per file
    file_edits: Counter = Counter()
    file_zones: dict[str, str] = {}
    for rec in records:
        fp = rec.get("file", "")
        if fp:
            file_edits[fp] += 1
            file_zones[fp] = rec.get("zone", "green")

    # Sort by zone severity then file path
    zone_order = {"forbidden": 0, "red": 1, "yellow": 2, "green": 3}
    sorted_files = sorted(
        file_edits.keys(),
        key=lambda f: (zone_order.get(file_zones[f], 3), f),
    )

    has_high_risk = any(
        file_zones[f] in ("forbidden", "red", "yellow") for f in sorted_files
    )

    lines = []
    lines.append(f"🔍 Sonnet 雙過覆審 — 偵測到 {len(sorted_files)} 個檔案修改")
    lines.append("")
    lines.append("請在結束前完成以下覆審（重新讀取每個修改的檔案，逐項檢查）：")
    lines.append("")

    # 修改清單表格
    lines.append("## 修改清單")
    lines.append("| # | 檔案 | 安全分級 | 修改次數 |")
    lines.append("|---|------|---------|---------|")
    for i, fp in enumerate(sorted_files, 1):
        zone = file_zones[fp]
        config = ZONE_CONFIG.get(zone, ZONE_CONFIG["green"])
        # 取相對路徑顯示
        short = fp
        for marker in ["src/museon/", "scripts/", "docs/", "tests/"]:
            idx = fp.find(marker)
            if idx != -1:
                short = fp[idx:]
                break
        lines.append(
            f"| {i} | `{short}` | {config['emoji']} {config['label']} | {file_edits[fp]} |"
        )

    lines.append("")
    lines.append("## 覆審檢查項（每個檔案都要過）")
    lines.append("1. **重讀檔案**：用 Read 工具重新讀取上述每個修改的檔案")
    lines.append("2. **一致性**：修改是否與 blast-radius.md / joint-map.md 描述一致？有無新增 import 未反映在藍圖中？")
    lines.append("3. **邊界處理**：系統邊界處（檔案 I/O、網路、JSON 解析、SQLite）是否有適當的錯誤處理？")
    lines.append("4. **跨模組影響**：上游呼叫者是否仍能正常工作？")
    lines.append("5. **測試覆蓋**：是否有對應的測試？新增的分支/邊界條件是否被覆蓋？")

    if has_high_risk:
        lines.append("")
        lines.append("## ⚠️ 黃區/紅區特別檢查")
        for fp in sorted_files:
            zone = file_zones[fp]
            if zone in ("forbidden", "red", "yellow"):
                config = ZONE_CONFIG[zone]
                short = os.path.basename(fp)
                lines.append(f"- {config['emoji']} `{short}`: {config['message']}")

    lines.append("")
    lines.append("## 覆審完成後")
    lines.append("- 如發現問題 → 立即修正")
    lines.append("- 如無問題 → 回報「覆審通過」後可結束")

    return lines


def _cleanup_tracker(tracker_path: str) -> None:
    """Delete the tracker file after review."""
    try:
        os.remove(tracker_path)
    except Exception:
        pass


def main():
    # Read hook input from stdin
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        hook_input = {}

    session_id = hook_input.get("session_id", "unknown")

    # 1. 找追蹤檔
    tracker_path = _find_tracker_file(session_id)
    records = _read_tracker(tracker_path) if tracker_path else []

    # 2. 組合所有提醒
    all_context = []

    # 覆審 prompt（如有修改記錄）
    review_lines = _build_review_prompt(records)
    if review_lines:
        all_context.extend(review_lines)

    # 原有的施工後檢查清單
    checklist_lines = _build_checklist_reminder()
    if checklist_lines:
        if all_context:
            all_context.append("")
            all_context.append("---")
            all_context.append("")
        all_context.extend(checklist_lines)

    # 3. 清除追蹤檔（避免下次重複觸發）
    if tracker_path:
        _cleanup_tracker(tracker_path)

    # 4. 輸出
    if all_context:
        output = {
            "decision": "allow",
            "additionalContext": "\n".join(all_context),
        }
        print(json.dumps(output, ensure_ascii=False))
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
