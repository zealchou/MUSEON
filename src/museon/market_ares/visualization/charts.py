"""Market Ares — 圖表元件

生成 ECharts 圖表的 JSON 配置，嵌入 HTML 儀表板。
"""

from __future__ import annotations

import json


def radar_chart_option(
    inner: dict[str, float],
    outer: dict[str, float],
    title: str = "八方位能量雷達圖",
) -> dict:
    """八方位雷達圖 ECharts 配置"""
    primals = ["天", "風", "水", "山", "地", "雷", "火", "澤"]

    return {
        "title": {"text": title, "textStyle": {"color": "#FDFCFA", "fontSize": 14}},
        "tooltip": {},
        "radar": {
            "indicator": [{"name": p, "max": 4, "min": -4} for p in primals],
            "shape": "polygon",
            "axisLine": {"lineStyle": {"color": "rgba(255,255,255,0.1)"}},
            "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.05)"}},
            "splitArea": {"areaStyle": {"color": ["rgba(255,255,255,0.02)", "rgba(255,255,255,0.04)"]}},
        },
        "series": [{
            "type": "radar",
            "data": [
                {
                    "value": [inner.get(p, 0) for p in primals],
                    "name": "內在",
                    "lineStyle": {"color": "#C4502A"},
                    "areaStyle": {"color": "rgba(196,80,42,0.2)"},
                    "itemStyle": {"color": "#C4502A"},
                },
                {
                    "value": [outer.get(p, 0) for p in primals],
                    "name": "外在",
                    "lineStyle": {"color": "#2A7A6E"},
                    "areaStyle": {"color": "rgba(42,122,110,0.2)"},
                    "itemStyle": {"color": "#2A7A6E"},
                },
            ],
        }],
    }


def line_chart_option(
    weeks: list[int],
    series_data: dict[str, list[float]],
    title: str = "52 週趨勢",
    y_label: str = "",
) -> dict:
    """多系列折線圖"""
    colors = ["#C4502A", "#2A7A6E", "#B8923A", "#2A6A8A", "#C9943A", "#5A5A6E"]
    series = []

    for i, (name, data) in enumerate(series_data.items()):
        series.append({
            "name": name,
            "type": "line",
            "data": data,
            "smooth": True,
            "lineStyle": {"width": 2},
            "itemStyle": {"color": colors[i % len(colors)]},
        })

    return {
        "title": {"text": title, "textStyle": {"color": "#FDFCFA", "fontSize": 14}},
        "tooltip": {"trigger": "axis"},
        "legend": {"data": list(series_data.keys()), "textStyle": {"color": "#9898A8"}},
        "grid": {"left": 60, "right": 20, "top": 60, "bottom": 30},
        "xAxis": {
            "type": "category",
            "data": [f"W{w}" for w in weeks],
            "axisLine": {"lineStyle": {"color": "#2A2A38"}},
            "axisLabel": {"color": "#9898A8"},
        },
        "yAxis": {
            "type": "value",
            "name": y_label,
            "axisLine": {"lineStyle": {"color": "#2A2A38"}},
            "axisLabel": {"color": "#9898A8"},
            "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.04)"}},
        },
        "series": series,
    }


def sankey_chart_option(
    links: list[dict],
    title: str = "原型狀態遷移",
) -> dict:
    """Sankey 流向圖"""
    nodes_set = set()
    for link in links:
        nodes_set.add(link["source"])
        nodes_set.add(link["target"])

    return {
        "title": {"text": title, "textStyle": {"color": "#FDFCFA", "fontSize": 14}},
        "tooltip": {"trigger": "item"},
        "series": [{
            "type": "sankey",
            "layout": "none",
            "emphasis": {"focus": "adjacency"},
            "data": [{"name": n} for n in sorted(nodes_set)],
            "links": links,
            "lineStyle": {"color": "gradient", "curveness": 0.5},
            "itemStyle": {"borderWidth": 0},
            "label": {"color": "#FDFCFA"},
        }],
    }


def pie_chart_option(
    data: dict[str, float],
    title: str = "狀態分布",
) -> dict:
    """圓餅圖"""
    colors = {
        "unaware": "#5A5A6E",
        "aware": "#2A6A8A",
        "considering": "#B8923A",
        "decided": "#2A7A6E",
        "loyal": "#C4502A",
        "resistant": "#C4402A",
    }

    return {
        "title": {"text": title, "textStyle": {"color": "#FDFCFA", "fontSize": 14}},
        "tooltip": {"trigger": "item"},
        "series": [{
            "type": "pie",
            "radius": ["40%", "70%"],
            "data": [
                {"value": round(v * 100, 1), "name": k,
                 "itemStyle": {"color": colors.get(k, "#5A5A6E")}}
                for k, v in data.items() if v > 0.001
            ],
            "label": {"color": "#FDFCFA", "fontSize": 12},
        }],
    }
