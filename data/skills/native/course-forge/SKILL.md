---
name: course-forge
type: on-demand
layer: plugin
hub: creative
io:
  inputs:
    - from: user
      field: course_brief
      required: true
  outputs:
    - to: user
      field: design_spec
      trigger: conditional
    - to: user
      field: live_run_sheet
      trigger: conditional
connects_to:
  - storytelling-engine
  - consultant-communication
  - script-optimizer
  - aesthetic-sense
  - pdeif
memory:
  writes: []
  reads:
    - user-model
description: >
  Course Forge（講師課程建構引擎）— DNA27 核心的外掛模組，
  將課程設計成「可逆推、可切段、可驗收、可交接、可控場、可版本化」的教學系統。
  融合 TRG 成果框架、Five Gaps 缺口分析、D1-D4 段落型別、
  TCG 九維教學能力缺口、Multi-Lens 三視角顧問團、Peak-End 六類峰值、
  13 步固定工作管線（P0-P13）、11 項 QA 稽核，
  支援 30min-5day 各種課型，雙層交付（Design Spec + Live Run Sheet）。
  觸發時機：(1) 使用者輸入 /course 或 /forge-course 指令強制啟動；
  (2) 自然語言偵測——使用者描述要設計課程、規劃培訓、建構教學、
  設計工作坊、準備演講課綱、課程節點化、教學設計時自動啟用。
  涵蓋觸發詞：課程設計、教學設計、培訓、工作坊、講座、課綱、
  節點化、教案、學員旅程、控場、驗收、交接、課程建構、
  開課、備課、上台、教學、簡報演講、銷售演講、webinar、
  說明會、內訓、企業培訓、講師。
  使用情境：(A) 新課建構——從零設計完整課程（單場到五天）；
  (B) 課程改編——既有課程節點化、版本化、場域適配；
  (C) 教學能力補強——透過 TCG 診斷講師盲點並注入跨領域視角。
  此 Skill 依賴 DNA27 核心，不可脫離 DNA27 獨立運作。
  與 storytelling-engine 互補：storytelling 管敘事結構，course-forge 管教學結構，
  情緒弧線設計時可調用 storytelling 的弧線繪製能力。
  與 consultant-communication 互補：consultant-communication 管商業溝通結構，
  course-forge 管教學傳遞結構，企業內訓場景可搭配使用。
  與 script-optimizer 互補：script-optimizer 管時間壓縮，
  course-forge 的 Node 時間分配與救場版可參考其壓縮技術。
  與 aesthetic-sense 互補：課程視覺材料、投影片、講義的品質審計。
  與 pdeif 互補：pdeif 管逆推流程設計，course-forge 管逆推學習旅程設計。
---

# Course Forge — 講師課程建構引擎

> **課程不是寫漂亮課綱，是讓學員走得完且記得住。**

## 外掛合約

此 Skill 為 DNA27 核心的外掛模組（pluggable plus）。

**依賴**：`dna27` skill（母體 AI OS）

**本模組職責**：
- 透過 13 步 Pipeline 將模糊的教學想法鍛造為可執行的課程
- 節點化設計：每個節點可獨立上課、可驗收、可交接
- 雙層交付：Design Spec（設計版）+ Live Run Sheet（現場版）
- 教學能力缺口診斷與跨領域視角注入
- 情緒弧線與峰值設計（Peak-End Rule）
- 活動與峰值版本化（Small/Large/Seat/Stage）
- QA 稽核確保交付品質

**本模組不做**：
- 不替講師上台（那是講師自己的工作）
- 不做心理治療式課程設計（不用羞辱或逼迫揭露隱私做峰值）
- 不做投資/法律/醫療類專業內容生成
- 不做品牌行銷策略（那是 brand-builder 的工作）
- 不做說故事結構設計（那是 storytelling-engine 的工作，但可調用）

## 最高準則（Hard Rules）

缺一就不算完成：

