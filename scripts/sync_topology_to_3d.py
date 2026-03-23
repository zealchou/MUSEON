#!/usr/bin/env python3
"""
sync_topology_to_3d.py — 拓撲文件 → 3D 心智圖 HTML 同步腳本

讀取 docs/system-topology.md（唯一真相來源），解析所有節點和連線，
重新生成 data/workspace/MUSEON_3d_mindmap.html 中的 nodes/links 陣列。

用法：
    .venv/bin/python scripts/sync_topology_to_3d.py             # 預覽差異（dry-run）
    .venv/bin/python scripts/sync_topology_to_3d.py --apply     # 全量重生成並套用
    .venv/bin/python scripts/sync_topology_to_3d.py --json      # JSON 格式輸出差異
"""

import re
import sys
import json
from pathlib import Path
from datetime import date
from typing import Optional


def _sanitize_zh(zh: str) -> str:
    """標準化 zh 欄位——截斷括號內的技術細節，保留簡潔中文名.

    拓撲文件的中文名常夾帶技術細節（括號、行數、公式等），
    3D 心智圖 info panel 只需短名，完整描述存 desc 欄位。

    規則：
    - 只截斷括號 `（` `(` 及之後的內容
    - 不截斷冒號（"Mixin: 任務分派" 保留完整）
    - 截斷後太短（< 2 字）則保留原文
    """
    # 只去除括號及之後的內容（保留冒號前後）
    short = re.split(r'[（(]', zh, maxsplit=1)[0].strip()
    # 如果截斷後太短（<2 字），保留原文
    if len(short) < 2:
        short = zh
    return short

# ── 路徑 ────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
TOPOLOGY_PATH = ROOT / "docs" / "system-topology.md"
HTML_PATH = ROOT / "data" / "workspace" / "MUSEON_3d_mindmap.html"


# ═══════════════════════════════════════════════════
#  拓撲解析器
# ═══════════════════════════════════════════════════

def parse_topology(text: str) -> dict:
    """解析 system-topology.md，回傳 {version, nodes, links}"""
    nodes_raw = _parse_nodes(text)
    # 去重：同 ID 取第一次出現的
    seen = {}
    nodes_dedup = []
    for n in nodes_raw:
        if n["id"] not in seen:
            seen[n["id"]] = True
            nodes_dedup.append(n)

    result = {
        "version": _parse_version(text),
        "nodes": nodes_dedup,
        "links": _parse_links(text),
    }
    return result


def _parse_version(text: str) -> str:
    m = re.search(r"# MUSEON 系統拓撲圖 (v[\d.]+)", text)
    return m.group(1) if m else "unknown"


def _parse_nodes(text: str) -> list[dict]:
    """解析所有節點表格"""
    nodes = []
    current_group = None
    lines = text.splitlines()

    # 群組 ID 集合（從群組定義表取得）
    known_groups = set()
    for line in lines:
        m = re.match(r"^\|\s*`(\w[\w-]*)`\s*\|", line)
        if m:
            gid = m.group(1)
            # 只有在群組定義表區域才收集
            if "色碼" not in line and gid not in ("ID",):
                known_groups.add(gid)

    # 從群組定義表取群組 ID
    in_group_table = False
    group_ids = set()
    for line in lines:
        if "群組 ID" in line and "色碼" in line:
            in_group_table = True
            continue
        if in_group_table:
            if line.startswith("|") and "`" in line:
                m = re.match(r"^\|\s*`(\w[\w-]*)`", line)
                if m:
                    group_ids.add(m.group(1))
            elif not line.strip().startswith("|"):
                if group_ids:
                    break

    for line in lines:
        # 偵測 ## 二級標題（離開節點區域）
        if re.match(r"^## [^#]", line) and "連線" in line:
            current_group = None
            continue

        # 偵測群組標題：### group_id — ... 或 #### sub-group — ...
        heading_match = re.match(r"^#{2,4}\s+(\S+)\s*[—–-]", line)
        if heading_match:
            candidate = heading_match.group(1)
            if candidate in group_ids:
                current_group = candidate
            elif candidate.startswith("skills-"):
                # skills 子群組（skills-thinking, skills-market 等）歸入 skills
                current_group = "skills"
            continue

        # 偵測節點表格行
        if current_group and line.startswith("|") and "`" in line:
            cols = [c.strip() for c in line.split("|")]
            cols = [c for c in cols if c]
            if len(cols) < 4:
                continue

            nid = cols[0].strip("`")
            if nid in ("ID", "---", "") or nid.startswith("-"):
                continue

            label = cols[1]
            zh_raw = cols[2]
            zh_short = _sanitize_zh(zh_raw)
            zh_desc = zh_raw if zh_short != zh_raw else ""

            node: dict = {
                "id": nid,
                "label": label,
                "zh": zh_short,
                "group": current_group,
            }
            if zh_desc:
                node["desc"] = zh_desc

            hub_col = cols[3].strip()
            if hub_col == "Yes":
                node["hub"] = 1

            # Parent + 半徑（6 欄）或 只有半徑（5 欄）
            if len(cols) >= 6:
                parent_col = cols[4].strip()
                if parent_col and parent_col != "-":
                    node["p"] = parent_col
                try:
                    node["r"] = float(cols[5].strip())
                except (ValueError, IndexError):
                    node["r"] = 1.0
            elif len(cols) >= 5:
                try:
                    node["r"] = float(cols[4].strip())
                except (ValueError, IndexError):
                    node["r"] = 1.0
            else:
                node["r"] = 1.0

            nodes.append(node)

    return nodes


