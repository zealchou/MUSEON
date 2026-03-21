# WF-DAILY-REPORT-01：企業個案晨報自動發布工作流

**建立日期**：2026-03-10
**狀態**：已上線（Active）
**版本**：v1.0

---

## 一句話描述

每天早上自動生成 HBR 風格的企業個案分析報告，推送到 Telegram，並發布到 GitHub Pages 公開網址。

---

## 觸發條件

- **排程**：每日早上（由 MUSEON Pulse/cron 觸發）
- **手動**：Zeal 在 Telegram 輸入「晨報」等關鍵字

---

## 完整流程（六步驟）

```
1. 生成報告
   └─ business_case.py 生成當日 HTML 報告
      ├─ 成功個案 × 1（附分析框架）
      └─ 失敗個案 × 1（附教訓萃取）

2. 上傳備援（Gist）
   └─ 推送到 GitHub Gist（zealchou 帳號）
      → 作為備援，raw URL 保留

3. 發布主鏈（GitHub Pages）
   └─ 用 GitHub API PUT /repos/zealchou/museon-daily/contents/reports/{date}.html
      ├─ 報告頁：https://zealchou.github.io/museon-daily/reports/{YYYY-MM-DD}.html
      └─ 首頁更新：index.html 自動追加今日連結

4. Telegram 推播
   └─ 發送訊息到 Zeal 的 Telegram
      ├─ 標題：📰 每日企業個案晨報 Vol.XXX
      ├─ 日期
      └─ 連結：GitHub Pages 正式網址（非 Gist）

5. 記錄（可選）
   └─ 寫入 activity_log.jsonl
```

---

## 關鍵設定

| 項目 | 值 |
|------|---|
| GitHub 帳號 | `zealchou` |
| GitHub Repo | `museon-daily` |
| Pages 首頁 | `https://zealchou.github.io/museon-daily/` |
| 報告網址格式 | `https://zealchou.github.io/museon-daily/reports/YYYY-MM-DD.html` |
| GitHub Token | `.env` → `GITHUB_TOKEN` |
| 核心程式 | `src/museon/pulse/` 下的 `business_case.py`（或同等模組） |

---

## 依賴

- `GITHUB_TOKEN`：需要有 `repo` 寫入權限
- `TELEGRAM_TOKEN` + `TELEGRAM_CHAT_ID`：推播用
- GitHub repo `museon-daily` 已設定 Pages（main branch）

---

## 歷史

| 日期 | 事件 |
|------|------|
| 2026-03-10 | v1.0 建立。從 Gist raw URL 升級為 GitHub Pages 固定網址。 |

---

## 延伸方向（未來可做）

- 加入週報彙整（每週一合併該週 5 篇）
- RSS feed 讓訂閱者可以追蹤
- 多語言版本（中文 + 英文）
