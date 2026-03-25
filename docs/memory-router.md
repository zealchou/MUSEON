# Memory Router — 記憶路由表 v1.9

> **用途**：定義「什麼類型的洞見存到哪個記憶系統、什麼時候取出」。第五張工程藍圖。
> **比喻**：郵局分揀表——每封信根據地址分到對應的信箱，不會寄丟也不會重複投遞。
> **更新時機**：新增 Skill 或記憶系統時，必須在同一個 commit 中新增對應的路由規則。
> **建立日期**：2026-03-21
> **搭配**：`docs/skill-manifest-spec.md`（Skill I/O 合約）、各 Skill 的 `memory.writes` 欄位、`docs/operational-contract.md`（操作契約表）
> **v1.9 (2026-03-25)**：七條斷裂管線修復——dispatch/completed → Nightly Step 18.5 客戶互動萃取 → external_users + clients personality_notes；ExternalAnima search_by_keyword dict topics 修復；Intuition heuristics → prompt 注入；Guardian mothership_queue → Gateway 啟動消費；Procedure 升級門檻 3→1
> **v1.7 (2026-03-24)**：新增操作記憶路由規則 7——外部操作的成功/失敗經驗存入 knowledge-lattice 的 PROCEDURE 結晶；搭配第六張藍圖 `operational-contract.md`

---

## 記憶系統總覽

| # | 記憶系統 | 存儲引擎 | 生命週期 | 跨 Session | 負責模組 |
|---|---------|---------|---------|-----------|---------|
| 1 | **knowledge-lattice** | Qdrant `crystals` + JSON `crystals.json` | 永久（可再結晶） | ✅ | `knowledge_lattice.py` |
| 2 | **user-model** | JSON `lord_profile.json` + PulseDB | 永久（持續更新） | ✅ | `brain.py` (via ANIMA_MC) |
| 3 | **wee** | SQLite `workflow_state.db` | 永久（版本化） | ✅ | `wee_engine.py` |
| 4 | **eval-engine** | PulseDB `metacognition` 表 | 永久（時序資料） | ✅ | `metacognition.py` |
| 5 | **session-log** | Markdown `memory/session-log.md` | 永久（倒序追加） | ✅ | Claude auto-memory |
| 6 | **auto-memory** | Markdown `MEMORY.md` | 永久（手動維護） | ✅ | Claude auto-memory |
| 7 | **morphenix** | JSON `morphenix/proposals/` | 永久（提案→執行→歸檔） | ✅ | `morphenix` (概念層) |
| 8 | **diary** | Markdown `SOUL.md` + JSON `soul_rings.json` | 永久 | ✅ | `diary_store.py` |

---

## 路由表

### 🔵 高價值洞見 → knowledge-lattice

| 來源 Skill | 洞見類型 | 寫入條件 | 結晶類型 |
|-----------|---------|---------|---------|
| roundtable | 仲裁裁決 + 異議摘要 | 使用者做出仲裁決定時 | decision_crystal |
| investment-masters | 軍師會診共識/分歧 | 會診完成時 | market_crystal |
| market-core | 多空論據 + 信心水準 | 分析報告產出時 | market_crystal |
| risk-matrix | 配置方案 + 壓力測試結果 | 配置建議產出時 | strategy_crystal |
| master-strategy | 戰略評估 + 兵棋推演結果 | 沙盤推演完成時 | strategy_crystal |
| business-12 | 商業診斷結論 | 12 力診斷完成時 | business_crystal |
| ssa-consultant | 銷售策略 + 成交對話設計 | 顧問/教練流程完成時 | business_crystal |
| xmodel | 破框路徑 + 實驗設計 | 多方案產出時 | solution_crystal |
| dharma | 思維轉化里程碑 | 六步驟完成到 Align 時 | insight_crystal |
| philo-dialectic | 概念澄清 + 論證分析 | 思辨推演完成時 | insight_crystal |
| deep-think | 思考軌跡中的關鍵發現 | 信心水準 ≥ 高 且 有新洞見時 | insight_crystal |
| meta-learning | 學習策略 + 盲點發現 | 學習模式分析完成時 | learning_crystal |
| dse | 技術融合可行性結論 | 驗證完成時 | tech_crystal |
| shadow | 博弈模式辨識結論 | 防禦/洞察分析完成時 | insight_crystal |
| brain.py (經驗回放) | 成功操作程序 + 步驟 + Skill 調用記錄 | Lesson 成功 3 次自動升級，或手動結晶 | procedure_crystal |
| crystal_actuator | Lesson → Procedure 升級 | success_count ≥ 3 + g2_structure ≥ 2 步驟 | procedure_crystal |
| report-forge | 報告核心洞見 + 分析結論 | 報告產出時（P2-2 新增） | report_crystal |
| system-health-check | 系統健康診斷結論 + 修復建議 | 健康檢查完成時（P1-1 新增） | health_crystal |
| decision-tracker | 決策歷程 + 選項比較 + 最終選擇理由 | 決策記錄完成時（P1-1 新增） | decision_crystal |

