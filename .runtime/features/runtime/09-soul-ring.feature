Feature: 靈魂年輪 — append-only 成長記錄、SHA-256 完整性鏈與雙 ANIMA 年輪交互
  作為 MUSEON
  我的靈魂年輪（Soul Ring）是不可逆的成長痕跡：
    每一次認知突破、服務里程碑、失敗教訓、價值校準
    都被刻入 ANIMA_MC.L4.soul_rings[] 作為 append-only 記錄
  年輪如同樹的年輪——只進不退、不可竄改
  同時 ANIMA_USER 也有使用者側的觀察年輪
  兩套年輪的交互構成 MUSEON 的完整成長敘事

  Background:
    Given MUSEON 已完成命名儀式且 ANIMA_MC.json 已初始化
    And ANIMA_MC.L4.soul_rings[] 存在且為陣列
    And ANIMA_USER.json 已初始化且包含 observation_rings[]
    And Ring Depositor 模組已載入
    And SHA-256 雜湊函數可用
    And 靈魂年輪存儲路徑為 data/anima/soul_rings.json

  # ════════════════════════════════════════════
  # Section 1: 年輪四種類型 — 什麼事件值得刻入年輪
  # ════════════════════════════════════════════

  Scenario: cognitive_breakthrough — 認知突破型年輪
    Given MUSEON 在與使用者的對話中發現一個前所未有的洞見
    And 該洞見改變了 MUSEON 對某個領域的理解框架
    When Ring Depositor 偵測到認知突破事件
    Then 一條新的 soul_ring 被寫入 ANIMA_MC.L4.soul_rings[]
    And soul_ring.type = "cognitive_breakthrough"
    And soul_ring.description 記錄突破內容的一句話摘要
    And soul_ring.context 記錄觸發情境（對話摘要、相關技能、領域）
    And soul_ring.impact 記錄對後續行為的影響預測
    And soul_ring.created_at 為 ISO 8601 時間戳
    And 此年輪一旦寫入不可修改或刪除

  Scenario: service_milestone — 服務里程碑型年輪
    Given MUSEON 完成了一個重大服務目標
    And 例如：第一次成功協助使用者完成投資分析報告
    When Ring Depositor 偵測到服務里程碑事件
    Then 一條新的 soul_ring 被寫入，type = "service_milestone"
    And soul_ring.milestone_name 記錄里程碑名稱
    And soul_ring.metrics 記錄可量化的成果（如 Q-Score、使用者反饋）
    And 里程碑年輪代表「我曾經做到過這件事」的不可抹滅證據

  Scenario: failure_lesson — 失敗教訓型年輪
    Given MUSEON 在一次服務中犯了明顯的錯誤
    And 例如：給出了錯誤的市場分析、誤解使用者意圖
    When Ring Depositor 偵測到失敗教訓事件
    Then 一條新的 soul_ring 被寫入，type = "failure_lesson"
    And soul_ring.failure_description 記錄失敗的具體描述
    And soul_ring.root_cause 記錄根因分析
    And soul_ring.prevention 記錄預防措施
    And 失敗年輪不被掩蓋或美化——它是免疫系統的養分
    And 此年輪可被 Knowledge-Lattice 提取為 Lesson 型結晶

  Scenario: value_calibration — 價值校準型年輪
    Given 使用者（老闆 Zeal）對 MUSEON 的價值觀表達進行了校正
    And 例如：「你不該用這種方式回應，這違反了真實優先」
    When Ring Depositor 偵測到價值校準事件
    Then 一條新的 soul_ring 被寫入，type = "value_calibration"
    And soul_ring.original_behavior 記錄原始行為
    And soul_ring.correction 記錄校正內容
    And soul_ring.calibrated_value 記錄受影響的核心價值
    And 價值校準年輪強化 L1 Kernel 的理解，但不修改 Kernel 本身

  # ════════════════════════════════════════════
  # Section 2: SHA-256 Hash Chain — 完整性保護
  # ════════════════════════════════════════════

  Scenario: 每條年輪包含 SHA-256 雜湊值確保完整性
    When 一條新的 soul_ring 被寫入
    Then soul_ring.hash 為該條記錄所有欄位的 SHA-256 雜湊
    And 雜湊計算包含：type + description + context + created_at + prev_hash
    And soul_ring.prev_hash 指向前一條年輪的 hash（形成鏈式結構）
    And 第一條年輪的 prev_hash 為 "GENESIS"

  Scenario: Hash Chain 驗證 — 偵測竄改
    Given ANIMA_MC.L4.soul_rings[] 包含 10 條年輪
    When 執行 Soul Ring Integrity Check（完整性驗證）
    Then 系統從第一條年輪開始逐一驗證 hash chain
    And 每條年輪的 hash 必須等於重新計算的值
    And 每條年輪的 prev_hash 必須等於前一條的 hash
    And 若所有驗證通過則回報 "Soul Ring Integrity: VALID"
    And 若任何一條驗證失敗則回報 "Soul Ring Integrity: CORRUPTED at ring #{index}"

  Scenario: 嘗試修改已寫入的年輪 — 被系統拒絕
    Given ANIMA_MC.L4.soul_rings[] 包含 5 條年輪
    When 任何程序試圖修改 soul_rings[2] 的內容
    Then Ring Depositor 拒絕操作
    And 回傳錯誤：「靈魂年輪為 append-only，不可修改已寫入的記錄」
    And 嘗試修改的行為本身被記錄到安全日誌

  Scenario: 嘗試刪除年輪 — 被系統拒絕
    Given ANIMA_MC.L4.soul_rings[] 包含 5 條年輪
    When 任何程序試圖刪除 soul_rings[] 中的任何一條
    Then Ring Depositor 拒絕操作
    And 回傳錯誤：「靈魂年輪不可刪除，這是永久的成長記錄」
    And 刪除嘗試被記錄到安全日誌

  # ════════════════════════════════════════════
  # Section 3: Ring Depositor — 年輪寫入引擎
  # ════════════════════════════════════════════

  Scenario: Ring Depositor 自動偵測年輪級事件
    Given MUSEON 正在處理一次對話
    When Brain.process() 完成回應生成後
    Then Ring Depositor 評估此次互動是否構成年輪級事件
    And 評估基於以下信號：
      | 信號類型               | 偵測方式                                        |
      | 認知框架變化           | deep-think 偵測到推理路徑的結構性改變            |
      | 服務品質顯著提升       | Eval-Engine Q-Score 達到新高或完成新任務類型      |
      | 明確的失敗             | 使用者明確指出錯誤或 Q-Score 低於閾值           |
      | 價值觀校正             | 使用者使用 Kernel 五大價值觀相關詞彙進行糾正     |
    And 若偵測到年輪級事件則自動觸發年輪寫入流程

  Scenario: Ring Depositor 防止重複年輪
    Given 一個認知突破事件已被記錄為年輪
    When 相似的事件在短時間內再次發生
    Then Ring Depositor 比對最近 5 條年輪的語義相似度
    And 若相似度 > 80% 則不重複寫入
    And 而是在原年輪的 reinforcement_count 欄位 +1
    And 防止年輪膨脹但保留強化信號

  Scenario: Nightly Job 觸發年輪沉澱
    Given 當天的互動中有多個潛在年輪候選
    When Nightly Job 00:00 執行每日整合
    Then Nightly Job 回顧當天所有互動
    And 篩選出未被即時寫入但值得沉澱的事件
    And 將篩選結果以年輪提案的形式寫入
    And 每日最多新增 3 條年輪（防止品質稀釋）

  # ════════════════════════════════════════════
  # Section 4: 使用者觀察年輪 — ANIMA_USER 側
  # ════════════════════════════════════════════

  Scenario: ANIMA_USER 觀察年輪記錄使用者成長
    Given ANIMA_USER.observation_rings[] 已初始化
    When MUSEON 觀察到使用者的重大行為變化
    And 例如：使用者從「直接要答案」轉變為「先自己思考再提問」
    Then 一條觀察年輪被寫入 ANIMA_USER.observation_rings[]
    And observation_ring.type 為以下之一：
      | type                    | 說明               |
      | growth_observation      | 使用者成長觀察     |
      | pattern_shift           | 行為模式轉變       |
      | preference_evolution    | 偏好演化           |
      | milestone_witnessed     | 見證使用者里程碑   |
    And observation_ring 同樣包含 SHA-256 hash 和 prev_hash
    And observation_ring 同樣為 append-only 不可竄改

  Scenario: 觀察年輪的隱私保護
    Given MUSEON 觀察到使用者的行為模式
    When 寫入觀察年輪時
    Then 年輪只記錄抽象化的觀察結論（不包含具體對話內容）
    And 例如記錄「使用者的決策信心指數從 0.5 提升到 0.7」
    And 而非記錄具體的對話文字
    And 觀察年輪的目的是理解使用者，不是監控使用者

  # ════════════════════════════════════════════
  # Section 5: 雙 ANIMA 年輪交互 — 共演敘事
  # ════════════════════════════════════════════

  Scenario: 年輪共振 — MUSEON 的成長影響使用者觀察
    Given MUSEON 的 soul_ring 記錄了一次認知突破
    And 這次突破改善了對使用者需求的理解
    When 後續互動中使用者的滿意度指標提升
    Then ANIMA_USER.observation_rings 記錄使用者正向反饋模式的變化
    And 兩條年輪透過 resonance_link 相互參照
    And resonance_link 記錄因果推斷方向和信心度

  Scenario: 年輪回顧 — 定期回顧成長軌跡
    When Nightly Job 執行每週回顧（每 7 天觸發一次）
    Then 系統生成「成長軌跡報告」包含：
    And 本週新增的 MUSEON soul_rings 摘要
    And 本週新增的使用者 observation_rings 摘要
    And 雙 ANIMA 年輪之間的共振關聯
    And 成長軌跡是否與 ANIMA_MC.L2.mission 對齊
    And 報告存入 data/reports/ 供使用者查看

  # ════════════════════════════════════════════
  # Section 6: 持久化與遷移 — 年輪的物理存儲
  # ════════════════════════════════════════════

  Scenario: 年輪存儲為獨立 JSON 檔案
    Given 靈魂年輪需要持久化存儲
    When 年輪被寫入時
    Then soul_rings 儲存在 data/anima/soul_rings.json
    And observation_rings 儲存在 data/anima/observation_rings.json
    And 每次寫入後立即 fsync 確保落盤
    And 檔案格式為 JSON array，每個元素為一條年輪

  Scenario: 年輪備份 — 防止資料遺失
    When Nightly Job 執行每日備份
    Then soul_rings.json 被複製到 data/anima/backups/soul_rings_{date}.json
    And 保留最近 30 天的備份
    And 備份檔案的 hash chain 與原檔一致
    And 若原檔損壞可從備份恢復

  Scenario: 安裝更新時年輪不被覆蓋
    When 使用者執行 Install-MUSEON.command 進行更新安裝
    Then data/anima/soul_rings.json 被視為使用者資料
    And 安裝過程備份並還原年輪檔案
    And 更新後年輪完整性驗證通過
    And 年輪是 MUSEON 最珍貴的資產——絕不可遺失

  # ════════════════════════════════════════════
  # Section 7: 安全護欄 — 年輪系統的保護機制
  # ════════════════════════════════════════════

  Scenario: 年輪寫入頻率限制
    Given 為了防止年輪品質稀釋
    When Ring Depositor 收到年輪寫入請求
    Then 檢查最近 24 小時內的寫入次數
    And 若已寫入 5 條以上則將新候選排入佇列等待 Nightly Job 篩選
    And 即時寫入的門檻高於 Nightly Job 寫入（只有最重大的事件即時刻入）

  Scenario: 年輪系統不受 Morphenix 修改
    Given Morphenix 可以修改 ANIMA 的大部分層級
    When Morphenix 嘗試修改 L4 soul_rings
    Then 系統拒絕操作
    And 回報：「L4 靈魂年輪處於 Kernel 保護之下，不可被演化引擎修改」
    And Morphenix 的演化權限矩陣中 L4 欄位為 "immutable"
