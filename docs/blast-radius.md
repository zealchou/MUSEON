# Blast Radius — 模組影響半徑表 v1.0

> **用途**：修改任何模組前，查閱此表確認「改了會影響誰、觸發什麼連鎖反應」。
> **比喻**：施工影響範圍圖——在哪裡動工、要封哪些路、通知哪些住戶。
> **更新時機**：改變模組的 import 關係或共享狀態存取時，必須在同一個 commit 中同步更新此文件。
> **建立日期**：2026-03-15（DSE 第二輪排查後建立）
> **搭配**：`docs/joint-map.md`（接頭圖）提供共享狀態細節

---

## 快速索引 — 修改安全分級

| 級別 | 定義 | 模組數 | 施工規則 |
|------|------|--------|---------|
| 🔴 **禁區** | 扇入 ≥ 40，修改影響全系統 | 1 | 除非系統級重構計畫，**禁止修改** |
| 🟠 **紅區** | 扇入 10-39，修改影響多個子系統 | 5 | 必須回報使用者 + 全量 pytest + 影響分析 |
| 🟡 **黃區** | 扇入 2-9，修改影響 2+ 模組 | 60 | 查 blast-radius + joint-map，跑相關測試 |
| 🟢 **綠區** | 扇入 0-1，修改不影響上游 | 114 | 可直接修改，跑單元測試即可 |

---

## 🔴 禁區模組（1 個）

### core/event_bus.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 117（33% 的模組直接依賴它） |
| **角色** | 全域事件匯流排，定義 215 個事件常量 |
| **共享狀態** | 無直接檔案讀寫，但事件流是隱性共享狀態 |

#### 影響半徑

| 影響類型 | 數量 | 說明 |
|---------|------|------|
| 直接 import | 43 個模組 | agent(6), channels(6), nightly(6), pulse(5), governance(4), 其他(16) |
| 間接影響 | 全系統 | 事件常量或 API 改動 → 所有訂閱/發布模組失效 |
| 事件發布者 | 47 個模組 | 發布 59 種事件 |
| 事件訂閱者 | 16 個模組 | 訂閱 31 種事件 |

#### 安全操作 vs 危險操作

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增事件常量（不影響現有） | 修改/刪除事件常量名稱 |
| 新增 `on()`/`emit()` 方法的 optional 參數 | 修改 `emit()` 或 `on()` 的簽名 |
| 新增文件/註釋 | 修改事件分發邏輯 |
| — | 修改 EventBus 初始化邏輯 |

#### 事件健康度

```
已定義事件：215 | 實際發布：59 | 有訂閱者：31 | 孤兒事件：38 | 幽靈訂閱：3
事件健康度 ≈ 52.5%（47% 信號被忽視）
```

---

## 🟠 紅區模組（5 個）

### gateway/server.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 0（入口點，無人 import） |
| **扇出** | 50+（import 50+ 模組） |
| **行數** | 5749 行（上帝物件） |
| **角色** | FastAPI 閘道器，管理 30+ app.state |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀寫 | ANIMA_MC.json(RW), ANIMA_USER.json(R), nightly_report.json(R), PulseDB(R) |
| 事件訂閱 | 5 個：BRAIN_RESPONSE_COMPLETE, EXPLORATION_CRYSTALLIZED, EXPLORATION_INSIGHT, NIGHTLY_COMPLETED, RELATIONSHIP_SIGNAL |
| 直接影響 | 所有 API 端點、WebSocket 連線、前端 Electron |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增獨立 API 端點 | 修改 `app.state` 的共享變數 |
| 修改 API 回應格式（不影響前端時） | 修改 `_build_system_prompt()` |
| 新增中間件（不影響既有路由） | 修改 `lifespan()` 初始化順序 |
| 修改日誌格式 | 修改 ANIMA_MC.json 的讀寫邏輯 |

---

### gateway/message.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 20 |
| **角色** | 訊息格式定義（Message, ChatMessage 等資料類別） |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 直接 import | 20 個模組（agent, channels, gateway, tools） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增 optional 欄位 | 修改/刪除既有 Message 欄位 |
| 新增新的 Message 子類 | 修改序列化/反序列化邏輯 |

---

### tools/tool_registry.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 18 |
| **角色** | 工具註冊與管理中心 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 直接 import | 18 個模組（所有 tool 模組 + agent/skill_router） |
| 事件發布 | TOOL_DEGRADED, TOOL_HEALTH_CHANGED, TOOL_RECOVERED |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增工具類型 | 修改 `register()` / `get()` API |
| 新增狀態監控欄位 | 修改工具生命週期管理 |

---

