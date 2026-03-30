---
name: workflow-brand-consulting
type: workflow
layer: workflow
hub: workflow
stages:
  - id: A
    name: "品牌發現（Discovery）"
    skills: [brand-discovery]
    lens: "50 題漸進式訪談 × 動態問題路由 × 六主題結構化蒐集"
    mode: serial
    gate:
      - "client_brand_brief 完整填寫（6 主題全部有資料）"
      - "客戶確認：摘要準確反映現況"
    output_to: [B]
  - id: B
    name: "品牌建構（Brand Build）"
    skills: [brand-builder, storytelling-engine, consultant-communication]
    lens: "七框架深度分析 × 三定位選項 × 品牌策略包產出"
    mode: serial
    gate:
      - "客戶確認選定一個定位路徑"
      - "brand_strategy_package 完整產出"
    output_to: [C, D]
  - id: C
    name: "識別系統（Identity System）"
    skills: [brand-builder, aesthetic-sense, text-alchemy, c15]
    lens: "視覺規格書 + 語言規格書 + Do/Don't 範例"
    mode: serial
    gate:
      - "客戶確認視覺方向"
      - "客戶確認語言規範"
    output_to: [D]
  - id: D
    name: "操作手冊（Operations Manual）"
    skills: [text-alchemy, c15, storytelling-engine, brand-builder]
    lens: "社群操作規範 + 內容策略矩陣 + 貼文範本 × 10 + 品牌審計清單"
    mode: serial
    gate:
      - "操作手冊通過品牌一致性審計"
    output_to: [E]
  - id: E
    name: "HTML 手冊渲染（Render）"
    skills: [report-forge, aesthetic-sense]
    lens: "依 brand-manual-template.html + design_spec.md 渲染完整品牌手冊"
    mode: serial
    gate:
      - "HTML 通過美感審計"
      - "所有章節完整（6 章節）"
    output_to: []
speed_paths:
  fast_loop:
    stages: [A, B, E]
    depth: "精簡（跳過 C/D 操作手冊，直接渲染策略 HTML）"
  exploration_loop:
    stages: [A, B, C, D, E]
    depth: "標準（完整五階段）"
  slow_loop:
    stages: [A, B, C, D, E]
    depth: "完整（每階段帶品質審計 + 客戶確認 + 修訂迴圈）"
io:
  inputs:
    - from: user
      field: client_context
      required: true
      description: "客戶公司基本資訊，作為 brand-discovery 的啟動語境"
  outputs:
    - to: user
      field: brand_manual_html
      trigger: always
      description: "完整品牌手冊 HTML 檔案"
    - to: wee
      field: execution_trace
      trigger: always
    - to: knowledge-lattice
      field: brand_crystal
      trigger: on_completion
connects_to:
  - brand-discovery
  - brand-builder
  - brand-identity
  - storytelling-engine
  - aesthetic-sense
  - text-alchemy
  - c15
  - consultant-communication
  - report-forge
  - orchestrator
  - knowledge-lattice
  - wee
memory:
  writes:
    - target: wee
      type: proficiency
      condition: 工作流完成時
    - target: knowledge-lattice
      type: brand_crystal
      condition: 客戶品牌策略確認時
description: >
  品牌建構顧問工作流（WF-BRD-01）— MUSEON 第四條預設工作流範本。
  國際級品牌定位與視覺操作手冊產出工作流，對標奧美等級品牌顧問服務。
  適用客戶：任何行業（B2B/B2C）、任何規模（新創/成長/重塑）的品牌建構需求。
  起始狀態：有想法但品牌模糊，或有品牌但需要重新定位，或需要可交付他人執行的操作手冊。
  服務週期：1-3 次深度對話（Discovery）+ 1-2 次策略確認（Brand Build）+ 最終交付 HTML。
  核心交付物：互動式 HTML 品牌手冊（含策略/識別/語言/操作四大部分）。
  五階段：A Discovery（漸進式訪談）→ B Brand Build（七框架分析）→
          C Identity System（視覺+語言規格）→ D Operations Manual（操作指南）→
          E HTML Render（手冊渲染）。
  觸發時機：(1) /brand-manual 指令強制啟動；
  (2) orchestrator 偵測到品牌建構 + 手冊交付需求時自動建議；
  (3) 自然語言偵測——「幫客戶做品牌」「出品牌手冊」「國際級品牌顧問」時。
  與 workflow-svc-brand-marketing（WF-SVC-01）的差異：
  WF-SVC-01 = 中小服務業快速品牌行銷，交付物是行動方案；
  WF-BRD-01 = 任何行業深度品牌建構，交付物是可傳承的品牌手冊。
  此工作流依賴 orchestrator 做階段編排，依賴 dna27 做迴圈路由與護欄判斷。
