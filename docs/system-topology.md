# MUSEON 系統拓撲圖 v1.47

> 本文件是 MUSEON 所有子系統及其關聯性的 **唯一真相來源（Single Source of Truth）**。
> 新增模組、Debug、審計時必須參照此文件，確保不遺漏依賴關係。
> **v1.47 (2026-03-24)**：跨群組洩漏防禦——gov 群組新增 `response-guard` 節點（ResponseGuard 發送前 chat_id 二次驗證閘門，`governance/response_guard.py`）；新增 3 條連線（governance→response-guard internal、gateway→response-guard cross 發送前驗證、brain→response-guard cross 註冊 origin_chat_id）；194 節點 481 連線
> **v1.46 (2026-03-23)**：推送品質修復——pulse 群組新增 `push-budget` 節點（PushBudget 全局推送預算管理器）；新增 3 條 internal 連線（push-budget→pulse-db、pulse-engine→push-budget、proactive-bridge→push-budget）；193 節點 478 連線
> **v1.45 (2026-03-23)**：Project Epigenesis（DNA 式記憶系統重構）——agent 群組新增 4 個節點（epigenetic-router 表觀遺傳路由器、memory-reflector 反思引擎、proactive-predictor 需求預判、adaptive-decay ACT-R 衰減）；pulse 群組新增 1 個節點（anima-changelog 差分追蹤）；新增 12 條 cross 連線；VectorBridge 新增 soul_rings collection（第 9 個）；192 節點 475 連線
> **v1.44 (2026-03-23)**：三層調度員架構（腦手分離）——agent 群組新增 3 個節點（`dispatcher` L1 調度員、`thinker` L2 思考者、`worker` L3 工人）；新增 7 條 internal 連線；CLAUDE.md 改寫為 L1 調度員模式；新增 `data/_system/museon-persona.md` 人格隨身檔供 L2 載入；187 節點 463 連線
> **v1.43 (2026-03-23)**：全系統拓撲審計——補齊 70 條遺漏 cross 連線（🔴7 結構斷裂 + 🟠20 重要遺漏 + 🟡43 文件欠債）；移除 2 條幽靈連線（drift-detector→memory、zotero-bridge→vector-index）；修正 1 條方向反轉（federation-sync→nightly 改為 nightly→federation-sync）；拓撲覆蓋率 62.8% → 100%；184 節點 456 連線
> **v1.42 (2026-03-22)**：Sparse Embedder 全面啟動——sparse-embedder 節點升級為已啟動狀態；新增 skill-router→sparse-embedder、memory→sparse-embedder 跨系統連線（hybrid_search 消費者接線）；Nightly Pipeline 新增 Step 8.7（IDF 重建 + 回填）；184 節點 389 連線
> **v1.41 (2026-03-22)**：Brain Prompt Builder 健康檢查——補齊 3 條遺漏連線（brain-prompt-builder→anima-mc-store/data-bus/anthropic-api）；常數化 20+ 個魔術值；Token zone 耗盡 warning 日誌；budget.remaining() None 防禦；新增單元測試；184 節點 387 連線
> **v1.40 (2026-03-22)**：Brain Tools 健康檢查——補齊 2 條遺漏連線（brain-tools→anthropic-api LLM 呼叫、brain-tools→data-bus session/JSONL 持久化）；常數化 8 個魔術值；Nightly Step 27 擴充按日期 JSONL 清理；新增 16 個 brain_tools 單元測試；184 節點 384 連線
> **v1.39 (2026-03-22)**：使用者 ↔ ANIMA 連線補齊——新增 3 條 cross 連線：zeal→anima-mc-store（Owner 互動觸發 ANIMA_MC 更新）、verified-user→anima-mc-store（配對使用者 L1-L8 觀察）、external-user→anima-mc-store（外部使用者觀察）；auth 持久化修復（PairingManager/AuthorizationPolicy 首次 load 時自動初始化空檔案）；184 節點 382 連線
> **v1.38 (2026-03-22)**：L3-A2 Brain Mixin 拆分——brain 節點拆分為 core + 5 Mixin 子模組 + brain_types 共享型別；agent 群組新增 `brain-prompt-builder`、`brain-dispatch`、`brain-observation`、`brain-p3-fusion`、`brain-tools`、`brain-types` 6 個節點 + 6 條 internal 連線；184 節點 379 連線
> **v1.37 (2026-03-22)**：Brain 三層治療——agent 群組新增 `chat-context`（ChatContext dataclass，r=0.7）、`deterministic-router`（確定性任務分解器，r=1.0）2 個節點；新增 2 條 internal 連線（brain→chat-context、brain→deterministic-router）；178 節點 373 連線
> **v1.36 (2026-03-22)**：使用者節點精細化——channel 群組 `user` 拆分為 `zeal`（CORE 主人）、`verified-user`（VERIFIED 動態配對）、`external-user`（EXTERNAL 群組外部成員）三節點；補上遺漏的 `discord` 節點；新增/更新 8 條 flow 連線反映實際使用者分流；175 節點 369 連線
> **v1.35 (2026-03-22)**：P0-P3 升級——Evolution Hub 新增 2 個 Skill 節點（system-health-check、decision-tracker）；新增 5 條跨群組連線（report-forge→knowledge-lattice、system-health-check→knowledge-lattice/morphenix、decision-tracker→knowledge-lattice/user-model）；173 節點 361 連線
> **v1.34 (2026-03-22)**：經驗諮詢閘門——新增 1 條 cross 連線 `brain → data-bus`（經驗回放搜尋 activity_log.search()）；171 節點 351 連線
> **v1.33 (2026-03-22)**：InteractionRequest 跨通道互動層——channel 群組新增 `line` 節點（LINE 通道適配器）；gateway 群組新增 `interaction-queue` 節點（InteractionQueue 非阻塞等待佇列）；新增 8 條連線（interaction-queue ↔ telegram/discord/line/gateway）；171 節點 358 連線
> **v1.32 (2026-03-22)**：Recommender 激活修復——`recommender` 節點半徑 0.7→0.9（從幽靈模組升級為實際接線）；新增 cross 連線 `recommender → crystal-store`（經由 CrystalStore API 讀取結晶+連結）；brain.py `_recommender` 初始化接線確認；169 節點 350 連線
> **v1.31 (2026-03-22)**：Knowledge Lattice 持久層遷移——data 群組新增 `crystal-store` 節點（CrystalStore SQLite WAL 統一存取層）+ 7 條連線
> **v1.30 (2026-03-21)**：授權系統升級——gov 群組新增 `authorization` 節點（配對碼+工具授權+分級策略）+ 5 條連線；持久化 `~/.museon/auth/`
> **v1.29 (2026-03-21)**：Skills 群組治理升級——新增 `hub` 欄位（9 種 Hub 分組）+ Workflow Stage 規格；詳見 `docs/skill-routing-governance.md`
> **v1.28 (2026-03-21)**：補全 skills 群組——7 Hub + 39 Skill 節點 + 91 條連線（從 3D 心智圖回補，修復拓撲⇄HTML 漂移）
> **v1.27 (2026-03-21)**：Skill 鍛造膠合層修復——VectorBridge 新增 index_all_skills()；Nightly Step 8.6 skill_vector_reindex；plugin-registry v2.3（+12 Skill 註冊）
> **v1.26 (2026-03-21)**：群組對話 DSE 三階段修復——brain.py P0 六類訊號分流 + 事實糾正偵測 + _observe_external_user v3.0；memory_manager chat_scope 隔離；multi_tenant ExternalAnimaManager v3.0；server.py 群組事實糾正+錯誤顯示啟用
> **v1.25 (2026-03-21)**：新增 deep-think、roundtable、investment-masters 拓撲節點 + 10 條連線
> **v1.24 (2026-03-21)**：A 區迭代 #1~#3 拓撲同步——MemGPT recall_tiered、Hybrid Retrieval sparse-embedder、GraphRAG 社群摘要 Layer 2.5
> **v1.23 (2026-03-20)**：補記 recommender 節點（知識推薦引擎）+ 3D 心智圖全面同步修復
> **v1.22 (2026-03-20)**：P3 前置交織融合——Step 5.5 前置多視角收集 + system_prompt 注入

---

## 使用方式

| 場景 | 如何使用 |
|------|---------|
| **新增模組** | 在 `nodes` 新增條目 → 在 `links` 定義所有輸入/輸出 → 跑驗證清單 |
| **Debug** | 找到問題節點 → 查上游（輸入）和下游（輸出）→ 逐一排查 |
| **審計** | `system_audit` 載入此文件 → 檢查孤立節點、缺失連線、循環依賴 |
| **迭代** | 修改前查影響範圍（所有相關 links）→ 修改後驗證無回歸 |

---

## 群組定義

| 群組 ID | 名稱 | 職責 | 色碼 |
|---------|------|------|------|
| `center` | 核心 | 事件匯流排，全系統通訊樞紐 | `#C4502A` |
| `channel` | 通道入口 | 使用者訊息收發、WebSocket、排程 | `#C4502A` |
| `agent` | Agent / Brain | 主判斷中樞、技能路由、元認知 | `#2A7A6E` |
| `pulse` | Pulse 生命力 | 自主探索、推播、心跳、承諾追蹤 | `#B8923A` |
| `gov` | Governance | 三焦治理、免疫、護欄、沙盒 | `#2A6A8A` |
| `doctor` | Doctor 診斷 | 系統審計、自我診斷、自動修復 | `#2D8A6E` |
| `llm` | LLM 路由 | 模型選擇、預算、速限、快取 | `#5A5A6E` |
| `data` | 資料持久層 | 記憶、向量索引、技能庫、SQLite | `#7A7888` |
| `evolution` | Evolution 演化 | 外向演化、意圖雷達、研究消化、參數調諧 | `#6B3FA0` |
| `tools` | Tools 工具 | 工具註冊、探測、排程、聯邦市場 | `#8A6A3E` |
| `nightly` | Nightly 夜間 | 30+ 步夜間整合管線、演化提案、好奇心路由 | `#9A3A1C` |
| `installer` | Installer 安裝 | 部署編排、Daemon 設定、Electron 打包 | `#5A8A3E` |
| `external` | 外部服務 | SearXNG、Qdrant、Firecrawl、API | `#6A6880` |
| `skills` | Skills 生態系 | 外掛 Skill 語義群組（7 子中樞 + 41 Skill）；治理規格見 `skill-routing-governance.md` | `#8B5CF6` |

---

## 節點清單（Nodes）

### center — 核心
| ID | 名稱 | 中文 | Hub | 半徑 |
|----|------|------|-----|------|
| `event-bus` | Event Bus | 核心事件匯流排 | Yes | 3.2 |

### channel — 通道入口

> **使用者分層模型（v1.36）**：程式碼層已實作 TrustLevel 四層（CORE/VERIFIED/EXTERNAL/UNTRUSTED）、
> 私聊 vs 群組分流（session_id 格式 `telegram_{id}` vs `telegram_group_{id}`）、
> ExternalAnimaManager（外部使用者記憶 `data/_system/external_users/{uid}.json`）、
> SensitivityChecker + EscalationQueue（敏感問題升級到 owner 私聊確認）。
> 拓撲節點按信任層級拆分，反映訊息在 `gateway/server.py` message pump 中的實際路由決策。

