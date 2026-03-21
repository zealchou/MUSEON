---
name: workflow-svc-brand-marketing
type: workflow
layer: workflow
hub: workflow
stages:
  - id: 1
    name: "品牌健檢"
    skills: [ssa-consultant, business-12]
    lens: "SSA 顧問訪談 + 十二力快篩"
    mode: serial
    gate:
      - "客戶確認：對，這就是我的問題"
    output_to: [2]
  - id: 2
    name: "品牌定位"
    skills: [brand-identity, storytelling-engine, aesthetic-sense, consultant-communication]
    lens: "April Dunford 五要素 + 品牌金字塔 + StoryBrand"
    mode: serial
    gate:
      - "客戶確認：這就是我"
    output_to: [3, 4]
  - id: 3
    name: "行銷策略"
    skills: [business-12, xmodel, pdeif, consultant-communication]
    lens: "通路盤點 + PDEIF 逆推 + 90 天計畫"
    mode: serial
    gate:
      - "客戶確認行動計畫可執行"
    output_to: [4, 6]
  - id: 4
    name: "內容生產"
    skills: [text-alchemy, c15, storytelling-engine, brand-identity, aesthetic-sense]
    lens: "社群內容批次產出 + 品牌一致性校驗"
    mode: serial
    gate:
      - "品牌一致性審計通過"
      - "美感品質閘門通過"
    output_to: [5, 6]
  - id: 5
    name: "自動化規格"
    skills: [dse, pdeif, consultant-communication]
    lens: "Bot 對話流程 + 技術方案比較"
    mode: serial
    gate:
      - "客戶決定是否執行"
    output_to: [6]
    optional: true
    skip_when: "客戶不需要自動化工具"
  - id: 6
    name: "成效追蹤"
    skills: [eval-engine, business-12, wee]
    lens: "KPI 前後測 + WEE 結果萃取五問"
    mode: serial
    gate:
      - "至少 2 個指標有前後對比數據"
speed_paths:
  fast_loop:
    stages: [1, 6]
    depth: "精簡"
  exploration_loop:
    stages: [1, 2, 3, 4, 6]
    depth: "標準"
  slow_loop:
    stages: [1, 2, 3, 4, 5, 6]
    depth: "完整"
io:
  inputs:
    - from: user
      field: client_brief
      required: true
  outputs:
    - to: wee
      field: execution_trace
      trigger: always
    - to: user
      field: deliverables
      trigger: always
connects_to:
  - ssa-consultant
  - business-12
  - brand-identity
  - storytelling-engine
  - xmodel
  - pdeif
  - master-strategy
  - text-alchemy
  - c15
  - aesthetic-sense
  - consultant-communication
  - eval-engine
  - orchestrator
  - knowledge-lattice
memory:
  writes:
    - target: wee
      type: proficiency
      condition: 工作流完成時
description: >
  服務業品牌行銷顧問工作流（WF-SVC-01）— MUSEON 第一條預設工作流範本。
  適用客戶：美業/餐飲/咖啡/零售，已經營一段時間但品牌模糊、行銷社群做不起來。
  起始狀態：有品牌但說不清自己是誰。
  服務週期：短期 2-4 週交付，可延伸為 1-3 月陪跑。
  核心交付物：行銷策略企劃書、品牌定位文件、社群內容範本、自動化工具規格書。
  涉及 Skill：14 個（ssa-consultant、business-12、brand-identity、storytelling-engine、
  xmodel、pdeif、master-strategy、text-alchemy、c15、aesthetic-sense、
  dse、consultant-communication、eval-engine、wee）。
  觸發時機：(1) /workflow svc 指令強制啟動；
  (2) orchestrator 偵測到品牌/行銷/社群類需求且客戶為服務業時自動建議。
  涵蓋觸發詞：品牌顧問、行銷策略、社群經營、品牌定位、服務業、美業、餐飲、
  咖啡廳、零售、IG經營、LINE經營、內容行銷、品牌模糊、不知道怎麼發文。
  使用情境：(A) Zeal 服務客戶時，按工作流跑完整顧問流程；
  (B) 教練模式——引導學員用此流程服務他的客戶。
  此工作流依賴 orchestrator 做階段編排，依賴 dna27 做迴圈路由與護欄判斷。
  與 orchestrator 互補：orchestrator 管 Skill 間編排，本工作流定義「什麼順序、什麼輸入輸出」。
  與 wee 互補：wee 追蹤本工作流的生命週期演化，記錄每輪執行的效率與卡點。
  與 ssa-consultant 互補：Stage 1 直接調用 SSA 顧問訪談 12 步驟。
  與 brand-identity 互補：Stage 2 直接調用 April Dunford 五要素 + 品牌金字塔。
  與 eval-engine 互補：Stage 6 調用客戶成效追蹤與 A/B 比對。
