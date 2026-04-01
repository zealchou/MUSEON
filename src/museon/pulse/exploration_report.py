"""探索報告生成器 — 將探索結果轉為符合品牌規範的 HTML 報告.

v2 升級：
- 完整 CSS 系統（design_spec.md 色彩/字型/間距）
- 解析 ## section 標記，渲染語義容器
- Hero 深色區塊 + 導航欄 + 動效
- Markdown inline 解析（bold / bullet / numbered list）
"""

import logging
import re
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── 動機對照 ────────────────────────────────────────────────────────────────

_MOTIVATION_ZH = {
    "curiosity": "好奇心驅動",
    "world": "世界脈動",
    "skill": "技能精進",
    "self": "自我反思",
    "mission": "使命探索",
    "morning": "晨間巡禮",
    "idle": "閒置時自主探索",
}

_MOTIVATION_EN = {
    "curiosity": "CURIOSITY",
    "world": "WORLD PULSE",
    "skill": "SKILL MASTERY",
    "self": "SELF REFLECTION",
    "mission": "MISSION",
    "morning": "MORNING BRIEF",
    "idle": "AUTONOMOUS",
}

# ── Section 解析映射（## header → section_key）──────────────────────────────

_SECTION_MAP: List[Tuple[str, str, str, str]] = [
    # (match_keyword, section_key, display_title, icon)
    ("核心發現", "core", "核心發現", "◆"),
    ("深度解析", "analysis", "深度解析", "◈"),
    ("與使用者", "user", "與你的關聯", "◎"),
    ("霓裳", "growth", "霓裳成長收穫", "◉"),
    ("結晶", "crystal", "結晶判斷", "◇"),
    ("下一步", "next", "下一步探索", "→"),
    ("關鍵引用", "quote", "關鍵引用", "❝"),
    ("來源", "sources", "資料來源", "◫"),
]

# ── CSS 樣式表 ───────────────────────────────────────────────────────────────

