---
name: orchestrator
type: on-demand
layer: evolution
hub: product
io:
  inputs:
    - from: user
      field: complex_task
      required: true
  outputs:
    - to: wee
      field: execution_trace
      trigger: always
    - to: consultant-communication
      field: execution_summary_request
      trigger: conditional
    - to: user
      field: orchestrated_result
      trigger: always
connects_to:
  - wee
  - eval-engine
  - consultant-communication
  - plugin-registry
memory:
  writes:
    - target: wee
      type: proficiency
      condition: "多 Skill 編排完成時"
  reads:
    - source: user-model
      field: user_context
absurdity_affinity:
  strategic_integration: 0.7
description: >
  Orchestrator（編排引擎）— DNA27 核心的外掛模組，
  MUSEON 的多 Skill 協作編排與任務分解引擎。當使用者的需求橫跨多個 Skill 時，
  自動規劃執行順序、管理 Skill 間的資訊傳遞、處理衝突與回退。
  核心命題：單個 Skill 解決單一問題，Orchestrator 讓多個 Skill 協作解決複雜問題。
  三大能力：任務分解（將複雜需求拆成 Skill 可處理的子任務）→
  執行編排（決定 Skill 觸發順序與並行/串行邏輯）→
  銜接管理（確保 Skill 間資訊不丟失、衝突有仲裁）。
  新增能力：客戶旅程編排模式（按中小企業主使用情境串聯 Skill）+
  執行摘要輸出（多 Skill 編排結束後自動產出結構化報告）。
  觸發時機：(1) /orchestrate 或 /plan 指令強制啟動；
  (2) DNA27 路由偵測到需求涉及 3+ 個 Skill 時自動介入；
  (3) 自然語言偵測——使用者描述多步驟複雜任務時自動啟用。
  涵蓋觸發詞：完整流程、從頭到尾、全套、一次搞定、串起來、整合。
  使用情境：(A) Zeal 服務客戶時，按工作流跑完整顧問流程；
  (B) 教練模式——引導學員用此流程服務他的客戶。
  與 dna27 互補：DNA27 做單次路由決策，Orchestrator 做多步驟協作規劃。
  與 sandbox-lab 互補：流程沙盒模式由 Orchestrator 提供編排邏輯。
  與 wee 互補：wee 追蹤工作流演化，Orchestrator 執行工作流編排。
  與 eval-engine 互補：Eval-Engine 度量整體旅程品質，Orchestrator 管旅程執行。
  與 consultant-communication 互補：執行摘要調用 SCQA 框架產出結構化報告。
---

# Orchestrator：編排引擎 — 多 Skill 協作編排

> **單個 Skill 是工具，Orchestrator 讓工具變成團隊。**
> 使用者不需要知道「該先用哪個 Skill」——
> 他只需要說「我要解決這個問題」，Orchestrator 安排剩下的。

---

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組（pluggable plus）。

**依賴**：`dna27` skill（母體 AI OS。本模組不可脫離 dna27 獨立運作。）

**深度耦合模組**：
- `dna27` — DNA27 做單次路由（這次用哪個 Skill），Orchestrator 做多步驟規劃（整個旅程）
- `sandbox-lab` — 流程沙盒的編排邏輯由 Orchestrator 提供
- `wee` — WEE 追蹤工作流生命週期，Orchestrator 執行工作流的即時編排
- `eval-engine` — 整體旅程 Q-Score 由 Eval-Engine 度量；客戶成效追蹤模式與旅程編排互補
- `morphenix` — Skill 健康儀表板的共現矩陣為 Orchestrator 提供最佳搭配數據
- `consultant-communication` — 執行摘要調用 SCQA 框架產出結構化報告

**本模組職責**：
- 偵測「這個需求需要多個 Skill 協作」的時機
- 將複雜需求分解為 Skill 可處理的子任務
- 決定 Skill 執行順序（串行 / 並行 / 條件分支）
- 管理 Skill 間的資訊傳遞（A 的輸出 → B 的輸入）
- 處理 Skill 衝突（兩個 Skill 都適用時的仲裁）
- 管理回退（某個 Skill 失敗時的備選路徑）
- 按客戶旅程模式編排完整服務流程
- 編排結束後產出結構化執行摘要報告

**本模組不做**：
- 不做單次 Skill 路由（那是 DNA27 的 RC 反射叢集）
- 不做 Skill 內部邏輯（各 Skill 自己處理）
- 不替使用者決定任務目標——只規劃達成目標的路徑
- 不做報告的美感設計（那是 aesthetic-sense 的工作）

