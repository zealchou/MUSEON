# MUSEON 清理迭代計畫 v1.1（DSE 全 5 路完成，補充精確行號和隱藏 bug）

> **日期**: 2026-04-01（DSE 完成，待下個 session 執行）
> **前置**: Brain 統一重構已完成（BrainFast/BrainDeep 刪除、26→8 步瘦身、DNA27 路由退役宣告）
> **目標**: 廢除 .runtime 鏡像 + signal_lite 接入 + 死碼清理 + 簡單訊息判定統一 + Nightly 重疊清理
> **原則**: 同一件事只有一套實作、文件就是 API、Python 不做語意判斷
> **安全分級**: 紅區（涉及 brain.py + server.py + supervisord.conf）

---

## Phase A: 廢除 .runtime 鏡像（P0）

### 前提驗證（已由 DSE 確認）
- `.venv/` 和 `.runtime/.venv/` 的 Python 版本一致（3.13）
- `pip freeze` 完全一致（零差異）
- `.env` 主要內容一致

### A1: 進程管理配置（必須同時改）

| 檔案 | 改動 | 風險 |
|------|------|------|
| `data/_system/supervisord.conf` L20 | command: `.runtime/.venv/bin/python` → `.venv/bin/python` | 安全 |
| 同上 L22 | PYTHONPATH: `.runtime/src` → `src` | 安全 |
| `scripts/start-gateway.sh` L17-22 | VENV_BIN + PYTHONPATH + find 路徑 | 安全 |
| `scripts/gunicorn_config.py` L37-43 | 硬編碼路徑改為 src/ 和 .venv/ | 安全 |

### A2: 腳本刪除 rsync 步驟

| 檔案 | 改動 |
|------|------|
| `scripts/workflows/restart-gateway.sh` L48-60 | 刪除 Step 1.5 rsync 區塊，保留 __pycache__ 清理 |
| `scripts/deploy.sh` L73-80 | rsync 目標改為直接 src/ |
| `scripts/build-installer.sh` L72-80 | 刪除 .runtime 同步區塊 |

### A3: Python 原始碼移除 .runtime 感知（20 處）

| 檔案 | 改動 | 驗證 |
|------|------|------|
| `server.py` L55,124,182,230 | 4 處刪除 `if parent.name == ".runtime":` 分支 | Gateway 啟動正常 |
| `session_cleanup.py` L33 | 刪除 .runtime fallback | session cleanup cron 正常 |
| `health_check.py` L76,80,285,607 | runtime_dir 改為 home | HealthChecker 全 OK |
| `auto_repair.py` L42-66 | 刪除 .runtime 分支 | AutoRepair 路徑正確 |
| `system_audit.py` L210,355,458,1435,1850,2065 | 6 處刪除 .runtime fallback | SystemAudit 全通過 |
| `surgeon.py` L512-543,717 | 刪除 sync_to_runtime + rollback 同步 | surgery 流程完整 |
| `runbook.py` L329-351 | find 路徑只留 src/ | RB-008 正常 |
| `tools.py` L834,855,1170 | 刪除 .runtime/data fallback | 工具載入正常 |
| `tool_schemas.py` L436 | 更新描述文字 | 無 |
| `guardian/daemon.py` L255 | 刪除 .runtime/.env 候選 | Guardian 正常 |
| `governance/refractory.py` L359 | 刪除 .runtime .env 分支 | refractory 正常 |
| `governance/preflight.py` L244 | 同上 | preflight 正常 |
| `nightly/morphenix_standards.py` L283 | 刪除 .runtime docs 分支 | morphenix 正常 |
| `nightly/morphenix_validator.py` L42 | 從排除列表移除 .runtime | validator 正常 |

### A4: 清理和驗證

1. 刪除遺留 `com.museon.gateway.plist`（定時炸彈）
2. `mv .runtime .runtime.bak`（先備份觀察一週，確認無問題後刪除）
3. 全量 pytest
4. Gateway 重啟驗證

### A5: 唯一高風險點

`.runtime/electron/main.js` 的 `getProjectRoot()` 和 `findPython()` — Electron App 入口。如果目前沒有在用 Electron App，可以暫緩處理。如果在用，需要修改 main.js 移除 .runtime 路徑邏輯。

---

## Phase B: brain.py Step 3 接入 signal_lite（P0）

### B1: 替換 Step 3 核心代碼

**刪除**（brain.py L790-839 整段）：reflex_router import + route() 呼叫 + build_routing_context() + safety_clusters fallback + 簡單訊息覆蓋

**同時刪除**（brain.py L843-864）：Step 3.0.3 健康感知路由調節（依賴 SLOW_LOOP）

