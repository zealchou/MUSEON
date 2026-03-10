# MUSEON 多輪遞進式完整性檢查 — 全自動模式

> **使用方式**：一次給 Claude 一輪指令。每輪完成後 Claude 會自動輸出結果摘要，
> 你只需說「下一輪」即可。若需一次跑完，使用底部的「全自動啟動指令」。

---

## 全域規則

### 檢查範圍
- **根目錄**：`~/MUSEON/`
- **主要掃描**：`src/museon/`、`tests/`、`scripts/`、`electron/`（僅 `main.js`, `preload.js`, `src/`, `package.json`）、`features/`、`bin/`
- **設定檔**：`pyproject.toml`、`.env.example`、`electron/package.json`、`data/_system/` 下的 JSON
- **排除**：`node_modules/`、`__pycache__/`、`.runtime/`、`dist/`、`htmlcov/`、`.venv/`、`.git/`、`*.pyc`、`electron/dist/`

### Skill 生態系範圍（Round 6A 專用）
- **Skill 定義**：`~/.claude/plugins/museon-consultant/skills/*/SKILL.md`
- **原生技能**：`~/MUSEON/data/skills/native/`
- **鍛造技能**：`~/MUSEON/data/skills/forged/`
- **Skill 路由**：`src/museon/agent/skill_router.py`
- **Skill 管理**：`src/museon/core/skill_manager.py`

### 自我手術系統範圍（Round 6F 專用）
- **靜態分析**：`src/museon/doctor/code_analyzer.py`（AST 規則引擎）
- **日誌分析**：`src/museon/doctor/log_analyzer.py`（日誌異常偵測）
- **診斷管線**：`src/museon/doctor/diagnosis_pipeline.py`（D1/D2/D3 三層管線）
- **手術引擎**：`src/museon/doctor/surgeon.py`（SurgeonSandbox + SurgeryEngine + SurgeryRestarter）
- **手術記錄**：`src/museon/doctor/surgery_log.py`（手術記錄持久化）
- **事件常數**：`src/museon/core/event_bus.py`（SURGERY_* + SELF_DIAGNOSIS_COMPLETED 系列）
- **Brain 工具**：`src/museon/agent/tools.py`（7 個手術工具：source_read/search/ast_check、surgery_diagnose/propose/apply/rollback）
- **工具 Schema**：`src/museon/agent/tool_schemas.py`（手術工具定義）
- **持久化檔案**：`data/doctor/surgery_log.json`（手術記錄）
- **Guardian L5**：`src/museon/guardian/daemon.py` → `run_l5()`（程式碼健康檢查）
- **Gateway API**：`src/museon/gateway/server.py`（`/api/doctor/*` 端點 + Guardian L5 cron）

### 外向型進化引擎範圍（Round 6D 專用）
- **觸發器**：`src/museon/evolution/outward_trigger.py`
- **意圖雷達**：`src/museon/evolution/intention_radar.py`
- **消化引擎**：`src/museon/evolution/digest_engine.py`
- **事件常數**：`src/museon/core/event_bus.py`（OUTWARD_* 系列）
- **上游事件源**：`src/museon/agent/eval_engine.py`（SKILL_QUALITY_SCORED）、`src/museon/evolution/feedback_loop.py`（USER_FEEDBACK_SIGNAL）
- **下游固化**：`src/museon/agent/knowledge_lattice.py`（Crystal 狀態擴展）、`src/museon/nightly/morphenix_executor.py`（Morphenix 提案）
- **安全層**：`src/museon/security/sanitizer.py`（InputSanitizer）
- **管線整合**：`src/museon/nightly/nightly_pipeline.py`（Step 13.6/13.7/13.8）
- **持久化檔案**：`_system/outward/`（`daily_counter.json`、`pending_signals.json`、`direction_cooldown.json`、`quarantine.json`、`search_plan.json`）

### 自主執行協議
1. 每輪檢查完成後，若發現錯誤，**立即修復，不需等待確認**
2. 修復後重新執行同一輪，直到該輪零錯誤
3. **無重跑次數上限**——持續修復 + 重跑直到通過
4. 若修復 A 引發新問題 B，立即修復 B，然後重跑整輪
5. 該輪通過後，輸出結果摘要，**自動進入下一輪**
6. 所有輪次都零錯誤後，執行結案動作
7. **唯一停止條件**：所有 Round 通過，或遇到需要人類提供資訊（如缺少密碼/token）的阻斷點

### 修復原則
- **一律自動修復**：import 路徑、缺少 `__init__.py`、JSON 格式、typo、未使用 import、函式簽名不匹配、事件名稱不同步、設定檔 key 缺漏、端口不一致——全部直接修
- **架構級問題**：若修復需要新增超過 50 行程式碼，或涉及根本性架構改動，標記為 🏗️ 並在最終報告中列出，但不阻擋流程繼續
- **修復品質**：每次修復必須是最小化變更（minimal diff），不要順便重構或美化周圍程式碼
- **安全底線**：不刪除任何 `data/` 下的使用者資料檔案，不修改 `.env`（只修 `.env.example`）

### 輸出格式（每輪結束時）
```
## Round N 結果 [通過 ✅ / 第 X 次重跑 🔄]

### 統計
- ✅ 通過：XX 項
- 🔧 發現並修復：XX 項
- 🏗️ 架構級（僅標記）：XX 項

### 修復明細（僅列出有修改的項目）
| # | 檔案 | 行號 | 問題 | 修復方式 |
|---|------|------|------|----------|
| 1 | src/museon/agent/brain.py | 42 | import `utils.helper` 不存在 | → `utils.helpers` |

### 架構級標記（如有）
| # | 檔案 | 問題描述 | 影響範圍 |
|---|------|----------|----------|

→ 自動進入 Round N+1
```

---

## Round 0：基準快照

**目的**：建立修改前的基準狀態

**步驟**：
1. `cd ~/MUSEON && git status` — 記錄工作區狀態
2. 若有未 commit 的變更，先執行 `git stash -m "pre-integrity-check"` 保存
3. `python -m museon.doctor.system_audit --home /Users/ZEALCHOU/MUSEON` — 記錄基準
4. 統計檔案數量：
   - `find src/museon -name "*.py" | wc -l`
   - `find tests -name "*.py" | wc -l`
5. 記錄 `pyproject.toml` 版本號
6. 記錄 `electron/package.json` 版本號

**此輪不修復任何東西，只記錄，然後自動進入 Round 1。**

---

## Round 1：檔案結構與路徑

**檢查手段**：Grep + Glob + Read

### 1A. Python import 路徑驗證
- 掃描 `src/museon/**/*.py` 中所有 `from museon.xxx import` 和 `import museon.xxx`
- 驗證每個 import 路徑對應的 `.py` 檔案或 `__init__.py` 是否存在
- 檢查 circular import（A→B→A），若存在則重構為延遲 import 或抽出共用模組

### 1B. `__init__.py` 完整性
- `src/museon/` 下每個 Python 子目錄必須有 `__init__.py`
- 例外：`__pycache__/`、純資料目錄
- 缺少的直接建立空檔案

### 1C. 設定檔路徑引用
- `pyproject.toml` 中 `[tool.pytest]` 路徑是否存在
- `scripts/*.sh` 中引用的路徑是否存在
- `bin/*.sh` 中引用的路徑是否存在

### 1D. 資料目錄引用
- 程式碼中 hardcode 的 `data/` 子目錄路徑（如 `data/_system/`、`data/memory/`、`data/skills/`）是否實際存在
- 程式碼中引用的 JSON/JSONL 設定檔路徑是否存在
- 外向型進化引擎持久化目錄：`_system/outward/` 是否存在，以下檔案的讀寫路徑是否一致：
  - `_system/outward/daily_counter.json`（每日配額計數）
  - `_system/outward/pending_signals.json`（待處理信號佇列）
  - `_system/outward/direction_cooldown.json`（方向冷卻記錄）
  - `_system/outward/quarantine.json`（隔離區結晶）
  - `_system/outward/search_plan.json`（搜尋計畫）
- 上游資料源路徑：`_system/wee/plateau_alerts.json`、`_system/morphenix/notes/` 目錄
- 自我手術系統持久化目錄：`data/doctor/` 是否存在，以下檔案的讀寫路徑是否一致：
  - `data/doctor/surgery_log.json`（手術記錄）
