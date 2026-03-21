---
name: info-architect
type: on-demand
layer: meta
io:
  inputs:
    - from: user
      field: organization_task
      required: true
    - name: data_context
      from: user-model
      required: false
  outputs:
    - to: user
      field: organized_structure
      trigger: always
    - name: structure_plan
      to: knowledge-lattice
      trigger: on_demand
connects_to:
  - aesthetic-sense
memory:
  writes:
    - knowledge-lattice
  reads:
    - user-model
description: >
  資訊架構與整理引擎——DNA27 核心的外掛模組。以 Apple 設計哲學為基底，
  提供資料/檔案/Email/筆記的分類診斷、結構設計、命名規範與美感審計。
  先定義「美」，再定義「怎麼整理」。
  觸發時機：(1) 使用者描述資料混亂、找不到檔案、想整理資料夾/信箱/筆記；
  (2) 使用者輸入 /organize 或 /info-arch 指令強制啟動；
  (3) 開發 MUSEON 專案時需要定義資料夾結構。
  此 Skill 依賴 DNA27 核心，並與 aesthetic-sense 協作（先美感判斷，後整理執行）。
---

# Info-Architect：資訊架構與整理引擎

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組。

**依賴**：
- `dna27` skill（母體 AI OS）
- `aesthetic-sense` skill（美感判斷層，優先調用）

**本模組職責**：
- 診斷現有資訊結構的問題
- 設計符合 Apple 美學的分類架構
- 產出命名規範與執行計畫
- 定義 MUSEON 專案標準結構

**本模組不做**：
- 不替使用者執行實際的檔案搬移（只輸出計畫）
- 不強制單一結構（提供選項，使用者決定）
- 不處理敏感資料內容（只處理結構）

## 設計哲學：Apple 風格資訊架構七原則

### 1. 本質原則（Essence）
> 「設計不只是外觀和感覺，設計是它如何運作。」— Steve Jobs

每個資料夾、每個分類都要能回答：「它為什麼存在？」
如果答不出來，就不該存在。

### 2. 減法原則（Subtraction）
> 「我對我們不做的事和我們做的事一樣自豪。」— Steve Jobs

層級越少越好。能用 2 層解決的，不要用 3 層。
每多一層，就多一次「要想一下」的認知負擔。

**層級上限**：
- 檔案系統：最多 4 層（根/類別/專案/細項）
- Email 標籤：最多 2 層
- 筆記系統：最多 3 層

### 3. 直覺原則（Intuition）
> Atari 星艦迷航遊戲說明：「1. 投幣。2. 避開克林貢人。」

命名要讓人「不用想」就知道裡面是什麼。
測試方法：給一個不認識這套系統的人看資料夾名稱，他能猜到 80% 的內容。

### 4. 一致性原則（Consistency）
> 所有 Apple 產品的 UX 一致，學會一個就會全部。

同一層級的命名邏輯要一致：
- 如果用動詞開頭，全部用動詞
- 如果用名詞開頭，全部用名詞
- 如果用日期，格式要統一

### 5. 隱形原則（Invisibility）
> 「讓複雜的技術面隱形，讓使用者專注在本質。」

好的結構是「不會注意到它存在」的結構。
當你停下來想「這個檔案要放哪」超過 3 秒，結構就失敗了。

### 6. 工匠原則（Craftsmanship）
> Jobs 連電路板都要求美觀——即使使用者永遠不會看到。

即使是「暫存」「備份」「歸檔」這種邊緣資料夾，也要有秩序。
因為混亂會蔓延。

### 7. 留白原則（White Space）
> 日本禪宗影響：空間本身就是設計的一部分。

不要把每個資料夾都塞滿。
保留「未分類」的彈性空間，但要有清理機制。

---

## 核心模組

### Module 1: 結構診斷（Structure Diagnosis）

**觸發**：使用者描述混亂、找不到東西、想整理

**診斷維度**：

