# MUSEON Skill 路由治理文件（Skill Routing Governance）v1.0

> **定位**：Skill 生態系的路由架構與治理規格。定義「Skill 怎麼分組、工作流怎麼編排、新 Skill 怎麼歸位」。
>
> **與其他藍圖的關係**：
> - `system-topology.md`：定義物理連線（節點 + links）
> - `skill-manifest-spec.md`：定義 I/O 合約格式（欄位規格）
> - `memory-router.md`：定義記憶流向
> - **本文件**：定義路由策略、Hub 分組、工作流階段規格
>
> **設計原則**：能簡單就不要複雜。利用已有基礎設施（拓撲 Hub），不引入新的 Python runtime 路由引擎。

---

## 一、架構概覽

MUSEON 的 Skill 路由由三個機制組成：

```
┌─────────────────────────────────────────────────────────┐
│  Always-on 中間件（品質守門，永遠生效）                    │
│  query-clarity → deep-think → c15 → user-model          │
├─────────────────────────────────────────────────────────┤
│  Hub 路由（語義分組，粗到細兩步選 Skill）                  │
│  ┌──────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐      │
│  │ Thinking │ │ Market │ │ Business │ │Creative │      │
│  └──────────┘ └────────┘ └──────────┘ └─────────┘      │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐              │
│  │ Product  │ │ Evolution │ │ Workflow │              │
│  └──────────┘ └───────────┘ └──────────┘              │
├─────────────────────────────────────────────────────────┤
│  Infra 基礎設施（跨 Hub 共用）                           │
│  knowledge-lattice / eval-engine / wee / morphenix      │
│  plan-engine / plugin-registry                          │
└─────────────────────────────────────────────────────────┘
```

---

## 二、Hub 定義

### 2.1 Hub 值表

| hub 值 | 名稱 | 職責 | 拓撲節點 |
|--------|------|------|---------|
| `core` | 常駐中間件 | 品質守門，每次回答自動執行 | agent 群組 |
| `infra` | 基礎設施 | 跨 Hub 共用的記憶/度量/演化/編排服務 | agent/data/nightly 群組 |
| `thinking` | Thinking Hub | 思維、轉化、共振、元認知 | skills-thinking-hub |
| `market` | Market Hub | 市場分析、風險、情緒 | skills-market-hub |
| `business` | Business Hub | 商模、戰略、銷售、溝通 | skills-business-hub |
| `creative` | Creative Hub | 語言、敘事、美感、品牌 | skills-creative-hub |
| `product` | Product Hub | 能力鑄造、DSE、報告 | skills-product-hub |
| `evolution` | Evolution Hub | 沙盒、品質審計 | skills-evolution-hub |
| `workflow` | Workflow Hub | 預製工作流範本 | skills-workflow-hub |

### 2.2 完整歸位表

| hub | Skills |
|-----|--------|
| `core` | deep-think, c15, query-clarity, user-model, dna27 |
| `infra` | knowledge-lattice, eval-engine, wee, morphenix, plan-engine, plugin-registry |
| `thinking` | dharma, philo-dialectic, resonance, shadow, meta-learning, roundtable |
| `market` | market-core, market-equity, market-crypto, market-macro, risk-matrix, sentiment-radar, investment-masters |
| `business` | business-12, ssa-consultant, master-strategy, consultant-communication, xmodel, pdeif |
| `creative` | text-alchemy, storytelling-engine, novel-craft, aesthetic-sense, brand-identity |
| `product` | acsf, dse, gap, env-radar, info-architect, report-forge, orchestrator |
| `evolution` | sandbox-lab, qa-auditor, tantra |
| `workflow` | workflow-svc-brand-marketing, workflow-investment-analysis, workflow-ai-deployment, group-meeting-notes |

### 2.3 Hub 路由邏輯

Hub 分組在**認知層**（Skill .md 和治理文件）運作，不改 Python runtime：