_CSS = """
:root {
  --ember: #C4502A;
  --ember-light: #E0714D;
  --ember-dark: #9A3A1C;
  --ember-glow: rgba(196,80,42,0.12);
  --teal: #2A7A6E;
  --teal-light: #3A9C8F;
  --gold: #B8923A;
  --gold-light: #D4A844;
  --ink: #12121A;
  --slate: #5A5A6E;
  --mist: #9898A8;
  --border: #E2E0DA;
  --parchment: #F7F5F0;
  --snow: #FDFCFA;
  --deep-ink: #0E0E16;
  --surface: #16161F;
  --raised: #1E1E2A;
  --border-dark: #2A2A38;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Outfit', 'Noto Sans TC', -apple-system, sans-serif;
  background: var(--parchment);
  color: var(--ink);
  line-height: 1.75;
  font-size: 16px;
}

/* ── Navigation ── */
.nav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  background: rgba(14,14,22,0.94);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(196,80,42,0.4);
  padding: 14px 0;
}
.nav-inner {
  max-width: 820px; margin: 0 auto; padding: 0 40px;
  display: flex; align-items: center; justify-content: space-between;
}
.nav-brand {
  font-family: 'Cormorant Garamond', serif;
  font-size: 17px; font-weight: 600; color: var(--ember-light);
  letter-spacing: 3px;
}
.nav-meta {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px; font-weight: 500; color: var(--mist);
  letter-spacing: 0.08em;
}

/* ── Hero ── */
.hero {
  background: linear-gradient(135deg, var(--deep-ink) 0%, #1C1208 50%, var(--deep-ink) 100%);
  padding: 120px 40px 72px;
  position: relative; overflow: hidden;
}
.hero::before {
  content: '';
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse at 15% 65%, rgba(196,80,42,0.20) 0%, transparent 55%),
    radial-gradient(ellipse at 80% 25%, rgba(184,146,58,0.09) 0%, transparent 45%);
}
.hero-content { position: relative; z-index: 1; max-width: 820px; margin: 0 auto; }
.hero-tags {
  display: flex; gap: 8px; align-items: center;
  margin-bottom: 20px; flex-wrap: wrap;
}
.hero-title {
  font-family: 'Cormorant Garamond', serif;
  font-size: 44px; font-weight: 600; line-height: 1.2;
  color: #F5F0EB; margin-bottom: 16px;
}
.hero-sub {
  font-size: 14px; color: var(--mist); line-height: 1.7;
  font-family: 'Outfit', sans-serif; letter-spacing: 0.03em;
}

/* ── Badges ── */
.badge {
  display: inline-block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.1em; text-transform: uppercase;
  padding: 3px 10px; border-radius: 100px;
}
.badge-ember {
  background: rgba(196,80,42,0.2); color: var(--ember-light);
  border: 1px solid rgba(196,80,42,0.35);
}
.badge-gold {
  background: rgba(184,146,58,0.2); color: var(--gold-light);
  border: 1px solid rgba(184,146,58,0.35);
}
.badge-mist {
  background: rgba(152,152,168,0.15); color: var(--mist);
  border: 1px solid rgba(152,152,168,0.25);
}

/* ── Container ── */
.container {
  max-width: 820px; margin: 0 auto;
  padding: 48px 40px 80px;
}

/* ── Section Base ── */
.section {
  margin-bottom: 36px;
  animation: fadeUp 0.45s ease-out both;
}
.section:nth-child(1) { animation-delay: 0.00s; }
.section:nth-child(2) { animation-delay: 0.06s; }
.section:nth-child(3) { animation-delay: 0.12s; }
.section:nth-child(4) { animation-delay: 0.18s; }
.section:nth-child(5) { animation-delay: 0.24s; }
.section:nth-child(6) { animation-delay: 0.30s; }

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: translateY(0); }
}

.section-label {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 14px;
}
.section-icon { font-size: 13px; color: var(--ember); }
.section-title {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--slate);
}
.section-line { flex: 1; height: 1px; background: var(--border); }

/* ── Cards ── */
.card-core {
  background: var(--snow);
  border: 1px solid var(--border);
  border-left: 3px solid var(--ember);
  border-radius: 10px;
  padding: 28px 32px;
  box-shadow: 0 1px 3px rgba(18,18,26,0.06), 0 4px 12px rgba(18,18,26,0.04);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.card-core:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(18,18,26,0.10), 0 1px 3px rgba(18,18,26,0.06);
}

.card-analysis {
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 28px 32px;
  box-shadow: 0 1px 3px rgba(18,18,26,0.06), 0 4px 12px rgba(18,18,26,0.04);
}

/* ── Two Column (User + Growth) ── */
.two-col {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  margin-bottom: 36px;
  animation: fadeUp 0.45s ease-out 0.18s both;
}
.card-relevance {
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 22px 24px;
  box-shadow: 0 1px 3px rgba(18,18,26,0.05);
}
.card-relevance-title {
  font-size: 12px; font-weight: 600; color: var(--teal);
  font-family: 'IBM Plex Mono', monospace;
  letter-spacing: 0.06em; text-transform: uppercase;
  margin-bottom: 12px;
}

/* ── Crystal Verdict (Dark Gold) ── */
.card-verdict {
  background: linear-gradient(135deg, #1A1510 0%, #0E0E16 100%);
  border: 1px solid rgba(184,146,58,0.28);
  border-radius: 10px;
  padding: 28px 32px;
  margin-bottom: 36px;
  animation: fadeUp 0.45s ease-out 0.22s both;
}
.verdict-title {
  font-family: 'Cormorant Garamond', serif;
  font-size: 19px; font-weight: 600; color: var(--gold-light);
  margin-bottom: 14px; display: flex; align-items: center; gap: 8px;
}
.card-verdict .md-para { color: #C8C0B0; }
.card-verdict .md-list li { color: #C8C0B0; }
.card-verdict strong { color: var(--gold-light); }

/* ── Next Steps (Teal top border) ── */
.card-next {
  background: var(--snow);
  border: 1px solid var(--border);
  border-top: 2px solid var(--teal);
  border-radius: 10px;
  padding: 24px 28px;
  box-shadow: 0 1px 3px rgba(18,18,26,0.05);
}

/* ── Stats Bar ── */
.stats-bar {
  display: flex; gap: 14px; flex-wrap: wrap;
  margin-bottom: 48px;
  animation: fadeUp 0.45s ease-out 0.30s both;
}
.stat-item {
  flex: 1; min-width: 100px;
  background: var(--snow);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px; text-align: center;
  transition: transform 0.2s ease;
}
.stat-item:hover { transform: translateY(-2px); }
.stat-label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--mist);
  margin-bottom: 6px;
}
.stat-value { font-size: 18px; font-weight: 600; color: var(--ink); }

/* ── Footer ── */
.footer {
  padding-top: 24px;
  border-top: 1px solid var(--border);
  text-align: center;
  animation: fadeUp 0.45s ease-out 0.36s both;
}
.footer-text {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 500; color: var(--mist);
  letter-spacing: 0.12em;
}

/* ── Markdown Rendering ── */
.md-para {
  margin: 0 0 1.1em 0;
  line-height: 1.82;
  color: var(--ink);
  font-size: 15px;
}
.md-para:last-child { margin-bottom: 0; }

.md-list {
  margin: 0.4em 0 1em 0;
  padding-left: 1.4em;
}
.md-list li {
  margin-bottom: 0.55em;
  line-height: 1.75; font-size: 15px; color: var(--ink);
}
.md-list li::marker { color: var(--ember); }

.inline-code {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 13px; background: #F0EDE8;
  padding: 1px 5px; border-radius: 3px;
  color: var(--ember-dark);
}
strong { color: var(--ink); font-weight: 600; }
em { color: var(--slate); font-style: italic; }

/* ── Executive Verdict ── */
.exec-verdict {
  background: var(--snow);
  border-left: 4px solid var(--ember);
  border-radius: 0 12px 12px 0;
  padding: 36px 40px;
  margin: -36px auto 48px;
  max-width: 820px;
  position: relative;
  z-index: 2;
  box-shadow: 0 8px 32px rgba(18,18,26,0.06);
}
.exec-verdict-label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--ember); font-weight: 600; margin-bottom: 12px;
}
.exec-verdict h2 {
  font-family: 'Cormorant Garamond', serif;
  font-size: 26px; font-weight: 600; color: var(--ink);
  line-height: 1.4; margin-bottom: 14px;
}
.exec-verdict p { color: var(--slate); font-size: 15px; line-height: 1.8; }
.exec-highlight {
  display: inline;
  background: linear-gradient(transparent 60%, rgba(196,80,42,0.15) 60%);
  font-weight: 600; color: var(--ink);
}

/* ── Pull Quote / Key Insight ── */
.pull-quote {
  border-left: 3px solid var(--gold);
  padding: 20px 24px;
  margin: 20px 0;
  background: rgba(184,146,58,0.06);
  border-radius: 0 8px 8px 0;
}
.pull-quote p {
  font-family: 'Cormorant Garamond', serif;
  font-size: 20px; font-weight: 600; color: var(--ink);
  line-height: 1.5; font-style: italic;
}

/* ── Source Citation Card ── */
.source-card {
  display: flex; align-items: flex-start; gap: 12px;
  background: var(--parchment);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 18px;
  margin: 12px 0;
  transition: transform 0.2s ease;
}
.source-card:hover { transform: translateY(-1px); }
.source-tag {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 9px; font-weight: 600; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--teal);
  background: rgba(42,122,110,0.1);
  padding: 2px 8px; border-radius: 4px;
  white-space: nowrap; margin-top: 2px;
}
.source-text { font-size: 14px; color: var(--slate); line-height: 1.6; }
.source-text strong { color: var(--ink); }

/* ── Insight Number Badge ── */
.insight-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--ember); color: #fff;
  font-family: 'Cormorant Garamond', serif;
  font-size: 15px; font-weight: 600;
  margin-right: 12px; flex-shrink: 0;
}
.insight-row {
  display: flex; align-items: flex-start;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}
.insight-row:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }

/* ── Mechanism Grid ── */
.mech-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  margin: 16px 0;
}
.mech-item {
  padding: 18px 20px;
  background: var(--parchment);
  border-radius: 8px;
  border: 1px solid var(--border);
}
.mech-label {
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
  text-transform: uppercase; margin-bottom: 8px;
}
.mech-label-mechanism { color: var(--ember); }
.mech-label-evidence { color: var(--teal); }
.mech-label-blindspot { color: var(--gold); }
.mech-label-connection { color: var(--slate); }
.mech-item p { font-size: 14px; color: var(--ink); line-height: 1.7; }

/* ── Responsive ── */
@media (max-width: 640px) {
  .hero { padding: 100px 24px 56px; }
  .hero-title { font-size: 30px; }
  .container { padding: 32px 24px 60px; }
  .card-core, .card-analysis { padding: 20px; }
  .nav-inner { padding: 0 24px; }
  .two-col { grid-template-columns: 1fr; }
  .exec-verdict { padding: 24px; margin: -24px 16px 36px; }
  .mech-grid { grid-template-columns: 1fr; }
}
"""


