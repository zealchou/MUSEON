# MUSEON Persistence Contract v1.57 — 水電圖

> **本文件是 MUSEON 資料持久層的唯一真相來源。**
> 所有資料的寫入、消費、生命週期、格式、儲存位置，以此文件為準。
> 與 `system-topology.md`（控制流拓撲）互補——那是「神經圖」，這是「水電圖」。
> **v1.57 (2026-04-05)**：Phase 4 FV 藍圖同步——新增 `data/_system/skill_trust_scores.json`（🟢 Skill 信任分數持久化，寫入者=`nightly/skill_trust_tracker.py`（`persist()`），讀取者=`nightly/skill_trust_tracker.py`（`_load()`），格式=JSON 物件（`{skill_name: {score, origin, last_updated}}`），生命週期=永久累積（無 TTL，分數持續更新），備注：目前 skill_trust_tracker.py 為 prototype，尚未被其他模組 import，採用 update_trust_score(delta) + persist() 雙步驟寫入，T1/T2/T3 三等級邊界 0.4/0.7）。同步 joint-map v1.72、blast-radius v2.04、system-topology v1.87。
> **v1.56 (2026-04-05)**：Phase 2+3 FV 藍圖同步——新增 `data/_system/morphenix/processed_notes.json`（已結晶筆記清單，寫入者=`nightly/morphenix_executor.py`（`_action_crystallize_notes()`），讀取者=`morphenix_executor.py`（讀取已處理清單做去重），格式=JSON 陣列（note_id strings），生命週期=累積，無 TTL）；新增 `data/_system/footprints/crystal_observations.jsonl`（探索結晶觀察日誌，寫入者=`nightly/exploration_bridge.py`（含「認知/盲點/偏見/學到/發現」關鍵字的探索結晶），讀取者=未來 Observatory/SystemAudit，格式=JSONL（每行含 topic/observation/timestamp），生命週期=append-only）；新增 `morphenix_executor.py` 作為 `crystal_rules.json` 的第二寫入者（`_action_crystallize_notes()` 在規則數超過 100 條時自動淘汰最舊的 crystallized_note 型規則）。同步 joint-map v1.72、memory-router v1.29。
> **v1.55 (2026-04-05)**：Decision Atlas + Breath System + Elder Council——新增 `data/_system/decision_atlas/da-*.json`（決策結晶 JSON 群，寫入者=Claude Code session + 未來 L4 觀察者，讀取者=brain_prompt_builder.py persona zone + vision_loop.py 覆蓋度掃描，永久保存）；新增 `data/_system/breath/patterns/{yyyy-wNN}.json`（呼吸分析結果，寫入者=breath_analyzer.py Nightly Step 34.8，讀取者=vision_loop.py，保留最近 12 週）；新增 `data/_system/breath/visions/{yyyy-wNN}.json`（願景提案，寫入者=vision_loop.py Nightly Step 34.9，讀取者=未來 Elder Council，保留最近 12 週）；新增 `data/_system/breath/observations/{yyyy-wNN}.jsonl`（呼吸觀察 JSONL，寫入者=L4 觀察者+系統監控，讀取者=breath_analyzer.py，保留最近 12 週）；新增 `data/_system/elder_council/members.json`（長老名單，寫入者=手動/未來自動晉升，讀取者=vision_loop.py，永久）。同步 joint-map v1.70、memory-router v1.27。
> **v1.54 (2026-04-05)**：Entity Registry 建置——GroupContextDB 新增 4 張表：`entity_aliases`（別名映射，PK=alias+entity_type+entity_id，case-insensitive index）、`projects`（專案基本資訊）、`project_entities`（專案成員多對多關聯）、`events`（事件時間線，entity+project 雙索引）；寫入者=`governance/group_context.py`，讀取者=`governance/group_context.py`+`agent/brain_prompt_builder.py`（alias resolve）。L4CpuObserver 記憶寫入路徑修正：從 MemoryStore.write()（Markdown，靜默失敗）改為 MemoryManager.store()（Qdrant memories collection），chat_scope 欄位從 metadata 推導。brain_prompt_builder.py 人物搜尋新增 ProfileStore + GroupContextStore 讀取者。同步 joint-map v1.69、blast-radius v2.01。
> **v1.53 (2026-04-04)**：semantic_response_cache——新增 Qdrant dense collection `semantic_response_cache`（512 維，BAAI/bge-small-zh-v1.5，cosine distance）；寫入者=`cache/semantic_response_cache.py`（L4CpuObserver 回覆後呼叫），讀取者=`cache/semantic_response_cache.py`（Brain L1 查詢），TTL 動態（30min~12h），按 chat_id 做 payload filter 群組隔離，查詢時判斷 TTL 過期自動刪除。同步 joint-map v1.68。
> **v1.52 (2026-04-04)**：l4_cpu_observer 架構更新——新增 `data/_system/context_cache/{session_id}_signals.json`（EMA 訊號快取，寫入者=agent/l4_cpu_observer.py，讀取者=brain_prompt_builder.py _build_signal_context，格式=`{"signal_name": float, "_updated_at": "ISO8601"}`）；新增 `data/_system/pending_preference_updates.jsonl`（偏好更新 append-only 佇列，寫入者=agent/l4_cpu_observer.py，讀取者=Nightly pipeline 批次處理）；更新 #66 `session_adjustments/{session_id}.json` 寫入者從「L4 觀察者」改為 `agent/l4_cpu_observer.py`。同步 joint-map v1.67、memory-router v1.26。
> **v1.51 (2026-04-02)**：荒謬雷達系統——新增 `data/_system/absurdity_radar/{user_id}.json`（per-user 原子 JSON，寫入者=agent/absurdity_radar.py save_radar() + brain.py update，讀取者=absurdity_radar.py load_radar() + brain_prompt_builder.py + skill_router.py Layer 4，Nightly step 32.5 每日衰減）。
> **v1.50 (2026-04-01)**：ares 套件更名為 athena——`src/museon/ares/` → `src/museon/athena/`（profile_store.py、external_bridge.py、graph_renderer.py）；data 路徑 `ares/profiles/` 不變。同步 joint-map v1.64、blast-radius v1.96。
> **v1.49 (2026-04-01)**：.runtime 目錄正式廢除——所有持久層路徑統一為 MUSEON_HOME/ 下的單一路徑，不再有 .runtime/data vs data/ 雙路徑分支；CrystalStore schema drift 自動修復已部署（v1.48）。同步 system-topology v1.76、blast-radius v1.95。
> **v1.48 (2026-04-01)**：Phase 1-3 十項修復——CrystalStore 新增 schema drift 自動修復（ALTER TABLE ADD COLUMN，crystal.db ENGINE 1 表格新增 drift_fixed_at 追蹤欄）；signal_cache JSON 不再有寫入者（已確認 brain_prompt_builder 移除檔案讀取點，signal_cache 管道由 keyword 快篩替代，持久化路徑正式廢棄）。同步 system-topology v1.75、joint-map v1.62、memory-router v1.22。
> **v1.47 (2026-04-01)**：Phase A-C 死碼清理 + signal_lite 遷移——Qdrant dna27 collection 從 deprecated 改為「已清理」並從 Engine 2 表格移除（reflex_router 退役，signal_lite 純記憶體取代，不再需要向量索引）；移除數據流圖中 reflex_router 讀取記憶的標注；signal_lite 確認不使用任何持久層（純記憶體計算，request-scoped）。
> **v1.46 (2026-04-01)**：Brain 統一重構——Qdrant dna27 collection 標記為 deprecated（reflex_router 路由退役，signal_lite 取代，不再需要反射模式向量索引）；brain_fast.py 刪除後 session 檔案讀寫統一為 brain.py。
> **v1.45 (2026-03-31)**：推播系統重構——`pulse/push_budget.py` 已刪除，PulseDB push_log 表的**直接寫入路徑**移除（push_log 表本身保留，但 push_budget.py 不再作為獨立寫入者）；`pulse/pulse_engine.py` 不再經由 PushBudget 讀取 push_log；`pulse/proactive_bridge.py` is_within_daily_limit 不再查 PushBudget；`push_journal_24h.json`（Engine 3 JSON 檔）維持 ProactiveDispatcher 單一寫入者不變（PushBudget 原本沒有直接寫入此檔，影響為零）；`gateway/server.py` 移除 PushBudget 注入區塊。同步 blast-radius v1.91、system-topology v1.72、joint-map v1.59。
> **v1.44 (2026-03-31)**：Persona Evolution 系統——新增 `_system/mask_states.json`（面具狀態快照，mask_engine.py 原子寫入 tmp+rename，TTL=7 天，mask_engine.cleanup_stale 自動清理，每次儲存全量覆寫）；ANIMA_MC 新增子結構：`personality.trait_dimensions`（P1-P5 PSI 保護需 evolution_write、C1-C5 FREE 可 anima_mc_store.update 直接更新，寫入者=trait_engine.py C-traits 即時/nightly_reflection.py P-traits 每夜）、`evolution.trait_history`（APPEND_ONLY，寫入者=nightly_reflection.py，上限 200 筆）、`evolution.stage_history`（APPEND_ONLY，寫入者=brain_observation.py 於成長階段轉換時，上限 50 筆）。
> **v1.43 (2026-03-31)**：9 條斷裂接線修復——新增持久化路徑 `data/_system/museoff/finding_counts.json`（🟢 MuseOff 異常計數，格式：`{finding_key: int}`，寫入者=doctor/finding.py record_occurrence()（原子讀寫），讀取者=doctor/museoff.py（觸發 ≥3 次升級判斷），生命週期=永久累積，無 TTL）；新增讀取路徑 `data/_system/evolution/tuned_parameters.json`（🟢 唯讀，skill_router.py _load_tuned_rc_weight() 讀取 RC 權重，寫入者=parameter_tuner.py，無格式變更）。同步 topology v1.69、blast-radius v1.87、joint-map v1.57。
> **v1.42 (2026-03-31)**：體液系統迭代——新增 7 個 JSONL/JSON 持久化路徑：`data/_system/triage_queue.jsonl`（覺察訊號佇列，triage_step 寫入/消費，append-only，永久）、`data/_system/awareness_log.jsonl`（覺察日誌，triage_step 寫入，append-only，永久）、`data/_system/pending_adjustments.json`（待處理調整，triage_step 寫入/session_adjustment 讀取，原子寫，短期 TTL）、`data/_system/nightly_priority_queue.json`（Nightly 優先佇列，triage_step 寫入/triage_to_morphenix 消費後清空，原子寫）、`data/_system/session_adjustments/{session_id}.json`（即時行為調整，L4 觀察者寫入/brain_prompt_builder 讀取，原子寫，expires_after_turns TTL）、`data/_system/triage_human_queue.json`（人工審核佇列，triage_step HIGH/CRITICAL 寫入/Telegram 告警後消費，原子寫）、`data/skills/native/{name}/_lessons.json`（Skill 教訓檔，session_adjustment promote 寫入/brain_prompt_builder 注入 system prompt，原子寫，永久累積）；同步 topology v1.68、blast-radius v1.86、joint-map v1.56、memory-router v1.18。
> **v1.41 (2026-03-30)**：市場戰神（Market Ares）——新增 SQLite DB `data/market_ares/market_ares.db`（WAL 模式，busy_timeout=60s），6 張表：regions（地區五層數據+能量基底）、archetypes（聚類原型定義+16維能量）、simulations（模擬設定+策略）、snapshots（每週快照+商業指標+洞察）、competitors（競爭者 Agent）、partners（生態夥伴 Agent）；寫入者=market_ares/storage/db.py（init_schema/save_region/save_snapshot）；讀取者=simulation/engine.py + visualization/dashboard.py + analysis/final_report.py；生命週期=永久（每次模擬獨立存檔）。同步 system-topology v1.64、blast-radius v1.83、joint-map v1.53、memory-router v1.14。
> **v1.40 (2026-03-29)**：戰神系統（Ares）——新增 `data/ares/profiles/` 儲存路徑（JSON 個體檔案，寫入者=anima-individual Skill + external_bridge.py，讀取者=ares Skill + profile_store.py）；索引檔 `data/ares/profiles/_index.json`；新增 Python 模組 `src/museon/ares/`（profile_store.py CRUD + graph_renderer.py PNG + external_bridge.py Telegram 橋接）；knowledge-lattice 新增 2 種結晶類型（individual_crystal from anima-individual、strategy_crystal from ares）。同步 system-topology v1.62、blast-radius v1.80、joint-map v1.52、memory-router v1.13。
> **v1.39 (2026-03-29)**：OneMuse 能量解讀技能群——新增唯讀參考資料區塊 `data/knowledge/onemuse/`（36 檔，Markdown/JSON 格式），涵蓋 OM-DNA 核心規範、模組定義、64 卦知識、AEO 行動包、品牌視覺、報告模板；讀取者：energy-reading、wan-miu-16、combined-reading 三個 Skill（唯讀參考，不寫入）。同步 system-topology v1.61、blast-radius v1.79、joint-map v1.51、memory-router v1.12。
> **v1.38 (2026-03-28)**：死碼清理後同步——Qdrant collection `dna27` 的寫入者 `reflex_router.py` 確認（dna27.py 模組已刪，collection 由 reflex_router 維護）；移除已刪除模組的寫入者條目：channels/line（data_bus 消費者）、llm/vision、memory/epigenetic_router、multiagent/flywheel_flow、pulse/group_session_proactive、tools/document_export、tools/report_publisher；新增消費者確認：pulse_db 消費者從 10→11（新增 pulse/group_digest）。

