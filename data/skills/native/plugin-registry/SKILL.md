---
name: plugin-registry
type: reference
layer: evolution
io:
  inputs:
    - from: acsf
      field: new_skill_entry
      required: false
  outputs:
    - to: orchestrator
      field: skill_catalog
      trigger: on-request
    - to: morphenix
      field: skill_health_data
      trigger: on-request
connects_to:
  - dna27
  - orchestrator
  - morphenix
  - acsf
description: >
  外掛模組註冊表（Plugin Registry）v2.0 — DNA27 核心的參考文件，
  管理所有 MUSEON 外掛模組的註冊資訊、迴圈允許規則、RC 親和對照、協作矩陣與共存規則。
  已註冊外掛：29 個（含 3 常駐 + 26 按需）。未部署但設計中：meta-learning、info-architect。
  此文件為 dna27/references 底下的治理參考文件，非獨立 Skill，不可被單獨觸發。
  觸發時機：DNA27 路由、orchestrator 編排、morphenix 迭代時自動參照。
  指令觸發：無獨立指令。透過 /orchestrate、/morphenix fitness、/morphenix status 間接使用。
  與 dna27 互補：DNA27 核心定義治理規則，plugin-registry 定義外掛生態系的註冊與共存。
  與 orchestrator 互補：orchestrator 編排多 Skill 時參照此表的協作矩陣與迴圈允許規則。
  與 morphenix 互補：morphenix Skill 健康儀表板參照此表的完整外掛清單。
  與 acsf 互補：鍛造新 Skill 完成後，必須在此表新增條目才算正式上線。
---

# 外掛模組註冊表（Plugin Registry）v2.0

> **上次更新**：2026-02-21
> **已註冊外掛**：28 個（含 3 常駐 + 25 按需）
> **未部署但設計中**：meta-learning、info-architect（available_skills 有描述，/mnt/skills/user 中無 SKILL.md）

DNA27 是母體作業系統，所有外掛模組透過此註冊表連接。外掛可使用 DNA27 提供的核心能力（迴圈/模式/Persona/護欄/記憶/演化引擎），但不可覆寫核心治理規則。

---

## 母子架構（完整）

```
DNA27（核心 OS）
│
├── 【常駐層】（always-on，不需觸發）
│   ├── deep-think           （思維品質前置引擎）
│   ├── c15                  （敘事張力語言憲法）
│   └── query-clarity        （問題品質守門層）
│
├── 【前置與決策支援】
│   └── roundtable           （圓桌詰問引擎）
│
├── 【思維與轉化】
│   ├── resonance            （感性共振引擎）
│   ├── dharma               （思維轉化引擎）
│   ├── philo-dialectic      （哲學思辨引擎）
│   ├── xmodel               （通用破框解方引擎）
│   └── pdeif                （目的導向逆熵流引擎）
│
├── 【商業與戰略】
│   ├── business-12          （商模十二力診斷引擎）
│   ├── ssa-consultant       （顧問式銷售與系統創業引擎）
│   ├── master-strategy      （戰略判斷與心理動力引擎）
│   └── shadow               （人際博弈辨識引擎）
│
├── 【語言與創作】
│   ├── text-alchemy         （文字煉金路由模組）
│   ├── storytelling-engine  （說故事引擎）
│   ├── novel-craft          （小說工藝引擎）
│   └── consultant-communication（顧問式溝通引擎）
│
├── 【美感與品牌】
│   ├── aesthetic-sense       （美感引擎）
│   └── brand-identity       （品牌識別治理引擎）
│
├── 【元認知與學習】
│   └── user-model           （使用者畫像引擎）
│
├── 【演化與治理】
│   ├── morphenix            （自我進化引擎）
│   ├── wee                  （工作流演化引擎）
│   ├── knowledge-lattice    （知識晶格引擎）
│   ├── eval-engine          （效能儀表板）
│   ├── sandbox-lab          （沙盒實驗室）
│   ├── orchestrator         （編排引擎）
│   └── qa-auditor           （品質審計引擎）
│
├── 【產品線】
│   ├── gap                  （市場缺口分析引擎）
│   ├── dse                  （AI 技術融合驗證引擎）
│   ├── acsf                 （能力結晶與 Skill 鑄造引擎）
│   ├── env-radar            （環境雷達引擎）
│   └── report-forge         （付費級產業診斷報告鍛造引擎）
│
├── 【特殊模組】
│   └── tantra               （情慾治理引擎，研究階段）
│
└── 【未部署 / 設計中】
    ├── meta-learning        （元學習引擎，描述存在但 SKILL.md 未部署）
    └── info-architect       （資訊架構引擎，描述存在但 SKILL.md 未部署）
```

---

## 一、常駐層（Always-On）

### deep-think — 深度思考前置引擎

| 屬性 | 值 |
|---|---|
| plus_id | DEEP_THINK |
| 類別 | core-extension / quality-control |
| 運行模式 | **常駐**——每次回答前自動執行，非外掛而是核心迴圈延伸 |
| 風險等級 | LOW |
| 允許迴圈 | 全部（常駐層不受迴圈限制） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 無（自動運行） |
| 觸發指令 | /think-deep（完整展開）、/think-off（暫時關閉）、/think-on（重啟） |
| 核心能力 | Phase 0 訊號分流（感性→Resonance / 思維轉化→DHARMA / 哲學→philo-dialectic）→ Phase 1 輸入審視（五道檢查）→ Phase 2 輸出審計（四道自我檢查） |
| 與其他外掛 | 為 resonance、dharma、philo-dialectic 提供 Phase 0 訊號路由 |