# ── Markdown 解析 ────────────────────────────────────────────────────────────

def _inline_md(text: str) -> str:
    """處理行內 Markdown：bold / italic / inline-code."""
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r'<code class="inline-code">\1</code>', text)
    return text


def _md_to_html(text: str) -> str:
    """Markdown 區塊 → HTML（段落 / bullet / numbered list）."""
    lines = text.split("\n")
    parts: List[str] = []
    in_ul = False
    in_ol = False

    for raw in lines:
        stripped = raw.strip()

        if not stripped:
            if in_ul:
                parts.append("</ul>"); in_ul = False
            if in_ol:
                parts.append("</ol>"); in_ol = False
            continue

        # Bullet list
        if stripped.startswith("- ") or stripped.startswith("• "):
            if in_ol:
                parts.append("</ol>"); in_ol = False
            if not in_ul:
                parts.append('<ul class="md-list">'); in_ul = True
            parts.append(f"<li>{_inline_md(stripped[2:])}</li>")
            continue

        # Numbered list
        m = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if m:
            if in_ul:
                parts.append("</ul>"); in_ul = False
            if not in_ol:
                parts.append('<ol class="md-list">'); in_ol = True
            parts.append(f"<li>{_inline_md(m.group(2))}</li>")
            continue

        # Close open lists then paragraph
        if in_ul:
            parts.append("</ul>"); in_ul = False
        if in_ol:
            parts.append("</ol>"); in_ol = False
        parts.append(f'<p class="md-para">{_inline_md(stripped)}</p>')

    if in_ul:
        parts.append("</ul>")
    if in_ol:
        parts.append("</ol>")

    return "\n".join(parts)


