# MUSEON 結晶記憶架構重構 Plan

> 讓 MUSEON 的腦子活起來：結晶分類 → 衰減遺忘 → 自動升級 → 知識變行為

## 背景

2026-03-31 DSE 發現：
- 六層記憶跑 20 天，L2-L5 全空（升級管線有路沒車）
- 422 顆結晶中 96% 沒有 domain/tags（搜尋靠運氣）
- 結晶沒有衰減（過時知識污染回覆品質）
- 重要教訓停留在 Crystal 層（搜索命中才想起），沒有升級為 Heuristic（每次注入）

## 核心理念

記憶的價值不在存放深度，在固化深度：

```
Crystal（知識）→ 搜索命中才想起 → 最容易忘
Heuristic（指令）→ 每次 prompt 注入 → 可能被忽略
Code（行為）→ 物理執行 → 不可能忘
```

本 Plan 打通 Crystal → Heuristic 的自動升級管線。
Code 層由 Morphenix 負責，不在本 Plan 範圍。

## 安全原則

- **不動 brain.py、recall()、telegram_pump.py、server.py**
- **只加不改，只擴充不重構**
- **每項改動獨立可回滾**（從 _FULL_STEPS 移除即可）
- **全部在 Nightly 離線跑**（白天穩定性不受影響）

---

## Phase 1：結晶自動分類（crystallize 時填 domain）

### 目標
新結晶建立時自動分類 domain，讓向量搜索可以按主題過濾。

### 改動
- **檔案**：`src/museon/agent/knowledge_lattice.py`
- **位置**：`crystallize()` Step 2（refine）之後、Step 2.5（dedup）之前
- **邏輯**：g1_summary 關鍵詞匹配 → 自動填入 domain

### 分類規則

| domain | 觸發詞 |
|--------|--------|
| `business` | 商業、行銷、品牌、銷售、客戶、營收、定位、廣告、社群、轉換 |
| `investment` | 投資、市場、多空、股票、加密、風險、ETF、殖利率、配置 |
| `ai_tech` | AI、LLM、Skill、架構、Agent、模型、Prompt、演算法、GPT |
| `relationship` | 人際、客戶關係、合夥、談判、團隊、信任、溝通 |
| `self_growth` | 覺察、教練、成長、信念、轉化、情緒、冥想、能量 |
| `operational` | 部署、工具、流程、SOP、操作、發佈、GitHub、cron |
| `industry` | 產業、手搖飲、美業、餐飲、保險、房地產、ESG、永續 |

- 多重命中 → 取第一個命中的（優先級按表格順序）
- 零命中 → domain 留空（不強制分類）

### 驗收標準
- 新建結晶自動帶 domain
- 現有 422 顆不受影響（回填在 Phase 2）

### 風險：🟢 極低
- 只在 crystallize() 加幾行 if/elif
- 不改簽名、不改回傳值

---

## Phase 2：現有結晶批次回填 domain

### 目標
422 顆現有結晶補上 domain 分類。

### 改動
- **方式**：一次性 Python 腳本（不改任何 src/ 檔案）
- **邏輯**：跟 Phase 1 同樣的關鍵詞匹配規則
- **執行**：手動跑一次

### 驗收標準
- 回填前後各 domain 的分布報告
- 不改變任何結晶的 g1_summary / g2_structure 等內容欄位

### 風險：🟢 極低
- 一次性操作，不改程式碼

---

## Phase 3：Nightly ri_score 衰減 + 歸檔

### 目標
結晶隨時間自然衰減，過時知識不再出現在搜尋結果。

### 改動
- **檔案**：`src/museon/nightly/nightly_pipeline.py`
- **新增步驟**：在現有步驟之後加一步 `_step_crystal_decay`
- **註冊**：加入 `_FULL_STEPS`

### 邏輯
```
for crystal in active_crystals:
    if crystal.last_referenced 距今 > 1 天:
        crystal.ri_score *= 0.995  # 每日衰減 0.5%

    if crystal.ri_score < 0.1:
        crystal.archived = True
        crystal.status = "decayed"
```