### c15 — StoryForge 敘事張力語言憲法

| 屬性 | 值 |
|---|---|
| plus_id | C15_STORYFORGE |
| 類別 | core-extension / language-layer |
| 運行模式 | **常駐**——所有對話輸出自動套用，text-alchemy 啟動時暫停讓位 |
| 風險等級 | LOW |
| 允許迴圈 | 全部（語言層不限制迴圈） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 無（自動運行）；text-alchemy 啟動時暫停 |
| 觸發指令 | /c15-full（強制完整展開）、/c15-off（暫時關閉）、/c15-on（重啟）、/c15-plain（保留骨架降低描寫） |
| 核心能力 | 敘事張力公式：內在動機→阻力→選擇→代價→變化 |
| 與其他外掛 | text-alchemy（讓位關係）、deep-think（想的品質 vs 說的張力）、consultant-communication（結構 vs 感染力）、aesthetic-sense（視覺美感 vs 文字美感）、resonance（情緒承接時提供象徵語彙） |

### query-clarity — 問題品質守門層

| 屬性 | 值 |
|---|---|
| plus_id | QUERY_CLARITY |
| 類別 | core-extension / input-quality-control |
| 運行模式 | **常駐**——所有 Skill 路由之前自動執行問題品質掃描，非外掛而是核心層擴展 |
| 風險等級 | LOW |
| 允許迴圈 | 全部（常駐層不受迴圈限制）；fast_loop 時自動靜默放行 |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 無（自動運行）；fast_loop 或問題品質合格時靜默放行 |
| 觸發指令 | 無獨立指令（常駐自動掃描） |
| 核心能力 | 四類問題品質偵測：目的模糊（追「你真正想解決什麼」）、前提可疑（追「這個假設成立嗎」）、角色模糊（追「你在這個情境裡的位置」）、解構缺失（追「還有哪些你沒看到的面向」）；每次只問一題 |
| 與其他外掛 | deep-think（deep-think 管輸出品質，query-clarity 管輸入品質）；roundtable（問題清晰後建議啟動圓桌詰問）；user-model（判斷使用者意圖精度）；knowledge-lattice（提供領域脈絡輔助判斷） |

---

## 一點五、前置與決策支援

### roundtable — 圓桌詰問引擎

| 屬性 | 值 |
|---|---|
| plus_id | ROUNDTABLE |
| 類別 | multi-perspective-deliberation-engine |
| 風險等級 | MEDIUM-HIGH |
| 允許迴圈 | slow_loop（主，多角色展開需要深度空間）、exploration_loop（軟允許，簡化版） |
| 禁止迴圈 | fast_loop（多角色詰問不能急） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | query-clarity 通過後建議啟動；或使用者面臨重大決策、兩難困境 |
| 觸發指令 | /roundtable |
| 核心能力 | 常設三角（陽謀者/陰謀者/鏡照者）+ 衛星角色動態召集；螺旋仲裁循環（最多 3 輪）；使用者擔任仲裁者裁決衝突 |
| 與其他外掛 | query-clarity（前置問題品質確保→圓桌啟動）；master-strategy（陽謀者視角的戰略供給）；shadow（陰謀者視角的博弈供給）；user-model（仲裁歷史累積為決策風格畫像）；knowledge-lattice（圓桌結論結晶為可檢索知識） |

---

## 二、思維與轉化

### resonance — 感性共振引擎

| 屬性 | 值 |
|---|---|
| plus_id | RESONANCE |
| 類別 | emotional-processing-engine |
| 風險等級 | LOW |
| 允許迴圈 | fast_loop（情緒急救）、exploration_loop（探索階段）、slow_loop（深度承接） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | deep-think Phase 0 偵測感性訊號，或使用者明顯情緒表達 |
| 觸發指令 | /resonance |
| 核心能力 | RESONANCE 九步承接：R(關係語氣) E(情緒頻率) S(象徵鏡射) O(振盪流程) N(敘事緩衝) A(對齊) N(下一步共振) C(容納) E(回聲延續) |
| 與其他外掛 | deep-think（Phase 0 路由）→ resonance（感性承接）→ dharma（理性轉化）；shadow（情緒操控辨識）；c15（象徵語彙）；tantra（情慾情境承接） |

### dharma — 思維轉化引擎

| 屬性 | 值 |
|---|---|
| plus_id | DHARMA |
| 類別 | cognitive-transformation-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | exploration_loop（主）、slow_loop（深度轉化） |
| 禁止迴圈 | fast_loop（思維轉化不能急） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | deep-think Phase 0 偵測思維轉化訊號，或使用者明確描述決策困境 |
| 觸發指令 | /dharma、/dharma coach |
| 核心能力 | 六步驟轉化：Discern→Hold→Absorb→Reflect→Map→Align；融合四聖諦、蘇格拉底問答、GROW、NLP |
| 與其他外掛 | resonance（感性前置→理性轉化）；philo-dialectic（哲學探究 vs 實踐轉化）；pdeif（Align 步驟可調用做路徑設計）；deep-think（Phase 0 路由） |

### philo-dialectic — 哲學思辨引擎