---

## 設計原則

1. **三引擎收斂**：所有持久化歸口到 SQLite（結構化）、Qdrant（語義向量）、Markdown（人類可讀）
2. **寫入必有消費者**：每個寫入點必須在本文件有對應的消費者，否則視為 Dead Write 需清理
3. **生命週期顯式**：每筆資料都有明確的 TTL 或歸檔策略
4. **單一寫入者原則**：每個儲存位置只有一個模組負責寫入，避免競爭
5. **讀取可多方**：消費者不限，但必須透過定義的介面讀取

---

## 儲存引擎（三引擎架構）

### Engine 1: SQLite — 結構化資料庫

| 資料庫 | 路徑 | 負責模組 | 用途 | WAL |
|--------|------|---------|------|-----|
| **PulseDB** | `data/pulse/pulse.db` | `pulse/pulse_db.py` | 排程、探索、ANIMA、演化、承諾、後設認知、推送日誌(push_log — v1.45 起無直接寫入者，push_budget.py 已刪除) | Yes |
| **GroupContextDB** | `data/_system/group_context.db`（v1.34 修正；另有 `_system/sessions/group_context.db` 副本待清理） | `governance/group_context.py` | 多租戶對話上下文 + Entity Registry（群組+DM+bot回覆+別名映射+專案+事件，v1.54 擴展） | Yes |
| **WorkflowStateDB** | `data/_system/wee/workflow_state.db` | `evolution/wee_engine.py` | 工作流演化狀態 | Yes |
| **CrystalDB** | `data/lattice/crystal.db` | `agent/crystal_store.py` | 知識晶體（crystals, links, cuid_counters 三表） | Yes |
| **RegistryDB** | `data/registry/cli_user/registry.db`（v1.34 修正路徑層級） | `tools/tool_registry.py` | 使用者註冊、工具清單 | Yes |
| **MessageQueueDB** | `data/_system/message_queue.db` | `gateway/message_queue_store.py` | 訊息佇列持久化（crash recovery，pending/done/failed 三態） | Yes |

**共用規範**：
- 所有 SQLite 必須開啟 WAL 模式（`PRAGMA journal_mode=WAL`）
- busy_timeout = 60000ms
- 透過 singleton factory 取得連線（`get_pulse_db()` 模式）
- 定期 WAL checkpoint（Nightly Step 28 — 待實作，需涵蓋 5 個 DB）

### Engine 2: Qdrant — 語義向量索引

| Collection | 維度 | 負責模組 | 寫入者 | 搜尋者 |
|-----------|------|---------|--------|--------|
| `memories` | 1024 | `vector_bridge.py` | `memory_manager.py` | `memory_manager.py`, `brain.py` |
| `skills` | 1024 | `vector_bridge.py` | `vector_bridge.py` (via `index_all_skills()`) | `skill_router.py`, `brain.py` |
| `crystals` | 1024 | `vector_bridge.py` | `knowledge_lattice.py` | `knowledge_lattice.py`, `brain.py` |
| `workflows` | 1024 | `vector_bridge.py` | `workflow_engine.py` | `workflow_engine.py` |
| `documents` | 1024 | `vector_bridge.py` | `mcp_connector.py` | `vector_bridge.query_points()` |
| `references` | 1024 | `vector_bridge.py` | `zotero_bridge.py` | `zotero_bridge.py` |
| `primals` | 1024 | `vector_bridge.py` | `primal_detector.py` | `primal_detector.py` |
| `gaps` | 1024 | `vector_bridge.py` | `agent/gap_accumulator.py`（弱匹配向量索引，三軌道 A/B/C 聚合寫入） | `agent/gap_accumulator.py`（RW，缺口去重與語意聚類） |

### semantic_response_cache（v12 新增）
- **引擎**: Qdrant dense collection（512 維，BAAI/bge-small-zh-v1.5，cosine distance）
- **寫入者**: `cache/semantic_response_cache.py`（via L4CpuObserver 呼叫）
- **讀取者**: `cache/semantic_response_cache.py`（via Brain L1 查詢）
- **Payload**: chat_id (keyword index), query, response, signals, ttl, created_at
- **TTL**: 動態（30min~12h，依訊號類型）
- **隔離**: 按 chat_id 做 payload filter（群組隔離）
- **容量策略**: TTL 過期自動刪除（查詢時判斷）

**Sparse Collections（BM25 稀疏向量，Route A 分離式）**：

| Collection | 型態 | 負責模組 | 寫入者 | 搜尋者 |
|-----------|------|---------|--------|--------|
| `{name}_sparse` | sparse-only (BM25) | `vector_bridge.py` | `VectorBridge.index_sparse()` / `backfill_sparse()` | `VectorBridge._sparse_search()` via `hybrid_search()` |

- 命名規則：原 collection 名稱加 `_sparse` 後綴（例：`crystals_sparse`）
- 稀疏向量名稱：`bm25`（`SparseVectorParams` 預設）
- IDF 表儲存：`data/_system/sparse_idf.json`（`SparseEmbedder` 持久化）
- 零遷移設計：不修改原 dense collection 的 schema
- Graceful degradation：IDF 未建立或 sparse collection 不存在時，`hybrid_search()` 降級為純 dense
- IDF 表重建由 Nightly Step 8.7 `_step_sparse_idf_rebuild()` 負責
- 回填（backfill）同步在 Step 8.7 執行，覆蓋 memories, skills, crystals 三個 collection
- `hybrid_search()` 現在被 4 個上游消費者呼叫：`skill_router`, `memory_manager`, `knowledge_lattice`, `server.py`

**共用規範**：
- 統一透過 `VectorBridge` 操作，不直接 import qdrant_client
- indexing_threshold = 1000（確保 HNSW 建立）
- 寫入失敗時 graceful degradation（不阻斷主流程）
- Nightly 負責 collection 健康檢查

### Engine 3: Markdown — 人類可讀記憶

| 路徑模式 | 負責模組 | 寫入者 | 消費者 |
|---------|---------|--------|--------|
| `data/memory/{YYYY}/{MM}/{DD}/{channel}.md` | `memory/store.py` | `MemoryStore.write()` | `MemoryStore.read()`, Nightly 壓縮 |
| `data/PULSE.md` | `pulse/pulse_engine.py` | `PulseEngine`（✅ threading.Lock + 原子寫入） | `brain.py`, `explorer.py` |
| `data/SOUL.md` | `agent/soul_ring.py` (DiaryStore) | `DiaryStore` | `brain.py` |
| `data/skills/{category}/{name}.md` | `core/skill_manager.py` | Morphenix/手動 | `skill_router.py`, `skill_manager.py` |
| `data/workspace/*.md` | 各模組 | 臨時產出 | 使用者直接閱讀 |

---

## 資料流圖（Data Flow Map）

### 管線 A：對話記憶管線

```
User Message
    │
    ▼
┌─────────────────┐
│  MemoryStore     │ ──→ data/memory/{date}/{channel}.md   [Markdown]
│  (store.py)      │
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  MemoryManager   │ ──→ data/memory_v3/{user}/{layer}/*.json  [JSON]
│  (memory_mgr.py) │ ──→ Qdrant:memories  [Vector]
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  Nightly         │     壓縮 L1→L2, L2→L3（步驟 1-5）
│  (pipeline.py)   │     向量重索引（步驟 6）
└─────────────────┘
```

**寫入→消費鏈**：
| 資料 | 寫入者 | 消費者 | TTL |
|------|--------|--------|-----|
| `memory/{date}/{ch}.md` | MemoryStore | Nightly 壓縮, 使用者閱讀 | 永久 |
| `memory_v3/{user}/L0_buffer/*.json` | MemoryManager | MemoryManager（升級到 L1） | 24h |
| `memory_v3/{user}/L1_short/*.json` | MemoryManager | recall(), Nightly L1→L2 | 7d |
| `memory_v3/{user}/L2_ep/*.json` | MemoryManager/Nightly | recall() | 90d |
| `memory_v3/{user}/L2_sem/*.json` | Nightly 跨結晶 | recall() | 永久 |
| `memory_v3/{user}/L3_procedural/*.json` | Nightly | recall() | 永久 |
| `memory_v3/{user}/L4_identity/*.json` | Nightly | recall() | 永久 |
| `memory_v3/{user}/L5_scratch/*.json` | 手動 | recall() | 永久 |
| Qdrant:`memories` | MemoryManager | semantic recall | ∞（跟隨 JSON） |
| Qdrant:`memories` (deprecated) | VectorBridge.mark_deprecated() | search() 自動過濾 | ∞（軟刪除標記） |
| `data/anima/fact_corrections.jsonl` | Brain._log_fact_correction() | ProactiveBridge, PulseEngine, Brain | 永久(append) |

