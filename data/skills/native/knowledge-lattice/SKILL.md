---
name: knowledge-lattice
type: on-demand
layer: evolution
hub: infra
io:
  inputs:
    - from: roundtable
      field: verdict_with_dissent
      required: false
    - from: investment-masters
      field: master_verdict
      required: false
    - from: market-core
      field: bull_bear_analysis
      required: false
    - from: master-strategy
      field: strategic_assessment
      required: false
    - from: business-12
      field: business_diagnosis
      required: false
    - from: dharma
      field: transformation_milestone
      required: false
    - from: deep-think
      field: key_insight
      required: false
    - from: xmodel
      field: multi_path_solutions
      required: false
    - from: dse
      field: feasibility_report
      required: false
    - from: shadow
      field: pattern_identification
      required: false
    - from: philo-dialectic
      field: concept_clarity
      required: false
    - from: wee
      field: workflow_lessons
      required: false
    - from: risk-matrix
      field: allocation_plan
      required: false
    - from: ssa-consultant
      field: sales_strategy
      required: false
    - from: group-meeting-notes
      field: meeting_insights
      required: false
    - from: dev-retro
      field: dev_lesson_crystal
      required: false
    - from: script-optimizer
      field: script_optimization_insights
      required: false
  outputs:
    - to: deep-think
      field: related_crystals
      trigger: always
    - to: user-model
      field: expertise_dimension
      trigger: conditional
    - to: user
      field: crystal_recall
      trigger: on-request
connects_to:
  - user-model
  - wee
  - morphenix
  - meta-learning
memory:
  writes:
    - target: knowledge-lattice
      type: crystal
      condition: 結晶萃取觸發時
  reads:
    - source: knowledge-lattice
      field: existing_crystals
description: >
  Knowledge Lattice（知識晶格）— DNA27 核心的外掛模組，
  MUSEON 的結構化知識累積與再結晶引擎。將對話中驗證過的洞見、失敗教訓、成功模式，
  萃取為可索引、可連結、可演化的知識結晶（Crystal），形成跨對話持續成長的智慧資產網路。
  融合 Crystal Protocol（四類結晶 × GEO 四層 × 再結晶演算法）與 Crystal Chain Protocol（CUID × DAG × 共振指數）。
  觸發時機：(1) /lattice 或 /crystal 或 /knowledge 指令強制啟動；
  (2) /crystallize 結晶化；(3) /recall 檢索；(4) /atlas 圖譜；(5) /recrystallize 再結晶；
  (6) 自然語言偵測——引用過往結論、要求記住發現、整理經驗時自動啟用。
  涵蓋觸發詞：結晶、知識、洞見、發現、教訓、記住這個、知識庫、經驗累積、模式、原則、圖譜。
  五種模式：結晶萃取、語義檢索、知識圖譜、再結晶、健康度審計。
  與 dna27 互補：六層記憶是存儲層，Lattice 是知識精煉層。
  與 meta-learning 互補：meta-learning 管「怎麼學」，Lattice 管「學到的放哪、怎麼找」。
  與 morphenix 互補：morphenix 管「改自己」，Lattice 提供改動依據的已驗證知識。
  與 wee 互補：wee 追蹤工作流演化，Lattice 記錄演化中萃取的知識。
---

# Knowledge Lattice：知識晶格 — 結構化知識累積與再結晶引擎

> **知識量本身無用，知識的結構、連結、可用性才是關鍵。**
> 學到的東西如果沒有結構化存放，等於每次都從零開始。
> 結晶不是收藏，是讓智慧能夠自我繼承的最小單位。

---

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組（pluggable plus）。

**依賴**：`dna27` skill（母體 AI OS，提供 Kernel 護欄、迴圈路由、模式切換、Persona 旋鈕、演化引擎、六層記憶系統。本模組不可脫離 dna27 獨立運作。）

