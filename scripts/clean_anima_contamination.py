#!/usr/bin/env python3
"""一次性清洗腳本：清除 ANIMA_USER.json 和 drift_baseline.json 中的群組對話污染。

用法:
    cd ~/MUSEON
    .venv/bin/python scripts/clean_anima_contamination.py

清洗邏輯:
1. ANIMA_USER.json:
   - eight_primals: signal 含群組前綴的重置為空，confidence 砍半
   - L1_facts: 移除含群組對話片段的條目
   - L2_personality: evidence 含群組內容的降 confidence
   - total_interactions: 扣除群組互動數
2. drift_baseline.json: 直接刪除，讓系統自動重建
"""

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

MUSEON_HOME = Path(__file__).resolve().parent.parent
DATA_DIR = MUSEON_HOME / "data"
ANIMA_USER_PATH = DATA_DIR / "ANIMA_USER.json"
DRIFT_BASELINE_PATH = DATA_DIR / "anima" / "drift_baseline.json"
GROUP_DB_PATH = DATA_DIR / "_system" / "group_context.db"

# 污染標記
CONTAMINATION_MARKERS = [
    "[群組近期對話紀錄]",
    "[群組會議]",
    "[/群組近期對話紀錄]",
    "Feng:",
    "Goku:",
    "（老闆）:",
    "周逸達（Zeal）（老闆）",
    "@MuseonClaw_bot",
]


def count_group_interactions() -> int:
    """從 group_context.db 查詢 owner 的群組訊息數。"""
    if not GROUP_DB_PATH.exists():
        return 0
    try:
        conn = sqlite3.connect(str(GROUP_DB_PATH))
        cursor = conn.execute("SELECT COUNT(*) FROM messages")
        total = cursor.fetchone()[0]
        conn.close()
        return total
    except Exception as e:
        print(f"  [WARN] 無法查詢 group_context.db: {e}")
        return 0


def is_contaminated(text: str) -> bool:
    """判斷文字是否包含群組污染標記。"""
    return any(marker in text for marker in CONTAMINATION_MARKERS)


def clean_anima_user():
    """清洗 ANIMA_USER.json。"""
    if not ANIMA_USER_PATH.exists():
        print("[SKIP] ANIMA_USER.json 不存在")
        return

    # 備份
    backup_path = ANIMA_USER_PATH.with_suffix(".pre_clean.bak")
    shutil.copy2(ANIMA_USER_PATH, backup_path)
    print(f"[BACKUP] {ANIMA_USER_PATH.name} → {backup_path.name}")

    anima = json.loads(ANIMA_USER_PATH.read_text(encoding="utf-8"))

    # ── 1. 清洗八原語 ──
    primals = anima.get("eight_primals", {})
    primal_cleaned = 0
    for key, primal in primals.items():
        signal = primal.get("signal", "")
        if signal and is_contaminated(signal):
            primal["signal"] = ""
            primal["confidence"] = max(0.0, primal.get("confidence", 0) * 0.5)
            primal["last_observed"] = None
            primal_cleaned += 1
            print(f"  [CLEAN] eight_primals.{key}: 重置 signal，confidence 砍半")
    print(f"  八原語清洗: {primal_cleaned}/8 個被重置")

    # ── 2. 清洗 L1_facts ──
    layers = anima.get("seven_layers", {})
    facts = layers.get("L1_facts", [])
    original_count = len(facts)
    clean_facts = [f for f in facts if not is_contaminated(f.get("fact", ""))]
    removed_count = original_count - len(clean_facts)
    layers["L1_facts"] = clean_facts
    print(f"  L1_facts 清洗: 移除 {removed_count}/{original_count} 筆污染條目")

    # ── 3. 清洗 L2_personality ──
    personality = layers.get("L2_personality", [])
    trait_cleaned = 0
    for trait in personality:
        evidence = trait.get("evidence", "")
        if is_contaminated(evidence):
            trait["confidence"] = max(0.1, trait.get("confidence", 0) * 0.5)
            trait["evidence"] = "(待重新觀察 — 群組污染已清除)"
            trait_cleaned += 1
            print(f"  [CLEAN] L2.{trait.get('trait', '?')}: evidence 重置，confidence 砍半")
    print(f"  L2_personality 清洗: {trait_cleaned} 筆")

    # ── 4. 修正 total_interactions ──
    group_msg_count = count_group_interactions()
    relationship = anima.get("relationship", {})
    old_total = relationship.get("total_interactions", 0)
    if group_msg_count > 0:
        new_total = max(1, old_total - group_msg_count)
        relationship["total_interactions"] = new_total
        print(f"  total_interactions: {old_total} → {new_total} (扣除群組 {group_msg_count} 筆)")

    # ── 寫回 ──
    ANIMA_USER_PATH.write_text(
        json.dumps(anima, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[DONE] ANIMA_USER.json 清洗完成")


def clean_drift_baseline():
    """刪除 drift_baseline.json，讓系統自動重建乾淨基線。"""
    if not DRIFT_BASELINE_PATH.exists():
        print("[SKIP] drift_baseline.json 不存在")
        return

    backup_path = DRIFT_BASELINE_PATH.with_suffix(".pre_clean.bak")
    shutil.copy2(DRIFT_BASELINE_PATH, backup_path)
    print(f"[BACKUP] {DRIFT_BASELINE_PATH.name} → {backup_path.name}")

    DRIFT_BASELINE_PATH.unlink()
    print("[DONE] drift_baseline.json 已刪除，系統將自動重建乾淨基線")


def main():
    print("=" * 60)
    print("ANIMA 群組污染清洗工具")
    print(f"時間: {datetime.now().isoformat()}")
    print(f"MUSEON_HOME: {MUSEON_HOME}")
    print("=" * 60)
    print()

    print("── 清洗 ANIMA_USER.json ──")
    clean_anima_user()
    print()

    print("── 清洗 drift_baseline.json ──")
    clean_drift_baseline()
    print()

    print("=" * 60)
    print("清洗完成！請重啟 Gateway daemon 以套用變更。")
    print("  launchctl kickstart -k gui/502/com.museon.gateway")
    print("=" * 60)


if __name__ == "__main__":
    main()