| ID | 名稱 | 中文 | 信任層級 | Hub | 半徑 |
|----|------|------|---------|-----|------|
| `zeal` | Zeal (Owner) | 主人 | CORE | - | 2.0 |
| `verified-user` | Verified User | 動態配對使用者 | VERIFIED | - | 1.2 |
| `external-user` | External User | 群組外部成員 | EXTERNAL | - | 1.4 |
| `telegram` | Telegram | 主通道（私聊 + 群組） | - | - | 1.6 |
| `gateway` | Gateway | WebSocket :8765 | - | - | 1.6 |
| `line` | LINE | LINE@ 通道（私聊 + 群組 + Room） | - | - | 1.4 |
| `discord` | Discord | Discord 通道 | - | - | 1.2 |
| `cron` | Cron | 排程入口 | - | - | 1.2 |
| `mcp-server` | MCP Server | Claude Code 介面 | - | - | 1.2 |
| `interaction-queue` | Interaction Queue | 跨通道互動佇列 | - | - | 1.0 |

#### 使用者信任層級與訊息路由

```
zeal（CORE）
  ├─ 私聊 → telegram/line → gateway → brain.process() 直接處理
  ├─ 群組 @mention → telegram/line → gateway → 注入群組上下文 + 標記「老闆」
  └─ EscalationQueue 回覆 → 確認/拒絕外部使用者的敏感問題

verified-user（VERIFIED，經 PairingManager 動態配對）
  └─ 私聊 → telegram → gateway → brain.process()（信任等級略低於 CORE）

external-user（EXTERNAL）
  ├─ 群組 @mention → telegram/line → gateway → SensitivityChecker 分級
  │    ├─ 非敏感 → ExternalAnimaManager.update() + brain 處理
  │    └─ 敏感（L1/L2/L3）→ EscalationQueue → 等待 zeal 私聊確認
  └─ 群組非 @mention → 只記錄到 GroupContextDB + JSONL log，不進入 brain
```

### agent — Agent / Brain
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `brain` | Agent / Brain | 主判斷中樞（core: init + process pipeline, 2575 行） | Yes | - | 2.8 |
| `brain-prompt-builder` | Brain Prompt Builder | Mixin: system prompt 建構（1668 行） | - | brain | 1.0 |
| `brain-dispatch` | Brain Dispatch | Mixin: 任務分派（1082 行） | - | brain | 1.0 |
| `brain-observation` | Brain Observation | Mixin: 觀察與演化（2003 行） | - | brain | 1.0 |
| `brain-p3-fusion` | Brain P3 Fusion | Mixin: P3 融合與決策層（948 行） | - | brain | 1.0 |
| `brain-tools` | Brain Tools | Mixin: LLM 呼叫與 session 管理（966 行） | - | brain | 1.0 |
| `brain-types` | Brain Types | 共享 dataclass: DecisionSignal, P3FusionSignal | - | brain | 0.7 |
| `dna27` | DNA27 | 27 反射叢集 | - | brain | 1.0 |
| `skill-router` | Skill Router | 技能路由 | - | brain | 1.1 |
| `reflex-router` | Reflex Router | 反射路由 | - | brain | 1.0 |
| `dispatch` | Dispatch | 多技能編排 | - | brain | 1.0 |
| `knowledge-lattice` | Knowledge Lattice | 知識晶格 | - | brain | 1.1 |
| `plan-engine` | Plan Engine | 六階段計畫 | - | brain | 1.0 |
| `metacognition` | Metacognition | 元認知審查 | - | brain | 1.0 |
| `intuition` | Intuition | 五層直覺 | - | brain | 0.9 |
| `eval-engine` | Eval Engine | Q-Score | - | brain | 1.0 |
| `diary-store` | Diary Store | 日記存儲（原靈魂年輪） | - | brain | 0.9 |
| `onboarding` | Onboarding | 上線儀式 | - | brain | 0.9 |
| `multiagent` | Multiagent | 多代理協調 | - | brain | 0.9 |
| `multi-agent-executor` | Multi Agent Executor | 並行 LLM 執行器 | - | brain | 1.0 |
| `response-synthesizer` | Response Synthesizer | DNA 交叉重組合成 | - | brain | 0.8 |
| `flywheel-coordinator` | Flywheel Coordinator | 飛輪流動協調 | - | brain | 0.9 |
| `primal-detector` | Primal Detector | 八原語偵測 | - | brain | 1.0 |
| `persona-router` | Persona Router | 人格路由 + 百合引擎決策 | - | brain | 1.1 |
| `deep-think` | Deep Think | 思考前置引擎（P0 訊號分流 / P1 輸入審視 / P2 決策偵測） | - | brain | 1.1 |
| `roundtable` | Roundtable | 圓桌詰問引擎（多角色交叉詰問 + 仲裁） | - | brain | 1.0 |
| `investment-masters` | Investment Masters | 投資軍師團（六位大師模型會診） | - | brain | 0.9 |
| `drift-detector` | Drift Detector | 漂移偵測 | - | brain | 0.8 |
| `okr-router` | OKR Router | 八卦路由 | - | brain | 0.9 |
| `fact-correction` | Fact Correction | 事實覆寫引擎 | - | brain | 0.9 |
| `dendritic-fusion` | Dendritic Fusion | P3 並行融合引擎（MetaCog+Eval+Health） | - | brain | 1.1 |
| `chat-context` | Chat Context | ChatContext dataclass（輕量對話上下文資料結構） | - | brain | 0.7 |
| `deterministic-router` | Deterministic Router | 確定性任務分解器（取代 LLM Orchestrator） | - | brain | 1.0 |
| `recommender` | Recommender | 知識推薦引擎（CrystalStore 結晶推薦） | - | brain | 0.9 |
| `dispatcher` | L1 Dispatcher | 調度員：收訊 → 1 秒內 spawn L2 思考者 → 處理下一則（CLAUDE.md 定義行為） | - | brain | 1.2 |
| `thinker` | L2 Thinker | 思考者 subagent：讀 museon-persona.md → 分析決策 → spawn L3 工人（model: sonnet, run_in_background） | - | brain | 1.0 |
| `worker` | L3 Worker | 工人 subagent：執行 MCP 工具呼叫後銷毀（model: haiku, run_in_background） | - | brain | 0.8 |
| `epigenetic-router` | Epigenetic Router | 表觀遺傳路由器（MAGMA 式多圖遍歷 semantic/temporal/causal/entity） | - | brain | 1.1 |
| `memory-reflector` | Memory Reflector | Hindsight 式反思引擎（矛盾偵測/模式發現/時間軸/Activation 排序） | - | brain | 1.0 |
| `proactive-predictor` | Proactive Predictor | 需求預判引擎（Skill 序列/情緒/決策循環 四維預測） | - | brain | 1.0 |
| `adaptive-decay` | Adaptive Decay | ACT-R 式統一衰減引擎（B_i = ln(Σt^{-d}) + β_i） | - | brain | 0.8 |

### pulse — Pulse 生命力
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `pulse` | Pulse Engine | VITA 生命力 | Yes | - | 2.8 |
| `heartbeat` | Heartbeat | 三脈主控 | - | pulse | 1.0 |
| `explorer` | Explorer | 自主探索 | - | pulse | 1.1 |
| `silent-digestion` | Silent Digestion | 靜默消化 | - | pulse | 1.0 |
| `proactive-bridge` | Proactive Bridge | 主動推播 + 百合引擎象限調適 | - | pulse | 1.2 |
| `push-budget` | Push Budget | 全局推送預算管理器（限額+語意去重+持久化） | - | pulse | 1.0 |
| `micro-pulse` | Micro Pulse | 秒級微脈 | - | pulse | 0.8 |
| `pulse-db` | Pulse DB | 脈搏資料庫 | - | pulse | 0.8 |
| `commitment-tracker` | Commitment | 承諾追蹤 | - | pulse | 0.9 |
| `anima-mc-store` | AnimaMC Store | ANIMA統一存取 | - | pulse | 1.1 |
| `anima-tracker` | Anima Tracker | 八元素追蹤 | - | pulse | 1.0 |
| `group-session-proactive` | Group Session Proactive | 群組後主動追問 | - | pulse | 0.9 |
| `anima-changelog` | Anima Changelog | ANIMA_USER 差分版本追蹤（append-only JSONL） | - | pulse | 0.8 |

### gov — Governance
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `governance` | Governance | 三焦式治理 | Yes | - | 2.8 |
| `governor` | Governor | 上中下焦 | - | governance | 1.0 |
| `immunity` | Immunity | 先天 + 後天免疫 | - | governance | 1.1 |
| `preflight` | Preflight | 啟動門 | - | governance | 0.9 |
| `refractory` | Refractory | 斷路器（三態+半開試探） | - | governance | 0.9 |
| `skill-scanner` | Skill Scanner | 技能掃描 | - | governance | 0.8 |
| `sandbox` | Sandbox | 沙盒隔離 | - | governance | 0.8 |
| `telegram-guard` | TG Guard | Polling 守衛 | - | governance | 0.8 |
| `service-health` | Service Health | 服務監控 | - | governance | 1.0 |
| `guardian` | Guardian | 系統守護 Daemon | - | governance | 1.1 |
| `security` | Security | 安全淨化與稽核 | - | governance | 1.0 |
| `dendritic-scorer` | Dendritic Scorer | 樹突評分器 | - | governance | 0.9 |
| `footprint` | Footprint | 操作足跡追蹤 | - | governance | 0.9 |
| `perception` | Perception | 四診合參感知 | - | governance | 0.9 |
| `cognitive-receipt` | Cognitive Receipt | 認知收據格式定義 | - | governance | 0.7 |
| `authorization` | Authorization | 配對碼 + 工具授權 + 分級策略 | - | governance | 1.0 |
| `response-guard` | Response Guard | 發送前 chat_id 二次驗證閘門 | - | governance | 0.9 |

### doctor — Doctor 診斷
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `doctor` | Doctor | 自我診斷修復 | Yes | - | 2.8 |
| `system-audit` | System Audit | 7 層 46 項 | - | doctor | 1.1 |
| `health-check` | Health Check | 12 項基礎 | - | doctor | 0.9 |
| `self-diagnosis` | Self Diagnosis | 診斷管線 | - | doctor | 0.9 |
| `auto-repair` | Auto Repair | 自動修復 | - | doctor | 1.0 |
| `surgery` | Surgery | 精準手術 | - | doctor | 0.8 |
| `log-analyzer` | Log Analyzer | 日誌分析 | - | doctor | 0.8 |
| `code-analyzer` | Code Analyzer | 代碼品質 | - | doctor | 0.8 |
| `memory-reset` | Memory Reset | 一鍵記憶重置 | - | doctor | 0.8 |
| `observatory` | Observatory | 認知可觀測性儀表板 | - | doctor | 0.8 |

### llm — LLM 路由
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `llm-router` | LLM Router | 智能模型選擇 | Yes | - | 2.2 |
| `budget-mgr` | Budget Mgr | Token 預算 | - | llm-router | 1.0 |
| `rate-limit` | Rate Limit | 速限守衛 | - | llm-router | 0.8 |
| `llm-cache` | Cache | LRU 快取 | - | llm-router | 0.8 |