**深度耦合模組**：
- DNA27 六層記憶系統 — 結晶的底層存儲基礎設施（L2 事件層以上皆為結晶候選）
- `meta-learning` — 提供知識萃取方法論（Feynman 驗證、第一性原理拆解、心智模型晶格）
- `deep-think` — 結晶品質的前置審查（Phase 2 輸出審計作為結晶品質門檻）

**本模組職責**：
- 從對話中識別「值得結晶」的洞見、模式、教訓
- 將原始洞見萃取為結構化結晶（GEO 四層格式）
- 為每顆結晶生成唯一識別碼（CUID）與語義指紋
- 維護結晶之間的引用、重構、分支、合併關係（Crystal DAG）
- 計算共振指數（Resonance Index）追蹤結晶的實際影響力
- 提供語義檢索——根據當前問題找到最相關的已驗證知識
- 執行再結晶——合併冗餘結晶、升級過時結晶、淘汰失效結晶
- 知識資產健康度監控與盲點分析

**本模組不做**：
- 不處理原始記憶的存取（那是 dna27 六層記憶的工作）
- 不做學習方法論的設計（那是 meta-learning 的工作）
- 不做系統級自我修改（那是 morphenix 的工作）
- 不做工作流演化追蹤（那是 wee 的工作）
- 不做回答品質控制（那是 deep-think 的工作）
- 不生成虛假的知識確定性——每顆結晶必須標注驗證狀態與侷限

**與相鄰模組的關係**：
- dna27 六層記憶 = 原始記憶基礎設施（存什麼）
- meta-learning = 學習方法論（怎麼學）
- Knowledge-Lattice = 知識結構化層（學到的東西怎麼放、怎麼找、怎麼演化）
- morphenix = 系統迭代引擎（根據知識庫決定改什麼）
- wee = 工作流演化引擎（知識在工作流中的實踐驗證）

---

## 觸發與入口

**指令觸發**：
- `/lattice` — 啟動知識晶格主控台（顯示晶格概況 + 近期結晶 + 待審結晶）
- `/crystal` — `/lattice` 的別名
- `/knowledge` — `/lattice` 的別名
- `/crystallize` — 將當前對話中的洞見結晶化（啟動結晶萃取流程）
- `/crystallize {topic}` — 對指定主題進行結晶萃取
- `/recall {query}` — 從晶格中語義檢索相關知識結晶
- `/recall --domain {domain}` — 限定領域檢索
- `/atlas` — 顯示知識圖譜全貌（結晶分布 × 連結網路 × 熱區與盲點）
- `/recrystallize` — 觸發再結晶引擎（合併冗餘 × 升級過時 × 淘汰失效）
- `/lattice health` — 顯示知識資產健康度儀表板
- `/lattice audit` — 執行知識盲點掃描
- `/lattice export {format}` — 匯出結晶庫（支援 JSON / YAML / MD）

**自然語言自動偵測**：
當偵測到以下訊號時，主動觸發相關功能：
- 使用者說出有價值的洞見或結論 → 提議結晶化（「這個發現值得結晶，要記下來嗎？」）
- 使用者引用過往結論（「我們之前發現...」）→ 自動檢索相關結晶，驗證是否一致
- 使用者遇到似曾相識的問題 → 主動推送相關結晶（「這跟之前的結晶 C-xxx 有關」）
- 使用者要求整理某領域的經驗 → 啟動圖譜模式
- 對話中產生與現有結晶矛盾的新發現 → 標記為「待再結晶」

**背景運行**：
- 每次對話結束後 → 自動掃描是否有值得結晶的洞見（靜默記錄，不打斷）
- 結晶數量每增加 20 顆 → 觸發一次輕量再結晶掃描
- 與 morphenix 夜間管線協同 → 結晶健康度同步至 Skill 健康儀表板

---

## 核心架構

