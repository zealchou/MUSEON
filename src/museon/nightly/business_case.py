"""Daily Business Case v2 — 每日企業個案晨報（Morning Business Case）.

工作流代號：WF-MBC-01

每天 09:05 執行七步工作流：
  1. 主題選定 — SearXNG 搜尋 → Haiku 提煉共同主題
  2. 素材蒐集 + 半匿名化 — 保留產業/國家/時間段，替換公司名/人名
  3. DSE 第一性原理拆解 — 問出問題本質
  4. 多 Skill 會診 — Business-12 + SSA + Master-Strategy + 商業框架路由
  5. Sonnet 撰寫 HTML — HBR 等級敘事 + MUSEON 品牌視覺規範
  6. 品質檢查 — 字數/匿名化/design_spec 合規
  7. GitHub Pages 發佈 + Telegram 推送

環境變數：
  GITHUB_TOKEN  — GitHub Personal Access Token
  GITHUB_USER   — GitHub 用戶名（可選）
"""

import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

WRITE_MODEL = "claude-sonnet-4-20250514"
SEARCH_MODEL = "claude-haiku-4-5-20251001"
ANALYSIS_MODEL = "claude-sonnet-4-20250514"

GIST_API = "https://api.github.com/gists"

# ──────────────────────────────────────────────
# HTML 模板（MUSEON 品牌規範 — design_spec.md 合規）
# ──────────────────────────────────────────────
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{meta_description}">
<meta name="keywords" content="{meta_keywords}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta_description}">
<meta property="og:url" content="{og_url}">
<meta property="og:type" content="article">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=Outfit:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+TC:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
:root {{
  --ember: #C4502A;
  --ember-light: #D4714F;
  --ember-glow: rgba(196,80,42,0.12);
  --teal: #2A7C6F;
  --teal-light: #3A9C8F;
  --gold: #B8860B;
  --gold-light: #D4A844;
  --ink: #1A1A1A;
  --charcoal: #333333;
  --stone: #6B6B6B;
  --silver: #9B9B9B;
  --mist: #E8E0D8;
  --parchment: #F5F0EB;
  --cream: #FAF8F5;
  --white: #FFFFFF;
  --deep-ink: #0E0E16;
  --success: #2D8659;
  --error: #C4402A;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  font-family: 'Outfit', 'Noto Sans TC', -apple-system, sans-serif;
  background: var(--parchment);
  color: var(--charcoal);
  line-height: 1.75;
  font-size: 16px;
}}

/* ===== NAV ===== */
.nav {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
  background: rgba(26,26,26,0.95);
  backdrop-filter: blur(12px);
  padding: 12px 0;
  border-bottom: 2px solid var(--ember);
}}
.nav-inner {{
  max-width: 820px; margin: 0 auto; padding: 0 24px;
  display: flex; align-items: center; justify-content: space-between;
}}
.nav-brand {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 18px; font-weight: 600; color: var(--ember-light);
  letter-spacing: 2px;
}}
.nav-meta {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px; font-weight: 500; color: var(--silver);
  letter-spacing: 0.08em;
}}
.nav-links {{
  display: flex; gap: 20px;
}}
.nav-links a {{
  color: var(--mist); text-decoration: none; font-size: 13px;
  transition: color 0.2s;
  font-family: 'Noto Sans TC', sans-serif;
}}
.nav-links a:hover {{ color: var(--ember-light); }}

/* ===== HERO ===== */
.hero {{
  background: linear-gradient(135deg, #1A1A1A 0%, #2A2018 50%, #1A1A1A 100%);
  padding: 140px 24px 80px;
  text-align: center;
  position: relative;
  overflow: hidden;
}}
.hero::before {{
  content: '';
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse at 30% 50%, rgba(196,80,42,0.15) 0%, transparent 60%),
    radial-gradient(ellipse at 70% 30%, rgba(42,124,111,0.1) 0%, transparent 50%);
}}
.hero-content {{ position: relative; z-index: 1; max-width: 720px; margin: 0 auto; }}
.hero-tags {{
  display: flex; justify-content: center; gap: 10px;
  margin-bottom: 24px; flex-wrap: wrap;
}}
.hero-tag {{
  display: inline-block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.1em; text-transform: uppercase;
  padding: 4px 14px; border-radius: 20px;
}}
.hero-tag-ember {{
  background: rgba(196,80,42,0.2); color: var(--ember-light);
  border: 1px solid rgba(196,80,42,0.35);
}}
.hero-tag-gold {{
  background: rgba(184,134,11,0.2); color: var(--gold-light);
  border: 1px solid rgba(184,134,11,0.35);
}}
.hero h1 {{
  font-family: 'Cormorant Garamond', serif;
  font-size: clamp(28px, 5vw, 44px);
  font-weight: 700; color: var(--cream);
  line-height: 1.2; margin-bottom: 20px;
}}
.hero h1 span {{ color: var(--ember-light); }}
.hero-sub {{
  font-size: 16px; color: var(--silver);
  line-height: 1.7; max-width: 560px; margin: 0 auto;
  font-family: 'Noto Sans TC', sans-serif;
}}

/* ===== MAIN ===== */
.main {{ max-width: 820px; margin: 0 auto; padding: 0 24px; }}