### data — 資料持久層
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `data-bus` | DataBus | 資料層路由器 | Yes | - | 1.8 |
| `crystal-store` | CrystalStore | 知識晶體 SQLite (WAL) | - | data-bus | 1.0 |
| `data-watchdog` | DataWatchdog | 資料層監控 | - | data-bus | 1.0 |
| `memory` | Memory | 六層記憶 | - | data-bus | 1.6 |
| `vector-index` | Vector Index | Qdrant 語義 | - | data-bus | 1.5 |
| `pulse-db` | PulseDB | 生命力 SQLite (15 表) | - | data-bus | 1.4 |
| `group-context-db` | GroupContextDB | 群組上下文 SQLite | - | data-bus | 1.0 |
| `workflow-state-db` | WorkflowStateDB | 工作流 SQLite | - | data-bus | 1.0 |
| `wee` | WEE | 演化引擎 | - | data-bus | 1.2 |
| `skills-registry` | Skills Registry | 技能資料庫 | - | data-bus | 1.2 |
| `registry` | Registry | RegistryDB SQLite | - | data-bus | 1.0 |
| `skill-synapse` | Skill Synapse | 突觸網路 | - | data-bus | 0.9 |
| `blueprint-reader` | Blueprint Reader | 藍圖解析器 | - | data-bus | 0.9 |
| `lord-profile` | Lord Profile | 主人領域畫像 | - | data-bus | 0.8 |
| `sparse-embedder` | Sparse Embedder | BM25 稀疏向量（已啟動） | - | data-bus | 0.9 |

### evolution — Evolution 演化
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `evolution` | Evolution | 演化系統 | Yes | - | 2.2 |
| `outward-trigger` | Outward Trigger | 外向演化觸發 | - | evolution | 1.1 |
| `intention-radar` | Intention Radar | 意圖雷達 | - | evolution | 1.0 |
| `digest-engine` | Digest Engine | 消化結晶引擎 | - | evolution | 1.0 |
| `research-engine` | Research Engine | 外部研究引擎 | - | evolution | 1.1 |
| `evolution-velocity` | Evolution Velocity | 演化速度測量 | - | evolution | 1.0 |
| `feedback-loop` | Feedback Loop | 使用者回饋迴路 | - | evolution | 0.9 |
| `parameter-tuner` | Parameter Tuner | 參數自動調諧 | - | evolution | 0.9 |
| `tool-muscle` | Tool Muscle | 工具肌肉記憶 | - | evolution | 0.8 |
| `trigger-weights` | Trigger Weights | 觸發器權重 | - | evolution | 0.8 |

### tools — Tools 工具套件
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `tool-registry` | Tool Registry | 工具註冊中心 | Yes | - | 1.8 |
| `tool-discovery` | Tool Discovery | 工具自動探測 | - | tool-registry | 1.0 |
| `dify-scheduler` | Dify Scheduler | Dify 排程器 | - | tool-registry | 0.8 |
| `image-gen` | Image Gen | 圖像生成 | - | tool-registry | 0.8 |
| `rss-aggregator` | RSS Aggregator | RSS 聚合器 | - | tool-registry | 0.8 |
| `voice-clone` | Voice Clone | 語音克隆 | - | tool-registry | 0.7 |
| `zotero-bridge` | Zotero Bridge | 文獻管理橋接 | - | tool-registry | 0.8 |
| `mcp-dify` | MCP Dify | MCP-Dify 連接器 | - | tool-registry | 0.7 |
| `skill-market` | Skill Market | 技能交易市場 | - | tool-registry | 1.0 |
| `federation-sync` | Federation Sync | 母子體同步 | - | tool-registry | 0.9 |

### nightly — Nightly 夜間
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `nightly` | Nightly Pipeline | 30+ 步夜間整合 | Yes | - | 2.2 |
| `morphenix` | Morphenix | 演化提案 | - | nightly | 1.0 |
| `curiosity-router` | Curiosity Router | 好奇心路由 | - | nightly | 0.9 |
| `exploration-bridge` | Exploration Bridge | 探索橋接 | - | nightly | 0.9 |
| `skill-forge-scout` | Skill Forge Scout | 技能鍛造偵察 | - | nightly | 0.8 |
| `crystal-actuator` | Crystal Actuator | 結晶致動器 | - | nightly | 0.8 |
| `periodic-cycles` | Periodic Cycles | 週期循環 | - | nightly | 0.9 |
| `morphenix-validator` | Morphenix Validator | Docker 沙盒驗證 | - | nightly | 0.7 |

### installer — Installer 安裝
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `installer` | Installer | 安裝編排器 | Yes | - | 1.6 |
| `installer-daemon` | Daemon Config | Daemon 設定 | - | installer | 0.8 |
| `installer-electron` | Electron Packager | Electron 打包 | - | installer | 0.8 |
| `installer-env` | Environment | 環境檢查 | - | installer | 0.7 |
| `installer-verifier` | Module Verifier | 模組驗證 | - | installer | 0.7 |

### external — 外部服務
| ID | 名稱 | 中文 | Hub | 半徑 |
|----|------|------|-----|------|
| `searxng` | SearXNG | 搜尋 :8888 | - | 1.0 |
| `qdrant` | Qdrant | 向量 DB :6333 | - | 1.0 |
| `firecrawl` | Firecrawl | 爬取 :3002 | - | 0.8 |
| `anthropic-api` | Anthropic API | Claude API | - | 1.1 |

### skills — Skills 生態系

> **治理文件**：`docs/skill-routing-governance.md`（Hub 路由 + Always-on 中間件 + Workflow Stage 規格）
> **Manifest 規格**：`docs/skill-manifest-spec.md`（YAML frontmatter 欄位定義 + 驗證規則）

#### skills-thinking — 思維類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-thinking-hub` | Thinking Hub | 思維類技能中樞 | Yes | - | 2.0 |
| `dharma` | DHARMA | 思維轉化引擎 | - | skills-thinking-hub | 1.2 |
| `philo-dialectic` | Philo-Dialectic | 哲學思辨引擎 | - | skills-thinking-hub | 1.2 |
| `resonance` | Resonance | 感性共振引擎 | - | skills-thinking-hub | 1.2 |
| `shadow` | Shadow | 人際博弈辨識引擎 | - | skills-thinking-hub | 1.2 |
| `meta-learning` | Meta-Learning | 元學習引擎 | - | skills-thinking-hub | 1.2 |
| `query-clarity` | Query-Clarity | 問題品質守門層 | - | skills-thinking-hub | 1.2 |
| `user-model` | User-Model | 使用者畫像引擎 | - | skills-thinking-hub | 1.2 |

#### skills-market — 市場類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-market-hub` | Market Hub | 市場類技能中樞 | Yes | - | 2.0 |
| `market-core` | Market-Core | 市場分析核心 | - | skills-market-hub | 1.4 |
| `market-equity` | Market-Equity | 股票分析衛星 | - | skills-market-hub | 1.2 |
| `market-crypto` | Market-Crypto | 加密貨幣分析 | - | skills-market-hub | 1.2 |
| `market-macro` | Market-Macro | 總體經濟分析 | - | skills-market-hub | 1.2 |
| `risk-matrix` | Risk-Matrix | 風險管理引擎 | - | skills-market-hub | 1.2 |
| `sentiment-radar` | Sentiment-Radar | 市場情緒雷達 | - | skills-market-hub | 1.2 |

#### skills-business — 商業類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-business-hub` | Business Hub | 商業類技能中樞 | Yes | - | 2.0 |
| `business-12` | Business-12 | 商模十二力 | - | skills-business-hub | 1.2 |
| `ssa-consultant` | SSA-Consultant | 顧問式銷售引擎 | - | skills-business-hub | 1.2 |
| `master-strategy` | Master-Strategy | 戰略判斷引擎 | - | skills-business-hub | 1.4 |
| `consultant-communication` | Consultant-Comm | 顧問溝通引擎 | - | skills-business-hub | 1.2 |
| `xmodel` | X-Model | 破框解方引擎 | - | skills-business-hub | 1.2 |
| `pdeif` | PDEIF | 逆熵流引擎 | - | skills-business-hub | 1.2 |

#### skills-creative — 創意類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-creative-hub` | Creative Hub | 創意類技能中樞 | Yes | - | 2.0 |
| `c15` | C15 | 敘事張力語言層 | - | skills-creative-hub | 1.2 |
| `text-alchemy` | Text-Alchemy | 文字煉金系統 | - | skills-creative-hub | 1.2 |
| `storytelling-engine` | Storytelling | 說故事引擎 | - | skills-creative-hub | 1.2 |
| `novel-craft` | Novel-Craft | 小說工藝引擎 | - | skills-creative-hub | 1.2 |
| `aesthetic-sense` | Aesthetic-Sense | 美感引擎 | - | skills-creative-hub | 1.2 |
| `brand-identity` | Brand-Identity | 品牌識別引擎 | - | skills-creative-hub | 1.2 |

#### skills-product — 產品類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-product-hub` | Product Hub | 產品類技能中樞 | Yes | - | 2.0 |
| `acsf` | ACSF | 能力結晶鑄造 | - | skills-product-hub | 1.2 |
| `dse` | DSE | 技術融合驗證 | - | skills-product-hub | 1.2 |
| `gap` | GAP | 缺口分析引擎 | - | skills-product-hub | 1.2 |
| `env-radar` | Env-Radar | 環境雷達 | - | skills-product-hub | 1.2 |
| `info-architect` | Info-Architect | 資訊架構引擎 | - | skills-product-hub | 1.2 |
| `report-forge` | Report-Forge | 報告鍛造 | - | skills-product-hub | 1.2 |
| `orchestrator` | Orchestrator | 編排引擎 | - | skills-product-hub | 1.2 |

#### skills-evolution — 演化類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-evolution-hub` | Evolution Hub | 演化類技能中樞 | Yes | - | 2.0 |
| `sandbox-lab` | Sandbox-Lab | 沙盒實驗室 | - | skills-evolution-hub | 1.2 |
| `qa-auditor` | QA-Auditor | 品質審計引擎 | - | skills-evolution-hub | 1.2 |
| `tantra` | Tantra | 情慾治理引擎 | - | skills-evolution-hub | 1.0 |
| `system-health-check` | System-Health-Check | 系統健康自檢引擎 | - | skills-evolution-hub | 1.0 |
| `decision-tracker` | Decision-Tracker | 決策歷史追蹤引擎 | - | skills-evolution-hub | 1.0 |

#### skills-workflow — 工作流類
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `skills-workflow-hub` | Workflow Hub | 工作流類技能中樞 | Yes | - | 2.0 |
| `workflow-svc-brand-marketing` | WF-SVC-01 | 品牌行銷工作流 | - | skills-workflow-hub | 1.2 |
| `workflow-investment-analysis` | WF-INV-01 | 投資分析工作流 | - | skills-workflow-hub | 1.2 |
| `workflow-ai-deployment` | WF-AID-01 | AI部署工作流 | - | skills-workflow-hub | 1.2 |
| `group-meeting-notes` | WF-GMN-01 | 會議記錄引擎 | - | skills-workflow-hub | 1.2 |

---

## 連線清單（Links）

### 連線類型定義