# ── Section 解析 ─────────────────────────────────────────────────────────────

def _parse_sections(text: str) -> List[Tuple[str, str, str, str]]:
    """解析 ## section 標記，返回 (key, title, icon, content) 列表."""
    sections: List[Tuple[str, str, str, str]] = []
    # Split on ## markers
    parts = re.split(r"\n##\s+", "\n" + text)

    for part in parts:
        if not part.strip():
            continue
        header, _, content = part.partition("\n")
        header = header.strip()
        content = content.strip()

        matched = False
        for keyword, key, display_title, icon in _SECTION_MAP:
            if keyword in header:
                sections.append((key, display_title, icon, content))
                matched = True
                break

        if not matched and header and content:
            sections.append(("generic", header, "◦", content))

    return sections


def _render_sections(sections: List[Tuple[str, str, str, str]]) -> str:
    """將 section 列表渲染為 HTML 字串."""
    parts: List[str] = []

    user_section = None
    growth_section = None
    crystal_section = None
    next_section = None
    quote_section = None
    sources_section = None
    main_sections: List[Tuple[str, str, str, str]] = []

    for sec in sections:
        key = sec[0]
        if key == "user":
            user_section = sec
        elif key == "growth":
            growth_section = sec
        elif key == "crystal":
            crystal_section = sec
        elif key == "next":
            next_section = sec
        elif key == "quote":
            quote_section = sec
        elif key == "sources":
            sources_section = sec
        else:
            main_sections.append(sec)

    # 主要 sections（核心發現 / 深度解析 / generic）
    for key, title, icon, content in main_sections:
        card_cls = "card-core" if key == "core" else "card-analysis"
        parts.append(f"""  <div class="section">
    <div class="section-label">
      <span class="section-icon">{escape(icon)}</span>
      <span class="section-title">{escape(title)}</span>
      <div class="section-line"></div>
    </div>
    <div class="{card_cls}">
      {_md_to_html(content)}
    </div>
  </div>""")

    # 使用者關聯 + 霓裳成長 → two-col
    if user_section or growth_section:
        user_html = ""
        growth_html = ""

        if user_section:
            _, t, _, c = user_section
            user_html = f"""<div class="card-relevance">
      <div class="card-relevance-title">◎ {escape(t)}</div>
      {_md_to_html(c)}
    </div>"""

        if growth_section:
            _, t, _, c = growth_section
            growth_html = f"""<div class="card-relevance">
      <div class="card-relevance-title">◉ {escape(t)}</div>
      {_md_to_html(c)}
    </div>"""

        parts.append(f"""  <div class="two-col">
    {user_html}
    {growth_html}
  </div>""")

    # 關鍵引用 → pull-quote
    if quote_section:
        _, t, _, c = quote_section
        # Render each line as a separate pull-quote block
        for line in c.strip().split("\n"):
            line = line.strip()
            if line:
                parts.append(f"""  <div class="pull-quote">
    <p>{_inline_md(line)}</p>
  </div>""")

    # 資料來源 → source cards
    if sources_section:
        _, t, icon, c = sources_section
        parts.append(f"""  <div class="section">
    <div class="section-label">
      <span class="section-icon">{escape(icon)}</span>
      <span class="section-title">{escape(t)}</span>
      <div class="section-line"></div>
    </div>""")
        for line in c.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Strip leading bullet markers
            if line.startswith("- ") or line.startswith("• "):
                line = line[2:]
            parts.append(f"""    <div class="source-card">
      <span class="source-tag">SOURCE</span>
      <span class="source-text">{_inline_md(line)}</span>
    </div>""")
        parts.append("  </div>")

    # 結晶判斷 → 深色 Gold card
    if crystal_section:
        _, t, _, c = crystal_section
        parts.append(f"""  <div class="card-verdict">
    <div class="verdict-title">◇ {escape(t)}</div>
    {_md_to_html(c)}
  </div>""")

    # 下一步探索 → teal top border
    if next_section:
        _, t, _, c = next_section
        parts.append(f"""  <div class="section">
    <div class="section-label">
      <span class="section-icon">→</span>
      <span class="section-title">{escape(t)}</span>
      <div class="section-line"></div>
    </div>
    <div class="card-next">
      {_md_to_html(c)}
    </div>
  </div>""")

    return "\n".join(parts)