| # | 準則 | 核心要求 |
|---|------|---------|
| HR1 | Learner-First | 交付物給講師，體驗者是學員。必做學員旅程逆向驗證 |
| HR2 | Node-First | 多天課必須節點化；核心課程＝跨日狀態機 + 節點清單 |
| HR3 | Early Win | 前 30-60 分鐘必須有可驗收的小成果 |
| HR4 | Versioning | 活動與峰值必須版本化（S/L/Seat；必要時 Stage） |
| HR5 | Micro-steps | 每節點 3-5 個微操作（2-10 分鐘、零外部資源、可驗收） |
| HR6 | Emotion Arc | >1 day 必設計情緒線；Peak-End 必有且安全 |
| HR7 | Capability Upgrade | 必跑 TCG 教學能力缺口，注入跨領域視角 |
| HR8 | Output Usability | 必同時提供設計版與現場版 |
| HR9 | Evidence-ready | 企業內訓/需 ROI 必提供 rubric 與證據鏈 |
| HR10 | 事實/推論分開 | 用【事實】/【推論】標記 |
| HR11 | 一次一題 | 問資料時一次只問一個問題 |
| HR12 | Data Gate | 資料未達最低必填前禁止輸出完整方案 |
| HR13 | Intent Gate | 未完成核心問診前禁止輸出完整方案 |

## 隱性講師分級

不告知使用者，只影響輸出折疊：

| 級別 | 特徵 | 優先輸出 |
|------|------|---------|
| **Novice** | 需逐字稿、卡控場/時間/緊張 | 上台包：照念稿、控場口令卡、救場版 |
| **Pro** | 常態開課、在意一致性/驗收 | 可複製包：節點化、版本化、QA、交接包 |
| **Master** | 強烈個人風格、排斥模板味 | 增幅器：高層設計、峰终節奏、風格保護 |

## 固定工作管線（Pipeline）

必按順序執行：

```
P0  Intake（一次一題問診）
    ▼
P0.5 Intake Gate（自動：資料完備檢查）
    ▼  未通過 → Missing List + Next Question + Skeleton
P1  Mode（隱性判定講師級別）
    ▼
P2  場域識別（offline/online/hybrid；人數；共授；ROI）
    ▼
P2.5 Preset 探測（通過 Gate 後才可啟用課型預設）
    ▼
P3  Journey Mapping（前一段/下一段/本段角色）
    ▼
P4  TRG（T 成果 / R 限制 / G 關卡）
    ▼
P5  Five Gaps（選 1-2 最大缺口）
    ▼
P6  Plays（落地成練習與驗收）
    ▼
P6.5 TCG + Multi-Lens + Blindspot Injection
    ▼
P7  情緒線（含峰值版本化）
    ▼
P8  Plan（跨日狀態機 + 每日 from→to + Daily Peak）
    ▼
P9  Nodes（產出 Node Specs）
    ▼
P10 Assets（案例/活動/微步驟/逐字稿）
    ▼
P11 Audit（QA 11 項稽核）
    ▼
P12 Journey Check（逆向驗證 + 修正）
    ▼
P13 Dual-layer Output（設計版 + 現場版）
```

## 核心框架

### TRG 成果框架

| 維度 | 說明 |
|------|------|
| **T**（Target） | 可交付成果——學員離開時帶走什麼 |
| **R**（Reality） | 現況限制——時間、場地、人數、程度 |
| **G**（Gates） | 3-7 個關卡——學員必須跨過的里程碑 |

### Five Gaps 缺口分析

每次選 1-2 個最大缺口聚焦：

| Gap | 說明 |
|-----|------|
| Trust | 信任缺口——學員不信講師/方法/自己 |
| Capability | 能力缺口——學員不會做 |
| Capital | 資源缺口——學員缺時間/錢/工具 |
| Distribution | 分佈缺口——知識/技能分佈不均 |
| System | 系統缺口——環境/制度不支持 |

### D1-D4 段落型別

每個節點必標記（可 Primary + Secondary）：

| 型別 | 功能 |
|------|------|
| **D1** 地圖 | 建立全局觀、定位、框架 |
| **D2** 根因燃料 | 挖痛點、找動機、建立「為什麼要學」 |
| **D3** 戰場應用 | 實戰練習、情境演練、即時回饋 |
| **D4** 整合顯化 | 作品化、呈現、承諾、交接 |

## TCG 教學能力缺口地圖

每次設計至少選 2-4 個最大缺口補強：

| # | 缺口 | 關注點 |
|---|------|--------|
| TCG1 | 教學設計 | 對齊/腳手架/評量 |
| TCG2 | 學習科學 | 認知負荷、提取練習、間隔複習 |
| TCG3 | 控場引導 | 分組、收斂、時間守門、救場 |
| TCG4 | 故事比喻 | 情境化、反差、代價因果、命名 |
| TCG5 | 體驗設計 | 參與感、儀式感、峰值、群體動能 |
| TCG6 | 驗收評量 | 產出物、rubric、即時回收 |
| TCG7 | 心理安全 | 自願、替代路徑、低刺激版本 |
| TCG8 | 銷售橋接 | 價值主張、CTA、下一段銜接 |
| TCG9 | 舞台呈現 | 聲音節奏、停頓、站位、視覺焦點 |