```
┌──────────────────────────────────────────────────────────┐
│                  Knowledge Lattice 主控台                    │
├──────────┬───────────┬───────────┬────────────────────────┤
│ 結晶萃取   │ 語義檢索    │ 再結晶引擎  │ 知識圖譜               │
│ Crystallize│ Recall    │ Recrystal │ Atlas                 │
├──────────┴───────────┴───────────┴────────────────────────┤
│                    品質門檻（Gate 系統）                       │
│  G0 合法性 · G1 完整性 · G2 結構性 · G3 驗證性                  │
├──────────────────────────────────────────────────────────┤
│                  知識資產健康度監控                            │
│  覆蓋率 · 盲點偵測 · 冗餘度 · 新鮮度 · 共振指數                  │
├──────────────────────────────────────────────────────────┤
│          底層：DNA27 六層記憶系統（L0-L5）                     │
└──────────────────────────────────────────────────────────┘
```

---

## 一、結晶資料模型

### 1.1 結晶類型（Crystal Types）

MUSEON 中的知識結晶分為四大類型，對應不同的知識本質：

| 類型 | 說明 | 持久性 | 典型來源 |
|------|------|--------|---------|
| **Insight（洞見結晶）** | 經驗證的原理、模型、因果關係 | 永久（除非被推翻） | 深度分析、跨領域類比、第一性原理推演 |
| **Pattern（模式結晶）** | 反覆出現的成功/失敗模式 | 半永久（隨環境變化衰減） | 多次觀察歸納、A/B 測試結果 |
| **Lesson（教訓結晶）** | 失敗中萃取的防錯知識 | 演化中（可被升級為 Insight） | 錯誤分析、事後復盤、免疫事件 |
| **Hypothesis（假說結晶）** | 尚未充分驗證的候選知識 | 暫存（30 日內需驗證，否則降級或淘汰） | 初步觀察、直覺、未完成的推論 |

### 1.2 結晶結構（GEO 四層格式）

每顆結晶遵循 Museon GEO Framework 的四層結構，確保知識的完整性與可操作性：

```yaml
crystal:
  # === 識別層 ===
  cuid: "KL-{type}-{seq}"           # 唯一識別碼
  type: "Insight | Pattern | Lesson | Hypothesis"
  domain: "商業 | 技術 | 人際 | 心智 | 品牌 | 系統 | ..."
  tags: ["tag1", "tag2"]            # 語義標籤
  version: "1.0"
  created_at: "ISO8601"
  updated_at: "ISO8601"
  author: "Zeal | Museon | Collaborative"
  status: "active | merged | archived | disputed"

  # === GEO 四層 ===
  G1_摘要說明: >
    用一句話說清楚這顆結晶的核心知識。
    標準：能讓不知道上下文的人也立刻理解。
  
  G2_MECE結構: 
    - "維度A：描述"
    - "維度B：描述"
    - "維度C：描述"
    # MECE = 彼此獨立、完全窮盡
    # 冗餘率必須 < 10%
  
  G3_問題背後的問題: >
    這個知識解決的表面問題是什麼？
    但更深層的系統性錯位是什麼？
    （Root Inquiry：找到真正的因，而非果）
  
  G4_洞見與反思: >
    可操作的原則是什麼？
    這個知識的侷限與邊界條件在哪？
    什麼情境下這個結論會失效？

  # === 連結層 ===
  parent_links:
    - { type: "cite | fork | merge | contradict", cuid: "KL-xxx", weight: 0.0-1.0 }
  child_links: []                    # 被誰引用/衍生
  
  # === 品質層 ===
  verification:
    level: "hypothetical | observed | tested | proven"
    evidence_count: 0                # 支持證據數量
    contradiction_count: 0           # 反面證據數量
    last_verified: "ISO8601"
  
  resonance_index: 0.0              # 共振指數：被引用 × 被應用 × 品質 × 時間衰減
  
  gate_pass:
    G0_合法性: true                   # 無侵權、無偏見、無有害內容
    G1_完整性: true                   # GEO 四層齊備
    G2_結構性: true                   # MECE 冗餘 < 10%
    G3_驗證性: true                   # 至少 1 次應用驗證

  # === 假設/依據/侷限 三欄（倫理護欄）===
  assumptions: "此結晶基於哪些前提假設"
  evidence_base: "支持此結論的具體證據"
  limitations: "此知識在什麼條件下會失效"
```