---

# WF-BRD-01：品牌建構顧問工作流

> **客戶畫像**：想要一份可以交給任何人（設計師/小編/合作夥伴）就能執行的品牌手冊。
> 不只是靈感，而是規範——讓品牌不因為換了執行者就變了樣。
> 最終產出：一份打開就能用的 HTML 品牌手冊。

---

## 外掛合約

**依賴**：
- `dna27` skill（母體 AI OS）
- `orchestrator` skill（多 Skill 協作編排）
- `brand-discovery` skill（Phase A 資料蒐集）
- `brand-builder` skill（Phase B 策略建構）

**本模組職責**：
- 定義五階段品牌建構流程的完整執行邏輯
- 規定每個 Stage 調用哪些 Skill、執行什麼步驟、產出什麼交付物
- 定義 Stage 之間的閘門檢查與確認機制
- 確保最終 HTML 輸出完整涵蓋六大章節

**本模組不做**：
- 不做實際品牌訪談（brand-discovery 的工作）
- 不做框架分析（brand-builder 的工作）
- 不做實際視覺設計稿（只輸出規格書）
- 不替客戶做最終定位選擇

---

## 觸發與入口

**指令觸發**：
- `/brand-manual` — 啟動完整品牌建構工作流
- `/brand-manual fast` — 快速版（跳過 C/D，直出策略 HTML）
- `/brand-manual status` — 查看目前在哪個 Phase

**自動偵測條件**（orchestrator 判斷）：
- 使用者說「幫客戶做品牌」「出品牌手冊」「國際級品牌」
- 任務涉及「可交付他人執行的品牌規範」
- 需要「視覺操作手冊」「品牌 VI」「品牌指南」

**啟動前確認**：
```
MUSEON：您好，我將為 [客戶名稱/您] 建構完整的品牌手冊。

完整流程包含：
① 品牌發現訪談（約 40-60 分鐘對話）
② 七框架品牌策略分析
③ 視覺與語言識別規格
④ 社群操作手冊
⑤ HTML 品牌手冊交付

您希望：
A) 完整版（標準，含所有 5 個階段）
B) 快速版（Strategy + HTML，跳過操作手冊細節）

請選擇，我們馬上開始。
```

---

## 五階段完整流程

```
Phase A          Phase B          Phase C          Phase D          Phase E
品牌發現    →   品牌建構    →   識別系統    →   操作手冊    →   HTML 渲染
(Discovery)     (Brand Build)   (Identity)       (Operations)     (Render)
   │                │               │               │               │
   ▼                ▼               ▼               ▼               ▼
client_brand    brand_strategy   visual_spec    operations      brand_manual
_brief.json     _package        + verbal_spec   _guide.md       .html
```

---

### Phase A：品牌發現（Discovery）

**目的**：蒐集建構品牌所需的全部資訊
**主導 Skill**：brand-discovery
**預計時間**：40-60 分鐘對話

**執行流程**：

1. 啟動 brand-discovery，說明訪談協議
2. 依序執行六主題 50 題（動態路由）：
   - 主題 1：業務基礎（8 題）
   - 主題 2：品牌目的（8 題）
   - 主題 3：競爭格局（8 題）
   - 主題 4：客戶深度（8 題）
   - 主題 5：視覺體驗（8 題）
   - 主題 6：運營野望（10 題）