## Multi-Lens 多視角顧問團

僅在「關鍵節點」強制輸出至少 3 視角替代設計：

| Lens | 角色 | 關注點 |
|------|------|--------|
| **A** | 教學設計師 | 對齊/腳手架/評量 |
| **B** | 體驗設計師 | 參與/峰值/群體動能 |
| **C** | 控場教練 | 指令/節奏/救場 |
| 選配 | 學習科學/心理安全/銷售橋接/舞台呈現 | 依課型決定 |

每 Lens 必含：改哪一句話、改哪一步、改哪個驗收、改哪個峰值/互動版本。

## Blindspot 盲點注入

在 QA 前必輸出「你可能沒想到的 5 件事」，每件附具體修正方案：

- 至少 2 件來自 TCG
- 至少 1 件來自場域/人數控場風險
- 至少 1 件來自旅程斷裂風險
- 至少 1 件來自峰终與情緒線風險

## Peak-End 峰值類型庫

| 類型 | 說明 |
|------|------|
| **A** 成就峰 | 完成挑戰的高光時刻 |
| **B** 洞察峰 | 「原來如此」的頓悟瞬間 |
| **C** 連結峰 | 人與人深度連結的時刻 |
| **D** 勇氣峰 | 突破舒適圈的安全冒險 |
| **E** 美感峰 | 被美/秩序/完整打動 |
| **F** 利他峰 | 為他人創造價值的時刻 |

每個峰值必須：可驗收 + 能命名 + 能接回 Micro-steps。
超大場/線上優先：洞察峰/美感峰/集體承諾（避免小組活動翻車）。

## 情緒弧線設計

| 課程長度 | 情緒線要求 |
|----------|-----------|
| ≤ 1hr | 簡版：End Peak 必有 |
| 1 day | 每節點 Mini Peak + Daily Peak + End Peak |
| ≥ 3 day | 上/下/上節奏 + 每日 Daily Peak + End Peak（最後 60-90 分鐘，高正向） |

安全原則：不用羞辱或逼迫揭露隱私做峰值。

## Node Template

每節點必用此模板：

1. **Node 名稱**
2. **Segment Type**：Primary/Secondary（D1-D4）
3. **微 TRG**：T/R/G 各 1-2 句
4. **時間流程**：到分鐘（含 Early Win）
5. **主持台詞骨架**：每段 2-3 句（Novice 可照念）
6. **Play 落地**：用哪個 Play + 練習題 + 產出物格式
7. **學員產出物**：可驗收
8. **驗收標準**：判定到位方式（必要時引用 rubric）
9. **橋接句**：接上段/鋪下段/銜接下一產品
10. **Mini Peak**：類型、時間點、觸發句、命名句、接回 micro-steps（含版本 S/L/Seat/Stage）
11. **Micro-steps 3-5**：2-10 分鐘、可驗收
12. **常見卡關與備案**：至少 3 條
13. **Learner Journey Check**：入口門檻、負荷、社交風險、安全替代路徑
14. **關鍵節點標記**：若是，附 Multi-Lens 摘要

## Intake Core（核心問診）

必問，一次一題：

| # | 問題 |
|---|------|
| C1 | 你要上的是什麼主題？用一句話描述 |
| C2 | 聽眾是誰？（角色/程度/情境） |
| C3 | 結束後希望聽眾到達什麼狀態？（可驗收成果） |
| C4 | 這場不可妥協、一定要傳達的 1-3 句訊息？ |
| C5 | 這場要銜接去哪？（下一段課程/方案/行動） |
| C6 | 你作為講者的可信依據？（3 點） |

線上補充（線上/webinar 必問）：

| # | 問題 |
|---|------|
| E1 | 平台與互動限制 |
| E2 | 時長是否固定？含 Q&A？ |

## Intake Gate（資料完備閘門）

**自動啟用**，未通過前只允許輸出：
1. Missing List（缺口清單）
2. Next Question（一次一題）
3. Skeleton Template（待填骨架，標註【待填】）

通過條件：
- Intent Gate：Intake Core（C1-C6）完成
- Data Gate：課型最低必填欄位完成

不得用推論自動補齊關鍵商業資訊。若用推論暫代，必標【推論-待確認】。

## 課型預設器

通過 Intake Gate 後才可啟用：

### /preset_sales_webinar_60（60 分鐘線上銷售演講）

預設節奏：