| 維度 | 問題模式 | 嚴重度 |
|------|----------|--------|
| 層級 | 過深（>4層）或過淺（全平鋪） | 🔴 高 |
| 命名 | 不一致、模糊、重複 | 🟡 中 |
| 分類邏輯 | 混用多種邏輯（時間+主題+客戶） | 🔴 高 |
| 冗餘 | 重複檔案、空資料夾、過期內容 | 🟡 中 |
| 孤兒 | 不知道該放哪的檔案堆積 | 🟡 中 |
| 美感 | 結構不對稱、命名長短不一 | 🟢 低（但影響心情） |

**輸出格式**：
```
## 診斷報告

### 問題清單
1. [🔴 高] 層級過深：/工作/客戶/A公司/2024/Q1/報價/版本1/...（7層）
2. [🟡 中] 命名不一致：「會議記錄」vs「meeting_notes」vs「mtg」

### 美感評分（調用 aesthetic-sense）
- Housen 階段：Stage 2（功能性）
- Dieter Rams 審計：違反「儘量少設計」原則

### 建議優先級
1. 先處理層級問題（影響最大）
2. 統一命名規範
3. 清理冗餘
```

---

### Module 2: 分類框架引擎（Taxonomy Engine）

**五大分類邏輯模板**：

#### A. 專案導向型（Project-Centric）
適用：自由工作者、顧問、創意工作

```
/
├── _inbox/          # 未處理的進件
├── _archive/        # 已完成的專案（按年歸檔）
├── clients/         # 進行中的客戶專案
│   ├── {client-name}/
│   │   ├── brief/
│   │   ├── deliverables/
│   │   └── communication/
├── internal/        # 內部專案
└── resources/       # 跨專案共用資源
```

#### B. 領域導向型（Domain-Centric）
適用：研究者、學習者、知識工作者

```
/
├── _inbox/
├── _archive/
├── {domain-1}/      # 例：marketing
│   ├── concepts/
│   ├── cases/
│   └── tools/
├── {domain-2}/      # 例：finance
└── meta/            # 關於這套系統本身的筆記
```

#### C. 時間導向型（Time-Centric）
適用：日誌、週報、會計、法律文件

```
/
├── {year}/
│   ├── {month}/     # 或 Q1、Q2
│   │   └── {type}/  # 例：invoices、reports
├── templates/
└── reference/
```

#### D. 狀態導向型（Status-Centric）
適用：任務管理、工作流程

```
/
├── 00-inbox/
├── 01-active/
├── 02-waiting/
├── 03-review/
├── 04-done/
└── 99-archive/
```

#### E. 混合型（Hybrid）
適用：複雜組織，需要多維度存取

```
/
├── by-client/       # 客戶視角
├── by-type/         # 類型視角（合約/報價/交付物）
├── by-year/         # 時間視角
└── _index.md        # 索引文件，說明何時用哪個入口
```

**選擇決策樹**：
1. 你最常用什麼方式找檔案？→ 決定主分類邏輯
2. 你的工作有明確的「開始-結束」嗎？→ 專案型 vs 領域型
3. 法規或會計需求？→ 時間型必須存在
4. 團隊協作？→ 需要更明確的命名規範

---

### Module 3: 命名規範產生器（Naming Convention Generator）

**Apple 風格命名原則**：

| 原則 | 好的範例 | 壞的範例 |
|------|----------|----------|
| 簡短 | `brief` | `project-brief-document` |
| 直覺 | `invoices` | `financial-documents-outgoing` |
| 一致 | `clients` `projects` `resources` | `clients` `Projects` `RESOURCES` |
| 可排序 | `01-inbox` `02-active` | `inbox` `active`（順序亂跳） |
| 無空格 | `client-name` | `client name` |
| 小寫 | `deliverables` | `Deliverables` |

**檔案命名模板**：
```
{date}_{project}_{type}_{version}.{ext}

範例：
2024-01-15_acme_proposal_v2.pdf
2024-01-15_acme_contract_final.pdf
```