3. 每主題完成後輸出「階段摘要」請客戶確認
4. 全部完成後產出 `client_brand_brief.json`

**閘門**：
- [ ] 六主題全部完成
- [ ] 客戶確認：「這份摘要準確反映了我們的現況」
- [ ] `client_brand_brief.json` 所有必填欄位有值

→ 通過後自動進入 Phase B

---

### Phase B：品牌建構（Brand Build）

**目的**：運行七大框架，產出品牌策略包 + 三個定位選項
**主導 Skill**：brand-builder + storytelling-engine + consultant-communication
**預計時間**：深度分析，輸出前展示中間結果

**執行流程**：

1. 載入 `client_brand_brief.json`
2. brand-builder 依序執行七框架：
   - ① Keller 品牌共鳴金字塔（六層分析）
   - ② Jung 12 品牌原型（主/次/Shadow）
   - ③ JTBD for Brand（三層工作理論）
   - ④ 品牌架構決策（三型選擇）
   - ⑤ Brand Purpose 五層測試
   - ⑥ 觸點生命週期規範（六階段）
   - ⑦ April Dunford 競爭定位強化版
3. 整合七框架結果，產出三個定位路徑選項
4. storytelling-engine 為選定路徑設計品牌故事（三個版本）
5. consultant-communication 用金字塔原則整理品牌策略文件

**三定位選項展示格式**：
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
選項 A：[保守] ___________
定位宣言：___
甜頭：___  |  代價：___
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
選項 B：[平衡] ___________
定位宣言：___
甜頭：___  |  代價：___
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
選項 C：[進攻] ___________
定位宣言：___
甜頭：___  |  代價：___
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
您選哪個？或想混合某些元素？
```

**閘門**：
- [ ] 客戶選定一個定位路徑（或確認混合方案）
- [ ] `brand_strategy_package` 完整

→ 通過後自動進入 Phase C 和 Phase D（可並行）

---

### Phase C：識別系統（Identity System）

**目的**：將策略轉化為可執行的視覺與語言規格
**主導 Skill**：brand-builder（視覺/語言規格建構）+ aesthetic-sense + text-alchemy + c15
**輸出**：視覺規格書 + 語言規格書 + Do/Don't 範例

**C1：視覺識別規格**

依 brand-builder 的視覺規格建構規則，產出：

```
【色彩系統】
主色：[名稱] [HEX] [CMYK] [Pantone參考]
輔色：___
中性色系：___
禁止色：___ （含原因）

【字型系統】
Display 層：[字型] [用途] [重量範圍]
Body 層：[英文字型] + [中文字型] [用途]
Accent 層：[字型] [用途]

【圖像風格】
✓ 應採用：___ （3-5 個描述詞 + 視覺語言說明）
✗ 禁止使用：___ （3-5 個描述詞 + 原因）
參考美感方向：___

【Logo 方向建議（供設計師）】
形狀方向：___
字型方向：___
符號/圖形方向：___
禁止方向：___
```

**C2：語言識別規格**

依 brand-builder 的語言規格建構規則，產出：

```
【語調光譜】
溫度：冰冷 ←──●──→ 溫暖  [分數/100]
嚴肅：學術 ←──●──→ 口語  [分數/100]
主動：回應 ←──────●→ 引導  [分數/100]
專業：大眾 ←────●──→ 術語  [分數/100]
在地：國際 ←──●──→ 在地  [分數/100]

【品牌聲音六特徵】
1. ___  2. ___  3. ___
4. ___  5. ___  6. ___

【品牌詞彙庫】
✓ 我們說：___（10-15 個）
✗ 我們不說：___（10-15 個）

【訊息金字塔】
Tier 1（品牌承諾）：___
Tier 2（分眾訊息）：___（3-5 個受眾版本）
Tier 3（信任證據）：___（3-5 個）

