#!/usr/bin/env python3
"""MUSEON 迭代報告生成器.

接收 JSON stdin → 生成 MUSEON 品牌 HTML → 上傳 GitHub Gist → 回傳 URL。

JSON 輸入格式：
{
    "title": "報告標題",
    "summary": "一句話摘要",
    "sections": [
        {
            "title": "段落標題",
            "content": "段落內容（支援 markdown）",
            "status": "ok|warning|error|info"
        }
    ],
    "metadata": {
        "commit_hash": "abc1234",
        "files_changed": 5,
        "tests_passed": true
    }
}

用法：
    echo '{"title":"test","sections":[{"title":"s1","content":"ok","status":"ok"}]}' | python3 scripts/generate_iteration_report.py
    cat report.json | python3 scripts/generate_iteration_report.py --no-upload
"""

import json
import os
import sys
from datetime import datetime

# ── MUSEON 品牌色系（來自 design_spec.md）──
COLORS = {
    "ember": "#C4502A",
    "ember_light": "#E0714D",
    "ember_dark": "#9A3A1C",
    "teal": "#2A7A6E",
    "gold": "#B8923A",
    "ink": "#12121A",
    "slate": "#5A5A6E",
    "mist": "#9898A8",
    "border": "#E2E0DA",
    "parchment": "#F7F5F0",
    "snow": "#FDFCFA",
    "success": "#2D8A6E",
    "warning": "#C9943A",
    "error": "#C4402A",
    "info": "#2A6A8A",
}

STATUS_MAP = {
    "ok": {"color": COLORS["success"], "icon": "\u2705", "label": "\u901a\u904e"},
    "warning": {"color": COLORS["warning"], "icon": "\u26a0\ufe0f", "label": "\u8b66\u544a"},
    "error": {"color": COLORS["error"], "icon": "\u274c", "label": "\u932f\u8aa4"},
    "info": {"color": COLORS["info"], "icon": "\u2139\ufe0f", "label": "\u8cc7\u8a0a"},
}

GIST_API = "https://api.github.com/gists"