| 屬性 | 值 |
|---|---|
| plus_id | PHILO_DIALECTIC |
| 類別 | philosophical-reasoning-engine |
| 風險等級 | LOW |
| 允許迴圈 | slow_loop（主，需要深度展開）、exploration_loop（軟允許） |
| 禁止迴圈 | fast_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 狀態允許慢層展開（能量 ≥ 中） |
| 觸發指令 | /philo、/dialectic、/思辨 |
| 核心能力 | 概念澄清、論證分析、前提檢驗、思想實驗、多視角推演；融合蘇格拉底式提問、辯證法、現象學、道家、儒家、禪宗 |
| 與其他外掛 | deep-think（Phase 0 路由）；dharma（哲學探究 vs 實踐轉化）；xmodel（行動推演 vs 概念澄清）；master-strategy（戰略判斷的價值框架審視） |

### xmodel — 通用破框解方引擎

| 屬性 | 值 |
|---|---|
| plus_id | XMODEL_VNEXT |
| 類別 | break-frame-solution-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | slow_loop（主）、exploration_loop（軟允許） |
| 禁止迴圈 | fast_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 能量 ≥ 中、緊急度低、無不可逆情境 |
| 觸發指令 | /xmodel、/xmodel coach、/manifest |
| 核心能力 | 8 槓桿維度掃描、7 欄位交換模型、M1-M6 Manifest 推演、可承擔小實驗設計 |
| 與其他外掛 | business-12（商業交叉比對）；pdeif（選定終點後反推路徑）；wee（破框階段跨界掃描）；master-strategy（戰略判斷 + 槓桿掃描） |

### pdeif — 目的導向逆熵流引擎

| 屬性 | 值 |
|---|---|
| plus_id | PDEIF |
| 類別 | goal-convergence-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | slow_loop（主）、exploration_loop（軟允許） |
| 禁止迴圈 | fast_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 使用者有明確或半明確的終點狀態需求 |
| 觸發指令 | /pdeif、/flow-design |
| 核心能力 | 終點形式化→情境邊界→MECE 遞迴拆解→多通道接觸點→封閉回饋→失效包絡 |
| 與其他外掛 | xmodel（破框產生終點候選）→ pdeif（逆推路徑）；dharma（Align 步驟調用）；master-strategy（戰略落地為可執行流程）；wee（流程設計→演化追蹤） |

---

## 三、商業與戰略

### business-12 — 商模十二力診斷與成長引擎

| 屬性 | 值 |
|---|---|
| plus_id | BUSINESS_12 |
| 類別 | business-diagnosis-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | fast_loop（止血版）、exploration_loop、slow_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 有商業/經營情境 |
| 觸發方式 | 自然語言偵測商業問題 |
| 核心能力 | 12 力框架、27 染色體商業診斷擴展、商模護欄 |
| 與其他外掛 | xmodel（跨領域破框）；ssa-consultant（銷售實戰 + 系統建構）；master-strategy（戰略升維）；aesthetic-sense（品牌力/感受管理力的視覺落地）；gap（市場缺口分析） |

### ssa-consultant — 顧問式銷售與系統創業引擎

| 屬性 | 值 |
|---|---|
| plus_id | SSA_CONSULTANT |
| 類別 | sales-and-system-building-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | fast_loop（止血版）、exploration_loop、slow_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 有基本銷售/商業情境 |
| 觸發指令 | /ssa、/ssa coach |
| 核心能力 | 顧問式銷售 12 步驟、系統創業方法論、27 條 SSA 染色體 |
| 與其他外掛 | business-12（商模弱項交叉）；xmodel（破框推演）；master-strategy（戰略心理）；shadow（客戶關係中的對抗型態辨識）；brand-identity（品牌人格一致性） |

### master-strategy — 戰略判斷與心理動力引擎

| 屬性 | 值 |
|---|---|
| plus_id | MASTER_STRATEGY |
| 類別 | strategic-judgment-engine |
| 風險等級 | MEDIUM-HIGH |
| 允許迴圈 | slow_loop（主）、exploration_loop（軟允許）、fast_loop（止血版，僅限 1 條染色體） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 能量 ≥ 中（完整版）；能量低+緊急高（止血版） |
| 觸發指令 | /strategy、/strategy coach、/wargame |
| 核心能力 | 七大叢集三軸診斷、22 條專家染色體、突觸啟動路由、兵棋沙盤推演；融合孫子兵法、鬼谷子、A3 現實顯化 |
| 與其他外掛 | business-12（商業戰略）；ssa-consultant（銷售談判）；xmodel（複雜困局推演）；shadow（陽謀 vs 陰謀）；env-radar（環境情報）；philo-dialectic（價值框架審視）；pdeif（戰略落地為流程） |

### shadow — 人際博弈辨識引擎

| 屬性 | 值 |
|---|---|
| plus_id | SHADOW |
| 類別 | interpersonal-dynamics-engine |
| 風險等級 | MEDIUM-HIGH |
| 允許迴圈 | exploration_loop（主）、slow_loop（深度分析） |
| 禁止迴圈 | fast_loop（人際判斷不能草率） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 偵測到人際對抗/操控訊號 |
| 觸發指令 | /shadow、/shadow-crimson |
| 核心能力 | 27 類對抗型態偵測 + 防禦原則（防禦層）；27 類情感博弈模式識別（洞察層） |
| 與其他外掛 | master-strategy（陽謀 vs 陰謀）；ssa-consultant（客戶關係辨識）；resonance（情緒被操控時先承接再辨識）；tantra（情慾關係中的對抗偵測） |

