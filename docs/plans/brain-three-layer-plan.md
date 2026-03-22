# Brain 三層治療計畫 — 2026-03-22

> **前置文件**：`~/.claude/projects/-Users-ZEALCHOU-Claude-Code/memory/brain-health-check-2026-03-22.md`
> **觸發原因**：Brain 健康檢查發現三個表象問題 → DSE 追溯到三個結構性疾病
> **策略**：止血 → 免疫 → 根治，每層獨立 commit，每層完成後跑 pytest + 審計

---

## 術語對照

| 結構性疾病 | 表象問題 | 治療層 |
|-----------|---------|--------|
| 隱性狀態隧道（7 個 `self._*` per-turn 變數無型別合約） | P0: `metadata` NameError | L1 止血 + L2 ChatContext + L3 Brain 拆分 |
| catch-all 毯式吞錯（146 個 `except Exception`） | Bug 靜默降級半天才被發現 | L1 止血 + L2 分級審計 + L3 分級執行 |
| LLM 作為控制流路由（Orchestrator 51% 失敗率） | P1: Dispatch fallback | L1 解析增強 + L2 診斷數據 + L3 確定性路由 |

---

## L1：止血（修表象，最小變動）

> **原則**：不改函數簽名、不改 `__init__()` 順序、不新增 import、不新增共享狀態
> **影響範圍**：brain.py 內部，扇入扇出不變
> **預計時間**：30 分鐘
> **Commit 策略**：單獨一個 commit

### L1-1: Memory inject NameError 修復

**檔案**：`src/museon/agent/brain.py`
**位置**：Line 3624
**變更**：

```python
# Before:
if self._is_group_session and metadata:
    _gid = metadata.get("group_id", "")

# After:
if self._is_group_session and self._current_metadata:
    _gid = self._current_metadata.get("group_id", "")
```

**漣漪檢查**：
- `_current_metadata` 在 `chat()` L519 設定，`_is_group_session=True` 時保證非 None ✅
- `memory_manager.recall()` 的 `chat_scope_filter` 已驗證安全（L320-323）✅
- 不改方法簽名、不改調用方式 ✅

### L1-2: Orchestrator JSON 解析增強

**檔案**：`src/museon/agent/brain.py`
**位置**：`_parse_orchestrator_response()` (Line 6609)
**變更**：在現有 regex 匹配前，增加 code fence 清理 + 單物件包裝

```python
def _parse_orchestrator_response(self, response_text, active_skills, plan_id):
    import re
    from museon.agent.dispatch import TaskPackage

    # L1-2: 清理 markdown code fences
    cleaned = response_text.strip()
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)

    # 原有邏輯：匹配 JSON 陣列
    json_match = re.search(r'\[[\s\S]*\]', cleaned)

    # L1-2: fallback — 嘗試匹配單一 JSON 物件，包成陣列
    if not json_match:
        obj_match = re.search(r'\{[\s\S]*\}', cleaned)
        if obj_match:
            try:
                obj = json.loads(obj_match.group())
                if "skill_name" in obj:
                    json_match = type('Match', (), {'group': lambda self: json.dumps([obj])})()
            except json.JSONDecodeError:
                pass

    if not json_match:
        logger.warning("Orchestrator 回覆中無 JSON 陣列")
        logger.debug(f"Orchestrator raw response: {response_text[:500]}")  # L1-3
        return []

    # ... 後續不變
```

**漣漪檢查**：
- `json.loads()` 作為最終守門，不會接受非法 JSON ✅
- `valid_names` 過濾仍在下游執行 ✅
- 不改方法簽名 ✅

### L1-3: Orchestrator 失敗診斷日誌

**已整合到 L1-2**：在 `json_match` 為 None 時，加 `logger.debug()` 記錄 LLM 回覆前 500 字。

### L1-4: Orchestrator prompt 尾部 JSON 約束

**檔案**：`src/museon/agent/brain.py`
**位置**：`_dispatch_orchestrate()` 的 system_prompt 組裝末尾（約 Line 6304）
**變更**：在 Rule 5 之後追加一行

```python
"5. 只回覆 JSON，不要其他文字\n"
"\n⚠️ 你的回覆必須以 [ 開頭，以 ] 結尾。除了 JSON 陣列本身，不要包含任何其他文字。\n"
```

