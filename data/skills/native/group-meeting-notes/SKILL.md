---
name: group-meeting-notes
type: workflow
layer: product
hub: workflow
description: >
  群組對話會議記錄引擎。受 Plaud Note 啟發，針對 Telegram 群組對話（B2B 洽談、顧問互動）
  自動生成結構化 HTML 摘要報告，比 Plaud 多一層商業策略分析。
  涵蓋觸發詞：會議記錄、會議紀錄、整理會議、會議摘要、對話摘要、群組記錄、
  幫我整理、出記錄、整理成記錄、出會議記錄、整理對話、整理成會議記錄
io:
  inputs:
    - from: gateway
      field: chat_history
      required: true
  outputs:
    - to: knowledge-lattice
      field: meeting_insights
      trigger: always
connects_to:
  - knowledge-lattice
  - user-model
  - wee
memory:
  writes:
    - knowledge-lattice
    - wee
  reads:
    - user-model
stages:
  - id: 1
    name: "訊息萃取 + 角色識別"
    skills: [dna27]
    lens: "Telegram 群組 DB 讀取、發言者標記、附件清單"
    mode: serial
    gate:
      - "訊息萃取完成，角色識別正確"
    output_to: [2]
  - id: 2
    name: "DSE 第一性原理拆解"
    skills: [dse]
    lens: "底層需求、假設、商業賭注"
    mode: serial
    gate:
      - "核心洞察不為空"
    output_to: [3]
  - id: 3
    name: "多維度結構化分析"
    skills: [business-12, master-strategy, ssa-consultant]
    lens: "MECE 主題分類 + 決策紀錄 + 行動清單 + 關鍵洞見"
    mode: serial
    gate:
      - "決策與行動清單完整"
    output_to: [4, 5]
  - id: 4
    name: "半匿名化"
    skills: [dna27]
    lens: "B2B 匿名 / 內部保留全名"
    mode: serial
    gate:
      - "權限標記正確"
    output_to: [5]
  - id: 5
    name: "HTML 生成 + 品質檢查"
    skills: [aesthetic-sense]
    lens: "design_spec.md 合規、八段結構、品牌視覺"
    mode: serial
    gate:
      - "HTML 結構完整且視覺合規"
    output_to: [6]
  - id: 6
    name: "發佈"
    skills: [dna27]
    lens: "GitHub Pages 推送 + Telegram 通知"
    mode: serial
    gate:
      - "URL 可訪問"
    output_to: []
speed_paths:
  quick:
    stages: [1, 3, 5]
    depth: "精簡"
  standard:
    stages: [1, 2, 3, 5, 6]
    depth: "標準"
  deep:
    stages: [1, 2, 3, 4, 5, 6]
    depth: "完整"
---

# Group Meeting Notes (WF-GMN-01)
**群組對話會議記錄引擎**

DNA27 核心的外掛模組，受 Plaud Note 會議記錄架構啟發，
針對 MUSEON 群組對話（Telegram 群組、B2B 洽談、顧問互動）設計的
自動化結構性摘要與 HTML 報告生成工作流。

---

## DSE 第一性原理（設計哲學）

Plaud Note 的本質洞察：
- **Plaud 的流程**：音訊 → 轉錄 → AI 摘要 → 結構化輸出 → 角色感知多版本
- **MUSEON 的優勢**：跳過轉錄（已有文字），直接進入 AI 摘要，且比 Plaud 多一層**商業策略分析**

Plaud Note 三大 AI 加值點 → MUSEON 的對應能力：

| Plaud Note | MUSEON Group Meeting Notes |
|-----------|--------------------------|
| Speaker Diarization（誰說了什麼）| 群組成員角色識別 + 立場分析 |
| Action Items 自動萃取 | 行動清單 + 負責人 + 戰略優先級 |
| 多角色摘要版本 | DSE 第一性原理層 + 商業洞見層 |
| 可溯源（點擊返回原音段）| 引用原始訊息 + 時間軸還原 |

**MUSEON 的差異化**：不只記錄「說了什麼」，更挖掘「為什麼說」「下一步怎麼走」。

---

## 工作流（七步）

