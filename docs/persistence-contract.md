# MUSEON Persistence Contract v1.38 — 水電圖

> **本文件是 MUSEON 資料持久層的唯一真相來源。**
> 所有資料的寫入、消費、生命週期、格式、儲存位置，以此文件為準。
> 與 `system-topology.md`（控制流拓撲）互補——那是「神經圖」，這是「水電圖」。
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
| **PulseDB** | `data/pulse/pulse.db` | `pulse/pulse_db.py` | 排程、探索、ANIMA、演化、承諾、後設認知、推送日誌(push_log) | Yes |
| **GroupContextDB** | `data/_system/group_context.db`（v1.34 修正；另有 `_system/sessions/group_context.db` 副本待清理） | `governance/group_context.py` | 多租戶對話上下文（群組+DM+bot 回覆，v1.35 擴展） | Yes |
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
| `dna27` | 1024 | `vector_bridge.py` | `reflex_router.py` | `reflex_router.py` |
| `crystals` | 1024 | `vector_bridge.py` | `knowledge_lattice.py` | `knowledge_lattice.py`, `brain.py` |
| `workflows` | 1024 | `vector_bridge.py` | `workflow_engine.py` | `workflow_engine.py` |
| `documents` | 1024 | `vector_bridge.py` | `mcp_connector.py` | `vector_bridge.query_points()` |
| `references` | 1024 | `vector_bridge.py` | `zotero_bridge.py` | `zotero_bridge.py` |
| `primals` | 1024 | `vector_bridge.py` | `primal_detector.py` | `primal_detector.py` |

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
| W13 | 知識晶體 | KnowledgeLattice (via CrystalStore) | KnowledgeLattice, Brain | SQLite(WAL)+Vector, 含 Procedure 結晶 (skills_used/preconditions/known_failures/last_success) | 永久 | OK |
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
                              reflex_router (讀取記憶)

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
| `ANIMA_USER.json` | `brain.py` | 使用者 ANIMA 狀態 | R/W |
| `ceremony_state.json` | `onboarding/ceremony.py` | 初始化儀式狀態 | R/W |
| `tasks.json` | `pulse/pulse_engine.py` | 任務清單快照 | R/W |

### `_system/` 子目錄

| 路徑 | 負責模組 | 用途 |
|------|---------|------|
| `_system/budget/usage_{month}.json` | `llm/budget.py` | 月度 Token 用量 |
| `_system/chromosome_index.json` | `memory/chromosome_index.py` | 染色體索引 |
| `_system/curiosity/question_queue.json` | `pulse/curiosity_router.py` | 好奇心佇列 |
| `_system/evolution/version.json` | `evolution/wee_engine.py` | 系統版本追蹤 |
| `_system/footprints/actions.jsonl` | `governance/footprint.py` | L1 足跡 |
| `_system/footprints/cognitive_trace.jsonl` | `governance/footprint.py` | 認知追蹤（Brain Step 8 決策迴圈的認知軌跡） |
| `_system/morphenix/*.json` | `nightly/morphenix_executor.py` | 執行快照 |
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
| v1.0 | 2026-03-15 | 初版：完整水電圖，涵蓋 23 個正常配對、3 個 Dead Write、14 個死目錄 |
| v1.1 | 2026-03-15 | Phase 2 完成：4 個 JSON 遷移至 PulseDB（ceremony_state + eval 三件套） |
| v1.2 | 2026-03-15 | Phase 3 完成：DataContract + DataBus 建立，10 個 Store 類統一接入 |
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