# ── 主函數 ───────────────────────────────────────────────────────────────────

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

    topic = data.get("topic", "未知主題")
    motivation_raw = data.get("motivation", "")
    motivation_zh = _MOTIVATION_ZH.get(motivation_raw, motivation_raw)
    motivation_en = _MOTIVATION_EN.get(motivation_raw, motivation_raw.upper())
    findings = data.get("findings", "")
    crystallized = bool(data.get("crystallized", 0))
    timestamp = data.get("timestamp", "")
    duration_ms = data.get("duration_ms", 0)
    cost_usd = data.get("cost_usd", 0.0)

    # 時間
    try:
        dt = datetime.fromisoformat(timestamp) if timestamp else datetime.now()
        time_str = dt.strftime("%Y年%m月%d日 %H:%M")
        date_slug = dt.strftime("%Y%m%d-%H%M%S")
    except (ValueError, TypeError):
        dt = datetime.now()
        time_str = dt.strftime("%Y年%m月%d日 %H:%M")
        date_slug = dt.strftime("%Y%m%d-%H%M%S")

    # 耗時 / 費用
    if duration_ms and duration_ms > 0:
        sec = duration_ms / 1000
        duration_str = f"{sec / 60:.1f} 分" if sec >= 60 else f"{sec:.1f} 秒"
    else:
        duration_str = "—"
    cost_str = f"${cost_usd:.4f}" if cost_usd else "—"

    # 結晶 badge
    if crystallized:
        crystal_badge = '<span class="badge badge-gold">CRYSTALLIZED</span>'
        crystal_status = "已結晶"
        crystal_color = "var(--gold)"
    else:
        crystal_badge = '<span class="badge badge-mist">PENDING</span>'
        crystal_status = "待結晶"
        crystal_color = "var(--mist)"

    # 解析 & 渲染 sections
    sections = _parse_sections(findings) if findings else []
    if not sections and findings:
        # fallback：無 ## 結構時整塊作為核心發現
        sections = [("core", "探索發現", "◆", findings)]
    sections_html = _render_sections(sections)

    # 從核心發現中提取第一句作為 exec-verdict 標題
    verdict_headline = ""
    verdict_body = ""
    for key, _title, _icon, content in sections:
        if key == "core" and content.strip():
            # 取第一段非空行作為標題，第二段作為摘要
            lines = [ln.strip() for ln in content.split("\n") if ln.strip()
                     and not ln.strip().startswith("- ")
                     and not ln.strip().startswith("• ")
                     and not re.match(r"^\d+\.\s+", ln.strip())]
            if lines:
                verdict_headline = lines[0]
                # 清除 markdown bold 標記用於純文字摘要
                verdict_headline = re.sub(r"\*\*(.+?)\*\*", r"\1", verdict_headline)
                verdict_headline = re.sub(r"__(.+?)__", r"\1", verdict_headline)
            if len(lines) > 1:
                verdict_body = lines[1]
                verdict_body = re.sub(r"\*\*(.+?)\*\*", r"\1", verdict_body)
                verdict_body = re.sub(r"__(.+?)__", r"\1", verdict_body)
            break

    topic_escaped = escape(topic)
    motivation_zh_e = escape(motivation_zh)
    motivation_en_e = escape(motivation_en)

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>探索報告 — {topic_escaped} | MUSEON</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&family=Outfit:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+TC:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>{_CSS}</style>
</head>
<body>