| 類型 | 說明 | 色碼 |
|------|------|------|
| `flow` | 資料流（使用者指令流經的路徑） | `#E0714D` |
| `control` | 控制流（事件分派、排程觸發） | `#7A7888` |
| `internal` | 群組內部連線（Hub ↔ 子節點） | `#9898A8` |
| `cross` | 跨群組連線（系統間協作） | `#C4502A` |
| `async` | 非同步連線（推播、回饋） | `#B8923A` |
| `monitor` | 監控連線（健康檢查） | `#2A6A8A` |
| `decay` | 衰減連線（資料老化、優先級退場） | `#8B6E5A` |

### 衰減連線（decay）

> 橫切關注點：四個模組各自實作衰減邏輯，影響資料的「老化退場」。
> 詳細公式與參數見 `persistence-contract.md` §衰減與優先級模型。

| Source | Target | 說明 |
|--------|--------|------|
| `knowledge-lattice` → `crystal-actuator` | `crystal.db` (via CrystalStore) | RI 指數衰減 `exp(-0.03×days)`，RI<0.05 由 crystal-actuator 執行歸檔 |
| `memory` → `vector-index` | Qdrant memories | TTL 分級（24h/14d/90d）+ 訪問次數晉升/降級 + supersede 事實覆寫 |
| `dendritic-scorer` → `pulse-db` | health_scores 表 | 半衰期 2h 指數衰減，governor 每回合 tick() |
| `recommender` → `knowledge-lattice` | 推薦排序 | 近因性半衰期 7d + 互動衰減 λ=0.95 |
| `nightly` → `skill-synapse` | synapses.json | Synapse Decay（已有連線） |

### 主資料流（flow）
| Source | Target | 說明 |
|--------|--------|------|
| `zeal` | `telegram` | 私聊指令 + 群組 @mention（CORE trust, is_owner=True） |
| `zeal` | `line` | LINE 私聊 + 群組（CORE trust） |
| `verified-user` | `telegram` | 動態配對使用者私聊（VERIFIED trust, PairingManager） |
| `external-user` | `telegram` | 群組對話（EXTERNAL trust, SensitivityChecker 過濾） |
| `external-user` | `line` | LINE 群組對話（EXTERNAL trust） |
| `external-user` | `discord` | Discord 群組對話（EXTERNAL trust） |
| `telegram` | `gateway` | 轉發（InternalMessage + metadata: is_group, is_owner, sender_name） |
| `line` | `gateway` | webhook 轉發 |
| `discord` | `gateway` | 轉發 |
| `gateway` | `event-bus` | 路由 |
| `cron` | `event-bus` | 定時觸發 |

### 控制流（control）
| Source | Target | 說明 |
|--------|--------|------|
| `event-bus` | `brain` | 事件分派 |
| `event-bus` | `pulse` | 脈搏事件 |
| `event-bus` | `governance` | 治理事件 |
| `event-bus` | `doctor` | 診斷事件 |
| `event-bus` | `llm-router` | LLM 事件 |
| `event-bus` | `data-bus` | 資料事件 |
| `event-bus` | `evolution` | 演化事件 |
| `event-bus` | `tool-registry` | 工具事件 |
| `event-bus` | `installer` | 安裝事件 |
| `cron` | `nightly` | 03:00 觸發 |

### Agent 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `brain` | `brain-prompt-builder` | Mixin: system prompt 建構 |
| `brain-prompt-builder` | `anima-mc-store` | 讀取 ANIMA_MC（身份/能力/演化/八原語） |
| `brain-prompt-builder` | `data-bus` | 讀取 PULSE.md + fact_corrections + 記憶注入 |
| `brain-prompt-builder` | `anthropic-api` | 結晶壓縮時的 LLM 呼叫（via knowledge_lattice） |
| `brain` | `brain-dispatch` | Mixin: 任務分派 |
| `brain` | `brain-observation` | Mixin: 觀察與演化 |
| `brain` | `brain-p3-fusion` | Mixin: P3 融合與決策層 |
| `brain` | `brain-tools` | Mixin: LLM 呼叫與 session 管理 |
| `brain-tools` | `anthropic-api` | LLM 呼叫（Fallback 鏈：Opus→Sonnet→Haiku→離線） |
| `brain-tools` | `data-bus` | Session 持久化 + cache/routing/skill_usage JSONL |
| `brain` | `brain-types` | 共享型別: DecisionSignal, P3FusionSignal |
| `brain` | `dna27` | 載入反射 |
| `brain` | `skill-router` | 技能路由 |
| `brain` | `reflex-router` | 迴圈判定 |
| `brain` | `dispatch` | 多技能分派 |
| `brain` | `knowledge-lattice` | 結晶注入 |
| `brain` | `knowledge-lattice` | MemGPT 三層分級召回 recall_tiered() |
| `brain` | `knowledge-lattice` | GraphRAG 社群摘要 Layer 2.5 recall_with_community() |
| `brain` | `plan-engine` | 計畫啟動 |
| `brain` | `metacognition` | 元認知 |
| `brain` | `intuition` | 直覺感知 |
| `brain` | `eval-engine` | 品質評分 |
| `brain` | `diary-store` | 日記記錄 |
| `brain` | `onboarding` | 上線儀式 |
| `brain` | `multiagent` | 多代理協調 |
| `brain` | `multi-agent-executor` | 並行 LLM 呼叫 |
| `brain` | `response-synthesizer` | 回覆合成 |
| `brain` | `flywheel-coordinator` | 飛輪流動 |
| `brain` | `primal-detector` | 八原語偵測 |
| `brain` | `persona-router` | 人格路由 |
| `brain` | `deep-think` | 思考前置 P0/P1/P2 |
| `brain` | `roundtable` | 圓桌詰問 |
| `brain` | `investment-masters` | 軍師會診 |
| `brain` | `drift-detector` | 漂移檢查 |
| `brain` | `okr-router` | 八卦路由 |
| `brain` | `fact-correction` | 事實更正偵測+覆寫 |
| `brain` | `dendritic-fusion` | P3 前置融合（Step 5.5）+ 並行融合（Step 6.2-6.5） |
| `brain` | `recommender` | 知識推薦引擎 |
| `brain` | `chat-context` | 對話上下文封裝 |
| `brain` | `deterministic-router` | 確定性任務分解（取代 LLM Orchestrator） |
| `dendritic-fusion` | `metacognition` | 並行預認知審查 |
| `dendritic-fusion` | `eval-engine` | 並行品質評分 |
| `multi-agent-executor` | `llm-router` | 多部門 API 呼叫 |
| `dispatcher` | `thinker` | L1→L2：收訊後 spawn 思考者（run_in_background, model: sonnet） |
| `thinker` | `worker` | L2→L3：思考完成後 spawn 工人執行 MCP 工具（run_in_background, model: haiku） |
| `worker` | `telegram` | L3 透過 MCP 工具回覆 Telegram 訊息 |
| `worker` | `gmail` | L3 透過 MCP 工具收發 Email |
| `worker` | `gcal` | L3 透過 MCP 工具管理行程 |
| `thinker` | `worker` | L2→L3（前景）：需要查詢結果時同步等待 L3 回傳資料 |

### Pulse 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `pulse` | `heartbeat` | 三脈 |
| `pulse` | `explorer` | 探索 |
| `pulse` | `silent-digestion` | 消化 |
| `pulse` | `proactive-bridge` | 推播 |
| `pulse` | `micro-pulse` | 微脈 |
| `pulse` | `pulse-db` | 持久化 |
| `pulse` | `commitment-tracker` | 承諾 |
| `pulse` | `anima-mc-store` | ANIMA 統一存取 |
| `pulse` | `anima-tracker` | 八元素追蹤 |
| `anima-tracker` | `anima-mc-store` | 八元素經由 Store |
| `micro-pulse` | `anima-mc-store` | 微脈經由 Store |
| `pulse` | `group-session-proactive` | 群組追問 |
| `pulse-engine` | `push-budget` | 推送預算檢查+記錄 |
| `proactive-bridge` | `push-budget` | 推送預算檢查+記錄 |
| `push-budget` | `pulse-db` | push_log 表持久化 |

### Governance 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `governance` | `governor` | 三焦 |
| `governance` | `immunity` | 免疫 |
| `governance` | `preflight` | 啟動門 |
| `governance` | `refractory` | 斷路 |
| `governance` | `skill-scanner` | 掃描 |
| `governance` | `sandbox` | 沙盒 |
| `governance` | `telegram-guard` | 守衛 |
| `governance` | `service-health` | 監控 |
| `governance` | `guardian` | 守護 |
| `governance` | `security` | 安全 |
| `governance` | `dendritic-scorer` | 評分 |
| `governance` | `footprint` | 足跡 |
| `governance` | `perception` | 感知 |
| `governance` | `cognitive-receipt` | 認知收據 |
| `footprint` | `cognitive-receipt` | 認知追蹤格式定義 |
| `governor` | `immunity` | learn() 抗體學習 |
| `governor` | `dendritic-scorer` | immunity 未解決→健康分數 |
| `governance` | `authorization` | 授權引擎 |
| `authorization` | `security` | 三級策略查詢 |
| `governance` | `response-guard` | 發送前 chat_id 驗證閘門 |

### Evolution 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `evolution` | `outward-trigger` | 外向觸發 |
| `evolution` | `intention-radar` | 意圖偵測 |
| `evolution` | `digest-engine` | 消化結晶 |
| `evolution` | `research-engine` | 外部研究 |
| `evolution` | `evolution-velocity` | 速度測量 |
| `evolution` | `feedback-loop` | 回饋迴路 |
| `evolution` | `parameter-tuner` | 參數調諧 |
| `evolution` | `tool-muscle` | 肌肉記憶 |
| `evolution` | `trigger-weights` | 觸發權重 |

### Tools 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `tool-registry` | `tool-discovery` | 工具探測 |
| `tool-registry` | `dify-scheduler` | Dify 排程 |
| `tool-registry` | `image-gen` | 圖像生成 |
| `tool-registry` | `rss-aggregator` | RSS 聚合 |
| `tool-registry` | `voice-clone` | 語音克隆 |
| `tool-registry` | `zotero-bridge` | 文獻管理 |
| `tool-registry` | `mcp-dify` | MCP-Dify |
| `tool-registry` | `skill-market` | 技能市場 |
| `tool-registry` | `federation-sync` | 母子同步 |

### Doctor 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `doctor` | `system-audit` | 審計 |
| `doctor` | `health-check` | 檢查 |
| `doctor` | `self-diagnosis` | 診斷 |
| `doctor` | `auto-repair` | 修復 |
| `doctor` | `surgery` | 手術 |
| `doctor` | `log-analyzer` | 日誌 |
| `doctor` | `code-analyzer` | 代碼 |
| `doctor` | `memory-reset` | 重置 |
| `doctor` | `observatory` | 認知儀表板 |

### LLM 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `llm-router` | `budget-mgr` | 預算 |
| `llm-router` | `rate-limit` | 速限 |
| `llm-router` | `llm-cache` | 快取 |

