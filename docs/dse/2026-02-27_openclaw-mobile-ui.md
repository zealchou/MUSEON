# DSE #4: OpenClaw Mobile Management App — UI/UX 設計分析

**Date**: 2026-02-27
**Trigger**: 使用者分享一篇 OpenClaw 社群 Flutter 行動管理 App 的文章與五張截圖，要求 DSE 其 UI/UX 設計，並提出 MUSEON Dashboard 優化建議。

---

## 1. 研究對象

一款 OpenClaw 社群開發的 Flutter 行動管理 App，功能涵蓋：
- Dashboard（概覽）
- Chat（對話串流）
- Agents（代理管理）
- Skills（技能管理）
- Usage（用量分析）

技術棧：Flutter (Dart) + OpenClaw Gateway API

---

## 2. UI/UX 分析（五大畫面）

### 2.1 Dashboard（首頁概覽）

**佈局結構**：
- 頂部 Hero 區：Gateway 連線狀態（大圓點 + 在線/離線文字）
- 中央 2×2 格子卡片：
  - Sessions（活躍會話數）
  - Nodes（連線節點數）
  - Tokens（今日 Token 用量）
  - Cost（估計花費 USD）
- 底部 Quick Actions 區：快捷操作按鈕

**設計亮點**：
| 項目 | 評價 |
|------|------|
| 資訊密度 | ★★★★☆ — 四張卡片一目了然，不需滾動 |
| 視覺層次 | ★★★★★ — Hero 區強調最重要狀態（Gateway），次要指標用均等卡片 |
| 即時性 | ★★★★☆ — 數字即時更新，有脈搏動畫 |
| 可操作性 | ★★★☆☆ — Quick Actions 功能有限，只有基本操作 |

**關鍵洞察**：
- **Gateway 狀態視覺化**是最佳設計決策 — 讓使用者一眼判斷系統是否正常
- 2×2 卡片佈局是行動裝置上的經典 Dashboard 模式，MUSEON 可直接借鏡
- Cost（花費）與 Tokens 分開顯示是好決定 — 使用者關心的是錢，不是 Token 數

### 2.2 Chat（對話介面）

**佈局結構**：
- 訊息串流顯示（支援 Markdown 渲染）
- 底部輸入欄 + 送出按鈕
- 支援 streaming（打字機效果）

**設計亮點**：
| 項目 | 評價 |
|------|------|
| 串流體驗 | ★★★★☆ — 打字機效果流暢 |
| Markdown 渲染 | ★★★☆☆ — 基本支援，但程式碼區塊樣式一般 |
| 多 Session 管理 | ★★☆☆☆ — 無明顯 Session 切換 UI |

**關鍵洞察**：
- Chat 不是管理型 App 的核心競爭力（使用者會直接用 Telegram/Web）
- 但作為「管理 + 對話」一站式體驗，提供基本 Chat 是合理的

### 2.3 Agents（代理管理）

**佈局結構**：
- 列表式卡片，每個 Agent 一張
- 顯示：Agent 名稱、描述、狀態（active/idle/error）
- 點擊進入詳情頁

**設計亮點**：
| 項目 | 評價 |
|------|------|
| 資訊呈現 | ★★★★☆ — 卡片式佈局清晰 |
| 狀態指示 | ★★★★★ — 顏色編碼直覺（綠=active, 灰=idle, 紅=error）|
| 操作深度 | ★★★☆☆ — 只能查看，缺少直接操作（啟動/停止）|

### 2.4 Skills（技能管理）

**佈局結構**：
- 卡片列表，每張卡包含：
  - 技能名稱
  - 簡短描述
  - Enable/Disable 開關（Toggle）
- 支援搜尋篩選

**設計亮點**：
| 項目 | 評價 |
|------|------|
| Toggle 設計 | ★★★★★ — 最佳決策！一眼看到哪些技能啟用，直接開關 |
| 搜尋功能 | ★★★★☆ — 技能多時必備 |
| 分類/分組 | ★★☆☆☆ — 缺少分類標籤，全部平鋪 |

**關鍵洞察**：
- **Toggle 開關管理 Skill** 是這個 App 最值得借鏡的設計
- MUSEON 有 26+ Skills（DNA27 外掛），如果未來開放使用者管理 Skill 組合，這個模式完美

### 2.5 Usage（用量分析）

**佈局結構**：
- 頂部 Hero 數字：Estimated Cost（估計花費）
- 中段三欄：Input Tokens / Output Tokens / Cache Tokens（帶色彩區分）
- Token Distribution 橫條圖（Input vs Output vs Cache 佔比）
- Daily Cost 折線圖（日花費趨勢）

**設計亮點**：
| 項目 | 評價 |
|------|------|
| 花費優先 | ★★★★★ — Cost 作為 Hero 數字是正確優先級 |
| 三欄分類 | ★★★★☆ — Input/Output/Cache 分開計算很實用 |
| 趨勢圖 | ★★★★★ — Daily Cost 趨勢是成本控制的關鍵視覺化 |
| 時間範圍 | ★★★☆☆ — 只有日視圖，缺少週/月切換 |

