# Memory Router — 記憶路由表 v1.25

> **用途**：定義「什麼類型的洞見存到哪個記憶系統、什麼時候取出」。第五張工程藍圖。
> **比喻**：郵局分揀表——每封信根據地址分到對應的信箱，不會寄丟也不會重複投遞。
> **更新時機**：新增 Skill 或記憶系統時，必須在同一個 commit 中新增對應的路由規則。
> **建立日期**：2026-03-21
> **搭配**：`docs/skill-manifest-spec.md`（Skill I/O 合約）、各 Skill 的 `memory.writes` 欄位、`docs/operational-contract.md`（操作契約表）
> **v1.25 (2026-04-02)**：荒謬雷達系統——新增雷達資料流：`brain.py` Skill 匹配後 → `absurdity_radar.py update_radar_from_skill()` → `_system/absurdity_radar/{user}.json`；prompt 注入路徑：`brain_prompt_builder.py _build_absurdity_radar_context()` ← `absurdity_radar.py load_radar()`。Nightly step 32.5 每日衰減。
> **v1.24 (2026-04-02)**：藍圖交叉引用同步——persistence-contract v1.49→v1.50（ares→athena 更名同步），同步 system-topology v1.77、persistence-contract v1.50。
> **v1.23 (2026-04-01)**：.runtime 廢除無記憶流向影響（signal_lite 純記憶體不變）；排程優化 Step 13.5 全清不影響記憶寫入路徑；路由表條目無增減。同步 system-topology v1.76、persistence-contract v1.49。
> **v1.22 (2026-04-01)**：Phase 1-3 十項修復——signal_cache 記憶管道正式標記為「keyword 快篩替代」：signal_lite.py 純記憶體計算（request-scoped），不寫入任何記憶系統；原 signal_cache JSON 路由規則廢棄，由 Step 1.5 keyword 快篩 + session context 直接傳遞取代；路由表移除 signal_cache 條目，G3 記憶管線說明同步更新。同步 persistence-contract v1.48、system-topology v1.75。
> **v1.21 (2026-04-01)**：Phase A-C 死碼清理 + signal_lite 遷移——正式移除 reflex_router 記憶管道條目（dna27 collection 已清理，reflex_router 完全退役）；確認 signal_lite 純記憶體計算，不寫入任何記憶系統（routing_signal 不進 memories collection、不進 knowledge-lattice、不進 diary，request-scoped 物件）。
> **v1.20 (2026-04-01)**：Brain 統一重構——G3 記憶管線成員移除 reflex_router（路由退役）；記憶注入路徑統一為 brain.py→brain_prompt_builder.py（消除 brain_fast.py 平行路徑）。
> **v1.19 (2026-03-31)**：Persona Evolution 系統——新增 1 條 diary 路由：nightly_reflection.py（Nightly Step 34）→ `soul_rings.json`（via RingDepositor.deposit_soul_ring），類型=value_calibration，觸發=每夜 Persona 自我反思，內容=特質差異佐證 + 反思摘要。同步 persistence-contract v1.44。
> **v1.17 (2026-03-30)**：Skill 自動演化管線記憶路由——新增 3 條路由：skill-health-tracker→`data/_system/skill_health/{skill_name}.json`（Per-Skill 健康度快照，每夜 Step 19.5 寫入，SkillDraftForger 讀取判斷退化）；skill-draft-forger→`data/_system/skills_draft/draft_*.json`（Skill 草稿，Step 19.6 寫入，SkillQA Gate 讀取驗證）；skill-qa-gate→更新 `skills_draft/draft_*.json` 狀態欄位（pending_qa→approved/quarantine）。新增 1 條 feedback-loop 持久化路由：feedback-loop→`data/_system/feedback_loop/daily_summary.json`（每次互動後寫入，Nightly 信號源 7 讀取）。同步 system-topology v1.67、blast-radius v1.85。
> **v1.16 (2026-03-30)**：新 Skill 群批次補路由——新增 7 條 knowledge-lattice 路由：finance-pilot→週期分析洞見（/close 結算時）、花費行為模式（累計 3 個月以上）；course-forge→課程設計模式（Pipeline 完成時）；ad-pilot→廣告優化洞見（/optimize 含品質護欄時）；equity-architect→合夥決策記錄（Mode B 選定方案時，路由至 decision-tracker→knowledge-lattice）；prompt-stresstest→壓測發現模式（final_gate 未通過時）；talent-match→招募模式洞見（證據面試包完成時）。
> **v1.15 (2026-03-30)**：商業模式健檢（biz-diagnostic）——新增 1 條 knowledge-lattice 路由：biz-diagnostic→diagnostic_crystal（健檢完成時，含商業診斷摘要 + DARWIN 模擬參數 + 優先問題，永久）。同步 system-topology v1.65。
> **v1.14 (2026-03-30)**：市場戰神（Market Ares）——新增 1 條 knowledge-lattice 路由：market-ares→simulation_crystal（策略模擬結果結晶，含 52 週演化摘要 + 最佳策略組合，永久）；新增 1 條 eval-engine 路由：market-ares→模擬準確度追蹤（真實數據 vs 模擬結果的偏差率）。同步 system-topology v1.64、blast-radius v1.83、joint-map v1.53、persistence-contract v1.41。
> **v1.13 (2026-03-29)**：戰神系統（Ares）——新增 2 條 knowledge-lattice 路由：anima-individual→individual_crystal（ANIMA 個體分析結晶，永久）、ares→strategy_crystal（戰神戰略結晶，永久）；新增 2 條 user-model 路由：anima-individual→關係網路維度、ares→戰略偏好維度。同步 system-topology v1.62、blast-radius v1.80、joint-map v1.52、persistence-contract v1.40。
> **v1.12 (2026-03-29)**：OneMuse 能量解讀技能群——新增 3 條 knowledge-lattice 路由：energy-reading→energy_crystal（八方位能量解讀結晶，永久）、wan-miu-16→persona_crystal（萬謬16型人格結晶，永久）、combined-reading→relationship_crystal（合盤能量比對結晶，永久）。同步 system-topology v1.61、blast-radius v1.79、joint-map v1.51、persistence-contract v1.39。
> **v1.11 (2026-03-28)**：死碼清理後同步——移除已刪除模組的路由規則：learning/strategy_accumulator（StrategyAccumulator→heuristics 路由已刪，功能由 insight-extractor 整合）；memory/epigenetic_router（不再介入記憶注入前路由）；memory/proactive_predictor（記憶路由不再涉及需求預判）；pulse/group_session_proactive（群組記憶路由不再涉及 group_session_proactive）。
> **v1.10 (2026-03-27)**：有機體進化計畫——新增 4 條路由規則：晨報個案→InsightExtractor→knowledge-lattice（case_crystal）+ heuristics；自主探索→InsightExtractor→knowledge-lattice（exploration_crystal）；InsightExtractor→MemoryGraph（建立洞見間關聯邊）；StrategyAccumulator→heuristics.json（升級為策略信條時）。同步 system-topology v1.54、blast-radius v1.71、joint-map v1.48、persistence-contract v1.37。
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
| biz-diagnostic | 健檢診斷摘要（商業模式弱點 + DARWIN 模擬參數 + 優先問題） | 健檢完成時 | diagnostic_crystal |
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
| finance-pilot | 週期分析洞見 | /close 結算時 | Insight | knowledge-lattice |
| finance-pilot | 花費行為模式 | 累計 3 個月以上 | Pattern | knowledge-lattice |
| course-forge | 課程設計模式 | Pipeline 完成時 | Pattern | knowledge-lattice |
| ad-pilot | 廣告優化洞見 | /optimize 含品質護欄時 | Insight | knowledge-lattice |
| equity-architect | 合夥決策記錄 | Mode B 選定方案時 | Decision | decision-tracker → knowledge-lattice |
| prompt-stresstest | 壓測發現模式 | final_gate 未通過時 | Pattern | knowledge-lattice |
| talent-match | 招募模式洞見 | 證據面試包完成時 | Insight | knowledge-lattice |

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
| human-design-blueprint | 人類圖類型 + 策略 + 內在權威 + 人生角色 | 人類圖解讀完成時 |

