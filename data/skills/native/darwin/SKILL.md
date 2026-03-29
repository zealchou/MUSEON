---
name: darwin
description: >
  DARWIN（DARWIN）— 策略模擬引擎。注入地區人口統計資料，生成具備 16 維能量屬性的
  數位人群原型（64-512 個），預測商業策略在 52 週內的演化與顯化結果。
  雙軌模式：自駕（使用者帶策略驗證）+ 代駕（MUSEON 設計最佳策略）。
type: workflow
layer: application
hub: market
status: active
version: 1.0.0
model_preference: opus
trigger_words:
  - DARWIN
  - 策略模擬
  - 模擬市場
  - 市場推演
  - 策略驗證
  - 幫我測試策略
  - 這個策略行不行
  - 跑一次模擬
  - 市場沙盤
  - 兵棋推演市場
  - 幫我設計策略
  - 營業額要提高
  - 我想知道這招有沒有用
  - /darwin
  - /simulate
  - /ares-market
io:
  inputs:
    - from: user
      field: city_and_strategy
      required: true
      description: 目標城市 + SMART 策略（自駕）或期望結果（代駕）
  outputs:
    - to: user
      field: simulation_dashboard
      trigger: on-complete
      description: 互動式 52 週儀表板 HTML
    - to: user
      field: final_report
      trigger: on-complete
      description: 八章戰情報告 HTML
    - to: knowledge-lattice
      field: simulation_crystal
      trigger: on-complete
      description: 策略模擬結果結晶
connects_to:
  - business-12
  - ssa-consultant
  - brand-builder
  - xmodel
  - pdeif
  - master-strategy
  - market-core
  - risk-matrix
  - knowledge-lattice
  - eval-engine
  - user-model
  - orchestrator
memory:
  writes:
    - target: knowledge-lattice
      type: simulation_crystal
      description: 52 週模擬結果 + 最佳策略組合 + 轉折點摘要
    - target: eval-engine
      type: accuracy_tracking
      description: 模擬預測 vs 真實結果的偏差率
stages:
  - id: setup
    name: 戰場設定
    description: 選定城市，爬五層數據，建數位雙生城市
    skills: []
  - id: coaching
    name: 策略引導
    description: 教練式提問收斂 SMART 策略（自駕）或訪談現況（代駕）
    skills: [ssa-consultant]
  - id: modeling
    name: 人群建模
    description: 數據→能量映射→聚類→命名，生成 64-512 個原型
    skills: []
  - id: strategy_design
    name: 策略設計（代駕限定）
    description: 商模健檢 + 品牌定位 + PDEIF 逆熵 + xmodel 破框，生成策略候選
    skills: [business-12, brand-builder, pdeif, xmodel]
  - id: simulation
    name: 52 週模擬
    description: 三股力量引擎跑 52 週，策略衝擊 + SIR 傳導 + 阻尼振盪
    skills: []
  - id: analysis
    name: 結果分析
    description: 每週洞察 + 轉折偵測 + 競爭者反應 + 生態夥伴態度
    skills: [market-core, risk-matrix]
  - id: optimize
    name: 策略優化（代駕限定，3 輪）
    description: 分析結果 → 優化策略向量 → 再跑模擬，反覆 3 輪
    skills: [business-12, master-strategy]
  - id: report
    name: 戰情報告
    description: 八章完整報告 + 互動式儀表板
    skills: [ssa-consultant, business-12]
speed_paths:
  fast: [setup, coaching, modeling, simulation, report]
  full: [setup, coaching, modeling, strategy_design, simulation, analysis, optimize, report]
---

# DARWIN DARWIN — 策略模擬引擎

## 核心能力

在投入真金白銀之前，先讓數位分身替你試一次。

輸入目標城市和商業策略，系統會：
1. 抓取真實人口數據，建造數位雙生城市
2. 生成 64-512 個行為原型（基於 One Muse 八方位能量系統）
3. 模擬策略在 52 週內的演化過程
4. 產出互動式儀表板 + 完整戰情報告

## 雙軌模式

### 自駕模式（使用者主導）
使用者帶著自己的策略進來驗證。
- 5-6 題教練式引導收斂 SMART 策略
- 可反覆跑 3-6 輪，調整策略看結果
- 指令：`/darwin` 或 `/simulate`

### 代駕模式（MUSEON 主導）
使用者只說目標，MUSEON 幫你設計最佳策略。
- 7-10 題三層訪談（SSA + 麥肯錫 + BCG）
- 自動生成 3-5 組策略候選
- 3 輪自動模擬 + 策略優化
- 指令：`/darwin chauffeur` 或「幫我設計策略」

## 技術架構

### 五層數據模型
- L1 地理基底（地形、交通、氣候）
- L2 人口結構（年齡、收入、家庭）
- L3 生活型態（POI 密度、消費模式）
- L4 事件脈動（政策、經濟、天災）
- L5 關係拓樸（產業鏈、社會階層）

### 能量映射
- 八方位 × 內在/外在 = 16 維能量向量
- 映射規則定義在 `mapping_config.yaml`

### 模擬引擎（三股力量）
- 力量一：策略衝擊（向量內積 × 敏感度）
- 力量二：社會傳導（SIR 模型 + 累積曝光）
- 力量三：能量擺盪（阻尼振盪，±4 極值反轉）

### Agent 三種
- 消費者原型（聚類自動生成，64-512 個）
- 競爭者 Agent（系統自動推算，會主動反應）
- 生態夥伴 Agent（配合度動態變化）

## 輸出

### 互動式儀表板（每週快照）
- 時間軸控制器（拖拉即更新）
- 商業指標面板（營業額、市佔率、鐵粉、口碑）
- 狀態分布圓餅圖
- 52 週趨勢折線圖
- 競爭動態 + 夥伴態度
- 白話洞察（LLM 生成）

### 最終戰情報告（八章）
1. Executive Summary（紅黃綠燈判定）
2. 52 週演化全景（Gartner 風格曲線）
3. 人群深度分析（突破口 + 阻力）
4. 商模十二力（12 力診斷）
5. 銷售路徑設計（SSA 成交路徑）
6. 風險與競爭分析
7. 創新傳播曲線定位（Rogers）
8. 行動建議（3 件立即可做）

## 程式碼位置

```
src/museon/darwin/
├── config.py               # 全域設定
├── crawler/                 # 數據爬蟲
├── mapping/                 # 數據→能量映射
├── clustering/              # 聚類引擎
├── simulation/              # 模擬引擎
├── metrics/                 # 商業指標換算
├── coaching/                # SMART 教練引導
├── analysis/                # 分析引擎
├── visualization/           # 視覺化（儀表板+報告）
└── storage/                 # SQLite 儲存
```

## 目前支援的城市

- 台南永康
- 台北信義
- 高雄鳳山

（未來可透過 API 擴充任意台灣城市）
