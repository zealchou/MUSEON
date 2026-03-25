---
name: fix-verify
description: >
  Fix-Verify（BDD 逆向驗證閉環工作流）— DNA27 核心的外掛模組，
  同時相容 Claude Code 原生 Skill 格式。
  核心能力：任何迭代或 debug 完成後，**強制觸發**三維驗證閉環——
  自動從使用者視角產生 BDD 驗證腳本，
  spawn 隔離審計員執行三維驗證（行為 × 接線 × 藍圖），
  未通過則繼續修復，反覆迴圈直到 100% 通過，
  最後將 pattern 存入記憶供未來防禦。
  觸發時機：(1) /fix-verify 或 /fv 指令強制啟動；
  (2) **任何迭代/debug 完成後強制執行**（不是建議，是必須）；
  (3) 自然語言偵測——使用者描述修完了想驗證、改了 A 擔心壞了 B、
  debug 反覆修不好、想確認修復品質、管線是否接通時自動啟用。
  涵蓋觸發詞：驗證、確認修好、真的修好了嗎、回歸、改壞、
  BDD、逆向驗證、debug 驗證、修復確認、fix verify、regression、
  測試修復、還是壞的、跑一次審計、管線斷裂、接線檢查、
  藍圖同步、100% 通過。
  此 Workflow 不重複 DNA27 核心邏輯，只擴展 BDD 逆向驗證閉環能力。
  依賴 DNA27 核心運作（MUSEON 環境）；在 Claude Code 環境中可獨立運行。
type: workflow
layer: quality
hub: Evolution
status: active
model_preference: opus
io:
  inputs:
    - name: bug_report_or_change_summary
      from: agent/user
      description: Bug 現場記錄或修改摘要
    - name: blueprints
      from: docs/
      description: 五張藍圖（神經圖/水電圖/接頭圖/爆炸圖/郵路圖）
  outputs:
    - name: bdd_scenarios
      to: audit_subagent
      description: BDD 驗證腳本（Gherkin 格式）
    - name: audit_report
      to: user/agent
      description: 三維審計結果矩陣
    - name: bug_pattern
      to: knowledge-lattice/crystal_rules
      description: 結晶化的 bug pattern 供未來防禦
memory:
  writes:
    - target: knowledge-lattice
      type: procedure_crystal
      condition: 100% 通過後結晶化 bug pattern
    - target: crystal_rules
      type: guard
      condition: 偵測訊號寫入 Crystal Actuator 供每次對話防禦
    - target: intuition/heuristics
      type: heuristic_rule
      condition: IF-THEN 預防規則
---

# Fix-Verify：BDD 逆向驗證閉環引擎 v2.1

> **AI 說「修好了」不算數。隔離審計員三維驗證 100% 全過才算數。**

---

## 設計哲學

來自 2026-03-25 的實戰教訓——修復 7 條斷裂管線，三輪迭代才達到 100%：

| 輪次 | 修復率 | 根因 |
|------|--------|------|
| 第一輪 | 29% | 沒追執行路徑、路徑用猜的、生產端不存在 |
| 第二輪 | 100% 接通，57% 品質合格 | logger.debug 吞錯、record_success 無呼叫者 |
| 第三輪 | 100% 通過 | — |

**教訓**：自己驗自己天然有盲點。寫入成功 ≠ 系統能用。測試通過 ≠ 系統會執行。

**業界參照**：
- Reflexion Pattern（Generate → Critique → Refine 迴圈）
- BMAD Code Review（六步嚴格審查 + adversarial review）
- Qualys Agent Val（validate-mitigate-revalidate 持續迴圈）
- Ralph Loop（sandbox 隔離 + MAX_ITERATIONS + 自動 revert）

---

## 外掛合約

**依賴**：
- MUSEON 環境：`dna27`（母體 AI OS）+ 五張藍圖
- Claude Code 環境：無依賴（獨立運行，藍圖路徑改為 CLAUDE.md）

