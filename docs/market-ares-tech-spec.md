# 市場戰神 Market Ares — 技術開發規格書 v1.0

> **文件用途**：內部開發依據，照此施工。
> **更新日期**：2026-03-30
> **狀態**：設計定稿，待開發

---

## 一、系統願景

模擬真實市場的交織狀態，透過注入地區人口統計資料，生成具備 16 維能量屬性的數位人群原型（Agent），預測商業策略在 52 週內的演化與顯化結果。

### 核心差異

| 維度 | 暴力枚舉模式 | 市場戰神 |
|------|----------|--------|
| 模擬邏輯 | 1000+ 隨機 Agent | 64-512 結構化原型 |
| 準確來源 | 群體智能湧現 | 能量因果 + 數據驅動聚類 |
| 算力消耗 | 極高 | CPU 為主，LLM 僅用於洞察 |

---

## 二、雙軌產品架構

### 軌道一：自駕模式（使用者主導）

```
使用者輸入 SMART 策略
→ 系統模擬 52 週
→ 使用者看結果、調整、再跑（3-6 輪）
→ 產出最終戰情報告
```

### 軌道二：代駕模式（MUSEON 主導）

```
使用者輸入期望結果（如「營業額提高 250%」）
→ SSA + 麥肯錫/BCG 提問法（7-10 題）訪談現況
→ 商模十二力健檢
→ 品牌定位分析（brand-builder）
→ PDEIF 逆熵流：從終點反推路徑
→ xmodel 破框：生成 3-5 組策略候選
→ 市場戰神 3 輪自動模擬 + 策略優化
→ 產出最佳策略組合 + 完整戰情報告 + 執行路線圖
```

---

## 三、數據架構：五層數據模型

### L1 地理基底（靜態/年更）

| 欄位 | 來源 | 用途 |
|------|------|------|
| 地形、海拔 | 政府地理資料 | 生活型態推導 |
| 氣候區 | 氣象局 | 季節性消費模式 |
| 交通工具比例 | 交通部統計 | 生活半徑 |
| 通勤時長分布 | 交通部統計 | 時空約束 |

### L2 人口結構（年度更新）

| 欄位 | 來源 | 用途 |
|------|------|------|
| 年齡分布 | 戶政統計 | 世代特徵 |
| 家庭組成（戶均人口、婚姻狀況） | 戶政統計 | 水能量推導 |
| 教育程度分布 | 教育部統計 | 認知傾向 |
| 職業/產業結構 | 勞動部統計 | 產業能量推導 |
| 戶均所得 | 財政部/主計處 | 地能量推導 |
| 房屋自有率 | 內政部統計 | 地能量推導 |
| 離婚率 | 戶政統計 | 水能量推導（反向） |
| 生育率 | 戶政統計 | 水能量推導 |
| 創業率/新創密度 | 經濟部統計 | 天能量推導 |

### L3 生活型態（季度更新）

| 欄位 | 來源 | 用途 |
|------|------|------|
| 健身房密度 | Google Maps Places API | 山能量 |
| 高檔餐廳密度 | Google Maps Places API | 山能量 |
| 宗教場所密度 | Google Maps Places API | 山能量 |
| 咖啡廳密度 | Google Maps Places API | 澤能量 |
| 百貨/商圈密度 | Google Maps Places API | 澤能量 |
| 美業店家密度 | Google Maps Places API | 火能量 |
| 身心靈課程/工作坊密度 | Google Maps + 爬蟲 | 雷能量 |
| 極限運動/戶外活動場所 | Google Maps Places API | 天能量 |
| 社群平台活躍度 | 社群 API（Meta/X） | 火/澤能量 |
| 合夥企業比例 | 經濟部商業司 | 風能量 |
| 企業存活率 | 經濟部統計 | 風能量 |

### L4 事件脈動（即時/日更）

