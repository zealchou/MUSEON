#!/usr/bin/env python3
"""Claude Code Stop Hook: session 結束前檢查未 commit 的變更.

偵測 src/ 目錄下是否有未 commit 的修改。
如有 → additionalContext 提醒跑 validate_connections.py + 藍圖更新。
如無 → 靜默 exit 0。

設計原則：
- 輕量，只用 subprocess + json
- 不 import museon 模組
- exit 0 = allow（Stop hook 不會阻斷）
"""

import json
import os
import subprocess
import sys

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


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


def main():
    src_changes = _get_uncommitted_src_changes()

    if not src_changes:
        # No uncommitted src/ changes → silent exit
        sys.exit(0)

    # Build checklist reminder
    reminders = []
    reminders.append(
        f"\u26a0\ufe0f \u5075\u6e2c\u5230 {len(src_changes)} \u500b\u672a commit \u7684 src/ \u8b8a\u66f4\uff1a"
    )
    for change in src_changes[:5]:
        reminders.append(f"  {change}")
    if len(src_changes) > 5:
        reminders.append(f"  ...(\u53e6\u6709 {len(src_changes) - 5} \u500b)")

    reminders.append("")
    reminders.append("\U0001f4cb \u65bd\u5de5\u5f8c\u6aa2\u67e5\u6e05\u55ae\uff1a")
    reminders.append("  1. \u8dd1 scripts/validate_connections.py \u78ba\u8a8d\u7121\u5b64\u7acb\u9023\u7dda")
    reminders.append("  2. \u6aa2\u67e5\u4e94\u5f35\u85cd\u5716\u662f\u5426\u9700\u8981\u540c\u6b65\u66f4\u65b0")
    reminders.append("  3. \u8dd1 pytest \u78ba\u8a8d\u7121\u56de\u6b78\u554f\u984c")
    reminders.append("  4. Git commit\uff08\u85cd\u5716 + \u7a0b\u5f0f\u78bc\u5728\u540c\u4e00\u500b commit\uff09")

    docs_changes = _check_docs_changes()
    if docs_changes:
        reminders.append("")
        reminders.append("\U0001f4d0 \u5df2\u5075\u6e2c\u5230\u85cd\u5716\u8b8a\u66f4\uff1a")
        for change in docs_changes:
            reminders.append(f"  {change}")

    output = {
        "decision": "allow",
        "additionalContext": "\n".join(reminders),
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
