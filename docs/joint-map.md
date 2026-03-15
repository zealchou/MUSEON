# Joint Map — 共享可變狀態接頭圖 v1.0

> **用途**：任何程式碼修改前，查閱此圖確認「我要改的模組碰了哪些共享狀態、誰還在讀寫同一根管子」。
> **比喻**：水電圖畫了管線位置，接頭圖畫的是「哪個水龍頭接哪根管、這根管誰負責」。
> **更新時機**：改變共享檔案的讀寫者或格式時，必須在同一個 commit 中同步更新此文件。
> **建立日期**：2026-03-15（DSE 第二輪排查後建立）

---

## 快速索引

| # | 共享狀態 | 危險度 | 寫入者 | 讀取者 | 鎖 | 頁內連結 |
|---|---------|--------|--------|--------|-----|---------|
| 1 | ANIMA_MC.json | 🔴 | 5 | 11+ | 部分 | [→](#1-anima_mcjson) |
| 2 | PULSE.md | 🔴 | 1(7法) | 5+ | 無 | [→](#2-pulsemd) |
| 3 | ANIMA_USER.json | 🔴 | 3 | 9 | 部分 | [→](#3-anima_userjson) |
| 4 | question_queue.json | 🟡 | 2 | 3 | 無 | [→](#4-question_queuejson) |
| 5 | scout_queue/pending.json | 🟡 | 2 | 2 | 無 | [→](#5-scout_queuependingjson) |
| 6 | lattice/crystals.json | 🟡 | 2 | 5 | 無 | [→](#6-latticecrystalsjson) |
| 7 | accuracy_stats.json | 🟡 | 2 | 6 | 無 | [→](#7-accuracy_statsjson) |
| 8 | PulseDB (pulse.db) | 🟡 | 2 | 11 | SQLite WAL | [→](#8-pulsedb-pulsedb) |
| 9 | Qdrant 向量庫 | 🟡 | 3 | 5 | 內部 MVCC | [→](#9-qdrant-向量庫) |
| 10 | soul_rings.json | 🟢 | 1 | 3 | ✅ Lock | [→](#10-soul_ringsjson) |
| 11 | immunity/events.jsonl | 🟢 | 2 | 3 | 無 | [→](#11-immunityeventsjsonl) |
| 12 | immune_memory.json | 🟢 | 1 | 2 | 無 | [→](#12-immune_memoryjson) |
| 13 | synapses.json | 🟢 | 1 | 3 | 無 | [→](#13-synapsesjson) |
| 14 | nightly_report.json | 🟢 | 1 | 3 | 原子寫 | [→](#14-nightly_reportjson) |
| 15 | morphenix/proposals/ | 🟢 | 1 | 3 | 原子寫 | [→](#15-morphenixproposals) |
| 16 | tuned_parameters.json | 🟢 | 1 | 2 | 無 | [→](#16-tuned_parametersjson) |

> **危險度定義**：🔴 多寫入者+高扇出+格式不一致 | 🟡 多寫入者或高扇出 | 🟢 單寫入者+低扇出

---

## 🔴 CRITICAL 區域

### 1. ANIMA_MC.json

**路徑**：`data/ANIMA_MC.json`
**用途**：MUSEON 靈魂核心——身份、人格、能力、演化狀態

#### 寫入者（5 個模組 → 統一經由 AnimaMCStore）

| 模組 | 函數 | 寫入的 Key | 格式 | 鎖 |
|------|------|-----------|------|-----|
| **`pulse/anima_mc_store.py`** | **`save()` / `update()`** | **統一入口** | 完整 JSON | **✅ `threading.Lock` + KernelGuard + 原子寫入(tmp→rename)** |
| `agent/brain.py` | `_save_anima_mc()` → 委派 Store | 整個檔案 | 完整 JSON | ✅ 經由 AnimaMCStore |
| `agent/brain.py` | `_update_crystal_count()` → Store.update() | `memory_summary.knowledge_crystals` | int | ✅ 原子讀改寫 |
| `agent/brain.py` | `_observe_self()` → Store.save() | `self_awareness.*`, `evolution.*` | str/dict | ✅ 經由 AnimaMCStore |
| `pulse/anima_tracker.py` | `_save()` → Store.update() | `eight_primal_energies`, `_vita_triggered_thresholds` | `{元素: {absolute: int, relative: float}}` | ✅ 經由 AnimaMCStore |
| `pulse/micro_pulse.py` | `_update_days_alive()` → Store.update() | `identity.days_alive` | int | ✅ 經由 AnimaMCStore |
| `onboarding/ceremony.py` | `receive_name()`, `_initialize_anima_l1()` | 初始化全部欄位 | 完整 JSON | 無（單次初始化，可接受） |

#### 讀取者（11+ 個模組）

| 模組 | 函數 | 讀取的 Key | 用途 |
|------|------|-----------|------|
| `agent/brain.py` | `_load_anima_mc()` | 全部 | 建構 system prompt、自我觀察 |
| `gateway/server.py` | `_build_system_prompt()` | identity, capabilities, personality | API 回應語氣 |
| `pulse/anima_tracker.py` | `_load()` | `eight_primal_energies` | 能量成長計算 |
| `pulse/micro_pulse.py` | `_update_days_alive()` | `identity.birth_date` | 天數計算 |
| `agent/soul_ring.py` | — | `eight_primal_energies` (via AnimaTracker) | 年輪記錄 |
| `agent/kernel_guard.py` | `validate_write()` | OMEGA/PHI/PSI 欄位 | 寫入前驗證 |
| `agent/drift_detector.py` | — | 全部 | 飄移基線比較 |
| `governance/perception.py` | — | 全部 | 四診合參 |
| `doctor/health_check.py` | — | JSON 結構 | 損毀偵測 |
| `doctor/field_scanner.py` | `ANIMA_MC_SCHEMA` | 全部欄位 | 使用率掃描 |
| `nightly/periodic_cycles.py` | — | `eight_primal_energies` | 30 天趨勢 |
| `mcp_server.py` | `museon_anima_status()` | 全部 | 暴露給 Claude Code |

#### ✅ 衝突風險（已修復 — 合約 1）

1. ~~brain vs anima_tracker 互相覆蓋~~ → **已修復**：統一經由 AnimaMCStore，單一 `threading.Lock`
2. ~~micro_pulse 直接寫入~~ → **已修復**：改用 `AnimaMCStore.update()` 原子讀改寫
3. **格式不一致**：brain 管 `eight_primals`（已過時），anima_tracker 管 `eight_primal_energies` → 兩套數值系統並存（待後續合約處理）

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

**鎖**：無顯式鎖，依賴原子寫入（tmp→rename）

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
| `agent/brain.py` | `_save_anima_user()` | 整體 | 原子寫入(tmp→rename) + KernelGuard |
| `onboarding/ceremony.py` | `receive_answers()` | `my_name`, `boss_name` | 無（單次初始化） |
| `guardian/daemon.py` | 修復邏輯 | 結構修復 | 無 |

#### 讀取者（9 個模組）

| 模組 | 用途 |
|------|------|
| `agent/brain.py` | 載入使用者資訊 |
| `agent/soul_ring.py` | 使用者觀察年輪 |
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

**位置**：`http://127.0.0.1:6333`（7 個 collections）
**用途**：語義搜尋——記憶、技能、知識文件的向量索引

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

#### 鎖與降級

- **無顯式鎖**（Qdrant 內部 MVCC）
- **Graceful Degradation**：Qdrant 離線時靜默失敗 → **檢索能力降級為 TF-IDF（0.3 折扣）**
- **Pending Index Queue**：`_pending_indexes` 暫存失敗索引（但無自動恢復觸發）
- **可用性快取**：60 秒

---

## 🟢 MEDIUM 區域

### 10. soul_rings.json

**路徑**：`data/anima/soul_rings.json`
**用途**：靈魂年輪——Append-only 成長記錄

| 模組 | 操作 | 鎖 |
|------|------|-----|
| `agent/soul_ring.py` | **RW** — append + reinforcement_count 更新 | ✅ `threading.Lock(_soul_lock)` |
| `agent/brain.py` | **R** | — |
| `nightly/evolution_velocity.py` | **R** | — |

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

## 必須同時修改的模組組（不可分批）

> 修改以下任一模組時，**必須**同時檢查並調整同組所有模組。

| 組 ID | 組名 | 模組 | 共享什麼 |
|-------|------|------|---------|
| **G1** | ANIMA 數值 | anima_tracker + brain + server + micro_pulse + kernel_guard | ANIMA_MC.json（寫入格式 + 鎖機制必須統一） |
| **G2** | 探索結晶管線 | pulse_engine + curiosity_router + exploration_bridge + nightly_pipeline + skill_forge_scout | question_queue.json + scout_queue/pending.json + PULSE.md 探索佇列 |
| **G3** | 記憶管線 | memory_manager + brain + vector_bridge + reflex_router | MemoryStore + Qdrant memories collection |
| **G4** | 演化速度 | evolution_velocity + parameter_tuner + periodic_cycles + metacognition | accuracy_stats.json + tuned_parameters.json + velocity_log.jsonl |
| **G5** | 知識晶格 | knowledge_lattice + crystal_actuator + recommender | crystals.json + crystal_rules.json |
| **G6** | 免疫系統 | immunity + immune_memory + immune_research + daemon | events.jsonl + immune_memory.json |

---

## 鎖機制一覽

| 共享狀態 | 鎖類型 | 模組 | 安全性 |
|---------|--------|------|--------|
| ANIMA_MC.json | **AnimaMCStore** (`threading.Lock` + KernelGuard + 原子寫入) | **全部寫入者** | ✅ **完整（合約 1 修復）** |
| ANIMA_MC.json | WriteQueue | brain | ✅ 序列化（非關鍵寫入） |
| soul_rings.json | `threading.Lock` | soul_ring | ✅ 完整 |
| observation_rings.json | `threading.Lock` | soul_ring | ✅ 完整 |
| PulseDB | SQLite WAL + `threading.Lock` | pulse_db | ✅ 完整 |
| Qdrant | 內部 MVCC | — | ✅ 資料庫層 |
| PULSE.md | 原子寫入(tmp→rename) | pulse_engine | ⚠️ 無並發保護 |
| question_queue.json | **無** | — | ❌ 危險 |
| scout_queue/pending.json | **無** | — | ❌ 危險 |
| crystals.json | **無** | — | ❌ 危險 |
| accuracy_stats.json | **無** | — | ❌ 危險 |

---

## 並發模型一覽

| 模組 | 並發模型 | 說明 |
|------|---------|------|
| brain.py | asyncio + threading 混合 | async def + threading.Lock |
| pulse_engine.py | asyncio | 全 async |
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
| 2026-03-15 | v1.2 | 合約 2 驗證已解決 + 合約 3：nightly async 橋接修復，並發模型表更新 |
| 2026-03-15 | v1.1 | 合約 1：AnimaMCStore 統一存取層，ANIMA_MC.json 鎖策略統一 |
| 2026-03-15 | v1.0 | 初始建立，16 個共享狀態，6 個模組組 |
