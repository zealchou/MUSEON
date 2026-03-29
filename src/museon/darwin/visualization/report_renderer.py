"""Market Ares — 最終報告 HTML 渲染器

將 LLM 生成的 Markdown 報告 + 圖表數據渲染為精美 HTML。
"""

from __future__ import annotations

from pathlib import Path

from museon.darwin.analysis.final_report import build_report_sections_data
from museon.darwin.storage.models import WeeklySnapshot


def render_report_html(
    report_markdown: str,
    snapshots: list[WeeklySnapshot],
    city: str,
    strategy: str,
    output_path: str | Path | None = None,
) -> str:
    """渲染最終報告 HTML"""
    data = build_report_sections_data(snapshots)

    verdict_colors = {"green": "#2D8A6E", "yellow": "#C9943A", "red": "#C4402A"}
    verdict_icons = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

    # 將 Markdown 轉為 HTML（簡易版）
    report_html = _markdown_to_html(report_markdown)

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Ares — {city} 戰情報告</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Outfit:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+TC:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Outfit','Noto Sans TC',sans-serif;background:#F7F5F0;color:#12121A;line-height:1.75;font-size:16px}}
.report-header{{background:linear-gradient(160deg,#0E0E16,#1c1418);color:#FDFCFA;padding:80px 24px 48px;text-align:center}}
.report-header h1{{font-family:'Cormorant Garamond',serif;font-size:48px;font-weight:600;margin-bottom:8px}}
.report-header h1 span{{color:#C4502A}}
.report-header .meta{{color:#9898A8;font-size:15px}}
.verdict-banner{{text-align:center;padding:32px;border-bottom:1px solid #E2E0DA}}
.verdict-banner .icon{{font-size:48px;margin-bottom:8px}}
.verdict-banner .text{{font-size:24px;font-weight:600;color:{verdict_colors[data['verdict']]}}}
.verdict-banner .stats{{display:flex;justify-content:center;gap:48px;margin-top:16px;color:#5A5A6E;font-size:14px}}
.verdict-banner .stats .num{{font-family:'Cormorant Garamond',serif;font-size:28px;font-weight:600;color:#12121A;display:block}}
.container{{max-width:820px;margin:0 auto;padding:48px 24px}}
.container h2{{font-family:'Cormorant Garamond',serif;font-size:32px;font-weight:600;margin:48px 0 16px;padding-top:32px;border-top:1px solid #E2E0DA}}
.container h3{{font-size:20px;font-weight:600;margin:24px 0 8px}}
.container p{{margin-bottom:16px}}
.container ul,.container ol{{margin:8px 0 16px 24px}}
.container li{{margin-bottom:6px}}
.container blockquote{{background:#FDFCFA;border-left:3px solid #C4502A;padding:16px 20px;margin:16px 0;border-radius:0 8px 8px 0;color:#5A5A6E}}
.container code{{font-family:'IBM Plex Mono',monospace;background:#F0EDE8;padding:2px 6px;border-radius:4px;font-size:14px}}
.footer{{text-align:center;padding:32px;color:#9898A8;font-size:12px;border-top:1px solid #E2E0DA;margin-top:48px}}
</style>
</head>
<body>

<div class="report-header">
  <h1>Market <span>Ares</span></h1>
  <div class="meta">{city} — {strategy} — 52 週戰情報告</div>
</div>

<div class="verdict-banner">
  <div class="icon">{verdict_icons[data['verdict']]}</div>
  <div class="text">策略判定：{data['verdict_text']}</div>
  <div class="stats">
    <div>滲透率<span class="num">{data['final_penetration']}%</span></div>
    <div>鐵粉<span class="num">{data['final_fans']}%</span></div>
    <div>NPS<span class="num">{data['final_nps']}</span></div>
    <div>營收指數<span class="num">{data['final_revenue']}</span></div>
    <div>轉折點<span class="num">{data['total_turning_points']}</span></div>
  </div>
</div>

<div class="container">
{report_html}
</div>

<div class="footer">
  Market Ares 策略模擬引擎 — Powered by MUSEON &amp; One Muse<br>
  本報告由 AI 模擬生成，結果為趨勢預測而非精確預測。實際結果取決於執行品質。
</div>

</body>
</html>"""

    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

    return html


def _markdown_to_html(md: str) -> str:
    """簡易 Markdown→HTML 轉換"""
    import re

    lines = md.split("\n")
    html_lines = []
    in_list = False
    in_ol = False

    for line in lines:
        stripped = line.strip()

        # Headers
        if stripped.startswith("# "):
            html_lines.append(f"<h2>{stripped[2:]}</h2>")
        elif stripped.startswith("## "):
            html_lines.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("### "):
            html_lines.append(f"<h3>{stripped[4:]}</h3>")
        # Unordered list
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{stripped[2:]}</li>")
        # Ordered list
        elif re.match(r"^\d+\.\s", stripped):
            if not in_ol:
                html_lines.append("<ol>")
                in_ol = True
            html_lines.append(f"<li>{re.sub(r'^\d+\.\s', '', stripped)}</li>")
        # Blockquote
        elif stripped.startswith(">"):
            html_lines.append(f"<blockquote>{stripped[1:].strip()}</blockquote>")
        # Empty line
        elif not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            html_lines.append("")
        # Paragraph
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            # Bold
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            # Inline code
            text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
            html_lines.append(f"<p>{text}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_ol:
        html_lines.append("</ol>")

    return "\n".join(html_lines)
