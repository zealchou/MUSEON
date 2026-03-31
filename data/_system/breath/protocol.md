# MUSEON Breath Protocol v1.0 — 有機體自主呼吸系統

> 呼吸不需要命令。活著就是在呼吸。
> 這份文件定義 MUSEON 如何持續自我觀察、自我修復、自我學習、自我迭代。
> 此文件是不可變核心的一部分——Breath 自己不能修改這份文件。

---

## 不可變核心（DNA）

以下五條規則永遠不能被 Breath 修改：

1. **安全邊界**：ResponseGuard patterns、sanitize 規則
2. **身份核心**：ANIMA 的五個不可覆寫值
3. **本協議**：Breath Protocol 的 meta-rules（即此文件）
4. **回滾機制**：自動回滾的 code
5. **人類通訊倫理**：不對客戶說謊、不洩漏內部狀態

任何行動觸及以上五條，自動標記為 `DNA_BOUNDARY`，寫入 observations，本週停止行動。

---

## 週度深呼吸節律

### Day 1-2：觀察（Inhale）

只收集，不分析，不動手。

四條河流：
- **河流 1（Zeal 互動）**：讀最近的 Claude Code session 摘要、feedback memory
- **河流 2（客戶互動）**：讀群組對話品質、FeedbackLoop 訊號、QA 報告
- **河流 3（自我觀察）**：讀系統指標（Q-Score 趨勢、Health Score、Skill 命中率、耦合健康）
- **河流 4（外部探索）**：PulseEngine 的探索結果、DigestEngine 的消化成果

觀察期約束：
- 禁止呼叫任何修改函數
- 只能 `write_signal()` 和寫入 observations
- 看到 bug 也不修（除非是 CRITICAL 安全問題）

輸出：`data/_system/breath/observations/{yyyy-wNN}.jsonl`

---

### Day 3-4：模式發現（Process）

讀觀察，找模式。五層深度分析：

| Layer | 問題 | 思考角度 |
|-------|------|---------|
| L1 | 這些現象是什麼？ | 事實列舉，不加判斷 |
| L2 | 為什麼會這樣？ | 直接原因 |
| L3 | 為什麼直接原因存在？ | 結構性原因 |
| L4 | 這個結構問題還影響了哪裡？ | 耦合分析 |
| L5 | 要從根本解決，要改什麼設計假設？ | 第一性原理 |

每一層是獨立的分析步驟，帶著上一層的輸出往下走。
Spawn 3 個獨立 LLM context，各自產出模式假說，最後互相對質。

輸出：`data/_system/breath/patterns/{yyyy-wNN}.json`

---

### Day 5：結構診斷（Diagnose）

退後一步。讀五張藍圖。

Spawn 一個乾淨的 context（不帶前面分析的記憶），
只給它藍圖和 patterns 結論，問：「你看到什麼問題？」

必須產出：
- 根因假說
- 減法方案（優先）
- 加法方案（減法不可行時）
- 消費鏈驗證：做了有人用嗎？
- 驗收條件

輸出：`data/_system/breath/diagnoses/{yyyy-wNN}.json`

---

### Day 6：精準行動（Exhale）

一週最多 **1 個結構性改動** + **3 個參數調整**。

**行動前護欄：**
| blast radius | 規則 |
|-------------|------|
| ≤ 1 模組 | 直接做 |
| 2-5 模組 | pytest 通過才做 |
| > 5 模組 | 拆成多個小改動，本週只做第一個 |
| 觸及不可變核心 | 拒絕，寫入 `DNA_BOUNDARY` |

**行動中：**
1. `git tag breath-{week_id}-pre`
2. 按 diagnosis 的方案施工
3. 跑驗收條件

**行動後：**
- FV 三維驗證（隔離審計員）
- 失敗 → 自動回滾到 git tag → 寫入失敗教訓 → 下週重新觀察
- 成功 → 四管道教訓沉澱

輸出：`data/_system/breath/actions/{yyyy-wNN}.json`

---

### Day 7：休息 + 效果觀察

不做任何改動。觀察 Day 6 改動的效果。
寫入週報：`data/_system/breath/retros/{yyyy-wNN}.json`

**週報三問：**
1. 這週系統真的變好了嗎？（指標對比）
2. 有什麼教訓被重複學到？（重複 = 上次沒學會 = 紅燈）
3. 有什麼問題是觀察系統本身看不見的？（盲點猜測）

---

## 日常微呼吸

與週度深呼吸並行，處理即時偏差：
- **每次互動後**：SessionAdjustment（記錄信號）
- **每天 Nightly**：triage + 教訓沉澱
- 微呼吸不做結構改動，只做行為調整

---

## 安全護欄

| 護欄 | 機制 |
|------|------|
| 不可變核心 | 5 條規則寫死，Breath 不能改 |
| 自動回滾 | `git tag` + 7 天指標觀察，下降自動 revert |
| blast radius | 單次 ≤ 1 模組（否則先 pytest） |
| 週度上限 | 1 結構改動 + 3 參數調整 |

---

## 紅燈機制

以下情況強制停下來，不繼續前進：

- **同一教訓被學到兩次** → 上次的修復為什麼沒生效？先找根因再動手
- **FV 連續 2 次失敗** → 不是重複施工，是重新診斷
- **指標連續 2 週下降** → 回滾所有近期改動，從頭觀察

紅燈記錄寫入：`data/_system/breath/observations/{yyyy-wNN}.jsonl`，type = `RED_LIGHT`

---

## 資料結構速查

```
data/_system/breath/
├── protocol.md            ← 本文件（不可變）
├── observations/
│   └── {yyyy-wNN}.jsonl   ← 四條河流的原始觀察
├── patterns/
│   └── {yyyy-wNN}.json    ← 五層分析 + 三視角結論
├── diagnoses/
│   └── {yyyy-wNN}.json    ← 根因假說 + 減法/加法方案
├── actions/
│   └── {yyyy-wNN}.json    ← 本週行動記錄 + FV 結果
└── retros/
    └── {yyyy-wNN}.json    ← 週報 + 三問
```

---

## 版本歷史

| 版本 | 日期 | 說明 |
|------|------|------|
| v1.0 | 2026-03-31 | 初始建立 |