### Data 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `data-bus` | `memory` | Store 路由 |
| `data-bus` | `vector-index` | Store 路由 |
| `data-bus` | `wee` | Store 路由 |
| `data-bus` | `skills-registry` | Store 路由 |
| `data-bus` | `registry` | Store 路由 |
| `data-bus` | `skill-synapse` | Store 路由 |
| `data-bus` | `blueprint-reader` | Store 路由 |
| `data-bus` | `sparse-embedder` | Store 路由 |
| `vector-index` | `sparse-embedder` | 混合檢索 BM25+Dense RRF 融合 |
| `data-bus` | `crystal-store` | Store 路由 |
| `data-bus` | `data-watchdog` | 監控注入 |
| `data-bus` | `pulse-db` | Store 路由 |
| `data-bus` | `group-context-db` | Store 路由 |
| `data-bus` | `workflow-state-db` | Store 路由 |
| `wee` | `skill-synapse` | 突觸演化 |
| `data-bus` | `lord-profile` | Store 路由 |
| `skills-registry` | `registry` | 技能資料表 |

### Nightly 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `nightly` | `morphenix` | 演化提案 |
| `nightly` | `curiosity-router` | 好奇心路由 |
| `nightly` | `exploration-bridge` | 探索橋接 |
| `nightly` | `skill-forge-scout` | 技能鍛造 |
| `nightly` | `crystal-actuator` | 結晶致動 |
| `nightly` | `periodic-cycles` | 週期循環 |
| `nightly` | `morphenix-validator` | Docker 沙盒驗證 |
| `morphenix-validator` | `morphenix` | 驗證通過→執行 |

### 跨系統連線（cross）
| Source | Target | 說明 |
|--------|--------|------|
| `primal-detector` | `vector-index` | 八原語語義匹配 |
| `primal-detector` | `skill-router` | 原語加分 |
| `primal-detector` | `reflex-router` | 原語 boost |
| `primal-detector` | `persona-router` | 原語調適 |
| `primal-detector` | `okr-router` | 原語路由 |
| `persona-router` | `proactive-bridge` | 象限決策結果回饋（P1-P3） |
| `deep-think` | `metacognition` | Phase 0 元認知觀察 |
| `deep-think` | `persona-router` | Phase 0 訊號分流→百合引擎 |
| `roundtable` | `knowledge-lattice` | 裁決軌跡結晶 |
| `investment-masters` | `knowledge-lattice` | 軍師會診結晶 |
| `investment-masters` | `skill-router` | DNA27 RC 親和觸發 |
| ~~`drift-detector`~~ | ~~`memory`~~ | ~~覺察日誌~~ ❌ **幽靈連線 v1.43 移除**：drift_detector.py 零 cross import，純 dataclass 邏輯 |
| `fact-correction` | `memory` | 記憶覆寫（supersede） |
| `fact-correction` | `vector-index` | 向量廢棄標記（mark_deprecated） |
| `fact-correction` | `llm-router` | Haiku 矛盾判斷 |
| `skill-router` | `vector-index` | 語義匹配 |
| `skill-router` | `skills-registry` | 技能查找 |
| `skill-router` | `llm-router` | API 呼叫 |
| `dispatch` | `llm-router` | API 呼叫 |
| `knowledge-lattice` | `vector-index` | 結晶存取 |
| `metacognition` | `llm-router` | Haiku 審查 |
| `eval-engine` | `memory` | 品質數據 |
| `eval-engine` | `registry` | Q-Score 存取 |
| `dendritic-fusion` | `dendritic-scorer` | P3 並行融合讀取健康分數 |
| `recommender` | `knowledge-lattice` | 近因性衰減 7d + 互動衰減 λ=0.95 |
| `recommender` | `crystal-store` | 結晶讀取（load_crystals_raw + load_links） |
| `diary-store` | `memory` | 日記寫入 |
| `brain` | `llm-router` | 生成回應 |
| `brain` | `memory` | 四通道持久化 |
| `commitment-tracker` | `brain` | 承諾自檢 |
| `commitment-tracker` | `registry` | 承諾記錄 |
| `explorer` | `searxng` | 網路搜尋 |
| `explorer` | `llm-router` | 深度分析 |
| `explorer` | `firecrawl` | 頁面爬取 |
| `silent-digestion` | `memory` | 反思寫入 |
| `skill-scanner` | `skills-registry` | 安全掃描 |
| `auto-repair` | `gateway` | 重啟修復 |
| `system-audit` | `service-health` | 交叉驗證 |
| `llm-router` | `anthropic-api` | API 呼叫 |
| `memory` | `vector-index` | 嵌入索引 |
| `memory` | `registry` | 持久化儲存 |
| `vector-index` | `qdrant` | 向量存儲（dense） |
| `sparse-embedder` | `qdrant` | 稀疏向量存儲（sparse collections） |
| `skill-router` | `sparse-embedder` | 混合檢索（hybrid_search） |
| `memory` | `sparse-embedder` | 記憶混合檢索（hybrid_search） |
| `wee` | `skills-registry` | 演化追蹤 |
| `wee` | `registry` | 演化狀態 |
| `pulse-db` | `registry` | 脈搏記錄 |
| `nightly` | `memory` | 記憶壓縮 |
| `nightly` | `skills-registry` | 品質檢查 |
| `nightly` | `wee` | 演化速度 |
| `nightly` | `knowledge-lattice` | 結晶固化 |
| `nightly` | `budget-mgr` | 預算結算 |
| `nightly` | `immunity` | 抗體修剪 |
| `nightly` | `skill-synapse` | Synapse Decay |
| `nightly` | `data-watchdog` | Step 29 健康檢查 |
| `nightly` | `blueprint-reader` | Step 30 藍圖一致性驗證 |
| `blueprint-reader` | `doctor` | 藍圖感知（系統審計） |
| `blueprint-reader` | `surgery` | 藍圖感知（精準手術） |
| `blueprint-reader` | `morphenix` | 藍圖感知（演化提案） |
| `governor` | `pulse-db` | 事件記錄 |
| `group-session-proactive` | `telegram` | 群組追問發送 |
| `data-bus` | `pulse-db` | Store 路由 |
| `data-bus` | `knowledge-lattice` | Store 路由 |
| `data-bus` | `diary-store` | Store 路由 |
| `data-bus` | `eval-engine` | Store 路由 |
| `outward-trigger` | `intention-radar` | 觸發搜尋 |
| `intention-radar` | `research-engine` | 執行研究 |
| `research-engine` | `digest-engine` | 消化結果 |
| `digest-engine` | `knowledge-lattice` | 結晶寫入 |
| `evolution-velocity` | `parameter-tuner` | 速度驅動調諧 |
| `nightly` | `evolution-velocity` | 夜間速度計算 |
| `nightly` | `diary-store` | 每日日記生成 |
| `group-session-proactive` | `event-bus` | GROUP_SESSION_END 訂閱 |
| `telegram` | `event-bus` | GROUP_SESSION_END 發布 |
| `nightly` | `parameter-tuner` | 夜間參數調諧 |
| `guardian` | `doctor` | 修復委派 |
| `guardian` | `brain` | ANIMA 修復 |
| `onboarding` | `brain` | 初始化身份 |
| `tool-registry` | `skill-router` | 工具查找 |
| `mcp-server` | `brain` | ANIMA 狀態查詢 |
| `brain` | `anima-mc-store` | ANIMA_MC 存取 |
| `gateway` | `anima-mc-store` | API 查詢 ANIMA |
| `dendritic-scorer` | `eval-engine` | 品質評分 |
| `footprint` | `data-bus` | 足跡持久化 |
| `perception` | `brain` | 四診合參 |
| `curiosity-router` | `pulse` | 探索主題 |
| `exploration-bridge` | `skill-forge-scout` | 技能線索 |
| `crystal-actuator` | `crystal-store` | 結晶降級/升級（經由 CrystalStore API） |
| `crystal-actuator` | `knowledge-lattice` | 結晶操作 |
| `knowledge-lattice` | `crystal-store` | 結晶讀寫（經由 CrystalStore API） |
| `nightly` | `crystal-store` | 結晶統計（經由 CrystalStore API） |
| `evolution-velocity` | `crystal-store` | 結晶數量統計 |
| `guardian` | `crystal-store` | 結晶健康檢查 |
| `memory-reset` | `crystal-store` | 一鍵重置（DELETE FROM 三表） |
| `periodic-cycles` | `pulse` | 週期驅動 |
| `skill-market` | `skills-registry` | 技能打包 |
| `nightly` | `federation-sync` | 夜間母子同步（v1.43 方向修正：nightly import federation.sync） |
| ~~`zotero-bridge`~~ | ~~`vector-index`~~ | ~~文獻索引~~ ❌ **幽靈連線 v1.43 移除**：zotero_bridge.py 只 import event_bus，無 vector 連線 |
| `auto-repair` | `installer` | 修復用安裝器 |
| `metacognition` | `pulse-db` | DNA 品質旗標寫入（METACOGNITION_QUALITY_FLAG） |
| `morphenix` | `pulse-db` | DNA 品質旗標讀取（品質回饋閉環） |
| `response-synthesizer` | `multi-agent-executor` | DNA 交叉重組（片段評分合成） |
| `brain` | `footprint` | Step 8 認知追蹤（trace_decision+trace_cognitive） |
| `brain` | `data-bus` | 經驗回放搜尋（activity_log.search() via ActivityLogger） |
| `authorization` | `telegram` | 配對碼推送 + 授權請求 inline keyboard |
| `authorization` | `gateway` | server.py 訊息泵授權回覆分支 |
| `authorization` | `mcp-server` | museon_auth_status 查詢 |
| `footprint` | `data-bus` | cognitive_trace.jsonl 寫入 |
| `observatory` | `footprint` | 讀取 cognitive_trace.jsonl 視覺化 |
| `observatory` | `service-health` | 讀取健康狀態 |
| `brain` | `lord-profile` | _observe_lord() 領域畫像寫入 |
| `lord-profile` | `persona-router` | 百合引擎讀取領域畫像（Phase 1） |
| `interaction-queue` | `telegram` | present_choices() InlineKeyboard 呈現 |
| `interaction-queue` | `discord` | present_choices() Button/Select 呈現 |
| `interaction-queue` | `line` | present_choices() Quick Reply/Flex 呈現 |
| `interaction-queue` | `gateway` | message pump 互動攔截 + asyncio.Event 等待 |
| `gateway` | `interaction-queue` | InteractionQueue 啟動初始化 |
| `line` | `event-bus` | LINE webhook 事件發布 |

#### v1.43 全系統拓撲審計補齊（70 條）

> **背景**：2026-03-23 全系統 import vs 拓撲交叉審計，發現拓撲覆蓋率僅 62.8%。
> 以下按嚴重度分組補齊。

##### 🔴 結構斷裂（7 條）
| Source | Target | 說明 |
|--------|--------|------|
| `gateway` | `feedback-loop` | server.py:4609 API 端點實例化 FeedbackLoop |
| `pulse` | `knowledge-lattice` | pulse_engine.py:565,:1723 探索→結晶化閉環 |
| `governance` | `heartbeat` | vital_signs.py:554 治理層讀取心跳引擎單例 |
| `immunity` | `research-engine` | immune_research.py:159 免疫研究呼叫外部研究引擎 |
| `wee` | `workflow-state-db` | wee_engine.py:23-24 頂層硬 import workflow.models + workflow_engine |
| `outward-trigger` | `research-engine` | outward_trigger.py:211 演化鏈核心環節（research 為獨立 Python 包） |
| `gateway` | `wee` | server.py:2595,:3336 直接呼叫 get_wee_engine() |

