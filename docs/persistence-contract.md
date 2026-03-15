# MUSEON Persistence Contract v1.7 — 水電圖

> **本文件是 MUSEON 資料持久層的唯一真相來源。**
> 所有資料的寫入、消費、生命週期、格式、儲存位置，以此文件為準。
> 與 `system-topology.md`（控制流拓撲）互補——那是「神經圖」，這是「水電圖」。

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
| **PulseDB** | `data/pulse/pulse.db` | `pulse/pulse_db.py` | 排程、探索、ANIMA、演化、承諾、後設認知 | Yes |
| **GroupContextDB** | `data/_system/state/group_context.db` | `governance/group_context.py` | 多租戶群組上下文 | Yes |
| **WorkflowStateDB** | `data/_system/wee/workflow_state.db` | `evolution/wee_engine.py` | 工作流演化狀態 | Yes |
| **RegistryDB** | `data/registry/registry.db` | `tools/tool_registry.py` | 使用者註冊、工具清單 | Yes |

**共用規範**：
- 所有 SQLite 必須開啟 WAL 模式（`PRAGMA journal_mode=WAL`）
- busy_timeout = 60000ms
- 透過 singleton factory 取得連線（`get_pulse_db()` 模式）
- 定期 WAL checkpoint（Nightly Step 28 — 待實作）

### Engine 2: Qdrant — 語義向量索引

| Collection | 維度 | 負責模組 | 寫入者 | 搜尋者 |
|-----------|------|---------|--------|--------|
| `memories` | 1024 | `vector_bridge.py` | `memory_manager.py` | `memory_manager.py`, `brain.py` |
| `skills` | 1024 | `vector_bridge.py` | `skill_router.py` | `skill_router.py`, `brain.py` |
| `dna27` | 1024 | `vector_bridge.py` | `reflex_router.py` | `reflex_router.py` |
| `crystals` | 1024 | `vector_bridge.py` | `knowledge_lattice.py` | `knowledge_lattice.py`, `brain.py` |
| `workflows` | 1024 | `vector_bridge.py` | `workflow_engine.py` | `workflow_engine.py` |
| `documents` | 1024 | `vector_bridge.py` | `mcp_connector.py` | `vector_bridge.query_points()` |
| `references` | 1024 | `vector_bridge.py` | `zotero_bridge.py` | `zotero_bridge.py` |

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
| `data/SOUL.md` | `agent/soul_ring.py` | `SoulRing` | `brain.py` |
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
│  (pulse_db.py)   │     12 tables
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
    └──→ incidents table ──→ SelfDiagnosis, Doctor
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

### 管線 G：Federation 聯邦管線

```
SkillMarket / FederationSync
    │
    ├──→ SkillMarket ──→ data/_system/marketplace/registry.json  [JSON]
    │                 ──→ data/_system/marketplace/installs.json  [JSON]
    │                 ──→ data/_system/marketplace/packages/*.mskill  [ZIP]
    └──→ FederationSync ──→ GitHub Private Repo (museon-federation/)  [Git]
```

### 管線 H：Installer 部署管線

```
Installer 編排 (orchestrator.py)
    │
    ├──→ DaemonConfigurator ──→ /Library/LaunchAgents/com.museon.gateway.plist  [plist]
    ├──→ ApiKeyConfigurator ──→ ${MUSEON_HOME}/.env  [dotenv]
    ├──→ InstallerPackager  ──→ ${OUTPUT_DIR}/*.command  [self-extracting archive]
    └──→ 目錄建立          ──→ ${MUSEON_HOME}/logs/  [目錄結構]
```

> **注意**：Installer 不讀寫任何 SQLite DB 或 JSONL 日誌。產出物為部署配置（plist, .env），屬於「基礎設施」而非「資料層」。

### 管線 D：審計與足跡管線

