---
name: landing-page-forge
description: >
  Landing-Page-Forge（一頁式銷售頁鍛造引擎）— DNA27 核心的外掛模組，
  將商品/課程/服務的模糊訴求，鍛造成「五段 Pipeline × 十大說服區段」
  的高轉化一頁式銷售頁。不是文案生成器——是「轉化率思維→敘事架構→
  說服文案→CRO 稽核→HTML 輸出」的完整產線。
  核心差異化：(1) 診斷先行——先搞清楚「轉化誰、從哪裡到哪裡」再動筆；
  (2) CRO Gate 強制通過——Hormozi Value Equation + Cialdini 六力稽核，
  不只是寫得好，而是說服得動。
  融合 StoryBrand（顧客=英雄）、Hormozi Value Equation、
  Hook-Story-Offer、Before-After-Bridge、Cialdini 六力。
  觸發時機：(1) 使用者輸入 /landing 或 /lpf 強制啟動；
  (2) 自然語言偵測——使用者說「幫我做銷售頁」「一頁式網站」
  「課程報名頁」「產品介紹頁」「我要賣 X，幫我寫文案」時自動啟用。
  涵蓋觸發詞：銷售頁、報名頁、一頁式、landing page、轉化率、
  文案、說服、課程介紹、服務介紹、推廣頁、銷售文案、CTA、報名。
  與 ssa-consultant 互補：ssa-consultant 做銷售對話，landing-page-forge
  做文字轉化；與 brand-builder 互補：brand-builder 定位品牌，
  landing-page-forge 把品牌定位轉化為說服力。
type: on-demand
hub: business
io:
  inputs:
    - from: user
      field: product_description
      required: true
    - from: brand-builder
      field: brand_positioning
      required: false
    - from: ssa-consultant
      field: customer_pain_analysis
      required: false
  outputs:
    - to: user
      field: landing_page_html
      trigger: always
    - to: knowledge-lattice
      field: conversion_pattern
      trigger: conditional
connects_to:
  - c15
  - text-alchemy
  - aesthetic-sense
  - storytelling-engine
  - consultant-communication
  - brand-builder
  - ssa-consultant
memory:
  writes:
    - knowledge-lattice
  reads:
    - user-model
    - knowledge-lattice
---

# Landing-Page-Forge：一頁式銷售頁鍛造引擎

> **你的產品值得一個說服得動人的呈現方式。**

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組（pluggable plus）。

**依賴**：`dna27` skill（母體 AI OS）

**本模組職責**：
- 診斷轉化目標（誰 → 從哪裡 → 到哪裡）
- 設計敘事架構（以 StoryBrand 為骨幹）
- 生成十大說服區段文案（c15 注入張力）
- 執行 CRO Gate（Hormozi + Cialdini 稽核）
- 輸出可上線 HTML（符合 MUSEON 品牌規範）

**本模組不做**：
- 不做品牌定位（那是 brand-builder 的工作）
- 不做廣告投放策略（那是 ad-pilot 的工作）
- 不做銷售對話腳本（那是 ssa-consultant 的工作）
- 不做多頁官網（只做單頁高轉化）

---

## 觸發與入口

**指令觸發**：
- `/landing` — 啟動完整五段 Pipeline
- `/lpf` — 別名
- `/lpf quick` — 快速模式（跳過問答，從描述推斷）
- `/lpf audit` — 只做 CRO Gate 稽核（診斷現有頁面）

**自然語言偵測**：
- 使用者說「幫我做銷售頁」「課程報名頁」「我要推廣 X」
- 使用者貼上現有頁面說「幫我改這個讓轉化率更好」

---

## 核心：五段 Pipeline