### 🔵 品牌建構結晶 → knowledge-lattice + user-model

| 來源 Skill | 洞見類型 | 寫入條件 | 結晶類型 |
|-----------|---------|---------|---------|
| brand-builder | 七框架分析結論 + 三選項定位方案 + 品牌策略包 | 品牌策略包產出時 | brand_crystal |
| brand-discovery | 客戶品牌訪談摘要 + 競爭格局洞見 + 客戶 JTBD | 50 問訪談完成並確認時 | client_crystal |
| workflow-brand-consulting | 品牌手冊完整交付物 + 定位決策 | HTML 手冊渲染完成時 | brand_crystal |

| 來源 Skill | 更新維度 | 寫入條件 |
|-----------|---------|---------|
| brand-discovery | 客戶業態 + 品牌挑戰類型 + 服務行業偏好 | 訪談完成時（更新 user-model 的行業知識維度） |

### 🔵 ESG 分析結晶 → knowledge-lattice

| 來源 Skill | 洞見類型 | 寫入條件 | 結晶類型 |
|-----------|---------|---------|---------|
| esg-architect-pro | 重大性評估結論 + 碳費影響量化 + 漂綠偵測結果 | 報告產出時 | esg_crystal |
| meeting-intelligence | 決議 + 博弈模式 + 承諾漂移 + 人格動態 | 會議分析完成時 | meeting_crystal |