- 若目錄缺失，建立空目錄；若 JSON 缺失且有預設值，建立含預設值的檔案

#### 1D-extra. 目錄建立防禦模式（DSE 2026-03 迭代教訓）

> **根因**：多個模組在 `__init__()` 或 `save()` 中直接讀寫目錄，但從未呼叫 `mkdir(parents=True, exist_ok=True)`。
> 首次啟動或資料目錄被清除後靜默崩潰。（Fix 11: skill_scout.py、Fix 12: ceremony.py）

- 掃描 `src/museon/**/*.py` 中所有 `Path(...).write_text()`、`open(..., 'w')`、`json.dump(..., open(...))`
- 對每個寫入目標，回溯確認其 **parent 目錄** 在寫入前是否有 `mkdir(parents=True, exist_ok=True)` 保護
- 重點模組（已知曾出問題）：
  - `nightly/skill_scout.py` — `self.data_dir` 必須有 mkdir
  - `onboarding/ceremony.py` — `ceremony_state_path.parent` 和 `anima_l1_path.parent` 必須有 mkdir
  - `governance/dendritic_scorer.py` — 持久化路徑
  - `memory/store.py` — 記憶儲存路徑
- 缺少目錄建立保護的 → 直接在寫入前補上 `path.parent.mkdir(parents=True, exist_ok=True)`

### 1E. 孤兒檔案掃描
- `src/museon/` 下是否有 `.py` 檔案從未被任何其他檔案 import
- 排除：`__init__.py`、`__main__.py`、`mcp_server.py`、CLI 入口點、test 檔案
- 孤兒檔案僅標記為 🏗️，不刪除

### 1F. Electron 引用
- `electron/main.js` 和 `electron/preload.js` 中 `require()` 的路徑是否存在
- `electron/src/` 中 HTML 引用的 JS/CSS 檔案是否存在

---

## Round 2：語法與格式

**檢查手段**：
- Python：`python -m py_compile <file>`
- JSON：`python -c "import json; json.load(open('<file>'))"`
- TOML：`python -c "import tomllib; tomllib.load(open('<file>','rb'))"`

### 2A. Python 語法
- 對 `src/museon/**/*.py` 每個檔案執行 `python -m py_compile`
- 對 `tests/**/*.py` 每個檔案執行 `python -m py_compile`
- 語法錯誤直接修復

### 2B. JSON 格式
- `data/_system/**/*.json` 格式驗證
- `data/*.json`（`ANIMA_MC.json`、`ceremony_state.json`、`tasks.json` 等）
- `electron/package.json`
- `update_marker.json`
- 格式錯誤（trailing comma、encoding 問題等）直接修復

### 2C. TOML 格式
- `pyproject.toml` 解析驗證

### 2D. YAML frontmatter（Skill 檔案）
- `data/skills/native/*/SKILL.md` 的 YAML frontmatter 驗證
- `data/skills/forged/*/SKILL.md`（如有）

### 2E. 環境變數引用
- 掃描 `src/museon/**/*.py` 中所有 `os.environ.get()`、`os.getenv()`、`os.environ[]`
- 比對 `.env.example` 中定義的 key
- 程式碼中引用但 `.env.example` 未定義的 → 補入 `.env.example`（含合理的預設值或註解）

### 2F. BDD Feature 語法
- `features/**/*.feature` 基本 Gherkin 結構驗證
- 每個 `Scenario` 必須有 `Given/When/Then`

---

## Round 3：模組間連動

**檢查手段**：Read + Grep + 交叉比對

### 3A. Export/Import 介面匹配
- `__init__.py` 中 `__all__` 列表 vs 子模組實際定義
- 呼叫端使用的 class/function 名稱 vs 定義端（注意大小寫、底線）

### 3B. 函式簽名一致性
重點檢查以下跨模組呼叫鏈的參數匹配：
- `brain.py` → `dispatch.py`
- `gateway/server.py` → `agent/` 模組
- `pulse/` → `agent/` 模組
- `nightly/` → `agent/`、`governance/`
- `channels/telegram.py` → `gateway/`
- `skill_router.py` → `skills.py`
- 自我手術管線呼叫鏈：
  - `tools.py` → `SurgeryEngine(project_root, auto_restart)` 建構參數
  - `tools.py._execute_surgery_diagnose()` → `DiagnosisPipeline(source_root, logs_dir, heartbeat_state_path, llm_adapter)` 建構參數
  - `tools.py._execute_surgery_apply()` → `SurgeryEngine.execute_surgery(proposal, dry_run)` 參數
  - `tools.py._execute_source_ast_check()` → `CodeAnalyzer(source_root)` 建構參數
  - `surgeon.py.execute_surgery()` → `morphenix_standards.review_proposal(proposal)` 參數（返回 `(passed, violations, recommendation)`）
  - `surgeon.py.execute_surgery()` → `SurgeryLog.create/update/complete` 生命週期
  - `diagnosis_pipeline.py.run()` → `CodeAnalyzer.scan_all()` / `scan_file()` / `scan_specific_rules()`
  - `diagnosis_pipeline.py.run()` → `LogAnalyzer.analyze(lookback_hours)`
  - `gateway/server.py._guardian_l5()` → `Guardian.run_l5()` → `CodeAnalyzer.scan_all()`
- 外向型進化管線呼叫鏈：
  - `nightly_pipeline.py` → `OutwardTrigger(workspace, event_bus)` 建構參數
  - `nightly_pipeline.py` → `IntentionRadar(workspace, event_bus)` 建構參數
  - `nightly_pipeline.py` → `DigestEngine(workspace, event_bus)` 建構參數
  - `outward_trigger._execute_immediate()` → `IntentionRadar.generate_queries(event)` 參數格式
  - `outward_trigger._execute_immediate()` → `ResearchEngine.research(query, context_type)` 參數
  - `outward_trigger._execute_immediate()` → `DigestEngine.ingest(result, context)` 參數
  - `digest_engine._promote()` → `KnowledgeLattice.add_crystal(crystal_data)` 參數
  - `digest_engine._sanitize_content()` → `InputSanitizer` 介面
  - `eval_engine.scan_blindspots()` → `event_bus.publish(SKILL_QUALITY_SCORED, data)` payload 格式
- 簽名不匹配的，以**定義端為準**修正呼叫端

### 3C. 事件名稱一致性
- `core/event_bus.py` 中 emit/publish 的事件名稱
- 各模組 subscribe/listen/on 的事件名稱
- 不匹配的，以 event_bus 定義為準修正訂閱端
- **外向型進化事件鏈**重點交叉驗證（事件常數必須從 `event_bus.py` import，不可 hardcode 字串）：
  - `SKILL_QUALITY_SCORED`：`eval_engine.py` publish → `outward_trigger.py` subscribe
  - `USER_FEEDBACK_SIGNAL`：`feedback_loop.py` publish → `outward_trigger.py` subscribe
  - `OUTWARD_SEARCH_NEEDED`：`outward_trigger.py` publish → `intention_radar.py` subscribe
  - `OUTWARD_SELF_CRYSTALLIZED`：`digest_engine.py` publish（通知型，無消費者）
  - `OUTWARD_SERVICE_CRYSTALLIZED`：`digest_engine.py` publish（通知型，無消費者）
  - `OUTWARD_TRIAL_RECORDED`：`digest_engine.py` publish（通知型，無消費者）
  - `OUTWARD_KNOWLEDGE_ARCHIVED`：`digest_engine.py` publish（通知型，無消費者）
- **自我手術事件鏈**重點交叉驗證：
  - `SELF_DIAGNOSIS_COMPLETED`：`diagnosis_pipeline.py` publish（通知型）
  - `SURGERY_TRIGGERED`：`surgeon.py` publish → ActivityLogger subscribe
  - `SURGERY_SAFETY_PASSED`：`surgeon.py` publish（通知型）
  - `SURGERY_SAFETY_FAILED`：`surgeon.py` publish → ActivityLogger subscribe
  - `SURGERY_COMPLETED`：`surgeon.py` publish → ActivityLogger subscribe
  - `SURGERY_FAILED`：`surgeon.py` publish → ActivityLogger subscribe
  - `SURGERY_ROLLBACK`：`surgeon.py` publish → ActivityLogger subscribe

