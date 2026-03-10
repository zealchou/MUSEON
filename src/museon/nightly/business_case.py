"""Daily Business Case — 每日企業個案晨報.

每天 09:05 執行：
  1. 以 SearXNG 搜尋當日一則成功、一則失敗的企業個案
  2. 用 Sonnet 寫成哈佛商業評論（HBR）風格 HTML 報告
  3. 上傳到 GitHub Gist（公開）取得外部連結
  4. 透過 Telegram 推播下載連結

環境變數：
  GITHUB_TOKEN  — GitHub Personal Access Token（需要 gist 權限）
  GITHUB_USER   — GitHub 用戶名（可選，用於美化 Gist URL 顯示）
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

TZ8 = timezone(timedelta(hours=8))

WRITE_MODEL = "claude-sonnet-4-20250514"
SEARCH_MODEL = "claude-haiku-4-5-20251001"

GIST_API = "https://api.github.com/gists"

# ──────────────────────────────────────────────
# HTML 模板（HBR 風格）
# ──────────────────────────────────────────────
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  /* HBR-inspired minimal design */
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{
    font-family: 'Georgia', 'Times New Roman', serif;
    background: #faf9f7;
    color: #1a1a1a;
    margin: 0; padding: 0;
    line-height: 1.75;
  }}
  .site-header {{
    background: #bf1722;
    color: #fff;
    padding: 10px 40px;
    font-size: 13px;
    letter-spacing: 2px;
    text-transform: uppercase;
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  }}
  .site-header span {{ opacity: 0.85; }}
  .container {{
    max-width: 860px;
    margin: 0 auto;
    padding: 40px 24px 80px;
  }}
  .issue-meta {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 12px;
    color: #888;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 32px;
    padding-bottom: 16px;
    border-bottom: 2px solid #1a1a1a;
  }}
  .report-title {{
    font-size: 36px;
    font-weight: 700;
    line-height: 1.2;
    margin: 0 0 12px;
    letter-spacing: -0.5px;
  }}
  .report-subtitle {{
    font-size: 19px;
    color: #444;
    font-weight: 400;
    margin: 0 0 32px;
    line-height: 1.45;
  }}
  .divider {{
    border: none;
    border-top: 1px solid #ddd;
    margin: 40px 0;
  }}
  .case-section {{
    margin-bottom: 56px;
  }}
  .case-badge {{
    display: inline-block;
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 4px 10px;
    border-radius: 2px;
    margin-bottom: 16px;
  }}
  .case-badge.success {{ background: #e6f4ea; color: #1e7e34; border: 1px solid #b7dfc0; }}
  .case-badge.failure {{ background: #fdecea; color: #c0392b; border: 1px solid #f5c6c2; }}
  .case-title {{
    font-size: 26px;
    font-weight: 700;
    margin: 0 0 8px;
    line-height: 1.3;
  }}
  .case-company {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 13px;
    color: #666;
    margin-bottom: 20px;
  }}
  .case-body h3 {{
    font-size: 16px;
    font-weight: 700;
    margin: 28px 0 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  }}
  .case-body p {{ margin: 0 0 16px; font-size: 16px; }}
  .case-body ul {{ padding-left: 20px; margin: 0 0 16px; }}
  .case-body ul li {{ margin-bottom: 8px; font-size: 16px; }}
  .takeaway-box {{
    background: #f5f5f0;
    border-left: 4px solid #bf1722;
    padding: 20px 24px;
    margin: 32px 0;
    font-size: 15px;
  }}
  .takeaway-box strong {{
    display: block;
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 11px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #bf1722;
    margin-bottom: 8px;
  }}
  .footer {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 12px;
    color: #aaa;
    text-align: center;
    padding-top: 32px;
    border-top: 1px solid #e0e0e0;
    margin-top: 60px;
  }}
</style>
</head>
<body>
<div class="site-header">
  <span>MUSEON</span>&nbsp;&nbsp;·&nbsp;&nbsp;每日商業個案晨報
</div>
<div class="container">
  <div class="issue-meta">{issue_date} &nbsp;·&nbsp; Vol. {vol}</div>
  <h1 class="report-title">{title}</h1>
  <p class="report-subtitle">{subtitle}</p>
  <hr class="divider">
  {cases_html}
  <div class="footer">
    由 MUSEON 霓裳 自動生成 · {generated_at} · 僅供學習參考
  </div>
</div>
</body>
</html>
"""