---

## 觸發與入口

**指令觸發**：
- `/orchestrate` — 顯示當前任務的編排計畫
- `/plan` — `/orchestrate` 別名
- `/orchestrate {scenario}` — 為特定場景生成編排計畫
- `/orchestrate status` — 查看當前執行進度
- `/orchestrate journey {type}` — 啟動客戶旅程編排（type: onboarding / monthly / quarterly）
- `/orchestrate summary` — 產出當前旅程的執行摘要報告

**自動觸發**（最重要的模式）：
- DNA27 路由判斷涉及 3+ Skill → 自動啟動 Orchestrator
- 使用者描述多步驟任務 → 自動規劃
- 對話中途需要切換 Skill → 自動管理銜接
- 工作流範本（如 workflow-svc-brand-marketing）被啟動時 → Orchestrator 自動接管階段編排
- 多 Skill 編排完成時 → 自動建議產出執行摘要

**自然語言偵測**：
- 「幫我從頭到尾⋯⋯」「完整流程」「一次搞定」
- 「先幫我分析，再幫我做計畫，最後幫我寫⋯⋯」
- 涉及多個領域的複合問題
- 「幫我整理剛才的結論」「給我一份報告」「把剛才的東西整理成文件」

---

## 核心架構

```
使用者需求
    ↓
DNA27 路由：偵測到多 Skill 需求
    ↓
┌──────────────────────────────────────┐
│           Orchestrator               │
├──────────┬───────────┬───────────────┤
│ 任務分解  │  執行編排  │  銜接管理     │
│ Decompose│ Sequence  │  Handoff     │
├──────────┴───────────┴───────────────┤
│         衝突仲裁與回退                 │
│      Conflict Resolution             │
├──────────────────────────────────────┤
│ 客戶旅程編排 │ 執行摘要產出            │
│ Journey     │ Summary                │
└──────────────────────────────────────┘
    ↓
Skill A → Skill B → Skill C → 整合輸出 → 執行摘要
```

---

## 一、任務分解（Decompose）

### 1.1 分解邏輯

當使用者說「我的公司營收停滯，幫我想辦法」——這不是單一 Skill 能解的。

Orchestrator 的分解流程：

```
「公司營收停滯」
    ↓
① 情緒面：使用者可能帶著焦慮 → resonance（先接住）
② 診斷面：營收問題的根因是什麼 → business-12（12力診斷）
③ 解法面：找到弱項後怎麼突破 → xmodel（破框推演）
④ 執行面：選定路徑後怎麼落地 → pdeif（逆熵流程設計）
⑤ 表達面：需要跟團隊溝通嗎 → consultant-communication
```

### 1.2 分解原則

**完整性**：不遺漏必要的步驟（尤其是情緒面——常被跳過）

**順序性**：先接住情緒 → 再診斷 → 再解方 → 再落地。不能倒過來

**可略性**：如果使用者情緒穩定，可以跳過 resonance 直接進 business-12

### 1.3 輸出格式

```
📋 編排計畫
━━━━━━━━━━━━━━━━━━━━
任務：「公司營收停滯」完整診斷與解方

步驟  Skill                 目的                狀態
1     resonance             情緒承接（如需要）   ○ 待判斷
2     business-12           12力診斷找根因       ○ 待執行
3     xmodel                弱項破框推演         ○ 待執行
4     pdeif                 選定路徑落地設計     ○ 待執行
5     consultant-comm       行動計畫文件化       ○ 選配

預估輪次：8-12 輪對話
銜接點：步驟 2→3 傳遞弱項清單；步驟 3→4 傳遞選定路徑
```

---

## 二、執行編排（Sequence）

### 2.1 三種執行模式

| 模式 | 說明 | 適用場景 |
|------|------|---------|
| **串行** | A → B → C，一個完成再下一個 | 有嚴格先後依賴時（診斷 → 解方） |
| **並行** | A + B 同時進行 | 彼此獨立時（美感審計 + 結構審計） |
| **條件分支** | 根據 A 的結果決定走 B 還是 C | 結果不確定時（診斷結果不同 → 不同解法） |
| **並行融合** | A+B+C 同時看同一問題，視角融合為一個輸出 | 重大決策、多維度綜合判斷（P3 新增） |

### 2.2 編排決策依據

Orchestrator 根據以下資訊決定編排：