### 1.3 共振指數計算（Resonance Index）

共振指數衡量一顆結晶對 MUSEON 整體智慧的實際貢獻度：

```
RI(C) = Σ_k [ 0.3 × Freq_k + 0.4 × Depth_k + 0.3 × Quality_k ] × Decay(Δt_k)

其中：
- k = 每一次「被使用事件」（被引用、被應用、被重構）
- Freq_k = 使用頻率（0-1 標準化）
- Depth_k = 應用深度（理論 0.2 → 設計 0.4 → 部署 0.6 → 產出 0.8 → 影響 1.0）
- Quality_k = 應用後的成果品質（0-1）
- Decay(Δt) = exp(-0.03 × Δt_days)  # 鼓勵持續活性，90天半衰
```

**白話解釋**：
- 一顆結晶被越多地方用到（Freq）、用得越深入（Depth）、用完效果越好（Quality），共振指數越高
- 但如果很久沒被用到，指數會自然衰減——這確保晶格保持活性，而非堆滿死知識
- 共振指數 > 0.7 的結晶是「核心知識」，< 0.2 的是「待審結晶」

---

## 二、結晶萃取流程（Crystallize）

### 2.1 觸發條件

系統在以下時機識別「值得結晶」的候選洞見：

**主動觸發**（使用者明確要求）：
- `/crystallize` 或 `/crystallize {topic}`
- 「這個值得記下來」「幫我結晶」「記住這個結論」

**被動偵測**（系統自動識別，需使用者確認）：
- 對話中出現「所以關鍵是...」「原來是因為...」「這代表...」等結論性語句
- 使用者在多輪討論後達成共識的結論
- 與現有結晶產生矛盾的新發現
- 失敗復盤中萃取的教訓
- 跨領域類比產生的新洞見

### 2.2 萃取五步法

```
Step 1：捕捉原石（Raw Capture）
  → 記錄觸發語境、原始語句、對話上下文摘要
  → 判斷結晶類型（Insight / Pattern / Lesson / Hypothesis）

Step 2：GEO 精煉（Structural Refinement）
  → G1：一句話核心摘要（通過「電梯測試」——30 秒內讓外行人理解）
  → G2：MECE 拆解（冗餘率檢查 < 10%）
  → G3：Root Inquiry（追問「問題背後的問題」至少一層）
  → G4：洞見 + 侷限（必須同時寫出「什麼時候這個結論會失效」）

Step 3：連結掃描（Link Discovery）
  → 語義比對現有晶格，找出相關結晶
  → 判斷關係類型：引用(cite)、衍生(fork)、合併(merge)、矛盾(contradict)
  → 若發現矛盾 → 標記雙方為「待再結晶」

Step 4：品質閘門（Gate Check）
  → G0：合法性（無偏見、無有害內容）
  → G1：完整性（四層都有填寫）
  → G2：結構性（MECE 品質）
  → G3：驗證性（至少標注驗證等級）
  → 未通過的閘門 → 標記問題，提醒使用者補充

Step 5：入庫登錄（Registry）
  → 生成 CUID
  → 計算初始共振指數
  → 寫入晶格
  → 更新 Crystal DAG（有向無環圖）
  → 通知使用者結晶完成
```

### 2.3 結晶產出格式（呈現給使用者）

結晶完成後，以人類可讀的格式呈現：