```
Phase 1: 診斷收口
    ↓ 買家畫像 + Before 狀態
Phase 2: 敘事架構設計
    ↓ 頁面敘事地圖（10 區段 × 目的 × 情緒目標）
Phase 3: 區段文案生成（呼叫 c15）
    ↓ 完整文案初稿
Phase 4: CRO Gate（轉化率稽核）
    ↓ 稽核報告 + 修正
Phase 5: HTML 輸出（讀 design_spec.md + aesthetic-sense）
    ↓ 可上線 HTML
```

---

## Phase 1：診斷收口

### 目標
搞清楚「這頁要轉化誰、從什麼狀態、到什麼狀態」。
不同的起點終點有不同的敘事邏輯——跳過這步就是在沒有地圖的情況下寫文案。

### 診斷四問

**Q1：這是賣給誰的？**（具體描述目標買家，不是「所有人」）

**Q2：他現在最痛的事是什麼（Before 狀態）？**
（不是「不開心」——是什麼具體情境讓他搜尋到這頁？他嘗試過哪些解法、為什麼都沒用？）

**Q3：他買了之後最渴望的狀態是什麼（After 狀態）？**
（不是功能清單——是生活/工作/感受上的具體改變）

**Q4：他最大的懷疑是什麼？**
（為什麼他看了這頁還是不買？他心裡最大的「但是⋯⋯」是什麼？）

### 輸出：買家畫像卡

```
買家畫像：___________
Before 狀態：___________ （要讓他說「對！就是這樣」）
After 狀態：___________  （要讓他說「我想去那裡」）
主要懷疑：___________    （FAQ 和風險逆轉要正面應對）
轉化前提：___________    （讀者需要先相信什麼，才可能轉化）
```

---

## Phase 2：敘事架構設計

### 框架：StoryBrand + Hormozi 四象限

**StoryBrand 角色分配**（每頁必須確認）：
- 英雄 = 你的買家
- 嚮導 = 你（講師/創辦人/服務提供者）
- 工具 = 你的課程/產品/服務
- 問題 = Before 狀態的根因
- 計畫 = 機制說明（為什麼這條路有效）
- 行動呼籲 = 報名/購買/諮詢

**Hormozi Value Equation**：
```
說服力 = (夢想結果 × 實現可能性) ÷ (等待時間 × 付出代價)
```
每個區段都在調整這四個變數之一——若都沒有調整，這段文案是浪費空間。

### 十大區段敘事地圖

| # | 區段 | 說服目的 | 目標情緒 | Hormozi 變數 |
|---|------|----------|----------|-------------|
| 1 | **Hero Hook** | 抓注意力、確認「這是給你的嗎？」 | 好奇 + 共鳴 | 夢想結果↑ |
| 2 | **大環境脈絡** | 讓問題顯得緊迫 | 緊迫感 | 等待時間風險↑ |
| 3 | **痛點共鳴 Before** | 讓讀者感到「對，就是這樣！」 | 被理解感 | 情感錨點 |
| 4 | **問題根因揭露** | 建立認知優勢，讓你成為可信嚮導 | 恍然大悟 | 實現可能性↑ |
| 5 | **轉化願景 After** | 讓讀者看見可能性 | 希望 + 渴望 | 夢想結果↑↑ |
| 6 | **Bridge + 機制說明** | 為什麼這條路有效（不是魔法） | 信任 | 實現可能性↑ |
| 7 | **講師信任建立** | 讓嚮導形象成立 | 安全感 | 實現可能性↑ |
| 8 | **Social Proof** | 同類人的驗證 | 「他們做到，我也可以」 | 實現可能性↑↑ |
| 9 | **Value Stack + Offer** | 讓「值得」感遠超過「價格」感 | 物超所值 | 付出代價↓ |
| 10 | **FAQ + CTA + 風險逆轉** | 清除最後障礙 | 安心 + 行動 | 付出代價↓↓ |

---

## Phase 3：區段文案生成

### 執行規則

1. **逐區段生成**，不跳過任何區段
2. **c15 注入張力**：每段有「懸念 → 釋放」節奏，不是條列式資訊堆疊
3. **BAB 結構貫穿**：Before 痛點開頭 → After 願景收尾，Bridge 連接
4. **白話優先**：讀者是企業主，不是你的同業，避免行話

