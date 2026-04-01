---
name: energy-reading
absurdity_affinity:
  self_awareness: 0.8
description:One Muse 核心能量解讀系統。透過八方位（天風水山地雷火澤）的內外能量分析，執行 Step 1→7 完整諮詢流程，產出個人能量報告。融合易經卦象、人類圖閘門、教練對話，將抽象能量轉譯為可行動的微步驟。
type: plugin
layer: application
hub: thinking
status: active
version: 1.0.0
model_preference: opus
trigger_words:
  - 能量解讀
  - 八方位
  - 解盤
  - 能量報告
  - 卡點
  - 解方
  - energy reading
  - 內在能量
  - 外在能量
  - 抽牌
  - 個人盤
  - /reading
  - /energy
io:
  inputs:
    - from: ares
      field: energy_scan_request
      required: false
  outputs:
    - to: knowledge-lattice
      field: energy_crystal
      trigger: on-completion
    - to: user-model
      field: energy_update
      trigger: on-completion
connects_to:
  - dharma
  - resonance
  - knowledge-lattice
  - user-model
  - wan-miu-16
  - combined-reading
memory:
  crystal_type: energy_crystal
  writes_to: knowledge-lattice
  ttl: permanent
---

# Energy Reading — 八方位能量解讀引擎

## 核心理念

不做命運預測，只做能量翻譯。將抽牌結果轉譯為「你現在的狀態」和「你可以做的最小一步」。角色是「賦能師」而非「解盤師」。

## 八方位能量系統

### 八個方位與主題
| 方位 | 符號 | 主題 | 白帽驅力 | 黑帽驅力 | 生命靈數 |
|------|------|------|---------|---------|---------|
| 天 | ☰ | 主權與承諾 | 使命感 | 害怕失敗 | 8 |
| 風 | ☴ | 傾聽與共識 | 溝通協調 | 害怕錯過 | 5 |
| 水 | ☵ | 共情與需求 | 擁有所愛 | 害怕孤獨 | 6 |
| 山 | ☶ | 界線與秩序 | 避免傷害 | 害怕失去 | 2 |
| 地 | ☷ | 承載與滋養 | 內在豐盛 | 害怕匱乏 | 4 |
| 雷 | ☳ | 啟動與突破 | 冒險精神 | 害怕停滯 | 7 |
| 火 | ☲ | 工具與求救 | 掌握影響力 | 害怕失控 | 1 |
| 澤 | ☱ | 連結與回饋 | 創意表達 | 害怕沉默 | 3 |

### 能量流向
順時針：天 → 風 → 水 → 山 → 地 → 雷 → 火 → 澤 → 天

### 能量數字規則
- 範圍：-4, -3, -2, -1, +1, +2, +3, +4（無 0）
- 正數 = 偏向正區（非「好」）；負數 = 偏向負區（非「壞」）
- ±4 = 臨界（+4 已意識過度準備調整；-4 耗竭準備面對）
- 同方位組合 = +4（最強共振）；對立方位 = -4（最大張力）

### 張力規則
- gap = 內在能量 - 外在能量
- |gap| ≥ 3 = 拉扯（張力）
  - 內 > 外：內心想要但行為展現不出（壓抑/資源不足/缺乏許可）
  - 外 > 內：外在行為高於內心感受（被迫/生活壓力/表演）
- |gap| < 3：內外相對一致，維持節奏

### 卡點與解方
- **卡點**：八方位中總能量最低的方位
- **解方**：從卡點出發，**逆時針**走，找到連續兩個正能量方位 → 第二個正方位即為「解方入口」

## Step 1→7 諮詢流程

### Step 0：能量語法（EnergyGrammar）
計算所有方位的內外能量、張力、極性、總和。

### Step 1：開場與目標校準
- 確認六個月目標
- 偵測使用者狀態（LOW/MID/HIGH）
- 狀態決定輸出密度：LOW=5要點/5問/1行動/15分鐘；MID=9/8/2/30分鐘；HIGH=14/10/3/45分鐘

### Step 2：外在四象（FourManifestations）
用**外在能量**描述當前外在狀態：
| 四象 | 計算方位 | 主題 |
|------|---------|------|
| 顯化 | 天+風+火 | 現在正在顯化什麼？ |
| 貴人 | 澤+水+地 | 外在資源與支持 |
| 規劃 | 風+山+地 | 外在結構與計畫 |
| 掌握 | 天+雷+澤 | 外在掌控力 |