---

# WF-SVC-01：服務業品牌行銷顧問工作流

> **客戶畫像**：美業/餐飲/咖啡/零售老闆。做了一陣子，有客人但說不清自己的品牌是什麼。
> IG 有在發但沒策略，偶爾爆一篇但不知道為什麼。想做 LineBot 但不知道從哪開始。
> 最在意的是「拿到手」的東西——不只是診斷報告，是可以直接用的策略和內容。

---

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組（pluggable plus），屬於「工作流範本」類型。

**依賴**：
- `dna27` skill（母體 AI OS，提供 Kernel 護欄、迴圈路由、模式切換）
- `orchestrator` skill（多 Skill 協作編排，管理 Stage 間轉換與資訊傳遞）

**本模組職責**：
- 定義服務業品牌行銷顧問的完整 6 階段流程
- 規定每個 Stage 調用哪些 Skill、執行什麼步驟、產出什麼交付物
- 定義 Stage 之間的閘門檢查與分支邏輯
- 規定 Skill 間的資訊傳遞規則（A 的輸出 = B 的輸入）

**本模組不做**：
- 不替代任何被調用的 Skill 的內部邏輯（SSA 怎麼做訪談是 SSA 自己的事）
- 不做非服務業的產業診斷（製造業、科技業另有工作流）
- 不替客戶做最終品牌或策略決策
- 不直接執行內容生產——調用 text-alchemy 生態系執行
- 不處理技術實作（Bot 開發、網站設計）——只產出規格書

**與其他外掛的關係**：
- orchestrator = 編排引擎（管「怎麼串」）
- 本工作流 = 流程範本（管「串什麼順序、傳什麼資訊」）
- wee = 工作流生命週期追蹤（管「跑完之後怎麼進化」）
- 被調用的 14 個 Skill 各自保有內部邏輯和護欄

---

## 觸發與入口

**指令觸發**：
- `/workflow svc` — 啟動服務業品牌行銷顧問流程（顧問模式）
- `/workflow svc coach` — 教練模式（引導學員用此流程服務他的客戶）
- `/workflow svc status` — 查看目前在哪個 Stage

**自然語言自動偵測**：
偵測到以下訊號且客戶為服務業時，主動建議啟用：
- 品牌模糊、說不清自己是誰
- 行銷/社群不知道怎麼做
- IG/LINE 經營沒策略
- 美業/餐飲/咖啡/零售的經營問題
- 「幫我從品牌到行銷一次搞定」

**啟動前置檢查**（由 DNA27 核心路由）：
- 確認客戶屬於服務業範疇（美業/餐飲/咖啡/零售/類似）
- 確認客戶的起始狀態（有品牌但模糊 vs 完全從零 vs 已有定位只缺行銷）
- 如果完全從零 → 建議先走品牌建構專案，再接入本工作流
- 如果已有定位只缺行銷 → 可從 Stage 3 直接開始

---

## 核心工作流程

```
Stage 1        Stage 2        Stage 3        Stage 4        Stage 5        Stage 6
品牌健檢   →   品牌定位   →   行銷策略   →   內容生產   →   自動化規格  →  成效追蹤
(第1次)        (第2-3次)      (第3-4次)      (第4-6次)      (選配)         (持續)
   │              │              │              │              │              │
   ▼              ▼              ▼              ▼              ▼              ▼
 健檢報告     定位文件       策略企劃書     社群內容包     規格書        成效報告
                                                                          │
                                                              ↻ 回到 Stage 3-4
```

**分支規則**：
- Stage 2 猶豫不決 → dharma 介入決策困境引導
- Stage 3 預算有限 → xmodel 槓桿推演最小資源路徑
- Stage 4 需持續 → 進入陪跑模式（每週/雙週批次）
- Stage 5 是選配 → 依客戶需求決定
- Stage 6 效果不佳 → xmodel 破框推演新路徑

---

### Stage 1：品牌健檢

**目的**：搞清楚客戶現在到底卡在哪裡
**時間**：第 1 次對談
**主導 Skill**：ssa-consultant（顧問模式）、business-12

**1-1 情境收集（SSA Step 1）**

