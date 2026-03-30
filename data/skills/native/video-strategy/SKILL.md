---
name: video-strategy
type: on-demand
layer: content
hub: business
io:
  inputs:
    - from: user
      field: topic_audience_goal_platform
      required: true
    - from: brand-builder
      field: brand_canon
      required: false
  outputs:
    - to: user
      field: video_inspirations_batch
      trigger: always
    - to: knowledge-lattice
      field: content_patterns
      trigger: on_successful_batch
connects_to:
  - brand-builder
  - brand-identity
  - c15
  - storytelling-engine
  - script-optimizer
  - text-alchemy
  - aesthetic-sense
memory:
  writes:
    - target: knowledge-lattice
      type: crystal
      condition: 產出高效內容模式時結晶化
  reads:
    - source: brand-builder
      field: brand_canon
    - source: knowledge-lattice
      field: past_video_patterns
description: >
  Video Strategy（短影音策略引擎）— DNA27 核心的外掛模組，
  短影音內容策略總監 + 腳本生成引擎。將品牌價值與模糊想法，
  轉為可拍、可上架、可轉化的短影音內容。
  核心能力：Precision Track 細分賽道鎖定 → 六維組合批量生成 20 條靈感
  （Default 商業引擎 + Forge 敘事引擎雙軌）→ #編號延伸 1min 腳本。
  內建品牌價值鎖定（topic = 品牌立場，不可覆寫）、
  受眾精準度檢查（場景不清先跑 /tracks）、
  安全詞替換（翻倍→提升、神器→工具）。
  觸發時機：(1) /video 或 /reels 指令強制啟動；
  (2) 自然語言偵測——使用者描述想拍短影片、規劃 Reels/TikTok/Shorts 內容、
  需要短影音腳本、想做內容矩陣時自動啟用。
  涵蓋觸發詞：短影音、Reels、TikTok、Shorts、影片腳本、內容矩陣、
  拍什麼、影片靈感、鉤子、開場、CTA、內容日曆、賽道、短影片、
  一分鐘腳本、vlog、how-to、教學影片。
  與 c15 互補：c15 管「語言張力」，video-strategy 的 Forge 引擎是 c15 核心公式
  （動機→阻力→選擇→代價→變化）在短影音場景的特化應用。
  與 script-optimizer 互補：script-optimizer 管「已有腳本的壓縮優化」，
  video-strategy 管「從零生成內容策略與腳本」。
  與 storytelling-engine 互補：storytelling-engine 管「長敘事結構」，
  video-strategy 管「15-60 秒的微敘事」。
  與 brand-builder 互補：消費 brand_canon 確保內容不偏離品牌定位。
  此 Skill 依賴 DNA27 核心，不可脫離 DNA27 獨立運作。
---

# Video Strategy：短影音策略引擎

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組（pluggable plus）。

**依賴**：`dna27` skill（母體 AI OS）

**本模組職責**：
- Precision Track 細分賽道鎖定（受眾不精準時先收斂）
- 六維組合批量靈感生成（20 條 / 批）
- Default 商業引擎（Focus × Intent × Clarity × Commercial）
- Forge 敘事引擎（動機→阻力→選擇→代價→變化，引用 C15 核心公式）
- #編號延伸 1min 腳本（Vlog / How-To / Explainer）
- 品牌價值鎖定與對齊回饋
- 安全詞替換與合規檢查

**本模組不做**：
- 不做品牌定位（交給 `brand-builder`）
- 不做已有腳本的時間壓縮（交給 `script-optimizer`）
- 不做長篇敘事結構設計（交給 `storytelling-engine`）
- 不做影片拍攝或剪輯（只到腳本層）

## 觸發與入口

