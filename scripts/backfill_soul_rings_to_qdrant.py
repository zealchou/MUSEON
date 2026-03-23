#!/usr/bin/env python3
"""回填既有 Soul Ring 到 Qdrant soul_rings collection.

Project Epigenesis 迭代 3：Soul Ring → Qdrant 索引。

用法：
    cd ~/MUSEON
    .venv/bin/python scripts/backfill_soul_rings_to_qdrant.py

功能：
    1. 載入 data/anima/soul_rings.json 的所有年輪
    2. 驗證 Hash Chain 完整性
    3. 逐條索引到 Qdrant soul_rings collection
    4. 報告索引結果
"""

import sys
from pathlib import Path

# 確保 src 在 path 中
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from museon.agent.soul_ring import DiaryStore
from museon.vector.vector_bridge import VectorBridge


def main():
    data_dir = project_root / "data"

    print("=== Soul Ring → Qdrant 回填工具 ===\n")

    # 初始化 VectorBridge
    print("1. 初始化 VectorBridge...")
    vb = VectorBridge(workspace=data_dir)
    if not vb.is_available():
        print("   ❌ Qdrant 不可用，請確認 Qdrant 服務已啟動")
        sys.exit(1)
    print("   ✅ Qdrant 已連線")

    # 初始化 DiaryStore（帶 vector_bridge）
    print("2. 初始化 DiaryStore...")
    store = DiaryStore(data_dir=str(data_dir), vector_bridge=vb)

    # 驗證完整性
    print("3. 驗證 Hash Chain 完整性...")
    is_valid, msg = store.verify_soul_ring_integrity()
    print(f"   {msg}")
    if not is_valid:
        print("   ⚠️ Hash Chain 損壞，但仍會嘗試索引")

    # 載入年輪
    rings = store.load_soul_rings(verify=False)
    print(f"4. 共 {len(rings)} 條年輪待索引\n")

    if not rings:
        print("   無年輪可索引。")
        return

    # 回填
    print("5. 開始回填...")
    indexed = store.backfill_vector_index()

    # 報告
    print(f"\n=== 完成 ===")
    print(f"   總年輪數：{len(rings)}")
    print(f"   成功索引：{indexed}")
    print(f"   失敗/跳過：{len(rings) - indexed}")


if __name__ == "__main__":
    main()
