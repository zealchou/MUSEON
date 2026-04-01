#!/usr/bin/env python3
"""Hook: git commit 後檢查四管道教訓同步完整性.

觸發：PostToolUse Bash，當命令含 git commit 時
邏輯：
1. 檢查最近 30 分鐘是否有新的 feedback memory 被寫入
2. 如果有，檢查 heuristics.json、crystal_rules.json、memory_v3/boss/L1_short/ 是否有對應近期更新
3. 如果三管道沒同步 → 輸出 systemMessage 警告
"""
import json
import sys
import os
from pathlib import Path
from datetime import datetime


def main():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        return

    cmd = hook_input.get("tool_input", {}).get("command", "")
    if "git commit" not in cmd:
        return

    # 檢查最近 30 分鐘內是否有 feedback memory 被寫入
    memory_dir = Path(os.path.expanduser("~/.claude/projects/-Users-ZEALCHOU/memory"))
    recent_threshold = datetime.now().timestamp() - 1800  # 30 分鐘

    recent_feedbacks = []
    for f in memory_dir.glob("feedback_*.md"):
        try:
            if f.stat().st_mtime > recent_threshold:
                recent_feedbacks.append(f.name)
        except Exception:
            continue

    if not recent_feedbacks:
        return  # 沒有新教訓，不需要檢查

    # 檢查 MUSEON 三管道
    museon_data = Path("/Users/ZEALCHOU/MUSEON/data")

    heuristics = museon_data / "intuition" / "heuristics.json"
    crystal = museon_data / "_system" / "crystal_rules.json"
    memory_v3 = museon_data / "memory_v3" / "boss" / "L1_short"

    channels_missing = []

    # heuristics 最近 30 分鐘有更新？
    if not (heuristics.exists() and heuristics.stat().st_mtime > recent_threshold):
        channels_missing.append("heuristics.json")

    # crystal_rules 最近 30 分鐘有更新？
    if not (crystal.exists() and crystal.stat().st_mtime > recent_threshold):
        channels_missing.append("crystal_rules.json")

    # memory_v3 最近 30 分鐘有新檔案？
    if memory_v3.exists():
        recent_mem = [f for f in memory_v3.glob("*.json") if f.stat().st_mtime > recent_threshold]
        if not recent_mem:
            channels_missing.append("memory_v3/boss/L1_short")
    else:
        channels_missing.append("memory_v3/boss/L1_short")

    if channels_missing:
        msg = (
            f"\u2717 \u56db\u7ba1\u9053\u6559\u8a13\u540c\u6b65\u4e0d\u5b8c\u6574\uff01"
            f"\u672c session \u6709 {len(recent_feedbacks)} \u689d\u65b0\u6559\u8a13\uff08Claude memory \u2705\uff09\uff0c"
            f"\u4f46 MUSEON \u7ba1\u9053\u7f3a\u5931\uff1a{', '.join(channels_missing)}\u3002"
            f"\u300c\u56db\u7ba1\u9053\u7f3a\u4e00\u4e0d\u53ef\uff01\u300d"
            f"\u7acb\u523b\u8fd0\u884c sync_lesson_to_museon.py \u88dc\u5b8c\uff0c"
            f"\u672a\u540c\u6b65=\u9000\u56de\u88dc\u5b8c\u518d commit\uff0c\u4e0d\u53ef\u8df3\u904e\u3002"
        )
        print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    main()