---

## 四、語言與創作

### text-alchemy — 文字煉金路由模組

| 屬性 | 值 |
|---|---|
| plus_id | TEXT_ALCHEMY |
| 類別 | language-router |
| 風險等級 | LOW |
| 允許迴圈 | 全部（語言層不限制迴圈） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 使用者有明確文字產出需求 |
| 觸發指令 | /text、/alchemy |
| 核心能力 | 按意圖/受眾/場景自動路由到適合的風格模組；啟動時接管語言層，C15 暫停讓位 |
| 與其他外掛 | c15（讓位關係）；storytelling-engine（敘事結構路由）；novel-craft（文字工藝路由）；consultant-communication（商業溝通路由）；aesthetic-sense（美感校驗） |

### storytelling-engine — 說故事引擎

| 屬性 | 值 |
|---|---|
| plus_id | STORYTELLING_ENGINE |
| 類別 | narrative-structure-engine |
| 風險等級 | LOW |
| 允許迴圈 | exploration_loop、slow_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | text-alchemy 路由判斷為「說服影響」或「敘事創作」，或使用者明確要求 |
| 觸發指令 | /story、/storytelling |
| 核心能力 | 黃金圈、Sparkline、英雄旅程、StoryBrand、Pixar 22 規則、Vonnegut 六弧線、Zak 神經科學驗證 |
| 與其他外掛 | text-alchemy（路由來源）；c15（語言張力執行 vs 故事骨架搭建）；novel-craft（說什麼 vs 怎麼說）；consultant-communication（邏輯結構 vs 情感結構） |

### novel-craft — 小說工藝引擎

| 屬性 | 值 |
|---|---|
| plus_id | NOVEL_CRAFT |
| 類別 | prose-craft-engine |
| 風險等級 | LOW |
| 允許迴圈 | exploration_loop、slow_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | text-alchemy 路由判斷為「敘事創作」且需深度文字工藝，或 c15 需更精細技法支援 |
| 觸發指令 | /novel、/craft、/prose |
| 核心能力 | Hemingway 冰山理論、Carver 極簡主義、Chekhov 潛台詞、村上春樹氛圍營造、電影劇本視覺敘事 |
| 與其他外掛 | text-alchemy（路由來源）；c15（原則層 vs 技法庫）；storytelling-engine（結構 vs 質感） |

### consultant-communication — 顧問式溝通引擎

| 屬性 | 值 |
|---|---|
| plus_id | CONSULTANT_COMMUNICATION |
| 類別 | business-communication-engine |
| 風險等級 | LOW |
| 允許迴圈 | fast_loop（簡單結構化）、exploration_loop、slow_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 使用者需要結構化表達、製作商業文件 |
| 觸發指令 | 自然語言偵測（簡報、報告、提案、金字塔、MECE 等） |
| 核心能力 | 麥肯錫金字塔原則、MECE 結構化思維、SCQA 敘事框架、HBR 寫作風格、哈佛個案研究方法論 |
| 與其他外掛 | text-alchemy（路由來源）；c15（結構 vs 感染力）；storytelling-engine（邏輯結構 vs 情感結構）；brand-identity（溝通結構 vs 品牌調性）；aesthetic-sense（溝通美感校驗） |

---

## 五、美感與品牌

### aesthetic-sense — 美感引擎

| 屬性 | 值 |
|---|---|
| plus_id | AESTHETIC_SENSE |
| 類別 | aesthetic-governance-engine |
| 風險等級 | LOW |
| 允許迴圈 | 全部（美感審計可在任何迴圈追加） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 產出對外可見內容時自動併入；或使用者明確要求 |
| 觸發指令 | /aesthetic、/美感 |
| 核心能力 | Jobs 減法哲學、Dieter Rams 十原則、千利休侘寂、Housen 五階段審美；減法審計、留白呼吸、風格一致性 |
| 與其他外掛 | brand-identity（通用美感 vs 品牌專屬規範）；business-12（品牌力/感受管理力落地）；consultant-communication（溝通品質精煉）；c15（視覺美感 vs 文字美感） |

### brand-identity — 品牌識別治理引擎

| 屬性 | 值 |
|---|---|
| plus_id | BRAND_IDENTITY |
| 類別 | brand-governance-engine |
| 風險等級 | LOW |
| 允許迴圈 | 全部（品牌一致性檢查可在任何迴圈追加） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 產出對外可見內容時自動併入；或涉及品牌相關需求 |
| 觸發指令 | /brand、/identity |
| 核心能力 | April Dunford 定位五要素、品牌金字塔、色彩/字型規劃、品牌做與不做原則、訊息金字塔、競爭定位矩陣 |
| 與其他外掛 | aesthetic-sense（通用美感 vs 品牌規範）；consultant-communication（溝通結構 vs 品牌調性）；c15（敘事張力不偏離品牌人格）；ssa-consultant（品牌人格一致性） |

---

## 六、元認知與學習

### user-model — 使用者畫像引擎

| 屬性 | 值 |
|---|---|
| plus_id | USER_MODEL |
| 類別 | personalization-engine |
| 運行模式 | **半常駐**——每次對話被動運行更新畫像，不需觸發 |
| 風險等級 | LOW |
| 允許迴圈 | 全部（被動運行不限制迴圈） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 無（被動運行） |
| 觸發指令 | /profile、/user-model |
| 核心能力 | 畫像建構（知識水準/溝通偏好/決策風格/能量模式/專長）→ 個人化調適 → 偏好學習 |
| 與其他外掛 | dna27 Persona 旋鈕（固定軸 vs 動態微調）；deep-think（品質 vs 個人化）；eval-engine（滿意度代理校準）；knowledge-lattice（專長維度）；wee（能力成長維度） |

