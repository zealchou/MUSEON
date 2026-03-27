# MUSEON v2 架構重設計 Plan

> 核心理念：保留 Claude 的簡單（直接回），加上 Claude 沒有的能力（L4 學習 + 多使用者 + 主動洞察）。
>
> 設計原則：預設最簡，按需加深。回覆路徑零阻塞，學習在背景。

---

## 架構總覽

```
                       ┌──────────────────────┐
                       │   context_cache/      │
                       │   （思考前置區）       │
                       │                      │
                       │  user_summary.json    │
                       │  pending_insights.json│
                       │  active_rules.json    │
                       │  self_summary.json    │
                       └──────────┬───────────┘
                                  │
                           ┌──────┴──────┐
                           ↓             ↓
Telegram ──→ ┌──────────────┐   ┌──────────────┐
             │  L1 主持人    │   │  L2 深度思考  │
             │  (Sonnet)    │   │  (Sonnet)    │
             │              │   │              │
             │ 讀 cache     │   │ 讀 cache     │
             │ 簡單→自答    │──→│ + Qdrant 搜尋 │
             │ 複雜→派 L2   │   │ + crystal 搜尋│
             │ /指令→派Worker│   │ → 深度回覆    │
             └──────┬───────┘   └──────┬───────┘
                    │                  │
                    │    ┌─────────────┐
                    │    │ Skill Worker│ ← /strategy, /dse 等
                    │    │ (按需 spawn)│
                    │    └──────┬──────┘
                    │           │
                    ▼           ▼
              Telegram reply（統一出口）
                    │
                    ▼
             ┌──────────────┐
             │ L4 觀察員    │ ← per-session, fire-and-forget
             │              │
             │ 記憶落地     │
             │ 向量化       │
             │ 快取重建     │
             │ 洞察產出     │
             │              │
             │ → 更新       │
             │  context_cache│
             └──────────────┘
                    │
                    ▼
             ┌──────────────┐
             │ Nightly      │ ← 18 步（從 43 步瘦身）
             │              │
             │ 記憶壓縮     │
             │ 結晶化       │
             │ 清理         │
             │ 健康檢查     │
             └──────────────┘
```

---

## 四個角色

### L1 主持人（Sonnet session）

**是什麼**：一個持續運行的 Claude Code session，像現在 Claude Code 跟 Zeal 對話一樣。

**做什麼**：
- 接收所有 Telegram 訊息
- 回覆前讀 context_cache/（L4 的洞察、使用者摘要）
- 簡單訊息 → 自己回覆（2 秒內）
- 複雜訊息 → spawn L2 深度思考，先跟使用者說「讓我想一下」
- /指令 → spawn Skill Worker
- 多群組同時進來 → 不阻塞，各自處理

**不做什麼**：
- 不寫任何資料庫
- 不跑 50 步 pipeline
- 不載入 Skill 定義

### L2 深度思考（per-message spawn）

**是什麼**：L1 spawn 的子 agent，處理需要深度思考的訊息。

**prompt 規格（恆定 ~10K tokens）**：

| 段落 | Tokens | 來源 | 更新者 |
|------|--------|------|--------|
| 身份 + Persona | ~1700 | persona.md | 恆定 |
| Crystal Rules Top-10 | ~800 | context_cache/active_rules.json | L4/Nightly |
| 使用者狀態摘要 | ~500 | context_cache/user_summary.json | L4 |
| MUSEON 自我狀態 | ~200 | context_cache/self_summary.json | Nightly |
| 對話歷史（10-20 輪） | ~3000 | group_context.db / session JSON | 即時讀 |
| L4 洞察 | ~300 | context_cache/pending_insights.json | L4 |
| 相關記憶 Top-5 | ~1500 | Qdrant hybrid_search | 即時搜 |
| 相關結晶 Top-3 | ~800 | crystal.db + Qdrant | 即時搜 |
| 當前訊息 | ~200 | L1 傳入 | — |
| **合計** | **~9500** | | **組建 ~650ms** |