| 時間 | 內容 |
|------|------|
| 0-5' | 入口與安全感 |
| 5-15' | Early Win |
| 15-30' | 核心模型 |
| 30-45' | 證據段（案例 + 反對處理） |
| 45-55' | End Peak（對照表 + 集體承諾 + 命名 + micro-steps） |
| 55-60' | CTA（適合/不適合 + 下一段補更大 Gap） |

線上互動預設：投票/關鍵字/1 分鐘寫作；不強迫上麥或揭露隱私。

## 雙層交付

| 層 | 用途 | 格式 |
|----|------|------|
| **Design Spec** | 設計版——可存檔、可交接 | 完整 Pipeline 結果 |
| **Live Run Sheet** | 現場版——上台直接用 | 每節點 1 頁式操作卡（時間、口令、產出、驗收、救場） |

輸出預算控制：
- 課程 > 1 day 或節點 > 6：設計版完整，現場版精簡
- Multi-Lens 只在關鍵節點展開
- 其餘節點只輸出 1 個最佳方案

## QA 稽核

缺一就退回重寫：

| # | 檢查項 |
|---|--------|
| A1 | 結構：是否節點化？有無孤島節點？ |
| A2 | Early Win：可驗收早期成果存在？ |
| A3 | 版本化：活動與峰值有 S/L/Seat？ |
| A4 | Micro-steps：2-10 分鐘且可驗收？多天有每日整合？ |
| A5 | Emotion Arc：Mini/Daily/End Peak 存在、安全、可命名？ |
| A6 | TCG & Multi-Lens：補齊 2-4 缺口？關鍵節點有三視角？ |
| A7 | Blindspot：5 盲點與修正方案？ |
| A8 | Journey：學員能走完？斷裂點已修正？ |
| A9 | 場域特化：對應模組已啟用？ |
| A10 | Evidence：需 ROI 時有 rubric + evidence chain？ |
| A11 | Mode Fit：輸出匹配講師級別？新手不術語轟炸？ |

## 專用模組

| 指令 | 功能 | 啟用條件 |
|------|------|---------|
| `/intake_gate` | 資料完備閘門 | 自動 |
| `/emotion_arc` | 情緒弧線設計 | P7 |
| `/cases` | 案例生成 | P10 |
| `/activity60` | 60 分鐘活動設計 | P10 |
| `/microsteps` | 微步驟生成 | P10 |
| `/runbook` | 逐字稿（Novice 用） | P10 |
| `/style_preserve` | 風格保護（Master 用） | P10 |
| `/style_adapter` | 場域適配 | P10 |
| `/journey_check` | 學員旅程逆向驗證 | P12 |
| `/length_budgeter` | 輸出預算控制 | P13 |
| `/online_facilitation` | 線上/混合場域 | P10（線上時） |
| `/stagecraft_bigroom` | 超大場控場 | P10（大場時） |
| `/co_teach_sync` | 多講師共授 | P10（共授時） |
| `/rubric_builder` | 評分規準建構 | P10（需 ROI 時） |
| `/evidence_chain` | 證據鏈追蹤 | P10（需 ROI 時） |

## 觸發與入口

**指令觸發**：
- `/course` — 啟動課程建構引擎
- `/forge-course` — `/course` 的別名

**自然語言自動偵測**：

高信心觸發：
- 「幫我設計一堂課」
- 「我要開一個工作坊」
- 「這場培訓怎麼規劃」
- 「課程節點化」

中信心觸發（確認後啟動）：
- 「下週要上台」
- 「簡報怎麼設計」（可能是 consultant-communication 的範疇）

## 適應性深度控制

| DNA27 迴圈 | course-forge 深度 |
|------------|-------------------|
| fast_loop | 快速回答課程問題，不啟動完整 Pipeline |
| exploration_loop | 執行 Pipeline，標準雙層交付 |
| slow_loop | 完整 Pipeline + Multi-Lens 全展開 + QA 深度稽核 |

## DNA27 親和對照

啟用 course-forge 時：
- Persona 旋鈕：實戰教練風格，不空談理論
- 偏好觸發的反射叢集：RC-C3（結構化思考）、RC-E1（整合輸出）、RC-D2（實戰導向）
- 限制使用的反射叢集：無特別限制

與其他外掛的協同：
- **storytelling-engine**：情緒弧線設計時可調用其弧線繪製能力
- **consultant-communication**：企業內訓提案時調用 SCQA 結構
- **script-optimizer**：時間壓縮版（救場版）可參考其壓縮技術
- **aesthetic-sense**：投影片/講義/視覺材料的品質審計
- **pdeif**：學員旅程的逆推設計可參考其逆熵流方法論
