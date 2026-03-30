---
name: brand-builder
type: on-demand
layer: business
hub: business
io:
  inputs:
    - from: brand-discovery
      field: client_brand_brief
      required: true
      description: "brand-discovery 產出的結構化品牌簡報"
    - name: direct_client_brief
      from: user
      required: false
      description: "若未跑 brand-discovery，可直接提供客戶品牌資訊"
  outputs:
    - to: workflow-brand-consulting
      field: brand_strategy_package
      trigger: on_completion
      description: "完整品牌策略包，含七框架分析結果（HUMAN_DOC）"
    - to: all-downstream-skills
      field: brand_canon
      trigger: on_completion
      description: "機器可讀 YAML Canon，下游 Skill 的唯一品牌定位來源（MACHINE_CANON）"
    - to: user
      field: brand_strategy_deck
      trigger: always
    - to: knowledge-lattice
      field: brand_crystal
      trigger: on_completion
connects_to:
  - brand-discovery
  - brand-identity
  - aesthetic-sense
  - storytelling-engine
  - consultant-communication
  - report-forge
  - orchestrator
  - knowledge-lattice
  - brand-project-engine
memory:
  writes:
    - knowledge-lattice
  reads:
    - brand-discovery
    - knowledge-lattice
description: >
  Brand Builder（奧美級品牌建構引擎）— DNA27 核心的外掛模組，
  品牌建構工作流的核心分析引擎。接收 brand-discovery 的結構化資料，
  運行七大國際品牌框架，產出完整的品牌策略包。
  七框架：① Keller 品牌共鳴金字塔（六層）② Jung 12 品牌原型（含 Shadow 面）
  ③ JTBD for Brand（三層工作理論）④ 品牌架構決策樹（三型六路徑）
  ⑤ Brand Purpose 五層測試（Simon Sinek 深化版）
  ⑥ 觸點生命週期規範（六階段）⑦ April Dunford 競爭定位（五要素強化版）
  觸發時機：(1) /brand-build 指令強制啟動；
  (2) workflow-brand-consulting Phase B 自動調用；
  (3) brand-discovery 完成後自動建議啟動。
  輸出：品牌策略文件 + 視覺規格書 + 語言規格書（供 workflow-brand-consulting 渲染 HTML）。
  此 Skill 依賴 DNA27 核心，不可脫離 DNA27 獨立運作。
  與 brand-project-engine 互補：brand-builder 產出品牌策略，brand-project-engine 管品牌行銷專案的階段推進與執行。
---

# Brand Builder 奧美級品牌建構引擎

## 外掛合約

**依賴**：MUSEON-DNA27-vNext + brand-discovery（資料來源）

**本模組職責**：
- 接收 `client_brand_brief`，執行七框架深度分析
- 產出 `brand_strategy_package`（結構化品牌策略包）
- 提供三個定位選項供客戶抉擇
- 輸出可直接用於 HTML 渲染的規格結構

**本模組不做**：
- 不做訪談資料蒐集（brand-discovery 的工作）
- 不做 HTML 渲染（workflow-brand-consulting Phase E 的工作）
- 不做內容生產（text-alchemy 的工作）
- 不做實際視覺設計執行（只定義規格）

---

## 七大分析框架

---

### 框架一：Keller 品牌共鳴金字塔（Brand Resonance Pyramid）

*出處：Kevin Lane Keller, Strategic Brand Management*

品牌強度從下往上建構，每層為上一層奠基。

```
                    ┌─────────────────────┐
                    │  6. RESONANCE        │  忠誠度、社群歸屬、主動推薦
                    └──────────┬──────────┘
              ┌─────────────────┴────────────────┐
              │  4. JUDGMENTS   5. FEELINGS       │  品質感知 ↔ 情感共鳴
              └─────────────────┬────────────────┘
        ┌────────────────────────┴──────────────────────┐
        │  2. PERFORMANCE          3. IMAGERY            │  功能表現 ↔ 形象聯想
        └────────────────────────┬──────────────────────┘
                    ┌─────────────┴─────────────┐
                    │  1. SALIENCE              │  知名度、第一聯想
                    └───────────────────────────┘
```

**分析步驟**：

根據 `client_brand_brief` 逐層填寫：