**不做什麼**：
- 不寫資料庫（交給 L4）
- 不載入完整 ANIMA_USER（42KB 太大，讀摘要快取）
- 不載入 Skill 定義
- 不跑 P3-Fusion / MultiAgent / Dispatch

### L4 觀察員（per-session, fire-and-forget）

**是什麼**：L2 回覆後自動 spawn 的背景 agent，每個 session 獨立。

**觀察步驟**：

| # | 做什麼 | 讀 | 寫 | 耗時 |
|---|--------|---|---|------|
| 1 | 對話記憶落地 | 本輪對話 | memory_v3/L1_short/ | 100ms |
| 2 | 對話向量化 | 本輪文本 | Qdrant memories | 500ms |
| 3 | 群組上下文落地 | 群組對話 | group_context.db | 50ms |
| 4 | 使用者摘要快取重建 | ANIMA_USER | context_cache/user_summary.json | 200ms |
| 5 | 結晶引用計數 | L2 用了哪些結晶 | crystal.db | 50ms |
| 6 | 洞察偵測 | 對話 + 記憶 | context_cache/pending_insights.json | 500ms |
| 7 | 承諾追蹤 | 對話中的承諾 | pulse.db | 100ms |

**不做什麼**：
- 不說話（永遠不直接回覆使用者）
- 不呼叫外部 API
- 不跑 Skill
- 不做結晶化（那是 Nightly 的事）

**快取輸出**（L1 和 L2 的思考前置區）：

```
data/_system/context_cache/
├── {session_id}/
│   ├── user_summary.json      ← L4 每次更新
│   ├── pending_insights.json  ← L4 寫入，L1/L2 讀取後清空
│   └── active_rules.json      ← Nightly 排序
├── self_summary.json           ← Nightly 更新（全域共用）
└── persona_digest.md           ← 恆定（persona.md 精華）
```

### Nightly 整合（18 步）

**保留的 15 日次步驟**：

| # | 步驟 | 職責 |
|---|------|------|
| 1 | 記憶壓縮 | L1_short → L2_ep（7 天窗口壓縮） |
| 2 | 結晶化 | 高價值對話 → crystal.db 新結晶 |
| 3 | 教訓蒸餾 | 失敗記錄 → crystal_rules |
| 4 | Crystal Rules 排序快取 | 84 條 → top-10 → context_cache/ |
| 5 | ANIMA_MC 自我觀察 | 更新 days_alive、八原語趨勢 |
| 6 | 自我摘要快取 | → context_cache/self_summary.json |
| 7 | IDF 重建 | SparseEmbedder 更新 |
| 8 | Qdrant 健康檢查 | collection 狀態 |
| 9 | SQLite WAL checkpoint | 5 個 DB |
| 10 | 過齡清理 | JSONL 30 天截斷 |
| 11 | 群組上下文截斷 | group_context.db 超齡記錄 |
| 12 | 承諾到期提醒 | → pending_insights |
| 13 | 報告 | 系統健康摘要 |
| 14 | Skill 向量重索引 | Qdrant skills 更新 |
| 15 | 外部使用者 profile | 群組互動 → external_users 更新 |

**3 週次步驟**：

| # | 步驟 | 頻率 |
|---|------|------|
| 16 | 記憶深度壓縮（L2_ep → L2_sem） | 每週 |
| 17 | Morphenix 演化提案 | 每週 |
| 18 | 環境雷達 | 每週 |

**砍掉的（從 43 步中）**：好奇心路由、聯邦同步、工具市場、突觸共振、SoulRing、Recommender、drift_detector 獨立模組、MuseQA 獨立排程、MuseDoc 獨立排程。

---

## /指令處理

```
使用者：/strategy 幫我分析這個市場
    ↓
L1 辨識 /strategy
    ↓
L1 回覆「收到，分析中...」
    ↓
Spawn Skill Worker：
  - 載入 skills/master-strategy/SKILL.md（完整定義）
  - 載入 context_cache/（使用者摘要 + 洞察）
  - 搜尋相關 crystal
  - 執行分析
  - 直接 Telegram reply 發送結果
    ↓
L4 觀察 Skill 結果 → 結晶化候選
```

