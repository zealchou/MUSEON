Feature: 自解壓安裝包 — Self-Extracting Installer Packaging
  將 MUSEON 專案打包為單一 .command 自解壓安裝檔
  雙擊即可在客戶 Mac 上完成完整安裝

  Background:
    Given 專案根目錄已確定
    And 打包器已初始化

  # ═══════════════════════════════════════
  # Section 1：來源檔案收集
  # ═══════════════════════════════════════

  Scenario: 收集來源檔案 — 包含必要目錄
    When 收集專案來源檔案
    Then 應該包含以下目錄
      | 目錄           | 說明                    |
      | src/           | Python 原始碼           |
      | electron/src/  | Dashboard 前端          |
      | features/      | BDD 特性檔案            |
      | data/          | 資料目錄結構            |
    And 應該包含以下檔案
      | 檔案                       | 說明              |
      | pyproject.toml             | Python 依賴宣告   |
      | electron/package.json      | Node.js 依賴宣告  |
      | Install-MUSEON.command   | 專案內安裝腳本    |

  Scenario: 排除不需要的檔案
    When 收集專案來源檔案
    Then 不應該包含以下路徑
      | 排除路徑              | 原因               |
      | .venv/                | 虛擬環境（會重建）  |
      | .git/                 | 版本控制歷史        |
      | node_modules/         | npm 依賴（會重裝）  |
      | __pycache__/          | Python 快取         |
      | htmlcov/              | 覆蓋率報告          |
      | .coverage             | 覆蓋率資料          |
      | .pytest_cache/        | pytest 快取         |
      | .DS_Store             | macOS 檔案          |
      | electron/dist/        | 打包產出            |

  # ═══════════════════════════════════════
  # Section 2：tar.gz 建立
  # ═══════════════════════════════════════

  Scenario: 建立壓縮封存檔 — 成功
    Given 來源檔案已收集
    When 建立 tar.gz 壓縮檔
    Then tar.gz 檔案應該存在
    And 檔案大小應該大於 0
    And 檔案大小應該小於 5 MB

  Scenario: tar.gz 內容結構正確
    Given tar.gz 已建立
    When 列出 tar.gz 內容
    Then 應該包含 src/museon/__init__.py
    And 應該包含 pyproject.toml
    And 不應該包含 .venv 路徑
    And 不應該包含 node_modules 路徑

  # ═══════════════════════════════════════
  # Section 3：Base64 編碼
  # ═══════════════════════════════════════

  Scenario: Base64 編碼 — 往返測試
    Given tar.gz 已建立
    When 執行 Base64 編碼
    Then Base64 輸出應該非空
    And Base64 解碼後應該與原始 tar.gz 相同

  # ═══════════════════════════════════════
  # Section 4：自解壓標頭
  # ═══════════════════════════════════════

  Scenario: 自解壓標頭 — 結構正確
    When 生成自解壓標頭
    Then 第一行應該是 #!/bin/bash
    And 應該包含 __PAYLOAD_BELOW__ 標記
    And 應該包含 base64 解碼指令
    And 應該包含 tar 解壓指令

  Scenario: 自解壓標頭 — 安裝流程完整
    When 生成自解壓標頭
    Then 應該提供安裝位置選擇（osascript 圖形化 + 文字回退）
    And 應該建立安裝目錄和 .runtime 子目錄
    And 應該搜尋 Python >= 3.11
    And 應該在 .runtime 內建立虛擬環境
    And 應該在 .runtime 內執行 pip install
    And 應該設定 MUSEON_HOME 為安裝根目錄
    And 應該啟動 BDD 安裝流程（python -m museon.installer）
    And 安裝完成後應該用 Finder 打開安裝目錄

  # ═══════════════════════════════════════
  # Section 5：組裝與驗證
  # ═══════════════════════════════════════

  Scenario: 組裝 .command 檔案 — 成功
    Given 自解壓標頭已生成
    And Base64 載荷已準備
    When 組裝最終 .command 檔案
    Then .command 檔案應該存在
    And 檔案應該有執行權限
    And 檔案大小應該小於 10 MB

  Scenario: 載荷提取往返測試
    Given .command 檔案已組裝
    When 從 .command 提取載荷
    And 解碼並解壓到臨時目錄
    Then 臨時目錄應該包含 src/museon/__init__.py
    And 臨時目錄應該包含 pyproject.toml
    And 檔案內容應該與原始來源完全相同

  Scenario: 更新安裝 — 保留使用者資料
    Given 目標目錄已有舊版安裝
    And .env 檔案包含 API Keys
    And data/ 目錄包含使用者資料
    When 備份使用者資料
    And 解壓新版本到 .runtime 子目錄
    And 還原使用者資料
    Then .env 檔案應該被保留（位於安裝根目錄）
    And data/ 目錄內容應該被保留（位於安裝根目錄）
    And .runtime/src/ 應該被更新為新版本

  # ═══════════════════════════════════════
  # Section 6：安裝目錄結構
  # ═══════════════════════════════════════

  Scenario: 安裝後目錄結構 — 使用者只看到需要的
    Given 安裝已完成
    Then 安裝根目錄應該包含以下使用者檔案
      | 項目      | 說明                |
      | .env      | API keys & 設定     |
      | data/     | 使用者資料          |
      | logs/     | 系統日誌            |
    And 開發者檔案應該在隱藏的 .runtime/ 目錄中
      | 項目                  | 說明                    |
      | .runtime/src/         | Python 原始碼           |
      | .runtime/.venv/       | Python 虛擬環境         |
      | .runtime/pyproject.toml | Python 依賴宣告       |

  Scenario: 安裝位置選擇 — osascript 圖形化 + 文字回退
    Given 使用者雙擊安裝檔
    When 安裝程式啟動
    Then 應該先嘗試 osascript 彈出 Finder 資料夾選擇
    And 如果使用者取消或 osascript 不可用則 fallback 到文字提問
    And 預設位置應該是 ~/MUSEON