### core/data_bus.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 13 |
| **角色** | 資料層路由器 + DataContract 協議 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 直接 import | 13 個模組：agent(3), core(3), nightly(2), 其他(5) |
| 共享狀態 | DataContract 規範所有 Store 的讀寫格式 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增 Store 類型 | 修改 DataContract 介面 |
| 新增查詢方法 | 修改 `get_store()` / `register_store()` |
| 新增監控指標 | 修改 Store spec 格式 |

---

### pulse/pulse_db.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 14 |
| **角色** | VITA 生命力引擎的 SQLite 後端（14 張表） |
| **共享狀態** | PulseDB (pulse.db) — 詳見 joint-map #8 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 直接 import | 14 個模組（brain, nightly_pipeline, eval_engine, 等） |
| 資料依賴 | 11 個模組讀取其表 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增表 | 修改既有表的 schema |
| 新增查詢方法 | 修改 `get_pulse_db()` 單例邏輯 |
| 新增索引 | 修改 WAL/busy_timeout 設定 |
| — | 修改 threading.Lock 策略 |

---

## 🟠 紅區模組（續）

### agent/brain.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 3（server, mcp_server, __init__） |
| **扇出** | 28+（import 28 個模組，初始化全系統） |
| **角色** | 系統核心——LLM 對話、記憶、自我觀察、所有子系統初始化 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀寫 | ANIMA_MC.json(RW), ANIMA_USER.json(RW), PULSE.md(R), PulseDB(R), Qdrant(W), soul_rings(R), synapses(R) |
| 子系統初始化 | 28 個模組在 Brain.__init__() 中初始化 |
| System Prompt | `_build_soul_context()` + `_build_system_prompt()` 決定 AI 所有行為 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改 `_chat()` 的回應後處理 | 修改 `__init__()` 的初始化順序 |
| 新增獨立觀察方法 | 修改 `_build_soul_context()` |
| 修改日誌格式 | 修改 `_save_anima_mc()` / `_load_anima_mc()` |
| — | 修改 `_anima_mc_lock` 鎖策略 |
| — | 新增/修改 system prompt 注入來源 |

#### ⚠️ 必須同時檢查的模組組

修改 brain.py 時，必須檢查 **G1（ANIMA 數值）+ G3（記憶管線）**（見 joint-map）

---

### agent/dispatch.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 11 |
| **角色** | 訊息分發路由器 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 直接 import | 11 個模組 |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增路由規則 | 修改分發邏輯的優先級 |
| 新增分發目標 | 修改 dispatch 介面 |

---

## 🟡 黃區重點模組

> 以下列出扇入 2-9 且觸及共享狀態的重要模組。完整 60 個黃區模組不逐一列出。

### pulse/pulse_engine.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 4 |
| **角色** | VITA 生命脈搏引擎——探索、反思、PULSE.md 寫入 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態寫入 | PULSE.md（7 種寫入方法）、question_queue.json(R) |
| 事件發布 | EXPLORATION_CRYSTALLIZED, EXPLORATION_INSIGHT, PROACTIVE_MESSAGE, PULSE_EXPLORATION_DONE |
| 下游影響 | brain.py（透過 PULSE.md → system prompt）、exploration_bridge、curiosity_router |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改反思文字生成邏輯 | 修改 PULSE.md 的 section header |
| 新增統計指標 | 修改探索佇列的格式 |
| — | 修改 `_seed_followup_topics()` |
| — | 修改 `_write_reflection_to_pulse()` 的保留策略 |

---

### pulse/anima_mc_store.py ★ NEW

| 屬性 | 值 |
|------|-----|
| **扇入** | 4（brain, anima_tracker, micro_pulse, server） |
| **角色** | ANIMA_MC.json 統一存取層（合約 1） |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態 | ANIMA_MC.json — **所有讀寫的唯一入口** |
| 上游依賴 | brain.py, anima_tracker.py, micro_pulse.py, server.py |
| 鎖機制 | ✅ `threading.Lock` + KernelGuard + 原子寫入（三重保護） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增健康檢查指標 | 修改 Lock 策略 |
| 新增 update 便利方法 | 修改 KernelGuard 整合邏輯 |
| 修改日誌格式 | 修改原子寫入機制 |

#### 必須同時檢查：**G1（ANIMA 數值組）**

---

### pulse/anima_tracker.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 3 |
| **角色** | 八元素能量追蹤 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態 | ANIMA_MC.json — `eight_primal_energies` 區段 |
| 下游 | brain.py, soul_ring.py, periodic_cycles.py |
| 鎖風險 | ✅ 已修復：經由 AnimaMCStore 統一鎖保護（合約 1） |