| 層級 | 核心問題 | 從 brief 萃取 | 輸出建議 |
|------|---------|-------------|---------|
| Salience | 客戶想到這個品類，能想到你嗎？ | `competitive_alternatives` + `win_reasons` | 知名度策略 |
| Performance | 你的產品/服務在功能上表現如何？ | `core_product_service` + `jtbd_functional` | 產品溝通要點 |
| Imagery | 品牌在用戶心中的形象聯想是什麼？ | `desired_feeling_words` + `visual_references_love` | 形象設計方向 |
| Judgments | 用戶對品牌的品質、可信度、優越感判斷 | `word_of_mouth_script` + `purchase_barrier` | 信任建立策略 |
| Feelings | 品牌喚起的情感：溫暖/興奮/安全/社會認可/自尊/自我實現 | `post_purchase_transformation` + `peak_delight_moment` | 情感溝通策略 |
| Resonance | 用戶與品牌的深度連結：忠誠/依附/社群/主動投入 | `jtbd_social` + `customers_we_dont_want` | 社群與忠誠計畫 |

**輸出**：六層填充的金字塔 + 每層「現況評分（1-5）」+ 「目標狀態」+ 「關鍵行動」

---

### 框架二：Jung 12 品牌原型系統（Brand Archetype）

*出處：Carl Jung 原型理論 × Margaret Mark & Carol Pearson, The Hero and the Outlaw*

**12 原型速查表**：

| 原型 | 核心渴望 | 品牌承諾 | 典型品牌 | 適用場景 |
|------|---------|---------|---------|---------|
| 天真者 Innocent | 純淨、快樂 | 讓生活回歸美好 | Dove、麥當勞早餐 | 消費品、健康 |
| 探索者 Explorer | 自由、發現 | 走出邊界 | The North Face、Patagonia | 戶外、旅行 |
| 智者 Sage | 真相、智慧 | 幫你看清楚 | Google、BBC | 教育、媒體、顧問 |
| 英雄 Hero | 勇氣、掌控 | 成為更好的自己 | Nike、Red Bull | 運動、挑戰 |
| 亡命之徒 Outlaw | 革命、改變 | 打破舊規則 | Harley-Davidson、Apple（早期） | 顛覆型品牌 |
| 魔法師 Magician | 轉化、奇蹟 | 讓夢想成真 | Disney、Tesla | 科技、娛樂 |
| 普通人 Everyman | 歸屬、連結 | 你不孤單 | IKEA、Gap | 大眾消費 |
| 戀人 Lover | 激情、美麗 | 你值得擁有最好的 | Chanel、Godiva | 奢侈品、美妝 |
| 弄臣 Jester | 歡樂、當下 | 生活不用這麼嚴肅 | Old Spice、M&M's | 食品飲料 |
| 照顧者 Caregiver | 服務、保護 | 我在你身旁 | UNICEF、嬌生 | 醫療、服務 |
| 統治者 Ruler | 控制、秩序 | 建立卓越標準 | Mercedes、HSBC | 金融、奢侈 |
| 創造者 Creator | 創新、表達 | 讓你的創意成真 | Adobe、LEGO | 創意工具 |

**原型分析步驟**：

1. **主原型識別**：根據 `founding_motivation` + `brand_personality_keywords` + `five_year_vision` 匹配最強共鳴原型（1 個）
2. **次原型識別**：根據 `ideal_customer_profile` + `jtbd_emotional` 識別次要原型（1 個）
3. **Shadow 面診斷**：每個原型都有其陰影面——主動定義品牌要如何避免墮入 Shadow

| 主原型 | Shadow 表現 | 防禦策略 |
|--------|-----------|---------|
| 智者 | 冷漠、高傲、不接地氣 | 永遠用人話說話，不用術語炫耀 |
| 英雄 | 傲慢、咄咄逼人、忽視弱者 | 強調「一起」而非「超越別人」 |
| 照顧者 | 令人窒息、自我犧牲、討好 | 設定明確界線，服務有邊界 |
| 創造者 | 完美主義、不切實際 | 永遠問「這對用戶有什麼用？」 |
（其他 8 個原型依此邏輯展開）

**輸出**：主原型 + 次原型 + Shadow 診斷 + 品牌人格宣言（1 段）

---

### 框架三：JTBD for Brand（品牌工作理論）