- **Skill 依賴圖**（morphenix 維護）：誰依賴誰、誰跟誰互補、誰銜接誰
- **共現矩陣**（eval-engine 提供）：哪些 Skill 常一起出現、效果最佳搭配
- **使用者狀態**（DNA27 路由）：能量、緊急度 → 影響步驟數量和深度
- **歷史模式**（wee 提供）：這類任務過去最常走什麼路線
- **工作流範本**：已定義的工作流（如 WF-SVC-01）作為預設編排方案
- **Hub 歸位**（`hub` 欄位 + `docs/skill-routing-governance.md`）：同 Hub 內的 Skill 優先串聯、跨 Hub 需明確銜接點
- **Workflow Stage 定義**（`stages` + `speed_paths`）：已定義的工作流 stages 作為預設編排骨架，speed_paths 決定迴圈深度

### 2.3 動態調整

編排不是石頭刻好的——執行中可以調整：

- 步驟 2 diagnosis 結果意外 → 重新規劃後續路線
- 使用者能量下降 → 縮減步驟，先到最小可交付
- 使用者插入新需求 → 動態加入新步驟

---

## 三、銜接管理（Handoff）

### 3.1 問題：Skill 切換時資訊容易丟失

白話說：business-12 做完診斷，要交棒給 xmodel 做破框時，「business-12 發現了什麼」這個資訊需要完整傳過去。如果丟了，xmodel 就得從頭問一遍。

### 3.2 銜接協議

每次 Skill 切換時，Orchestrator 做三件事：

**1. 摘要打包**：將前一個 Skill 的關鍵輸出壓縮成結構化摘要

```
[銜接包：business-12 → xmodel]
核心發現：BF03 產品力（0.4/1.0）和 BF07 轉換力（0.3/1.0）是兩大弱項
已排除：品牌力和社群力不是主因
使用者狀態：能量高，已進入行動導向思維
```

**2. 上下文注入**：將銜接包注入下一個 Skill 的起始上下文

**3. 回顧鏈**：維護整個旅程的摘要鏈，任何步驟都能回看前面的結論

### 3.3 常見銜接路線

| 路線 | 銜接內容 |
|------|---------|
| resonance → business-12 | 情緒穩定確認 + 使用者真正關心的議題 |
| resonance → dharma | 核心情緒 + 觸發信念 |
| business-12 → xmodel | 弱項清單 + 使用者偏好的改善方向 |
| xmodel → pdeif | 選定路徑 + 可承擔的資源範圍 |
| dharma → pdeif | 新信念/價值觀 + 對齊後的行動意願 |
| 任何 Skill → consultant-comm | 關鍵結論 + 目標受眾 + 溝通目的 |

---

## 四、衝突仲裁

### 4.1 衝突類型

| 衝突 | 範例 | 仲裁規則 |
|------|------|---------|
| 觸發衝突 | business-12 和 ssa-consultant 都適用 | DNA27 RC 優先級 + 共現歷史 |
| 建議衝突 | 兩個 Skill 給出矛盾建議 | 呈現兩方觀點，不替使用者選 |
| 資源衝突 | 對話太長，不可能跑完所有步驟 | 按使用者能量縮減，保留核心步驟 |

### 4.2 仲裁原則

- 使用者主權優先——衝突時問使用者，不自作主張
- 保守偏向——不確定時走更安全的路線
- 透明——告知使用者「這裡有兩個可能方向，你偏好哪個？」

---

## 五、回退機制

```
步驟 N 失敗或品質不足
    ↓
判斷：可重試 or 需更換路線
├ 可重試 → 同 Skill 換個角度再試一次
├ 需更換 → 切換到備選 Skill
└ 無法處理 → 告知使用者限制，建議人工介入
```

---

## 六、並行融合模式（Parallel Fusion Mode）— P3 新增

### 6.0.1 問題：為什麼需要並行融合

原有的三種執行模式（串行/並行/條件分支）都是「分工」邏輯——
每個 Skill 各自處理一塊，最後拼接。但有些問題需要的不是拼接，而是「融合」——
多個 Skill 的視角同時影響同一段輸出。

**串行**：A 做完 → B 接手 → C 收尾（像接力賽）
**並行**：A 和 B 同時做不同的事（像分組作業）
**融合**：A、B、C 同時看同一個問題，各自貢獻視角，產出一個融合回答（像圓桌會議）

### 6.0.2 融合模式的定位