##### 🟠 重要遺漏（20 條）
| Source | Target | 說明 |
|--------|--------|------|
| `wee` | `knowledge-lattice` | wee_engine.py:658 讀取 KnowledgeLattice |
| `evolution-velocity` | `crystal-store` | evolution_velocity.py:373 跨群組讀取 |
| `perception` | `heartbeat` | perception.py:723 感知模組讀取心跳聚焦 |
| `governor` | `morphenix` | governor.py:908 治理者觸發演化執行 |
| `nightly` | `vector-index` | nightly_pipeline.py:1686,:1704 Step 8.5/8.6 向量重建 |
| `nightly` | `memory` | nightly_pipeline.py:665,:1404 ChromosomeIndex 記憶壓縮 |
| `nightly` | `research-engine` | nightly_pipeline.py:2255,:2315 夜間探索研究 |
| `morphenix` | `pulse` | morphenix_executor.py:622,:641,:677 演化執行修改 Pulse 行為 |
| `nightly` | `multiagent` | nightly_pipeline.py:459,:489 Step 3/4 共享資產 |
| `brain` | `heartbeat` | brain.py:868 log_action() 呼叫 |
| `brain` | `pulse-db` | brain.py:393 token_budget（pulse 包下） |
| `brain` | `pulse` | brain.py:361 async_write_queue |
| `gateway` | `nightly` | server.py:1163+ 呼叫 10+ 個 nightly 子模組 |
| `gateway` | `workflow-state-db` | server.py:2988-2991,:4219 WorkflowStore/Engine/Executor/Scheduler |
| `gateway` | `multiagent` | server.py:1700,:1734,:1762 department_config/shared_assets/okr_router |
| `gateway` | `skill-market` | server.py:4456,:4471,:4491 SkillMarket API |
| `gateway` | `sandbox` | server.py:2519,:2539 ExecutionSandbox |
| `gateway` | `research-engine` | server.py:5721 研究引擎觸發 |
| `brain` | `tool-muscle` | brain.py:227 ModuleSpec + L1442 record_use() |
| `brain` | `trigger-weights` | brain.py:237 ModuleSpec 觸發權重 |

##### 🟡 文件欠債（43 條）
| Source | Target | 說明 |
|--------|--------|------|
| `digest-engine` | `security` | digest_engine.py:487 輸入淨化 sanitizer |
| `nightly` | `crystal-actuator` | nightly_pipeline.py:719 Step 4 結晶降級 |
| `nightly` | `reflex-router` | nightly_pipeline.py:1673 Step 8.4 反射模式索引重建 |
| `nightly` | `footprint` | nightly_pipeline.py:2853 Step 23.5 足跡統計 |
| `nightly` | `immunity` | nightly_pipeline.py:2936 Step 24 immune_memory 學習（補充粒度） |
| `nightly` | `group-context-db` | nightly_pipeline.py:3295 Step 28 群組上下文清理 |
| `nightly` | `workflow-state-db` | nightly_pipeline.py:3306 Step 28.5 工作流清理 |
| `nightly` | `tool-registry` | nightly_pipeline.py:2623-2624 Step 22 工具探測 |
| `nightly` | `federation-sync` | nightly_pipeline.py:2751 Step 23 母子同步（v1.43 新增正向連線） |
| `nightly` | `pulse-db` | nightly_pipeline.py:1103+ 多步驟讀寫 PulseDB（5 處） |
| `nightly` | `tool-muscle` | nightly_pipeline.py:2904 Step 24 肌肉記憶追蹤 |
| `nightly` | `trigger-weights` | nightly_pipeline.py:2973 Step 25 觸發權重 |
| `morphenix` | `knowledge-lattice` | morphenix_executor.py:1357 結晶查詢 |
| `nightly` | `eval-engine` | job.py:111 NightlyJob 品質評分 |
| `periodic-cycles` | `skill-router` | periodic_cycles.py:923 週期統計 SkillLoader |
| `skill-forge-scout` | `research-engine` | skill_forge_scout.py:141 鍛造偵察研究 |
| `brain` | `doctor` | brain.py:571,:1378 self_diagnosis 觸發 |
| `brain` | `multiagent` | brain.py:344 context_switch |
| `brain` | `okr-router` | brain.py:766 OKR 路由呼叫 |
| `brain-observation` | `governance` | brain_observation.py:1072 ExternalAnimaManager |
| `brain-observation` | `vector-index` | brain_observation.py:875 向量索引存取 |
| `brain-prompt-builder` | `governance` | brain_prompt_builder.py:468 外部使用者記憶 |
| `brain-prompt-builder` | `pulse-db` | brain_prompt_builder.py:501 PulseDB 脈搏數據 |
| `brain-dispatch` | `pulse-db` | brain_dispatch.py:652 orchestrator_calls |
| `eval-engine` | `pulse-db` | eval_engine.py:463 Q-Score 存取 |
| `gateway` | `doctor` | server.py:577+ 呼叫 doctor 全部子模組（health_check/audit/repair/surgeon 等） |
| `gateway` | `tool-registry` | server.py:1780+ 呼叫 tools 群組 26 處 import |
| `gateway` | `governance` | server.py:2846,:3709,:3843 bulkhead/multi_tenant/group_context |
| `gateway` | `response-guard` | server.py 發送回覆前呼叫 ResponseGuard.validate() |
| `brain` | `response-guard` | brain.py process() 開始時 register_origin() 註冊來源 chat_id |
| `guardian` | `security` | daemon.py:566 安全審計日誌 |
| `self-diagnosis` | `tool-registry` | self_diagnosis.py:246,:484 工具狀態查詢 |
| `surgery` | `morphenix` | surgeon.py:47 morphenix_standards 引用 |
| `telegram` | `governance` | telegram.py:245,:318 群組上下文讀寫 |
| `telegram` | `multiagent` | telegram.py:444,:461,:478 飛輪部門查詢 |
| `telegram` | `pulse-db` | telegram.py:583 脈搏讀取 |
| `onboarding` | `pulse-db` | ceremony.py:16 上線儀式 PulseDB 寫入 |
| `nightly` | `sparse-embedder` | nightly_pipeline.py:3157 Step 8.7 IDF 重建 |
| `gateway` | `immunity` | server.py:3233 免疫研究初始化 |
| `brain` | `llm-router` | brain.py:319 create_adapter_sync 直接存取 |
| `brain-tools` | `llm-router` | brain_tools.py:134 APICompatResponse 型別引用 |
| `nightly` | `token-budget` | nightly_pipeline.py:2992 Step 26 預算結算（pulse 包下） |
| `gateway` | `cron` | server.py:5000+ cron 排程管理初始化 |
| `gateway` | `event-bus` | server.py:1000+ 事件訂閱註冊（5 事件） |
| `gateway` | `brain` | server.py 訊息泵→Brain.chat()（主要呼叫路徑） |

### Skills 控制連線（control）
| Source | Target | 說明 |
|--------|--------|------|
| `event-bus` | `skills-thinking-hub` | 思維技能事件 |
| `event-bus` | `skills-market-hub` | 市場技能事件 |
| `event-bus` | `skills-business-hub` | 商業技能事件 |
| `event-bus` | `skills-creative-hub` | 創意技能事件 |
| `event-bus` | `skills-product-hub` | 產品技能事件 |
| `event-bus` | `skills-evolution-hub` | 演化技能事件 |
| `event-bus` | `skills-workflow-hub` | 工作流技能事件 |

### Skills 內部連線（internal）

#### Thinking Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-thinking-hub` | `dharma` | 思維轉化 |
| `skills-thinking-hub` | `philo-dialectic` | 哲學思辨 |
| `skills-thinking-hub` | `resonance` | 感性共振 |
| `skills-thinking-hub` | `shadow` | 博弈辨識 |
| `skills-thinking-hub` | `meta-learning` | 元學習 |
| `skills-thinking-hub` | `query-clarity` | 問題品質 |
| `skills-thinking-hub` | `user-model` | 使用者畫像 |

#### Market Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-market-hub` | `market-core` | 市場核心 |
| `skills-market-hub` | `market-equity` | 股票分析 |
| `skills-market-hub` | `market-crypto` | 加密貨幣 |
| `skills-market-hub` | `market-macro` | 總體經濟 |
| `skills-market-hub` | `risk-matrix` | 風險管理 |
| `skills-market-hub` | `sentiment-radar` | 情緒雷達 |
| `market-core` | `market-equity` | 股票衛星 |
| `market-core` | `market-crypto` | 加密衛星 |
| `market-core` | `market-macro` | 總經衛星 |

#### Business Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-business-hub` | `business-12` | 商模十二力 |
| `skills-business-hub` | `ssa-consultant` | 顧問銷售 |
| `skills-business-hub` | `master-strategy` | 戰略判斷 |
| `skills-business-hub` | `consultant-communication` | 顧問溝通 |
| `skills-business-hub` | `xmodel` | 破框解方 |
| `skills-business-hub` | `pdeif` | 逆熵流 |

#### Creative Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-creative-hub` | `c15` | 敘事張力 |
| `skills-creative-hub` | `text-alchemy` | 文字煉金 |
| `skills-creative-hub` | `storytelling-engine` | 說故事 |
| `skills-creative-hub` | `novel-craft` | 小說工藝 |
| `skills-creative-hub` | `aesthetic-sense` | 美感 |
| `skills-creative-hub` | `brand-identity` | 品牌識別 |
| `text-alchemy` | `c15` | 語言層注入 |
| `text-alchemy` | `novel-craft` | 小說工藝 |
| `text-alchemy` | `storytelling-engine` | 說故事 |

#### Product Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-product-hub` | `acsf` | 能力結晶 |
| `skills-product-hub` | `dse` | 技術融合 |
| `skills-product-hub` | `gap` | 缺口分析 |
| `skills-product-hub` | `env-radar` | 環境雷達 |
| `skills-product-hub` | `info-architect` | 資訊架構 |
| `skills-product-hub` | `report-forge` | 報告鍛造 |
| `skills-product-hub` | `orchestrator` | 編排 |

#### Evolution Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-evolution-hub` | `sandbox-lab` | 沙盒實驗 |
| `skills-evolution-hub` | `qa-auditor` | 品質審計 |
| `skills-evolution-hub` | `tantra` | 情慾治理 |
| `skills-evolution-hub` | `system-health-check` | 系統健康自檢 |
| `skills-evolution-hub` | `decision-tracker` | 決策歷史追蹤 |

#### Workflow Hub
| Source | Target | 說明 |
|--------|--------|------|
| `skills-workflow-hub` | `workflow-svc-brand-marketing` | 品牌行銷 |
| `skills-workflow-hub` | `workflow-investment-analysis` | 投資分析 |
| `skills-workflow-hub` | `workflow-ai-deployment` | AI部署 |
| `skills-workflow-hub` | `group-meeting-notes` | 會議記錄 |

### Skills 跨群組連線（cross）

> 基於 Skill Manifest 的 connects_to 定義

