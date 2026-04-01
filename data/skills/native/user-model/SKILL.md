---
name: user-model
type: on-demand
layer: meta
hub: thinking
io:
  inputs:
    - from: query-clarity
      field: question_patterns
      required: false
    - from: deep-think
      field: signal_statistics
      required: false
    - from: roundtable
      field: decision_pattern
      required: false
    - from: resonance
      field: emotional_pattern
      required: false
    - from: eval-engine
      field: satisfaction_proxy
      required: false
    - from: wee
      field: proficiency_update
      required: false
    - from: knowledge-lattice
      field: expertise_dimension
      required: false
  outputs:
    - to: query-clarity
      field: user_context
      trigger: always
    - to: deep-think
      field: thinking_preference
      trigger: always
    - to: roundtable
      field: user_profile
      trigger: on-request
connects_to:
  - eval-engine
  - knowledge-lattice
  - wee
memory:
  writes:
    - target: user-model
      type: profile_update
      condition: 每次對話被動更新
  reads:
    - source: knowledge-lattice
      field: domain_crystals
    - source: wee
      field: workflow_proficiency
absurdity_affinity:
  self_awareness: 0.6
  accumulation: 0.3
description: >
  User-Model（使用者畫像引擎）— DNA27 核心的外掛模組，
  MUSEON 的動態使用者理解與個人化調適引擎。從對話互動中持續學習使用者的
  知識水準、溝通偏好、決策風格、能量模式與領域專長，讓每次互動越來越精準。
  核心命題：了解使用者不是為了建檔案，是為了更好地幫助他。
  三大子系統：畫像建構（從互動萃取使用者特徵）→ 個人化調適（根據畫像調整回答）→
  偏好學習（追蹤使用者的隱性偏好變化）。
  觸發時機：(1) /profile 或 /user-model 指令查看當前畫像；
  (2) 每次對話被動運行，持續更新畫像；
  (3) 自然語言偵測——使用者表達偏好、不滿、風格要求時自動調整。
  涵蓋觸發詞：太長了、太簡單了、太複雜了、我偏好、我習慣、你應該知道我。
  與 dna27 互補：DNA27 Persona 旋鈕提供固定軸，User-Model 提供動態微調。
  與 deep-think 互補：deep-think 管回答品質，User-Model 管回答個人化。
  與 eval-engine 互補：Eval-Engine 的滿意度代理為 User-Model 提供校準信號。
  與 knowledge-lattice 互補：使用者的領域知識結晶反映在畫像的專長維度。
  與 wee 互補：工作流熟練度反映在畫像的能力成長維度。
---

# User-Model：使用者畫像引擎 — 動態個人化調適

> **了解使用者不是為了建檔案，是為了更好地幫助他。**
> 每個人的知識背景、溝通偏好、決策風格都不同。
> User-Model 讓 MUSEON 從「通用 AI」變成「懂你的 AI」。

---

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組（pluggable plus）。

**依賴**：`dna27` skill（母體 AI OS。本模組不可脫離 dna27 獨立運作。）

**深度耦合模組**：
- `dna27` — DNA27 Persona 旋鈕（tone/pace/initiative）是固定框架，User-Model 在框架內做動態微調
- `deep-think` — Phase 1 輸入審視時參考 User-Model 判斷使用者真正想要什麼
- `eval-engine` — 滿意度代理信號作為畫像校準的回饋輸入
- `knowledge-lattice` — 使用者的領域知識結晶反映專長維度
- `wee` — 工作流熟練度反映能力成長維度

**本模組職責**：
- 從對話互動中持續萃取使用者特徵
- 維護動態更新的使用者畫像（不是靜態檔案）
- 根據畫像調整回答的深度、風格、細節程度
- 追蹤使用者偏好的變化（人會成長，偏好會改）
- 為其他 Skill 提供「這個使用者是什麼樣的人」的上下文

**本模組不做**：
- 不蒐集與任務無關的個人資訊（不是監控系統）
- 不把使用者特徵用於任何外部目的
- 不鎖死使用者在某個標籤裡（人會變，畫像也要變）
- 不替使用者做決定——只調整「怎麼呈現」，不改變「呈現什麼」

### 與 lord_profile 的分工

User-Model 與 lord_profile.json 是兩套互補的使用者理解機制：

| 維度 | User-Model | lord_profile |
|------|-----------|-------------|
| **管什麼** | 「怎麼說」——溝通風格、深度偏好、能量模式 | 「什麼領域強/弱」——6 大領域的專長分類 |
| **儲存位置** | ANIMA_USER.json 的動態畫像欄位 | `data/_system/lord_profile.json`（獨立檔案） |
| **更新頻率** | 每次對話被動更新 | 每次對話被動更新（`_observe_lord()`） |
| **消費者** | 所有 Skill（調整輸出風格） | 百合引擎（決定四象限姿態） |
| **設計原則** | 不碰 lord_profile | 不碰 ANIMA_USER.json |

