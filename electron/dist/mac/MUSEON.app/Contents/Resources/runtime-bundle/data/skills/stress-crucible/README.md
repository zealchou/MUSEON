# Stress-Crucible — 壓力熔爐

> AI Agent 端到端壓力測試引擎

## 這是什麼

Claude Code 開發完回報「完成」，實測一堆 Bug——因為建設者跟測試者是同一人，天生有盲區。
Stress-Crucible 用從 OpenClaw 30 萬用戶生態系萃取的真實複雜情境，強制壓測 Agent 的極限。

**不測簡單功能。專測多工併行 × 長時間自主運行 × 系統層湧現行為的交叉地帶。**

## 解決什麼問題

| 問題 | 原因 | Stress-Crucible 怎麼解 |
|------|------|----------------------|
| 只測 Happy Path | 建設者心態：「我設計的流程當然能跑」 | 7 個真實複雜情境 × 4 維度（正常/異常/併行/系統觀察） |
| 不測多工併行 | 單任務隔離測試看不到干擾 | SC-03 在 5 分鐘內轟炸 8 個任務 |
| 不測時間推移 | 快照式驗收看不到隔日崩潰 | SC-02 模擬 72 小時時間軸 |
| 不測系統層 | 只看功能，不看心跳/路由/記憶 | 每個情境都附帶系統觀察規格 |
| 自己測自己放水 | Claude Code 寫的測試給自己過 | 建設者/破壞者角色強制分離 |

## 7 個核心情境（全部來自 OpenClaw DSE 研究）

| 編號 | 情境 | 測什麼 | 來源 |
|------|------|--------|------|
| SC-01 | 跨通道生活管家 | 日常多工 + 排程建立 + 隔日觸發 | OpenClaw 最常見使用模式 |
| SC-02 | 自主創業全流程 | 長時間自主 + 方向轉變 + 記憶持續 | OpenClaw 最極端使用模式 |
| SC-03 | 高頻多指令轟炸 | 併發極限 + 優先級 + 取消處理 | 真實用戶不會等上一個做完 |
| SC-04 | 越界行為偵測 | 安全邊界 + 權限控制 + 過度自主 | Jack Luo 交友平台事件 |
| SC-05 | 記憶持久化 | 跨 session + 記憶更新 + 容量 | OpenClaw Markdown 記憶退化 |
| SC-06 | 排程×外部事件交叉 | 時序衝突 + 冪等 + 時區 | 心跳每 30 分鐘但事件不排隊 |
| SC-07 | 開發+營運並行 | MuseClaw 專屬：邊鍛造 Skill 邊服務客戶 | Zeal 的實際日常 |

## 壓力等級

| 等級 | 時限 | 情境 | 何時用 |
|------|------|------|--------|
| Quick | 30 分鐘 | SC-03 + 系統健康 | 每次小改動後 |
| Standard | 2 小時 | SC-01 + SC-03 + SC-06 + 全系統 | 功能完成 |
| Extreme | 4 小時 | 全部 SC-01~07 + 混沌注入 | 部署前 |

## 安裝

將 `stress-crucible/` 資料夾放入 Claude Skills 目錄：
```
/mnt/skills/user/stress-crucible/
├── SKILL.md                          # Skill 本體
├── README.md                         # 本檔案
└── references/
    └── quality-baseline.md           # 品質基準線
```

## 使用

```
/crucible               → 主控台
/crucible quick          → 30 分鐘快速壓測
/crucible standard       → 2 小時標準壓測
/crucible extreme        → 4 小時極限壓測
/crucible scenario 3     → 只跑 SC-03
/crucible heartbeat      → 只測心跳
/crucible routing        → 只測 Mode 分流
/crucible report         → 查看最近報告
```

## 依賴

- **必要**：dna27（母體 AI OS）
- **深度耦合**：qa-auditor、eval-engine、orchestrator
- **建議啟用**：sandbox-lab、wee、morphenix

## 與 qa-auditor 的分工

| 維度 | qa-auditor | stress-crucible |
|------|-----------|----------------|
| 範圍 | 單腳本/單排程 | 多工 × 長時間 × 系統層 |
| 框架 | 4D 審計（D1~D4） | 4D + 真實情境庫 + 時間軸劇本 |
| 角色 | 可由開發者自跑 | 強制建設者/破壞者分離 |
| 報告 | QA_RECORD.md | CRUCIBLE_REPORT.md |