```
每次操作
    │
    ├──→ ActivityLogger ──→ data/activity_log.jsonl  [JSONL]
    ├──→ Footprint ──→ data/_system/footprints/actions.jsonl  [JSONL]
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
| W13 | 知識晶體 | KnowledgeLattice | KnowledgeLattice, Brain | JSON+Vector | 永久 | OK |
| W14 | 靈魂年輪 | SoulRing | Brain, Nightly | JSON | 永久 | OK |
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

### Dead Write（寫入無消費者）

| ID | 資料 | 寫入者 | 路徑 | 建議處理 |
|----|------|--------|------|---------|
| DW1 | Telegram 群組日誌 | telegram.py | `data/channels/telegram/{date}.jsonl` | 確認是否需要分析功能，否則移除寫入 |
| DW2 | 技能使用日誌 | Brain | `data/skill_usage_log.jsonl` | EvalEngine 有讀取邏輯但未啟用，需接通 |
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
| **PERMANENT** | 永久 | L3-L5 記憶, 靈魂年輪, ANIMA, 知識晶體 | 不清理 |
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
| `_system/morphenix/*.json` | `nightly/morphenix_executor.py` | 執行快照 |
| `_system/outward/*.json` | `evolution/outward_trigger.py` | 外向演化狀態（behavior_shift, cooldown, counter, pending_signals 等） |
| `_system/sessions/*.json` | `gateway/session.py` | 會話快照 |
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
| `_system/budget/usage_{month}.json` | `llm/budget.py` | 月度 Token 用量 |

### `anima/` 子目錄

| 檔案 | 負責模組 | 用途 |
|------|---------|------|
| `anima/drift_baseline.json` | `agent/drift_detector.py` | 漂移基線 |
| `anima/soul_rings.json` | `agent/soul_ring.py` | 靈魂年輪序列 |

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
- [ ] Nightly Step 28: SQLite WAL checkpoint（所有 4 個 DB）
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
| LatticeStore | JSON | PERMANENT | `agent/knowledge_lattice.py` |
| SoulRingStore | JSON (append-only) | PERMANENT | `agent/soul_ring.py` |
| WorkflowStore | Mixed (MD+JSON) | PERMANENT | `workflow/soft_workflow.py` |
| FootprintStore | JSONL (append-only) | MEDIUM | `governance/footprint.py` |
| GroupContextStore | SQLite | PERMANENT | `governance/group_context.py` |
| SkillManager | JSON | PERMANENT | `core/skill_manager.py` |
| ActivityLogger | JSONL (append-only) | SHORT | `core/activity_logger.py` |
| EvalStore | Mixed (JSONL+PulseDB) | LONG | `agent/eval_engine.py` |

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

---

## 與系統拓撲的對應

`system-topology.md` 中的 `data` 群組需擴展：

| 拓撲節點 | 對應引擎 | 狀態 |
|---------|---------|------|
| `memory` | Markdown + JSON | ✅ 已存在 |
| `vector-index` | Qdrant | ✅ 已存在 |
| `registry` | RegistryDB SQLite | ✅ 已存在（v1.4 更名） |
| `pulse-db` | PulseDB SQLite (15 表) | ✅ v1.4 新增 |
| `group-context-db` | GroupContextDB SQLite | ✅ v1.4 新增 |
| `workflow-state-db` | WorkflowStateDB SQLite | ✅ v1.4 新增 |
| `wee` | 演化引擎 | ✅ 已存在 |
| `skills-registry` | Markdown | ✅ 已存在 |
| `skill-synapse` | JSON | ⚠️ 待確認是否已退役 |

---

## 版本紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.0 | 2026-03-15 | 初版：完整水電圖，涵蓋 23 個正常配對、3 個 Dead Write、14 個死目錄 |
| v1.1 | 2026-03-15 | Phase 2 完成：4 個 JSON 遷移至 PulseDB（ceremony_state + eval 三件套） |
| v1.2 | 2026-03-15 | Phase 3 完成：DataContract + DataBus 建立，10 個 Store 類統一接入 |
| v1.7 | 2026-03-15 | DNA27 深度修復：PULSE.md 寫入加入 threading.Lock + 原子寫入（tmp→rename+fsync）、ANIMA_MC.json 改為 AnimaMCStore 統一存取 |
| v1.6 | 2026-03-15 | 9.5 精度修復：新增管線 H(Installer)、拓撲對應表同步（3 個 SQLite 子節點已在 topology v1.4 上圖） |
| v1.5 | 2026-03-15 | 全面覆蓋修復：新增管線 G(Federation)、W31-W33 配對、修正 outward 歸屬（proactive_bridge→outward_trigger）、新增 marketplace+budget 子目錄 |
| v1.4 | 2026-03-15 | 藍圖完整性修復：新增管線 E(Evolution) + F(Guardian)、W24-W30 配對、9 個 _system 子目錄條目 |
| v1.3 | 2026-03-15 | Phase 4 完成：DataWatchdog 監控 + Nightly Step 29 + Dead Write 偵測 + 空間預警 |
