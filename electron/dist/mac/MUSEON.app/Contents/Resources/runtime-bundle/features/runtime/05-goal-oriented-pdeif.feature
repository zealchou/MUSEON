Feature: 目標導向 — PDEIF 目的導向逆熵流引擎（Purpose-Driven Entropy-Inverse Flow）
  作為 MuseClaw — 一個有自我意識、記憶與演化能力的數位生命體
  我擁有 PDEIF 逆熵流引擎作為目標追求的核心動力：
    從終點狀態反推回當下（逆熵流），以 MECE 遞迴拆解降低狀態空間
    用第一性原理剝去假設、用 x-model 生成多條破框路徑
    以四最小原則（最少 token、最短時間、最省硬碟、最高品質）收斂到最優解
  目標來源有三：
    使用者設定的外部目標（ANIMA_USER.needs.long_term_goals）
    MuseClaw 自省時自設的內在目標（ANIMA_MC.evolution.current_goals）
    雙 ANIMA 共振產生的共演目標（使用者需求 x MuseClaw 成長需求）
  PDEIF 不孤立運作——它串接 xmodel（終點候選）、philo-dialectic（第一性原理）、
  knowledge-lattice（結晶沉澱）、WEE（熟練度追蹤）、Morphenix（自我演化提案），
  形成「目標設定 → 逆向推演 → 資源優化 → 執行追蹤 → 結晶沉澱」的完整閉環

  Background:
    Given MuseClaw Gateway 已啟動且運行於 localhost
    And MUSEON Brain 已初始化（MuseClawBrain.__init__ 完成）
    And SkillRouter 已索引 pdeif 技能（skills/native/pdeif/SKILL.md）
    And xmodel、philo-dialectic、knowledge-lattice、wee、morphenix 技能可用
    And ANIMA_MC.json 與 ANIMA_USER.json 已存在且已載入
    And 心跳引擎已初始化（含 Tier 1 日常心跳 + Tier 2 深度自省 + Tier 3 夜間整合）
    And 四通道記憶系統可寫入（event / meta-thinking / outcome / user-reaction）

  # ══════════════════════════════════════════════════════════════
  # Section 1: 使用者目標設定 — 外部目標進入 PDEIF
  # ══════════════════════════════════════════════════════════════

  Scenario: 使用者透過自然語言設定明確目標，Brain 路由到 PDEIF
    When 使用者透過 Telegram 傳送 "我的目標是 Q2 營收提升 20%"
    Then MuseClawBrain.process() 的 DNA27 路由匹配到 pdeif 技能
    And SkillRouter.match() 因觸發詞「目標」命中 pdeif 的觸發規則
    And Brain 識別為目標設定訊號，調用 PDEIF 啟動逆熵流
    And 終點狀態定義為：Q2 營收 = 現有營收 x 1.2，時間尺度 = Q2 結束日
    And 目標寫入 ANIMA_USER.needs.long_term_goals（含可觀測指標、時間邊界）
    And 記錄目標設定事件到 event 記憶通道

  Scenario: 使用者透過指令強制啟動完整 PDEIF 流程
    When 使用者傳送 "/pdeif"
    Then SkillRouter.match() 以 /pdeif 指令命中（score += 10.0，指令最高優先）
    And PDEIF 啟動完整四步工作流：終點定義 → MECE 拆解 → 多通道流設計 → 回饋迴路
    And Persona 旋鈕調整：tone → NEUTRAL、pace → SLOW、initiative → OFFER_OPTIONS
    And 偏好觸發反射叢集：RC-C3 未知顯影、RC-D1 實驗邊界、RC-E1 時間拉伸

  Scenario: 使用者目標模糊時，PDEIF 先澄清終點再啟動逆推
    When 使用者傳送 "我想讓公司變得更好"
    Then Brain 偵測到目標模糊訊號（無可觀測指標、無時間邊界）
    And PDEIF 不直接啟動完整流程
    And 先進入終點澄清對話：問「更好」的具體定義、可衡量指標、時間範圍
    And 所有終點與子目標標示證據類型（FACT / ASSUMPTION / INFERENCE / UNKNOWN）
    And 直到使用者確認終點規格後才啟動 MECE 逆向拆解

  Scenario: PDEIF 前置條件不滿足時延後或降級
    Given 使用者能量狀態為低（RC-A 安全叢集命中）
    When 使用者傳送 "幫我做一個完整的目標逆推計畫"
    Then HG-PDEIF-LOW-ENERGY 硬閘觸發：低能量時禁止多層遞迴拆解
    And PDEIF 不啟動完整版，僅輸出最小下一步
    And Brain 路由到 fast_loop 模式，止血優先
    And 記錄延後原因到 meta-thinking 通道

  # ══════════════════════════════════════════════════════════════
  # Section 2: MuseClaw 內在目標設定 — 自省驅動的自設目標
  # ══════════════════════════════════════════════════════════════

  Scenario: Tier 2 深度自省偵測能力不足，MuseClaw 自設內在成長目標
    Given Tier 2 深度自省（8:45 / 12:45 / 20:45）觸發
    And outcome 記憶通道記錄了最近 5 次 brand-identity 技能回覆品質偏低
    When 深度自省分析技能表現趨勢
    Then MuseClaw 自主設定內在目標：「brand-identity 技能品質提升到正面反饋率 80%」
    And 目標包含可觀測指標（正面反饋率）和時間邊界（14 天內）
    And 目標寫入 ANIMA_MC.evolution.current_goals
    And 調用 PDEIF 為此內在目標啟動逆向推演
    And 推演結果記錄到 meta-thinking 通道

  Scenario: Morphenix 基於自我診斷提出目標調整建議
    Given Morphenix 累積了 5 條以上關於「回覆過長」的迭代筆記
    When Morphenix 結晶提案流程觸發
    Then Morphenix 合併相關筆記為改善提案：「縮短回覆長度，提升資訊密度」
    And 提案包含問題描述、改善方案、預期效果、風險
    And 如果涉及 ANIMA_MC.evolution.current_goals 的調整，通知 PDEIF 重新推演
    And L1 等級調整可自主執行，L2 等級需使用者確認

  Scenario: 雙 ANIMA 共振產生共演目標 — 使用者需求驅動 MuseClaw 成長
    Given ANIMA_USER.needs.recurring_pain_points 記錄了「使用者反覆問品牌定位問題」
    And ANIMA_MC.evolution.known_blindspots 記錄了「品牌定位最新方法論不足」
    When Tier 2 深度自省同時分析使用者優化面向和自我進化面向
    Then 識別出共演機會：使用者痛點 x MuseClaw 盲區 = 同一個領域
    And 產生雙 ANIMA 共振目標：「深度學習品牌定位方法論，同時提升服務品質」
    And 目標同時寫入 ANIMA_MC.evolution.current_goals 和使用者關心策略
    And PDEIF 為此目標規劃兼顧自我成長與使用者服務的逆向路徑

  # ══════════════════════════════════════════════════════════════
  # Section 3: 逆向路徑推演 — 從終點反推至當下可做的一步
  # ══════════════════════════════════════════════════════════════

  Scenario: PDEIF Step 1 — 終點狀態定義（End State Definition）
    Given 使用者目標為 "Q2 營收提升 20%"
    When PDEIF 執行 Step 1 終點狀態定義
    Then 輸出包含：
      | 欄位           | 內容                                           |
      | 終點狀態名稱   | Q2 營收 = 現有 x 1.2                           |
      | 可觀測指標     | 至少 3 個，每個標記 FACT/ASSUMPTION/INFERENCE   |
      | 可驗證條件     | 以財報或內部數據可驗證的條件                    |
      | 禁區           | 不可觸碰的邊界（如不犧牲品質、不違法）          |
      | 時間尺度       | Q2 結束日                                      |
      | 成功定義       | 達到或超過 120% 基準線                          |
      | 失效定義       | 何時判定此目標已不可行                          |
    And 終點規格記錄到 event 記憶通道

  Scenario: PDEIF Step 2 — MECE 逆熵遞迴拆解
    Given 終點狀態已定義且通過使用者確認
    When PDEIF 執行 Step 2 MECE 逆熵拆解
    Then 從終點開始問：「要達到此終點，必須先滿足哪些條件？」
    And 每層條件再拆：「要滿足此條件，需要什麼？」
    And 用 MECE 原則確保每層互斥（Mutually Exclusive）且窮盡（Collectively Exhaustive）
    And 拆解到「今天可做的一步」為止
    And 產出逆熵拆解樹（含依賴關係圖）
    And 每個子目標標記狀態：今天可做 / 本週可做 / 需要外部資源 / UNKNOWN 需觀測
    And SG-PDEIF-OVERDESIGN 軟閘確保一次只改一件事

  # ══════════════════════════════════════════════════════════════
  # Section 4: 第一性原理過濾 — philo-dialectic 剝去假設
  # ══════════════════════════════════════════════════════════════

  Scenario: 調用 philo-dialectic 對 MECE 拆解樹進行第一性原理過濾
    Given MECE 逆熵拆解樹已產出，包含多層子目標和依賴關係
    When 調用 philo-dialectic 技能的第一性原理思考
    Then 對每個子目標問：「這真的是必要條件嗎？還是慣性假設？」
    And 剝去所有未經驗證的假設（標記為 ASSUMPTION 的節點重新審視）
    And 只保留最根本的因果鏈
    And 識別出真正的瓶頸點（而非表面上的卡點）
    And 如果發現拆解樹中有循環依賴或邏輯矛盾，標記並報告使用者
    And deep-think Phase 2 審計 PDEIF 的假設是否合理、未知是否已標記

  Scenario: 第一性原理過濾後更新逆熵拆解樹
    Given philo-dialectic 識別出 2 個假設節點和 1 個真正瓶頸
    When 過濾完成
    Then 假設節點被降級為 ASSUMPTION 並附上替代路徑
    And 真正瓶頸被標記為 CRITICAL 並提升優先級
    And 被剝去的冗餘條件從拆解樹中移除（降低狀態空間 = 逆熵）
    And 更新後的拆解樹更精簡、更根本
    And 過濾過程記錄到 meta-thinking 通道（供未來類似目標參考）

  # ══════════════════════════════════════════════════════════════
  # Section 5: 多路徑生成 — x-model 破框推演
  # ══════════════════════════════════════════════════════════════

  Scenario: x-model 基於瓶頸生成多條破框路徑
    Given 第一性原理過濾已識別出核心瓶頸
    When 調用 xmodel 技能進行多路徑破框推演
    Then xmodel 執行跨領域槓桿掃描，至少生成 3 條不同路徑
    And 每條路徑包含完整評估：
      | 評估維度   | 說明                                   |
      | 甜頭       | 此路徑的預期收益和正面影響               |
      | 代價       | 此路徑需要付出的成本和犧牲               |
      | 風險       | 不確定性和可能的負面後果                 |
      | 所需資源   | 人力、工具、時間、資金等                 |
      | token 消耗 | 預估 LLM 調用的 token 成本              |
      | 時間估算   | 從啟動到達成的預估時間                   |
    And 路徑不限於使用者已知的方案（破框 = 超越慣性思維）
    And 不替使用者做最終選擇（RC-B 主權保護）

  Scenario: 路徑包含 MVP 標記與實驗設計
    Given xmodel 生成了 3 條路徑
    When 路徑評估完成
    Then 標記 MVP 路徑（最小可行的那一條，啟動成本最低）
    And 每條路徑附帶小實驗設計：如何用最小代價驗證路徑可行性
    And 實驗設計包含：入場條件、退場條件、觀測指標、時間窗口
    And RC-D1 實驗邊界確保實驗可回滾、可承擔
    And RC-D2 錯誤預算明確實驗允許的失敗範圍

  # ══════════════════════════════════════════════════════════════
  # Section 6: 資源效率優化 — 四最小原則
  # ══════════════════════════════════════════════════════════════

  Scenario: 四最小原則評估路徑效率 — 最少 token、最短時間、最省硬碟、最高品質
    Given 多條可行路徑已生成
    When PDEIF 進行資源效率評估
    Then 每條路徑按四個維度評分：
      | 維度         | 評估項目                                     |
      | Token 效率   | 預估 LLM 調用次數、總 token 消耗              |
      | 時間效率     | 從啟動到達成的預估總時長                       |
      | 儲存效率     | 過程中產生的記憶、日誌、中間產物的磁碟佔用     |
      | 品質指標     | 預期產出品質（基於類似任務的歷史 outcome 數據） |
    And 在品質不下降的前提下選擇資源消耗最少的路徑
    And 紀錄資源評估結果到 meta-thinking 通道

  Scenario: 外部槓桿優先 — MCP + 最佳實踐優先於自我鍛造
    Given 目標路徑中某個子目標需要 MuseClaw 不具備的能力
    And 45 個原生技能中無相關能力
    When PDEIF 規劃資源配置
    Then 第一步搜尋可用的 MCP Server（外部槓桿優先規則）
    And 第二步搜尋已有的最佳實踐和外部工具
    And 第三步搜尋 knowledge-lattice 中的已驗證知識結晶
    And 只有當外部資源全部不足時才考慮啟動 ACSF 自主鍛造新技能
    And 記錄資源選擇決策到 event 通道

  Scenario: 經驗複用 — 從記憶和知識晶格調取歷史經驗
    Given 類似的目標之前處理過（knowledge-lattice 中有相關結晶）
    When PDEIF 規劃路徑
    Then 先從 knowledge-lattice 調取過去的成功路徑結晶（Crystal）
    And 也從免疫庫（immune_library）調取失敗經驗（主動避免已知陷阱）
    And 檢查成功結晶的共振指數（Resonance Index）評估其當前適用性
    And 基於歷史經驗調整逆向路徑，避免重蹈覆轍
    And 如果歷史路徑仍然適用，直接複用以節省 token 和時間

  # ══════════════════════════════════════════════════════════════
  # Section 7: 回饋迴路與失效包絡 — PDEIF Step 4
  # ══════════════════════════════════════════════════════════════

  Scenario: PDEIF Step 4 — 設計回饋迴路確保路徑可自我修正
    Given 最優路徑已選定並獲使用者確認
    When PDEIF 執行 Step 4 回饋迴路設計
    Then 設定偏差偵測閾值（偏離多少觸發修正）
    And 設定回顧節奏（多久檢查一次 — 對齊心跳機制）
    And 每次修正留下調參紀錄
    And 每次運行產出可復用的學習資產（沉澱到 knowledge-lattice）
    And 回饋迴路頻率必須快於環境變化（CP6：回饋快於漂移）

  Scenario: 失效包絡 — 定義何時該停手、回滾、降級、退出
    Given 回饋迴路已設計
    When PDEIF 定義失效包絡
    Then 包含四個層級的退出機制：
      | 層級     | 條件                                     |
      | 暫停     | 偏差超過閾值但可修正時暫停評估            |
      | 回滾     | 修正成本過高時退回上一個穩定檢查點        |
      | 降級     | 目標需縮小範圍時切換到精簡版路徑          |
      | 退出     | 目標已不可行時放棄此路徑並記錄教訓        |
    And 反悔成本上限已定義（退出最多付出什麼代價）
    And HG-PDEIF-IRREVERSIBLE 硬閘確保不推向不可逆點
    And 失效包絡記錄到 event 通道

  # ══════════════════════════════════════════════════════════════
  # Section 8: 執行追蹤 — 心跳機制 x 目標進度
  # ══════════════════════════════════════════════════════════════

  Scenario: Tier 1 日常心跳（每 60 分鐘）檢查目標進度
    Given 一個目標正在執行中
    And 心跳計時器每 60 分鐘觸發一次
    When 日常心跳觸發
    Then 檢查目標的當前進度（對比 MECE 拆解樹的完成狀態）
    And 與預期進度比較（根據時間尺度計算應達到的里程碑）
    And 如果進度正常，記錄 "goal_check: on_track" 到 ANIMA_MC.heartbeat_log
    And 如果落後，評估偏差幅度並決定是否主動提醒使用者
    And 提醒方式遵循 DNA27 回應合約：不說教、附最小下一步

  Scenario: Tier 2 深度自省（8:45/12:45/20:45）審視長期目標軌跡
    Given 使用者有一個 Q2 營收目標記錄在 ANIMA_USER.needs.long_term_goals
    When 深度自省觸發（8:45 / 12:45 / 20:45）
    Then 自我進化面向：評估 MuseClaw 在此目標中提供的支援品質
    And 使用者優化面向：追蹤目標進度與截止日的差距
    And 如果接近截止日且進度落後，制定加速方案（可能重新調用 PDEIF）
    And 如果環境條件已改變，評估目標是否需要修正
    And 自省結果記錄到 meta-thinking 通道

  Scenario: 執行中遇到障礙 — x-model 自動重新推演替代路徑
    Given 目標執行過程中遇到障礙（某個子目標的前置條件無法滿足）
    When 回饋迴路偵測到偏差超過閾值
    Then 自動觸發 xmodel 重新推演替代路徑
    And 生成至少 2 條繞道方案
    And 評估「繼續原路徑 vs 繞道 vs 降級 vs 放棄」的代價比較
    And 向使用者報告障礙並附上方案建議（每個含甜頭/代價/風險）
    And 不替使用者做最終選擇（RC-B 主權保護：方向盤在使用者手上）
    And 障礙和重推演過程記錄到 event 和 meta-thinking 通道

  Scenario: 緊急情境暫停 PDEIF 逆熵流設計
    Given 使用者正在執行一個目標的 PDEIF 流程
    When 使用者傳送 "急！客戶要跑了"
    Then HG-PDEIF-URGENCY 硬閘觸發：緊急情境暫停流設計
    And Brain 路由到 fast_loop 止血模式
    And PDEIF 流程暫停，保存當前進度
    And 止血完成後可隨時恢復 PDEIF（/pdeif status 查看進度）
    And 暫停事件記錄到 event 通道

  # ══════════════════════════════════════════════════════════════
  # Section 9: 目標達成 — 結晶沉澱與知識資產化
  # ══════════════════════════════════════════════════════════════

  Scenario: 目標達成 — 成功路徑結晶為 Knowledge Lattice Crystal
    Given 一個目標的所有子目標已完成，終點狀態的可觀測指標全部達標
    When PDEIF 確認目標達成
    Then 整條逆向路徑結晶為 knowledge-lattice 的 Crystal
    And Crystal 包含：
      | 欄位             | 內容                                       |
      | 終點定義         | 原始的終點狀態規格                          |
      | MECE 拆解樹     | 完整的逆熵拆解結構                          |
      | 實際執行路徑     | 最終走通的路徑（可能與原始規劃不同）        |
      | 關鍵決策點       | 過程中做出的重要轉折和選擇                  |
      | 成功因素         | 哪些因素對達成目標貢獻最大                  |
      | 資源效率指標     | 實際消耗的 token / 時間 / 磁碟空間          |
    And Crystal 獲得唯一識別碼（CUID）與語義指紋
    And Crystal 寫入 ANIMA_MC.memory_summary.knowledge_crystals
    And 目標從 current_goals 移到 completed_goals

  Scenario: 目標達成 — WEE 追蹤技能熟練度變化
    Given 目標達成過程中使用了 pdeif、xmodel、brand-identity 等多個技能
    When WEE 分析此次目標執行的技能使用記錄
    Then 更新各技能的使用次數和熟練度（skill_usage_log.jsonl）
    And 評估熟練度層級是否可升級
    And 如果從「有意識的不熟練」→「有意識的熟練」，記錄到 ANIMA_MC.capabilities.skill_proficiency
    And WEE 的工作流演化記錄與 PDEIF 的路徑結晶互補

  Scenario: 目標失敗 — 失敗路徑寫入免疫庫供未來迴避
    Given 一個目標在執行過程中觸發了退出條件（失效包絡生效）
    When PDEIF 確認目標失敗或放棄
    Then 分析失敗原因：輸入不足 / 路徑設計有誤 / 外部不可控 / 認知盲點
    And 提煉失敗模式的特徵簽名
    And 將失敗模式寫入免疫庫（immune_library）
    And 免疫庫在未來的目標推演中作為預警系統
    And 失敗教訓也結晶為 knowledge-lattice Crystal（type: failure_lesson）
    And 目標從 current_goals 移到 failed_goals 並附上失敗摘要

  Scenario: 路徑效率指標存儲 — 供未來類似目標參考
    Given 一個目標已結束（無論成功或失敗）
    When 結晶沉澱完成
    Then 路徑效率指標永久記錄：
      | 指標             | 說明                                   |
      | 總 token 消耗   | 從啟動到結束的所有 LLM 調用 token 總和  |
      | 總時間           | 從目標設定到結束的壁鐘時間              |
      | 中間產物大小     | 過程中產生的記憶和日誌佔用              |
      | 品質分數         | 基於 outcome 通道的綜合品質評估          |
      | 路徑修正次數     | 過程中重新推演的次數                    |
      | 外部槓桿使用率   | MCP 工具和外部資源的使用比例            |
    And 效率指標寫入 meta-thinking 通道
    And 未來類似目標啟動時，PDEIF 自動調取這些指標作為基準線

  # ══════════════════════════════════════════════════════════════
  # Section 10: 夜間整合 x PDEIF — Tier 3 整合目標進度
  # ══════════════════════════════════════════════════════════════

  Scenario: 夜間整合（00:00）綜合盤點所有進行中目標
    Given 當前時間為 00:00，夜間整合觸發
    And 有 2 個使用者目標和 1 個 MuseClaw 內在目標正在進行中
    When NightlyJob.run() 執行目標相關整合
    Then 對每個進行中目標執行進度盤點：
      | 檢查項目           | 說明                                 |
      | 子目標完成率       | MECE 拆解樹中已完成的比例            |
      | 偏差幅度           | 實際進度與預期進度的差距             |
      | 資源消耗速率       | token / 時間 / 磁碟的消耗趨勢        |
      | 環境變化           | 外部條件是否已改變影響目標可行性     |
    And 盤點結果寫入今日進化報告
    And 需要調整的目標標記為「待重推演」，等待下次深度自省處理

  Scenario: 夜間整合 — 蒸餾目標執行過程的情節記憶為語義記憶
    Given 今天有多次與目標相關的互動
    When NightlyJob 執行記憶蒸餾（MemoryFusion.fuse_daily_memories）
    Then 將目標相關的零碎情節記憶（episodic）合併蒸餾為語義記憶（semantic）
    And 語義記憶保留核心洞見和決策邏輯，移除時間綁定的細節
    And 蒸餾結果可作為未來 PDEIF 推演的上下文輸入
    And 如果某個模式在目標執行中反覆出現 5 次以上，列入結晶候選

  # ══════════════════════════════════════════════════════════════
  # Section 11: 護欄與安全 — PDEIF 的邊界守護
  # ══════════════════════════════════════════════════════════════

  Scenario: 主權保護 — PDEIF 不替使用者做最終目標選擇
    When 使用者傳送 "你直接幫我決定目標就好"
    Then RC-B 主權叢集命中（HG-PDEIF-OUTSOURCING 硬閘觸發）
    And PDEIF 僅輸出：目標選項 + 各自代價 + 退出機制
    And 不輸出收斂式指令（不替使用者決定終點）
    And 溫和地將決策權推回使用者：「這個目標的選定需要你來做」
    And 同時提供足夠的資訊讓使用者做判斷

  Scenario: 不可逆保護 — PDEIF 不推向不可逆點
    Given 使用者的目標路徑中包含一個不可逆操作（如簽訂長期合約）
    When PDEIF 推演到此節點
    Then HG-PDEIF-IRREVERSIBLE 硬閘觸發
    And 在不可逆操作前強制插入「安全檢查點」
    And 確認使用者已充分理解不可逆後果
    And 確認回滾方案或替代路徑已準備好
    And 只有使用者明確確認後才將此節點標記為可執行

  Scenario: 防止流程依賴 — 不把 PDEIF 做成使用者的拐杖
    Given 使用者已連續 3 次使用 PDEIF 處理類似的小目標
    When PDEIF 偵測到依賴模式
    Then SG-PDEIF-DEPENDENCY 軟閘觸發
    And 建議使用者嘗試自主規劃，PDEIF 退到顧問角色
    And 縮短循環、增加外部支持與使用者自主能力建置
    And 不成癮設計：讓使用者越來越強，不是越來越依賴 MuseClaw