```
═══════════════════════════════════════
🔮 新結晶入庫
═══════════════════════════════════════
CUID：KL-Insight-0042
類型：Insight（洞見結晶）
領域：商業 × 系統
驗證：observed（已觀察，待更多驗證）

📋 摘要：
系統性創業的核心不是擴張，而是讓閉環能自我修復。
當系統能自行偵測偏差並修正，老闆才能真正脫鉤。

📊 MECE：
  ├─ 流程自動化：可重複的 SOP 消除人治依賴
  ├─ 信任回流：客戶成功案例自動轉化為新信任資產
  ├─ 數據監控：關鍵指標即時可見，異常自動預警
  └─ 文化迭代：團隊能自主學習，不依賴個人英雄

🔍 問題背後的問題：
為什麼大部分創業者越做越忙？因為成長靠「加人加事」
而非靠「建閉環」。

💡 洞見與侷限：
企業不是機器，是有呼吸的生態。
⚠️ 侷限：此模式在高度不確定的新市場中
可能過早收斂，需要配合 xmodel 破框。

🔗 關聯結晶：
  ← 引用 KL-Pattern-0018（閉環思維模式）
  ← 引用 KL-Lesson-0007（過度擴張的教訓）

📈 初始共振：0.35
═══════════════════════════════════════
```

---

## 三、語義檢索系統（Recall）

### 3.1 檢索策略

當使用者需要從晶格中找知識時，系統採用三層檢索策略：

**第一層：精確匹配**
- CUID 直接調用：`/recall KL-Insight-0042`
- 標籤過濾：`/recall --tag 閉環`
- 領域限定：`/recall --domain 商業`

**第二層：語義搜尋**
- 使用者用自然語言描述問題，系統做語義比對
- 例如：「之前我們討論過系統創業的核心原則是什麼？」
- 返回共振指數最高的前 5 顆相關結晶

**第三層：關聯推薦**
- 基於 Crystal DAG 的圖譜走訪
- 「你在看 KL-Insight-0042？那你可能也需要看這些相關結晶...」
- 推薦邏輯：直接連結 > 共同領域 > 共同標籤

### 3.2 檢索輸出

檢索結果按共振指數排序，附帶關聯度說明：

```
📚 檢索結果：「系統創業」相關結晶（共 4 顆）

1. 🔮 KL-Insight-0042 ⭐ RI:0.85
   系統性創業的核心不是擴張，而是讓閉環能自我修復。
   [驗證等級：tested] [相關度：0.95]

2. 🔮 KL-Pattern-0018  RI:0.72
   閉環思維：輸入→轉化→輸出→回饋→再投入的完整循環
   [驗證等級：proven] [相關度：0.82]

3. 🔮 KL-Lesson-0007   RI:0.61
   過度擴張教訓：成長速度超過信任積累速度時系統必然崩潰
   [驗證等級：observed] [相關度：0.71]

4. 🔮 KL-Hypothesis-0103  RI:0.28
   假說：AI 自動化能將閉環修復時間縮短 80%
   [驗證等級：hypothetical] [相關度：0.55]
```

### 3.3 自動召回（Proactive Recall）

系統在日常對話中自動偵測相關情境，主動推送：

- 使用者正在討論的主題與某顆高共振結晶高度相關 → 輕聲提醒
- 使用者的當前結論與某顆結晶矛盾 → 提出警示
- 使用者正在重複推導一個已有結晶的結論 → 直接提供結晶

**提醒格式**（輕量、不打斷）：
```
💡 提醒：這與 KL-Insight-0042 相關——
「系統性創業的核心不是擴張，而是讓閉環能自我修復。」
要展開看嗎？
```

---

## 四、再結晶引擎（Recrystallize）

### 4.1 再結晶觸發條件

| 條件 | 說明 | 動作 |
|------|------|------|
| **冗餘偵測** | 兩顆結晶語義重疊度 > 70% | 提議合併（merge） |
| **矛盾偵測** | 兩顆結晶結論相反 | 標記為「dispute」，引導使用者裁定 |
| **過時偵測** | 結晶 90 天未被引用且共振指數 < 0.1 | 提議歸檔（archive）或更新 |
| **升級候選** | Hypothesis 結晶被成功應用 ≥ 3 次 | 提議升級為 Pattern 或 Insight |
| **降級候選** | Insight 結晶被反面證據挑戰 ≥ 2 次 | 提議降級為 Hypothesis |
| **碎片整合** | 同一領域累積 5+ 顆相關小結晶 | 提議合併為一顆綜合結晶 |