### 3D. API endpoint 一致性
- `gateway/server.py` 的 FastAPI 路由（`@app.get`、`@app.post` 等）
- `electron/main.js` 或 `electron/src/app.js` 中呼叫的 API 路徑
- 不匹配的，以 server.py 定義為準修正前端

### 3E. 共用常數與 Enum
- 在多個檔案中出現的字串常數（channel 名稱、status 值、lifecycle 狀態）
- 確認所有引用處是否同步
- 不同步的，以定義源頭為準統一

### 3F. Pydantic Model 欄位
- `gateway/message.py` 等處定義的 Pydantic Model
- 其他模組建構這些 Model 時傳入的欄位
- 欄位不匹配的，以 Model 定義為準修正呼叫端

---

## Round 4：邏輯與流程

**檢查手段**：Read + 靜態分析

### 4A. 錯誤處理覆蓋
- `async def` 函式是否有 `try/except` 或呼叫端有處理
- 重點：`gateway/server.py`、`channels/telegram.py`、`llm/client.py`、`pulse/` 模組
- `httpx` 呼叫 → 應處理 `httpx.HTTPError`
- `anthropic` API 呼叫 → 應處理 `anthropic.APIError`
- 缺少錯誤處理的，加上最小必要的 try/except + logging

### 4B. Async/Await 正確性
- 遺漏 `await` 的 coroutine 呼叫 → 補上 `await`
- 非 async 函式呼叫 async 函式 → 改用 `asyncio.run()` 或標記為 🏗️
- `asyncio.run()` 在已有 event loop 中被呼叫 → 改用 `loop.create_task()` 或 `await`
- **CPU-bound 操作必須使用 `asyncio.to_thread()`**（避免阻塞 event loop）：
  - `CodeAnalyzer.scan_all()` / `scan_file()` / `scan_specific_rules()` — AST 遍歷是 CPU-bound
  - `LogAnalyzer.analyze()` — 日誌解析是 CPU-bound
  - 檢查以下呼叫點是否有 `await asyncio.to_thread()` 包裝：
    - `diagnosis_pipeline.py` D1/D2 階段
    - `gateway/server.py` `/api/doctor/code-health` 端點
    - `gateway/server.py` `_guardian_l5()` cron job
    - `agent/tools.py` `_execute_source_ast_check()`
  - 缺少 `to_thread` 的直接補上

### 4C. 無限迴圈/遞迴風險
- `while True` 迴圈 → 必須有 `break`/`return`/`shutdown` 條件
- 遞迴函式 → 必須有深度限制或明確終止條件
- `pulse/heartbeat_engine.py` 心跳迴圈 → 必須有 shutdown 機制
- 缺少的直接補上

### 4D. 資料流完整性
- `brain.py` → `dispatch.py` → `skill_router.py` 資料傳遞鏈
- `channels/*.py` → `gateway/` → `agent/` 鏈路
- `nightly_pipeline.py` 各步驟間資料傳遞
- `memory/` 讀寫格式對稱性（寫入格式 = 讀取期望格式）
- **外向型進化即時管線**資料流：
  - EvalEngine.scan_blindspots() → `SKILL_QUALITY_SCORED` payload → OutwardTrigger._on_skill_quality(data)
    - 驗證：payload 含 `blind_spots` 陣列，每項含 `domain`、`skill`、`detail`
  - FeedbackLoop → `USER_FEEDBACK_SIGNAL` payload → OutwardTrigger._on_feedback_signal(data)
    - 驗證：payload 含 `direction`（"declining"/"improving"）、`delta`（float）
  - OutwardTrigger._signal_to_event() 輸出格式 → IntentionRadar.generate_queries(event) 輸入格式
    - 驗證：event 含 `track`、`trigger_type`、`priority`、`search_intent`、`related_skill`、`related_domain`
  - IntentionRadar 輸出 query dict → ResearchEngine.research() 輸入
    - 驗證：query dict 含 `query`（str）、`context_type`（"outward_self"/"outward_service"）
  - ResearchEngine 結果 → DigestEngine.ingest(result, context)
    - 驗證：result 含 `summary`（str）、`source_urls`（list）、`is_valuable`（bool）
  - DigestEngine._promote() → KnowledgeLattice.add_crystal()（Track B）
    - 驗證：crystal_data 含必填欄位（`crystal_type`、`g1_summary`、`origin`）
- **外向型進化凌晨管線**資料流：
  - Step 13.6 輸出 `{"triggered": int, "events": [...]}` → Step 13.7 消費 `events`
  - Step 13.7 輸出 `{"researched": int, "ingested": int}` → Step 13.8 使用 `ingested` 統計
  - Step 13.8 輸出 `{"promoted": int, "archived": int, "expired": int}`
- 斷點直接修復

### 4F. 物件存在性守衛（DSE 2026-03 迭代教訓）

> **根因**：模組在呼叫物件方法前未確認物件是否已初始化。
> Gateway 啟動順序或條件分支導致物件為 None 時靜默崩潰。
> （Fix 9: telegram.py `self.application` 未檢查、先前 Fix: server.py `adapter` 變數未定義）

**掃描規則**：
- 搜尋 `getattr(app.state, "xxx", None)` 模式後，檢查回傳值是否有 `if xxx:` 或 `if xxx is not None:` 守衛
- 搜尋 `self.application`、`self.bot`、`self.adapter` 等可能為 None 的物件屬性，在呼叫其方法前是否有存在性檢查
- 重點模組（已知曾出問題）：
  - `channels/telegram.py` — `self.application` 在 `_on_morphenix_executed()` 等回呼中必須有守衛
  - `gateway/server.py` — `app.state.telegram_adapter` 在 cron job 中必須用 `getattr()` + None 檢查
  - `gateway/server.py` — `app.state.brain` 在 API handler 中必須確認已初始化
- 通用規則：**任何在 cron job / event handler / callback 中使用的 `app.state.xxx` 或 `self.xxx`，若該物件在啟動流程中可能尚未初始化或初始化失敗，必須有 None 守衛**
- 缺少守衛的 → 在方法入口加上 `if not obj: logger.warning(...); return`

### 4G. 品質閘門複雜度（DSE 2026-03 迭代教訓）

> **根因**：品質控制邏輯使用過度簡化的二元判定，無法反映真實的分級需求。
> （Fix 10: dendritic_scorer.py 原本只有 tier 1/2 二元判定，高頻+高影響的問題無法升級人工介入）

**掃描規則**：
- 搜尋 `src/museon/**/*.py` 中的品質判定邏輯（包含 `tier`、`level`、`grade`、`severity` 等分級變數）
- 任何「只有 2 級」的分級邏輯 → 評估是否需要至少 3 級
- 重點模組：
  - `governance/dendritic_scorer.py` — incident tier 必須是 3 級（自動修復 / LLM 研究 / 人工介入）
  - `governance/metacognition.py` — 質量判定不可只用簡單閾值
  - `agent/eval_engine.py` — 品質評分不可只有 pass/fail
- 通用規則：**品質/嚴重度分級至少 3 級（低/中/高），避免二元判定遺漏中間狀態**
- 過度簡化的 → 標記為 🏗️ 並建議分級方案

### 4H. 通知管道韌性（DSE 2026-03 迭代教訓）

> **根因**：通知管道在部分元件失效時整條管線斷裂，無 fallback 也無降級策略。
> （先前 Fix: brain.py 通知函式未定義、server.py 通知變數未初始化）

**掃描規則**：
- 搜尋所有 `push_notification`、`send_message`、`notify` 呼叫
- 每個通知呼叫必須有 try/except 包裝，失敗時 logger.error 而非 raise
- 重點管道：
  - `gateway/server.py` → Telegram 通知（工具降級、nightly 完成等）
  - `channels/telegram.py` → Morphenix 執行通知
  - `pulse/proactive_bridge.py` → 主動訊息推送
- 通用規則：**通知失敗不可中斷主流程（fire-and-forget with logging）**
- 缺少保護的 → 加上 try/except + logger.error

### 4E. 並行安全
- 共用 JSON 檔案讀寫 → 是否有 file lock
- `session.py` → 是否 thread-safe
- SQLite async context 安全性
- **原子寫入驗證**（防止並行讀寫 race condition）：
  - `brain.py` `_save_anima_mc()` 和 `_save_anima_user()` → 必須使用 tmp→rename 原子寫入模式
  - `memory/store.py` `write()` → 必須使用 `threading.Lock` 保護並發寫入
  - 驗證模式：`tmp_path.write_text(data) → tmp_path.replace(target_path)`，不可直接 `open(target, 'w')`