**漣漪檢查**：
- 純新增文字，不修改既有 prompt 內容 ✅
- 利用 LLM recency bias 提高遵從率 ✅

### L1-5: RootCause 空字串日誌過濾

**檔案**：`src/museon/agent/brain.py`
**位置**：Line 1064-1065
**變更**：

```python
# Before:
if root_cause_hint:
    logger.info(f"[RootCause] 偵測到重複模式: {root_cause_hint[:100]}")

# After（已經有 if，但 root_cause_hint 可能是空字串）:
if root_cause_hint and root_cause_hint.strip():
    logger.info(f"[RootCause] 偵測到重複模式: {root_cause_hint[:100]}")
```

### L1 驗證清單

- [ ] `pytest tests/ -x` 無新增失敗
- [ ] 手動 Telegram 群組發訊確認記憶注入日誌不再出現 NameError
- [ ] blast-radius.md changelog 更新（純內部修正）

---

## L2：免疫（建立合約，防止同類問題再犯）

> **原則**：建立新的資料結構和標記系統，但不改變既有行為邏輯
> **影響範圍**：brain.py 內部重構 + 新檔案
> **預計時間**：2-3 小時
> **Commit 策略**：S1/S2/S3 各一個 commit，或合併一個
> **前置條件**：L1 完成且 pytest 通過

### S1: ChatContext Dataclass（消滅隱性狀態隧道）

**新增檔案**：`src/museon/agent/chat_context.py`

```python
"""ChatContext — Brain 每回合的顯式上下文物件.

消滅 self._current_metadata 等 7+ 個隱性 per-turn 變數，
改為顯式傳遞的 dataclass。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ChatContext:
    """單次 chat() 呼叫的完整上下文."""

    # ── 來源資訊 ──
    metadata: Optional[Dict[str, Any]] = None
    source: str = ""
    session_id: str = ""
    user_id: str = ""

    # ── 群組上下文 ──
    is_group_session: bool = False
    group_sender: str = ""

    @property
    def group_id(self) -> str:
        if self.metadata and self.is_group_session:
            return str(self.metadata.get("group_id", ""))
        return ""

    @property
    def chat_scope(self) -> str:
        """回傳 memory recall 用的 scope filter."""
        gid = self.group_id
        return f"group:{gid}" if gid else ""

    # ── 模式標記 ──
    skillhub_mode: Optional[str] = None  # "skill_builder" / "workflow_executor"
    self_modification_detected: bool = False

    # ── 收集器 ──
    pending_artifacts: List[Any] = field(default_factory=list)
```

**Brain 改造步驟**：

1. `chat()` 開頭：建立 `ctx = ChatContext(...)` 取代 7 個 `self._*` 設定
2. 逐一替換消費端：
   - `_build_memory_inject(self, ctx, ...)` — `ctx.chat_scope` 取代 `self._current_metadata`
   - `_build_system_prompt(self, ctx, ...)` — `ctx.is_group_session` 取代 `self._is_group_session`
   - 其他 ~15 個方法
3. **向後相容**：保留 `self._current_metadata = ctx.metadata` 等 alias 一段時間，待全部遷移完再移除

**漣漪分析**：
- `chat()` 簽名不變（外部 server.py 不受影響）✅
- 新增 `chat_context.py` 是純新增檔案，扇入 0 → 1（brain.py）✅
- 分步遷移：先讓 `ctx` 和 `self._*` 並存，再逐步清除 `self._*`

**成功標準**：
- `_build_memory_inject()` 不再引用任何 `self._*` per-turn 變數
- IDE type checking 能對 `ctx.` 提供自動完成
- 所有 pytest 通過

### S2: except 分級審計（brain.py 146 個 catch）

**產出檔案**：`docs/brain-exception-audit.md`

**方法**：逐一標記 146 個 `except Exception` 的信任層級

```markdown
| # | 行號 | 方法名 | 信任層級 | 理由 | 改動建議 |
|---|------|-------|---------|------|---------|
| 1 | 3442 | _build_system_prompt | OPTIONAL→CORE | 吞掉 NameError | 改為 catch 具體異常 |
| 2 | 3636 | _build_memory_inject | OPTIONAL | 外部 recall 可能失敗 | 保持 warning |
| ... | ... | ... | ... | ... | ... |
```