<!-- Navigation -->
<nav class="nav">
  <div class="nav-inner">
    <div class="nav-brand">MUSEON</div>
    <div class="nav-meta">EXPLORATION · {time_str}</div>
  </div>
</nav>

<!-- Hero -->
<div class="hero">
  <div class="hero-content">
    <div class="hero-tags">
      <span class="badge badge-ember">EXPLORATION</span>
      <span class="badge badge-ember">{motivation_en_e}</span>
      {crystal_badge}
    </div>
    <h1 class="hero-title">{topic_escaped}</h1>
    <p class="hero-sub">{motivation_zh_e} &middot; {time_str}</p>
  </div>
</div>

<!-- Executive Verdict -->
{"" if not verdict_headline else f'''<div class="exec-verdict">
  <div class="exec-verdict-label">EXECUTIVE VERDICT</div>
  <h2>{escape(verdict_headline)}</h2>
  {f'<p>{escape(verdict_body)}</p>' if verdict_body else ""}
</div>'''}

<!-- Main Content -->
<main class="container">
{sections_html}

  <!-- Stats Bar -->
  <div class="stats-bar">
    <div class="stat-item">
      <div class="stat-label">DURATION</div>
      <div class="stat-value">{duration_str}</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">COST</div>
      <div class="stat-value">{cost_str}</div>
    </div>
    <div class="stat-item">
      <div class="stat-label">CRYSTAL</div>
      <div class="stat-value" style="color:{crystal_color};">{crystal_status}</div>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <p class="footer-text">MUSEON AUTONOMOUS EXPLORATION REPORT</p>
  </div>

</main>
</body>
</html>"""

    filepath = output_dir / f"explore_{date_slug}.html"
    filepath.write_text(html, encoding="utf-8")
    logger.info(f"Exploration report generated: {filepath}")
    return filepath