### 管線 A-2：事實更正覆寫管線（P0 新增）

```
User 糾正事實（「不是…是…」「只有」「你記錯了」等）
    │
    ▼
┌─────────────────┐
│  Brain           │ ──→ _detect_fact_correction()（CPU 啟發式）
│  (brain.py)      │ ──→ _handle_fact_correction()（LLM 判斷矛盾）
└─────────────────┘
    │
    ├──→ MemoryManager.supersede()  [JSON: archived=True + 新記憶]
    ├──→ VectorBridge.mark_deprecated()  [Qdrant: status=deprecated]
    └──→ data/anima/fact_corrections.jsonl  [JSONL append: 更正日誌]
```

### 管線 B：Pulse 生命力管線

```
Heartbeat Timer (30s)
    │
    ▼
┌─────────────────┐
│  PulseEngine     │ ──→ data/PULSE.md  [Markdown]
│  (pulse_engine)  │ ──→ data/pulse/heartbeat_focus.json  [JSON]
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  PulseDB         │ ──→ data/pulse/pulse.db  [SQLite]
│  (pulse_db.py)   │     13 tables
└─────────────────┘
    │
    ├──→ explorations table ──→ Explorer, Nightly
    ├──→ schedules table ──→ TaskScheduler, Telegram
    ├──→ anima_log table ──→ AnimaTracker, Nightly
    ├──→ commitments table ──→ CommitmentTracker, Brain
    ├──→ morphenix_proposals ──→ MorphenixExecutor, Nightly
    ├──→ evolution_events ──→ WEE, Nightly
    ├──→ metacognition table ──→ Metacognition
    ├──→ scout_drafts table ──→ SkillScout, Nightly
    ├──→ health_scores table ──→ DendriticScorer, Doctor
    ├──→ incidents table ──→ SelfDiagnosis, Doctor  [P2: Governor→server callback 寫入]
    └──→ orchestrator_calls table ──→ 未來 A1 確定性路由  [L2-S3 Orchestrator 診斷]
```

### 管線 C：評估與追蹤管線

```
每次回應後
    │
    ▼
┌─────────────────┐
│  EvalEngine      │ ──→ data/eval/q_scores.jsonl  [JSONL append]
│  (eval_engine)   │ ──→ data/eval/satisfaction.jsonl  [JSONL append]
│                  │ ──→ data/eval/daily/{date}.json  [JSON snapshot]
│                  │ ──→ data/eval/weekly/{week}.json  [JSON snapshot]
│                  │ ──→ data/eval/ab_baselines.json  [JSON state]
│                  │ ──→ data/eval/blindspots.json  [JSON state]
│                  │ ──→ data/eval/alerts.json  [JSON state]
└─────────────────┘
```

### 管線 E：Evolution 演化管線

```
Nightly / WEE / OutwardTrigger
    │
    ├──→ EvolutionVelocity ──→ data/_system/evolution/velocity_log.jsonl  [JSONL]
    ├──→ ParameterTuner ──→ data/_system/evolution/tuned_parameters.json  [JSON]
    │                    ──→ data/_system/evolution/tuning_audit.jsonl  [JSONL]
    ├──→ TriggerWeights ──→ data/_system/trigger_configs.json  [JSON]
    ├──→ ToolMuscle ──→ data/_system/tool_muscles.json  [JSON]
    ├──→ OutwardTrigger ──→ data/_system/outward/*.json  [JSON 多檔]
    └──→ DigestEngine ──→ data/_system/outward/quarantine.json  [JSON]
                       ──→ data/_system/morphenix/notes/*.json  [JSON]
```

### 管線 F：Guardian 守護管線

```
Guardian Daemon (launchd 常駐)
    │
    ├──→ ANIMA_MC.json  [JSON R/W] — 結構修復
    ├──→ ANIMA_USER.json  [JSON R/W] — 結構修復
    ├──→ data/_system/guardian/repair_log.jsonl  [JSONL W]
    ├──→ data/_system/guardian/unresolved.json  [JSON W]
    ├──→ data/_system/guardian/state.json  [JSON W]
    └──→ data/_system/guardian/mothership_queue.json  [JSON W]
```

### 管線 F-2：寫入前快照備份管線（P3-1 新增）

```
寫入前觸發（ANIMA_MC / PULSE.md）
    │
    ├──→ AnimaMCStore._backup_before_write()
    │       ──→ data/_system/backups/anima_mc/ANIMA_MC_{timestamp}.json  [JSON]
    │       保留最近 10 份快照
    │
    └──→ PulseEngine._backup_pulse_md()
            ──→ data/_system/backups/pulse_md/PULSE_{timestamp}.md  [Markdown]
            保留最近 10 份快照
```

**寫入→消費鏈**：
| 資料 | 寫入者 | 消費者 | TTL |
|------|--------|--------|-----|
| `_system/backups/anima_mc/*.json` | AnimaMCStore._backup_before_write() | 手動恢復 | 保留 10 份（FIFO 輪替） |
| `_system/backups/pulse_md/*.md` | PulseEngine._backup_pulse_md() | 手動恢復 | 保留 10 份（FIFO 輪替） |

### 管線 G：Federation 聯邦管線

```
SkillMarket / FederationSync
    │
    ├──→ SkillMarket ──→ data/_system/marketplace/registry.json  [JSON]
    │                 ──→ data/_system/marketplace/installs.json  [JSON]
    │                 ──→ data/_system/marketplace/packages/*.mskill  [ZIP]
    └──→ FederationSync ──→ GitHub Private Repo (museon-federation/)  [Git]
```


### 管線 D：審計與足跡管線

```
每次操作
    │
    ├──→ ActivityLogger ──→ data/activity_log.jsonl  [JSONL]
    ├──→ Footprint ──→ data/_system/footprints/actions.jsonl  [JSONL]
    ├──→ Footprint ──→ data/_system/footprints/cognitive_trace.jsonl  [JSONL]
    ├──→ Gateway ──→ data/heartbeat.jsonl  [JSONL]
    ├──→ Guardian ──→ data/guardian/kernel_audit.jsonl  [JSONL]
    ├──→ LLM Router ──→ data/_system/pulse/routing_log_{date}.jsonl  [JSONL]
    └──→ Telegram ──→ data/channels/telegram/{date}.jsonl  [JSONL]
```

---

## 寫入→消費配對表（完整）

### 正常配對

| ID | 資料 | 寫入者 | 消費者 | 格式 | TTL | 狀態 |
|----|------|--------|--------|------|-----|------|
| W01 | Q-Score 歷史 | EvalEngine | EvalEngine.load, Nightly | JSONL | 輪替 >5MB | OK |
| W02 | 滿意度信號 | EvalEngine | EvalEngine.load | JSONL | 輪替 >5MB | OK |
| W03 | ANIMA 日誌 | PulseDB | AnimaTracker, Nightly | SQLite | 永久 | OK |
| W04 | 演化事件 | PulseDB | WEE, Nightly | SQLite | 永久 | OK |
| W05 | 承諾追蹤 | CommitmentTracker | Brain, Nightly | SQLite | 已完成 90d 後清理 | OK |
| W06 | Morphenix 提案 | PulseDB | MorphenixExecutor, Nightly | SQLite | 已完成 30d 後清理 | OK |
| W07 | 探索日誌 | Explorer/PulseDB | Explorer, Nightly | SQLite | 永久 | OK |
| W08 | 心跳日誌 | Gateway | Doctor/LogAnalyzer | JSONL | 輪替 >5MB | OK |
| W09 | 活動日誌 | ActivityLogger | SystemAudit | JSONL | 輪替 >5MB | OK |
| W10 | 六層記憶 | MemoryManager | MemoryManager.recall | JSON+Vector | 按層級 | OK |
| W11 | 向量索引 | VectorBridge | VectorBridge.search | Qdrant | ∞ | OK |
| W12 | 路由統計 | LLM Router | Nightly/Job | JSONL | 輪替 >5MB | OK |
| W13 | 知識晶體 | KnowledgeLattice (via CrystalStore) | KnowledgeLattice, Brain | SQLite(WAL)+Vector, 含 Procedure 結晶 (skills_used/preconditions/known_failures/last_success) + OneMuse 三結晶（energy_crystal/persona_crystal/relationship_crystal） | 永久 | OK |
| W14 | 日記條目（原靈魂年輪） | DiaryStore | Brain, Nightly | JSON | 永久 | OK |
| W15 | ANIMA 狀態 | Brain | Brain 啟動時載入 | JSON | 永久 | OK |
| W16 | Pulse 狀態 | PulseEngine | Brain, Explorer | Markdown | 每次覆寫 | OK |
| W17 | 技能庫 | SkillManager | SkillRouter | Markdown | 永久 | OK |
| W18 | 工具註冊 | ToolRegistry | ToolRegistry | JSON | 永久 | OK |
| W19 | 預算追蹤 | BudgetManager | BudgetManager, Nightly | JSON | 月度歸檔 | OK |
| W20 | 群組上下文 | GroupContextStore | Gateway, Brain | SQLite | 永久 | OK |
| W21 | 染色體索引 | ChromosomeIndex | MemoryManager | JSON | 永久 | OK |
| W22 | Kernel 審計 | Guardian | Doctor | JSONL | 輪替 >5MB | OK |
| W23 | 足跡日誌 | Footprint | SystemAudit | JSONL | 輪替 >5MB | OK |
| W24 | 演化速度快照 | EvolutionVelocity | ParameterTuner | JSONL | 輪替 >5MB | OK |
| W25 | 調諧稽核 | ParameterTuner | EvolutionVelocity | JSONL | 輪替 >5MB | OK |
| W26 | 觸發器設定 | TriggerWeights | NightlyPipeline | JSON | 永久 | OK |
| W27 | 工具肌肉記憶 | ToolMuscle | NightlyPipeline | JSON | 永久 | OK |
| W28 | Guardian 修復日誌 | Guardian/Daemon | Doctor/HealthCheck | JSONL | 輪替 >5MB | OK |
| W29 | Outward 隔離區 | DigestEngine | DigestEngine(再處理) | JSON | 永久 | OK |
| W30 | Guardian 狀態 | Guardian/Daemon | Guardian/Daemon(恢復) | JSON | 永久 | OK |
| W31 | LLM Token 預算 | BudgetManager | BudgetManager, Nightly | JSON | 月度歸檔 | OK |
| W32 | 技能市集註冊 | SkillMarket | SkillMarket, Gateway | JSON | 永久 | OK |
| W33 | 外向演化狀態 | OutwardTrigger | NightlyPipeline | JSON | 永久 | OK |
| W34 | 八原語向量索引 | PrimalDetector | PrimalDetector.detect | Qdrant | ∞ | OK |
| W35 | 認知追蹤日誌 | FootprintStore.trace_cognitive() | SystemAudit(Skill Doctor), Observatory | JSONL | 30 天 | OK |
| W36 | 百合引擎決策快取 | Brain.Step 3.65 (baihe_decide) | ProactiveBridge._read_baihe_cache() | JSON | 2 小時（過期忽略） | OK |
| W37 | 動態授權清單 | PairingManager (gateway/authorization.py) | PairingManager.is_paired(), TelegramAdapter.get_trust_level(), museon_auth_status() | JSON | 永久（TTL 可選） | OK |
| W38 | 分級授權策略 | AuthorizationPolicy (gateway/authorization.py) | SecurityGate.check_tool_access(), museon_auth_status() | JSON | 永久 | OK |
| W39 | Orchestrator 呼叫診斷 | brain.py（via _dispatch_orchestrate） | 未來 A1 確定性路由設計 | SQLite(PulseDB) | 永久 | OK |