#### 必須同時檢查：**G1（ANIMA 數值組）**

---

### nightly/nightly_pipeline.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2 |
| **角色** | 夜間整合管線（45 步驟，~22 步實際執行） |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態讀寫 | question_queue(RW), scout_queue(R), nightly_report(W), PulseDB(RW), crystals(R), accuracy_stats(R) |
| 事件發布 | 6 個：NIGHTLY_COMPLETED, IMMUNE_MEMORY_LEARNED, MORPHENIX_PROPOSAL_CREATED, SOUL_IDENTITY_TAMPERED, SYNAPSE_PRELOAD, TRIGGER_FIRED, TOOL_MUSCLE_DORMANT |
| 子步驟呼叫 | curiosity_router, exploration_bridge, skill_forge_scout, crystal_actuator, parameter_tuner, morphenix_validator, morphenix_executor, evolution_velocity, periodic_cycles |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改步驟的日誌輸出 | 修改步驟執行順序 |
| 新增獨立步驟（不影響既有） | 修改 question_queue 的讀寫邏輯 |
| 修改報告格式 | 修改 `_step_curiosity_scan()` 的問句過濾 |

---

### vector/vector_bridge.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 6 |
| **角色** | Qdrant 向量庫的統一存取層 |

#### 影響半徑

| 影響類型 | 範圍 |
|---------|------|
| 共享狀態 | Qdrant 7 個 collections |
| 直接 import | 6 個模組（brain, memory_manager, reflex_router, skill_router, knowledge_lattice, chromosome_index） |
| 降級影響 | Qdrant 離線 → 檢索能力降級為 TF-IDF（0.3 折扣） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 新增 collection | 修改 embedding 維度或模型 |
| 新增查詢參數 | 修改 graceful degradation 邏輯 |
| — | 修改 collection schema |

---

### nightly/curiosity_router.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2 |
| **共享狀態** | question_queue.json(RW) |
| **必須同時檢查** | **G2（探索結晶管線）** |

---

### nightly/exploration_bridge.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 2 |
| **共享狀態** | scout_queue/pending.json(W) |
| **事件訂閱** | EXPLORATION_CRYSTALLIZED, EXPLORATION_INSIGHT, NIGHTLY_COMPLETED, SCOUT_DRAFT_READY |
| **必須同時檢查** | **G2（探索結晶管線）** |

---

### governance/governor.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 3 |
| **角色** | 治理層中樞——事件訂閱與決策 |
| **事件訂閱** | AUDIT_COMPLETED, MORPHENIX_AUTO_APPROVED, SOUL_IDENTITY_TAMPERED |

---

### core/module_registry.py

| 屬性 | 值 |
|------|-----|
| **扇入** | 4 |
| **角色** | 模組三層信任等級管理（CORE / OPTIONAL / EDGE） |

#### 修改安全邊界

| ✅ 安全 | ❌ 危險 |
|---------|---------|
| 修改模組的信任等級分類 | 修改 `register()` / `get()` API |
| 新增信任等級 | 修改信任等級的行為邏輯 |

---

## 🟢 綠區安全模組（42 個葉子模組）

> 以下模組無人 import（扇入 = 0），修改不影響任何上游，可直接修改。

### Agent 層（8 個）
`agent/dna27.py`, `agent/drift_detector.py`, `agent/intuition.py`, `agent/kernel_guard.py`, `agent/plan_engine.py`, `agent/routing_bridge.py`, `agent/safety_anchor.py`, `agent/sub_agent.py`

### Gateway 層（3 個）
`gateway/cron.py`, `gateway/security.py`, `gateway/session.py`

### Installer 層
`installer/` 下大部分模組

### LLM 層
`llm/` 下大部分模組

### 其他
各子系統的終端執行模組（無人 import 的工具、通道適配器等）

> **注意**：「無人 import」不代表「不重要」——許多是入口點（cron, server）或由 __init__.py re-export。
> 修改前仍需檢查 joint-map 確認是否觸及共享狀態。

---

## 事件影響半徑

### 高影響事件（訂閱者 ≥ 2）

| 事件 | 發布者 | 訂閱者 | 修改影響 |
|------|--------|--------|---------|
| `EXPLORATION_CRYSTALLIZED` | pulse_engine | server, exploration_bridge | 探索結果雙向傳播 |
| `EXPLORATION_INSIGHT` | pulse_engine | server, exploration_bridge | 探索洞見雙向傳播 |
| `NIGHTLY_COMPLETED` | nightly_pipeline | server, exploration_bridge | 凌晨管線完成同步點 |
| `MORPHENIX_EXECUTION_COMPLETED` | morphenix_executor | skill_router, telegram | 演化執行完成廣播 |
| `SKILL_QUALITY_SCORED` | eval_engine, wee_engine | dendritic_scorer, outward_trigger | 技能評分（多源雙消） |

