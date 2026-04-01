# Joint Map — 共享可變狀態接頭圖 v1.60

> **用途**：任何程式碼修改前，查閱此圖確認「我要改的模組碰了哪些共享狀態、誰還在讀寫同一根管子」。
> **比喻**：水電圖畫了管線位置，接頭圖畫的是「哪個水龍頭接哪根管、這根管誰負責」。
> **更新時機**：改變共享檔案的讀寫者或格式時，必須在同一個 commit 中同步更新此文件。
> **建立日期**：2026-03-15（DSE 第二輪排查後建立）
> **v1.61 (2026-04-01)**：Phase A-C 死碼清理 + signal_lite 遷移——移除 reflex_router 相關共享狀態條目（Qdrant dna27 collection 已清理，routing_signal 純記憶體，不另立條目）；移除 brain_observer 讀寫者條目（#46 pending_insights.json 寫入者改為 brain.py L4 觀察者，#47 context_cache 寫入者移除 brain_observer.py）；新增 #74 signal_lite 的 SignalLite 物件（純記憶體計算，寫入者 signal_lite.py，讀取者 brain.py + metacognition.py + telegram_pump.py）；G3 記憶管線移除 reflex_router；共享狀態 73→74 個。
> **v1.60 (2026-04-01)**：Brain 統一重構——刪除 brain_fast.py 相關共享狀態讀寫者條目（pending_insights.json #46、context_cache #47 的讀取者從 brain_fast.py 改為統一 brain.py）；Qdrant dna27 collection 標記為廢棄（reflex_router 退役）；session 歷史統一為 brain.py 單一讀寫者（消除 brain_fast.py 的平行 session 管理）；共享狀態 73→72 個。
> **v1.59 (2026-03-31)**：推播系統重構——刪除 #41 索引項「PushBudget 單例」（`pulse/push_budget.py` 已刪除，全局推送配額改由 ProactiveDispatcher 三桶分級配額內建管理）；#8 PulseDB 寫入者 4→3（移除 push_budget.py），讀取者 13→12（移除 push_budget.py）；pulse_engine.py 不再經由 PushBudget 讀取 push_log；push_journal_24h.json（#48）寫入者維持 proactive_dispatcher.py 獨自寫入（PushBudget 已非第二寫入路徑）；共享狀態 73→72 個（刪除 #41 PushBudget 單例）。同步 blast-radius v1.91、system-topology v1.72、persistence-contract v1.45。
> **v1.58 (2026-03-31)**：Persona Evolution 系統——新增 #70 `ANIMA_MC.personality.trait_dimensions`（🟠 人格特質維度，P1-P5 需 evolution_write，C1-C5 FREE，寫入者=trait_engine.py+nightly_reflection.py，讀取者=brain_prompt_builder+growth_stage+mask_engine+dissent_engine）；新增 #71 `ANIMA_MC.evolution.trait_history`（🟢 APPEND_ONLY 特質變化歷史，寫入者=nightly_reflection.py，讀取者=momentum_brake+drift_detector）；新增 #72 `ANIMA_MC.evolution.stage_history`（🟢 APPEND_ONLY 成長階段歷史，寫入者=brain_observation.py，讀取者=growth_stage）；新增 #73 `_system/mask_states.json`（🟢 短暫面具狀態，寫入者=mask_engine.py，讀取者=mask_engine.py，7 天自動清理）；更新 `_system/crystal_rules.json`（G5 新增讀取者=dissent_engine.py 矛盾校驗）；共享狀態 69→73 個。同步 blast-radius、system-topology。
> **v1.57 (2026-03-31)**：9 條斷裂接線修復——新增 #69 `data/_system/museoff/finding_counts.json`（🟢 MuseOff 異常計數持久化，寫入者=doctor/finding.py record_occurrence()，讀取者=doctor/museoff.py ≥3次升級判斷，原子 JSON 讀寫，格式：{finding_key: int}，永久累積）；共享狀態 68→69 個。同步 blast-radius v1.87、system-topology v1.69、persistence-contract v1.43。
> **v1.56 (2026-03-31)**：體液系統迭代——新增 #62-#68 共 7 個共享狀態：#62 `data/_system/triage_queue.jsonl`（🟢 覺察訊號佇列，寫入者=各覺察源+triage_step，讀取者=triage_step Nightly 消費）；#63 `data/_system/awareness_log.jsonl`（🟢 覺察日誌，寫入者=triage_step，讀取者=triage_step accumulation）；#64 `data/_system/pending_adjustments.json`（🟢 待處理調整，寫入者=triage_step，讀取者=session_adjustment）；#65 `data/_system/nightly_priority_queue.json`（🟢 Nightly 優先佇列，寫入者=triage_step，讀取者=triage_to_morphenix）；#66 `data/_system/session_adjustments/{id}.json`（🟢 即時行為調整，寫入者=L4 觀察者，讀取者=brain_prompt_builder _auto_adjust_from_history()）；#67 `data/_system/triage_human_queue.json`（🟢 人工審核佇列，寫入者=triage_step HIGH/CRITICAL，讀取者=triage_step drain + Telegram 告警）；#68 `data/skills/native/{name}/_lessons.json`（🟢 Skill 教訓檔，寫入者=session_adjustment promote，讀取者=brain_prompt_builder _build_skill_lesson_context() 注入 system prompt）；共享狀態 61→68 個。同步 topology v1.68、blast-radius v1.86、memory-router v1.18、persistence-contract v1.42。
> **v1.55 (2026-03-30)**：Skill 自動演化管線——新增 #59 `data/_system/skills_draft/`（🟢 Skill 草稿暫存區，寫入者=skill_draft_forger.py，讀取者=skill_qa_gate.py + skill_install_worker.py + telegram.py callback，原子寫入）；新增 #60 `data/_system/skill_health/`（🟢 Per-Skill 健康度快照，寫入者=skill_health_tracker.py，讀取者=skill_draft_forger.py optimize_existing 模式，原子寫入）；新增 #61 `data/_system/feedback_loop/daily_summary.json`（🟢 FeedbackLoop 品質摘要，寫入者=feedback_loop.py singleton，讀取者=nightly_pipeline.py 信號源 7，原子寫入）；共享狀態 58→61 個。同步 system-topology v1.67、blast-radius v1.85、memory-router v1.17。
> **v1.54 (2026-03-30)**：13 個新 Skill Post-Build 共享狀態補登——新增 #58 `data/equity-architect/case_files/`（🟢 Case File 跨 Session 持久化，寫入者=equity-architect Skill，讀取者=equity-architect 續談模式，原子寫入）；共享狀態 57→58 個。注意：finance-pilot 的交易記錄若未來實作將使用 PulseDB 現有 skill_invocations 表擴充（無需新增共享狀態）；talent-match 的候選人資料目前由對話記憶（Qdrant L1_short）承接，不建立獨立共享狀態（biz-collab/talent-match 的 anima-individual 寫入為 runtime 呼叫，不是新共享狀態）。同步 system-topology v1.66、blast-radius v1.84、memory-router v1.16。
> **v1.53 (2026-03-30)**：市場戰神（Market Ares）——新增 #57 `data/market_ares/market_ares.db`（🟢 Market Ares SQLite DB，6 張表：regions/archetypes/simulations/snapshots/competitors/partners，寫入者=market_ares/storage/db.py，讀取者=market_ares/simulation/engine.py + visualization/dashboard.py）；共享狀態 56→57 個。同步 system-topology v1.64、blast-radius v1.83、memory-router v1.14、persistence-contract v1.41。
> **v1.52 (2026-03-29)**：戰神系統（Ares）——新增 #56 `data/ares/profiles/`（🟢 ANIMA 個體檔案，寫入者=anima-individual Skill + external_bridge.py，讀取者=ares Skill + profile_store.py）；共享狀態 55→56 個。同步 system-topology v1.62、blast-radius v1.80、memory-router v1.13、persistence-contract v1.40。
> **v1.51 (2026-03-29)**：OneMuse 能量解讀技能群——新增 #55 `data/knowledge/onemuse/`（🟢 唯讀參考資料，36 檔 Markdown/JSON，寫入者=無（手動維護），讀取者=energy-reading/wan-miu-16/combined-reading 三個 Skill）；共享狀態 54→55 個（含唯讀參考）。同步 system-topology v1.61、blast-radius v1.79、memory-router v1.12、persistence-contract v1.39。
> **v1.49 (2026-03-28)**：死碼清理 20 個模組後同步——移除已刪除模組（channels/line、channels/electron、llm/vision、agent/dna27、agent/routing_bridge、agent/pending_sayings、memory/epigenetic_router、memory/proactive_predictor、multiagent/flywheel_flow、pulse/group_session_proactive、pulse/heartbeat_activation、pulse/proactive_activation、pulse/telegram_pusher、security/trust、tools/document_export、tools/report_publisher、governance/cognitive_receipt、doctor/scalpel_lessons、learning/strategy_accumulator）的讀寫者條目；data_bus 消費者從 16→15（channels/line 已刪）；pulse_db 消費者從 10→11（新增 pulse/group_digest）。

---

## 快速索引

