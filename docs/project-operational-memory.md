# Project: Operational Memory（操作記憶層）

> **狀態**：設計完成，待實作
> **建立日期**：2026-03-24
> **教訓來源**：GitHub Pages DSE + 外部研究（CodeMem, ReMe, Devin Playbook, SWE-Bench-CL）
> **目標**：讓 MUSEON 記住「怎麼做」而不只是「做什麼」

---

## 問題陳述

MUSEON 有 49 個 Skill 和 4 個 Workflow，但：
- Skill 只有 SKILL.md 描述（意圖），沒有可執行代碼（實作）
- 每次 Claude session 重新讀描述後自行即興實作
- 成功了也不記錄怎麼成功的，失敗了也不記錄怎麼失敗的
- 下次 session 又從零開始

這是 CodeMem 論文（arXiv:2512.15813）定義的「Intent-Implementation Gap」。

---

## 設計方案：Procedure Crystal + Operational Contract

### 架構位置

```
Knowledge Lattice（知識結晶）→ 存「什麼是對的」
    ↓
Procedure Crystal（操作結晶）→ 存「怎麼做才對」← 新增
    ↓
Operational Contract（操作契約）→ 存「失敗怎麼辦」← 新增
    ↓
WEE（工作流演化）→ 追蹤「越做越好」
```

### Procedure Crystal 欄位設計

```yaml
crystal_type: PROCEDURE
domain: operations/<category>/<name>  # e.g. operations/github/pages-deploy
version: 4                             # 每次修正遞增
executable: scripts/workflows/<name>.sh
success_path:
  - step: "git worktree add"
    expected: "worktree created"
  - step: "cp report to reports/"
    expected: "file copied"
  - step: "git add + commit + push"
    expected: "push success"
  - step: "verify URL 200"
    expected: "HTTP 200"
known_failures:
  - pattern: "Actions has been disabled"
    root_cause: "GitHub 帳號 Actions 被停用"
    workaround: "改用 gh-pages + legacy mode"
    discovered: "2026-03-24"
  - pattern: "_reports/ 404"
    root_cause: "底線前綴被 Jekyll 忽略"
    workaround: "改用 reports/（無底線）"
    discovered: "2026-03-24"
last_success: "2026-03-24T12:45:00"
success_count: 3
failure_count: 7
confidence: 0.95
```

### Brain 整合流程

```
使用者/Workflow 觸發外部操作
    ↓
Brain 語義搜尋 Qdrant: domain=operations/* AND type=PROCEDURE
    ↓
├── 找到結晶 → 執行 `executable` 腳本
│   ├── 成功 → 更新 last_success + success_count + confidence↑
│   └── 失敗 → 更新 known_failures + failure_count + confidence↓
│
└── 找不到 → Claude 即興實作
    ├── 成功 → 自動建立新 Procedure Crystal
    └── 失敗 → 記錄失敗模式到 known_failures（空結晶）
```

### Nightly 操作經驗蒸餾

```
Nightly Pipeline 新增 Step:
1. 掃描 activity_log.jsonl 中的外部操作事件
2. 對照 Procedure Crystal 的 known_failures
3. 發現新失敗模式 → 自動追加到 known_failures
4. 發現成功率下降 → 生成 Morphenix 修復提案
5. 修剪 confidence < 0.3 且 6 個月未使用的結晶
```

---

## 實作迭代表

| 迭代 | 內容 | 狀態 |
|------|------|------|
| 1 | CLAUDE.md Tier 0 + scripts/workflows/ | ✅ 已完成 |
| 2 | operational-contract.md（第六張藍圖） | ✅ 已完成 |
| 3 | 五張藍圖同步 + 拓撲更新 | 🔲 本次 |
| 4 | Procedure Crystal schema + Qdrant collection | 🔲 待做 |
| 5 | Brain 整合（語義搜尋 + 自動結晶化） | 🔲 待做 |
| 6 | Nightly 操作經驗蒸餾 Step | 🔲 待做 |
| 7 | ReMe 精煉機制（修剪 + 上下文自適應） | 🔲 待做 |

---

## 參考文獻

- CodeMem: arXiv:2512.15813 — 可執行程式碼作為最佳程序性記憶
- ReMe: arXiv:2512.10696 — 動態程序性記憶精煉框架
- SWE-Bench-CL: arXiv:2507.00014 — 持續學習基準
- Devin Playbook: docs.devin.ai/product-guides/creating-playbooks
- Reflexion: arXiv:2303.11366 — 語言代理的語言強化學習
- Mem0: arXiv:2504.19413 — 生產級可擴展長期記憶