> **v1.10 補充（Phase 4 飛輪多代理）**：
> - W10 六層記憶條目新增 `dept_id` 欄位（可選），用於部門級記憶隔離
> - `memory_manager.py` 的 `store()` 接受 `dept_id` 參數，自動注入 `dept:{dept_id}` 標籤
> - `memory_manager.py` 的 `recall()` 接受 `dept_filter` 參數，在 Qdrant 和 TF-IDF 兩條搜尋路徑均支援過濾
> - MultiAgentExecutor、ResponseSynthesizer、FlywheelCoordinator 均為無狀態/記憶體內狀態，不新增持久化
>
> **v1.23 補充（群組 chat_scope 隔離）**：
> - W10 六層記憶條目新增 `chat_scope` + `group_id` 欄位（可選），用於群組級記憶隔離
> - `memory_manager.py` 的 `store()` 接受 `chat_scope`/`group_id` 參數，自動注入 `scope:{chat_scope}` 標籤
> - `memory_manager.py` 的 `recall()` 接受 `chat_scope_filter`/`exclude_scopes` 參數，三條搜尋路徑（向量+TF-IDF+keyword fallback）均支援過濾
> - `_vector_index()` 將 chat_scope 注入 Qdrant metadata
> - 外部使用者 ANIMA v3.0：`governance/multi_tenant.py` ExternalAnimaManager schema 升級（profile/relationship/seven_layers + trust_evolution + v2→v3 自動遷移）

### Dead Write（寫入無消費者）

| ID | 資料 | 寫入者 | 路徑 | 建議處理 |
|----|------|--------|------|---------|
| DW1 | Telegram 群組日誌 | telegram.py | `data/channels/telegram/{date}.jsonl` | 確認是否需要分析功能，否則移除寫入 |
| DW2 | 技能使用日誌 | Brain | `data/skill_usage_log.jsonl` | ✅ 已升級為正常配對——消費者：Brain（_track_skill_usage outcome 寫入）+ WEE（待接通） |
| DW3 | 直覺信號日誌 | Intuition | `data/intuition/signal_log.jsonl` | 需確認 Nightly 是否消費 |

### Dead Directory（無代碼引用）

| 路徑 | 建議 |
|------|------|
| `data/plans/` (含 active/, archive/, workflows/) | 已遷移到 WorkflowStore，刪除空目錄 |
| `data/_system/courses/` | 空，刪除 |
| `data/_system/dreams/` | 空，刪除 |
| `data/_system/mcp/` | 空，刪除 |
| `data/_system/shared_assets/` | 空，刪除 |
| `data/_system/stress-test/` | 空，刪除 |
| `data/dispatch/` | 已退役，刪除 |
| `data/inbox/` | 已退役，刪除 |
| `data/morphenix/` | 已遷移到 _system/morphenix/，刪除 |
| `data/secretary/` | 已退役，刪除 |
| `data/sub_agents/` | 已退役，刪除 |
| `data/vault/` | 已退役，刪除 |
| `data/vector/` | 已遷移到 Qdrant，刪除 |
| `data/wee/` | 已遷移到 _system/wee/，刪除 |

---

## 生命週期管理

### TTL 分級

| 等級 | 保留期 | 適用資料 | 清理機制 |
|------|--------|---------|---------|
| **PERMANENT** | 永久 | L3-L5 記憶, 日記條目, ANIMA(含L8群組行為), 知識晶體 | 不清理 |
| **LONG** | 90 天 | L2 情節記憶, 已完成承諾 | Nightly Step 清理 |
| **MEDIUM** | 30 天 | L1 短期記憶, 已執行提案, 壓縮歸檔 | Nightly Step 清理 |
| **SHORT** | 14 天 | Session 快取, 臨時上下文 | Nightly Step 26 (已實作) |
| **EPHEMERAL** | 24 小時 | L0 buffer, 臨時運算 | MemoryManager 自動升級 |
| **ROLLING** | >5MB 輪替 | JSONL 日誌 | Nightly Step 27 (已實作) |

### 歸檔策略

| 資料類型 | 歸檔觸發 | 歸檔位置 | 格式 |
|---------|---------|---------|------|
| JSONL 日誌 | >5MB | 同目錄 .gz | gzip 壓縮 |
| .gz 歸檔 | >30 天 | 刪除 | - |
| Session JSON | >14 天 | 刪除 | - |
| 評估日報 | >90 天 | `eval/archive/` | 合併 JSON |
| PulseDB 備份 | 每次 Nightly | `pulse/pulse.db.bak` | 覆寫式 |

### 衰減與優先級模型（Decay & Priority Model）

> 跨模組的橫切關注點：四個子系統各自實作衰減函數，控制資料的「老化退場」。
> 修改任何衰減參數時，需同步查閱 `blast-radius.md` G8 組。

#### 四大衰減引擎

| 引擎 | 模組 | 衰減公式 | 閾值 | 觸發時機 |
|------|------|---------|------|---------|
| **結晶衰減** | `agent/knowledge_lattice.py` | `RI = (0.3×Freq + 0.4×Depth + 0.3×Quality) × exp(-0.03 × days_since_last_cited)` | RI < 0.05 → 自動歸檔 | 每次結晶檢索時計算 |
| **記憶層級衰減** | `agent/memory_manager.py` | TTL 離散分級（見上方 TTL 分級表）+ 訪問次數晉升（L0→L1→L2）+ 低相關性降級（L2→L1→L0） | 各層 TTL 到期 / 訪問計數 < 閾值 | Nightly 清理 + MemoryManager 即時升降 |
| **健康分數衰減** | `governance/dendritic_scorer.py` | 指數衰減，半衰期 2 小時：`score(t) = score₀ × exp(-ln2/2h × Δt)` | 無硬閾值（分數影響治理決策） | 每次 `tick()` 呼叫（governor 每回合觸發） |
| **推薦近因性衰減** | `agent/recommender.py` | 近因性半衰期 7 天 + 互動衰減係數 λ=0.95：`recency = exp(-ln2/7d × days)` × `interaction_decay = 0.95^n` | 無硬閾值（影響推薦排序權重） | 每次推薦計算時即時計算 |
| **ACT-R Activation 衰減** | `memory/adaptive_decay.py` | `B_i = ln(Σ t_j^{-d}) + β_i`；d=0.5（ACT-R 標準值）；β_i = ring_type_bonus + entry_type_bonus + reinforcement_bonus | activation < -2.0 → 沉降（dormant） | EpigeneticRouter.activate() 呼叫 MemoryReflector.reflect() → AdaptiveDecay.rank_by_activation()；nightly Step 32 sweep |

#### 衰減引擎間的關係

```
knowledge_lattice ──RI 衰減──→ crystal.db (via CrystalStore) ←──降級/升級──── crystal_actuator (Nightly)
                                     ↑
                              recommender (讀取 RI 排序推薦)

memory_manager ──TTL+訪問──→ Qdrant memories ←──deprecated 標記── fact_correction
                                     ↑
                              ~~reflex_router~~ (已清理 v1.47，signal_lite 純記憶體取代)

dendritic_scorer ──半衰期──→ health_scores (PulseDB) ←── governor (注入 immunity 事件)
                                     ↑
                              brain Step 5.5 (P3 融合讀取)

recommender ──近因性衰減──→ 推薦排序 (in-memory)

adaptive_decay ──ACT-R B_i──→ _activation 欄位 (in-memory) ←── memory_reflector (排序+反思)
                                     ↑
                              ~~epigenetic_router~~ (已刪除 v1.38，多圖遍歷功能移除)
                              brain_prompt_builder (注入 memory zone)
                                     ↑
                              crystals.json RI (交叉影響)
```

#### 衰減參數速查

| 參數 | 值 | 所在檔案 | 修改影響 |
|------|-----|---------|---------|
| 結晶 RI λ | 0.03 | `knowledge_lattice.py` | 結晶老化速度：↑ 更快遺忘、↓ 更長記憶 |
| 結晶歸檔閾值 | 0.05 | `knowledge_lattice.py` | ↓ 更多結晶被歸檔、↑ 更多低品質結晶留存 |
| 健康分數半衰期 | 2h | `dendritic_scorer.py` | ↑ 系統更寬容、↓ 對異常更敏感 |
| 推薦近因性半衰期 | 7d | `recommender.py` | ↑ 舊內容更常被推薦、↓ 偏好近期內容 |
| 互動衰減 λ | 0.95 | `recommender.py` | ↑ 互動次數影響更小、↓ 越多互動權重越低 |
| 記憶 L0 TTL | 24h | `memory_manager.py` | 短期記憶存活時間 |
| 記憶 L1 TTL | 14d | `memory_manager.py` | 中期記憶存活時間 |
| 記憶 L2 TTL | 90d | `memory_manager.py` | 長期記憶存活時間 |
| Supersede 機制 | 即時 | `memory_manager.py` | 事實覆寫：新事實 mark 舊事實為 deprecated |

---

## JSON 資料位置清單

> 此區對應目前散落在 `data/` 各處的 JSON 檔案，標明負責模組。

### 根目錄 JSON

| 檔案 | 負責模組 | 用途 | R/W |
|------|---------|------|-----|
| `ANIMA_MC.json` | `pulse/anima_mc_store.py` | ANIMA 多元性狀態（✅ AnimaMCStore 統一存取） | R/W |
| `ANIMA_MC.personality.trait_dimensions` | `trait_engine.py`（C-traits 即時）/ `nightly_reflection.py`（P-traits 每夜） | 人格特質維度：P1-P5 PSI 保護（需 evolution_write），C1-C5 FREE（可 anima_mc_store.update 直接更新） | R/W |
| `ANIMA_MC.evolution.trait_history` | `nightly_reflection.py` | 特質演化歷史（APPEND_ONLY，上限 200 筆） | R/W |
| `ANIMA_MC.evolution.stage_history` | `brain_observation.py`（成長階段轉換時觸發） | 成長階段歷史（APPEND_ONLY，上限 50 筆） | R/W |
| `ANIMA_USER.json` | `brain.py` | 使用者 ANIMA 狀態 | R/W |
| `ceremony_state.json` | `onboarding/ceremony.py` | 初始化儀式狀態 | R/W |
| `tasks.json` | `pulse/pulse_engine.py` | 任務清單快照 | R/W |

