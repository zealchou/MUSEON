# Brain 統一重構計畫 v1.0

> **日期**: 2026-04-01
> **目標**: 統一 BrainFast/Brain 管線 + DNA27 從路由器升格為人格表達 + Brain 26→5 步瘦身
> **原則**: 減法>加法、文件就是 API、Python 不做需要理解人話的判斷
> **安全分級**: 紅區（brain 是系統核心）

---

## Phase 0: 止血 ✅ 已完成

- [x] BrainFast 加 commitment 群組守衛（brain.py L627）
- [x] 推播預算分時段（proactive_dispatcher.py）
- [x] CrystalStore reinforcement_count 遷移
- [x] Nightly _FULL_STEPS 對齊
- [x] Docker/Qdrant/SearXNG 恢復
- [x] GitHub Token 更新

---

## Phase 1: 統一管線——刪 BrainFast/BrainDeep

### 進入條件
- Phase 0 完成
- 當前 Gateway 正常運行

### 目標
- 所有 Telegram 訊息走同一條 Brain.process() 管線
- 刪除 brain_fast.py（498 行）和 brain_deep.py
- 統一 session history 格式

### 操作清單

1. **telegram_pump.py** — `_brain_process_with_sla()` (L93-173)
   - 移除 BrainFast 分支（L132-142）
   - 所有路徑統一呼叫 `brain.process()`
   - 保留 SLA 90 秒機制（timeout → 暫時回覆 → 繼續等）

2. **server.py** — 刪除 BrainFast 全域工廠
   - 刪除 `_brain_fast` 變數和 `_get_brain_fast()` 函數（L268-282）

3. **brain.py** — 吸收 BrainFast 的簡單判定
   - 在 process() 最前面加 `_is_simple` 快速判定（純字串比對，<1ms）
   - 簡單訊息（"好"/"收到"/"謝謝"/emoji）→ 跳過重型步驟，直接用 Sonnet 回覆
   - 複雜訊息 → 走完整管線

4. **Session history 統一**
   - 確認 BrainFast 的 `_system/sessions/{id}.json` 格式與 Brain 相容
   - 統一為一套讀寫邏輯

5. **brain_observer.py vs brain_observation.py**
   - BrainFast 用 brain_observer.py（輕量 5 管道）
   - Brain 用 brain_observation.py（重量級 Mixin）
   - 統一為：簡單訊息用輕量觀察、複雜訊息用完整觀察

6. **刪除檔案**
   - `src/museon/agent/brain_fast.py` — 刪除
   - `src/museon/agent/brain_deep.py` — 刪除
   - `.runtime/` 同步刪除

### 退出條件
- `grep -r "brain_fast\|BrainFast\|brain_deep\|BrainDeep" src/` 零結果（除 brain_dispatch 的防洩漏 regex）
- Gateway 重啟後正常回覆 Telegram 訊息
- 簡單訊息回覆時間 < 5 秒
- FV 三維驗證 100%

---

## Phase 2: 信任 LLM——Brain 26→5 步

### 進入條件
- Phase 1 FV 通過
- 統一管線正常運行

### 目標
- 刪除 17 個 D 類（Python 替 LLM 判斷）步驟
- 回覆前熱路徑從 26 步縮減到 5 步
- 後處理全部 fire-and-forget

### 刪除的步驟（17 個）

| 步驟 | 分類 | 處理方式 |
|------|------|---------|
| Step 0.7 元認知觀察 | D | 直接刪，無消費者 |
| Step 1.1.5 Haiku 分類器 | D | 直接刪，用 _is_simple 取代 |
| Step 1.5 直覺引擎 | D | 直接刪，與 DNA27 重疊 |
| Step 2.2 Mask Layer | D | 直接刪，LLM 自適配 |
| Step 3.0.5 Multi-Agent 路由 | D | 直接刪，LLM tool use |
| Step 3.15 主動 Skill 擴展 | D | 直接刪，LLM 自發現 |
| Step 3.2 P2 決策層偵測 | D | 遷移到 prompt 指引 |
| Step 3.3 P2 決策層短路 | D | 隨 3.2 刪除 |
| Step 3.4 P3 融合偵測 | D | 直接刪 |
| Step 3.5 計畫引擎觸發 | D | 直接刪，目前只 log |
| Step 3.65 百合引擎 | D | 遷移到 prompt（lord_profile 直注入）|
| Step 3.655 Dissent Engine check | D | 遷移到 prompt |
| Step 3.66 根因偵測 | D | 遷移到 prompt |
| Step 3.7 Dispatch 評估 | D | 直接刪，LLM tool use |
| Step 4.5 主動工具偵測 | D | 直接刪，LLM 有 tool defs |
| Step 5.5 P3 前置融合 | D | 直接刪，省 1-3s 額外 LLM 呼叫 |
| Step 6.2-6.3 PreCognition | D | 直接刪，省 0.5-3s |
| Step 9.7 元認知預判 | D | 直接刪，消費者已刪 |

### 保留的 5 步結構

```
Step 1: 圍欄短路（InputSanitizer + 命名儀式 + 更名 + 自我檢查）
Step 2: 載入上下文（ANIMA + 承諾 + DNA27 簡化信號 + Skill 匹配）
Step 3: 組建 prompt（persona + 記憶 + 結晶 + rules + history）
Step 4: 呼叫 LLM（一次呼叫，帶 tool_use）
Step 5: 輸出圍欄 + fire-and-forget 後處理
```

### 操作清單

