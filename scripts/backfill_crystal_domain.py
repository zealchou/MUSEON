#!/usr/bin/env python3
"""一次性腳本：批次回填現有結晶的 domain 欄位。

對 domain 為空的結晶，用 g1_summary 做關鍵詞匹配自動填入 domain。
執行一次即可，之後新結晶由 crystallize() 的 Step 2.2 自動處理。
"""

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import List, Tuple

# 加入 src 到 path，確保可以 import museon 模組
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

# 使用與 knowledge_lattice.py 相同的關鍵詞表
_DOMAIN_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("business", ["商業", "行銷", "品牌", "銷售", "客戶", "營收", "定位", "廣告", "社群", "轉換"]),
    ("investment", ["投資", "市場", "多空", "股票", "加密", "風險", "ETF", "殖利率", "配置"]),
    ("ai_tech", ["AI", "LLM", "Skill", "架構", "Agent", "模型", "Prompt", "演算法", "GPT"]),
    ("relationship", ["人際", "客戶關係", "合夥", "談判", "團隊", "信任", "溝通"]),
    ("self_growth", ["覺察", "教練", "成長", "信念", "轉化", "情緒", "冥想", "能量"]),
    ("operational", ["部署", "工具", "流程", "SOP", "操作", "發佈", "GitHub", "cron"]),
    ("industry", ["產業", "手搖飲", "美業", "餐飲", "保險", "房地產", "ESG", "永續"]),
]


def classify_domain(text: str) -> str:
    """根據文字內容關鍵詞自動分類 domain。"""
    for domain, keywords in _DOMAIN_KEYWORDS:
        for kw in keywords:
            if kw in text:
                return domain
    return ""


def main() -> None:
    db_path = _ROOT / "data" / "lattice" / "crystal.db"
    if not db_path.exists():
        print(f"[ERROR] 找不到 crystal.db：{db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    # 取得所有 domain 為空的活躍結晶
    rows = conn.execute(
        "SELECT cuid, g1_summary FROM crystals WHERE archived = 0 AND (domain = '' OR domain IS NULL)"
    ).fetchall()

    print(f"找到 {len(rows)} 顆 domain 為空的結晶，開始回填...")

    updates: List[Tuple[str, str]] = []
    for cuid, g1_summary in rows:
        domain = classify_domain(g1_summary or "")
        if domain:
            updates.append((domain, cuid))

    # 批次更新
    if updates:
        conn.execute("BEGIN IMMEDIATE")
        conn.executemany(
            "UPDATE crystals SET domain = ? WHERE cuid = ?",
            updates,
        )
        conn.commit()
        print(f"已回填 {len(updates)} 顆結晶。")
    else:
        print("沒有可分類的結晶（零命中）。")

    # 統計分布
    all_rows = conn.execute(
        "SELECT domain FROM crystals WHERE archived = 0"
    ).fetchall()
    conn.close()

    dist: dict = defaultdict(int)
    for (d,) in all_rows:
        dist[d if d else "(未分類)"] += 1

    total = sum(dist.values())
    print(f"\n=== Domain 分布（共 {total} 顆活躍結晶）===")
    for domain in sorted(dist.keys()):
        count = dist[domain]
        bar = "█" * (count * 30 // max(dist.values()))
        print(f"  {domain:<20} {count:>4} 顆  {bar}")

    unclassified = dist.get("(未分類)", 0)
    print(f"\n未分類：{unclassified} 顆  ({unclassified / total * 100:.1f}%)")


if __name__ == "__main__":
    main()
