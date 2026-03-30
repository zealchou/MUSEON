---
name: onemuse-core
description: >
  One Muse 核心知識引擎 — MUSEON 所有能量系統的源頭方法論。
  統一管理八方位能量系統、四軸線、64 卦象行為模型、顯化法則、能量擺盪規則、
  先鋒/追隨者分類邏輯、數據→能量映射規則等核心知識。
  是 energy-reading、wan-miu-16、combined-reading、DARWIN、ATHENA 的共同知識根。
type: plugin
layer: core
hub: thinking
status: active
version: 1.0.0
model_preference: opus
trigger_words:
  - One Muse
  - 八方位
  - 能量系統
  - 天風水山地雷火澤
  - 八卦能量
  - 能量循環
  - 顯化法則
  - 萬謬
  - 四軸線
  - 能量映射
  - 先鋒定義
  - 卡點與解方
  - 能量擺盪
  - 內在外在能量
  - /onemuse
  - /om
io:
  inputs:
    - from: user
      field: onemuse_query
      required: false
      description: 關於 One Muse 體系的任何問題
  outputs:
    - to: energy-reading
      field: primal_definitions
      trigger: on-request
      description: 八方位定義、能量值域、循環規則
    - to: wan-miu-16
      field: axis_definitions
      trigger: on-request
      description: 四軸線定義、16 型人格基礎
    - to: combined-reading
      field: interaction_rules
      trigger: on-request
      description: 能量交互規則、合盤邏輯
    - to: darwin
      field: energy_mapping_rules
      trigger: on-request
      description: 八方位→統計數據映射、先鋒分類、能量擺盪參數
    - to: athena
      field: primal_behavior_model
      trigger: on-request
      description: 八方位行為動力學、人格能量解讀
    - to: knowledge-lattice
      field: onemuse_crystal
      trigger: on-update
      description: One Muse 知識結晶（新洞見/修正）
    - to: talent-match
      field: eight_directions_model
      trigger: on-request
      description: 八方位能量模型、人格特質分類規則，供人才評估使用
connects_to:
  - energy-reading
  - wan-miu-16
  - combined-reading
  - darwin
  - athena
  - knowledge-lattice
  - user-model
  - dna27
memory:
  writes:
    - target: knowledge-lattice
      type: onemuse_crystal
      description: One Muse 方法論更新、新洞見、映射規則修正
---

# One Muse 核心知識引擎

## 定位

One Muse 是 MUSEON 所有能量相關系統的**源頭方法論**。它不是一個獨立功能，而是一套知識體系——由創辦人 Zeal 在服務 600+ 位企業主的實戰中淬煉出來的。

```
One Muse（源頭方法論）
    ├── energy-reading（個人能量解讀）
    ├── wan-miu-16（16 型人格分析）
    ├── combined-reading（合盤比對）
    ├── DARWIN（市場策略模擬）← 用八方位映射統計數據
    └── ATHENA（個人戰略情報）← 用八方位解讀人物
```

## 核心知識體系

### 一、八方位能量系統

順時針循環：**天→風→水→山→地→雷→火→澤→天**

| 方位 | 核心驅力 | 白帽（正向） | 黑帽（負向） | 強時 | 弱時 |
|------|--------|------------|------------|------|------|
| 天 | 目標、引領、行為破框 | 使命感 | 恐懼失敗 | 領導者 | 追隨者 |
| 風 | 適應、溝通、成交 | 稀缺性 | 害怕錯失 | 鬥士 | 導演 |
| 水 | 關係、照顧、連結 | 擁有所愛 | 害怕孤立 | 協調者 | 獨裁者 |
| 山 | 累積、復盤、紀律 | 避開危害 | 害怕損失 | 策略家 | 藝術家 |
| 地 | 穩定、承載、資產運用 | 內在豐盛 | 恐懼匱乏 | 守護者 | 自護者 |
| 雷 | 覺察、認知破框 | 冒險 | 害怕停滯 | 開拓者 | 守舊派 |
| 火 | 展現、趨勢觀察、個人投入 | 掌握影響力 | 害怕失控 | 追尋者 | 隱士 |
| 澤 | 點燃、社群、品牌、感染 | 從創造出發 | 害怕沉寂 | 鼓舞者 | 破壞者 |