**替換為**：
```python
# ── Step 3: SignalLite 輕量路由 ──
_report("🧬 信號判定", "SignalLite 計算中...")
routing_signal = None
safety_context = ""
try:
    from museon.agent.signal_lite import compute_signal, SignalLite
    _sig = compute_signal(content, is_simple=_is_simple)
    routing_signal = _sig
    self._last_routing_signal = _sig
    if _sig.safety_triggered:
        safety_context = (
            "## 安全提示\n\n"
            "偵測到高風險訊號。請以安全、同理為最高優先。\n"
            "不要給予具體行動建議，先傾聯與陪伴。\n"
        )
    elif _sig.sovereignty_triggered:
        safety_context = (
            "## 主權保護提示\n\n"
            "偵測到決策外包傾向。引導使用者自主決策，不代為做主。\n"
        )
    logger.info(f"[SignalLite] push={_sig.max_crystal_push}, safety={_sig.safety_triggered}")
except Exception as e:
    logger.warning(f"SignalLite failed: {e}")
```

### B2: routing_signal 殘留消費者精確清理（DSE 確認 30+ 處）

| 位置 | 改動 |
|------|------|
| brain.py L109 | 刪除 `_routing_history = {}` |
| brain.py L110 | `_last_routing_signal` 保留但改存 SignalLite |
| brain.py L808-812 | 刪除簡單訊息覆蓋 FAST_LOOP（signal_lite 的 is_simple 已處理） |
| brain.py L821-827 | 刪除 `_routing_history` 讀寫 |
| brain.py L872 | 改為 `_safety = getattr(routing_signal, 'safety_triggered', False)` |
| brain.py L1086-1087 | `_max_history = 10 if _is_simple else 40` |
| brain.py L1322-1324 | `_loop_short = "F" if _is_simple else "E"` |
| brain.py L1624-1628 | 刪除 SLOW_LOOP 分支 |
| brain.py L2237 | 用 `_is_simple` 取代 FAST_LOOP 判斷 |
| brain.py L2376 | `_deliberate` 內用 `is_simple` 映射 |
| brain_dispatch.py L211 | 刪除 `routing_signal=` 參數（latent bug：decompose() 不接受此參數） |
| telegram_pump.py L874-889 | 刪除 `routing_signal` 讀取（latent bug：review() 不接受此參數） |
| brain_observation.py L667 | 保留（函數內不讀 routing_signal 屬性） |
| metacognition.py L246-293 | `is_safety_triggered` 改為 `safety_triggered`；loop 判斷改用 is_simple |

### B3: server.py 啟動時的 dna27 索引

刪除 `server.py:3022-3028` 的 `index_reflex_patterns_to_qdrant` 呼叫。

### B4: signal_lite.py 補充相容 property

```python
@property
def is_safety_triggered(self) -> bool:
    return self.safety_triggered
```
讓 metacognition.py 的消費零改動。

### B5: DSE 發現的 3 個隱藏 bug（順便修復）

1. **brain.py L812**: `routing_signal.loop = "FAST_LOOP"` 但 RoutingSignal 是 frozen dataclass → FrozenInstanceError（從未被觸發？）
2. **telegram_pump.py L883**: 傳 `routing_signal=` 給 PDRCouncil.review() 但 review() 不接受此參數
3. **brain_dispatch.py L211**: 傳 `routing_signal=` 給 decompose() 但 decompose() 不接受此參數

---

## Phase C: 死碼刪除（P1，~3,500 行）

### C1: brain_p3_fusion.py（1008 行，零風險）

| 改動 | 檔案 |
|------|------|
| 刪除檔案 | `src/museon/agent/brain_p3_fusion.py` |
| 刪除 import | `brain.py` L55 `from museon.agent.brain_p3_fusion import BrainP3FusionMixin` |
| 刪除繼承 | `brain.py` L66 繼承列表中的 `BrainP3FusionMixin` |
| 刪除 import | `brain.py` L63 `from museon.agent.brain_types import DecisionSignal, P3FusionSignal` |

### C2: brain_observer.py（~400 行，零風險——死碼）

| 改動 | 檔案 |
|------|------|
| 刪除檔案 | `src/museon/agent/brain_observer.py` |
| 保留 regex | `brain_dispatch.py` L1139 的防洩漏 regex 不動 |

**注意**：signal_cache 寫入功能隨此刪除。signal_cache 功能的處理見 Phase E。

### C3: safety_clusters.py（~200 行，與 reflex_router 重複）

| 改動 | 檔案 |
|------|------|
| 刪除檔案 | `src/museon/agent/safety_clusters.py` |
| 刪除 fallback | `brain.py` ~L830-838 的 safety_clusters fallback import |

### C4: reflex_router.py（1221 行，Phase B 完成後可刪）

| 改動 | 檔案 |
|------|------|
| 刪除檔案 | `src/museon/agent/reflex_router.py` |
| 確認零殘留 | `grep -r "reflex_router" src/` 零結果 |

### C5: persona_router.py 標記 deprecated（586 行）