def _parse_links(text: str) -> list[dict]:
    """解析所有連線表格"""
    links = []
    current_type: Optional[str] = None
    type_re = re.compile(r"[（(](flow|control|internal|cross|async|monitor|decay)[）)]")

    for line in text.splitlines():
        # 偵測連線區段標題（### 或 ####）
        if re.match(r"^#{3,4}\s+", line):
            m = type_re.search(line)
            if m:
                current_type = m.group(1)
            continue

        if current_type and line.startswith("|") and "`" in line:
            cols = [c.strip() for c in line.split("|")]
            cols = [c for c in cols if c]
            if len(cols) < 3:
                continue

            source_raw = cols[0]
            target_raw = cols[1]
            desc = cols[2]

            # 第一欄必須包含反引號包裹的 ID（排除版本歷史表等誤判）
            if "`" not in source_raw:
                continue

            # 處理 decay 連線特殊格式：`A` → `B` | target_desc | desc
            if current_type == "decay" and "→" in source_raw:
                parts = source_raw.split("→")
                source = parts[0].strip().strip("`").strip()
                target = parts[1].strip().strip("`").strip()
                desc = target_raw  # 第二欄是描述
            else:
                source = source_raw.strip("`")
                target = target_raw.strip("`")

            if source in ("Source", "---", "") or target in ("Target", "---", ""):
                continue

            links.append({
                "source": source,
                "target": target,
                "label": desc,
                "type": current_type,
            })

    return links


# ═══════════════════════════════════════════════════
#  HTML JS 陣列解析器
# ═══════════════════════════════════════════════════

def _extract_js_array(html: str, var_name: str) -> str:
    """從 HTML 中提取 const <var_name> = [...] 的內容"""
    pattern = rf"const\s+{var_name}\s*=\s*\["
    m = re.search(pattern, html)
    if not m:
        return ""
    depth = 0
    pos = m.end() - 1  # 指向 [
    for j in range(pos, len(html)):
        if html[j] == "[":
            depth += 1
        elif html[j] == "]":
            depth -= 1
            if depth == 0:
                return html[pos:j + 1]
    return ""


def _parse_html_nodes(html: str) -> list[dict]:
    """從 HTML 解析現有節點"""
    arr = _extract_js_array(html, "nodes")
    nodes = []
    for m in re.finditer(r"\{([^}]+)\}", arr):
        obj = m.group(1)
        node = {}
        for key in ("id", "label", "zh", "group", "p"):
            km = re.search(rf'(?<!\w){key}\s*:\s*"([^"]*)"', obj)
            if km:
                node[key] = km.group(1)
        for key in ("r",):
            km = re.search(rf"(?<!\w){key}\s*:\s*([\d.]+)", obj)
            if km:
                node[key] = float(km.group(1))
        km = re.search(r"(?<!\w)hub\s*:\s*(\d)", obj)
        if km and km.group(1) == "1":
            node["hub"] = 1
        if "id" in node:
            nodes.append(node)
    return nodes