### 孤兒事件（只發不收）：38 個

> 這些事件被發布但無人訂閱——修改/刪除它們是安全的。

**關鍵孤兒**（可能是設計遺漏）：
- `DNA27_WEIGHTS_UPDATED` — 演化權重變化無人監聽
- `CRYSTAL_CREATED` — 知識結晶無人應用
- `SOUL_RING_DEPOSITED` — 靈魂環存入無人確認
- `MEMORY_PROMOTED` / `MEMORY_RECALLED` — 記憶事件無人監聽
- `AUTONOMIC_REPAIR` — 自主修復無人知曉

### 幽靈訂閱（只收不發）：3 個

| 事件 | 訂閱者 | 狀態 |
|------|--------|------|
| `PULSE_RHYTHM_CHECK` | telegram | ❌ 無發布者 → Telegram 永遠收不到 |
| `PULSE_NIGHTLY_DONE` | telegram | ❌ 無發布者 → Telegram 永遠收不到 |
| `NIGHTLY_COMPLETED` | server, exploration_bridge | ✅ 實際存在（nightly_pipeline 用 `_publish()` 包裝） |

---

## 必須同時修改的模組組（交叉引用 joint-map）

| 組 ID | 觸發條件 | 必須一起改的模組 | 共享的狀態 |
|-------|---------|----------------|-----------|
| **G1** | 改 ANIMA 數值邏輯 | anima_tracker + brain + server + micro_pulse + kernel_guard | ANIMA_MC.json |
| **G2** | 改探索/好奇心邏輯 | pulse_engine + curiosity_router + exploration_bridge + nightly_pipeline + skill_forge_scout | question_queue.json + scout_queue/pending.json + PULSE.md |
| **G3** | 改記憶存取 | memory_manager + brain + vector_bridge + reflex_router | MemoryStore + Qdrant |
| **G4** | 改演化速度計算 | evolution_velocity + parameter_tuner + periodic_cycles + metacognition | accuracy_stats.json + tuned_parameters.json |
| **G5** | 改知識晶格 | knowledge_lattice + crystal_actuator + recommender | crystals.json |
| **G6** | 改免疫系統 | immunity + immune_memory + immune_research + daemon | events.jsonl + immune_memory.json |

---

## 修改決策流程圖

```
要修改模組 X
    │
    ├─ 查扇入（本表）→ 扇入 = 0？
    │       ├─ 是 → 🟢 查 joint-map 確認無共享狀態 → 直接修改
    │       └─ 否 → 繼續 ↓
    │
    ├─ 扇入 ≥ 10？
    │       ├─ 是 → 🟠 必須回報使用者 + 完整影響分析
    │       └─ 否 → 🟡 查 joint-map + 跑相關測試
    │
    ├─ 查模組組（G1-G6）→ 屬於任一組？
    │       ├─ 是 → 必須同時檢查同組所有模組
    │       └─ 否 → 正常流程
    │
    ├─ 查事件影響 → 修改的事件有多個訂閱者？
    │       ├─ 是 → 通知所有訂閱模組的維護者
    │       └─ 否 → 正常流程
    │
    └─ 動手修改 → 跑 pytest → 更新本表（如果改了 import）→ 更新 joint-map（如果改了共享狀態）
```

---

## 系統健康度快照（2026-03-15）

| 指標 | 數值 | 說明 |
|------|------|------|
| 總模組數 | 176 | 含所有 .py（不含 __init__.py） |
| Hub 模組（扇入 ≥ 10） | 6 | event_bus(117), message(20), tool_registry(18), pulse_db(14), data_bus(13), dispatch(11) |
| 中間模組（扇入 2-9） | 60 | — |
| 單引用模組（扇入 1） | 72 | — |
| 葉子模組（扇入 0） | 42 | 可安全修改 |
| 共享可變狀態 | 16 個 | 詳見 joint-map.md |
| 事件健康度 | 52.5% | 47% 信號被忽視 |
| 致命單點 | event_bus | 佔全系統 33% 依賴 |

---

## 變更日誌

| 日期 | 版本 | 變更 |
|------|------|------|
| 2026-03-15 | v1.1 | 合約 1：新增 AnimaMCStore 模組，anima_tracker 鎖風險標記為已修復 |
| 2026-03-15 | v1.0 | 初始建立，176 模組分析，6 Hub + 42 葉子，38 孤兒事件 |