| 改動 | 檔案 |
|------|------|
| 不刪除 | persona_router.py 的 Mask 層仍被 mask_engine 使用 |
| 標記 | baihe_decide() 方法加 @deprecated 標記 |
| 清理 | brain.py 中殘留的 baihe_context 變數改為空字串（已完成） |

### C6: 需同步刪除的測試檔案

| 測試檔案 | 因刪除哪個檔案 |
|---------|-------------|
| `tests/unit/test_brain_p3_fusion.py` | brain_p3_fusion.py |
| `tests/unit/test_safety_clusters.py` | safety_clusters.py |
| `tests/unit/test_baihe_engine.py` | persona_router.py |
| `tests/unit/test_brain_observe_scope.py:28` | 移除 BRAIN_MIXIN_FILES 中的 brain_p3_fusion 條目 |

### C7: 需同步修改的腳本

| 檔案 | 改動 |
|------|------|
| `scripts/inject_health_meta.py` | 移除 brain-observer 和 brain-p3-fusion 條目 |

---

## Phase D: 簡單訊息判定統一（P1）

### 現狀
4 處各自定義：brain._is_simple、Router.classify、MetaCognition._SKIP、Haiku _CLASSIFY_PROMPT

### 方案
Phase 2 已刪除 Haiku 分類器（Step 1.1.5）。剩下 3 處。

統一為 brain.py 的 `_is_simple` 作為唯一判定源：
1. brain.py `_is_simple` 保留（現有邏輯夠用：len<15 + 排除詞）
2. Router.classify() 的 HAIKU_PATTERNS 改為消費 `_is_simple` 結果（metadata 傳遞）
3. MetaCognition._SKIP_PATTERNS 改為消費 `_is_simple` 結果

或者更簡單：由於 Phase 2 已刪除 MetaCognition 的 pre_review 呼叫，且 Router.classify() 的消費者是 _call_llm 中的模型選擇——可以直接用 `_is_simple → Sonnet/Haiku` 的映射取代整個 Router.classify()。

**待下次 session 開始時用 DSE 補充 Router.classify 的完整消費鏈再決定方案。**

---

## Phase E: Nightly 重疊清理 + signal_cache（P2）

### E1: 刪除 Nightly Step 18.7（system-audit 30 分鐘內跑兩次）

| 改動 | 檔案 |
|------|------|
| 刪除方法 | `nightly_pipeline.py:3537-3582` `_step_system_health_audit` |
| 刪除 step_map 條目 | `nightly_pipeline.py:228` |
| 刪除 _FULL_STEPS 條目 | `"18.7"` |

### E2: Step 26 改為 audit-only

不清理 session，只驗證 cron session-cleanup 有正常運作（檢查最近 3 小時內是否有 cleanup log）。

### E3: signal_cache 處理

**建議方案**：簡化而非完全刪除。

- 刪除 brain_observer.py 管道 5（Haiku 寫入端）— 隨 Phase C2 一起刪除
- 保留 brain_prompt_builder 的 `_build_signal_context` 中的 keyword 快篩部分（即時生效，零 LLM 成本）
- 刪除 signal_cache JSON 檔的讀寫依賴（改為每次即時計算）
- 刪除 skill_router 的 signal_cache 加權（從未生效）

---

## 施工順序和驗證檢查點

| 順序 | Phase | 驗證方式 | 回滾方式 |
|------|-------|---------|---------|
| 1 | A（廢除 .runtime） | Gateway 重啟 + curl /health/live + Telegram 測試 | `mv .runtime.bak .runtime` + 改回 supervisord.conf |
| 2 | B（signal_lite 接入） | Gateway 重啟 + grep "SignalLite" logs + Telegram 測試 | git checkout brain.py |
| 3 | C（死碼刪除） | `python -c "from museon.gateway.server import create_app"` + pytest | git checkout 刪除的檔案 |
| 4 | D（簡單判定統一） | 發送「好」「收到」測試回覆速度 | git checkout 修改的檔案 |
| 5 | E（Nightly 清理） | 手動觸發 Nightly 確認步驟數正確 | git checkout nightly_pipeline.py |

每個 Phase 完成後：
1. FV 三維驗證
2. 五張藍圖版本同步
3. 確認無 TypeError / ImportError / AttributeError
4. Telegram 私訊 + 群組各發一條訊息測試
5. commit

---

## 預估成果

| 指標 | 修改前 | 修改後 |
|------|--------|--------|
| .runtime 鏡像 | 存在（每次重啟 rsync + __pycache__ 風險） | **廢除** |
| 死碼 | ~3,500 行 | **0** |
| 簡單訊息判定 | 4 處各自定義 | **1 處** |
| Nightly/日間重疊 | 2 處完全重複 | **0** |
| signal_cache | 功能失效（零寫入者） | **簡化為即時 keyword 快篩** |
| reflex_router | 1221 行仍在 brain.py 呼叫 | **80 行 signal_lite 取代** |
| 遺留 plist | 定時炸彈 | **刪除** |
| 總淨減程式碼 | — | **~4,500 行** |