| 類型 | 來源 | 影響 |
|------|------|------|
| 政治事件（選舉、政策） | 新聞 API | 天/地能量波動 |
| 經濟指標（CPI、利率） | 主計處/央行 | 地/山能量波動 |
| 天災/疫情 | 氣象局/衛福部 | 全方位衝擊 |
| 產業新聞 | 新聞 API | 特定方位波動 |
| 競爭者動態 | 自動推演 | 策略對沖 |

### L5 關係拓樸（月更）

| 欄位 | 來源 | 用途 |
|------|------|------|
| 產業鏈上下游關係 | 產業資料庫 | 生態夥伴影響力方向 |
| 社會階層互動模式 | 人口統計交叉分析 | 原型間傳導係數 |
| 創新傳播擴散路徑 | Rogers 模型 + 地區特徵 | 影響力權重 |

---

## 四、能量模型：八方位 × 內外在 = 16 維

### 八方位定義

| 方位 | 核心驅力 | 白帽 | 黑帽 | 強時 | 弱時 |
|------|--------|------|------|------|------|
| 天 | 目標、引領、行為破框 | 使命感 | 恐懼失敗 | 領導者 | 追隨者 |
| 風 | 適應、溝通、成交 | 稀缺性 | 害怕錯失 | 鬥士 | 導演 |
| 水 | 關係、照顧、連結 | 擁有所愛 | 害怕孤立 | 協調者 | 獨裁者 |
| 山 | 累積、復盤、紀律 | 避開危害 | 害怕損失 | 策略家 | 藝術家 |
| 地 | 穩定、承載、資產運用 | 內在豐盛 | 恐懼匱乏 | 守護者 | 自護者 |
| 雷 | 覺察、認知破框、內在探索 | 冒險 | 害怕停滯 | 開拓者 | 守舊派 |
| 火 | 展現、趨勢觀察、個人投入 | 掌握影響力 | 害怕失控 | 追尋者 | 隱士 |
| 澤 | 點燃、社群、品牌、感染 | 從創造出發 | 害怕沉寂 | 鼓舞者 | 破壞者 |

### 內在 vs 外在

- **內在**：初衷、潛意識、能量狀態（權重較高）
- **外在**：行為表現、他人眼中的投射
- 內在正 → 吸引人靠近 → 外在跟著好
- 內在負 → 貴人迴避 → 外在持續惡化
- 能量值域：-4 ~ +4，±4 為極值（即將反轉）

### 數據→能量映射表 v0.1

| 方位 | 外在指標（行為可觀察） | 內在指標（間接推導） |
|------|------------------|--------------|
| 天 | 創業率、新創密度、戶外活動場所密度 | 志工組織數、社團登記數 |
| 風 | 業務職占比、合夥企業比例、企業存活率 | 結婚率、調解成功率 |
| 水 | 戶均人口數、離婚率（反向）、生育率 | 社區照護密度、長照設施密度 |
| 山 | 健身房密度、高檔餐廳密度、宗教場所數 | 儲蓄率、保險投保率 |
| 地 | 戶均所得、人口密度、房屋自有率 | 被動收入比例、連鎖加盟密度 |
| 雷 | 身心靈課程密度、藝文展演數、次文化社群 | 冥想相關搜尋趨勢、心理諮商所密度 |
| 火 | 展覽/講座參與率、進修課程報名率 | 訂閱制服務使用率、市調公司密度 |
| 澤 | 咖啡廳/百貨密度、自媒體創作者比例 | 社群互動率、KOL 密度、品牌店家密度 |

---

## 五、原型生成：數據驅動聚類

### 流程

```
五層原始數據
  ↓ 映射表轉譯
16 維能量向量（每個地區子區域一組）
  ↓ 階層式聚類
樹狀圖 → 找自然斷點
  ↓ K-Means 收斂
64-512 個穩定原型
  ↓ LLM（Sonnet）命名
每個原型賦予白話名稱 + 行為描述
```

### 聚類演算法

