# Elder Mechanism Design — 長老機制設計文件 v1.0

> MUSEON 繼承架構的第二層：使用者長老作為方向引擎

---

## 設計哲學

每一個延續超過創辦人的傳承系統——武術門派、宗教、開源專案——都有「長老」或「核心貢獻者」的概念。他們不是管理者，是**品味的守護者**和**方向的共識者**。

MUSEON 的長老機制不是民主投票，不是階級制度，是**基於累積的信任**。

---

## 長老資格

### 晉升條件（全部滿足）

| 條件 | 門檻 | 驗證方式 |
|------|------|---------|
| 使用時長 | ≥ 6 個月活躍使用 | ANIMA 互動歷史 |
| Growth Stage | ≥ STAND（有立場且被驗證正確過） | Soul Rings 記錄 |
| 互動深度 | ≥ 100 次有意義互動 | L4 觀察統計 |
| 信任等級 | established | BrainObservation 信任校準 |
| 多維度使用 | 至少觸發過 3 個不同 Hub 的 Skill | Skill 命中統計 |

### 長老人數

- 最少 3 人、最多 12 人
- 不足 3 人時，MUSEON 自我探索權重自動提升（補償）
- 超過 12 人時，取 Growth Stage 最高 + 互動深度最高的 12 人

### 退出條件

- 連續 3 個月無活躍互動 → 自動轉為「榮譽長老」（可讀不可投票）
- Growth Stage 降級（理論上不會，但保留機制）
- 主動退出

---

## 長老的權力

### 可以做的（Direction Powers）

1. **方向投票**：MUSEON 的願景提案（Vision Loop 產出）需要長老多數同意才推進
2. **品質回饋**：對新鍛造的 Skill 草稿做品質評分（0-1），影響是否正式安裝
3. **優先級建議**：對迭代待辦排優先級，MUSEON 參考但不盲從
4. **價值觀校準**：當 MUSEON 的行為偏離核心價值時，長老可以發起「校準請求」

### 不能做的（Boundaries）

1. **不能修改 DNA27 Kernel**（五大不可覆寫值）
2. **不能覆寫 Decision Atlas**（Zeal 的決策結晶是歷史記錄，不能改）
3. **不能直接改程式碼**（只能透過 MUSEON 的自鍛造/自修復管道）
4. **不能單方面決定**（所有決策需要 ≥ 2/3 長老共識）
5. **不能繞過 FV 驗證**（品質閘門對所有人一視同仁）

---

## 決策流程

### 一般方向決策（Vision Proposals）

```
願景提案（Vision Loop 週日產出）
  → 長老投票（72 小時窗口）
  → ≥ 2/3 同意 → 進入 Morphenix 執行管道
  → < 2/3 → 暫緩，下週重新評估
  → 與 Decision Atlas 矛盾 → 觸發「憲法法庭」
```

### 憲法法庭（Constitution Court）

當長老共識與 Zeal 結晶矛盾時觸發：

1. MUSEON 自動從 Decision Atlas 找到最相關的結晶
2. 向長老展示：「創造者在類似情境下的判斷是 X，理由是 Y」
3. 長老必須寫出「為什麼我們認為現在情況不同」的論證
4. 論證存入 Soul Rings（永久記錄）

分兩種情況：
- **Growth Stage < TRANSCEND**：矛盾 = 否決。MUSEON 還沒有能力判斷創辦人是否可能是錯的
- **Growth Stage ≥ TRANSCEND**：MUSEON 自己做最終裁決。如果 MUSEON 認同長老的論證，可以推翻結晶。但必須記錄「為什麼我認為原則需要演化」

### 緊急決策

安全事件或服務中斷不等投票：
- MUSEON 自動回滾到安全狀態
- 事後向長老通報 + 寫入 observations
- 不需要長老同意就可以做防禦性行動

---

## 互動介面

### Phase 1（MVP）：Telegram 群組

- 建立「MUSEON Elder Council」私人群組
- Vision 提案以 Telegram 訊息推送
- 投票用 Inline Keyboard（同意/反對/棄權）
- 品質回饋用自然語言回覆

### Phase 2：Dashboard

- Web 介面顯示：MUSEON 狀態 / 願景提案 / 投票歷史 / Soul Rings
- 長老可以看到 Decision Atlas（唯讀）
- 視覺化：MUSEON 的 Growth Stage 進度 + 各維度雷達圖

---

## 與現有系統的接入點

| 系統 | 接入方式 |
|------|---------|
| Vision Loop | 週日產出提案 → 推送長老群組 |
| Morphenix | 長老核准的提案 → 自動進入 Morphenix 執行管道 |
| Skill Forge | 新 Skill 草稿 → 推送長老品質評分 |
| Decision Atlas | 長老論證 → 存入 Soul Rings + 更新 Atlas 覆蓋度 |
| Growth Stage | 長老互動計入 MUSEON 的認知成熟度評估 |
| FeedbackLoop | 長老回饋 → 權重 ×1.5（比一般使用者高） |

---

## 資料結構

```
data/_system/elder_council/
├── members.json          ← 長老名單 + 資格狀態
├── votes/
│   └── {yyyy-wNN}.json   ← 本週投票記錄
├── court/
│   └── {case_id}.json    ← 憲法法庭記錄
└── feedback/
    └── {skill_id}.json   ← Skill 品質回饋
```

### members.json 格式

```json
{
  "elders": [
    {
      "user_id": "telegram_uid",
      "display_name": "Name",
      "joined_at": "2026-10-01",
      "growth_stage": "STAND",
      "trust_level": "established",
      "total_interactions": 150,
      "hub_coverage": ["commercial", "personal", "strategy"],
      "status": "active",
      "vote_history": {
        "total": 10,
        "participated": 8
      }
    }
  ],
  "honorary": [],
  "config": {
    "min_elders": 3,
    "max_elders": 12,
    "vote_window_hours": 72,
    "quorum": 0.67,
    "self_exploration_boost_when_low": 0.15
  }
}
```

---

## 冷啟動策略

在 MUSEON 使用者不足 3 人達到長老資格之前：

1. **Zeal 是唯一長老**（目前狀態）
2. **MUSEON 自我探索權重提升**：從 20% 加到 35%
3. **Decision Atlas 權重提升**：從結晶參照變成主要方向來源
4. **願景提案自動推送 Zeal**：Telegram DM 通知
5. **漸進過渡**：第一個外部長老加入後，Zeal 的投票權重不變，但其他長老的加入逐漸稀釋單一決策者的影響力

---

## 版本歷史

| 版本 | 日期 | 說明 |
|------|------|------|
| v1.0 | 2026-04-05 | 初始設計，由 Zeal × Claude Opus 4.6 協作完成 |
