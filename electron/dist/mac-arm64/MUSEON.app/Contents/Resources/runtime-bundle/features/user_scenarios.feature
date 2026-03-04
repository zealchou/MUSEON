Feature: 使用者情境壓力測試 — 200+ Real-World Scenarios
  模擬各種不同個性、產業、需求的老闆在安裝 & 使用 MuseClaw 時
  會遇到的真實問題場景，確保系統對任何邊界情況都能優雅處理

  Background:
    Given 專案目錄已存在
    And 系統為 macOS

  # ═══════════════════════════════════════════════════════════════
  # Section 1：安裝環境偵測 (30 scenarios)
  # 模擬：科技業老闆（新 Mac）、設計師（舊 Intel Mac）、學生（Linux）
  # ═══════════════════════════════════════════════════════════════

  Scenario: ENV-01 非 macOS 系統（Linux 使用者）
    Given 使用者在 Linux 系統上安裝
    When 檢查作業系統
    Then 應回傳 FAILED 並提示僅支援 macOS

  Scenario: ENV-02 ARM64 架構偵測（M1/M2 Mac）
    When 在 Apple Silicon Mac 上偵測架構
    Then 應回傳 "arm64"

  Scenario: ENV-03 Intel 架構偵測（舊 Mac）
    When 在 Intel Mac 上偵測架構
    Then 應回傳 "x86_64"

  Scenario: ENV-04 找到 Python 3.13
    Given 系統有 python3.13
    When 搜尋 Python
    Then 應找到 python3.13 路徑

  Scenario: ENV-05 找到 Python 3.12（第二優先）
    Given 系統只有 python3.12
    When 搜尋 Python
    Then 應找到 python3.12 路徑

  Scenario: ENV-06 找到 Python 3.11（最低版本）
    Given 系統只有 python3.11
    When 搜尋 Python
    Then 應找到 python3.11 路徑

  Scenario: ENV-07 只有 Python 3.10 — 版本太低
    Given 系統只有 Python 3.10
    When 搜尋 Python
    Then 應回傳 None（找不到合適版本）

  Scenario: ENV-08 完全沒有 Python
    Given 系統沒有任何 Python
    When 搜尋 Python
    Then 應回傳 None

  Scenario: ENV-09 Python 路徑存在但執行失敗
    Given python3 指令存在但執行時拋出 OSError
    When 搜尋 Python
    Then 應跳過該候選繼續搜尋

  Scenario: ENV-10 Python 版本字串異常（"Python unknown"）
    Given python3 回傳 "Python unknown"
    When 解析版本字串
    Then 應回傳 None

  Scenario: ENV-11 Python 版本字串空白
    Given python3 回傳空字串
    When 解析版本字串
    Then 應回傳 None

  Scenario: ENV-12 Python 版本含有額外文字（"Python 3.13.1+"）
    Given 版本字串為 "Python 3.13.1+"
    When 解析版本
    Then 應正確解析為 (3, 13, 1)

  Scenario: ENV-13 Node.js 已安裝且有 npm
    Given 系統有 Node.js 和 npm
    When 搜尋 Node
    Then 應回傳路徑和 has_npm=True

  Scenario: ENV-14 Node.js 已安裝但沒有 npm
    Given 系統有 Node.js 但 npm 回傳錯誤
    When 搜尋 Node
    Then 應回傳路徑和 has_npm=False

  Scenario: ENV-15 完全沒有 Node.js
    Given 系統沒有 Node.js
    When 搜尋 Node
    Then 應回傳 None

  Scenario: ENV-16 Node 指令拋出 FileNotFoundError
    Given node 指令不存在拋出 FileNotFoundError
    When 搜尋 Node
    Then 應優雅處理回傳 None

  Scenario: ENV-17 磁碟空間充足（5000 MB）
    Given 磁碟剩餘 5000 MB
    When 檢查磁碟空間（最低 500 MB）
    Then 應回傳 SUCCESS

  Scenario: ENV-18 磁碟空間不足（300 MB）
    Given 磁碟剩餘 300 MB
    When 檢查磁碟空間（最低 500 MB）
    Then 應回傳 WARNING

  Scenario: ENV-19 磁碟空間檢查拋出 OSError
    Given 磁碟存取拋出 OSError
    When 檢查磁碟空間
    Then 應回傳 WARNING 而非 crash

  Scenario: ENV-20 collect_system_info 整合所有資訊
    When 收集系統資訊
    Then 應回傳包含 os_type, arch, python 等完整資訊

  Scenario: ENV-21 版本字串 "Python 3.11.0"（邊界版本）
    When 解析版本 "Python 3.11.0"
    Then 版本 (3, 11, 0) 應滿足最低需求

  Scenario: ENV-22 版本字串 "Python 3.10.99"（低於門檻）
    When 解析版本 "Python 3.10.99"
    Then 版本 (3, 10, 99) 不應滿足最低需求

  Scenario: ENV-23 版本字串只有主版本 "Python 3"
    When 解析版本 "Python 3"
    Then 應能處理不完整版本號

  Scenario: ENV-24 subprocess.run 超時
    Given python3 --version 執行超過 5 秒
    When 搜尋 Python
    Then 應跳過該候選繼續搜尋

  Scenario: ENV-25 多個 Python 版本共存
    Given 系統有 python3.13 和 python3.11
    When 搜尋 Python
    Then 應優先選擇 python3.13

  Scenario: ENV-26 macOS 檢查成功
    Given 系統為 Darwin
    When 檢查作業系統
    Then 應回傳 SUCCESS

  Scenario: ENV-27 Windows 系統嘗試安裝
    Given 系統為 Windows
    When 檢查作業系統
    Then 應回傳 FAILED

  Scenario: ENV-28 磁碟空間剛好等於最低需求
    Given 磁碟剩餘剛好 500 MB
    When 檢查磁碟空間（最低 500 MB）
    Then 應回傳 SUCCESS

  Scenario: ENV-29 Homebrew 偵測
    When 收集系統資訊
    Then 應偵測 Homebrew 是否可用

  Scenario: ENV-30 node --version 回傳非零退出碼
    Given node --version 回傳 exit code 1
    When 搜尋 Node
    Then 應視為 Node 不可用

  # ═══════════════════════════════════════════════════════════════
  # Section 2：Python 環境設定 (20 scenarios)
  # 模擬：餐飲業老闆（不懂 terminal）、工程師（有自己的 venv）
  # ═══════════════════════════════════════════════════════════════

  Scenario: PYENV-01 .venv 不存在
    Given .venv 目錄不存在
    When 檢查 venv 是否存在
    Then 應回傳 False

  Scenario: PYENV-02 .venv 存在且 bin/python 在
    Given .venv/bin/python 存在
    When 檢查 venv 是否存在
    Then 應回傳 True

  Scenario: PYENV-03 .venv 目錄存在但 bin/python 缺失
    Given .venv 目錄存在但沒有 bin/python
    When 檢查 venv 是否存在
    Then 應回傳 False

  Scenario: PYENV-04 建立 venv 成功
    When 以 python3 建立 venv
    Then 應回傳 SUCCESS

  Scenario: PYENV-05 建立 venv 失敗（returncode != 0）
    Given python3 -m venv 回傳非零退出碼
    When 建立 venv
    Then 應回傳 FAILED

  Scenario: PYENV-06 建立 venv 超時（120 秒）
    Given 建立 venv 花費超過 120 秒
    When 建立 venv
    Then 應回傳 FAILED 並提示超時

  Scenario: PYENV-07 建立 venv 拋出 OSError
    Given python3 路徑不存在
    When 建立 venv
    Then 應回傳 FAILED 並顯示錯誤訊息

  Scenario: PYENV-08 安裝依賴成功
    When 安裝 pip 依賴
    Then 應回傳 SUCCESS

  Scenario: PYENV-09 安裝依賴失敗（returncode != 0）
    Given pip install 回傳非零退出碼
    When 安裝依賴
    Then 應回傳 FAILED

  Scenario: PYENV-10 安裝依賴超時（600 秒）
    Given pip install 花費超過 600 秒
    When 安裝依賴
    Then 應回傳 FAILED 並提示超時

  Scenario: PYENV-11 安裝依賴拋出 OSError
    Given venv python 路徑無效
    When 安裝依賴
    Then 應回傳 FAILED

  Scenario: PYENV-12 安裝依賴 stderr 截斷
    Given pip install 產生超長 stderr
    When 安裝依賴失敗
    Then 錯誤訊息應截斷至最後 500 字

  Scenario: PYENV-13 venv 存在時跳過建立
    Given .venv 已存在且健康
    When 執行 Python 環境步驟
    Then 應跳過 venv 建立

  Scenario: PYENV-14 空白 python 路徑
    When 以空白路徑建立 venv
    Then 應回傳 FAILED

  Scenario: PYENV-15 venv 目錄路徑含空格
    Given 專案目錄含空格 "/Users/user/My Projects"
    When 建立 venv
    Then 應正確處理含空格路徑

  Scenario: PYENV-16 pip install 輸出正常截斷
    Given pip install 產生大量正常輸出
    When 安裝成功
    Then SUCCESS 訊息不應包含長輸出

  Scenario: PYENV-17 venv python 路徑正確性
    Given venv 建立成功
    Then venv_python 路徑應指向 .venv/bin/python

  Scenario: PYENV-18 create_venv 使用正確指令
    When 建立 venv
    Then 應使用 "-m venv" 指令

  Scenario: PYENV-19 install_dependencies 使用正確指令
    When 安裝依賴
    Then 應使用 "pip install -e .[dev]" 指令

  Scenario: PYENV-20 建立 venv 時 stderr 有內容但成功
    Given venv 建立 returncode=0 但 stderr 有警告
    When 建立 venv
    Then 應回傳 SUCCESS

  # ═══════════════════════════════════════════════════════════════
  # Section 3：模組驗證 (15 scenarios)
  # 模擬：安裝到一半中斷、套件損壞、版本衝突
  # ═══════════════════════════════════════════════════════════════

  Scenario: MOD-01 Gateway 模組載入成功
    When 驗證 "museclaw.gateway.server" 的 "create_app"
    Then 應回傳 SUCCESS

  Scenario: MOD-02 模組不存在（ImportError）
    When 驗證不存在的模組
    Then 應回傳 WARNING

  Scenario: MOD-03 模組存在但屬性缺失
    When 驗證模組存在但屬性不存在
    Then 應回傳 WARNING 並提示屬性缺失

  Scenario: MOD-04 模組載入拋出非 ImportError 異常
    When 模組載入時拋出 RuntimeError
    Then 應回傳 WARNING

  Scenario: MOD-05 所有 4 個核心模組都成功
    When 驗證所有核心模組
    Then 應全部回傳 SUCCESS

  Scenario: MOD-06 部分模組成功部分失敗
    When 驗證所有核心模組（部分失敗）
    Then 結果清單應包含混合狀態

  Scenario: MOD-07 verify_all 回傳正確數量
    When 驗證所有核心模組
    Then 應回傳 4 個結果

  Scenario: MOD-08 CORE_MODULES 列表完整性
    Then CORE_MODULES 應包含 Gateway, LLM Router, Memory Engine, Security

  Scenario: MOD-09 模組路徑格式正確
    Then 所有 CORE_MODULES 路徑應為點分格式

  Scenario: MOD-10 verify_module 空字串模組路徑
    When 驗證空字串模組路徑
    Then 應回傳 WARNING

  Scenario: MOD-11 verify_module 空字串屬性名
    When 驗證模組但屬性名為空
    Then 應回傳 WARNING

  Scenario: MOD-12 模組載入有副作用但不 crash
    When 模組載入時觸發副作用
    Then 不應導致整個驗證流程崩潰

  Scenario: MOD-13 verify_all 結果含 step_name
    When 驗證所有模組
    Then 每個結果的 step_name 應為模組顯示名稱

  Scenario: MOD-14 模組驗證不應修改系統狀態
    When 驗證模組
    Then 不應改變任何全域狀態

  Scenario: MOD-15 驗證結果 is_ok 語義正確
    Given 模組驗證回傳 WARNING
    Then is_ok 應為 True（WARNING 不算致命）

  # ═══════════════════════════════════════════════════════════════
  # Section 4：背景服務（Daemon）(25 scenarios)
  # 模擬：伺服器管理員、首次用 Mac 的人、有舊版 MuseClaw 的人
  # ═══════════════════════════════════════════════════════════════

  Scenario: DMN-01 生成 plist 包含正確 Label
    When 生成 plist
    Then 應包含正確的 Label 標籤

  Scenario: DMN-02 生成 plist 包含正確 ProgramArguments
    When 生成 plist
    Then ProgramArguments 應包含 uvicorn 指令

  Scenario: DMN-03 生成 plist 包含環境變數
    When 生成 plist
    Then 應包含 PYTHONPATH 和 MUSECLAW_HOME

  Scenario: DMN-04 plist RunAtLoad 為 true
    When 生成 plist
    Then RunAtLoad 應為 true

  Scenario: DMN-05 plist 包含 log 路徑
    When 生成 plist
    Then 應包含 StandardOutPath 和 StandardErrorPath

  Scenario: DMN-06 寫入 plist 成功
    When 寫入 plist 到磁碟
    Then 應回傳 SUCCESS

  Scenario: DMN-07 寫入 plist 目錄不存在 — 自動建立
    Given plist 目錄不存在
    When 寫入 plist
    Then 應自動建立目錄並寫入

  Scenario: DMN-08 寫入 plist 權限不足
    Given plist 目錄權限為唯讀
    When 寫入 plist
    Then 應回傳 FAILED

  Scenario: DMN-09 卸載現有 daemon（bootout 成功）
    Given 有舊版 daemon 在執行
    When 卸載現有 daemon
    Then 應透過 bootout 成功卸載

  Scenario: DMN-10 卸載 — bootout 失敗改用 unload
    Given bootout 失敗
    When 卸載現有 daemon
    Then 應 fallback 到 launchctl unload

  Scenario: DMN-11 卸載 — 沒有現有 daemon
    Given 沒有現有 daemon
    When 卸載現有 daemon
    Then 應回傳 SUCCESS（無需操作）

  Scenario: DMN-12 載入 daemon 成功
    When 載入 daemon
    Then 應回傳 SUCCESS

  Scenario: DMN-13 載入 daemon 失敗
    Given launchctl load 回傳非零
    When 載入 daemon
    Then 應回傳 FAILED

  Scenario: DMN-14 健康檢查成功（HTTP 200）
    Given Gateway 在 localhost:8765 回應 200
    When 執行健康檢查
    Then 應回傳 SUCCESS

  Scenario: DMN-15 健康檢查失敗（非 200）
    Given Gateway 回應 500
    When 執行健康檢查
    Then 應回傳 FAILED

  Scenario: DMN-16 健康檢查超時
    Given Gateway 沒有回應
    When 執行健康檢查（timeout=3）
    Then 應回傳 FAILED

  Scenario: DMN-17 健康檢查 curl 不存在
    Given 系統沒有 curl
    When 執行健康檢查
    Then 應回傳 FAILED

  Scenario: DMN-18 plist 路徑正確性
    Given 設定使用預設 plist 名稱
    Then plist_path 應為 ~/Library/LaunchAgents/com.museclaw.gateway.plist

  Scenario: DMN-19 卸載 daemon 超時
    Given launchctl bootout 超時
    When 卸載 daemon
    Then 應 fallback 到 unload

  Scenario: DMN-20 生成 plist 的 ThrottleInterval
    When 生成 plist
    Then ThrottleInterval 應為 5

  Scenario: DMN-21 生成 plist 的 KeepAlive 設定
    When 生成 plist
    Then KeepAlive SuccessfulExit 應為 false

  Scenario: DMN-22 log 目錄自動建立
    Given log 目錄不存在
    When 寫入 plist
    Then log 目錄應被建立

  Scenario: DMN-23 健康檢查使用正確 port
    When 檢查 port 8765 的健康狀態
    Then curl 應存取 http://127.0.0.1:8765/health

  Scenario: DMN-24 plist ProcessType
    When 生成 plist
    Then ProcessType 應為 "Background"

  Scenario: DMN-25 plist PATH 環境變數
    When 生成 plist
    Then PATH 應包含 /usr/local/bin 和 /opt/homebrew/bin

  # ═══════════════════════════════════════════════════════════════
  # Section 5：API Key 設定 (25 scenarios)
  # 模擬：不懂 API 的老闆、複製貼上帶空格、重複設定
  # ═══════════════════════════════════════════════════════════════

  Scenario: KEY-01 建立新 .env 檔案
    Given .env 不存在
    When 建立 .env 檔案
    Then 應以模板建立並回傳 SUCCESS

  Scenario: KEY-02 .env 已存在 — 不覆蓋
    Given .env 已有內容
    When 建立 .env 檔案
    Then 應跳過不覆蓋

  Scenario: KEY-03 寫入新 key 到 .env
    Given .env 已存在
    When 寫入 "ANTHROPIC_API_KEY=sk-ant-api03-test"
    Then .env 應包含該 key-value

  Scenario: KEY-04 更新已存在的 key
    Given .env 已有 "ANTHROPIC_API_KEY=old"
    When 寫入 "ANTHROPIC_API_KEY=new"
    Then 應覆蓋為新值且只有一行

  Scenario: KEY-05 更新被註解的 key
    Given .env 有 "# ANTHROPIC_API_KEY=placeholder"
    When 寫入 "ANTHROPIC_API_KEY=real_value"
    Then 註解行應被替換為實際值

  Scenario: KEY-06 has_key 檢查存在的 key
    Given .env 有 "TELEGRAM_BOT_TOKEN=123:abc"
    When 檢查是否有 TELEGRAM_BOT_TOKEN
    Then 應回傳 True

  Scenario: KEY-07 has_key 檢查不存在的 key
    Given .env 沒有 TELEGRAM_BOT_TOKEN
    When 檢查是否有 TELEGRAM_BOT_TOKEN
    Then 應回傳 False

  Scenario: KEY-08 has_key 跳過註解行
    Given .env 有 "# ANTHROPIC_API_KEY=placeholder"
    When 檢查是否有 ANTHROPIC_API_KEY
    Then 應回傳 False（註解不算）

  Scenario: KEY-09 has_key 檔案不存在
    Given .env 檔案不存在
    When 檢查是否有任何 key
    Then 應回傳 False

  Scenario: KEY-10 write_key 到不存在的目錄
    Given .env 的父目錄不存在
    When 寫入 key
    Then 應自動建立目錄

  Scenario: KEY-11 ENV_TEMPLATE 包含必要佔位符
    Then ENV_TEMPLATE 應包含 ANTHROPIC_API_KEY 和 TELEGRAM_BOT_TOKEN

  Scenario: KEY-12 write_key 保持其他行不變
    Given .env 有多行內容
    When 更新其中一行
    Then 其他行應完整保留

  Scenario: KEY-13 .env 有空行和註解混合
    Given .env 有空行和多個註解
    When 寫入新 key
    Then 應正確附加在最後

  Scenario: KEY-14 key 值包含等號
    Given 要儲存的值包含 "=" 符號
    When 寫入 key
    Then 應正確處理值中的等號

  Scenario: KEY-15 has_key 對空值 key 的處理
    Given .env 有 "ANTHROPIC_API_KEY="（空值）
    When 檢查是否有 ANTHROPIC_API_KEY
    Then 應回傳 False（空值不算）

  Scenario: KEY-16 write_key 回傳 StepResult
    When 寫入 key 成功
    Then 應回傳 StepResult(status=SUCCESS)

  Scenario: KEY-17 create_env_file 檔案內容正確
    When 建立新 .env
    Then 內容應包含模板的所有行

  Scenario: KEY-18 write_key 多次寫入同一 key
    When 對同一 key 寫入三次不同值
    Then .env 應只有最後一次的值

  Scenario: KEY-19 has_key 處理只有 key 名沒有等號
    Given .env 有 "ANTHROPIC_API_KEY" （沒有等號）
    When 檢查 has_key
    Then 應回傳 False

  Scenario: KEY-20 write_key 檔案寫入權限問題
    Given .env 檔案為唯讀
    When 嘗試寫入 key
    Then 應回傳 FAILED

  Scenario: KEY-21 CRLF 換行處理
    Given .env 使用 CRLF 換行
    When 讀取和寫入 key
    Then 應正確處理不同換行符

  Scenario: KEY-22 key 值前後有空格
    Given 使用者複製貼上帶前後空格的 key
    When 寫入 key
    Then 應保存原始值（含空格）

  Scenario: KEY-23 key 值包含引號
    Given 使用者輸入帶引號的值 '"sk-ant-xxx"'
    When 寫入 key
    Then 應保存包含引號的值

  Scenario: KEY-24 .env 檔案很大（100+ 行）
    Given .env 有超過 100 行
    When 更新其中一個 key
    Then 應正確找到並更新

  Scenario: KEY-25 create_env_file 目錄權限不足
    Given .env 目錄權限不足
    When 建立 .env
    Then 應回傳 FAILED

  # ═══════════════════════════════════════════════════════════════
  # Section 6：Setup Wizard 精靈 (30 scenarios)
  # 模擬：第一次開 Dashboard、重新設定、各種輸入錯誤
  # ═══════════════════════════════════════════════════════════════

  Scenario: WIZ-01 首次啟動 — .env 不存在
    Given .env 檔案不存在
    When 判斷是否為首次啟動
    Then 應回傳 True

  Scenario: WIZ-02 首次啟動 — .env 缺少 SETUP_DONE
    Given .env 有 API key 但沒有 MUSECLAW_SETUP_DONE
    When 判斷是否為首次啟動
    Then 應回傳 True

  Scenario: WIZ-03 非首次啟動 — 已完成設定
    Given .env 有所有 key 和 MUSECLAW_SETUP_DONE=1
    When 判斷是否為首次啟動
    Then 應回傳 False

  Scenario: WIZ-04 SETUP_DONE=0 的語義問題
    Given .env 有 MUSECLAW_SETUP_DONE=0
    When 判斷是否為首次啟動
    Then 應回傳 True（0 不代表完成）

  Scenario: WIZ-05 儲存 Anthropic key 成功
    When 透過 SetupManager 儲存 ANTHROPIC_API_KEY
    Then 應回傳 SUCCESS

  Scenario: WIZ-06 儲存 Telegram token 成功
    When 透過 SetupManager 儲存 TELEGRAM_BOT_TOKEN
    Then 應回傳 SUCCESS

  Scenario: WIZ-07 儲存時 .env 不存在 — 自動建立
    Given .env 不存在
    When 儲存 API key
    Then 應先建立 .env 再儲存

  Scenario: WIZ-08 驗證有效 Anthropic key 格式
    When 驗證 "sk-ant-api03-validkey123"
    Then 格式驗證應通過

  Scenario: WIZ-09 驗證無效 Anthropic key — 缺少前綴
    When 驗證 "invalid-key-without-prefix"
    Then 格式驗證應失敗

  Scenario: WIZ-10 驗證 Anthropic key — 太短
    When 驗證 "sk-ant-api03-x"
    Then 格式驗證應失敗（長度不足）

  Scenario: WIZ-11 驗證空 Anthropic key
    When 驗證 ""
    Then 格式驗證應失敗並提示不得為空

  Scenario: WIZ-12 驗證有效 Telegram token
    When 驗證 "123456789:ABCdefGHIjklMNOpqrsTUV"
    Then Telegram 格式驗證應通過

  Scenario: WIZ-13 驗證無效 Telegram token — 無冒號
    When 驗證 "no-colon-here"
    Then Telegram 格式驗證應失敗

  Scenario: WIZ-14 驗證 Telegram token — 冒號前不是數字
    When 驗證 "abc:defghijk"
    Then Telegram 格式驗證應失敗

  Scenario: WIZ-15 驗證空 Telegram token
    When 驗證空 Telegram token
    Then 格式驗證應失敗

  Scenario: WIZ-16 Anthropic 連線測試成功
    Given API 回應 HTTP 200
    When 測試 Anthropic 連線
    Then 應回傳 (True, 成功訊息)

  Scenario: WIZ-17 Anthropic 連線測試 — key 無效 (401)
    Given API 回應 HTTP 401
    When 測試 Anthropic 連線
    Then 應回傳 (False, 驗證失敗訊息)

  Scenario: WIZ-18 Anthropic 連線測試 — 超時
    Given API 連線超時
    When 測試 Anthropic 連線
    Then 應回傳 (False, 超時訊息)

  Scenario: WIZ-19 Telegram 連線測試成功
    Given Telegram API 回應成功
    When 測試 Telegram 連線
    Then 應回傳 (True, 含 Bot 名稱)

  Scenario: WIZ-20 Telegram 連線測試 — token 無效
    Given Telegram API 回應 401
    When 測試 Telegram 連線
    Then 應回傳 (False, 驗證失敗)

  Scenario: WIZ-21 Telegram 連線測試 — 超時
    Given Telegram API 連線超時
    When 測試 Telegram 連線
    Then 應回傳 (False, 超時訊息)

  Scenario: WIZ-22 取得設定狀態 — 全部未設定
    Given .env 為空
    When 取得設定狀態
    Then 所有 key 狀態應為未設定

  Scenario: WIZ-23 取得設定狀態 — 部分設定
    Given .env 只有 ANTHROPIC_API_KEY
    When 取得設定狀態
    Then ANTHROPIC 已設定，TELEGRAM 未設定

  Scenario: WIZ-24 取得設定狀態 — 值遮罩
    Given .env 有長 API key
    When 取得設定狀態
    Then masked_value 不應包含完整 key

  Scenario: WIZ-25 值遮罩 — 短值（<=8 字元）
    Given key 值只有 5 個字元
    When 遮罩值
    Then 應顯示前 3 字元 + "***"

  Scenario: WIZ-26 值遮罩 — 長值（>8 字元）
    Given key 值超過 8 字元
    When 遮罩值
    Then 應顯示前 8 字元 + "***"

  Scenario: WIZ-27 值遮罩 — 空值
    Given key 值為空
    When 遮罩值
    Then 應回傳空字串

  Scenario: WIZ-28 標記設定完成
    When 標記設定完成
    Then .env 應包含 MUSECLAW_SETUP_DONE=1

  Scenario: WIZ-29 REQUIRED_KEYS 完整性
    Then REQUIRED_KEYS 應包含 ANTHROPIC_API_KEY 和 TELEGRAM_BOT_TOKEN

  Scenario: WIZ-30 Anthropic 連線測試 — 非 200/401 狀態碼
    Given API 回應 HTTP 500
    When 測試 Anthropic 連線
    Then 應回傳 (False, 含狀態碼資訊)

  # ═══════════════════════════════════════════════════════════════
  # Section 7：安全性閘道 (25 scenarios)
  # 模擬：惡意使用者、注入攻擊、DDoS 嘗試
  # ═══════════════════════════════════════════════════════════════

  Scenario: SEC-01 有效 HMAC 驗證通過
    Given 使用正確 secret 產生 HMAC
    When 驗證 HMAC
    Then 應回傳 True

  Scenario: SEC-02 無效 HMAC 驗證失敗
    Given 使用錯誤 secret 產生 HMAC
    When 驗證 HMAC
    Then 應回傳 False

  Scenario: SEC-03 空 HMAC 簽章
    When 驗證空 HMAC 簽章
    Then 應回傳 False

  Scenario: SEC-04 速率限制 — 正常請求通過
    Given 使用者在 1 分鐘內只發送 5 次請求
    When 檢查速率限制
    Then 應回傳 True（允許）

  Scenario: SEC-05 速率限制 — 超過上限
    Given 使用者在 1 分鐘內發送 61 次請求
    When 檢查速率限制
    Then 應回傳 False（拒絕）

  Scenario: SEC-06 速率限制 — 舊紀錄清除
    Given 使用者有 60 秒前的請求紀錄
    When 新請求到達
    Then 舊紀錄應被清除

  Scenario: SEC-07 速率限制 — 不同使用者獨立計算
    Given 使用者 A 和使用者 B 各發送請求
    When 檢查速率限制
    Then 各自獨立計算

  Scenario: SEC-08 輸入清理 — 命令替換 $()
    When 清理包含 "$(rm -rf /)" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-09 輸入清理 — 反引號命令
    When 清理包含 "`whoami`" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-10 輸入清理 — 管線注入
    When 清理包含 "| cat /etc/passwd" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-11 輸入清理 — SQL 注入
    When 清理包含 "DROP TABLE users" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-12 輸入清理 — XSS script 標籤
    When 清理包含 "<script>alert(1)</script>" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-13 輸入清理 — javascript: 協議
    When 清理包含 "javascript:alert(1)" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-14 輸入清理 — 路徑遍歷
    When 清理包含 "../../etc/passwd" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-15 輸入清理 — 正常文字通過
    When 清理 "Hello, how are you?"
    Then 應回傳原始文字

  Scenario: SEC-16 輸入清理 — 超大內容（>50KB）
    When 清理超過 50KB 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-17 輸入清理 — 剛好 50KB
    When 清理剛好 50KB 的輸入
    Then 應通過（不超過限制）

  Scenario: SEC-18 來源驗證 — telegram 允許
    When 驗證來源 "telegram"
    Then 應回傳 True

  Scenario: SEC-19 來源驗證 — webhook 允許
    When 驗證來源 "webhook"
    Then 應回傳 True

  Scenario: SEC-20 來源驗證 — 未知來源拒絕
    When 驗證來源 "unknown"
    Then 應回傳 False

  Scenario: SEC-21 HMAC 使用 constant-time 比較
    Then HMAC 驗證應使用 hmac.compare_digest

  Scenario: SEC-22 輸入清理 — 分號命令串接
    When 清理包含 "; rm -rf /" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-23 輸入清理 — && 命令串接
    When 清理包含 "&& cat secret" 的輸入
    Then 應拋出 ValueError

  Scenario: SEC-24 來源驗證 — electron 允許
    When 驗證來源 "electron"
    Then 應回傳 True

  Scenario: SEC-25 來源驗證 — 空字串
    When 驗證空來源
    Then 應回傳 False

  # ═══════════════════════════════════════════════════════════════
  # Section 8：工作階段管理 (15 scenarios)
  # 模擬：多使用者同時使用、長時間佔用、斷線重連
  # ═══════════════════════════════════════════════════════════════

  Scenario: SES-01 取得鎖定成功
    When 新 session 嘗試取得鎖定
    Then 應回傳 True

  Scenario: SES-02 鎖定已被佔用
    Given session "user1" 已取得鎖定
    When "user1" 再次嘗試取得鎖定
    Then 應回傳 False

  Scenario: SES-03 釋放鎖定
    Given session "user1" 已取得鎖定
    When 釋放 "user1" 的鎖定
    Then 再次取得應成功

  Scenario: SES-04 is_processing 預設值
    When 查詢未知 session 的處理狀態
    Then 應回傳 False

  Scenario: SES-05 is_processing 取得鎖後為 True
    Given session 已取得鎖定
    When 查詢處理狀態
    Then 應回傳 True

  Scenario: SES-06 is_processing 釋放後為 False
    Given session 已取得並釋放鎖定
    When 查詢處理狀態
    Then 應回傳 False

  Scenario: SES-07 wait_and_acquire 無超時
    When 等待取得鎖定（無超時）
    Then 應成功取得

  Scenario: SES-08 wait_and_acquire 超時
    Given 鎖定已被佔用
    When 等待取得鎖定（超時 0.1 秒）
    Then 應回傳 False

  Scenario: SES-09 不同 session 各自獨立
    When session A 和 B 各自取得鎖定
    Then 兩者應都成功

  Scenario: SES-10 釋放不存在的 session
    When 釋放從未取得鎖定的 session
    Then 不應拋出異常

  Scenario: SES-11 重複釋放同一 session
    Given session 已釋放
    When 再次釋放
    Then 不應拋出異常

  Scenario: SES-12 鎖定自動建立
    When 取得新 session 的鎖定
    Then 鎖定物件應被自動建立

  Scenario: SES-13 多個 session 同時操作
    When 同時建立 10 個不同 session
    Then 全部應能成功取得鎖定

  Scenario: SES-14 wait_and_acquire 鎖定釋放後取得
    Given 鎖定被佔用
    When 另一 coroutine 等待取得
    And 原持有者釋放鎖定
    Then 等待者應成功取得

  Scenario: SES-15 session_id 為空字串
    When 使用空字串 session_id 取得鎖定
    Then 應能正常運作

  # ═══════════════════════════════════════════════════════════════
  # Section 9：安裝流程整合（Orchestrator）(25 scenarios)
  # 模擬：完整安裝、中途失敗、部分跳過
  # ═══════════════════════════════════════════════════════════════

  Scenario: ORC-01 完整安裝流程 — 7 個步驟
    Then STEPS 應有 7 個步驟

  Scenario: ORC-02 STEP_LABELS 對應正確
    Then 每個步驟都應有對應的顯示標籤

  Scenario: ORC-03 run 成功執行所有步驟
    Given 所有步驟都成功
    When 執行安裝
    Then 應回傳 7 個 SUCCESS 結果

  Scenario: ORC-04 run 遇到 FAILED 停止
    Given 第 3 步驟失敗
    When 執行安裝
    Then 應在第 3 步停止

  Scenario: ORC-05 run 遇到 WARNING 繼續
    Given 第 2 步驟回傳 WARNING
    When 執行安裝
    Then 應繼續執行後續步驟

  Scenario: ORC-06 run 遇到 SKIPPED 繼續
    Given 第 4 步驟回傳 SKIPPED
    When 執行安裝
    Then 應繼續執行後續步驟

  Scenario: ORC-07 generate_summary 全部成功
    Given 所有步驟成功
    When 生成摘要
    Then 應包含所有成功圖示

  Scenario: ORC-08 generate_summary 含失敗
    Given 有步驟失敗
    When 生成摘要
    Then 應包含失敗圖示和計數

  Scenario: ORC-09 generate_summary 含混合狀態
    Given 有成功、警告、跳過步驟
    When 生成摘要
    Then 應正確顯示各類計數

  Scenario: ORC-10 check_day0_readiness — daemon 正常
    Given daemon 健康檢查通過
    When 檢查 day0 準備狀態
    Then 應提示下一步（如設定 Telegram）

  Scenario: ORC-11 check_day0_readiness — daemon 失敗
    Given daemon 健康檢查失敗
    When 檢查 day0 準備狀態
    Then 應提示 daemon 問題

  Scenario: ORC-12 _step_environment 整合檢查
    When 執行環境步驟
    Then 應檢查 OS、Python、磁碟空間

  Scenario: ORC-13 _step_python_env — venv 已存在
    Given venv 已存在
    When 執行 Python 環境步驟
    Then 應跳過建立直接安裝依賴

  Scenario: ORC-14 _step_python_env — venv 不存在
    Given venv 不存在
    When 執行 Python 環境步驟
    Then 應建立 venv 再安裝依賴

  Scenario: ORC-15 _step_verify_modules — 全部成功
    Given 所有模組載入成功
    When 執行模組驗證步驟
    Then 應回傳 SUCCESS

  Scenario: ORC-16 _step_verify_modules — 有失敗
    Given 某模組載入失敗
    When 執行模組驗證步驟
    Then 應回傳 FAILED

  Scenario: ORC-17 _step_electron — 沒有 Node.js
    Given 系統沒有 Node.js
    When 執行 Electron 步驟
    Then 應回傳 SKIPPED

  Scenario: ORC-18 _step_electron — 沒有 npm
    Given 有 Node 但沒有 npm
    When 執行 Electron 步驟
    Then 應回傳 SKIPPED

  Scenario: ORC-19 _step_electron — 沒有 electron/ 目錄
    Given electron/ 目錄不存在
    When 執行 Electron 步驟
    Then 應回傳 SKIPPED

  Scenario: ORC-20 _step_daemon 整合流程
    When 執行 daemon 步驟
    Then 應依序卸載、寫入、載入

  Scenario: ORC-21 _step_api_keys — 非互動模式
    Given interactive=False
    When 執行 API key 步驟
    Then 應回傳 SKIPPED

  Scenario: ORC-22 _step_launch — 健康檢查通過
    Given Gateway 健康
    When 執行啟動步驟
    Then 應回傳 SUCCESS

  Scenario: ORC-23 _step_launch — 健康檢查失敗
    Given Gateway 未啟動
    When 執行啟動步驟
    Then 應回傳 FAILED

  Scenario: ORC-24 try_open_dashboard — Dashboard 存在
    Given Dashboard.app 存在
    When 嘗試開啟 Dashboard
    Then 應呼叫 subprocess.run open

  Scenario: ORC-25 try_open_dashboard — Dashboard 不存在
    Given Dashboard.app 不存在
    When 嘗試開啟 Dashboard
    Then 不應嘗試開啟

  # ═══════════════════════════════════════════════════════════════
  # Section 10：Models 和資料結構 (15 scenarios)
  # ═══════════════════════════════════════════════════════════════

  Scenario: MDL-01 StepStatus 列舉值完整
    Then StepStatus 應有 PENDING, SUCCESS, WARNING, SKIPPED, FAILED

  Scenario: MDL-02 StepResult is_ok — SUCCESS
    Given StepResult(status=SUCCESS)
    Then is_ok 應為 True

  Scenario: MDL-03 StepResult is_ok — WARNING
    Given StepResult(status=WARNING)
    Then is_ok 應為 True

  Scenario: MDL-04 StepResult is_ok — SKIPPED
    Given StepResult(status=SKIPPED)
    Then is_ok 應為 True

  Scenario: MDL-05 StepResult is_ok — FAILED
    Given StepResult(status=FAILED)
    Then is_ok 應為 False

  Scenario: MDL-06 StepResult is_fatal — FAILED
    Given StepResult(status=FAILED)
    Then is_fatal 應為 True

  Scenario: MDL-07 StepResult is_fatal — SUCCESS
    Given StepResult(status=SUCCESS)
    Then is_fatal 應為 False

  Scenario: MDL-08 StepResult details 可選
    When 建立 StepResult 不帶 details
    Then details 應為 None

  Scenario: MDL-09 InstallConfig 自動初始化路徑
    Given project_dir 為 /tmp/museclaw
    When 建立 InstallConfig
    Then venv_dir 應為 /tmp/museclaw/.venv

  Scenario: MDL-10 InstallConfig plist_path
    Then plist_path 應指向 LaunchAgents

  Scenario: MDL-11 InstallConfig venv_python
    Then venv_python 應指向 .venv/bin/python

  Scenario: MDL-12 InstallConfig gateway_log
    Then gateway_log 應指向 logs/gateway.log

  Scenario: MDL-13 InstallConfig 預設值正確
    Then gateway_port 應為 8765
    And min_disk_mb 應為 500

  Scenario: MDL-14 SystemInfo 資料結構
    When 建立 SystemInfo
    Then 應包含 os_type, arch, python_path 等欄位

  Scenario: MDL-15 StepResult 字串表示
    Given 一個 StepResult
    Then 應能正常轉為字串