def _parse_html_links(html: str) -> list[dict]:
    """從 HTML 解析現有連線"""
    arr = _extract_js_array(html, "links")
    links = []
    for m in re.finditer(r"\{([^}]+)\}", arr):
        obj = m.group(1)
        link = {}
        for key in ("source", "target", "label", "type"):
            km = re.search(rf'(?<!\w){key}\s*:\s*"([^"]*)"', obj)
            if km:
                link[key] = km.group(1)
        if "source" in link and "target" in link:
            links.append(link)
    return links


# ═══════════════════════════════════════════════════
#  差異比對
# ═══════════════════════════════════════════════════

def diff_report(topo: dict, html_nodes: list, html_links: list) -> dict:
    """比對拓撲與 HTML 的差異"""
    topo_node_ids = {n["id"] for n in topo["nodes"]}
    html_node_ids = {n["id"] for n in html_nodes}

    topo_link_keys = {(l["source"], l["target"]) for l in topo["links"]}
    html_link_keys = {(l["source"], l["target"]) for l in html_links}

    return {
        "topo_version": topo["version"],
        "topo_nodes": len(topo["nodes"]),
        "topo_links": len(topo["links"]),
        "html_nodes": len(html_nodes),
        "html_links": len(html_links),
        "nodes_added": sorted(topo_node_ids - html_node_ids),
        "nodes_removed": sorted(html_node_ids - topo_node_ids),
        "links_added": sorted(topo_link_keys - html_link_keys),
        "links_removed": sorted(html_link_keys - topo_link_keys),
    }


# ═══════════════════════════════════════════════════
#  JS 程式碼生成器
# ═══════════════════════════════════════════════════

GROUP_ORDER = [
    "center", "channel", "agent", "pulse", "gov", "doctor",
    "llm", "data", "evolution", "tools", "nightly", "installer",
    "external", "skills",
]


def _node_to_js(n: dict) -> str:
    parts = [
        f'id:"{n["id"]}"',
        f'label:"{n["label"]}"',
        f'zh:"{n["zh"]}"',
        f'group:"{n["group"]}"',
    ]
    r = n.get("r", 1.0)
    parts.append(f"r:{r}")
    if n.get("p"):
        parts.append(f'p:"{n["p"]}"')
    if n.get("hub"):
        parts.append("hub:1")
    if n.get("desc"):
        # 完整描述（括號/技術細節），info panel 點擊查看
        parts.append(f'desc:"{n["desc"]}"')
    return "  {" + ",".join(parts) + "}"


def _link_to_js(lk: dict) -> str:
    return (
        f'  {{source:"{lk["source"]}",'
        f'target:"{lk["target"]}",'
        f'label:"{lk["label"]}",'
        f'type:"{lk["type"]}"}}'
    )


def generate_nodes_js(nodes: list[dict]) -> str:
    """生成完整 const nodes = [...]; 區塊"""
    order_map = {g: i for i, g in enumerate(GROUP_ORDER)}

    def sort_key(n):
        gidx = order_map.get(n["group"], 99)
        is_hub = 0 if n.get("hub") else 1
        return (gidx, is_hub, n["id"])

    sorted_nodes = sorted(nodes, key=sort_key)
    lines = ["const nodes = ["]
    current_group = None
    for n in sorted_nodes:
        if n["group"] != current_group:
            current_group = n["group"]
            lines.append(f"  // ── {current_group} ──")
        lines.append(_node_to_js(n) + ",")
    lines.append("];")
    return "\n".join(lines)


def generate_links_js(links: list[dict]) -> str:
    """生成完整 const links = [...]; 區塊"""
    type_order = ["decay", "flow", "control", "internal", "cross", "monitor", "async"]
    order_map = {t: i for i, t in enumerate(type_order)}

    def sort_key(lk):
        return (order_map.get(lk["type"], 99), lk["source"], lk["target"])

    sorted_links = sorted(links, key=sort_key)
    lines = ["const links = ["]
    current_type = None
    for lk in sorted_links:
        if lk["type"] != current_type:
            current_type = lk["type"]
            lines.append(f"  // ── {current_type} ──")
        lines.append(_link_to_js(lk) + ",")
    lines.append("];")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════
#  HTML 全量替換
# ═══════════════════════════════════════════════════