---

## 跨群隔離

| 層級 | 機制 |
|------|------|
| context_cache | per-session_id 子目錄 |
| L4 觀察 | per-session spawn，只讀自己的歷史 |
| L2 思考 | 帶明確 chat_id，reply 到指定群組 |
| pending_insights | per-session 隔離 |
| 最後防線 | ResponseGuard 發送前 chat_id 驗證 |

---

## 長期可持續設計

| 機制 | 防什麼 |
|------|--------|
| MemoryCompactor（Nightly） | 記憶無限增長 |
| context_cache 恆定 ~10K | prompt 膨脹回歸 |
| 每次新 session（不 --resume） | context 溢出 |
| 過齡清理（30 天 JSONL、7 天 CLI session） | 磁碟膨脹 |
| context_cache/ 最多 5 檔規則 | 快取層膨脹 |
| 新增 Nightly 步驟必須砍一個舊步驟 | 零增長紀律 |

---

## 實施路線

### Phase 1：context_cache 快取層（1-2 天）

- [ ] 建立 `data/_system/context_cache/` 目錄結構
- [ ] 實作 user_summary 生成（從 ANIMA_USER 壓縮為 500 tokens）
- [ ] 實作 active_rules 排序（crystal_rules top-10）
- [ ] 實作 self_summary 生成（從 ANIMA_MC 壓縮）
- [ ] 實作 pending_insights 讀寫介面（per-session）
- [ ] 修改 L2 prompt 範本：讀快取而非即時計算

**驗證**：快取層在 100ms 內讀完，L2 prompt < 10K tokens

### Phase 2：L1 升級為 Sonnet 主持人（2-3 天）

- [ ] 修改 MUSEON/CLAUDE.md 的 L1 角色定義
- [ ] L1 回覆前讀 context_cache/
- [ ] L1 判斷簡單/複雜的邏輯（內建於 prompt，不用分類器）
- [ ] 簡單訊息 L1 直接回覆
- [ ] 複雜訊息 spawn L2
- [ ] 測試：「早安」2 秒內回覆、「幫我分析」正確 spawn L2

**驗證**：10 則不同複雜度的訊息全部正確處理

### Phase 3：L4 觀察者（2-3 天）

- [ ] 實作 L4 prompt 範本
- [ ] 對話記憶落地（memory_v3 L1_short 寫入）
- [ ] 對話向量化（Qdrant upsert）
- [ ] 使用者摘要快取重建
- [ ] 洞察偵測
- [ ] 修改 L1/L2：完成後 fire-and-forget spawn L4
- [ ] 測試：L4 洞察出現在下一次 L1/L2 回覆中

**驗證**：L4 < 3 秒完成，快取檔正確更新

### Phase 4：Nightly 瘦身 + MemoryCompactor（1-2 天）

- [ ] 保留 15 日次 + 3 週次步驟
- [ ] 實作 MemoryCompactor（L1_short → L2_ep 壓縮）
- [ ] 合併 MuseQA + MuseDoc 職責到 Nightly
- [ ] 清理砍掉的步驟代碼
- [ ] ~/.claude/projects/ 7 天清理排程

**驗證**：Nightly < 30 分鐘完成

### Phase 5：/指令 Skill Worker（2-3 天）

- [ ] L1 的 /指令辨識邏輯
- [ ] Skill Worker prompt 範本
- [ ] Top-20 常用 Skill 指令映射表
- [ ] 測試：/dse → Worker → 結果 → Telegram reply

**驗證**：/dse 端到端 < 60 秒

---

## 硬規則（防止 v1 重蹈覆轍）

1. **L1/L2 回覆路徑禁止新增步驟**——要加東西放 L4 或 Nightly
2. **context_cache/ 最多 5 檔**——超過就合併
3. **L2 prompt 硬上限 12K tokens**——超過就 LRU 淘汰
4. **新增 Nightly 步驟必須砍一個舊步驟**
5. **L4 代碼不超過 200 行**——超過就是在重建 v1 pipeline
6. **每次修改先問「能刪什麼」**——CLAUDE.md Pre-Flight #0