| # | 共享狀態 | 危險度 | 寫入者 | 讀取者 | 鎖 | 頁內連結 |
|---|---------|--------|--------|--------|-----|---------|
| 1 | ANIMA_MC.json | 🔴 | 6 | 12+ | 部分 | [→](#1-anima_mcjson) |
| 2 | PULSE.md | 🔴 | 1(7法) | 5+ | 無 | [→](#2-pulsemd) |
| 3 | ANIMA_USER.json | 🔴 | 3 | 9 | 部分 | [→](#3-anima_userjson) |
| 4 | question_queue.json | 🟡 | 2 | 3 | 無 | [→](#4-question_queuejson) |
| 5 | scout_queue/pending.json | 🟡 | 2 | 2 | 無 | [→](#5-scout_queuependingjson) |
| 6 | lattice/crystal.db | 🟢 | 2 | 5 | ✅ SQLite WAL + Lock | [→](#6-latticecrystaldb) |
| 7 | accuracy_stats.json | 🟡 | 2 | 6 | 無 | [→](#7-accuracy_statsjson) |
| 8 | PulseDB (pulse.db) | 🟡 | 4 | 13 | SQLite WAL | [→](#8-pulsedb-pulsedb) |
| 9 | Qdrant 向量庫 | 🟡 | 4 | 6 | 內部 MVCC | [→](#9-qdrant-向量庫) |
| 10 | diary entries (soul_rings.json) | 🟢 | 1 | 4 | ✅ Lock | [→](#10-diary-entries) |
| 11 | immunity/events.jsonl | 🟢 | 2 | 4 | 無 | [→](#11-immunityeventsjsonl) |
| 12 | immune_memory.json | 🟢 | 1 | 2 | 無 | [→](#12-immune_memoryjson) |
| 13 | synapses.json | 🟢 | 1 | 3 | 無 | [→](#13-synapsesjson) |
| 14 | nightly_report.json | 🟢 | 1 | 3 | 原子寫 | [→](#14-nightly_reportjson) |
| 15 | morphenix/proposals/ | 🟢 | 1 | 3 | 原子寫 | [→](#15-morphenixproposals) |
| 16 | tuned_parameters.json | 🟢 | 1 | 2 | 無 | [→](#16-tuned_parametersjson) |
| 17 | velocity_log.jsonl | 🟢 | 1 | 1 | 無 | [→](#17-velocity_logjsonl) |
| 18 | tuning_audit.jsonl | 🟢 | 1 | 1 | 無 | [→](#18-tuning_auditjsonl) |
| 19 | trigger_configs.json | 🟢 | 1 | 1 | 無 | [→](#19-trigger_configsjson) |
| 20 | tool_muscles.json | 🟢 | 1 | 1 | 無 | [→](#20-tool_musclesjson) |
| 21 | guardian/repair_log.jsonl | 🟢 | 1 | 1 | 無 | [→](#21-guardianrepair_logjsonl) |
| 22 | budget/usage_{month}.json | 🟢 | 1 | 2 | 無 | [→](#22-budgetusage_monthjson) |
| 23 | _system/outward/*.json | 🟡 | 1 | 2 | 無 | [→](#23-_systemoutwardjson) |
| 24 | _system/marketplace/*.json | 🟢 | 1 | 1 | 無 | [→](#24-_systemmarketplacejson) |
| 25 | JSONL 審計日誌群 (21 檔) | 🟢 | 各1 | 各1-3 | 無(append) | [→](#25-jsonl-審計日誌群) |
| 26 | memory/{date}/{ch}.md | 🟡 | 3 | 5 | 無 | [→](#26-memorydatechmd) |
| 27 | fact_corrections.jsonl | 🟢 | 1 | 3 | 無(append) | [→](#27-fact_correctionsjsonl) |
| 28 | cognitive_trace.jsonl | 🟢 | 1 | 2 | 無(append) | [→](#28-cognitive_tracejsonl) |
| 29 | lord_profile.json | 🟢 | 1 | 1+ | 原子寫 | [→](#29-lord_profilejson) |
| 30 | _system/baihe_cache.json | 🟢 | 1 | 2 | 原子寫 | [→](#30-_systembaihe_cachejson) |
| 31 | ~/.museon/auth/allowlist.json | 🟢 | 1 | 2 | 原子寫 | [→](#31-museonauthallowlistjson) |
| 32 | ~/.museon/auth/policy.json | 🟢 | 1 | 2 | 原子寫 | [→](#32-museonauthpolicyjson) |
| 33 | _system/recommendations/interactions.json | 🟢 | 1 | 1 | 原子寫 | [→](#33-_systemrecommendationsinteractionsjson) |
| 34 | _system/backups/ | 🟢 | 2 | 0 | 無(獨立) | [→](#34-_systembackups) |
| 35 | orchestrator_calls（PulseDB 表） | 🟢 | 1 | 0 | SQLite WAL | [→](#35-orchestrator_callspulsedb-表) |
| 36 | external_users/{uid}.json | 🟢 | 2 | 1 | ✅ Lock+原子寫 | [→](#36-external_usersuidjson) |
| 37 | museon-persona.md | 🟡 | 2 | 全部 L2 subagent | 無 | [→](#37-museon-personamd) |
| 38 | ~/.claude/skills/*/SKILL.md | 🔴 | 3 | 4+ | 無 | [→](#38-claudeskillsskillmd) |
| 39 | _system/sessions/{id}.json | 🟡 | 1 | 2 | 無 | [→](#39-_systemsessionsidjson) |
| 40 | group_context.db | 🟡 | 1 | 2 | SQLite WAL | [→](#40-group_contextdb) |
| ~~41~~ | ~~PushBudget 單例（記憶體+PulseDB push_log）~~ | ~~🟡~~ | ~~2~~ | ~~2~~ | ~~SQLite WAL~~ | ~~已刪除 v1.59~~ |
| 42 | BrainCircuitBreaker singleton（記憶體） | 🟢 | 1 | 2 | threading.Lock | [→](#42-braincircuitbreaker-singleton記憶體) |
| 46 | _system/context_cache/pending_insights.json | 🟢 | 1 | 1 | 原子寫 | [→](#46-pending_insightsjson) |
| 47 | _system/context_cache/{4檔} | 🟡 | 2 | 2 | 無 | [→](#47-context-cache-四檔) |
| 43 | message_queue.db | 🟢 | 1 | 1 | SQLite WAL + threading.Lock | [→](#43-message_queuedb) |
| 44 | AsyncTokenBucket singleton（記憶體） | 🟢 | 1 | 1 | asyncio.Lock | [→](#44-asynctokenbucket-singleton記憶體) |
| 45 | BrainWorkerManager singleton（記憶體） | 🟢 | 1 | 1 | asyncio.Lock | [→](#45-brainworkermanager-singleton記憶體) |
| 48 | _system/pulse/push_journal_24h.json | 🟢 | 1 | 1 | 無 | [→](#48-push_journal_24hjson) |
| 49 | _system/memory_graph/edges.json | 🟢 | 1 | 1 | 無 | [→](#49-memory_graph-edgesjson) |
| 50 | _system/memory_graph/access_log.json | 🟢 | 1 | 1 | 無 | [→](#50-memory_graph-access_logjson) |
| 51 | _system/learning/insights/*.json | 🟢 | 1 | 1 | 無 | [→](#51-learning-insightsjson) |
| 52 | _system/doctor/shared_board.json | 🟡 | 4 | 5 | 無 | [→](#52-shared_boardjson) |
| 54 | _system/doctor/patrol_state.json | 🟢 | 1 | 1 | 無（單寫入者） | — |
| 53 | _system/billing/skill_invocations_*.json | 🟢 | 1 | 1 | 無 | [→](#53-skill_invocationsjson) |
| 55 | knowledge/onemuse/ (36 檔) | 🟢 | 0 | 3 | 無（唯讀） | [→](#55-knowledgeonemuse) |
| 56 | ares/profiles/ | 🟢 | 2 | 2 | 無 | [→](#56-aresprofiles) |
| 57 | market_ares/market_ares.db | 🟢 | 1 | 2 | SQLite WAL | [→](#57-market_aresdb) |
| 58 | equity-architect/case_files/ | 🟢 | 1 | 1 | 原子寫 | [→](#58-equity-architectcase_files) |
| 59 | _system/skills_draft/ | 🟢 | 1 | 3 | 原子寫 | [→](#59-skills_draft) |
| 60 | _system/skill_health/ | 🟢 | 1 | 1 | 原子寫 | [→](#60-skill_health) |
| 61 | _system/feedback_loop/daily_summary.json | 🟢 | 1 | 1 | 原子寫 | [→](#61-feedback_loop-daily_summaryjson) |
| 62 | _system/triage_queue.jsonl | 🟢 | 多(各覺察源) | 1(triage_step) | 無(append) | — |
| 63 | _system/awareness_log.jsonl | 🟢 | 1(triage_step) | 1(triage_step) | 無(append) | — |
| 64 | _system/pending_adjustments.json | 🟢 | 1(triage_step) | 1(session_adjustment) | 原子寫 | — |
| 65 | _system/nightly_priority_queue.json | 🟢 | 1(triage_step) | 1(triage_to_morphenix) | 原子寫 | — |
| 66 | _system/session_adjustments/{id}.json | 🟢 | 1(L4觀察者) | 1(brain_prompt_builder) | 原子寫 | — |
| 67 | _system/triage_human_queue.json | 🟢 | 1(triage_step) | 1(triage_step+algedonic_alert) | 原子寫 | — |
| 68 | skills/native/{name}/_lessons.json | 🟢 | 1(session_adjustment) | 1(brain_prompt_builder) | 原子寫 | — |
| 69 | _system/museoff/finding_counts.json | 🟢 | 1(doctor/finding.py) | 1(doctor/museoff.py) | 原子 JSON 讀寫 | — |
| 70 | ANIMA_MC.personality.trait_dimensions | 🟠 | 2(trait_engine+nightly_reflection) | 4(brain_prompt_builder+growth_stage+mask_engine+dissent_engine) | AnimaMCStore + evolution_write (P-traits) | [→](#70-anima_mcpersonalitytrait_dimensions) |
| 71 | ANIMA_MC.evolution.trait_history | 🟢 | 1(nightly_reflection) | 2(momentum_brake+drift_detector) | APPEND_ONLY | [→](#71-anima_mcevolutiontrait_history) |
| 72 | ANIMA_MC.evolution.stage_history | 🟢 | 1(brain_observation) | 1(growth_stage) | APPEND_ONLY | [→](#72-anima_mcevolutionstage_history) |
| 73 | _system/mask_states.json | 🟢 | 1(mask_engine) | 1(mask_engine) | 無（短暫，7 天自動清理） | [→](#73-_systemmask_statesjson) |
| 74 | SignalLite 物件（記憶體） | 🟢 | 1(signal_lite.py) | 3(brain.py + metacognition.py + telegram_pump.py) | 純記憶體，無鎖（不可變計算結果） | [→](#74-signallite-物件記憶體) |

> **危險度定義**：🔴 多寫入者+高扇出+格式不一致 | 🟡 多寫入者或高扇出 | 🟢 單寫入者+低扇出

---

## 🔴 CRITICAL 區域

### 1. ANIMA_MC.json

**路徑**：`data/ANIMA_MC.json`
**用途**：MUSEON 靈魂核心——身份、人格、能力、演化狀態

#### 寫入者（8 個模組 → 統一經由 AnimaMCStore + guardian 修復）

| 模組 | 函數 | 寫入的 Key | 格式 | 鎖 |
|------|------|-----------|------|-----|
| **`pulse/anima_mc_store.py`** | **`save()` / `update()`** | **統一入口** | 完整 JSON | **✅ `threading.Lock` + KernelGuard + 原子寫入(tmp→rename)** |
| `agent/brain.py` | `_save_anima_mc()` → 委派 Store | 整個檔案 | 完整 JSON | ✅ 經由 AnimaMCStore |
| `agent/brain.py` | `_update_crystal_count()` → Store.update() | `memory_summary.knowledge_crystals` | int | ✅ 原子讀改寫 |
| `agent/brain.py` | `_observe_self()` → Store.update() via WQ | `memory_summary.*`, `evolution.*`, `capabilities.*`, `eight_primals.*` | dict | ✅ 原子讀改寫 via AnimaMCStore.update() |
| `pulse/anima_tracker.py` | `_save()` → Store.update() | `eight_primal_energies`, `_vita_triggered_thresholds` | `{元素: {absolute: int, relative: float}}` | ✅ 經由 AnimaMCStore |
| `pulse/micro_pulse.py` | `_update_days_alive()` → Store.update() | `identity.days_alive` | int | ✅ 經由 AnimaMCStore |
| `agent/brain.py` | `_merge_ceremony_into_anima_mc()` → Store.update() via WQ | 全部欄位（ceremony 合併） | 完整 JSON | ✅ 原子讀改寫 via AnimaMCStore.update() |
| `onboarding/ceremony.py` | `receive_name()`, `_initialize_anima_l1()` | 初始化全部欄位 | 完整 JSON | 無（單次初始化，可接受） |
| `guardian/daemon.py` | 修復邏輯 — `_check_anima()` | 結構修復（缺失欄位補回） | 部分 JSON patch | 無（修復模式，低頻） |
| `agent/trait_engine.py` | `update_c_traits()` → Store.update() | `personality.trait_dimensions`（C1-C5 即時特質） | `{trait_id: {value: float, level: str}}` | ✅ 經由 AnimaMCStore（FREE 層級） |
| `nightly/nightly_reflection.py` | `evolution_write()` → Store.update() | `personality.trait_dimensions`（P1-P5 穩定人格特質）、`evolution.trait_history`（append） | dict + JSONL append | ✅ 經由 AnimaMCStore（PSI 層級，需 evolution_write 授權） |
| `agent/brain_observation.py` | `record_stage_transition()` → Store.update() | `evolution.stage_history`（append） | JSONL append | ✅ 經由 AnimaMCStore（APPEND_ONLY） |

#### 讀取者（12+ 個模組）

| 模組 | 函數 | 讀取的 Key | 用途 |
|------|------|-----------|------|
| `agent/brain.py` | `_load_anima_mc()` | 全部 | 建構 system prompt、自我觀察 |
| `gateway/server.py` | `_build_system_prompt()` | identity, capabilities, personality | API 回應語氣 |
| `pulse/anima_tracker.py` | `_load()` | `eight_primal_energies` | 能量成長計算 |
| `pulse/micro_pulse.py` | `_update_days_alive()` | `identity.birth_date` | 天數計算 |
| `agent/soul_ring.py` (DiaryStore) | — | `eight_primal_energies` (via AnimaTracker) | 日記條目記錄 |
| `agent/kernel_guard.py` | `validate_write()` | OMEGA/PHI/PSI 欄位 | 寫入前驗證 |
| `agent/drift_detector.py` | — | 全部 | 飄移基線比較 |
| `governance/perception.py` | — | 全部 | 四診合參 |
| `doctor/health_check.py` | — | JSON 結構 | 損毀偵測 |
| `doctor/field_scanner.py` | `ANIMA_MC_SCHEMA` | 全部欄位 | 使用率掃描 |
| `nightly/periodic_cycles.py` | — | `eight_primal_energies` | 30 天趨勢 |
| `mcp_server.py` | `museon_anima_status()` | 全部 | 暴露給 Claude Code |
| `guardian/daemon.py` | `_check_anima()` | 全部 | 結構完整性檢查 + 修復 |
| `agent/brain_prompt_builder.py` | `_get_identity_prompt()` | `personality.trait_dimensions` | 將人格特質維度注入 system prompt |
| `agent/growth_stage.py` | — | `personality.trait_dimensions.confidence` | 判斷成熟度（confidence 值） |
| `agent/mask_engine.py` | `get_effective_traits()` | `personality.trait_dimensions`（核心特質） | 計算面具偏移量的基準值 |
| `agent/dissent_engine.py` | — | `personality.trait_dimensions`（via stage_constraints） | 異議決策的階段限制校驗 |

#### ✅ 衝突風險（已修復 — 合約 1）

1. ~~brain vs anima_tracker 互相覆蓋~~ → **已修復**：統一經由 AnimaMCStore，單一 `threading.Lock`
2. ~~micro_pulse 直接寫入~~ → **已修復**：改用 `AnimaMCStore.update()` 原子讀改寫
3. ~~`_observe_self` 在 WQ 外讀取~~ → **已修復**：改用 `AnimaMCStore.update()` 原子讀改寫（整個 RMW 在 Store 鎖內）
4. ~~`_merge_ceremony_into_anima_mc` 繞過 WQ/Store~~ → **已修復**：改用 `AnimaMCStore.update()` + WriteQueue 序列化
5. **格式不一致**：brain 管 `eight_primals`（已過時），anima_tracker 管 `eight_primal_energies` → 兩套數值系統並存（待後續合約處理）

---

### 2. PULSE.md

**路徑**：`data/PULSE.md`
**用途**：生命脈搏日誌——Markdown 偽裝的資料庫，直接注入 system prompt

#### 寫入者（1 個模組，7 種寫入方法）

| 模組 | 函數 | 寫入區段 | 格式 |
|------|------|---------|------|
| `pulse/pulse_engine.py` | `_ensure_pulse_md()` | 初始化全文 | Markdown template |
| `pulse/pulse_engine.py` | `_write_reflection_to_pulse()` | `## 🌊 成長反思` | `- [MM/DD HH:MM] 反思文字`（保留最近 5 條） |
| `pulse/pulse_engine.py` | `_write_observation_to_pulse()` | `## 🔭 今日觀察` | `- [MM/DD HH:MM] 觀察文字`（保留最近 5 條） |
| `pulse/pulse_engine.py` | `_mark_pulse_topic_done()` | `## 🧭 探索佇列` | `[pending]` → `[done]` 標記替換 |
| `pulse/pulse_engine.py` | `_seed_followup_topics()` | `## 🧭 探索佇列` | 新增 `- [pending] 主題` |
| `pulse/pulse_engine.py` | `_update_pulse_md_status()` | `## 📊 今日狀態` | 探索次數、推送次數等統計 |
| `pulse/pulse_engine.py` | — | `## 💝 關係日誌` | 正面/負面/分享訊號記錄 |

**鎖**：✅ `threading.Lock` + 原子寫入（tmp→rename+fsync）——所有 7 種寫入方法均在鎖內完成完整讀改寫

#### 讀取者（5+ 個模組）

| 模組 | 函數 | 讀取區段 | 用途 |
|------|------|---------|------|
| **`agent/brain.py`** | **`_build_soul_context()`** | 🌊成長反思(3條) + 🔭今日觀察(3條) + 🌱成長軌跡(2條) + 💝關係日誌(3條) | **⚡ 直接注入 system prompt（最危險的通道）** |
| `pulse/pulse_engine.py` | `_read_pulse_summary()` | 前 500 字 | 自省上下文 |
| `pulse/pulse_engine.py` | `_get_next_explore_topic()` | 🧭探索佇列 | 選取下一個探索主題 |
| `pulse/pulse_engine.py` | `_prepare_brain_context()` | 多區段摘要 | 生成 curiosity_hint |
| `pulse/heartbeat_engine.py` | — | 間接 | 心跳週期管理 |

#### ⚠️ 衝突風險

1. **System Prompt 汙染通道**：PulseEngine 寫入的任何格式異常，都會透過 `_build_soul_context()` 直接注入 AI 的 system prompt → **這是檢索飄移的隱藏根因**
2. **三條正回饋迴路**：
   - 自我餵養：findings → followup → PULSE [pending] → 下次探索
   - 反思回聲：reflect → PULSE → soul_context → system prompt → 行為 → reflect
   - 問句循環：findings → ExplorationBridge → question_queue → 主題選取 → explore
3. **無 schema**：純 Markdown，section header 就是 schema → 修改 header 文字即破壞讀取
4. **無版本控制**：覆蓋寫入，丟失歷史

---

### 3. ANIMA_USER.json

**路徑**：`data/ANIMA_USER.json`
**用途**：使用者畫像——老闆名字、觀察記錄、關係歷史

#### 寫入者（3 個模組）

| 模組 | 函數 | 寫入的 Key | 鎖 |
|------|------|-----------|-----|
| `agent/brain.py` | `_save_anima_user()` | 整體（DM 全權重 + 群組 0.5 權重）| 原子寫入(tmp→rename) + KernelGuard |
| `agent/brain.py` | `_observe_group_behavioral_shift()` | `L8_context_behavior_notes` | 同上（群組訊息觸發） |
| `memory/memory_gate.py` | （間接）經由 brain.py `_observe_user(suppress_primals, suppress_facts)` | 控制八原語+L1是否寫入 | ★ v1.14 新增：MemoryGate 判定糾正/否認時 suppress |
| `onboarding/ceremony.py` | `receive_answers()` | `my_name`, `boss_name` | 無（單次初始化） |
| `guardian/daemon.py` | 修復邏輯 | 結構修復 | 無 |

#### 讀取者（9 個模組）

| 模組 | 用途 |
|------|------|
| `agent/brain.py` | 載入使用者資訊 |
| `agent/soul_ring.py` (DiaryStore) | 使用者觀察日記 |
| ~~`pulse/group_session_proactive.py`~~ | ~~L8 群組行為觀察（已刪除 v1.49）~~ |
| `gateway/server.py` | API: `/api/anima/user/group-behaviors` |
| `onboarding/ceremony.py` | 初始化流程 |
| `agent/metacognition.py` | 元認知觀察 |
| `guardian/daemon.py` | 健康檢查 |
| `agent/kernel_guard.py` | 寫入驗證 |
| `doctor/health_check.py` | 完整性檢查 |
| `doctor/field_scanner.py` | 欄位使用率 |
| `mcp_server.py` | 暴露給 Claude Code |

#### ⚠️ 衝突風險

- 與 ANIMA_MC.json 共用 `boss_name` 等資訊但分別儲存 → 可能不同步
- daemon 的修復邏輯可能覆蓋 brain 的寫入

#### ✅ v1.14 Memory Gate 防護

- brain.py Step 9.0 在記憶寫入前，經 `MemoryGate.classify_intent()` + `decide_action()` 判斷意圖
- 糾正/否認意圖 → `suppress_primals=True`（跳過八原語 signal 寫入）+ `suppress_facts=True`（跳過 L1 事實寫入）
- 解決「越否認越強化」迴圈（糾正句子不再被存為新記憶信號）
- L1 事實新增 `status`（active/deprecated）+ `confidence`（0.0-1.0）欄位

---

## 🟡 HIGH 區域

### 4. question_queue.json

**路徑**：`data/_system/curiosity/question_queue.json`
**用途**：好奇心佇列——待研究的問題列表

#### 讀寫表

| 模組 | 操作 | 函數 | Key | 鎖 |
|------|------|------|-----|-----|
| `nightly/nightly_pipeline.py` | **RW** | `_step_curiosity_scan()` | 掃描 session/*.json 提取問句 → append | ❌ 無 |
| `nightly/curiosity_router.py` | **RW** | `_load_queue()` / `_save_queue()` | 讀取 → 評分排序 → 更新 status="researched" | ❌ 無 |
| `pulse/pulse_engine.py` | **R** | `_get_next_explore_topic()` | 讀取 pending 問題作為探索主題 (Fallback 3) | ❌ 無 |

#### 資料格式

```json
[{"question": "str", "source_date": "YYYY-MM-DD", "status": "pending|researched", "source": "exploration_bridge?"}]
```

#### ⚠️ 衝突風險

- NightlyPipeline 覆蓋寫 + CuriosityRouter 覆蓋寫 → **互相覆蓋**
- 去重僅在記憶體中（非持久化）→ 重啟後可能灌入重複問題
- PulseEngine 過濾規則與 NightlyPipeline 掃描規則不一致

---

### 5. scout_queue/pending.json

**路徑**：`data/_system/bridge/scout_queue/pending.json`
**用途**：Skill 改善待研究佇列

#### 讀寫表

| 模組 | 操作 | 函數 | Key | 鎖 |
|------|------|------|-----|-----|
| `nightly/exploration_bridge.py` | **W** | `_route_to_scout()` | 從探索發現提取線索 → 寫入 | ❌ 無 |
| `nightly/skill_forge_scout.py` | **RW** | `process_queue()` | 讀取 → 篩選 pending → 研究 → 寫草稿 | ❌ 無 |
| `nightly/nightly_pipeline.py` | **R** | `_step_skill_scout()` | 讀取 → 去重 → 統計 | ❌ 無 |

#### 資料格式

```json
[{"topic": "str", "findings_snippet": "str(≤1200)", "source": "exploration_bridge", "created_at": "ISO8601", "status": "pending"}]
```

**保留策略**：最多 20 個項目（`queue[-20:]`）

---

### 6. lattice/crystal.db

**路徑**：`data/lattice/crystal.db`（SQLite WAL 模式，三表：crystals, links, cuid_counters）
**用途**：知識晶格——結晶化的知識資產
**遷移紀錄**：v1.29 從 JSON（crystals.json + links.json + cuid_counter.json + archive.json）遷移至 SQLite WAL 模式，舊檔案已歸檔為 .bak

#### 讀寫表

| 模組 | 操作 | 函數 | 鎖 |
|------|------|------|-----|
| `agent/crystal_store.py` (CrystalStore) | **RW** | 統一存取層（CRUD + 查詢 + 歸檔） | ✅ SQLite WAL + `threading.Lock` |
| `agent/knowledge_lattice.py` | **RW** | 結晶存取（經由 CrystalStore API） | ✅ 經由 CrystalStore |
| `nightly/crystal_actuator.py` | **W** | 降級/升級（經由 CrystalStore API） | ✅ 經由 CrystalStore |
| `nightly/nightly_pipeline.py` | **R** | 降級偵測（經由 CrystalStore API） | — |
| `nightly/evolution_velocity.py` | **R** | 結晶數量統計（經由 CrystalStore API） | — |
| `agent/recommender.py` | **R** | 推薦（經由 CrystalStore API） | — |
| `pulse/wee_engine.py` | **R** | 工作流查詢（經由 CrystalStore API） | — |
| `guardian/daemon.py` | **R** | 健康檢查（經由 CrystalStore API） | — |
| `doctor/memory_reset.py` | **W** | 一鍵重置（DELETE FROM 三表） | — |
| `skills/energy-reading` | **W** | Skill 執行時寫入 energy_crystal（經由 KnowledgeLattice） | ✅ 經由 CrystalStore |
| `skills/wan-miu-16` | **W** | Skill 執行時寫入 persona_crystal（經由 KnowledgeLattice） | ✅ 經由 CrystalStore |
| `skills/combined-reading` | **W** | Skill 執行時寫入 relationship_crystal（經由 KnowledgeLattice） | ✅ 經由 CrystalStore |

#### 衰減策略

| 機制 | 公式/參數 | 執行者 | 觸發時機 |
|------|---------|--------|---------|
| RI 指數衰減 | `RI = (0.3×Freq + 0.4×Depth + 0.3×Quality) × exp(-0.03 × days)` | `knowledge_lattice.py` 檢索時計算 | 每次結晶檢索 |
| 低 RI 歸檔 | RI < 0.05 → 標記 archived | `crystal_actuator.py` Nightly 降級步驟 | Nightly 管線 |
| 類型升降級 | Hypothesis→Insight→Principle（驗證次數驅動） | `crystal_actuator.py` | Nightly 管線 |

> 詳見 `persistence-contract.md` §衰減與優先級模型。

#### MemGPT 分層召回（v1.23 新增）

| 層級 | RI 範圍 | 策略 | 執行者 |
|------|---------|------|--------|
| Tier-0 (Hot) | RI ≥ 0.7 | 無條件注入 context window | `knowledge_lattice.py` `recall_tiered()` |
| Tier-1 (Warm) | 0.2 ≤ RI < 0.7 | 語義搜尋後注入 | `knowledge_lattice.py` `recall_tiered()` |
| Tier-2 (Cold) | RI < 0.2 | 僅顯式查詢才拉取 | 不在 `recall_tiered` 中處理 |

> `brain.py` 的結晶注入區已從 `recall_with_chains()` 切換為 `recall_tiered()`。
> `recall_with_chains()` 仍保留作為 `recall_tiered()` 內部的 Warm 搜尋引擎。

#### GraphRAG 社群摘要（v1.25 新增）

| 方法 | 作用 | 依賴 |
|------|------|------|
| `detect_communities()` | Label Propagation 社群偵測 | DAG adjacency（記憶體計算，不持久化） |
| `_summarize_community()` | Extract-based 社群摘要 | crystals.json（唯讀） |
| `has_communities()` | 快速檢查是否有社群 | DAG links count |
| `recall_with_community()` | 語義搜尋相關社群 | `recall()` + `detect_communities()` |

> `brain.py` Layer 2.5 在結晶不足時呼叫 `recall_with_community()` 注入社群摘要。
> 社群偵測為即時計算（不持久化），基於 Crystal DAG 既有連結，無新增共享狀態。

#### Procedure 結晶擴展欄位（v1.32 新增）

| 欄位 | 型態 | 用途 |
|------|------|------|
| `skills_used` | TEXT (JSON array) | 操作程序使用的 Skill 清單 |
| `preconditions` | TEXT (JSON array) | 執行前提條件 |
| `known_failures` | TEXT (JSON array) | 已知失敗模式 |
| `last_success` | TEXT (ISO8601) | 最近一次成功執行時間戳 |

> 四個欄位均為選填（ALTER TABLE ADD COLUMN，向後相容），僅 Procedure 類型結晶使用。

#### ✅ 衝突風險（已修復 — CrystalStore 遷移）

- ~~knowledge_lattice 和 crystal_actuator 都能寫入 → 無鎖保護~~ → **已修復**：統一經由 CrystalStore，SQLite WAL + `threading.Lock` 雙重保護
- ~~降級邏輯可能與新增邏輯衝突~~ → **已修復**：CrystalStore 序列化所有寫入
- **衰減計算與新增寫入並發時**，受 SQLite WAL 保護，不再有歸檔衝突（已降為理論風險）

---

### 7. accuracy_stats.json

**路徑**：`data/_system/metacognition/accuracy_stats.json`
**用途**：預測準確率統計

#### 讀寫表

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `pulse/pulse_db.py` | **W** — `get_prediction_accuracy_stats()` 計算寫入 | SQLite 層 |
| `agent/metacognition.py` | **W** — 更新統計 | ❌ 無 |
| `pulse/pulse_engine.py` | **R** | — |
| `nightly/evolution_velocity.py` | **R** — `_calc_prediction_improvement()` | — |
| `nightly/periodic_cycles.py` | **R** — `_step_metacognition_calibration()` | — |
| `nightly/parameter_tuner.py` | **R** | — |

---

### 8. PulseDB (pulse.db)

**路徑**：`data/pulse/pulse.db`（注意：`data/_system/pulse/pulse.db` 為 0B 殭屍檔案，實際使用此路徑）
**引擎**：SQLite WAL mode
**用途**：VITA 生命力引擎結構化儲存（16 張表，含 push_log）

#### 寫入者

| 模組 | 寫入表 |
|------|--------|
| `pulse/pulse_db.py` | 全部 16 表（schedules, explorations, anima_log, evolution_events, morphenix_proposals, commitments, metacognition, scout_drafts, health_scores, incidents, orchestrator_calls, push_log 等） |
| `nightly/nightly_pipeline.py` | evolution_events, 多表日誌 |
| `gateway/server.py` (via Governor callback) | incidents（P2 新增：Governor 免疫迴圈 → `_bridge_incident_to_pulsedb()` → `pulse_db.save_incident()`） |
| ~~`pulse/push_budget.py` (via PushBudget)~~ | ~~push_log（全局推送去重 + 限額追蹤）~~ ← **已刪除 v1.59**，配額管理移至 ProactiveDispatcher 三桶分級內建 |

#### 讀取者（12 個模組）

| 模組 | 讀取表 |
|------|--------|
| `agent/eval_engine.py` | 全部 |
| `agent/metacognition.py` | metacognition |
| `agent/brain.py` | explorations, commitments |
| `pulse/commitment_tracker.py` | commitments |
| `onboarding/ceremony.py` | ceremony_state |
| `nightly/nightly_pipeline.py` | 多表 |
| `channels/telegram.py` | morphenix_proposals |
| `gateway/server.py` | commitments |
| `pulse/pulse_engine.py` | explorations（push_log 讀取已移除，PushBudget 依賴已清除 v1.59） |
| `nightly/evolution_velocity.py` | evolution_events |
| `nightly/periodic_cycles.py` | metacognition |
| `nightly/morphenix_executor.py` | metacognition（DNA-Inspired 品質旗標閉環：`get_quality_flags()` / `get_quality_flag_summary()`） |

#### 鎖機制 ✅

- `threading.Lock()` 在 pulse_db.py
- SQLite `PRAGMA journal_mode=WAL` + `busy_timeout=60000ms`
- `threading.local()` per-thread 連線
- `get_pulse_db()` 單例模式

#### ✅ 狀態（合約 2 驗證：已解決）

- ~~11 個模組可能各自初始化 PulseDB 而非走單例~~ → **已解決**：所有 14 處呼叫均使用 `get_pulse_db()` 單例
- 混合 asyncio + threading 存取 → 合約 3 處理

---

### 9. Qdrant 向量庫

**位置**：`http://127.0.0.1:6333`（8 個 collections）
**用途**：語義搜尋——記憶、技能、知識文件、八原語的向量索引

#### 讀寫表

| 模組 | 操作 | Collection |
|------|------|-----------|
| `vector/vector_bridge.py` | **RW** | memories, skills, documents |
| `vector/vector_bridge.py` | **W** | skills（`index_all_skills()` 全量索引——Gateway startup + Nightly 8.6 + API reindex） |
| `agent/brain.py` | **W** | memories（記憶持久化） |
| `memory/memory_manager.py` | **RW** | memories |
| `agent/skill_router.py` | **R** | skills |
| `agent/knowledge_lattice.py` | **R** | documents |
| `memory/chromosome_index.py` | **R** | references |
| `agent/primal_detector.py` | **RW** | primals（八原語語義偵測——寫入索引 + 搜尋匹配） |

#### Sparse Collections（混合檢索）

| 模組 | 操作 | Sparse Collection |
|------|------|-------------------|
| `vector/vector_bridge.py` | **RW** | `{name}_sparse`（BM25 稀疏向量） |
| `vector/sparse_embedder.py` | **W** | `data/_system/sparse_idf.json`（IDF 表） |

- **Route A 分離式**：不修改原 dense collections 的 schema
- `hybrid_search()` 同時查 dense + sparse → RRF 融合，**已被 4 個模組消費**：`skill_router.py`、`memory_manager.py`、`knowledge_lattice.py`、`server.py`（取代原 pure dense search）
- IDF 表由 `build_sparse_idf()` 從 dense collection 語料建立
- **Nightly Step 8.7** `_step_sparse_idf_rebuild()` 負責 IDF 重建 + 回填 sparse collections
- **Gateway startup** 驗證 SparseEmbedder IDF 可用性（`sparse_idf.json` 存在且非空）

#### 鎖與降級

- **無顯式鎖**（Qdrant 內部 MVCC）
- **Graceful Degradation**：Qdrant 離線時靜默失敗 → **檢索能力降級為 TF-IDF（0.3 折扣）**
- **Hybrid 降級**：sparse collection 不存在或 IDF 未建立 → hybrid_search 自動降級為純 dense
- **Pending Index Queue**：`_pending_indexes` 暫存失敗索引（但無自動恢復觸發）
- **可用性快取**：60 秒

---

## 🟢 MEDIUM 區域

### 10. diary entries

**路徑**：`data/anima/soul_rings.json`（v2.0 重命名為 DiaryStore，檔案路徑不變）
**用途**：日記條目——Append-only 成長記錄（原靈魂年輪 + 每日摘要 + 反思）

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `agent/soul_ring.py` (DiaryStore) | **RW** — append + reinforcement_count 更新 + generate_daily_summary | ✅ `threading.Lock(_soul_lock)` |
| `agent/brain.py` | **R** — 讀取最近日記（E-tier 路由時） | — |
| `nightly/nightly_pipeline.py` | **W** — 每日日記生成（_step_diary_generation） | — |
| `nightly/evolution_velocity.py` | **R** | — |

**v2.0 新增欄位**：`entry_type`（daily_summary/event/reflection）、`highlights`、`learnings`、`tomorrow_intent`

**安全等級**：✅ 有鎖 + Append-only + SHA-256 Hash Chain + 每日備份

---

### 11. immunity/events（v1.41 路徑修正）

**路徑**：`data/_system/immunity.json`（v1.41 修正：原記 `events.jsonl` 目錄結構已改為扁平 JSON）
**用途**：免疫系統事件與抗體記錄

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `governance/immunity.py` | **RW** | ❌ 無（JSONL append 相對安全） |
| `guardian/daemon.py` | **W** | ❌ 無 |
| `governance/governor.py` | **R**（P3: 讀取 `_immunity._incidents` 未解決事件 → 注入 DendriticScorer） | — |
| `nightly/evolution_velocity.py` | **R** | — |
| `nightly/parameter_tuner.py` | **R** | — |

---

### 12. immune_memory.json

**路徑**：`data/_system/immune_memory.json`
**用途**：後天免疫記憶庫

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `governance/immune_memory.py` | **RW** — `_load()` / `_save()` / `check_defense()` | ❌ 無 |
| `governance/immunity.py` | **R** | — |

---

### 13. synapses.json

**路徑**：`data/_system/synapses.json`
**用途**：技能神經網路——skill 間共同使用追蹤

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `agent/skill_synapse.py` | **RW** | ❌ 無 |
| `agent/brain.py` | **R** | — |
| `agent/knowledge_lattice.py` | **R** | — |

---

### 14. nightly_report.json

**路徑**：`data/_system/state/nightly_report.json`
**用途**：夜間報告

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `nightly/nightly_pipeline.py` | **W** — `_save_nightly_report()` | 原子寫入 |
| `gateway/server.py` | **R** | — |
| `pulse/pulse_engine.py` | **R** | — |

---

### 15. morphenix/proposals/

**路徑**：`data/_system/morphenix/proposals/proposal_*.json`
**用途**：自我演化提案

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `nightly/nightly_pipeline.py` | **W** — `_step_morphenix_proposals()` | 原子寫入 |
| `nightly/morphenix_validator.py` | **R** | — |
| `nightly/morphenix_executor.py` | **R** | — |

---

### 16. tuned_parameters.json

**路徑**：`data/_system/evolution/tuned_parameters.json`
**用途**：自動參數調優結果

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `nightly/parameter_tuner.py` | **W** | ❌ 無 |
| `nightly/evolution_velocity.py` | **R** | — |

---

### 17. velocity_log.jsonl

**路徑**：`data/_system/evolution/velocity_log.jsonl`
**用途**：演化速度週間快照

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `nightly/evolution_velocity.py` | **W** — 週間快照 append | ❌ 無（JSONL append 相對安全） |
| `nightly/parameter_tuner.py` | **R** — 速度趨勢分析 | — |

---

### 18. tuning_audit.jsonl

**路徑**：`data/_system/evolution/tuning_audit.jsonl`
**用途**：參數調諧稽核軌跡

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `nightly/parameter_tuner.py` | **W** — 每次調諧記錄 | ❌ 無（JSONL append 相對安全） |
| `nightly/evolution_velocity.py` | **R** — 調諧效果追蹤 | — |

---

### 19. trigger_configs.json

**路徑**：`data/_system/trigger_configs.json`
**用途**：Evolution 觸發器設定

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `evolution/trigger_weights.py` | **RW** — 觸發器權重更新 | ❌ 無 |
| `nightly/nightly_pipeline.py` | **R** — 觸發條件檢查 | — |

---

### 20. tool_muscles.json

**路徑**：`data/_system/tool_muscles.json`
**用途**：工具肌肉記憶（使用頻率與熟練度）

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `evolution/tool_muscle.py` | **RW** — 肌肉記憶更新 | ❌ 無 |
| `nightly/nightly_pipeline.py` | **R** — 工具退化偵測 | — |

---

### 21. guardian/repair_log.jsonl

**路徑**：`data/_system/guardian/repair_log.jsonl`
**用途**：Guardian 守護修復日誌

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `guardian/daemon.py` | **W** — 修復記錄 append | ❌ 無（JSONL append） |
| `doctor/health_check.py` | **R** — 修復歷史分析 | — |

---

### 22. budget/usage_{month}.json

**路徑**：`data/_system/budget/usage_{YYYY-MM}.json`
**用途**：月度 Token 預算追蹤

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `llm/budget.py` | **RW** — 每次 API 呼叫累加 | ❌ 無 |
| `nightly/nightly_pipeline.py` | **R** — 預算結算 | — |

---

### 23. _system/outward/*.json

**路徑**：`data/_system/outward/` （含 behavior_shift.json, direction_cooldown.json, daily_counter.json, pending_signals.json 等 6 檔）
**用途**：外向演化觸發器的狀態追蹤

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `evolution/outward_trigger.py` | **RW** — 行為轉變偵測、冷卻時間、每日計數、待處理訊號 | ❌ 無 |
| `nightly/nightly_pipeline.py` | **R** — 狀態檢查 | — |

> **注意**：水電圖曾將此目錄標為 `pulse/proactive_bridge.py` 負責，經查證實際只有 `outward_trigger.py` 寫入此目錄。proactive_bridge 使用的是 `_system/bridge/` 下的獨立路徑。

---

### 24. _system/marketplace/*.json

**路徑**：`data/_system/marketplace/`
**用途**：技能交易市場資料（打包、簽章、安裝記錄）

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `federation/skill_market.py` | **RW** — 市集註冊、安裝記錄 | ❌ 無 |
| `gateway/server.py` | **R** — API 暴露 | — |

---

### 25. JSONL 審計日誌群

**路徑**：散佈於 `data/` 各處（見下表）
**用途**：Append-only 審計日誌——風險低（只追加不修改），統一群組管理而非逐一追蹤
**設計原則**：此條目用「一個群組」管理 21 個 JSONL 檔案，避免藍圖膨脹導致維護成本超過收益

| 子檔案 | 路徑 | 寫入者 | 讀取者 | TTL |
|--------|------|--------|--------|-----|
| activity_log.jsonl | `data/activity_log.jsonl` | ActivityLogger | SystemAudit, Brain (search()) | >5MB 輪替 |
| heartbeat.jsonl | `data/heartbeat.jsonl` | PulseEngine | Doctor, Nightly | >5MB 輪替 |
| q_scores.jsonl | `data/eval/q_scores.jsonl` | EvalEngine | EvalEngine, Nightly, ParameterTuner | >5MB 輪替 |
| satisfaction.jsonl | `data/eval/satisfaction.jsonl` | EvalEngine | EvalEngine | >5MB 輪替 |
| kernel_audit.jsonl | `data/guardian/kernel_audit.jsonl` | KernelGuard | SystemAudit | >5MB 輪替 |
| repair_log.jsonl | `data/guardian/repair_log.jsonl` | GuardianDaemon | Doctor | >5MB 輪替 |
| actions.jsonl | `data/_system/footprints/actions.jsonl` | FootprintStore | SystemAudit | 30 天 |
| decisions.jsonl | `data/_system/footprints/decisions.jsonl` | FootprintStore | SystemAudit | 90 天 |
| cognitive_trace.jsonl | `data/_system/footprints/cognitive_trace.jsonl` | FootprintStore | SystemAudit, Observatory | 30 天 |
| evolutions.jsonl | `data/_system/footprints/evolutions.jsonl` | FootprintStore | SystemAudit | 永久 |
| velocity_log.jsonl | `data/_system/evolution/velocity_log.jsonl` | EvolutionVelocity | ParameterTuner | >5MB 輪替 |
| tuning_audit.jsonl | `data/_system/evolution/tuning_audit.jsonl` | ParameterTuner | EvolutionVelocity | >5MB 輪替 |
| routing_log_{date}.jsonl | `data/_system/budget/routing_log_*.jsonl` | Router, Gateway | NightlyJob, FederationSync | 日期輪替 |
| cache_log_{date}.jsonl | `data/_system/budget/cache_log_*.jsonl` | Brain | Nightly | 日期輪替 |
| reflex_log_{date}.jsonl | `data/_system/budget/reflex_log_*.jsonl` | Gateway | 反射分析 | 日期輪替 |
| exec_{date}.jsonl | `data/_system/morphenix/execution_log/exec_*.jsonl` | MorphenixExecutor | SystemAudit, Nightly | 日期輪替 |
| breath_log_{date}.jsonl | `data/_system/pulse/breath_log_*.jsonl` | ProactiveBridge | Nightly | 日期輪替 |
| push_history.jsonl | `data/workspace/push_history.jsonl` | TelegramPusher | 去重驗證 | 永久 |
| anima_history.jsonl | `data/_system/anima/anima_history.jsonl` | PeriodicCycles | ANIMA 追蹤 | 永久 |
| nightly_history.jsonl | `data/_system/state/nightly_history.jsonl` | PeriodicCycles | 執行歷史 | 永久 |
| skill_usage_log.jsonl | `data/skill_usage_log.jsonl` | Brain, PulseEngine | Brain (outcome 欄位) | >5MB 輪替 |
| signal_log.jsonl | `data/intuition/signal_log.jsonl` | Intuition | ⚠️ DW3 嫌疑 | 30 天 |

> **統一清理機制**：Nightly Step 27（>5MB gzip 壓縮）+ Step 27 延伸（>30 天 .gz 刪除）

---

### 26. memory/{date}/{ch}.md

**路徑**：`data/memory/{YYYY}/{MM}/{DD}/{channel}.md`（4 通道：meta-thinking, event, outcome, user-reaction）
**用途**：人類可讀的對話記憶 Markdown——Brain 四通道持久化 + MemoryFusion 跨通道融合

#### 讀寫表

| 模組 | 操作 | 說明 |
|------|------|------|
| `memory/store.py` (MemoryStore) | **W** — `write()`, `save_memory()` | 核心寫入入口（append-only） |
| `agent/brain.py` | **W** — `_persist_memory()` 呼叫 MemoryStore | 四通道事件/思考/結果持久化 |
| `nightly/fusion.py` (MemoryFusion) | **RW** — 讀取 `load_daily_log()` → LLM 融合 → 寫回 meta-thinking | 夜間跨通道融合 |
| `gateway/server.py` | **W** — Chrome Extension 捕獲 → MemoryStore | 網頁片段存入 |
| `nightly/nightly_pipeline.py` | **R** — 步驟 1-5 記憶壓縮升級 | 短期→長期記憶 |
| `memory/memory_manager.py` | **R** — `load_daily_log()` | 六層記憶管理讀取源（支援 dept_filter + chat_scope_filter + exclude_scopes 過濾） |
| `pulse/micro_pulse.py` | **R** — 掃描目錄統計 | 脈衝檢測 |
| `mcp_server.py` | **R** — REST API 暴露 | Claude Code 存取 |
| `guardian/daemon.py` | **R** — 健康檢查 | MemoryStore 存活確認 |

> **⚠️ 風險**：3 個寫入者（Brain, MemoryFusion, Gateway）無鎖機制，但因分時段寫入（即時 vs 夜間 vs 手動）實際衝突概率低

---

### 27. fact_corrections.jsonl

**路徑**：`data/anima/fact_corrections.jsonl`
**用途**：使用者事實更正日誌——記錄每次事實覆寫的舊→新對應，供自省、PULSE.md 過濾、system prompt 注入

#### 讀寫表

| 模組 | 操作 | 說明 |
|------|------|------|
| `agent/brain.py` | **W** — `_log_fact_correction()` | 偵測到使用者糾正事實時 append 寫入 |
| `agent/brain.py` | **R** — `_build_soul_context()` | 讀取最近 3 條注入 system prompt |
| `pulse/proactive_bridge.py` | **R** — `_build_context_messages()` | 自省時讀取最近 5 條避免引用過期記憶 |
| `pulse/pulse_engine.py` | **R** — `_write_reflection_to_pulse()` | 寫入反思前過濾已糾正的事實 |

> **格式**：JSONL，每行一個 JSON 物件：`{timestamp, session_id, user_said, corrections: [{old_id, old_content, new_content, new_id}]}`
> **鎖**：無需（Append-only，單一寫入者）
> **TTL**：永久（歷史追蹤）

---

### 28. cognitive_trace.jsonl

**路徑**：`data/_system/footprints/cognitive_trace.jsonl`
**用途**：認知可觀測性追蹤——每次 Brain 決策迴圈的認知軌跡（P0 信號、QC 判決、能量、共振、迴圈數、Top Skills）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `governance/footprint.py` | **W** | `trace_cognitive()` | 每次 Brain Step 8 決策後 append 寫入 | ❌ 無（JSONL append 相對安全） |
| `doctor/system_audit.py` | **R** | `_audit_skill_doctor()` → `_sd_check_*` | Skill Doctor 認知層檢查（12 項子檢查） | — |
| `MUSEON_observatory.html` | **R** | 前端 JS fetch | 認知可觀測性儀表板視覺化 | — |

#### 資料格式

```json
{"timestamp": "ISO8601", "p0_signal": "str(六類：感性/理性/混合/思維轉化/哲學/戰略)", "qc_verdict": "str", "user_energy": "str(from cognitive_trace mapping)", "c15_active": "str", "resonance": "str", "loop": "int", "top_skills": ["str"], "meta_note": "str(thinking_path_summary[:50])"}
```

> **鎖**：無需（Append-only，單一寫入者 FootprintStore）
> **TTL**：與 actions.jsonl 相同（30 天）
> **設計**：與 footprints/actions.jsonl、decisions.jsonl 同層，由 FootprintStore 統一管理

---

### 29. lord_profile.json

**路徑**：`data/_system/lord_profile.json`
**用途**：主人領域強弱項畫像（軍師架構基礎層）——記錄 Zeal 在 6 大領域的專長等級、分類（strength/weakness/unknown）、觀察證據計數

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/brain.py` | **W** | `_observe_lord()` | 每次 _observe_user() 尾部呼叫，根據關鍵字匹配遞增 evidence_count | 原子寫入（tmp→rename） |
| `agent/brain.py` | **R** | `Step 3.65` | 百合引擎路由：讀取 lord_profile 傳入 baihe_decide()，進諫時原子寫回 cooldown | 原子寫入（tmp→rename） |
| `agent/persona_router.py` | **R** | `baihe_decide()` | 接收 brain.py 傳入的 lord_profile dict，純讀不寫 | — |
| `skills/energy-reading` | **RW** | Skill 執行時讀寫 | 讀取使用者能量狀態、寫回能量維度更新 | — |
| `skills/wan-miu-16` | **RW** | Skill 執行時讀寫 | 讀取使用者人格狀態、寫回人格維度更新 | — |
| `skills/combined-reading` | **RW** | Skill 執行時讀寫 | 讀取使用者關係狀態、寫回關係維度更新 | — |

#### 資料格式

```json
{"version": "1.0", "lord_id": "zeal", "domains": {"business_strategy": {"level": "expert", "confidence": 0.92, "classification": "strength", "evidence_count": 50}, ...}, "domain_keywords": {...}, "advise_cooldown": {"last_advise_ts": null, "cooldown_minutes": 30, "session_advise_count": 0, "max_per_session": 3}}
```

> **鎖**：原子寫入（.json.tmp → rename），單一寫入者 brain.py
> **TTL**：永久，不自動清理
> **設計**：與 ANIMA_USER.json 完全解耦——ANIMA_USER 管「使用者是誰」，lord_profile 管「使用者哪裡強哪裡弱」

---

### 30. _system/baihe_cache.json

**路徑**：`data/_system/baihe_cache.json`
**用途**：百合引擎最近一次決策快取——讓 ProactiveBridge 在自省時知道 brain 的人格象限狀態

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/brain.py` | **W** | `Step 3.65` | 百合引擎決策後原子寫入（tmp→rename） | 原子寫入 |
| `pulse/proactive_bridge.py` | **R** | `_read_baihe_cache()` | 自省前讀取象限，調整推送語氣和頻率 | — |

#### 資料格式

```json
{"quadrant": "Q1", "expression_mode": "parallel_staff", "advise_tier": 0, "topic_domain": "strength", "ts": "2026-03-19T20:00:00"}
```

> **鎖**：原子寫入（.json.tmp → rename），單一寫入者 brain.py
> **TTL**：讀取時只使用 2 小時內的快取，過期忽略

### 31. ~/.museon/auth/allowlist.json

**路徑**：`~/.museon/auth/allowlist.json`（runtime 區，非 data/）
**用途**：動態授權使用者清單——透過配對碼加入的 Telegram 使用者

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `gateway/authorization.py` | **W** | `PairingManager.save()` | 配對/撤銷使用者時原子寫入（tmp→rename） | 原子寫入 |
| `gateway/authorization.py` | **R** | `PairingManager.load()` | Gateway 啟動時載入 | — |
| `channels/telegram.py` | **R** | `get_trust_level()` → `PairingManager.is_paired()` | 訊息處理時檢查動態信任 | — |

#### 資料格式

```json
{"version": "1.0.0", "updated_at": "2026-03-21T10:00:00", "users": {"12345": {"display_name": "張三", "trust_level": "VERIFIED", "added_at": "...", "ttl": null}}}
```

> **鎖**：原子寫入（.tmp → rename），單一寫入者 PairingManager
> **TTL**：每筆使用者可選 ttl 秒數，null 為永久

---

### 32. ~/.museon/auth/policy.json

**路徑**：`~/.museon/auth/policy.json`（runtime 區，非 data/）
**用途**：三級授權策略設定——auto / ask / block 工具分類

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `gateway/authorization.py` | **W** | `AuthorizationPolicy.save()` | 透過 /auth move 指令修改時原子寫入 | 原子寫入 |
| `gateway/authorization.py` | **R** | `AuthorizationPolicy.load()` | Gateway 啟動時載入 | — |
| `gateway/security.py` | **R** | `check_tool_access()` → `AuthorizationPolicy.classify()` | 工具存取檢查時分類 | — |

#### 資料格式

```json
{"version": "1.0.0", "updated_at": "2026-03-21T10:00:00", "auto": ["museon_memory_read", ...], "ask": ["shell_exec", ...], "block": ["modify_security", ...]}
```

> **鎖**：原子寫入（.tmp → rename），單一寫入者 AuthorizationPolicy
> **TTL**：無，永久有效

---

### 33. _system/recommendations/interactions.json

**路徑**：`data/_system/recommendations/interactions.json`
**用途**：推薦引擎互動歷史——記錄使用者對推薦項目的互動（view/click/bookmark/share/rate/dismiss）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/recommender.py` | **RW** | `_load_interactions()` / `_save_interactions()` | 載入+持久化互動歷史 | 原子寫入（.tmp → rename） |

#### 資料格式

```json
[{"item_id": "INS-001", "action": "click", "rating": null, "timestamp": "2026-03-22T10:00:00+08:00"}]
```

> **鎖**：原子寫入（.json.tmp → rename），單一寫入者 Recommender
> **TTL**：5000 條上限（超出截斷）
> **設計**：單一模組讀寫，風險極低

---

### 34. _system/backups/

**路徑**：`data/_system/backups/`（子目錄：`anima_mc/`、`pulse_md/`）
**用途**：關鍵檔案寫入前自動快照備份——ANIMA_MC.json 和 PULSE.md 的時間戳快照

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `pulse/anima_mc_store.py` | **W** | `_backup_before_write()` | 每次 save() 前自動快照 `backups/anima_mc/ANIMA_MC_{timestamp}.json`，FIFO 保留 10 份 | 無（自包含，寫入前觸發） |
| `pulse/pulse_engine.py` | **W** | `_backup_pulse_md()` | 每次寫入前自動快照 `backups/pulse_md/PULSE_{timestamp}.md`，FIFO 保留 10 份 | 無（自包含，寫入前觸發） |

#### 消費者

無自動消費者——快照僅供手動恢復時讀取。

> **鎖**：無需（兩個寫入者各自寫不同子目錄，無競爭）
> **TTL**：FIFO 保留最近 10 份，超出自動刪除最舊
> **危險度**：🟢 綠（自包含，不影響其他模組）

---

### 35. orchestrator_calls（PulseDB 表）

**路徑**：`data/pulse/pulse.db` — `orchestrator_calls` 表
**用途**：L2-S3 Orchestrator 診斷數據收集——記錄每次 Orchestrator 呼叫的 plan_id、skill/task 數量、成功率、模型、回應長度

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/brain.py` | **W** | `_dispatch_orchestrate()` | 每次 Orchestrator 呼叫後寫入診斷數據 | SQLite WAL（PulseDB 共用） |

#### 消費者

無自動消費者——供未來 A1 確定性路由設計分析使用。

#### 資料格式（Schema）

| 欄位 | 型態 | 說明 |
|------|------|------|
| `id` | INTEGER PK | 自增主鍵 |
| `plan_id` | TEXT | 任務計畫 ID |
| `skill_count` | INTEGER | 計畫中的 Skill 數量 |
| `task_count` | INTEGER | 計畫中的 Task 數量 |
| `success` | BOOLEAN | 是否成功完成 |
| `model` | TEXT | 使用的 LLM 模型 |
| `response_length` | INTEGER | 回應長度（字元數） |
| `created_at` | TEXT (ISO8601) | 建立時間戳 |

> **鎖**：SQLite WAL（PulseDB 共用鎖機制）
> **TTL**：永久（診斷數據，供長期趨勢分析）
> **危險度**：🟢 綠（單一寫入者，無消費者競爭）

---

### 36. external_users/{uid}.json

**路徑**：`data/_system/external_users/{uid}.json`
**用途**：群組外部用戶記憶——非 Owner 的群組參與者獨立 ANIMA（v3.0 schema：信任演化 + 八原語 + 七層精選 + 偏好）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `governance/multi_tenant.py` (ExternalAnimaManager) | **RW** | `save()` / `update()` | 完整覆寫 / 增量更新（互動計數、群組列表） | ✅ `threading.Lock` + 原子寫入（tmp→rename） |
| `agent/brain_observation.py` | **W** | `_observe_external_user()` | 八原語 + L1 事實 + L6 溝通風格 + 偏好 + 主題（經由 ExternalAnimaManager.save()） | ✅ 經由 ExternalAnimaManager |
| `agent/brain_prompt_builder.py` | **R** | `search_by_keyword()` | 私聊中引用群組成員背景（注入 system prompt） | — |
| `gateway/server.py` | **W** | 群組訊息處理 → `ExternalAnimaManager.update()` | 非敏感群組訊息的互動計數更新 | ✅ 經由 ExternalAnimaManager |

#### 資料格式

```json
{"version": "3.0.0", "user_id": "str", "interaction_count": 0, "display_name": "str", "profile": {"name": null, "role": null}, "relationship": {"trust_level": "initial|building|growing|established", "total_interactions": 0}, "eight_primals": {}, "seven_layers": {"L1_facts": [], "L6_communication_style": {}}, "recent_topics": [], "preferences": {}}
```

> **鎖**：✅ `threading.Lock` + 原子寫入（`.{uid}.json.tmp` → rename）
> **TTL**：永久（外部用戶記憶不自動清理）
> **危險度**：🟢 綠（Lock 保護完整，單一管理者 ExternalAnimaManager）

---

### 37. museon-persona.md

**路徑**：`data/_system/museon-persona.md`
**用途**：MUSEON 核心人格定義檔——所有 L2 thinker subagent 在 spawn 時讀取此檔，作為行為準則與語氣基調

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| Zeal（手動） | **W** | — | 手動維護人格定義 | — |
| morphenix | **W** | 人格迭代提案 | 人格迭代時由 morphenix 提案修改 | — |
| 所有 L2 thinker subagent | **R** | spawn 時讀取 | 每次 L2 思考者 spawn 時讀取作為系統人格指令 | — |

#### 資料格式

Markdown 純文字，包含行為準則、語氣定義、決策原則等。

> **鎖**：無（手動維護為主，寫入頻率極低）
> **TTL**：永久
> **危險度**：🟡 黃（無鎖但影響面廣——所有 L2 subagent 的行為基調皆由此檔決定）

---

### 38. ~/.claude/skills/*/SKILL.md

**路徑**：`~/.claude/skills/*/SKILL.md`（51 個 Skill，約 909KB）
**用途**：ACSF Skill 定義檔群——Claude Code session 啟動時載入、skill_router 路由匹配、vector_bridge 向量索引、nightly Step 8.6 重建索引

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| Zeal（手動） | **W** | — | 手動新增/修改 Skill 定義 | — |
| acsf（Skill 鍛造） | **W** | Skill 鍛造流程 | 自動化 Skill 生成/更新 | — |
| morphenix | **W** | 演化提案 | Skill 迭代時修改 SKILL.md | — |
| Claude Code session | **R** | session 啟動 | 載入 Skill 清單作為可用工具 | — |
| `skill_router.py` | **R** | `route()` | Skill 路由匹配 | — |
| `vector_bridge.py` | **R** | `index_all_skills()` | 向量索引建立 | — |
| nightly Step 8.6 | **R** | Skill 重建索引 | 夜間管線重新索引所有 Skill | — |

#### 資料格式

每個 SKILL.md 為獨立 Markdown 文件，包含 Skill 的 Manifest（io/connects_to/memory/hub）、使用說明、範例等。

> **鎖**：無（檔案系統層級，無並發寫入機制）
> **TTL**：永久
> **危險度**：🔴 紅（51 個檔案 ~909KB，無鎖，3 個寫入者 + 4 個讀取者；任一 SKILL.md 格式錯誤可能導致 skill_router 路由失敗或 vector_bridge 索引損壞）

---

### 39. _system/sessions/{id}.json

**路徑**：`data/_system/sessions/{session_id}.json`
**用途**：對話 session 歷史——Brain 持久化的對話記錄（role + content 陣列）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/brain_tools.py` | **W** | `_save_session_to_disk()` | 每次回覆後序列化到磁碟 | 無（asyncio 單線程寫入） |
| `agent/brain_tools.py` | **R** | `_load_session_from_disk()` | Gateway 啟動時 / 新對話時載入 | — |
| `mcp_server.py` | **R** | `museon_session_history()` | L2 思考者取得對話上下文（三層架構 MCP） | — |

> **鎖**：無（單一寫入者 brain_tools，MCP 為只讀）
> **TTL**：永久（跟隨 session 生命週期）
> **危險度**：🟡 黃（MCP server 在 Gateway 寫入過程中讀取可能讀到不完整 JSON，但概率極低且 MCP 有 try/except 保護）

---

### 40. group_context.db

**路徑**：`data/_system/group_context/group_context.db`
**用途**：對話結構化記錄——Telegram 群組訊息 + DM 私訊 + Bot 回覆、成員、群組資訊（SQLite）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `governance/group_context.py` | **RW** | `record_message()` / `upsert_group()` | channels/telegram.py 收到訊息時經由此模組寫入（群組+DM+bot 回覆） | SQLite WAL |
| `mcp_server.py` | **R** | `museon_group_context()` | L2 思考者取得群組對話脈絡（三層架構 MCP） | — |
| `channels/telegram.py` | **W** | lazy import group_context | 群組訊息、DM 私訊、Bot 回覆三路寫入（v1.66 新增 DM+bot_reply） | — |
| `gateway/telegram_pump.py` | **R** | lazy import group_context | 群組回覆時讀取 format_context_for_prompt 注入上下文 | — |

> **鎖**：SQLite WAL（GroupContextStore 自帶）
> **TTL**：永久
> **危險度**：🟡 黃（SQLite WAL 支援並發讀寫，安全）
> **v1.66 變更**：messages 表新增 DM（msg_type='dm'）和 bot 回覆（msg_type='bot_reply'）；group_id 正數=DM chat_id、負數=群組；text 截斷從 2000→8000 字元；clients 表新增 personality_notes/communication_style 欄位

---

### 41. exploration_log.md

**路徑**：`data/exploration_log.md`
**用途**：探索主題去重與深度遞進追蹤——記錄最近 30 天的自主探索履歷，防止同一主題重複探索無深度

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `pulse/explorer.py` | **W** | `_log_exploration()` | 探索完成後 append 新記錄 | 無（單寫入者） |
| `pulse/explorer.py` | **R** | `_load_exploration_log()` | 探索前檢查去重 + 判斷深度遞進 | 無（唯讀快照） |

> **鎖**：無（Markdown append-only，單一寫入者 explorer.py）
> **TTL**：保留最近 30 天（實裝：歷史條目永久保留，查詢時過濾）
> **危險度**：🟢 綠（單一寫入者 explorer.py，讀取者同一模組內部，無外部依賴）

---

### 42. BrainCircuitBreaker singleton（記憶體）

**路徑**：記憶體 singleton（`governance/bulkhead.py` 模組層級 `_brain_circuit_breaker`）
**用途**：Brain 連續失敗時自動斷路，返回降級回覆，防止客戶長時間等待無回應

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `governance/bulkhead.py` | **Owner** | `get_brain_circuit_breaker()` | singleton 工廠 + 狀態管理（record_success/record_failure） | `threading.Lock` |
| `gateway/telegram_pump.py` | **R/W** | `_brain_process_with_sla()` | 每次 brain.process() 前檢查 `is_open`，完成後 `record_success/failure` | 經由 CB 內部 Lock |
| `gateway/server.py` | **R** | `startup_event()` + `/health` | startup 註冊通知回調；/health 讀取 `get_status()` | 經由 CB 內部 Lock |

> **鎖**：`threading.Lock`（bulkhead.py 內部，所有狀態變更均加鎖）
> **TTL**：記憶體生命週期（Gateway 重啟歸零）
> **危險度**：🟢 綠（thread-safe singleton，無持久化，重啟自動恢復 CLOSED）

---

### 43. message_queue.db

**路徑**：`data/_system/message_queue.db`
**用途**：訊息佇列持久化——Gateway 重啟後恢復未處理的 Telegram 訊息（pending/done/failed 三態）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `gateway/message_queue_store.py` | **Owner** | `MessageQueueStore` singleton | SQLite 持久化佇列管理（enqueue/mark_done/mark_failed/recover_pending） | `threading.Lock` + SQLite WAL |
| `gateway/telegram_pump.py` | **W** | pump 主迴圈 + `_handle_telegram_message` | 收訊 enqueue、完成 mark_done、失敗 mark_failed | 經由 Store 內部 Lock |
| `gateway/telegram_pump.py` | **R** | `_recover_pending_messages()` | 啟動時讀取 pending 訊息重新排隊 | 經由 Store 內部 Lock |
| `gateway/server.py` | **Init** | `startup_event()` | 初始化 singleton（`get_message_queue_store(data_dir=...)`) | — |

> **鎖**：`threading.Lock` + SQLite WAL（MessageQueueStore 內部）
> **TTL**：done/failed 記錄保留 7 天後由 `cleanup_old()` 清理
> **危險度**：🟢 綠（單一 singleton 管理，所有存取經由 API，thread-safe）

---

### 44. AsyncTokenBucket singleton（記憶體）

**路徑**：記憶體 singleton（`llm/rate_limiter.py` 模組層級 `_api_bucket`）
**用途**：API 呼叫頻率控制——token bucket 演算法限制 LLM API 呼叫速率（取代 semaphore）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `llm/rate_limiter.py` | **Owner** | `get_api_bucket()` | singleton 工廠 + acquire/pause/slow_down/speed_up | `asyncio.Lock` |
| `gateway/telegram_pump.py` | **R/W** | `_brain_process_with_sla()` fallback | `async with get_api_bucket():` 取得 token 後呼叫 brain | 經由 bucket 內部 Lock |

> **鎖**：`asyncio.Lock`（rate_limiter.py 內部）
> **TTL**：記憶體生命週期（Gateway 重啟歸零）
> **危險度**：🟢 綠（async-safe singleton，無持久化）

---

### 45. BrainWorkerManager singleton（記憶體）

**路徑**：記憶體 singleton（`gateway/brain_worker.py` 模組層級 `_manager`）
**用途**：Brain subprocess 生命週期管理——啟動/停止/重啟 worker process

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `gateway/brain_worker.py` | **Owner** | `init_brain_worker_manager()` / `get_brain_worker_manager()` | singleton 工廠 + start/stop/process | `asyncio.Lock` |
| `gateway/telegram_pump.py` | **R** | `_brain_process_with_sla()` | `get_brain_worker_manager()` 取得 worker 發送請求 | 經由 manager 內部 Lock |
| `gateway/server.py` | **W** | `startup_event()` / `shutdown_event()` | 啟動時 init、關閉時 stop | — |

> **鎖**：`asyncio.Lock`（brain_worker.py 內部，序列化請求）
> **TTL**：記憶體生命週期（Gateway 重啟重建）
> **危險度**：🟢 綠（async-safe singleton，subprocess 管理）

---

### 46. pending_insights.json

**路徑**：`data/_system/context_cache/pending_insights.json`
**用途**：L4 觀察者寫入的洞察（目標/情緒/決策/教訓），L1 下次回覆時讀取並融入 prompt

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/brain.py` | **W** | `_write_insights()` | L4 觀察者偵測到洞察時寫入（append + LRU 50） | 原子寫 |
| `agent/brain.py` | **R+W** | `_read_pending_insights()` / `_consume_insights()` | L1 讀取融入 prompt，回覆後清空 | 原子寫 |

> **鎖**：無顯式鎖（原子寫入 + 單一寫入者 + 讀後清空模式）
> **TTL**：由 L1 消費後清空；未消費的由 LRU 保持最多 50 筆
> **危險度**：🟢 綠（單寫單讀，讀後清空）

---

### 47. context_cache 四檔

**路徑**：`data/_system/context_cache/` 下四個檔案
- `persona_digest.md` — MUSEON 核心人格濃縮版
- `active_rules.json` — Top-10 行動規則
- `user_summary.json` — 使用者能力摘要
- `self_summary.json` — MUSEON 自我狀態摘要

**用途**：v2 L1/L2 的快速上下文載入（取代載入 42KB ANIMA_USER）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `cache/context_cache_builder.py` | **W** | `build_all()` | Nightly Step 31 重建所有四檔 | 無（夜間單次執行） |
| `agent/brain.py` | **W** | `_observe()` | L4 增量更新 user_summary（選配） | 原子寫 |
| `agent/brain.py` | **R** | `_build_prompt()` | L1/L2 每次回覆前讀取 | — |

> **鎖**：無（寫入者時間分離：nightly 凌晨、L4 即時但低頻）
> **TTL**：每日 Nightly Step 31 全量重建
> **危險度**：🟡 黃（多讀者 + 2 寫入者，但寫入者時間錯開）

### 48. push_journal_24h.json

**路徑**：`data/_system/pulse/push_journal_24h.json`
**用途**：ProactiveDispatcher 24hr 推播日誌（語意去重 + 內容追蹤）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `pulse/proactive_dispatcher.py` | **W** | `_log_push()` | 每次推播寫入 | 無 |
| `channels/telegram.py` | **R** | `push_notification()` | 推播前查詢去重 | — |

> **鎖**：無（單寫入者）
> **TTL**：24hr 自動清除過期條目
> **危險度**：🟢

### 49. memory_graph edges.json

**路徑**：`data/_system/memory_graph/edges.json`
**用途**：MemoryGraph 記憶間語意關聯邊

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `memory/memory_graph.py` | **W** | `add_edge()` | 新增關聯邊 | 無 |
| `agent/brain.py` | **R** | `_build_memory_inject()` | 建構記憶注入時讀取關聯 | — |

> **鎖**：無（單寫入者）
> **TTL**：永久保留
> **危險度**：🟢

### 50. memory_graph access_log.json

**路徑**：`data/_system/memory_graph/access_log.json`
**用途**：MemoryGraph 記憶存取追蹤（偵測過期記憶）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `memory/memory_graph.py` | **W** | `log_access()` | 記錄存取 | 無 |
| `memory/memory_graph.py` | **R** | `detect_stale()` | 偵測過期記憶 | — |

> **鎖**：無（單寫單讀）
> **TTL**：永久保留
> **危險度**：🟢

### 51. learning insights/*.json

**路徑**：`data/_system/learning/insights/*.json`
**用途**：InsightExtractor 萃取的洞見（個別 JSON 檔案）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `learning/insight_extractor.py` | **W** | `extract()` | 萃取洞見寫入 | 無 |
| `agent/brain.py` | **R** | 初始化時載入 | 洞見作為上下文 | — |

> **鎖**：無（單寫入者）
> **TTL**：永久保留
> **危險度**：🟢

### 52. shared_board.json

**路徑**：`data/_system/doctor/shared_board.json`
**用途**：五虎將共享看板（任務協調、結果共享）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `doctor/museoff.py` | **W** | `_write_board()` | 寫入巡邏結果 | 無 |
| `doctor/museqa.py` | **W** | `_write_board()` | 寫入品質檢查結果 | 無 |
| `doctor/musedoc.py` | **W** | `_write_board()` | 寫入文件同步結果 | 無 |
| `doctor/museworker.py` | **W** | `_write_board()` | 寫入變動記錄 | 無 |
| `doctor/museoff.py` | **R** | `_read_board()` | 啟動時讀取 | — |
| `doctor/museqa.py` | **R** | `_read_board()` | 啟動時讀取 | — |
| `doctor/musedoc.py` | **R** | `_read_board()` | 啟動時讀取 | — |
| `doctor/museworker.py` | **R** | `_read_board()` | 啟動時讀取 | — |
| `nightly/nightly_pipeline.py` | **R** | 夜間報告 | 讀取看板摘要 | — |

> **鎖**：無（50 筆上限滾動，寫入者時間錯開）
> **TTL**：50 筆上限滾動清除
> **危險度**：🟡 黃（4 寫入者，但為不同五虎將模組，執行時間錯開）

### 53. skill_invocations_*.json

**路徑**：`data/_system/billing/skill_invocations_*.json`
**用途**：Skill 調用計數月度檔案

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `billing/trust_points.py` | **W** | `record_invocation()` | 每次 Skill 調用記錄 | 無 |
| `billing/trust_points.py` | **R** | `get_monthly_stats()` | 讀取月度統計 | — |

> **鎖**：無（單寫單讀）
> **TTL**：永久保留（月度檔案）
> **危險度**：🟢

---

### 55. knowledge/onemuse/

**路徑**：`data/knowledge/onemuse/`（36 檔）
**用途**：OneMuse 能量解讀知識庫——OM-DNA 核心規範、模組定義、64 卦知識、AEO 行動包、品牌視覺、報告模板

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| （無） | — | — | 唯讀參考資料，無寫入者（手動維護） | — |
| `skills/energy-reading` | **R** | Skill 執行時讀取 | 八方位能量解讀知識參考 | — |
| `skills/wan-miu-16` | **R** | Skill 執行時讀取 | 萬謬16型人格知識參考 | — |
| `skills/combined-reading` | **R** | Skill 執行時讀取 | 合盤能量比對知識參考 | — |

> **鎖**：無需（唯讀參考資料，無寫入競爭）
> **TTL**：永久（手動維護更新）
> **危險度**：🟢（唯讀，無寫入爭用風險）

### 56. ares/profiles/

**路徑**：`data/ares/profiles/`（{profile_id}.json 個體檔案 + _index.json 索引）
**用途**：ANIMA 個體追蹤引擎的持久化儲存——第三方人物（客戶/供應商/合夥人/員工/私人關係）的七層鏡像、八大槓桿、互動歷史、關係溫度

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `skills/anima-individual` | **W** | Skill 執行時寫入 | 個體分析結果持久化（七層鏡像 + 八大槓桿） | — |
| `src/museon/ares/external_bridge.py` | **W** | `bridge_group_member()` | Telegram 群組成員自動建立/更新個體檔案 | — |
| `src/museon/ares/profile_store.py` | **RW** | CRUD + `search_paths()` + `simulate()` | 個體 CRUD、槓桿分析、路徑搜尋、連動模擬 | — |
| `skills/ares` | **R** | Skill 執行時讀取 | 戰略分析時讀取個體檔案做跨人物分析 | — |

> **鎖**：無需（profile_store.py 為唯一 CRUD 入口，Skill 寫入經由 profile_store 路由）
> **TTL**：永久（持續更新）
> **危險度**：🟢（寫入者均經由 profile_store.py 統一入口，無併發寫入風險）
> **結晶化**：anima-individual → knowledge-lattice `individual_crystal`；ares → knowledge-lattice `strategy_crystal`

---

### 70. ANIMA_MC.personality.trait_dimensions

**路徑**：`data/ANIMA_MC.json` → `personality.trait_dimensions`
**用途**：人格特質維度——分為即時特質（C1-C5，FREE 層級）與穩定人格特質（P1-P5，PSI 層級，需 evolution_write 授權）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/trait_engine.py` | **W** | `update_c_traits()` | 即時更新 C1-C5 特質（對話中動態計算） | ✅ 經由 AnimaMCStore（FREE 層級） |
| `nightly/nightly_reflection.py` | **W** | `evolution_write()` | 夜間更新 P1-P5 穩定人格特質 | ✅ 經由 AnimaMCStore（PSI 層級，需 evolution_write 授權） |
| `agent/brain_prompt_builder.py` | **R** | `_get_identity_prompt()` | 讀取特質維度注入 system prompt | ✅ 經由 AnimaMCStore 讀取 |
| `agent/growth_stage.py` | **R** | — | 讀取 `confidence` 值判斷成熟度分級 | ✅ 經由 AnimaMCStore 讀取 |
| `agent/mask_engine.py` | **R** | `get_effective_traits()` | 讀取核心特質作為面具偏移量的基準值 | ✅ 經由 AnimaMCStore 讀取 |
| `agent/dissent_engine.py` | **R** | — | 讀取 stage_constraints 進行異議決策校驗 | ✅ 經由 AnimaMCStore 讀取 |

> **保護級別**：P1-P5（穩定人格特質）= PSI 層級，寫入需 KernelGuard `evolution_write` 授權；C1-C5（即時特質）= FREE 層級，可即時寫入
> **危險度**：🟠（2 寫入者 × 4 讀取者，P-traits 保護已到位，C-traits 動態覆寫需注意競態）

---

### 71. ANIMA_MC.evolution.trait_history

**路徑**：`data/ANIMA_MC.json` → `evolution.trait_history`（JSONL 格式陣列）
**用途**：人格特質演化歷史——APPEND_ONLY 記錄每次 P-trait 變化，供動量剎車與漂移偵測使用

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `nightly/nightly_reflection.py` | **W（append-only）** | `evolution_write()` | 每次夜間反思後 append 特質變化記錄 | ✅ 經由 AnimaMCStore（APPEND_ONLY） |
| `agent/momentum_brake.py` | **R** | — | 讀取近 7 天視窗，計算變化速率上限 | ✅ 經由 AnimaMCStore 讀取 |
| `agent/drift_detector.py` | **R** | — | 讀取歷史進行方向性漂移分析 | ✅ 經由 AnimaMCStore 讀取 |

> **保護**：APPEND_ONLY——禁止修改或刪除歷史記錄；size limit 200 條（超過時 LRU 截斷）
> **危險度**：🟢（單一寫入者，append-only，無並發寫入風險）

---

### 72. ANIMA_MC.evolution.stage_history

**路徑**：`data/ANIMA_MC.json` → `evolution.stage_history`（JSONL 格式陣列）
**用途**：成長階段轉換歷史——APPEND_ONLY 記錄每次階段晉升事件，只升不降（only-upgrade enforcement）

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/brain_observation.py` | **W（append-only）** | `record_stage_transition()` | 偵測到階段晉升時 append 轉換記錄 | ✅ 經由 AnimaMCStore（APPEND_ONLY） |
| `agent/growth_stage.py` | **R** | — | 讀取歷史確認 only-upgrade 規則（不允許降級） | ✅ 經由 AnimaMCStore 讀取 |

> **保護**：APPEND_ONLY——歷史不可修改；size limit 50 條；growth_stage.py 讀取時強制 only-upgrade 驗證
> **危險度**：🟢（單一寫入者，append-only，讀取者只讀）

---

### 73. _system/mask_states.json

**路徑**：`data/_system/mask_states.json`
**用途**：面具狀態快取——記錄當前啟用的面具及其衰減狀態，短暫性資料，無需嚴格保護，7 天後自動清理

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/mask_engine.py` | **W** | `activate()` | 啟用新面具，寫入啟用時間與初始強度 | 原子寫入（tmp→rename） |
| `agent/mask_engine.py` | **W** | `decay_session()` | 每次 session 後衰減面具強度 | 原子寫入（tmp→rename） |
| `agent/mask_engine.py` | **W** | `cleanup_stale()` | 清理超過 7 天的失效面具 | 原子寫入（tmp→rename） |
| `agent/mask_engine.py` | **R** | `get_effective_traits()` | 讀取當前啟用的面具計算有效特質 | 讀取 JSON |

> **鎖**：無（mask_engine.py 為唯一讀寫者，寫入使用 tmp→rename 原子操作）
> **TTL**：7 天自動清理（`cleanup_stale()` 定期執行）
> **危險度**：🟢（單一模組讀寫，短暫資料，自動清理）

---

### 74. SignalLite 物件（記憶體）

**路徑**：純記憶體（無持久化）
**用途**：signal_lite.py 計算的輕量訊號物件，取代 reflex_router 的路由訊號（Phase A-C 遷移）。包含 category、strength、tags 等欄位，每次請求計算後傳遞給下游消費者。

#### 讀寫表

| 模組 | 操作 | 函數 | 說明 | 鎖 |
|------|------|------|------|-----|
| `agent/signal_lite.py` | **W** | `compute()` | 每次請求時計算 SignalLite 物件並回傳 | 無（純函數，不可變） |
| `agent/brain.py` | **R** | `_build_prompt()` | 讀取 SignalLite 決定路由策略 | — |
| `agent/metacognition.py` | **R** | `observe()` | 讀取 SignalLite 做後設認知標記 | — |
| `gateway/telegram_pump.py` | **R** | `dispatch()` | 讀取 SignalLite 決定是否需要 L2 spawn | — |

> **鎖**：無（純記憶體計算，每次計算產生不可變物件，無並發競爭）
> **TTL**：請求生命週期（request-scoped），不跨 session 持久化
> **危險度**：🟢（單一寫入者，純記憶體，不可變計算結果）
> **注意**：此物件不寫入 Qdrant、不寫入任何 JSON 檔——routing_signal 已從 baihe_cache 的 context 欄位移除（純記憶體傳遞）

---

## 必須同時修改的模組組（不可分批）

> 修改以下任一模組時，**必須**同時檢查並調整同組所有模組。

| 組 ID | 組名 | 模組 | 共享什麼 |
|-------|------|------|---------|
| **G1** | ANIMA 數值 | anima_tracker + brain + server + micro_pulse + kernel_guard | ANIMA_MC.json（寫入格式 + 鎖機制必須統一） |
| **G2** | 探索結晶管線 | pulse_engine + curiosity_router + exploration_bridge + nightly_pipeline + skill_forge_scout | question_queue.json + scout_queue/pending.json + PULSE.md 探索佇列 |
| **G3** | 記憶管線 | memory_manager + brain + vector_bridge + multi_agent_executor | MemoryStore + Qdrant memories collection（memory_manager 支援 dept_id 標籤寫入 + dept_filter 過濾檢索 + chat_scope 群組隔離 + supersede() 事實覆寫 + VectorBridge.mark_deprecated() 軟刪除） |
| **G4** | 演化速度 | evolution_velocity + parameter_tuner + periodic_cycles + metacognition | accuracy_stats.json + tuned_parameters.json + velocity_log.jsonl |
| **G5** | 知識晶格 | knowledge_lattice + crystal_store + crystal_actuator + recommender + dissent_engine | crystal.db (via CrystalStore) + crystal_rules.json（dissent_engine 讀取做矛盾校驗） |
| **G6** | 免疫系統 | immunity + immune_memory + immune_research + daemon | events.jsonl + immune_memory.json |

---

## 鎖機制一覽

| 共享狀態 | 鎖類型 | 模組 | 安全性 |
|---------|--------|------|--------|
| ANIMA_MC.json | **AnimaMCStore** (`threading.Lock` + KernelGuard + 原子寫入) | **全部寫入者** | ✅ **完整（合約 1 修復）** |
| ANIMA_MC.json | WriteQueue | brain | ✅ 序列化（非關鍵寫入） |
| diary entries (soul_rings.json) | `threading.Lock` | soul_ring (DiaryStore) | ✅ 完整 |
| observation_rings.json | `threading.Lock` | soul_ring (DiaryStore) | ✅ 完整 |
| PulseDB | SQLite WAL + `threading.Lock` | pulse_db | ✅ 完整 |
| Qdrant | 內部 MVCC | — | ✅ 資料庫層 |
| PULSE.md | `threading.Lock` + 原子寫入(tmp→rename+fsync) | pulse_engine | ✅ 完整（Lock + 原子寫入） |
| question_queue.json | **無** | — | ❌ 危險 |
| scout_queue/pending.json | **無** | — | ❌ 危險 |
| crystal.db | **CrystalStore** (`SQLite WAL` + `threading.Lock`) | **全部寫入者** | ✅ **完整（CrystalStore 遷移）** |
| accuracy_stats.json | **無** | — | ❌ 危險 |
| external_users/{uid}.json | **ExternalAnimaManager** (`threading.Lock` + 原子寫入) | **全部寫入者** | ✅ **完整** |

---

## 並發模型一覽

| 模組 | 並發模型 | 說明 |
|------|---------|------|
| brain.py | asyncio + threading 混合 | async def + threading.Lock |
| pulse_engine.py | asyncio + threading.Lock | async + threading.Lock（PULSE.md 寫入保護） |
| anima_tracker.py | 同步 | 原子寫入，無 async |
| micro_pulse.py | 同步 | 直接寫入 |
| nightly_pipeline.py | 同步（背景執行緒） | `_run_async_safe()` → `asyncio.new_event_loop()`（合約 3 修復） |
| curiosity_router.py | 同步 | NightlyPipeline 子步驟 |
| pulse_db.py | threading | threading.Lock + threading.local |
| server.py | asyncio + threading 混合 | FastAPI async + threading.Lock |

> **⚠️ 核心風險**：asyncio event loop + threading.Thread + run_in_executor 三種模型交叉存取同一檔案（ANIMA_MC.json）

---

## 變更日誌

| 日期 | 版本 | 變更 |
|------|------|------|
| 2026-03-25 | v1.46 | L2 Worker + RateLimiter：新增 #44 AsyncTokenBucket singleton（🟢 記憶體，asyncio.Lock）、#45 BrainWorkerManager singleton（🟢 記憶體，asyncio.Lock）；共享狀態 43→45 個 |
| 2026-03-25 | v1.45 | 訊息佇列持久化：新增 #43 message_queue.db（🟢 危險度，SQLite WAL + threading.Lock，Owner message_queue_store.py，Writer/Reader telegram_pump.py，Init server.py）；共享狀態 42→43 個 |
| 2026-03-25 | v1.44 | Brain Circuit Breaker：新增 #42 BrainCircuitBreaker singleton（記憶體，🟢 危險度，threading.Lock，寫入者 bulkhead.py，讀取者 telegram_pump.py + server.py）；共享狀態 41→42 個 |
| 2026-03-25 | v1.43 | 對話持久化+教訓蒸餾+7 條斷裂管線修復——#40 group_context.db 擴展（DM+bot_reply+8000 截斷+personality_notes/communication_style）；MemoryManager user_id cli_user→boss；Nightly Step 5.6.5 教訓蒸餾+Step 18.5 客戶互動萃取加入 _FULL_STEPS；Crystal Actuator ELIGIBLE_CRYSTAL_TYPES 過濾+PROTECTED_RULE_ORIGINS 保護；Guardian mothership_queue→Gateway 消費；ExternalAnima search dict topics 修復；Intuition heuristics→prompt 注入；Procedure 升級門檻 0+limit 20；Morphenix validator str→dict 防禦；MuseDoc Fix-Verify 整合 |
| 2026-03-23 | v1.40 | Project Epigenesis 接線——EpigeneticRouter / MemoryReflector / AdaptiveDecay 接入 brain.py。無新增共享狀態（四個模組皆為純 RO 消費者——讀取 Qdrant memories/soul_rings/crystals + changelog，不寫入任何共享檔案）。G9 記憶反思組（epigenetic_router + memory_reflector + adaptive_decay + brain_prompt_builder）與 G3 記憶組交叉——反思層讀取 G3 相同的 Qdrant collections。共享狀態維持 41 個（不變）；同步 blast-radius v1.55、memory-router v1.6、persistence-contract v1.32 |
| 2026-03-23 | v1.39 | 探索去重防禦機制：新增 #41 `exploration_log.md`（🟢 危險度，Explorer 單一寫入者，去重檢查 + 深度遞進邏輯）；Explorer 新增 `_check_duplicate()` / `_normalize_topic()` / `_load_exploration_log()` / `_log_exploration()` 四個方法（防止同一主題短期內重複探索無深度——解決 2026-03-23 一天 12 次探索雷同的盲點）；共享狀態 40→41 個 |
| 2026-03-23 | v1.38 | 三層架構 MCP 橋接：新增 #39 `_system/sessions/{id}.json`（🟡 危險度，Brain 寫入+MCP server 只讀，L2 思考者取得對話上下文）；新增 #40 `group_context.db`（🟡 危險度，GroupContextStore 寫入+MCP server 只讀，L2 取得群組脈絡，SQLite WAL 保護）；mcp_server.py 新增 3 工具（museon_session_history/museon_group_context/museon_persona）；共享狀態 38→40 個 |
| 2026-03-23 | v1.37 | 三層調度員架構：新增 #37 `museon-persona.md`（🟡 危險度，Zeal/morphenix 寫入，所有 L2 thinker subagent spawn 時讀取——影響面廣但寫入頻率極低）；補登 #38 `~/.claude/skills/*/SKILL.md`（🔴 危險度，51 個 Skill ~909KB，3 寫入者 手動/acsf/morphenix，4+ 讀取者 Claude Code session/skill_router/vector_bridge/nightly 8.6）；快速索引表補齊 #36；共享狀態 36→38 個 |
| 2026-03-22 | v1.36 | External User 健康檢查：新增 #36 `external_users/{uid}.json`（🟢 危險度，ExternalAnimaManager 統一管理）；ExternalAnimaManager 新增 `threading.Lock` + 原子寫入（tmp→rename）修復 TOCTOU 競態條件；鎖一覽表新增 external_users 條目；共享狀態 35→36 個 |
| 2026-03-22 | v1.35 | Sparse Embedder 啟動：#9 Qdrant 向量庫 Sparse Collections 從「已定義未消費」升級為「全面啟動」；hybrid_search() 被 skill_router + memory_manager + knowledge_lattice + server.py 4 個消費者呼叫（取代原 pure dense search）；Nightly Step 8.7 新增 IDF 重建 + 回填步驟；Gateway startup 新增 IDF 驗證；同步 blast-radius v1.35、persistence-contract v1.30 |
| 2026-03-31 | v1.59 | 推播系統重構：刪除 #41 PushBudget 單例（push_budget.py 已刪除，全局配額改由 ProactiveDispatcher 三桶分級內建）；#8 PulseDB 寫入者 4→3、讀取者 13→12；pulse_engine.py push_log 讀取依賴清除；共享狀態 73→72 個；同步 blast-radius v1.91、system-topology v1.72、persistence-contract v1.45 |
| 2026-03-23 | v1.39 | 推送品質修復：新增 #41 PushBudget 單例（🟡 危險度，2 寫入者 pulse_engine+proactive_bridge 經由共用實例，2 讀取者同）；#8 PulseDB 表數 15→16（新增 push_log 表）；寫入者 3→4（+push_budget.py）；讀取者 12→13（+push_budget.py）；共享狀態 40→41 個；同步 persistence-contract v1.31、blast-radius v1.54、system-topology v1.46 |
| 2026-03-22 | v1.34 | Brain 三層治療：新增 #35 `orchestrator_calls`（PulseDB 表，🟢 危險度，單寫入者 brain.py `_dispatch_orchestrate()`，讀取者 0 供未來 A1 確定性路由）；#8 PulseDB 表數 14→15；共享狀態 34→35 個；同步 persistence-contract v1.29、system-topology v1.37 |
| 2026-03-22 | v1.33 | P0-P3 升級：新增 #34 `_system/backups/` 目錄（🟢 危險度，2 個寫入者各自寫不同子目錄無競爭——AnimaMCStore._backup_before_write() 寫 anima_mc/、PulseEngine._backup_pulse_md() 寫 pulse_md/，各保留 10 份 FIFO）；無讀取者（手動恢復）；共享狀態 33→34 個；同步 persistence-contract v1.28、system-topology v1.35、blast-radius v1.46、memory-router v1.4 |
| 2026-03-22 | v1.32 | 經驗諮詢閘門：#6 crystal.db 新增 Procedure 結晶 4 欄位（skills_used/preconditions/known_failures/last_success）；#25 activity_log.jsonl 讀取者新增 brain.py（search() 經驗搜尋）；#25 skill_usage_log.jsonl 從 DW2 升級（新增 outcome 欄位，Brain 消費） |
| 2026-03-22 | v1.31 | InteractionRequest 跨通道互動層：InteractionQueue 為新共享可變狀態（記憶體中 Dict，asyncio.Event 非阻塞等待，不持久化）；寫入者 3 個（telegram/discord/line 的 callback handler 呼叫 `resolve()`）；讀取者 1 個（gateway/server.py message pump `wait_for_response()`）；危險度 🟢（單一消費者、非持久化、自動超時清理）；message.py 新增 ChoiceOption/InteractionRequest/InteractionResponse 三個 dataclass + BrainResponse.interaction 欄位（純新增，不改現有結構）；同步 system-topology v1.33、blast-radius v1.44 |
| 2026-03-22 | v1.30 | Recommender 激活修復：新增 #33 `_system/recommendations/interactions.json`（🟢 危險度，單一寫入者 recommender.py 原子寫入，5000 條上限）；#6 crystal.db 讀取者新增 recommender（經由 CrystalStore API `load_crystals_raw()` + `load_links()`）；G5 知識晶格組 recommender 接線正式啟用；共享狀態 32→33 個 |
| 2026-03-22 | v1.29 | Knowledge Lattice 持久層遷移：#6 路徑從 `data/lattice/crystals.json` 改為 `data/lattice/crystal.db`（SQLite WAL 模式，三表 crystals/links/cuid_counters）；新增 `agent/crystal_store.py` CrystalStore 為統一存取層（threading.Lock + SQLite WAL）；所有讀寫者改為經由 CrystalStore API；危險度從 🟡 降為 🟢（鎖保護完整）；鎖一覽表更新 crystals.json→crystal.db（❌ 危險→✅ 完整）；G5 模組組新增 crystal_store；舊 JSON 檔案歸檔為 .bak；同步 persistence-contract v1.26、blast-radius v1.41、system-topology v1.31 |
| 2026-03-21 | v1.27 | #9 Qdrant skills collection 新增 VectorBridge.index_all_skills() 寫入路徑（Gateway startup + Nightly 8.6 + API reindex） |
| 2026-03-21 | v1.26 | 群組對話 DSE 三階段修復：G3 記憶管線新增 chat_scope 群組隔離（memory_manager store() 新增 chat_scope/group_id 參數 + 自動注入 scope:{scope} 標籤 + recall() 新增 chat_scope_filter/exclude_scopes 過濾 + _keyword_fallback() 同步過濾 + _vector_index() metadata 注入）；#28 cognitive_trace p0_signal 欄位修復為六類判定（_classify_p0_signal 啟發式）+ meta_note 修復（thinking_path_summary[:50]）；外部使用者 ANIMA v3.0 schema 升級（governance/multi_tenant.py ExternalAnimaManager 新增 profile/relationship/seven_layers + trust_evolution 四階段 + PrimalDetector 八原語）；同步 blast-radius v1.32、memory-router v1.1、persistence-contract v1.23 |
| 2026-03-21 | v1.25 | GraphRAG 社群偵測：#6 crystals.json 新增「GraphRAG 社群摘要」表（detect_communities + recall_with_community 四個方法）；knowledge_lattice.py 新增社群偵測（純新增，RW 不變，讀寫者不變）；brain.py Layer 2.5 新增 `has_communities()` + `recall_with_community()` 呼叫（僅讀）；無新增共享狀態（社群偵測為即時計算，不持久化）；同步 blast-radius v1.31 |
| 2026-03-21 | v1.24 | 混合檢索（Hybrid Retrieval）：#9 Qdrant 向量庫新增 Sparse Collections 分區（`{name}_sparse`，BM25 稀疏向量）；新增 `sparse_embedder.py` 為 `_system/sparse_idf.json` 寫入者；VectorBridge 新增 `hybrid_search()`/`_sparse_search()`/`index_sparse()`/`backfill_sparse()`/`build_sparse_idf()`；Route A 分離式設計——不修改原 dense collections schema；同步 persistence-contract v1.22、blast-radius v1.30 |
| 2026-03-21 | v1.23 | MemGPT 分層結晶召回：#6 crystals.json 新增「MemGPT 分層召回」表（Hot/Warm/Cold 三層策略）；`knowledge_lattice.py` 新增 `recall_tiered()` 方法（RW 不變，讀寫者不變）；同步 blast-radius v1.29 |
| 2026-03-20 | v1.22 | 衰減生命週期補全：#6 crystals.json 新增「衰減策略」表（RI 公式、歸檔閾值、升降級觸發）+ 衝突風險新增衰減並發項；同步 persistence-contract v1.21（四大衰減引擎全文件）、system-topology v1.22（decay 連線類型）、blast-radius v1.28（G8 衰減組） |
| 2026-03-20 | v1.21 | P3 前置交織融合：system_prompt 動態注入 _p3_pre_fusion_ctx（唯讀參考，不新增共享狀態） | blast-radius v1.27, system-topology v1.21 |
| 2026-03-20 | v1.20 | P0-P3 思維引擎升級（純 Skill .md 認知行為變更）：deep-think v2.0、query-clarity v2.0、orchestrator v3.0、dna27 v2.2；無新增共享狀態（30 個不變）、無讀寫者變更、無鎖機制變更；版本同步 system-topology v1.19、persistence-contract v1.19、blast-radius v1.25 |
| 2026-03-19 | v1.19 | P1-P3 PersonaRouter 全接線：新增 #30 `_system/baihe_cache.json`（🟢 危險度，單寫入者 brain.py `Step 3.65` 原子寫入，讀取者 `pulse/proactive_bridge.py` `_read_baihe_cache()`）；brain.py Step 3.65 baihe_decide() context 從空 `{}` 填入 routing_signal+matched_skills+commitment+session_len+is_late_night；brain.py 新增 Step 3.66 根因偵測層（`_detect_root_cause_hint()`，純記憶體，無持久化）；proactive_bridge.py 新增 baihe_cache.json 讀取依賴；共享狀態 29→30 個 |
| 2026-03-17 | v1.18 | 軍師架構 Phase 1：#29 lord_profile.json 讀取者確認——brain.py Step 3.65 百合引擎讀取+進諫冷卻寫回，persona_router.py `baihe_decide()` 純讀（接收 dict 參數）；寫入者 1→2（brain.py: _observe_lord + Step 3.65 cooldown）；危險度維持 🟢（同一寫入者 brain.py 的兩個路徑） |
| 2026-03-17 | v1.17 | 軍師架構 Phase 0：新增 #29 lord_profile.json（🟢 危險度，單寫入者 brain.py `_observe_lord()`，原子寫入）；讀取者預留 persona_router.py（Phase 1）；共享狀態 28→29 個 |
| 2026-03-17 | v1.16 | 認知可觀測性：新增 #28 cognitive_trace.jsonl（FootprintStore.trace_cognitive() 寫入、SystemAudit Skill Doctor + Observatory 讀取）；#25 JSONL 審計日誌群新增 cognitive_trace.jsonl 條目（21→22 檔）；共享狀態 27→28 個 |
| 2026-03-16 | v1.15 | Memory Reset 一鍵重置工具：新增 `doctor/memory_reset.py` 為 25 個共享狀態的重置者（#1 ANIMA_MC.json boss/self_awareness 重置、#2 ANIMA_USER.json 全量重置、#3 PULSE.md 模板重建、#9 Qdrant 全部 collections 刪除重建、#25 JSONL 審計日誌群清空、#26 記憶 Markdown 刪除、#27 fact_corrections.jsonl 清空）；同時重置 PulseDB 全表、sessions、crystals/synapses/scout_queue、diary/drift、eval/workflow_state.db、guardian/footprints/activity_log、nightly_state/outward；預設 dry-run 安全模式 |
| 2026-03-17 | v1.15 | DNA-Inspired 品質回饋閉環：#8 PulseDB 讀取者 11→12（+morphenix_executor `get_quality_flags()`/`get_quality_flag_summary()`）；metacognition 新增 `METACOGNITION_QUALITY_FLAG` 事件發布（verdict=revise 時）；morphenix_executor 夜間管線讀取品質旗標作為演化上下文 |
| 2026-03-16 | v1.14 | Memory Gate 記憶閘門：新增 `memory/memory_gate.py` 為 ANIMA_USER.json 間接寫入控制者；brain.py `_observe_user()` 新增 `suppress_primals`/`suppress_facts` 參數；`_observe_user_layers()` 新增 `suppress_facts` 參數；L1_facts 新增 `status`/`confidence` 欄位；Step 9.2 事實更正偵測提前到 Step 9 之前；解決「越否認越強化」記憶迴圈 |
| 2026-03-31 | v1.58 | Persona Evolution 系統——新增 #70 `ANIMA_MC.personality.trait_dimensions`（🟠 P1-P5 PSI 層級+C1-C5 FREE，寫入者=trait_engine+nightly_reflection，讀取者=brain_prompt_builder+growth_stage+mask_engine+dissent_engine）；新增 #71 `ANIMA_MC.evolution.trait_history`（🟢 APPEND_ONLY，size limit 200，讀取者=momentum_brake+drift_detector）；新增 #72 `ANIMA_MC.evolution.stage_history`（🟢 APPEND_ONLY，size limit 50，only-upgrade 強制，讀取者=growth_stage）；新增 #73 `_system/mask_states.json`（🟢 短暫，7 天清理，mask_engine 獨佔）；G5 新增 dissent_engine 讀取 crystal_rules.json；共享狀態 69→73 個 |
| 2026-03-31 | v1.57 | 9 條斷裂接線修復——新增 #69 `data/_system/museoff/finding_counts.json`（🟢 MuseOff 異常計數持久化，{finding_key: int}，永久累積）；共享狀態 68→69 個；同步 blast-radius v1.87、system-topology v1.69、persistence-contract v1.43 |
| 2026-03-31 | v1.56 | 體液系統迭代——新增 #62-#68 共 7 個共享狀態（triage_queue.jsonl / awareness_log.jsonl / pending_adjustments.json / nightly_priority_queue.json / session_adjustments/{id}.json / triage_human_queue.json / skills/native/{name}/_lessons.json）；共享狀態 61→68 個；同步 topology v1.68、blast-radius v1.86、memory-router v1.18、persistence-contract v1.42 |
| 2026-03-30 | v1.55 | Skill 自動演化管線——新增 #59-#61（skills_draft/ + skill_health/ + feedback_loop/daily_summary.json）；共享狀態 58→61 個 |
| 2026-03-30 | v1.54 | 13 個新 Skill Post-Build 補登——新增 #58 `data/equity-architect/case_files/`（🟢 單寫入者 equity-architect，原子寫，Case File 跨 session 持久化）；finance-pilot 交易記錄沿用 PulseDB skill_invocations 擴充、talent-match 候選人資料由 Qdrant L1_short 承接、biz-collab/talent-match anima-individual 寫入為 runtime 呼叫不建新共享狀態；共享狀態 57→58 個。同步 topology v1.66、blast-radius v1.84、memory-router v1.16 |
| 2026-03-30 | v1.53 | 市場戰神（Market Ares）——新增 #57 `data/market_ares/market_ares.db`（🟢 Market Ares SQLite DB，6 張表）；共享狀態 56→57 個 |
| 2026-03-29 | v1.52 | 戰神系統（Ares）——新增 #56 `data/ares/profiles/`（🟢 2 寫入者 anima-individual+external_bridge / 2 讀取者 ares+profile_store）；共享狀態 55→56 個 |
| 2026-03-29 | v1.51 | OneMuse 能量解讀技能���——新增 #55 `data/knowledge/onemuse/`（🟢 唯讀，0 寫入者 / 3 讀取者 energy-reading+wan-miu-16+combined-reading）；共享狀態 54→55 個 |
| 2026-03-28 | v1.50 | MuseDoctor 第六虎將——新增 #54 `data/_system/doctor/patrol_state.json`（🟢 單寫入者 musedoctor.py，讀取者：cron_registry 啟動時、Telegram /patrol 指令）；共享狀態 53→54 個 |
| 2026-03-27 | v1.48 | 有機體進化計畫 Phase 1-9——新增 #48 `push_journal_24h.json`（ProactiveDispatcher 寫入、telegram 讀取）、#49-#50 `memory_graph/` edges+access_log（MemoryGraph 單寫、Brain 讀取）、#51 `learning/insights/`（InsightExtractor 單寫、Brain 讀取）、#52 `shared_board.json`（🟡 4 寫入者 museoff/qa/doc/worker，5 讀取者）、#53 `skill_invocations_*.json`（SkillCounter 單寫單讀）。共享狀態 47→53 個 |
| 2026-03-26 | v1.47 | v2 Brain 四層架構共享狀態——新增 #43 `pending_insights.json`（L4 觀察者寫入、L1 讀取+清空，原子寫）、#44 `context_cache/` 4 檔（nightly Step 31 重建、L1/L2 每次讀取）。刪除 federation/installer 相關引用。共享狀態 45→47 個 |
| 2026-03-16 | v1.12 | P4 PULSE.md 自省清洗：#27 fact_corrections.jsonl 的三個讀取者已實作——brain.py `_get_fact_correction_declarations()` 注入 system prompt、proactive_bridge.py `_read_recent_fact_corrections()` 注入自省上下文、pulse_engine.py `_reflection_contains_stale_facts()` 寫入前過濾；PULSE.md 寫入新增過期事實過濾閘 |
| 2026-03-16 | v1.11 | P1 推送上下文串接：TelegramAdapter._write_push_to_session() 推送成功後寫入 Brain session history（session_id=telegram_{owner_chat_id}），role=assistant 帶 [主動推送 HH:MM] 前綴；session history 新增間接寫入者（TelegramAdapter 經由 Brain._get_session_history()） |
| 2026-03-16 | v1.10 | P0 記憶事實覆寫：新增 #27 fact_corrections.jsonl（Brain 寫、Brain+ProactiveBridge+PulseEngine 讀）；G3 記憶管線新增 supersede()+mark_deprecated() 事實覆寫路徑；Qdrant memories 新增 status=deprecated 過濾；共享狀態 26→27 個 |
| 2026-03-16 | v1.9 | Phase 4 飛輪多代理實質化：memory_manager.py store() 新增 dept_id 參數（記憶條目帶部門標籤）；recall() 新增 dept_filter 參數（按部門過濾檢索）；G3 記憶管線新增 multi_agent_executor 為間接消費者；無新增共享狀態（MultiAgentExecutor/ResponseSynthesizer/FlywheelCoordinator 均為無狀態或記憶體內狀態） |
| 2026-03-16 | v1.8 | Phase 2 八原語接線：#9 Qdrant 向量庫 collections 7→8（新增 primals）；寫入者 3→4（+primal_detector）；讀取者 5→6（+primal_detector）；primal_detector.py 負責 primals collection 的索引寫入與語義搜尋 |
| 2026-03-16 | v1.7 | Docker 沙盒驗證器上線：morphenix_validator 已在 #15 morphenix/proposals/ 登錄為讀取者，無新增共享狀態；Dockerfile.validator 修復並 build 成功（1637 passed） |
| 2026-03-16 | v1.6 | DNA27 深度審計修復：PULSE.md 加入 threading.Lock + 原子寫入（7 處寫入全覆蓋）；ANIMA_MC _observe_self + _merge_ceremony 改用 Store.update() 原子讀改寫；鎖一覽表同步更新 |
| 2026-03-15 | v1.5 | 9.5 精度修復：新增 #25 JSONL 審計日誌群（21 檔群組管理）、#26 memory/{date}/{ch}.md 記憶檔（3 寫 5 讀）；共享狀態 24→26 個 |
| 2026-03-15 | v1.4 | 全面覆蓋修復：新增 #22 budget/usage_{month}.json、#23 _system/outward/*.json、#24 _system/marketplace/*.json；共享狀態 21→24 個 |
| 2026-03-15 | v1.3 | 藍圖完整性修復：guardian/daemon.py 加入 ANIMA_MC 讀寫者，新增 #17-#21 共享狀態（velocity_log, tuning_audit, trigger_configs, tool_muscles, repair_log） |
| 2026-03-15 | v1.2 | 合約 2 驗證已解決 + 合約 3：nightly async 橋接修復，並發模型表更新 |
| 2026-03-15 | v1.1 | 合約 1：AnimaMCStore 統一存取層，ANIMA_MC.json 鎖策略統一 |
| 2026-03-15 | v1.0 | 初始建立，16 個共享狀態，6 個模組組 |