啟動 ssa-consultant 顧問模式。收集最小必要資訊：
- 行業、規模、經營多久了
- 目前最急迫的卡點是什麼
- 已經嘗試過什麼、結果如何

DNA27 路由判斷：
- 如果客戶很急（例：下週要開幕）→ fast_loop，只給最小下一步
- 如果客戶「不確定問題在哪」→ exploration_loop，先收集訊號
- 如果客戶有餘裕想好好梳理 → slow_loop，完整診斷

**1-2 染色體匹配（SSA Step 2）**

根據情境匹配 SSA 染色體。服務業品牌模糊的客戶，高頻命中的染色體：
- SSA08（五感識別）：品牌的視覺/聽覺/觸覺/嗅覺/味覺一致性
- SSA05（口碑驗證）：客人為什麼來？口碑傳播路徑是什麼？
- SSA14（鐵粉裂變）：有沒有鐵粉？鐵粉怎麼來的？
- SSA19（目標落差）：現況 vs 理想的具體落差

**1-3 十二力快篩（business-12）**

啟動 business-12 做快速掃描，聚焦五個與服務業品牌行銷最相關的力：
- 品牌力：客戶能不能一句話說清楚自己
- 社群力：線上觸及 + 互動 + 導流的能力
- 轉換力：從「看到」到「買單」的轉換效率
- 感受管理力：客戶體驗的五感一致性
- 產品力：核心產品/服務的差異化程度

找出最弱的 2-3 力，作為後續聚焦點。

**1-4 落差萃取（SSA Step 4-6）**

SSA 12 步驟的「找到痛點→追問擊穿→共情同理」：
- 表面痛點：「IG 沒人看」「不知道發什麼」
- 追問擊穿（SSA02 偽裝需求偵測）：「你覺得沒人看的原因是什麼？」
- 真實痛點萃取：往往不是「不會發 IG」而是「不知道自己的品牌到底是什麼」

**輸出交付物**：品牌健檢報告（1 頁摘要）——狀態讀取 + 卡點定位 + 落差地圖 + 建議方向

**閘門檢查**：客戶確認「對，這就是我的問題」→ 進入 Stage 2。

---

### Stage 2：品牌定位

**目的**：幫客戶說清楚「我是誰、跟別人哪裡不一樣」
**時間**：第 2-3 次對談
**主導 Skill**：brand-identity（品牌生成模式）、storytelling-engine（故事建構模式）

**2-1 競爭替代分析（April Dunford 第 1 要素）**

啟動 brand-identity 品牌生成模式：
- 如果你的店不存在，客人會去哪裡？
- 附近的同類型店是誰？他們的特色是什麼？
- 客人在「你」和「他們」之間怎麼選的？

**2-2 差異化能力萃取（April Dunford 第 2 要素）**

- 你有什麼是他們都沒有的？
- 不接受「我比較用心」——那不是差異化，那是基本功
- 具體的、客人能感知到的差異：技術？原料？空間？服務流程？人？

**2-3 獨特價值定義（April Dunford 第 3 要素）**

- 那個差異化，對客人來說到底有什麼好處？
- 從功能價值（做得好）→ 情感價值（感覺好）→ 社會價值（分享給別人好看）

**2-4 目標客群聚焦（April Dunford 第 4 要素）**

- 誰最在意你的差異化？
- 具體的人物畫像：年齡、職業、生活型態、在哪裡滑手機、什麼時候會想到你

**2-5 品牌人格定義（品牌金字塔）**

用 brand-identity 的品牌金字塔五層結構：
- Product Attributes → Functional Benefits → Emotional Benefits → Brand Personality → Brand Essence
- 落地問法：「如果你的品牌是一個人，他/她是什麼個性？說話方式？穿著風格？」

**2-6 品牌語調定義（語調光譜）**

用 brand-identity 的語調座標軸設定：
- 溫度軸（冰冷理性 ↔ 溫暖感性）
- 嚴肅軸（嚴肅學術 ↔ 輕鬆口語）
- 專業軸（大眾通俗 ↔ 內行術語）
- 主動軸（被動回應 ↔ 主動引導）
- 產出具體用語規範：「我們說___，不說___」

**2-7 品牌故事設計（StoryBrand 框架）**

啟動 storytelling-engine 故事建構模式：
- 英雄（客人）有一個問題 → 遇到引導者（你）→ 引導者給了一個計畫 → 呼喚行動 → 避免了失敗 → 獲得了成功
- 產出 3 個版本：30 秒版（電梯簡報）、3 分鐘版（官網首頁）、完整版（品牌手冊）