### 各區段寫作規格

**區段 1：Hero Hook**
```
結構：標題（10-20 字）+ 副標（1-2 句）+ 確認對象（1 句）
禁止：寫功能、寫「歡迎來到」、寫公司名開頭
要有：一個讓目標買家說「這在說我」的痛點或渴望
```

**區段 2：大環境脈絡**
```
結構：外部趨勢（2-3 句）→ 這對你意味著什麼（1-2 句）→ 不改變的代價（1 句）
要有：讀者聽完說「對，我感受到這個壓力」
```

**區段 3：痛點共鳴**
```
結構：具體情境（「你是不是有過...」）+ 嘗試過的失敗解法（「你可能試過...但...」）
     + 情緒確認（「這讓你覺得...對吧」）
禁止：說教、給答案（此區段只共鳴，不解決）
要有：至少 3 個具體痛點，每個都有畫面感
```

**區段 4：問題根因揭露**
```
結構：「其實，真正的問題是...」+ 根因說明 + 「這就是為什麼 [常見解法] 效果有限」
要有：讀者看完說「原來如此，我之前想錯了」
```

**區段 5：轉化願景**
```
結構：「想像一下，如果...」+ 具體的 After 生活畫面 + 情感層面的改變
禁止：說「你會很開心」（太空泛）
要有：具體畫面，讓讀者有代入感
```

**區段 6：Bridge + 機制說明**
```
結構：「有一條可以走的路」+ 機制說明（不是魔法，是步驟）+ 「為什麼這個方式有效」
要有：可複製性（讀者相信這對他也 work）
```

**區段 7：講師信任建立**
```
結構：故事（不是履歷）+ 相關戰績（含數字）+ 為什麼在乎這件事
禁止：堆頭銜、只說學歷
要有：「他走過這條路，他理解你的處境」的感受
```

**區段 8：Social Proof**
```
結構：見證引言（真實、有具體細節）+ 數字規模 + 對象標籤
禁止：「很棒」「很有幫助」等模糊見證
要有：至少一個有具體成果數字的見證
```

**區段 9：Value Stack + Offer**
```
結構：你得到什麼（項目清單 + 各自價值）+ 總價值 vs 售價對比
要有：讓「值得」感遠超過「價格」感，把模組數翻譯成對買家的意義
```

**區段 10：FAQ + CTA + 風險逆轉**
```
結構：3-5 個真實顧慮 Q&A + 主要 CTA 按鈕 + 退款/保證條款
禁止：FAQ 寫假問題
要有：應對「主要懷疑」（Phase 1 診斷出來的那個）
```

---

## Phase 4：CRO Gate（轉化率稽核）

### G1：Cialdini 六力覆蓋率

| 影響力 | 頁面哪裡覆蓋 | 強度 1-3 |
|--------|-------------|---------|
| Social Proof 社會認同 | | |
| Authority 權威 | | |
| Scarcity 稀缺 | | |
| Reciprocity 互惠 | | |
| Liking 好感 | | |
| Commitment 承諾 | | |

**合格標準**：至少 5 個覆蓋，每個強度至少 1。

### G2：CTA 路徑（五點）

- [ ] Hero Hook 就出現過一次 CTA
- [ ] Social Proof 後再次出現 CTA
- [ ] 頁尾強力 CTA
- [ ] 按鈕文字是動詞
- [ ] 按鈕說清楚點了之後會發生什麼

### G3：主要反對意見覆蓋

- [ ] FAQ 直接回答（Phase 1 的主要懷疑）
- [ ] Social Proof 間接化解
- [ ] 風險逆轉降低代價感

### G4：Hormozi 四象限掃描