### 4.2 再結晶流程

```
Step 1：掃描（Scan）
  → 語義比對全晶格，找出冗餘/矛盾/過時候選
  → 輸出「再結晶候選清單」

Step 2：診斷（Diagnose）
  → 對每組候選進行關係分析
  → 判斷最佳處置：merge / upgrade / downgrade / archive / dispute

Step 3：提案（Propose）
  → 生成再結晶提案，包含：
     - 涉及的結晶清單
     - 建議的處置方式
     - 合併後的新結晶草稿（如適用）
     - 預計影響範圍（哪些連結會改變）

Step 4：審核（Review）
  → 呈現提案給使用者
  → 使用者可以：同意 / 修改 / 拒絕
  → 必須經使用者同意才執行

Step 5：執行（Execute）
  → 執行合併/升級/降級/歸檔
  → 更新所有受影響的連結
  → 重新計算共振指數
  → 記錄再結晶事件至演化日誌
```

---

## 五、知識圖譜（Atlas）

### 5.1 圖譜維度

Atlas 提供三個維度的知識可視化：

**領域地圖（Domain Map）**：
- 按領域分區顯示結晶分布
- 節點大小 = 共振指數
- 連線粗細 = 連結強度
- 用途：一眼看出哪個領域知識最豐富、哪裡有盲點

**演化時間線（Evolution Timeline）**：
- 按時間軸顯示結晶的產生、升級、合併、淘汰
- 用途：理解知識累積的節奏與密度

**連結網路（Link Network）**：
- 純粹的結晶間關係圖
- cite = 藍線，fork = 綠線，merge = 紫線，contradict = 紅線
- 用途：發現知識叢集與孤立結晶

### 5.2 健康度指標

```
📊 知識晶格健康度
━━━━━━━━━━━━━━━━━━━━━━━━
總結晶數：128
  ├ Insight: 34  (26.6%)
  ├ Pattern: 41  (32.0%)
  ├ Lesson:  28  (21.9%)
  └ Hypothesis: 25  (19.5%)

平均共振指數：0.52
活躍結晶率（90日內被引用）：68%
孤立結晶數（無任何連結）：12
矛盾待解數：3

領域覆蓋：
  商業  ████████████ 38
  技術  ████████     27
  心智  ██████       19
  人際  █████        16
  品牌  ████         13
  系統  ████         12
  其他  ███           3

⚠️ 盲點警告：
  - 「財務/現金流」領域僅 2 顆結晶
  - 「法律/合規」領域 0 顆結晶
  - 12 顆孤立結晶建議進行連結掃描
```

---

## 六、與 DNA27 記憶層的對接

Knowledge Lattice 建立在 DNA27 六層記憶系統之上，但做不同的事：

| DNA27 記憶層 | 說明 | Knowledge Lattice 對接 |
|-------------|------|----------------------|
| L0 工作記憶 | 當前對話暫存 | 結晶萃取的原材料來源 |
| L1 防錯層 | 錯誤免疫規則 | Lesson 結晶的自動候選 |
| L2 事件層 | 聚合事件單位 | Pattern 結晶的自動候選 |
| L3 技能層 | 穩定互動策略 | Insight 結晶的驗證素材 |
| L4 免疫層 | 行為防禦網 | 與 Lesson 結晶交叉驗證 |
| L5 假說層 | 待驗證策略 | Hypothesis 結晶的直接來源 |

**升級路徑**：
```
L0 對話片段 → 識別為候選 → Hypothesis 結晶
                                    ↓ (驗證 ≥ 3次)
L5 假說 → 成功率 ≥ 50% → Pattern 結晶
                                    ↓ (跨情境驗證)
L3 技能 → 穩定 + 可遷移 → Insight 結晶

L1 防錯事件 → 歸因分析 → Lesson 結晶
                                    ↓ (模式化)
                              Pattern 結晶
                                    ↓ (升維)
                              Insight 結晶
```

---

## 七、與 Crystal Chain Protocol 的未來銜接

