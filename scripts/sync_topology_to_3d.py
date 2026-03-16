#!/usr/bin/env python3
"""
sync_topology_to_3d.py — 拓撲同步腳本
從 docs/system-topology.md (SSOT) 解析節點與連線，
與 data/workspace/MUSEON_3d_mindmap.html 中的 JS nodes/links 陣列比對，
報告差異並可選擇性地自動 patch HTML。

用法:
    .venv/bin/python scripts/sync_topology_to_3d.py --dry-run   # 只報告差異
    .venv/bin/python scripts/sync_topology_to_3d.py --apply      # 自動同步
"""

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

# ═══════════════════════════════════════
# 路徑設定
# ═══════════════════════════════════════
ROOT = Path(__file__).resolve().parent.parent
TOPOLOGY_PATH = ROOT / "docs" / "system-topology.md"
HTML_PATH = ROOT / "data" / "workspace" / "MUSEON_3d_mindmap.html"


# ═══════════════════════════════════════
# 解析 system-topology.md
# ═══════════════════════════════════════

def parse_topology_version(text: str) -> str:
    """從標題取得版本號 (e.g. 'v1.8')"""
    m = re.search(r"#\s+MUSEON\s+系統拓撲圖\s+(v[\d.]+)", text)
    return m.group(1) if m else "unknown"


def parse_md_table(lines: list[str]) -> list[dict[str, str]]:
    """解析 markdown 表格，返回 list of dicts"""
    if len(lines) < 2:
        return []
    # 第一行是 header
    headers = [h.strip().strip('`') for h in lines[0].split('|') if h.strip()]
    rows = []
    for line in lines[2:]:  # skip header + separator
        if not line.strip() or not '|' in line:
            break
        cells = [c.strip().strip('`') for c in line.split('|') if c.strip() != '']
        if len(cells) >= len(headers):
            row = {}
            for i, h in enumerate(headers):
                row[h] = cells[i] if i < len(cells) else ''
            rows.append(row)
    return rows


def parse_topology_nodes(text: str) -> dict[str, dict]:
    """解析所有節點表格，返回 {id: {label, zh, group, hub, parent, r}}"""
    nodes = {}
    lines = text.split('\n')
    current_group = None

    for i, line in enumerate(lines):
        # 遇到 ## 二級標題時重置（離開節點清單區域）
        if re.match(r'^##\s+[^#]', line) and not re.match(r'^###', line):
            current_group = None

        # 偵測群組標題: ### group_id — 群組名
        gm = re.match(r'^###\s+(\w[\w-]*)\s+—', line)
        if gm:
            current_group = gm.group(1)
            continue

        # 偵測節點表格行
        if current_group and line.startswith('|') and '`' in line:
            cells = [c.strip() for c in line.split('|')]
            cells = [c for c in cells if c]
            if len(cells) < 4:
                continue
            # 跳過 header 和 separator
            if cells[0].startswith('ID') or cells[0].startswith('--'):
                continue

            node_id = cells[0].strip('`').strip()
            if not node_id or node_id == 'ID':
                continue

            label = cells[1].strip() if len(cells) > 1 else ''
            zh = cells[2].strip() if len(cells) > 2 else ''

            # 根據表格有無 Parent 欄位，欄位位置不同
            hub = False
            parent = None
            radius = 1.0

            if len(cells) >= 6:
                # 有 Parent 欄位: ID | 名稱 | 中文 | Hub | Parent | 半徑
                hub = cells[3].strip().lower() == 'yes'
                parent_val = cells[4].strip()
                if parent_val and parent_val != '-':
                    parent = parent_val
                try:
                    radius = float(cells[5].strip())
                except (ValueError, IndexError):
                    radius = 1.0
            elif len(cells) >= 5:
                # 無 Parent 欄位: ID | 名稱 | 中文 | Hub | 半徑
                hub = cells[3].strip().lower() == 'yes'
                try:
                    radius = float(cells[4].strip())
                except (ValueError, IndexError):
                    radius = 1.0

            nodes[node_id] = {
                'id': node_id,
                'label': label,
                'zh': zh,
                'group': current_group,
                'hub': hub,
                'parent': parent,
                'r': radius,
            }

    return nodes