### 🔵 OneMuse 能量解讀結晶 → knowledge-lattice + user-model

| 來源 Skill | 洞見類型 | 寫入條件 | 結晶類型 |
|-----------|---------|---------|---------|
| energy-reading | 八方位能量解讀結論 + 方位能量分布 | 能量解讀完成時 | energy_crystal |
| wan-miu-16 | 萬謬16型人格分析 + 人格特質洞見 | 人格分析完成時 | persona_crystal |
| combined-reading | 合盤能量比對 + 關係動態分析 | 合盤比對完成時 | relationship_crystal |

| 來源 Skill | 更新維度 | 寫入條件 |
|-----------|---------|---------|
| energy-reading | 能量狀態 + 方位偏好 | 解讀完成時（更新 user-model 的能量維度） |
| wan-miu-16 | 人格類型 + 行為傾向 | 分析完成時（更新 user-model 的人格維度） |
| combined-reading | 關係模式 + 互動動態 | 比對完成時（更新 user-model 的關係維度） |

### 🔵 戰神系統結晶 → knowledge-lattice + user-model

| 來源 Skill | 洞見類型 | 寫入條件 | 結晶類型 |
|-----------|---------|---------|---------|
| anima-individual | ANIMA 個體分析結論（七層鏡像 + 八大槓桿 + 關係溫度） | 個體分析完成時 | individual_crystal |
| ares | 戰神戰略分析（人物策略 + 多層槓桿路徑 + 連動模擬） | 戰略分析/戰前簡報完成時 | strategy_crystal |

| 來源 Skill | 更新維度 | 寫入條件 |
|-----------|---------|---------|
| anima-individual | 關係網路 + 人際互動模式 | 個體分析完成時（更新 user-model 的關係網路維度） |
| ares | 戰略偏好 + 博弈決策風格 | 戰略分析完成時（更新 user-model 的戰略偏好維度） |

> **消費者**：
> - knowledge-lattice individual_crystal / strategy_crystal → brain.py `_build_memory_inject()` 語意檢索
> - user-model 關係網路/戰略偏好維度 → brain.py 個人化調適
> - data/ares/profiles/ → ares Skill 讀取個體檔案做跨人物分析

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

### 🔵 持續學習引擎路由（v1.10 新增）

| 來源 | 洞見類型 | 去向 | 結晶/規則類型 | 寫入條件 |
|------|---------|------|-------------|---------|
| 晨報個案（Nightly 晨報） | 業務洞見萃取 | InsightExtractor → knowledge-lattice | case_crystal | 晨報完成後自動萃取 |
| 晨報個案（Nightly 晨報） | 可操作規則 | InsightExtractor → heuristics.json | guard（方法論） | 洞見可操作化時 |
| 自主探索（Explorer） | 探索發現 | InsightExtractor → knowledge-lattice | exploration_crystal | 探索完成且品質 ≥ NEW_INSIGHT |
| InsightExtractor 任何輸出 | 洞見間關聯 | InsightExtractor → MemoryGraph | edge（關聯邊） | 萃取時自動建立語意關聯 |
| ~~StrategyAccumulator~~ | ~~策略信條~~ | ~~StrategyAccumulator → heuristics.json（已刪除 v1.11，功能由 insight-extractor 整合）~~ | - | - |