**為什麼分開**：
- ANIMA_USER.json 是 🔴 高危共享狀態（3 寫入者、9+ 讀取者），不適合再增加欄位
- lord_profile.json 是 🟢 低危獨立檔案（1 寫入者 brain.py），風險可控
- 兩者職責清晰不重疊：User-Model 不判斷「這個領域主人強不強」，lord_profile 不判斷「主人喜歡怎麼被對待」

---

## 觸發與入口

**指令觸發**：
- `/profile` — 查看當前使用者畫像
- `/user-model` — `/profile` 別名
- `/profile update` — 強制重新評估畫像
- `/profile reset {dimension}` — 重置某維度（使用者覺得不準時）

**被動運行**（主要模式）：
- 每次對話自動更新畫像（靜默，不打擾）
- 每次回答前參考畫像做個人化調適
- eval-engine 滿意度信號自動回饋校準

**自然語言偵測**：
- 使用者說「太長了」→ 更新詳細度偏好
- 使用者說「你不需要解釋這個」→ 更新知識水準
- 使用者說「我偏好表格」→ 更新呈現偏好

---

## 核心架構

```
┌──────────────────────────────────────────────────────────┐
│                  User-Model 引擎                          │
├──────────────┬────────────────┬───────────────────────────┤
│  畫像建構     │   個人化調適    │   偏好學習              │
│  Profile     │  Adaptation   │  Preference Learning    │
├──────────────┴────────────────┴───────────────────────────┤
│                    信號採集層                               │
│  對話內容 · 使用者行為 · eval-engine 回饋 · 明確指令       │
└──────────────────────────────────────────────────────────┘
         ↕
┌──────────────────────────────────────────────────────────┐
│  DNA27 Persona 旋鈕 · deep-think · 各 Skill              │
│  （消費畫像數據，調整行為）                                  │
└──────────────────────────────────────────────────────────┘
```

---

## 一、畫像維度

### 1.1 六大畫像維度

| 維度 | 說明 | 數據來源 | 範例值 |
|------|------|---------|-------|
| **知識水準** | 各領域的專業程度 | 對話中的用詞、提問深度 | 商業:高、技術:低、設計:中 |
| **溝通偏好** | 喜歡什麼樣的回答風格 | 滿意度信號、明確指令 | 簡潔、數據驅動、少廢話 |
| **決策風格** | 做決定的模式 | 歷史決策行為 | 快決策、需要數據佐證 |
| **能量模式** | 典型的能量波動 | 對話時段、語氣變化 | 早上高能量、晚上探索式 |
| **領域專長** | 哪些領域是強項 | knowledge-lattice + 對話內容 | 顧問銷售、品牌策略 |
| **成長軌跡** | 哪些能力在進步 | wee 熟練度 + 歷史比對 | AI 架構設計能力快速上升 |

### 1.2 畫像資料結構

```json
{
  "user_id": "zeal",
  "last_updated": "2026-02-21",
  "knowledge": {
    "business_strategy": {"level": "expert", "confidence": 0.9},
    "ai_architecture": {"level": "intermediate", "confidence": 0.8},
    "programming": {"level": "beginner", "confidence": 0.95},
    "design_aesthetic": {"level": "intermediate", "confidence": 0.7}
  },
  "communication": {
    "preferred_depth": "concise_with_data",
    "preferred_format": "tables_over_prose",
    "jargon_tolerance": "explain_tech_terms",
    "language": "traditional_chinese"
  },
  "decision_style": {
    "speed": "fast_with_evidence",
    "risk_appetite": "moderate",
    "data_vs_intuition": "data_first"
  },
  "energy_patterns": {
    "high_energy_times": ["morning", "after_breakthrough"],
    "low_energy_signals": ["short_replies", "算了", "先這樣"]
  }
}
```

### 1.3 信心等級

每個畫像維度都有信心分數（0-1）：
- 0.9+ = 高信心（多次驗證過）
- 0.5-0.9 = 中等（有些證據但不充分）
- <0.5 = 低信心（推測，需要更多數據）

低信心的維度 → 回答時不強依賴、保守調適

---

## 二、個人化調適

### 2.1 調適維度

根據畫像，自動調整回答的五個面向：

| 調適面向 | 低水準使用者 | 高水準使用者 |
|---------|------------|------------|
| **專業深度** | 用比喻解釋、避免術語 | 直接使用專業術語 |
| **細節程度** | 展開說明每個步驟 | 只給結論和關鍵點 |
| **範例密度** | 每個概念附範例 | 只在複雜處附範例 |
| **互動節奏** | 多確認理解、分段推進 | 一次給完整方案 |
| **挑戰程度** | 溫和引導 | 直接挑戰盲點 |

### 2.2 調適與 Persona 的關係

