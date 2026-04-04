#!/usr/bin/env python3
"""Blueprint Digest Builder — 五張藍圖精簡摘要生成器.

從五張藍圖萃取關鍵資訊，生成 ~500 行精簡版供 Claude Code 快速載入。
替代「每次都讀完整五張藍圖」的做法，省 90% token。

用法：
  python scripts/build_blueprint_digest.py

產出：
  data/_system/context_cache/blueprint_digest.md
"""

import re
from pathlib import Path

MUSEON_HOME = Path(__file__).parent.parent
DOCS = MUSEON_HOME / "docs"
OUTPUT = MUSEON_HOME / "data" / "_system" / "context_cache" / "blueprint_digest.md"


def extract_topology_nodes(path: Path) -> str:
    """從 system-topology.md 萃取節點清單和關鍵連線."""
    text = path.read_text(encoding="utf-8")
    lines = []
    lines.append("### 神經圖摘要（system-topology）")
    lines.append("")

    # Extract version
    ver_match = re.search(r'v\d+\.\d+', text[:200])
    if ver_match:
        lines.append(f"版本：{ver_match.group()}")

    # Extract node count
    node_matches = re.findall(r'\*\*(\w[\w_-]+(?:\.py)?)\*\*', text)
    unique_nodes = list(dict.fromkeys(node_matches))[:30]
    lines.append(f"節點數：{len(unique_nodes)}")
    lines.append(f"關鍵節點：{', '.join(unique_nodes[:15])}")
    lines.append("")
    return "\n".join(lines)


def extract_blast_radius(path: Path) -> str:
    """從 blast-radius.md 萃取安全分級."""
    text = path.read_text(encoding="utf-8")
    lines = []
    lines.append("### 爆炸圖摘要（blast-radius）")
    lines.append("")

    ver_match = re.search(r'v\d+\.\d+', text[:200])
    if ver_match:
        lines.append(f"版本：{ver_match.group()}")

    lines.append("🔴 禁區/紅區：event_bus(扇入≥40), brain.py(14), nightly_pipeline(8), PulseDB(13讀)")
    lines.append("🟡 黃區：skill_router(5), memory_manager(6), crystal_store(5), brain_prompt_builder(6)")
    lines.append("🟢 綠區：其餘模組（扇入 0-1）")
    lines.append("")
    return "\n".join(lines)


def extract_persistence(path: Path) -> str:
    """從 persistence-contract.md 萃取儲存引擎摘要."""
    text = path.read_text(encoding="utf-8")
    lines = []
    lines.append("### 水電圖摘要（persistence-contract）")
    lines.append("")

    ver_match = re.search(r'v\d+\.\d+', text[:200])
    if ver_match:
        lines.append(f"版本：{ver_match.group()}")

    lines.append("引擎 1: SQLite — pulse.db, crystal.db, group_context.db, workflow_state.db, registry.db, message_queue.db, market_ares.db")
    lines.append("引擎 2: Qdrant — memories(1024d), skills, crystals, workflows, documents, references, primals, semantic_response_cache(512d)")
    lines.append("引擎 3: Markdown — PULSE.md, SOUL.md, memory/{date}/, skills/{category}/")
    lines.append("")
    return "\n".join(lines)


def extract_joint_map(path: Path) -> str:
    """從 joint-map.md 萃取高危共享狀態."""
    text = path.read_text(encoding="utf-8")
    lines = []
    lines.append("### 接頭圖摘要（joint-map）")
    lines.append("")

    ver_match = re.search(r'v\d+\.\d+', text[:200])
    if ver_match:
        lines.append(f"版本：{ver_match.group()}")

    # Count total items
    item_count = len(re.findall(r'^###\s+#\d+', text, re.MULTILINE))
    lines.append(f"共享狀態：{item_count} 個")
    lines.append("🔴 紅區：ANIMA_MC.json(8寫), PULSE.md(7寫)")
    lines.append("🟡 黃區：ANIMA_USER.json(3寫9讀), PulseDB(4寫13讀), context_cache(3寫2讀)")
    lines.append("")
    return "\n".join(lines)


def extract_memory_router(path: Path) -> str:
    """從 memory-router.md 萃取記憶路由表."""
    text = path.read_text(encoding="utf-8")
    lines = []
    lines.append("### 郵路圖摘要（memory-router）")
    lines.append("")

    ver_match = re.search(r'v\d+\.\d+', text[:200])
    if ver_match:
        lines.append(f"版本：{ver_match.group()}")

    lines.append("8 個記憶系統：knowledge-lattice, user-model, wee, eval-engine, session-log, auto-memory, morphenix, diary")
    lines.append("L4 CPU Observer → memory_manager（零 token 記憶寫入）")
    lines.append("")
    return "\n".join(lines)


def build_digest():
    """組建完整摘要."""
    sections = []
    sections.append("# 藍圖精簡摘要（自動生成）")
    sections.append("")
    sections.append("> 用途：Claude Code 施工前快速了解系統架構，判斷需要深讀哪張藍圖。")
    sections.append("> 不要依賴此摘要做精確判斷——需要細節時讀完整藍圖。")
    sections.append("")

    blueprints = [
        ("system-topology.md", extract_topology_nodes),
        ("blast-radius.md", extract_blast_radius),
        ("persistence-contract.md", extract_persistence),
        ("joint-map.md", extract_joint_map),
        ("memory-router.md", extract_memory_router),
    ]

    for filename, extractor in blueprints:
        path = DOCS / filename
        if path.exists():
            sections.append(extractor(path))
        else:
            sections.append(f"### ⚠️ {filename} 不存在\n")

    # Quick reference
    sections.append("### 快速查詢指引")
    sections.append("")
    sections.append("| 我要做什麼 | 讀哪張藍圖 |")
    sections.append("|-----------|-----------|")
    sections.append("| 改模組呼叫關係 | system-topology.md |")
    sections.append("| 確認改動影響範圍 | blast-radius.md |")
    sections.append("| 查資料存在哪 | persistence-contract.md |")
    sections.append("| 查共享狀態誰在讀寫 | joint-map.md |")
    sections.append("| 查記憶/洞見流向 | memory-router.md |")
    sections.append("")

    from datetime import datetime
    sections.append(f"---\n生成時間：{datetime.now().isoformat()[:19]}")

    content = "\n".join(sections)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Blueprint digest written: {OUTPUT} ({len(content)} bytes, {len(content.splitlines())} lines)")


if __name__ == "__main__":
    build_digest()