- **Telegram 分段發送 rate limit**：
  - `channels/telegram.py` 分段訊息之間必須有 `asyncio.sleep(0.15)` 延遲，避免 Telegram API rate limit
- **表裏分離驗證**：
  - `brain.process()` 只能被三個表層入口呼叫：Telegram message pump、Webhook、Dashboard inject
  - 所有裏層 cron 排程（Guardian、NightlyPipeline、Morphenix、Surgery）不可呼叫 `brain.process()`
  - 違反表裏分離的呼叫 → 標記為 CRITICAL
- 缺少保護的標記為 🏗️

---

## Round 5：設定與依賴一致性

**檢查手段**：Bash（pip、npm）+ Grep

### 5A. Python 依賴（pyproject.toml）
- `[project.dependencies]` 列出但未被 import 的 → 保留不動（可能是間接依賴）
- `src/museon/` import 但未在 dependencies 宣告的 → 補入 `pyproject.toml`
- 用 `pip list --format=freeze` 確認版本相容性

### 5B. Node.js 依賴（electron/package.json）
- `dependencies` 列出但未被 require 的 → 標記為 🏗️
- `require()` 但未在 dependencies 宣告的 → 補入 `package.json`

### 5C. 設定檔 Key 一致性
- `.env.example` keys vs 程式碼 `os.environ.get()`/`os.getenv()` → 補齊缺漏
- `data/_system/token_budget.json` 結構 vs `llm/budget.py` 讀取邏輯
- `data/_system/synapses.json` 結構 vs `agent/` 讀取邏輯
- `data/_system/tool_muscles.json` 結構 vs `evolution/tool_muscle.py` 讀取邏輯
- `_system/outward/daily_counter.json` 結構（`{"date": "YYYY-MM-DD", "count": int}`）vs `outward_trigger.py` 讀寫邏輯
- `_system/outward/quarantine.json` 結構（Crystal 陣列）vs `digest_engine.py` 讀寫邏輯

### 5D. 版本號一致性
- `pyproject.toml` version
- `electron/package.json` version
- `update_marker.json` version（如有）
- 不一致的，以 `pyproject.toml` 為準統一

### 5E. 腳本路徑
- `scripts/build-installer.sh` 引用路徑驗證
- `scripts/prepare-runtime-bundle.sh` 同步來源/目標路徑驗證
- `scripts/deploy.sh` 路徑與環境假設驗證

---

## Round 6A：Skill 生態系一致性

**檢查手段**：Glob + Read + 比對

### 6A-1. Skill 註冊 vs 實際檔案
- `data/skills/native/` 每個資料夾 vs `skill_router.py` 掃描清單
- 一一對應，無遺漏無多餘

### 6A-2. SKILL.md 交叉引用
- 每個 SKILL.md 中「依賴其他 Skill」的名稱 → 被引用 Skill 是否存在
- `plugin-registry` 註冊清單 vs 實際 Skill 資料夾

### 6A-3. DNA27 反射叢集路由表
- `agent/dna27.py` 或 `agent/reflex_router.py` 中 RC 定義
- **叢集總數驗證**：`ALL_CLUSTERS` 應包含 31 個叢集（Tier A~F）
  - Tier A: 情緒層（RC-A1~A5）
  - Tier B: 行為層（RC-B1~B5）
  - Tier C: 認知層（RC-C1~C5）
  - Tier D: 存在層（RC-D1~D5）
  - Tier E: 演化層（RC-E1~E7）
  - **Tier F: 系統診斷層（RC-F1~F4）**（DSE 2026-03 新增）
    - RC-F1: system_health_inquiry（系統健康查詢）
    - RC-F2: tool_status_check（工具狀態檢查）
    - RC-F3: self_diagnosis（自我診斷）
    - RC-F4: operational_feedback（運作回饋）
- 每個 RC 對應的 Skill 是否存在
- 無重複 ID、無遺漏
- `rc_affinity_loader.py` 的 RC 正則表達式必須包含 `RC-[A-F]`（非 `RC-[A-E]`）
- `CLUSTER_ANIMA_AFFINITY` 必須覆蓋所有 6 個 Tier（含 F tier → "li"/覺察）
- `get_tier_scores()` 的 `tier_map` 必須包含 "F" key
- `select_loop()` 必須有 F tier 路由規則（F tier → EXPLORATION_LOOP）
- 不匹配的直接修正路由表

### 6A-4. Skill 載入器相容性
- `agent/skills.py`（SkillLoader）解析邏輯
- vs 所有 SKILL.md 實際格式（frontmatter 欄位名稱、必填欄位）

---

## Round 6B：服務連動

**檢查手段**：Read + Grep

### 6B-1. MCP Server
- `src/museon/mcp_server.py` tool 定義 vs `data/_system/mcp/` 配置
- 工具名稱、參數一致性

### 6B-2. Telegram Bot
- `channels/telegram.py` command handler 列表
- `governance/telegram_guard.py` 權限檢查列表
- 兩者指令清單同步

### 6B-3. Gateway 端口與路由
- `gateway/server.py` 預設端口
- `electron/main.js` / `electron/src/app.js` 連接端口
- `cron.py` / `pulse/` 呼叫端口
- 全部統一

### 6B-4. LLM Client 配置
- `llm/client.py` + `llm/router.py` 支援的 model
- `llm/adapters.py` adapter 列表
- 新增 model 但遺漏 adapter → 補上

---

## Round 6C：資料層完整性

**檢查手段**：Read + 路徑驗證

### 6C-1. 記憶系統路徑
- `memory/memory_manager.py` 讀寫目錄 vs 實際 `data/memory/`、`data/memory_v3/`
- `memory/storage_backend.py` backend 路徑
- `data/vector/` 是否存在
- 缺失目錄直接建立

### 6C-2. 日誌路徑
- `core/activity_logger.py` 寫入路徑 vs `logs/` 目錄
- 日誌 rotation 設定合理性

### 6C-3. 狀態檔案完整性
- `data/ANIMA_MC.json`、`data/ANIMA_USER.json` 結構 vs 程式碼讀取邏輯
- `data/ceremony_state.json` 結構
- `data/_system/state/` 狀態檔案

### 6C-4. Agent 訊息格式
- `gateway/message.py` Pydantic Model 定義
- `channels/*.py` 建構的訊息
- `agent/dispatch.py` 期望的格式
- 三者欄位對齊，不一致的以 Model 定義為準修正

---

## Round 6D：外向型進化引擎完整性

**檢查手段**：Read + Grep + 交叉比對 + 單元測試

> 此輪專門檢查外向型進化引擎（OutwardTrigger → IntentionRadar → DigestEngine）
> 三模組之間以及與現有子系統之間的連動完整性。

### 6D-1. 觸發器事件訂閱鏈

**上游（誰餵信號給 OutwardTrigger）**：
- `eval_engine.py` 的 `scan_blindspots()` 是否在偵測到盲點時 publish `SKILL_QUALITY_SCORED`
  - 驗證：`EvalEngine.__init__()` 接受 `event_bus` 參數
  - 驗證：publish 的 payload 含 `blind_spots` 陣列，每項含 `domain`、`skill`、`detail`
  - 驗證：Nightly Pipeline 建構 EvalEngine 時有傳入 `event_bus`
- `feedback_loop.py` 是否 publish `USER_FEEDBACK_SIGNAL`
  - 驗證：payload 含 `direction`（"declining"/"improving"）、`delta`（float）

**中游（OutwardTrigger 內部路由）**：
- `_on_skill_quality()` → 生成 `domain_gap` 信號 → `_handle_realtime_signal()` → HIGH 走 `_execute_immediate()`，NORMAL 存 `pending_signals.json`
- `_on_feedback_signal()` → declining + delta > `QUALITY_DECLINE_DELTA` → HIGH 走 `_execute_immediate()`
- `scan()` 凌晨入口 → `_check_plateau()` + `_check_architecture_bottleneck()` + `_check_rhythmic()` + `_process_pending_signals()` + `_check_behavior_shift()`

**下游（OutwardTrigger 餵給誰）**：
- `_execute_immediate()` 呼叫 IntentionRadar → ResearchEngine → DigestEngine 完整管線
- `event_bus.publish(OUTWARD_SEARCH_NEEDED, event)` → IntentionRadar._on_search_needed() 訂閱