**信任層級定義**（呼應架構教訓 #2）：

| 層級 | 定義 | 處理方式 | 範例 |
|------|------|---------|------|
| **CORE** | 失敗 = 程式碼 Bug（NameError, TypeError, AttributeError） | `raise`（或 catch 具體異常後 re-raise 通用異常） | import 失敗、未定義變數 |
| **OPTIONAL** | 失敗 = 功能降級但可繼續 | `logger.warning()` + fallback | 外部 API 超時、記憶召回失敗 |
| **EDGE** | 失敗 = 可跳過的增強功能 | `logger.debug()` | 日誌寫入失敗、cosmetic 功能 |

**本層不改程式碼**——只產出審計報告。L3 才根據報告修改。

**S2 附帶改動**：對 L1 中 P0 所在的 `except Exception`（Line 3442），改為更精確的 catch：

```python
# Before:
except Exception as e:
    logger.warning(f"Memory inject 失敗: {e}")

# After:
except (OSError, ConnectionError, TimeoutError) as e:
    logger.warning(f"Memory inject 失敗（外部依賴）: {e}")
except Exception as e:
    logger.error(f"Memory inject 異常（可能是程式碼 Bug）: {e}", exc_info=True)
```

這是 S2 的「示範性修改」——展示分級 catch 的模式，供 L3 推廣。

### S3: Orchestrator 診斷數據收集

**檔案**：`src/museon/agent/brain.py`
**位置**：`_dispatch_orchestrate()` 和 `_parse_orchestrator_response()`

**變更**：在 PulseDB 記錄 Orchestrator 每次呼叫的結果

```python
# 在 _dispatch_orchestrate() 末尾，plan.tasks 賦值後：
if self._pulse_db:
    try:
        self._pulse_db.log_orchestrator_call(
            plan_id=plan.plan_id,
            skill_count=len(active_skills),
            task_count=len(plan.tasks),
            success=bool(plan.tasks),
            model=model,
            response_length=len(response_text),
        )
    except Exception:
        pass  # EDGE: 診斷數據寫入失敗不影響主流程
```

**PulseDB 新增表**：`orchestrator_calls`

```sql
CREATE TABLE IF NOT EXISTS orchestrator_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id TEXT,
    skill_count INTEGER,
    task_count INTEGER,
    success BOOLEAN,
    model TEXT,
    response_length INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);
```

**漣漪分析**：
- PulseDB 新增表 = 安全操作（blast-radius.md 已標記為 ✅ 安全）✅
- 診斷數據只寫不讀（L3 設計確定性路由時才讀）✅
- `pass` 標記為 EDGE 信任層級 ✅

**成功標準**：
- 跑一天後有 50+ 筆 `orchestrator_calls` 數據
- 可以統計 success rate by skill_count（驗證「Skill 數量多 → 失敗率高」假說）

### L2 藍圖同步清單

- [ ] `blast-radius.md` v1.47：ChatContext 新增、except 分級示範、PulseDB orchestrator_calls 表
- [ ] `persistence-contract.md`：新增 orchestrator_calls 表定義
- [ ] `joint-map.md`：新增 #35 orchestrator_calls（寫入者：brain，讀取者：未來 A1）
- [ ] `system-topology.md`：新增 chat-context 節點（如果影響拓撲）或不新增（純內部 dataclass）

---

## L3：根治（架構重構）

> **原則**：改變系統結構，但分步執行、每步可回滾
> **影響範圍**：brain.py 大規模內部重構 + dispatch 系統重設計
> **預計時間**：6-10 小時（分 3 個子任務）
> **前置條件**：L2 完成、S3 數據至少收集 3 天

### A1: 確定性 Dispatch Router（取代 LLM 控制流）

**目標**：Orchestrator 從「LLM 做任務分解」改為「規則做任務分解 + LLM 做 focus 描述」

**設計**：

