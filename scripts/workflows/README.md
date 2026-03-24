# scripts/workflows/ — 可執行工作流腳本

> **建立日期**：2026-03-24
> **設計目的**：解決「Skill/Workflow 只有描述沒有可執行代碼」的系統性問題

## 設計哲學

MUSEON 的 SKILL.md 定義了「做什麼」（intent），但涉及外部操作的 Workflow
需要「怎麼做」（implementation）的可執行腳本。

**沒有腳本 → Claude 每次即興實作 → 路徑不同 → 反覆失敗**

此目錄存放所有需要外部操作的 Workflow 的可執行腳本。

## 現有腳本

| 腳本 | 用途 | 對應 Skill/Workflow |
|------|------|-------------------|
| `publish-report.sh` | 發布 HTML 報告到 GitHub Pages | report-forge output |

## 新增腳本的規範

1. 腳本必須是 **idempotent**（重複執行不會壞）
2. 腳本必須有 **驗證步驟**（不只是做完，還要確認做對了）
3. 腳本必須有 **清楚的錯誤訊息**
4. 腳本的 `set -e` 確保失敗即停
5. 每個腳本在 `memory/` 目錄下有對應的經驗記錄

## 與 SKILL.md 的關係

```
SKILL.md（描述意圖 + 觸發詞）
    ↓
DNA27 路由（判斷啟用哪個 Skill）
    ↓
scripts/workflows/<name>.sh（可執行實作）  ← 此目錄
    ↓
Claude 執行腳本（不即興，跑腳本）
```
