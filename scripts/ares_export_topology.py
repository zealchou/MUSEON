#!/usr/bin/env python3
"""Ares Topology Exporter — 輸出人物拓樸圖 JSON 供 Mini App 使用.

Usage:
    python scripts/ares_export_topology.py [--domain business|internal|personal]
    python scripts/ares_export_topology.py --png output.png

輸出到 data/ares/mini-app/topology.json
"""

import argparse
import json
import sys
from pathlib import Path

MUSEON_ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description="Export Ares people topology")
    parser.add_argument("--domain", choices=["business", "internal", "personal"], default=None)
    parser.add_argument("--png", type=str, default=None, help="Output PNG path")
    parser.add_argument("--json-out", type=str, default=None, help="Output JSON path")
    args = parser.parse_args()

    sys.path.insert(0, str(MUSEON_ROOT / "src"))
    from museon.ares.profile_store import ProfileStore

    store = ProfileStore(MUSEON_ROOT / "data")
    data = store.generate_topology_data(domain=args.domain)

    if args.png:
        from museon.ares.graph_renderer import render_topology_png
        render_topology_png(data, output_path=args.png, owner_name="Zeal")
        print(f"PNG saved: {args.png}")
    else:
        out_path = Path(args.json_out) if args.json_out else MUSEON_ROOT / "data" / "ares" / "mini-app" / "topology.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON saved: {out_path} ({len(data['nodes'])} nodes, {len(data['links'])} links)")


if __name__ == "__main__":
    main()