**2-8 一句話定位**

所有元素收斂成一句：
「我們是 [品類]，幫助 [目標客群] 解決 [核心問題]，跟 [競爭者] 不一樣的是 [差異化]。」

**輸出交付物**：品牌定位文件——競爭分析摘要 + 定位宣言 + 品牌人格卡 + 品牌故事（3 版本）+ 視覺方向建議

用 aesthetic-sense 做最後品質審計。用 consultant-communication 的 SCQA 框架組織文件結構。

**閘門檢查**：客戶確認「這就是我」→ 進入 Stage 3。猶豫 → dharma 介入。

---

### Stage 3：行銷策略

**目的**：知道自己是誰之後，規劃怎麼讓別人也知道
**時間**：第 3-4 次對談
**主導 Skill**：business-12（社群力/轉換力深度展開）、xmodel、pdeif

**3-1 通路盤點與優先排序**

business-12 的社群力 + 轉換力深度展開：
- 現有通路清單：IG、LINE OA、Google 商家、口碑、路過、外送平台、轉介紹⋯⋯
- 每個通路的現況：有在做嗎？效果如何？花多少時間？
- 用 xmodel 的 8 槓桿維度掃描：哪個通路「投入最少但撬動最大」？

**3-2 內容策略矩陣**

跨 xmodel + business-12 設計：
- 內容類型：教育型 / 娛樂型 / 促銷型 / 幕後型 / 客戶見證型
- 發佈節奏：每週幾篇？哪幾天？什麼時段？
- 平台適配：IG 重視覺、LINE 重實用、Google 重 SEO
- 內容比例建議：例如教育 40% / 幕後 25% / 促銷 15% / 客戶見證 20%

**3-3 轉換路徑設計（PDEIF 逆推）**

啟動 pdeif 從「客人回購 + 推薦」的終點往回推：
- 終點狀態定義：回購率 X% + 每月 Y 則口碑推薦
- MECE 拆解：推薦 ← 滿意 ← 體驗 ← 到店 ← 預約 ← 信任 ← 認識
- 每一步的轉換率假設 + 可操作的提升手段
- 失效包絡：如果某一步轉換率低於 X%，回退到什麼策略

**3-4 90 天行動計畫（PDEIF 產出）**

用 pdeif 的四步流程產出可執行計畫：
- 月 1（基礎建設）：品牌識別統一 + 內容模板建立 + 第一批內容上線
- 月 2（穩定輸出）：固定節奏發文 + 開始投廣/合作 + 數據追蹤啟動
- 月 3（優化迭代）：根據數據調整 + 嘗試新格式 + 成效評估
- 每月 KPI：追蹤人數、互動率、私訊數、預約量、營收

如果客戶預算有限 → xmodel 做 Manifest 推演：M3 槓桿掃描找最小資源路徑。

**輸出交付物**：行銷策略企劃書——目標客群畫像 + 通路優先矩陣 + 內容策略矩陣 + 轉換漏斗 + 90 天行動計畫

用 consultant-communication 的金字塔原則組織：結論先行 → 支撐論點 → 執行細節。

**閘門檢查**：客戶確認行動計畫可執行 → 進入 Stage 4。做不到 → pdeif 重新拆解為更小步驟。

---

### Stage 4：內容生產

**目的**：不只是規劃，直接做出可以發的東西
**時間**：第 4-6 次對談（可持續為陪跑模式）
**主導 Skill**：text-alchemy → c15 + storytelling-engine + brand-identity + aesthetic-sense

**4-1 社群貼文批次產出**

啟動 text-alchemy，路由到行銷文案模式：
- 根據 Stage 3 的內容日曆逐篇產出
- 每篇包含：文案正文 + hashtag 建議 + 圖片方向描述
- text-alchemy 自動調用 c15 注入敘事張力（開頭 hook、情感節奏、CTA）
- 首批產出 4-8 篇作為範本

**4-2 品牌一致性校驗**

啟動 brand-identity 品牌審計模式：
- 語調是否符合 Stage 2 定義的光譜？
- 用語規範檢查：有沒有用到「禁止用語」？
- 視覺方向是否一致？

**4-3 短影片腳本**

啟動 storytelling-engine：
- Reels / TikTok 腳本模板：0-3 秒 Hook → 3-15 秒內容 → 15-30 秒 CTA
- 含分鏡建議（鏡位、畫面元素、字卡文字）
- 產出 2-4 支腳本

**4-4 美感品質閘門**