### 6D-2. 意圖雷達查詢生成

- `QUERY_TEMPLATES_SELF`（plateau/architecture/rhythmic）和 `QUERY_TEMPLATES_SERVICE`（pain/curiosity/failure）6 類模板是否齊全
- `generate_queries(event)` 依 `event["track"]` 分流選模板，確認 "self" → SELF 模板、"service" → SERVICE 模板
- 模板變數填充（`{skill_name}`、`{domain}`、`{year}`、`{month}` 等）不可殘留未填充的 `{xxx}`
- `search_plan.json` 讀寫路徑一致性
- `MAX_QUERIES_PER_EVENT` 限制是否正確生效
- `_is_duplicate_query()` 去重邏輯是否正確（避免重複搜尋）

### 6D-3. 消化引擎生命週期

**進食（Ingest）**：
- `ingest()` 先呼叫 `_sanitize_content()` 檢查注入攻擊
  - 驗證：`InputSanitizer` import 路徑正確
  - 驗證：sanitizer 偵測到威脅時 return None（不存入隔離區）
- 新建 crystal 的初始值：`confidence = INITIAL_CONFIDENCE (0.3)`、`trial_count = 0`、`status = "quarantined"`

**試用（Trial）**：
- `record_trial(quarantine_id, success)` 正確更新 `trial_count`、`success_count`/`failure_count`、`confidence`
- confidence 更新公式：成功 `+CONFIDENCE_SUCCESS_DELTA (0.1)`、失敗 `-CONFIDENCE_FAILURE_DELTA (0.15)`
- 發布 `OUTWARD_TRIAL_RECORDED` 事件

**固化（Promote）— 雙軌分流**：
- 晉升條件三重門檻同時滿足：
  - `trial_count >= PROMOTE_MIN_TRIALS (3)`
  - `success_rate >= PROMOTE_MIN_SUCCESS_RATE (0.6)`
  - `confidence >= PROMOTE_MIN_CONFIDENCE (0.7)`
- Track A（`origin == "outward_self"`）→ `_create_morphenix_proposal()` → 寫入 `_system/morphenix/notes/` → 發布 `OUTWARD_SELF_CRYSTALLIZED`
- Track B（`origin == "outward_service"`）→ `_write_to_knowledge_lattice()` → 呼叫 `KnowledgeLattice.add_crystal()` → 發布 `OUTWARD_SERVICE_CRYSTALLIZED`
  - 驗證：`add_crystal()` 收到的 `crystal_data` 含必填欄位（`crystal_type`、`g1_summary`、`origin`、`verification_level`）
  - 驗證：`origin = "outward_service"` 不可遺漏

**淘汰（Demote/Archive）**：
- 淘汰條件：`confidence < DEMOTE_MIN_CONFIDENCE (0.15)` 或 `failure_count >= DEMOTE_MAX_CONSECUTIVE_FAILS (3)` 或 `quarantine_days > MAX_QUARANTINE_DAYS (90)`
- 歸檔後發布 `OUTWARD_KNOWLEDGE_ARCHIVED` 事件

**相關性掃描**：
- `scan_for_relevance(query_text)` 純 CPU（SequenceMatcher + 關鍵字重疊）
- 匹配分數 > `RELEVANCE_MATCH_THRESHOLD (0.4)` 才回傳

### 6D-4. Nightly Pipeline 整合

- `_step_map` 中是否包含 `"13.6"`、`"13.7"`、`"13.8"` 三個 key
- `_FULL_STEPS` 列表中這三步的順序：`"13.5"` → `"13.6"` → `"13.7"` → `"13.8"` → `"14"`
- 各步驟實作方法存在且可呼叫：
  - `_step_outward_trigger_scan()` → 呼叫 `OutwardTrigger.scan()`，回傳 `{"triggered": int}`
  - `_step_outward_research()` → 呼叫 IntentionRadar + ResearchEngine + DigestEngine
  - `_step_digest_lifecycle()` → 呼叫 `DigestEngine.lifecycle_scan()`
- **降級模式**：`_get_degraded_steps()` 的 skip set 必須包含 `"13.6"`、`"13.7"`、`"13.8"`（Health Score 40-70 時不花錢做外向搜尋）
- **最小模式**：Health Score < 40 時這三步也不執行

### 6D-5. 防洪機制一致性

- `DAILY_OUTWARD_CAP = 3`：跨 `outward_trigger.py`、測試檔案的值一致
- `DIRECTION_COOLDOWN_DAYS = 7`：跨模組一致
- 每日配額在即時管線 + 凌晨批次之間**共享**（同一個 `daily_counter.json`）
- 跨日重置邏輯：`_reset_daily_counter_if_needed()` 比較 Taipei 時區（UTC+8）日期
- 方向冷卻：`_direction_hash(signal)` 產生唯一鍵 → 7 天內同 hash 不重複觸發

### 6D-6. Crystal 狀態擴展向後相容

- `knowledge_lattice.py` Crystal dataclass 的 `origin` 欄位有預設值（`origin: str = ""`）
  - 驗證：現有 Crystal（無 origin 欄位）載入時不報錯
- `Crystal.status` 新增值 `"quarantined"` 和 `"provisional"` 不影響現有狀態流轉
  - 驗證：`from_dict()` 處理未知欄位時不 crash（graceful handling）
- `ResearchEngine` 新增 `context_type` 值 `"outward_self"` 和 `"outward_service"`
  - 驗證：`_FILTER_PROMPTS` dict 包含這兩個 key
  - 驗證：`_build_round_query()` 中對應的 suffix 存在

### 6D-7. 安全層整合

- DigestEngine.ingest() 必須在存入隔離區**之前**呼叫 `_sanitize_content()`
- `_sanitize_content()` 使用 `InputSanitizer` 的注入偵測模式（prompt injection、role-playing、tag injection 等 7 層）
- 隔離區結晶（`quarantine.json`）不進入正式 Knowledge Lattice DAG 圖
- 固化前（`_promote()`）應再跑一次 sanitizer 全掃（若缺少則標記為 🏗️）
- 外部搜尋結果的 `origin` 標記不可被修改（"outward_self"/"outward_service" 一旦設定不可覆寫）

---

## Round 6E：系統黏合層完整性（Glue Layer Integrity）

**檢查手段**：Read + Grep + 交叉比對

> 此輪專門檢查所有「模組獨立開發但黏合層斷裂」的問題。
> 模組各自能跑，但模組之間的 `.start()`、`.register()`、`.connect()`、EventBus 訂閱/發布
> 沒有在 Gateway 啟動流程中正確串接，導致功能靜默失效。
>
> **四大斷裂模式**：
> 1. **物件已建但未啟動/註冊**：`bridge = ProactiveBridge(...)` 建了，但沒有 `engine.register()` + `engine.start()`
> 2. **EventBus 事件鏈斷裂**：事件在 `event_bus.py` 定義了，但 publish 端或 subscribe 端缺一邊
> 3. **假成功日誌**：啟動時印了 `"✅ XXX initialized"`，但實際功能管線未連通
> 4. **執行期依賴缺失**：程式碼 import 了某模組（如 `aiohttp`），但 `pyproject.toml` 未宣告

### 6E-1. Gateway 啟動流程模組串接驗證

**檢查 `gateway/server.py` 啟動流程中每個模組的完整生命週期**：

對以下每個子系統，驗證三步驟 **建構 → 註冊/連接 → 啟動** 是否齊全：

| 子系統 | 建構 | 註冊/連接 | 啟動 |
|--------|------|-----------|------|
| HeartbeatEngine | `get_heartbeat_engine()` | `proactive_bridge.register_with_engine(engine)` | `engine.start()` |
| ProactiveBridge | `ProactiveBridge(brain=..., event_bus=...)` | 註冊到 HeartbeatEngine | — (由 HeartbeatEngine tick 驅動) |
| EventBus | `get_event_bus()` | 各模組 subscribe | — (被動) |
| ActivityLogger | `ActivityLogger(...)` | subscribe 所有事件 | — (被動) |
| VitalSignsMonitor | `VitalSignsMonitor(...)` | `run_preflight()` | — |
| Telegram Channel | `TelegramChannel(...)` | subscribe `PROACTIVE_MESSAGE` | `start()` / `start_polling()` |
| NightlyPipeline | `NightlyPipeline(...)` | — | 由 cron 觸發 |
| WEE Engine | `WeeEngine(...)` | — | 由 NightlyPipeline 呼叫 |
| SurgeryEngine | `SurgeryEngine(project_root, auto_restart)` | — | 由 ToolExecutor 建構，API/Brain 工具觸發 |
| DiagnosisPipeline | `DiagnosisPipeline(...)` | — | 由 ToolExecutor 按需建構 |
| Guardian L5 | `brain._guardian.run_l5()` | — | 由 cron 每 6 小時觸發（純 CPU） |

