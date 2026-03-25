"""五虎將共用通知模組 — 人類可讀的 DM 通知 + 待審閱摘要.

所有五虎將（MuseOff/MuseQA/MuseDoc/Nightly）共用此模組發送 DM 通知。
統一格式：中文嚴重度 + 問題說明 + 建議行動 + finding ID。
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 嚴重度中文對照 ──

_SEVERITY_ICON = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}

_SEVERITY_ZH = {
    "CRITICAL": "緊急",
    "HIGH": "重要",
    "MEDIUM": "注意",
    "LOW": "提醒",
}


def notify_owner(
    severity: str,
    title: str,
    finding_id: str,
    source: str = "system",
    home: Optional[Path] = None,
    explain: str = "",
) -> None:
    """透過 Telegram Bot API 即時 DM 通知老闆.

    Args:
        severity: CRITICAL/HIGH/MEDIUM/LOW
        title: 原始技術標題
        finding_id: Finding ID（如 MO-20260325-fe9bee）
        source: 來源（museoff/museqa/musedoc/nightly）
        home: MUSEON 根目錄（讀 .env 用）
        explain: 人類可讀的中文說明（空則自動推斷）
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    trusted_ids = os.environ.get("TELEGRAM_TRUSTED_IDS", "")

    if not token or not trusted_ids:
        env_path = (home or Path(os.environ.get("MUSEON_HOME", "."))) / ".env"
        if env_path.exists():
            for line in env_path.read_text().strip().split("\n"):
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                elif line.startswith("TELEGRAM_TRUSTED_IDS="):
                    trusted_ids = line.split("=", 1)[1].strip()

    if not token or not trusted_ids:
        return

    owner_id = trusted_ids.split(",")[0].strip()
    icon = _SEVERITY_ICON.get(severity, "⚪")
    severity_zh = _SEVERITY_ZH.get(severity, severity)
    source_zh = {
        "museoff": "巡檢官",
        "museqa": "品質官",
        "musedoc": "修復官",
        "nightly": "夜班",
    }.get(source, source)

    if not explain:
        explain = explain_finding(title, finding_id, home)

    text = (
        f"{icon}【{severity_zh}】{source_zh}回報\n"
        f"\n"
        f"{explain}\n"
        f"\n"
        f"📋 {title}\n"
        f"🔖 #{finding_id}"
    )

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": owner_id, "text": text}).encode()
        urllib.request.urlopen(url, data, timeout=5)
    except Exception as e:
        logger.debug(f"[notify] DM failed: {e}")


def explain_finding(title: str, finding_id: str = "", home: Optional[Path] = None) -> str:
    """將技術 finding 翻譯為人類可讀的中文說明."""
    _t = title.lower()

    # 模式匹配常見問題
    explanations = [
        (("no_wal",), "資料庫未開啟 WAL 模式，可能影響並行讀寫。通常重啟後自動修復。"),
        (("missing_file",), "系統必要檔案遺失，可能導致功能異常。需要檢查是否被誤刪。"),
        (("empty_file",), "檔案存在但內容為空，可能是寫入中斷。需要檢查是否需重建。"),
        (("bad_permissions",), "檔案權限不正確，可能有安全風險。"),
        (("import", "syntax"), "程式碼匯入或語法錯誤，模組無法載入。需要開發者修復。"),
        (("timeout", "slow"), "系統回應過慢或超時。觀察是否持續發生。"),
        (("memory", "oom"), "記憶體使用異常。持續發生可能需要重啟。"),
        (("crash", "error"), "系統發生錯誤或崩潰。需要查看日誌判斷根因。"),
        (("db_error",), "資料庫存取異常。可能是檔案損壞或鎖定衝突。"),
        (("stale", "outdated"), "偵測到過期的資料或設定。"),
        (("empty_response", "empty response"), "AI 回覆內容為空。可能是 API 異常或 prompt 問題。"),
        (("hallucination", "幻覺"), "AI 可能產生不準確的回覆。需要檢查 prompt 品質。"),
        (("persona_drift", "人格漂移"), "AI 的回覆風格偏離設定的人格。需要校準。"),
        (("long_response", "過長"), "AI 回覆過長，可能影響閱讀體驗。"),
        (("sensitive", "敏感"), "偵測到敏感內容相關問題。需要人工審閱。"),
    ]

    for keywords, explanation in explanations:
        if any(kw in _t for kw in keywords):
            return explanation

    # 嘗試從 finding JSON 讀 prescription
    if finding_id and home:
        try:
            findings_dir = home / "data" / "_system" / "museoff" / "findings"
            paths = list(findings_dir.rglob(f"{finding_id}.json"))
            if paths:
                data = json.loads(paths[0].read_text())
                rx = data.get("prescription", {})
                if isinstance(rx, dict) and rx.get("diagnosis"):
                    return rx["diagnosis"]
        except Exception:
            pass

    return "系統巡檢發現異常，詳情請查看完整報告。"


def generate_review_summary(home: Path) -> str:
    """生成待審閱摘要（Markdown），供老闆回家後一次審閱.

    掃描所有 open 狀態的 findings，按嚴重度排序，
    輸出人類可讀的摘要到 data/_system/review_summary.md
    """
    findings_dirs = [
        home / "data" / "_system" / "museoff" / "findings",
        home / "data" / "_system" / "museqa" / "qa_reports",
        home / "data" / "_system" / "musedoc" / "surgery_log",
    ]

    all_findings = []

    for fdir in findings_dirs:
        if not fdir.exists():
            continue
        for f in sorted(fdir.rglob("*.json"), reverse=True):
            try:
                data = json.loads(f.read_text())
                # 只收集 open / needs_human 狀態
                status = data.get("status", "open")
                if status not in ("open", "needs_human"):
                    continue
                all_findings.append(data)
            except Exception:
                continue

    # 按嚴重度排序
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    all_findings.sort(key=lambda x: severity_order.get(x.get("severity", "LOW"), 9))

    # 生成 Markdown
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 待審閱問題摘要",
        f"",
        f"> 生成時間：{now}",
        f"> 共 {len(all_findings)} 個待處理問題",
        f"",
    ]

    if not all_findings:
        lines.append("沒有待處理的問題。系統狀態良好。")
    else:
        for f in all_findings:
            fid = f.get("finding_id", "?")
            sev = f.get("severity", "?")
            title = f.get("title", "?")
            source = f.get("source", "?")
            ts = f.get("timestamp", "")[:16]
            status = f.get("status", "?")
            icon = _SEVERITY_ICON.get(sev, "⚪")
            sev_zh = _SEVERITY_ZH.get(sev, sev)

            explain = explain_finding(title, fid, home)

            rx = f.get("prescription", {})
            if isinstance(rx, dict):
                suggested = rx.get("suggested_fix", "")
            else:
                suggested = ""

            lines.append(f"### {icon} [{sev_zh}] {title}")
            lines.append(f"")
            lines.append(f"- **說明**：{explain}")
            lines.append(f"- **ID**：`{fid}`")
            lines.append(f"- **來源**：{source} | {ts}")
            lines.append(f"- **狀態**：{status}")
            if suggested:
                lines.append(f"- **建議**：{suggested}")
            lines.append(f"")

    summary = "\n".join(lines)

    # 寫入檔案
    out_path = home / "data" / "_system" / "review_summary.md"
    out_path.write_text(summary, encoding="utf-8")
    logger.info(f"[notify] Review summary generated: {len(all_findings)} findings → {out_path}")

    return summary