【Tagline 候選】
Option 1：___
Option 2：___
Option 3：___
```

**C3：Do/Don't 視覺示範（文字版）**

每個視覺規則配一組正反範例（供設計師理解意圖）：

```
色彩使用
✓ Do：主色作為 CTA 按鈕和標題強調，背景使用暖白 Parchment
✗ Don't：整個頁面用主色塊填滿，或背景使用純白 #FFFFFF

圖像選擇
✓ Do：真實環境中的人物，自然光，暖色調，有細節的手部特寫
✗ Don't：白底去背的 iStock 商業照、機器人手持平板圖

語言示範
✓ Do：「讓我們來看看，你的________到底卡在哪裡。」
✗ Don't：「我們致力於提供卓越的客戶導向解決方案。」
```

**閘門**：
- [ ] 客戶確認視覺方向（色彩 + 圖像風格）
- [ ] 客戶確認語言規範（語調 + 詞彙庫）

→ 通過後進入 Phase D

---

### Phase D：操作手冊（Operations Manual）

**目的**：讓任何使用者都能靠手冊獨立執行品牌
**主導 Skill**：text-alchemy + c15 + storytelling-engine
**輸出**：社群操作指南 + 貼文範本 × 10 + 品牌審計自查清單

**D1：社群平台規範**

針對客戶使用的每個平台（從 brief.current_channels 萃取）：

```
[平台名] 品牌規範
• 定位：這個平台我們主要用來____
• 語調微調：比基準語調更__（活潑/正式/視覺化）
• 貼文結構：____（開頭/內容/CTA 格式）
• 最佳發文時段：____
• Hashtag 策略：主標籤___＋次標籤___（常駐） + 活動標籤
• 禁止事項：___
```

**D2：內容策略矩陣**

```
內容類型      比例    頻率    目的          舉例
品牌故事      25%     週1     建立信任      創辦人的___時刻
專業知識      30%     週2     建立權威      ___的三個迷思
客戶見證      20%     週1     社會認同      客戶說___
產品/服務     15%     週1     轉換導向      ___限時方案
幕後花絮      10%     雙週1   品牌溫度      ___的一天
```

**D3：貼文範本 × 10**

依內容矩陣，每種類型 2 篇範本，共 10 篇：
- 每篇包含：文案本體 + 圖片方向描述 + Hashtag + CTA
- c15 注入敘事張力（開頭 Hook / 情感節奏 / 行動召喚）
- storytelling-engine 確保每篇有完整弧線

**D4：品牌審計自查清單（給小編每週用）**

```
【每次發文前確認】
□ 語調是否在品牌光譜範圍內？
□ 有沒有用到禁止詞彙？
□ 視覺是否符合色彩與圖像規範？
□ 這篇是否體現了品牌聲音的至少一個特徵？
□ CTA 是否清楚？

【每月品牌一致性審計】
□ 最近 20 篇貼文是否「看起來像同一個品牌在說話」？
□ 有沒有出現前後矛盾的定位？
□ 哪篇表現最好？它體現了品牌的什麼特質？
□ 哪篇最弱？原因是什麼？下次怎麼改？
```

**閘門**：
- [ ] 操作手冊通過品牌一致性審計

→ 通過後進入 Phase E

---

### Phase E：HTML 渲染（Render）

**目的**：將 Phase B/C/D 所有產出整合為一份完整的 HTML 品牌手冊
**主導 Skill**：report-forge + aesthetic-sense
**模板**：`~/MUSEON/docs/templates/brand-manual-template.html`
**設計規範**：`~/MUSEON/data/_system/brand/design_spec.md`

**渲染前確認清單**：
- [ ] 讀取 `design_spec.md`，確認色彩/字型規範
- [ ] 讀取 `brand-manual-template.html`，確認章節結構
- [ ] 合併 Phase B 策略包 + Phase C 識別規格 + Phase D 操作手冊
- [ ] 所有六章節都有內容

**HTML 六章節結構**：

```
第 1 章：品牌概覽（Brand Overview）
  • 品牌一句話 + Purpose 宣言
  • Tagline
  • 品牌原型（視覺化）
  • 快速索引