**驗證規則**：
- 每個模組若需要 `event_bus`，檢查建構時是否有傳入
- 每個模組若需要 `brain`，檢查建構時是否有傳入
- 每個有 `start()` 方法的模組，檢查是否有被呼叫
- 每個需要註冊到其他模組的（如 ProactiveBridge → HeartbeatEngine），檢查是否有 `register_with_engine()`
- 任何 `app.state.xxx = Module(...)` 後面沒有對應的連接/啟動碼 → 標記為 CRITICAL

### 6E-2. EventBus 事件鏈完整性

**對 `core/event_bus.py` 中定義的每一個事件常數**，驗證：

1. **Publish 端**：Grep 所有 `.publish(EVENT_NAME, ...)` — 是否存在至少一處
2. **Subscribe 端**：Grep 所有 `.subscribe(EVENT_NAME, ...)` — 是否存在至少一處
3. **交叉比對**：

| 狀態 | 定義 | 判定 |
|------|------|------|
| 有 publish + 有 subscribe | 正常 ✅ | — |
| 有 publish + 無 subscribe | 警告 ⚠️ | 事件被發出但沒人聽，可能是遺漏 subscribe |
| 無 publish + 有 subscribe | 嚴重 🔴 | 訂閱者永遠收不到事件，功能靜默失效 |
| 無 publish + 無 subscribe | 資訊 ℹ️ | 事件定義了但未使用，可能是預留或遺忘 |

**重點事件鏈（已知曾斷裂，必須每次驗證）**：
- `PULSE_PROACTIVE_SENT`：`channels/telegram.py` publish → ActivityLogger subscribe
- `PULSE_EXPLORATION_DONE`：`pulse/pulse_engine.py` publish → ActivityLogger subscribe
- `MORPHENIX_EXECUTED`：`nightly/morphenix_executor.py` publish → ActivityLogger subscribe
- `MORPHENIX_PROPOSAL_CREATED`：`nightly/nightly_pipeline.py` publish → ActivityLogger subscribe
- `WEE_CYCLE_COMPLETE`：`evolution/wee_engine.py` publish → ActivityLogger subscribe
- `CRYSTAL_CREATED`：`agent/knowledge_lattice.py` publish → ActivityLogger subscribe
- `SOUL_RING_DEPOSITED`：`agent/soul_ring.py` publish → ActivityLogger subscribe
- `PROACTIVE_MESSAGE`：`pulse/proactive_bridge.py` publish → `channels/telegram.py` subscribe

**注意區分同功能但不同名稱的事件**：
- `MORPHENIX_EXECUTION_COMPLETED`（executor 內部完成信號）≠ `MORPHENIX_EXECUTED`（對外通知信號）
- 兩者可能需要同時存在，各有各的 subscriber

**已知死訂閱事件（Subscribe-Only，功能已由替代事件覆蓋）**：
- `PULSE_RHYTHM_CHECK`：`channels/telegram.py` subscribe（L818）→ **無 publish 端**
  - 功能由 `PROACTIVE_MESSAGE` 覆蓋（ProactiveBridge → Telegram 推送）
  - 🏗️ 決策：移除死訂閱，或在 HeartbeatEngine 中補 publish
- `PULSE_NIGHTLY_DONE`：`channels/telegram.py` subscribe（L819）→ **無 publish 端**
  - 功能由 `NIGHTLY_COMPLETED` 覆蓋（NightlyPipeline → ProactiveBridge 上下文注入）
  - 🏗️ 決策：移除死訂閱，或在 NightlyPipeline 完成時補 publish

**6E-2 誤報防禦指引**：
> 歷次審計中 6E-2 容易產生以下誤報，檢查時需注意：
> 1. **ActivityLogger 訂閱**：`gateway/server.py` L2992-3006 使用 `getattr` 動態訂閱 12 個事件。
>    grep `.subscribe()` 時可能漏掉這段動態訂閱，導致這些事件被錯誤標記為 PUBLISH_ONLY。
>    **必須檢查 `_log_events` 清單**。
> 2. **被動模組無 start()**：以下模組**設計上不需要 start()**，不應標記為缺陷：
>    - `ActivityLogger`（被動事件訂閱）
>    - `ProactiveBridge`（由 HeartbeatEngine tick 驅動）
>    - `PulseEngine`（被動工具類，由 cron/API 觸發）
>    - `SurgeryEngine` / `DiagnosisPipeline`（按需建構，由 Brain 工具觸發）
> 3. **Guardian L5 存在**：位於 `guardian/daemon.py:run_l5()` + `gateway/server.py` cron 排程。
>    不是獨立模組，是 Guardian daemon 的方法。

### 6E-3. 假成功日誌偵測

**掃描 `gateway/server.py` 中所有 `logger.info(...)` 包含以下關鍵字的行**：
- `initialized`、`connected`、`started`、`ready`、`activated`、`registered`

**對每一條假成功日誌，驗證**：
1. 日誌所聲稱的功能是否**在該行之前**已經完成了所有必要的連接步驟
2. 是否有對應的 `try/except`，在連接失敗時印 `logger.error(...)` 而非靜默跳過
3. 日誌訊息是否**精確描述**實際完成的步驟（不能只說 "initialized" 而實際只做了 `= Module(...)`）

**修復規則**：
- 假成功日誌 → 改為精確描述（例如 `"ProactiveBridge created"` 而非 `"ProactiveBridge connected"`）
- 缺少失敗日誌 → 補上 `except` 分支的 `logger.error(...)`

### 6E-4. 執行期依賴完整性

**掃描 `src/museon/**/*.py` 中所有 `import` 語句**，排除標準庫模組後：

1. 每個第三方 import（如 `aiohttp`、`httpx`、`anthropic`、`pydantic`）是否在 `pyproject.toml` 的 `[project.dependencies]` 中宣告
2. 每個宣告的依賴是否實際可 import（`python -c "import xxx"`）

**重點依賴（已知曾缺失）**：
- `aiohttp`：Telegram 推送依賴
- `httpx`：HTTP 客戶端
- `anthropic`：LLM API

### 6E-4b. CronEngine 超時保護驗證（DSE 2026-03 迭代教訓）

> **根因**：cron 排程的 async job 若卡死（如外部 API 無回應），會永遠佔住 event loop。
> （Fix 8: 所有 async cron job 現已包裝 `asyncio.wait_for` 超時保護）

**驗證規則**：
- `gateway/cron.py` 的 `CronEngine.add_job()` 必須呼叫 `_wrap_with_timeout(func, timeout, job_id)` 包裝所有 async 函式
- 預設超時值：cron 觸發 = 600s（10 分鐘）、interval 觸發 = 120s（2 分鐘）
- `_wrap_with_timeout()` 必須：
  - 使用 `asyncio.wait_for(func(), timeout=timeout)` 執行
  - `TimeoutError` → `logger.error()` 記錄（不 raise，避免 crash scheduler）
  - 一般 `Exception` → `logger.debug()` 記錄
  - 同步函式不包裝（直接 return）
- `timeout=0` 時必須跳過包裝（允許停用超時保護）
- 驗證 `gateway/server.py` 中所有 `cron_engine.add_job()` 呼叫是否有合理的 timeout 參數

### 6E-4c. 工具自癒機制驗證（DSE 2026-03 迭代教訓）

> **根因**：工具健康檢查只會報告 degraded 狀態，不會嘗試恢復。
> 工具持續失敗時使用者完全不知道。
> （Fix 7: 加入三階段自癒 — 記數 → 自動重啟 → 升級通知）