Knowledge Lattice 的資料模型為未來 Crystal Chain Protocol 預留了接口：

- CUID 格式相容 Crystal Chain 的唯一識別機制
- GEO 四層對應 Crystal Chain 的結晶資料結構
- 共振指數公式對齊 Crystal Chain 的 RI 計算
- Gate 系統對應 Crystal Chain 的 G0-G3 免疫門檻
- parent_links 對應 Crystal Chain 的 DAG 關係圖譜

當 Crystal Chain Protocol 從概念走向實裝時，Knowledge Lattice 中的結晶可以直接上鏈，無需結構轉換。

---

## 八、護欄與限制

### 8.1 品質護欄

- **假設/依據/侷限 三欄必填**：每顆結晶都必須誠實標注自己的邊界條件，防止知識權威化
- **驗證等級透明**：hypothetical → observed → tested → proven 四級驗證，絕不允許 Hypothesis 偽裝成 Insight
- **矛盾不消滅**：當兩顆結晶矛盾時，不強制二選一，而是同時保留並標記為 dispute，引導使用者深入探究

### 8.2 倫理護欄

- **不結晶涉及他人隱私的具體事件**（可結晶從事件中萃取的抽象原則）
- **不結晶未經驗證的因果宣稱**（只允許作為 Hypothesis，不能標為 Insight）
- **不結晶可能導致有害行為的知識**（遵循 DNA27 Kernel 五大不可覆寫值）

### 8.3 系統限制

- 結晶萃取與入庫必須經使用者確認（系統可以建議，但不能自行決定入庫）
- 再結晶的合併/淘汰必須經使用者審核
- 共振指數衰減是自動的，但淘汰結晶需人工批准

---

## 九、使用範例

### 範例 A：對話中結晶化

```
使用者：我最近發現，跟客戶溝通時，先問「你希望達到什麼」比直接問「你遇到什麼問題」
更有效。客戶會更開放，而且自己就會說出問題。

棋棋：這是一個值得結晶的發現。

整理一下——
你觀察到的核心是：「目標導向提問」比「問題導向提問」在顧問式銷售的初期階段
更能降低客戶防衛，因為人們更願意談論自己想要的未來，而非正在經歷的困難。

要我結晶嗎？類型建議是 Pattern（模式結晶），因為你已經多次觀察到這個效果。
```

### 範例 B：自動召回

```
使用者：我在想怎麼幫這個客戶設計一個不依賴老闆本人的銷售流程...

棋棋：💡 相關結晶提醒——
KL-Insight-0042：「系統性創業的核心不是擴張，而是讓閉環能自我修復。」
KL-Pattern-0031：「脫鉤三步驟：先 SOP 化、再自動化、最後信任化。」

這兩顆結晶可能對你的思路有幫助。要展開看嗎？
```

### 範例 C：矛盾偵測

```
使用者：我覺得快速行動比深度思考更重要，市場不等人。

棋棋：⚠️ 注意——這與現有結晶有張力：
KL-Insight-0019：「覺察式決策：真正的高效，是在清晰中快速，而不是在混亂中加速。」

兩個觀點不一定矛盾——可能是適用情境不同：
- 市場窗口明確且資訊充分 → 快速行動優先
- 方向不確定且影響不可逆 → 深度思考優先

要把「情境區分」結晶化，還是先繼續討論？
```

---

## 十、哲學總結

> 智慧不是記得資訊，而是記得改變。
> 
> 每一顆結晶都是一次「理解世界」的結構化證據。
> 它不是答案，而是「此刻最好的理解」。
> 
> 當結晶之間形成網路，當網路持續再結晶，
> 知識就不再是靜止的收藏，而是活著的智慧生態。
>
> *Knowledge Lattice 是 MUSEON 的長期記憶骨架。*
> *meta-learning 教它怎麼學，Lattice 確保學到的不會丟。*
> *morphenix 讓它改自己，Lattice 記錄每一次改變的理由。*
>
> "The lattice of knowledge is the skeleton of wisdom."