*出處：Clayton Christensen Jobs-to-be-Done × Bob Moesta 品牌應用*

客戶不是在「買你的產品」，而是在「雇用你的品牌完成一個工作（Job）」。

**三層 Job 深度解析**：

```
Functional Job（功能性工作）
  「我需要___來達成___」
  例：「我需要一個設計師品牌來讓我的提案被認真對待」
  → 從 brief.jtbd_functional 萃取

Emotional Job（情感性工作）
  「我想要感覺___」
  例：「我想要感覺自己是懂品味的人」
  → 從 brief.jtbd_emotional 萃取

Social Job（社會性工作）
  「我想要被別人看見我___」
  例：「我想讓同行看到我選了一個有眼光的合作對象」
  → 從 brief.jtbd_social 萃取
```

**JTBD 品牌定位公式**：

```
當 [目標客群] 在 [情境/掙扎] 時，
他們雇用 [品牌名] 來完成 [功能工作]，
感受到 [情感工作]，
並向他人展示 [社會工作]。

而現有替代方案 [競品] 無法做到，因為 [替代方案的結構性缺陷]。
```

**輸出**：三層 Job 清晰定義 + JTBD 定位公式 + 品牌承諾句

---

### 框架四：品牌架構決策樹（Brand Architecture）

*出處：David Aaker Brand Portfolio Strategy × P&G vs Apple 模型比較*

當客戶有多個產品線/子品牌時，必須決定架構模型。

**三大架構類型**：

```
① Monolithic（單一品牌架構）
  母品牌撐全場，所有產品共用一個名字
  ✓ 適用：品牌力強、產品相關性高
  ✓ 例：Apple（iPhone/Mac/iPad 都是 Apple）
  ✗ 風險：一個產品失敗拖累整個品牌

② Endorsed（背書品牌架構）
  母品牌為子品牌背書，子品牌有獨立個性
  ✓ 適用：拓展新市場但需母品牌信任背書
  ✓ 例：Marriott（Marriott Hotels、Ritz-Carlton by Marriott）
  ✗ 風險：品牌管理複雜度高

③ Pluralistic（獨立品牌架構）
  各品牌完全獨立，母公司隱形
  ✓ 適用：目標客群差異大、品類跨度大
  ✓ 例：P&G（Tide、Pantene、Gillette 各自獨立）
  ✗ 風險：資源分散、無法積累品牌資產
```

**決策標準**：

| 評估維度 | Monolithic | Endorsed | Pluralistic |
|---------|-----------|---------|------------|
| 目標客群重疊度 | 高（>70%） | 中（40-70%） | 低（<40%） |
| 品牌價值一致性 | 高 | 中 | 低或刻意區隔 |
| 資源規模 | 小/中型 | 中型 | 大型 |
| 失敗隔離需求 | 低 | 中 | 高 |

**輸出**：架構類型建議（含理由）+ 子品牌命名系統建議（若適用）

---

### 框架五：Brand Purpose 五層測試

*出處：Simon Sinek Golden Circle 深化 × Jim Stengel Brand Ideal × Patagonia 實踐案例*

**五層 Purpose 測試**（層層深入，直到觸底）：

```
Layer 1：What（你做什麼）
  → brief.one_liner + core_product_service
  這是最表面的，幾乎每個品牌都能說清楚

Layer 2：How（你怎麼做）
  → brief.win_reasons + peak_delight_moment
  你的獨特方法——通常是可防禦的差異化

Layer 3：Why（你為什麼做）
  → brief.founding_motivation + defining_moment
  你的起點動機——Simon Sinek 的黃金圈核心

Layer 4：為誰的 Why（你為誰而存在）
  → brief.ideal_customer_profile + post_purchase_transformation
  如果品牌消失，誰的生活會變差？他們的生活怎麼變差？

Layer 5：世界的 Why（品牌對世界的意義）
  → brief.five_year_vision + brand_absolutely_wont_do
  如果這個品牌存在 100 年，它在書寫什麼故事？
```

**Purpose 品質測試**：

