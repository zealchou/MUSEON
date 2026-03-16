# MUSEON 系統拓撲圖 v1.7

> 本文件是 MUSEON 所有子系統及其關聯性的 **唯一真相來源（Single Source of Truth）**。
> 新增模組、Debug、審計時必須參照此文件，確保不遺漏依賴關係。

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
| `nightly` | Nightly 夜間 | 29 步夜間整合管線、演化提案、好奇心路由 | `#9A3A1C` |
| `installer` | Installer 安裝 | 部署編排、Daemon 設定、Electron 打包 | `#5A8A3E` |
| `external` | 外部服務 | SearXNG、Qdrant、Firecrawl、API | `#6A6880` |

---

## 節點清單（Nodes）

### center — 核心
| ID | 名稱 | 中文 | Hub | 半徑 |
|----|------|------|-----|------|
| `event-bus` | Event Bus | 核心事件匯流排 | Yes | 3.2 |

### channel — 通道入口
| ID | 名稱 | 中文 | Hub | 半徑 |
|----|------|------|-----|------|
| `user` | User (Zeal) | 使用者 | - | 2.0 |
| `telegram` | Telegram | 主通道 | - | 1.6 |
| `gateway` | Gateway | WebSocket :8765 | - | 1.6 |
| `cron` | Cron | 排程入口 | - | 1.2 |
| `mcp-server` | MCP Server | Claude Code 介面 | - | 1.2 |

### agent — Agent / Brain
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `brain` | Agent / Brain | 主判斷中樞 | Yes | - | 2.8 |
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
| `response-synthesizer` | Response Synthesizer | 多部門回覆合成 | - | brain | 0.8 |
| `flywheel-coordinator` | Flywheel Coordinator | 飛輪流動協調 | - | brain | 0.9 |
| `primal-detector` | Primal Detector | 八原語偵測 | - | brain | 1.0 |
| `fact-correction` | Fact Correction | 事實覆寫引擎 | - | brain | 0.9 |

### pulse — Pulse 生命力
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `pulse` | Pulse Engine | VITA 生命力 | Yes | - | 2.8 |
| `heartbeat` | Heartbeat | 三脈主控 | - | pulse | 1.0 |
| `explorer` | Explorer | 自主探索 | - | pulse | 1.1 |
| `silent-digestion` | Silent Digestion | 靜默消化 | - | pulse | 1.0 |
| `proactive-bridge` | Proactive Bridge | 主動推播 | - | pulse | 1.1 |
| `micro-pulse` | Micro Pulse | 秒級微脈 | - | pulse | 0.8 |
| `pulse-db` | Pulse DB | 脈搏資料庫 | - | pulse | 0.8 |
| `commitment-tracker` | Commitment | 承諾追蹤 | - | pulse | 0.9 |
| `anima-mc-store` | AnimaMC Store | ANIMA統一存取 | - | pulse | 1.1 |
| `anima-tracker` | Anima Tracker | 八元素追蹤 | - | pulse | 1.0 |
| `group-session-proactive` | Group Session Proactive | 群組後主動追問 | - | pulse | 0.9 |

### gov — Governance
| ID | 名稱 | 中文 | Hub | Parent | 半徑 |
|----|------|------|-----|--------|------|
| `governance` | Governance | 三焦式治理 | Yes | - | 2.8 |
| `governor` | Governor | 上中下焦 | - | governance | 1.0 |
| `immunity` | Immunity | 先天 + 後天免疫 | - | governance | 1.1 |
| `preflight` | Preflight | 啟動門 | - | governance | 0.9 |
| `refractory` | Refractory | 斷路器 | - | governance | 0.9 |
| `skill-scanner` | Skill Scanner | 技能掃描 | - | governance | 0.8 |
| `sandbox` | Sandbox | 沙盒隔離 | - | governance | 0.8 |
| `telegram-guard` | TG Guard | Polling 守衛 | - | governance | 0.8 |
| `service-health` | Service Health | 服務監控 | - | governance | 1.0 |
| `guardian` | Guardian | 系統守護 Daemon | - | governance | 1.1 |
| `security` | Security | 安全淨化與稽核 | - | governance | 1.0 |
| `dendritic-scorer` | Dendritic Scorer | 樹突評分器 | - | governance | 0.9 |
| `footprint` | Footprint | 操作足跡追蹤 | - | governance | 0.9 |
| `perception` | Perception | 四診合參感知 | - | governance | 0.9 |

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
| `nightly` | Nightly Pipeline | 29 步夜間整合 | Yes | - | 2.2 |
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

### 主資料流（flow）
| Source | Target | 說明 |
|--------|--------|------|
| `user` | `telegram` | 訊息指令 |
| `telegram` | `gateway` | 轉發 |
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
| `cron` | `nightly` | 03:00 觸發 |

### Agent 內部連線（internal）
| Source | Target | 說明 |
|--------|--------|------|
| `brain` | `dna27` | 載入反射 |
| `brain` | `skill-router` | 技能路由 |
| `brain` | `reflex-router` | 迴圈判定 |
| `brain` | `dispatch` | 多技能分派 |
| `brain` | `knowledge-lattice` | 結晶注入 |
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
| `brain` | `fact-correction` | 事實更正偵測+覆寫 |
| `multi-agent-executor` | `llm-router` | 多部門 API 呼叫 |

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
| `data-bus` | `data-watchdog` | 監控注入 |
| `data-bus` | `pulse-db` | Store 路由 |
| `data-bus` | `group-context-db` | Store 路由 |
| `data-bus` | `workflow-state-db` | Store 路由 |
| `wee` | `skill-synapse` | 突觸演化 |
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
| `vector-index` | `qdrant` | 向量存儲 |
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
| `crystal-actuator` | `knowledge-lattice` | 結晶操作 |
| `periodic-cycles` | `pulse` | 週期驅動 |
| `skill-market` | `skills-registry` | 技能打包 |
| `federation-sync` | `nightly` | 夜間同步 |
| `zotero-bridge` | `vector-index` | 文獻索引 |
| `auto-repair` | `installer` | 修復用安裝器 |

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
| `telegram` | `user` | 回傳回應 |
| `data-watchdog` | `event-bus` | 監控事件 |

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
| 總節點數 | 110 |
| 總連線數 | 207 |
| 群組數 | 13 |
| Hub 節點 | 11 (event-bus, brain, pulse, governance, doctor, llm-router, evolution, tool-registry, nightly, data-bus, installer) |
| 跨系統連線 | 67 |
| 內部連線 | 110 |
| 非同步連線 | 5 |
| 監控連線 | 5 |
| 控制連線 | 9 |
| 資料流連線 | 4 |
| 平均連線數/節點 | 3.8 |

---

## 版本紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.0 | 2026-03-14 | 初版建立，59 節點 91 連線 |
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