```
┌─ 現狀 ─────────────────────────────────────┐
│ matched_skills → Sonnet LLM → JSON 解析     │
│                  (51% 失敗)   → TaskPackage  │
└─────────────────────────────────────────────┘

┌─ 目標 ─────────────────────────────────────┐
│ matched_skills → 規則引擎 → TaskPackage     │
│   ├ 1. io 依賴圖排序（inputs/outputs）     │
│   ├ 2. 情緒 Skill 排前（resonance 等）     │
│   ├ 3. depth 按 RoutingSignal 決定         │
│   └ 4. model 按 token 估算決定             │
│                                             │
│ TaskPackage → Haiku LLM → focus 描述填充    │
│                (可容錯，失敗用預設描述)       │
└─────────────────────────────────────────────┘
```

**新增檔案**：`src/museon/agent/deterministic_router.py`

```python
class DeterministicRouter:
    """規則式任務分解器——取代 LLM Orchestrator."""

    def decompose(
        self,
        user_request: str,
        matched_skills: List[Dict],
        routing_signal: Any,
    ) -> List[TaskPackage]:
        """確定性任務分解.

        步驟：
        1. 過濾非 worker 類 Skill（workflow, always_on）
        2. 按 io 依賴排序（skill A 的 output 是 skill B 的 input → A 先）
        3. 情緒 Skill 排前（RC 親和度 = preferred for emotional）
        4. depth 由 RoutingSignal.loop 決定
        5. model 由 token 估算決定
        """
        ...
```

**漣漪分析**：
- `_dispatch_orchestrate()` 改為調用 `DeterministicRouter.decompose()` ✅
- `_dispatch_worker()` 和 `_dispatch_synthesize()` 不變（消費 TaskPackage 的介面不變）✅
- 保留 LLM Orchestrator 作為 fallback（`DeterministicRouter` 產出 0 tasks 時切回 LLM）✅
- S3 的診斷數據用來驗證：確定性路由 vs LLM 路由的品質比較

**成功標準**：
- Dispatch 成功率 > 90%（現在 ~49%）
- 不再浪費 Sonnet 呼叫做任務分解
- Worker 品質不退化（用 eval-engine Q-Score 比較）

**前置條件**：
- S3 數據收集 ≥ 3 天
- Skill Manifest 的 `io.inputs` / `io.outputs` 覆蓋率 ≥ 80%（目前 48/49）
- 驗證 `validate_connections.py` 無新增孤立連線

### A2: Brain 方法分組提取（God Object → Helper 類別）

**目標**：brain.py 從 9098 行拆分為核心 + 5 個 Helper

**分組設計**：

```
brain.py (核心：chat() 主流程 + __init__() + _chat())
   ├── brain_prompt_builder.py    — _build_system_prompt(), _build_soul_context(), _build_memory_inject() 等
   ├── brain_dispatch.py          — _dispatch_orchestrate(), _dispatch_worker(), _dispatch_synthesize() 等
   ├── brain_observation.py       — _observe_lord(), _observe_external_user(), _detect_fact_correction() 等
   ├── brain_p3_fusion.py         — _p3_gather_pre_fusion_insights(), _parallel_review_synthesis() 等
   └── brain_tools.py             — _handle_tool_call(), _call_llm_with_model() 等
```

**實作方式**：Mixin Pattern（Python 多重繼承）

```python
# brain_prompt_builder.py
class BrainPromptBuilderMixin:
    def _build_system_prompt(self, ctx: ChatContext, ...) -> str:
        ...
    def _build_memory_inject(self, ctx: ChatContext, ...) -> str:
        ...

# brain.py
class Brain(BrainPromptBuilderMixin, BrainDispatchMixin, ...):
    ...
```

**漣漪分析**：
- server.py 的 `from museon.agent.brain import Brain` 不變 ✅
- Brain 的 public API（`chat()`, `process()`）不變 ✅
- 內部方法移到 Mixin 但仍可透過 `self.` 存取所有屬性 ✅
- **風險**：Mixin 之間互相調用時，IDE 型別提示會退化（`self` 的型別是 Mixin 而非 Brain）
- **緩解**：使用 `TYPE_CHECKING` + `Protocol` 提供型別提示

**成功標準**：
- brain.py 從 9098 行降到 < 3000 行
- 每個 Mixin < 2000 行
- pytest 全數通過
- 新增檔案的 import 只有 brain.py 單方向 import Mixin