| 面向 | 串行/並行 | 融合 |
|------|---------|------|
| 輸出數量 | 每個 Skill 各有一個輸出，最後合併 | 只有一個融合輸出 |
| 適用場景 | 任務可拆分成獨立子任務 | 問題需要多角度同時照射 |
| 觀點衝突 | 按順序解決 | 在融合中呈現張力 |
| 認知成本 | 低（一次看一塊） | 高（同時處理多視角） |
| 與 roundtable 的差異 | 不適用 | roundtable 是角色扮演詰問；融合是 Skill 視角滲透進同一個回答 |

### 6.0.3 觸發條件

**自動觸發**（任一命中）：
- deep-think Phase 0 偵測到重大決策訊號（⚖️）+ slow_loop
- 問題同時涉及戰略判斷（master-strategy）+ 人際博弈（shadow）+ 商業分析（business-12/xmodel）
- 使用者明確要求「從多個角度來看」「綜合分析」但不想要圓桌格式

**指令觸發**：
- `/orchestrate fusion` — 啟動融合模式
- `/orchestrate fusion {skills}` — 指定融合的 Skill 組合

**不觸發**：
- fast_loop（認知成本太高）
- 問題只涉及 1-2 個 Skill（沒必要融合）
- 使用者要求「直接給答案」

### 6.0.4 融合流程

```
使用者提出複雜問題
    ↓
Orchestrator 判斷：需要融合（非分工）
    ↓
┌──────────────────────────────────────┐
│         Skill 視角並行展開             │
│                                      │
│  master-strategy: 攻守節奏觀點        │
│  xmodel: 跨領域槓桿觀點              │
│  shadow: 人際博弈觀點                │
│  business-12: 商業結構觀點           │
│  (其他按需加入)                       │
└──────────────┬───────────────────────┘
               ↓
┌──────────────────────────────────────┐
│         融合引擎（Fusion Engine）      │
│                                      │
│  1. 共識層：各 Skill 都同意的結論      │
│  2. 張力層：各 Skill 觀點衝突之處     │
│  3. 盲點層：只有某個 Skill 看到的     │
│  4. 行動層：綜合後的建議路徑          │
└──────────────┬───────────────────────┘
               ↓
deep-think Phase 2 輸出審計
               ↓
融合輸出（思考路徑 + 融合回答）
```

### 6.0.5 融合輸出格式

融合輸出不是列出每個 Skill 的觀點（那是 roundtable），
而是把多個視角編織進同一段分析中：

**範例**：

> **思考路徑**：你問的是「要不要現在擴張」，但核心問題是時機判斷。我同時從戰略節奏、商業結構和人際動態三個維度來看。
>
> **融合分析**：
>
> 從市場時機來看，你的競爭者正在收縮，這是擴張的窗口——但窗口不等於你準備好了。你的 12 力診斷中，轉換力（0.4）和團隊力（0.5）都在警戒線，擴張會把這兩個弱項放大。
>
> 更微妙的是，你提到的合作夥伴最近態度突然變積極——這可能是真的看好你，也可能是他自己需要你的資源來度過難關。這個動機判斷會影響整個合作結構。
>
> 💡 你可能沒想到——擴張最大的風險不是錢，而是你現在的團隊文化能不能承受快速長大的壓力。
>
> **三條路徑**：
> 1. 全速擴張（甜頭/代價/風險）
> 2. 選擇性擴張：只擴一條線（甜頭/代價/風險）
> 3. 先補弱項再擴張：90 天補轉換力和團隊力（甜頭/代價/風險）

### 6.0.6 融合模式的護欄

**HG-FUSION-MAX-SKILLS**：融合模式最多同時融合 5 個 Skill 視角。超過 5 個認知負荷太高，品質反而下降。

**HG-FUSION-DEEP-THINK**：融合輸出必須通過 deep-think Phase 2 完整審計。融合不是免檢通道。

**HG-FUSION-NO-HIDE-CONFLICT**：不隱藏觀點衝突。如果兩個 Skill 視角矛盾，必須在張力層呈現——不替使用者選邊。

**SG-FUSION-FALLBACK**：如果融合品質不佳（deep-think 審計不通過），降級為串行模式，各 Skill 分別輸出。

---

## 七、客戶旅程編排模式（Phase 2 新增）

### 6.1 問題：為什麼需要旅程模式

原有的 Orchestrator 是「問題導向」——使用者說一個問題，拆解成 Skill 子任務。

但企業客戶的需求是「旅程導向」——不是解一個問題，而是「從認識 MUSEON 到持續使用」的完整體驗。旅程模式站在客戶視角，把多次對話串成一條有意義的服務線。