### `_system/` 子目錄

| 路徑 | 負責模組 | 用途 |
|------|---------|------|
| `_system/budget/usage_{month}.json` | `llm/budget.py` | 月度 Token 用量 |
| `_system/mask_states.json` | `persona/mask_engine.py` | 面具狀態快照（引擎=JSON 原子寫入 tmp+rename，TTL=7 天，mask_engine.cleanup_stale 清理，每次全量覆寫） |
| `_system/chromosome_index.json` | `memory/chromosome_index.py` | 染色體索引 |
| `_system/curiosity/question_queue.json` | `pulse/curiosity_router.py` | 好奇心佇列 |
| `_system/evolution/version.json` | `evolution/wee_engine.py` | 系統版本追蹤 |
| `_system/footprints/actions.jsonl` | `governance/footprint.py` | L1 足跡 |
| `_system/footprints/cognitive_trace.jsonl` | `governance/footprint.py` | 認知追蹤（Brain Step 8 決策迴圈的認知軌跡） |
| `_system/morphenix/*.json` | `nightly/morphenix_executor.py` | 執行快照 |
| `_system/morphenix/processed_notes.json` | `nightly/morphenix_executor.py`（`_action_crystallize_notes()`） | 已結晶筆記清單（去重用）|
| `_system/footprints/crystal_observations.jsonl` | `nightly/exploration_bridge.py` | 探索結晶觀察日誌（append-only） |
| `_system/outward/*.json` | `evolution/outward_trigger.py` | 外向演化狀態（behavior_shift, cooldown, counter, pending_signals 等） |
| `_system/sessions/*.json` | `brain_tools.py` / `session_cleanup.py` | 會話快照（v1.55 新增 metadata.last_active 自動清理） |
| `_system/tools/registry.json` | `tools/tool_registry.py` | 工具清單 |
| `_system/evolution/velocity_log.jsonl` | `nightly/evolution_velocity.py` | 演化速度快照 |
| `_system/evolution/tuned_parameters.json` | `nightly/parameter_tuner.py` | 已調諧參數 |
| `_system/evolution/tuning_audit.jsonl` | `nightly/parameter_tuner.py` | 調諧稽核軌跡 |
| `_system/trigger_configs.json` | `evolution/trigger_weights.py` | 觸發器設定 |
| `_system/tool_muscles.json` | `evolution/tool_muscle.py` | 工具肌肉記憶 |
| `_system/outward/*.json` | `evolution/outward_trigger.py` | 外向演化狀態 |
| `_system/guardian/repair_log.jsonl` | `guardian/daemon.py` | 修復日誌 |
| `_system/guardian/state.json` | `guardian/daemon.py` | 守護狀態 |
| `_system/marketplace/*.json` | `federation/skill_market.py` | 技能市集註冊與安裝記錄 |
| `_system/lord_profile.json` | `agent/brain.py` (`_observe_lord()`) | 主人領域強弱項畫像（軍師架構基礎層） |
| `_system/baihe_cache.json` | `agent/brain.py` (Step 3.65 百合引擎) | 百合引擎最近決策快取——供 ProactiveBridge 讀取象限調整推送語氣（原子寫入 tmp→rename） |
| `_system/budget/usage_{month}.json` | `llm/budget.py` | 月度 Token 用量 |
| `_system/backups/anima_mc/*.json` | `pulse/anima_mc_store.py` | ANIMA_MC 寫入前快照（保留 10 份） |
| `_system/backups/pulse_md/*.md` | `pulse/pulse_engine.py` | PULSE.md 寫入前快照（保留 10 份） |
| `_system/absurdity_radar/{user_id}.json` | `agent/absurdity_radar.py` + `agent/brain.py` | 六大荒謬雷達 per-user 快照（v1.51 新增，詳見下方專節） |
| `_system/context_cache/{session_id}_signals.json` | `agent/l4_cpu_observer.py` | L4 CPU Observer EMA 訊號快取（v1.52 新增，寫入者=l4_cpu_observer observe() EMA 合併，讀取者=brain_prompt_builder.py _build_signal_context，格式=`{"signal_name": float, "_updated_at": "ISO8601"}`） |
| `_system/pending_preference_updates.jsonl` | `agent/l4_cpu_observer.py` | L4 CPU Observer 偏好更新 append-only 佇列（v1.52 新增，每條一個 JSON 物件，Nightly pipeline 批次處理） |
| `_system/session_adjustments/{session_id}.json` | `agent/l4_cpu_observer.py` (寫入) / `agent/brain_prompt_builder.py` (讀取) | 即時行為調整（v1.52 更新寫入者為 l4_cpu_observer.py，expires_after_turns TTL） |
| `_system/decision_atlas/da-*.json` | Claude Code session（手動/自動萃取） / 未來 L4 觀察者（寫入）；`agent/brain_prompt_builder.py`（persona zone 注入）/ `nightly/vision_loop.py`（覆蓋度掃描）（讀取） | 決策結晶 JSON 群（v1.55 新增，每個決策結晶一檔，永久保存，不衰減） |
| `_system/breath/patterns/{yyyy-wNN}.json` | `nightly/breath_analyzer.py`（唯一寫入者，Nightly Step 34.8，週三/四）；`nightly/vision_loop.py`（讀取） | 呼吸分析結果（v1.55 新增，保留最近 12 週） |
| `_system/breath/visions/{yyyy-wNN}.json` | `nightly/vision_loop.py`（唯一寫入者，Nightly Step 34.9，週日）；未來 Elder Council 投票機制（讀取） | 願景提案（v1.55 新增，保留最近 12 週） |
| `_system/breath/observations/{yyyy-wNN}.jsonl` | L4 觀察者 + 系統監控（寫入）；`nightly/breath_analyzer.py`（讀取） | 呼吸觀察 JSONL，每行一個觀察（v1.55 新增，保留最近 12 週） |
| `_system/elder_council/members.json` | 手動 / 未來自動晉升（寫入）；`nightly/vision_loop.py`（讀取，未來投票機制） | 長老名單（v1.55 新增，永久，人類管理） |

### PDR 持久化（v1.70 新增）

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `_system/pdr_params.json` | JSON | pdr_params | telegram_pump, brain, pdr_council, museqa | PDR 調控參數 |
| `_system/agent_registry.json` | JSON | agent_registry | pdr_council | 統一能力目錄 |
| `_system/museqa/pdr_adjustments.jsonl` | JSONL append | museqa | nightly audit | MuseQA 自動調控審計日誌 |
| `_system/realtime_gaps.jsonl` | JSONL append | skill_forge_scout | skill_forge_scout | 即時 Skill 缺口記錄 |

### Phase 1-9 新增持久化（v1.37）

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `_system/pulse/push_journal_24h.json` | JSON | `pulse/proactive_dispatcher.py` | `channels/telegram.py` | ProactiveDispatcher 24hr 推播日誌，每次推播寫入，24hr 自動清除 |
| `_system/memory_graph/edges.json` | JSON | `memory/memory_graph.py` | `agent/brain.py` | MemoryGraph 關聯邊，永久保留 |
| `_system/memory_graph/access_log.json` | JSON | `memory/memory_graph.py` | `memory/memory_graph.py` | MemoryGraph 存取紀錄，永久保留 |
| `_system/learning/insights/*.json` | JSON (個別檔案) | `learning/insight_extractor.py` | `agent/brain.py` | InsightExtractor 萃取的洞見，永久保留 |
| `_system/doctor/shared_board.json` | JSON | `doctor/museoff.py`, `doctor/museqa.py`, `doctor/musedoc.py`, `doctor/museworker.py` | 五虎將 + nightly | 五虎將共享看板，50 筆上限滾動 |
| `_system/billing/skill_invocations_*.json` | JSON (月度檔案) | `billing/trust_points.py` | `billing/trust_points.py` | Skill 調用計數月度檔案，永久保留 |
| `_system/forge_triggers.jsonl` | JSONL append | skill_forge_scout | nightly | Skill 鍛造觸發記錄 |
| `_system/pdr_baseline_analysis.json` | JSON | 分析腳本 | PDR 初始化 | 七天基線分析 |

### Brain Token 預算分配（P2-1 更新）

> `token_optimizer.py` 管理 system prompt 的 token 區段預算。v1.28 新增第 6 區段 Strategic Zone。

| Zone | 預算 (tokens) | 用途 | 負責模組 |
|------|--------------|------|---------|
| Core Identity | 1200 | 身份+人格 | brain.py |
| Memory | 2000 | 六層記憶注入 | brain.py |
| Soul Context | 1500 | PULSE.md + 日記 | brain.py |
| Skills | 800 | 技能上下文 | brain.py |
| Buffer | 1800 | 預留彈性空間（原 2800，P2-1 壓縮） | brain.py |
| **Strategic** | **1000** | **決策夥伴策略上下文（P2-1 新增）** | **brain.py `_build_strategic_context()`** |

> **注意**：Strategic Zone 為記憶體內 token 預算分配，不產生持久化資料。`_build_strategic_context()` 從 ANIMA_MC.json、lord_profile.json 等既有持久層讀取並組裝。

### `~/.museon/auth/` 子目錄（Runtime 授權狀態）

> **注意**：此目錄位於 `~/.museon/auth/`（Runtime 區），不在 `data/` 下。
> 授權狀態為 Gateway 運行時管理，不隨 `data/` 備份或遷移。

| 檔案 | 負責模組 | 用途 |
|------|---------|------|
| `allowlist.json` | `gateway/authorization.py` (PairingManager) | 動態授權使用者清單（user_id → display_name + trust_level + TTL）；原子寫入（tmp→rename） |
| `policy.json` | `gateway/authorization.py` (AuthorizationPolicy) | 三級授權策略（auto/ask/block 工具分類）；原子寫入（tmp→rename） |

### `anima/` 子目錄

| 檔案 | 負責模組 | 用途 |
|------|---------|------|
| `anima/drift_baseline.json` | `agent/drift_detector.py` | 漂移基線 |
| `anima/soul_rings.json` | `agent/soul_ring.py` (DiaryStore) | 日記條目序列（v2.0 新增 entry_type/highlights/learnings/tomorrow_intent） |

### `knowledge/onemuse/` 子目錄（唯讀參考資料）

> **注意**：此目錄為唯讀參考資料，不由任何模組寫入。Skill 僅讀取作為分析知識庫。

| 路徑 | 格式 | 讀取者 | 用途 |
|------|------|--------|------|
| `knowledge/onemuse/` (36 檔) | Markdown / JSON | energy-reading, wan-miu-16, combined-reading | OneMuse 能量解讀知識庫 |

> **內容**：OM-DNA 核心規範、模組定義、64 卦知識、AEO 行動包、品牌視覺規範、報告模板
> **引擎**：Markdown/JSON（人類可讀參考檔案，非資料庫）
> **寫入者**：無（唯讀參考資料，手動維護）

