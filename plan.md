# plan.md — MUSEON BDD 重設計 + 核心系統開發迭代

> 狀態：Annotated → BDD 設計中
> 建立時間：2026-02-26T17:00
> 批註輪次：1/6

---

## 🔍 Research Log（情報區）

### 已確認事實

- [x] MUSEON 是 MUSEON AI OS 的實例，五層金字塔架構：L1 Kernel → L2 DNA27 → L3 Memory → L4 Evolution → L5 Language — 來源：Bootloader Whitepaper
- [x] 目前 gateway/server.py 已接通 Brain routing，474+ 測試通過，安裝程式可用 — 來源：前幾輪開發
- [x] 45 個原生技能在 data/skills/native/，SkillRouter 已能正確索引匹配 — 來源：skill_router.py
- [x] ANIMA 雙版本格式（JSON + Markdown）已決定，現在就要實作 — 來源：使用者決定
- [x] User ANIMA 完整版（7 層 + 4 觀察引擎 + 年輪 + 八原語）— 來源：使用者決定
- [x] 心跳系統雙層（60min 日常 + 3x 每日自省 8:45/12:45/20:45）+ Nightly Job 00:00 — 來源：使用者決定
- [x] MCP 是原生本能（因為用 Claude API token）— 來源：使用者確認
- [x] **第一性原理瓶頸**：四個演化引擎（WEE + Morphenix + Eval-Engine + Knowledge-Lattice）都設計好了，但需要程式碼化成**脫離對話依賴的持續運行背景程序** — 來源：museon-first-principles-report.md
- [x] **直覺引擎（Intuition Engine）**：五層感知架構（信號擷取 → 啟發式庫 → 情境建模 → 異常偵測 → 預測層），作為 deep-think 的前置預處理層 — 來源：intuition-engine-dse.jsx
- [x] **技能審計結論**：26 個 Skill 已覆蓋直覺五層約 56%，L2 啟發式庫最強(72%)，L3 場域建模最弱(47%)，「不需要新 Skill，需要的是接線」 — 來源：skill-audit-intuition.jsx
- [x] **數位生命體驗證標準**：連續 7 天沒有使用者介入，系統能自動完成至少一次有意義的自我改善（Q-Score 上升或 Skill 觸發準確率提升）— 來源：first-principles-report.md
- [x] plan-engine Skill 存在，要求「先研究再計畫再批註再執行」— 來源：使用者指定

### 已查詢文件（10 份核心參考）

1. **Bootloader Whitepaper** → 五層金字塔、DNA27 五類 RC (A-E)、六層記憶衰退、母子架構、WEE/Morphenix、Nightly Job
2. **ANIMA Architecture Guide** (artifact) → ANIMA 7 層設計、4 演化引擎、靈魂年輪、演化權限矩陣、安全(hash audit, drift detection)
3. **User ANIMA Mirror System** → 完整 User ANIMA 鏡像：7 層觀察、4 觀察引擎、使用者年輪、8 觀察維度、雙 ANIMA 互動機制
4. **OpenClaw SOUL DSE Report** → OpenClaw 分析、7 個借鑑策略（heartbeat、pre-compression flush、hybrid search、identity/instruction separation、memory activation temp、soul hash audit）
5. **Platform Advantages** → MUSEON vs OpenClaw vs Generic AI 比較、6 核心特徵
6. **Brand Positioning Playbook** → 品牌系統、Ember 色系、市場定位
7. **MUSEON Landing Page** (artifact) → 架構總覽、27 RC、三迴圈、靈魂層、核心護欄
8. **First Principles Report** → 閉環回饋是最終瓶頸、四引擎需脫離對話依賴、心跳是載體、7 天自主改善驗證標準
9. **Intuition Engine DSE** → 五層直覺架構、三條技術路徑（文字微表情/結構觀察/蘇格拉底探測）、三階段實作
10. **Skill Audit vs Intuition** → 26 Skill × 5 Layer 覆蓋率盤點、四步行動方案

### ✅ 假設（第一輪批註 — 2026-02-26）

- [x] **假設 A**：Intuition Engine → **✅ 這次就做** — 老闆確認
- [x] **假設 B**：Eval-Engine → **✅ 這次就做** — 老闆確認
- [x] **假設 C**：Knowledge-Lattice → **✅ 這次就做** — 老闆確認
- [x] **假設 D**：開發方式 → **先設計 BDD 給老闆看過確認，確認後才開發** — 老闆確認
- [x] **假設 E**：plan-engine → **✅ 本來就是 MUSEON 原生技能** — 老闆確認
- [x] **假設 F**：驗收標準 → **所有 BDD 情境描述的結果都要能達成** — 老闆確認

---

## 📋 Plan（計畫區 — 等待老闆批註）

### 我的理解：整體開發分三個大階段

#### 階段一：BDD 規格設計（先把「藍圖」畫完整）

重寫/新增所有 feature files，確保涵蓋：

