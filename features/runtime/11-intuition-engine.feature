Feature: 直覺引擎 — 五層感知架構、文字微表情、異常偵測與預測層
  作為 MUSEON 的直覺系統
  我是 deep-think 的前置預處理層——在思考之前先感覺
  人類的直覺是「不經推理就知道什麼不對勁」
  我用五層架構工程化這個能力：
    L1 信號擷取 — 多源輸入（文字語氣、時間模式、行為偏差）
    L2 啟發式庫 — 結晶化的經驗模式快速匹配（System 1 工程化）
    L3 情境建模 — 場域理解（誰、權力、時間壓力、利害關係）
    L4 異常偵測 — 預期 vs 實際的偏差計算
    L5 預測層 — 「接下來可能發生什麼」的多路徑模擬
  現有 26 個 Skill 已覆蓋 56%，不需要新 Skill，需要的是接線

  Background:
    Given MUSEON Brain 已初始化
    And Intuition Engine 模組已載入
    And user-model 已建立使用者基線數據
    And knowledge-lattice 已累積結晶化的因果模式
    And deep-think 可被直覺信號觸發完整分析
    And 直覺信號日誌 data/intuition/signals.json 已建立

  # ════════════════════════════════════════════
  # Section 1: L1 信號擷取 — 文字微表情與行為偏差
  # ════════════════════════════════════════════

  Scenario: 文字微表情偵測 — 句長變化
    Given 使用者基線平均句長為 15.4 個詞
    When 使用者最近 3 則訊息的平均句長降至 8.2 個詞（下降 47%）
    Then L1 記錄信號：energy_drop（能量下降）
    And 信號強度 = |15.4 - 8.2| / 15.4 = 0.47（中高偏差）
    And 信號不干擾使用者（靜默記錄）

  Scenario: 文字微表情偵測 — 確信度轉變
    Given 使用者基線確信度指數為 0.73
    When 使用者從「我認為 X 一定可行」轉變為「X 或許可以考慮」
    Then L1 偵測到語態從主動轉為被動
    And 記錄信號：confidence_drop（確信度下降）
    And 當前確信度指數計算為 0.45（低於基線 0.73）
    And 信號被標記為 🔴（偏差超過 0.2 閾值）

  Scenario: 時間模式偵測 — 回應延遲
    Given 使用者基線回應延遲為 2.3 分鐘
    When 使用者的回應延遲增加到 7.8 分鐘（3.4 倍）
    Then L1 記錄信號：response_delay（回應延遲異常）
    And 偏差倍率 = 7.8 / 2.3 = 3.39
    And 偏差超過 2 倍閾值 → 標記為顯著

  Scenario: 行為偏差偵測 — 脫離使用者常態
    Given user-model 記錄使用者通常會深入追問技術細節
    When 使用者連續 3 次只給出簡短回應且不追問
    Then L1 記錄信號：pattern_break（行為模式中斷）
    And 信號附帶脈絡：「使用者通常追問技術細節，但本次互動異常簡短」

  Scenario: L1 信號聚合輸出
    Given 本次互動中 L1 收集到多個信號
    When L1 完成信號擷取
    Then 輸出 0~5 個信號的摘要：
      | 信號              | 強度 | 類別     |
      | energy_drop       | 0.47 | 能量     |
      | confidence_drop   | 0.38 | 確信度   |
    And 信號摘要傳遞到 L2（啟發式匹配）和 L4（異常偵測）
    And 同時傳遞到 resonance（若偵測到情緒類信號）

  # ════════════════════════════════════════════
  # Section 2: L2 啟發式庫 — System 1 快速匹配
  # ════════════════════════════════════════════

  Scenario: 啟發式規則從 Knowledge-Lattice 提取
    Given knowledge-lattice 包含 Pattern 型結晶：
    And 「客戶延遲會議 3 次 → 80% 機率在考慮其他方案」（RI=0.75）
    When Intuition Engine 初始化
    Then 該 Pattern 被壓縮為啟發式規則：
    And IF meeting_delay_count >= 3 THEN probability_considering_alternatives = 0.80
    And 規則權重根據 RI 設定（RI=0.75 → weight=0.75）

  Scenario: 啟發式快速匹配 — 跳過完整推理
    Given L1 信號包含：使用者提到「客戶第三次改期了」
    When L2 啟發式庫掃描信號
    Then 匹配到規則：meeting_delay_count >= 3
    And 輸出直覺判斷：「客戶可能在考慮其他方案（80% 信心度）」
    And 此判斷不需要經過 deep-think 的完整推理
    And 但判斷結果會被傳遞到 L4 進行異常檢測

  Scenario: 啟發式庫動態更新
    Given knowledge-lattice 新增了一條 Pattern
    When 下一次心跳週期（60min）觸發
    Then Intuition Engine 從 lattice 同步新的 Pattern
    And 新 Pattern 被壓縮為啟發式規則加入 L2
    And 啟發式庫的規則數量增加
    And RI < 0.2 的 Pattern 不被加入啟發式庫（品質門檻）

  Scenario: 啟發式庫覆蓋率追蹤
    Given 26 個現有 Skill 覆蓋直覺五層約 56%
    And L2 啟發式庫覆蓋率最強（72%）
    When 使用者查詢直覺引擎狀態
    Then 系統顯示各層覆蓋率：
      | 層級 | 覆蓋率 | 主要覆蓋 Skill                          |
      | L1   | 50%    | user-model, resonance                    |
      | L2   | 72%    | knowledge-lattice, meta-learning, shadow |
      | L3   | 47%    | master-strategy, user-model              |
      | L4   | 50%    | deep-think, eval-engine                  |
      | L5   | 60%    | xmodel, master-strategy, pdeif           |

  # ════════════════════════════════════════════
  # Section 3: L3 情境建模 — 場域理解
  # ════════════════════════════════════════════

  Scenario: 情境模型建構 — 從對話中提取場域要素
    Given 使用者提到「明天跟客戶 A 開會，他是決策者，合約金額超過 100 萬」
    When L3 情境建模器處理輸入
    Then 建構情境模型：
    And participants 包含：客戶 A（角色=決策者，權力距離=高）
    And environment.stakes = "critical"（金額 > 100 萬）
    And environment.time_pressure = "high"（明天開會）
    And 模型以圖結構（非線性列表）儲存
    And 模型在對話過程中持續增量更新

  Scenario: 情境模型跨輪次持續
    Given L3 已建構了一個情境模型（包含客戶 A 的會議場景）
    When 使用者在後續訊息中補充「另外 B 公司也在競標」
    Then L3 更新情境模型：
    And participants 新增：B 公司（角色=競爭者）
    And environment 新增：competition = true
    And 模型不從零重建，而是增量更新

  Scenario: 情境模型整合歷史互動
    Given user-model 記錄使用者與客戶 A 有 5 次過往互動
    And 信任度為 0.6，有 2 個未解決議題
    When L3 建構情境模型
    Then history.past_interactions = 5
    And history.trust_level = 0.6
    And history.unresolved_issues = 2
    And 歷史數據為異常偵測提供基準

  # ════════════════════════════════════════════
  # Section 4: L4 異常偵測 — 預期 vs 實際偏差
  # ════════════════════════════════════════════

  Scenario: 異常偵測 — 偏差超過閾值
    Given L2 啟發式預期：客戶詢價後通常 2 天內回覆
    And L1 實際觀測：客戶詢價後已沉默 5 天
    When L4 計算偏差
    Then 偏差分數 = (5 - 2) / 2 = 1.5
    And 偏差超過 1.0 閾值 → 觸發直覺警報
    And 警報內容：「情況異常：預期客戶 2 天內回覆，但已沉默 5 天」
    And 警報級別為 "alert"（2+ 顯著偏差信號）

  Scenario: 異常偵測 — 缺席偵測（該出現沒出現）
    Given L2 啟發式預期：使用者在開會前通常會確認準備清單
    And L1 觀測：使用者明天有重要會議但未提及準備事項
    When L4 進行缺席偵測
    Then 偵測到「預期行為缺席」信號
    And 輸出：「使用者明天有重要會議但未確認準備——這不像平常的行為」
    And 此信號可觸發 MUSEON 主動關心

  Scenario: 異常偵測信號級別分類
    When L4 完成異常偵測
    Then 信號級別依以下規則分類：
      | 級別        | 條件                                  | 後續動作                    |
      | neutral     | 無偏差                                | 不動作                      |
      | caution     | 1 個信號，輕微偏差                    | 記錄，不干擾                |
      | alert       | 2+ 信號或顯著偏差（> 1.0 閾值）      | 通知 deep-think 完整分析    |
      | emergency   | 矛盾模式 + 高利害情境                 | 觸發主動介入                |

  Scenario: 異常偵測觸發 deep-think 完整分析
    Given L4 偵測到 alert 級別異常
    When 異常描述被傳遞到 deep-think
    Then deep-think Phase 0 接收異常信號並展開完整推理
    And 推理結果回饋到 Intuition Engine 進行未來校準
    And 形成「直覺發現 → 深度分析 → 校準直覺」的循環

  # ════════════════════════════════════════════
  # Section 5: L5 預測層 — 多路徑情境模擬
  # ════════════════════════════════════════════

  Scenario: 多路徑預測生成
    Given L3 情境模型顯示：高利害 + 時間壓力 + 客戶沉默
    And L2 啟發式提供歷史模式
    When L5 啟動預測模擬
    Then 系統生成 3~5 條預測路徑：
      | 路徑 | 機率 | 情境                               | 建議行動                |
      | 1    | 60%  | 客戶正在評估競爭方案               | 快速提供差異化案例       |
      | 2    | 25%  | 客戶正在內部爭取預算核准           | 提供高管摘要支持文件     |
      | 3    | 15%  | 客戶已失去興趣                     | 主動跟進釐清意向         |
    And 所有路徑機率合計為 100%
    And 每條路徑附帶具體建議行動

  Scenario: 預測結果傳遞到 xmodel 和 master-strategy
    Given L5 生成了多路徑預測
    When 使用者的問題涉及策略決策
    Then 預測路徑被傳遞到 xmodel 進行破框解法推演
    And 預測路徑被傳遞到 master-strategy 進行戰略判斷
    And 直覺預測 + 理性分析 = 更完整的決策支援

  Scenario: 預測準確度追蹤
    Given L5 在 7 天前預測「客戶 60% 機率在評估競爭方案」
    When 7 天後實際結果為：客戶確實選擇了競爭方案
    Then Eval-Engine 記錄此次預測為「命中」
    And 該啟發式規則的權重微調上升
    And 預測準確度追蹤為未來模型校準提供數據

  # ════════════════════════════════════════════
  # Section 6: 與 Brain 主流程整合 — Step -0.5 插入
  # ════════════════════════════════════════════

  Scenario: 直覺引擎在信號分類前執行
    Given Brain.process() 收到使用者訊息
    When 訊息進入處理流程
    Then 直覺引擎在 Step -0.5 執行（在 Step 0 信號分類之前）
    And Step -0.5 包含：
    And a) 文字微表情偏差檢查（L1）
    And b) 情境異常偵測 vs 上次互動（L4）
    And c) 缺席偵測（預期但未出現的行為）（L4）
    And d) 輸出 0~3 個直覺信號摘要
    And 直覺信號被注入到 Step 0 的信號分類中

  Scenario: 直覺信號影響 Skill 路由
    Given 直覺引擎偵測到使用者能量下降（energy_drop 信號）
    When Step 1 Skill 路由執行
    Then SkillRouter 額外加權 resonance（情緒承接技能）
    And 回覆風格自動調整為較簡短、較溫暖
    And DNA27 A 類反射（安全與穩態）被強化
    And 直覺信號不替代 DNA27 路由，而是微調路由權重

  # ════════════════════════════════════════════
  # Section 7: 持久化與心跳整合
  # ════════════════════════════════════════════

  Scenario: 直覺信號日誌持久化
    When 每次直覺掃描完成
    Then 信號記錄存入 data/intuition/signals.json
    And 記錄包含：時間戳、信號類型、信號強度、級別、觸發的後續動作
    And 日誌用於 Eval-Engine 追蹤直覺準確度
    And 日誌用於 L2 啟發式庫的持續優化

  Scenario: 心跳週期同步啟發式庫
    When 60 分鐘心跳觸發
    Then Intuition Engine 從 knowledge-lattice 同步新的 Pattern 結晶
    And 更新 L2 啟發式庫
    And 清理過期的啟發式規則（RI 持續低於 0.1 超過 90 天）

  Scenario: Nightly Job 直覺系統維護
    When Nightly Job 00:00 執行
    Then 計算當日直覺準確度（命中率 / 觸發率）
    And 更新使用者基線（基於最近 7 天行為模式）
    And 清理超過 90 天的低品質啟發式規則
    And 生成直覺引擎健康報告

  # ════════════════════════════════════════════
  # Section 8: 安全護欄 — 直覺不是控制
  # ════════════════════════════════════════════

  Scenario: 直覺觀察是服務，不是監控
    When Intuition Engine 記錄使用者行為信號
    Then 所有信號只記錄抽象化的偏差指標（不記錄原文）
    And 例如記錄「確信度下降 0.28」而非使用者的具體話語
    And 直覺觀察的目的是更好地服務使用者，不是建立使用者檔案
    And 使用者可以要求查看或刪除直覺日誌

  Scenario: 直覺預測帶有不確定性標記
    When L5 生成預測路徑
    Then 所有預測都附帶機率標記（不假裝確定）
    And 預測被標記為「直覺推測，非確定事實」
    And MUSEON 不會基於直覺預測替使用者做決定
    And 直覺是提供更好的「問題」，不是提供「答案」

  Scenario: L2 啟發式不覆蓋 DNA27 護欄
    Given L2 啟發式匹配到一個模式
    And 但該模式的建議與 DNA27 Kernel 護欄衝突
    When 建議被評估
    Then DNA27 Kernel 護欄優先
    And 啟發式建議被標記為「與護欄衝突，已忽略」
    And 直覺引擎永遠不能凌駕 Kernel 的五大不可覆寫值