**前置條件**：S1 完成（ChatContext 穩定），避免 Mixin 裡又出現 `self._current_metadata` 的問題

### A3: except 分級執行（146 catch → 三層信任模型）

**目標**：根據 S2 的審計報告，逐一改造 146 個 `except Exception`

**改造模式**：

```python
# CORE 層（程式碼 Bug，必須 crash loud）：
try:
    result = operation()
except (NameError, TypeError, AttributeError, KeyError) as e:
    logger.error(f"[CORE] {method_name} Bug: {e}", exc_info=True)
    raise  # 或 raise BrainCoreError(f"...") from e

# OPTIONAL 層（外部依賴，降級運行）：
try:
    result = external_api_call()
except (OSError, ConnectionError, TimeoutError, json.JSONDecodeError) as e:
    logger.warning(f"[OPTIONAL] {method_name} 降級: {e}")
    result = fallback_value

# EDGE 層（可跳過的增強，靜默處理）：
try:
    log_diagnostic_data()
except Exception as e:
    logger.debug(f"[EDGE] {method_name}: {e}")
```

**分步執行**：
1. **Phase A**：先改 CORE 層（約 20-30 個）— NameError/AttributeError 絕不能被吞
2. **Phase B**：改 OPTIONAL 層（約 80 個）— 指定具體異常類型
3. **Phase C**：標記 EDGE 層（約 40 個）— 加 `[EDGE]` 前綴保留現狀

**漣漪分析**：
- CORE 層 re-raise 可能導致之前靜默降級的路徑現在 crash
- **必須在 Staging 環境跑完整天測試**才能上線
- 分 Phase 執行，每 Phase 一個 commit

**成功標準**：
- 0 個 bare `except Exception` 在 CORE 區域
- 程式碼 Bug 在日誌中呈現為 ERROR（而非 WARNING）
- 外部故障在日誌中呈現為 WARNING（帶具體異常類型）
- pytest 通過（不含既有失敗）

---

## 執行順序與依賴圖

```
L1（止血）
 ├── L1-1: metadata fix
 ├── L1-2: JSON 解析
 ├── L1-3: 診斷日誌
 ├── L1-4: prompt 約束
 └── L1-5: RootCause 過濾
     │
     ▼  ← pytest + commit
L2（免疫）
 ├── S1: ChatContext dataclass ←── L1 完成
 ├── S2: except 審計報告 ←── 可並行
 └── S3: Orchestrator 診斷收集 ←── L1-3 完成
     │
     ▼  ← pytest + commit + 收集數據 3 天
L3（根治）
 ├── A1: 確定性 Router ←── S3 數據 + S1 完成
 ├── A2: Brain Mixin 拆分 ←── S1 完成
 └── A3: except 分級執行 ←── S2 報告完成 + A2 完成（在 Mixin 裡改比在 9098 行裡改安全）
```

## 回滾策略

| 層 | 回滾方式 | 代價 |
|---|---------|------|
| L1 | `git revert` 單個 commit | 零（回到原狀） |
| L2-S1 | `git revert` + 刪除 `chat_context.py` | 低（alias 向後相容） |
| L2-S3 | `DROP TABLE orchestrator_calls` | 零 |
| L3-A1 | 刪除 `deterministic_router.py` + revert `_dispatch_orchestrate` | 中（回到 LLM 路由） |
| L3-A2 | 合併 Mixin 回 brain.py | 高（但 git revert 仍可用） |
| L3-A3 | 逐個 revert Phase A/B/C commit | 中 |

## 藍圖同步矩陣

| 層 | 神經圖 | 水電圖 | 接頭圖 | 爆炸圖 | 郵路圖 |
|---|--------|--------|--------|--------|--------|
| L1 | — | — | — | ✅ changelog | — |
| L2-S1 | — | — | — | ✅ ChatContext | — |
| L2-S3 | — | ✅ orchestrator_calls 表 | ✅ #35 新增 | ✅ PulseDB 新增消費者 | — |
| L3-A1 | ✅ 新增 deterministic-router 節點 | — | — | ✅ 新檔案扇入扇出 | — |
| L3-A2 | ✅ brain 節點拆分為子節點 | — | — | ✅ 大規模更新 | — |
| L3-A3 | — | — | — | ✅ changelog | — |