啟動 aesthetic-sense 做最終審計：
- 整體節奏：9 宮格排列是否有呼吸？
- 單篇質感：留白、字數、情緒強度是否恰當？
- 一致性：所有內容是否看起來「像同一個品牌在說話」？

**輸出交付物**：社群內容包——IG/FB 貼文 4-8 篇 + 短影片腳本 2-4 支 + 內容日曆

**閘門檢查**：客戶確認品質 → 發布。想持續 → 陪跑模式。需要自動化 → Stage 5。到此為止 → 跳到 Stage 6。

---

### Stage 5：自動化規格（選配）

**目的**：把重複的客服/預約/問答交給系統
**時間**：第 5-7 次對談（依客戶需求）
**主導 Skill**：dse、pdeif、consultant-communication

**5-1 自動化需求盤點**

用 pdeif 的終點先行原則：
- 客人最常問什麼？（TOP 10 問題）
- 哪些問題每天重複回答？
- 預約流程目前怎麼走？哪一步最花時間？

**5-2 Bot 對話流程設計**

用 dse 的技術方案設計：
- 對話入口：掃 QR Code / 加好友 / IG 私訊 / 官網
- 分流邏輯：問答 / 預約 / 查詢 / 客訴 / 轉人工
- 每條路徑的對話腳本 + 觸發條件 + 回退機制

**5-3 技術方案與工具建議**

dse 的 SOTA 比對：
- LINE Bot 方案比較（LINE OA + Messaging API vs 第三方平台）
- IG Bot 方案比較（ManyChat vs Chatfuel vs 自建）
- 預約系統方案比較
- 每個方案的優缺點 + 適用規模 + 概略費用

**5-4 規格書撰寫**

用 consultant-communication 的金字塔原則：
- 功能需求清單（MUST / SHOULD / NICE-TO-HAVE）
- 對話流程圖
- 串接需求
- 報價範圍建議

**輸出交付物**：自動化工具規格書——可直接交給工程師或外包執行

**閘門檢查**：客戶決定是否執行。不論是否執行 → 進入 Stage 6。

---

### Stage 6：成效追蹤

**目的**：確認前面做的東西到底有沒有用
**時間**：持續（月度/季度）
**主導 Skill**：eval-engine、business-12、wee

**6-1 KPI 基準線建立**

啟動 eval-engine：導入前快照——IG 追蹤人數、月互動率、月私訊量、月預約/進店量、月營收

**6-2 月度複盤（WEE 結果萃取五問）**

啟動 wee 的 /review 模式：效果好的 / 沒人看的 / 流失最多的步驟 / 學到什麼 / 下個月調整什麼

**6-3 策略微調**

根據數據調整 Stage 3 策略：business-12 重檢弱項 + 內容比例重配 + 通路權重調整

**6-4 成效報告產出**

eval-engine 的 A/B 比對：導入前 vs 導入後的 KPI 變化 + 量化成效

**輸出交付物**：月度/季度成效報告——KPI 儀表板 + 最佳實踐 + 下期建議

**迴圈規則**：效果好 → 複製為案例範本；效果不佳 → xmodel 破框；持續 → 回到 Stage 3-4 微調

---

## 護欄

### 硬閘

**HG-WF-SVC-NO-MANIPULATE**：不操控客戶的品牌決策。所有定位建議呈現選項 + 代價，讓客戶自己選。繼承 SSA 硬閘 HG-SSA-MANIPULATION。

**HG-WF-SVC-NO-IRREVERSIBLE**：不推動客戶做不可逆的高成本行動（例：在品牌定位還沒確認前就投大量廣告預算）。繼承 xmodel 硬閘 HG-IRREVERSIBLE。

**HG-WF-SVC-NO-SKIP-GATE**：不跳過 Stage 之間的閘門檢查。客戶沒有確認「對，這就是我的問題」之前，不得進入下一個 Stage。

**HG-WF-SVC-OVERWORK**：客戶明顯處於過勞/低能量狀態時，不做高強度策略推演。先降級到 fast_loop 給最小下一步。繼承 SSA 硬閘 HG-SSA-OVERWORK。

### 軟閘

**SG-WF-SVC-SCOPE**：客戶需求超出本工作流範圍（例：要做 App 開發、要做財務規劃）時，建議啟用對應的其他 Skill，不勉強用本工作流處理。

**SG-WF-SVC-PACE**：不要一次給太多。每次對談聚焦 1 個 Stage，不要同時跑 2 個以上的 Stage。

**SG-WF-SVC-BUDGET**：客戶預算有限時，自動觸發 xmodel 槓桿推演，找最小資源路徑，不要推高成本方案。

