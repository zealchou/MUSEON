# Operational Contract — 操作契約表 v1.0

> **用途**：定義「每個外部操作的預期失敗、重試策略、降級方案」。第六張工程藍圖。
> **比喻**：保險契約——不是怕出事，是出事時知道怎麼處理。
> **更新時機**：新增外部操作的 Skill/Workflow 時，必須在同一個 commit 中新增對應的契約。
> **建立日期**：2026-03-24（GitHub Pages DSE 根因修復後建立）
> **搭配**：`scripts/workflows/` 可執行腳本、`docs/persistence-contract.md`（水電圖）

---

## 設計原則

1. **每個外部操作必有契約**：沒有契約的外部操作 = 沒有保險的施工
2. **預期失敗清單先於腳本**：先想清楚會怎麼壞，再寫怎麼做
3. **驗證是操作的一部分**：做完不確認 = 沒做完
4. **降級 > 硬失敗**：能降級就不要直接報錯

---

## 操作契約表

### OP-01: GitHub Pages 報告發布

| 屬性 | 值 |
|------|---|
| **操作名稱** | 發布 HTML 報告到 GitHub Pages |
| **可執行腳本** | `scripts/publish-report.sh` (v4.0) |
| **觸發者** | report-forge output / Claude 手動 / MUSEON Workflow |
| **外部依賴** | GitHub API、GitHub Pages CDN (Fastly) |

| 預期失敗 | 根因 | 重試策略 | 降級方案 |
|---------|------|---------|---------|
| `git push` 認證失敗 | OAuth token 過期 | `gh auth login` → 重試 | 通知使用者手動 push |
| CDN 快取 404 | Fastly 快取了先前的 404 | 30s×4 重試（共 2 分鐘） | 通知使用者等 5-10 分鐘 |
| `_reports/` 底線 404 | Jekyll 忽略底線前綴 | 改用 `reports/` | — |
| Actions 停用 | 帳號級別限制 | — | 改用 gh-pages + legacy mode |
| `main/docs` 不觸發建構 | Pages API 設定不實際生效 | — | 改用 gh-pages 分支 |
| git worktree 殘留 | 上次失敗未清理 | `git worktree prune` → 重建 | — |

### OP-02: Gateway 安全重啟

| 屬性 | 值 |
|------|---|
| **操作名稱** | 重啟 MUSEON Gateway daemon |
| **可執行腳本** | `scripts/workflows/restart-gateway.sh` (v1.0) |
| **觸發者** | 迭代完成 / 程式碼更新 / 手動 |
| **外部依賴** | launchd、macOS keychain |

| 預期失敗 | 根因 | 重試策略 | 降級方案 |
|---------|------|---------|---------|
| busy session 進行中 | 正在處理群組訊息 | 等 60s timeout → 重檢 | 通知群組「維護中」→ 等完再重啟 |
| 重啟後 brain=None | OAuth/API key 失效 | 檢查 `gh auth status` → 重新登入 | 手動注入 token |
| port TIME_WAIT | 上次 kill -9 殘留 | 等 30s（ThrottleInterval） | `sys.exit(1)` 停止撞牆 |
| 健康檢查超時 | 啟動慢/記憶載入中 | 30s 等待 | 手動 `curl /health` |
| 群組訊息遺失 | 重啟期間的未處理訊息 | — | 補處理：檢查重啟前 5 分鐘的訊息 |

### OP-03: Telegram 訊息發送

| 屬性 | 值 |
|------|---|
| **操作名稱** | 透過 Telegram Bot API 發送訊息 |
| **可執行腳本** | 內建於 Gateway `channels/telegram.py` |
| **觸發者** | Brain response / 報告推播 / 系統通知 |
| **外部依賴** | Telegram Bot API |

| 預期失敗 | 根因 | 重試策略 | 降級方案 |
|---------|------|---------|---------|
| 429 Too Many Requests | Telegram rate limit | exponential backoff (1s→2s→4s) | 排入佇列延後 |
| 400 Bad Request | Markdown 格式錯誤 | 移除 MarkdownV2 → 純文字重送 | — |
| chat not found | 群組 ID 變更/bot 被移除 | — | 記錄錯誤 + 通知使用者 |
| 訊息過長 | 超過 4096 字元 | `_split_long_text()` 自動分段 | — |
| 網路逾時 | 網路不穩 | 3 次重試 × 5s 間隔 | 本地暫存等恢復 |

### OP-04: HTML 報告生成

| 屬性 | 值 |
|------|---|
| **操作名稱** | 生成符合設計規範的 HTML 報告 |
| **可執行腳本** | 待建立 `scripts/workflows/generate-report.sh` |
| **觸發者** | report-forge / 投資分析工作流 / 品牌行銷工作流 |
| **外部依賴** | 無（純本地檔案操作） |

| 預期失敗 | 根因 | 重試策略 | 降級方案 |
|---------|------|---------|---------|
| 設計規範未載入 | 未讀 `design_spec.md` | 強制讀取後重生成 | 使用預設樣式 |
| 檔案過大 (>5MB) | 報告內容太長 | 壓縮圖片/移除冗餘 CSS | 分頁報告 |
| 本地預覽與 Pages 不一致 | CSS CDN 版本差異 | 內嵌所有 CSS（self-contained） | — |

---

## 契約覆蓋率

| 操作類型 | 已有契約 | 有可執行腳本 | 狀態 |
|---------|---------|------------|------|
| GitHub Pages 發布 | ✅ OP-01 | ✅ publish-report.sh | 完整 |
| Gateway 重啟 | ✅ OP-02 | ✅ restart-gateway.sh | 完整 |
| Telegram 發送 | ✅ OP-03 | ⚠️ 內建（非獨立腳本） | 契約完整，腳本內建 |
| HTML 報告生成 | ✅ OP-04 | ❌ 待建立 | 契約完整，腳本待做 |
| Qdrant 向量索引 | ❌ | ❌ | 待新增 |
| Nightly Pipeline | ❌ | ⚠️ 內建 | 待新增 |

---

## 新增契約的模板

```markdown
### OP-XX: [操作名稱]

| 屬性 | 值 |
|------|---|
| **操作名稱** | [描述] |
| **可執行腳本** | `scripts/workflows/[name].sh` |
| **觸發者** | [誰會觸發此操作] |
| **外部依賴** | [列出所有外部服務] |

| 預期失敗 | 根因 | 重試策略 | 降級方案 |
|---------|------|---------|---------|
| [失敗模式] | [為什麼會失敗] | [怎麼重試] | [重試也失敗怎麼辦] |
```
