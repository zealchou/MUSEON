Feature: 一鍵安裝 — MUSEON Installation
  MUSEON 一鍵安裝程式，從環境檢查到 Day 0 就緒
  雙擊 Install-MUSEON.command 即可啟動完整安裝流程

  Background:
    Given 安裝程式在 macOS 上執行
    And 專案根目錄已確定

  # ═══════════════════════════════════════
  # Section 1：環境檢查
  # ═══════════════════════════════════════

  Scenario: macOS 環境確認
    When 檢查作業系統
    Then 應該確認為 macOS
    And 應該偵測處理器架構
      | 架構    | 說明            |
      | arm64   | Apple Silicon  |
      | x86_64  | Intel Mac      |

  Scenario: Python 3.11+ 偵測 — 已安裝
    Given 系統已安裝 Python 3.13
    When 搜尋可用的 Python 版本
    Then 應該找到 Python 路徑
    And 版本應該 >= 3.11

  Scenario: Python 版本不足 — 引導安裝
    Given 系統只有 Python 3.9
    When 搜尋可用的 Python 版本
    Then 應該回傳找不到合適版本
    And 應該建議執行 brew install python@3.13

  Scenario: Node.js 偵測 — 已安裝
    Given 系統已安裝 Node.js 20
    When 搜尋 Node.js
    Then 應該找到 Node.js 路徑
    And npm 應該可用

  Scenario: Node.js 缺失 — 可降級繼續
    Given 系統沒有安裝 Node.js
    When 搜尋 Node.js
    Then 應該回傳 Node.js 不可用
    And 安裝流程應該可以繼續（Gateway 不需要 Node.js）

  Scenario: 磁碟空間檢查 — 足夠
    Given 磁碟可用空間為 50000 MB
    When 檢查磁碟空間（最低需求 500 MB）
    Then 應該回傳空間足夠

  Scenario: 磁碟空間不足 — 警告
    Given 磁碟可用空間為 200 MB
    When 檢查磁碟空間（最低需求 500 MB）
    Then 應該回傳警告（非致命錯誤）
    And 警告訊息應該包含可用空間和最低需求

  # ═══════════════════════════════════════
  # Section 2：Python 環境建置
  # ═══════════════════════════════════════

  Scenario: 虛擬環境建立 — 全新安裝
    Given 專案目錄下沒有 .venv
    When 建立 Python 虛擬環境
    Then .venv 目錄應該被建立
    And .venv/bin/python 應該可執行

  Scenario: 虛擬環境已存在 — 重用
    Given 專案目錄下已有 .venv
    When 檢查虛擬環境
    Then 應該重用現有的 .venv
    And 不應該重新建立

  Scenario: pip install 依賴安裝 — 成功
    Given 虛擬環境已就緒
    When 執行 pip install -e ".[dev]"
    Then 安裝應該成功
    And museon 套件應該可以被 import

  Scenario: pip install 失敗 — 網路問題
    Given 虛擬環境已就緒
    And 網路連線不可用
    When 執行 pip install -e ".[dev]"
    Then 應該回傳安裝失敗
    And 錯誤訊息應該建議檢查網路連線

  # ═══════════════════════════════════════
  # Section 3：模組驗證
  # ═══════════════════════════════════════

  Scenario: 四大核心模組驗證 — 全部通過
    Given 依賴已安裝完成
    When 驗證核心模組
    Then 以下模組應該全部可以載入
      | 模組名稱         | import 路徑                              | 類別名稱         |
      | Gateway         | museon.gateway.server                  | create_app      |
      | LLM Router      | museon.llm.router                      | Router          |
      | Memory Engine   | museon.memory.channels                 | ChannelManager  |
      | Security        | museon.security.sanitizer              | InputSanitizer  |

  Scenario: 部分模組驗證失敗 — 不中斷安裝
    Given 依賴已安裝完成
    And Memory Engine 模組載入失敗
    When 驗證核心模組
    Then 應該回報哪些模組失敗
    And 安裝流程應該繼續（回傳 WARNING 而非 FAILED）

  # ═══════════════════════════════════════
  # Section 4：Electron Dashboard 打包
  # ═══════════════════════════════════════

  Scenario: Electron Dashboard 打包 — 成功
    Given Node.js 和 npm 可用
    And electron/ 目錄存在
    When 執行 Electron 打包流程
    Then npm install 應該成功
    And electron-builder 應該產出 .app bundle
    And .app 應該在 dist/mac-arm64/ 或 dist/mac/ 目錄

  Scenario: Electron 打包失敗 — 降級繼續
    Given npm 執行失敗
    When 執行 Electron 打包流程
    Then 應該回傳打包失敗（WARNING 而非 FAILED）
    And Gateway 安裝應該不受影響

  Scenario: Dashboard 安裝到 /Applications — 成功
    Given .app bundle 已打包完成
    When 安裝 Dashboard 到 /Applications
    Then /Applications/MUSEON Dashboard.app 應該存在
    And quarantine 屬性應該已移除
    And 權限應該設定為 755

  Scenario: 已有安裝 — 詢問覆蓋
    Given /Applications/MUSEON Dashboard.app 已存在
    When 檢查是否已有安裝
    Then 應該回傳「已有安裝」
    And 應該提供覆蓋選項

  # ═══════════════════════════════════════
  # Section 5：Gateway 24/7 Daemon
  # ═══════════════════════════════════════

  Scenario: launchd plist 生成 — 結構正確
    Given 安裝設定已確定
    When 生成 launchd plist
    Then plist 應該包含以下欄位
      | 欄位                | 預期值                           |
      | Label               | com.museon.gateway              |
      | RunAtLoad           | true                              |
      | KeepAlive           | SuccessfulExit = false            |
      | ThrottleInterval    | 5                                 |
      | ProcessType         | Background                        |
    And ProgramArguments 應該指向 .venv/bin/python -m museon.gateway.server
    And WorkingDirectory 應該指向專案根目錄
    And EnvironmentVariables 應該包含 PYTHONPATH 和 MUSEON_HOME

  Scenario: launchd plist 路徑正確
    When 生成 plist 檔案路徑
    Then 應該位於 ~/Library/LaunchAgents/com.museon.gateway.plist

  Scenario: 停止舊 daemon — 已有運行中
    Given com.museon.gateway 已在 launchctl 中載入
    When 停止舊的 daemon
    Then 應該執行 launchctl unload
    And 不應該產生錯誤

  Scenario: Gateway daemon 啟動 — 成功
    Given plist 已寫入正確路徑
    When 啟動 Gateway daemon
    Then launchctl load 應該成功
    And Gateway 應該在 localhost:8765 回應健康檢查

  Scenario: Gateway 啟動失敗 — 顯示日誌路徑
    Given plist 已寫入正確路徑
    And Gateway 啟動失敗
    When 檢查 daemon 狀態
    Then 應該回傳啟動失敗
    And 應該提供日誌檔案路徑
      | 日誌類型    | 路徑                      |
      | stdout     | logs/gateway.log          |
      | stderr     | logs/gateway.err          |

  # ═══════════════════════════════════════
  # Section 6：API Key 設定
  # ═══════════════════════════════════════

  Scenario: Telegram Bot Token 設定
    Given 使用者輸入 Token "123456:ABC-DEF"
    When 儲存 Telegram Bot Token
    Then .env 檔案應該包含 TELEGRAM_BOT_TOKEN=123456:ABC-DEF

  Scenario: Anthropic API Key 設定
    Given 使用者輸入 API Key "sk-ant-xxx"
    When 儲存 Anthropic API Key
    Then .env 檔案應該包含 ANTHROPIC_API_KEY=sk-ant-xxx

  Scenario: API Key 跳過 — 稍後設定
    Given 使用者選擇跳過 API Key 設定
    When 處理跳過的 API Key
    Then .env 檔案應該被建立（空的或有註解）
    And 安裝流程應該繼續

  Scenario: .env 檔案已存在 — 保留設定
    Given .env 檔案已包含 TELEGRAM_BOT_TOKEN
    When 檢查現有的 API Key 設定
    Then 不應該覆蓋現有的 Token
    And 應該回報已設定

  # ═══════════════════════════════════════
  # Section 7：啟動與 Day 0 就緒
  # ═══════════════════════════════════════

  Scenario: 完整安裝流程 — 全部成功
    Given 所有前置條件都已滿足
    When 執行完整安裝流程
    Then 最終報告應該顯示
      | 元件              | 狀態        |
      | Gateway daemon   | running     |
      | Dashboard        | installed   |
      | Telegram Bot     | configured  |
      | Anthropic API    | configured  |
    And 所有步驟的結果都應該是 SUCCESS

  Scenario: 部分安裝 — 降級完成
    Given Node.js 不可用
    And 使用者跳過 API Key 設定
    When 執行完整安裝流程
    Then 最終報告應該顯示
      | 元件              | 狀態        |
      | Gateway daemon   | running     |
      | Dashboard        | skipped     |
      | Telegram Bot     | pending     |
      | Anthropic API    | pending     |
    And Gateway 應該仍然在 24/7 運行

  Scenario: Day 0 就緒確認
    Given 安裝流程已完成
    And Gateway daemon 正在運行
    When 確認 Day 0 就緒狀態
    Then Gateway health endpoint 應該回應正常
    And 命名儀式應該準備好（等待老闆的第一句話）
    And 系統應該輸出下一步指引：「打開 Telegram，跟你的 MUSEON Bot 說第一句話」