1. **brain.py** — 重寫 `_process_impl()`
   - 刪除 17 個步驟的代碼塊
   - 重新編號剩餘步驟
   - 保留的圍欄步驟合併到 Step 1
   - 保留的管道步驟合併到 Step 2-3
   - Step 7+ 全部包在 `asyncio.ensure_future()` 中 fire-and-forget
   - Step 3.8 謀定引擎：保留行為約束（圍欄），刪除透鏡/策略（判斷）

2. **brain_prompt_builder.py** — 簡化
   - 移除 routing_signal 依賴（不再有 is_safety_triggered、mode、loop 參數）
   - 行為指引改為靜態注入（從 persona_digest 讀取，不動態生成）
   - 保留：記憶注入、結晶注入、Skill 注入、承諾注入

3. **brain_p3_fusion.py** — 可整檔刪除（P3 前置融合已刪）

4. **metacognition.py** — 簡化
   - 刪除 pre_review / revise 功能
   - 保留 Q-Score 評分（降級為 fire-and-forget）

5. **百合引擎 persona_router.py** — 不再被 brain.py 呼叫
   - baihe_decide() 不再被調用
   - lord_profile 改為直接注入 prompt
   - 檔案保留但標記為 legacy（Mask 層仍需要）

### 退出條件
- Brain.process() 步驟數 <= 8
- 無額外 LLM 呼叫（分類器、P3 融合、PreCognition）
- 簡單訊息回覆 < 3 秒
- 複雜訊息回覆 < 15 秒
- FV 三維驗證 100%

---

## Phase 3: 人格表達——DNA27 從路由器退役

### 進入條件
- Phase 2 FV 通過
- Brain 瘦身完成

### 目標
- reflex_router.py 從 1221 行簡化為 ~100 行「輕量信號器」
- 人格部分遷移到 persona_digest.md
- SkillRouter 解除對 top_clusters 的依賴

### 操作清單

1. **新建 `signal_lite.py`**（~100 行，取代 reflex_router.py 1221 行）
   ```python
   def compute_signal(message: str, is_simple: bool) -> SignalLite:
       """純算術信號器，零語意判斷。"""
       msg_len = len(message)
       # 結晶注入量：純算術
       if msg_len <= 30: max_push = 5
       elif msg_len <= 300: max_push = 10
       else: max_push = 20
       # 安全偵測：只做 Tier A 關鍵字掃描（10 個高風險詞）
       safety = any(kw in message for kw in _SAFETY_KEYWORDS)
       if safety: max_push = min(max_push, 5)
       return SignalLite(max_crystal_push=max_push, safety_triggered=safety)
   ```

2. **brain.py** — 用 signal_lite 取代 reflex_router
   - `from museon.agent.signal_lite import compute_signal`
   - 刪除 routing_signal 的 loop/mode/tier_scores 消費（Phase 2 已刪大部分）

3. **skill_router.py** — 解除 RC 親和依賴
   - 刪除 Layer 1 RC 驅動匹配（top_clusters × 5.0）
   - 保留 Layer 2 keyword + Layer 3 vector 匹配
   - 簡化 safety 覆寫：`if safety_triggered → only always-on skills`

4. **persona_digest.md 增強**（由 context_cache_builder 生成）
   - 加入行為指引（迴圈自判、安全準則、主權保護、認知誠實、實驗演化）
   - 加入十維特質→行為映射
   - 加入角色自判指引（取代百合引擎）
   - 加入重大決策準則（取代 P2 決策層）

5. **context_cache_builder.py** — 增強 persona_digest 生成
   - 讀 ANIMA_MC 十維特質分數 → 生成行為傾向描述
   - 讀 Growth Stage → 生成階段行為指引
   - 讀 DNA27 核心 → 生成靜態行為準則

6. **reflex_router.py** — 標記為 deprecated 或刪除
   - Qdrant `dna27` collection 標記為廢棄
   - Nightly Step 8.5 dna27_reindex 標記為跳過

7. **清理消費者**
   - pdr_council.py — 移除 cluster_scores 依賴，改為固定軍師選擇邏輯
   - deterministic_router.py — 移除 loop 依賴（Phase 2 已刪調用方）
   - token_optimizer.py — 移除 max_tier_score 依賴，改為 safety_triggered flag
   - brain_observation.py — 移除 loop 依賴（已改為 fire-and-forget）
   - telegram_pump.py — 移除 Phase 2 PDR loop 判斷

### 退出條件
- `grep -r "reflex_router\|RoutingSignal\|routing_signal" src/` 只在 deprecated 或 signal_lite 中
- `grep -r "top_clusters\|tier_scores\|cluster_scores" src/` 零結果
- SkillRouter 匹配品質：對 10 條測試訊息的 top-3 Skill 命中率 >= 70%
- FV 三維驗證 100%

---

## Phase 4: 藍圖同步 + 最終驗證

### 進入條件
- Phase 3 FV 通過

### 操作清單

1. **system-topology.md** — 刪 reflex-router 節點、更新 brain 節點描述、刪相關連線
2. **blast-radius.md** — 更新 brain.py 角色（統一入口）、刪 brain_fast/reflex_router 條目
3. **joint-map.md** — 更新共享狀態（刪 dna27 collection、合併 session 條目）
4. **persistence-contract.md** — 標記 dna27 Qdrant collection 廢棄
5. **memory-router.md** — 更新 G3 記憶管線成員
6. **validate_connections.py** — 跑一次確認無孤立連線
7. **全量 pytest**
8. **Git commit**（src + docs 同一 commit）
9. **重啟 MUSEON Gateway**
10. **復盤反思**

### 退出條件
- validate_connections.py 零 error
- pytest 全量通過
- Gateway 重啟後正常回覆
- 五張藍圖版本號同步更新