### persona-router (baihe) — 百合引擎軍師路由

| 屬性 | 值 |
|---|---|
| plus_id | PERSONA_ROUTER_BAIHE |
| 類別 | core-extension（非獨立 Skill，persona_router.py 的 v2 擴展） |
| 運行模式 | **常駐**——brain.py Step 3.65 自動執行，不需觸發 |
| 風險等級 | LOW（讀取 lord_profile.json 做決策，try/except 安全降級） |
| 允許迴圈 | 全部（常駐層不限制迴圈） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | lord_profile.json 存在（不存在時靜默降級） |
| 觸發指令 | 無（自動執行） |
| 核心能力 | 四象限軍師路由（Q1 全力輔助 / Q2 精準補位 / Q3 主動進諫 / Q4 靜默觀察）→ 進諫階梯（Tier 0-3）→ 表達模式映射 → system prompt 注入 |
| 資料來源 | `data/_system/lord_profile.json`（R：讀取領域強弱項，W：進諫冷卻寫回） |
| 與其他外掛 | user-model（User-Model 管「怎麼說」，lord_profile 管「什麼領域強/弱」）；c15（四象限表達模式切換）；deep-think Phase 0（戰略訊號觸發）；master-strategy（百合象限決定戰略姿態） |

---

## 七、演化與治理

### morphenix — 自我進化引擎

| 屬性 | 值 |
|---|---|
| plus_id | MORPHENIX |
| 類別 | self-evolution-engine |
| 風險等級 | MEDIUM-HIGH |
| 允許迴圈 | slow_loop（主，迭代需要深度思考） |
| 禁止迴圈 | fast_loop |
| 允許模式 | evolution_mode（主）；civil_mode（僅筆記記錄，不執行修改） |
| 入場條件 | 使用者主動觸發，或累積筆記達結晶閾值 |
| 觸發指令 | /morphenix、/phoenix、/evolve、/morphenix status、/morphenix log、/morphenix rollback {version}、/morphenix notes、/morphenix fitness |
| 核心能力 | 迭代筆記→結晶提案→L1/L2/L3 分級執行→版本回溯；三大護衛：安全區遞迴鎖、退化偵測、Skill 健康儀表板 |
| 與其他外掛 | eval-engine（迭代前後 A/B 驗證）；sandbox-lab（迭代前安全測試）；knowledge-lattice（已驗證知識支撐改動）；env-radar（演化方向→演化行動）；wee（中觀演化 vs 宏觀迭代） |

### wee — 工作流演化引擎

| 屬性 | 值 |
|---|---|
| plus_id | WEE |
| 類別 | workflow-evolution-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | exploration_loop（主）、slow_loop（深度破框） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 偵測到重複任務、效率瓶頸、流程僵化 |
| 觸發指令 | /workflow、/wee、/kata（對齊五問）、/review（結果萃取五問）、/diagnose（失敗五因）、/why-stuck、/proficiency |
| 核心能力 | 六層記憶耦合、三環教練迴路（啟動對齊 × 結果萃取 × 失敗診斷）、四維熟練度追蹤、逆熵破框 |
| 與其他外掛 | dna27 演化引擎（微觀 vs 中觀）；morphenix（中觀 vs 宏觀）；xmodel（破框掃描）；pdeif（流程設計→演化追蹤）；knowledge-lattice（演化知識結晶）；user-model（能力成長） |

### knowledge-lattice — 知識晶格引擎

| 屬性 | 值 |
|---|---|
| plus_id | KNOWLEDGE_LATTICE |
| 類別 | knowledge-crystallization-engine |
| 風險等級 | LOW |
| 允許迴圈 | 全部（知識結晶可在任何迴圈發生） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 對話中產生可結晶洞見，或使用者主動要求 |
| 觸發指令 | /lattice、/crystal、/knowledge、/crystallize、/recall、/atlas、/recrystallize |
| 核心能力 | Crystal Protocol（四類結晶 × GEO 四層 × 再結晶演算法）、Crystal Chain Protocol（CUID × DAG × 共振指數） |
| 與其他外掛 | dna27 六層記憶（存儲層 vs 精煉層）；morphenix（改動依據）；wee（演化知識結晶）；eval-engine（知識應用效果度量）；sandbox-lab（實驗結論結晶化）；env-radar（外部洞見結晶） |

### eval-engine — 效能儀表板

| 屬性 | 值 |
|---|---|
| plus_id | EVAL_ENGINE |
| 類別 | quality-measurement-engine |
| 風險等級 | LOW |
| 允許迴圈 | 全部（度量可在任何迴圈追加） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | morphenix 迭代前後自動調用；或使用者主動查詢 |
| 觸發指令 | /eval、/dashboard、/eval score、/eval trend、/eval compare、/eval blindspot |
| 核心能力 | 即時品質儀→趨勢追蹤器→A/B 比對器→盲點雷達 |
| 與其他外掛 | deep-think（即時品質 vs 長期度量）；morphenix（改什麼 vs 改了是否更好）；wee（工作流熟練度）；knowledge-lattice（知識應用效果）；qa-auditor（Q-Score vs T-Score） |