### `ares/profiles/` 子目錄（Ares 個體檔案）

> **注意**：此目錄為 ANIMA 個體追蹤引擎的持久化儲存。每個第三方人物一個 JSON 檔案。

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `ares/profiles/{profile_id}.json` | JSON | `anima-individual` Skill, `src/museon/athena/profile_store.py`, `src/museon/athena/external_bridge.py` | `ares` Skill, `src/museon/athena/profile_store.py` | ANIMA 個體檔案（七層鏡像、八大槓桿、互動歷史、關係溫度） |
| `ares/profiles/_index.json` | JSON | `src/museon/athena/profile_store.py` | `ares` Skill, `src/museon/athena/profile_store.py` | 個體索引（profile_id → 名稱/建立時間/最後更新） |

> **引擎**：JSON（人類可讀個體檔案）
> **生命週期**：永久（持續更新）
> **結晶類型**：anima-individual → knowledge-lattice `individual_crystal`；ares → knowledge-lattice `strategy_crystal`
> **Python 模組**：`src/museon/athena/profile_store.py`（CRUD + 槓桿 + 連線 + 路徑搜尋 + 連動模擬）、`src/museon/athena/graph_renderer.py`（networkx PNG 渲染）、`src/museon/athena/external_bridge.py`（Telegram 群組成員→Ares 個體橋接器）

### `_system/absurdity_radar/` 子目錄（荒謬雷達，v1.51 新增）

> **注意**：此目錄為六大荒謬守望的 per-user 雷達快照。每個使用者一個 JSON 檔案，原子寫入。

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `_system/absurdity_radar/{user_id}.json` | JSON | `agent/absurdity_radar.py save_radar()`, `agent/brain.py update_radar_from_skill()` | `agent/absurdity_radar.py load_radar()`, `agent/brain_prompt_builder.py _build_absurdity_radar_context()`, `agent/skill_router.py match() Layer 4` | 六大荒謬雷達 per-user 快照 |

**引擎**：原子 JSON（read → modify → write_text）
**路徑**：`data/_system/absurdity_radar/{user_id}.json`
**格式**：`{"user_id": "boss", "self_awareness": 0.5, ..., "confidence": 0.1, "updated_at": "ISO8601"}`
**寫入者**：`agent/absurdity_radar.py save_radar()` + `agent/brain.py update_radar_from_skill()`
**讀取者**：`agent/absurdity_radar.py load_radar()` + `agent/brain_prompt_builder.py _build_absurdity_radar_context()` + `agent/skill_router.py match() Layer 4`
**TTL**：永久（Nightly step 32.5 每日衰減，不刪除）
**鎖**：無需（per-user 檔案，單一寫入者路徑）

### `_system/context_cache/{session_id}_signals.json`（l4_cpu_observer 訊號快取，v1.52 新增）

> **注意**：此檔案為 L4 CPU Observer 每次觀察後以 EMA 方式合併更新的訊號快取，供 brain_prompt_builder 建構訊號上下文使用。

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `_system/context_cache/{session_id}_signals.json` | JSON | `agent/l4_cpu_observer.py observe()`（每次觀察 EMA 合併） | `agent/brain_prompt_builder.py _build_signal_context()` | per-session 訊號快取 |

**引擎**：JSON 原子寫入
**格式**：`{"signal_name": float, "_updated_at": "ISO8601"}`
**寫入者**：`agent/l4_cpu_observer.py`（EMA merge on each observation）
**讀取者**：`agent/brain_prompt_builder.py _build_signal_context()`
**TTL**：Session 級別，session 結束或 Nightly 清理
**鎖**：無需（per-session 單一寫入者）
**危險度**：🟢（單寫入者）

### `_system/pending_preference_updates.jsonl`（l4_cpu_observer 偏好佇列，v1.52 新增）

> **注意**：此檔案為 L4 CPU Observer 偵測到偏好變化時 append-only 寫入，Nightly pipeline 批次處理。

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `_system/pending_preference_updates.jsonl` | JSONL append-only | `agent/l4_cpu_observer.py observe()` | Nightly pipeline（批次處理偏好更新） | 偏好更新待處理佇列 |

**引擎**：JSONL append-only
**格式**：每行一個 JSON 物件（偏好更新記錄）
**寫入者**：`agent/l4_cpu_observer.py`
**讀取者**：Nightly pipeline（批次處理）
**TTL**：Nightly 處理後清空
**鎖**：無需（append-only 單寫入者）
**危險度**：🟢（append-only，單寫入者）

### `_system/quality_gaps.jsonl`（gap_accumulator 品質缺口日誌，v1.56 新增）

> **注意**：gap_accumulator 每次偵測到低分請求時 append-only 寫入，供 Claude Code session 啟動掃描使用。

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `_system/quality_gaps.jsonl` | JSONL append-only | `agent/gap_accumulator.py`（低分 Skill 請求記錄） | Claude Code session 啟動掃描 / 未來 Nightly 分析 | 品質缺口審計日誌 |

**引擎**：JSONL append-only
**格式**：每行一個 JSON（含 timestamp/chat_id/user_input/best_skill/match_score/track 欄位）
**寫入者**：`agent/gap_accumulator.py`
**讀取者**：Claude Code session 啟動時掃描 `_system/skill_requests/`
**TTL**：30 天滾動
**鎖**：無需（append-only 單寫入者）
**危險度**：🟢（append-only）

---

### `_system/weak_match_log.jsonl`（gap_accumulator 弱匹配日誌，v1.56 新增）

> **注意**：skill_router._match_score 低於閾值時，gap_accumulator 記錄弱匹配事件。

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `_system/weak_match_log.jsonl` | JSONL append-only | `agent/gap_accumulator.py`（_match_score < threshold 時記錄） | Claude Code session 啟動掃描 | 弱匹配審計日誌（Track B） |

**引擎**：JSONL append-only
**格式**：每行一個 JSON（含 timestamp/user_input/matched_skill/score/threshold 欄位）
**寫入者**：`agent/gap_accumulator.py`（brain.py Step 3.1c 注入點觸發）
**讀取者**：Claude Code session 啟動掃描
**TTL**：30 天滾動
**鎖**：無需（append-only 單寫入者）
**危險度**：🟢（append-only）

---

### `_system/skill_requests/`（gap_accumulator Skill 需求槽，v1.56 新增）

> **注意**：gap_accumulator 在跨多輪累積到足夠缺口信號時，寫入 req_*.json 供 Claude Code session 讀取。

| 路徑 | 格式 | 寫入者 | 讀取者 | 說明 |
|------|------|--------|--------|------|
| `_system/skill_requests/req_*.json` | JSON（單一需求） | `agent/gap_accumulator.py`（缺口聚合達閾值時生成） | Claude Code session（啟動時掃描），人工審閱 | 待鍛造 Skill 需求槽 |

**引擎**：JSON 原子寫入（tmp→rename）
**格式**：`{"request_id": str, "gap_type": str, "description": str, "supporting_evidence": list, "priority": str, "created_at": ISO8601}`
**寫入者**：`agent/gap_accumulator.py`
**讀取者**：Claude Code session 啟動時掃描，確認後轉交 Skill Forge 流程
**TTL**：人工審閱後手動刪除或歸檔
**鎖**：原子寫入（tmp→rename）
**危險度**：🟢（單寫入者，人工消費）

---

### `eval/` 子目錄

| 路徑 | 負責模組 | 用途 |
|------|---------|------|
| `eval/q_scores.jsonl` | `agent/eval_engine.py` | Q-Score 追蹤 |
| `eval/satisfaction.jsonl` | `agent/eval_engine.py` | 滿意度信號 |
| `eval/ab_baselines.json` | `agent/eval_engine.py` | A/B 基線 |
| `eval/blindspots.json` | `agent/eval_engine.py` | 盲點分析 |
| `eval/alerts.json` | `agent/eval_engine.py` | 品質警報 |
| `eval/daily/{date}.json` | `agent/eval_engine.py` | 日報 |
| `eval/weekly/{week}.json` | `agent/eval_engine.py` | 週報 |

---

## 重構路線圖（Phased）

### Phase 0：清理（本次迭代已完成部分）
- [x] C1: Qdrant 恢復策略 → process
- [x] C2: indexing_threshold → 1000
- [x] D1: 刪除冗餘 data/pulse.db
- [x] D2: Session TTL (Nightly Step 26)
- [x] D3: JSONL 輪替 (Nightly Step 27)
- [x] D4: references → VectorBridge COLLECTIONS
- [x] B3: 重建 PulseDB

### Phase 1：死目錄清理 + WAL checkpoint（低風險）
- [ ] 刪除 14 個死目錄
- [ ] 清理 .bak 檔案到 MUSEON_archive/
- [ ] Nightly Step 28: SQLite WAL checkpoint（所有 5 個 DB）
- [ ] 接通 skill_usage_log.jsonl 的消費者
- [ ] 確認 Telegram JSONL 的去留

### Phase 2：JSON → SQLite 遷移（中風險）
- [x] `ceremony_state.json` → PulseDB.ceremony_state table
- [x] `tasks.json` → 跳過（無程式碼讀寫，已由 schedules + commitments 覆蓋）
- [x] `eval/ab_baselines.json` → PulseDB.eval_baselines table
- [x] `eval/blindspots.json` → PulseDB.eval_blindspots table
- [x] `eval/alerts.json` → PulseDB.eval_alerts table
- [x] 保留 JSONL 作為 append-only 審計（不遷移）
- [x] 保留 daily/weekly JSON 作為快照（不遷移）
- [x] 自動遷移機制：首次讀取 PulseDB 無資料時自動從 JSON fallback 遷移

### Phase 3：Store 介面統一（高收益）
- [x] 定義 `DataContract` 基類（store_spec + health_check）→ `core/data_bus.py`
- [x] 所有 Store 類實現 DataContract（10 個 Store 已接入）
- [x] 建立 `DataBus`（類比 EventBus 的資料層路由）→ `core/data_bus.py`
- [x] Store 註冊機制（DataBus.register + get_data_bus singleton）

已接入 DataContract 的 Store 類：
| Store 類 | 引擎 | TTL | 檔案 |
|---------|------|-----|------|
| PulseDB | SQLite | PERMANENT | `pulse/pulse_db.py` |
| MemoryStore | Markdown | PERMANENT | `memory/store.py` |
| LatticeStore | SQLite (WAL) via CrystalStore | PERMANENT | `agent/knowledge_lattice.py` + `agent/crystal_store.py` |
| DiaryStore (原 SoulRingStore) | JSON (append-only) | PERMANENT | `agent/soul_ring.py` |
| WorkflowStore | Mixed (MD+JSON) | PERMANENT | `workflow/soft_workflow.py` |
| FootprintStore | JSONL (append-only: actions+decisions+evolutions+cognitive_trace) | MEDIUM | `governance/footprint.py` |
| GroupContextStore | SQLite | PERMANENT | `governance/group_context.py` |
| SkillManager | JSON | PERMANENT | `core/skill_manager.py` |
| ActivityLogger | JSONL (append-only) | SHORT | `core/activity_logger.py` |
| EvalStore | Mixed (JSONL+PulseDB) | LONG | `agent/eval_engine.py` |
| WorkflowEngine | SQLite | PERMANENT | `workflow/workflow_engine.py` |

