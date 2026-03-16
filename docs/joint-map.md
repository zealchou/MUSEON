# Joint Map — 共享可變狀態接頭圖 v1.12

> **用途**：任何程式碼修改前，查閱此圖確認「我要改的模組碰了哪些共享狀態、誰還在讀寫同一根管子」。
> **比喻**：水電圖畫了管線位置，接頭圖畫的是「哪個水龍頭接哪根管、這根管誰負責」。
> **更新時機**：改變共享檔案的讀寫者或格式時，必須在同一個 commit 中同步更新此文件。
> **建立日期**：2026-03-15（DSE 第二輪排查後建立）

---

## 快速索引

| # | 共享狀態 | 危險度 | 寫入者 | 讀取者 | 鎖 | 頁內連結 |
|---|---------|--------|--------|--------|-----|---------|
| 1 | ANIMA_MC.json | 🔴 | 6 | 12+ | 部分 | [→](#1-anima_mcjson) |
| 2 | PULSE.md | 🔴 | 1(7法) | 5+ | 無 | [→](#2-pulsemd) |
| 3 | ANIMA_USER.json | 🔴 | 3 | 9 | 部分 | [→](#3-anima_userjson) |
| 4 | question_queue.json | 🟡 | 2 | 3 | 無 | [→](#4-question_queuejson) |
| 5 | scout_queue/pending.json | 🟡 | 2 | 2 | 無 | [→](#5-scout_queuependingjson) |
| 6 | lattice/crystals.json | 🟡 | 2 | 5 | 無 | [→](#6-latticecrystalsjson) |
| 7 | accuracy_stats.json | 🟡 | 2 | 6 | 無 | [→](#7-accuracy_statsjson) |
| 8 | PulseDB (pulse.db) | 🟡 | 2 | 11 | SQLite WAL | [→](#8-pulsedb-pulsedb) |
| 9 | Qdrant 向量庫 | 🟡 | 4 | 6 | 內部 MVCC | [→](#9-qdrant-向量庫) |
| 10 | diary entries (soul_rings.json) | 🟢 | 1 | 4 | ✅ Lock | [→](#10-diary-entries) |
| 11 | immunity/events.jsonl | 🟢 | 2 | 3 | 無 | [→](#11-immunityeventsjsonl) |
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

> **危險度定義**：🔴 多寫入者+高扇出+格式不一致 | 🟡 多寫入者或高扇出 | 🟢 單寫入者+低扇出

---

## 🔴 CRITICAL 區域

### 1. ANIMA_MC.json

**路徑**：`data/ANIMA_MC.json`
**用途**：MUSEON 靈魂核心——身份、人格、能力、演化狀態

#### 寫入者（6 個模組 → 統一經由 AnimaMCStore + guardian 修復）

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
| `agent/brain.py` | `_save_anima_user()` | 整體（DM 全權重 + 群組 0.5 權重） | 原子寫入(tmp→rename) + KernelGuard |
| `agent/brain.py` | `_observe_group_behavioral_shift()` | `L8_context_behavior_notes` | 同上（群組訊息觸發） |
| `onboarding/ceremony.py` | `receive_answers()` | `my_name`, `boss_name` | 無（單次初始化） |
| `guardian/daemon.py` | 修復邏輯 | 結構修復 | 無 |

#### 讀取者（9 個模組）

| 模組 | 用途 |
|------|------|
| `agent/brain.py` | 載入使用者資訊 |
| `agent/soul_ring.py` (DiaryStore) | 使用者觀察日記 |
| `pulse/group_session_proactive.py` | L8 群組行為觀察 |
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

### 6. lattice/crystals.json

**路徑**：`data/lattice/crystals.json`
**用途**：知識晶格——結晶化的知識資產

#### 讀寫表

| 模組 | 操作 | 函數 | 鎖 |
|------|------|------|-----|
| `agent/knowledge_lattice.py` | **RW** | 結晶存取 | ❌ 無 |
| `nightly/crystal_actuator.py` | **W** | 降級/升級 | ❌ 無 |
| `nightly/nightly_pipeline.py` | **R** | 降級偵測 | — |
| `nightly/evolution_velocity.py` | **R** | 結晶數量統計 | — |
| `agent/recommender.py` | **R** | 推薦 | — |
| `pulse/wee_engine.py` | **R** | 工作流查詢 | — |

#### ⚠️ 衝突風險

- knowledge_lattice 和 crystal_actuator 都能寫入 → 無鎖保護
- 降級邏輯可能與新增邏輯衝突

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

**路徑**：`data/pulse/pulse.db`
**引擎**：SQLite WAL mode
**用途**：VITA 生命力引擎結構化儲存（14 張表）

#### 寫入者

| 模組 | 寫入表 |
|------|--------|
| `pulse/pulse_db.py` | 全部 14 表（schedules, explorations, anima_log, evolution_events, morphenix_proposals, commitments, metacognition, scout_drafts, health_scores, incidents 等） |
| `nightly/nightly_pipeline.py` | evolution_events, 多表日誌 |

#### 讀取者（11 個模組）

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
| `pulse/pulse_engine.py` | explorations |
| `nightly/evolution_velocity.py` | evolution_events |
| `nightly/periodic_cycles.py` | metacognition |

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
| `agent/brain.py` | **W** | memories（記憶持久化） |
| `memory/memory_manager.py` | **RW** | memories |
| `agent/skill_router.py` | **R** | skills |
| `agent/knowledge_lattice.py` | **R** | documents |
| `agent/reflex_router.py` | **R** | memories |
| `memory/chromosome_index.py` | **R** | references |
| `agent/primal_detector.py` | **RW** | primals（八原語語義偵測——寫入索引 + 搜尋匹配） |

#### 鎖與降級

- **無顯式鎖**（Qdrant 內部 MVCC）
- **Graceful Degradation**：Qdrant 離線時靜默失敗 → **檢索能力降級為 TF-IDF（0.3 折扣）**
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

### 11. immunity/events.jsonl

**路徑**：`data/_system/immunity/events.jsonl`
**用途**：免疫系統事件日誌

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `governance/immunity.py` | **RW** | ❌ 無（JSONL append 相對安全） |
| `guardian/daemon.py` | **W** | ❌ 無 |
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
| activity_log.jsonl | `data/activity_log.jsonl` | ActivityLogger | SystemAudit | >5MB 輪替 |
| heartbeat.jsonl | `data/heartbeat.jsonl` | PulseEngine | Doctor, Nightly | >5MB 輪替 |
| q_scores.jsonl | `data/eval/q_scores.jsonl` | EvalEngine | EvalEngine, Nightly, ParameterTuner | >5MB 輪替 |
| satisfaction.jsonl | `data/eval/satisfaction.jsonl` | EvalEngine | EvalEngine | >5MB 輪替 |
| kernel_audit.jsonl | `data/guardian/kernel_audit.jsonl` | KernelGuard | SystemAudit | >5MB 輪替 |
| repair_log.jsonl | `data/guardian/repair_log.jsonl` | GuardianDaemon | Doctor | >5MB 輪替 |
| actions.jsonl | `data/_system/footprints/actions.jsonl` | FootprintStore | SystemAudit | 30 天 |
| decisions.jsonl | `data/_system/footprints/decisions.jsonl` | FootprintStore | SystemAudit | 90 天 |
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
| skill_usage_log.jsonl | `data/skill_usage_log.jsonl` | Brain, PulseEngine | ⚠️ DW2 嫌疑 | >5MB 輪替 |
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
| `memory/memory_manager.py` | **R** — `load_daily_log()` | 六層記憶管理讀取源（支援 dept_filter 過濾） |
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

## 必須同時修改的模組組（不可分批）

> 修改以下任一模組時，**必須**同時檢查並調整同組所有模組。

| 組 ID | 組名 | 模組 | 共享什麼 |
|-------|------|------|---------|
| **G1** | ANIMA 數值 | anima_tracker + brain + server + micro_pulse + kernel_guard | ANIMA_MC.json（寫入格式 + 鎖機制必須統一） |
| **G2** | 探索結晶管線 | pulse_engine + curiosity_router + exploration_bridge + nightly_pipeline + skill_forge_scout | question_queue.json + scout_queue/pending.json + PULSE.md 探索佇列 |
| **G3** | 記憶管線 | memory_manager + brain + vector_bridge + reflex_router + multi_agent_executor | MemoryStore + Qdrant memories collection（memory_manager 支援 dept_id 標籤寫入 + dept_filter 過濾檢索 + supersede() 事實覆寫 + VectorBridge.mark_deprecated() 軟刪除） |
| **G4** | 演化速度 | evolution_velocity + parameter_tuner + periodic_cycles + metacognition | accuracy_stats.json + tuned_parameters.json + velocity_log.jsonl |
| **G5** | 知識晶格 | knowledge_lattice + crystal_actuator + recommender | crystals.json + crystal_rules.json |
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
| crystals.json | **無** | — | ❌ 危險 |
| accuracy_stats.json | **無** | — | ❌ 危險 |

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
