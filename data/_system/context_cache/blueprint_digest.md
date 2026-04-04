# 藍圖精簡摘要（自動生成）

> 用途：Claude Code 施工前快速了解系統架構，判斷需要深讀哪張藍圖。
> 不要依賴此摘要做精確判斷——需要細節時讀完整藍圖。

### 神經圖摘要（system-topology）

版本：v1.81
節點數：13
關鍵節點：新增模組, Debug, 審計, 迭代, 依賴關係, 治理文件, 背景, 無孤立節點, 外部服務必監控, 資料層必連, 雙向一致, 輸入連線, 輸出連線

### 爆炸圖摘要（blast-radius）

版本：v2.00
🔴 禁區/紅區：event_bus(扇入≥40), brain.py(14), nightly_pipeline(8), PulseDB(13讀)
🟡 黃區：skill_router(5), memory_manager(6), crystal_store(5), brain_prompt_builder(6)
🟢 綠區：其餘模組（扇入 0-1）

### 水電圖摘要（persistence-contract）

版本：v1.53
引擎 1: SQLite — pulse.db, crystal.db, group_context.db, workflow_state.db, registry.db, message_queue.db, market_ares.db
引擎 2: Qdrant — memories(1024d), skills, crystals, workflows, documents, references, primals, semantic_response_cache(512d)
引擎 3: Markdown — PULSE.md, SOUL.md, memory/{date}/, skills/{category}/

### 接頭圖摘要（joint-map）

版本：v1.68
共享狀態：4 個
🔴 紅區：ANIMA_MC.json(8寫), PULSE.md(7寫)
🟡 黃區：ANIMA_USER.json(3寫9讀), PulseDB(4寫13讀), context_cache(3寫2讀)

### 郵路圖摘要（memory-router）

版本：v1.26
8 個記憶系統：knowledge-lattice, user-model, wee, eval-engine, session-log, auto-memory, morphenix, diary
L4 CPU Observer → memory_manager（零 token 記憶寫入）

### 快速查詢指引

| 我要做什麼 | 讀哪張藍圖 |
|-----------|-----------|
| 改模組呼叫關係 | system-topology.md |
| 確認改動影響範圍 | blast-radius.md |
| 查資料存在哪 | persistence-contract.md |
| 查共享狀態誰在讀寫 | joint-map.md |
| 查記憶/洞見流向 | memory-router.md |

---
生成時間：2026-04-04T18:03:33