第 2 章：品牌策略（Brand Strategy）
  • WHY / HOW / WHAT
  • 競爭定位圖
  • 目標客群洞察（JTBD）
  • 品牌承諾

第 3 章：視覺識別（Visual Identity）
  • 色彩系統（色票 + 色碼）
  • 字型系統
  • 圖像風格（✓ Do / ✗ Don't）
  • Logo 方向建議

第 4 章：語言識別（Verbal Identity）
  • 語調光譜（可視化）
  • 品牌詞彙庫
  • 訊息金字塔
  • Tagline 候選

第 5 章：觸點規範（Touchpoint Standards）
  • 六階段觸點行為規則
  • 各平台品牌規範
  • 品牌做與不做

第 6 章：操作手冊（Operations Guide）
  • 內容策略矩陣
  • 貼文範本 × 10
  • 品牌審計自查清單
  • 常見問題 FAQ
```

**後置 aesthetic-sense 審計**：
- 視覺層次是否清晰（H1/H2/H3 節奏）
- 留白是否充分（不擁擠）
- 整體是否「看起來值錢」

**交付格式**：
- 單一 HTML 檔案（自含 CSS，不依賴外部資源）
- 檔名：`[客戶名]_brand_manual_YYYYMMDD.html`
- 可直接在瀏覽器開啟，可列印

---

## 護欄

**HG-WF-BRD-NO-SKIP-DISCOVERY**：禁止跳過 Phase A。沒有真實客戶資料就做品牌策略，是最危險的貨架式方案。

**HG-WF-BRD-NO-GENERIC**：所有輸出必須援引 `client_brand_brief` 的具體資料。通用語言一律打回重做。

**HG-WF-BRD-THREE-OPTIONS**：Phase B 必須提供三個定位選項，不替客戶做最終選擇。

**HG-WF-BRD-NO-VISUAL-DESIGN**：本工作流只輸出「設計師可執行的規格」，不替代設計師做視覺執行。

**SG-WF-BRD-PACE**：每次對話聚焦一個 Phase，不要一次推進兩個以上。

---

## 適應性深度控制

| DNA27 迴圈 | 工作流深度 | 適用情境 |
|-----------|-----------|---------|
| fast_loop | Phase A + B + E（跳過 C/D，直出策略 HTML） | 客戶只需策略文件，不需操作手冊 |
| exploration_loop | 完整五 Phase | 標準品牌建構案 |
| slow_loop | 完整五 Phase + 每 Phase 修訂迴圈 | 高預算案/品類創造/國際品牌 |

---

## DNA27 親和對照

| Phase | tone | pace | initiative | challenge_level |
|-------|------|------|-----------|----------------|
| A（訪談） | WARM | SLOW | ASK | 1 |
| B（建構） | NEUTRAL | MEDIUM | OFFER_OPTIONS | 2 |
| C（識別） | NEUTRAL | MEDIUM | OFFER_OPTIONS | 1 |
| D（操作） | WARM | FAST | MIRROR | 0 |
| E（渲染） | NEUTRAL | FAST | OFFER_OPTIONS | 0 |

**偏好觸發反射叢集**：RC-C3（結構化思考）、RC-E1（慢層啟動）、RC-B6（代價標籤）
**禁止觸發**：RC-B1（不替客戶做最終選擇）

---

## 系統指令

| 指令 | 效果 |
|------|------|
| `/brand-manual` | 啟動完整工作流 |
| `/brand-manual fast` | 快速版（A + B + E） |
| `/brand-manual status` | 查看目前 Phase + 已完成交付物 |
| `/brand-manual back [phase]` | 回到指定 Phase 重做 |

---

## 邊界宣告

**什麼情況下本工作流不適用**：
- 只需要「快速貼文範本」→ 用 text-alchemy 直接生成
- 已有完整品牌策略，只需社群執行 → 用 workflow-svc-brand-marketing
- 需要設計執行稿 → 本工作流只到規格書，需搭配設計師

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.0 | 2026-03-28 | 初版：五 Phase 完整工作流 + HTML 六章節結構 + 完整護欄系統 |