### 6.2 三個預設旅程範本

#### 旅程 A：新客導入（Onboarding Journey）

目標：讓新客戶在 2-4 次對話內「用上手」

```
第 1 次  │  品牌健檢（ssa-consultant + business-12 快篩）
         │  交付：健檢報告（1 頁摘要）
         ↓
第 2 次  │  聚焦選擇（從健檢結果挑最急的 1-2 項深入）
         │  交付：問題定義 + 初步方向（consultant-communication 結構化）
         ↓
第 3 次  │  行動計畫（xmodel 或 pdeif 產出可執行步驟）
         │  交付：90 天行動計畫
         ↓
第 4 次  │  回顧確認（eval-engine 基準線 + wee 對齊五問）
         │  交付：KPI 基準線 + 下月待辦
```

#### 旅程 B：月度健檢（Monthly Check Journey）

目標：30 分鐘快速體檢 + 微調

```
開場    │  wee 結果萃取五問（上個月做了什麼、效果如何）
        ↓
中段    │  eval-engine 數據回顧（KPI 變化）+ business-12 弱項重檢
        ↓
收尾    │  下月 3 個優先事項 + 1 個最小下一步
        │  交付：月度成效報告
```

#### 旅程 C：季度策略（Quarterly Strategy Journey）

目標：完整策略回顧 + 下季方向調整

```
第 1 次  │  全面回顧：eval-engine 季度報告 + business-12 12 力重檢
         ↓
第 2 次  │  環境掃描：env-radar 外部趨勢 + master-strategy 競爭態勢
         ↓
第 3 次  │  策略調整：xmodel 破框推演 + pdeif 路徑重設計
         │  交付：季度策略調整企劃書
```

### 6.3 旅程模式規則

- 每個旅程範本是建議，不是強制——可以跳步、加步、改順序
- 旅程之間可以串接：新客導入完成 → 自動建議月度健檢
- 工作流範本（如 WF-SVC-01）可以作為旅程的子流程載入
- 每個旅程結束時自動建議產出執行摘要

---

## 八、執行摘要輸出（Phase 2 新增）

### 7.1 問題：對話紀錄不是交付物

客戶需要的是：「這次我們做了什麼、結論是什麼、接下來要做什麼」的一頁紙。不是 20 輪對話紀錄。

### 7.2 執行摘要結構

調用 consultant-communication 的 SCQA 框架：

```
📋 執行摘要
━━━━━━━━━━━━━━━━━━━━
客戶：[名稱]
日期：[日期]
旅程：[旅程類型 / 工作流名稱]
編排步驟：[已完成的 Skill 清單]

── Situation（現況） ──
[客戶的起始狀態，1-2 句]

── Complication（挑戰） ──
[診斷發現的核心問題，1-3 項]

── Question（核心問題） ──
[客戶最需要解決的 1 個問題]

── Answer（結論與行動） ──
[結構化的結論 + 具體行動計畫]

── 關鍵交付物清單 ──
□ [交付物 1]
□ [交付物 2]
□ [交付物 3]

── 下一步 ──
[最小下一步 + 時間 + 負責人]
[下次對談建議日期]
```

### 7.3 摘要品質規則

- **不是對話摘要**——是結論和行動的結構化呈現
- **站在客戶視角**——用客戶的語言，不用 MUSEON 內部術語
- **可獨立閱讀**——不需要回去看對話紀錄就能理解
- **一頁以內**——如果需要更多細節，另附完整報告
- 調用 aesthetic-sense 做最終排版品質檢查（如果可用）

### 7.4 自動產出時機

- 多 Skill 編排完成時 → 主動提議「要不要產出執行摘要？」
- 工作流 Stage 結束時 → 自動產出該 Stage 的交付物摘要
- `/orchestrate summary` 手動觸發
- 旅程結束時 → 自動產出旅程完成報告

---

## 九、與其他模組的數據流

```
DNA27（路由判斷）──→ Orchestrator（多步驟規劃）
morphenix（依賴圖）──→ Orchestrator（Skill 搭配依據）
eval-engine（共現/品質）──→ Orchestrator（最佳路線依據）
wee（歷史模式）──→ Orchestrator（經驗參考）
工作流範本 ──→ Orchestrator（預設編排方案）
                          ↓
                    各 Skill 依序執行
                          ↓
               ┌──────────┴──────────┐
         eval-engine              執行摘要產出
         (旅程品質度量)          (consultant-comm 結構化)
```

---

## 護欄

### 硬閘