def parse_topology_links(text: str) -> list[dict]:
    """解析所有連線表格，返回 [{source, target, label, type}]"""
    links = []
    lines = text.split('\n')
    current_type = None

    # 連線類型映射（從標題推斷）
    type_map = {
        '主資料流': 'flow',
        '控制流': 'control',
        'agent 內部': 'internal',
        'pulse 內部': 'internal',
        'governance 內部': 'internal',
        'evolution 內部': 'internal',
        'tools 內部': 'internal',
        'doctor 內部': 'internal',
        'llm 內部': 'internal',
        'data 內部': 'internal',
        'nightly 內部': 'internal',
        'installer 內部': 'internal',
        '跨系統': 'cross',
        '監控': 'monitor',
        '非同步': 'async',
    }

    for i, line in enumerate(lines):
        # 遇到 ## 二級標題時重置（離開連線清單區域）
        if re.match(r'^##\s+[^#]', line) and not re.match(r'^###', line):
            current_type = None

        # 偵測連線類型標題
        hm = re.match(r'^###\s+(.+?)(?:\s*（|$)', line)
        if hm:
            title = hm.group(1).strip()
            for key, ltype in type_map.items():
                if key.lower() in title.lower():
                    current_type = ltype
                    break

        # 偵測連線表格行
        if current_type and line.startswith('|') and '`' in line:
            cells = [c.strip() for c in line.split('|')]
            cells = [c for c in cells if c]
            if len(cells) < 3:
                continue
            if cells[0].startswith('Source') or cells[0].startswith('--'):
                continue

            source = cells[0].strip('`').strip()
            target = cells[1].strip('`').strip()
            label = cells[2].strip() if len(cells) > 2 else ''

            if not source or source == 'Source':
                continue

            links.append({
                'source': source,
                'target': target,
                'label': label,
                'type': current_type,
            })

    return links


# ═══════════════════════════════════════
# 解析 HTML 中的 JS nodes/links 陣列
# ═══════════════════════════════════════

def extract_js_array(html: str, var_name: str) -> str:
    """從 HTML 中提取 JS 陣列的原始文字（含 [ ... ]）"""
    # 找到 const nodes = [ 或 const links = [
    pattern = rf'const\s+{var_name}\s*=\s*\['
    m = re.search(pattern, html)
    if not m:
        return ''

    start = m.start()
    # 找到對應的 ];
    bracket_count = 0
    pos = m.end() - 1  # 指向 [
    for j in range(pos, len(html)):
        if html[j] == '[':
            bracket_count += 1
        elif html[j] == ']':
            bracket_count -= 1
            if bracket_count == 0:
                return html[pos:j + 1]
    return ''


def parse_js_nodes(js_text: str) -> dict[str, dict]:
    """解析 JS nodes 陣列文字，返回 {id: {label, zh, group, hub, parent, r}}"""
    nodes = {}
    # 用正則匹配每個 {…} 物件
    pattern = re.compile(r'\{([^}]+)\}')
    for m in pattern.finditer(js_text):
        obj_str = m.group(1)

        # (?<!\w) 確保 key 前不是字母，避免 group: 中的 p 被匹配
        def get_val(key):
            km = re.search(rf'(?<!\w){key}\s*:\s*"([^"]*)"', obj_str)
            if not km:
                km = re.search(rf"(?<!\w){key}\s*:\s*'([^']*)'", obj_str)
            return km.group(1) if km else None

        def get_num(key):
            km = re.search(rf'(?<!\w){key}\s*:\s*([\d.]+)', obj_str)
            return float(km.group(1)) if km else None

        def get_bool(key):
            km = re.search(rf'(?<!\w){key}\s*:\s*(\d)', obj_str)
            return km.group(1) == '1' if km else False

        node_id = get_val('id')
        if not node_id:
            continue

        nodes[node_id] = {
            'id': node_id,
            'label': get_val('label') or '',
            'zh': get_val('zh') or '',
            'group': get_val('group') or '',
            'hub': get_bool('hub'),
            'parent': get_val('p'),
            'r': get_num('r') or 1.0,
        }

    return nodes


