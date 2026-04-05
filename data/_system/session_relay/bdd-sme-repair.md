# BDD SME 十大情境 — 修復清單

> **建立時間**：2026-04-05 09:30
> **來源**：BDD 實機測試 10 Scenario × 27 輪 + 星座系統診斷
> **狀態**：in_progress

---

## 已完成

- [x] **P0-A：刪除 brain.py P0+P1 後處理注入** — `【順便一提】` 和 `🧠` 的生成源頭
  - 檔案：`src/museon/agent/brain.py` 行 1690-1734
  - 刪除整段 P0（思考軌跡注入）+ P1（盲點提醒注入），共 45 行
  - 現在 `final_response = response_text` 直接到 BrainResponse
  - 死碼：`get_blindspot_hint_for_query()` 和 `_estimate_user_exploration_level()` 已無消費者

- [x] **P0-B：brain_prompt_builder 星座注入加 INFO log**
  - 檔案：`src/museon/agent/brain_prompt_builder.py` 行 205-213
  - 加了三個分支的 INFO/WARNING log（注入成功/被截斷/空字串/失敗）
  - 用於確認星座注入是否在 runtime 實際發生

---

## 待修復 — 系統洩漏（BDD 測試發現）

- [ ] **LEAK-03：系統檔案路徑洩漏**
  - 現象：S03 R3 回覆中出現 `/Users/ZEALCHOU/MUSEON/數位行銷提案大綱_製造業.md`
  - 根因：Brain 的 LLM 回覆中包含本地檔案路徑
  - 修復：ResponseGuard 加 pattern 過濾 `/Users/` 開頭的路徑
  - 檔案：`src/museon/governance/response_guard.py`

- [ ] **LEAK-04：系統身份洩漏**
  - 現象：S10 R1 回覆中出現「你已經在用 MUSEON，它跑在 Claude 上」
  - 根因：Brain prompt 中有 MUSEON 自我意識資訊，LLM 直接引用
  - 修復：ResponseGuard 加 pattern 或 persona_digest 調整（不告訴 LLM 使用者在用什麼系統）
  - 檔案：`src/museon/governance/response_guard.py` + `data/_system/context_cache/persona_digest.md`

---

## 待修復 — 行為偏差（BDD 測試發現）

- [ ] **BEH-01：Bot 在使用者迴避時順從而非挑戰**
  - 現象：使用者說「都要」「不想補償」→ Bot 附和
  - 涉及：S01 R2, S05 R2
  - 根因：「不失真」在 Brain prompt 中的權重低於「不奪權」
  - 修復方向：在 active_rules 或 persona_digest 加規則——「使用者的第一反應是模糊/迴避時，是最需要挑戰的時刻」
  - 檔案：`data/_system/context_cache/active_rules.json` 或 `data/_system/crystal_rules.json`

- [ ] **BEH-02：沒有數據就列方法清單**
  - 現象：S06 R1 直接列「最快見效的三招」，不問數據
  - 根因：同 BEH-01，加上「先交付」的慣性壓過「先閘門」
  - 修復方向：同 BEH-01 的規則，額外在 persona_digest 強調「未完成資源盤點 → 不提供完整策略」
  - 檔案：同上

- [ ] **BEH-03：列功能比較表而非重新定義問題**
  - 現象：S10 R1 列了 ChatGPT vs Claude 比較表
  - 根因：同 BEH-01
  - 修復方向：同上

- [ ] **BEH-04：問了問題但同時給完整答案**
  - 現象：S03 R1 問了 3 個問題但同時給了完整 10 頁大綱
  - 根因：「先交付再展開」的指示沒有區分「急迫止血」vs「資訊閘門」
  - 修復方向：在 persona_digest 或 active_rules 加「資訊閘門模式：當關鍵資訊不足時，先問再給，不同時給」
  - 檔案：同上

- [ ] **BEH-05：沒有先接住情緒**
  - 現象：S08 R1 直接進入分析，缺少一句話的情緒共情
  - 根因：webhook 路徑可能跳過 resonance 觸發條件
  - 修復方向：在 persona_digest 加「低能量+挫折感的訊號 → 先一句話接住再診斷」
  - 檔案：同上

- [ ] **BEH-06：效率臨界點未觸發工具升級建議**
  - 現象：S07 R2 使用者說每週 3-4 小時手動對表，Bot 繼續問表格結構
  - 根因：Bot 卡在「解決 Excel 問題」框架，沒跳出看更大圖景
  - 修復方向：同 BEH-01 的規則體系可涵蓋

---

## 待修復 — 星座系統

- [x] **CONST-01：Nightly step 32.6 constellation_decay 崩潰**
  - 錯誤：`unsupported operand type(s) for /: 'PosixPath' and 'dict'`
  - 根因：registry.json 的 constellations 是 list of dicts，舊代碼把整個 dict 當 name 傳給 Path /
  - 修復：`_step_constellation_decay` 重新加入 nightly_pipeline.py，修正 list of dicts 解析邏輯
  - 測試：實機跑 `func()` 回傳 8 星座 × 8 使用者，無錯誤

- [ ] **CONST-02：absurdity 星座 tracked_skills = 0**
  - 現象：荒謬六芒星的 definition.json 沒有 tracked_skills
  - 影響：Skill 使用後不會更新荒謬六芒星的維度，永遠停在 0.5
  - 修復：在 absurdity/definition.json 加 tracked_skills（映射到相關 Skill）
  - 檔案：`data/_system/constellations/absurdity/definition.json`

- [ ] **CONST-03：確認星座注入在 runtime 是否生效**
  - 狀態：已加 INFO log（P0-B），需要重啟 Gateway 後觀察
  - 若注入成功：OK，只是維度全 0.5 沒差異化（需要 CONST-02 修復）
  - 若注入失敗：需要進一步調查 data_dir 路徑或 exception

- [ ] **CONST-04：所有雷達維度 = 0.5（bootstrap 預設值）**
  - 原因：Bootstrap 後從未被 Skill 使用更新
  - 影響：星座摘要永遠回傳同樣的 top-3（荒謬六芒星的前三維度）
  - 修復：CONST-02 修完後，透過正常使用自然更新；或手動根據歷史數據初始化

---

## 修復優先序

| 優先級 | 項目 | 預估工作量 | 依賴 |
|--------|------|-----------|------|
| **P0** | ~~LEAK-01/02~~ 已完成 | — | — |
| **P1** | BEH-01~06 行為偏差（一次性改 prompt/rules） | 中 | 需要重啟 |
| **P2** | LEAK-03/04 路徑和身份洩漏 | 小 | 需要重啟 |
| **P3** | CONST-01 Nightly decay 修復 | 小 | — |
| **P4** | CONST-02 absurdity tracked_skills | 小 | — |
| **P5** | CONST-03 確認注入 | 觀察 | 需要重啟 |
| **驗證** | 重啟 Gateway → 跑 10 Scenario 回歸測試 | 30-60 min | 全部修完 |

---

## 下一步

1. 完成 P1-P4 所有修復
2. 重啟 Gateway
3. 觀察 CONST-03（星座注入 log）
4. FV 驗證修復項
5. 全部 10 Scenario 重跑回歸測試
