#!/usr/bin/env python3
"""Hook: 當 Claude Code 寫入 feedback memory 時，自動同步到 MUSEON 三管道.

觸發條件：PostToolUse Write/Edit，檔案路徑含 memory/feedback_
同步目標：crystal_rules.json + heuristics.json + memory_v3/boss/L1_short/

用法（Claude Code Hook）：
  PostToolUse Edit|Write → 偵測 feedback_ 檔案 → 執行本腳本
"""

import json
import sys
import uuid
import re
from datetime import datetime
from pathlib import Path

MUSEON_DATA = Path("/Users/ZEALCHOU/MUSEON/data")
CRYSTAL_RULES = MUSEON_DATA / "_system" / "crystal_rules.json"
HEURISTICS = MUSEON_DATA / "intuition" / "heuristics.json"
MEMORY_DIR = MUSEON_DATA / "memory_v3" / "boss" / "L1_short"


def extract_lesson_from_feedback(filepath: str) -> dict:
    """從 feedback memory 檔案中萃取教訓."""
    content = Path(filepath).read_text(encoding="utf-8")

    # 提取 frontmatter
    name = ""
    description = ""
    fm_match = re.search(r"---\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        name_m = re.search(r"name:\s*(.+)", fm)
        desc_m = re.search(r"description:\s*(.+)", fm)
        if name_m:
            name = name_m.group(1).strip()
        if desc_m:
            description = desc_m.group(1).strip()

    # 提取 body（frontmatter 之後）
    body = content.split("---", 2)[-1].strip() if "---" in content else content

    # 生成 ID（從檔名）
    lesson_id = Path(filepath).stem.replace("feedback_", "")

    return {
        "id": lesson_id,
        "name": name,
        "description": description,
        "body": body[:500],
    }


def sync_to_crystal_rules(lesson: dict) -> bool:
    """同步到 crystal_rules.json."""
    if not CRYSTAL_RULES.exists():
        return False
    data = json.loads(CRYSTAL_RULES.read_text(encoding="utf-8"))
    existing = {r.get("id", "") for r in data.get("rules", [])}
    if lesson["id"] in existing:
        return False  # 已存在

    data["rules"].append({
        "id": lesson["id"],
        "rule": lesson["description"] or lesson["name"],
        "strength": 2.0,
        "origin": "auto_sync_from_feedback",
        "created_at": datetime.now().isoformat(),
        "source": lesson["body"][:200],
    })
    data["updated_at"] = datetime.now().isoformat()
    CRYSTAL_RULES.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def sync_to_heuristics(lesson: dict) -> bool:
    """同步到 heuristics.json."""
    if not HEURISTICS.exists():
        return False
    data = json.loads(HEURISTICS.read_text(encoding="utf-8"))
    existing = {r.get("id", "") for r in data.get("rules", [])}
    if lesson["id"] in existing:
        return False

    data.setdefault("rules", []).append({
        "id": lesson["id"],
        "condition": lesson["name"],
        "action": lesson["description"],
        "confidence": 0.85,
        "source": "auto_sync_from_feedback",
        "created_at": datetime.now().isoformat(),
    })
    HEURISTICS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def sync_to_memory_v3(lesson: dict) -> bool:
    """同步到 memory_v3/boss/L1_short/."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # 檢查是否已有同 lesson_id 的記憶
    for fp in MEMORY_DIR.glob("*.json"):
        try:
            m = json.loads(fp.read_text(encoding="utf-8"))
            if m.get("lesson_id") == lesson["id"]:
                return False  # 已存在
        except Exception:
            continue

    mem_id = str(uuid.uuid4())
    mem = {
        "id": mem_id,
        "type": "lesson",
        "lesson_id": lesson["id"],
        "content": f"教訓：{lesson['name']}。{lesson['description']}",
        "tags": ["教訓", "auto_sync", datetime.now().strftime("%Y-%m-%d")],
        "created_at": datetime.now().isoformat(),
    }
    (MEMORY_DIR / f"{mem_id}.json").write_text(
        json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


def main():
    """從 stdin 讀取 hook input，判斷是否為 feedback memory 寫入."""
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        return

    file_path = (
        hook_input.get("tool_input", {}).get("file_path", "")
        or hook_input.get("result", {}).get("file_path", "")
    )

    # 只處理 feedback memory 檔案
    if "memory/feedback_" not in file_path:
        return

    if not Path(file_path).exists():
        return

    lesson = extract_lesson_from_feedback(file_path)
    if not lesson["name"] and not lesson["description"]:
        return

    r1 = sync_to_crystal_rules(lesson)
    r2 = sync_to_heuristics(lesson)
    r3 = sync_to_memory_v3(lesson)

    synced = sum([r1, r2, r3])
    if synced > 0:
        # 回傳 systemMessage 通知 Claude
        msg = f"✅ 教訓已自動同步到 MUSEON ({synced}/3 管道): {lesson['name'][:50]}"
        print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    main()