**本模組職責**：
- 修改完成後，從使用者視角自動產生 BDD 驗證腳本
- Spawn **隔離審計員** subagent 執行三維驗證
- 未通過 → 回饋失敗資訊 → 修復 → 重新審計 → 直到 100%
- 通過後將 pattern 存入記憶（Crystal Actuator + knowledge-lattice + heuristics）

**本模組不做**：
- 不做 debug 本身（修 bug 是 Agent/使用者的事）
- 不做部署前完整審計（那是 qa-auditor）
- 不做長期品質趨勢追蹤（那是 eval-engine）

---

## 觸發與入口

**指令觸發**：
| 指令 | 效果 |
|------|------|
| `/fix-verify` `/fv` | 完整閉環（Phase 0→3） |
| `/fv record` | Phase 0：記錄現場 |
| `/fv bdd` | Phase 1：產 BDD 腳本 |
| `/fv audit` | Phase 2：spawn 審計員跑三維驗證 |
| `/fv memory` | Phase 3：存記憶 |
| `/fv status` | 查看迴圈狀態 |
| `/fv patterns` | 查看 bug pattern 記憶庫 |

**自動建議觸發**：
- Agent 回報修復完成 → 建議「跑一輪 /fv？」
- 同一問題被修復超過 2 次 → 強制建議
- 涉及 ≥2 個模組的修改 → 強制建議

---

## 核心流程：四階段迴圈

```
Phase 0: 記錄現場
    ↓
Agent / 使用者 修復
    ↓
Phase 1: 產生三維 BDD 驗證腳本
    ↓
Phase 1.5: 讀藍圖，產生接線 + 藍圖驗證項
    ↓
Phase 2: Spawn 隔離審計員執行 ──→ 100%？──→ Yes → Phase 3: 存入記憶 + 更新藍圖
                                    │
                                    No（失敗摘要）
                                    │
                                    ↓
                               回到修復（帶失敗資訊）
                                    ↓
                               再跑 Phase 2 ──→ ...直到 100%
```

---

### Phase 0：現場記錄

**觸發時機**：發現問題的當下，修之前。

**模板**：

```markdown
## 現場記錄 [FV-YYYY-MM-DD-序號]

### 症狀（使用者看到什麼）
[白話描述，不用技術術語]

### 重現步驟
1. [步驟]
2. [步驟]
→ 預期：[應該怎樣]
→ 實際：[實際怎樣]

### 影響範圍
- 功能：[列出]
- 使用者路徑：[哪些操作受影響]
- 嚴重度：致命 / 嚴重 / 中等 / 輕微

### 涉及的藍圖（MUSEON 環境）
- [ ] 查 blast-radius.md：扇入/扇出多少？
- [ ] 查 joint-map.md：碰了哪些共享狀態？
- [ ] 查 memory-router.md：記憶流向有沒有斷？
```

---

### Phase 1：產生三維 BDD 驗證腳本

**觸發時機**：修復完成後。

**三維驗證架構**（今天實戰教訓的結晶）：

| 維度 | 驗什麼 | 來自哪個教訓 |
|------|--------|-------------|
| **D1: 行為** | 功能正不正確——BDD Given/When/Then | 基礎驗證 |
| **D2: 接線** | 管線通不通——消費端→寫入端路徑匹配、排程清單、觸發源 | _FULL_STEPS 漏列、路徑不匹配 |
| **D3: 藍圖** | 文檔有沒有同步——五張藍圖是否反映最新修改 | joint-map/blast-radius 過期 |

#### D1: 行為驗證（BDD 腳本）

從 Phase 0 記錄中萃取至少 5 個驗證案例：

| 類型 | 數量 | 說明 |
|------|------|------|
| **直接驗證** | ≥2 | 重現 Phase 0 重現步驟，確認問題消失 |
| **邊界驗證** | ≥2 | 踩在邊界條件（快/慢/多/少/空/滿） |
| **連帶驗證** | ≥1 | 確認修復沒有影響相鄰功能 |