def parse_js_links(js_text: str) -> list[dict]:
    """解析 JS links 陣列文字，返回 [{source, target, label, type}]"""
    links = []
    pattern = re.compile(r'\{([^}]+)\}')
    for m in pattern.finditer(js_text):
        obj_str = m.group(1)

        def get_val(key):
            km = re.search(rf'(?<!\w){key}\s*:\s*"([^"]*)"', obj_str)
            if not km:
                km = re.search(rf"(?<!\w){key}\s*:\s*'([^']*)'", obj_str)
            return km.group(1) if km else None

        source = get_val('source')
        target = get_val('target')
        if not source or not target:
            continue

        links.append({
            'source': source,
            'target': target,
            'label': get_val('label') or '',
            'type': get_val('type') or 'internal',
        })

    return links


# ═══════════════════════════════════════
# 比對差異
# ═══════════════════════════════════════

def compare_nodes(
    topo_nodes: dict[str, dict],
    html_nodes: dict[str, dict],
) -> dict[str, list]:
    """比對節點差異"""
    diffs = {
        'added': [],      # topology 有、HTML 無 → 需新增
        'removed': [],     # HTML 有、topology 無 → 需刪除
        'changed': [],     # 兩邊都有但屬性不同
    }

    topo_ids = set(topo_nodes.keys())
    html_ids = set(html_nodes.keys())

    # 新增（topology 有，HTML 無）
    for nid in sorted(topo_ids - html_ids):
        diffs['added'].append(topo_nodes[nid])

    # 刪除（HTML 有，topology 無）
    for nid in sorted(html_ids - topo_ids):
        diffs['removed'].append(html_nodes[nid])

    # 屬性變更
    for nid in sorted(topo_ids & html_ids):
        tn = topo_nodes[nid]
        hn = html_nodes[nid]
        changes = []

        for key in ['label', 'zh', 'group', 'hub', 'r']:
            tv = tn.get(key)
            hv = hn.get(key)
            # r 用近似比較
            if key == 'r' and tv is not None and hv is not None:
                if abs(float(tv) - float(hv)) > 0.05:
                    changes.append((key, hv, tv))
            elif tv != hv:
                changes.append((key, hv, tv))

        # parent 特殊比較（topology 用完整 parent，HTML 用 p）
        tp = tn.get('parent')
        hp = hn.get('parent')
        if tp != hp:
            changes.append(('parent', hp, tp))

        if changes:
            diffs['changed'].append({
                'id': nid,
                'changes': changes,
            })

    return diffs


def compare_links(
    topo_links: list[dict],
    html_links: list[dict],
) -> dict[str, list]:
    """比對連線差異"""
    diffs = {
        'added': [],
        'removed': [],
        'type_changed': [],
    }

    def link_key(l):
        return (l['source'], l['target'], l.get('label', ''))

    def link_key_no_label(l):
        return (l['source'], l['target'])

    topo_set = {}
    for l in topo_links:
        k = link_key_no_label(l)
        if k not in topo_set:
            topo_set[k] = l

    html_set = {}
    for l in html_links:
        k = link_key_no_label(l)
        if k not in html_set:
            html_set[k] = l

    topo_keys = set(topo_set.keys())
    html_keys = set(html_set.keys())

    for k in sorted(topo_keys - html_keys):
        diffs['added'].append(topo_set[k])

    for k in sorted(html_keys - topo_keys):
        diffs['removed'].append(html_set[k])

    for k in sorted(topo_keys & html_keys):
        tl = topo_set[k]
        hl = html_set[k]
        if tl['type'] != hl['type']:
            diffs['type_changed'].append({
                'source': k[0],
                'target': k[1],
                'html_type': hl['type'],
                'topo_type': tl['type'],
            })

    return diffs


# ═══════════════════════════════════════
# 報告輸出
# ═══════════════════════════════════════