1. **階層式聚類**（AgglomerativeClustering）產出樹狀圖
2. 觀察 512→256→128→64 的合併損失曲線，找自然斷點
3. **K-Means** 以斷點數量重新跑，得到穩定分群
4. 輸出：每個原型的 16 維中心向量 + 佔比權重

### 原型資料結構

```python
@dataclass
class Archetype:
    id: int
    name: str                    # 白話名稱（LLM 生成）
    description: str             # 一句話描述
    weight: float                # 在地區人口中的佔比（0-1）

    inner_energy: dict[str, float]  # 8 方位內在能量（-4 ~ +4）
    outer_energy: dict[str, float]  # 8 方位外在能量（-4 ~ +4）

    # 市場行為特徵（LLM 生成）
    purchase_triggers: list[str]    # 觸發購買的條件
    resistance_triggers: list[str]  # 觸發抗拒的條件
    influence_targets: list[int]    # 能影響哪些原型 ID
    influenced_by: list[int]        # 被哪些原型影響

    # 創新傳播曲線位置
    adoption_stage: str  # innovator / early_adopter / early_majority / late_majority / laggard

    # 模擬狀態（動態更新）
    awareness_state: str  # unaware / aware / considering / decided / loyal / resistant
    current_inner: dict[str, float]  # 當前內在能量（模擬中動態變化）
    current_outer: dict[str, float]  # 當前外在能量
```

---

## 六、Agent 類型

### 三種 Agent

| 類型 | 數量 | 生成方式 | 特徵 |
|------|------|--------|------|
| 消費者原型 | 64-512 | 數據聚類自動生成 | 帶權重比例 |
| 競爭者 | 1-5 | 系統自動推算（基於產業數據） | 有獨立策略，會主動反應 |
| 生態夥伴 | 1-10 | 系統自動推算（基於產業鏈） | 有利益考量，配合度動態變化 |

### 競爭者 Agent 邏輯

```python
@dataclass
class CompetitorAgent:
    id: str
    name: str
    market_share: float
    energy_profile: dict[str, float]  # 8 方位能量指紋

    # 反應邏輯（基於能量特質）
    # 天強 → 主動反擊（降價、加碼行銷）
    # 山強 → 先觀察再回應（蒐集數據）
    # 地強 → 靠系統慣性防守（既有客群忠誠度）
    reaction_style: str  # aggressive / analytical / defensive

    # 反應觸發條件
    reaction_threshold: float  # 市佔率下降多少 % 觸發反應
```

---

## 七、模擬引擎：三股力量

### 每週更新公式

```
E_i(t+1) = E_i(t) + F_strategy(i,t) + F_social(i,t) + F_oscillation(i,t) + F_event(t)
```

### 力量一：策略衝擊 F_strategy

```python
def strategy_impact(archetype, strategy_vector):
    """策略向量 × 原型敏感度"""
    sensitivity = compute_sensitivity(archetype.current_inner, archetype.current_outer)
    return strategy_vector * sensitivity

# 策略向量：8 維，每個方位的刺激強度（-1 ~ +1）
# 敏感度：原型的對應方位能量越極端，敏感度越高
```

### 力量二：社會傳導 F_social（SIR 變體）

```python
def social_contagion(archetype_i, all_archetypes, topology):
    """基於 SIR 傳染病模型的社會傳導"""

    # 狀態轉移：U → A → C → D → L（或 R）
    # U(Unaware) → A(Aware) → C(Considering) → D(Decided) → L(Loyal)
    #                                             ↘ R(Resistant)

    # 轉化率
    neighbors_converted = sum(
        a.weight * topology[i][j]
        for j, a in enumerate(all_archetypes)
        if a.awareness_state in ['decided', 'loyal']
    )

    base_rate = 0.02  # 基礎轉化率
    wind_factor = normalize(archetype_i.current_inner['風'])  # 溝通接受度
    mountain_defense = normalize(archetype_i.current_inner['山'])  # 防衛係數

    conversion_rate = base_rate * (1 + neighbors_converted) * wind_factor * (1 - mountain_defense * 0.3)

    return conversion_rate
```

