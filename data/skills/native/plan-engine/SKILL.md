---
name: plan-engine
type: on-demand
layer: evolution
io:
  inputs:
    - from: user
      field: chaotic_start
      required: true
  outputs:
    - to: orchestrator
      field: clear_plan
      trigger: conditional
    - to: user
      field: plan_document
      trigger: always
connects_to:
  - orchestrator
memory:
  writes:
    - wee
  reads:
    - user-model
    - knowledge-lattice
description: >
  Plan-Engine（計畫引擎）— DNA27 核心的外掛模組，
  工作流前段引擎，用持久化 .md 檔案將混沌起點收斂為清晰計畫後交棒。
  融合 Boris Tane 的 Annotation Cycle 方法論與 MUSEON 的 Skill 生態系，
  透過 Research → Plan → Annotate → Todo → Execute → Close 六階段流程，
  物理隔離「想」與「做」，把 AI 的認知狀態透明化，讓人類判斷力精準注入。
  核心命題：AI 協作中最貴的失敗不是做錯，是基於錯誤假設往前衝。
  plan.md 作為人機共享的可變狀態，解決三個問題：
  (1) AI 猜測而非查證導致的方向性錯誤；
  (2) 對話式指令無法精準定位問題的溝通損耗；
  (3) 長上下文摘要壓縮導致的資訊遺失。
  觸發時機：(1) /plan 指令強制啟動；
  (2) 自然語言偵測——任務涉及多檔案修改、不可逆操作、重構、新功能開發、
  整合、遷移、架構變更等複雜任務時自動建議；
  (3) 其他 Skill 調用 plan-engine 作為前段資訊搜集與分析階段。
  涵蓋觸發詞：計畫、plan、研究一下再做、先別動手、先看看、
  重構、新功能、整合、遷移、架構、複雜任務、多步驟。
  不限 coding 場景——商業企劃、投資分析、Skill 鍛造、內容創作等
  任何「不能一步到位」的複雜任務皆適用。
  與 orchestrator 互補：orchestrator 管跨 Skill 編排，plan-engine 管工作流前段收斂。
  與 wee 互補：wee 管工作流生命週期演化，plan-engine 管單次任務的計畫品質。
  與 dse 互補：plan-engine 的 Research 階段可調用 dse 做技術深度研究。
  與 knowledge-lattice 互補：plan-engine 收尾摘要可結晶化存入 lattice。
---

# Plan-Engine：計畫引擎 — 工作流前段收斂系統

## 核心命題

**別一上來就動手。先研究、再計畫、讓人批註到滿意，然後才執行。**

- AI 最貴的失敗模式不是語法錯或邏輯錯，是「在隔離環境下正確但放進真實系統就炸」
- 對話是線性的、會消失的；plan.md 是結構化的、持久的、可批註的
- 把 AI 的認知狀態（知道什麼、假設什麼、還沒查什麼）攤在陽光下，讓人一眼看穿
- 計畫定案後，執行應該是「無聊的機械勞動」——所有決策都在批註循環裡完成了

---

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組（pluggable plus）。

**依賴**：`dna27` skill（母體 AI OS）

**本模組職責**：
- 為複雜任務建立持久化的 plan.md 作為人機共享狀態
- 強制 AI 在動手前完成研究，消滅未驗證假設
- 提供批註循環介面，讓人的判斷力精準注入計畫
- 透明化 AI 的認知狀態（已確認 vs 假設 vs 未知）
- 計畫定案後交棒給執行 Skill，不干預後段
- 收尾時歸檔摘要，累積可複用的情報資產

**本模組不做**：
- 不做跨 Skill 編排（那是 orchestrator 的工作）
- 不做工作流生命週期管理（那是 wee 的工作）
- 不做系統級迭代（那是 morphenix 的工作）
- 不替使用者做決策（只呈現資訊、標記假設、等待批註）
- 不在小任務上過度工程化（有明確的不觸發條件）

**與其他外掛的協作**：

