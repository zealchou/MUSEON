---
name: athena
absurdity_affinity:
  relationship_leverage: 0.8
  strategic_integration: 0.5
description: ATHENA（智慧戰略情報平台）— 個人戰略情報平台。編排 ANIMA 個體引擎、萬謬16型、合盤、九策軍師、陰謀辨識、八大槓桿等 Skill，產出人物分析、策略建議、多層槓桿路徑、連動模擬、戰前簡報。
type: workflow
layer: application
hub: thinking
status: active
version: 1.0.0
model_preference: opus
trigger_words:
  - 戰神
  - 策略分析
  - 幫我分析這個人
  - 談判策略
  - 攻略
  - 怎麼跟他談
  - 客戶攻略
  - 供應商談判
  - 合夥評估
  - 人才留任
  - 會前簡報
  - 槓桿交換
  - 多層佈局
  - 連動分析
  - 組織管理
  - 專案選人
  - 關鍵人物
  - /athena
  - /athena-person
stages:
  - id: identify
    name: 人物辨識
    description: 辨識目標人物，從 ANIMA 檔案庫載入或新建檔案
    skills: [anima-individual]
  - id: assess
    name: 人格能量評估
    description: 代理評估目標人物的萬謬16型人格 + 能量狀態
    skills: [wan-miu-16, energy-reading]
  - id: compare
    name: 合盤比對
    description: 使用者 vs 目標人物的能量合盤，找出共振/張力/分歧
    skills: [combined-reading]
  - id: strategize
    name: 策略生成
    description: 陽謀佈局 + 陰謀辨識 + 槓桿交換路徑
    skills: [master-strategy, shadow, xmodel]
  - id: design
    name: 流程設計
    description: 逆熵流程設計，把策略拆成可執行的接觸點序列
    skills: [pdeif]
  - id: verify
    name: 多視角驗證
    description: 圓桌詰問確保策略沒有盲點
    skills: [roundtable]
  - id: output
    name: 產出
    description: 生成戰前簡報、策略報告、關係圖
    skills: [anima-individual, c15]
speed_paths:
  quick:
    description: 快速戰前簡報（已有檔案的人物）
    stages: [identify, output]
    estimated_time: 2min
  standard:
    description: 標準策略分析
    stages: [identify, assess, compare, strategize, output]
    estimated_time: 15min
  full:
    description: 完整策略佈局（含流程設計+多視角驗證）
    stages: [identify, assess, compare, strategize, design, verify, output]
    estimated_time: 30min
io:
  input:
    - 目標人物名稱或描述
    - 互動場景/目標（必填：你想達成什麼？）
    - 場域標籤（商業/內部/私人）
  output:
    - 人物分析報告（七層鏡像摘要）
    - 策略建議（陽謀+陰謀辨識+槓桿交換）
    - 戰前簡報（一頁文字版）
    - 行動流程（逆熵接觸點序列）
    - 關係圖 PNG（靜態拓樸圖）
connects_to:
  - anima-individual
  - wan-miu-16
  - energy-reading
  - combined-reading
  - master-strategy
  - shadow
  - xmodel
  - pdeif
  - roundtable
  - business-12
  - ssa-consultant
  - knowledge-lattice
  - user-model
  - c15
memory:
  crystal_type: strategy_crystal
  writes_to: knowledge-lattice
  ttl: permanent
---

# Ares — ATHENA

## 核心理念

知己知彼，不是為了打贏對方，是為了找到雙方都能接受的最佳路徑。
Ares 是 MUSEON 的個人戰略情報平台——一個比你更記得身邊每個人是誰、要什麼、怕什麼的策略幕僚。

## 核心迴路

```
知己（我的人格 + 我的八大槓桿資源）
  ↕ 合盤比對
知彼（對方人格分析 + 對方八大槓桿資源）
  ↓
策略生成（陽謀佈局 + 陰謀辨識 + 資源交換路徑）
  ↓
逆熵流程設計（把策略拆成可執行的接觸點序列）
  ↓
執行後回饋 → 更新雙方畫像 → 下一輪更精準
```

## 三個場域

### 1. 組織內部管理
- 專案選人（能量盤匹配方位到角色）
- 關鍵人物辨識（誰是承載者/影響力核心）
- 職務適配診斷
- 員工能量預警（趨勢追蹤）
- 團隊合盤（張力/互補分析）

### 2. 商業外部
- 客戶攻略（代理評估→合盤→策略→槓桿交換）
- 供應商談判（窗口角色判斷→量價方案→節奏設計）
- 合夥評估（四軸衝突定位→角色分配）
- 人才留任（人格驅力分析→精準留人方案）
- 會前簡報（人格+溫度+建議+禁忌+槓桿）

### 3. 私人關係
- 伴侶經營（合盤→結構性張力→互補轉化）
- 追求建議（用對方語言展現真實自己）
- 禁忌清單

## 多層槓桿佈局

支援 2-4 層間接路徑搜尋：
```
第一層（直接）：我 → 目標
第二層（借力）：我 → 中間人 → 目標
第三層（造勢）：我 → A → B → 目標
第四層（佈局）：我 → A → B → C → 目標
```

每條路徑評估：成功率、時間成本、風險（洩漏/變卦可能性）。

## 連動模擬

策略下去後，拓樸圖上哪些節點受影響：
- 對每個受影響人物用人格模型預測反應
- 產出預防策略建議
- 標記風險等級

## 指令

| 指令 | 說明 |
|------|------|
| `/athena {人名}` | 快速戰前簡報（已有檔案）|
| `/athena 分析 {人名}` | 標準策略分析 |
| `/athena 完整 {人名}` | 完整策略佈局 |
| `/athena 建檔 {人名}` | 新建人物檔案 |
| `/athena 更新 {人名}` | 更新互動記錄 |
| `/athena 關係圖` | 生成人物拓樸圖 PNG |
| `/athena 路徑 {起點} → {終點}` | 多層槓桿路徑搜尋 |
| `/athena 連動 {事件描述}` | 策略連動模擬 |
| `/athena 團隊 {專案描述}` | 組織管理/專案選人 |

## 與既有 Skill 的編排

| 階段 | 調用 Skill | 目的 |
|------|-----------|------|
| 人物辨識 | anima-individual | 載入/建立個體檔案 |
| 人格評估 | wan-miu-16 (代理模式) | 16型人格代碼 + 置信度 |
| 能量掃描 | energy-reading (代理模式) | 八方位能量狀態 |
| 合盤比對 | combined-reading | 我 vs 對方互動狀態 |
| 陽謀策略 | master-strategy | 九策軍師佈局 |
| 陰謀辨識 | shadow | 防禦建議 + 博弈模式 |
| 槓桿交換 | xmodel | 八大槓桿資源路徑 |
| 商業診斷 | business-12 | 商業情境適配 |
| 銷售話術 | ssa-consultant | 具體話術建議 |
| 流程設計 | pdeif | 逆熵接觸點序列 |
| 多視角驗證 | roundtable | 策略盲點檢查 |
| 結晶累積 | knowledge-lattice | 關係/策略結晶 |
| 語言品質 | c15 | 敘事張力 |

## 語言護欄

- 禁止操控性建議（「怎麼讓對方聽話」）
- 禁止傷害性策略（「怎麼整他」）
- 強調互利共贏、雙方都能接受的路徑
- 代理評估必須標明置信度和資料來源
- 推測與觀察分離
- 所有專有名詞附白話解釋
