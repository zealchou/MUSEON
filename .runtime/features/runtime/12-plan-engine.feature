Feature: Plan-Engine — 六階段工作流、plan.md 持久化與批註循環
  作為 MUSEON 的計畫引擎（原生技能）
  我是工作流前段引擎——用持久化 .md 檔案將混沌起點收斂為清晰計畫後交棒
  核心命題：AI 協作中最貴的失敗不是做錯，是基於錯誤假設往前衝
  plan.md 作為人機共享的可變狀態，解決三個問題：
    (1) AI 猜測而非查證導致的方向性錯誤
    (2) 對話式指令無法精準定位問題的模糊性
    (3) 執行後才發現偏離的沉沒成本
  六階段流程：Research → Plan → Annotate → Todo → Execute → Close
  物理隔離「想」與「做」，把 AI 的認知狀態透明化，讓人類判斷力精準注入

  Background:
    Given MUSEON Brain 已初始化
    And Plan-Engine 作為原生技能已載入 skills/native/plan-engine/
    And plan.md 檔案路徑為 data/workspace/plan.md
    And knowledge-lattice 可用（用於 Close 階段結晶化）
    And eval-engine 可用（用於追蹤計畫品質）

  # ════════════════════════════════════════════
  # Section 1: 觸發評估 — 何時需要啟動計畫引擎
  # ════════════════════════════════════════════

  Scenario: 自動偵測需要計畫的任務
    When 使用者描述一個涉及以下條件的任務：
      | 條件                           | 範例                                    |
      | 涉及 3+ 個檔案修改             | 「重構認證系統」                        |
      | 預估執行時間 > 10 分鐘         | 「建一個新的 API 端點含測試」           |
      | 涉及不可逆操作                 | 「資料庫遷移」                          |
      | 關鍵字觸發                     | 重構、新功能、整合、遷移、架構          |
      | 範圍模糊需要釐清               | 「讓應用程式更快」                      |
    Then MUSEON 建議：「這個任務建議先用 /plan 做計畫對齊」
    And 不強制——使用者可以拒絕

  Scenario: 不需要計畫的簡單任務
    When 使用者描述以下類型的任務：
      | 條件                           | 範例                                    |
      | 單一檔案 ≤ 30 行修改           | 「修正 typo」                           |
      | 原因明確、範圍確定             | 「修復登入按鈕顏色」                    |
      | 格式調整                       | 「把 tab 換成 space」                   |
      | 使用者明確說不要計畫           | 「直接做就好」「別計畫了」              |
    Then MUSEON 直接執行，不建議 plan-engine

  Scenario: /plan 指令強制啟動
    When 使用者輸入 /plan
    Then Plan-Engine 立即啟動
    And 建立 plan.md（若不存在）
    And 進入 Stage 1: Research
    And plan.md 狀態設為 "Draft"

  # ════════════════════════════════════════════
  # Section 2: Stage 1 Research — 研究階段
  # ════════════════════════════════════════════

  Scenario: Research 階段 — 讀取相關檔案建立事實
    When Plan-Engine 進入 Stage 1 Research
    Then 系統讀取相關原始碼、文件、資料夾結構
    And 驗證技術限制
    And 檢查現有模式
    And 將已確認的事實寫入 plan.md 的 Research Log：
    And 格式為：「- [x] [事實] — 來源：[檔案路徑 / 文件 URL / 命令輸出]」
    And 每項事實必須有來源標註——絕不猜測

  Scenario: Research 階段 — 標記未驗證假設
    Given 研究過程中遇到無法確認的資訊
    When 系統無法從現有資源驗證某個資訊
    Then 將其標記為假設：「- [ ] 假設：[內容] → 驗證方式：[如何確認]」
    And 假設必須附帶驗證方式
    And 假設在 Annotate 階段由使用者確認或推翻

  Scenario: Research 階段 — 非程式碼任務的研究
    When 任務不涉及程式碼（如商業規劃、投資分析）
    Then 研究行為對應調整：
      | 任務類型     | 研究行為                               |
      | 商業規劃     | 讀取客戶資料 + 市場數據 + 競品分析     |
      | 投資分析     | 讀取資產數據 + 總經數據 + 歷史績效     |
      | Skill 鍛造   | 讀取相關 Skill + ACSF 流程 + 註冊表   |
      | 內容創作     | 讀取品牌指南 + 受眾數據 + 過往內容     |

  # ════════════════════════════════════════════
  # Section 3: Stage 2 Plan — 計畫階段
  # ════════════════════════════════════════════

  Scenario: Plan 階段 — 必要組件
    When Plan-Engine 進入 Stage 2 Plan
    Then plan.md 的 Plan 區必須包含：
    And 方法說明（為何選這個方案 + 替代方案 + 取捨）
    And 變更清單（什麼 + 在哪裡 + 為什麼——三元組）
    And 風險分析（甜頭 + 代價 + 回滾計畫）
    And Skill 路由建議（建議用哪些 Skill 以及為什麼）
    And 若涉及程式碼則包含關鍵程式碼片段

  Scenario: Plan 階段 — 所有假設可追溯
    Given Plan 區引用了 Research Log 中的事實
    When 計畫內容引用了一個假設
    Then 該假設在 Research Log 的 Assumptions 區清楚列出
    And 假設未經驗證時不能作為計畫的唯一依據
    And Plan 會標記「此步驟依賴假設 X，需在批註中確認」

  # ════════════════════════════════════════════
  # Section 4: Stage 3 Annotate — 批註循環
  # ════════════════════════════════════════════

  Scenario: 批註循環 — AI 寫 plan.md → 人類批註 → AI 更新
    Given plan.md 的 Plan 區已完成初稿
    When 使用者檢閱 plan.md 並加入批註
    And 使用者說 "/plan annotate" 或 "處理批註"
    Then AI 讀取使用者的批註
    And 只更新 plan.md——絕不開始執行
    And 重新檢視 Assumptions 區，標記哪些假設被批註推翻
    And plan.md 批註輪次 +1

  Scenario: 批註推翻 Research Log 時 — 人類優先但標記矛盾
    Given Research Log 記錄了事實 A
    When 使用者批註說「A 不對，應該是 B」
    Then AI 以使用者批註為準
    And 但在 Research Log 中標記矛盾：「[更正] A → B — 來源：使用者批註 Round X」
    And 計畫相應部分同步更新

  Scenario: 批註超過 6 輪 — 建議重新評估任務範圍
    Given plan.md 批註輪次已達到 6
    When 使用者嘗試進行第 7 輪批註
    Then 系統建議：「已批註 6 輪，建議評估任務是否需要拆分成更小的範圍」
    And 不強制中止——使用者可以繼續
    And 但系統記錄此信號到 eval-engine 作為計畫品質追蹤

  Scenario: 批註的優勢 — 比對話更精準
    Given 批註是在 plan.md 的特定位置直接修改
    When 使用者用批註而非對話提供回饋
    Then 回饋精準定位到計畫的具體位置（不是模糊的「感覺哪裡不對」）
    And plan.md 是持久化檔案，不會被 context 壓縮丟失
    And 每輪批註都有完整的修改歷史

  # ════════════════════════════════════════════
  # Section 5: Stage 4 Todo — 任務拆解
  # ════════════════════════════════════════════

  Scenario: Todo 任務拆解 — 原子化
    When Plan 被使用者核准後進入 Stage 4 Todo
    Then plan.md 的 Todo 區被填入具體任務
    And 每個任務是原子性的（可在 10 分鐘內完成）
    And 任務按階段分組，有明確順序
    And 格式為 checkbox：「- [ ] Task 1.1: [具體任務]」

  Scenario: Todo 階段等待使用者確認
    Given Todo 區已填入任務清單
    When 使用者檢閱 Todo 清單
    Then 使用者可以增刪改任務
    And 使用者確認後才進入 Execute 階段
    And plan.md 狀態從 "Annotating" 變為 "Ready"

  # ════════════════════════════════════════════
  # Section 6: Stage 5 Execute — 執行階段
  # ════════════════════════════════════════════

  Scenario: 執行階段 — 按 Todo 順序機械執行
    When 使用者說 "/plan execute" 或確認開始執行
    Then plan.md 狀態變為 "Executing"
    And 系統按 Todo 清單順序逐一執行
    And 每完成一項任務就在 plan.md 標記 [x]
    And 執行中保持機械紀律——不偏離計畫

  Scenario: 執行中遇到計畫外問題 — 暫停等待人類決定
    Given 執行過程中遇到計畫外的問題
    When 問題超出 plan.md 的預期範圍
    Then 系統在 plan.md 加入 ⚠️ 標記
    And 暫停執行
    And 通知使用者：「遇到計畫外問題：[問題描述]，需要你的決定」
    And 等待使用者回覆後再繼續
    And 絕不自行解決計畫外問題

  Scenario: Revert over Patch — 方向錯了就回退而非修補
    Given 執行過程中發現方向性錯誤
    When 錯誤是方向性的（不是局部的 bug）
    Then 系統建議 Revert（回退）而非 Patch（修補）
    And Revert 記錄寫入 plan.md 的 Revert Log
    And 記錄包含：時間、原因、影響範圍、教訓
    And 回退後用更小的範圍重新開始

  Scenario: 執行中的人類回饋 — 最小化
    When 使用者在執行過程中提供回饋
    Then 回饋應盡量精簡（「功能沒實作」「再寬一點」「差 2px」）
    And 優先用截圖而非文字
    And 目的是讓執行保持動量，不因冗長討論而中斷

  # ════════════════════════════════════════════
  # Section 7: Stage 6 Close — 收尾階段
  # ════════════════════════════════════════════

  Scenario: Close 階段 — 所有 Todo 完成後
    Given plan.md 的所有 Todo 項目都標記為 [x]
    When 系統確認所有任務完成
    Then 生成執行摘要，包含：完成內容、遇到的問題、學到的教訓
    And 摘要寫入 plan.md 的收尾摘要區

  Scenario: Close — Research Log 有價值資訊結晶到 Knowledge-Lattice
    Given Close 階段檢視 Research Log
    When Research Log 中包含有價值的發現或教訓
    Then 系統建議將這些發現結晶到 knowledge-lattice
    And 使用者可以選擇哪些值得結晶
    And 結晶後的知識成為未來計畫的參考

  Scenario: Close — Revert Log 作為未來護欄
    Given plan.md 的 Revert Log 有記錄
    When Close 階段處理 Revert Log
    Then 回退原因被提煉為未來的防護規則
    And 例如：「不要在沒有先對齊理解時就啟動 agent 重寫」
    And 防護規則可被 Knowledge-Lattice 結晶為 Lesson 型結晶

  Scenario: Close — 刪除原始 plan.md
    Given 收尾摘要已生成且存檔
    When Close 完成
    Then 原始 plan.md 可被標記為完成
    And 摘要已存入 dev log 或 knowledge-lattice
    And plan.md 可被刪除以保持工作區整潔
    And 若使用者選擇保留則移至 data/workspace/archive/

  # ════════════════════════════════════════════
  # Section 8: 硬閘與軟閘
  # ════════════════════════════════════════════

  Scenario: HG-PLAN-NO-GUESS — 不猜測，要查證
    When Research 階段遇到不確定的資訊
    Then 系統不猜測答案
    And 將其標記為假設（⚠️ 未驗證）
    And 等待 Annotate 階段由使用者確認
    And 基於猜測往前衝是最昂貴的失敗模式

  Scenario: HG-PLAN-NO-SKIP-ANNOTATE — 不跳過批註階段
    When Plan 階段完成
    Then 系統必須等待至少一輪批註才能進入 Execute
    And 即使使用者說「就這樣做」，系統也會確認：「確認進入執行階段？」
    And 批註是品質保證的核心機制

  Scenario: HG-PLAN-REVERT-OVER-PATCH — 方向錯了就回退
    When 執行中發現方向性錯誤
    Then 系統優先建議回退（Revert）而非修補（Patch）
    And 回退的成本低於持續在錯誤方向上修補
    And 每次回退必須記錄原因和教訓

  Scenario: HG-PLAN-NO-EXECUTE-WITHOUT-APPROVAL — 未核准不執行
    When plan.md 狀態為 "Draft" 或 "Annotating"
    Then 系統不會開始任何執行動作
    And 必須等使用者明確說 "/plan execute" 或等效確認
    And 物理隔離「想」與「做」是 plan-engine 的核心設計

  # ════════════════════════════════════════════
  # Section 9: DNA27 三迴圈適配
  # ════════════════════════════════════════════

  Scenario: fast_loop — 跳過計畫直接執行
    Given DNA27 路由判定為 fast_loop（簡單快速任務）
    When 使用者的請求為簡單明確的任務
    Then Plan-Engine 不介入
    And 直接由 Brain 處理

  Scenario: exploration_loop — 精簡版計畫
    Given DNA27 路由判定為 exploration_loop（探索性任務）
    When 使用者的請求需要一些探索但不需要完整計畫
    Then Plan-Engine 啟動精簡模式
    And 只做 Research + 簡易 Plan
    And 跳過正式 Annotate 循環（使用者口頭確認即可）

  Scenario: slow_loop — 完整六階段
    Given DNA27 路由判定為 slow_loop（深度任務）
    When 使用者的請求需要深度思考和系統性規劃
    Then Plan-Engine 啟動完整六階段流程
    And Research → Plan → Annotate（1~6 輪）→ Todo → Execute → Close
    And 每個階段都嚴格遵守硬閘規則

  # ════════════════════════════════════════════
  # Section 10: 持久化與跨對話延續
  # ════════════════════════════════════════════

  Scenario: plan.md 跨對話持續存在
    Given plan.md 存在於 data/workspace/plan.md
    When 對話結束後再開啟新對話
    Then 新對話中 Plan-Engine 自動偵測到 plan.md 存在
    And 讀取 plan.md 的當前狀態
    And 從上次中斷的階段繼續
    And plan.md 是持久化的——不受對話 context 限制

  Scenario: 多個計畫同時存在
    Given 使用者有多個進行中的專案
    When 使用者需要同時管理多個計畫
    Then 計畫檔案以專案名區分：plan-{project}.md
    And 使用者可以切換：/plan switch {project}
    And 每個計畫獨立追蹤狀態