def _build_html(data: dict) -> str:
    """Generate MUSEON-branded HTML report."""
    title = data.get("title", "MUSEON \u8fed\u4ee3\u5831\u544a")
    summary = data.get("summary", "")
    sections = data.get("sections", [])
    metadata = data.get("metadata", {})
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build sections HTML
    sections_html = ""
    for sec in sections:
        st = STATUS_MAP.get(sec.get("status", "info"), STATUS_MAP["info"])
        content = sec.get("content", "").replace("\n", "<br>")
        sections_html += f"""
        <div class="section-card">
            <div class="section-header">
                <span class="status-badge" style="background:{st['color']}">{st['icon']} {st['label']}</span>
                <h3>{sec.get('title', '')}</h3>
            </div>
            <div class="section-content">{content}</div>
        </div>"""

    # Build metadata HTML
    meta_html = ""
    if metadata:
        meta_items = []
        if metadata.get("commit_hash"):
            meta_items.append(f"<span class='meta-item'>Commit: <code>{metadata['commit_hash'][:8]}</code></span>")
        if metadata.get("files_changed") is not None:
            meta_items.append(f"<span class='meta-item'>\u6a94\u6848\u8b8a\u66f4: {metadata['files_changed']}</span>")
        if metadata.get("tests_passed") is not None:
            icon = "\u2705" if metadata["tests_passed"] else "\u274c"
            meta_items.append(f"<span class='meta-item'>\u6e2c\u8a66: {icon}</span>")
        meta_html = " | ".join(meta_items)

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} - MUSEON</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=Outfit:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Noto+Sans+TC:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{
    --ember: {COLORS['ember']};
    --ember-light: {COLORS['ember_light']};
    --ember-dark: {COLORS['ember_dark']};
    --teal: {COLORS['teal']};
    --gold: {COLORS['gold']};
    --ink: {COLORS['ink']};
    --slate: {COLORS['slate']};
    --mist: {COLORS['mist']};
    --border: {COLORS['border']};
    --parchment: {COLORS['parchment']};
    --snow: {COLORS['snow']};
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: 'Outfit', 'Noto Sans TC', sans-serif;
    background: var(--parchment);
    color: var(--ink);
    line-height: 1.75;
    padding: 2rem;
    max-width: 800px;
    margin: 0 auto;
}}
.report-header {{
    text-align: center;
    padding: 2rem 0;
    border-bottom: 2px solid var(--border);
    margin-bottom: 2rem;
}}
.report-header h1 {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 2.2rem;
    font-weight: 600;
    color: var(--ember);
    margin-bottom: 0.5rem;
}}
.report-header .summary {{
    color: var(--slate);
    font-size: 1rem;
}}
.report-header .timestamp {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    color: var(--mist);
    margin-top: 0.5rem;
    letter-spacing: 0.05em;
}}
.meta-bar {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.8rem;
    color: var(--slate);
    padding: 0.75rem 1rem;
    background: var(--snow);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 1.5rem;
    text-align: center;
}}
.meta-item {{ margin: 0 0.5rem; }}
.meta-item code {{
    background: #F0EDE8;
    padding: 0.1em 0.4em;
    border-radius: 3px;
    font-size: 0.85em;
}}
.section-card {{
    background: var(--snow);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
}}
.section-header {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
}}
.section-header h3 {{
    font-size: 1.1rem;
    font-weight: 600;
}}
.status-badge {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    font-weight: 600;
    color: white;
    padding: 0.2em 0.6em;
    border-radius: 4px;
    letter-spacing: 0.05em;
    white-space: nowrap;
}}
.section-content {{
    font-size: 0.95rem;
    color: var(--slate);
    line-height: 1.8;
}}
.footer {{
    text-align: center;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.7rem;
    color: var(--mist);
    letter-spacing: 0.08em;
}}
</style>
</head>
<body>
<div class="report-header">
    <h1>{title}</h1>
    {"<p class='summary'>" + summary + "</p>" if summary else ""}
    <p class="timestamp">MUSEON Iteration Report \u00b7 {now}</p>
</div>
{"<div class='meta-bar'>" + meta_html + "</div>" if meta_html else ""}
{sections_html}
<div class="footer">MUSEON \u00b7 \u58c1\u7210\u65c1\u7684\u7cbe\u5bc6\u5100\u5668</div>
</body>
</html>"""


def _upload_to_gist(html: str, title: str) -> str | None:
    """Upload HTML to GitHub Gist, return raw URL."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("WARN: GITHUB_TOKEN not set, skipping Gist upload", file=sys.stderr)
        return None

    try:
        import httpx
    except ImportError:
        print("WARN: httpx not available, skipping Gist upload", file=sys.stderr)
        return None

    date_str = datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"museon-iteration-{date_str}.html"
    payload = {
        "description": f"MUSEON: {title}",
        "public": True,
        "files": {filename: {"content": html}},
    }

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                GIST_API,
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json=payload,
            )
            if resp.status_code == 201:
                data = resp.json()
                raw_url = data["files"][filename]["raw_url"]
                gist_url = data["html_url"]
                print(f"Gist uploaded: {gist_url}", file=sys.stderr)
                return raw_url
            else:
                print(
                    f"Gist upload failed: {resp.status_code} {resp.text[:200]}",
                    file=sys.stderr,
                )
                return None
    except Exception as e:
        print(f"Gist upload error: {e}", file=sys.stderr)
        return None


def main():
    no_upload = "--no-upload" in sys.argv

    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    html = _build_html(data)
    title = data.get("title", "Iteration Report")

    if no_upload:
        # Output HTML to stdout
        print(html)
    else:
        url = _upload_to_gist(html, title)
        result = {"title": title, "html_length": len(html)}
        if url:
            result["url"] = url
        print(json.dumps(result))


if __name__ == "__main__":
    main()