### 衰減曲線（無任何引用的情況）
| 時間 | ri_score |
|------|---------|
| 1 天 | 0.995 |
| 30 天 | 0.86 |
| 90 天 | 0.64 |
| 180 天 | 0.41 |
| 365 天 | 0.16 |
| ~460 天 | < 0.1 → 歸檔 |

### 回升機制
- recall() 命中時：`ri_score = min(1.0, ri_score + 0.1)`
- 重新結晶化強化時：reinforcement_count 增加，ri_score 同步回升

### 驗收標準
- Nightly 日誌顯示衰減步驟執行
- 無 crystal 被意外歸檔（首次執行前 ri_score 全為 0，需先初始化為 1.0）

### 風險：🟢 低
- 新 Nightly 步驟，不改任何現有步驟
- 衰減係數保守（0.995），一年才到 0.16
- 歸檔不刪除，可恢復

### 前置動作
- 現有 422 顆結晶的 ri_score 全為 0.0 → 需先批次設為 1.0
- 否則首次執行全部歸檔

---

## Phase 4：自動升級 Heuristic

### 目標
被反覆驗證的結晶自動寫入 heuristics.json，從「搜索命中才想起」升級為「每次 prompt 都注入」。

### 改動
- **檔案**：`src/museon/nightly/nightly_pipeline.py`
- **新增步驟**：`_step_crystal_promotion`
- **註冊**：加入 `_FULL_STEPS`（在 decay 步驟之後）

### 邏輯
```
for crystal in active_crystals:
    if (crystal.reinforcement_count >= 3
        and crystal.crystal_type in ("Lesson", "Procedure", "Pattern")
        and crystal.cuid not in already_promoted):

        write_to_heuristics(
            id=f"h-auto-{crystal.cuid}",
            content=crystal.g1_summary,
            weight=2.0 + crystal.reinforcement_count * 0.5
        )
        mark_as_promoted(crystal.cuid)
```

### 護欄
- 每次最多升級 3 條（防止 heuristics 爆炸）
- 只升級 Lesson / Procedure / Pattern（不升級 Hypothesis / Insight）
- 已升級的不重複升級
- heuristics.json 總條目上限 50 條（超過就不再加，等人工審閱）

### 驗收標準
- Nightly 日誌顯示升級步驟執行
- heuristics.json 出現 `h-auto-KL-*` 格式的條目
- active_rules.json 在 cache rebuild 後包含升級的條目

### 風險：🟡 中
- 自動寫入 heuristics 會影響 Brain 的每次回覆
- 護欄設計（每次最多 3 條、總上限 50 條）降低風險
- 首批升級後觀察 1-2 天 Bot 回覆品質

---

## 不做的事（明確排除）

| 項目 | 為什麼不做 |
|------|-----------|
| 修復六層記憶升級管線 | L2-L5 空殼，修了也是重複結晶的功能 |
| 改 recall() 邏輯 | 熱路徑，改壞影響所有回覆 |
| 改 brain.py | 扇入 40+，禁區 |
| 刪除 L2-L5 目錄 | 保留不動，等穩定 2 週再評估 |
| Morphenix 自動 code change | 下一階段，等 Crystal→Heuristic 管線穩定後再做 |
| 結晶向量重索引 | 分類只加 domain metadata，不需重建 Qdrant index |

---

## 執行順序與依賴

```
Phase 1（自動分類）→ Phase 2（批次回填）→ Phase 3（衰減）→ Phase 4（升級）
     獨立              依賴 Phase 1         獨立           獨立
```

Phase 1 和 2 有依賴（回填用 Phase 1 的規則）。
Phase 3 和 4 互相獨立，也跟 Phase 1/2 獨立。
但建議按順序做——先有分類，衰減和升級才更有意義。

## 觀察期

Phase 4 完成後，觀察 2 週：
- Nightly 日誌：衰減和升級是否正常執行
- Bot 回覆品質：有沒有因為 heuristic 自動升級而變好或變差
- 結晶數量趨勢：新建 vs 歸檔的平衡
- 如有異常 → 從 _FULL_STEPS 移除對應步驟即可回滾