| 外掛 | 協作方式 |
|-----|---------|
| orchestrator | orchestrator 可調用 plan-engine 作為工作流前段；plan-engine 計畫定案後交棒給 orchestrator 編排後段 |
| wee | plan-engine 管單次任務計畫品質，wee 管跨任務的熟練度演化。plan-engine 的收尾摘要可餵入 wee 的結果萃取 |
| dse | Research 階段涉及 AI 技術研究時，調用 dse 做深度技術盤點 |
| market-core | Research 階段涉及市場分析時，調用 market-core 做數據搜集 |
| consultant-communication | Plan 階段需要結構化商業文書時，調用 SCQA 框架 |
| knowledge-lattice | 收尾摘要結晶化存入 lattice，累積跨任務情報資產 |
| qa-auditor | Execute 階段涉及程式碼時，調用 qa-auditor 做品質護欄 |
| eval-engine | 追蹤 plan-engine 的使用效果：計畫準確度、revert 頻率、批註循環次數 |

---

## 觸發與入口

**指令觸發**：
- `/plan` — 對當前任務建立 plan.md，啟動完整六階段流程
- `/plan lite` — 精簡版（Research + Plan，跳過 Todo，適合 exploration_loop）
- `/plan status` — 顯示當前 plan.md 的階段與進度
- `/plan annotate` — 告訴 AI「我加了批註，處理它」
- `/plan execute` — 計畫定案，全部執行
- `/plan close` — 收尾歸檔 + 刪除 plan.md
- `/plan revert` — 復原執行中的變更，記錄原因

**自然語言自動偵測**：
當偵測到以下訊號時，主動建議啟動 plan-engine：
- 任務涉及 3 個以上檔案修改
- 任務預估執行超過 10 分鐘
- 任務涉及不可逆操作（資料庫 migration、API 變更、刪除操作）
- 使用者指令包含「重構」「新功能」「整合」「遷移」「架構」等關鍵詞
- 任務範圍模糊、需要先釐清方向

**不觸發條件**（直接執行，不建立 plan.md）：
- 單一檔案、30 行以下的修改
- 原因明確、範圍確定的 bug fix
- 文字潤飾、格式調整
- 使用者明確說「直接做」或「不用計畫」

**被調用模式**：
其他 Skill 可調用 plan-engine 作為前段。例如：
- orchestrator 編排複雜任務時，先調用 plan-engine 做資訊搜集
- acsf 鍛造 Skill 時，用 plan-engine 管理鍛造計畫
- workflow 系列執行多階段任務時，用 plan-engine 管理單階段的研究與計畫

---

## 核心工作流程：六階段

```
觸發判斷
  │
  ├─ 不觸發 → 直接執行
  │
  └─ 觸發 → 建立 plan.md
              │
              ├── Stage 1：Research（研究）
              │     └── 輸出：Research Log（情報區）
              │
              ├── Stage 2：Plan（計畫）
              │     └── 輸出：Plan 區（方案 + 變更 + 風險）
              │
              ├── Stage 3：Annotate（批註循環 ×1-6）
              │     └── 人批註 → AI 更新 → 人再批註 → ...
              │
              ├── Stage 4：Todo（任務分解）
              │     └── 輸出：核取清單
              │
              ├── Stage 5：Execute（執行）
              │     └── 機械化執行，進度回寫 plan.md
              │
              └── Stage 6：Close（收尾歸檔）
                    └── 摘要 → 開發紀錄 → 刪除 plan.md
```

### Stage 1：Research（研究）

**目標**：建立情報基礎，消滅假設。不猜，查。

**執行規則**：
1. 先讀相關原始碼、文件、資料夾結構——不靠記憶猜測
2. 查官方文件確認技術限制——不假設 API 行為
3. 檢查現有系統的慣例和模式——不忽略既有架構
4. 所有發現寫入 plan.md 的 Research Log 區

**語言的精確度**：
研究指令中使用「深入」「詳細」「完整理解」等詞彙，向 AI 明確表達表面閱讀不可接受。

**參考實作技巧**：
如果有好的開源實作或既有系統中的類似模式，直接貼入作為參考。AI 有具體範本時產出品質顯著提升。

**非 coding 場景的 Research 變體**：

| 場景 | Research 做什麼 |
|------|----------------|
| Coding | 讀 codebase + 查技術文件 + 檢查既有模式 |
| 商業企劃 | 讀客戶資料 + 查市場數據 + 盤點競品 |
| 投資分析 | 讀標的資料 + 查總經數據 + 盤點歷史表現 |
| Skill 鍛造 | 讀相關 Skill + 查 ACSF 流程 + 檢查 plugin-registry |
| 內容創作 | 讀品牌規範 + 查受眾資料 + 盤點過往內容 |

