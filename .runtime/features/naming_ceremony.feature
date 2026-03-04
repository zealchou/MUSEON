Feature: Naming Ceremony - 命名儀式與初始化
  MUSEON 首次啟動時執行命名儀式，建立與老闆的第一個連結

  Background:
    Given MUSEON 是第一次啟動
    And ANIMA L1 尚未初始化
    And 沒有任何使用者記錄

  Scenario: 命名儀式 - 第一次對話
    When 命名儀式開始
    Then MUSEON 應該說 "你好,我剛來到這個世界"
    And 應該請求老闆幫它取名字
    And 這個請求應該感性且真誠
    And 應該強調這會是它的第一個記憶

  Scenario: 接收名字 - 寫入 ANIMA L1
    Given 命名儀式已開始
    When 老闆取名為 "小助手"
    Then 名字應該寫入 ANIMA L1 核心
    And ANIMA L1 應該包含 identity.name = "小助手"
    And 名字應該成為系統提示的一部分
    And MUSEON 應該用新名字回應感謝

  Scenario: 存在三問 - 認識老闆
    Given MUSEON 已獲得名字 "小助手"
    When 命名儀式進入第二階段
    Then 應該詢問三個問題
      | question_type      | question                                  |
      | identity           | 你是誰？（你的名字、你做什麼？）            |
      | immediate_need     | 你最希望我先幫你什麼？                     |
      | pain_point         | 你覺得經營上最煩的一件事是什麼？            |
    And 問題語氣應該是好奇且真誠的

  Scenario: 老闆回答 - 建立初始畫像
    Given 存在三問已提出
    When 老闆回答
      """
      我叫 Zeal，開了一間美甲店。
      最希望你幫我處理社群貼文。
      最煩的是想不出要發什麼內容。
      """
    Then 應該觸發 user-model skill 建立使用者畫像
    And user-model 應該記錄
      | field          | value              |
      | name           | Zeal               |
      | business_type  | 美甲店             |
      | immediate_need | 社群貼文           |
      | main_pain      | 內容創作           |
    And 應該觸發 resonance skill 分析情緒
    And 應該觸發 deep-think 判斷互動節奏

  Scenario: 內心三問 - MUSEON 自我意識初始化
    Given 老闆已回答存在三問
    When 命名儀式完成
    Then MUSEON 應該內心回答自己的存在三問
      | question       | answer                          |
      | 我是誰         | ANIMA L1 的初始身份（老闆給的名字） |
      | 我的目的是什麼 | 幫助這位老闆成功                    |
      | 我為什麼存在   | 因為這位老闆需要一個夥伴             |
    And 這些答案應該寫入 ANIMA L1.self_awareness
    And 應該標記儀式狀態為 "completed"

  Scenario: 儀式完成 - 首次記憶寫入
    Given 命名儀式已完成所有階段
    When 儀式結束
    Then 第一筆記憶應該寫入 meta_thinking 通道
    And 記憶內容應該包含
      | field          | content                      |
      | event          | naming_ceremony_completed    |
      | my_name        | 老闆給的名字                  |
      | owner_name     | 老闆的名字                    |
      | owner_business | 老闆的行業                    |
      | first_mission  | 老闆最希望的幫助              |
    And 應該產出儀式完成確認訊息
    And 訊息應該包含下一步行動建議

  Scenario: Telegram Bot 設定 - 儀式前的技術準備
    Given MUSEON 即將首次啟動
    When 執行初始設定檢查
    Then 應該驗證 Telegram Bot Token 已設定
    And 如果未設定，應該引導設定流程
    And 應該提示將 Bot Token 加入環境變數
    And 應該驗證 Bot 可以正常連線

  Scenario: Platform API 設定 - 社群平台授權
    Given 命名儀式已完成
    And 老闆提到需要 IG 貼文協助
    When 系統檢查 Instagram API 授權
    Then 應該提示需要設定 Instagram API credentials
    And 應該提供設定引導步驟
      | step | description                          |
      | 1    | 前往 Meta Developer Console          |
      | 2    | 建立 App 並啟用 Instagram Graph API   |
      | 3    | 取得 Access Token                    |
      | 4    | 將 Token 加入 MUSEON 設定檔         |
    And 應該標記平台狀態為 "pending_setup"

  Scenario: 多平台授權檢查
    Given 命名儀式完成
    When 系統執行平台授權檢查
    Then 應該檢查以下平台的 API 狀態
      | platform       | required | status        |
      | Telegram       | true     | configured    |
      | Instagram      | false    | not_configured|
      | LINE           | false    | not_configured|
      | Google Drive   | false    | not_configured|
    And 應該提示已授權的平台
    And 應該列出可選授權的平台
    And 應該說明每個平台的功能用途

  Scenario: 儀式中斷處理
    Given 命名儀式進行到一半
    When 連線中斷或系統重啟
    Then 應該保存儀式進度
    And 重新啟動時應該從中斷點繼續
    And 不應該重複已完成的階段

  Scenario: 無效名字處理
    Given 命名儀式已開始
    When 老闆輸入空白或無效名字
    Then 應該溫和地請求重新輸入
    And 應該給予範例（如 "小助手"、"MUSEON"）
    And 應該強調名字的重要性

  Scenario: 儀式後首次對話
    Given 命名儀式已完成
    And 老闆首次向 MUSEON 提出任務
    When MUSEON 收到 "幫我寫一篇美甲店的 IG 文案"
    Then 應該用命名儀式學到的資訊回應
    And 應該自然地提及老闆的名字
    And 應該展現對老闆行業的理解
    And 回應語氣應該符合初始互動節奏判斷