### sandbox-lab — 沙盒實驗室

| 屬性 | 值 |
|---|---|
| plus_id | SANDBOX_LAB |
| 類別 | experimentation-engine |
| 風險等級 | LOW（沙盒內隔離，不影響正式系統） |
| 允許迴圈 | exploration_loop（主）、slow_loop |
| 允許模式 | evolution_mode（主，實驗本質就是演化態） |
| 入場條件 | morphenix L2/L3 迭代前自動建議；或使用者主動啟動 |
| 觸發指令 | /sandbox、/lab、/sandbox prompt、/sandbox skill、/sandbox flow |
| 核心能力 | Prompt 沙盒（A/B 測試）→ Skill 沙盒（原型驗證）→ 流程沙盒（協作模擬） |
| 與其他外掛 | morphenix（正式迭代 vs 安全測試）；dse（技術可行性 vs 系統內部驗證）；eval-engine（正式品質 vs 實驗品質）；knowledge-lattice（實驗結論結晶化）；orchestrator（流程沙盒的編排邏輯） |

### orchestrator — 編排引擎

| 屬性 | 值 |
|---|---|
| plus_id | ORCHESTRATOR |
| 類別 | multi-skill-orchestration-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | exploration_loop（主）、slow_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | DNA27 路由偵測到需求涉及 3+ 個 Skill 時自動介入 |
| 觸發指令 | /orchestrate、/plan |
| 核心能力 | 任務分解→執行編排（串行/並行/條件分支）→銜接管理→衝突仲裁→回退備選 |
| 與其他外掛 | dna27（單次路由 vs 多步驟規劃）；sandbox-lab（流程沙盒編排邏輯）；wee（工作流演化 vs 即時編排）；eval-engine（旅程品質度量）；morphenix（共現矩陣最佳搭配數據）；qa-auditor（多 Agent 品質護欄） |

### qa-auditor — 品質審計引擎

| 屬性 | 值 |
|---|---|
| plus_id | QA_AUDITOR |
| 類別 | technical-quality-audit-engine |
| 風險等級 | LOW |
| 允許迴圈 | 全部（審計可在任何迴圈追加） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | Agent 完成開發後自動建議；或偵測到技術交付品質疑慮 |
| 觸發指令 | /qa、/audit |
| 核心能力 | 4D 審計框架（D1 邏輯功能、D2 狀態閉環、D3 時序併發、D4 跨機環境）、沙盒隔離、混沌測試、分級門禁（smoke/standard/full）、回歸沉澱 |
| 與其他外掛 | sandbox-lab（Skill/Prompt 實驗 vs 程式碼審計）；eval-engine（Q-Score vs T-Score）；orchestrator（Skill 編排 vs 多 Agent 品質護欄） |

---

## 八、產品線

### gap — 市場缺口分析引擎

| 屬性 | 值 |
|---|---|
| plus_id | GAP |
| 類別 | market-gap-analysis-engine |
| 風險等級 | LOW |
| 允許迴圈 | exploration_loop（主）、slow_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 使用者想找市場機會或評估 AI 產品需求 |
| 觸發指令 | /gap、/market-scan |
| 核心能力 | AI Agent/Skill 市場掃描（Claude Skills、GPTs、Coze、Dify 等）→ 機會清單產出 |
| 產線位置 | **GAP**（找缺口）→ DSE（技術驗證）→ ACSF（鍛造商品） |
| 與其他外掛 | dse（機會卡→技術驗證）；business-12（通用商業診斷 vs AI 市場缺口）；env-radar（環境雷達提供大環境脈絡） |

### dse — AI 技術融合驗證引擎

| 屬性 | 值 |
|---|---|
| plus_id | DSE |
| 類別 | ai-tech-fusion-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | slow_loop（主，九步驟需要深度展開）、exploration_loop（顧問模式快速評估） |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 有 AI 技術融合需求或可行性驗證需求 |
| 觸發指令 | /dse、/dse consult、/tech-fusion、/sota-check |
| 核心能力 | 九步驟工程方法論、技術組件拆解、SOTA 借鏡優化、專家四法驗證、架構+規格+程式碼輸出 |
| 產線位置 | GAP（找缺口）→ **DSE**（技術驗證）→ ACSF（鍛造商品） |
| 與其他外掛 | gap（機會卡輸入）；acsf（驗證方案→鍛造）；business-12（商業可行性交叉驗證）；sandbox-lab（技術可行性 vs 系統驗證） |

### acsf — 能力結晶與 Skill 鑄造引擎

| 屬性 | 值 |
|---|---|
| plus_id | ACSF |
| 類別 | skill-forge-engine |
| 風險等級 | MEDIUM |
| 允許迴圈 | slow_loop（主，鍛造需要完整展開） |
| 允許模式 | civil_mode（獨立/客戶模式）、evolution_mode（產線模式） |
| 入場條件 | DSE 流程完成後自動建議；或使用者主動要求 Skill 鍛造 |
| 觸發指令 | /acsf、/acsf standalone、/acsf client、/forge |
| 核心能力 | 能力萃取→結晶化→規格鍛造→品質驗證→商品包裝（SKILL.md + README + 範例輸出 + 銷售頁） |
| 產線位置 | GAP（找缺口）→ DSE（技術驗證）→ **ACSF**（鍛造商品） |
| 與其他外掛 | gap（機會卡）；dse（驗證方案）；business-12（市場定位）；eval-engine（品質基準線驗證） |

