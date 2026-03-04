Feature: Dashboard 開機精靈 — Setup Wizard
  Dashboard 首次開啟時，引導使用者完成 API Key 設定
  設定完成後自動進入正常 Dashboard 介面

  Background:
    Given 專案目錄已存在
    And .env 檔案路徑已確定

  # ═══════════════════════════════════════
  # Section 1：首次啟動偵測
  # ═══════════════════════════════════════

  Scenario: .env 不存在 — 應顯示精靈
    Given .env 檔案不存在
    When 檢查是否為首次啟動
    Then 應該回傳 true（需要設定）

  Scenario: .env 缺少必要 key — 應顯示精靈
    Given .env 檔案存在但缺少 ANTHROPIC_API_KEY
    When 檢查是否為首次啟動
    Then 應該回傳 true（需要設定）

  Scenario: .env 已有所有必要 key — 跳過精靈
    Given .env 檔案已包含 ANTHROPIC_API_KEY 和 TELEGRAM_BOT_TOKEN
    And .env 包含 MUSECLAW_SETUP_DONE=1
    When 檢查是否為首次啟動
    Then 應該回傳 false（不需要設定）

  # ═══════════════════════════════════════
  # Section 2：API Key 儲存
  # ═══════════════════════════════════════

  Scenario: 儲存 Anthropic API Key
    Given .env 檔案已建立（空的或有模板）
    When 儲存 API Key "ANTHROPIC_API_KEY" 值為 "sk-ant-api03-test123"
    Then .env 檔案應該包含 "ANTHROPIC_API_KEY=sk-ant-api03-test123"
    And 回傳結果為 SUCCESS

  Scenario: 儲存 Telegram Bot Token
    Given .env 檔案已建立
    When 儲存 API Key "TELEGRAM_BOT_TOKEN" 值為 "123456:ABCdefGHIjklMNO"
    Then .env 檔案應該包含 "TELEGRAM_BOT_TOKEN=123456:ABCdefGHIjklMNO"

  Scenario: 更新已存在的 key — 覆蓋而非重複
    Given .env 已有 "ANTHROPIC_API_KEY=old_value"
    When 儲存 API Key "ANTHROPIC_API_KEY" 值為 "new_value"
    Then .env 應該只有一個 ANTHROPIC_API_KEY
    And 值應該是 "new_value"

  # ═══════════════════════════════════════
  # Section 3：API Key 格式驗證
  # ═══════════════════════════════════════

  Scenario: Anthropic key 格式正確
    When 驗證 Anthropic key "sk-ant-api03-validkey123"
    Then 驗證應該通過

  Scenario: Anthropic key 格式錯誤
    When 驗證 Anthropic key "invalid-key"
    Then 驗證應該失敗
    And 應該提示 key 格式不正確

  Scenario: Telegram token 格式正確
    When 驗證 Telegram token "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
    Then 驗證應該通過

  Scenario: Telegram token 格式錯誤
    When 驗證 Telegram token "not-a-valid-token"
    Then 驗證應該失敗

  Scenario: 空值拒絕
    When 驗證 Anthropic key ""
    Then 驗證應該失敗
    And 應該提示不得為空

  # ═══════════════════════════════════════
  # Section 4：連線測試
  # ═══════════════════════════════════════

  Scenario: Anthropic API 連線成功
    Given Anthropic API 回應正常
    When 測試 Anthropic 連線
    Then 應該回傳連線成功

  Scenario: Telegram Bot 連線成功
    Given Telegram API 回應正常
    When 測試 Telegram 連線
    Then 應該回傳連線成功
    And 應該包含 Bot 名稱

  Scenario: 連線超時處理
    Given API 回應超時
    When 測試連線
    Then 應該回傳超時錯誤
    And 不應該當機

  # ═══════════════════════════════════════
  # Section 5：設定狀態管理
  # ═══════════════════════════════════════

  Scenario: 取得設定狀態 — 部分完成
    Given .env 已有 ANTHROPIC_API_KEY 但缺少 TELEGRAM_BOT_TOKEN
    When 取得設定狀態
    Then ANTHROPIC_API_KEY 狀態應為已設定
    And TELEGRAM_BOT_TOKEN 狀態應為未設定

  Scenario: 標記設定完成
    When 標記設定完成
    Then .env 應該包含 "MUSECLAW_SETUP_DONE=1"
