Feature: Eval-Engine — Q-Score 品質儀表板、趨勢追蹤、A/B 比對與盲點雷達
  作為 MUSEON 的品質度量系統
  我是閉環回饋的核心——沒有度量就沒有真正的演化
  感覺變好了不算，數據說變好了才算
  我提供四大子系統：
    即時品質儀（Q-Score）— 每次回答的品質評分
    趨勢追蹤器 — 跨對話的品質曲線
    A/B 比對器 — 迭代前後效果驗證
    盲點雷達 — 系統性弱項偵測
  加上兩個延伸：
    客戶成效追蹤器 — 企業 KPI 前後測
    Skill 使用率熱力圖 — Skill 實際使用分布

  Background:
    Given MUSEON Brain 已初始化
    And Eval-Engine 模組已載入
    And deep-think Phase 2 四點審計可用（理解度/深度/清晰度/可行動性）
    And 品質資料庫 data/eval/quality_db.json 已建立
    And Skill 觸發事件日誌 data/eval/skill_events.json 已建立

  # ════════════════════════════════════════════
  # Section 1: Q-Score 即時品質儀 — 每次回答的品質量化
  # ════════════════════════════════════════════

  Scenario: Q-Score 計算 — 基於 deep-think Phase 2 四點審計
    Given deep-think Phase 2 對一次回答完成四點審計
    And 審計結果為：理解度=0.85, 深度=0.70, 清晰度=0.90, 可行動性=0.75
    When Eval-Engine 計算 Q-Score
    Then Q-Score = 0.30×0.85 + 0.25×0.70 + 0.20×0.90 + 0.25×0.75
    And Q-Score = 0.255 + 0.175 + 0.180 + 0.1875 = 0.7975
    And 品質等級為 🟢 優秀（Q-Score > 0.7）
    And 結果被記錄到品質資料庫，包含時間戳和對話 ID

  Scenario: Q-Score 品質等級分層
    When Q-Score 被計算出來
    Then 品質等級依以下規則判定：
      | Q-Score 範圍 | 等級 | 標記 |
      | > 0.7        | 優秀 | 🟢   |
      | 0.5 ~ 0.7    | 及格 | 🟡   |
      | < 0.5        | 待改善 | 🔴  |
    And 每個等級伴隨對應的建議動作
    And 🔴 觸發 Morphenix 關注信號

  Scenario: 單一維度為 0 時 Q-Score 反映退化
    Given deep-think Phase 2 審計結果為：理解度=0.80, 深度=0.0, 清晰度=0.85, 可行動性=0.60
    When Eval-Engine 計算 Q-Score
    Then Q-Score = 0.240 + 0.0 + 0.170 + 0.150 = 0.560
    And 品質等級為 🟡 及格
    And 但系統額外標記「深度維度為零」的警告
    And 警告被送入 Morphenix 的觀察日誌

  # ════════════════════════════════════════════
  # Section 2: 滿意度代理指標 — 行為信號推估
  # ════════════════════════════════════════════

  Scenario: 正向行為信號偵測
    When 使用者在收到回答後執行以下行為之一：
      | 行為                           | 信號權重 |
      | 直接根據回答採取行動           | +1.0     |
      | 使用肯定語言（好的/對/謝謝）   | +1.0     |
      | 在回答基礎上深入追問           | +1.0     |
      | 在後續對話中引用之前的回答     | +1.0     |
    Then 滿意度代理指標記錄正向信號

  Scenario: 負向行為信號偵測
    When 使用者在收到回答後執行以下行為之一：
      | 行為                           | 信號權重 |
      | 重複提問相同問題               | -1.5     |
      | 否定或要求重來                 | -1.5     |
      | 對話中斷（長時間不回應）       | -1.5     |
      | 突然轉換話題                   | -1.5     |
    Then 滿意度代理指標記錄負向信號

  Scenario: 滿意度代理計算
    Given 過去 10 次互動中，正向信號 7 次（+7.0），負向信號 2 次（-3.0）
    When 計算滿意度代理指標
    Then Satisfaction Proxy = (7.0 - 3.0) / 10 = 0.40
    And 0.40 落在 0~0.5 範圍 → 標記為「觀察中」
    And 若 Proxy > 0.5 → 「健康」
    And 若 Proxy < 0 → 「警報」→ 觸發品質檢討

  # ════════════════════════════════════════════
  # Section 3: 趨勢追蹤器 — 跨對話品質曲線
  # ════════════════════════════════════════════

  Scenario: 日度品質趨勢計算
    Given 品質資料庫已累積 30 天的 Q-Score 資料
    When 使用者查詢 /eval trend
    Then 系統計算每日平均 Q-Score
    And 顯示 7 天 / 30 天的品質曲線
    And 標記趨勢方向（上升 ↑ / 穩定 → / 下降 ↓）
    And 若連續 3 天下降則觸發品質警報

  Scenario: 領域別趨勢分析
    Given MUSEON 在不同領域（商業/技術/人際/投資）有不同品質表現
    When 使用者查詢 /eval trend 商業
    Then 系統篩選該領域的 Q-Score 資料
    And 顯示該領域的專屬品質曲線
    And 與全域平均進行比較
    And 標記該領域的強項和弱項

  Scenario: 連續低品質警報
    Given 連續 3 次回答的 Q-Score 低於 0.5
    When 第 3 次低分被記錄
    Then 系統自動觸發品質警報
    And 警報內容包含：最近 3 次回答的具體弱項維度
    And 警報被送入 Morphenix 作為迭代觸發信號
    And 警報同時記錄到 data/eval/alerts.json

  # ════════════════════════════════════════════
  # Section 4: A/B 比對器 — 迭代前後效果驗證
  # ════════════════════════════════════════════

  Scenario: Morphenix 迭代前自動基線快照
    Given Morphenix 準備執行一次迭代（如 v2.1.1 → v2.1.2）
    When Morphenix 發出迭代開始信號
    Then Eval-Engine 自動擷取當前品質基線：
    And 基線包含：最近 7 天平均 Q-Score、各維度分數、Satisfaction Proxy、Skill Hit Rate
    And 基線被標記為 "pre_iteration_baseline" 存入品質資料庫
    And 基線一旦建立不可事後修改（防止回溯偏差）

  Scenario: 迭代後 A/B 比對
    Given Morphenix 迭代完成且已運行 7 天
    When 7 天觀察期結束
    Then Eval-Engine 自動生成 A/B 比對報告
    And 報告包含：
      | 維度             | 迭代前 | 迭代後 | 變化   | 判定     |
      | Q-Score 平均     | 0.72   | 0.78   | +0.06  | ✅ 有效  |
      | 理解度           | 0.80   | 0.85   | +0.05  | ✅ 提升  |
      | 清晰度           | 0.75   | 0.67   | -0.08  | ⚠️ 退化 |
      | Satisfaction     | 0.55   | 0.62   | +0.07  | ✅ 提升  |
    And 若任何維度退化則自動標記警告
    And 報告被送入 Morphenix 作為迭代效果評估
    And Morphenix 根據結果決定是否回滾

  Scenario: A/B 比對需要最少 7 天觀察
    Given Morphenix 迭代完成僅 3 天
    When 使用者查詢 /eval compare
    Then 系統回報「觀察期不足：需至少 7 天數據」
    And 顯示目前已收集 3 天的初步趨勢（標記為「參考值」）
    And 不做正式的效果判定

  # ════════════════════════════════════════════
  # Section 5: 盲點雷達 — 系統性弱項偵測
  # ════════════════════════════════════════════

  Scenario: 盲點掃描 — 識別持續低分領域
    Given 品質資料庫累積 30 天以上的資料
    When 使用者查詢 /eval blindspot
    Then 系統分析各領域的平均 Q-Score
    And 識別出低於全域平均 0.15 以上的領域
    And 識別出特定維度持續低分的模式（如「深度」在投資領域持續 < 0.5）
    And 盲點被分類為：
      | 盲點類型         | 說明                                    |
      | 領域盲點         | 某領域整體品質偏低                      |
      | 維度盲點         | 某維度跨領域持續低分                    |
      | 技能盲點         | 某技能被觸發但未被採用（命中率低）      |
      | 情境盲點         | 特定情境類型（如急迫決策）品質下降      |

  Scenario: 盲點報告驅動 Morphenix 優先級
    Given 盲點雷達識別出「深度維度在技術領域持續低於 0.45」
    When 盲點報告生成
    Then 報告同時推送到 Morphenix 的觀察日誌
    And Morphenix 將此盲點列為下一次迭代的候選改善方向
    And 盲點不是失敗——它是演化方向的指引

  # ════════════════════════════════════════════
  # Section 6: Skill 使用率熱力圖
  # ════════════════════════════════════════════

  Scenario: Skill 觸發事件記錄
    When SkillRouter.match() 匹配到一個或多個技能
    Then 每次匹配事件被記錄到 data/eval/skill_events.json
    And 事件包含：時間戳、匹配的技能名稱、觸發詞、是否被實際採用、對話 ID

  Scenario: Skill 使用率統計
    Given 過去 30 天的 Skill 觸發事件已累積
    When 使用者查詢 /eval usage
    Then 系統顯示 Skill 使用率熱力圖：
    And 每個 Skill 的統計包含：
      | 欄位         | 說明                              |
      | 觸發次數     | SkillRouter 路由到該 Skill 的次數 |
      | 採用次數     | 實際在回答中使用該 Skill 的次數   |
      | 採用率       | 採用 / 觸發（低於 50% 則警告）    |
      | 使用深度     | 平均對話輪次                      |
      | 共現頻率     | 與其他 Skill 同時觸發的比例       |
    And 未使用超過 30 天的 Skill 被標記為「閒置」

  Scenario: Skill 低採用率警告
    Given business-12 被觸發 20 次但僅被採用 8 次（採用率 40%）
    When 熱力圖統計完成
    Then 系統標記 business-12 為「可能誤觸率高」
    And 建議檢查觸發詞是否太寬泛
    And 警告推送到 Morphenix 作為 Skill 優化候選

  Scenario: Skill 共現數據回饋 Orchestrator
    Given business-12 與 xmodel 的共現率為 78%
    When 共現數據被計算
    Then 數據同步到 Orchestrator 的路由優化資料
    And Orchestrator 可據此調整 Skill 組合推薦

  # ════════════════════════════════════════════
  # Section 7: 客戶成效追蹤器 — KPI 前後測
  # ════════════════════════════════════════════

  Scenario: 建立客戶 KPI 基線
    When 使用者執行 /eval client baseline
    Then 系統提示輸入 3~8 個基線 KPI 值
    And KPI 類型涵蓋：營收、行銷、品牌、營運、人資、財務
    And 基線值一旦建立不可回溯修改（防止偏差）
    And 基線存入 data/eval/client_baselines.json

  Scenario: 客戶 KPI 前後測比對
    Given 客戶 KPI 基線已建立 30 天以上
    When 使用者執行 /eval client compare
    Then 系統提示輸入當前 KPI 值
    And 生成前後測比對報告：
    And 報告包含：舊值、新值、百分比變化、定性歸因敘述
    And 所有報告必須包含免責聲明：「前後測相關不是因果關係」
    And 報告存入 data/eval/client_reports/

  # ════════════════════════════════════════════
  # Section 8: 背景運行與心跳整合
  # ════════════════════════════════════════════

  Scenario: 每次回答後靜默記錄品質信號
    When Brain.process() 完成一次回答
    Then Eval-Engine 靜默記錄：
    And deep-think Phase 2 審計結果 → Q-Score
    And 使用者行為信號 → Satisfaction Proxy
    And Skill 觸發事件 → Hit Rate
    And 對話 metadata（token 數、回應時間）→ 效率指標
    And 記錄過程不干擾使用者體驗

  Scenario: Nightly Job 生成每日品質摘要
    When Nightly Job 00:00 執行
    Then Eval-Engine 生成當日品質摘要：
    And 摘要包含：平均 Q-Score、Satisfaction Proxy、最佳/最差回答、Skill 使用分布
    And 摘要寫入 data/eval/daily/{date}.json
    And 若品質低於週平均則觸發 Morphenix 關注信號

  Scenario: 週度品質報告自動生成
    When 每週日 Nightly Job 觸發週報模式
    Then Eval-Engine 彙總過去 7 天的品質數據
    And 生成週度品質報告，包含趨勢圖、盲點更新、Skill 使用變化
    And 報告存入 data/eval/weekly/{week}.json
    And 報告可供使用者查閱

  # ════════════════════════════════════════════
  # Section 9: 硬閘與安全護欄
  # ════════════════════════════════════════════

  Scenario: HG-EVAL-HONEST — 數據誠實不美化
    When Eval-Engine 生成任何報告
    Then 不美化數據（退化就說退化）
    And 不過度歸因（相關不是因果）
    And 樣本數 < 10 時標記為「僅供參考」
    And 品質數據不包含對話內容（只有分數和 metadata）

  Scenario: HG-EVAL-BASELINE-LOCK — 基線鎖定不可回溯修改
    Given 一個 A/B 比對基線已建立
    When 任何程序嘗試修改已建立的基線
    Then 系統拒絕操作
    And 回報：「基線一旦建立不可修改，這是數據誠實的基礎」
    And 確保 A/B 比對的公正性

  Scenario: SG-EVAL-PRIVACY — 品質數據不含對話原文
    When Q-Score 和行為信號被記錄
    Then 品質資料庫只存儲：分數、維度值、行為類型、時間戳、對話 ID
    And 不存儲對話原文或使用者輸入
    And 品質數據可被安全分享而不洩漏隱私