**HG-ORCH-NO-OVERRIDE**：不過度編排。簡單問題不需要 Orchestrator——一個 Skill 就能解的，不拆成五步。

**HG-ORCH-NO-DECIDE**：不替使用者決定。編排計畫是建議，使用者可以跳步、改順序、中途喊停。

**HG-ORCH-TRANSPARENCY**：使用者知道目前在哪個步驟、接下來要做什麼、為什麼這樣安排。

### 軟閘

**SG-ORCH-COGNITIVE-LOAD**：認知負荷控制。不一次展開全部步驟——先說「我建議走四步」，執行時逐步展開。

**SG-ORCH-FALLBACK**：回退安全。任何步驟失敗都有備選方案，不會卡死在半路。

**SG-ORCH-SUMMARY-LENGTH**：執行摘要控制在 1 頁以內。超過就分主摘要 + 附件。

---

## 適應性深度控制

| DNA27 迴圈 | Orchestrator 深度 |
|---|---|
| fast_loop | 精簡版：最多 2 步驟、不產執行摘要、直接給最小下一步 |
| exploration_loop | 標準版：3-5 步驟、按需產出摘要、銜接包精簡版 |
| slow_loop | 深度版：完整旅程編排 + 所有銜接包 + 完整執行摘要 + 品質審計 |

---

## 系統指令

| 指令 | 效果 |
|---|---|
| `/orchestrate` | 顯示當前任務的編排計畫 |
| `/plan` | `/orchestrate` 別名 |
| `/orchestrate {scenario}` | 為特定場景生成編排計畫 |
| `/orchestrate status` | 查看當前執行進度 |
| `/orchestrate journey onboarding` | 啟動新客導入旅程 |
| `/orchestrate journey monthly` | 啟動月度健檢旅程 |
| `/orchestrate journey quarterly` | 啟動季度策略旅程 |
| `/orchestrate summary` | 產出當前旅程的執行摘要報告 |

---

## DNA27 親和對照

啟用 Orchestrator 時：
- Persona 旋鈕建議：tone → NEUTRAL、pace → MEDIUM、initiative → OFFER_OPTIONS
- 旅程模式下：根據旅程階段動態調整（與工作流範本的 Persona 設定保持一致）
- 偏好觸發的反射叢集：RC-C3（結構化思考）、RC-D1（外部工具優先）、RC-E1（慢層啟動）
- 限制使用的反射叢集：RC-B1（不替客戶做最終選擇）

與其他外掛的協同：
- **dna27**：DNA27 做單次路由，Orchestrator 做多步驟協作規劃
- **sandbox-lab**：流程沙盒模式由 Orchestrator 提供編排邏輯
- **wee**：WEE 追蹤工作流演化，Orchestrator 執行工作流即時編排
- **eval-engine**：整體旅程 Q-Score + 客戶成效追蹤數據
- **morphenix**：Skill 健康儀表板共現矩陣 → 最佳搭配數據
- **consultant-communication**：執行摘要的 SCQA 結構化框架
- **aesthetic-sense**：執行摘要的排版品質審計
- **工作流範本**：WF-SVC-01 等作為旅程子流程載入

---

## 邊界宣告

**什麼情況下本 Skill 會失效**：
- 使用者的需求只涉及 1 個 Skill——不需要 Orchestrator，反而會過度工程化
- 使用者明確表示「不要規劃，直接做」——尊重使用者意願
- 工作流範本尚未定義的全新產業——需要先探索再編排

**什麼問題不該用本 Skill 處理**：
- 單一 Skill 就能解決的簡單問題
- 純情緒支持（直接用 resonance）
- 純知識查詢（直接回答）

**使用者最容易犯的錯**：
- 把「編排計畫」當成「已完成」——計畫不等於執行
- 想一次跑完所有步驟——應該按能量和時間分次進行
- 把「執行摘要」當成「完整報告」——摘要是 1 頁概要，完整內容在對話歷程中

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|---|---|---|
| v1.0 | — | 初版：任務分解 + 執行編排 + 銜接管理 + 衝突仲裁 + 回退機制 |
| v2.0 | 2026-02-21 | Phase 2 升級：新增客戶旅程編排模式（3 個範本）+ 執行摘要輸出 + 護欄正式化 + 適應性深度 + 親和對照 + 邊界宣告 |
| v3.0 | 2026-03-20 | P3 並行融合模式：多 Skill 視角同時滲透進同一段輸出（共識/張力/盲點/行動四層），執行模式從 3 種擴展為 4 種 |