**關鍵洞察**：
- **Cost-first 思維**完全正確 — 使用者最終關心的是花了多少錢
- Token 分三類（Input/Output/Cache）讓使用者理解成本結構
- MUSEON 的 BudgetMonitor 已有 `get_usage_stats()`，缺的是前端視覺化

---

## 3. 整體 UI/UX 評價

### 優勢

1. **資訊架構清晰**：5 個底部 Tab 涵蓋管理全場景（Dashboard / Chat / Agents / Skills / Usage）
2. **視覺層次分明**：Hero 數字 > 摘要卡片 > 詳細圖表，由粗到細
3. **行動裝置優化**：卡片式佈局、大字體、觸控友善
4. **即時狀態呈現**：Gateway 狀態、Agent 狀態都有顏色編碼
5. **Cost-first 設計**：花費數字永遠最醒目

### 不足

1. **缺少操作深度**：大部分畫面只能「看」，缺少「做」的能力
2. **無歷史比較**：Usage 只有當前數據，無法對比上週/上月
3. **無告警機制**：沒有花費超標的視覺告警
4. **無多 Provider 視圖**：只顯示總量，沒有按 Provider 分拆
5. **Skill 缺少分類**：26+ Skills 平鋪展示，缺少分組導航

---

## 4. MUSEON Dashboard 現況對比

| 面向 | OpenClaw Mobile App | MUSEON Dashboard | 差距 |
|------|-------------------|-----------------|------|
| 系統狀態 | Gateway Hero + 動畫 | 頂部 status-dot | MUSEON 較弱 |
| Token 用量 | 三欄 + 趨勢圖 | Settings 頁文字顯示 | **大差距** |
| 花費追蹤 | Cost Hero 數字 | 無 | **完全缺失** |
| Skill 管理 | Toggle 開關列表 | 無 UI | **完全缺失** |
| Agent 狀態 | 卡片 + 色彩編碼 | 無 UI | **完全缺失** |
| 記憶瀏覽 | 無 | 有（Memory Tab）| MUSEON 優勢 |
| 演化追蹤 | 無 | 有（Evolution Tab）| MUSEON 優勢 |
| 生命拓樸 | 無 | 有（Organism Tab + Canvas）| MUSEON 獨特優勢 |
| 自我修復 | 無 | 有（Doctor Tab）| MUSEON 優勢 |
| Setup Wizard | 無 | 有（5-step flow）| MUSEON 優勢 |
| 底部導航 | 5 Tabs（行動優化）| 5 Tabs（桌面橫排）| 各有適合 |

### MUSEON 的優勢

MUSEON Dashboard 有三個獨特的 Tab 是 OpenClaw Mobile App 完全沒有的：
- **🧬 生命（Organism）**：Brain 拓樸圖 + Vital Signs — 這是 MUSEON 作為「數位生物」的核心差異化
- **📈 演化（Evolution）**：Q-Score 歷史 + Soul Ring — 長期成長追蹤
- **🧠 記憶（Memory）**：四通道記憶瀏覽器 — 使用者可以直接查看 AI 的記憶

這些是 MUSEON 的品牌核心，**不應刪除或弱化**。

### MUSEON 的缺失

但 MUSEON 在「運維管理」面向嚴重不足：
- Token 用量只是 Settings 頁的一行文字
- 無花費追蹤
- 無 Skill 管理 UI
- 無 Agent 狀態監控
- 系統狀態（Gateway）只是個小圓點

---

## 5. MUSEON Dashboard 優化建議

### Phase 1：🔥 立即可做（現有基礎設施）

#### 1.1 設定頁 Token Budget 升級

**現況**：`settings` Tab 裡一行文字 `今日用量: X / 200,000 tokens (Y%)`
**目標**：視覺化 Token 用量卡片

```
┌─────────────────────────────────┐
│  💰 Token 預算                   │
│                                 │
│  ████████████░░░░  72.3%        │
│  144,600 / 200,000 tokens       │
│                                 │
│  ┌─────┐ ┌─────┐ ┌─────┐       │
│  │Input│ │Output│ │Cache│       │
│  │ 89K │ │ 52K │ │  3K │       │
│  └─────┘ └─────┘ └─────┘       │
│                                 │
│  ⚠️ 接近每日上限               │
└─────────────────────────────────┘
```

**技術需求**：
- `BudgetMonitor.get_usage_stats()` 已接線（Step 2 完成）
- 需要擴充 `BudgetMonitor` 追蹤 input/output/cache 分類
- Progress bar 用 CSS `linear-gradient` 即可
- 不需額外 API

#### 1.2 Gateway 狀態升級

**現況**：頂部一個小圓點 + `Online/Offline` 文字
**目標**：Gateway Hero 卡片