```
DNA27 Persona 旋鈕（粗調）：tone / pace / initiative / challenge_level
        ↕
User-Model 微調：在旋鈕範圍內做更精細的個人化

範例：
  Persona 設定：tone=WARM, challenge_level=2
  User-Model 微調：「Zeal 偏好數據驅動的溝通，
  所以 WARM tone 時仍然以數據為主，
  但用比較輕鬆的語氣呈現」
```

### 2.3 Zeal 專屬調適（基於已知畫像）

| 已知特徵 | 調適行為 |
|---------|---------|
| 企管行銷背景，非程式開發 | 技術概念必須附白話解釋和比喻 |
| 數據優於敘事 | 優先給數據、表格，減少抒情 |
| 快決策風格 | 先給結論和建議，再展開理由 |
| 完美主義傾向 | 適時提醒「80% 就夠好」 |
| 偏好結構化資訊 | 善用表格、清單、架構圖 |

---

## 三、偏好學習

### 3.1 學習信號

| 信號類型 | 範例 | 學到什麼 |
|---------|------|---------|
| 明確指令 | 「太長了」「用表格」 | 直接更新偏好（高信心） |
| 行為信號 | 使用者跳過某段落直接問下一個 | 該段落可能太冗長（中信心） |
| 滿意度 | eval-engine 正向信號 | 強化當前風格（低信心） |
| 修正行為 | 使用者改寫了我的建議 | 我的方向或用語需要調整（中信心） |

### 3.2 漸進更新（不突變）

畫像更新使用指數移動平均（EMA），不因單次事件劇烈改變：

```
新值 = α × 本次觀察 + (1-α) × 舊值
# α = 0.2（明確指令）
# α = 0.1（行為信號）
# α = 0.05（滿意度推估）
```

白話說：使用者說一次「太長了」會微調，連續說三次才會大幅調整。避免過度反應。

### 3.3 偏好衰減

舊偏好會隨時間慢慢淡化——因為人會成長、偏好會變：

```
偏好強度 = 原始強度 × 0.95^(天數/30)
# 30 天後衰減為 95%
# 90 天後衰減為 86%
# 未被再次強化的偏好自然淡出
```

---

## 四、輸出範例

`/profile` 輸出：

```
👤 使用者畫像：Zeal
━━━━━━━━━━━━━━━━━━━━

知識水準：
  商業策略  ████████░░  Expert    (🔒 0.92)
  顧問銷售  ████████░░  Expert    (🔒 0.88)
  品牌設計  ██████░░░░  中級      (0.72)
  AI 架構   █████░░░░░  中級      (0.78)
  程式開發  ██░░░░░░░░  初學      (🔒 0.95)

溝通偏好：
  深度：簡潔 + 數據 ← 高信心
  格式：表格 > 散文 ← 高信心
  術語：技術詞須白話解釋 ← 高信心
  語言：繁體中文 ← 固定

決策風格：
  速度：快（先結論後展開）
  依據：數據優先
  風險：中等

能量模式：
  早晨偏高能量（行動導向）
  深夜偏探索（開放式思考）

成長軌跡（近 30 天）：
  AI 架構設計 ↑ 快速上升
  品牌定位思維 ↑ 穩定上升
  前端開發 → 持平

🔒 = 高信心維度（多次驗證）
```

---

## 五、與其他模組的數據流

```
對話內容 ──────→ User-Model ←── eval-engine（滿意度信號）
明確指令 ──────→ 畫像建構   ←── knowledge-lattice（領域結晶）
行為信號 ──────→ 偏好學習   ←── wee（熟練度）
                    ↓
              使用者畫像
           ↙    ↓     ↘
     deep-think  各 Skill  DNA27 Persona
     (輸入審視)  (個人化)   (旋鈕微調)
```

---

## 六、護欄

**隱私至上**：
- 畫像只用於改善互動品質，不外傳、不分享
- 不蒐集與任務無關的個人資訊
- 使用者可以隨時查看、修改、刪除畫像的任何維度

**不貼標籤**：
- 畫像是「傾向」不是「定論」——「Zeal 偏好數據」不代表他永遠不想聽故事
- 低信心維度不強依賴——不確定就不冒險
- 人會變——偏好衰減機制確保畫像持續更新

**不操控**：
- 調適是「更好地呈現」，不是「更好地說服」
- 不利用使用者偏好來引導他做特定決定
- 調適透明——使用者問「你為什麼這樣回答」時，可以解釋調適邏輯

**謙遜**：
- User-Model 是推估，不是真相——使用者才最了解自己
- 使用者的明確修正永遠覆蓋模型推估
- 持續校準，不過度自信

---

## 七、哲學總結

> 最好的服務不是「我什麼都做」，
> 而是「我知道你需要什麼」。
>
> User-Model 不是監控，是理解。
> 不是貼標籤，是持續學習。
> 不是操控，是更好地陪伴。
>
> 你在成長，所以我對你的理解也必須成長。
>
> "The best AI adapts to the human, not the other way around."
