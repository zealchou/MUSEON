# Skill Manifest 規格 v1.0

> **用途**：定義 MUSEON Skill 生態系的 I/O 合約格式，讓每個 Skill 聲明「我需要什麼、我產出什麼、我連誰」。
> **目的**：從「靠紀律記住接線」進化到「靠基礎設施自動驗證」。
> **建立日期**：2026-03-21
> **搭配**：`validate_connections.py`（自動掃描驗證）、`docs/memory-router.md`（記憶路由表）

---

## YAML Frontmatter 格式

每個 Skill 的 `SKILL.md` 在原有 `name` + `description` 之外，新增以下欄位：

```yaml
---
name: roundtable
type: on-demand          # always-on | on-demand | reference | workflow
layer: analysis          # core-extension | analysis | thinking | business | language | aesthetic | meta | evolution | product | market | workflow | special

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

### layer（所屬層級）

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

---

## 驗證規則（validate_connections.py 實作）

1. **孤立輸出**：`output.trigger == "always"` 但沒有任何 Skill 的 `input.from` 對應到它 → ⚠️ 警告
2. **斷裂輸入**：`input.required == true` 但沒有任何 Skill 的 `output.to` 對應到它 → ❌ 錯誤
3. **孤立 Skill**：io.inputs 和 io.outputs 都是空的（非 reference/workflow 類型）→ ⚠️ 警告
4. **記憶無家**：`memory.writes.target` 不在 memory-router.md 的路由表中 → ⚠️ 警告
5. **幽靈連線**：`connects_to` 中的 Skill 名稱不存在於已註冊的 Skill 列表 → ❌ 錯誤

---

## 變更紀錄

| 版本 | 日期 | 變更 |
|------|------|------|
| v1.0 | 2026-03-21 | 初始版本——定義 Manifest YAML 格式、驗證規則 |