### Stage 2：Plan（計畫）

**目標**：把研究成果轉化為可批註的執行計畫。

**計畫必須包含**：
- 方法說明：為什麼選這個方案、替代方案是什麼、權衡是什麼
- 變更清單：具體要改什麼、在哪裡改、為什麼（coding 場景含程式碼片段）
- 風險與代價：甜頭、代價、回滾方案三者同框
- Skill 路由建議：這個任務建議串接哪些 Skill（人在批註中確認或刪除）

### Stage 3：Annotate（批註循環）

**目標**：讓人的判斷力精準注入計畫。

**流程**：
1. AI 寫完 plan.md → 交給人
2. 人在文件中直接寫批註（行內筆記、刪除線、`[NOTE: ...]`、任何格式）
3. 人說「處理批註」或 `/plan annotate` → AI 讀取所有批註，更新計畫
4. 重複，直到人滿意

**AI 行為規則**：
- 收到「處理批註」指令後，**只更新 plan.md，絕不開始執行**
- 每次更新後，重新檢查假設區，標記哪些假設被批註消滅了
- 如果批註跟 Research Log 矛盾，以人的批註為準，但標記出矛盾點讓人知道
- 批註超過 6 次時，建議重新評估任務範圍是否太大

**為什麼批註比對話好**：
- 對話是線性的，批註是空間的——你直接指向問題所在的位置
- 對話會被上下文壓縮吃掉，plan.md 是持久的檔案
- 批註強制你思考具體位置的具體問題，而不是模糊地「感覺哪裡不對」

### Stage 4：Todo（任務分解）

**目標**：把計畫拆成可追蹤的核取清單。

**規則**：
- 每個 Task 是可在 10 分鐘內完成的原子操作
- 按 Phase 分組，有明確的執行順序
- 寫入 plan.md 的 Todo 區，執行時作為進度追蹤器

### Stage 5：Execute（執行）

**目標**：機械化執行，不做創意決策。

**執行時 AI 的行為**：
- 按 Todo 清單順序執行，完成一項就在 plan.md 裡標記 `[x]`
- 所有任務完成前不停止
- 持續檢查類型 / 語法 / 邏輯，確保不引入新問題
- 遇到計畫裡沒預期到的問題 → **停下來**，在 plan.md 新增 ⚠️ 標記，等人決定。不自己猜解法

**Revert over Patch**：
走錯方向時，不修補，復原重來。縮小範圍後重新進入 Plan 或 Annotate 階段。每次 revert 記錄原因。

**執行中人的反饋極簡化**：
- 「這個函數沒實作」
- 「寬一點」
- 「這裡有 2px 間隙」
- 截圖比文字描述更快

### Stage 6：Close（收尾歸檔）

**流程**：
1. 所有 Todo 完成 → 生成 plan.md 執行摘要
2. 摘要記錄到開發紀錄（含：做了什麼、遇到什麼問題、學到什麼）
3. Research Log 中有價值的情報 → 結晶化存入 knowledge-lattice
4. 如果有 revert → revert 原因記入 Revert Log，作為未來護欄
5. 刪除原 plan.md（摘要已歸檔，原檔不需保留）

---

## plan.md 檔案模板

```markdown
# plan.md — [任務名稱]

> 狀態：[Draft / Annotating / Ready / Executing / Done]
> 建立時間：[datetime]
> 批註輪次：[0/6]

---

## 🔍 Research Log（情報區 — AI 用）

### 已確認事實
- [x] [事實描述] — 來源：[檔案路徑 / 文件 URL / 指令輸出]

### 已查詢文件
- [文件名或 URL] → [關鍵摘要，2-3 句]

### ⚠️ 假設（未驗證，執行前必須確認）
- [ ] 假設 [內容] → 驗證方式：[怎麼查]

---

## 📋 Plan（計畫區 — 人用）

### 方法說明
[為什麼選這個方案、替代方案、權衡]

### 變更清單
1. [位置] — [做什麼] — [為什麼]

### 程式碼片段 / 具體方案（如適用）
[關鍵變更的草稿]

### Skill 路由建議
- [建議串接的 Skill 及原因]

### 風險與代價
- 甜頭：[好處]
- 代價：[付出]
- 回滾方案：[失敗時怎麼恢復]

---

## ✅ Todo

### Phase 1：[階段名]
- [ ] Task 1.1：[具體任務]
- [ ] Task 1.2：[具體任務]

### Phase 2：[階段名]
- [ ] Task 2.1：[具體任務]

---

## 📝 Revert Log
| 時間 | 原因 | 影響範圍 | 教訓 |
|------|------|---------|------|

---

## 📦 收尾摘要（Close 時填寫）
- 完成了什麼：
- 遇到的問題：
- 學到的教訓：
- 歸檔到：[knowledge-lattice / 開發日誌]
```