每案 Gherkin 格式：

```gherkin
Feature: [FV-ID] — [一句話]

  Scenario: [案例名]
    Given [使用者的起始狀態]
    When  [使用者做了什麼]
    Then  [應該看到什麼]

  驗證方式：[怎麼跑——手動 / pytest / grep / curl]
  通過標準：[怎麼判斷通過]
  分類：直接 / 邊界 / 連帶
```

#### D2: 接線驗證

針對每個被修改的資料管線，產生接線驗證項：

```markdown
## 接線驗證 [FV-ID]-D2

### 管線：[寫入端] → [消費端]

- [ ] 消費端代碼存在：[file:line] 有 function call
- [ ] 路徑匹配：消費端讀 `[path]` = 寫入端寫 `[path]`
- [ ] 排程確認：
  - Nightly step？→ _FULL_STEPS 包含 step ID
  - 啟動時？→ startup_event 中有呼叫
  - 每次對話？→ brain_prompt_builder 中有注入
- [ ] 觸發源存在：生產端有呼叫者（不是空殼消費端）
- [ ] 靜默吞錯檢查：except 區塊用 logger.warning 以上（不是 debug）
- [ ] 數據驗證：跑一次確認消費端能讀到寫入端的資料
```

#### D3: 藍圖驗證

```markdown
## 藍圖驗證 [FV-ID]-D3

- [ ] 改了共享狀態讀寫？→ joint-map.md 已更新
- [ ] 改了 import 關係？→ blast-radius.md 已更新
- [ ] 改了記憶流向？→ memory-router.md 已更新
- [ ] 改了模組拓撲？→ system-topology.md 已更新
- [ ] 改了持久層？→ persistence-contract.md 已更新
- [ ] 改了外部操作？→ operational-contract.md 已更新
```

---

### Phase 2：Spawn 隔離審計員執行

**觸發時機**：Phase 1 完成後。

**核心設計：審計員必須是隔離的 subagent。**

```
Spawn 審計員 Subagent：
  - 不帶修復者的對話記憶
  - 只帶 BDD 腳本 + 接線清單 + 藍圖清單
  - 從消費端倒追，不從寫入端正追
  - 對每案獨立判定 ✅ PASS / ❌ FAIL / ⚠️ PARTIAL
```

**MUSEON 環境的 spawn 參數**：
```
Agent tool:
  subagent_type: general-purpose
  mode: bypassPermissions
  prompt: [Phase 1 產出的完整驗證腳本]
  isolation: 不帶先前記憶
```

**Claude Code 環境的 spawn 參數**：
```
Agent tool:
  subagent_type: general-purpose
  prompt: [Phase 1 產出的完整驗證腳本]
  不帶先前對話 context
```

**審計結果表**：

```markdown
## Fix-Verify 審計結果 — Round [N]

### D1: 行為驗證
| # | 案例 | 分類 | 結果 | 備註 |
|---|------|------|------|------|
| S1 | ... | 直接 | ✅/❌ | ... |

### D2: 接線驗證
| # | 管線 | 消費端 | 路徑匹配 | 排程 | 吞錯 | 數據 | 結果 |
|---|------|--------|---------|------|------|------|------|
| W1 | ... | ... | ✅/❌ | ✅/❌ | ✅/⚠️ | ✅/❌ | ✅/❌ |

### D3: 藍圖驗證
| # | 藍圖 | 需更新 | 已更新 | 結果 |
|---|------|--------|--------|------|
| B1 | joint-map.md | 是/否 | 是/否 | ✅/❌ |

**總通過率：D1=[N/M] D2=[N/M] D3=[N/M] → 總計 [N/M] = [X]%**
```

**迴圈規則**：

