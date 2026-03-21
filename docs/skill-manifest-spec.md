# Skill Manifest 規格 v1.1

> **用途**：定義 MUSEON Skill 生態系的 I/O 合約格式，讓每個 Skill 聲明「我需要什麼、我產出什麼、我連誰、我歸哪個 Hub」。
> **目的**：從「靠紀律記住接線」進化到「靠基礎設施自動驗證」。
> **建立日期**：2026-03-21
> **搭配**：`validate_connections.py`（自動掃描驗證）、`docs/memory-router.md`（記憶路由表）、`docs/skill-routing-governance.md`（路由治理）

---

## YAML Frontmatter 格式

每個 Skill 的 `SKILL.md` 在原有 `name` + `description` 之外，新增以下欄位：

```yaml
---
name: roundtable
type: on-demand          # always-on | on-demand | reference | workflow
layer: analysis          # （已降級）core-extension | analysis | thinking | business | language | aesthetic | meta | evolution | product | market | workflow | special
hub: thinking            # core | infra | thinking | market | business | creative | product | evolution | workflow

io:
  inputs:
    - from: query-clarity
      field: validated_question
      required: true
    - from: user-model
      field: user_profile
      required: false
  outputs:
    - to: knowledge-lattice
      field: verdict_with_dissent
      trigger: always      # always | on-request | conditional
    - to: user-model
      field: decision_pattern
      trigger: conditional

connects_to:
  - master-strategy
  - shadow

memory:
  writes:
    - target: knowledge-lattice
      type: crystal
      condition: "使用者做出仲裁決定時"
  reads:
    - source: user-model
      field: user_profile

stages:                              # 僅 type: workflow 使用
  - id: 1
    name: "階段名稱"
    skills: [skill-a, skill-b]       # 此階段調用的 Skill
    lens: "此階段的觀察透鏡"
    mode: serial                      # serial | parallel | conditional
    gate:
      - "閘門條件 1"
    output_to: [2, 3]
    optional: false
    skip_when: "跳過條件描述"

speed_paths:                          # 僅 type: workflow 使用
  fast_loop:
    stages: [1, 5, 6]
    depth: "精簡"
  exploration_loop:
    stages: [1, 2, 5, 6]
    depth: "標準"
  slow_loop:
    stages: [1, 2, 3, 4, 5, 6]
    depth: "完整"

description: >
  （原有描述保持不動）
---
```

---

## 欄位說明

### type（運行模式）

| 值 | 說明 | 範例 |
|----|------|------|
| `always-on` | 常駐層，每次回答自動執行 | deep-think, c15, query-clarity |
| `on-demand` | 按需啟動（指令/偵測/路由） | roundtable, investment-masters |
| `reference` | 參考文件，不獨立觸發 | plugin-registry |
| `workflow` | 工作流範本，編排多 Skill | workflow-svc-brand-marketing |

### hub（所屬 Hub）— v1.1 新增

Skill 的語義分組，對應拓撲圖中的 Skills Hub。用於粗到細兩步路由和治理分組。**所有 Skill 必填。**

| 值 | 說明 | 範例 |
|----|------|------|
| `core` | 常駐中間件（品質守門，每次回答自動執行） | deep-think, c15, query-clarity, user-model, dna27 |
| `infra` | 基礎設施（跨 Hub 共用的記憶/度量/演化/編排服務） | knowledge-lattice, eval-engine, wee, morphenix, plan-engine, plugin-registry |
| `thinking` | Thinking Hub（思維、轉化、共振、元認知） | dharma, philo-dialectic, resonance, shadow, meta-learning, roundtable |
| `market` | Market Hub（市場分析、風險、情緒） | market-core, market-equity, market-crypto, market-macro, risk-matrix, sentiment-radar, investment-masters |
| `business` | Business Hub（商模、戰略、銷售、溝通） | business-12, ssa-consultant, master-strategy, consultant-communication, xmodel, pdeif |
| `creative` | Creative Hub（語言、敘事、美感、品牌） | text-alchemy, storytelling-engine, novel-craft, aesthetic-sense, brand-identity |
| `product` | Product Hub（能力鑄造、DSE、報告） | acsf, dse, gap, env-radar, info-architect, report-forge, orchestrator |
| `evolution` | Evolution Hub（沙盒、品質審計） | sandbox-lab, qa-auditor, tantra |
| `workflow` | Workflow Hub（預製工作流範本） | workflow-svc-brand-marketing, workflow-investment-analysis, workflow-ai-deployment, group-meeting-notes |

詳見 `docs/skill-routing-governance.md` 的 Hub 定義與歸位指引。

### layer（所屬層級）— 已降級

> **注意**：`layer` 在 v1.1 降級為選填欄位。新 Skill 可選填，不再用於治理決策。Hub 導入後，`hub` 取代 `layer` 作為主要分組機制。

| 值 | 說明 |
|----|------|
| `core-extension` | DNA27 核心擴展（常駐層） |
| `analysis` | 前置分析與決策支援 |
| `thinking` | 思維與轉化 |
| `business` | 商業與戰略 |
| `language` | 語言與創作 |
| `aesthetic` | 美感與品牌 |
| `meta` | 元認知與學習 |
| `evolution` | 演化與治理 |
| `product` | 產品線 |
| `market` | 市場分析 |
| `workflow` | 工作流範本 |
| `special` | 特殊模組 |