### 力量三：能量擺盪 F_oscillation（阻尼振盪）

```python
def oscillation_pressure(current_value, baseline_value, damping=0.15):
    """能量越偏離基底，反轉壓力越大"""
    displacement = current_value - baseline_value

    # 阻尼振盪：F = -k * x - c * v
    # k = 彈性係數（反轉強度）
    # c = 阻尼係數（能量衰減速度）
    k = 0.08  # 調參數，使半週期 ≈ 2-12 週

    restoring_force = -k * displacement * abs(displacement)  # 非線性：越極端反轉越快

    return restoring_force
```

### 力量四：環境事件 F_event

```python
@dataclass
class EnvironmentEvent:
    week: int
    name: str
    impact_vector: dict[str, float]  # 對 8 方位的影響（-1 ~ +1）
    duration: int  # 影響持續幾週
    decay_rate: float  # 每週衰減率
```

---

## 八、商業指標換算

### 能量→商業指標的翻譯層

| 商業指標 | 計算邏輯 |
|--------|--------|
| 營業額 | Σ(已轉化原型 × 權重 × 地區人口 × 客單價 × 購買頻率) |
| 市佔率 | 已轉化人口 / 地區目標人口 |
| 鐵粉數量 | awareness_state == 'loyal' 的原型 × 權重 × 人口 |
| 口碑內容 | LLM 基於原型能量特徵生成正/負面評語 |
| 淨推薦值 | (loyal 比例 - resistant 比例) × 100 |
| 競爭對手反應 | 競爭者 Agent 的 reaction_style × 觸發條件判斷 |
| 合作夥伴態度 | 生態夥伴 Agent 的配合度分數（0-100） |

### 相對趨勢→真實數字換算（最終報告用）

```python
def relative_to_absolute(relative_trend, region_baseline):
    """
    模擬期間用相對趨勢（指數 100 為基準）
    最終報告換算為真實數字
    """
    absolute_value = relative_trend / 100 * region_baseline
    return absolute_value

# region_baseline 從 L2 人口結構 × L3 消費力數據推算
```

---

## 九、SMART 策略輸入：教練式引導

### 自駕模式（5-6 題）

```
Q1: 目標城市？
Q2: 策略一句話描述？
Q3: 期望時間 + 數字？（必填）
Q4: 服務/產品單價？
Q5: 現有客戶/名單規模？
Q6: 確認整理後的 SMART 策略
```

### 代駕模式（7-10 題，三層結構）

**第一層：目標錨定（2-3 題）**
- 52 週後事業的畫面？
- 優先順序排列
- 可接受的最低目標

**第二層：現況盤點（3-4 題）**
- 當前營收結構（客戶數 × 客單價）
- 客戶來源管道
- 現有資源盤點（名單、社群、品牌、合作關係）
- 主觀卡點

**第三層：約束條件（2-3 題）**
- 絕對不做的事
- 每週可投入時間
- 行銷預算

### 提問法來源

| 框架 | 借鏡 |
|------|------|
| SSA 12 步驟 | 痛點挖掘順序（目標→現況→卡點） |
| 麥肯錫 | 假設驅動、MECE 邊界 |
| BCG | 事實基礎（要數字不要感覺）、80/20 聚焦 |
| One Muse | 一次一問、不預設答案、讓對方自己說出畫面 |

---

## 十、輸出系統

### 10.1 每週快照（互動式 HTML 儀表板）

**核心互動**：時間軸控制器（Week 1-52），拖拉即更新所有面板。