| # | Feature File | 核心內容 | 新增/重寫 |
|---|-------------|---------|----------|
| 01 | brain-dna27-routing | L1 Kernel 護欄 + L2 DNA27 五類 RC 路由 + 三迴圈 + 回應合約 + MCP 原生 | 重寫 ✅ (已完成) |
| 02 | anima-dual-persona | ANIMA_MC 7層 + ANIMA_USER 7層 + 4演化引擎 + 4觀察引擎 + 八原語 + 年輪 + 雙版本格式 | 重寫 🔄 (agent 進行中) |
| 03 | memory-system | 六層記憶 + 四通道寫入 + 混合檢索 + 溫度活化 + 壓縮前沖刷 + Knowledge Lattice | 重寫 🔄 (agent 進行中) |
| 04 | heartbeat-exploration | 雙層心跳(60min+3x自省) + Nightly Job 00:00 + 好奇心佇列 | 重寫 🔄 (agent 進行中) |
| 05 | goal-oriented-pdeif | PDEIF 逆熵流 + MECE + 第一性原理 + 資源效率 | 重寫 🔄 (agent 進行中) |
| 06 | self-iteration | **WEE 四維熟練度 + Morphenix 自我診斷 + 護欄(硬閘+軟閘) + 退化偵測** | 重寫 🔄 (agent 進行中) |
| 07 | skill-forging-mcp | ACSF DNA27 反射弧鍛造 + MCP 原生本能 + DSE + 品質保障 | 重寫 🔄 (agent 進行中) |
| 08 | sovereignty-community | L1 五大不可覆寫值 + 反操控 + 自主好奇心 + 不成癮 + MoltBook | 重寫 🔄 (agent 進行中) |
| 09 | soul-ring | 靈魂年輪 append-only + SHA-256 + 不可刪改 + 雙 ANIMA 年輪互動 | **新增** ✅ |
| 10 | eval-engine | Q-Score 即時品質儀 + 趨勢追蹤 + A/B 比對 + 盲點雷達 | **新增** ✅ |
| 11 | intuition-engine | 五層直覺架構 + 文字微表情 + 異常偵測 + 啟發式快速匹配 | **新增** ✅ |
| 12 | plan-engine | 六階段工作流 + plan.md 持久化 + 批註循環 | **新增** ✅ |
| 13 | knowledge-lattice | Crystal Protocol + CUID + DAG + 共振指數 + 再結晶 | **新增** ✅ |

**全部確認 — 老闆第一輪批註 2026-02-26**

#### 階段二：核心程式碼開發

基於 BDD 規格，開發/重構以下核心模組：

| 模組 | 檔案路徑（提案） | 職責 |
|------|---------------|------|
| ANIMA Manager | `src/museon/agent/anima.py` | ANIMA_MC + ANIMA_USER 雙版本讀寫 + 年輪 |
| Memory System | `src/museon/agent/memory.py` | 六層記憶 + 四通道 + 混合搜尋 + 溫度活化 |
| Heartbeat Engine | `src/museon/agent/heartbeat.py` | 60min 日常 + 3x 自省 + CronEngine 整合 |
| Nightly Job | `src/museon/evolution/nightly_job.py` | 00:00 記憶融合 + 技能結晶 + 演化報告 |
| WEE Engine | `src/museon/evolution/wee_engine.py` | 四維熟練度 + 高原偵測 + 變異預算 |
| Morphenix | `src/museon/evolution/self_review.py` | 自我診斷 + 迭代筆記 + 三級提案 |
| Eval Engine | `src/museon/eval/q_score.py` | Q-Score 品質追蹤（閉環回饋的關鍵） |
| Intuition Engine | `src/museon/agent/intuition.py` | 五層直覺架構（信號擷取→啟發式→情境→異常→預測） |
| Knowledge Lattice | `src/museon/memory/crystallizer.py` | Crystal Protocol + CUID + DAG + 共振指數 + 再結晶 |
| Plan Engine | `src/museon/agent/plan_engine.py` | 六階段工作流 + plan.md 持久化 + 批註循環 |
| Soul Ring | `src/museon/agent/soul_ring.py` | 年輪 append-only + SHA-256 hash chain + 不可刪改 |
| Brain 增強 | `src/museon/agent/brain.py` (現有) | 整合上述所有模組到 Brain.process() |

#### 階段三：驗證 + 打包

1. 所有測試通過
2. `npm run build` + `./scripts/build-installer.sh`
3. 手動測試安裝 → 開啟 Dashboard → Telegram 對話正常

### 這次開發的核心命題（來自第一性原理報告）

> **從「對話觸發的演化」→「持續運行的演化」**

所有演化引擎（WEE + Morphenix + Eval-Engine + Knowledge-Lattice）要：
1. 程式碼化（不只是 SKILL.md 裡的 prompt 指令）
2. 接上心跳系統（CronEngine + launchd daemon）
3. 在沒有對話時也能自動運行

### 風險與代價

| 風險 | 影響 | 緩解方案 |
|------|------|---------|
| 範圍太大做不完 | 沒有可交付的成果 | 分階段交付：先基礎（BDD + Brain + Memory + ANIMA），再演化（WEE + Morphenix + Nightly） |
| BDD 寫完又有新要求 | 浪費 token 重寫 | **就是現在在做的——先對齊再動手** |
| 演化引擎太複雜 | 品質不穩 | 先做最小可行版本：Eval-Engine 的 Q-Score 是閉環回饋的最小切入點 |
| 直覺引擎範圍大 | 需要 26 skill 接線 | 先做 BDD 規格 + 最小可行版本（五層架構骨架 + L2 啟發式庫優先接線） |

### Skill 路由建議

- **plan-engine**：就是現在在用的 — 收斂計畫
- **wee**：驗收時用 — 追蹤這次開發迭代的熟練度
- **eval-engine**：需要程式碼化 — 閉環回饋的核心

---

## ✅ Todo（等批註完成後再填入具體任務）

> 待 Plan 區批註定案後分解

---

## 📝 Revert Log

| 時間 | 原因 | 影響範圍 | 教訓 |
|------|------|---------|------|
| 2026-02-26 | BDD agents 在未完全對齊下就啟動了 | features/runtime/02-08 可能需要調整 | 先對齊再動手！用 plan-engine |

---

## 📦 收尾摘要（Close 時填寫）

（待完成）