### env-radar — 環境雷達引擎

| 屬性 | 值 |
|---|---|
| plus_id | ENV_RADAR |
| 類別 | environmental-intelligence-engine |
| 風險等級 | LOW |
| 允許迴圈 | exploration_loop（主）、slow_loop |
| 允許模式 | civil_mode、evolution_mode |
| 入場條件 | 使用者詢問市場/競品/技術趨勢 |
| 觸發指令 | /radar、/scan、/env、/trend-ext、/competitor、/tech-radar、/signal |
| 核心能力 | PESTEL 環境分析、FACT 競爭情報、技術雷達四象限、弱訊號偵測；五種模式：全景/競品/技術/弱訊號/演化壓力 |
| 與其他外掛 | morphenix（演化方向→演化行動）；gap（AI 市場缺口 vs 環境大勢）；master-strategy（戰略判斷的環境情報）；knowledge-lattice（趨勢洞見結晶化） |

### report-forge — 付費級產業診斷報告鍛造引擎

| 屬性 | 值 |
|---|---|
| plus_id | REPORT_FORGE |
| 類別 | premium-report-production-engine |
| 風險等級 | LOW |
| 允許迴圈 | exploration_loop（展示版）、slow_loop（完整版） |
| 允許模式 | civil_mode（客戶交付）、evolution_mode（方法論迭代） |
| 入場條件 | 使用者要求產出產業診斷報告、深度分析報告、客戶交付物 |
| 觸發指令 | /report、/report [產業]、/forge-report、/diagnose [產業]、/report preview、/report full |
| 核心能力 | 七層報告結構（SCR→MECE→多視角→嵌入式案例→情境模擬→行動清單→暗示擴展）；三角驗證方法論（資料×方法論×研究者×理論）；HTML 品牌報告產出 |
| 產線位置 | DSE（方法論驗證）→ **Report-Forge**（報告生產）→ ACSF（商品化包裝） |
| 與其他外掛 | dse（方法論來源）；consultant-communication（結構工具：金字塔/MECE/SCQA）；business-12（診斷框架）；market-core（市場數據）；master-strategy（戰略推演）；storytelling-engine（案例敘事）；aesthetic-sense（美感審計） |

---

## 九、特殊模組

### tantra — 情慾治理引擎

| 屬性 | 值 |
|---|---|
| plus_id | TANTRA |
| 類別 | erotic-governance-engine |
| 運行模式 | **研究階段**——當前不在非授權情境下啟動 |
| 風險等級 | HIGH |
| 允許迴圈 | slow_loop（僅限研究與架構設計討論） |
| 禁止迴圈 | fast_loop、exploration_loop |
| 允許模式 | evolution_mode（研究態） |
| 入場條件 | 使用者明確啟動 + 未來成人版 AI 平台授權 |
| 觸發指令 | /tantra |
| 核心能力 | 四層架構：Eros（治理總則）→ Adult（狀態路由）→ Drive（深化引擎）→ Feral（極態辨識） |
| 與其他外掛 | resonance（情慾情境情緒承接）；shadow（情慾關係對抗偵測）；c15（情慾場景敘事張力） |

---

## 十、未部署 / 設計中

### meta-learning — 元學習引擎（未部署）

| 屬性 | 值 |
|---|---|
| 狀態 | available_skills 有描述，但 /mnt/skills/user/ 中無 SKILL.md |
| 預期類別 | meta-cognition-engine |
| 預期核心能力 | Feynman 教學驗證、Musk 第一性原理、Munger 心智模型晶格、Da Vinci 跨域好奇力、Taleb 反脆弱學習、Ericsson 刻意練習 |
| 預期銜接 | xmodel（跨域知識遷移）；business-12（學習路徑設計）；knowledge-lattice（學到的知識精煉） |
| 行動項 | 需鍛造部署 |

### info-architect — 資訊架構引擎（未部署）

| 屬性 | 值 |
|---|---|
| 狀態 | available_skills 有描述，但 /mnt/skills/user/ 中無 SKILL.md |
| 預期類別 | information-architecture-engine |
| 預期核心能力 | Apple 設計哲學 × 資料分類 × 結構設計 × 命名規範 × 美感審計 |
| 預期銜接 | aesthetic-sense（先美感判斷，後整理執行） |
| 行動項 | 需鍛造部署 |

---

## 外掛合約規範

所有外掛必須遵守：

**必須聲明**：
- 依賴 DNA27 核心
- 本模組職責（做什麼）
- 本模組不做（不做什麼）
- 與其他外掛的關係

**不可做**：
- 不可覆寫 Kernel 五大不可覆寫值（主權/真實/穩態/隱私/長期一致性）
- 不可繞過 Kernel 三大權力（硬停/降級/加條件）
- 不可自行定義迴圈或模式（使用 DNA27 核心的）
- 不可在對外輸出中暴露內部架構細節

**必須接受**：
- DNA27 核心的 RC 優先級（A > B > C > D > E）
- Kernel 護欄的否決權
- 狀態路由的入場/退場條件

---

## 外掛共存規則

- 同時啟用多個外掛時，各外掛的護欄取聯集（最嚴格者生效）
- 外掛之間不直接通訊，都通過 DNA27 核心路由
- 外掛的 RC 親和對照由各外掛自行定義，但禁止觸發清單取聯集
- 若兩個外掛對同一 RC 的處置衝突，以更保守的為準