---

## 適應性深度控制

| DNA27 迴圈 | 工作流深度 | 適用情境 |
|---|---|---|
| fast_loop | 精簡版：Stage 1 快篩（跳過染色體匹配）→ 直接給 3 個最緊急的行動建議 | 客戶很急（下週開幕、被競品打到）|
| exploration_loop | 標準版：Stage 1-4 完整走，Stage 5 依需求，Stage 6 基礎追蹤 | 多數客戶的正常流程 |
| slow_loop | 深度版：全 6 Stage + 每 Stage 輸出完整文件 + 品質審計 + WEE 追蹤 | 高預算客戶 / 政府補助案 / 長期陪跑 |

---

## 系統指令

| 指令 | 效果 |
|---|---|
| `/workflow svc` | 啟動服務業品牌行銷顧問流程（顧問模式） |
| `/workflow svc coach` | 教練模式（引導學員用此流程服務客戶） |
| `/workflow svc status` | 查看目前在哪個 Stage + 已完成的交付物清單 |
| `/workflow svc skip [stage]` | 跳過指定 Stage（僅限 Stage 5，其他 Stage 需說明理由） |
| `/workflow svc back [stage]` | 回到指定 Stage 重做（例：品牌定位需要調整） |

---

## DNA27 親和對照

**Persona 旋鈕建議設定**（按 Stage 動態切換）：

| Stage | tone | pace | initiative | challenge_level |
|---|---|---|---|---|
| 1-2（診斷/定位） | WARM | SLOW | ASK | 1 |
| 3（策略規劃） | NEUTRAL | MEDIUM | OFFER_OPTIONS | 2 |
| 4（內容生產） | WARM | MEDIUM | MIRROR | 0 |
| 5（技術規格） | NEUTRAL | FAST | OFFER_OPTIONS | 1 |
| 6（成效追蹤） | NEUTRAL | FAST | OFFER_OPTIONS | 1 |

**偏好觸發的反射叢集**：RC-C3（結構化思考）、RC-D1（外部工具優先）、RC-E1（慢層啟動）、RC-B6（代價標籤）
**限制使用的反射叢集**：RC-B1（避免替客戶做最終選擇）
**禁止觸發時啟動的反射叢集**：RC-A3（不可逆情境——先處理安全）

**跨 Skill 協同**：
- Stage 1 結束後，ssa-consultant 的診斷輸出傳遞給 brand-identity 作為 Stage 2 輸入
- Stage 2 結束後，brand-identity 的定位文件傳遞給 business-12 和 text-alchemy 作為 Stage 3-4 輸入
- Stage 3 的行動計畫傳遞給 eval-engine 作為 Stage 6 的 KPI 基準設定依據
- orchestrator 負責確保以上資訊傳遞不遺失

**WEE 工作流追蹤**：
- 本工作流由 wee 追蹤生命週期
- 每次跑完一輪（Stage 1-6），wee 記錄：花了多久、哪個 Stage 最耗時、客戶在哪裡卡住
- 跑完 3-5 輪後，wee 的四維熟練度追蹤會顯示優化建議
- morphenix 可基於 wee 數據提出工作流迭代提案

---

## 邊界宣告

**什麼情況下本工作流會失效**：
- 客戶的問題根本不是品牌/行銷，而是產品本身有嚴重缺陷（品牌再好也救不了爛產品）
- 客戶完全沒有執行能力（沒人、沒時間、沒預算去落地任何策略）
- 客戶不是服務業（製造業的行銷邏輯差異太大，需要另一條工作流）

**什麼問題不該用本工作流處理**：
- 財務危機（用 finance-coach 或直接找會計師）
- 人事糾紛（用 talent-engine 或直接找勞務律師）
- 技術開發（本工作流只產出規格書，不做開發）
- 個人心理困境（用 dharma / resonance）

**使用者最容易犯的錯**：
- 跳過 Stage 1-2 直接要內容——沒有定位的內容是沒有靈魂的
- 每個 Stage 都想一次做完——應該尊重閘門，一步一確認
- 把「視覺方向建議」當成「設計稿」——本工作流不產出設計稿，只產出設計師能執行的方向

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|---|---|---|
| v1.0 | 2026-02-21 | 初版：6 Stage 工作流設計 |
| v1.1 | 2026-02-21 | 補齊 DNA27 合規結構：外掛合約、觸發與入口、護欄、適應性深度、系統指令、親和對照、邊界宣告 |