### Phase 4：監控與自癒
- [x] 資料完整性自動檢查 → Nightly Step 29 `DataWatchdog.run_health_check()`
- [x] 寫入量/讀取量監控指標 → 每次 health_check 記錄 size snapshot，JSONL 歷史追蹤
- [x] Dead Write 自動偵測 → 比對 30 天快照，size 不變 = 嫌疑 Dead Write
- [x] 儲存空間預警 → SQLite >500MB / JSONL >50MB / JSON >10MB / 全系統 >1GB

實作模組：
- `core/data_watchdog.py` — DataWatchdog 主邏輯
- `core/event_bus.py` — 新增 4 個資料監控事件
- `nightly/nightly_pipeline.py` — Step 29 接入
- 快照持久化：`data/_system/data_health/` (latest_snapshot.json + snapshot_history.jsonl)

### Pipeline R：Memory Reset Pipeline（一鍵重置管線）

> v1.14 新增。`doctor/memory_reset.py` 提供全系統記憶/知識一鍵重置，涵蓋 25 個持久層。

**觸發方式**：CLI `python -m museon.doctor.memory_reset --home ~/MUSEON [--confirm]`

| 類別 | 層 | 目標 | 操作 |
|------|-----|------|------|
| A.身份 | A1 | ANIMA_MC.json（boss/self_awareness） | 重置為初始模板（保留 identity.name=霓裳） |
| A.身份 | A2 | ANIMA_USER.json | 重置為空模板（七層結構+空 profile） |
| A.身份 | A3 | PulseDB.ceremony_state | DELETE FROM + reset sequence |
| B.對話 | B1 | PULSE.md | 從模板重新生成 |
| B.對話 | B2 | SOUL.md | 清空內容 |
| B.對話 | B3 | memory/{date}/*.md | 刪除所有記憶 Markdown |
| B.對話 | B4 | memory_v3/*.json | 刪除 JSON 記憶檔 |
| B.對話 | B5 | session/*.json | 刪除所有 session 檔 |
| B.對話 | B6 | PulseDB.anima_log | DELETE FROM + reset sequence |
| B.對話 | B7 | PulseDB.metacognition | DELETE FROM + reset sequence |
| C.知識 | C1 | crystal.db (crystals, links, cuid_counters) | DELETE FROM 三表 + reset sequence（舊 crystals.json 已歸檔為 .bak） |
| C.知識 | C2 | Qdrant collections | 刪除並重建（保留 schema） |
| C.知識 | C3 | synapses.json | 重置為空物件 |
| C.知識 | C4 | scout_queue/*.json | 刪除待處理佇列 |
| D.行為 | D1 | soul_rings.json (DiaryStore) | 重置為空陣列 |
| D.行為 | D2 | drift_log.jsonl | 清空 |
| D.行為 | D3 | fact_corrections.jsonl | 清空 |
| E.評估 | E1 | PulseDB（其餘表） | DELETE FROM 所有非 ceremony 表 |
| E.評估 | E2 | eval/*.jsonl + daily_reports/ | 刪除所有評估資料 |
| E.評估 | E3 | workflow_state.db | DELETE FROM workflows + executions |
| F.日誌 | F1 | activity_log.jsonl | 清空 |
| F.日誌 | F2 | guardian/*.jsonl | 清空所有 guardian 日誌 |
| F.日誌 | F3 | footprints/*.jsonl | 清空足跡日誌 |
| G.狀態 | G1 | nightly_state.json | 重置為空物件 |
| G.狀態 | G2 | _system/outward/*.json | 刪除外展狀態 |

**安全機制**：
- 預設 `--dry-run`（不加 `--confirm` 只列出清單不執行）
- 執行前列出所有待清除層，執行後報告成功/失敗/跳過統計
- ANIMA_MC 保留 identity.name（Museon 不忘記自己叫什麼）
- 清除後重建骨架目錄結構

---

## 與系統拓撲的對應

`system-topology.md` 中的 `data` 群組需擴展：

| 拓撲節點 | 對應引擎 | 狀態 |
|---------|---------|------|
| `memory` | Markdown + JSON | ✅ 已存在 |
| `vector-index` | Qdrant | ✅ 已存在 |
| `registry` | RegistryDB SQLite | ✅ 已存在（v1.4 更名） |
| `pulse-db` | PulseDB SQLite (16 表) | ✅ v1.4 新增 |
| `group-context-db` | GroupContextDB SQLite | ✅ v1.4 新增 |
| `workflow-state-db` | WorkflowStateDB SQLite | ✅ v1.4 新增 |
| `wee` | 演化引擎 | ✅ 已存在 |
| `skills-registry` | Markdown | ✅ 已存在 |
| `crystal-store` | CrystalDB SQLite (WAL) | ✅ v1.26 新增 |
| `skill-synapse` | JSON | ⚠️ 待確認是否已退役 |

---

## 版本紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.56 | 2026-04-05 | 能力缺口偵測系統——新增 Qdrant `gaps` collection（1024 維，寫入者+搜尋者=agent/gap_accumulator.py，三軌道弱匹配向量索引）；新增 `_system/quality_gaps.jsonl`（品質缺口審計日誌，JSONL append-only，單寫入者 gap_accumulator.py）；新增 `_system/weak_match_log.jsonl`（弱匹配事件日誌，JSONL append-only，單寫入者 gap_accumulator.py，Track B）；新增 `_system/skill_requests/req_*.json`（待鍛造 Skill 需求槽，JSON 原子寫入，寫入者=gap_accumulator.py，讀取者=Claude Code session 啟動掃描）。同步 system-topology v1.85、joint-map v1.71、blast-radius v2.03 |
| v1.55 | 2026-04-05 | Decision Atlas + Breath System + Elder Council——新增 `_system/decision_atlas/da-*.json`（決策結晶 JSON 群，寫入者=Claude Code session + 未來 L4 觀察者，讀取者=brain_prompt_builder.py + vision_loop.py，永久）；新增 `_system/breath/patterns/{yyyy-wNN}.json`（呼吸分析結果，寫入者=breath_analyzer.py Step 34.8，讀取者=vision_loop.py，12 週保留）；新增 `_system/breath/visions/{yyyy-wNN}.json`（願景提案，寫入者=vision_loop.py Step 34.9，讀取者=未來 Elder Council，12 週保留）；新增 `_system/breath/observations/{yyyy-wNN}.jsonl`（呼吸觀察 JSONL，寫入者=L4 觀察者+系統監控，讀取者=breath_analyzer.py，12 週保留）；新增 `_system/elder_council/members.json`（長老名單，寫入者=手動/未來自動晉升，讀取者=vision_loop.py，永久）。同步 joint-map v1.70、memory-router v1.27 |
| v1.52 | 2026-04-04 | l4_cpu_observer 架構更新——新增 `_system/context_cache/{session_id}_signals.json`（EMA 訊號快取，寫入者=agent/l4_cpu_observer.py observe() EMA 合併，讀取者=brain_prompt_builder.py _build_signal_context，格式=`{"signal_name": float, "_updated_at": "ISO8601"}`）；新增 `_system/pending_preference_updates.jsonl`（偏好更新 append-only 佇列，寫入者=l4_cpu_observer.py，讀取者=Nightly pipeline 批次處理）；更新 #66 session_adjustments/{id}.json 寫入者從「L4 觀察者」改為 `agent/l4_cpu_observer.py`。同步 joint-map v1.67、memory-router v1.26 |
| v1.44 | 2026-03-31 | Persona Evolution 系統——新增 `_system/mask_states.json`（面具狀態快照，mask_engine.py 原子寫入 tmp+rename，TTL=7 天，cleanup_stale 清理，全量覆寫）；ANIMA_MC 新增 `personality.trait_dimensions`（P1-P5 PSI 保護/C1-C5 FREE，寫入者 trait_engine.py+nightly_reflection.py）、`evolution.trait_history`（APPEND_ONLY，上限 200 筆，nightly_reflection.py）、`evolution.stage_history`（APPEND_ONLY，上限 50 筆，brain_observation.py）。同步 memory-router v1.19 |
| v1.0 | 2026-03-15 | 初版：完整水電圖，涵蓋 23 個正常配對、3 個 Dead Write、14 個死目錄 |
| v1.1 | 2026-03-15 | Phase 2 完成：4 個 JSON 遷移至 PulseDB（ceremony_state + eval 三件套） |
| v1.2 | 2026-03-15 | Phase 3 完成：DataContract + DataBus 建立，10 個 Store 類統一接入 |
| v1.40 | 2026-03-29 | 戰神系統（Ares）——新增 `data/ares/profiles/` 儲存路徑（JSON 個體檔案 + _index.json 索引）；寫入者 anima-individual Skill + profile_store.py + external_bridge.py；讀取者 ares Skill + profile_store.py；knowledge-lattice 新增 individual_crystal + strategy_crystal 結晶類型；新增 Python 模組 src/museon/ares/。同步 topology v1.62、blast v1.80、joint v1.52、memory-router v1.13 |
| v1.39 | 2026-03-29 | OneMuse 能量解讀技能群——新增唯讀參考資料 `data/knowledge/onemuse/`（36 檔 Markdown/JSON），讀取者 energy-reading/wan-miu-16/combined-reading（唯讀）。同步 topology v1.61、blast v1.79、joint v1.51、memory-router v1.12 |
| v1.37 | 2026-03-27 | 有機體進化計畫 Phase 1-9——新增 6 個持久化條目：`push_journal_24h.json`（ProactiveDispatcher 24hr 推播日誌）、`memory_graph/` edges+access_log（MemoryGraph 關聯邊+存取紀錄，永久）、`learning/insights/`（InsightExtractor 洞見，永久）、`shared_board.json`（五虎將看板，50 筆滾動）、`skill_invocations_*.json`（Skill 調用計數月度檔，永久）。同步 system-topology v1.54、blast-radius v1.71、joint-map v1.48、memory-router v1.10 |
| v1.36 | 2026-03-25 | 訊息佇列持久化——新增 MessageQueueDB（`data/_system/message_queue.db`，SQLite WAL，message_queue_store.py Owner，telegram_pump.py enqueue/mark_done/mark_failed，server.py startup init）；表數 5→6 |
| v1.35 | 2026-03-25 | 對話持久化——GroupContextDB 擴展（DM msg_type='dm' + bot_reply，text 截斷 2000→8000，clients 表新增 personality_notes/communication_style）；無新增 DB |
| v1.34 | 2026-03-24 | 全面審計同步——group_context.db 路徑修正為 `data/_system/group_context.db`；registry.db 路徑修正為 `data/registry/cli_user/registry.db`；無新增持久層 |
| v1.33 | 2026-03-23 | Sparse Embedder 512 維重建——sparse_idf.json 更新（2307 詞 IDF 表）；memories sparse collection 286 筆回填；無新增 DB |
| v1.32 | 2026-03-23 | Project Epigenesis 接線——衰減引擎新增第 5 個：ACT-R Activation 衰減（`memory/adaptive_decay.py`，`B_i = ln(Σ t_j^{-d}) + β_i`，d=0.5，沉降閾值 -2.0）；衰減引擎間關係圖新增 adaptive_decay → memory_reflector → epigenetic_router → brain_prompt_builder 鏈路；純 in-memory 計算，無新增持久層寫入/消費配對；同步 blast-radius v1.55、joint-map v1.40、memory-router v1.6 |
| v1.30 | 2026-03-22 | Sparse Embedder 啟動：Sparse Collections 新增 Nightly Step 8.7 IDF 重建 + 回填排程；hybrid_search() 消費者 0→4（skill_router + memory_manager + knowledge_lattice + server.py）；同步 joint-map v1.35、blast-radius v1.35 |
| v1.29 | 2026-03-22 | Brain 三層治療——PulseDB 新增 `orchestrator_calls` 表（id/plan_id/skill_count/task_count/success/model/response_length/created_at，brain.py `_dispatch_orchestrate()` 寫入，供未來 A1 確定性路由分析）；新增 W39 配對（Orchestrator 呼叫診斷）；PulseDB 表數 15→16；管線 B 表清單新增 orchestrator_calls；拓撲對應表更新；同步 joint-map v1.34、system-topology v1.37 |
| v1.28 | 2026-03-22 | P0-P3 升級——新增管線 F-2 寫入前快照備份（ANIMA_MC 寫入前快照 `_system/backups/anima_mc/` + PULSE.md 寫入前快照 `_system/backups/pulse_md/`，各保留 10 份 FIFO 輪替）；Brain Token 預算新增第 6 區段 Strategic Zone（1000 tokens，buffer 2800→1800）；`_system/` 子目錄新增 backups 兩個路徑條目；同步 system-topology v1.35、joint-map v1.33、blast-radius v1.46、memory-router v1.4 |
| v1.27 | 2026-03-22 | 經驗諮詢閘門——W13 知識晶體 Schema 新增 Procedure 結晶類型（4 個選填欄位，ALTER TABLE 向後相容）；DW2 skill_usage_log.jsonl 從 Dead Write 升級為正常配對（新增 outcome 欄位） |
| v1.26 | 2026-03-22 | Knowledge Lattice 持久層遷移：crystals.json + links.json + cuid_counter.json + archive.json → crystal.db（SQLite WAL 模式，crystals/links/cuid_counters 三表）；新增 `agent/crystal_store.py` CrystalStore 類別（singleton factory `get_crystal_store()`）；Engine 1 SQLite 引擎表新增 CrystalDB 條目；W13 知識晶體引擎從 JSON+Vector 改為 SQLite(WAL)+Vector；Phase 3 Store 表 LatticeStore 引擎從 JSON 改為 SQLite(WAL) via CrystalStore；拓撲對應表新增 crystal-store 節點；Pipeline R Memory Reset C1 從 crystals.json 改為 crystal.db 三表 DELETE；Nightly WAL checkpoint DB 數量 4→5；舊 JSON 檔案已歸檔為 .bak |
| v1.25 | 2026-03-21 | 授權系統升級：新增 W37-W38 配對——W37 動態授權清單（PairingManager 寫入、TelegramAdapter+museon_auth_status 讀取，JSON 永久+可選 TTL）、W38 分級授權策略（AuthorizationPolicy 寫入、SecurityGate+museon_auth_status 讀取）；新增 `~/.museon/auth/` Runtime 子目錄（allowlist.json + policy.json，原子寫入 tmp→rename）；同步 system-topology v1.30、blast-radius v1.35、joint-map v1.28 |
| v1.24 | 2026-03-21 | Skill 向量索引：VectorBridge.index_all_skills() 全量寫入 skills collection（Gateway 啟動 + Nightly Step 8.6 + /api/vector/reindex）；修正 skills 寫入者從 skill_router 為 vector_bridge |
| v1.23 | 2026-03-21 | 群組 chat_scope 隔離：W10 六層記憶新增 chat_scope/group_id 欄位 + scope 標籤自動注入；recall 三路徑（向量+TF-IDF+keyword）均支援 chat_scope_filter/exclude_scopes 過濾；_vector_index metadata 注入 chat_scope；外部使用者 ANIMA v3.0 schema（profile/relationship/seven_layers + trust_evolution + v2→v3 自動遷移） |
| v1.22 | 2026-03-20 | 混合檢索（Hybrid Retrieval）：Qdrant Engine 2 新增 Sparse Collections 分區（`{name}_sparse`，BM25 稀疏向量，Route A 分離式零遷移設計）；新增 `data/_system/sparse_idf.json`（SparseEmbedder IDF 表持久化）；VectorBridge 新增 `hybrid_search()` / `index_sparse()` / `backfill_sparse()` / `build_sparse_idf()`；hybrid_search 降級策略：IDF 未建 → 純 dense |
| v1.21 | 2026-03-20 | 衰減生命週期補全：新增「衰減與優先級模型」章節——四大衰減引擎（結晶 RI λ=0.03、記憶 TTL 離散分級、健康分數半衰期 2h、推薦近因性 7d）的公式/閾值/觸發時機/引擎間關係圖/參數速查表；同步 system-topology v1.22（新增 decay 連線類型）、blast-radius v1.28（新增 G8 衰減組）、joint-map v1.22（crystals.json 補衰減策略） |
| v1.20 | 2026-03-20 | P3 前置交織融合：無新增持久層（_p3_pre_fusion_ctx 為 in-memory 注入，不落地） | joint-map v1.21 |
| v1.19 | 2026-03-20 | P0-P3 思維引擎升級（純 Skill .md 認知行為變更）：無新增持久層寫入/消費配對，無新增儲存引擎條目。版本同步 system-topology v1.19、blast-radius v1.25、joint-map v1.20 |
| v1.18 | 2026-03-19 | P1-P3 藍圖同步：新增 W36 baihe_cache.json 配對（Brain Step 3.65 原子寫入、ProactiveBridge 讀取，TTL 2h）；補入 _system/baihe_cache.json 子目錄條目；同步 blast-radius/joint-map 已有的 baihe_cache 記錄 |
| v1.17 | 2026-03-17 | 軍師架構 Phase 0：`_system/` 子目錄新增 lord_profile.json 條目（brain.py `_observe_lord()` 寫入、persona_router.py 讀取）；JSON 格式：6 領域 × 4 欄位 + domain_keywords + advise_cooldown；原子寫入（tmp→rename） |
| v1.16 | 2026-03-17 | WorkflowEngine DataContract 接入：WorkflowEngine 實作 DataContract（store_spec+health_check）；Nightly _auto_register_known_stores 新增 workflow_state_db 自動註冊；新增 cleanup_old_executions() 清理已歸檔工作流的過期 executions（90 天） |
| v1.56 | 2026-04-05 | Phase 2+3 FV 藍圖同步：新增 `_system/morphenix/processed_notes.json`（morphenix_executor `_action_crystallize_notes()` 寫入，JSON 陣列 note_id strings，已處理清單去重）；新增 `_system/footprints/crystal_observations.jsonl`（exploration_bridge.py 寫入，JSONL，探索結晶觀察日誌，append-only）；`crystal_rules.json` 新增寫入者 morphenix_executor（_action_crystallize_notes，100 條上限淘汰最舊 crystallized_note）。同步 joint-map v1.72、memory-router v1.29 |
| v1.15 | 2026-03-17 | 認知可觀測性：新增 W35 cognitive_trace.jsonl（FootprintStore.trace_cognitive() 寫入、SystemAudit Skill Doctor + Observatory 讀取）；管線 D 新增 Footprint→cognitive_trace.jsonl 資料流；FootprintStore DataContract 描述更新（actions+decisions+evolutions+cognitive_trace 四檔）；`_system/footprints/` 子目錄新增 cognitive_trace.jsonl 條目 |
| v1.14 | 2026-03-16 | Memory Reset 一鍵重置管線：新增 Pipeline R（25 個持久層的原子重置管線）；涵蓋 7 大類（A.身份 B.對話 C.知識 D.行為 E.評估 F.日誌 G.狀態）；`doctor/memory_reset.py` 為唯一執行入口；預設 dry-run 安全模式 |
| v1.12 | 2026-03-16 | P0 記憶事實覆寫：新增管線 A-2（事實更正覆寫管線）；Qdrant memories 新增 status=deprecated 軟刪除標記（VectorBridge.mark_deprecated() 寫入、search() 自動過濾）；新增 data/anima/fact_corrections.jsonl（Brain 寫入、ProactiveBridge+PulseEngine+Brain 讀取）；MemoryManager.supersede() 已存在但現在被 Brain 自動呼叫 |
| v1.11 | 2026-03-16 | Phase 4 飛輪多代理實質化：W10 六層記憶條目新增 dept_id 欄位；memory_manager store()+recall() 支援部門級隔離；MultiAgentExecutor/ResponseSynthesizer/FlywheelCoordinator 均無新增持久化 |
| v1.10 | 2026-03-16 | Phase 3 日記+群組ANIMA：SoulRingStore→DiaryStore 重命名（W14 更新）；ANIMA_USER 新增 L8_context_behavior_notes 層（群組行為追蹤）；diary entries 新增 entry_type/highlights/learnings/tomorrow_intent 欄位；nightly _step_diary_generation 每日生成日記摘要 |
| v1.9 | 2026-03-16 | Phase 2 八原語接線：Qdrant Engine 2 新增 primals collection（1024 維，PrimalDetector 寫入+搜尋）；新增 W34 配對（八原語向量索引） |
| v1.8 | 2026-03-16 | Docker 沙盒驗證器上線：morphenix_validator 使用暫時性 tempdir（非持久儲存），Docker volume 為唯讀掛載，無新增持久資料 |
| v1.7 | 2026-03-15 | DNA27 深度修復：PULSE.md 寫入加入 threading.Lock + 原子寫入（tmp→rename+fsync）、ANIMA_MC.json 改為 AnimaMCStore 統一存取 |
| v1.6 | 2026-03-15 | 9.5 精度修復：新增管線 H(Installer)、拓撲對應表同步（3 個 SQLite 子節點已在 topology v1.4 上圖） |
| v1.5 | 2026-03-15 | 全面覆蓋修復：新增管線 G(Federation)、W31-W33 配對、修正 outward 歸屬（proactive_bridge→outward_trigger）、新增 marketplace+budget 子目錄 |
| v1.4 | 2026-03-15 | 藍圖完整性修復：新增管線 E(Evolution) + F(Guardian)、W24-W30 配對、9 個 _system 子目錄條目 |
| v1.3 | 2026-03-15 | Phase 4 完成：DataWatchdog 監控 + Nightly Step 29 + Dead Write 偵測 + 空間預警 |