def print_report(
    node_diffs: dict,
    link_diffs: dict,
    topo_version: str,
    topo_node_count: int,
    topo_link_count: int,
    html_node_count: int,
    html_link_count: int,
):
    """輸出格式化的差異報告"""
    print("=" * 60)
    print("  MUSEON 拓撲同步報告")
    print("=" * 60)
    print(f"  拓撲版本：{topo_version}")
    print(f"  拓撲節點：{topo_node_count} | HTML 節點：{html_node_count}")
    print(f"  拓撲連線：{topo_link_count} | HTML 連線：{html_link_count}")
    print("=" * 60)

    has_diff = False

    # 節點差異
    if node_diffs['added']:
        has_diff = True
        print(f"\n🟢 需新增的節點（{len(node_diffs['added'])} 個）:")
        for n in node_diffs['added']:
            print(f"   + {n['id']} ({n['zh']}) [{n['group']}] r={n['r']}")

    if node_diffs['removed']:
        has_diff = True
        print(f"\n🔴 需刪除的節點（{len(node_diffs['removed'])} 個）:")
        for n in node_diffs['removed']:
            print(f"   - {n['id']} ({n['zh']}) [{n['group']}]")

    if node_diffs['changed']:
        has_diff = True
        print(f"\n🟡 屬性變更的節點（{len(node_diffs['changed'])} 個）:")
        for item in node_diffs['changed']:
            print(f"   ~ {item['id']}:")
            for key, old_val, new_val in item['changes']:
                print(f"     {key}: {old_val!r} → {new_val!r}")

    # 連線差異
    if link_diffs['added']:
        has_diff = True
        print(f"\n🟢 需新增的連線（{len(link_diffs['added'])} 條）:")
        for l in link_diffs['added']:
            print(f"   + {l['source']} → {l['target']} [{l['type']}] {l['label']}")

    if link_diffs['removed']:
        has_diff = True
        print(f"\n🔴 需刪除的連線（{len(link_diffs['removed'])} 條）:")
        for l in link_diffs['removed']:
            print(f"   - {l['source']} → {l['target']} [{l['type']}] {l['label']}")

    if link_diffs['type_changed']:
        has_diff = True
        print(f"\n🟡 類型變更的連線（{len(link_diffs['type_changed'])} 條）:")
        for l in link_diffs['type_changed']:
            print(f"   ~ {l['source']} → {l['target']}: {l['html_type']} → {l['topo_type']}")

    if not has_diff:
        print("\n✅ 完全同步！無任何差異。")

    print()
    return has_diff


# ═══════════════════════════════════════
# 自動 Patch HTML
# ═══════════════════════════════════════

def generate_node_js(node: dict) -> str:
    """生成單一節點的 JS 物件字串"""
    parts = [
        f'id:"{node["id"]}"',
        f'label:"{node["label"]}"',
        f'zh:"{node["zh"]}"',
        f'group:"{node["group"]}"',
    ]
    if node.get('parent'):
        parts.append(f'p:"{node["parent"]}"')
    if node.get('hub'):
        parts.append('hub:1')
    parts.append(f'r:{node["r"]}')
    return '  {' + ','.join(parts) + '}'


def generate_link_js(link: dict) -> str:
    """生成單一連線的 JS 物件字串"""
    return (
        f'  {{source:"{link["source"]}",'
        f'target:"{link["target"]}",'
        f'label:"{link["label"]}",'
        f'type:"{link["type"]}"}}'
    )