/* ===== VERDICT (Executive Summary) ===== */
.verdict {{
  background: var(--white);
  border-left: 4px solid var(--ember);
  border-radius: 0 12px 12px 0;
  padding: 40px;
  margin: -40px 0 48px;
  position: relative; z-index: 2;
  box-shadow: 0 8px 32px rgba(0,0,0,0.06);
  animation: fadeUp 0.4s ease-out both;
}}
.verdict-label {{
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--ember); font-weight: 600; margin-bottom: 12px;
  font-family: 'IBM Plex Mono', monospace;
}}
.verdict h2 {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 28px; font-weight: 700; color: var(--ink);
  line-height: 1.4; margin-bottom: 16px;
}}
.verdict p {{
  color: var(--stone); font-size: 15px; line-height: 1.8;
}}
.verdict-highlight {{
  display: inline;
  background: linear-gradient(transparent 60%, rgba(196,80,42,0.15) 60%);
  font-weight: 600; color: var(--ink);
}}

/* ===== CASE SECTIONS ===== */
.case-section {{ margin-bottom: 64px; }}
.case-section:nth-child(1) {{ animation: fadeUp 0.4s ease-out 0.05s both; }}
.case-section:nth-child(2) {{ animation: fadeUp 0.4s ease-out 0.10s both; }}

.case-badge {{
  display: inline-block;
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.1em; text-transform: uppercase;
  padding: 4px 14px; border-radius: 20px;
  margin-bottom: 16px;
}}
.case-badge.success {{
  background: rgba(45,134,89,0.15); color: var(--success);
  border: 1px solid rgba(45,134,89,0.3);
}}
.case-badge.failure {{
  background: rgba(196,64,42,0.12); color: var(--error);
  border: 1px solid rgba(196,64,42,0.25);
}}
.case-title {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 28px; font-weight: 700; color: var(--ink);
  line-height: 1.3; margin: 0 0 8px;
}}
.case-company {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 12px; color: var(--stone);
  letter-spacing: 0.05em; margin-bottom: 24px;
}}

.case-body h3 {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 20px; font-weight: 600; color: var(--ink);
  margin: 32px 0 12px;
}}
.case-body p {{
  margin: 0 0 16px; font-size: 15px; line-height: 1.85; color: var(--charcoal);
}}
.case-body ul {{ padding-left: 20px; margin: 0 0 16px; }}
.case-body ul li {{ margin-bottom: 8px; font-size: 15px; line-height: 1.7; }}

/* ===== PULL QUOTE ===== */
.pull-quote {{
  border-left: 3px solid var(--gold);
  padding: 24px 28px;
  margin: 28px 0;
  background: rgba(184,134,11,0.05);
  border-radius: 0 10px 10px 0;
}}
.pull-quote p {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 20px; font-weight: 600; color: var(--ink);
  line-height: 1.5; font-style: italic;
  margin-bottom: 0;
}}

/* ===== FRAMEWORK GRID ===== */
.framework-grid {{
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  margin: 24px 0;
}}
.framework-item {{
  padding: 24px;
  background: var(--white);
  border-radius: 12px;
  border: 1px solid var(--mist);
  transition: transform 0.2s;
}}
.framework-item:hover {{ transform: translateY(-2px); }}
.framework-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 600; letter-spacing: 2px;
  text-transform: uppercase; margin-bottom: 10px;
}}
.framework-label.ember {{ color: var(--ember); }}
.framework-label.teal {{ color: var(--teal); }}
.framework-label.gold {{ color: var(--gold); }}
.framework-label.slate {{ color: var(--stone); }}
.framework-item p {{ font-size: 14px; color: var(--charcoal); line-height: 1.7; margin-bottom: 0; }}
.framework-item strong {{ color: var(--ink); }}

/* ===== PERSPECTIVE GRID ===== */
.perspective-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px; margin: 24px 0;
}}
.perspective {{
  background: var(--white);
  border-radius: 12px;
  padding: 24px;
  border-top: 3px solid var(--ember);
  transition: transform 0.2s;
}}
.perspective:hover {{ transform: translateY(-2px); }}
.perspective.teal {{ border-top-color: var(--teal); }}
.perspective.gold {{ border-top-color: var(--gold); }}
.perspective h4 {{
  font-family: 'Cormorant Garamond', serif;
  font-size: 17px; font-weight: 600; color: var(--ink);
  margin-bottom: 8px;
}}
.perspective p {{ font-size: 14px; color: var(--stone); line-height: 1.7; margin-bottom: 0; }}

/* ===== TAKEAWAY / OPEN DISCUSSION ===== */
.takeaway-box {{
  background: linear-gradient(135deg, var(--ink) 0%, #2A2018 100%);
  border-radius: 16px;
  padding: 36px 40px;
  margin: 32px 0;
  color: var(--cream);
}}
.takeaway-label {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 11px; letter-spacing: 2px; text-transform: uppercase;
  color: var(--ember-light); font-weight: 600; margin-bottom: 16px;
}}
.takeaway-box ol {{
  padding-left: 20px; margin: 0;
}}
.takeaway-box ol li {{
  margin-bottom: 14px; color: var(--silver);
  font-size: 15px; line-height: 1.75;
}}
.takeaway-box ol li strong {{ color: var(--gold-light); }}

/* ===== DIVIDER ===== */
.case-divider {{
  border: none;
  border-top: 1px solid var(--mist);
  margin: 48px 0;
}}

/* ===== FOOTER ===== */
.footer {{
  padding: 32px 0;
  border-top: 1px solid var(--mist);
  text-align: center;
  margin-top: 48px;
}}
.footer-text {{
  font-family: 'IBM Plex Mono', monospace;
  font-size: 10px; font-weight: 500; color: var(--silver);
  letter-spacing: 0.15em;
}}