```
觸發（手動指令 或 自動偵測群組對話結束）
  ↓
Step 1：訊息萃取 + 角色識別
  從 Telegram 群組 DB 或對話記錄讀取指定成員/時間段的訊息
  標記：發言者、時間、附件清單
  ↓
Step 2：DSE 第一性原理拆解
  問：「這段對話的本質需求是什麼？」
  「對方真正想要的是什麼？底層假設是什麼？」
  「這段關係在商業層面的核心賭注是什麼？」
  ↓
Step 3：多維度結構化分析
  - 討論主題分類（MECE：不重複、不遺漏）
  - 決策紀錄（已做 / 待做 / 擱置）
  - 行動清單（負責人 + 優先級 + 依賴關係）
  - 關鍵洞見（4 個以內，每個有一句核心觀點）
  - 未解問題（不要假裝已解決）
  ↓
Step 4：半匿名化（視需要）
  B2B 洽談：保留角色 + 產業，匿名個人姓名
  內部使用：保留全名，加入權限標記
  ↓
Step 5：HTML 生成（design_spec.md 合規）
  結構：Hero → 參與者 → 時間軸 → DSE 洞察 → 關鍵洞見 → 決策表 → 行動清單 → 下一步
  視覺：Ember 主色 + Cormorant Garamond 大標 + Parchment 背景
  ↓
Step 6：品質檢查
  - HTML 結構完整
  - design_spec 合規（顏色/字型/間距）
  - 決策紀錄無遺漏
  ↓
Step 7：發佈
  GitHub Pages 推送 → 外部鏈接 → Telegram 通知 Zeal
```

---

## 輸出結構（HTML 八段）

| 段落 | 內容 |
|------|------|
| **Hero** | 對話主題、時間跨度、Session 數量、交付物統計 |
| **參與者** | 每人卡片（角色、職能、互動定位） |
| **時間軸** | 每個 Session 的日期、主題、素材清單、核心討論 |
| **Pull Quote** | 最能代表這段對話核心張力的一句話 |
| **DSE 洞察** | 第一性原理拆解（底層需求、假設、賭注） |
| **關鍵洞見** | 4 個不能忽略的商業/關係訊號 |
| **決策紀錄** | 表格：決策事項 × 負責方 × 狀態（已完成/待執行/待確認） |
| **行動清單** | 編號 + 負責人 + 具體說明 + 戰略背景 |
| **下一步** | 4 宮格優先級排序（高 + 中兩個各兩個） |

---

## 觸發方式

**手動觸發：**
- `/gmn @群組成員` — 對指定成員的群組對話生成摘要
- `/meeting-notes` — 互動式引導（詢問時間段、對象、場景）
- `/gmn --all-today` — 今日所有群組對話的摘要

**自動觸發（未來）：**
- 偵測群組對話中出現「結束語」（謝謝、好的、下次再聊）
- 定期排程（例如每週一整理上週群組互動）

---

## 依賴 Skill

| Skill | 使用場景 |
|-------|---------|
| `dna27` | 核心路由、護欄 |
| `dse` | Step 2 第一性原理拆解 |
| `business-12` | 商業關係分析（12 力哪幾力在發揮？） |
| `master-strategy` | 戰略層面的局勢研判 |
| `aesthetic-sense` | HTML 視覺品質審計 |
| `ssa-consultant` | B2B 洽談場景的顧問視角 |

---

## 檔案命名規則

```
group_meeting_notes_{人名/群組}_{YYYYMMDD}.html
```

範例：
- `group_meeting_notes_joh_20260318.html`
- `group_meeting_notes_team_weekly_20260317.html`

GitHub Pages 路徑：
```
zealchou.github.io/museon-reports/reports/group_meeting_notes_*
```

---

## 與 Plaud Note 的差異定位

| 維度 | Plaud Note | MUSEON GMN |
|------|-----------|------------|
| 輸入來源 | 錄音 | 文字對話（Telegram/群組） |
| 核心加值 | 轉錄 + 摘要 | 商業策略分析 + DSE 洞察 |
| 角色感知 | 銷售/管理/執行版 | 依場景：B2B/內部/顧問 |
| 輸出格式 | PDF/文字 | 精美 HTML（品牌合規） |
| 發佈能力 | 無 | GitHub Pages + Telegram 推播 |
| 業務情報 | 無 | 關係深度、商業賭注、戰略優先級 |

---

## 版本記錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.0 | 2026-03-19 | 初版鍛造，基於 Plaud Note DSE 分析 |