def sync_html(topo: dict, html: str) -> str:
    """以拓撲資料全量替換 HTML 中的 nodes/links 陣列"""
    # 找到 nodes 陣列開頭
    nodes_start = re.search(r"^const nodes = \[", html, re.MULTILINE)
    if not nodes_start:
        raise ValueError("找不到 const nodes = [ 標記")

    # 找到 links 陣列結尾的 ];（緊接 const nodeMap 之前）
    links_end = re.search(r"^\];\s*\n\s*const nodeMap", html, re.MULTILINE)
    if not links_end:
        raise ValueError("找不到 links 陣列結尾（]; before const nodeMap）")

    # 生成新的 nodes + links 區塊
    new_nodes = generate_nodes_js(topo["nodes"])
    new_links = generate_links_js(topo["links"])
    new_block = new_nodes + "\n\n" + new_links + "\n"

    # 替換
    result = html[:nodes_start.start()] + new_block + html[links_end.start() + 2:]
    # links_end.start() + 2 跳過 ]; 本身

    # 更新 SYNC_META
    result = re.sub(
        r"topologyVersion:\s*'[^']*'",
        f"topologyVersion: '{topo['version']}'",
        result,
    )
    result = re.sub(
        r"syncDate:\s*'[^']*'",
        f"syncDate: '{date.today().isoformat()}'",
        result,
    )

    return result


# ═══════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════

def main():
    apply = "--apply" in sys.argv
    as_json = "--json" in sys.argv

    if not TOPOLOGY_PATH.exists():
        print(f"❌ 拓撲文件不存在：{TOPOLOGY_PATH}")
        sys.exit(1)
    if not HTML_PATH.exists():
        print(f"❌ HTML 不存在：{HTML_PATH}")
        sys.exit(1)

    # 解析拓撲
    topo_text = TOPOLOGY_PATH.read_text(encoding="utf-8")
    topo = parse_topology(topo_text)

    # 解析 HTML 現狀
    html_text = HTML_PATH.read_text(encoding="utf-8")
    html_nodes = _parse_html_nodes(html_text)
    html_links = _parse_html_links(html_text)

    # 差異報告
    diff = diff_report(topo, html_nodes, html_links)

    if as_json and not apply:
        print(json.dumps(diff, ensure_ascii=False, indent=2, default=list))
        return

    # 輸出報告
    print(f"""
{'═' * 50}
  MUSEON 拓撲 → 3D 心智圖同步
{'═' * 50}
  拓撲版本：{diff['topo_version']}
  拓撲：{diff['topo_nodes']} 節點 / {diff['topo_links']} 連線
  HTML：{diff['html_nodes']} 節點 / {diff['html_links']} 連線
{'─' * 50}""")

    has_diff = False

    if diff["nodes_added"]:
        has_diff = True
        print(f"\n  🟢 需新增節點（{len(diff['nodes_added'])} 個）：")
        for nid in diff["nodes_added"]:
            print(f"     + {nid}")

    if diff["nodes_removed"]:
        has_diff = True
        print(f"\n  🔴 需刪除節點（{len(diff['nodes_removed'])} 個）：")
        for nid in diff["nodes_removed"]:
            print(f"     - {nid}")

    if diff["links_added"]:
        has_diff = True
        print(f"\n  🟢 需新增連線（{len(diff['links_added'])} 條）：")
        for s, t in diff["links_added"][:20]:
            print(f"     + {s} → {t}")
        if len(diff["links_added"]) > 20:
            print(f"     ... 還有 {len(diff['links_added']) - 20} 條")

    if diff["links_removed"]:
        has_diff = True
        print(f"\n  🔴 需刪除連線（{len(diff['links_removed'])} 條）：")
        for s, t in diff["links_removed"][:20]:
            print(f"     - {s} → {t}")
        if len(diff["links_removed"]) > 20:
            print(f"     ... 還有 {len(diff['links_removed']) - 20} 條")

    if not has_diff:
        print("\n  ✅ 完全同步！無任何差異。")

    print(f"\n{'═' * 50}")

    if not apply:
        if has_diff:
            print("  💡 這是 dry-run 模式。加 --apply 套用變更。")
        return

    # 套用
    print("  🔧 正在全量重生成 nodes/links...")
    new_html = sync_html(topo, html_text)
    HTML_PATH.write_text(new_html, encoding="utf-8")
    print(f"  ✅ 已更新 {HTML_PATH.name}")
    print(f"     版本：{topo['version']} / 日期：{date.today().isoformat()}")
    print(f"     節點：{len(topo['nodes'])} / 連線：{len(topo['links'])}")
    print(f"\n  ⚠️  請在瀏覽器重新整理頁面以查看變更。")
    print()


if __name__ == "__main__":
    main()
