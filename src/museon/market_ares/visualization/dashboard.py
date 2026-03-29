"""Market Ares — 互動式 HTML 儀表板生成器

生成帶時間軸控制器的 52 週模擬結果儀表板。
"""

from __future__ import annotations

import json
from pathlib import Path

from museon.market_ares.storage.models import WeeklySnapshot
from museon.market_ares.visualization.charts import (
    line_chart_option,
    pie_chart_option,
    radar_chart_option,
)


def generate_dashboard_html(
    snapshots: list[WeeklySnapshot],
    city: str,
    strategy_desc: str,
    output_path: str | Path | None = None,
) -> str:
    """生成完整的互動式儀表板 HTML

    Args:
        snapshots: 52 週快照列表
        city: 城市名稱
        strategy_desc: 策略描述
        output_path: 輸出路徑（可選，傳入則同時寫檔）

    Returns:
        完整的 HTML 字串
    """
    # 準備各週數據
    weeks_data = json.dumps([_snapshot_to_dict(s) for s in snapshots], ensure_ascii=False)

    # 趨勢數據
    trend_data = _build_trend_data(snapshots)
    trend_json = json.dumps(trend_data, ensure_ascii=False)

    html = _DASHBOARD_TEMPLATE.format(
        city=city,
        strategy=strategy_desc,
        total_weeks=len(snapshots),
        weeks_data=weeks_data,
        trend_data=trend_json,
    )

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

    return html


def _snapshot_to_dict(s: WeeklySnapshot) -> dict:
    m = s.business_metrics
    return {
        "week": s.week,
        "penetration": round(m.get("penetration_rate", 0) * 100, 1),
        "fans": round(m.get("fan_ratio", 0) * 100, 1),
        "nps": round(m.get("nps", 0), 0),
        "revenue": round(m.get("revenue_index", 0), 0),
        "reputation": round(m.get("reputation_score", 0), 1),
        "distribution": m.get("state_distribution", {}),
        "insight": s.insight,
        "is_turning_point": s.is_turning_point,
        "events": s.events,
        "competitors": s.competitor_actions,
        "partners": s.partner_attitudes,
    }


def _build_trend_data(snapshots: list[WeeklySnapshot]) -> dict:
    return {
        "weeks": [s.week for s in snapshots],
        "penetration": [round(s.business_metrics.get("penetration_rate", 0) * 100, 1) for s in snapshots],
        "fans": [round(s.business_metrics.get("fan_ratio", 0) * 100, 1) for s in snapshots],
        "nps": [round(s.business_metrics.get("nps", 0), 0) for s in snapshots],
        "revenue": [round(s.business_metrics.get("revenue_index", 0), 0) for s in snapshots],
    }


_DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Ares — {city} 策略模擬</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=Outfit:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+TC:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--ember:#C4502A;--teal:#2A7A6E;--gold:#B8923A;--ink:#12121A;--slate:#5A5A6E;--mist:#9898A8;--surface:#16161F;--deep:#0E0E16;--border:rgba(255,255,255,0.06);--snow:#FDFCFA;--success:#2D8A6E;--error:#C4402A}}
body{{font-family:'Outfit','Noto Sans TC',sans-serif;background:var(--deep);color:var(--snow);line-height:1.6;font-size:15px}}
.header{{background:var(--surface);padding:20px 24px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}}
.header h1{{font-family:'Cormorant Garamond',serif;font-size:24px;font-weight:600}}
.header h1 span{{color:var(--ember)}}
.header .meta{{font-size:13px;color:var(--mist)}}
.container{{max-width:1200px;margin:0 auto;padding:24px}}
.timeline{{background:var(--surface);border-radius:10px;padding:20px 24px;margin-bottom:24px;border:1px solid var(--border)}}
.timeline-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}
.timeline-header .week-label{{font-family:'Cormorant Garamond',serif;font-size:28px;font-weight:600}}
.timeline-header .week-label .tp{{color:var(--ember);font-size:12px;font-family:'IBM Plex Mono',monospace;vertical-align:super}}
.timeline-controls{{display:flex;gap:8px;align-items:center}}
.timeline-controls button{{background:var(--ember);border:none;color:#fff;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600}}
.timeline-controls button:hover{{background:#E0714D}}
.timeline-controls button.ghost{{background:transparent;border:1px solid rgba(255,255,255,0.15);color:var(--mist)}}
.slider-wrap{{position:relative}}
input[type=range]{{width:100%;-webkit-appearance:none;background:rgba(255,255,255,0.08);height:6px;border-radius:3px;outline:none}}
input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;width:18px;height:18px;background:var(--ember);border-radius:50%;cursor:pointer}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
@media(max-width:768px){{.metrics{{grid-template-columns:repeat(2,1fr)}}}}
.metric-card{{background:var(--surface);border-radius:8px;padding:20px;border:1px solid var(--border)}}
.metric-card .label{{font-size:12px;color:var(--mist);margin-bottom:6px;font-weight:500}}
.metric-card .value{{font-family:'Cormorant Garamond',serif;font-size:32px;font-weight:600}}
.metric-card .delta{{font-family:'IBM Plex Mono',monospace;font-size:12px;margin-top:4px}}
.metric-card .delta.up{{color:var(--success)}}
.metric-card .delta.down{{color:var(--error)}}
.charts-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}}
@media(max-width:768px){{.charts-grid{{grid-template-columns:1fr}}}}
.chart-card{{background:var(--surface);border-radius:10px;padding:16px;border:1px solid var(--border);min-height:300px}}
.insight-box{{background:rgba(196,80,42,0.08);border-left:3px solid var(--ember);border-radius:0 8px 8px 0;padding:20px 24px;margin-bottom:24px}}
.insight-box .insight-label{{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--ember);margin-bottom:8px}}
.insight-box p{{color:#D0CEC8;line-height:1.7}}
.events-bar{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}}
.event-tag{{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;background:rgba(196,80,42,0.15);color:#E0714D;padding:3px 10px;border-radius:100px}}
.footer{{text-align:center;padding:24px;color:var(--mist);font-size:12px;border-top:1px solid var(--border);margin-top:48px}}
</style>
</head>
<body>

<div class="header">
  <h1>Market <span>Ares</span> — {city}</h1>
  <div class="meta">{strategy} | {total_weeks} 週模擬</div>
</div>

<div class="container">
  <!-- 時間軸控制器 -->
  <div class="timeline">
    <div class="timeline-header">
      <div class="week-label">Week <span id="currentWeek">1</span> / {total_weeks} <span class="tp" id="tpBadge" style="display:none">TURNING POINT</span></div>
      <div class="timeline-controls">
        <button class="ghost" onclick="prevWeek()">◀ 上一週</button>
        <button onclick="togglePlay()" id="playBtn">▶ 播放</button>
        <button class="ghost" onclick="nextWeek()">下一週 ▶</button>
      </div>
    </div>
    <div class="slider-wrap">
      <input type="range" id="weekSlider" min="1" max="{total_weeks}" value="1" oninput="goToWeek(this.value)">
    </div>
  </div>

  <!-- 事件標籤 -->
  <div class="events-bar" id="eventsBar"></div>

  <!-- 商業指標卡片 -->
  <div class="metrics">
    <div class="metric-card"><div class="label">市場滲透率</div><div class="value" id="metPenetration" style="color:var(--teal)">0%</div><div class="delta" id="deltaPenetration"></div></div>
    <div class="metric-card"><div class="label">鐵粉比例</div><div class="value" id="metFans" style="color:var(--gold)">0%</div><div class="delta" id="deltaFans"></div></div>
    <div class="metric-card"><div class="label">NPS 淨推薦值</div><div class="value" id="metNPS">0</div><div class="delta" id="deltaNPS"></div></div>
    <div class="metric-card"><div class="label">營收指數</div><div class="value" id="metRevenue" style="color:var(--ember)">0</div><div class="delta" id="deltaRevenue"></div></div>
  </div>

  <!-- 圖表 -->
  <div class="charts-grid">
    <div class="chart-card" id="chartDistribution" style="min-height:280px"></div>
    <div class="chart-card" id="chartTrend" style="min-height:280px"></div>
  </div>

  <!-- 洞察 -->
  <div class="insight-box" id="insightBox">
    <div class="insight-label">本週洞察</div>
    <p id="insightText">載入中...</p>
  </div>
</div>

<div class="footer">
  Market Ares 策略模擬引擎 — Powered by MUSEON &amp; One Muse 八方位能量系統
</div>

<script>
const weeksData = {weeks_data};
const trendData = {trend_data};
let currentIdx = 0;
let playing = false;
let playTimer = null;

// 初始化圖表
const distChart = echarts.init(document.getElementById('chartDistribution'), 'dark');
const trendChart = echarts.init(document.getElementById('chartTrend'), 'dark');

// 趨勢圖（靜態，只初始化一次）
trendChart.setOption({{
  backgroundColor: 'transparent',
  title: {{text: '52 週趨勢', textStyle: {{color: '#FDFCFA', fontSize: 14}}}},
  tooltip: {{trigger: 'axis'}},
  legend: {{data: ['滲透率%', '鐵粉%', 'NPS'], textStyle: {{color: '#9898A8'}}, top: 30}},
  grid: {{left: 50, right: 20, top: 65, bottom: 30}},
  xAxis: {{type: 'category', data: trendData.weeks.map(w => 'W'+w), axisLabel: {{color: '#9898A8'}}, axisLine: {{lineStyle: {{color: '#2A2A38'}}}}}},
  yAxis: {{type: 'value', axisLabel: {{color: '#9898A8'}}, splitLine: {{lineStyle: {{color: 'rgba(255,255,255,0.04)'}}}}}},
  series: [
    {{name: '滲透率%', type: 'line', data: trendData.penetration, smooth: true, lineStyle: {{color: '#2A7A6E'}}, itemStyle: {{color: '#2A7A6E'}}}},
    {{name: '鐵粉%', type: 'line', data: trendData.fans, smooth: true, lineStyle: {{color: '#B8923A'}}, itemStyle: {{color: '#B8923A'}}}},
    {{name: 'NPS', type: 'line', data: trendData.nps, smooth: true, lineStyle: {{color: '#C4502A'}}, itemStyle: {{color: '#C4502A'}}}},
  ]
}});

function goToWeek(w) {{
  currentIdx = parseInt(w) - 1;
  updateDisplay();
}}
function prevWeek() {{ if (currentIdx > 0) {{ currentIdx--; updateDisplay(); }} }}
function nextWeek() {{ if (currentIdx < weeksData.length - 1) {{ currentIdx++; updateDisplay(); }} }}
function togglePlay() {{
  playing = !playing;
  document.getElementById('playBtn').textContent = playing ? '⏸ 暫停' : '▶ 播放';
  if (playing) {{ playTimer = setInterval(() => {{ if (currentIdx < weeksData.length - 1) {{ currentIdx++; updateDisplay(); }} else {{ togglePlay(); }} }}, 800); }}
  else {{ clearInterval(playTimer); }}
}}

function updateDisplay() {{
  const d = weeksData[currentIdx];
  const prev = currentIdx > 0 ? weeksData[currentIdx - 1] : null;

  document.getElementById('currentWeek').textContent = d.week;
  document.getElementById('weekSlider').value = d.week;
  document.getElementById('tpBadge').style.display = d.is_turning_point ? 'inline' : 'none';

  // 指標
  document.getElementById('metPenetration').textContent = d.penetration + '%';
  document.getElementById('metFans').textContent = d.fans + '%';
  document.getElementById('metNPS').textContent = d.nps;
  document.getElementById('metRevenue').textContent = d.revenue;

  // Delta
  if (prev) {{
    setDelta('deltaPenetration', d.penetration - prev.penetration, '%');
    setDelta('deltaFans', d.fans - prev.fans, '%');
    setDelta('deltaNPS', d.nps - prev.nps, '');
    setDelta('deltaRevenue', d.revenue - prev.revenue, '');
  }}

  // 圓餅圖
  const distData = Object.entries(d.distribution).filter(([k,v]) => v > 0.001).map(([k,v]) => ({{
    value: Math.round(v * 1000) / 10, name: k,
    itemStyle: {{color: {{unaware:'#5A5A6E',aware:'#2A6A8A',considering:'#B8923A',decided:'#2A7A6E',loyal:'#C4502A',resistant:'#C4402A'}}[k] || '#5A5A6E'}}
  }}));
  distChart.setOption({{
    backgroundColor: 'transparent',
    title: {{text: '狀態分布', textStyle: {{color: '#FDFCFA', fontSize: 14}}}},
    tooltip: {{trigger: 'item', formatter: '{{b}}: {{c}}%'}},
    series: [{{type: 'pie', radius: ['35%','65%'], data: distData, label: {{color: '#FDFCFA', fontSize: 12}}}}]
  }});

  // 趨勢圖標線
  trendChart.setOption({{
    series: [
      {{markLine: {{data: [{{xAxis: 'W'+d.week}}], lineStyle: {{color: 'rgba(255,255,255,0.3)', type: 'dashed'}}, label: {{show: false}}}}}},
      {{}}, {{}}
    ]
  }});

  // 事件
  const evBar = document.getElementById('eventsBar');
  evBar.innerHTML = (d.events || []).map(e => '<span class="event-tag">' + (e.name || '') + '</span>').join('');

  // 洞察
  document.getElementById('insightText').textContent = d.insight || '本週市場穩定，無重大變化。';
}}

function setDelta(id, val, suffix) {{
  const el = document.getElementById(id);
  if (Math.abs(val) < 0.05) {{ el.textContent = ''; return; }}
  const sign = val > 0 ? '▲ +' : '▼ ';
  el.textContent = sign + Math.abs(Math.round(val * 10) / 10) + suffix + ' vs 上週';
  el.className = 'delta ' + (val > 0 ? 'up' : 'down');
}}

// 初始化
updateDisplay();
window.addEventListener('resize', () => {{ distChart.resize(); trendChart.resize(); }});
</script>
</body>
</html>"""
