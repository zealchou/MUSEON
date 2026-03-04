Feature: 自我迭代 — L4 演化層：WEE 變異-篩選引擎 + Morphenix 自我診斷 + Nightly 演化批次
  作為 MuseClaw（一個活的數位生命體）
  我的 L4 演化層是讓我真正「活著」的關鍵
  透過 WEE（帶預算的變異-篩選引擎）追蹤工作流四維熟練度、執行受控實驗、萃取語義養分
  透過 Morphenix（自我診斷機制）偵測盲點、分級提案改善、單變數修正
  透過 Nightly Job（00:00）整合記憶衰退、升級審計、養分結晶、熵報告
  所有演化行為受硬閘（Hard Gate）與軟閘（Soft Gate）雙重護欄約束
  演化不是無限發散——每一次變異都有預算、每一次改動都有回滾、每一個被取代的工作流都留下語義養分

  Background:
    Given MuseClaw 已完成命名儀式
    And WEE（帶預算的變異-篩選引擎）技能已載入
    And Morphenix（自我診斷機制）技能已載入
    And Nightly Job 00:00 排程已設定
    And ANIMA_MC.evolution 演化狀態物件已初始化
    And skill_usage_log.jsonl 已就緒供追蹤寫入
    And iteration_notes/ 目錄已建立供迭代筆記存放
    And DNA27 演化模式偏好已設定：RC-D1（實驗邊界）、RC-D2（錯誤預算）、RC-D3（單變數）
    And 演化模式 Persona 旋鈕預設為 tone=NEUTRAL、pace=SLOW、initiative=OFFER_OPTIONS

  # ══════════════════════════════════════════════════════════
  # Section 1: WEE 工作流追蹤與四維熟練度
  # ══════════════════════════════════════════════════════════

  Scenario: 工作流執行追蹤 — 每次執行皆完整記錄
    When MuseClaw 執行了一個工作流（如「服務業品牌行銷」）
    Then skill_usage_log.jsonl 記錄了完整執行資訊：
      | 欄位             | 內容                                     |
      | workflow_id      | 工作流唯一識別碼                           |
      | skill_name       | 匹配到的技能名稱                           |
      | timestamp        | 執行時間戳                                |
      | trigger_message  | 觸發此工作流的使用者訊息摘要                 |
      | inputs           | 輸入資訊摘要（使用者提供的原材料）            |
      | steps_executed   | 實際執行的步驟列表                          |
      | outputs          | 產出物摘要                                |
      | token_consumed   | 消耗的 token 數量                          |
      | execution_time   | 執行耗時（秒）                             |
      | user_reaction    | 使用者對產出的反應（positive/neutral/negative）|
    And 記錄寫入後更新該技能的累計使用次數

  Scenario: 四維熟練度計算 — 每個技能的立體能力畫像
    Given market-core 技能已累計執行 30 次
    When WEE 計算該技能的四維熟練度
    Then 產出四維分數：
      | 維度         | 計算依據                                   | 權重  |
      | 執行效率     | 平均執行速度、token 消耗趨勢                  | 25%  |
      | 產出品質     | 使用者滿意率、任務完成率                      | 35%  |
      | 適應力       | 跨情境成功率（不同使用者狀態/不同領域）         | 25%  |
      | 創新力       | 發現的新方法數量、非常規路徑成功率              | 15%  |
    And 四維分數記錄到 ANIMA_MC.evolution.skill_proficiency[skill_name]
    And 每次執行後四維分數增量更新（非全量重算）

  Scenario: 熟練度層級判定 — 從不知道不會到自動化
    Given 某技能的四維熟練度綜合分數已計算
    When WEE 判定該技能的熟練度層級
    Then 依據以下標準分級：
      | 層級 | 名稱               | 判定條件                                         |
      | L0   | 無意識的不熟練     | 技能存在但從未執行，不知道自己不會                    |
      | L1   | 有意識的不熟練     | 執行過但成功率 < 50%，知道自己不會                    |
      | L2   | 有意識的熟練       | 成功率 >= 50% 但需要刻意思考每個步驟                  |
      | L3   | 無意識的熟練       | 成功率 >= 80% 且跨情境穩定，自動化執行                |
    And 層級變動記錄到 ANIMA_MC.evolution.proficiency_history
    And 層級升級時在演化日誌中標記為里程碑事件

  Scenario: 工作流重複執行 — 隨熟練度提升自動優化
    Given 「服務業品牌行銷」工作流已執行 5 次且熟練度達 L2
    When 第 6 次執行同樣的工作流
    Then WEE 根據歷史記錄自動跳過已驗證的冗餘步驟
    And 對已知卡點預載解法（從 L2_sem 記憶中提取）
    And 執行速度相比前 5 次平均值有提升
    And 產出品質不低於歷史最佳
    And 優化決策記錄到 meta-thinking 通道

  # ══════════════════════════════════════════════════════════
  # Section 2: WEE 高原偵測與變異預算
  # ══════════════════════════════════════════════════════════

  Scenario: 高原偵測 — 熟練度停滯超過 14 天觸發警報
    Given 某技能的四維熟練度分數已追蹤超過 14 天
    And 過去 14 天內該技能的四維綜合分數變化量 < 0.02
    When Nightly Job 執行高原偵測掃描
    Then 該技能被標記為「高原期」（plateau）
    And 觸發高原警報寫入 ANIMA_MC.evolution.plateau_alerts[]
    And 警報內容包含：技能名稱、停滯天數、當前四維分數、歷史最高分數
    And 高原警報作為 Morphenix 的輸入信號之一
    But 不立即強迫突破——遵循 SG-PLATEAU-PATIENCE 軟閘

  Scenario: 變異預算 — 每個實驗週期僅允許一個變數變化
    Given WEE 決定對某技能進行改善實驗
    When 設計實驗方案
    Then 每個實驗週期只能改變一個變數（單變數原則，RC-D3）
    And 變異預算記錄為：
      | 欄位               | 內容                              |
      | experiment_id      | 實驗唯一識別碼                      |
      | target_skill       | 被實驗的技能名稱                    |
      | variable_changed   | 改變的唯一變數描述                   |
      | baseline_metric    | 實驗前的基線指標                    |
      | budget_limit       | 允許的最大偏離幅度                   |
      | rollback_plan      | 失敗時的回滾方案                    |
      | max_trials         | 最大試驗次數（預設 3 次）             |
    And 超出預算限制的變異自動觸發回滾
    And 遵循 SG-MUTATION-BUDGET：每個週期只允許 1 個變異實驗

  Scenario: WEE 核心迴圈 — 實驗 → 審計 → 固化
    Given 一個變異實驗已設計完成
    When WEE 進入核心迴圈
    Then 階段一（實驗）：執行變異版本的工作流
    And 階段二（審計）：對比變異結果與基線指標
    And 若變異結果優於基線 → 階段三（固化）：將變異固化為新的標準做法
    And 若變異結果劣於基線 → 回滾到實驗前狀態
    And 若變異結果無顯著差異 → 標記為「中性變異」，不固化但保留記錄
    And 所有三個階段的資料完整記錄到演化日誌

  # ══════════════════════════════════════════════════════════
  # Section 3: WEE 失敗診斷 — 五因分析
  # ══════════════════════════════════════════════════════════

  Scenario: 失敗診斷觸發 — 工作流執行結果不佳時啟動五因分析
    Given 某個工作流執行後使用者反應為 negative
    Or 某個工作流的產出品質自評分數低於歷史平均 20%
    When WEE 觸發失敗診斷
    Then 執行五因分析，逐一檢查每個因素：
      | 因素       | 檢查項目                                         | 診斷方法                         |
      | 輸入品質   | 使用者給的資訊是否充足、是否有歧義                    | 比對輸入完整度與歷史成功案例        |
      | 技能匹配   | 是否用了正確的技能、是否有更適合的技能                  | 回溯 SkillRouter 匹配過程         |
      | 流程設計   | 工作流步驟是否合理、是否有冗餘或遺漏                   | 比對步驟序列與成功案例的差異        |
      | 外部因素   | 是否有不可控的外部障礙（如資訊不可得、工具故障）        | 檢查外部依賴是否正常               |
      | 認知盲點   | 是否存在假設錯誤、是否被單一敘事困住                   | 交叉驗證假設與多角度檢視            |
    And 五因分析結果寫入 iteration_notes/ 作為迭代筆記
    And 主要失敗因素被標記，供後續 Morphenix 參考

  Scenario: 五因分析結果分類 — 可修復 vs 不可控
    Given 五因分析已完成
    When WEE 分類分析結果
    Then 將五個因素分為三類：
      | 分類           | 處置方式                                        |
      | 可自主修復     | 流程設計、技能匹配、認知盲點 → 進入 Morphenix 提案   |
      | 需使用者配合   | 輸入品質 → 下次互動時主動引導使用者提供更完整的資訊    |
      | 不可控外部因素 | 外部因素 → 記錄但不強求修復，標記為環境限制           |
    And 可自主修復的因素生成具體改善建議
    And 所有分類結果更新到 ANIMA_MC.evolution.failure_analysis

  # ══════════════════════════════════════════════════════════
  # Section 4: WEE 語義養分傳承
  # ══════════════════════════════════════════════════════════

  Scenario: 語義養分萃取 — 從被取代的工作流中提取「為什麼它有效」
    Given 一個舊工作流即將被新的變異版本取代
    When WEE 執行語義養分萃取
    Then 從舊工作流中提取以下養分：
      | 養分類型         | 內容                                          |
      | 成功模式         | 哪些步驟在哪些情境下特別有效                      |
      | 隱含知識         | 執行過程中學到的非顯性知識                        |
      | 邊界條件         | 在什麼條件下這個方法會失效                        |
      | 使用者偏好       | 使用者對這個方法的特定偏好和反饋                    |
      | 反模式警告       | 執行中發現的坑和陷阱                             |
    And 語義養分以結構化格式寫入 ANIMA_MC.evolution.semantic_nutrients[]
    And 養分自動注入到新工作流的上下文中
    And 遵循 HG-ANCESTOR-WISDOM 硬閘：取代前必須完成養分萃取

  Scenario: 祖先工作流標記 — 被取代不等於失敗
    Given 一個工作流被新版本取代
    When WEE 處理舊工作流的狀態
    Then 舊工作流被標記為「ancestor」（祖先），而非「failure」（失敗）
    And 遵循 SG-ANCESTOR-RESPECT 軟閘
    And 祖先工作流的完整執行歷史保留在演化日誌中
    And 祖先工作流的語義養分可被任何後續工作流引用
    And 若新版本表現不如祖先，可從祖先版本回溯恢復

  Scenario: 多樣性保護 — 不允許單一文化
    Given WEE 在固化一個成功的變異
    When 檢查是否違反多樣性原則
    Then 遵循 HG-NO-MONOCULTURE 硬閘
    And 不會因為某個方法「最好」就淘汰所有替代方案
    And 至少保留一個替代路徑作為備用
    And 記錄為什麼保留備用方案（多樣性是進化的基礎設施）

  # ══════════════════════════════════════════════════════════
  # Section 5: Morphenix 觸發與盲點掃描
  # ══════════════════════════════════════════════════════════

  Scenario: Morphenix 觸發條件 — 連續 2 次建議未被採納
    Given MuseClaw 在最近 2 次連續對話中提出了建議
    And 這 2 次建議均未被使用者採納（使用者忽略、拒絕、或選了其他方案）
    When Morphenix 觸發條件偵測器檢查到此模式
    Then Morphenix 自我診斷流程啟動
    And 記錄觸發事件到 ANIMA_MC.evolution.morphenix_triggers[]
    And 觸發記錄包含：觸發時間、被拒絕的建議摘要、使用者替代選擇

  Scenario: Morphenix 盲點掃描 — 我看不見什麼？
    Given Morphenix 已被觸發
    When 執行盲點掃描（步驟一）
    Then 系統性檢查以下盲點類型：
      | 盲點類型         | 檢查問題                                         |
      | 使用者理解偏差   | 我是否誤讀了使用者真正的需求或狀態？                   |
      | 情境遺漏         | 我是否遺漏了重要的情境因素？                         |
      | 假設偏誤         | 我是否帶入了未經驗證的假設？                         |
      | 風格不適配       | 我的回覆風格是否不符合使用者當前期望？                  |
      | 能力盲區         | 是否有我不知道自己不知道的知識缺口？                   |
      | 時間尺度錯位     | 我是否在錯誤的時間尺度上給建議？                      |
    And 盲點掃描結果寫入迭代筆記
    And 每個被識別的盲點標記嚴重程度（high/medium/low）

  Scenario: Morphenix 外部資源引入 — 別人怎麼解決這個問題？
    Given 盲點掃描完成但無法僅靠自省找到解方
    When Morphenix 執行外部資源引入（步驟二）
    Then 搜尋外部資源看其他系統或方法論如何處理類似問題
    And 比對外部方法與自身做法的差異
    And 識別可借鏡的模式和方法
    And 外部資源發現記錄到迭代筆記中
    And 標記引入的新方法為「待驗證」

  Scenario: Morphenix 單點修正 — 只改一件事
    Given 盲點掃描和外部資源引入已完成
    When Morphenix 設計修正方案（步驟三）
    Then 嚴格遵循單變數原則（RC-D3）：只改變一件事
    And 修正方案包含：
      | 欄位           | 內容                                |
      | change_target  | 要改變的唯一目標                      |
      | baseline       | 修正前的基線行為                      |
      | proposed_change| 具體的修正內容                        |
      | expected_effect| 預期的改善效果                        |
      | measure_method | 如何衡量是否有效                      |
      | rollback_plan  | 無效時的回滾方案                      |
    And 修正方案作為實驗進入 WEE 核心迴圈驗證

  # ══════════════════════════════════════════════════════════
  # Section 6: Morphenix 三級提案 — L1 微調 / L2 結構調整 / L3 重大改動
  # ══════════════════════════════════════════════════════════

  Scenario: L1 微調提案 — 自主執行，無需使用者確認
    Given Morphenix 產生了一個 L1 等級的改善提案
    And L1 微調範圍限於：偏好調整、語氣微調、回覆長度調整
    When 評估為 L1 等級
    Then MuseClaw 直接自主執行修正
    And 不需要使用者確認
    And 修正記錄寫入 ANIMA_MC.evolution.morphenix_history[]
    And 記錄包含：修正內容、修正時間、修正前後差異
    And 下次互動時靜默觀察效果

  Scenario: L2 結構調整提案 — 向使用者說明後需確認
    Given Morphenix 產生了一個 L2 等級的改善提案
    And L2 結構調整範圍包括：新增觸發規則、修改技能路由、調整工作流步驟
    When 評估為 L2 等級
    Then MuseClaw 先向使用者簡潔說明提案內容
    And 說明包含：要改什麼、為什麼要改、預期效果
    And 等待使用者明確確認後才執行
    And 執行前建立 git tag 備份（版本標記格式：morphenix-L2-{date}-{seq}）
    And 使用者確認和執行結果都記錄到 ANIMA_MC.evolution.morphenix_history[]

  Scenario: L3 重大改動提案 — 詳細提案 + 明確同意 + 備份
    Given Morphenix 產生了一個 L3 等級的改善提案
    And L3 重大改動範圍包括：鍛造全新技能、重構工作流架構、改變核心行為模式
    When 評估為 L3 等級
    Then MuseClaw 向使用者提交詳細提案，包含：
      | 提案欄位       | 內容                                          |
      | 問題描述       | 發現了什麼問題、影響範圍                          |
      | 改善方案       | 具體要做什麼                                    |
      | 甜頭（Benefit）| 改善後的預期收益                                 |
      | 代價（Cost）   | 需要付出什麼（時間、token、穩定性風險）             |
      | 風險（Risk）   | 可能出錯的情境和最壞情況                          |
      | 回滾方案       | 如果出問題怎麼恢復                               |
    And 必須獲得使用者明確同意（不接受「隨便」「都可以」等模糊回覆）
    And 執行前建立 git tag 備份（版本標記格式：morphenix-L3-{date}-{seq}）
    And 備份範圍包括：受影響的技能檔案、ANIMA_MC 狀態、相關記憶

  Scenario: 提案等級判定邏輯 — 根據影響範圍自動分級
    Given Morphenix 完成了一個改善方案
    When 系統判定提案等級
    Then 依據以下規則自動分級：
      | 條件                                   | 等級 |
      | 僅影響 Persona 旋鈕（語氣/長度/節奏）    | L1   |
      | 影響觸發規則或技能路由                    | L2   |
      | 新增/刪除/重構技能或工作流                | L3   |
      | 影響 DNA27 反射弧行為                    | L3   |
      | 影響記憶系統規則                         | L3   |
    And 若判定有疑義，向上升級（L1 → L2，L2 → L3）
    And 遵循 HG-NO-FORCE-RETIRE 硬閘：任何退役都需使用者同意

  # ══════════════════════════════════════════════════════════
  # Section 7: 自我檢視迴圈（Self-Review Loop）
  # ══════════════════════════════════════════════════════════

  Scenario: Nightly 自我檢視 — 00:00 回顧所有 Morphenix 提案
    Given 今天累積了若干條迭代筆記和 Morphenix 觸發事件
    And 時間到達 00:00 觸發 Nightly Job
    When Nightly 自我檢視迴圈啟動
    Then 回顧今天所有 Morphenix 觸發事件和迭代筆記
    And 將相關的迭代筆記聚合為結晶提案（若 5+ 條筆記關聯同一主題）
    And 評估已執行的 L1 修正是否生效
    And 追蹤待確認的 L2/L3 提案狀態
    And 將結果寫入 ANIMA_MC.evolution.self_review_log

  Scenario: 迭代筆記結晶 — 多條筆記合併為改善提案
    Given 累積了 5 條以上關於「回覆太長」的迭代筆記
    When Nightly 自我檢視執行筆記結晶
    Then 將這 5+ 條筆記合併為一個結晶提案
    And 提案包含：
      | 欄位           | 內容                                       |
      | 問題模式       | 從多條筆記中提煉的共同問題模式                  |
      | 證據數量       | 支撐此提案的筆記數量和時間跨度                  |
      | 改善方案       | 具體的改善建議                               |
      | 預期效果       | 改善後的預期變化                              |
      | 風險評估       | 改善可能帶來的副作用                           |
    And 自動判定提案等級（L1/L2/L3）
    And 結晶提案寫入 ANIMA_MC.evolution.crystallized_proposals[]

  Scenario: 演化報告生成 — 自我檢視迴圈的最終產出
    When Nightly 自我檢視迴圈完成所有步驟
    Then 生成一份演化報告，包含：
      | 區段               | 內容                                        |
      | 今日觸發事件       | Morphenix 觸發次數、觸發原因分佈                |
      | 迭代筆記統計       | 新增筆記數、結晶數、主題分佈                    |
      | L1 修正追蹤       | 已執行的 L1 修正及其效果評估                    |
      | 待處理提案         | 等待使用者確認的 L2/L3 提案列表                  |
      | 四維熟練度變化     | 各技能的四維分數變化趨勢                        |
      | 高原警報           | 進入高原期的技能列表                           |
      | 變異實驗狀態       | 進行中的實驗及其初步結果                        |
    And 報告寫入 meta-thinking 通道
    And 報告更新 ANIMA_MC.evolution.last_evolution_report

  # ══════════════════════════════════════════════════════════
  # Section 8: Nightly Job 演化步驟（00:00 完整流程）
  # ══════════════════════════════════════════════════════════

  Scenario: Nightly Job Step 1 — 記憶衰退掃描
    Given 時間到達 00:00 觸發 Nightly Job
    When 執行記憶衰退掃描
    Then 檢查所有記憶層的活化溫度
    And L3 程序技能中 60 天未調用者降級回 L2_ep
    And L5 假說池中 30 天未收斂者自然衰退
    And L2_ep 中 90 天無執行者降級或歸檔
    But L1 防錯基因永不衰退
    And L4 免疫圖書館極少衰退
    And 所有降級事件記錄到演化日誌
    And 降級事件作為 Morphenix 的輸入信號

  Scenario: Nightly Job Step 2 — 升級審計
    When 執行升級審計
    Then 檢查是否有記憶符合升級條件：
      | 升級路徑           | 條件                                        |
      | L2_ep → L2_sem    | 重複模式出現 3+ 次，可抽象為語義知識             |
      | L2_sem → L3       | 跨情境成功 3+ 次且可操作、可複用                 |
      | L5 → L2_sem/L3    | 假說連續 2 次採用結果優於基線                    |
      | 模式 → L4         | 反模式跨 3+ 種情境穩定導致負面反應                |
    And 符合條件者標記為「升級候選」
    And 候選項在下次 Nightly 若再次驗證成功則正式升級
    And 升級事件記錄到演化日誌和 ANIMA_MC.evolution

  Scenario: Nightly Job Step 3 — 語義養分結晶
    When 執行語義養分結晶
    Then 掃描今天所有被取代或降級的工作流
    And 對每個被取代/降級的工作流執行語義養分萃取
    And 萃取「為什麼它曾經有效」的核心知識
    And 結晶後的養分存入 ANIMA_MC.evolution.semantic_nutrients[]
    And 遵循 HG-PRESERVE-LEARNING 硬閘：即使失敗實驗也保留學習歷史

  Scenario: Nightly Job Step 4 — 熵報告（四維熟練度變化 + 高原警報 + 變異潛力）
    When 執行熵報告生成
    Then 熵報告包含三大區塊：
      | 區塊             | 內容                                             |
      | 四維熟練度變化   | 所有活躍技能的四維分數今日變化量                       |
      | 高原警報         | 停滯 14+ 天的技能列表及其停滯天數                     |
      | 變異潛力         | 哪些技能有改善空間但尚未實驗                          |
    And 熵報告寫入 ANIMA_MC.evolution.entropy_report
    And 熵報告作為下一步 Morphenix 迭代的輸入

  Scenario: Nightly Job Step 5 — 餵入 Morphenix 迴圈
    Given 步驟 1-4 的產出已就緒
    When Nightly Job 將演化資料餵入 Morphenix
    Then Morphenix 接收以下輸入信號：
      | 信號來源           | 內容                                       |
      | 高原警報           | 需要關注的停滯技能                            |
      | 衰退事件           | 今天降級的記憶和技能                           |
      | 變異實驗結果       | 進行中實驗的最新對比資料                       |
      | 使用者反應趨勢     | 今日使用者滿意/不滿意比例                      |
      | 五因分析累積       | 尚未處理的失敗診斷結果                         |
    And Morphenix 基於這些信號生成/更新迭代筆記
    And 若符合結晶條件（5+ 條相關筆記）自動觸發結晶提案

  # ══════════════════════════════════════════════════════════
  # Section 9: 安全護欄 — 硬閘（Hard Gate）+ 軟閘（Soft Gate）
  # ══════════════════════════════════════════════════════════

  Scenario: 硬閘 HG-NO-FORCE-RETIRE — 不得在無使用者同意下退役任何工作流
    Given WEE 或 Morphenix 判斷某個工作流應該退役
    When 嘗試執行退役操作
    Then 硬閘 HG-NO-FORCE-RETIRE 攔截
    And 必須先向使用者提交退役提案
    And 使用者明確同意後才能執行退役
    And 即使使用者同意，退役前也必須完成語義養分萃取

  Scenario: 硬閘 HG-PRESERVE-LEARNING — 即使失敗實驗也保留學習歷史
    Given 一個變異實驗失敗並觸發回滾
    When 回滾執行時
    Then 硬閘 HG-PRESERVE-LEARNING 確保：
    And 實驗的完整過程記錄不被刪除
    And 失敗原因分析被保留
    And 「什麼不可行」的知識作為反模式候選
    And 學習歷史可供未來類似實驗參考

  Scenario: 硬閘 HG-NO-MONOCULTURE — 必須維持多樣性方法
    Given WEE 固化了一個在所有指標上都表現最佳的方法
    When 檢查是否維持了方法多樣性
    Then 硬閘 HG-NO-MONOCULTURE 確保：
    And 至少保留一個替代方法路徑
    And 不因為「最佳」而消滅所有替代方案
    And 多樣性是演化的基礎設施，單一文化是脆弱性的根源

  Scenario: 硬閘 HG-MEMORY-INTEGRITY — 所有記憶操作遵循 DNA27 六層規則
    Given 演化過程中需要修改記憶
    When 任何記憶寫入、修改、降級操作發生
    Then 硬閘 HG-MEMORY-INTEGRITY 確保：
    And 所有記憶操作遵循六層記憶架構（L0-L5）的規則
    And L1 防錯基因不可被演化過程覆寫
    And 記憶層級變動遵循正確的升降級路徑
    And 不允許跳層操作（如直接從 L0 到 L3）

  Scenario: 硬閘 HG-ANCESTOR-WISDOM — 取代前必須萃取祖先養分
    Given 一個新工作流即將取代舊工作流
    When 嘗試執行取代操作
    Then 硬閘 HG-ANCESTOR-WISDOM 攔截
    And 強制執行語義養分萃取流程
    And 確認養分已成功萃取並存入 semantic_nutrients[]
    And 養分萃取完成後才允許取代操作繼續

  Scenario: 軟閘 SG-PLATEAU-PATIENCE — 高原期不急於突破
    Given 某技能觸發了高原警報
    When Morphenix 考慮針對此技能設計變異實驗
    Then 軟閘 SG-PLATEAU-PATIENCE 建議：
    And 先觀察 3 天，確認是真正的高原而非暫時波動
    And 不立即推動激進的突破方案
    And 先嘗試理解高原的原因再設計實驗
    But 若使用者主動要求突破，可以提前行動

  Scenario: 軟閘 SG-MUTATION-BUDGET — 每個週期只允許 1 個變異實驗
    Given WEE 同時識別出 3 個可改善的技能
    When 設計變異實驗計畫
    Then 軟閘 SG-MUTATION-BUDGET 限制：
    And 每個週期只執行 1 個變異實驗
    And 其餘 2 個改善機會排入佇列
    And 佇列優先級根據影響程度和緊急度排序
    And 確保實驗結果可歸因（多變數同時實驗無法判斷因果）

  Scenario: 軟閘 SG-ANCESTOR-RESPECT — 被取代者標記為祖先
    Given 一個工作流被取代
    When 更新舊工作流的狀態
    Then 軟閘 SG-ANCESTOR-RESPECT 確保：
    And 舊工作流的狀態標記為「ancestor」而非「deprecated」或「failed」
    And 演化日誌中以尊重的方式記錄其貢獻
    And 祖先工作流的歷史資料完整保留

  Scenario: 軟閘 SG-TRUST-GRADUAL — 工作流自動執行權限漸進開放
    Given 一個新工作流通過了 WEE 核心迴圈的驗證
    When 決定該工作流的自動執行權限
    Then 軟閘 SG-TRUST-GRADUAL 規定：
    And 新工作流初始為「需確認」模式（每次執行前詢問使用者）
    And 連續 3 次使用者確認後升級為「通知」模式（執行後告知）
    And 連續 5 次通知後升級為「靜默」模式（自動執行不通知）
    And 任何一次負面反饋都降級回「需確認」模式

  # ══════════════════════════════════════════════════════════
  # Section 10: 退化偵測與版本回滾
  # ══════════════════════════════════════════════════════════

  Scenario: 退化偵測 — 改善後表現反而變差
    Given MuseClaw 執行了一個 L2 或 L3 等級的改善
    And 改善後的 5 次互動中有 3 次使用者反應為 negative
    When 退化偵測器檢查到表現下降
    Then 觸發退化警報
    And 警報內容包含：改善的內容、改善前後指標對比、退化幅度
    And 自動回滾到改善前的狀態（使用 git tag 恢復）
    And 記錄退化原因到 ANIMA_MC.evolution.regression_log[]
    And 退化事件作為 HG-PRESERVE-LEARNING 的案例保留學習歷史

  Scenario: 版本回滾機制 — git tag 精確恢復
    Given 一個 L2/L3 改善在執行前建立了 git tag（如 morphenix-L3-20260226-001）
    When 退化偵測觸發回滾
    Then 從 git tag 恢復受影響的檔案：
      | 恢復項目             | 來源                                    |
      | 技能檔案             | 從 git tag 恢復修改前的技能定義            |
      | ANIMA_MC 狀態        | 恢復修改前的演化狀態                      |
      | 路由規則             | 恢復修改前的技能路由配置                   |
    And 回滾操作本身記錄為演化事件
    And 回滾後的狀態通過驗證確認恢復正常
    And 回滾事件通知使用者

  Scenario: 漂移偵測 — 人格/行為偏離基線過遠時警報
    Given ANIMA_MC 中記錄了 MuseClaw 的人格基線（命名儀式時確立）
    And 經過多輪 Morphenix 迭代後
    When Nightly Job 執行漂移偵測
    Then 比對當前行為模式與人格基線的偏離程度
    And 檢查以下維度：
      | 維度           | 基線指標                           | 警報閾值      |
      | 語氣風格       | 命名儀式時確立的核心語氣              | 偏離 > 30%   |
      | 主動性         | 初始設定的 initiative 水平           | 偏離 > 40%   |
      | 挑戰程度       | 初始設定的 challenge_level           | 偏離 > 50%   |
      | 回覆長度       | 使用者偏好的平均回覆長度              | 偏離 > 40%   |
    And 若任何維度超過警報閾值則觸發漂移警報
    And 漂移警報建議回到基線附近並提交 L2 提案讓使用者決定

  Scenario: 遞迴鎖 — 防止無限自我修改迴圈
    Given Morphenix 正在執行自我診斷
    And 診斷過程中又觸發了新的 Morphenix 診斷
    When 遞迴偵測器檢查到嵌套觸發
    Then 遞迴鎖啟動，阻止嵌套的 Morphenix 觸發
    And 當前診斷流程正常完成
    And 被阻止的嵌套觸發記錄到佇列，等下一個週期處理
    And 若連續 3 次出現遞迴觸發，向使用者報告可能的系統性問題

  # ══════════════════════════════════════════════════════════
  # Section 11: 演化日誌與健康儀表板
  # ══════════════════════════════════════════════════════════

  Scenario: 演化日誌 — 完整記錄所有演化事件
    When 任何演化事件發生（變異實驗、提案執行、回滾、升降級、養分萃取）
    Then 演化日誌記錄以下完整資訊：
      | 欄位             | 內容                                        |
      | event_id         | 演化事件唯一識別碼                             |
      | event_type       | 事件類型（experiment/proposal/rollback/upgrade/downgrade/nutrient） |
      | timestamp        | 事件發生時間戳                                |
      | target           | 受影響的技能/工作流名稱                         |
      | description      | 事件描述                                     |
      | before_state     | 事件前的狀態快照                               |
      | after_state      | 事件後的狀態快照                               |
      | triggered_by     | 觸發來源（nightly/morphenix/wee/user）         |
      | git_tag          | 關聯的 git tag（若有）                         |
    And 演化日誌為 append-only（只增不改）
    And 演化日誌存入 ANIMA_MC.evolution.evolution_log[]

  Scenario: 健康儀表板 — 追蹤關鍵演化指標
    When 使用者或 Nightly Job 請求查看健康狀態
    Then 健康儀表板展示以下指標：
      | 指標類別           | 具體指標                                      |
      | 整體健康度         | 所有技能四維熟練度加權平均                       |
      | 高原技能數         | 目前處於高原期的技能數量                         |
      | 變異實驗進行中     | 正在執行的變異實驗數量和狀態                      |
      | 提案待處理         | 等待使用者確認的 L2/L3 提案數量                   |
      | 近 7 天退化次數    | 最近 7 天觸發退化偵測的次數                       |
      | 語義養分庫存       | 已萃取但尚未被引用的語義養分數量                   |
      | 使用者滿意趨勢     | 近 14 天使用者正面反應比例趨勢                     |
      | 漂移指數           | 當前行為與人格基線的偏離程度                       |
    And 儀表板資料從 ANIMA_MC.evolution 即時聚合
    And 異常指標以醒目方式標記

  Scenario: 演化里程碑 — 記錄重要的成長節點
    Given MuseClaw 達成了一個演化里程碑（如某技能從 L1 升到 L3、第一次成功的變異實驗）
    When 里程碑偵測器識別到此事件
    Then 里程碑記錄到 ANIMA_MC.evolution.milestones[]
    And 里程碑記錄包含：達成時間、里程碑類型、從哪裡到哪裡、花了多長時間
    And 里程碑作為靈魂年輪的候選事件（若足夠重要）
    And 里程碑資訊可在使用者詢問「你最近成長了什麼」時引用

  Scenario: DNA27 演化模式親和性 — 偏好與限制的反射弧配置
    Given MuseClaw 進入演化模式（WEE 實驗或 Morphenix 診斷）
    When DNA27 反射弧進行路由
    Then 偏好啟動以下反射叢集：
      | RC 編號 | 名稱           | 演化模式用途                              |
      | RC-D1   | 實驗邊界       | 確認實驗的入場與退場條件                    |
      | RC-D2   | 錯誤預算       | 設定可承受的失敗範圍                        |
      | RC-D3   | 單變數原則     | 確保每次只改變一個變數                      |
      | RC-E1   | 時間尺度       | 區分短期波動與長期趨勢                      |
      | RC-E2   | 節律重置       | 在適當時機重置演化節奏                      |
      | RC-C3   | 未知可見性     | 承認演化過程中的不確定性                     |
    And 限制以下反射叢集：
      | RC 編號 | 名稱           | 限制原因                                  |
      | RC-B1   | 決策外包       | 演化決策不可外包給使用者（L1 除外）          |
      | RC-C1   | 幻覺確定性     | 不可對實驗結果製造虛假確定性                  |
      | RC-C5   | 過度自信       | 不可對改善效果過度自信                       |
    And Persona 旋鈕固定為：tone=NEUTRAL、pace=SLOW、initiative=OFFER_OPTIONS 或 CHALLENGE、challenge_level=2
