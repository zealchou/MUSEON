# Entity Registry 建置 — Session Relay

## 目標
建立統一人物身份層（Entity Registry），解決 Bot「有時記得有時不記得」的問題，支援人脈主動識別與跟進提醒。

## 設計原則（DSE 驗證）
1. 使用者指定，系統建議 — Entity 合併/會議記錄人物對應永遠由人類決定
2. 互動驅動，不是 Profile 驅動 — 追蹤互動時間線，不是建人物檔案
3. 我的視角，不是上帝視角 — 只記錄使用者參與的互動

## 當前進度

### Phase 0a：修 Ares _index.json 空殼 ✅
- [x] 手動重建 _index.json（22 profiles indexed）
- [x] profile_store.py 加 rebuild_index() 方法
- [x] external_bridge.py 加索引一致性驗證

### Phase 0b：修 Brain 人物搜尋路徑 ✅
- [x] brain_prompt_builder.py 三層搜尋（alias → Ares → ExternalAnima）

### Phase 1：alias 表 ✅
- [x] group_context.py 加 entity_aliases 表 + CRUD（4 方法）

### Phase 2：溫度自動衰減 ✅
- [x] Nightly Step 18.6 中加衰減邏輯（不新增步驟）
- hot → warm (14天), warm → cold (30天)

### Phase 3：chat_scope 修復 ✅
- [x] brain.py 三處 L4 初始化改用 self.memory_manager
- [x] l4_cpu_observer.py 改用 store() API + chat_scope 推導
- [ ] 會議記錄 Skill 加 entity 指定流程（留待下一 session）

### Phase 4：專案/事件追蹤表 ✅
- [x] group_context.py 加 projects, project_entities, events 表 + CRUD（7 方法）

### 收尾
- [ ] FV 三維驗證（審計 agent 進行中）
- [ ] 五張藍圖同步（藍圖 agent 進行中）
- [ ] git commit

## 關鍵發現
- _index.json 空殼：Ares search、ProactiveIntel alerts、Brain 注入三條管線全部空轉
- L4 記憶寫入靜默失敗：brain.py 傳了 MemoryStore 給 L4，不是 MemoryManager
- 四個人物 store 互不連通：ExternalAnima / Ares / GroupContextStore / memory_v3

## 關鍵檔案
- src/museon/athena/profile_store.py — Ares 七層人物檔案
- src/museon/athena/external_bridge.py — External → Ares 橋接
- src/museon/agent/brain_prompt_builder.py — Brain 人物搜尋注入
- src/museon/governance/group_context.py — 群組上下文 SQLite
- src/museon/governance/multi_tenant.py — ExternalAnima 管理
- src/museon/nightly/nightly_pipeline.py — Nightly 排程
- src/museon/agent/brain.py — L4 初始化（紅區）
- src/museon/agent/l4_cpu_observer.py — L4 CPU 觀察者