def patch_html(
    html: str,
    node_diffs: dict,
    link_diffs: dict,
    topo_nodes: dict,
    topo_version: str,
) -> str:
    """根據差異 patch HTML 內容"""
    patched = html

    # ── 1. 更新 SYNC_META ──
    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    topo_node_count = len(topo_nodes)

    patched = re.sub(
        r"topologyVersion:\s*'[^']*'",
        f"topologyVersion: '{topo_version}'",
        patched,
    )
    patched = re.sub(
        r"syncDate:\s*'[^']*'",
        f"syncDate: '{now_str}'",
        patched,
    )

    # ── 2. Patch 節點 ──
    # 2a. 刪除節點
    for n in node_diffs['removed']:
        # 移除匹配行（包含前後的註解行如果相鄰）
        pattern = rf'\n\s*\{{[^}}]*id:"{re.escape(n["id"])}"[^}}]*\}},?'
        patched = re.sub(pattern, '', patched)

    # 2b. 更新節點屬性
    for item in node_diffs['changed']:
        nid = item['id']
        tn = topo_nodes[nid]
        new_js = generate_node_js(tn)
        # 找到舊的節點行並替換
        pattern = rf'(\s*)\{{[^}}]*id:"{re.escape(nid)}"[^}}]*\}}'
        m = re.search(pattern, patched)
        if m:
            patched = patched[:m.start()] + '\n' + new_js + patched[m.end():]

    # 2c. 新增節點（加在 nodes 陣列的末尾 ]; 之前）
    if node_diffs['added']:
        new_lines = []
        for n in node_diffs['added']:
            new_lines.append(generate_node_js(n) + ',')

        # 找到 nodes 陣列的結尾
        # 搜尋 "]; 附近" 且位於 const links 之前
        nodes_end = re.search(r'(\n\];)\s*\n\s*const\s+links', patched)
        if nodes_end:
            insert_pos = nodes_end.start()
            comment = f'\n  // ═══ 同步新增 ({now_str}) ═══\n'
            insert_text = comment + '\n'.join(new_lines)
            patched = patched[:insert_pos] + insert_text + patched[insert_pos:]

    # ── 3. Patch 連線 ──
    # 3a. 刪除連線
    for l in link_diffs['removed']:
        pattern = (
            rf'\n\s*\{{[^}}]*source:"{re.escape(l["source"])}"'
            rf'[^}}]*target:"{re.escape(l["target"])}"[^}}]*\}},?'
        )
        patched = re.sub(pattern, '', patched, count=1)

    # 3b. 新增連線
    if link_diffs['added']:
        new_lines = []
        for l in link_diffs['added']:
            new_lines.append(generate_link_js(l) + ',')

        # 找到 links 陣列的結尾
        links_end = re.search(r'(\n\];)\s*\n\s*const\s+nodeMap', patched)
        if links_end:
            insert_pos = links_end.start()
            comment = f'\n  // ═══ 同步新增 ({now_str}) ═══\n'
            insert_text = comment + '\n'.join(new_lines)
            patched = patched[:insert_pos] + insert_text + patched[insert_pos:]

    # 3c. 更新連線類型
    for l in link_diffs['type_changed']:
        pattern = (
            rf'(\{{[^}}]*source:"{re.escape(l["source"])}"'
            rf'[^}}]*target:"{re.escape(l["target"])}"'
            rf'[^}}]*)type:"{re.escape(l["html_type"])}"'
        )
        replacement = rf'\1type:"{l["topo_type"]}"'
        patched = re.sub(pattern, replacement, patched, count=1)

    return patched


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='MUSEON 拓撲同步腳本')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help='只報告差異，不修改')
    group.add_argument('--apply', action='store_true', help='自動同步 patch HTML')
    args = parser.parse_args()

    # 檢查檔案存在
    if not TOPOLOGY_PATH.exists():
        print(f"❌ 找不到拓撲文件：{TOPOLOGY_PATH}")
        sys.exit(1)
    if not HTML_PATH.exists():
        print(f"❌ 找不到 HTML 文件：{HTML_PATH}")
        sys.exit(1)

    # 讀取文件
    topo_text = TOPOLOGY_PATH.read_text(encoding='utf-8')
    html_text = HTML_PATH.read_text(encoding='utf-8')

    # 解析 topology
    topo_version = parse_topology_version(topo_text)
    topo_nodes = parse_topology_nodes(topo_text)
    topo_links = parse_topology_links(topo_text)

    # 解析 HTML
    nodes_js = extract_js_array(html_text, 'nodes')
    links_js = extract_js_array(html_text, 'links')
    html_nodes = parse_js_nodes(nodes_js)
    html_links = parse_js_links(links_js)

    print(f"📖 解析拓撲文件：{len(topo_nodes)} 節點, {len(topo_links)} 連線 ({topo_version})")
    print(f"📖 解析 HTML 文件：{len(html_nodes)} 節點, {len(html_links)} 連線")
    print()

    # 比對
    node_diffs = compare_nodes(topo_nodes, html_nodes)
    link_diffs = compare_links(topo_links, html_links)

    # 報告
    has_diff = print_report(
        node_diffs, link_diffs,
        topo_version,
        len(topo_nodes), len(topo_links),
        len(html_nodes), len(html_links),
    )

    if not has_diff:
        print("🎉 無需同步。")
        return

    if args.dry_run:
        print("💡 這是 --dry-run 模式，未修改任何檔案。")
        print("   使用 --apply 來自動同步。")
        return

    # Apply mode
    print("🔧 正在 patch HTML...")
    patched = patch_html(html_text, node_diffs, link_diffs, topo_nodes, topo_version)

    # 寫回
    HTML_PATH.write_text(patched, encoding='utf-8')
    print(f"✅ 已更新 {HTML_PATH}")
    print(f"   SYNC_META → {topo_version} / {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    print()
    print("⚠️  請在瀏覽器重新整理頁面以查看變更。")
    print("⚠️  建議再跑一次 --dry-run 確認無殘餘差異。")


if __name__ == '__main__':
    main()