**驗證規則**：
- `gateway/server.py` 的 `_tool_health_check_job()` 必須實作：
  1. **失敗計數**：`_tool_fail_counts` dict 追蹤每個工具的連續失敗次數
  2. **自動重啟**（閾值 = 3 次連續失敗）：`registry.toggle_tool(name, False)` → sleep → `registry.toggle_tool(name, True)`
  3. **升級通知**（閾值 = 6 次連續失敗）：透過 Telegram adapter 發送降級通知給使用者
  4. **恢復重置**：工具恢復健康時重置計數器為 0 + 記錄恢復日誌
- 驗證 Telegram adapter 取得使用 `getattr(app.state, "telegram_adapter", None)` + None 守衛
- 通知失敗不可中斷健康檢查流程

### 6E-5. Preflight 涵蓋率驗證

**檢查 `governance/vital_signs.py` 的 `run_preflight()` 方法**：

每個在 Gateway 啟動流程中初始化的子系統，是否都有對應的 Preflight Check：

| 子系統 | Preflight Check 名稱 | 驗證內容 |
|--------|----------------------|----------|
| Brain | `brain_health` 或類似 | Brain 可呼叫 LLM |
| HeartbeatEngine | `proactive_pipeline` | singleton 已建 + running + ProactiveBridge 已註冊 |
| Telegram Channel | `telegram_connection` 或類似 | Bot token 有效 + 可送訊息 |
| EventBus | — | 事件鏈完整性（可選） |
| Memory | `memory_health` 或類似 | 記憶路徑可讀寫 |

**缺少 Preflight Check 的子系統 → 新增對應檢查方法**

### 6E-6. 新模組黏合清單（擴展指引）

> 未來新增任何模組時，必須確認以下黏合步驟完成：

```
☐ 1. 模組在 gateway/server.py 啟動流程中被 建構 + 連接 + 啟動
☐ 2. 模組若使用 EventBus，所有 publish 的事件有對應 subscribe
☐ 3. 模組若使用 EventBus，所有 subscribe 的事件有對應 publish
☐ 4. 模組的啟動成功日誌精確描述實際完成的步驟
☐ 5. 模組的啟動失敗有 logger.error 記錄
☐ 6. 模組的第三方依賴已加入 pyproject.toml
☐ 7. 模組有對應的 Preflight Check（若為關鍵子系統）
☐ 8. ActivityLogger 已 subscribe 模組發出的所有事件
```

---

## Round 6F：自我手術系統完整性

**檢查手段**：Read + Grep + 交叉比對 + 單元測試

> 此輪專門檢查自我手術系統（CodeAnalyzer → DiagnosisPipeline → SurgeryEngine）
> 三層架構之間以及與現有子系統之間的連動完整性。

### 6F-1. SurgeonSandbox 安全邊界驗證

**FORBIDDEN_FILES 清單完整性**：
- `surgeon.py` 中 `SurgeonSandbox.FORBIDDEN_FILES` 必須包含以下檔案（不可被手術修改）：
  - `morphenix_standards.py`
  - `morphenix_executor.py`
  - `kernel_guard.py`
  - `drift_detector.py`
  - `safety_anchor.py`
- 驗證：手術提案涉及 FORBIDDEN_FILES 時，`_check_sandbox()` 必須拒絕

**FORBIDDEN_DIRS 目錄保護**：
- `security/` 和 `guardian/` 目錄下的檔案不可被手術修改
- 驗證：`SurgeonSandbox.is_writable(path)` 對 FORBIDDEN_DIRS 下的路徑回傳 False

**讀寫範圍**：
- `READABLE_ROOTS` 覆蓋 `src/museon/` 下所有 `.py`
- `WRITABLE_ROOTS` 覆蓋 `src/museon/`（排除 FORBIDDEN_FILES 和 FORBIDDEN_DIRS）
- 驗證：SurgeonSandbox 與 PathSandbox（`data/workspace/`）完全分離，互不干擾

### 6F-2. 手術速率限制

**日限 + 間隔 + 規模限制一致性**：
- 每日手術上限：3 次
- 最小間隔：60 分鐘
- 單次最大影響檔案：3 個（與 morphenix_standards S1 相容）
- 單次最大修改行數：50 行
- 驗證：以上限制值在 `surgeon.py` 中定義且在 `execute_surgery()` 中正確檢查
- 驗證：超限時 `execute_surgery()` 回傳失敗結果而非靜默跳過

### 6F-3. 10 步手術流程完整性

驗證 `SurgeryEngine.execute_surgery()` 包含完整 10 步流程：

| 步驟 | 名稱 | 驗證要點 |
|------|------|---------|
| 1 | Trigger | 接收 CodeIssue/DiagnosisResult |
| 2 | Diagnose | D3 LLM 根因分析（可選） |
| 3 | Propose | 生成 SurgeryProposal（affected_files, diff） |
| 4 | SafetyReview | 呼叫 `morphenix_standards.review_proposal()` |
| 5 | Snapshot | `git tag morphenix/pre-surgery-{id}-{timestamp}` |
| 6 | Apply | 複用 morphenix_executor 模式（text_replace / git_patch） |
| 7 | Sync | rsync src/ → .runtime/src/ |
| 8 | Restart | 三策略降級（Electron IPC → launchd → pending marker） |
| 9 | Verify | 重啟後健康檢查 + 問題消失確認 |
| 10 | Complete | 成功記錄 / 失敗 git checkout 回滾 |

- 每步之間發布對應 EventBus 事件（SURGERY_TRIGGERED → SAFETY_PASSED/FAILED → COMPLETED/FAILED/ROLLBACK）
- SafetyReview 失敗時立即中止，不進入 Apply

### 6F-4. morphenix_standards 安全審查整合

- `surgeon.py` 呼叫 `review_proposal()` 時傳入格式正確的 proposal 物件
- `review_proposal()` 回傳 `(passed: bool, violations: list, recommendation: str)`
- **硬性規則違反**（如修改 FORBIDDEN_FILES）→ `passed = False` → 手術中止 + publish `SURGERY_SAFETY_FAILED`
- **軟性規則違反**（如 `escalate_l3`）→ `passed = True` + `violations` 含警告 → 手術繼續 + 記錄警告
- 驗證：`escalate_l3` 不會導致手術被拒絕（上次 bug 修復的回歸測試）

### 6F-5. 手術記錄持久化

- `surgery_log.py` 的 `SurgeryLog` class 提供完整 CRUD：
  - `create(surgery_id, trigger, ...)` — 建立記錄
  - `update(surgery_id, ...)` — 更新進度
  - `complete(surgery_id, result, ...)` — 完成/失敗記錄
  - `get(surgery_id)` — 查詢單筆
  - `list_recent(n)` — 查詢最近 n 筆
- 持久化路徑：`data/doctor/surgery_log.json`
- 記錄格式含必填欄位：`id`、`trigger`、`diagnosis`、`proposal`、`safety_review`、`result`、`timestamp`
- 驗證：`execute_surgery()` 在每個步驟正確呼叫 SurgeryLog 生命週期方法

### 6F-6. DiagnosisPipeline 三層管線

**D1 靜態分析**：
- `CodeAnalyzer` 的 8 條 AST 規則（CA001~CA008）全部可執行
- `scan_all()` 掃描範圍 = `src/museon/` 下所有 `.py`（排除 `__pycache__`）
- 每條規則一個 visitor class，回傳 `List[CodeIssue]`

**D2 動態探測**：
- `LogAnalyzer.analyze(lookback_hours)` 掃描 `logs/` 下的 `.log` 檔案
- 錯誤頻率突增偵測（滑動窗口）
- 重複錯誤模式識別

**D3 LLM 輔助**：
- 僅當 D1/D2 發現問題時才觸發（零問題不消耗 Token）
- 使用 ClaudeCLIAdapter 呼叫 `claude -p` 子進程
- 3600s timeout 設定正確

**管線控制**：
- `run()` 方法依序執行 D1 → D2 → D3
- 完成後 publish `SELF_DIAGNOSIS_COMPLETED` 事件
- 回傳 `DiagnosisResult` 含 `code_issues`、`log_anomalies`、`diagnosis_level`

### 6F-7. Brain 工具完整性

**7 個手術工具全部在以下位置註冊一致**：
- `tool_schemas.py`：Schema 定義（name、description、parameters）
- `tools.py`：`ALLOWED_TOOLS` 白名單 + `_dispatch()` 路由 + 執行方法