```
使用者輸入
    │
    v
[deep-think P0] 訊號分流（6 類信號）
    │
    v
[DNA27 RC 叢集] 27 反射觸發
    │
    v
[SkillRouter 四層疊加]  ← 現有 Python，不改
    │  Layer 1: RC 驅動（Skill 的 RC 親和宣告）
    │  Layer 2: 關鍵字（觸發詞 + 名稱 + 描述）
    │  Layer 3: Qdrant 向量語義
    │  Layer 4: 八原語親和
    │
    v
匹配結果  → hub 欄位供 orchestrator 編排時參考
```

Hub 的「粗到細」兩步效果由 RC 叢集自然實現——市場類 RC 自然匹配 Market Hub 的 Skill，思維類 RC 自然匹配 Thinking Hub。`hub` 欄位的程式碼用途留給未來。

---

## 三、Always-on 中間件

中間件不是「層」，而是**永遠生效的品質守門**。

| 中間件 | 守門職責 | 執行時機 |
|--------|---------|---------|
| `query-clarity` | 輸入品質——問題是否清晰 | Skill 路由之前 |
| `deep-think` | 思考品質——P0 訊號分流 + P1 輸入審視 + P2 輸出審計 | Skill 路由前後 |
| `c15` | 輸出品質——敘事張力語言層 | 輸出生成時 |
| `user-model` | 脈絡品質——使用者畫像持續更新 | 每次對話被動更新 |

**中間件 vs 普通 Skill**：

| 特性 | 中間件 | 普通 Skill |
|------|--------|-----------|
| 觸發方式 | 自動執行，無需路由 | 需要 SkillRouter 匹配 |
| RC 親和 | 不需要（常駐不受 RC 影響） | 需要宣告 RC 親和 |
| hub 值 | `core` | 7 個 Hub 之一 |
| type 值 | `always-on` | `on-demand` |

---

## 四、Workflow Stage 規格

### 4.1 Stage 定義格式

每個 `type: workflow` 的 SKILL.md 在 YAML frontmatter 中新增 `stages` 和 `speed_paths` 欄位：

```yaml
stages:
  - id: 1
    name: "階段名稱"
    skills: [skill-a, skill-b]       # 此階段調用的 Skill
    lens: "此階段的觀察透鏡"           # 認知調性描述
    mode: serial                      # serial | parallel | conditional
    gate:                             # 階段完成前的品質閘門
      - "閘門條件 1"
      - "閘門條件 2"
    output_to: [2, 3]                 # 輸出傳遞給哪些後續 Stage
    optional: false                   # 是否可跳過
    skip_when: "跳過條件描述"          # 配合 optional 使用

speed_paths:
  fast_loop:
    stages: [1, 5, 6]
    depth: "精簡"
  exploration_loop:
    stages: [1, 2, 5, 6]
    depth: "標準"
  slow_loop:
    stages: [1, 2, 3, 4, 5, 6]
    depth: "完整"
```

### 4.2 並行融合（mode: parallel）

當 `mode: parallel` 時，需要定義合併策略：

```yaml
  - id: 4
    name: "投資大師會診"
    skills: [investment-masters]
    lens: "六師會診"
    mode: parallel
    merge:
      strategy: consensus             # consensus | vote | weighted
      layers:                          # 合併後的輸出結構
        - consensus                    # 共識層：所有視角一致的結論
        - tension                      # 張力層：視角間的分歧
        - blind_spot                   # 盲點層：只有某個視角看到的
        - action                       # 行動層：提煉可行動建議
```

### 4.3 Multi-Agent 預留欄位（未來擴展）

為未來 multi-agent 場景預留 `agents` 欄位，**當前不要求填寫**：

```yaml
  - id: 4
    name: "多視角並行分析"
    mode: parallel
    agents:
      - role: "value_investor"
        skill: investment-masters
        lens: "Buffett + Munger 框架"
      - role: "risk_analyst"
        skill: risk-matrix
        lens: "尾端風險 + 壓力測試"
      - role: "sentiment_reader"
        skill: sentiment-radar
        lens: "散戶 vs 法人分歧"
    merge:
      strategy: consensus
      arbiter: roundtable              # 仲裁者（負責最終合併）
```

