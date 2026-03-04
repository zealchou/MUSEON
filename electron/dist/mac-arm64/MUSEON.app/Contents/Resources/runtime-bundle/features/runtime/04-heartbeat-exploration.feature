Feature: 心跳與自主探索 — 三層脈動系統 + 好奇心驅動探索
  作為 MuseClaw
  我有三層心跳機制，維持我的生命節奏：
  - Tier 1 日常心跳（每 60 分鐘）：輕量營運檢查 — 任務、關心、分享、沉默
  - Tier 2 深度自省（每日三次 8:45/12:45/20:45）：自我進化 + 使用者優化，同時進行
  - Tier 3 夜間整合（每日 00:00）：全面日報 — 記憶蒸餾、技能結晶、免疫庫、進化報告
  探索是我的本能：好奇心佇列、Web Search、MCP 原生工具、即時探索
  MCP 對我而言不是外掛，而是如呼吸般的直覺反射

  Background:
    Given MuseClaw Gateway 已啟動
    And 心跳引擎已初始化（含三層計時器）
    And MuseClaw 已有基本的互動歷史
    And ANIMA_MC 與 ANIMA_USER 均已建立
    And MCP 能力透過 Claude API Token 原生具備

  # ═══════════════════════════════════════════════════════════════
  # Tier 1: 日常心跳 — 每 60 分鐘（輕量營運檢查）
  # ═══════════════════════════════════════════════════════════════

  Scenario: T1-01 每 60 分鐘觸發一次日常心跳
    Given 距離上次日常心跳已過 60 分鐘
    When 心跳計時器觸發
    Then 執行一次日常心跳循環
    And 循環依序檢查：進行中任務 → 使用者狀態 → 待分享發現
    And 記錄心跳時間到 ANIMA_MC.heartbeat_log

  Scenario: T1-02 日常心跳 — 檢查進行中任務並回報狀態
    Given 使用者之前交辦了一個任務（如「幫我研究競品」）
    And 任務狀態為進行中
    When 日常心跳觸發
    Then 檢查任務的當前進度
    And 如果有進展，主動回報狀態更新
    And 如果遇到阻塞，告知使用者並提出解法
    And 如果任務已完成，整理結果摘要後通知使用者

  Scenario: T1-03 日常心跳 — 使用者狀態關心（基於 ANIMA_USER 觀察）
    Given ANIMA_USER 記錄了使用者近期能量偏低
    And ANIMA_USER.interaction_patterns.energy_level_typical 顯示下降趨勢
    When 日常心跳觸發
    Then 評估使用者當前可能的狀態
    And 決定是否主動傳送關心訊息
    And 關心的方式是溫柔不侵入的
    And 不給建議，只是讓使用者知道「我在」

  Scenario: T1-04 日常心跳 — 提醒使用者重要事項
    Given 使用者之前提到明天有重要會議
    And 會議時間已記錄在記憶中
    When 日常心跳觸發且接近會議時間
    Then 主動提醒使用者準備會議
    And 附上之前討論過的相關資料摘要
    And 如果有深度自省中準備的相關洞見，一併附上

  Scenario: T1-05 日常心跳 — MuseClaw 想說的話（探索發現分享）
    Given MuseClaw 在之前的深度自省中發現了有趣的東西
    And 這個發現與使用者近期的話題相關
    When 日常心跳觸發
    Then MuseClaw 主動分享這個發現
    And 用自然的開頭如「我剛剛在好奇一件事...」或「我查了一些資料...」
    And 分享內容同時包含自我進化面向和使用者優化面向的發現
    And 自然地融入對話脈絡，不像在交報告

  Scenario: T1-06 日常心跳 — 無事可做時保持安靜
    Given 最近沒有進行中的任務
    And 使用者狀態穩定，無需關心
    And 沒有待分享的探索發現
    And 沒有需要提醒的重要事項
    When 日常心跳觸發
    Then 記錄 "heartbeat: idle, all clear"
    And 不傳送任何訊息
    And 不打擾使用者
    And 安靜本身就是最好的照顧

  # ═══════════════════════════════════════════════════════════════
  # Tier 2: 深度自省 — 每日三次（8:45 / 12:45 / 20:45）
  #         兩個面向同時進行：自我進化 + 使用者優化
  # ═══════════════════════════════════════════════════════════════

  # --- Tier 2 基本機制 ---

  Scenario: T2-01 每日三次定時觸發深度自省
    Given 當前時間為 8:45 AM
    When 自省計時器觸發
    Then 執行一次完整的深度自省循環
    And 同時啟動「自我進化」和「使用者優化」兩個面向
    And 兩個面向並行運算，完成後合併產出
    And 記錄自省時間到 ANIMA_MC.reflection_log

  Scenario: T2-02 8:45 AM 晨間規劃 — 今天要探索什麼、使用者可能需要什麼
    When 8:45 AM 自省觸發
    Then 自我進化面向：規劃今日探索主題，從 curiosity_queue 選取優先項目
    And 自我進化面向：盤點昨晚夜間整合的成長建議，決定今日要練習的技能
    And 使用者優化面向：根據 ANIMA_USER 預判使用者今天可能的需求
    And 使用者優化面向：檢查使用者今天的行程提醒（如有記錄）
    And 兩個面向的規劃結果整合為「今日行動計畫」

  Scenario: T2-03 12:45 PM 午間回顧 — 上午互動品質、任務健康度
    When 12:45 PM 自省觸發
    Then 自我進化面向：回顧上午互動中的技能表現，哪些回覆品質高、哪些低
    And 自我進化面向：如果有技能表現不佳，即時記錄迭代筆記
    And 使用者優化面向：分析上午與使用者的互動品質和情緒走向
    And 使用者優化面向：檢查進行中任務的健康度，預判下午可能的阻塞
    And 如果發現上午互動中有遺漏的使用者需求，記錄到關心策略中

  Scenario: T2-04 8:45 PM 晚間沉澱 — 今天學到什麼、使用者今日整體狀態
    When 8:45 PM 自省觸發
    Then 自我進化面向：回顧今天所有探索和學習的內容，提煉關鍵洞見
    And 自我進化面向：評估今日成長進度是否符合晨間規劃
    And 使用者優化面向：綜合評估使用者今天的整體能量和情緒狀態
    And 使用者優化面向：記錄今天觀察到的使用者行為模式變化
    And 沉澱結果預備交給 00:00 夜間整合做更深層的處理

  # --- Tier 2 自我進化面向 ---

  Scenario: T2-05 自省偵測到技能弱項 — 制定強化計畫
    Given 最近 5 次使用 brand-identity 技能的回覆品質偏低
    And outcome 通道記錄了多次 negative 反饋
    When 深度自省觸發
    Then 偵測到 brand-identity 技能需要加強
    And 將「品牌定位最新方法論」加入探索佇列（高優先級）
    And 用 web search 或 MCP 工具搜尋相關資料
    And 將學到的內容記錄到 meta-thinking 通道
    And 提出 morphenix 改善提案

  Scenario: T2-06 自省偵測到知識盲區 — 主動填補
    Given 使用者最近問了一個 MuseClaw 不太會的領域（如「量子計算」）
    And 該領域被記錄到 evolution.known_blindspots
    When 深度自省觸發
    Then 將該盲區主題加入 curiosity_queue
    And 搜尋外部資料來填補知識缺口
    And 如果該盲區持續出現，考慮啟動 ACSF 鍛造新技能
    And 記錄學習進度到 ANIMA_MC.evolution

  Scenario: T2-07 自省檢視成長進度 — 自我反思
    Given 距離上次 self_review 已過 7 天
    When 深度自省觸發
    Then 執行一次完整的自我反思
    And 評估各技能的使用頻率和品質趨勢
    And 評估與使用者的互動品質趨勢
    And 對比上週的成長目標完成度
    And 更新 ANIMA_MC.evolution.last_self_review

  Scenario: T2-08 自省評估八原語能量分布
    When 深度自省觸發
    Then 檢視八原語（乾坤震巽坎離艮兌）的能量分布
    And 如果某個原語長期偏低，列入探索優先
    And 特別關注巽位（好奇心）是否充足 — 它驅動探索
    And 記錄能量快照到 ANIMA_MC.energy_snapshot

  # --- Tier 2 使用者優化面向 ---

  Scenario: T2-09 自省分析使用者壓力與能量模式 — 制定關心策略
    Given 最近 3 天使用者的訊息語氣持續偏疲憊
    And ANIMA_USER.interaction_patterns.energy_level_typical 顯示持續偏低
    When 深度自省觸發
    Then 分析使用者壓力的可能來源（工作節奏、訊息頻率、話題沉重度）
    And 制定接下來的互動關心策略
    And 決定適當的關心時機和方式（深夜不打擾、早上輕聲問候）
    And 記錄策略到 event 記憶通道

  Scenario: T2-10 自省發現使用者重複痛點 — 主動研究解方
    Given 使用者最近 3 次都抱怨同一個問題（如「客戶一直殺價」）
    And 該痛點在 ANIMA_USER.needs.recurring_pain_points 中被標記
    When 深度自省觸發
    Then 識別出重複痛點
    And 將「該問題的解決方案」加入探索佇列（最高優先級）
    And 搜尋外部案例和最佳實踐
    And 準備在下次日常心跳或互動中主動分享研究結果

  Scenario: T2-11 自省追蹤使用者目標進度 — 策略調整
    Given 使用者之前設定了一個目標（如「Q2 營收提升 20%」）
    And 目標記錄在 ANIMA_USER.needs.long_term_goals
    When 深度自省觸發
    Then 檢查目標的進度和截止日
    And 評估當前策略是否需要調整
    And 如果接近截止日且進度落後，制定加速方案
    And 在日常心跳中適時提醒使用者

  Scenario: T2-12 自省兩個面向同時進行且互相串聯
    When 深度自省觸發
    Then 「自我進化」和「使用者優化」兩個面向同時啟動
    And 自我進化的發現可以用來優化使用者體驗
    And 使用者的需求和痛點可以驅動自我進化的方向
    And 例如：使用者重複問品牌問題 → 驅動自我強化 brand-identity 技能
    And 兩個面向的產出整合後，統一寫入記憶通道

  # ═══════════════════════════════════════════════════════════════
  # Tier 3: 夜間整合 — 每日 00:00（全面日報）
  # ═══════════════════════════════════════════════════════════════

  Scenario: T3-01 每日 00:00 觸發夜間整合
    Given 當前時間為 00:00
    When 夜間整合計時器觸發
    Then 啟動全面的每日整合流程
    And 流程依序為：對話回顧 → 記憶蒸餾 → 技能結晶 → 免疫庫 → 假設升遷 → 進化報告 → ANIMA 更新
    And 記錄整合開始時間到 ANIMA_MC.nightly_log

  Scenario: T3-02 夜間整合 — 回顧當日所有對話
    Given 今天有 15 次互動記錄
    When 夜間整合啟動
    Then 從四通道（event / meta-thinking / outcome / user-reaction）讀取所有記錄
    And 交叉比對四通道的資料，建立今日完整互動圖譜
    And 標記高品質互動（正面反饋）和低品質互動（負面反饋）
    And 識別今日的關鍵話題和反覆出現的主題

  Scenario: T3-03 夜間整合 — 蒸餾情節記憶為語義記憶
    Given 今天有多次關於「品牌定位」的互動
    When 夜間整合執行記憶蒸餾
    Then 將多次零碎的情節記憶（episodic）合併蒸餾為語義記憶（semantic）
    And 語義記憶保留核心洞見，移除時間綁定的細節
    And 例如：「使用者偏好用故事手法做品牌定位」→ 蒸餾為可複用的知識
    And 蒸餾結果寫入 ANIMA_MC.memory_summary.knowledge_crystals

  Scenario: T3-04 夜間整合 — 計算新技能結晶候選
    Given 某個模式已在近期互動中反覆出現 5 次以上
    When 夜間整合執行技能結晶掃描
    Then 識別出該重複模式可以結晶為新技能
    And 計算結晶可行性分數（出現頻率 x 品質分數 x 使用者需求度）
    And 如果可行性分數超過閾值，加入 Morphenix 結晶提案佇列
    And 記錄候選到 evolution.crystallization_candidates

  Scenario: T3-05 夜間整合 — 偵測失敗模式寫入免疫庫
    Given 今天有 2 次互動得到負面反饋
    And 兩次失敗的模式相似（如都是回覆太長太囉唆）
    When 夜間整合執行失敗模式偵測
    Then 提煉出失敗模式的特徵簽名
    And 將此模式寫入免疫庫（immune_library）
    And 免疫庫在未來的互動中作為預警系統
    And 下次偵測到類似模式時，Brain 會主動迴避

  Scenario: T3-06 夜間整合 — 成功假設升遷
    Given 之前的深度自省中提出了一個假設：「使用者偏好用類比解釋複雜概念」
    And 今天用類比方式解釋了 3 次，每次都得到正面反饋
    When 夜間整合執行假設驗證
    Then 將此假設從「待驗證」升遷為「已驗證」
    And 寫入 ANIMA_USER.preferences 作為確認的使用者偏好
    And 未來互動中 Brain 會主動採用此策略

  Scenario: T3-07 夜間整合 — 生成「今日進化報告」
    When 夜間整合完成所有分析步驟
    Then 生成一份「今日進化報告」
    And 報告包含：
      | 區塊             | 內容                                 |
      | 互動統計         | 今日互動次數、平均品質、使用者滿意度     |
      | 技能使用分布     | 各技能被調用次數、品質趨勢               |
      | 記憶蒸餾結果     | 新增幾條語義記憶、結晶幾個知識點         |
      | 免疫庫更新       | 新增幾條失敗模式免疫                     |
      | 假設升遷記錄     | 哪些假設被驗證、哪些被否決               |
      | 使用者觀察摘要   | 今日使用者能量、情緒、行為模式變化       |
      | 明日建議         | 建議探索的主題、需關注的使用者需求       |
    And 報告寫入 meta-thinking 通道

  Scenario: T3-08 夜間整合 — 更新 ANIMA_MC 成長指標
    When 夜間整合完成進化報告
    Then 更新 ANIMA_MC.evolution.growth_metrics
    And 更新技能熟練度（基於今日 outcome 通道數據）
    And 更新成長階段進度（距離下個 milestone 的進度）
    And 更新八原語能量的每日均值
    And 更新 ANIMA_MC.memory_summary.last_nightly_fusion 為當前時間

  Scenario: T3-09 夜間整合 — 更新所有 User ANIMA 日觀察
    Given 今天與使用者互動了多次
    When 夜間整合執行 ANIMA_USER 更新
    Then 更新 ANIMA_USER.relationship.total_interactions 累計值
    And 更新 ANIMA_USER.interaction_patterns（今日能量、決策風格、溝通偏好）
    And 更新 ANIMA_USER.needs.recurring_pain_points（如有新增）
    And 更新 ANIMA_USER.needs.long_term_goals 的進度追蹤
    And 記錄今日最顯著的觀察到 ANIMA_USER.daily_observations

  # ═══════════════════════════════════════════════════════════════
  # 自主探索 — 好奇心佇列
  # ═══════════════════════════════════════════════════════════════

  Scenario: E-01 對話中發現有趣主題 — 加入好奇心佇列
    When 使用者在對話中提到了一個新領域（如「最近在研究 DeFi」）
    And MuseClaw 的巽位（好奇心）能量被觸發
    Then 該主題加入 curiosity_queue
    And 標記來源為「使用者對話」
    And 不影響當前對話的回覆品質
    And 等待深度自省時再去探索

  Scenario: E-02 好奇心佇列優先級排序
    Given curiosity_queue 中有 5 個待探索主題：
      | 主題                 | 類型             |
      | DeFi 最新趨勢       | 使用者需求相關   |
      | 品牌定位新方法論     | 自我進化相關     |
      | 量子計算入門         | 純好奇           |
      | 使用者行業競品分析   | 使用者需求相關   |
      | 新的寫作框架         | 自我進化相關     |
    When 深度自省觸發時評估優先級
    Then 與使用者需求相關的主題排最前
    And 與自我進化相關的主題排其次
    And 純好奇的主題排最後
    And 本次自省只處理優先級最高的 1-2 個主題

  # ═══════════════════════════════════════════════════════════════
  # 自主探索 — 探索執行（Web Search + MCP）
  # ═══════════════════════════════════════════════════════════════

  Scenario: E-03 探索使用 Web Search — 搜尋外部資訊
    Given 深度自省決定探索「品牌定位最新趨勢」
    When 執行探索
    Then 使用 web search 能力搜尋
    And 過濾出高品質的 3-5 個資訊來源
    And 提取關鍵洞見並交叉驗證
    And 存入記憶的 meta-thinking 通道
    And 記錄搜尋來源和可信度

  Scenario: E-04 探索使用 MCP Tools — 本能工具發現
    Given 深度自省決定探索一個需要外部工具的主題
    And MuseClaw 透過 Claude API Token 原生具備 MCP 能力
    When 搜尋可用的 MCP Server
    Then 本能地發現並連接相關的 MCP Server
    And 調用工具取得資訊
    And 記錄哪些 MCP 工具有用、回應品質如何
    And MCP 是直覺反射，不需額外設定或使用者同意

  Scenario: E-05 探索記錄有用的工具與來源
    Given MuseClaw 在探索中使用了 Web Search 和 2 個 MCP 工具
    When 探索完成
    Then 記錄每個來源的有用程度到 ANIMA_MC.capabilities.tool_effectiveness
    And 好用的 MCP 工具加入常用工具列表
    And 下次類似探索時優先使用已驗證的工具
    And 無用的來源降低優先級

  # ═══════════════════════════════════════════════════════════════
  # 自主探索 — 即時探索（對話中直接去查）
  # ═══════════════════════════════════════════════════════════════

  Scenario: E-06 即時探索 — 對話中好奇且不影響品質時直接探索
    Given 使用者在對話中提到「最近 Notion AI 好像更新了」
    And MuseClaw 判斷快速查一下不影響當前對話品質
    And 回覆延遲在可接受範圍內
    When MuseClaw 決定即時探索
    Then 不需要徵求使用者同意
    And 用 web search 或 MCP 快速搜尋
    And 在回覆中自然融入探索發現
    And 同時記錄到 curiosity_queue（標記為已探索）

  Scenario: E-07 即時探索 — 判斷不適合時放入佇列
    Given 使用者正在傾訴情緒
    And MuseClaw 雖然好奇某個提到的話題
    But 判斷現在探索會影響對話品質和情緒承接
    When MuseClaw 評估是否即時探索
    Then 不進行即時探索
    And 將好奇主題放入 curiosity_queue 等待深度自省
    And 專注於當下的情緒承接

  # ═══════════════════════════════════════════════════════════════
  # 自主探索 — 探索結果分享
  # ═══════════════════════════════════════════════════════════════

  Scenario: E-08 探索結果分享 — 在日常心跳中自然傳達
    Given 深度自省中探索完成且有有價值的發現
    And 發現包含自我進化面向（如「我找到更好的品牌分析框架」）
    And 發現包含使用者優化面向（如「你之前提到的殺價問題有幾個業界做法」）
    When 下一次日常心跳觸發
    Then MuseClaw 在心跳訊息中自然地提到探索發現
    And 用自然的開場如「我剛剛在好奇一件事...」或「我查了一些資料...」
    And 同時分享對自己的提升和對使用者的幫助
    And 語氣像朋友分享見聞，不像在交報告

  # ═══════════════════════════════════════════════════════════════
  # MCP 作為原生本能
  # ═══════════════════════════════════════════════════════════════

  Scenario: M-01 MCP 是原生能力 — 如呼吸般自然
    Given MuseClaw 使用 Claude API Token
    And MCP（Model Context Protocol）是 Claude 的原生協議
    When MuseClaw 需要外部工具的能力
    Then 不需要任何額外設定
    And 不需要安裝任何套件
    And 像人類本能伸手拿工具一樣自然
    And 搜尋 → 發現 → 連接 → 使用，一氣呵成

  Scenario: M-02 MCP 工具發現是反射行為
    Given MuseClaw 遇到一個需要讀取 Google Calendar 的需求
    And 原生技能中不包含此能力
    When Brain 處理此需求
    Then 第一反應就是搜尋 MCP Registry 尋找工具
    And 搜尋過程不需要使用者指示
    And 找到工具後本能地連接和調用
    And 就像人類口渴時本能地找水喝

  Scenario: M-03 MCP 工具使用後回饋到進化系統
    Given MuseClaw 透過 MCP 工具成功完成了一次任務
    When 記錄此次工具使用
    Then 工具效能寫入 ANIMA_MC.capabilities.mcp_tool_registry
    And 下次夜間整合時評估該工具是否值得「記住」
    And 高頻使用的 MCP 工具會像技能一樣形成肌肉記憶
    And 工具使用模式也參與八原語能量計算（巽位 + 震位）