| 工具名 | Schema | 白名單 | 路由 | 執行方法 |
|--------|--------|--------|------|---------|
| `source_read` | ✓ | ✓ | ✓ | `_execute_source_read()` |
| `source_search` | ✓ | ✓ | ✓ | `_execute_source_search()` |
| `source_ast_check` | ✓ | ✓ | ✓ | `_execute_source_ast_check()` |
| `surgery_diagnose` | ✓ | ✓ | ✓ | `_execute_surgery_diagnose()` |
| `surgery_propose` | ✓ | ✓ | ✓ | `_execute_surgery_propose()` |
| `surgery_apply` | ✓ | ✓ | ✓ | `_execute_surgery_apply()` |
| `surgery_rollback` | ✓ | ✓ | ✓ | `_execute_surgery_rollback()` |

- 任何一處缺失 → 補齊
- `source_read` 和 `source_search` 使用 SurgeonSandbox 唯讀權限
- `surgery_apply` 使用 SurgeonSandbox 寫入權限 + SafetyReview 前置檢查

### 6F-8. 回滾機制驗證

- `surgery_rollback` 工具可回滾到 `git tag morphenix/pre-surgery-*` 快照
- 回滾後 publish `SURGERY_ROLLBACK` 事件
- 回滾後自動觸發 rsync 同步 + 重啟（與 Apply 相同的 Sync + Restart 流程）
- 驗證：回滾不會破壞非手術相關的 uncommitted changes

---

## Round 7：測試驗證

### 7A. 測試可執行性
- `pytest tests/unit/ -x --tb=short` — 全部通過
- 外向型進化引擎專項測試（65 tests）：
  - `pytest tests/unit/test_outward_trigger.py -v` — 18 tests（基本功能、防洪、即時直通、凌晨批次、持久化）
  - `pytest tests/unit/test_intention_radar.py -v` — 13 tests（模板、查詢生成、計畫管理、去重）
  - `pytest tests/unit/test_digest_engine.py -v` — 34 tests（常數、進食、試用、相關性、生命週期、晉升、持久化、統計）
- 自我手術系統專項測試：
  - `pytest tests/unit/test_code_analyzer.py -v` — CA001~CA008 八條 AST 規則（正例+反例）
  - `pytest tests/unit/test_tool_use.py -v` — 19 個工具白名單 + 7 個手術工具名稱驗證
  - `pytest tests/unit/test_nightly_pipeline.py -v` — 37 步 pipeline 步驟數驗證
- 失敗的測試：判斷是程式碼問題還是測試過時
  - 程式碼問題 → 修程式碼
  - 測試過時 → 更新測試以匹配當前程式碼

#### 7A 已知測試-源碼漂移模式（每次檢查必看）

> 以下是歷次審計中反覆出現的「測試過時」根因模式。
> 每輪 7A 發現失敗測試時，**優先比對此清單**，可快速定位問題。

| # | 漂移模式 | 典型症狀 | 修復原則 |
|---|---------|---------|---------|
| D1 | **方法回傳結構重構** | 源碼從舊結構（如含 `"skipped"` 字串）改為新 dict（如 `{"proposals_created": 0}`），測試還在用 `assert "skipped" in result` | 以當前源碼回傳結構為準，更新 assert 條件 |
| D2 | **常數計數增減** | 新增/移除集合元素（如 `COLLECTIONS` 新增 `documents`），測試硬寫 `assert len(X) == 5` | 改用 `len(COLLECTIONS)` 或 `len(X) - len(existing)` 等動態表達式，避免硬編碼數字 |
| D3 | **欄位名稱重命名** | 源碼重命名欄位（如 `source_notes` 從 result 移入子物件），測試還在用舊 key | 以源碼 return 語句為準，更新測試的 key 存取路徑 |
| D4 | **信號驅動重構** | 原本依賴特定目錄/檔案存在的邏輯（如 notes 目錄）改為多信號源掃描，測試仍基於舊前提 | 重新理解函式行為，依新邏輯設計 setup 資料與斷言 |

| D5 | **物件存在性假設** | 源碼新增模組但初始化有條件分支（如 Telegram adapter 可能未啟動），callback 中直接呼叫 `self.xxx.method()` 而未檢查 `self.xxx is not None` | 所有 callback/cron handler 中使用的可空物件，入口加 `if not obj: return` 守衛 |
| D6 | **品質閘門過度簡化** | 品質/嚴重度分級只有 2 級（pass/fail 或 tier 1/2），高頻+高影響的問題無法區分處理 | 至少 3 級分級（低/中/高 或 自動修復/LLM 研究/人工介入） |
| D7 | **目錄不存在靜默崩潰** | 模組寫入檔案但 parent 目錄從未建立，首次啟動或資料清除後 `FileNotFoundError` | 所有 `write_text()` / `open(w)` 前確認 `parent.mkdir(parents=True, exist_ok=True)` |
| D8 | **RC 叢集擴展不同步** | 新增 RC tier（如 F tier）但 regex、affinity map、tier_map、loop routing 未全部更新 | 新增 tier 時必須同步更新：`_RC_PATTERN`、`ALL_CLUSTERS`、`CLUSTER_ANIMA_AFFINITY`、`get_tier_scores()`、`select_loop()`、`build_routing_context()` |

**防禦建議**：
- 每次迭代修改函式回傳結構或新增集合元素時，`grep -rn` 搜尋該函式/常數在 `tests/` 中的引用，同步更新
- 測試中避免硬寫集合大小（`== 5`），改用源碼定義的常數（`== len(COLLECTIONS)`）
- **新增（DSE 2026-03）**：每次迭代後，對修改的模組執行以下快速掃描：
  - `grep -rn "self\.\w\+\." <file>` — 檢查是否有物件方法呼叫缺少 None 守衛
  - `grep -rn "write_text\|open.*'w'" <file>` — 檢查是否有寫入缺少 mkdir 保護
  - `grep -rn "RC-[A-F]" src/museon/agent/` — 確認 RC 叢集範圍一致性

### 7B. 測試與源碼對應
- `tests/unit/test_*.py` vs 對應源碼模組
- 有源碼無測試的標記為 🏗️

### 7C. BDD Feature 對應
- `features/*.feature` vs `tests/bdd/` step definition
- 有 feature 無 step 的標記為 🏗️

---

## 結案動作

全部 Round 通過後：

1. 執行 `python -m museon.doctor.system_audit --home /Users/ZEALCHOU/MUSEON`
2. 與 Round 0 基準做差異比較
3. 輸出總結報告：

```
# MUSEON 完整性檢查 — 最終報告

## 總覽
- 執行輪次：Round 0 ~ Round 7（含 Round 6A/6B/6C/6D/6E/6F）
- 重跑總次數：XX 次
- 總計發現問題：XX 項
- 自動修復：XX 項
- 架構級標記（🏗️）：XX 項

## 各輪摘要
| Round | 檢查項 | 發現 | 修復 | 重跑次數 |
|-------|--------|------|------|----------|
| 0 | 基準快照 | — | — | 0 |
| 1 | 檔案結構 | X | X | X |
| 2 | 語法與格式 | X | X | X |
| 3 | 模組間連動 | X | X | X |
| 4 | 邏輯與流程 | X | X | X |
| 5 | 設定與依賴 | X | X | X |
| 6A | Skill 生態系 | X | X | X |
| 6B | 服務連動 | X | X | X |
| 6C | 資料層 | X | X | X |
| 6D | 外向型進化引擎 | X | X | X |
| 6E | 系統黏合層 | X | X | X |
| 6F | 自我手術系統 | X | X | X |
| 7 | 測試驗證 | X | X | X |

## 修改檔案清單
（附 git diff --stat 摘要）

## 架構級待辦（🏗️）
（需要人類決策的項目清單）
```

4. `say "MUSEON integrity check complete"`

---

## 全自動啟動指令

將以下內容作為單一 prompt 發送給 Claude：

```
對 ~/MUSEON/ 執行完整性檢查，規則見 docs/integrity-check-prompt.md。

全自動模式：
- 從 Round 0 開始，依序執行到 Round 7
- 發現問題立即修復，不要停下來問我
- 每輪跑到零錯誤才進入下一輪，無重跑次數上限
- 唯一停止條件：全部 Round 通過，或遇到需要我提供資訊的阻斷點
- 每輪結束時輸出結果摘要表格
- 全部完成後輸出最終報告並執行 say 通知
```