`agents` 欄位設計要點：
- 每個 agent 有獨立的 `role`（角色名）、`skill`（調用的 Skill）、`lens`（認知透鏡）
- 同一 stage 內的 agents 並行執行
- `merge.arbiter` 指定由哪個 Skill 做最終仲裁合併
- 未來可擴展 agent 生命週期管理（啟動/通訊/終止）

### 4.4 欄位速查表

| 欄位 | 必填 | 類型 | 說明 |
|------|------|------|------|
| `id` | 是 | int | Stage 序號（1-based） |
| `name` | 是 | string | Stage 名稱 |
| `skills` | 是 | list[string] | 此 Stage 調用的 Skill 列表 |
| `lens` | 否 | string | 觀察透鏡描述 |
| `mode` | 是 | enum | `serial` / `parallel` / `conditional` |
| `gate` | 否 | list[string] | 閘門條件（Stage 完成前的品質門檻） |
| `output_to` | 否 | list[int] | 輸出傳遞給哪些後續 Stage |
| `optional` | 否 | bool | 是否可跳過（預設 false） |
| `skip_when` | 否 | string | 跳過條件描述 |
| `merge` | 否 | object | parallel 模式的合併策略 |
| `agents` | 否 | list[object] | 未來 multi-agent 擴展 |

---

## 五、鍛造歸位指引

新 Skill 決定歸哪個 Hub：

```
1. 主要職責是什麼？
   思維/認知/元學習 → thinking
   市場/投資/風險   → market
   商模/戰略/銷售   → business
   語言/創作/品牌   → creative
   產品/診斷/報告   → product
   演化/品質/實驗   → evolution
   多階段流程範本   → workflow

2. 如果跨兩個 Hub？
   → 選主要消費場景的 Hub
   → 用 connects_to 連接另一個 Hub 的 Skill

3. 如果是基礎設施（被多個 Hub 共用）？
   → hub: infra

4. 如果是常駐品質控制？
   → hub: core
```

---

## 六、與 Manifest 的整合

### 新增欄位

`hub` 欄位加入 YAML frontmatter，位於 `layer` 之後：

```yaml
---
name: roundtable
type: on-demand
layer: analysis
hub: thinking               # <-- 新增

io:
  ...
---
```

### 現有欄位保留

| 欄位 | 處理 | 原因 |
|------|------|------|
| `type` | 保留 | `always-on` / `on-demand` / `reference` / `workflow` 是運行模式，與 hub 正交 |
| `layer` | 保留（降級） | 舊分類，新 Skill 可選填。hub 導入後不再用於治理決策 |
| `io` | 保留 | I/O 合約不變 |
| `connects_to` | 保留 | 鬆散連結不變 |
| `memory` | 保留 | 記憶路由不變 |

---

## 附錄 A：認知層級參考（T1-T4）

> 以下分類源自 MUSEON Knowledge Tier Governance v1.0，作為 Skill 設計時的「認知複雜度參考」，不用於路由或治理決策。

| 層 | 認知類型 | 代表 Skill | 特徵 |
|----|---------|-----------|------|
| T1 認知層 | 透鏡/元認知 | deep-think, c15, resonance, meta-learning, master-strategy, decision-tracker, shadow, dharma, philo-dialectic | 改變「怎麼想」，常駐影響所有輸出（10 個 always-on） |
| T2 方法論 | 分析框架 | business-12, dse, market-core, acsf | 有領域邊界的結構化拆解 |
| T3 操作層 | 單次動作 | risk-matrix, sentiment-radar, info-architect | 輸入→處理→輸出，不需全局脈絡 |
| T4 流程層 | 編排 | orchestrator, workflow-*, wee | 管順序、條件、銜接，不產生內容 |

此分類反映認知複雜度的梯度。完整文件見 `MUSEON-Knowledge-Tier-Governance.md`。

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.0 | 2026-03-21 | 初版：Hub 路由 + Always-on 中間件 + Workflow Stage 規格 + 鍛造歸位指引 |
