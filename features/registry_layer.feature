Feature: Registry Layer — 結構化資料層（記帳 / 會議追蹤 / 行程提醒 / 聯絡人）
  作為 MUSEON
  我需要一個結構化資料層
  能記帳查帳、追蹤會議待辦、管理行程提醒、維護聯絡人
  以 SQLite 為結構化真相來源，Qdrant documents collection 為語義索引輔助
  讓使用者用自然語言操作，系統自動路由到精確查詢或語義搜尋

  Background:
    Given MUSEON 已完成命名儀式
    And Brain 已初始化
    And RegistryManager 已為當前 user_id 初始化
    And registry.db 已建立且 migration 版本為最新
    And VectorBridge documents collection 已就緒

  # ══════════════════════════════════════════════════════════
  # Section 1: 初始化與 Migration
  # ══════════════════════════════════════════════════════════

  Scenario: 首次啟動時自動建立 registry.db 與目錄結構
    Given 使用者 user_id 為 "cli_user"
    And data/registry/cli_user/ 目錄不存在
    When RegistryManager 初始化
    Then data/registry/cli_user/registry.db 已建立
    And registry.db 包含 7 張表
    And data/vault/cli_user/meetings/ 目錄已建立
    And data/vault/cli_user/receipts/ 目錄已建立
    And data/vault/cli_user/imports/ 目錄已建立
    And data/inbox/ 目錄已建立

  Scenario: 預設分類體系自動灌入
    Given registry.db 剛建立
    When 檢查 _categories 表
    Then 包含至少 20 個系統預設分類
    And 分類涵蓋收入、支出、轉帳三大類
    And 支出下包含餐飲、交通、住宿等子分類

  Scenario: Migration 版本控制確保冪等
    Given registry.db 已存在且 _migrations 版本為 1
    When RegistryManager 再次初始化
    Then 不重複執行已套用的 migration
    And _migrations 版本仍為 1

  Scenario: VectorBridge 新增 documents collection
    Given VectorBridge 已初始化
    When ensure_collections 執行
    Then documents collection 已建立
    And doc_type payload index 已建立
    And user_id payload index 已建立
    And created_at payload index 已建立
    And tags payload index 已建立

  # ══════════════════════════════════════════════════════════
  # Section 2: 記帳功能
  # ══════════════════════════════════════════════════════════

  Scenario: 自然語言記帳 — 支出
    Given 使用者說「午餐花了 180 元吃拉麵」
    When LLM 萃取結構化交易資料
    Then transactions 表新增一筆記錄
    And amount 為 -180
    And currency 為 "TWD"
    And category 為 "expense.food.dining_out"
    And counterparty 包含「拉麵」
    And Qdrant documents 同步索引

  Scenario: 自然語言記帳 — 收入
    Given 使用者說「今天收到專案尾款 50000 元」
    When LLM 萃取結構化交易資料
    Then transactions 表新增一筆記錄
    And amount 為 50000
    And category 為 "income.freelance"

  Scenario: 精確查帳 — 走 SQLite
    Given 已有 30 筆交易記錄
    When 使用者問「上個月餐飲花了多少」
    Then 系統判斷為精確查詢
    And 執行 SQL 加總查詢
    And 回傳加總金額

  Scenario: 模糊查帳 — 走 Qdrant
    Given 已有 30 筆交易記錄
    When 使用者問「之前跟符大哥吃飯那次在哪裡」
    Then 系統判斷為語義查詢
    And 搜尋 Qdrant documents
    And 用 source_id 回 SQLite 拿完整記錄
    And 回傳匹配的交易詳情

  Scenario: 使用者新增自訂分類
    Given 使用者說「加一個寵物的分類」
    When LLM 萃取分類資訊
    Then _categories 表新增一筆記錄
    And parent_id 為 "expense"
    And name 為「寵物」

  # ══════════════════════════════════════════════════════════
  # Section 3: 會議記錄與追蹤
  # ══════════════════════════════════════════════════════════

  Scenario: 上傳會議逐字稿 — Telegram 檔案
    Given 使用者透過 Telegram 傳送一份 txt 逐字稿
    When TelegramAdapter 下載檔案至 data/uploads/telegram/
    And 系統偵測為會議紀錄格式
    Then 檔案複製到 vault/cli_user/meetings/
    And meetings 表新增一筆索引記錄
    And LLM 萃取摘要寫入 meetings.summary
    And LLM 萃取 Action Items 寫入 action_items 表
    And 逐字稿分塊後存入 Qdrant documents

  Scenario: Action Items 萃取
    Given 會議逐字稿中提到「符大哥下週三前把旅行社工作流 prototype 做完」
    When LLM 萃取 Action Items
    Then action_items 表新增一筆記錄
    And task 為「把旅行社工作流 prototype 做完」
    And assignee 為「符大哥」
    And due_date 為下週三的日期
    And status 為 "pending"
    And meeting_id 指向來源會議

  Scenario: 標記待辦完成
    Given 使用者說「符大哥的旅行社工作流已經做完了」
    When LLM 匹配到對應的 action_item
    Then action_items.status 更新為 "done"
    And completed_at 記錄當前時間

  Scenario: 查詢特定會議內容
    Given 已有 5 場會議紀錄
    When 使用者問「上次跟符大哥開會討論到 Skill Hub 那段」
    Then 系統搜尋 Qdrant documents
    And 召回相關的 chunk
    And 回傳該段會議內容摘要

  # ══════════════════════════════════════════════════════════
  # Section 4: 行程提醒
  # ══════════════════════════════════════════════════════════

  Scenario: 新增行程 — 預設時區
    Given 使用者說「下週三下午兩點跟王總開會」
    And 使用者預設時區為 Asia/Taipei
    When LLM 萃取行程資料
    Then events 表新增一筆記錄
    And datetime_start 儲存為 UTC
    And timezone 為 "Asia/Taipei"
    And title 為「跟王總開會」
    And status 為 "upcoming"

  Scenario: 新增行程 — 跨時區確認
    Given 使用者說「下週一東京時間下午三點跟日本客戶視訊」
    When LLM 偵測到地名「東京」
    Then 系統推斷時區為 Asia/Tokyo
    And 向使用者確認時間轉換
    And 使用者確認後寫入 events 表
    And timezone 為 "Asia/Tokyo"

  Scenario: 行程提醒觸發
    Given events 有一筆 30 分鐘後開始的行程
    And reminder_minutes 為 30
    And reminder_sent 為 false
    When CronEngine 整點掃描行程
    Then 透過 Telegram 推送提醒
    And 提醒包含事件名稱、時間、地點
    And reminder_sent 更新為 true

  Scenario: 重複事件
    Given 使用者說「每週一早上九點團隊站會」
    When LLM 萃取行程資料
    Then events 表新增一筆記錄
    And recurrence 為 "RRULE:FREQ=WEEKLY;BYDAY=MO"

  Scenario: 取消行程
    Given 使用者說「取消明天跟王總的會議」
    When LLM 匹配到對應的 event
    Then events.status 更新為 "cancelled"

  # ══════════════════════════════════════════════════════════
  # Section 5: 聯絡人管理
  # ══════════════════════════════════════════════════════════

  Scenario: 新增聯絡人
    Given 使用者說「記一下，符大哥的手機是 0912345678，生日是 5 月 15 號」
    When LLM 萃取聯絡人資料
    Then contacts 表新增一筆記錄
    And name 為「符大哥」
    And phone 為 "0912345678"
    And birthday 為 "05-15"
    And Qdrant documents 同步索引

  Scenario: 查詢聯絡人
    Given 使用者問「符大哥的電話幾號」
    When 系統搜尋 contacts 表
    Then 回傳聯絡人詳細資訊

  # ══════════════════════════════════════════════════════════
  # Section 6: 語義搜尋 — 跨類型與混合路由
  # ══════════════════════════════════════════════════════════

  Scenario: 跨類型語義搜尋
    Given 使用者問「之前跟符大哥相關的所有事情」
    When 系統搜尋 Qdrant documents 不指定 doc_type
    Then 回傳跨類型結果
    And 結果按相關性分數排序
    And 標註每筆結果的來源類型

  Scenario: 混合查詢路由
    Given 使用者問「三月份跟日本相關的花費和會議」
    When LLM 判斷需要混合查詢
    Then 精確部分走 SQLite
    And 語義部分走 Qdrant
    And 合併結果回傳

  # ══════════════════════════════════════════════════════════
  # Section 7: 大檔案處理
  # ══════════════════════════════════════════════════════════

  Scenario: Telegram 大檔案智慧提示
    Given 使用者嘗試透過 Telegram 傳送超過 50MB 的會議錄音
    When Telegram Bot API 拒絕上傳
    Then 系統偵測到上傳失敗
    And 回覆使用者提供 inbox 資料夾路徑與 Web Upload 連結

  Scenario: inbox 資料夾自動偵測
    Given 使用者將 meeting_recording.m4a 放入 data/inbox/
    When 檔案監控偵測到新檔案
    Then 檔案移至 vault/cli_user/meetings/
    And 觸發 Whisper 轉錄 Pipeline
    And 轉錄完成後走會議記錄處理流程

  # ══════════════════════════════════════════════════════════
  # Section 8: Graceful Degradation
  # ══════════════════════════════════════════════════════════

  Scenario: Qdrant 不可用時降級 — 寫入
    Given Qdrant 服務未啟動
    When 使用者記一筆帳
    Then SQLite 正常寫入
    And Qdrant 索引靜默失敗
    And 系統記錄 pending 索引任務

  Scenario: Qdrant 不可用時降級 — 查詢
    Given Qdrant 服務未啟動
    When 使用者進行語義查詢
    Then 系統降級為 SQLite LIKE 搜尋
    And 回傳結果標註語義搜尋暫時不可用

  Scenario: SQLite 損毀時的保護
    Given registry.db 檔案損毀
    When RegistryManager 嘗試存取
    Then 系統偵測到 integrity 問題
    And 嘗試從最近備份恢復
    And 若無備份則建立新 DB 並通知使用者