**面板組成**：
1. 商業指標面板（營業額、市佔率、鐵粉數、口碑溫度 + vs 上週 delta）
2. 能量雷達圖（八方位即時分布）
3. 原型遷移流向圖（Sankey 圖：誰從哪個狀態移到哪個狀態）
4. 52 週趨勢折線圖（各指標 × 時間）
5. 競爭動態面板（對手反應 + 搶客率）
6. 生態夥伴面板（配合度變化）
7. 本週洞察（LLM 生成，白話文）

### 10.2 LLM 呼叫策略

```
模擬運算（能量、聚類、傳導、指標換算）→ Python/CPU，零 token
判斷「本週有沒有事」→ Python 閾值比較，零 token
圖表生成 → ECharts/Plotly，零 token

有事件週洞察 → Sonnet（~12 週/輪）
關鍵轉折深度分析 → Sonnet（~5 週/輪）
原型命名 → Sonnet（一次性）
競爭者策略推演 → Sonnet
最終戰情報告 → Opus（1 次/輪）
商模十二力 / SSA 分析 → Opus（1 次/輪）
```

### 10.3 最終戰情報告（精美 HTML）

**八章結構**：

| 章 | 標題 | 內容 | 分析引擎 |
|---|------|------|--------|
| 1 | Executive Summary | 紅黃綠燈判定 + 一句話結論 | Opus |
| 2 | 52 週全景曲線 | Gartner 風格滲透曲線 + 轉折標註 | Python 圖表 |
| 3 | 人群深度分析 | Top 3 突破口 + Top 3 阻力 + Sankey 遷移 | Opus + 圖表 |
| 4 | 商模十二力 | 12 力框架診斷 | business-12 Skill |
| 5 | 銷售路徑設計 | SSA 成交路徑 | ssa-consultant Skill |
| 6 | 風險與競爭 | 反轉預警 + 競爭者模擬 + 敏感度分析 | Opus + Python |
| 7 | 創新傳播定位 | Rogers 曲線位置 + 下一步條件 | Python + Opus |
| 8 | 行動建議 | 3 件立即可做 + 策略微調方向 | Opus |

---

## 十一、運算架構

### 分工

| 層 | 工具 | 佔工作量 | 成本 |
|---|------|--------|------|
| 數據爬蟲 + 映射 + 聚類 + 模擬 + 指標 + 圖表 | Python / NumPy / SciPy / ECharts | 90% | 主機費 |
| 洞察 + 分析 + 命名 + 報告 | Sonnet / Opus | 10% | Token 費 |
| 大規模模擬（未來） | GPU | 0%（預留） | 按需 |

### 單次成本估算（自駕模式）

| 項目 | 次數 | 模型 | Token | 成本 |
|------|------|------|-------|------|
| 事件週洞察 | ~12 | Sonnet | ~18K | ~$0.54 |
| 關鍵轉折分析 | ~5 | Sonnet | ~15K | ~$0.45 |
| 最終報告 | 1 | Opus | ~8K | ~$1.20 |
| **單輪合計** | | | **~41K** | **~$2.19** |
| **6 輪合計** | | | **~246K** | **~$13.14** |

### 代駕模式額外成本

| 項目 | 次數 | 模型 | 估算成本 |
|------|------|------|--------|
| SMART 教練引導 | 1 | Sonnet | ~$0.50 |
| 商模十二力 | 1 | Opus | ~$2.00 |
| 品牌定位 | 1 | Opus | ~$2.00 |
| PDEIF + xmodel 策略設計 | 1 | Opus | ~$3.00 |
| 3 輪模擬 | 3 | 同上 | ~$6.57 |
| 策略優化（輪間） | 2 | Opus | ~$4.00 |
| 最終報告（含 B12 + SSA） | 1 | Opus | ~$5.00 |
| **代駕總計** | | | **~$23.07** |

---

## 十二、儲存架構

### SQLite（確定性數據）