---

## 護欄

### 硬閘

**HG-PLAN-NO-GUESS**：Research Log 有未驗證假設時，不得進入 Execute 階段。每個假設必須被消滅（查證為事實，或推翻後修改計畫）才能往下走。

**HG-PLAN-NO-SKIP-ANNOTATE**：slow_loop 下，Plan 必須經過至少 1 次人工批註。AI 不可自己寫完計畫就自己執行。

**HG-PLAN-REVERT-OVER-PATCH**：執行中發現方向性錯誤時，復原重來，不打補丁。每次 revert 必須記錄原因。

**HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL**：收到「處理批註」指令時，只更新 plan.md，絕不開始執行。必須收到明確的執行指令（`/plan execute` 或「全部執行」）才進入 Execute。

### 軟閘

**SG-PLAN-OVERWEIGHT**：小任務不啟動完整流程。單一檔案、30 行以下改動、原因明確的 bug fix，直接做。使用者說「直接做」「不用計畫」時，尊重指令。

**SG-PLAN-ANNOTATE-LIMIT**：批註循環超過 6 次時，建議人重新評估——任務範圍是否太大？是否該拆成多個獨立任務？

**SG-PLAN-SCOPE-CREEP**：計畫中出現 nice-to-have 項目時，主動標記並建議移除。防止範圍蔓延。

---

## 適應性深度控制

| DNA27 迴圈 | plan-engine 行為 |
|-----------|-----------------|
| fast_loop | 跳過 plan-engine，直接執行。小任務不需要計畫。 |
| exploration_loop | 精簡版：Research + Plan + 1 次 Annotate → Execute。用 `/plan lite`。 |
| slow_loop | 完整版：全六階段，Annotate 可達 6 次，Todo 細粒度分解，收尾歸檔完整。 |

---

## 系統指令

| 指令 | 效果 |
|------|------|
| `/plan` | 對當前任務建立 plan.md，啟動完整流程 |
| `/plan lite` | 精簡版（Research + Plan + 1 次 Annotate → Execute） |
| `/plan status` | 顯示當前 plan.md 的階段、批註輪次、假設消滅進度 |
| `/plan annotate` | 等同「我加了批註，處理它，先不要執行」 |
| `/plan execute` | 計畫定案，全部執行 |
| `/plan close` | 收尾歸檔 + 刪除 plan.md |
| `/plan revert` | 復原執行中的變更 + 記錄 revert 原因 |

---

## DNA27 親和對照

啟用 plan-engine 時：
- Persona 旋鈕建議：
  - Research 階段：tone → NEUTRAL、pace → SLOW、initiative → OBSERVE（不急著提方案，先查清楚）
  - Plan + Annotate 階段：tone → WARM、pace → MEDIUM、initiative → SUGGEST（提方案但等批註）
  - Execute 階段：tone → NEUTRAL、pace → FAST、initiative → DRIVE（機械化執行，不猶豫）
- 偏好觸發的反射叢集：RC-C3（結構化思考）、RC-D1（外部工具優先——先查再說）
- 限制使用的反射叢集：RC-A1（不要在 Research 階段就急著給答案）

與其他外掛的協同：
- **orchestrator**：plan-engine 可被 orchestrator 調用作為前段，計畫定案後交棒
- **wee**：收尾摘要可餵入 wee 的結果萃取五問
- **dse**：Research 階段涉及 AI 技術時調用
- **market-core**：Research 階段涉及市場分析時調用
- **consultant-communication**：Plan 階段需要結構化商業文書時調用
- **knowledge-lattice**：收尾摘要結晶化存入
- **qa-auditor**：Execute 階段涉及程式碼品質時調用
- **eval-engine**：追蹤 plan-engine 使用效果（計畫準確度、revert 頻率）
- **sandbox-lab**：Plan 階段需要驗證假說時，可先進 sandbox 測試再寫入計畫
