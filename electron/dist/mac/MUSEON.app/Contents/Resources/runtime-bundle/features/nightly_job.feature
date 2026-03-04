Feature: Nightly Job - 自鍛造與記憶融合
  MuseClaw 每天 3AM 執行 nightly job，進行記憶融合、Token 優化、自鍛造檢查

  Background:
    Given MuseClaw 已經運行了 7 天
    And 有每日對話記錄和記憶數據
    And 當前時間是 3:00 AM

  Scenario: 記憶融合 - 跨四通道整合
    Given 昨日有以下記憶數據
      | channel        | count |
      | meta_thinking  | 5     |
      | event          | 10    |
      | outcome        | 8     |
      | user_reaction  | 12    |
    When nightly job 執行記憶融合
    Then 應該生成融合後的洞見
    And 融合洞見應該包含所有四個通道的資訊
    And 融合結果應該寫入 MEMORY.md

  Scenario: 記憶融合 - 無數據時跳過
    Given 昨日沒有任何對話記錄
    When nightly job 執行記憶融合
    Then 應該跳過融合任務
    And 記錄 "no_data" 狀態

  Scenario: Token 自主優化 - 觀察路由模式
    Given 過去 7 天的路由統計
      | model  | count | avg_quality | success_rate |
      | haiku  | 150   | 85          | 0.95         |
      | sonnet | 50    | 88          | 0.92         |
    When nightly job 分析 Token 使用模式
    Then 應該產出路由模式報告
    And 報告應該包含各模型的成功率和品質

  Scenario: Token 優化 - 建議降級
    Given 某些 sonnet 任務的品質與 haiku 相近
      | task_type     | sonnet_quality | haiku_quality | tokens_saved |
      | simple_query  | 85             | 86            | 220          |
      | greeting      | 88             | 87            | 150          |
    When nightly job 分析降級機會
    Then 應該建議將 "simple_query" 降級到 haiku
    And 預估可節省 220 tokens per task

  Scenario: Token 優化 - 驗證品質後回滾
    Given 系統嘗試將 "creative" 任務降級到 haiku
    When 驗證降級後品質下降超過 5 分
    Then 應該自動回滾到 sonnet
    And 記錄回滾原因為 "quality_drop"

  Scenario: 自鍛造 - 品質驅動觸發（Q-Score < 70 連續 5 次）
    Given brand-identity skill 的品質歷史
      | date       | q_score |
      | 2026-02-20 | 75      |
      | 2026-02-21 | 72      |
      | 2026-02-22 | 68      |
      | 2026-02-23 | 65      |
      | 2026-02-24 | 64      |
    When nightly job 檢查自鍛造觸發條件
    Then 應該觸發 "brand-identity" 的品質驅動自鍛造
    And 自鍛造類型應該是 "quality_decline"
    And 應該標記為「待改良」

  Scenario: 自鍛造 - 使用驅動觸發（重複任務 10+ 次無專屬 Skill）
    Given 過去 7 天有以下重複任務
      | task_type           | count | has_dedicated_skill |
      | nail_salon_promo    | 12    | false               |
      | general_social_post | 20    | true                |
    When nightly job 檢查自鍛造觸發條件
    Then 應該觸發 "nail_salon_promo" 的使用驅動自鍛造
    And 自鍛造類型應該是 "repeated_manual"
    And 應該建議鍛造新的專屬 Skill

  Scenario: 自鍛造 - 時間驅動觸發（記憶衰退掃描）
    Given 有以下 Skill 的使用記錄
      | skill_name   | last_used  | days_since |
      | old-skill    | 2026-01-01 | 54         |
      | active-skill | 2026-02-24 | 1          |
    When nightly job 執行時間驅動掃描
    Then 應該標記 "old-skill" 為過時
    And 建議動作應該是 "archive_or_update"

  Scenario: Batch API 整合 - 50% 成本節省
    Given nightly job 需要處理 5 天的記憶融合
    When 使用 Batch API 執行任務
    Then 應該將所有任務合併為單一 batch
    And batch 成本應該是標準成本的 50%
    And 應該在 24 小時內完成

  Scenario: Nightly Job 完整流程
    Given MuseClaw 運行正常
    When 到達 3:00 AM 觸發 nightly job
    Then 應該依序執行以下任務
      | task              | status    |
      | memory_fusion     | completed |
      | token_optimization| completed |
      | forge_check       | completed |
      | health_report     | completed |
    And 應該產出每日安全健康報告
    And 健康報告應該包含 token 使用、記憶狀態、安全摘要

  Scenario: Nightly Job 錯誤處理
    Given 記憶融合任務發生錯誤
    When nightly job 執行
    Then 應該繼續執行其他任務
    And 最終狀態應該是 "partial_success"
    And 應該記錄錯誤詳情

  Scenario: 知識再結晶
    Given 過去 7 天有新的可結晶洞見
      | insight                          | date       |
      | 老闆喜歡簡潔有力的文案            | 2026-02-20 |
      | IG 貼文在晚上 8-9 點效果最好      | 2026-02-22 |
    When nightly job 執行知識結晶
    Then 應該產出新的結晶知識
    And 知識應該寫入 knowledge-lattice
    And 應該建立結晶之間的連結

  Scenario: Skill 健康度審計
    Given 所有 Skill 的使用統計
      | skill_name      | usage_count | success_rate | token_efficiency |
      | text-alchemy    | 50          | 0.95         | high             |
      | unused-skill    | 0           | 0.0          | n/a              |
      | low-success     | 20          | 0.60         | low              |
    When nightly job 執行 Skill 健康度審計
    Then 應該建議歸檔 "unused-skill"
    And 應該標記 "low-success" 為需改良
    And "text-alchemy" 應該保持現狀
