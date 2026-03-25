#!/usr/bin/env python3
"""
Stop Hook 檢查清單——在 Claude session 結束前自動驗證
"""
import sys
import json
from pathlib import Path

def main():
    # 檢查 session 摘要
    memory_dir = Path.home() / ".claude/projects/-Users-ZEALCHOU/memory/sessions"

    if not memory_dir.exists():
        print(json.dumps({"status": "ok", "note": "no session memory yet"}))
        return 0

    # 列出最近的摘要
    summaries = sorted(memory_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    if summaries:
        latest = summaries[0]
        print(json.dumps({"status": "ok", "latest_summary": str(latest)}))
    else:
        print(json.dumps({"status": "ok", "note": "no summaries yet"}))

    return 0

if __name__ == "__main__":
    sys.exit(main())