一個真正的 Brand Purpose 必須通過：
- [ ] **真實性測試**：這是真的，還是市場行銷話術？（從 brief.founding_motivation 驗證）
- [ ] **差異化測試**：別的品牌也能說同樣的 Purpose 嗎？
- [ ] **可行動測試**：這個 Purpose 能指導日常決策嗎？
- [ ] **吸引力測試**：目標客群聽到這個 Purpose，會想靠近嗎？
- [ ] **邊界測試**：這個 Purpose 能幫你說「不」嗎？（與 brand_absolutely_wont_do 一致）

**輸出**：Brand Purpose 宣言（1-2 句）+ 五層解析 + Purpose 品質測試結果

---

### 框架六：觸點生命週期規範（Brand Touchpoint Map）

*出處：McKinsey Customer Journey × Byron Sharp How Brands Grow*

品牌在每個觸點的行為必須一致，才能累積品牌資產。

**六階段觸點規範**：

```
① Awareness（意識）
  客戶第一次聽說你
  核心問題：「你讓人第一眼記住什麼？」
  觸點：廣告/口碑/社群/PR/活動
  品牌行為規則：________________

② Consideration（考慮）
  客戶在評估你和競品
  核心問題：「你的什麼讓客戶把你放入候選清單？」
  觸點：官網/社群/評價/試用/簡報
  品牌行為規則：________________

③ Purchase（購買）
  客戶做決定的那一刻
  核心問題：「你如何讓這一刻感覺正確？」
  觸點：報價單/合約/收銀台/購物車
  品牌行為規則：________________

④ Onboarding/Use（使用）
  客戶開始使用你的服務
  核心問題：「第一次體驗應該確立什麼印象？」
  觸點：歡迎信/說明書/首次服務/包裝開箱
  品牌行為規則：________________

⑤ Loyalty（忠誠）
  客戶持續選擇你
  核心問題：「你如何讓回頭成為習慣？」
  觸點：會員計畫/定期服務/客服/感謝
  品牌行為規則：________________

⑥ Advocacy（推薦）
  客戶主動幫你傳播
  核心問題：「你給了他們什麼理由去談論你？」
  觸點：分享機制/口碑工具/社群內容
  品牌行為規則：________________
```

**各觸點從 brief 萃取**：
- brief.word_of_mouth_script → Advocacy 的核心語言
- brief.peak_delight_moment → Onboarding 的設計焦點
- brief.purchase_barrier → Purchase 的「讓它消失」清單
- brief.most_important_touchpoint → 最高優先規範觸點

**輸出**：六階段觸點清單 + 每個觸點的品牌行為規則 + 最高槓桿觸點標記

---

### 框架七：April Dunford 競爭定位強化版（Enhanced Competitive Positioning）

*出處：April Dunford, Obviously Awesome（強化版，加入競品 DNA 解構）*

**五要素強化分析**：

**① 競爭替代方案（深化版）**

除了列出替代方案，還要分析競品的「品牌 DNA」：

| 競品 | 原型 | Purpose | 目標客群 | 弱點 | 我們的機會 |
|------|------|---------|---------|------|----------|
| 競品A | | | | | |
| 競品B | | | | | |

來源：brief.competitive_alternatives + brief.industry_rules_we_reject

**② 差異化能力（可防禦性測試）**

差異化能力必須通過三項測試：
- **可感知**：客戶能直接感受到嗎？
- **可防禦**：競品三個月內能複製嗎？（能複製=不是差異化）
- **有價值**：客戶真的在乎嗎？（理論上很酷但客戶不在乎=假差異化）

**③ 獨特價值（功能→情感→社會三層表達）**

每個差異化能力都用三層翻譯：
```
功能層（What it does）：___
情感層（How it feels）：___
社會層（What it says about the user）：___
```

**④ 最佳目標客群（ICP 鑽石模型）**

```
外環：Demographics（人口統計）年齡/職業/地點
中環：Psychographics（心理特徵）信念/恐懼/渴望
內環：Behavioral（行為特徵）購買觸發點/使用習慣
核心：JTBD（工作理論）雇用你完成什麼工作
```

**⑤ 市場品類創造（Category Design）**

*出源：Play Bigger by Al Ramadan*

不要在既有品類裡競爭，創造新品類才能主導市場。

- 現有品類是：___
- 現有品類的問題/限制是：___
- 新品類名稱候選：___（3個）
- 新品類的「敵人」是：___（讓品類成立的對立面）

