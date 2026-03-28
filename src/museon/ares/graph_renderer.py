"""People Topology Graph Renderer — 人物拓樸圖 PNG 生成.

使用 matplotlib + networkx 生成靜態關係圖 PNG。
設計為輕量級方案（Phase 1），未來 Phase 2 改用 D3.js Mini App。
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 溫度→顏色映射
TEMP_COLORS = {
    "hot": "#e74c3c",
    "warm": "#f39c12",
    "cold": "#3498db",
    "new": "#95a5a6",
}

# 場域→形狀映射（networkx node shape）
DOMAIN_SHAPES = {
    "internal": "s",     # 方形
    "business": "o",     # 圓形
    "personal": "^",     # 三角形
}


def render_topology_png(
    topology_data: dict[str, Any],
    output_path: Path | str | None = None,
    title: str = "我的戰略網路",
    owner_name: str = "我",
    figsize: tuple[int, int] = (14, 10),
) -> bytes | None:
    """將拓樸圖資料渲染為 PNG.

    Args:
        topology_data: ProfileStore.generate_topology_data() 的輸出
        output_path: 輸出路徑，None 則返回 bytes
        title: 圖表標題
        owner_name: 中心節點名稱
        figsize: 圖表尺寸

    Returns:
        PNG bytes（如果 output_path 為 None）
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx
    except ImportError:
        logger.warning("[ARES] matplotlib/networkx not installed, cannot render graph")
        return None

    # 設定中文字體
    plt.rcParams["font.sans-serif"] = ["PingFang TC", "Heiti TC", "Arial Unicode MS", "sans-serif"]
    plt.rcParams["axes.unicode_minus"] = False

    nodes = topology_data.get("nodes", [])
    links = topology_data.get("links", [])

    if not nodes:
        logger.info("[ARES] No nodes to render")
        return None

    G = nx.Graph()

    # 加入「我」節點
    G.add_node("owner", label=owner_name, color="#181737", size=800)

    # 加入人物節點
    for node in nodes:
        nid = node["id"]
        label = node["name"] or nid[:6]
        temp = node.get("temperature", "new")
        color = TEMP_COLORS.get(temp, "#95a5a6")
        wan_miu = node.get("wan_miu_code")
        if wan_miu:
            label = f"{label}\n({wan_miu})"
        G.add_node(nid, label=label, color=color, size=400)
        # 所有人物預設連到「我」
        G.add_edge("owner", nid, weight=3, style="solid")

    # 加入人物間連線
    for link in links:
        src = link["source"]
        tgt = link["target"]
        strength = link.get("strength", 5)
        if G.has_node(src) and G.has_node(tgt):
            G.add_edge(src, tgt, weight=max(1, strength // 2), style="dashed")

    # 佈局
    pos = nx.spring_layout(G, k=2.5, iterations=50, seed=42)

    # 繪製
    fig, ax = plt.subplots(1, 1, figsize=figsize)
    fig.patch.set_facecolor("#f8f6f0")
    ax.set_facecolor("#f8f6f0")

    # 邊
    edges = G.edges(data=True)
    edge_widths = [e[2].get("weight", 1) for e in edges]
    edge_styles = [e[2].get("style", "solid") for e in edges]
    for (u, v, data), width in zip(edges, edge_widths):
        style = data.get("style", "solid")
        nx.draw_networkx_edges(
            G, pos, edgelist=[(u, v)], width=width,
            alpha=0.4, edge_color="#888888", style=style, ax=ax,
        )

    # 節點
    node_colors = [G.nodes[n].get("color", "#95a5a6") for n in G.nodes()]
    node_sizes = [G.nodes[n].get("size", 400) for n in G.nodes()]
    nx.draw_networkx_nodes(
        G, pos, node_color=node_colors, node_size=node_sizes,
        edgecolors="#333333", linewidths=1.5, alpha=0.9, ax=ax,
    )

    # 標籤
    labels = {n: G.nodes[n].get("label", n) for n in G.nodes()}
    nx.draw_networkx_labels(
        G, pos, labels, font_size=9, font_family="sans-serif",
        font_color="#181737", ax=ax,
    )

    # 圖例
    legend_items = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markersize=10, label=l)
        for l, c in [("🔴 熱", "#e74c3c"), ("🟡 溫", "#f39c12"), ("🔵 冷", "#3498db"), ("⚪ 新", "#95a5a6")]
    ]
    ax.legend(handles=legend_items, loc="upper left", framealpha=0.8)

    ax.set_title(title, fontsize=16, fontweight="bold", color="#181737", pad=20)
    ax.axis("off")
    plt.tight_layout()

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="#f8f6f0")
        plt.close(fig)
        logger.info(f"[ARES] Topology PNG saved: {output_path}")
        return None
    else:
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#f8f6f0")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