_CASE_TEMPLATE = """\
<div class="case-section">
  <span class="case-badge {badge_class}">{badge_label}</span>
  <h2 class="case-title">{case_title}</h2>
  <div class="case-company">{company_meta}</div>
  <div class="case-body">
    {body_html}
  </div>
  <div class="takeaway-box">
    <strong>關鍵啟示</strong>
    {takeaway}
  </div>
</div>
"""


# ──────────────────────────────────────────────
# 搜尋 prompt
# ──────────────────────────────────────────────
_SEARCH_SUMMARY_PROMPT = """\
你是商業新聞分析師。根據以下搜尋結果，請提煉出一個真實企業個案的核心事實。

類型：{case_type}（成功/失敗）
搜尋主題：{query}

搜尋摘要：
{hits_text}

請用繁體中文，100字以內，輸出：
1. 公司名稱與所在國家
2. 核心事件（做了什麼）
3. 結果（數字優先）
4. 時間（年份）

若搜尋結果無具體個案，直接回覆「INSUFFICIENT」。
"""

_WRITE_PROMPT = """\
你是哈佛商業評論（Harvard Business Review）的資深撰稿人，擅長以嚴謹的分析框架和平易近人的敘事風格寫作企業個案。

今天的兩個個案摘要如下：

【成功個案】
{success_brief}

【失敗個案】
{failure_brief}

請用繁體中文撰寫一份完整的 HTML 報告，遵循以下規範：

**結構要求（嚴格遵守）：**
輸出純 HTML 片段（不含 <html>/<head>/<body>，只含個案內容），包含兩個 <div class="case-section">：

個案一（成功）結構：
- <span class="case-badge success">成功個案</span>
- <h2 class="case-title">個案標題（15字以內）</h2>
- <div class="case-company">公司名稱 · 國家 · 年份</div>
- <div class="case-body">
    <h3>背景</h3><p>...</p>
    <h3>關鍵決策</h3><p>...</p>
    <h3>執行過程</h3><p>...</p>
    <h3>成果</h3><p>（附數字）</p>
  </div>
- <div class="takeaway-box"><strong>關鍵啟示</strong>...</div>

個案二（失敗）結構（同上，badge 換成 failure）：
- 同上，加入「失敗根因」section

**寫作風格：**
- 敘事從衝突或矛盾切入，不從背景介紹開始
- 每個 section 2-4 段，每段 3-5 句
- 數字具體（百分比、金額、時間）
- 結語有洞察，不說廢話

輸出：只輸出 HTML 片段，不加說明文字，不加 markdown 代碼塊標記。
"""