| 變數 | 有調整？ | 夠強？ |
|------|---------|-------|
| 夢想結果↑ | | |
| 實現可能性↑ | | |
| 等待時間↓ | | |
| 付出代價↓ | | |

**合格標準**：四個變數全部有調整，至少兩個「夠強」。

### 稽核評分

```
Cialdini 六力：___/6
CTA 路徑：___/5
反對意見覆蓋：___/3
Hormozi 四象限：___/4
總分：___/18
```

判定：15-18 ✅ → Phase 5 | 11-14 ⚠️ → 修復後 Phase 5 | ≤10 ❌ → 回 Phase 3

---

## Phase 5：HTML 輸出

### 執行規則

1. 讀取 `~/MUSEON/data/_system/brand/design_spec.md`
2. 套用 MUSEON 設計語言：暖色調（Ember #C4502A）、Cormorant Garamond 標題
3. aesthetic-sense 稽核後輸出
4. 必須支援手機版 RWD

### HTML 必備 CSS 組件

```
.hero-section / .context-cards / .pain-points / .mechanism-visual
.instructor-bio / .credentials-grid / .testimonials / .value-stack-table
.cta-section / .faq-accordion
```

### 輸出路徑規則

- 原始檔：`~/MUSEON/data/workspace/`
- 備份：`~/MUSEON/docs/reports/`
- 檔名：`lpf-[主題]-[YYYYMMDD].html`（全小寫橫線分隔，**嚴禁底線**）

---

## 護欄

### 硬閘

**HG-LPF-DIAGNOSIS-FIRST**：Phase 1 四問未完成不得推進至 Phase 2。
例外：`/lpf quick` 模式——從描述推斷，明確標示「推斷值，建議確認」。

**HG-LPF-CRO-GATE**：Phase 4 稽核低於 11 分不得輸出 HTML。

**HG-LPF-FILENAME-NO-UNDERSCORE**：檔名嚴禁底線（Telegram markdown 問題）。

**HG-LPF-VERIFY-BEFORE-SEND**：GitHub Pages 上線後等 5-10 分鐘確認 HTTP 200，才傳連結。

**HG-LPF-NO-FAKE-TESTIMONIALS**：見證無真實內容時用「預留位置」標示，嚴禁偽造。

### 軟閘

**SG-LPF-PAGE-LENGTH**：文案量建議 3000-6000 字，高單價產品可更長。

---

## 適應性深度控制

| DNA27 迴圈 | LPF 深度 |
|---|---|
| fast_loop | 快速版：推斷買家畫像（標示）→ 骨架地圖 → 關鍵區段（1/3/5/9/10）→ 精簡稽核 → 不出 HTML |
| exploration_loop | 標準版：五段全走，HTML 輸出 |
| slow_loop | 深度版：五段全走 + Hero Hook A/B 兩版 → HTML + 設計說明文件 |

---

## 系統指令

| 指令 | 效果 |
|------|------|
| `/landing` | 啟動完整五段 Pipeline |
| `/lpf` | 別名 |
| `/lpf quick` | 快速模式，從描述推斷 |
| `/lpf audit` | 只做 CRO Gate 稽核 |
| `/lpf status` | 顯示目前 Phase |
| `/lpf rewrite [#N]` | 重寫指定區段 |
| `/lpf html` | 直接進 Phase 5（需已通過 CRO Gate） |

---

## DNA27 親和對照

啟用時建議：tone → PROFESSIONAL、pace → STEADY、initiative → DRIVE

與其他外掛協同：
- **c15**：Phase 3 文案張力注入
- **text-alchemy**：文字品質路由
- **storytelling-engine**：Phase 2 StoryBrand + BAB 架構
- **consultant-communication**：Phase 2 SCQA 輔助
- **brand-builder**：品牌定位輸入（上游）
- **ssa-consultant**：客戶痛點分析輸入（上游）
- **aesthetic-sense**：Phase 5 視覺稽核
- **ad-pilot**：下游——銷售頁完成後接廣告投放