| Source | Target | 說明 |
|--------|--------|------|
| `deep-think` | `resonance` | 共振觸發 |
| `deep-think` | `dharma` | 思維轉化 |
| `deep-think` | `philo-dialectic` | 哲學思辨 |
| `deep-think` | `master-strategy` | 戰略判斷 |
| `investment-masters` | `market-core` | 市場分析 |
| `investment-masters` | `risk-matrix` | 風險管理 |
| `investment-masters` | `sentiment-radar` | 情緒雷達 |
| `roundtable` | `master-strategy` | 戰略詰問 |
| `roundtable` | `shadow` | 博弈辨識 |
| `wee` | `pdeif` | 逆熵流演化 |
| `wee` | `xmodel` | 破框解方 |
| `wee` | `orchestrator` | 編排演化 |
| `morphenix` | `qa-auditor` | 品質審計 |
| `morphenix` | `env-radar` | 環境掃描 |
| `dna27` | `query-clarity` | 問題品質守門 |
| `dna27` | `c15` | 敘事張力 |
| `knowledge-lattice` | `skills-thinking-hub` | 記憶接收（思維） |
| `knowledge-lattice` | `skills-market-hub` | 記憶接收（市場） |
| `knowledge-lattice` | `skills-business-hub` | 記憶接收（商業） |
| `knowledge-lattice` | `skills-creative-hub` | 記憶接收（創意） |
| `knowledge-lattice` | `skills-product-hub` | 記憶接收（產品） |
| `knowledge-lattice` | `skills-evolution-hub` | 記憶接收（演化） |
| `knowledge-lattice` | `skills-workflow-hub` | 記憶接收（工作流） |
| `skills-thinking-hub` | `brain` | 思維技能→Brain |
| `skills-market-hub` | `brain` | 市場技能→Brain |
| `skills-business-hub` | `brain` | 商業技能→Brain |
| `skills-creative-hub` | `brain` | 創意技能→Brain |
| `skills-product-hub` | `brain` | 產品技能→Brain |
| `skills-evolution-hub` | `evolution` | 演化技能→Evolution |
| `skills-workflow-hub` | `brain` | 工作流技能→Brain |
| `report-forge` | `knowledge-lattice` | 報告洞見結晶化 |
| `system-health-check` | `knowledge-lattice` | 健康結晶化 |
| `system-health-check` | `morphenix` | 修復提案 |
| `decision-tracker` | `knowledge-lattice` | 決策結晶化 |
| `decision-tracker` | `user-model` | 決策偏好 |

### Installer 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `installer` | `installer-daemon` | Daemon 設定 |
| `installer` | `installer-electron` | Electron 打包 |
| `installer` | `installer-env` | 環境檢查 |
| `installer` | `installer-verifier` | 模組驗證 |

### 監控連線（monitor）
| Source | Target | 說明 |
|--------|--------|------|
| `service-health` | `gateway` | 監控 |
| `service-health` | `qdrant` | 監控 |
| `service-health` | `searxng` | 監控 |
| `service-health` | `firecrawl` | 監控 |
| `service-health` | `anthropic-api` | 監控 |

### 非同步連線（async）
| Source | Target | 說明 |
|--------|--------|------|
| `proactive-bridge` | `telegram` | 非同步推播 |
| `nightly` | `event-bus` | 回饋迴路 |
| `morphenix` | `event-bus` | 提案回饋 |
| `telegram` | `zeal` | 回傳回應（私聊 + 群組回覆） |
| `telegram` | `external-user` | 群組中回覆外部使用者 |
| `line` | `zeal` | LINE 回傳回應 |
| `data-watchdog` | `event-bus` | 監控事件 |
| `telegram` | `brain` | 推送寫入 session |
| `fact-correction` | `proactive-bridge` | P4 自省清洗推播 |
| `fact-correction` | `pulse` | P4 自省清洗脈搏 |
| `zeal` | `anima-mc-store` | Owner 互動觸發 ANIMA_MC 更新（boss_name、self_awareness） |
| `verified-user` | `anima-mc-store` | 配對使用者互動更新 ANIMA_USER（L1-L8 觀察） |
| `external-user` | `anima-mc-store` | 外部使用者互動更新 external_users/ 觀察 |
| `brain` | `epigenetic-router` | 記憶注入前呼叫表觀遺傳路由（Project Epigenesis） |
| `epigenetic-router` | `memory-reflector` | 回憶後觸發反思 |
| `epigenetic-router` | `diary-store` | 時間圖/因果圖遍歷 Soul Ring |
| `epigenetic-router` | `anima-changelog` | 時間圖遍歷使用者演化歷史 |
| `epigenetic-router` | `knowledge-lattice` | 結晶圖遍歷 |
| `memory-reflector` | `adaptive-decay` | 反思時計算 Activation 排序 |
| `brain` | `proactive-predictor` | Skill 使用記錄 + 需求預判 |
| `proactive-predictor` | `metacognition` | 預判結果回饋元認知 |
| `brain` | `anima-changelog` | _save_anima_user 前記錄差分 |
| `diary-store` | `qdrant` | Soul Ring 向量索引到 soul_rings collection |
| `adaptive-decay` | `nightly` | 每日衰減排程（Step 32） |

---

## 驗證規則（Validation Rules）

### 必要條件 — 每次審計必檢

- [ ] **無孤立節點**：每個節點至少有 1 條連線（輸入或輸出）
- [ ] **Hub 完整性**：每個 Hub 節點必須與其所有 `parent=hub` 的子節點有 `internal` 連線
- [ ] **Event Bus 必達**：每個群組的 Hub 至少有 1 條與 `event-bus` 的連線（control 或 async）
- [ ] **外部服務必監控**：每個 `external` 節點至少被 `service-health` 監控
- [ ] **資料層必連**：任何讀寫持久資料的節點必須與 `data` 群組有 `cross` 連線
- [ ] **雙向一致**：如果 A→B 是 `cross`，B 的影響範圍分析中必須包含 A

### 新增模組必做清單

1. 在本文件 `nodes` 對應群組表格新增條目
2. 定義所有 **輸入連線**（誰呼叫/觸發此模組？）
3. 定義所有 **輸出連線**（此模組呼叫/影響誰？）
4. 如果是 Hub 的子節點，設定 `parent` 並加入 `internal` 連線
5. 如果依賴外部服務，加入 `cross` 連線到 `external` 節點
6. 如果產生/消費持久資料，加入 `cross` 連線到 `data` 群組
7. 更新 3D 心智圖 HTML（`data/workspace/MUSEON_3d_mindmap.html`）的 nodes 和 links 陣列
8. 執行驗證規則確認無違規

### 影響範圍分析模板

修改節點 `X` 前，查詢：

```
直接影響：X 的所有輸出連線 targets
間接影響：targets 的輸出連線 targets（二度關聯）
上游依賴：X 的所有輸入連線 sources
測試範圍：直接影響 + X 本身
```

---

## 統計摘要

| 指標 | 數值 |
|------|------|
| 總節點數 | 184 (134 系統 + 50 Skills) |
| 總連線數 | 456 (353 系統 + 103 Skills) |
| 群組數 | 14 (含 skills) |
| Hub 節點 | 18 (11 系統 + 7 Skills Hub) |
| 跨系統連線 | 186 (151 系統 + 35 Skills cross) |
| 內部連線 | 185 (126 系統 + 59 Skills internal) |
| 非同步連線 | 14 |
| 監控連線 | 5 |
| 控制連線 | 16 (9 系統 + 7 Skills control) |
| 資料流連線 | 9 |
| 衰減連線 | 5 |
| 平均連線數/節點 | 2.5 |
| 拓撲覆蓋率 | 100%（v1.43 全系統審計後） |

---