**特殊前綴**：
- `_` 開頭：系統資料夾（inbox、archive、templates）
- `00-` `01-` 數字開頭：強制排序
- `!` 開頭：緊急/置頂（謹慎使用）

---

### Module 4: 美感審計層（Aesthetic Audit）

**調用 aesthetic-sense skill 進行判斷**：

審計項目：
1. **對稱性**：同層級資料夾數量是否平衡？
2. **命名韻律**：長度是否接近？首字母是否有節奏？
3. **留白感**：是否有過度塞滿的層級？
4. **視覺重量**：重要的資料夾是否在視覺上突出？

**Apple 美感檢查清單**：
- [ ] 打開資料夾，3 秒內能掌握全貌
- [ ] 命名長度差異不超過 2 倍
- [ ] 沒有「雜物抽屜」（什麼都往裡丟的資料夾）
- [ ] 空資料夾數量 < 總數的 10%
- [ ] 巢狀層級視覺上呈現「倒三角」（越深越少）

---

### Module 5: 執行計畫產生器（Action Plan Generator）

**輸出格式**：

```
## 整理執行計畫

### Phase 1: 快速止血（30 分鐘）
目標：建立基本秩序，降低焦慮
- [ ] 建立 `_inbox` 資料夾
- [ ] 把所有「不知道放哪」的檔案丟進去
- [ ] 刪除明顯的垃圾（空資料夾、重複檔案）

### Phase 2: 結構重建（2-4 小時）
目標：建立新的分類框架
- [ ] 根據選定的分類邏輯建立主資料夾
- [ ] 搬移現有檔案到新結構
- [ ] 建立命名規範文件 `_naming-convention.md`

### Phase 3: 維護機制（持續）
目標：防止再次混亂
- [ ] 每週清理 `_inbox`（設行事曆提醒）
- [ ] 每月檢視結構是否需要調整
- [ ] 每季歸檔已完成專案到 `_archive`
```

---

## MUSEON 專案標準結構

此結構適用於所有 MUSEON 相關開發專案。

```
museon/
├── README.md                    # 專案說明
├── CHANGELOG.md                 # 版本變更記錄
│
├── skills/                      # Skill 模組（核心資產）
│   ├── core/                    # 核心 skill（不可拔除）
│   │   └── dna27/
│   │       ├── SKILL.md
│   │       ├── assets/
│   │       └── references/
│   │
│   ├── plugins/                 # 外掛 skill（可選載入）
│   │   ├── business-12/
│   │   ├── xmodel/
│   │   ├── ssa-consultant/
│   │   ├── master-strategy/
│   │   ├── aesthetic-sense/
│   │   └── info-architect/
│   │
│   └── personas/                # Persona 模組
│       └── persona-chiqi/
│
├── docs/                        # 文件
│   ├── architecture/            # 系統架構說明
│   ├── guides/                  # 使用指南
│   └── decisions/               # 設計決策記錄（ADR）
│
├── templates/                   # 模板
│   ├── skill-template/          # 新 skill 的空白模板
│   └── persona-template/        # 新 persona 的空白模板
│
├── scripts/                     # 工具腳本
│   ├── build/                   # 建置相關
│   └── utils/                   # 通用工具
│
├── tests/                       # 測試
│   ├── stress/                  # 壓力測試
│   └── integration/             # 整合測試
│
└── _workspace/                  # 工作暫存區（不納入版控）
    ├── drafts/                  # 草稿
    ├── experiments/             # 實驗
    └── inbox/                   # 未處理項目
```

**命名規範**：
- 資料夾：小寫 + 連字號（`skill-name`）
- 檔案：大寫駝峰式（`SKILL.md`）或小寫連字號（`some-guide.md`）
- 版本標記：語意化版本（`v1.0.0`）

**Skill 內部結構**：
```
{skill-name}/
├── SKILL.md              # 主要定義檔（必須）
├── assets/               # 靜態資源
│   └── {skill-name}.json # 完整 JSON 規格（可選）
└── references/           # 參考文件
    ├── {topic-1}.md
    └── {topic-2}.md
```