**輸出**：競爭定位矩陣 + 差異化能力清單（含可防禦性評分）+ 市場品類建議 + 一句話定位宣言

---

## 輸出結構：brand_strategy_package

七框架分析完成後，整合產出：

```
brand_strategy_package
├── brand_strategy/
│   ├── keller_pyramid.md          # 六層填充 + 行動建議
│   ├── archetype_profile.md       # 主/次原型 + 人格宣言
│   ├── jtbd_statement.md          # 三層 Job + 定位公式
│   ├── architecture_decision.md   # 架構類型 + 子品牌規則
│   ├── brand_purpose.md           # Purpose 宣言 + 五層解析
│   ├── touchpoint_map.md          # 六階段觸點規範
│   └── positioning_statement.md   # 競爭定位 + 品類創造
│
├── three_positioning_options/      # 三個定位路徑供客戶選擇
│   ├── option_conservative.md     # 保守路徑（強化現有優勢）
│   ├── option_balanced.md         # 平衡路徑（擴張但有節制）
│   └── option_aggressive.md       # 進攻路徑（品類創造 + 大膽宣言）
│
├── visual_identity_spec/
│   ├── color_system.md            # 主色/輔色/禁色 + 色碼 + 用法
│   ├── typography_system.md       # 三層字型 + 中文搭配 + 語意規則
│   ├── imagery_direction.md       # 圖像風格描述 + 參考方向 + 禁止方向
│   ├── logo_direction.md          # Logo 方向建議（供設計師參考）
│   └── do_dont_examples.md        # 視覺 Do/Don't 文字說明
│
└── verbal_identity_spec/
    ├── brand_voice.md             # 語調光譜 + 五軸座標
    ├── messaging_hierarchy.md     # 訊息金字塔（Tier 1/2/3）
    ├── vocabulary_library.md      # 品牌詞彙庫（用 vs 禁）
    ├── naming_system.md           # 產品/服務命名規則
    └── tagline_options.md         # Tagline 三個候選
```

---

## 雙軌輸出：HUMAN_DOC + MACHINE_CANON

brand-builder 在 Output 階段**必須同步產出兩份交付物**：

### (1) HUMAN_DOC（給人用）
即上方的 `brand_strategy_package`，人類可讀的品牌策略文件。

### (2) MACHINE_CANON（給 Skill 用）
以 YAML 格式輸出 `brand_canon`，作為所有下游 Skill（brand-identity、text-alchemy、workflow-brand-consulting 等）的**唯一可信品牌定位來源**。

**品牌定義權只存在 brand-builder**。下游 Skill 消費 Canon 時：
- 不得重新詮釋品牌定位
- 不得補寫缺失定位
- 不得用自身偏好修正 tone / 敘事 / 受眾 / 承諾
- 超出 Canon 的內容一律不產生
- Canon 缺欄位或自相矛盾時，必須回 brand-builder 更新

### brand_canon YAML Schema

```yaml
brand_canon:
  identity:
    who_we_are: ""       # 我們是誰（一句話）
    role: ""             # 在客戶生命中扮演什麼角色
    essence: ""          # 品牌本質（不可妥協的核心）

  audience:
    primary: ""          # 核心受眾描述
    core_tension: ""     # 受眾內在張力
    key_insight: ""      # 關鍵洞察

  positioning:
    promise: ""          # 品牌承諾（一句話）
    differentiation: []  # 差異化要素（列表）
    reasons_to_believe: [] # 信任理由（列表）

  narrative:
    arc: []              # 敘事弧線（品牌故事骨架）
    story_seed: ""       # 故事種子（一句話的品牌故事）
    forbidden_frames: [] # 禁止的敘事框架

  tone:
    must: []             # 語調必須有的特質
    must_not: []         # 語調絕對不能有的特質
    lexicon: []          # 品牌詞彙庫（推薦用詞）
    banned_words: []     # 禁用詞彙

  experience:
    top_touchpoints: []  # 優先觸點排序
    content_ratio:       # 內容比例
      narrative: 0
      education: 0
      community: 0

  governance:
    decision_rights: []  # 品牌決策權歸屬
    mini_raci:
      decider: ""
      reviewer: ""
      veto: ""
    rituals: []          # 品牌治理儀式

  growth:
    triple_funnel: []    # 三層漏斗
    triple_helix: []     # 三螺旋成長機制

  guardrail:
    one_line_guardrail: "" # 一句話護欄（品牌做什麼、不做什麼）

  risks:
    top_risks: []        # 最大風險
    mitigations: []      # 風險對策
```