### 🟢 使用者理解 → user-model

| 來源 Skill | 更新維度 | 寫入條件 |
|-----------|---------|---------|
| roundtable | 決策風格 + 價值優先序 | 使用者仲裁時（從裁決推斷偏好） |
| query-clarity | 問題習慣 + 脈絡偏好 | 問題品質掃描結果（長期模式） |
| deep-think | 思維偏好（感性/理性比例） | Phase 0 訊號分流累積統計 |
| resonance | 情緒模式 + 觸發點 | 情緒承接完成時 |
| eval-engine | 滿意度代理指標 | 每次回答品質評分後 |
| wee | 技能熟練度維度 | 工作流熟練度升級時 |
| knowledge-lattice | 領域專長維度 | 結晶累積跨越閾值時 |
| persona-router (baihe) | 領主畫像 + 進諫策略 | 百合引擎路由完成時 |
| decision-tracker | 決策偏好 + 風險容忍度 | 決策記錄完成時（P1-1 新增） |

### 🟡 工作流記憶 → wee

| 來源 Skill | 記憶類型 | 寫入條件 |
|-----------|---------|---------|
| orchestrator | 執行軌跡 + 編排決策 | 多 Skill 編排完成時 |
| wee（自身） | 教練迴路結果 | 啟動五問/結果五問/失敗五因完成時 |
| pdeif | 逆熵流設計 | 流程設計完成時 |
| workflow-* | 工作流執行紀錄 | 工作流完成時 |

### 🟠 系統演化 → morphenix

| 來源 Skill | 記憶類型 | 寫入條件 |
|-----------|---------|---------|
| eval-engine | 品質趨勢 + 盲點雷達 | 偵測到系統性弱項時 |
| env-radar | 外部訊號 + 演化壓力 | 環境掃描發現重要變化時 |
| sandbox-lab | 實驗結果 | 實驗完成且有結論時 |
| qa-auditor | 審計報告 + 回歸問題 | 審計完成時 |

### 🔵 教訓蒸餾 → crystal_rules.json（v1.8 新增）

| 來源 | 洞見類型 | 寫入條件 | 規則類型 |
|------|---------|---------|---------|
| metacognition PostCognition | REVISE 標記的修改建議 | Nightly Step 5.6.5 掃描最近 7 天 | guard（方法論） |
| memory_v3 failure_distill | 失敗經驗教訓 | Nightly Step 5.6.5 掃描最近 7 天 | guard（反模式） |
| boss_directive | 老闆直接下達的操作紀律 | 手動寫入 | guard（永久） |

> **消費者**：Crystal Actuator → `brain_prompt_builder.py` Stage 5 `format_rules_for_prompt()` → 注入每次對話 prompt
> **TTL**：metacog/failure 規則 14-30 天；boss_directive 規則 1 年
> **設計理念**：「知道」→「智慧」的橋樑。教訓不靠語義搜索碰運氣，而是主動推送到每次對話的 prompt。

### ⚪ 跨 Session 持久 → auto-memory / session-log

| 來源 | 記憶類型 | 目標 | 寫入條件 |
|------|---------|------|---------|
| 任何 Skill | Debug 教訓 + 架構決策 | auto-memory (MEMORY.md) | 跨多次互動驗證的穩定模式 |
| 每次 session | 工作摘要 | session-log | session 結束或重要里程碑時 |
| 重大迭代 | 迭代紀錄 | session-log | commit 完成時 |

### 🔩 系統基礎設施持久資料

| 檔案路徑 | 用途 | Writer | 寫入觸發 | Reader | 讀取觸發 |
|---------|------|--------|---------|--------|---------|
| `data/_system/sparse_idf.json` | BM25 IDF 表（稀疏向量搜尋權重） | `vector/sparse_embedder.py` (`build_idf()` → `_save_idf()`) | Nightly Step 8.7 `_step_sparse_idf_rebuild()` (via `VectorBridge.build_sparse_idf()`) | `vector/sparse_embedder.py` (`_load_idf()`) | SparseEmbedder 初始化時自動載入 |

---

## 路由規則

### 規則 1：寫入必有消費者
每個 `memory.writes` 在此路由表中必須有對應的消費場景。沒有消費者的寫入 = Dead Write。

### 規則 2：消費者必有來源
每個 `memory.reads` 必須在此路由表中有對應的寫入方。讀取不存在的資料 = Phantom Read。

### 規則 3：不重複存放
同一筆洞見只存一個地方。如果一個軍師會診結論同時對 knowledge-lattice 和 user-model 有價值，存 knowledge-lattice（完整內容），user-model 只更新使用者偏好維度（衍生更新）。

### 規則 4：結晶優先
凡是「可能未來有用」的洞見，優先存 knowledge-lattice。其他記憶系統只存各自負責的特定維度。