> **消費者**：
> - knowledge-lattice case_crystal / exploration_crystal → brain.py `_build_memory_inject()` 語意檢索
> - heuristics.json → `brain_prompt_builder.py` Stage 5 `format_rules_for_prompt()` 注入每次對話 prompt
> - MemoryGraph edges → brain.py 記憶注入時查詢關聯記憶

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

### 📔 Persona 自我反思 → diary（soul_rings.json）（v1.19 新增）

| 來源 | 觸發 | 去向 | 路由方法 | 內容 |
|------|------|------|---------|------|
| nightly_reflection.py（Nightly Step 34） | 每夜 Persona 自我反思 | `anima/soul_rings.json` | RingDepositor.deposit_soul_ring | 特質差異佐證 + 反思摘要（value_calibration 類型） |

> **消費者**：DiaryStore.recall_soul_rings() → MemoryReflector → brain_prompt_builder memory zone（Soul Ring 年輪反思）
> **路由類型**：value_calibration（Persona 特質校準記錄，用於追蹤 P-traits 夜間演化軌跡）

### 🔴 荒謬雷達 → _system/absurdity_radar（v1.25 新增）

| 來源 | 觸發 | 去向 | 路由方法 | 內容 |
|------|------|------|---------|------|
| 荒謬雷達 | brain.py (Skill 使用後) | absurdity_radar.py | _system/absurdity_radar/{user}.json | 漸進更新 | brain_prompt_builder (persona zone) + skill_router (Layer 4) |

> **寫入路徑**：`brain.py` Skill 匹配後 → `absurdity_radar.py update_radar_from_skill()` → `_system/absurdity_radar/{user}.json`
> **讀取路徑（prompt 注入）**：`brain_prompt_builder.py _build_absurdity_radar_context()` ← `absurdity_radar.py load_radar()`
> **讀取路徑（路由加權）**：`skill_router.py` Layer 4 absurdity gap affinity ← `absurdity_radar.py load_radar()`
> **衰減機制**：Nightly step 32.5 `_step_absurdity_radar_recalc` 每日自動衰減雷達各維度分值

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

### 規則 6：反思層路由（MemoryReflector 直接路由，v1.11 更新）

> **v1.11 更新**：EpigeneticRouter 已刪除（v1.59）。反思層現由 MemoryReflector 直接處理，不再經過多圖遍歷中間層。