```
┌─────────────────────────────────┐
│  🟢 Gateway Online              │
│  PID: 65730 | Port: 8765        │
│  Uptime: 2h 15m                 │
│  [修復] [重啟] [查看 Log]       │
└─────────────────────────────────┘
```

**技術需求**：
- Gateway health 已有 `/health` 端點
- PID 可從 `gatewayProcess.pid` 取得
- Uptime 需要在 `spawnGateway()` 記錄啟動時間

### Phase 2：🟡 值得做（中等工作量）

#### 2.1 新增「Usage」Tab 或 Section

借鏡 OpenClaw App 的 Usage 頁面，在 MUSEON 設定頁或新 Tab 中：

```
┌─────────────────────────────────┐
│  📊 今日用量                     │
│                                 │
│  估計花費: $0.42                │
│                                 │
│  Token 分佈                     │
│  ▓▓▓▓▓▓▓▓░░░░ Input: 62%       │
│  ▓▓▓▓░░░░░░░░ Output: 35%      │
│  ▓░░░░░░░░░░░ Cache: 3%        │
│                                 │
│  [日] [週] [月]                 │
│  ┌──────────────────────┐       │
│  │  📈 Daily Cost        │       │
│  │  ╱╲  ╱╲              │       │
│  │ ╱  ╲╱  ╲___          │       │
│  └──────────────────────┘       │
└─────────────────────────────────┘
```

**技術需求**：
- 花費計算：`input_tokens * $3/1M + output_tokens * $15/1M`（Claude Sonnet 定價）
- 歷史數據：需要 SQLite 持久化（參見 DSE #3 建議）
- 圖表：已有 Chart.js 依賴（Evolution Tab 使用中）

#### 2.2 Skill 管理 UI

MUSEON 有 26+ Skills（DNA27 外掛模組），可在 Settings 或新 Tab 中：

```
┌─────────────────────────────────┐
│  🧩 技能管理                     │
│  [搜尋...]                      │
│                                 │
│  ── 常駐 ──                     │
│  ┌───────────────────────┐      │
│  │ DNA27 核心   [🔒 ON]  │      │
│  │ C15 敘事     [🔒 ON]  │      │
│  └───────────────────────┘      │
│                                 │
│  ── 按需載入 ──                 │
│  ┌───────────────────────┐      │
│  │ DSE 引擎     [🔘 ON]  │      │
│  │ 市場分析     [🔘 OFF] │      │
│  │ 投資軍師     [🔘 OFF] │      │
│  └───────────────────────┘      │
└─────────────────────────────────┘
```

**技術需求**：
- Skill 列表：從 `data/skills/` 目錄讀取
- 新 Gateway 端點：`GET /api/skills`、`POST /api/skills/{name}/toggle`
- 前端：Toggle 組件已有（`renderSettingToggle`）

### Phase 3：🔵 未來迭代

#### 3.1 多 Provider 用量視圖
- 當 MUSEON 支援多 LLM Provider（Claude + Local Qwen3）時
- 顯示每個 Provider 的用量和花費

#### 3.2 Agent 狀態頁
- 顯示所有 Sub-Agent 的運行狀態
- 需要等 Sub-Agent 系統更成熟

#### 3.3 花費趨勢圖（需 SQLite）
- Daily/Weekly/Monthly cost chart
- 需要持久化存儲（參見 DSE #3 規劃）

---

## 6. 實作優先排序

| 優先級 | 項目 | 工作量 | 依賴 |
|--------|------|--------|------|
| P0 | Token Budget 視覺化（Progress Bar + 分類） | 2h | BudgetMonitor 已接線 |
| P0 | Gateway Hero 卡片 | 1h | 已有 health API |
| P1 | 花費估算顯示 | 1h | Token 數 × 定價 |
| P1 | Skill 列表 + Toggle | 4h | 新 API 端點 |
| P2 | Usage 獨立 Tab/Section | 6h | Chart.js 已可用 |
| P3 | 花費趨勢圖 | 8h+ | 需 SQLite 持久化 |
| P3 | Agent 狀態頁 | 8h+ | Sub-Agent 系統完善後 |

---

## 7. 結論

OpenClaw Mobile App 的核心設計理念是 **「Cost-first + Status-first」**，讓使用者一眼看到花了多少錢、系統是否正常。

MUSEON Dashboard 的核心設計理念是 **「生物演化 + 自我認知」**（Organism/Evolution/Memory），這是品牌差異化的根基。

**最佳策略**：保留 MUSEON 的獨特 Tab（生命/演化/記憶），同時在 Settings 和 Organism Tab 中強化運維監控能力（Token 視覺化、Gateway Hero、花費估算），形成「生物靈魂 + 運維實用」的雙贏佈局。

---

## 參考來源

- 使用者分享之 OpenClaw 社群 Flutter App 文章及 5 張截圖
- OpenClaw 官方 GitHub (openclaw/openclaw, 232K stars)
- OpenClaw Flutter 生態系搜尋（10+ 社群 Flutter 客戶端）
- MUSEON 現有 Dashboard codebase 審計