### io.inputs

| 欄位 | 必填 | 說明 |
|------|------|------|
| `from` | ✅ | 輸入來源 Skill 名稱，或 `user` 表示直接來自使用者 |
| `field` | ✅ | 語義欄位名（無需精確對應程式變數，描述性即可） |
| `required` | ✅ | `true`=沒有此輸入就不該啟動；`false`=有則更好 |

### io.outputs

| 欄位 | 必填 | 說明 |
|------|------|------|
| `to` | ✅ | 輸出目標 Skill 名稱 |
| `field` | ✅ | 語義欄位名 |
| `trigger` | ✅ | `always`=每次都輸出（validator 會檢查是否有人接）；`on-request`=被要求才輸出；`conditional`=條件滿足才輸出 |

### connects_to

列出「可以互相呼叫但不是嚴格 I/O 依賴」的 Skill。用於表示「在特定情境下可能協作」的鬆散連結。

### memory

| 欄位 | 說明 |
|------|------|
| `writes.target` | 寫入的記憶系統（knowledge-lattice / user-model / wee / session-log / auto-memory） |
| `writes.type` | 寫入類型（crystal / profile_update / proficiency / summary） |
| `writes.condition` | 什麼時候觸發寫入 |
| `reads.source` | 讀取的記憶系統 |
| `reads.field` | 讀取的欄位 |

### stages（工作流階段定義）— v1.1 新增

僅 `type: workflow` 的 Skill 使用。將自然語言描述的工作流階段轉換為結構化 YAML。

| 欄位 | 必填 | 類型 | 說明 |
|------|------|------|------|
| `id` | 是 | int | Stage 序號（1-based） |
| `name` | 是 | string | Stage 名稱 |
| `skills` | 是 | list[string] | 此 Stage 調用的 Skill 列表 |
| `lens` | 否 | string | 觀察透鏡描述 |
| `mode` | 是 | enum | `serial`（串行）/ `parallel`（並行）/ `conditional`（條件） |
| `gate` | 否 | list[string] | 閘門條件（Stage 完成前的品質門檻） |
| `output_to` | 否 | list[int] | 輸出傳遞給哪些後續 Stage |
| `optional` | 否 | bool | 是否可跳過（預設 false） |
| `skip_when` | 否 | string | 跳過條件描述 |
| `merge` | 否 | object | `mode: parallel` 時的合併策略 |
| `agents` | 否 | list[object] | 未來 multi-agent 擴展（當前不要求填寫） |

**merge 物件格式**（`mode: parallel` 時使用）：

```yaml
merge:
  strategy: consensus    # consensus | vote | weighted
  layers:
    - consensus          # 共識層：所有視角一致的結論
    - tension            # 張力層：視角間的分歧
    - blind_spot         # 盲點層：只有某個視角看到的
    - action             # 行動層：提煉可行動建議
```

**agents 物件格式**（未來 multi-agent 擴展）：

```yaml
agents:
  - role: "角色名"
    skill: skill-name
    lens: "此 agent 的透鏡"
merge:
  strategy: consensus
  arbiter: roundtable    # 仲裁者 Skill
```

### speed_paths（速度路徑）— v1.1 新增

僅 `type: workflow` 的 Skill 使用。定義三迴圈路由（fast/exploration/slow）對應的 Stage 子集。

```yaml
speed_paths:
  fast_loop:
    stages: [1, 5, 6]       # 跳過中間深度分析，快速出結果
    depth: "精簡"
  exploration_loop:
    stages: [1, 2, 5, 6]    # 標準深度
    depth: "標準"
  slow_loop:
    stages: [1, 2, 3, 4, 5, 6]  # 完整展開所有階段
    depth: "完整"
```

詳見 `docs/skill-routing-governance.md` 的 Workflow Stage 規格。

---

## 驗證規則（validate_connections.py 實作）

1. **孤立輸出**：`output.trigger == "always"` 但沒有任何 Skill 的 `input.from` 對應到它 → ⚠️ 警告
2. **斷裂輸入**：`input.required == true` 但沒有任何 Skill 的 `output.to` 對應到它 → ❌ 錯誤
3. **孤立 Skill**：io.inputs 和 io.outputs 都是空的（非 reference/workflow 類型）→ ⚠️ 警告
4. **記憶無家**：`memory.writes.target` 不在 memory-router.md 的路由表中 → ⚠️ 警告
5. **幽靈連線**：`connects_to` 中的 Skill 名稱不存在於已註冊的 Skill 列表 → ❌ 錯誤
6. **Hub 一致性**（v1.1）：`hub` 值必須在 9 種合法值中（core/infra/thinking/market/business/creative/product/evolution/workflow）→ ❌ 錯誤
7. **Workflow stages**（v1.1）：`type: workflow` 的 Skill 必須有 `stages` 欄位 → ⚠️ 警告

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.1 | 2026-03-21 | 新增 `hub`（必填）、`stages` + `speed_paths`（workflow 用）；`layer` 降級為選填；新增驗證規則 6、7 |
| v1.0 | 2026-03-21 | 初始版本——定義 Manifest YAML 格式、驗證規則 |