| 規則 | 說明 |
|------|------|
| **重跑範圍** | 上輪 FAIL 案例必跑 + 所有連帶驗證必跑（防修 A 壞 B） |
| **迴圈上限** | 預設 5 輪。超過 5 輪強制暫停，重新審視根因 |
| **新增案例** | debug 中發現新邊界條件，可追加 |
| **PARTIAL** | 記為 FAIL，摘要標記已通過部分 |
| **100% 定義** | D1 + D2 + D3 三個維度全部 100% |
| **歷史保留** | 每輪結果保留，最終報告含完整迴圈軌跡 |

**未通過案例必須附失敗摘要**：

```markdown
### [案例編號] — [案例名稱]
- 預期：[BDD 的 Then]
- 實際：[跑出來的結果]
- 差距：[一句話]
- Debug 方向：[建議下一步修什麼]
```

---

### Phase 3：Pattern 記憶存入 + 藍圖更新

**觸發時機**：Phase 2 達到三維 100%。

**記憶封存**：

```markdown
## Pattern [FV-YYYY-MM-DD-序號]

### 摘要
- 一句話：[白話描述 pattern]
- 分類：[重複執行 / 狀態殘留 / 路徑不匹配 / 排程漏列 / 靜默吞錯 / ...]

### 偵測訊號（下次怎麼提早發現）
- [訊號 1]
- [訊號 2]

### 修復方向（下次怎麼更快修）
- 有效修法：[這次成功的]
- 無效修法：[試過但沒用的]

### 防禦建議
- 程式碼：[例如]
- 架構：[例如]
- 流程：[例如]

### 迴圈紀錄
- 總輪數：[N]
- 案例數：D1=[M] D2=[M] D3=[M]
- 通過率軌跡：[R1: 60% → R2: 85% → R3: 100%]
```

**存入位置**：

| 管道 | MUSEON | Claude Code |
|------|--------|-------------|
| 即時防禦 | crystal_rules.json（guard 規則） | CLAUDE.md checklist |
| 直覺規則 | intuition/heuristics.json | memory/ feedback file |
| 長期記憶 | memory_v3/boss/ + Qdrant | memory/ file + MEMORY.md |
| 結晶 | knowledge-lattice procedure_crystal | N/A |

**藍圖更新**（Phase 3 的最後一步）：
- 如果修改涉及共享狀態 → 更新 joint-map.md
- 如果改了 import → 更新 blast-radius.md
- 如果改了記憶流向 → 更新 memory-router.md
- 藍圖更新必須與代碼在同一個 commit

---

## 護欄

### 硬閘

**HG-FV-THREE-DIMENSIONS**：Phase 2 必須包含 D1（行為）+ D2（接線）+ D3（藍圖）三維。只跑 D1 不算通過。

**HG-FV-ISOLATED-AUDITOR**：Phase 2 審計必須由隔離 subagent 執行，不帶修復者的對話記憶。自己驗自己天然有盲點。

**HG-FV-NO-PARTIAL-PASS**：三維全部 100% 才能進 Phase 3。D1=100% 但 D2=80% 不算通過。

**HG-FV-NO-SKIP-LINKED**：重跑時連帶驗證案例必跑。修 A 可能壞了原本好的 B。

**HG-FV-MEMORY-REQUIRED**：100% 通過後 Phase 3 不可跳過。每次修復都是未來防禦的資料。

**HG-FV-BLUEPRINT-SYNC**：Phase 3 必須檢查並更新受影響的藍圖。藍圖過期 = 地雷。

### 軟閘

**SG-FV-SIMPLE-FIX**：純 typo/樣式修改 → 降級：D1 只需 2 案例，D2/D3 快速確認，Phase 3 可精簡。

**SG-FV-LOOP-LIMIT**：超過 5 輪未達 100% → 強制暫停，建議重新審視根因（可能不是 bug，是架構問題）。

**SG-FV-FAST-LOOP**：MUSEON fast_loop 下 → D1 3 案例 + D2 路徑匹配 + D3 跳過，迴圈上限 3 輪。

---

## 適應性深度控制

