---
name: dev-preflight
description: >
  開發前置飛行檢查。在對 Claude Code 下開發指令前，用白話提問覆蓋五張架構藍圖
  （功能地圖、連線地圖、分工地圖、部署地圖、動線驗證），把工程師覺得理所當然但
  非工程師不知道要問的東西挖出來。自動分級：小改動跳過、中型任務快速版、大型任務
  完整版。載入歷史教訓（來自 dev-retro）避免重複踩坑。產出藍圖摘要卡當作
  Claude Code 的上下文。觸發：使用者要建新功能、整合多系統、重構、下達涉及
  多檔案的開發指令、說「接起來」「新模組」「從零開始」時使用。不觸發：純修
  bug、文字修改、CSS 微調、已有完整藍圖的任務。
hub: evolution
io:
  inputs:
    - from: user
      field: dev_instruction
      required: true
    - from: knowledge-lattice
      field: dev_lesson_crystals
      required: false
    - from: dev-retro
      field: defense_rules
      required: false
  outputs:
    - to: user
      field: blueprint_summary_card
      trigger: always
    - to: plan-engine
      field: preflight_context
      trigger: on_demand
    - to: orchestrator
      field: complexity_signal
      trigger: conditional
memory:
  writes_to: knowledge-lattice
  crystal_type: dev-preflight-context
---

# Dev-Preflight：開發前置飛行檢查

> **飛機起飛前，機長不管飛了多少次，每次都要跑一遍 preflight checklist。**
> **不是因為不信任自己，是因為系統性遺漏靠記憶力防不住。**

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組。

**依賴**：`dna27` skill（母體 AI OS）
**閉環夥伴**：`dev-retro`（retro 教訓回灌 preflight 檢查項）

**本模組職責**：在開發前用白話提問覆蓋五張藍圖、自動分級、載入歷史教訓、產出藍圖摘要卡
**本模組不做**：不寫 code、不做架構設計文件、不做開發後審計（qa-auditor）、不做經驗回溯（dev-retro）

## 指令

| 指令 | 效果 |
|---|---|
| `/preflight` `/pf` | 啟動（自動判斷規模）|
| `/pf quick` | 強制快速版 |
| `/pf full` | 強制完整版 |
| `/pf history` | 顯示相關歷史教訓 |
| `/pf card` | 從已有上下文推斷，直接輸出藍圖摘要卡 |

## 任務規模分級

| 規模 | 條件 | 深度 | 題數 |
|------|------|------|------|
| S | 單檔修改、bug 修復 | 不需 preflight | 0 |
| M | 新功能但模組內 | 快速版 | 5-8 |
| L | 新模組、多系統整合 | 標準版 | 15-20 |
| XL | 全新子系統、架構變更 | 完整版 + 歷史比對 | 25-30 |

判斷關鍵字：「接起來/整合/多個系統」→ ≥L、「新建/從零」→ ≥L、「重構/遷移/架構」→ XL、「改一下/加一個」→ M/S。不確定→預設 M。

## 五張藍圖

完整的五張藍圖方法論、每張圖的完整版與快速版提問清單，見 `references/five-blueprints.md`。

以下是核心摘要：

### 📐 藍圖一：功能地圖
**核心問題**：這東西管什麼事、不管什麼事、跟誰有關係？
- 快速版：邊界（做/不做）+ 依賴（跟誰互動）

### 🕸️ 藍圖二：連線地圖（⚠️ 最常踩坑）
**核心問題**：誰跟誰要說話？用什麼方式？格式約定了嗎？斷了怎麼辦？
- 快速版：溝通對象與方式 + 失敗處理
- **M 以上任務不可跳過此藍圖（硬閘 HG-PF-NO-SKIP-MAP-2）**

### 📦 藍圖三：分工地圖
**核心問題**：程式碼放哪裡？拆得開嗎？改了這裡別的地方會壞嗎？
- 快速版：放在哪 + 影響範圍

### 🖥️ 藍圖四：部署地圖
**核心問題**：跑在哪？需要什麼？啟動有順序嗎？
- 快速版：環境與依賴

### 🎬 藍圖五：走一遍
**核心問題**：從觸發到結果走一遍每個步驟，都通嗎？怎麼驗證？
- 快速版：走一遍流程 + 成功定義

## 歷史教訓載入

每次啟動時自動比對 dev-retro 的 `dev-lesson` Crystal：
1. 用任務描述做關鍵字比對
2. 找到相關紀錄→在對應藍圖提問前插入 `⚠️ 歷史教訓` 提醒
3. dev-retro L5 新增的防線規則→併入對應藍圖的檢查項

## 輸出：藍圖摘要卡

跑完 preflight 產出結構化摘要卡（格式見 `references/card-template.md`），用途：
1. 貼到 Claude Code prompt 當上下文
2. 存到專案目錄作為開發紀錄
3. 完成後交給 dev-retro 做回溯比對

## 護欄

### 硬閘
- **HG-PF-NO-SKIP-MAP-2**：連線地圖在 M 以上不可跳過
- **HG-PF-NO-JARGON**：所有提問必須白話，工程術語必附翻譯
- **HG-PF-HISTORY-CHECK**：有相關歷史教訓必須主動提示

### 軟閘
- **SG-PF-OVERASK**：規模匹配，不用 XL 陣仗處理 M 任務
- **SG-PF-PACE**：每次最多 3-5 題，等回答再推進
- **SG-PF-CONTEXT-AWARE**：已從上下文推斷的不重複問

## 適應性深度

| 迴圈 | 深度 |
|---|---|
| fast_loop | 跳過或最多 2 題（邊界+連線）|
| exploration_loop | 標準版，按級別提問 |
| slow_loop | 完整版 + 歷史比對 + 藍圖摘要卡 |

## DNA27 親和對照

- Persona：tone=WARM、pace=STEADY、initiative=ASK
- RC 偏好：Group A（認知層）、Group C（結構化）
- RC 限制：Group E（不展開商業/戰略分析）

**跨 Skill 協同**：
- `dev-retro`：閉環。retro L5→preflight 檢查項；preflight 摘要卡→retro 比對基準
- `plan-engine`：Research 階段可調用 preflight 做認知補全
- `qa-auditor`：preflight 管寫前，qa-auditor 管寫後
- `dse`：dse 管深度技術研究，preflight 管廣度遺漏預防
- `query-clarity`：query-clarity 管通用問題品質，preflight 管開發指令品質
- `knowledge-lattice`：歷史教訓以 `dev-lesson` Crystal 存入
- `orchestrator`：3+ 模組任務可自動觸發 preflight