### 規則 5：chat_scope 隔離
群組記憶帶 `chat_scope="group:{group_id}"`，recall 時用 `chat_scope_filter` 過濾，避免不同群組記憶交叉污染。無 scope 的舊記憶（向下相容）在任何 filter 下均可見。可用 `exclude_scopes` 排除指定群組。

### 規則 6：反思層路由（Project Epigenesis）
EpigeneticRouter 在 brain.py `_build_memory_inject()` 中觸發，對已召回的記憶執行 Hindsight 反思：

| 來源 | 經由 | 去向 | 說明 |
|------|------|------|------|
| MemoryManager.recall() | EpigeneticRouter → MemoryReflector | brain_prompt_builder memory zone | 六層記憶反思摘要（矛盾偵測/重複模式/時間軸） |
| DiaryStore.recall_soul_rings() | EpigeneticRouter (temporal/causal graph) → MemoryReflector | brain_prompt_builder memory zone | Soul Ring 年輪的時間/因果圖遍歷結果 |
| KnowledgeLattice.recall_tiered() | EpigeneticRouter (crystal graph) → MemoryReflector | brain_prompt_builder memory zone | 知識結晶反思（與記憶交叉比對） |
| AnimaChangelog.get_evolution_summary() | EpigeneticRouter (temporal graph) | brain_prompt_builder memory zone | 使用者演化趨勢摘要（僅時間意圖觸發） |

> **反思層不寫入任何持久狀態**——純 CPU 計算，不呼叫 LLM，延遲 < 50ms。
> AdaptiveDecay 負責 Activation 排序（ACT-R 公式），MemoryReflector 負責交叉反思。

---

### 規則 7：操作記憶路由（Operational Memory）

外部操作（git push、API 呼叫、服務重啟）的成功/失敗經驗存入 knowledge-lattice 的 PROCEDURE 結晶：

| 來源 | 事件 | 去向 | 結晶類型 |
|------|------|------|---------|
| scripts/workflows/*.sh | 操作成功 | knowledge-lattice | procedure_crystal（更新 last_success + confidence） |
| scripts/workflows/*.sh | 操作失敗 | knowledge-lattice | procedure_crystal（追加 known_failures） |
| Brain 即興操作 | 首次成功 | knowledge-lattice | procedure_crystal（新建結晶 + executable 路徑） |
| Nightly 蒸餾 | 日誌分析 | knowledge-lattice | procedure_crystal（合併新失敗模式） |

消費者：Brain 執行外部操作前，語義搜尋 `domain=operations/*` 的 PROCEDURE 結晶。
搭配：`docs/operational-contract.md`（第六張藍圖）定義預期失敗清單。

> **狀態**：路由規則已定義，Procedure Crystal schema 待實作（見 `docs/project-operational-memory.md` 迭代 4-7）

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.7 | 2026-03-24 | 操作記憶路由——新增規則 7（外部操作 PROCEDURE 結晶路由）；搭配第六張藍圖 operational-contract.md |
| v1.6 | 2026-03-23 | Project Epigenesis 接線——新增規則 6（反思層路由）；EpigeneticRouter 在 brain.py _build_memory_inject() 中觸發 Hindsight 反思；4 條路由（memories→reflector、soul_rings→reflector、crystals→reflector、changelog→reflector）；反思摘要注入 memory zone；純 RO 計算不寫入持久層；同步 blast-radius v1.55、joint-map v1.40、persistence-contract v1.32 |
| v1.5 | 2026-03-22 | 新增「系統基礎設施持久資料」區塊——收錄 sparse_idf.json（BM25 IDF 表），Writer: vector/sparse_embedder.py，Reader: SparseEmbedder init |
| v1.4 | 2026-03-22 | P0-P3 升級——新增 3 條 knowledge-lattice 路由（report-forge→report_crystal、system-health-check→health_crystal、decision-tracker→decision_crystal）；新增 1 條 user-model 路由（decision-tracker→決策偏好+風險容忍度）；同步 system-topology v1.35、persistence-contract v1.28、blast-radius v1.46、joint-map v1.33 |
| v1.3 | 2026-03-22 | 經驗諮詢閘門——新增 Procedure 結晶路由（brain.py 經驗回放 + crystal_actuator Lesson 升級），消費者：brain.py _build_memory_inject() 第四層經驗回放 |
| v1.2 | 2026-03-21 | 新增 persona-router (baihe) 路由（lord_profile.json + baihe_cache.json → user-model）；Skill 鍛造膠合層修復——49 個 Skill 的 memory.writes/reads 補齊 |
| v1.1 | 2026-03-21 | chat_scope 隔離：新增規則 5（群組記憶 chat_scope 隔離），memory_manager store/recall/vector 全路徑支援 chat_scope_filter + exclude_scopes；外部使用者 ANIMA v3.0（ExternalAnimaManager per-client 獨立八原語+七層觀察） |
| v1.0 | 2026-03-21 | 初始版本——定義 8 大記憶系統路由表、4 條路由規則 |