### 二、核心法則

**卡點法則**：某方位卡住，解方在逆時針回推兩個方位。不是當下的問題，而是前兩步的能量沒補好。

**能量擺盪**（600+ 個案觀察）：
- ±4 極值即將反轉
- 反轉週期：2 週 ~ 3 個月（極端可達 12 個月）
- +4 不代表好，-4 不代表差——都是即將反轉的信號
- 能量好 ≠ 有做事，能量好 = 做對應事情時心情順流

**內外在**：
- 內在 = 初衷、潛意識、能量狀態（權重遠大於外在）
- 外在 = 行為表現、他人眼中的投射
- 內在正 → 吸引人靠近 → 外在跟著好
- 內在負 → 貴人迴避 → 外在持續惡化

### 三、火與澤的區分（關鍵，常混淆）

- **火**：從自己出發往外參與。觀察趨勢、研究市場、個人投入。「我去看世界」
- **澤**：有意識地聚集同好、影響他人。自媒體、社群經營、品牌傳播、KOL。「我把世界拉過來」
- **自媒體/行銷/社群/品牌 = 澤，不是火**

### 四、先鋒定義（One Muse 獨到洞見）

Rogers 創新傳播理論的 13.5% 早期採用者（先鋒），在 One Muse 體系中的定義：
- **火高**：被新奇有趣好玩的事物吸引
- **澤高**：願意在人群中主動拉攏人

**不是**天高+雷高。天+雷高的是 2.5% 的發明家/純創新者——他們創造新事物，但不一定會帶動別人。先鋒是「哇這個好酷我要試，而且我會跟朋友說」的人。

### 五、八方位→統計數據映射（DARWIN 用）

| 方位 | 可觀察指標（外在） | 推導指標（內在） |
|------|-----------------|--------------|
| 天 | 創業率、戶外活動場所、政治參與 | 志工組織、社團數 |
| 風 | 業務職占比、合夥企業、企業存活率 | 結婚率、調解成功率 |
| 水 | 戶均人口、離婚率（反向）、生育率 | 照護機構、長照密度 |
| 山 | 健身房、高檔餐廳、宗教場所 | 儲蓄率、保險投保率 |
| 地 | 戶均所得、房屋自有率、連鎖店密度 | 人口密度（上下文）、被動收入 |
| 雷 | 身心靈課程、藝文活動、次文化社群 | 冥想搜尋趨勢、心理諮商密度 |
| 火 | 展覽/講座參與率、進修課程 | 訂閱制使用率、市調公司密度 |
| 澤 | 咖啡廳/百貨密度、自媒體創作者 | 社群互動率、KOL 密度、品牌店密度 |

### 六、四條對軸

- 天-地（目標-穩定）
- 風-雷（適應-覺察）
- 火-水（展現-關係）
- 山-澤（累積-點燃）

### 七、事業能量循環

雷（研發）→ 火（趨勢對接）→ 澤（社群傳播）→ 天（銷售成交）→ 風（客戶跟進）→ 水（售後服務）→ 山（復盤累積）→ 地（系統建構）→ 回到雷

## 知識來源

```
data/knowledge/onemuse/
├── core/          # 核心規範（OM-DNA-Kernel, Router, Protocols）
├── modules/       # 解盤模組（八方位/四軸線/64卦/顯化步驟）
├── knowledge/     # 知識包（AEO/GEO/能量數字組合）
├── brand/         # 品牌視覺規範
├── templates/     # 報告模板
└── reports/       # 範例報告
```

## 使用方式

**被其他 Skill 引用時**：提供八方位定義、映射規則、分類邏輯作為共用知識基底。

**直接觸發時**（`/onemuse` 或 `/om`）：
- 回答關於 One Muse 體系的任何問題
- 查詢特定方位的深度解讀
- 解釋能量循環和卡點邏輯
- 提供映射規則的依據和理由

## 迭代規則

One Muse 的知識會隨 Zeal 的實戰經驗持續更新。任何更新必須：
1. 由 Zeal 確認（不可自行推測或修改 One Muse 定義）
2. 同步到所有依賴此知識的 Skill
3. 結晶化存入 knowledge-lattice