class BusinessCaseDaily:
    """每日企業個案產生器."""

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

    # ── 搜尋 ─────────────────────────────────

    async def _search_case(
        self,
        case_type: str,
        searxng_url: str = "http://127.0.0.1:8888",
    ) -> list[dict]:
        """用 SearXNG 搜尋個案，回傳 hits list."""
        if case_type == "success":
            queries = [
                "企業成功轉型案例 2025 2026",
                "company successful turnaround business case 2025 2026",
            ]
        else:
            queries = [
                "企業失敗倒閉案例 2025 2026",
                "company business failure collapse case study 2025 2026",
            ]

        all_hits = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                for q in queries:
                    params = {
                        "q": q,
                        "format": "json",
                        "language": "zh-TW" if "企業" in q else "en",
                        "categories": "general",
                    }
                    try:
                        resp = await client.get(f"{searxng_url}/search", params=params)
                        if resp.status_code == 200:
                            results = resp.json().get("results", [])[:4]
                            all_hits.extend([
                                {
                                    "title": r.get("title", ""),
                                    "content": r.get("content", "")[:400],
                                    "url": r.get("url", ""),
                                }
                                for r in results
                            ])
                    except Exception as e:
                        logger.debug(f"SearXNG query '{q}' failed: {e}")
        except Exception as e:
            logger.warning(f"BusinessCase search failed ({case_type}): {e}")

        return all_hits

    # ── LLM：提煉搜尋摘要 ────────────────────

    async def _summarize_hits(
        self,
        hits: list[dict],
        case_type: str,
        brain,
    ) -> str:
        """用 Haiku 把搜尋結果濃縮成個案摘要."""
        if not hits:
            return "INSUFFICIENT"

        hits_text = "\n".join(
            f"- {h['title']}: {h['content']}" for h in hits[:6]
        )
        prompt = _SEARCH_SUMMARY_PROMPT.format(
            case_type=case_type,
            query="企業成功案例" if case_type == "success" else "企業失敗案例",
            hits_text=hits_text,
        )
        result = await brain._call_llm_with_model(
            system_prompt="你是商業新聞分析師，輸出簡潔中文摘要。",
            messages=[{"role": "user", "content": prompt}],
            model=SEARCH_MODEL,
            max_tokens=300,
        )
        return result.strip() if result else "INSUFFICIENT"

    # ── LLM：撰寫 HTML 個案 ──────────────────

    async def _write_html_cases(
        self,
        success_brief: str,
        failure_brief: str,
        brain,
    ) -> str:
        """用 Sonnet 撰寫完整 HBR 風格 HTML 片段."""
        prompt = _WRITE_PROMPT.format(
            success_brief=success_brief,
            failure_brief=failure_brief,
        )
        result = await brain._call_llm_with_model(
            system_prompt="你是哈佛商業評論資深撰稿人，輸出純 HTML 片段，不含任何說明文字。",
            messages=[{"role": "user", "content": prompt}],
            model=WRITE_MODEL,
            max_tokens=4000,
        )
        return result.strip() if result else ""

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

    def _push_to_github_pages(self, html_content: str, date_str: str, vol_num: int) -> str:
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

        # 推送報告
        report_path = f"reports/{date_str}.html"
        encoded_content = base64.b64encode(html_content.encode("utf-8")).decode("ascii")

        # 先檢查檔案是否存在（取得 sha）
        sha = None
        check_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{report_path}"
        check_resp = requests.get(check_url, headers=headers)
        if check_resp.status_code == 200:
            sha = check_resp.json().get("sha")

        payload = {
            "message": f"Add daily report {date_str}",
            "content": encoded_content,
        }
        if sha:
            payload["sha"] = sha

        resp = requests.put(check_url, json=payload, headers=headers)
        if resp.status_code not in (200, 201):
            logger.error(f"GitHub Pages 推送失敗: {resp.status_code} {resp.text}")
            return ""

        # 同時更新 index.html，在列表最前面加上今天的連結
        index_url = f"https://api.github.com/repos/{owner}/{repo}/contents/index.html"
        index_resp = requests.get(index_url, headers=headers)
        if index_resp.status_code == 200:
            existing_index = base64.b64decode(index_resp.json()["content"]).decode("utf-8")
            index_sha = index_resp.json()["sha"]

            # 在 <ul id="reports"> 後插入新條目
            new_item = f'  <li><a href="reports/{date_str}.html">Vol.{vol_num:03d} — {date_str} 企業個案晨報</a><span class="date">{date_str}</span></li>\n'
            if f'reports/{date_str}.html' not in existing_index:
                updated_index = existing_index.replace(
                    '<ul class="report-list" id="reports">\n',
                    f'<ul class="report-list" id="reports">\n{new_item}',
                )
                requests.put(index_url, json={
                    "message": f"Update index for {date_str}",
                    "content": base64.b64encode(updated_index.encode("utf-8")).decode("ascii"),
                    "sha": index_sha,
                }, headers=headers)

        pages_url = f"https://{owner}.github.io/{repo}/reports/{date_str}.html"
        logger.info(f"GitHub Pages 推送成功: {pages_url}")
        return pages_url

    # ── 主流程 ────────────────────────────────

    async def run(self, brain, adapter=None) -> Optional[str]:
        """執行完整流程。

        Returns:
            下載連結（raw URL），失敗時返回 None
        """
        now = datetime.now(TZ8)
        date_str = now.strftime("%Y-%m-%d")
        logger.info(f"BusinessCase: starting daily run for {date_str}")

        # 1. 搜尋
        success_hits, failure_hits = [], []
        try:
            import asyncio
            success_hits, failure_hits = await asyncio.gather(
                self._search_case("success"),
                self._search_case("failure"),
            )
        except Exception as e:
            logger.error(f"BusinessCase: search stage failed: {e}")

        # 2. 摘要提煉（Haiku）
        success_brief = await self._summarize_hits(success_hits, "success", brain)
        failure_brief = await self._summarize_hits(failure_hits, "failure", brain)

        if success_brief == "INSUFFICIENT" and failure_brief == "INSUFFICIENT":
            logger.warning("BusinessCase: both searches returned insufficient data")
            # 用 fallback 佔位符讓報告仍可生成
            success_brief = "近期企業成功轉型案例：搜尋引擎暫無結果，請以通用案例替代。"
            failure_brief = "近期企業失敗案例：搜尋引擎暫無結果，請以通用案例替代。"

        # 3. 撰寫 HTML（Sonnet）
        cases_html = await self._write_html_cases(success_brief, failure_brief, brain)
        if not cases_html:
            logger.error("BusinessCase: LLM failed to generate HTML")
            return None

        # 4. 組裝完整 HTML
        vol = self._get_next_vol()
        full_html = _HTML_TEMPLATE.format(
            title=f"每日企業個案晨報 · {date_str}",
            subtitle="一則成功，一則失敗。從真實企業決策中淬取商業洞見。",
            issue_date=now.strftime("%Y 年 %m 月 %d 日"),
            vol=str(vol).zfill(3),
            cases_html=cases_html,
            generated_at=now.strftime("%Y-%m-%d %H:%M CST"),
        )

        # 5. 儲存本地備份
        backup_dir = self.data_dir / "daily_summaries"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"business_case_{date_str}.html"
        try:
            backup_path.write_text(full_html, encoding="utf-8")
            logger.info(f"BusinessCase: local backup saved → {backup_path}")
        except Exception as e:
            logger.warning(f"BusinessCase: local backup failed: {e}")

        # 6. 上傳 GitHub Gist
        raw_url = await self._upload_to_gist(full_html, date_str)

        # 7. 推送 GitHub Pages
        pages_url = ""
        try:
            pages_url = self._push_to_github_pages(full_html, date_str, vol)
        except Exception as e:
            logger.warning(f"BusinessCase: GitHub Pages push failed: {e}")

        # 8. Telegram 推播
        if adapter:
            if pages_url:
                msg = (
                    f"📰 <b>每日企業個案晨報</b> Vol.{str(vol).zfill(3)}\n\n"
                    f"📅 {date_str}\n"
                    f"✅ 成功個案 + ❌ 失敗個案\n\n"
                    f"🌐 <a href=\"{pages_url}\">在線閱讀（GitHub Pages）</a>"
                )
                if raw_url:
                    msg += f"\n📥 <a href=\"{raw_url}\">下載 HTML 原始檔</a>"
            elif raw_url:
                msg = (
                    f"📰 <b>每日企業個案晨報</b> Vol.{str(vol).zfill(3)}\n\n"
                    f"📅 {date_str}\n"
                    f"✅ 成功個案 + ❌ 失敗個案\n\n"
                    f"🔗 <a href=\"{raw_url}\">下載 HTML 報告</a>"
                )
            else:
                msg = (
                    f"📰 <b>每日企業個案晨報</b> Vol.{str(vol).zfill(3)}\n\n"
                    f"📅 {date_str}\n"
                    f"報告已生成並儲存本地。\n"
                    f"⚠️ GitHub 上傳失敗（請確認 GITHUB_TOKEN）"
                )
            try:
                await adapter.push_notification(msg)
            except Exception as e:
                logger.warning(f"BusinessCase: Telegram push failed: {e}")

        return pages_url or raw_url
