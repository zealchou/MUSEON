"""探索報告生成器 — 將探索結果轉為符合品牌規範的 HTML 報告."""

import logging
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 動機中英對照
_MOTIVATION_ZH = {
    "curiosity": "好奇心驅動",
    "world": "世界脈動",
    "skill": "技能精進",
    "self": "自我反思",
    "mission": "使命探索",
    "morning": "晨間巡禮",
    "idle": "閒置時自主探索",
}


def generate_html_report(data: Dict[str, Any], output_dir: Path) -> Path:
    """將探索結果轉為 HTML 報告檔案.

    Args:
        data: PulseDB exploration 記錄，含 topic, motivation, findings,
              crystallized, timestamp, duration_ms, cost_usd 等欄位
        output_dir: 輸出目錄

    Returns:
        生成的 HTML 檔案路徑
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    topic = escape(data.get("topic", "未知主題"))
    motivation_raw = data.get("motivation", "")
    motivation = escape(_MOTIVATION_ZH.get(motivation_raw, motivation_raw))
    findings = data.get("findings", "")
    crystallized = data.get("crystallized", 0)
    timestamp = data.get("timestamp", "")
    duration_ms = data.get("duration_ms", 0)
    cost_usd = data.get("cost_usd", 0.0)

    # 格式化時間
    try:
        dt = datetime.fromisoformat(timestamp) if timestamp else datetime.now()
        time_str = dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        time_str = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")

    # 格式化耗時
    if duration_ms and duration_ms > 0:
        duration_sec = duration_ms / 1000
        if duration_sec >= 60:
            duration_str = f"{duration_sec / 60:.1f} 分鐘"
        else:
            duration_str = f"{duration_sec:.1f} 秒"
    else:
        duration_str = "—"

    # 格式化費用
    cost_str = f"${cost_usd:.4f}" if cost_usd else "—"

    # 結晶狀態
    crystal_html = (
        '<span style="display:inline-block;padding:3px 10px;'
        "background:rgba(184,146,58,0.15);color:#B8923A;"
        "border-radius:100px;font-family:'IBM Plex Mono',monospace;"
        'font-size:11px;font-weight:600;letter-spacing:0.08em;">'
        "CRYSTALLIZED</span>"
        if crystallized
        else '<span style="display:inline-block;padding:3px 10px;'
        "background:rgba(152,152,168,0.15);color:#5A5A6E;"
        "border-radius:100px;font-family:'IBM Plex Mono',monospace;"
        'font-size:11px;font-weight:600;letter-spacing:0.08em;">'
        "PENDING</span>"
    )

    # 處理 findings — 段落分隔
    findings_paragraphs = ""
    if findings:
        for para in findings.split("\n"):
            para = para.strip()
            if para:
                findings_paragraphs += (
                    f'<p style="margin:0 0 1.25em 0;line-height:1.75;">'
                    f"{escape(para)}</p>\n"
                )
    else:
        findings_paragraphs = (
            '<p style="margin:0;color:#9898A8;font-style:italic;">無探索發現</p>'
        )

    # 檔名
    ts_slug = dt.strftime("%Y%m%d_%H%M%S") if isinstance(dt, datetime) else "report"
    filename = f"explore_{ts_slug}.html"
    filepath = output_dir / filename

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MUSEON 探索報告 — {topic}</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=Outfit:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+TC:wght@400;500&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#F7F5F0;font-family:'Outfit','Noto Sans TC',sans-serif;color:#12121A;">

<div style="max-width:820px;margin:0 auto;padding:48px 40px;">

  <!-- Header -->
  <div style="margin-bottom:48px;">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
      <span style="display:inline-block;padding:3px 10px;background:rgba(196,80,42,0.1);color:#9A3A1C;border-radius:100px;font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:600;letter-spacing:0.08em;">EXPLORATION</span>
      {crystal_html}
    </div>
    <h1 style="margin:0 0 8px 0;font-family:'Cormorant Garamond',serif;font-size:40px;font-weight:600;line-height:1.2;color:#12121A;">
      {topic}
    </h1>
    <p style="margin:0;font-size:14px;color:#5A5A6E;line-height:1.7;">
      {motivation} &middot; {time_str}
    </p>
  </div>

  <!-- Findings Card -->
  <div style="background:#FDFCFA;border:1px solid #E2E0DA;border-radius:10px;padding:24px;margin-bottom:32px;box-shadow:0 1px 3px rgba(18,18,26,0.06),0 4px 12px rgba(18,18,26,0.04);">
    <h2 style="margin:0 0 16px 0;font-family:'Outfit','Noto Sans TC',sans-serif;font-size:18px;font-weight:600;color:#C4502A;">
      主要發現
    </h2>
    <div style="font-size:16px;color:#12121A;">
      {findings_paragraphs}
    </div>
  </div>

  <!-- Stats -->
  <div style="display:flex;gap:16px;flex-wrap:wrap;">
    <div style="flex:1;min-width:120px;background:#FDFCFA;border:1px solid #E2E0DA;border-radius:10px;padding:16px;text-align:center;">
      <div style="font-size:12px;font-weight:500;color:#5A5A6E;margin-bottom:4px;">耗時</div>
      <div style="font-size:18px;font-weight:600;color:#12121A;">{duration_str}</div>
    </div>
    <div style="flex:1;min-width:120px;background:#FDFCFA;border:1px solid #E2E0DA;border-radius:10px;padding:16px;text-align:center;">
      <div style="font-size:12px;font-weight:500;color:#5A5A6E;margin-bottom:4px;">成本</div>
      <div style="font-size:18px;font-weight:600;color:#12121A;">{cost_str}</div>
    </div>
    <div style="flex:1;min-width:120px;background:#FDFCFA;border:1px solid #E2E0DA;border-radius:10px;padding:16px;text-align:center;">
      <div style="font-size:12px;font-weight:500;color:#5A5A6E;margin-bottom:4px;">結晶</div>
      <div style="font-size:18px;font-weight:600;color:{'#B8923A' if crystallized else '#9898A8'};">{'是' if crystallized else '否'}</div>
    </div>
  </div>

  <!-- Footer -->
  <div style="margin-top:48px;padding-top:16px;border-top:1px solid #E2E0DA;text-align:center;">
    <span style="font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:500;color:#9898A8;letter-spacing:0.08em;">
      MUSEON AUTONOMOUS EXPLORATION
    </span>
  </div>

</div>
</body>
</html>"""

    filepath.write_text(html, encoding="utf-8")
    logger.info(f"Exploration report generated: {filepath}")
    return filepath
