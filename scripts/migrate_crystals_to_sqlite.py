#!/usr/bin/env python3
"""一次性遷移腳本：crystals.json + links.json + cuid_counter.json → crystal.db (SQLite WAL).

用法：
    .venv/bin/python scripts/migrate_crystals_to_sqlite.py [--data-dir DATA_DIR] [--dry-run]

行為：
    1. 讀取 data/lattice/ 下的四個 JSON 檔案
    2. 寫入 data/lattice/crystal.db（SQLite WAL 模式）
    3. 將舊 JSON 檔案改名為 .bak 歸檔
    4. 驗證遷移後的資料完整性
"""

import argparse
import json
import sys
from pathlib import Path

# 確保 src 在 sys.path 中
_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "src"))

from museon.agent.crystal_store import CrystalStore  # noqa: E402
from museon.agent.knowledge_lattice import Crystal, CrystalLink  # noqa: E402


def migrate(data_dir: str, dry_run: bool = False) -> None:
    """執行遷移."""
    lattice_dir = Path(data_dir) / "lattice"

    crystals_path = lattice_dir / "crystals.json"
    links_path = lattice_dir / "links.json"
    archive_path = lattice_dir / "archive.json"
    counter_path = lattice_dir / "cuid_counter.json"
    db_path = lattice_dir / "crystal.db"

    # ── 檢查前置條件 ──
    if db_path.exists():
        print(f"[WARN] {db_path} 已存在。如果要重新遷移，請先手動刪除。")
        return

    if not crystals_path.exists():
        print(f"[ERROR] {crystals_path} 不存在，無法遷移。")
        return

    # ── 讀取 JSON ──
    print("=== Phase 1: 讀取 JSON ===")

    crystals_data = json.loads(crystals_path.read_text(encoding="utf-8"))
    print(f"  crystals.json: {len(crystals_data)} 筆")

    links_data = []
    if links_path.exists():
        links_data = json.loads(links_path.read_text(encoding="utf-8"))
    print(f"  links.json: {len(links_data)} 筆")

    archive_data = []
    if archive_path.exists():
        try:
            archive_data = json.loads(archive_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            archive_data = []
    print(f"  archive.json: {len(archive_data)} 筆")

    counters = {"INS": 0, "PAT": 0, "LES": 0, "HYP": 0}
    if counter_path.exists():
        counters.update(
            json.loads(counter_path.read_text(encoding="utf-8"))
        )
    print(f"  cuid_counter.json: {counters}")

    if dry_run:
        print("\n[DRY-RUN] 不執行實際遷移。")
        return

    # ── 寫入 SQLite ──
    print("\n=== Phase 2: 寫入 SQLite WAL ===")

    store = CrystalStore(data_dir=data_dir)

    # 結晶
    crystals = {}
    errors = 0
    for item in crystals_data:
        try:
            c = Crystal.from_dict(item)
            crystals[c.cuid] = c
        except Exception as e:
            errors += 1
            print(f"  [WARN] 跳過無效結晶: {e}")
    store.save_crystals(crystals)
    print(f"  寫入 crystals: {len(crystals)} 筆（{errors} 筆跳過）")

    # 歸檔結晶
    archive = {}
    for item in archive_data:
        try:
            c = Crystal.from_dict(item)
            c.archived = True
            archive[c.cuid] = c
        except Exception as e:
            print(f"  [WARN] 跳過無效歸檔結晶: {e}")
    if archive:
        store.save_archive(archive)
    print(f"  寫入 archive: {len(archive)} 筆")

    # 連結
    links = []
    for item in links_data:
        try:
            links.append(CrystalLink.from_dict(item))
        except Exception as e:
            print(f"  [WARN] 跳過無效連結: {e}")
    store.save_links(links)
    print(f"  寫入 links: {len(links)} 筆")

    # 計數器
    store.save_counters(counters)
    print(f"  寫入 counters: {counters}")

    # ── 驗證 ──
    print("\n=== Phase 3: 驗證 ===")

    v_crystals = store.load_crystals()
    v_archive = store.load_archive()
    v_links = store.load_links()
    v_counters = store.load_counters()

    ok = True
    if len(v_crystals) != len(crystals):
        print(f"  [FAIL] crystals: 預期 {len(crystals)}，實際 {len(v_crystals)}")
        ok = False
    else:
        print(f"  [OK] crystals: {len(v_crystals)} 筆")

    if len(v_archive) != len(archive):
        print(f"  [FAIL] archive: 預期 {len(archive)}，實際 {len(v_archive)}")
        ok = False
    else:
        print(f"  [OK] archive: {len(v_archive)} 筆")

    if len(v_links) != len(links):
        print(f"  [FAIL] links: 預期 {len(links)}，實際 {len(v_links)}")
        ok = False
    else:
        print(f"  [OK] links: {len(v_links)} 筆")

    if v_counters != counters:
        print(f"  [FAIL] counters: 預期 {counters}，實際 {v_counters}")
        ok = False
    else:
        print(f"  [OK] counters: {v_counters}")

    if not ok:
        print("\n[ERROR] 驗證失敗，保留 JSON 不歸檔。")
        # 刪除剛建立的 db
        if db_path.exists():
            db_path.unlink()
        return

    # ── 歸檔舊 JSON ──
    print("\n=== Phase 4: 歸檔舊 JSON ===")

    for p in [crystals_path, links_path, archive_path, counter_path]:
        if p.exists():
            bak = p.with_suffix(".json.bak")
            p.rename(bak)
            print(f"  {p.name} → {bak.name}")

    health = store.health_check()
    print(f"\n=== 遷移完成 ===")
    print(f"  DB: {db_path}")
    print(f"  WAL: journal_mode=WAL")
    print(f"  健康檢查: {health}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="遷移 Knowledge Lattice JSON → SQLite WAL"
    )
    parser.add_argument(
        "--data-dir",
        default=str(_root / "data"),
        help="資料目錄路徑（預設：專案根目錄/data）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只讀取不寫入",
    )
    args = parser.parse_args()
    migrate(args.data_dir, args.dry_run)