### MUSEON 環境（DNA27 三迴圈）

| 迴圈 | D1 案例 | D2 深度 | D3 | 迴圈上限 | Phase 3 |
|------|---------|---------|-----|---------|---------|
| fast_loop | 3 | 路徑匹配 only | 跳過 | 3 輪 | 一句話 pattern |
| exploration_loop | 5 | 完整六項 | 受影響的藍圖 | 5 輪 | 標準封存 |
| slow_loop | 7-10 | 完整 + 對抗性 | 全部六張 | 5 輪 | 完整 + 結晶化 |

### Claude Code 環境

| 場景 | D1 | D2 | D3 | 迴圈 |
|------|-----|-----|-----|------|
| 單一 bug fix | 5 | 完整 | CLAUDE.md checklist | 5 輪 |
| Hotfix 緊急 | 3 | 路徑匹配 | 跳過 | 3 輪 |
| 重構多檔案 | 7-10 | 完整 + 對抗性 | 全部 | 5 輪 |

---

## 系統指令

| 指令 | 效果 |
|------|------|
| `/fix-verify` `/fv` | 完整閉環 |
| `/fv record` | Phase 0 |
| `/fv bdd` | Phase 1 |
| `/fv audit` | Phase 2（spawn 審計員） |
| `/fv memory` | Phase 3 |
| `/fv status` | 迴圈狀態 |
| `/fv patterns` | bug pattern 記憶庫 |

---

## DNA27 親和對照（MUSEON 環境）

- Persona 旋鈕：tone → NEUTRAL、pace → MEDIUM、initiative → CHALLENGE
- 偏好 RC：Group C（認知誠實）、Group A（安全穩態）
- 限制 RC：Group D（驗證階段不探索）

**協同外掛**：
| 外掛 | 互補關係 |
|------|---------|
| qa-auditor | fix-verify 管「微觀 BDD 閉環」，qa-auditor 管「4D 宏觀審計」 |
| dev-retro | fix-verify 的 Phase 3 pattern 回灌 dev-retro 的教訓庫 |
| eval-engine | 迴圈次數餵入 debug 效率追蹤 |
| knowledge-lattice | bug pattern 結晶化 |
| sandbox-lab | 複雜修復的 BDD 審計可在沙盒隔離執行 |
| morphenix | pattern 累積 → 系統脆弱點數據 → 演化提案 |
| plan-engine | 複雜修復前先走 plan-engine 收斂，再交給 fix-verify 驗證 |

---

## 雙環境安裝

**Claude Code**：
```bash
mkdir -p ~/.claude/skills/fix-verify
cp SKILL.md ~/.claude/skills/fix-verify/SKILL.md
```

**MUSEON**：
```bash
cp SKILL.md ~/MUSEON/data/skills/native/fix-verify/SKILL.md
# 同步 Claude Code 鏡像
cp SKILL.md ~/.claude/skills/fix-verify/SKILL.md
```

---

## Plugin Registry 條目

```
| 屬性 | 值 |
|---|---|
| plus_id | FIX_VERIFY |
| 類別 | bdd-verification-loop-engine |
| 風險等級 | LOW |
| 允許迴圈 | 全部（fast_loop 自動降級） |
| 允許模式 | civil_mode、evolution_mode |
| 觸發指令 | /fix-verify、/fv、/fv record、/fv bdd、/fv audit、/fv memory |
| 核心能力 | 四階段三維閉環：現場記錄→BDD+接線+藍圖驗證腳本→隔離審計迴圈至 100%→Pattern 記憶存入 |
```

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|---|---|---|
| v1.0 | 2026-03-25 | 初版草稿 |
| v2.0 | 2026-03-25 | 重新鍛造——BDD 逆向驗證迴圈閉環 |
| v2.1 | 2026-03-25 | DSE 增強：三維驗證（D1 行為 + D2 接線 + D3 藍圖）、隔離審計員硬閘、藍圖同步義務、業界參照融入 |
