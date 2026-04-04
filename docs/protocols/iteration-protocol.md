# 迭代協議（Iteration Protocol）

每次進行系統迭代時，請依序執行：

---

## Step 1：施工前檢查（防禦性）

- 完成 `docs/protocols/pre-flight-checklist.md` 全部清單
- 確認修改安全分級（見 pre-flight-checklist.md 末尾速查表）

---

## Step 2：迭代前審計

```bash
python -m museon.doctor.system_audit --home /Users/ZEALCHOU/MUSEON
```

- 必須在修改程式碼**之前**執行
- 記錄當前系統基準狀態
- 若有 CRITICAL 問題，優先修復再開始迭代

---

## Step 3：DSE 分析

- 對審計中發現的問題，使用 DSE 第一性原理分析
- 找出「問題背後的問題」
- 向使用者報告分析結果，等待確認再動手

---

## Step 4：實作修改

- 按照分析結果進行修改
- 遵循安全分級規則

---

## Step 5：施工後檢查（建構性）

- 完成 `docs/protocols/post-build-checklist.md` 全部清單
- 跑 `scripts/validate_connections.py` 確認無孤立連線

---

## Step 6：Fix-Verify 閉環驗證（強制）

> **此步驟不可跳過。AI 說「修好了」不算數，隔離審計員三維驗證 100% 全過才算數。**

執行 `/fv` 或手動走 Fix-Verify Workflow：

### Phase 1
從修改內容自動產生三維 BDD 驗證腳本（D1 行為 + D2 接線 + D3 藍圖）

### Phase 2
**Spawn 隔離審計員 subagent**（不帶修復記憶）執行驗證
- 審計未 100%？→ 根據失敗摘要修復 → 重跑 Phase 2 → **反覆直到三維全部 100%**
- 迴圈上限 5 輪。超過 5 輪強制暫停重新審視根因
- 精簡場景（純 typo/樣式）可降級為 D1 2 案例 + D2 快速確認

### Phase 2.5（BDD 多路反向驗證——大型迭代時強制）

判斷標準：影響 ≥ 3 個模組、或刪除/替換模組、或改動 `.runtime/` 排程/啟動路徑 → 強制

Spawn 5 路獨立 BDD 審計 agents（各自不知道其他 agent 在驗什麼）：

a. **功能端到端**：模擬使用者操作，驗證核心路徑（如 signal_lite 的 FAST/SLOW/EXPLORATION 全路徑）
b. **死碼零殘留**：grep 所有刪除模組的名稱、型別、方法名在 `src/` + `tests/` 中為零
c. **系統健康修復**：逐項驗證每個修復的功能是否生效（讀程式碼確認方法存在+可 import）
d. **基礎設施路徑**：驗證 Gateway/supervisord/launchd/腳本 的路徑配置正確
e. **藍圖一致性**：五張藍圖版本號正確 + 已刪除模組只在版本紀錄中 + 新模組有記載

每路 agent 獨立輸出 PASS/FAIL 清單。任何 FAIL → 立即修復 → 重跑該路驗證。全部 5 路 PASS 才進入 Phase 3。

### Phase 3（不可跳過）
教訓同步四管道——每條教訓必須同時寫入：
- `data/_system/heuristics.json`（Brain prompt 每次注入）
- `data/_system/crystal_rules.json`（Crystal Actuator 評估）
- `data/memory_v3/boss/L1_short/`（Brain 記憶搜尋）
- `~/.claude/projects/.../memory/feedback_*.md`（Claude Code auto-memory）

> **只寫 Claude memory 不寫 MUSEON 三管道 = MUSEON 學不到，下次同樣的錯由 Bot 再犯一次**

---

## Step 7：藍圖同步

- 檢查是否需要更新五張藍圖（見 `docs/protocols/blueprint-maintenance.md`）
- 如果改了共享狀態 → 更新 joint-map.md
- 如果改了 import 關係 → 更新 blast-radius.md
- 如果改了模組拓撲 → 更新 system-topology.md
- 如果改了持久層 → 更新 persistence-contract.md
- 如果改了 Skill 記憶連線 → 更新 memory-router.md

---

## Step 8：Git Commit

- 藍圖更新與程式碼修改必須在同一個 commit
- FV 通過後直接 commit，不問（見 feedback_18）