**指令觸發**：
- `/video` 或 `/reels` — 啟動短影音策略引擎
- `/tracks` — 輸出細分賽道候選
- `/lock [賽道編號]` — 鎖定賽道，產出 20 條靈感
- `/unlock` — 解除賽道鎖定
- `/plan` — 7 天測試計畫
- `/forge-only` — 僅用 Forge 敘事引擎
- `/default-only` — 僅用 Default 商業引擎
- `#N` — 延伸第 N 條為 1min 腳本

## 護欄

### 硬閘

**HG-BRAND-LOCK**：topic 視為品牌價值，不可被覆寫。違反品牌立場的內容直接淘汰。

**HG-PRECISION-FIRST**：受眾不精準時，禁止直接產出靈感。必須先跑 `/tracks` 收斂。
精準度檢查：同時具備【職務/角色、階段、痛點、場景物件】任兩項 → 視為精準。

**HG-SAFETY**：
- 禁用詞自動替換：翻倍→提升、神器→工具、穩賺→穩健
- 禁止醫療/投資/違法內容
- 不收集不必要個資

### 軟閘

**SG-DEDUPE**：六維組合不可重複；相鄰主題必須 MECE。

**SG-FORGE-ARC**：Forge 引擎的每條靈感必須有完整五段弧線（動機→阻力→選擇→代價→變化），不可省略。

## Precision Track 引擎（細分賽道）

### 資訊不足時
只問一題：「先鎖：產業 / 階段 / 卡點？」

### 賽道候選規則
每個賽道必含：
- `who`：誰（具體到角色/職務）
- `stuck`：卡在哪
- `identity_line`：對號入座句（讓受眾覺得「在說我」）
- `shooting_elements`：可拍元素（場景/道具/動作）
- `axis_tag`：MECE 軸標籤（階段/產業/痛點/結果/心理/角色）

### MECE 護欄
axis_tag 不可集中於同一軸。再細一層時僅拆 3-5 個子賽道。

## 雙軌生成引擎

### Default 引擎（商業導向）
四維組合：Focus × Intent × Clarity × Commercial
- 每條含：鎖定句（target_lock_line）+ 關鍵字（targeting_keywords）
- 關鍵字規則：場景詞 +（身分詞或問題詞）
- B2B 特化：[職務]+[流程]+[風險]+[物件]

### Forge 引擎（敘事導向）
五段弧線：動機→阻力→選擇→代價→變化（= C15 核心公式）
- Forge 的「選擇」與「變化」必須強化品牌角色
- 每條必須有完整五段，不可省略

### 六維去重
品牌核心 × 相鄰主題 × 故事 × 鉤子 × 形式 × Precision Track
六維組合不可重複。

## 品牌價值對齊

### 每批輸出前必顯示
```
品牌價值對齊：
- 相信：{{brand_belief}}
- 反對：{{brand_antagonist}}
- 本批內容持續傳達：{{brand_positioning_sentence}}
```

### 品牌推導
若使用者未提供 brand_claim / brand_antagonist：
- brand_claim：由 topic 推導「你相信的是什麼」
- brand_antagonist：由 topic 推導「你反對的是什麼」

若有 brand_canon（來自 brand-builder）：直接引用，不推導。

## 腳本延伸

觸發：`#N`（N = 靈感編號）

輸出 1min 腳本，格式按影片類型：
- **Vlog**：開場鉤子 → 情境帶入 → 核心觀點 → CTA
- **How-To**：問題定義 → 步驟拆解 → 結果展示 → CTA
- **Explainer**：反常識開場 → 原理解釋 → 應用場景 → CTA

每個腳本同時產出 Default 版 + Forge 版。

## 7 天測試計畫

觸發：`/plan`

```
Day 1: [#N] — 測試鉤子類型 A
Day 2: [#M] — 測試受眾反應
Day 3: 回顧 Day 1-2 數據，調整
Day 4: [#K] — Forge 版測試
Day 5: [#J] — B2B 版測試
Day 6: 回顧 Day 4-5，鎖定最佳組合
Day 7: 最佳組合 × 3 變體衝量
```