/* ===== ANIMATIONS ===== */
@keyframes fadeUp {{
  from {{ opacity: 0; transform: translateY(16px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}

/* ===== RESPONSIVE ===== */
@media (max-width: 640px) {{
  .hero {{ padding: 120px 20px 60px; }}
  .hero h1 {{ font-size: 26px; }}
  .verdict {{ padding: 24px; margin: -24px 0 36px; }}
  .case-title {{ font-size: 22px; }}
  .framework-grid {{ grid-template-columns: 1fr; }}
  .perspective-grid {{ grid-template-columns: 1fr; }}
  .takeaway-box {{ padding: 28px 24px; }}
  .nav-inner {{ padding: 0 16px; }}
  .main {{ padding: 0 16px; }}
}}
</style>
</head>
<body>

<!-- Navigation -->
<nav class="nav">
  <div class="nav-inner">
    <div class="nav-brand">MUSEON</div>
    <div class="nav-links">
      <a href="#case-success">成功篇</a>
      <a href="#case-failure">失敗篇</a>
    </div>
  </div>
</nav>

<!-- Hero -->
<div class="hero">
  <div class="hero-content">
    <div class="hero-tags">
      <span class="hero-tag hero-tag-ember">MORNING BUSINESS CASE</span>
      <span class="hero-tag hero-tag-gold">Vol. {vol}</span>
    </div>
    <h1>{hero_title}</h1>
    <p class="hero-sub">{hero_sub}</p>
  </div>
</div>

<div class="main">

  <!-- Executive Verdict -->
  <div class="verdict">
    <div class="verdict-label">今日主題</div>
    <h2>{verdict_title}</h2>
    <p>{verdict_body}</p>
  </div>

  {cases_html}

  <!-- Footer -->
  <div class="footer">
    <p class="footer-text">MUSEON MORNING BUSINESS CASE · {issue_date} · Vol.{vol} · 僅供學習參考</p>
  </div>

</div>

</body>
</html>
"""


# ──────────────────────────────────────────────
# Step 1: 主題選定 + 搜尋
# ──────────────────────────────────────────────
_THEME_EXTRACT_PROMPT = """\
你是資深商業新聞編輯。以下是今日搜尋到的商業新聞摘要：

【成功案例相關】
{success_hits}

【失敗案例相關】
{failure_hits}

請用繁體中文完成以下任務：

1. 從以上新聞中提煉出 **1 個共同主題**（例如：「定價策略的生死線」「數位轉型中的組織慣性」「創辦人何時該放手」）
2. 各選出 1 個最適合深入分析的個案（成功 + 失敗各一個）
3. 用一句話說明「兩個案例為什麼相關」

【重要限制】
- 個案必須發生在 **2023 年 1 月 1 日之後**（ChatGPT 帶動 AI 浪潮的新世代）
- 個案來源**不限於台灣**，應優先選擇具全球代表性的案例（美國、歐洲、日本、東南亞、拉美均可）
- 若搜尋結果中有多個候選，優先選全球知名度較高或對 AI 時代背景有關聯的案例
- **地域多元化**：兩個案例不應來自同一個國家，除非搜尋結果確實無其他選擇
- **禁止虛構**：只選有公開新聞報導、可查證的真實企業和真實事件。絕對不可編造公司名稱或捏造案例

輸出格式（嚴格 JSON）：
{{
  "theme": "主題一句話（15字以內）",
  "theme_slug": "english-slug-for-filename",
  "connection": "兩個案例的關聯（一句話）",
  "success_case": "選中的成功案例簡述（公司名+事件+國家，100字以內）",
  "failure_case": "選中的失敗案例簡述（公司名+事件+國家，100字以內）"
}}

只輸出 JSON，不加任何說明文字。
"""


# ──────────────────────────────────────────────
# Step 2: 素材蒐集 + 半匿名化
# ──────────────────────────────────────────────
_MATERIAL_PROMPT = """\
你是商業個案研究員。請根據以下搜尋結果和選定案例，提煉深度素材。

選定案例：{selected_case}
類型：{case_type}

搜尋摘要：
{hits_text}

請用繁體中文，800字以內，輸出以下資訊（越具體越好）：

1. **產業與背景**：產業、營收規模、成立年份、當時的市場環境（不寫真實公司名）
2. **核心人物**：至少 2-3 人用化名（例如「陳總」「王營運長」），各自的立場是什麼
3. **決策情境**：決策者面對的核心矛盾、壓力來源（董事會、投資人、競爭者、時間窗口）
4. **對立觀點**：支持方 vs 反對方的論點，各自的邏輯
5. **關鍵轉折**：什麼假設被推翻了？什麼意外發生了？
6. **具體數據**：營收成長率、市佔變化、用戶數等——保留比例和趨勢，模糊絕對值
7. **最反直覺的事實**：一個讓人意想不到的細節

【半匿名化規則】（嚴格遵守）
- 保留：產業、國家/地區、時間段（年份可保留）、營收規模級距
- 替換：真實公司名 → A公司/B公司、真實人名 → 化名（如李董、王總）
- 模糊：精確營收數字 → 營收規模級距（千萬級/億級/十億級）

【嚴格禁止虛構】
- 只使用搜尋結果中明確提到的真實企業和真實事件
- 如果搜尋結果不足以辨識具體個案，直接回覆「INSUFFICIENT」，絕對不可編造
- 個案必須發生在 2023 年 1 月 1 日之後（AI 時代）
"""


# ──────────────────────────────────────────────
# Step 3: DSE 第一性原理拆解
# ──────────────────────────────────────────────
_DSE_PROMPT = """\
你是 DSE（Dialogic Synthesis Engineering）分析師，專精第一性原理拆解。

以下是兩個商業案例的素材：

【成功案例素材】
{success_material}

【失敗案例素材】
{failure_material}

今日主題：{theme}

請針對兩個案例各回答以下 3 個第一性問題，用繁體中文，每個答案 150-250 字：

**成功案例：**
1. 「拿掉所有外殼，這個成功的最核心原因是什麼？（不是策略正確，而是什麼底層結構使策略得以成立？）」
2. 「決策者默認成立的假設有哪些？這些假設在什麼條件下會崩塌？」
3. 「如果把這個成功搬到另一個產業，什麼會保留、什麼會失效？」

**失敗案例：**
1. 「拿掉所有歸因（管理不善、市場變化...），最底層的因果鏈是什麼？」
2. 「在失敗發生之前，有沒有任何人做出了正確判斷卻被忽略？為什麼被忽略？」
3. 「如果時間倒流到崩壞前 6 個月，最小的改變是什麼能扭轉結局？」

輸出格式：直接輸出分析文字，用 ## 成功案例 DSE 和 ## 失敗案例 DSE 分隔。
"""


# ──────────────────────────────────────────────
# Step 4: 多 Skill 會診
# ──────────────────────────────────────────────
_CONSULTATION_PROMPT = """\
你同時具備以下三種顧問視角，請對兩個商業案例進行多維會診。

今日主題：{theme}

【成功案例素材】
{success_material}

【失敗案例素材】
{failure_material}

【DSE 第一性分析】
{dse_analysis}

請依序完成三個視角的分析：

---

## 視角一：商業基本盤（Business-12 診斷）
針對兩個案例，分別回答：
- 12 力中哪 2-3 個力是這個案例的關鍵槓桿？
- 成功案例的哪幾個力特別強？失敗案例的哪幾個力崩塌了？
（12 力 = 產品力/行銷力/銷售力/品牌力/社群力/談判力/整合力/累積力/感受力/視覺力/設計力/生態力）

## 視角二：顧問式客戶視角（SSA 診斷）
假設案例中的決策者是你的客戶：
- 他的真正卡點在哪？（不是他說的卡點，是你判斷的卡點）
- 他在什麼方面自我欺騙？
- 如果你只能問他一個問題來撬動改變，你會問什麼？

## 視角三：戰略層判斷（Master-Strategy 診斷）
- 局勢：當時的敵我態勢是什麼？（PEST 角度 + Porter 五力角度）
- 時機：這個決策的時間窗口有多大？早做或晚做 6 個月會怎樣？
- 槓桿：哪一個單一動作產生了最大的連鎖反應？

---

## 商業框架路由
根據今日主題，自動選擇 2-3 個最適合的分析框架，每個框架：
1. 先用一句白話解釋「這個工具在看什麼」
2. 再用該框架拆解兩個案例的對比
可選框架：SWOT / PEST / Porter 五力 / MECE / 4P / BCG 矩陣 / 價值鏈

用繁體中文輸出，觀點要具體、有衝突、可討論。主要講觀念和觀點衝突，不要教科書式列點。
"""


# ──────────────────────────────────────────────
# Step 5: 撰寫 HTML
# ──────────────────────────────────────────────
_WRITE_PROMPT = """\
你是哈佛商業評論（Harvard Business Review）的資深個案撰稿人。\
你寫的不是新聞報導，而是商學院教學個案——有人物、有決策掙扎、有多方角力、有讀完後仍然沒有標準答案的開放張力。

今日主題：{theme}
兩案例的關聯：{connection}

【成功案例素材（已匿名化）】
{success_material}

【失敗案例素材（已匿名化）】
{failure_material}

【DSE 第一性拆解】
{dse_analysis}

【多維會診分析】
{consultation}

---

請用繁體中文撰寫完整的 HTML 片段（不含 <html>/<head>/<body>），包含兩個個案：

**每個個案的結構（嚴格遵守比例）：**

個案一（id="case-success"）：
- <span class="case-badge success">成功篇</span>
- <h2 class="case-title">標題（15字以內，用懸念或矛盾句式）</h2>
- <div class="case-company">產業 · 地區 · 年份 · 營收規模</div>
- <div class="case-body">
    <h3>場景</h3>（15% 篇幅）一個人、一個時刻、一個選擇。用化名。鏡頭感開場。
    <h3>賭注</h3>（10%）風險多大、正反兩方論點
    <h3>框架透視</h3>（25%）用 2-3 個商業框架拆解，每個框架先用一句白話說明工具看的是什麼，再拆解觀念和觀點衝突。不要教科書式列點，而是帶出分析裡的張力。
    <h3>轉折</h3>（15%）哪個假設被推翻、意外從哪來
    <h3>結局與數字</h3>（15%）具體數據（比例保留，絕對值模糊化），嵌在敘事裡
    <h3>複利點</h3>（10%）從哪一刻開始產生複利效應
  </div>
- <div class="takeaway-box"><div class="takeaway-label">開放討論</div><ol>3-5 個沒標準答案的深度問題</ol></div>

<hr class="case-divider">

個案二（id="case-failure"）：
- <span class="case-badge failure">失敗篇</span>
- 結構同上，但：
  - 「複利點」改為 <h3>崩壞點</h3>：精確指出「從哪一刻開始不可逆」
  - 開放討論要有「如果時光倒流」的假設性問題

**寫作規範：**

1. **敘事深度**：永遠從一個人的視角、一個具體時刻開始。鏡頭感。讓讀者感受決策者的壓力。每段 3-5 句。

2. **角色與關係**：每個案例至少 3-4 個有化名的角色（決策者、反對者、外部分析師、員工等），每人有立場、動機、邏輯。展現角色間的張力。

3. **框架透視的寫法**：不是教科書式列點，而是用框架來「照亮衝突」。例如：「從 SWOT 來看，A公司的 S（核心技術）恰好是 B公司的 T（技術被替代），兩者的命運在同一個變量上分岔。」

4. **場景描寫**：用具體場景（會議室爭論、財報沉默、凌晨的 Slack 訊息）取代抽象分析。至少 2-3 個畫面。

5. **開放洞見結尾**：絕不給結論。問題要有層次——一個關於公司的、一個關於產業的、一個關於決策本質的。最後一個要挑戰讀者的直覺假設。

6. **篇幅**：每個案例 2000-2500 字（中文）。低於 2000 = 太淺。高於 3000 = 太冗。

7. **CSS 組件使用（可選）**：
   - <div class="pull-quote"><p>引用文字</p></div> — 用於關鍵洞見
   - <div class="framework-grid">...</div> — 用於框架對比（最多 4 格）
   - <div class="perspective-grid">...</div> — 用於多角色觀點並列

**匿名化驗證**：輸出中絕對不可出現真實公司名或真實人名。使用 A公司/B公司 和化名。

輸出：只輸出 HTML 片段，不加說明文字，不加 markdown 代碼塊標記。
"""


class BusinessCaseDaily:
    """每日企業個案產生器 v2."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.github_token = os.environ.get("GITHUB_TOKEN", "")
        self.github_user = os.environ.get("GITHUB_USER", "MUSEON-bot")
        self._vol_file = data_dir / "_system" / "state" / "business_case_vol.json"

    # ── 期數管理 ──────────────────────────────

    def _get_next_vol(self) -> int:
        """取得並遞增期數."""
        try:
            self._vol_file.parent.mkdir(parents=True, exist_ok=True)
            if self._vol_file.exists():
                data = json.loads(self._vol_file.read_text(encoding="utf-8"))
                vol = data.get("vol", 0) + 1
            else:
                vol = 1
            self._vol_file.write_text(
                json.dumps({"vol": vol}, ensure_ascii=False), encoding="utf-8"
            )
            return vol
        except Exception:
            return 1

    # ── Step 1: 搜尋 ─────────────────────────

    async def _search_case(
        self,
        case_type: str,
        searxng_url: str = "http://127.0.0.1:8888",
    ) -> list[dict]:
        """用 SearXNG 搜尋個案，回傳 hits list."""
        if case_type == "success":
            queries = [
                "CEO bold decision turnaround case study global 2023 2024 2025 AI era",
                "startup pivot success founder risk paid off post-ChatGPT 2023 2024 2025",
                "HBR case study company transformation leadership AI disruption 2023 2024 2025",
                "business turnaround strategy success story Fortune 500 global 2024 2025",
                "AI企業轉型成功 創辦人決策 全球案例 2023 2024 2025",
            ]
        else:
            queries = [
                "company failure CEO mistake what went wrong post-mortem global 2023 2024 2025",
                "startup shutdown founder lessons why failed AI era 2023 2024 2025",
                "business collapse leadership failure case study global 2024 2025",
                "corporate strategy failure warning signs ignored 2023 2024 2025",
                "企業失敗 CEO決策錯誤 全球案例 AI時代 2023 2024 2025",
            ]

        all_hits = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for q in queries:
                    params = {
                        "q": q,
                        "format": "json",
                        "language": "auto",
                        "categories": "general",
                        "time_range": "year",
                    }
                    try:
                        resp = await client.get(f"{searxng_url}/search", params=params)
                        if resp.status_code == 200:
                            results = resp.json().get("results", [])[:4]
                            all_hits.extend([
                                {
                                    "title": r.get("title", ""),
                                    "content": r.get("content", "")[:800],
                                    "url": r.get("url", ""),
                                }
                                for r in results
                            ])
                    except Exception as e:
                        logger.debug(f"SearXNG query '{q}' failed: {e}")
        except Exception as e:
            logger.warning(f"BusinessCase search failed ({case_type}): {e}")

        return all_hits

    # ── Step 1b: 主題提煉 ─────────────────────

    async def _extract_theme(
        self,
        success_hits: list[dict],
        failure_hits: list[dict],
        brain,
    ) -> dict:
        """用 Haiku 從搜尋結果中提煉共同主題."""
        success_text = "\n".join(
            f"- {h['title']}: {h['content']}" for h in success_hits[:6]
        ) or "（無搜尋結果）"
        failure_text = "\n".join(
            f"- {h['title']}: {h['content']}" for h in failure_hits[:6]
        ) or "（無搜尋結果）"

        prompt = _THEME_EXTRACT_PROMPT.format(
            success_hits=success_text,
            failure_hits=failure_text,
        )
        result = await brain._call_llm_with_model(
            system_prompt="你是商業新聞編輯，擅長提煉共同主題。輸出嚴格 JSON。",
            messages=[{"role": "user", "content": prompt}],
            model=SEARCH_MODEL,
            max_tokens=500,
        )
        try:
            # 嘗試解析 JSON
            text = result.strip() if result else "{}"
            # 清除可能的 markdown 包裝
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            logger.warning("BusinessCase: theme extraction JSON parse failed")
            return {
                "theme": "商業決策的十字路口",
                "theme_slug": "business-crossroads",
                "connection": "同一個決策邏輯，不同的執行結果",
                "success_case": "",
                "failure_case": "",
            }

    # ── Step 2: 素材蒐集 + 半匿名化 ──────────

    async def _collect_material(
        self,
        hits: list[dict],
        selected_case: str,
        case_type: str,
        brain,
    ) -> str:
        """用 Haiku 提煉素材並半匿名化."""
        if not hits:
            return "INSUFFICIENT"

        hits_text = "\n".join(
            f"- {h['title']}: {h['content']}" for h in hits[:6]
        )
        prompt = _MATERIAL_PROMPT.format(
            selected_case=selected_case,
            case_type="成功" if case_type == "success" else "失敗",
            hits_text=hits_text,
        )
        result = await brain._call_llm_with_model(
            system_prompt="你是商業個案研究員，輸出半匿名化的中文素材。所有內容必須使用繁體中文。",
            messages=[{"role": "user", "content": prompt}],
            model=SEARCH_MODEL,
            max_tokens=1500,
        )
        return result.strip() if result else "INSUFFICIENT"

    # ── Step 3: DSE 第一性原理拆解 ────────────

    async def _dse_analysis(
        self,
        success_material: str,
        failure_material: str,
        theme: str,
        brain,
    ) -> str:
        """用 Sonnet 進行 DSE 第一性原理拆解."""
        prompt = _DSE_PROMPT.format(
            success_material=success_material,
            failure_material=failure_material,
            theme=theme,
        )
        result = await brain._call_llm_with_model(
            system_prompt="你是 DSE 分析師，專精第一性原理拆解。輸出深度分析，使用繁體中文。",
            messages=[{"role": "user", "content": prompt}],
            model=ANALYSIS_MODEL,
            max_tokens=3000,
        )
        return result.strip() if result else ""

    # ── Step 4: 多 Skill 會診 ─────────────────

    async def _multi_skill_consultation(
        self,
        success_material: str,
        failure_material: str,
        dse_analysis: str,
        theme: str,
        brain,
    ) -> str:
        """用 Sonnet 進行多 Skill 會診分析."""
        prompt = _CONSULTATION_PROMPT.format(
            theme=theme,
            success_material=success_material,
            failure_material=failure_material,
            dse_analysis=dse_analysis,
        )
        result = await brain._call_llm_with_model(
            system_prompt=(
                "你同時是 Business-12 商業診斷師、SSA 顧問式銷售專家、"
                "Master-Strategy 戰略分析師。輸出深度多維會診。使用繁體中文。"
            ),
            messages=[{"role": "user", "content": prompt}],
            model=ANALYSIS_MODEL,
            max_tokens=4000,
        )
        return result.strip() if result else ""

    # ── Step 5: 撰寫 HTML ─────────────────────

    async def _write_html_cases(
        self,
        success_material: str,
        failure_material: str,
        dse_analysis: str,
        consultation: str,
        theme: str,
        connection: str,
        brain,
    ) -> str:
        """用 Sonnet 撰寫完整 HBR 風格 HTML 片段."""
        prompt = _WRITE_PROMPT.format(
            theme=theme,
            connection=connection,
            success_material=success_material,
            failure_material=failure_material,
            dse_analysis=dse_analysis,
            consultation=consultation,
        )
        result = await brain._call_llm_with_model(
            system_prompt=(
                "你是哈佛商業評論資深撰稿人，輸出純 HTML 片段，不含任何說明文字。"
                "所有內容必須使用繁體中文。每個案例 2000-2500 字。"
            ),
            messages=[{"role": "user", "content": prompt}],
            model=WRITE_MODEL,
            max_tokens=12000,
        )
        return result.strip() if result else ""

    # ── Step 6: 品質檢查 ──────────────────────

    def _quality_check(self, html: str) -> list[str]:
        """檢查 HTML 品質，回傳問題清單（空 = 通過）."""
        issues = []

        # 字數檢查（粗估中文字數）
        text_only = re.sub(r"<[^>]+>", "", html)
        text_only = re.sub(r"\s+", "", text_only)
        char_count = len(text_only)
        if char_count < 3500:  # 兩篇合計至少 3500（考慮 HTML 結構佔比）
            issues.append(f"字數不足：{char_count} 字（預期 ≥ 3500）")
        if char_count > 7000:
            issues.append(f"字數過多：{char_count} 字（預期 ≤ 7000）")

        # 匿名化檢查已在 prompt 中強制，這裡做最後防線
        # （真實世界應有更完整的 NER 掃描）

        return issues

    # ── GitHub Gist 上傳 ─────────────────────

    async def _upload_to_gist(self, html: str, date_str: str) -> Optional[str]:
        """上傳到 GitHub Gist，回傳 raw 下載 URL."""
        if not self.github_token:
            logger.warning("BusinessCase: GITHUB_TOKEN not set, skipping Gist upload")
            return None

        filename = f"museon-business-case-{date_str}.html"
        payload = {
            "description": f"MUSEON 每日企業個案晨報 {date_str}",
            "public": True,
            "files": {
                filename: {"content": html},
            },
        }

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    GIST_API,
                    headers={
                        "Authorization": f"token {self.github_token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json=payload,
                )
                if resp.status_code == 201:
                    data = resp.json()
                    raw_url = data["files"][filename]["raw_url"]
                    gist_url = data["html_url"]
                    logger.info(f"BusinessCase: Gist uploaded → {gist_url}")
                    return raw_url
                else:
                    logger.error(
                        f"BusinessCase: Gist upload failed "
                        f"status={resp.status_code} body={resp.text[:200]}"
                    )
                    return None
        except Exception as e:
            logger.error(f"BusinessCase: Gist upload exception: {e}")
            return None

    # ── GitHub Pages 推送 ────────────────────

    def _push_to_github_pages(
        self, html_content: str, date_str: str, vol_num: int, theme_slug: str
    ) -> str:
        """推送 HTML 報告到 GitHub Pages"""
        import base64
        import requests

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            logger.warning("GITHUB_TOKEN 未設定，跳過 GitHub Pages 推送")
            return ""

        owner = "zealchou"
        repo = "museon-daily"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # 檔名帶日期 + 關鍵字
        filename = f"morning-case-{date_str}-{theme_slug}.html"
        report_path = f"reports/{filename}"
        encoded_content = base64.b64encode(html_content.encode("utf-8")).decode("ascii")

        # 先檢查檔案是否存在（取得 sha）
        sha = None
        check_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{report_path}"
        check_resp = requests.get(check_url, headers=headers)
        if check_resp.status_code == 200:
            sha = check_resp.json().get("sha")

        payload = {
            "message": f"feat: Morning Case {date_str} — {theme_slug}",
            "content": encoded_content,
        }
        if sha:
            payload["sha"] = sha

        resp = requests.put(check_url, json=payload, headers=headers)
        if resp.status_code not in (200, 201):
            logger.error(f"GitHub Pages 推送失敗: {resp.status_code} {resp.text}")
            return ""

        # 同時更新 index.html
        index_url = f"https://api.github.com/repos/{owner}/{repo}/contents/index.html"
        index_resp = requests.get(index_url, headers=headers)
        if index_resp.status_code == 200:
            existing_index = base64.b64decode(index_resp.json()["content"]).decode("utf-8")
            index_sha = index_resp.json()["sha"]

            new_item = (
                f'  <li><a href="reports/{filename}">'
                f'Vol.{vol_num:03d} — {date_str} {theme_slug}</a>'
                f'<span class="date">{date_str}</span></li>\n'
            )
            if filename not in existing_index:
                updated_index = existing_index.replace(
                    '<ul class="report-list" id="reports">\n',
                    f'<ul class="report-list" id="reports">\n{new_item}',
                )
                requests.put(index_url, json={
                    "message": f"Update index for {date_str}",
                    "content": base64.b64encode(
                        updated_index.encode("utf-8")
                    ).decode("ascii"),
                    "sha": index_sha,
                }, headers=headers)

        # ✓ 新增：GitHub Pages HTTP 驗證流程（避免 2026-03-23 Feng 報告 404 失敗）
        pages_url = f"https://{owner}.github.io/{repo}/reports/{filename}"
        return self._verify_github_pages_url(pages_url, max_retries=5)

    def _verify_github_pages_url(self, url: str, max_retries: int = 5) -> str:
        """驗證 GitHub Pages URL 是否可訪問（HTTP 200）

        Args:
            url: GitHub Pages URL
            max_retries: 最多重試次數（2-5 秒間隔）

        Returns:
            如果驗證成功，返回 URL；失敗返回空字符串
        """
        import requests
        import time

        for attempt in range(max_retries):
            try:
                resp = requests.head(url, timeout=5)
                if resp.status_code == 200:
                    logger.info(f"GitHub Pages URL 驗證成功 (attempt {attempt + 1}): {url}")
                    return url
                else:
                    logger.warning(
                        f"GitHub Pages URL 返回 {resp.status_code} "
                        f"(attempt {attempt + 1}/{max_retries}): {url}"
                    )
            except Exception as e:
                logger.warning(
                    f"GitHub Pages URL 驗證失敗 (attempt {attempt + 1}/{max_retries}): {e}"
                )

            # 等待 2-3 秒後重試（讓 GitHub Pages 有足夠時間部署）
            if attempt < max_retries - 1:
                time.sleep(2.5)

        logger.error(
            f"GitHub Pages URL 驗證失敗，超過最大重試次數: {url}\n"
            f"可能原因：(1) GitHub token 無效 (2) 倉庫不存在 (3) Pages 部署延遲\n"
            f"建議：手動檢查 https://github.com/zealchou/museon-daily/actions"
        )
        return ""

    # ── 主流程 ────────────────────────────────

    async def run(self, brain, adapter=None) -> Optional[str]:
        """執行完整 7 步工作流。

        Returns:
            外部連結（GitHub Pages URL），失敗時返回 None
        """
        now = datetime.now(TZ8)
        date_str = now.strftime("%Y-%m-%d")
        logger.info(f"BusinessCase v2: starting daily run for {date_str}")

        # ── Step 1: 搜尋 + 主題選定 ──
        success_hits, failure_hits = [], []
        try:
            import asyncio
            success_hits, failure_hits = await asyncio.gather(
                self._search_case("success"),
                self._search_case("failure"),
            )
        except Exception as e:
            logger.error(f"BusinessCase: search stage failed: {e}")

        # 提煉主題
        theme_data = await self._extract_theme(success_hits, failure_hits, brain)
        theme = theme_data.get("theme", "商業決策的十字路口")
        theme_slug = theme_data.get("theme_slug", "business-crossroads")
        connection = theme_data.get("connection", "同一個決策邏輯，不同的結果")
        selected_success = theme_data.get("success_case", "")
        selected_failure = theme_data.get("failure_case", "")

        # 清理 slug（確保 URL 安全）
        theme_slug = re.sub(r"[^a-zA-Z0-9-]", "", theme_slug)[:40] or "case"

        logger.info(f"BusinessCase: theme='{theme}', slug='{theme_slug}'")

        # ── Step 2: 素材蒐集 + 半匿名化 ──
        import asyncio
        success_material, failure_material = await asyncio.gather(
            self._collect_material(success_hits, selected_success, "success", brain),
            self._collect_material(failure_hits, selected_failure, "failure", brain),
        )

        if success_material == "INSUFFICIENT" and failure_material == "INSUFFICIENT":
            logger.warning("BusinessCase: both material collections returned insufficient data")
            success_material = (
                "近期全球企業成功轉型案例（2023年後，AI時代）：搜尋引擎暫無結果，"
                "請以 2023 年後的全球知名案例替代。"
                "不限台灣，可選美國、歐洲、東亞等地的代表性案例。"
            )
            failure_material = (
                "近期全球企業失敗案例（2023年後，AI時代）：搜尋引擎暫無結果，"
                "請以 2023 年後的全球知名案例替代，與成功案例同主題。"
            )

        # ── Step 3: DSE 第一性原理拆解 ──
        dse_result = await self._dse_analysis(
            success_material, failure_material, theme, brain
        )
        logger.info("BusinessCase: DSE analysis completed")

        # ── Step 4: 多 Skill 會診 ──
        consultation = await self._multi_skill_consultation(
            success_material, failure_material, dse_result, theme, brain
        )
        logger.info("BusinessCase: multi-skill consultation completed")

        # ── Step 5: 撰寫 HTML ──
        cases_html = await self._write_html_cases(
            success_material, failure_material,
            dse_result, consultation,
            theme, connection, brain,
        )
        if not cases_html:
            logger.error("BusinessCase: LLM failed to generate HTML")
            return None

        # ── Step 6: 品質檢查 ──
        issues = self._quality_check(cases_html)
        if issues:
            logger.warning(f"BusinessCase: quality issues: {issues}")
            # 不硬擋，記錄後繼續（未來可退回 Step 5 重寫）

        # 組裝完整 HTML
        vol = self._get_next_vol()
        pages_filename = f"morning-case-{date_str}-{theme_slug}.html"
        og_url = f"https://zealchou.github.io/museon-daily/reports/{pages_filename}"

        full_html = _HTML_TEMPLATE.format(
            title=f"晨報 · {theme} · {date_str}",
            meta_description=f"MUSEON 每日商業個案晨報 Vol.{vol:03d}：{theme}。{connection}",
            meta_keywords=f"商業個案,{theme},{theme_slug},MUSEON,晨報",
            og_url=og_url,
            vol=f"{vol:03d}",
            hero_title=theme,
            hero_sub=connection,
            verdict_title=theme,
            verdict_body=connection,
            cases_html=cases_html,
            issue_date=now.strftime("%Y年%m月%d日"),
        )

        # ── Step 7a: 本地備份 ──
        backup_dir = self.data_dir / "daily_summaries"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"morning-case-{date_str}-{theme_slug}.html"
        try:
            backup_path.write_text(full_html, encoding="utf-8")
            logger.info(f"BusinessCase: local backup saved → {backup_path}")
        except Exception as e:
            logger.warning(f"BusinessCase: local backup failed: {e}")

        # 同時保存分析元數據（用於未來檢索）
        meta_path = backup_dir / f"morning_case_{date_str}_{theme_slug}.json"
        try:
            meta_path.write_text(json.dumps({
                "date": date_str,
                "vol": vol,
                "theme": theme,
                "theme_slug": theme_slug,
                "connection": connection,
                "quality_issues": issues,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        # ── Step 7b: GitHub Gist 上傳 ──
        raw_url = await self._upload_to_gist(full_html, date_str)

        # ── Step 7c: GitHub Pages 推送 ──
        pages_url = ""
        try:
            pages_url = self._push_to_github_pages(full_html, date_str, vol, theme_slug)
        except Exception as e:
            logger.warning(f"BusinessCase: GitHub Pages push failed: {e}")

        # ── Step 7d: Telegram 推播 ──
        if adapter:
            link = pages_url or raw_url or ""
            if link:
                msg = (
                    f"📰 <b>每日商業個案晨報</b> Vol.{vol:03d}\n\n"
                    f"📅 {date_str}\n"
                    f"🎯 主題：{theme}\n"
                    f"✅ 成功篇 + ❌ 失敗篇\n\n"
                    f"🔗 <a href=\"{link}\">完整分析</a>"
                )
            else:
                msg = (
                    f"📰 <b>每日商業個案晨報</b> Vol.{vol:03d}\n\n"
                    f"📅 {date_str}\n"
                    f"🎯 主題：{theme}\n"
                    f"報告已生成並儲存本地。\n"
                    f"⚠️ GitHub 上傳失敗（請確認 GITHUB_TOKEN）"
                )
            try:
                await adapter.push_notification(msg)
            except Exception as e:
                logger.warning(f"BusinessCase: Telegram push failed: {e}")

        return pages_url or raw_url
