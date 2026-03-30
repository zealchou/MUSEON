"""
report_generator.py — DARWIN 策略演化模擬｜麥肯錫等級策略顧問報告產生器 v2.0

產出 self-contained 單頁 HTML 報告，12 頁等級策略顧問報告：
- Page 1: 封面
- Page 2: 策略診斷摘要（Executive Summary）
- Page 3-4: 市場能量地景
- Page 5-6: 52 週戰場回放
- Page 7: SWOT 分析
- Page 8: Porter 五力分析
- Page 9: 4P 行銷建議
- Page 10-11: 分階段行動計畫
- Page 12: 風險矩陣

公開 API：
    generate_report(simulation_result, insights=None, output_path=None) -> str
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any


# ──────────────────────────────────────────────────────────────
# 品牌色彩（MUSEON design_spec.md）
# ──────────────────────────────────────────────────────────────

COLORS = {
    # 品牌主色
    "ember": "#C4502A",
    "ember_light": "#E0714D",
    "ember_dark": "#9A3A1C",
    # 輔助色
    "teal": "#2A7A6E",
    "gold": "#B8923A",
    # 中性色（亮色模式）
    "ink": "#12121A",
    "slate": "#5A5A6E",
    "mist": "#9898A8",
    "border": "#E2E0DA",
    "parchment": "#F7F5F0",
    "snow": "#FDFCFA",
    # 深色模式
    "deep_ink": "#0E0E16",
    "surface": "#16161F",
    "raised": "#1E1E2A",
    "border_dark": "#2A2A38",
    # 語義色
    "success": "#2D8A6E",
    "warning": "#C9943A",
    "error": "#C4402A",
    "info": "#2A6A8A",
    # 卡片背景（深色）
    "card_dark": "#1A1A2E",
}

# 八方位中文名稱
PRIMALS_ZH = ["天", "風", "水", "山", "地", "雷", "火", "澤"]

# 採用曲線五階段
STAGE_COLORS = {
    "unaware": "#5A5A6E",
    "aware": "#2A6A8A",
    "considering": "#C9943A",
    "decided": "#2D8A6E",
    "loyal": "#B8923A",
    "resistant": "#C4402A",
}

STAGE_LABELS_ZH = {
    "unaware": "未意識",
    "aware": "已意識",
    "considering": "考慮中",
    "decided": "已決定",
    "loyal": "忠實客戶",
    "resistant": "抵抗者",
}

# 指標格式化
INDICATOR_META = {
    "population_density":  ("人口密度",     lambda v: f"{v:,.0f} 人/km²"),
    "household_income":    ("家戶所得中位",  lambda v: f"{v:,.0f} 千元"),
    "cafe_density":        ("咖啡廳密度",   lambda v: f"{v:.2f}（飽和度）"),
    "gym_density":         ("健身房密度",   lambda v: f"{v:.2f}（飽和度）"),
    "birth_rate":          ("出生率",       lambda v: f"{v:.1f} ‰"),
    "marriage_rate":       ("結婚率",       lambda v: f"{v:.1f} ‰"),
    "divorce_rate":        ("離婚率",       lambda v: f"{v:.1f} ‰"),
    "household_size":      ("平均戶量",     lambda v: f"{v:.2f} 人/戶"),
    "elderly_ratio":       ("老年比例",     lambda v: f"{v:.1f}%"),
    "young_ratio":         ("青年比例",     lambda v: f"{v:.1f}%"),
    "employment_rate":     ("就業率",       lambda v: f"{v:.1f}%"),
    "college_ratio":       ("大學以上比例", lambda v: f"{v:.1f}%"),
    "tax_revenue":         ("稅收",         lambda v: f"{v:,.0f} 千元"),
    "land_price":          ("地價",         lambda v: f"{v:,.0f} 元/m²"),
    "crime_rate":          ("犯罪率",       lambda v: f"{v:.2f}"),
}

# Verdict 顏色映射
VERDICT_COLORS = {
    "穩健": "#2D8A6E",
    "強勁": "#B8923A",
    "待觀察": "#C9943A",
    "高風險": "#C4402A",
    "爆發": "#C4502A",
}


# ──────────────────────────────────────────────────────────────
# SVG 工具函數
# ──────────────────────────────────────────────────────────────

def _radar_point(angle_deg: float, value: float, cx: float, cy: float, r_max: float, v_min: float = -4.0, v_max: float = 4.0) -> tuple[float, float]:
    """能量值轉換為 SVG 坐標，-4~+4 → 0~r_max。"""
    ratio = (value - v_min) / (v_max - v_min)
    r = ratio * r_max
    angle_rad = math.radians(angle_deg - 90)
    x = cx + r * math.cos(angle_rad)
    y = cy + r * math.sin(angle_rad)
    return x, y


def _build_radar_svg_large(inner: dict[str, float], outer: dict[str, float]) -> str:
    """產出升級版八方位能量雷達圖 SVG（400×400）。"""
    W, H = 400, 400
    cx, cy = W / 2, H / 2
    r_max = 150
    n = 8
    angle_step = 360 / n

    # 背景同心圓 -4, -2, 0, +2, +4
    circles = ""
    level_values = [-4, -2, 0, 2, 4]
    for lv in level_values:
        ratio = (lv - (-4)) / (4 - (-4))
        r = ratio * r_max
        if r < 2:
            r = 2
        is_zero = (lv == 0)
        stroke_color = COLORS["ember_dark"] if is_zero else COLORS["border_dark"]
        stroke_width = "1.2" if is_zero else "0.6"
        dash = ' stroke-dasharray="4,3"' if is_zero else ""
        opacity = "0.8" if is_zero else "0.4"
        circles += f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" stroke="{stroke_color}" stroke-width="{stroke_width}"{dash} opacity="{opacity}"/>\n'
        # 刻度標籤
        label_x = cx + 5
        label_y = cy - r - 4
        circles += f'<text x="{label_x:.1f}" y="{label_y:.1f}" font-size="9" fill="{COLORS["mist"]}" font-family="IBM Plex Mono, monospace" opacity="0.6">{lv:+d}</text>\n'

    # 軸線與標籤
    axes = ""
    labels = ""
    label_r = r_max + 22
    for i, primal in enumerate(PRIMALS_ZH):
        angle = i * angle_step
        angle_rad = math.radians(angle - 90)
        x_end = cx + r_max * math.cos(angle_rad)
        y_end = cy + r_max * math.sin(angle_rad)
        axes += f'<line x1="{cx}" y1="{cy}" x2="{x_end:.1f}" y2="{y_end:.1f}" stroke="{COLORS["border_dark"]}" stroke-width="0.8" opacity="0.5"/>\n'

        lx = cx + label_r * math.cos(angle_rad)
        ly = cy + label_r * math.sin(angle_rad)

        iv = inner.get(primal, 0.0)
        ov = outer.get(primal, 0.0)
        labels += f'''<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="14" font-weight="600" fill="white" font-family="Noto Sans TC, system-ui">{primal}</text>
<text x="{lx:.1f}" y="{ly + 16:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="9" fill="{COLORS["mist"]}" font-family="IBM Plex Mono, monospace">{iv:+.1f}/{ov:+.1f}</text>\n'''

    # 內外多邊形
    inner_pts = []
    outer_pts = []
    for i, primal in enumerate(PRIMALS_ZH):
        angle = i * angle_step
        iv = inner.get(primal, 0.0)
        ov = outer.get(primal, 0.0)
        ix, iy = _radar_point(angle, iv, cx, cy, r_max)
        ox, oy = _radar_point(angle, ov, cx, cy, r_max)
        inner_pts.append((ix, iy))
        outer_pts.append((ox, oy))

    def pts_to_polygon(pts):
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    inner_color = COLORS["gold"]
    outer_color = "#4A90D9"

    inner_poly = f'<polygon points="{pts_to_polygon(inner_pts)}" fill="{inner_color}" fill-opacity="0.18" stroke="{inner_color}" stroke-width="2.2"/>\n'
    outer_poly = f'<polygon points="{pts_to_polygon(outer_pts)}" fill="{outer_color}" fill-opacity="0.12" stroke="{outer_color}" stroke-width="2.2" stroke-dasharray="5,3"/>\n'

    dots = ""
    for ix, iy in inner_pts:
        dots += f'<circle cx="{ix:.1f}" cy="{iy:.1f}" r="4" fill="{inner_color}" stroke="{COLORS["deep_ink"]}" stroke-width="1.5"/>\n'
    for ox, oy in outer_pts:
        dots += f'<circle cx="{ox:.1f}" cy="{oy:.1f}" r="4" fill="{outer_color}" stroke="{COLORS["deep_ink"]}" stroke-width="1.5"/>\n'

    legend = f'''
<g transform="translate(20, {H - 28})">
  <circle cx="6" cy="4" r="5" fill="{inner_color}" fill-opacity="0.8"/>
  <text x="16" y="8" font-size="10" fill="{COLORS["mist"]}" font-family="Noto Sans TC, system-ui">內在能量</text>
  <circle cx="80" cy="4" r="5" fill="{outer_color}" fill-opacity="0.8"/>
  <text x="90" y="8" font-size="10" fill="{COLORS["mist"]}" font-family="Noto Sans TC, system-ui">外在能量</text>
</g>'''

    svg = f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{W}" height="{H}" fill="{COLORS["surface"]}" rx="12"/>
  {circles}
  {axes}
  {outer_poly}
  {inner_poly}
  {dots}
  {labels}
  {legend}
</svg>'''
    return svg


def _build_s_curve_svg(snapshots: list[Any], critical_weeks: list[dict] | None = None) -> str:
    """產出升級版 S 曲線 SVG（800×300），含關鍵轉折點標記。"""
    W, H = 800, 300
    pad_left, pad_right, pad_top, pad_bottom = 52, 32, 28, 48

    chart_w = W - pad_left - pad_right
    chart_h = H - pad_top - pad_bottom

    stages_to_show = ["aware", "considering", "decided", "loyal", "resistant"]
    stage_display = {
        "aware": ("認知（aware+considering）", COLORS["info"]),
        "considering": ("觀望中", COLORS["warning"]),
        "decided": ("採用（decided+loyal）", COLORS["success"]),
        "loyal": ("忠實客戶", COLORS["gold"]),
        "resistant": ("抵抗者", COLORS["error"]),
    }

    week_data: dict[str, list[float]] = {s: [] for s in stages_to_show}
    weeks_count = len(snapshots) if snapshots else 52

    if snapshots:
        for snap in snapshots:
            if hasattr(snap, "business_metrics"):
                dist = snap.business_metrics.get("state_distribution", {})
            elif isinstance(snap, dict):
                dist = snap.get("business_metrics", {}).get("state_distribution", {})
            else:
                dist = {}
            for stage in stages_to_show:
                week_data[stage].append(dist.get(stage, 0.0) * 100)
    else:
        for w in range(52):
            t = w / 51
            week_data["aware"].append(min(40, 40 * min(1, t * 2)))
            week_data["considering"].append(min(25, 25 * max(0, t - 0.1) * 3) if t < 0.5 else max(8, 25 - 17 * (t - 0.5) * 4))
            week_data["decided"].append(min(20, 20 * max(0, t - 0.2) * 4) if t < 0.6 else max(5, 20 - 15 * (t - 0.6) * 5))
            week_data["loyal"].append(min(40, 40 * max(0, t - 0.3) * 2))
            week_data["resistant"].append(min(5, 5 * max(0, t - 0.3) * 3))

    def w2x(w: int) -> float:
        return pad_left + (w / max(weeks_count - 1, 1)) * chart_w

    def v2y(v: float) -> float:
        return pad_top + chart_h - (v / 100) * chart_h

    bg = f'<rect width="{W}" height="{H}" fill="{COLORS["surface"]}" rx="12"/>\n'

    # 鴻溝區域（15-35% 採用率）
    y_chasm_top = v2y(35)
    y_chasm_bot = v2y(15)
    chasm_zone = (
        f'<rect x="{pad_left}" y="{y_chasm_top:.1f}" width="{chart_w}" height="{y_chasm_bot - y_chasm_top:.1f}" '
        f'fill="{COLORS["ember"]}" fill-opacity="0.07" rx="2"/>\n'
        f'<text x="{pad_left + 8}" y="{(y_chasm_top + y_chasm_bot)/2:.1f}" '
        f'dominant-baseline="middle" font-size="10" fill="{COLORS["ember"]}" '
        f'font-family="IBM Plex Mono, monospace" opacity="0.8">CHASM ZONE</text>\n'
    )

    # Y 軸格線每 20%
    grid = ""
    for pct in [0, 20, 40, 60, 80, 100]:
        y = v2y(pct)
        grid += (f'<line x1="{pad_left}" y1="{y:.1f}" x2="{pad_left + chart_w}" y2="{y:.1f}" '
                 f'stroke="{COLORS["border_dark"]}" stroke-width="0.5" opacity="0.6"/>\n')
        grid += (f'<text x="{pad_left - 6}" y="{y:.1f}" text-anchor="end" dominant-baseline="middle" '
                 f'font-size="10" fill="{COLORS["mist"]}" font-family="IBM Plex Mono, monospace">{pct}%</text>\n')

    # X 軸每 13 週
    x_axis = ""
    quarter_labels = ["Q1", "Q2", "Q3", "Q4", ""]
    for qi, w in enumerate([0, 13, 26, 39, 52]):
        if w >= weeks_count:
            w = weeks_count - 1
        x = w2x(w)
        x_axis += (f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{pad_top + chart_h + 6}" '
                   f'stroke="{COLORS["border_dark"]}" stroke-width="0.8" stroke-dasharray="3,3" opacity="0.5"/>\n')
        if qi < len(quarter_labels) and quarter_labels[qi]:
            x_axis += (f'<text x="{x:.1f}" y="{pad_top + chart_h + 20}" text-anchor="middle" '
                       f'font-size="11" font-weight="600" fill="{COLORS["slate"]}" font-family="IBM Plex Mono, monospace">'
                       f'{quarter_labels[qi]}</text>\n')
        x_axis += (f'<text x="{x:.1f}" y="{pad_top + chart_h + 34}" text-anchor="middle" '
                   f'font-size="9" fill="{COLORS["mist"]}" font-family="system-ui">W{w+1}</text>\n')

    # 只畫 3 條核心線
    lines_to_draw = ["decided", "aware", "resistant"]
    line_configs = {
        "aware": (COLORS["info"], "認知覆蓋", "2.2", ""),
        "decided": (COLORS["gold"], "採用率", "2.8", ""),
        "resistant": (COLORS["error"], "抵抗者", "1.6", "4,3"),
    }
    lines = ""
    for stage in lines_to_draw:
        if stage not in week_data:
            continue
        color, label, sw, dash = line_configs[stage]
        vals = week_data[stage]
        if not vals:
            continue
        pts = " ".join(f"{w2x(i):.1f},{v2y(v):.1f}" for i, v in enumerate(vals))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        lines += f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round"{dash_attr}/>\n'

    # 關鍵週標記
    markers = ""
    if critical_weeks:
        for cw in critical_weeks[:6]:
            w_idx = cw.get("week", 1) - 1
            if 0 <= w_idx < weeks_count:
                x = w2x(w_idx)
                # 找採用率
                decided_val = week_data["decided"][w_idx] if w_idx < len(week_data["decided"]) else 0
                y_dot = v2y(decided_val)
                event_short = cw.get("event", "")[:12]
                markers += f'<circle cx="{x:.1f}" cy="{y_dot:.1f}" r="5" fill="{COLORS["ember"]}" stroke="white" stroke-width="2"/>\n'
                markers += f'<line x1="{x:.1f}" y1="{y_dot - 6:.1f}" x2="{x:.1f}" y2="{pad_top + 8:.1f}" stroke="{COLORS["ember"]}" stroke-width="0.8" stroke-dasharray="2,2" opacity="0.6"/>\n'
                markers += f'<text x="{x:.1f}" y="{pad_top + 4:.1f}" text-anchor="middle" font-size="9" fill="{COLORS["ember"]}" font-family="Noto Sans TC, system-ui">{event_short}</text>\n'

    # 圖例
    legend_items = ""
    lx = pad_left + 8
    for stage in lines_to_draw:
        color, label, sw, _ = line_configs[stage]
        legend_items += f'<rect x="{lx}" y="{H - 16}" width="14" height="3" fill="{color}" rx="1"/>'
        legend_items += f'<text x="{lx + 18}" y="{H - 12}" font-size="10" fill="{COLORS["mist"]}" font-family="Noto Sans TC, system-ui">{label}</text>'
        lx += 95

    svg = f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
  {bg}
  {chasm_zone}
  {grid}
  {x_axis}
  {lines}
  {markers}
  {legend_items}
</svg>'''
    return svg


def _build_porter_svg(forces: dict) -> str:
    """產出 Porter 五力雷達圖（五角形 SVG）。"""
    W, H = 300, 300
    cx, cy = 150, 150
    r_max = 110
    force_names = ["競爭對手", "新進者", "替代品", "購買者", "供應商"]
    force_keys = ["rivalry", "new_entrants", "substitutes", "buyer_power", "supplier_power"]
    force_levels = {"高": 5, "中高": 4, "中": 3, "中低": 2, "低": 1}

    n = 5
    angle_step = 360 / n

    # 背景五角形（3 層）
    bg_polys = ""
    for level in [0.33, 0.67, 1.0]:
        pts = []
        for i in range(n):
            angle_rad = math.radians(i * angle_step - 90)
            r = level * r_max
            x = cx + r * math.cos(angle_rad)
            y = cy + r * math.sin(angle_rad)
            pts.append((x, y))
        poly_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        bg_polys += f'<polygon points="{poly_pts}" fill="none" stroke="{COLORS["border_dark"]}" stroke-width="0.7" opacity="0.5"/>\n'

    # 軸線
    axes = ""
    for i in range(n):
        angle_rad = math.radians(i * angle_step - 90)
        x_end = cx + r_max * math.cos(angle_rad)
        y_end = cy + r_max * math.sin(angle_rad)
        axes += f'<line x1="{cx}" y1="{cy}" x2="{x_end:.1f}" y2="{y_end:.1f}" stroke="{COLORS["border_dark"]}" stroke-width="0.7" opacity="0.5"/>\n'

    # 數據多邊形
    data_pts = []
    for i, key in enumerate(force_keys):
        force_data = forces.get(key, {})
        level_str = force_data.get("level", "中") if isinstance(force_data, dict) else "中"
        val = force_levels.get(level_str, 3)
        ratio = val / 5.0
        angle_rad = math.radians(i * angle_step - 90)
        r = ratio * r_max
        x = cx + r * math.cos(angle_rad)
        y = cy + r * math.sin(angle_rad)
        data_pts.append((x, y))

    poly_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in data_pts)
    data_poly = f'<polygon points="{poly_pts}" fill="{COLORS["ember"]}" fill-opacity="0.2" stroke="{COLORS["ember"]}" stroke-width="2"/>\n'

    # 節點
    dots = ""
    for x, y in data_pts:
        dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLORS["ember"]}" stroke="white" stroke-width="1.5"/>\n'

    # 標籤
    labels = ""
    label_r = r_max + 18
    for i, name in enumerate(force_names):
        angle_rad = math.radians(i * angle_step - 90)
        lx = cx + label_r * math.cos(angle_rad)
        ly = cy + label_r * math.sin(angle_rad)

        key = force_keys[i]
        force_data = forces.get(key, {})
        level_str = force_data.get("level", "中") if isinstance(force_data, dict) else "中"

        level_color = COLORS["error"] if level_str in ["高", "中高"] else (COLORS["warning"] if level_str == "中" else COLORS["success"])
        labels += f'<text x="{lx:.1f}" y="{ly - 4:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="11" font-weight="600" fill="white" font-family="Noto Sans TC, system-ui">{name}</text>\n'
        labels += f'<text x="{lx:.1f}" y="{ly + 10:.1f}" text-anchor="middle" dominant-baseline="middle" font-size="10" fill="{level_color}" font-family="IBM Plex Mono, monospace">{level_str}</text>\n'

    svg = f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
  <rect width="{W}" height="{H}" fill="{COLORS["surface"]}" rx="12"/>
  {bg_polys}
  {axes}
  {data_poly}
  {dots}
  {labels}
</svg>'''
    return svg


# ──────────────────────────────────────────────────────────────
# 主函數
# ──────────────────────────────────────────────────────────────

def generate_report(
    simulation_result: dict,
    insights: dict | None = None,
    events: list[dict] | None = None,
    output_path: str | None = None,
) -> str:
    """
    產出 DARWIN 麥肯錫等級策略顧問報告。

    Args:
        simulation_result: from run_real_data_simulation()
        insights:          from insight_generator（可選，None 時自動生成基礎洞察）
        events:            事件列表（可選，from event_detector；None 時降級為純 S 曲線+季度回顧）
                           每個事件 dict 格式：
                           {week, type, severity, icon, title, narrative, impact, action, data?}
        output_path:       None = 回傳 HTML 字串；有值則同時寫入檔案

    Returns:
        HTML 字串
    """
    now = datetime.now()
    date_str = now.strftime("%Y 年 %m 月 %d 日")

    district = simulation_result.get("district", "未知區域")
    energy = simulation_result.get("energy", {"inner": {}, "outer": {}})
    inner_energy = energy.get("inner", {})
    outer_energy = energy.get("outer", {})
    coverage = simulation_result.get("coverage", {})
    tam = simulation_result.get("tam", 0)
    population = simulation_result.get("population")
    final_state = simulation_result.get("final_state", {})
    snapshots = simulation_result.get("snapshots", [])
    indicators = simulation_result.get("indicators", {})

    cov_pct = coverage.get("coverage_pct", 0)

    # ── 從 insights 提取各區段資料 ──────────────────────────────
    diag = insights.get("diagnosis", {}) if insights else {}
    energy_landscape = insights.get("energy_landscape", {}) if insights else {}
    timeline = insights.get("timeline_narrative", {}) if insights else {}
    frameworks = insights.get("frameworks", {}) if insights else {}
    action_plan = insights.get("action_plan", []) if insights else []
    risk_matrix_data = insights.get("risk_matrix", []) if insights else []

    headline = diag.get("headline", f"{district} 策略演化模擬分析報告")
    verdict = diag.get("verdict", "待觀察")
    key_numbers = diag.get("key_numbers", {})
    one_paragraph = diag.get("one_paragraph", "")

    verdict_color = VERDICT_COLORS.get(verdict, COLORS["warning"])

    # ── 計算基礎數字 ──────────────────────────────────────────
    loyal_ratio = final_state.get("loyal", {}).get("ratio", 0)
    decided_ratio = final_state.get("decided", {}).get("ratio", 0)
    considering_ratio = final_state.get("considering", {}).get("ratio", 0)
    aware_ratio = final_state.get("aware", {}).get("ratio", 0)
    resistant_ratio = final_state.get("resistant", {}).get("ratio", 0)

    adoption_rate = (loyal_ratio + decided_ratio) * 100
    awareness_rate = (aware_ratio + considering_ratio + decided_ratio + loyal_ratio) * 100

    if not key_numbers:
        key_numbers = {
            "採用率": f"{adoption_rate:.1f}%",
            "忠實客戶": f"{int(loyal_ratio * tam):,} 人",
            "認知覆蓋": f"{awareness_rate:.1f}%",
            "TAM": f"{tam:,} 人",
            "數據覆蓋": f"{cov_pct:.0f}%",
        }

    # ────────────────────────────────────────────────────────────
    # 建立 HTML
    # ────────────────────────────────────────────────────────────

    html = _build_full_html(
        district=district,
        date_str=date_str,
        headline=headline,
        verdict=verdict,
        verdict_color=verdict_color,
        key_numbers=key_numbers,
        one_paragraph=one_paragraph,
        inner_energy=inner_energy,
        outer_energy=outer_energy,
        energy_landscape=energy_landscape,
        snapshots=snapshots,
        timeline=timeline,
        events=events,
        frameworks=frameworks,
        action_plan=action_plan,
        risk_matrix_data=risk_matrix_data,
        final_state=final_state,
        tam=tam,
        population=population,
        indicators=indicators,
        cov_pct=cov_pct,
    )

    if output_path:
        dir_name = os.path.dirname(output_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    return html


# ──────────────────────────────────────────────────────────────
# 完整 HTML 建構器
# ──────────────────────────────────────────────────────────────

def _build_full_html(
    district, date_str, headline, verdict, verdict_color,
    key_numbers, one_paragraph, inner_energy, outer_energy,
    energy_landscape, snapshots, timeline, events, frameworks,
    action_plan, risk_matrix_data, final_state, tam, population,
    indicators, cov_pct
) -> str:
    c = COLORS

    # ── 封面 ────────────────────────────────────────────────────
    cover_html = _build_cover(district, date_str, headline, verdict, verdict_color)

    # ── Executive Summary ─────────────────────────────────────
    exec_html = _build_executive_summary(verdict, verdict_color, key_numbers, one_paragraph, final_state, tam)

    # ── 市場能量地景 ──────────────────────────────────────────
    energy_html = _build_energy_landscape_section(inner_energy, outer_energy, energy_landscape)

    # ── 52 週戰場回放 ─────────────────────────────────────────
    critical_weeks = timeline.get("critical_weeks", []) if timeline else []
    timeline_html = _build_timeline_section(snapshots, timeline, critical_weeks, events)

    # ── SWOT ──────────────────────────────────────────────────
    swot_data = frameworks.get("swot", {}) if frameworks else {}
    swot_html = _build_swot_section(swot_data, inner_energy, outer_energy)

    # ── Porter 五力 ───────────────────────────────────────────
    porter_data = frameworks.get("porter_five_forces", {}) if frameworks else {}
    porter_html = _build_porter_section(porter_data, inner_energy, outer_energy)

    # ── 4P ────────────────────────────────────────────────────
    p4_data = frameworks.get("marketing_4p", {}) if frameworks else {}
    p4_html = _build_4p_section(p4_data)

    # ── 行動計畫 ──────────────────────────────────────────────
    action_html = _build_action_plan_section(action_plan)

    # ── 風險矩陣 ──────────────────────────────────────────────
    risk_html = _build_risk_matrix_section(risk_matrix_data, cov_pct)

    # ── 導航列 ────────────────────────────────────────────────
    nav_html = _build_nav()

    # ── CSS + 框架 ────────────────────────────────────────────
    css = _build_css()

    return f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>DARWIN 策略報告｜{district}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400;1,600&family=Outfit:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+TC:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>{css}</style>
</head>
<body>
  {nav_html}
  <div class="report-wrap">
    {cover_html}
    {exec_html}
    {energy_html}
    {timeline_html}
    {swot_html}
    {porter_html}
    {p4_html}
    {action_html}
    {risk_html}
  </div>
</body>
</html>'''


# ──────────────────────────────────────────────────────────────
# 頁面區塊建構器
# ──────────────────────────────────────────────────────────────

def _build_nav() -> str:
    nav_items = [
        ("cover", "封面"),
        ("exec", "執行摘要"),
        ("energy", "能量地景"),
        ("timeline", "52週回放"),
        ("swot", "SWOT"),
        ("porter", "五力分析"),
        ("p4", "4P建議"),
        ("action", "行動計畫"),
        ("risk", "風險矩陣"),
    ]
    items_html = "".join(
        f'<a href="#{id_}" class="nav-link">{label}</a>'
        for id_, label in nav_items
    )
    return f'''<nav class="top-nav">
  <div class="nav-inner">
    <span class="nav-brand">DARWIN</span>
    <div class="nav-links">{items_html}</div>
  </div>
</nav>'''


def _build_cover(district, date_str, headline, verdict, verdict_color) -> str:
    return f'''<section class="page cover-page" id="cover">
  <div class="cover-content">
    <div class="cover-top">
      <div class="cover-brand-badge">DARWIN STRATEGY ENGINE</div>
      <div class="cover-subtitle">策略演化模擬報告</div>
    </div>
    <div class="cover-center">
      <div class="cover-district">{district}</div>
      <div class="cover-headline">"{headline}"</div>
      <div class="cover-verdict-wrap">
        <span class="cover-verdict-label">策略判定</span>
        <span class="cover-verdict" style="background:{verdict_color}22; color:{verdict_color}; border-color:{verdict_color}44">{verdict}</span>
      </div>
    </div>
    <div class="cover-footer">
      <div class="cover-date">{date_str}</div>
      <div class="cover-brand-logo">
        <span class="logo-m">M</span><span class="logo-useon">USEON</span>
      </div>
      <div class="cover-disclaimer">本報告由 MUSEON DARWIN 引擎產出，模擬結果僅供策略參考</div>
    </div>
  </div>
</section>'''


def _build_executive_summary(verdict, verdict_color, key_numbers, one_paragraph, final_state, tam) -> str:
    # 大數字卡片
    cards_html = ""
    for i, (label, value) in enumerate(list(key_numbers.items())[:5]):
        cards_html += f'''<div class="kpi-card">
      <div class="kpi-value">{value}</div>
      <div class="kpi-label">{label}</div>
    </div>'''

    return f'''<section class="page section-page" id="exec">
  <div class="section-header">
    <div class="section-tag">EXECUTIVE SUMMARY</div>
    <h2 class="section-title">策略診斷摘要</h2>
  </div>
  <div class="exec-verdict-banner" style="border-left-color:{verdict_color}">
    <div class="exec-verdict-label">整體判定</div>
    <div class="exec-verdict-value" style="color:{verdict_color}">{verdict}</div>
    <div class="exec-verdict-sub">本報告依據 DARWIN 模擬引擎綜合分析所得</div>
  </div>
  <div class="kpi-grid">
    {cards_html}
  </div>
  <div class="exec-paragraph">
    <div class="exec-paragraph-label">核心洞見</div>
    <p class="exec-paragraph-text">{one_paragraph if one_paragraph else "—"}</p>
  </div>
  <div class="exec-read-note">讀完本頁即可掌握核心結論。後續章節提供深度分析與執行細節。</div>
</section>'''


def _build_energy_landscape_section(inner_energy, outer_energy, energy_landscape) -> str:
    radar_svg = _build_radar_svg_large(inner_energy, outer_energy)

    dominant = energy_landscape.get("dominant_energies", [])
    weak = energy_landscape.get("weak_energies", [])
    market_char = energy_landscape.get("market_character", "")
    customer_psych = energy_landscape.get("customer_psychology", "")
    competitive_env = energy_landscape.get("competitive_environment", "")

    # 優勢方位
    if dominant:
        dom_html = "".join(f'''<div class="energy-insight-row strength">
      <div class="energy-primal-badge">{d["primal"]}</div>
      <div class="energy-primal-val positive">+{abs(float(d.get("score", d.get("value", 0)))):.1f}</div>
      <div class="energy-primal-meaning">{d.get("business_implication", d.get("meaning", ""))}</div>
    </div>''' for d in dominant)
    else:
        top3 = sorted(
            [(p, (inner_energy.get(p, 0) + outer_energy.get(p, 0)) / 2) for p in ["天", "風", "水", "山", "地", "雷", "火", "澤"]],
            key=lambda x: x[1], reverse=True
        )[:3]
        dom_html = "".join(f'''<div class="energy-insight-row strength">
      <div class="energy-primal-badge">{p}</div>
      <div class="energy-primal-val positive">{v:+.1f}</div>
      <div class="energy-primal-meaning">主導能量方位，對市場動態有顯著影響</div>
    </div>''' for p, v in top3)

    if weak:
        weak_html = "".join(f'''<div class="energy-insight-row weakness">
      <div class="energy-primal-badge weak">{d["primal"]}</div>
      <div class="energy-primal-val negative">-{abs(float(d.get("score", d.get("value", 0)))):.1f}</div>
      <div class="energy-primal-meaning">{d.get("business_implication", d.get("meaning", ""))}</div>
    </div>''' for d in weak)
    else:
        weak3 = sorted(
            [(p, (inner_energy.get(p, 0) + outer_energy.get(p, 0)) / 2) for p in ["天", "風", "水", "山", "地", "雷", "火", "澤"]],
            key=lambda x: x[1]
        )[:2]
        weak_html = "".join(f'''<div class="energy-insight-row weakness">
      <div class="energy-primal-badge weak">{p}</div>
      <div class="energy-primal-val negative">{v:+.1f}</div>
      <div class="energy-primal-meaning">偏低能量方位，策略佈局需注意</div>
    </div>''' for p, v in weak3)

    # 能量數值表格
    energy_table = ""
    for primal in ["天", "風", "水", "山", "地", "雷", "火", "澤"]:
        iv = inner_energy.get(primal, 0.0)
        ov = outer_energy.get(primal, 0.0)
        avg = (iv + ov) / 2
        bar_width = min(100, max(0, (avg + 4) / 8 * 100))
        bar_color = COLORS["gold"] if avg > 0 else COLORS["mist"]
        energy_table += f'''<div class="energy-bar-row">
      <div class="energy-bar-label">{primal}</div>
      <div class="energy-bar-track">
        <div class="energy-bar-fill" style="width:{bar_width:.1f}%;background:{bar_color}"></div>
      </div>
      <div class="energy-bar-vals">
        <span style="color:{COLORS['gold']}">{iv:+.1f}</span>
        <span style="color:#4A90D9">{ov:+.1f}</span>
      </div>
    </div>'''

    descriptions = ""
    if market_char:
        descriptions += f'''<div class="landscape-desc-item">
      <div class="ldesc-label">市場性格</div>
      <p class="ldesc-text">{market_char}</p>
    </div>'''
    if customer_psych:
        descriptions += f'''<div class="landscape-desc-item">
      <div class="ldesc-label">消費者心理</div>
      <p class="ldesc-text">{customer_psych}</p>
    </div>'''
    if competitive_env:
        descriptions += f'''<div class="landscape-desc-item">
      <div class="ldesc-label">競爭環境</div>
      <p class="ldesc-text">{competitive_env}</p>
    </div>'''

    return f'''<section class="page section-page" id="energy">
  <div class="section-header">
    <div class="section-tag">ENERGY LANDSCAPE</div>
    <h2 class="section-title">市場能量地景</h2>
  </div>
  <div class="energy-main-grid">
    <div class="energy-radar-col">
      {radar_svg}
      <div class="energy-bar-table">
        <div class="energy-bar-header">
          <span>方位</span>
          <span>能量分布</span>
          <span>內/外</span>
        </div>
        {energy_table}
      </div>
    </div>
    <div class="energy-insight-col">
      <div class="energy-insights-block">
        <h3 class="insight-block-title strength-title">優勢方位</h3>
        {dom_html}
      </div>
      <div class="energy-insights-block">
        <h3 class="insight-block-title weakness-title">待強化方位</h3>
        {weak_html}
      </div>
    </div>
  </div>
  <div class="landscape-descriptions">
    {descriptions}
  </div>
</section>'''


def _build_s_curve_interactive_svg(snapshots: list[Any], events: list[dict] | None = None) -> str:
    """
    產出互動式 S 曲線 SVG（100% 寬度、400px 高），含三條線、鴻溝帶、季度分隔、事件標記。

    三條線：
      - 認知線（1 - unaware）= 藍色 #4A90D9
      - 採用線（decided + loyal）= 金色 #B8923A
      - 忠實線（loyal）= 綠色 #2A7A6E

    事件標記（若 events 提供）：
      - 每個事件圓點標在採用線對應週的位置上
      - severity 決定顏色/大小
      - hover 顯示標題（SVG title）
    """
    W, H = 900, 360
    pad_left, pad_right, pad_top, pad_bottom = 56, 36, 32, 52

    chart_w = W - pad_left - pad_right
    chart_h = H - pad_top - pad_bottom

    # 提取週資料
    weeks_data = []
    if snapshots:
        for snap in snapshots:
            if hasattr(snap, "business_metrics"):
                metrics = snap.business_metrics
                dist = metrics.get("state_distribution", {}) if isinstance(metrics, dict) else {}
                week = getattr(snap, "week", len(weeks_data) + 1)
            elif isinstance(snap, dict):
                metrics = snap.get("business_metrics", {})
                dist = metrics.get("state_distribution", {}) if isinstance(metrics, dict) else {}
                week = snap.get("week", len(weeks_data) + 1)
            else:
                dist = {}
                week = len(weeks_data) + 1

            unaware = dist.get("unaware", 1.0)
            decided = dist.get("decided", 0.0)
            loyal = dist.get("loyal", 0.0)
            weeks_data.append({
                "week": week,
                "awareness": (1 - unaware) * 100,
                "adoption": (decided + loyal) * 100,
                "loyal": loyal * 100,
            })
    else:
        for w in range(52):
            t = w / 51
            unaware = max(0, 1 - min(1, t * 2.2))
            loyal = min(40, 40 * max(0, t - 0.3) * 2) / 100
            decided = min(20, 20 * max(0, t - 0.2) * 4) / 100 if t < 0.6 else max(5, 20 - 15 * (t - 0.6) * 5) / 100
            weeks_data.append({
                "week": w + 1,
                "awareness": (1 - unaware) * 100,
                "adoption": (decided + loyal) * 100,
                "loyal": loyal * 100,
            })

    total_weeks = len(weeks_data)

    def w2x(w_idx: int) -> float:
        return pad_left + (w_idx / max(total_weeks - 1, 1)) * chart_w

    def v2y(v: float) -> float:
        return pad_top + chart_h - (v / 100.0) * chart_h

    # SVG 背景
    bg = f'<rect width="{W}" height="{H}" fill="{COLORS["surface"]}" rx="14"/>\n'

    # Y 軸格線
    grid = ""
    for pct in [0, 20, 40, 60, 80, 100]:
        y = v2y(pct)
        grid += (
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{pad_left + chart_w}" y2="{y:.1f}" '
            f'stroke="{COLORS["border_dark"]}" stroke-width="0.5" opacity="0.5"/>\n'
        )
        grid += (
            f'<text x="{pad_left - 8}" y="{y:.1f}" text-anchor="end" dominant-baseline="middle" '
            f'font-size="10" fill="{COLORS["mist"]}" font-family="IBM Plex Mono, monospace">{pct}%</text>\n'
        )

    # 鴻溝帶（15-35% 採用率）
    y_chasm_top = v2y(35)
    y_chasm_bot = v2y(15)
    chasm_zone = (
        f'<rect x="{pad_left}" y="{y_chasm_top:.1f}" width="{chart_w}" '
        f'height="{y_chasm_bot - y_chasm_top:.1f}" '
        f'fill="{COLORS["ember"]}" fill-opacity="0.07" rx="2"/>\n'
        f'<text x="{pad_left + 10}" y="{(y_chasm_top + y_chasm_bot) / 2:.1f}" '
        f'dominant-baseline="middle" font-size="10" fill="{COLORS["ember"]}" '
        f'font-family="IBM Plex Mono, monospace" opacity="0.75">CHASM ZONE</text>\n'
    )

    # 季度分隔線（W13, W26, W39）
    quarter_lines = ""
    quarter_labels_map = {13: "Q1", 26: "Q2", 39: "Q3"}
    for wk, label in [(13, "Q1"), (26, "Q2"), (39, "Q3")]:
        if wk < total_weeks:
            x = pad_left + (wk / max(total_weeks - 1, 1)) * chart_w
            quarter_lines += (
                f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{pad_top + chart_h + 8}" '
                f'stroke="{COLORS["border_dark"]}" stroke-width="1" stroke-dasharray="4,4" opacity="0.5"/>\n'
                f'<text x="{x:.1f}" y="{pad_top + chart_h + 22}" text-anchor="middle" '
                f'font-size="11" font-weight="600" fill="{COLORS["slate"]}" '
                f'font-family="IBM Plex Mono, monospace">{label}</text>\n'
            )
    # W1 和 W52 標籤
    for wk, label in [(0, "W1"), (total_weeks - 1, f"W{total_weeks}")]:
        x = pad_left if wk == 0 else pad_left + chart_w
        anchor = "start" if wk == 0 else "end"
        quarter_lines += (
            f'<text x="{x:.1f}" y="{pad_top + chart_h + 36}" text-anchor="{anchor}" '
            f'font-size="9" fill="{COLORS["mist"]}" font-family="IBM Plex Mono, monospace">{label}</text>\n'
        )

    # 三條 S 曲線
    def _make_polyline(key: str, color: str, sw: str, dash: str = "") -> str:
        pts = " ".join(
            f"{w2x(i):.1f},{v2y(d[key]):.1f}" for i, d in enumerate(weeks_data)
        )
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"{dash_attr}/>\n'

    awareness_line = _make_polyline("awareness", "#4A90D9", "2.2")
    adoption_line  = _make_polyline("adoption",  COLORS["gold"], "2.8")
    loyal_line     = _make_polyline("loyal",     COLORS["teal"], "1.8", "4,3")

    # 圖例
    legend_items = ""
    legend_data = [
        ("#4A90D9", "認知線（1-unaware）"),
        (COLORS["gold"], "採用線（decided+loyal）"),
        (COLORS["teal"], "忠實線（loyal）"),
    ]
    lx = pad_left + 8
    for color, label in legend_data:
        legend_items += f'<rect x="{lx}" y="{H - 18}" width="16" height="3" fill="{color}" rx="1.5"/>'
        legend_items += f'<text x="{lx + 22}" y="{H - 13}" font-size="10" fill="{COLORS["mist"]}" font-family="Noto Sans TC, system-ui">{label}</text>'
        lx += 160

    # 事件圓點標記
    severity_styles = {
        "critical": (COLORS["error"],   8, "#C4402A"),
        "high":     (COLORS["warning"], 6, "#C9943A"),
        "medium":   (COLORS["gold"],    5, "#B8923A"),
        "low":      (COLORS["teal"],    4, "#2A7A6E"),
    }

    event_markers = ""
    if events:
        for ev in events:
            week_num = ev.get("week", 1)
            w_idx = week_num - 1
            if 0 <= w_idx < total_weeks:
                sev = ev.get("severity", "medium")
                dot_color, dot_r, _ = severity_styles.get(sev, severity_styles["medium"])
                adoption_val = weeks_data[w_idx]["adoption"]
                ex = w2x(w_idx)
                ey = v2y(adoption_val)
                title = ev.get("title", "")
                icon = ev.get("icon", "")
                event_markers += (
                    f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="{dot_r}" '
                    f'fill="{dot_color}" stroke="white" stroke-width="1.5" opacity="0.95">\n'
                    f'  <title>W{week_num}: {icon} {title}</title>\n'
                    f'</circle>\n'
                )
                # 若為 critical/high：虛線連到下方
                if sev in ("critical", "high"):
                    event_markers += (
                        f'<line x1="{ex:.1f}" y1="{ey + dot_r + 2:.1f}" '
                        f'x2="{ex:.1f}" y2="{pad_top + chart_h:.1f}" '
                        f'stroke="{dot_color}" stroke-width="0.8" stroke-dasharray="2,3" opacity="0.5"/>\n'
                    )

    svg = f'''<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:400px;">
  {bg}
  {chasm_zone}
  {grid}
  {quarter_lines}
  {awareness_line}
  {adoption_line}
  {loyal_line}
  {event_markers}
  {legend_items}
</svg>'''
    return svg


def _build_timeline_section(snapshots, timeline, critical_weeks, events: list[dict] | None = None) -> str:
    """
    52 週戰場回放 Section。

    若 events 提供：輸出互動式事件時間軸（S 曲線 + 事件時間軸 + 季度回顧穿插）。
    若 events 為 None：降級模式（S 曲線 + 季度卡片）。
    """
    c = COLORS

    # ── Part A：互動式 S 曲線 ─────────────────────────────────
    s_curve_svg = _build_s_curve_interactive_svg(snapshots, events)

    phases = timeline.get("phases", []) if timeline else []
    chasm_analysis = timeline.get("chasm_analysis", "") if timeline else ""
    momentum_narrative = timeline.get("momentum_narrative", "") if timeline else ""

    # ── 季度定義（用於 Part C 季度戰略回顧）──────────────────
    quarter_defs = [
        ("Q1 認知建立期", "1-13", COLORS["info"]),
        ("Q2 鴻溝跨越期", "14-26", COLORS["warning"]),
        ("Q3 早期多數滲透", "27-39", COLORS["success"]),
        ("Q4 規模化與鞏固", "40-52", COLORS["gold"]),
    ]

    if events:
        # ═══════════════════════════════════════════════
        # 有事件資料：完整互動式時間軸
        # ═══════════════════════════════════════════════

        severity_badge = {
            "critical": ("關鍵轉折", "#C4402A"),
            "high":     ("重要事件", COLORS["warning"]),
            "medium":   ("值得關注", COLORS["gold"]),
            "low":      ("背景事件", COLORS["teal"]),
        }

        # 把事件依週排序
        sorted_events = sorted(events, key=lambda e: e.get("week", 0))

        # 把季度分隔插入事件列表：
        # Q 邊界 = week 13 之後、26 之後、39 之後
        quarter_boundaries = {13: 1, 26: 2, 39: 3}  # after week N → insert Q(N+1)

        # 先組合全部節點（事件 + 季度回顧）
        all_nodes: list[dict] = []  # type: "event" | "quarter"
        q_inserted = set()
        for ev in sorted_events:
            wk = ev.get("week", 1)
            for boundary, q_idx in quarter_boundaries.items():
                if wk > boundary and q_idx not in q_inserted:
                    q_inserted.add(q_idx)
                    all_nodes.append({"__type": "quarter", "__q_idx": q_idx})
            all_nodes.append({"__type": "event", **ev})
        # 補插未加入的季度回顧（全部事件在 Q1 的情況）
        for q_idx in range(1, 4):
            if q_idx not in q_inserted:
                all_nodes.append({"__type": "quarter", "__q_idx": q_idx})

        # ── 組建時間軸 HTML ──────────────────────────────────
        timeline_items_html = ""
        for node in all_nodes:
            if node["__type"] == "quarter":
                q_idx = node["__q_idx"]
                # 找對應 phase 資料
                phase = phases[q_idx] if q_idx < len(phases) else {}
                q_name, q_weeks, q_color = quarter_defs[q_idx] if q_idx < len(quarter_defs) else (f"Q{q_idx+1}", "?", c["ember"])
                what = phase.get("what_happened", "")
                why = phase.get("why", "")
                should_have = phase.get("should_have_done", "")
                strategy_eff = phase.get("strategy_effectiveness", "")

                # 週期指標
                metrics_html = ""
                if snapshots:
                    # 取該季末的 snapshot
                    quarter_end_week = min(13 * (q_idx + 1), len(snapshots)) - 1
                    if 0 <= quarter_end_week < len(snapshots):
                        snap = snapshots[quarter_end_week]
                        if hasattr(snap, "business_metrics"):
                            dist = snap.business_metrics.get("state_distribution", {})
                        elif isinstance(snap, dict):
                            dist = snap.get("business_metrics", {}).get("state_distribution", {})
                        else:
                            dist = {}
                        unaware = dist.get("unaware", 1.0)
                        decided = dist.get("decided", 0.0)
                        loyal_v = dist.get("loyal", 0.0)
                        awareness_v = (1 - unaware) * 100
                        adoption_v = (decided + loyal_v) * 100
                        metrics_html = f'''<div class="quarter-stats">
              <span class="qs-item"><span class="qs-label">認知</span>{awareness_v:.0f}%</span>
              <span class="qs-item"><span class="qs-label">採用</span>{adoption_v:.1f}%</span>
              <span class="qs-item"><span class="qs-label">忠實</span>{loyal_v * 100:.1f}%</span>
            </div>'''

                timeline_items_html += f'''
  <div class="tl-quarter-review" style="--q-color:{q_color}">
    <div class="tl-quarter-line"></div>
    <div class="tl-quarter-card">
      <div class="tl-quarter-header">
        <h3 class="tl-quarter-name" style="color:{q_color}">{q_name}</h3>
        <span class="tl-quarter-weeks">第 {q_weeks} 週</span>
      </div>
      {metrics_html}
      {f'<div class="tl-quarter-row"><span class="tl-quarter-row-label">發生了什麼</span><p>{what}</p></div>' if what else ""}
      {f'<div class="tl-quarter-row"><span class="tl-quarter-row-label">背後原因</span><p>{why}</p></div>' if why else ""}
      {f'<div class="tl-quarter-row highlight"><span class="tl-quarter-row-label">應該做</span><p>{should_have}</p></div>' if should_have else ""}
    </div>
  </div>'''

            else:
                # 事件節點
                wk = node.get("week", "?")
                ev_type = node.get("type", "milestone")
                sev = node.get("severity", "medium")
                icon = node.get("icon", "")
                title = node.get("title", "")
                narrative = node.get("narrative", "")
                impact = node.get("impact", "")
                action = node.get("action", "")

                badge_text, badge_color = severity_badge.get(sev, ("事件", c["mist"]))

                # 週的指標快照
                w_idx = int(wk) - 1 if isinstance(wk, (int, float)) else -1
                snap_metrics_html = ""
                if 0 <= w_idx < len(snapshots) and snapshots:
                    snap = snapshots[w_idx]
                    if hasattr(snap, "business_metrics"):
                        dist = snap.business_metrics.get("state_distribution", {})
                    elif isinstance(snap, dict):
                        dist = snap.get("business_metrics", {}).get("state_distribution", {})
                    else:
                        dist = {}
                    unaware = dist.get("unaware", 1.0)
                    decided = dist.get("decided", 0.0)
                    loyal_v = dist.get("loyal", 0.0)
                    aw = (1 - unaware) * 100
                    ad = (decided + loyal_v) * 100
                    snap_metrics_html = f'''<div class="event-metrics">
              <span>認知 {aw:.0f}%</span>
              <span>採用 {ad:.1f}%</span>
              <span>忠實 {loyal_v * 100:.1f}%</span>
            </div>'''

                timeline_items_html += f'''
  <div class="tl-event {sev}" data-week="{wk}">
    <div class="tl-event-dot {sev}"></div>
    <div class="tl-event-card {sev}">
      <div class="tl-event-header">
        <span class="tl-event-week">第 {wk} 週</span>
        <span class="tl-event-badge" style="background:{badge_color}22;color:{badge_color}">{badge_text}</span>
      </div>
      <h4 class="tl-event-title">{icon} {title}</h4>
      {f'<p class="tl-event-narrative">{narrative}</p>' if narrative else ""}
      {f'<div class="tl-event-impact"><strong>影響：</strong>{impact}</div>' if impact else ""}
      {f'<div class="tl-event-action"><strong>建議行動：</strong>{action}</div>' if action else ""}
      {snap_metrics_html}
    </div>
  </div>'''

        return f'''<section class="page section-page" id="timeline">
  <div class="section-header">
    <div class="section-tag">52-WEEK BATTLEFIELD REPLAY</div>
    <h2 class="section-title">52 週戰場回放</h2>
  </div>

  <!-- Part A: 互動式 S 曲線 -->
  <div class="curve-wrapper">
    {s_curve_svg}
  </div>

  <!-- Part B + C: 事件時間軸（含穿插季度回顧） -->
  <div class="tl-container">
    <div class="tl-spine"></div>
    {timeline_items_html}
  </div>
</section>'''

    else:
        # ═══════════════════════════════════════════════
        # 降級模式：S 曲線 + 季度卡片（原版行為）
        # ═══════════════════════════════════════════════
        quarter_colors = [COLORS["info"], COLORS["warning"], COLORS["success"], COLORS["gold"]]
        phase_cards = ""
        for i, phase in enumerate(phases[:4]):
            color = quarter_colors[i % len(quarter_colors)]
            phase_name = phase.get("name", f"Q{i+1}")
            weeks = phase.get("weeks", "")
            what_happened = phase.get("what_happened", "")
            why = phase.get("why", "")
            strategy_eff = phase.get("strategy_effectiveness", "")
            should_have = phase.get("should_have_done", "")
            turning_pts = phase.get("turning_points", [])
            turning_html = "".join(
                f'<div class="turning-point"><span class="tp-week">W{tp.get("week","?")}</span>'
                f'<span class="tp-event">{tp.get("event","")}</span></div>'
                for tp in turning_pts
            )
            phase_cards += f'''<div class="phase-card" style="border-top-color:{color}">
      <div class="phase-header">
        <div class="phase-name" style="color:{color}">{phase_name}</div>
        <div class="phase-weeks">第 {weeks} 週</div>
      </div>
      {f'<div class="phase-turning">{turning_html}</div>' if turning_pts else ""}
      <div class="phase-body">
        <div class="phase-row"><div class="phase-row-label">發生了什麼</div><div class="phase-row-text">{what_happened}</div></div>
        <div class="phase-row"><div class="phase-row-label">背後原因</div><div class="phase-row-text">{why}</div></div>
        <div class="phase-row"><div class="phase-row-label">策略效果</div><div class="phase-row-text">{strategy_eff}</div></div>
        <div class="phase-row highlight"><div class="phase-row-label">回顧建議</div><div class="phase-row-text">{should_have}</div></div>
      </div>
    </div>'''

        chasm_block = ""
        if chasm_analysis:
            chasm_block = f'''<div class="chasm-analysis-block">
      <div class="chasm-icon">CHASM</div>
      <div class="chasm-text">
        <div class="chasm-label">鴻溝分析</div>
        <p>{chasm_analysis}</p>
      </div>
    </div>'''

        momentum_block = ""
        if momentum_narrative:
            momentum_block = f'''<div class="momentum-block">
      <div class="momentum-label">動能敘事</div>
      <p>{momentum_narrative}</p>
    </div>'''

        milestone_html = ""
        if critical_weeks:
            for cw in critical_weeks:
                sig = cw.get("significance", "")
                milestone_html += f'''<div class="milestone-item">
        <div class="milestone-week">W{cw.get("week","?")}</div>
        <div class="milestone-dot"></div>
        <div class="milestone-body">
          <div class="milestone-event">{cw.get("event","")}</div>
          <div class="milestone-sig">{sig}</div>
        </div>
      </div>'''

        return f'''<section class="page section-page" id="timeline">
  <div class="section-header">
    <div class="section-tag">52-WEEK BATTLEFIELD REPLAY</div>
    <h2 class="section-title">52 週戰場回放</h2>
  </div>
  <div class="curve-wrapper">
    {s_curve_svg}
  </div>
  {f'<div class="milestone-timeline">{milestone_html}</div>' if milestone_html else ""}
  <div class="phase-grid">
    {phase_cards}
  </div>
  {chasm_block}
  {momentum_block}
</section>'''


def _build_swot_section(swot_data, inner_energy, outer_energy) -> str:
    strengths = swot_data.get("strengths", ["主導能量為正值方位，市場契合度高", "消費能力強勁，溢價空間大"])
    weaknesses = swot_data.get("weaknesses", ["部分能量方位偏低，需要主動補強", "市場競爭密度高"])
    opportunities = swot_data.get("opportunities", ["認知覆蓋高但轉化空間大", "消費升級趨勢明顯"])
    threats = swot_data.get("threats", ["鴻溝效應可能阻礙成長", "同業模仿成本低"])

    def list_items(items, cls=""):
        return "".join(f'<li class="swot-item {cls}">{item}</li>' for item in items)

    return f'''<section class="page section-page" id="swot">
  <div class="section-header">
    <div class="section-tag">STRATEGIC FRAMEWORK</div>
    <h2 class="section-title">SWOT 分析</h2>
  </div>
  <div class="swot-grid">
    <div class="swot-cell strengths">
      <div class="swot-cell-header">
        <span class="swot-icon s-icon">S</span>
        <span class="swot-cell-title">優勢 Strengths</span>
      </div>
      <ul class="swot-list">{list_items(strengths, "strength")}</ul>
    </div>
    <div class="swot-cell weaknesses">
      <div class="swot-cell-header">
        <span class="swot-icon w-icon">W</span>
        <span class="swot-cell-title">劣勢 Weaknesses</span>
      </div>
      <ul class="swot-list">{list_items(weaknesses, "weakness")}</ul>
    </div>
    <div class="swot-cell opportunities">
      <div class="swot-cell-header">
        <span class="swot-icon o-icon">O</span>
        <span class="swot-cell-title">機會 Opportunities</span>
      </div>
      <ul class="swot-list">{list_items(opportunities, "opportunity")}</ul>
    </div>
    <div class="swot-cell threats">
      <div class="swot-cell-header">
        <span class="swot-icon t-icon">T</span>
        <span class="swot-cell-title">威脅 Threats</span>
      </div>
      <ul class="swot-list">{list_items(threats, "threat")}</ul>
    </div>
  </div>
  <div class="swot-note">* 各項分析依據 DARWIN 能量向量與 52 週模擬結果推導</div>
</section>'''


def _build_porter_section(porter_data, inner_energy, outer_energy) -> str:
    porter_svg = _build_porter_svg(porter_data)
    overall = porter_data.get("overall", "")

    force_configs = [
        ("rivalry", "同業競爭"),
        ("new_entrants", "新進者威脅"),
        ("substitutes", "替代品威脅"),
        ("buyer_power", "購買者議價力"),
        ("supplier_power", "供應商議價力"),
    ]

    force_rows = ""
    for key, name in force_configs:
        data = porter_data.get(key, {})
        if isinstance(data, dict):
            level = data.get("level", "—")
            analysis = data.get("analysis", "")
        else:
            level = "—"
            analysis = ""
        level_color = COLORS["error"] if level in ["高", "中高"] else (COLORS["warning"] if level == "中" else COLORS["success"])
        force_rows += f'''<div class="porter-row">
      <div class="porter-force-name">{name}</div>
      <div class="porter-level" style="color:{level_color};border-color:{level_color}44">{level}</div>
      <div class="porter-analysis">{analysis}</div>
    </div>'''

    return f'''<section class="page section-page" id="porter">
  <div class="section-header">
    <div class="section-tag">COMPETITIVE ANALYSIS</div>
    <h2 class="section-title">Porter 五力分析</h2>
  </div>
  <div class="porter-layout">
    <div class="porter-chart-col">
      {porter_svg}
    </div>
    <div class="porter-table-col">
      {force_rows}
      {f'<div class="porter-overall"><div class="porter-overall-label">整體競爭環境</div><p>{overall}</p></div>' if overall else ""}
    </div>
  </div>
</section>'''


def _build_4p_section(p4_data) -> str:
    configs = [
        ("product", "Product", "產品", "#2A6A8A"),
        ("price", "Price", "定價", "#2D8A6E"),
        ("place", "Place", "通路", "#C9943A"),
        ("promotion", "Promotion", "推廣", "#7B5EA7"),
    ]

    p4_cards = ""
    for key, en_name, zh_name, color in configs:
        data = p4_data.get(key, {})
        if isinstance(data, dict):
            current = data.get("current", "")
            recommendation = data.get("recommendation", "")
            energy_basis = data.get("energy_basis", "")
        else:
            current = recommendation = energy_basis = ""
        p4_cards += f'''<div class="p4-card" style="border-top-color:{color}">
      <div class="p4-card-header">
        <div class="p4-letter" style="background:{color}22;color:{color}">{en_name[0]}</div>
        <div>
          <div class="p4-en-name" style="color:{color}">{en_name}</div>
          <div class="p4-zh-name">{zh_name}</div>
        </div>
      </div>
      <div class="p4-current-wrap">
        <div class="p4-section-label">現狀</div>
        <div class="p4-current">{current}</div>
      </div>
      <div class="p4-rec-wrap">
        <div class="p4-section-label">策略建議</div>
        <p class="p4-recommendation">{recommendation}</p>
      </div>
      {f'<div class="p4-energy-basis"><span class="p4-basis-icon">◈</span>{energy_basis}</div>' if energy_basis else ""}
    </div>'''

    return f'''<section class="page section-page" id="p4">
  <div class="section-header">
    <div class="section-tag">MARKETING STRATEGY</div>
    <h2 class="section-title">4P 行銷策略建議</h2>
  </div>
  <div class="p4-grid">
    {p4_cards}
  </div>
</section>'''


def _build_action_plan_section(action_plan) -> str:
    if not action_plan:
        action_plan = [{
            "phase": "Q1：啟動期",
            "objective": "建立初步市場認知",
            "actions": [
                {"action": "建立品牌識別系統", "expected_impact": "提升品牌辨識度", "resources": "視設計需求", "kpi": "品牌認知率 > 20%"},
            ],
            "budget_allocation": "總預算 40%"
        }]

    phase_blocks = ""
    phase_colors = [COLORS["info"], COLORS["warning"], COLORS["success"]]

    for i, phase in enumerate(action_plan):
        color = phase_colors[i % len(phase_colors)]
        phase_name = phase.get("phase", f"Phase {i+1}")
        objective = phase.get("objective", "")
        actions = phase.get("actions", [])
        budget = phase.get("budget_allocation", "")

        action_rows = ""
        for j, act in enumerate(actions):
            action_rows += f'''<div class="action-row">
          <div class="action-num" style="background:{color}22;color:{color}">{j+1}</div>
          <div class="action-content">
            <div class="action-title">{act.get("action", "")}</div>
            <div class="action-meta-row">
              <span class="action-meta-item"><span class="action-meta-label">預期效果</span>{act.get("expected_impact", "")}</span>
              <span class="action-meta-item"><span class="action-meta-label">所需資源</span>{act.get("resources", "")}</span>
              <span class="action-meta-item"><span class="action-meta-label">KPI</span><strong>{act.get("kpi", "")}</strong></span>
            </div>
          </div>
        </div>'''

        phase_blocks += f'''<div class="action-phase-block">
      <div class="action-phase-header" style="border-left-color:{color}">
        <div>
          <div class="action-phase-name" style="color:{color}">{phase_name}</div>
          <div class="action-objective">{objective}</div>
        </div>
        {f'<div class="action-budget" style="color:{color}">{budget}</div>' if budget else ""}
      </div>
      <div class="action-rows">{action_rows}</div>
    </div>'''

    return f'''<section class="page section-page" id="action">
  <div class="section-header">
    <div class="section-tag">ACTION ROADMAP</div>
    <h2 class="section-title">分階段行動計畫</h2>
  </div>
  <div class="action-plan-container">
    {phase_blocks}
  </div>
</section>'''


def _build_risk_matrix_section(risk_matrix_data, cov_pct) -> str:
    # 按象限分類
    quadrant_map = {
        "critical": [],   # 高機率高影響
        "monitor": [],    # 高機率低影響
        "prepare": [],    # 低機率高影響
        "accept": [],     # 低機率低影響
    }

    for risk in risk_matrix_data:
        q = risk.get("quadrant", "accept")
        quadrant_map[q].append(risk)

    def risk_items(items):
        if not items:
            return '<div class="risk-empty">暫無此象限風險</div>'
        return "".join(f'''<div class="risk-item">
      <div class="risk-name">{r.get("risk","")}</div>
      <div class="risk-mitigation">{r.get("mitigation","")}</div>
    </div>''' for r in items)

    return f'''<section class="page section-page" id="risk">
  <div class="section-header">
    <div class="section-tag">RISK MANAGEMENT</div>
    <h2 class="section-title">風險矩陣</h2>
  </div>
  <div class="risk-matrix-header">
    <div class="risk-axis-label y-label">影響程度</div>
    <div class="risk-grid">
      <div class="risk-cell prepare">
        <div class="risk-cell-header">
          <span class="risk-cell-badge prepare-badge">低機率 × 高影響</span>
          <span class="risk-cell-title">預備應對</span>
        </div>
        {risk_items(quadrant_map["prepare"])}
      </div>
      <div class="risk-cell critical">
        <div class="risk-cell-header">
          <span class="risk-cell-badge critical-badge">高機率 × 高影響</span>
          <span class="risk-cell-title">優先處置</span>
        </div>
        {risk_items(quadrant_map["critical"])}
      </div>
      <div class="risk-cell accept">
        <div class="risk-cell-header">
          <span class="risk-cell-badge accept-badge">低機率 × 低影響</span>
          <span class="risk-cell-title">接受監控</span>
        </div>
        {risk_items(quadrant_map["accept"])}
      </div>
      <div class="risk-cell monitor">
        <div class="risk-cell-header">
          <span class="risk-cell-badge monitor-badge">高機率 × 低影響</span>
          <span class="risk-cell-title">持續監控</span>
        </div>
        {risk_items(quadrant_map["monitor"])}
      </div>
    </div>
    <div class="risk-axis-label x-label">發生機率</div>
  </div>
  <div class="disclaimer">
    <strong>免責聲明：</strong>本報告所有內容均基於 DARWIN 策略演化引擎之計算模擬，數據覆蓋率為 {cov_pct:.0f}%。
    模擬結果反映統計趨勢，不代表實際市場保證。策略決策請結合實地調研與專業顧問意見。
    MUSEON © {datetime.now().year}
  </div>
</section>'''


# ──────────────────────────────────────────────────────────────
# CSS 樣式表
# ──────────────────────────────────────────────────────────────

def _build_css() -> str:
    c = COLORS
    return f'''
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --ember: {c["ember"]};
  --ember-light: {c["ember_light"]};
  --ember-dark: {c["ember_dark"]};
  --teal: {c["teal"]};
  --gold: {c["gold"]};
  --ink: {c["ink"]};
  --slate: {c["slate"]};
  --mist: {c["mist"]};
  --border: {c["border"]};
  --parchment: {c["parchment"]};
  --snow: {c["snow"]};
  --deep-ink: {c["deep_ink"]};
  --surface: {c["surface"]};
  --raised: {c["raised"]};
  --border-dark: {c["border_dark"]};
  --success: {c["success"]};
  --warning: {c["warning"]};
  --error: {c["error"]};
  --info: {c["info"]};
}}

html {{ scroll-behavior: smooth; }}

body {{
  font-family: 'Outfit', 'Noto Sans TC', system-ui, sans-serif;
  background: var(--parchment);
  color: var(--ink);
  line-height: 1.75;
  font-size: 16px;
}}

/* ── 導航列 ── */
.top-nav {{
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: rgba(14,14,22,0.96);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid {c["border_dark"]};
  height: 52px;
}}

.nav-inner {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 32px;
}}

.nav-brand {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--ember);
  text-transform: uppercase;
  white-space: nowrap;
}}

.nav-links {{
  display: flex;
  gap: 4px;
  overflow-x: auto;
  scrollbar-width: none;
}}

.nav-links::-webkit-scrollbar {{ display: none; }}

.nav-link {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--mist);
  text-decoration: none;
  padding: 6px 10px;
  border-radius: 4px;
  white-space: nowrap;
  transition: all 0.15s ease;
}}

.nav-link:hover {{
  color: white;
  background: rgba(196,80,42,0.15);
}}

/* ── 報告容器 ── */
.report-wrap {{
  padding-top: 52px;
}}

/* ── 通用 Page ── */
.page {{
  min-height: 100vh;
  padding: 0;
}}

.section-page {{
  max-width: 1200px;
  margin: 0 auto;
  padding: 64px 40px 80px;
}}

@media (max-width: 1024px) {{
  .section-page {{ padding: 48px 24px 64px; }}
}}

@media (max-width: 640px) {{
  .section-page {{ padding: 32px 16px 48px; }}
}}

/* ── Section Header ── */
.section-header {{
  margin-bottom: 40px;
}}

.section-tag {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.2em;
  color: var(--ember);
  text-transform: uppercase;
  margin-bottom: 8px;
}}

.section-title {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 36px;
  font-weight: 600;
  color: var(--ink);
  line-height: 1.2;
}}

/* ── 封面 ── */
.cover-page {{
  background: var(--deep-ink);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  position: relative;
  overflow: hidden;
}}

.cover-page::before {{
  content: '';
  position: absolute;
  top: -200px;
  right: -200px;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, {c["ember"]}18 0%, transparent 70%);
  pointer-events: none;
}}

.cover-content {{
  max-width: 820px;
  width: 100%;
  padding: 80px 40px;
  display: flex;
  flex-direction: column;
  gap: 80px;
  position: relative;
  z-index: 1;
}}

.cover-top {{
  display: flex;
  flex-direction: column;
  gap: 8px;
}}

.cover-brand-badge {{
  display: inline-block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.25em;
  color: var(--ember);
  text-transform: uppercase;
  border: 1px solid {c["ember"]}44;
  padding: 4px 12px;
  border-radius: 100px;
  width: fit-content;
}}

.cover-subtitle {{
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  color: var(--mist);
  letter-spacing: 0.1em;
}}

.cover-center {{
  display: flex;
  flex-direction: column;
  gap: 24px;
}}

.cover-district {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 52px;
  font-weight: 600;
  color: white;
  line-height: 1.1;
}}

.cover-headline {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 22px;
  font-weight: 400;
  font-style: italic;
  color: {c["mist"]};
  line-height: 1.5;
  max-width: 65ch;
  border-left: 3px solid {c["ember"]};
  padding-left: 20px;
}}

.cover-verdict-wrap {{
  display: flex;
  align-items: center;
  gap: 12px;
}}

.cover-verdict-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  color: var(--mist);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}}

.cover-verdict {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.1em;
  padding: 6px 16px;
  border-radius: 100px;
  border: 1px solid;
}}

.cover-footer {{
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 16px;
  padding-top: 40px;
  border-top: 1px solid {c["border_dark"]};
}}

.cover-date {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  color: var(--mist);
}}

.cover-brand-logo {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 24px;
  font-weight: 600;
}}

.logo-m {{
  color: var(--ember);
}}

.logo-useon {{
  color: white;
}}

.cover-disclaimer {{
  font-size: 11px;
  color: var(--mist);
  max-width: 300px;
  line-height: 1.5;
}}

/* ── Executive Summary ── */
.exec-verdict-banner {{
  background: {c["surface"]};
  border: 1px solid {c["border_dark"]};
  border-left: 4px solid;
  border-radius: 8px;
  padding: 24px 32px;
  margin-bottom: 40px;
  display: flex;
  align-items: center;
  gap: 32px;
  flex-wrap: wrap;
}}

.exec-verdict-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--mist);
  text-transform: uppercase;
}}

.exec-verdict-value {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 40px;
  font-weight: 600;
  line-height: 1;
}}

.exec-verdict-sub {{
  font-size: 13px;
  color: var(--mist);
}}

.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
  margin-bottom: 40px;
}}

@media (max-width: 900px) {{
  .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }}
}}

@media (max-width: 600px) {{
  .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
}}

.kpi-card {{
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 16px;
  text-align: center;
  box-shadow: 0 1px 3px rgba(18,18,26,0.06);
}}

.kpi-value {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 32px;
  font-weight: 600;
  color: var(--ember);
  line-height: 1.1;
  margin-bottom: 6px;
}}

.kpi-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--slate);
  text-transform: uppercase;
}}

.exec-paragraph {{
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 28px 32px;
  margin-bottom: 24px;
}}

.exec-paragraph-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.15em;
  color: var(--ember);
  text-transform: uppercase;
  margin-bottom: 12px;
}}

.exec-paragraph-text {{
  font-size: 16px;
  line-height: 1.85;
  color: var(--ink);
}}

.exec-read-note {{
  font-size: 13px;
  color: var(--mist);
  font-style: italic;
  text-align: center;
  padding: 16px;
  border-top: 1px solid var(--border);
}}

/* ── 能量地景 ── */
.energy-main-grid {{
  display: grid;
  grid-template-columns: 420px 1fr;
  gap: 40px;
  margin-bottom: 48px;
}}

@media (max-width: 900px) {{
  .energy-main-grid {{ grid-template-columns: 1fr; }}
}}

.energy-radar-col {{
  display: flex;
  flex-direction: column;
  gap: 24px;
}}

.energy-bar-table {{
  background: {c["surface"]};
  border-radius: 10px;
  padding: 16px;
}}

.energy-bar-header {{
  display: grid;
  grid-template-columns: 24px 1fr 72px;
  gap: 8px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  letter-spacing: 0.1em;
  color: var(--mist);
  text-transform: uppercase;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid {c["border_dark"]};
}}

.energy-bar-row {{
  display: grid;
  grid-template-columns: 24px 1fr 72px;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}}

.energy-bar-label {{
  font-family: 'Noto Sans TC', system-ui;
  font-size: 13px;
  font-weight: 600;
  color: white;
  text-align: center;
}}

.energy-bar-track {{
  background: {c["border_dark"]};
  border-radius: 100px;
  height: 6px;
  overflow: hidden;
}}

.energy-bar-fill {{
  height: 100%;
  border-radius: 100px;
  transition: width 0.3s ease;
}}

.energy-bar-vals {{
  display: flex;
  gap: 6px;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  justify-content: flex-end;
}}

.energy-insight-col {{
  display: flex;
  flex-direction: column;
  gap: 24px;
}}

.energy-insights-block {{
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 24px;
}}

.insight-block-title {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}}

.strength-title {{ color: {c["success"]}; }}
.weakness-title {{ color: {c["warning"]}; }}

.energy-insight-row {{
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}}

.energy-insight-row:last-child {{ border-bottom: none; }}

.energy-primal-badge {{
  font-family: 'Noto Sans TC', system-ui;
  font-size: 20px;
  font-weight: 700;
  color: {c["gold"]};
  min-width: 28px;
  text-align: center;
  line-height: 1;
  padding-top: 2px;
}}

.energy-primal-badge.weak {{
  color: var(--mist);
}}

.energy-primal-val {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px;
  font-weight: 600;
  min-width: 36px;
}}

.energy-primal-val.positive {{ color: {c["gold"]}; }}
.energy-primal-val.negative {{ color: var(--mist); }}

.energy-primal-meaning {{
  font-size: 13px;
  color: var(--slate);
  line-height: 1.55;
}}

.landscape-descriptions {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}}

.landscape-desc-item {{
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px 24px;
}}

.ldesc-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--ember);
  text-transform: uppercase;
  margin-bottom: 10px;
}}

.ldesc-text {{
  font-size: 14px;
  color: var(--slate);
  line-height: 1.75;
}}

/* ── 52 週時間軸 ── */
.curve-wrapper {{
  margin-bottom: 32px;
  overflow-x: auto;
}}

.curve-wrapper svg {{
  max-width: 100%;
}}

.milestone-timeline {{
  display: flex;
  gap: 0;
  margin-bottom: 40px;
  position: relative;
  overflow-x: auto;
  padding-bottom: 8px;
}}

.milestone-timeline::before {{
  content: '';
  position: absolute;
  top: 16px;
  left: 20px;
  right: 20px;
  height: 1px;
  background: var(--border);
}}

.milestone-item {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-width: 120px;
  flex: 1;
  position: relative;
}}

.milestone-week {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  color: var(--ember);
  background: {c["parchment"]};
  padding: 2px 6px;
  border-radius: 4px;
  z-index: 1;
}}

.milestone-dot {{
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--ember);
  border: 2px solid {c["parchment"]};
  z-index: 1;
}}

.milestone-body {{
  text-align: center;
}}

.milestone-event {{
  font-size: 11px;
  font-weight: 600;
  color: var(--ink);
  margin-bottom: 2px;
}}

.milestone-sig {{
  font-size: 10px;
  color: var(--mist);
  line-height: 1.4;
}}

.phase-grid {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
  margin-bottom: 32px;
}}

@media (max-width: 768px) {{
  .phase-grid {{ grid-template-columns: 1fr; }}
}}

.phase-card {{
  background: var(--snow);
  border: 1px solid var(--border);
  border-top: 3px solid;
  border-radius: 10px;
  padding: 20px;
}}

.phase-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}}

.phase-name {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 18px;
  font-weight: 600;
}}

.phase-weeks {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  color: var(--mist);
  background: {c["parchment"]};
  padding: 3px 8px;
  border-radius: 4px;
}}

.phase-turning {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}}

.turning-point {{
  display: flex;
  gap: 4px;
  align-items: center;
  background: {c["parchment"]};
  border-radius: 4px;
  padding: 3px 8px;
  font-size: 11px;
}}

.tp-week {{
  font-family: 'IBM Plex Mono', monospace;
  font-weight: 600;
  color: var(--ember);
  font-size: 10px;
}}

.tp-event {{
  color: var(--slate);
}}

.phase-row {{
  padding: 8px 0;
  border-bottom: 1px solid {c["parchment"]};
}}

.phase-row:last-child {{ border-bottom: none; }}

.phase-row.highlight {{
  background: rgba(196,80,42,0.04);
  margin: 0 -4px;
  padding: 8px 4px;
  border-radius: 6px;
  border-bottom: none;
}}

.phase-row-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--ember);
  text-transform: uppercase;
  margin-bottom: 4px;
}}

.phase-row-text {{
  font-size: 13px;
  color: var(--slate);
  line-height: 1.6;
}}

.chasm-analysis-block {{
  background: {c["surface"]};
  border: 1px solid {c["border_dark"]};
  border-left: 4px solid {c["ember"]};
  border-radius: 8px;
  padding: 20px 24px;
  display: flex;
  gap: 20px;
  align-items: flex-start;
  margin-bottom: 20px;
}}

.chasm-icon {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.15em;
  color: var(--ember);
  background: {c["ember"]}22;
  padding: 6px 10px;
  border-radius: 4px;
  white-space: nowrap;
}}

.chasm-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--mist);
  text-transform: uppercase;
  margin-bottom: 8px;
}}

.chasm-text p {{
  font-size: 14px;
  color: {c["mist"]};
  line-height: 1.7;
}}

.momentum-block {{
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px 24px;
}}

.momentum-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--gold);
  text-transform: uppercase;
  margin-bottom: 10px;
}}

.momentum-block p {{
  font-size: 14px;
  color: var(--slate);
  line-height: 1.75;
}}

/* ── 互動式事件時間軸 ── */
.tl-container {{
  position: relative;
  padding-left: 52px;
  margin-top: 40px;
}}

.tl-spine {{
  position: absolute;
  left: 20px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: linear-gradient(to bottom, {c["info"]}, {c["gold"]}, {c["teal"]});
  border-radius: 2px;
  opacity: 0.6;
}}

/* 事件卡片 */
.tl-event {{
  position: relative;
  margin-bottom: 24px;
}}

.tl-event-dot {{
  position: absolute;
  left: -40px;
  top: 18px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2.5px solid {c["surface"]};
  z-index: 2;
}}

.tl-event-dot.critical {{ background: {c["error"]}; box-shadow: 0 0 10px rgba(196,64,42,0.5); }}
.tl-event-dot.high {{ background: {c["warning"]}; box-shadow: 0 0 8px rgba(201,148,58,0.4); }}
.tl-event-dot.medium {{ background: {c["gold"]}; }}
.tl-event-dot.low {{ background: {c["teal"]}; }}

.tl-event-card {{
  background: {c["raised"]};
  border: 1px solid {c["border_dark"]};
  border-left: 3px solid;
  border-radius: 8px;
  padding: 16px 20px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}}

.tl-event-card:hover {{
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.2);
}}

.tl-event-card.critical {{ border-left-color: {c["error"]}; }}
.tl-event-card.high {{ border-left-color: {c["warning"]}; }}
.tl-event-card.medium {{ border-left-color: {c["gold"]}; }}
.tl-event-card.low {{ border-left-color: {c["teal"]}; }}

.tl-event-header {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}}

.tl-event-week {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  color: var(--ember);
  background: rgba(196,80,42,0.12);
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.06em;
}}

.tl-event-badge {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 100px;
}}

.tl-event-title {{
  font-family: 'Outfit', 'Noto Sans TC', system-ui;
  font-size: 15px;
  font-weight: 600;
  color: white;
  margin: 0 0 8px 0;
  line-height: 1.4;
}}

.tl-event-narrative {{
  font-size: 13px;
  color: {c["mist"]};
  line-height: 1.75;
  margin: 0 0 10px 0;
}}

.tl-event-impact {{
  font-size: 13px;
  color: {c["mist"]};
  line-height: 1.65;
  padding: 8px 12px;
  background: rgba(196,80,42,0.06);
  border-radius: 6px;
  margin-bottom: 8px;
}}

.tl-event-impact strong {{
  color: {c["ember"]};
  font-weight: 600;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  display: block;
  margin-bottom: 4px;
}}

.tl-event-action {{
  font-size: 13px;
  color: {c["mist"]};
  line-height: 1.65;
  padding: 8px 12px;
  background: rgba(42,122,110,0.08);
  border-radius: 6px;
  margin-bottom: 8px;
}}

.tl-event-action strong {{
  color: {c["teal"]};
  font-weight: 600;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  display: block;
  margin-bottom: 4px;
}}

.event-metrics {{
  display: flex;
  gap: 12px;
  margin-top: 10px;
  flex-wrap: wrap;
}}

.event-metrics span {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  color: {c["slate"]};
  background: {c["surface"]};
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid {c["border_dark"]};
}}

/* 季度回顧卡片 */
.tl-quarter-review {{
  position: relative;
  margin: 36px 0 32px -52px;
  padding-left: 52px;
}}

.tl-quarter-line {{
  position: absolute;
  left: 20px;
  top: 50%;
  width: 32px;
  height: 2px;
  background: var(--q-color, {c["ember"]});
  opacity: 0.6;
}}

.tl-quarter-card {{
  background: rgba(196,80,42,0.04);
  border: 1px dashed rgba(196,80,42,0.3);
  border-radius: 12px;
  padding: 20px 24px;
}}

.tl-quarter-card:hover {{
  background: rgba(196,80,42,0.06);
}}

.tl-quarter-header {{
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}}

.tl-quarter-name {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  line-height: 1.2;
}}

.tl-quarter-weeks {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  color: var(--mist);
  background: rgba(255,255,255,0.06);
  padding: 2px 8px;
  border-radius: 4px;
}}

.quarter-stats {{
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}}

.qs-item {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  color: {c["slate"]};
  background: {c["raised"]};
  border: 1px solid {c["border_dark"]};
  padding: 4px 10px;
  border-radius: 6px;
}}

.qs-label {{
  color: {c["mist"]};
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-right: 4px;
}}

.tl-quarter-row {{
  padding: 8px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}}

.tl-quarter-row:last-child {{ border-bottom: none; }}

.tl-quarter-row.highlight {{
  background: rgba(196,80,42,0.05);
  margin: 4px -8px 0;
  padding: 8px 8px;
  border-radius: 6px;
  border-bottom: none;
}}

.tl-quarter-row-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--ember);
  text-transform: uppercase;
  margin-bottom: 4px;
  display: block;
}}

.tl-quarter-row p {{
  font-size: 13px;
  color: {c["mist"]};
  line-height: 1.7;
  margin: 0;
}}

@media (max-width: 640px) {{
  .tl-container {{ padding-left: 36px; }}
  .tl-spine {{ left: 12px; }}
  .tl-event-dot {{ left: -28px; }}
  .tl-quarter-review {{ margin-left: -36px; padding-left: 36px; }}
  .tl-quarter-line {{ left: 12px; width: 24px; }}
}}

/* ── SWOT ── */
.swot-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 3px;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 16px;
}}

@media (max-width: 640px) {{
  .swot-grid {{ grid-template-columns: 1fr; }}
}}

.swot-cell {{
  padding: 24px;
  min-height: 180px;
}}

.swot-cell.strengths {{ background: rgba(45,138,110,0.08); border: 1px solid rgba(45,138,110,0.2); }}
.swot-cell.weaknesses {{ background: rgba(196,64,42,0.06); border: 1px solid rgba(196,64,42,0.15); }}
.swot-cell.opportunities {{ background: rgba(42,106,138,0.08); border: 1px solid rgba(42,106,138,0.2); }}
.swot-cell.threats {{ background: rgba(201,148,58,0.07); border: 1px solid rgba(201,148,58,0.2); }}

.swot-cell-header {{
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}}

.swot-icon {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 14px;
  font-weight: 700;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}}

.s-icon {{ background: rgba(45,138,110,0.15); color: {c["success"]}; }}
.w-icon {{ background: rgba(196,64,42,0.12); color: {c["error"]}; }}
.o-icon {{ background: rgba(42,106,138,0.15); color: {c["info"]}; }}
.t-icon {{ background: rgba(201,148,58,0.15); color: {c["warning"]}; }}

.swot-cell-title {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
}}

.swot-list {{
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}

.swot-item {{
  font-size: 13px;
  color: var(--slate);
  line-height: 1.55;
  padding-left: 14px;
  position: relative;
}}

.swot-item::before {{
  content: '·';
  position: absolute;
  left: 0;
  color: var(--ember);
  font-weight: 700;
}}

.swot-note {{
  font-size: 12px;
  color: var(--mist);
  font-style: italic;
}}

/* ── Porter 五力 ── */
.porter-layout {{
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 40px;
  align-items: start;
}}

@media (max-width: 800px) {{
  .porter-layout {{ grid-template-columns: 1fr; }}
}}

.porter-row {{
  display: grid;
  grid-template-columns: 110px 56px 1fr;
  gap: 12px;
  align-items: start;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
}}

.porter-row:last-child {{ border-bottom: none; }}

.porter-force-name {{
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}}

.porter-level {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid;
  text-align: center;
  white-space: nowrap;
}}

.porter-analysis {{
  font-size: 13px;
  color: var(--slate);
  line-height: 1.6;
}}

.porter-overall {{
  margin-top: 20px;
  background: {c["parchment"]};
  border-radius: 8px;
  padding: 16px 20px;
}}

.porter-overall-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--ember);
  text-transform: uppercase;
  margin-bottom: 8px;
}}

.porter-overall p {{
  font-size: 14px;
  color: var(--slate);
  line-height: 1.7;
}}

/* ── 4P ── */
.p4-grid {{
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}}

@media (max-width: 700px) {{
  .p4-grid {{ grid-template-columns: 1fr; }}
}}

.p4-card {{
  background: var(--snow);
  border: 1px solid var(--border);
  border-top: 3px solid;
  border-radius: 10px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}}

.p4-card-header {{
  display: flex;
  align-items: center;
  gap: 14px;
}}

.p4-letter {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 28px;
  font-weight: 600;
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}}

.p4-en-name {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 18px;
  font-weight: 600;
  line-height: 1;
}}

.p4-zh-name {{
  font-size: 12px;
  color: var(--mist);
  margin-top: 2px;
}}

.p4-section-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--mist);
  text-transform: uppercase;
  margin-bottom: 6px;
}}

.p4-current {{
  font-size: 13px;
  color: var(--slate);
  padding: 8px 12px;
  background: {c["parchment"]};
  border-radius: 6px;
}}

.p4-recommendation {{
  font-size: 13px;
  color: var(--ink);
  line-height: 1.7;
}}

.p4-energy-basis {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  color: {c["gold"]};
  display: flex;
  gap: 6px;
  align-items: center;
}}

.p4-basis-icon {{
  opacity: 0.7;
}}

/* ── 行動計畫 ── */
.action-plan-container {{
  display: flex;
  flex-direction: column;
  gap: 28px;
}}

.action-phase-block {{
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}}

.action-phase-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 20px 24px;
  border-left: 4px solid;
  background: {c["parchment"]};
  flex-wrap: wrap;
  gap: 12px;
}}

.action-phase-name {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 20px;
  font-weight: 600;
}}

.action-objective {{
  font-size: 13px;
  color: var(--slate);
  margin-top: 4px;
}}

.action-budget {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  background: white;
  border-radius: 4px;
  border: 1px solid var(--border);
  white-space: nowrap;
}}

.action-rows {{
  padding: 12px 24px;
}}

.action-row {{
  display: flex;
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid {c["parchment"]};
  align-items: flex-start;
}}

.action-row:last-child {{ border-bottom: none; }}

.action-num {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}}

.action-content {{
  flex: 1;
}}

.action-title {{
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  margin-bottom: 8px;
}}

.action-meta-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}}

.action-meta-item {{
  font-size: 12px;
  color: var(--mist);
  display: flex;
  gap: 4px;
  align-items: center;
}}

.action-meta-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--slate);
  text-transform: uppercase;
}}

.action-meta-item strong {{
  color: var(--success);
}}

/* ── 風險矩陣 ── */
.risk-matrix-header {{
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 24px;
}}

.risk-axis-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--mist);
  text-transform: uppercase;
}}

.y-label {{ text-align: left; margin-bottom: 4px; }}
.x-label {{ text-align: right; margin-top: 4px; }}

.risk-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 3px;
  border-radius: 10px;
  overflow: hidden;
}}

@media (max-width: 640px) {{
  .risk-grid {{ grid-template-columns: 1fr; }}
}}

.risk-cell {{
  padding: 20px;
  min-height: 160px;
}}

.risk-cell.critical {{ background: rgba(196,64,42,0.08); border: 1px solid rgba(196,64,42,0.2); }}
.risk-cell.prepare {{ background: rgba(201,148,58,0.07); border: 1px solid rgba(201,148,58,0.2); }}
.risk-cell.monitor {{ background: rgba(42,106,138,0.07); border: 1px solid rgba(42,106,138,0.15); }}
.risk-cell.accept {{ background: rgba(45,138,110,0.06); border: 1px solid rgba(45,138,110,0.15); }}

.risk-cell-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  flex-wrap: wrap;
  gap: 6px;
}}

.risk-cell-badge {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.06em;
  padding: 3px 8px;
  border-radius: 100px;
}}

.critical-badge {{ background: rgba(196,64,42,0.15); color: {c["error"]}; }}
.prepare-badge {{ background: rgba(201,148,58,0.15); color: {c["warning"]}; }}
.monitor-badge {{ background: rgba(42,106,138,0.15); color: {c["info"]}; }}
.accept-badge {{ background: rgba(45,138,110,0.12); color: {c["success"]}; }}

.risk-cell-title {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
}}

.risk-item {{
  padding: 10px 0;
  border-bottom: 1px dashed var(--border);
}}

.risk-item:last-child {{ border-bottom: none; }}

.risk-name {{
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  margin-bottom: 4px;
}}

.risk-mitigation {{
  font-size: 12px;
  color: var(--slate);
  line-height: 1.5;
}}

.risk-empty {{
  font-size: 12px;
  color: var(--mist);
  font-style: italic;
  padding: 8px 0;
}}

/* ── 免責聲明 ── */
.disclaimer {{
  margin-top: 32px;
  padding: 16px 20px;
  background: {c["parchment"]};
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  color: var(--mist);
  line-height: 1.6;
}}

/* ── 動效 ── */
.page {{
  animation: fadeUp 0.4s ease-out;
}}

@keyframes fadeUp {{
  from {{ opacity: 0; transform: translateY(12px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

/* ── 印刷友善 ── */
@media print {{
  .top-nav {{ display: none; }}
  .report-wrap {{ padding-top: 0; }}
  .page {{ page-break-after: always; min-height: auto; }}
  body {{ background: white; }}
  .cover-page {{ background: #0E0E16; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .energy-main-grid, .phase-grid, .p4-grid, .risk-grid {{ grid-template-columns: 1fr; }}
  .porter-layout {{ grid-template-columns: 1fr; }}
  .kpi-grid {{ grid-template-columns: repeat(3, 1fr); }}
}}
'''


# ──────────────────────────────────────────────────────────────
# 向後相容：保留舊版 auto_insights 輔助函數（供 fallback 使用）
# ──────────────────────────────────────────────────────────────

def _auto_insights(district, inner, outer, final_state, tam, population):
    insights = []
    top_inner = max(inner.items(), key=lambda x: x[1]) if inner else ("—", 0)
    top_outer = max(outer.items(), key=lambda x: x[1]) if outer else ("—", 0)
    insights.append(
        f"{district} 的內在主導能量為「{top_inner[0]}」（{top_inner[1]:+.1f}），"
        f"外在主導能量為「{top_outer[0]}」（{top_outer[1]:+.1f}）。"
    )
    loyal_ratio = final_state.get("loyal", {}).get("ratio", 0)
    decided_ratio = final_state.get("decided", {}).get("ratio", 0)
    conversion = (loyal_ratio + decided_ratio) * 100
    insights.append(f"模擬採用率達 {conversion:.1f}%（決定 + 忠實），TAM 約 {int(conversion / 100 * tam):,} 人完成轉換。")
    return insights