## 版本紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.43 | 2026-03-23 | 全系統拓撲審計——補齊 70 條遺漏 cross 連線（🔴7 結構斷裂 + 🟠20 重要遺漏 + 🟡43 文件欠債）；移除 2 條幽靈連線（drift-detector→memory 源碼零 import、zotero-bridge→vector-index 源碼零 import）；修正 1 條方向反轉（federation-sync→nightly → nightly→federation-sync）；拓撲覆蓋率 62.8% → 100%；184 節點 456 連線 |
| v1.42 | 2026-03-22 | Sparse Embedder 全面啟動——sparse-embedder 節點升級為已啟動狀態；新增 skill-router→sparse-embedder、memory→sparse-embedder 跨系統連線（hybrid_search 消費者接線）；Nightly Pipeline 新增 Step 8.7（IDF 重建 + 回填） |
| v1.38 | 2026-03-22 | L3-A2 Brain Mixin 拆分：brain 節點拆分為 core + 5 Mixin 子模組 + brain_types 共享型別；agent 群組新增 `brain-prompt-builder`（system prompt 建構, 1668 行）、`brain-dispatch`（任務分派, 1082 行）、`brain-observation`（觀察與演化, 2003 行）、`brain-p3-fusion`（P3 融合與決策層, 948 行）、`brain-tools`（LLM 呼叫與 session 管理, 966 行）、`brain-types`（共享 dataclass: DecisionSignal, P3FusionSignal）6 個節點（+6）；新增 6 條 internal 連線；184 節點 379 連線 |
| v1.37 | 2026-03-22 | Brain 三層治療：agent 群組新增 `chat-context`（ChatContext dataclass 輕量對話上下文，r=0.7）、`deterministic-router`（確定性任務分解器取代 LLM Orchestrator，r=1.0）2 個節點（+2）；新增 2 條 internal 連線（brain→chat-context 對話上下文封裝、brain→deterministic-router 確定性任務分解）；同步 persistence-contract v1.29（PulseDB 新增 orchestrator_calls 表）、joint-map v1.34（#35 orchestrator_calls）；178 節點 373 連線 |
| v1.36 | 2026-03-22 | 使用者節點精細化：channel 群組 `user` 拆分為 `zeal`（CORE 主人，r=2.0）、`verified-user`（VERIFIED 動態配對，r=1.2）、`external-user`（EXTERNAL 群組外部成員，r=1.4）三節點（+2 淨增，user→3）；補上遺漏的 `discord` 節點（r=1.2，+1）；flow 連線從 2 條（user→telegram/line）更新為 6 條（zeal→telegram/line、verified-user→telegram、external-user→telegram/line/discord）+ discord→gateway 1 條；async 連線新增 telegram→external-user、line→zeal 2 條；176 節點 369 連線 |
| v1.35 | 2026-03-22 | P0-P3 升級：Evolution Hub 新增 2 個 Skill 節點（system-health-check 系統健康自檢引擎、decision-tracker 決策歷史追蹤引擎）+ 2 條 internal 連線；新增 5 條 cross 連線（report-forge→knowledge-lattice 報告洞見結晶化、system-health-check→knowledge-lattice 健康結晶化、system-health-check→morphenix 修復提案、decision-tracker→knowledge-lattice 決策結晶化、decision-tracker→user-model 決策偏好）；173 節點 363 連線 |
| v1.34 | 2026-03-22 | 經驗諮詢閘門：新增 1 條 cross 連線 `brain → data-bus`（經驗回放搜尋 activity_log.search()）；無新增節點；171 節點 351 連線 |
| v1.32 | 2026-03-22 | Recommender 激活修復：`recommender` 節點半徑 0.7→0.9（幽靈模組→實際接線）；新增 1 條 cross 連線（recommender→crystal-store 結晶讀取）；brain.py `_recommender` 初始化；server.py API 改用常駐實例；169 節點 350 連線 |
| v1.31 | 2026-03-22 | Knowledge Lattice 持久層遷移：data 群組新增 `crystal-store` 節點（CrystalStore SQLite WAL 統一存取層，+1 節點）；新增 8 條連線——internal: data-bus→crystal-store Store 路由（+1）；cross: knowledge-lattice→crystal-store 結晶讀寫、crystal-actuator→crystal-store 結晶降級升級、nightly→crystal-store 結晶統計、evolution-velocity→crystal-store 結晶數量統計、guardian→crystal-store 結晶健康檢查、memory-reset→crystal-store 一鍵重置（+6）；decay: knowledge-lattice→crystal-actuator 描述更新 crystals.json→crystal.db（+0）；舊 JSON 檔案歸檔為 .bak；同步 persistence-contract v1.26、blast-radius v1.41、joint-map v1.29；169 節點 349 連線 |
| v1.30 | 2026-03-21 | 授權系統升級：gov 群組新增 `authorization` 節點（配對碼+工具授權+分級策略）；新增 5 條連線——internal: governance→authorization 授權引擎、authorization→security 三級策略查詢（+2）；cross: authorization→telegram 配對碼推送+inline keyboard、authorization→gateway 訊息泵授權回覆、authorization→mcp-server auth_status 查詢（+3）；持久化 `~/.museon/auth/`（allowlist.json + policy.json）；168 節點 341 連線 |
| v1.29 | 2026-03-21 | Skills 群組治理升級：新增 `hub` 欄位（9 種 Hub 分組：core/infra/thinking/market/business/creative/product/evolution/workflow）至 49 個 Skill Manifest；新增 Workflow Stage 結構化 YAML（3 個 workflow 含 stages + speed_paths）；新增治理文件 `skill-routing-governance.md`；plugin-registry v2.4（Hub 架構樹）；validate_connections.py v1.1（+2 驗證規則）；167 節點 336 連線（不變） |
| v1.28 | 2026-03-21 | 補全 skills 群組：7 Hub + 39 Skill 節點 + 91 條連線（從 3D 心智圖回補，修復拓撲⇄HTML 漂移）；167 節點 336 連線 |
| v1.27 | 2026-03-21 | Skill 鍛造膠合層修復：VectorBridge 新增 `index_all_skills()`（skills collection 全量索引，Gateway startup + Nightly Step 8.6 + API reindex）；Nightly Step 8.6 `skill_vector_reindex`；plugin-registry v2.3（+12 Skill 註冊）；49 個 Skill Manifest 補齊 memory/io 欄位；同步 blast-radius v1.33、joint-map v1.27、persistence-contract v1.24、memory-router v1.2 |
| v1.25 | 2026-03-21 | 軍師互動+思考前置區拓撲補全：agent 群組新增 `deep-think`、`roundtable`、`investment-masters` 3 個節點（+3）；新增 10 條連線——internal: brain→deep-think/roundtable/investment-masters（+3）；cross: deep-think→metacognition Phase 0 元認知、deep-think→persona-router 訊號分流→百合引擎、roundtable→knowledge-lattice 裁決軌跡結晶、investment-masters→knowledge-lattice 軍師會診結晶、investment-masters→skill-router DNA27 RC 親和觸發（+5）；配套百合引擎 27 單元測試 + Telegram 端到端驗證；124 節點 255 連線 |
| v1.24 | 2026-03-21 | A 區迭代 #1~#3 拓撲同步：data 群組新增 `sparse-embedder` 節點（BM25 稀疏向量，+1 節點）；新增 5 條連線——agent internal: brain→knowledge-lattice MemGPT recall_tiered() + GraphRAG Layer 2.5 recall_with_community()（+2）；data internal: data-bus→sparse-embedder Store 路由 + vector-index→sparse-embedder 混合檢索 RRF 融合（+2）；cross: sparse-embedder→qdrant 稀疏向量存儲（+1）；vector-index→qdrant 描述更新為「向量存儲（dense）」；121 節點 245 連線 |
| v1.22 | 2026-03-20 | 衰減生命週期補全：新增 `decay` 連線類型（色碼 #8B6E5A）+ 5 條衰減連線（結晶 RI、記憶 TTL、健康分數半衰期、推薦近因性、Synapse Decay）；同步 persistence-contract v1.21、blast-radius v1.28、joint-map v1.22 |
| v1.21 | 2026-03-20 | P3 前置交織融合——Step 5.5 前置多視角收集 + system_prompt 注入，視角從「追加」變「交織」，dendritic-fusion 連線擴展至 Step 5.5 |
| v1.20 | 2026-03-20 | P3 策略層並行融合落地：brain.py 新增 P3FusionSignal + Step 3.4 偵測 + Phase 4.5 執行管道 + 5 個 P3 方法；120 節點 240 連線不變；無新增節點；P3 Skill 層（orchestrator v3.0）+ P3 程式碼層（brain.py）雙層實作完整 |
| v1.19 | 2026-03-20 | P0-P3 思維引擎升級（純 Skill .md 認知行為變更，無新節點/連線）：deep-think v2.0（思考路徑可見化 P0 + 主動盲點提醒 P1 + 重大決策先問後答 P2）、query-clarity v2.0（主動觸發「你可能沒想到」P1）、orchestrator v3.0（並行融合模式 P3）、dna27 v2.2（回應合約對齊）；120 節點 240 連線（不變） |
| v1.18 | 2026-03-19 | P1-P3 PersonaRouter 全接線 + 四張藍圖同步：persona-router 節點半徑 1.0→1.1、proactive-bridge 節點半徑 1.1→1.2；新增 cross 連線 persona-router→proactive-bridge（象限決策結果回饋）；brain→proactive-bridge 連線描述更新為「推播 + 百合象限上下文注入」；版本統一為 v1.18（同步 blast-radius v1.24, persistence-contract v1.18, joint-map v1.18）；統計無變化；120 節點 240 連線 |
| v1.0 | 2026-03-14 | 初版建立，59 節點 91 連線 |
| v1.12 | 2026-03-17 | 軍師架構 Phase 0：data 群組新增 `lord-profile` 節點（+1 節點）；新增 2 條 cross 連線（brain→lord-profile 領域畫像寫入、lord-profile→persona-router 百合引擎讀取）；116 節點 220 連線 |
| v1.11 | 2026-03-17 | 3D 心智圖全面同步：nightly 群組標籤統一為「30+ 步」；3D 新增 `observatory`+`cognitive-receipt` 節點（+2）、+7 連線（認知可觀測性閉環）；修正 multi-agent-executor/response-synthesizer/flywheel-coordinator 群組歸屬 multiagent→agent；SYNC_META 升級 v1.10；115 節點 218 連線（3D）|
| v1.10 | 2026-03-17 | 認知可觀測性：gov 群組新增 `cognitive-receipt` 節點；doctor 群組新增 `observatory` 節點（+2 節點）；新增 7 條連線（governance→cognitive-receipt internal、footprint→cognitive-receipt internal、doctor→observatory internal、brain→footprint cross 認知追蹤、footprint→data-bus cross JSONL 寫入、observatory→footprint cross 讀取、observatory→service-health cross 健康狀態）；120 節點 240 連線 |
| v1.9 | 2026-03-17 | DNA-Inspired 品質回饋閉環：新增 3 條跨群組連線（metacognition→pulse-db 品質旗標寫入、morphenix→pulse-db 品質旗標讀取、response-synthesizer→multi-agent-executor DNA 交叉重組）；response-synthesizer 描述更新為「DNA 交叉重組合成」；118 節點 233 連線 |
| v1.14 | 2026-03-16 | Memory Reset 一鍵重置：doctor 群組新增 `memory-reset` 節點（+1 節點 +1 內部連線 doctor→memory-reset）；memory-reset 為 CLI 工具，涵蓋 25 個持久層的原子重置；3D 心智圖同步；統計修正（v1.9-v1.13 遺漏）；118 節點 230 連線 |
| v1.13 | 2026-03-16 | 五缺陷修復 3D 心智圖同步：新增 `blueprint-reader` 節點（data 群組）；新增 7 條連線（governor→immunity learn、governor→pulse-db incident、governor→dendritic-scorer immunity注入、blueprint-reader→doctor/surgery/morphenix 藍圖感知、nightly→blueprint-reader Step 30）；refractory 更新為「三態+半開」；system-audit 更新為「8層49項」；117 節點 229 連線 |
| v1.12 | 2026-03-16 | P5 斷路器半開 + Nightly 藍圖驗證：refractory 節點描述更新為「三態+半開試探」；nightly 新增 Step 30→blueprint-reader 連線（+1 連線） |
| v1.11 | 2026-03-16 | P1+P4 3D 心智圖同步：新增 telegram→brain async（P1 推送寫入 session）、fact-correction→proactive-bridge async + fact-correction→pulse async（P4 自省清洗）；112 節點 219 連線 |
| v1.10 | 2026-03-16 | P0 記憶事實覆寫：agent 群組新增 fact-correction 節點（+1 節點 +4 連線：brain→fact-correction internal、fact-correction→memory cross、fact-correction→vector-index cross、fact-correction→llm-router cross）；111 節點 211 連線 |
| v1.9 | 2026-03-16 | Phase 4 飛輪多代理實質化：multiagent 群組新增 multi-agent-executor、response-synthesizer、flywheel-coordinator 節點（+3 節點 +4 連線：brain→multi-agent-executor internal、brain→response-synthesizer internal、brain→flywheel-coordinator internal、multi-agent-executor→llm-router cross）；110 節點 207 連線 |
| v1.8 | 2026-03-16 | Phase 3 日記+群組ANIMA：soul-ring→diary-store 重命名；pulse 群組新增 group-session-proactive 節點（+1 節點 +4 連線）；107 節點 203 連線 |
| v1.7 | 2026-03-16 | Phase 2 八原語接線：agent 群組新增 primal-detector 節點（+1 節點 +2 連線：brain→primal-detector internal + primal-detector→vector-index cross）；106 節點 199 連線 |
| v1.6 | 2026-03-16 | Docker 沙盒驗證器上線：nightly 群組新增 morphenix-validator 節點（+1 節點 +2 內部連線）；105 節點 197 連線 |
| v1.5 | 2026-03-15 | DNA27 深度修復：移除幽靈節點 task-scheduler(pulse) + guardrails(gov)、新增 anima-mc-store + anima-tracker 到 pulse 群組、修正跨系統連線（+6 新連線 -3 幽靈連線）；104 節點 195 連線 |
| v1.4 | 2026-03-15 | 9.5 精度修復：data 群組新增 3 個 SQLite 子節點（pulse-db, group-context-db, workflow-state-db）+ 3 條 Store 路由連線；104 節點 191 連線 |
| v1.3 | 2026-03-15 | 全面覆蓋修復：新增 installer 群組(5節點)；nightly 擴充+5子節點；tools 擴充+7節點(含federation)；gov 擴充+3子節點；channel 加 mcp-server；新增 43 條連線，總計 101 節點 188 連線 |
| v1.2 | 2026-03-15 | 藍圖完整性修復：新增 evolution(10節點)、tools(3節點) 群組；agent 群組加 onboarding+multiagent；gov 群組加 guardian+security；新增 37 條連線 |
| v1.1 | 2026-03-15 | 新增 DataBus/DataWatchdog、data 群組 Hub 化、Nightly 29 步 |