### Evidence-First Auto-Gating（Canon 寫入門檻）

寫入 Canon 的品質門檻——不是所有品牌相關陳述都能進 Canon：

| 優先序 | 證據類型 | 可否進 Canon |
|-------|---------|------------|
| 1 | 真實案例（客戶故事、成交紀錄） | 直接寫入 |
| 2 | 行為/交易證據（數據、回饋） | 直接寫入 |
| 3 | 團隊共識（多人認同但無數據） | 標示為「暫定」 |
| 4 | 個人偏好（老闆喜歡、顧問建議） | **禁止進 Canon** |

固定收斂句：「這個說法目前缺乏案例支撐，我們先保留為假設，不寫進品牌正式表達。」

---

## 三個定位選項框架

每個選項包含：

```
【選項名稱：___】
定位宣言：___
品牌原型：___（主）+ ___（次）
市場品類：___
核心差異化：___
目標客群：___
視覺方向關鍵詞：___
語調特徵：___

甜頭：___（這個定位能帶來什麼）
代價：___（需要放棄什麼、承擔什麼風險）
適合的客戶狀態：___（什麼情況下選這個）
```

---

## 視覺規格建構規則

**色彩系統（依 brief.visual_experience 建構）**

從客戶資料萃取色彩方向，遵循以下原則：

| 考量維度 | 來源 |
|---------|------|
| 情感目標 | `desired_feeling_words` |
| 行業慣例（遵循或打破） | `industry_rules_we_reject` |
| 客戶偏好 | `visual_references_love` + `visual_references_hate` |
| 品牌原型色彩語言 | 框架二原型對應 |
| 目標市場文化色彩 | `new_market_plans` |

輸出格式：
```
主色：[名稱] [HEX] [用途] [情感意義]
輔色1：[名稱] [HEX] [用途]
輔色2：[名稱] [HEX] [用途]
中性色系：[最少 4 個]
禁止色：[具體說明為什麼禁止]
```

**字型系統**

三層結構（中文必須有配對方案）：
```
Display（標題層）：[英文字型] + [中文字型] — 用途 — 適用場景
Body（內文層）：[英文字型] + [中文字型] — 用途 — 適用場景
Accent（強調層）：[英文字型] — 用途（品牌關鍵詞/數字/標籤）
```

---

## 語言規格建構規則

**語調光譜（五軸定位）**

每個軸 0-100 分：
```
溫度軸：冰冷理性 ←─────●───→ 溫暖感性
嚴肅軸：嚴肅學術 ←───●─────→ 輕鬆口語
主動軸：被動回應 ←─────────●→ 主動引導
專業軸：大眾通俗 ←──────●──→ 專業術語
在地軸：國際語境 ←────●────→ 在地語境
```

每個軸的數值從 `brief.brand_purpose` + `brief.ideal_customer_profile` + `brief.visual_experience.desired_feeling_words` 推導。

---

## 護欄

**HG-BB-THREE-OPTIONS**：永遠提供三個定位選項（保守/平衡/進攻），不替客戶做最終選擇。

**HG-BB-EVIDENCE**：每個框架分析必須援引 `client_brand_brief` 的具體資料，不允許空口假設。

**HG-BB-NO-GENERIC**：禁止使用「品質卓越」「以客戶為中心」「創新」等無意義的通用語言。

**SG-BB-UNCERTAINTY**：若 brief 中有 `uncertainty_flag`，在對應框架中提供多個選項而非單一答案。

---

## DNA27 親和對照

| 屬性 | 值 |
|------|-----|
| 迴圈 | slow_loop（七框架分析需要充分深度）|
| 語調 | NEUTRAL + ANALYTICAL |
| 節奏 | MEDIUM |
| 主動性 | OFFER_OPTIONS（三個定位路徑）|
| 挑戰等級 | 2（在品牌定位上主動提出建議，但最終讓客戶選） |

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.0 | 2026-03-28 | 初版：七大框架 + brand_strategy_package 輸出結構 + 視覺/語言規格建構規則 |