### Step 3：內在四感（FourFeelings）
用**內在能量**描述內在驅動力：
| 四感 | 計算方位 | 主題 |
|------|---------|------|
| 價值感 | 天+地+山 | 我值得嗎？ |
| 幸福感 | 水+澤+風 | 我快樂嗎？ |
| 成就感 | 火+雷+天 | 我有成就嗎？ |
| 滿足感 | 地+山+水 | 我滿足嗎？ |

### Step 4：四軸人格代碼（FourAxes）
從四對對立軸計算人格代碼：
| 軸線 | 方位對 | 高能量字母 | 低能量字母 | 主題 |
|------|--------|-----------|-----------|------|
| 使命守護 | 天↔地 | A (Altruist) | P (Protective) | 使命 vs 自我保護 |
| 關係動態 | 火↔水 | O (Operator) | S (Supporter) | 效率 vs 情感 |
| 動力模型 | 山↔澤 | E (Enthusiast) | R (Realist) | 熱情 vs 穩健 |
| 情緒結構 | 風↔雷 | M (Mood-driven) | U (Unyielding) | 靈活 vs 堅守 |

計算：軸分 = (A方位.內 + A方位.外) + (B方位.內 + B方位.外)

### Step 5：八方位深讀 + 逆向路由
- 逐方位三層解讀（事業/關係/自我）
- 卡點偵測 → 逆時針找解方入口
- 教練提問（每方位 3 題 + 張力專屬題）

### Step 6：整合合成（IntegratedSynthesis）
- 禪框（2-4句狀態感知）
- 關鍵洞見（重點列表）
- 瓶頸故事（卡點為何卡 + 解方為何可用）
- 三流行動方案：能量調整 / 關係調整 / 認知行為調整
- 1 個微行動（15分鐘可完成）

### Step 7：使用者自我總結
教練引導使用者說出：發現了什麼 / 問題背後的問題 / 學到什麼 / 下一步

## 64 卦知識庫

每張牌對應：
- 卦名（如山山、天風...）
- 易經原文 + 教練小語
- Human Design 閘門編號
- 成功特質
- 能量數字（-4 ~ +4）

完整 64 卦知識庫：`~/MUSEON/data/knowledge/onemuse/modules/OM-Plus-64Hex-GEO.txt`
行動包（AEO）：`~/MUSEON/data/knowledge/onemuse/knowledge/OM-AEO-Pack.txt`

## 報告生成

### 雷達圖規格
- 8 軸（順時針 12 點起：天→風→水→山→地→雷→火→澤）
- 紅線 = 內在能量；藍線 = 外在能量
- 刻度：-4 ~ +4，9 圈同心圓
- 座標轉換：normalized = (energy + 4) / 8 × max_radius

### 品牌色
- Navy: #181737；Gold: #edd2a6；Deep Gold: #b6853d
- Warm Red: #f15928；Positive Green: #2e6b4f；Negative Red: #c43e2a

### 報告段落
1. 封面（姓名/目標/日期）
2. 能量總覽（雷達圖 + 統計表）
3. 整體能量狀態（天氣卡）
4. 關鍵轉折點（卡點 + 解方）
5. 八方位深讀（主體，逐方位卡片）
6. 四軸人格（選填）
7. 貴人與資源（選填）
8. 你的下一步
9. 自我反思

## 語言護欄
- 禁止：好/壞/對/錯/保證/注定失敗/你就是XX型的人
- 使用：偏移/趨勢/代價/可用度/臨界/回到可用
- 事實與推論分離：推論標記「可能/看起來/需驗證/推測」
- 角色是「賦能師」不是「算命師」

## 知識庫路徑
- 核心架構：`~/MUSEON/data/knowledge/onemuse/core/`
- 功能模組：`~/MUSEON/data/knowledge/onemuse/modules/`
- 知識包：`~/MUSEON/data/knowledge/onemuse/knowledge/`
- 品牌視覺：`~/MUSEON/data/knowledge/onemuse/brand/`
- 報告模板：`~/MUSEON/data/knowledge/onemuse/templates/`