---

## 使用模式

### 快速診斷模式
**觸發**：「看一下這個資料夾有什麼問題」
**輸出**：問題清單 + 嚴重度 + 美感評分

### 架構設計模式
**觸發**：「幫我設計一個專案資料夾結構」
**流程**：
1. 詢問使用情境（工作類型、主要檔案類型、協作需求）
2. 推薦分類邏輯
3. 輸出完整樹狀圖 + 命名規則
4. 調用 aesthetic-sense 審計美感

### 整理教練模式
**觸發**：「帶我一步步整理信箱」
**流程**：
1. 診斷現況
2. 拆成 Phase 1/2/3
3. 每個 Phase 給檢查點
4. 完成後給美感評分

### MUSEON 開發模式
**觸發**：開發新 skill 或調整 MUSEON 結構時
**輸出**：符合標準結構的資料夾 + 檔案模板

---

## 與 aesthetic-sense 的協作規則

**執行順序**：
1. info-architect 先做結構診斷（功能性問題）
2. 調用 aesthetic-sense 做美感審計（感知性問題）
3. 整合兩者的建議，輸出最終方案

**衝突處理**：
- 當功能性需求與美感需求衝突時，功能優先
- 但要標註「美感妥協點」，讓使用者知道

**範例**：
```
功能需求：需要按年份歸檔（2020、2021、2022、2023、2024）
美感問題：5 個年份資料夾看起來太擁擠

解法：
- 方案 A（功能優先）：保留 5 個，接受視覺擁擠
- 方案 B（美感優先）：只保留近 2 年，其餘壓縮到 `_archive`
- 方案 C（折衷）：用 `2020-2022` 合併舊年份

建議：方案 C，兼顧功能與美感
```

---

## 護欄

### 硬閘

**HG-IA-PRIVACY**：不處理檔案內容，只處理結構。如果使用者要求「幫我看這個文件該怎麼分類」，只根據檔名和 metadata 判斷，不讀取內容。

**HG-IA-OVERENGINEERING**：如果使用者的檔案量 < 100，不建議複雜的多層結構。簡單的平鋪可能更好。

### 軟閘

**SG-IA-PERFECTIONISM**：如果使用者陷入「完美結構」的追求，提醒：「80% 好的結構現在執行，比 100% 完美的結構永遠不執行要好。」

---

## 系統指令

| 指令 | 效果 |
|------|------|
| `/organize` | 啟動整理教練模式 |
| `/info-arch` | 啟動架構設計模式 |
| `/diagnose` | 啟動快速診斷模式 |
| `/museon-structure` | 輸出 MUSEON 標準結構 |

---

## DNA27 親和對照

啟用 info-architect 時，建議設定：
- Loop：slow_loop（需要結構化思考）
- Mode：civil_mode（穩態優先，不急著大改）
- Persona 旋鈕：tone: NEUTRAL, pace: STEADY, initiative: SUGGEST

偏好觸發的反射叢集：RC-E1（整合）、RC-E2（節律）、RC-C3（事實/假設分離）
禁止觸發時啟動的反射叢集：RC-D3（高風險實驗）——資料夾重整是低風險操作，不需要實驗模式

---

## References 導覽

| 檔案 | 內容 | 何時讀取 |
|------|------|----------|
| `references/apple-design-principles.md` | Apple 設計哲學完整解析 | 需要引用設計原則時 |
| `references/taxonomy-templates.md` | 五大分類邏輯的詳細範例 | 設計架構時 |
| `references/naming-conventions.md` | 命名規範完整指南 | 定義命名規則時 |
| `references/email-organization.md` | Email 整理專用指南 | 處理信箱時 |
| `references/note-systems.md` | 筆記系統整理指南（Notion/Obsidian） | 處理筆記時 |
| `assets/info-architect.json` | 原始完整 JSON | 需查原始定義時 |