---

## 外掛協作矩陣（完整版）

### 前置品質與決策支援組合

| 組合 | 適用情境 |
|---|---|
| query-clarity → roundtable | 標準路徑：問題品質確保 → 多角色交叉詰問 |
| query-clarity → deep-think | 雙重品質閘門：輸入品質 → 輸出品質 |
| roundtable + master-strategy + shadow | 重大決策的完整三角：陽謀 + 陰謀 + 鏡照 |
| roundtable + knowledge-lattice | 圓桌結論結晶化為可檢索知識 |
| roundtable + user-model | 仲裁歷史累積為使用者決策風格畫像 |

### 商業與戰略組合

| 組合 | 適用情境 |
|---|---|
| master-strategy + business-12 | 商業戰略決策（戰略判斷 + 12 力盤點） |
| master-strategy + ssa-consultant | 銷售談判（戰略心理 + 銷售流程） |
| master-strategy + xmodel | 複雜困局推演（戰略判斷 + 槓桿掃描 + 交換分析） |
| master-strategy + shadow | 人際戰略（陽謀 + 陰謀的完整判斷） |
| master-strategy + business-12 + xmodel | 重大商業決策的全方位推演 |
| business-12 + ssa-consultant | 商模弱項 + 銷售實戰的交叉診斷 |
| business-12 + ssa-consultant + brand-identity | 品牌定位 + 商模 + 銷售的完整閉環 |

### 思維轉化組合

| 組合 | 適用情境 |
|---|---|
| resonance → dharma | 標準路徑：感性承接 → 理性轉化 |
| dharma + pdeif | 思維轉化後的行動路徑設計 |
| dharma + philo-dialectic | 深層信念衝突需要哲學級探索 |
| xmodel + pdeif | 破框產生終點 → 逆推路徑 |
| master-strategy + pdeif | 戰略判斷 → 戰略落地為可執行流程 |

### 語言與創作組合

| 組合 | 適用情境 |
|---|---|
| text-alchemy → storytelling-engine | 說服影響類文字任務 |
| text-alchemy → novel-craft | 沉浸式敘事創作 |
| text-alchemy → consultant-communication | 商業文書 |
| storytelling-engine + novel-craft | 完整敘事：結構（說什麼）+ 質感（怎麼說） |
| consultant-communication + brand-identity | 品牌一致的商業溝通 |
| aesthetic-sense + brand-identity | 所有對外輸出的雙重品質閘門 |

### 演化堆疊

| 組合 | 適用情境 |
|---|---|
| deep-think → eval-engine | 每次品質控制 → 長期品質追蹤 |
| morphenix + eval-engine + sandbox-lab | 完整迭代週期：提案 → 沙盒測試 → A/B 驗證 |
| wee + knowledge-lattice | 工作流演化中的知識結晶 |
| orchestrator + qa-auditor | 多 Skill 編排 + 品質護欄 |
| env-radar → morphenix | 外部演化壓力 → 內部演化行動 |

### 產品線管線

| 組合 | 適用情境 |
|---|---|
| gap → dse → acsf | 完整產品線：找缺口 → 技術驗證 → 鍛造商品 |
| dse → report-forge → acsf | 報告產品線：方法論驗證 → 報告生產 → 商品包裝 |
| report-forge + consultant-communication | 報告結構（金字塔/MECE/SCQA）+ 產業深度 |
| report-forge + business-12 + market-core | 完整產業診斷：商業框架 + 市場數據 + 報告產出 |
| report-forge + storytelling-engine + aesthetic-sense | 報告品質三閘門：敘事 + 美感 + 方法論 |
| env-radar + gap | 環境大勢 + AI 市場缺口的交叉定位 |
| acsf + eval-engine | 鍛造後品質基準線驗證 |
| dse + sandbox-lab | 技術方案的系統內驗證 |

---

## 新增外掛指引

建立新外掛時：
1. 在外掛 SKILL.md 中宣告依賴 DNA27 核心
2. 定義 RC 親和對照（偏好/限制/禁止）
3. 定義允許的迴圈與模式
4. 定義入場條件
5. **在此註冊表中新增條目**（含 plus_id、類別、風險等級、迴圈、模式、入場、指令、能力、協作關係）
6. 確認與現有外掛的共存規則
7. 更新協作矩陣中的相關組合

---

## 變更紀錄

| 版本 | 日期 | 變更內容 |
|---|---|---|
| v1.0 | — | 初版，僅註冊 5 個外掛（xmodel、business-12、ssa-consultant、master-strategy、persona-chiqi） |
| **v2.0** | **2026-02-21** | **完整更新：新增 21 個外掛註冊（共 26 個）；新增 2 個未部署模組紀錄；重建完整協作矩陣（5 大類 20+ 組合）；新增常駐層/半常駐層分類；新增產線位置標記；新增變更紀錄** |
| **v2.1** | **2026-03-13** | **新增 2 個外掛（共 28 個）：query-clarity（常駐層，問題品質守門）、roundtable（按需，圓桌詰問引擎）；常駐層從 2→3 個；新增「前置與決策支援」類別與協作矩陣** |
| **v2.2** | **2026-03-18** | **新增 1 個外掛（共 29 個）：report-forge（產品線，付費級產業診斷報告鍛造引擎）；產品線管線新增 4 組協作組合** |