| 來源 | 經由 | 去向 | 說明 |
|------|------|------|------|
| MemoryManager.recall() | ~~EpigeneticRouter →~~ MemoryReflector | brain_prompt_builder memory zone | 六層記憶反思摘要（矛盾偵測/重複模式/時間軸） |
| DiaryStore.recall_soul_rings() | MemoryReflector（直接） | brain_prompt_builder memory zone | Soul Ring 年輪反思 |
| KnowledgeLattice.recall_tiered() | MemoryReflector（直接） | brain_prompt_builder memory zone | 知識結晶反思 |

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
| v1.19 | 2026-03-31 | Persona Evolution 系統——新增 1 條 diary 路由（nightly_reflection.py Nightly Step 34 → soul_rings.json via RingDepositor.deposit_soul_ring，value_calibration 類型，內容=特質差異佐證+反思摘要）。同步 persist v1.44 |
| v1.18 | 2026-03-31 | 體液系統迭代——新增 Skill 教訓預載路由（brain_prompt_builder `_build_skill_lesson_context()` 讀取 `data/skills/native/{name}/_lessons.json` 注入 system prompt）；新增 SessionAdjustment 路由（L4 觀察者寫入 `_system/session_adjustments/{id}.json`，brain_prompt_builder `_auto_adjust_from_history()` 讀取）；新增覺察訊號路由（triage_step 寫入 `_system/triage_queue.jsonl`，Nightly Step 5.8 消費到 Morphenix 迭代筆記）；同步 topology v1.68、blast v1.86、joint v1.56、persist v1.42 |
| v1.17 | 2026-03-30 | Skill 自動演化管線——新增 3 條知識路由（skill_health_tracker→skill_health/ 健康度快照、feedback_loop→daily_summary.json 品質摘要、skill_draft_forger→skills_draft/ 草稿暫存） |
| v1.16 | 2026-03-30 | 新 Skill 群批次補路由——新增 7 條 knowledge-lattice 路由：finance-pilot（週期洞見/行為模式）、course-forge（課程設計模式）、ad-pilot（廣告優化洞見）、equity-architect（合夥決策記錄，via decision-tracker）、prompt-stresstest（壓測發現模式）、talent-match（招募模式洞見） |
| v1.13 | 2026-03-29 | 戰神系統（Ares）——新增 2 條 knowledge-lattice 路由（anima-individual→individual_crystal、ares→strategy_crystal）+ 2 條 user-model 路由（關係網路/戰略偏好維度更新）；新增消費者 data/ares/profiles/ 個體檔案；同步 topology v1.62、blast v1.80、joint v1.52、persist v1.40 |
| v1.12 | 2026-03-29 | OneMuse 能量解讀技能群——新增 3 條 knowledge-lattice 路由（energy-reading→energy_crystal、wan-miu-16→persona_crystal、combined-reading→relationship_crystal）+ 3 條 user-model 路由（能量/人格/關係維度更新）；同步 topology v1.61、blast v1.79、joint v1.51、persist v1.39 |
| v1.10 | 2026-03-27 | 持續學習引擎路由——新增 4 條路由（晨報個案→case_crystal+heuristics、自主探索→exploration_crystal、InsightExtractor→MemoryGraph edges、StrategyAccumulator→heuristics conviction）；同步 topology v1.54、blast v1.71、joint v1.48、persist v1.37 |
| v1.7 | 2026-03-24 | 操作記憶路由——新增規則 7（外部操作 PROCEDURE 結晶路由）；搭配第六張藍圖 operational-contract.md |
| v1.6 | 2026-03-23 | Project Epigenesis 接線——新增規則 6（反思層路由）；EpigeneticRouter 在 brain.py _build_memory_inject() 中觸發 Hindsight 反思；4 條路由（memories→reflector、soul_rings→reflector、crystals→reflector、changelog→reflector）；反思摘要注入 memory zone；純 RO 計算不寫入持久層；同步 blast-radius v1.55、joint-map v1.40、persistence-contract v1.32 |
| v1.5 | 2026-03-22 | 新增「系統基礎設施持久資料」區塊——收錄 sparse_idf.json（BM25 IDF 表），Writer: vector/sparse_embedder.py，Reader: SparseEmbedder init |
| v1.4 | 2026-03-22 | P0-P3 升級——新增 3 條 knowledge-lattice 路由（report-forge→report_crystal、system-health-check→health_crystal、decision-tracker→decision_crystal）；新增 1 條 user-model 路由（decision-tracker→決策偏好+風險容忍度）；同步 system-topology v1.35、persistence-contract v1.28、blast-radius v1.46、joint-map v1.33 |
| v1.3 | 2026-03-22 | 經驗諮詢閘門——新增 Procedure 結晶路由（brain.py 經驗回放 + crystal_actuator Lesson 升級），消費者：brain.py _build_memory_inject() 第四層經驗回放 |
| v1.2 | 2026-03-21 | 新增 persona-router (baihe) 路由（lord_profile.json + baihe_cache.json → user-model）；Skill 鍛造膠合層修復——49 個 Skill 的 memory.writes/reads 補齊 |
| v1.1 | 2026-03-21 | chat_scope 隔離：新增規則 5（群組記憶 chat_scope 隔離），memory_manager store/recall/vector 全路徑支援 chat_scope_filter + exclude_scopes；外部使用者 ANIMA v3.0（ExternalAnimaManager per-client 獨立八原語+七層觀察） |
| v1.0 | 2026-03-21 | 初始版本——定義 8 大記憶系統路由表、4 條路由規則 |