```sql
-- 地區基底數據
CREATE TABLE regions (
    id TEXT PRIMARY KEY,
    country TEXT, city TEXT, district TEXT,
    l1_geography JSON,    -- L1 地理基底
    l2_demographics JSON, -- L2 人口結構
    l3_lifestyle JSON,    -- L3 生活型態
    updated_at TIMESTAMP
);

-- 原型定義
CREATE TABLE archetypes (
    id INTEGER PRIMARY KEY,
    region_id TEXT REFERENCES regions(id),
    name TEXT,
    description TEXT,
    weight REAL,
    inner_energy JSON,  -- {天: 2.1, 風: -0.5, ...}
    outer_energy JSON,
    adoption_stage TEXT,
    purchase_triggers JSON,
    resistance_triggers JSON,
    created_at TIMESTAMP
);

-- 模擬快照
CREATE TABLE simulation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    simulation_id TEXT,
    week INTEGER,
    archetype_states JSON,     -- 所有原型當週狀態
    business_metrics JSON,     -- 商業指標
    competitor_actions JSON,   -- 競爭者行動
    partner_attitudes JSON,    -- 夥伴態度
    events JSON,               -- 本週事件
    insight TEXT,               -- LLM 生成的洞察
    created_at TIMESTAMP
);

-- 模擬設定
CREATE TABLE simulations (
    id TEXT PRIMARY KEY,
    region_id TEXT REFERENCES regions(id),
    strategy JSON,            -- SMART 策略定義
    mode TEXT,                -- 'self_drive' | 'chauffeur'
    round INTEGER DEFAULT 1,  -- 第幾輪
    status TEXT,              -- 'running' | 'completed' | 'aborted'
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### Qdrant（向量搜尋，未來擴展）

用途：跨模擬的原型相似度搜尋、歷史模擬結果的語意化溯源。

第一版不需要，待系統累積足夠模擬數據後再啟用。

---

## 十三、模組分工

```
src/museon/market_ares/
├── __init__.py
├── crawler/                  # L1-L5 數據爬蟲
│   ├── tw_demographics.py    # 台灣人口統計爬蟲
│   ├── tw_geography.py       # 台灣地理數據
│   ├── google_places.py      # Google Maps POI 密度
│   ├── social_signals.py     # 社群數據
│   └── event_feed.py         # 事件脈動
├── mapping/                  # 數據→能量映射
│   ├── energy_mapper.py      # 映射表引擎
│   └── mapping_config.yaml   # 映射規則定義
├── clustering/               # 聚類引擎
│   ├── hierarchical.py       # 階層式聚類
│   ├── kmeans_refine.py      # K-Means 收斂
│   └── archetype_namer.py    # LLM 命名（Sonnet）
├── simulation/               # 模擬引擎
│   ├── engine.py             # 主引擎（52 週循環）
│   ├── strategy_impact.py    # 力量一：策略衝擊
│   ├── social_contagion.py   # 力量二：社會傳導（SIR）
│   ├── oscillation.py        # 力量三：能量擺盪
│   ├── competitor_agent.py   # 競爭者 Agent
│   ├── partner_agent.py      # 生態夥伴 Agent
│   └── event_injector.py     # 環境事件注入
├── metrics/                  # 商業指標換算
│   ├── business_metrics.py   # 能量→商業指標翻譯
│   └── trend_to_absolute.py  # 相對趨勢→真實數字
├── coaching/                 # SMART 教練引導
│   ├── self_drive_coach.py   # 自駕模式引導
│   └── chauffeur_coach.py    # 代駕模式引導（SSA+McKinsey+BCG）
├── analysis/                 # 分析引擎
│   ├── weekly_insight.py     # 每週洞察生成（Sonnet）
│   ├── turning_point.py      # 關鍵轉折偵測
│   ├── strategy_optimizer.py # 代駕模式策略優化
│   └── final_report.py       # 最終戰情報告生成（Opus）
├── visualization/            # 視覺化
│   ├── dashboard.py          # 互動式 HTML 儀表板生成
│   ├── charts.py             # ECharts 圖表元件
│   └── report_renderer.py    # 最終報告 HTML 渲染
├── storage/                  # 儲存層
│   ├── db.py                 # SQLite 操作
│   └── models.py             # ORM / Dataclass
└── config.py                 # 全域設定
```

---

## 十四、開發順序（Roadmap）

### Phase 1：數據基礎（估計 1-2 週）

1. 建立 SQLite Schema
2. 台灣人口統計爬蟲（政府開放資料平台 API）
3. Google Maps Places API 整合（POI 密度計算）
4. 數據→能量映射引擎
5. BDD 測試：輸入台南永康數據 → 輸出 16 維能量向量

### Phase 2：聚類引擎（估計 1 週）

1. 階層式聚類 + 樹狀圖
2. K-Means 收斂
3. LLM 原型命名
4. BDD 測試：64-512 個原型的穩定性驗證

### Phase 3：模擬核心（估計 2 週）

1. 策略衝擊模組
2. SIR 社會傳導模組
3. 阻尼振盪模組
4. 競爭者 Agent
5. 生態夥伴 Agent
6. 52 週主引擎迴圈
7. 商業指標換算層
8. BDD 測試：策略注入 → 52 週演化 → 指標合理性驗證

### Phase 4：教練引導（估計 1 週）

1. 自駕模式 SMART 引導流程
2. 代駕模式三層提問流程
3. 策略向量自動生成

### Phase 5：視覺化（估計 2 週）

1. 每週快照 HTML 儀表板（時間軸 + 6 面板）
2. ECharts 圖表元件（雷達圖、Sankey、折線圖）
3. 最終報告 HTML 渲染（8 章 + 圖表嵌入）
4. GitHub Pages 部署

### Phase 6：分析引擎整合（估計 1 週）

1. 商模十二力 Skill 整合
2. SSA Skill 整合
3. 代駕模式策略優化邏輯
4. 最終報告自動生成

### Phase 7：校準與迭代（持續）

1. 真實數據 vs 模擬結果比對
2. 映射表係數校準
3. 模擬參數調優
4. 使用者回饋循環

---

## 十五、第一版限制與未來擴展

### 第一版限制

- 僅支援台灣
- 單一城市（不支援跨城市交互）
- 不支援蒙地卡羅置信區間
- Qdrant 向量搜尋暫不啟用
- 無 GPU 加速

### 未來擴展方向

- 多國支援（美國 Census API、日本統計局）
- 跨城市交互影響模擬
- 蒙地卡羅模擬（GPU 加速），輸出「策略成功率 78%」
- 原型歷史追蹤（Qdrant 語意搜尋）
- 即時數據串流（取代手動爬蟲）
- API 化，讓第三方接入

---

## 附錄 A：參考框架

| 框架 | 借鏡用途 |
|------|--------|
| PRIZM / MOSAIC | 地理人口分群的數據變數選擇 |
| VALS | 心理動機→外在行為的轉譯邏輯 |
| Rogers 創新傳播 | 2.5%/13.5%/34%/34%/16% 分層 |
| Schelling 隔離模型 | Agent 間影響力拓樸 |
| SIR 傳染病模型 | 口碑/認知的擴散動力學 |
| 系統動力學 Stock-and-Flow | 能量擺盪建模 |
| PESTEL | L4 事件分類 |
| ESG 利害關係人 | L5 關係拓樸 |
| 霍金斯情緒能量表 | 能量值域參考 |

## 附錄 B：One Muse 八方位循環法則

順時針循環：天→風→水→山→地→雷→火→澤→天

卡點法則：某方位卡住，解方在逆時針回推兩個方位。

四條對軸：天-地、風-雷、火-水、山-澤

能量特性：
- 能量好 ≠ 有做事，能量好 = 做對應的事時心情順流
- ±4 極值即將反轉（鐘擺效應）
- 反轉週期：2 週 ~ 3 個月（極端可達 12 個月）
- 內在能量權重 > 外在能量權重
