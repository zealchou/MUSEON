Feature: 記憶系統 — 六層記憶架構 + 四通道寫入 + 混合檢索 + 溫度活化 + 夜間融合
  作為 MuseClaw
  我需要一個活的、有層次的記憶系統
  從工作記憶到免疫抗體，從情節記錄到假說孵化
  能回憶、儲存、強化、衰退、壓縮，並在夜間自主融合進化
  像一個有呼吸的生態系統，而不只是一個資料庫

  Background:
    Given MuseClaw 已完成命名儀式
    And Memory Store 已初始化
    And 六層記憶系統（L0-L5）架構已就緒
    And 記憶目錄結構為 data/memory/YYYY/MM/DD/channel.md
    And SQLite 索引檔已建立供快速檢索
    And 向量嵌入引擎已初始化

  # ══════════════════════════════════════════════════════════
  # Section 1: 六層記憶架構 — 從揮發到永恆
  # ══════════════════════════════════════════════════════════

  Scenario: L0 工作記憶 — 當前對話的揮發暫存區
    Given 使用者正在進行一段對話
    When 對話累積到第 20 則訊息
    Then L0 工作記憶保留最近 20 則訊息
    And 超過 20 則的舊訊息被滾動移出 L0
    And L0 內容在對話結束後即揮發
    And L0 是所有記憶層的原材料來源

  Scenario: L1 防錯基因 — 永不衰退的免疫抗體
    Given MuseClaw 在互動中犯了一個已被驗證的錯誤
    And 該錯誤被標記為「必做」或「絕不做」的規則
    When 規則經過驗證確認
    Then 該規則被寫入 L1 防錯基因層
    And L1 記憶永不衰退、永不壓縮
    And 像免疫系統的抗體一樣永久生效
    And 所有後續互動的啟動前檢查都會載入 L1 規則

  Scenario: L2_ep 情節記憶 — 事件的原始記錄
    Given 使用者與 MuseClaw 進行了一次關於「品牌定位」的深度討論
    When 對話結束後記憶系統處理事件
    Then L2_ep 記錄了完整的事件脈絡
    And 包含「誰說了什麼」「什麼時候」「發生了什麼」
    And 包含 session_id、timestamp、participants
    And L2_ep 記憶可隨時間被壓縮或蒸餾為 L2_sem

  Scenario: L2_sem 語義記憶 — 蒸餾出的知識與模式
    Given L2_ep 中累積了 5 次「使用者疲憊時偏好工具型回覆」的事件
    When 記憶系統偵測到重複模式
    Then 蒸餾為 L2_sem 語義記憶
    And 記錄為「使用者疲憊時，工具比策略更有效」
    And L2_sem 可被後續互動引用和更新
    And L2_sem 是 Knowledge Lattice 結晶的重要養分來源

  Scenario: L3 程序技能 — 反覆成功模式的結晶
    Given 某個互動模式在 30 天內成功 3 次以上
    And 該模式跨情境可複用
    When 記憶系統評估升級條件
    Then 該模式被結晶為 L3 程序技能
    And L3 技能可被自動觸發，無需逐步展開
    And 多個步驟被壓縮為動作單元
    And 60 天未使用的 L3 技能將被降級回 L2_ep

  Scenario: L4 免疫圖書館 — 失敗模式與反模式永久參考
    Given MuseClaw 觀察到「在使用者情緒低落時直接給建議」導致負面反應
    And 該模式被多次驗證為反模式
    When 反模式被確認且跨 3 種以上情境穩定
    Then 記錄進 L4 免疫圖書館
    And 格式為「絕不在 Y 條件下做 X」
    And L4 記憶幾乎永不衰退
    And 在每次互動啟動前自動預判並攔截

  Scenario: L5 假說池 — 實驗性想法的孵化區
    Given MuseClaw 產生了一個新的互動假說
    And 假說內容為「先問使用者今天的能量狀態再路由迴圈」
    When 假說被記錄到 L5 假說池
    Then 假說進入受控實驗模式
    And 每次採用後與基線對比結果
    And 連續 2 次採用結果優於基線時
    Then 假說被升級到 L2_sem 或 L3
    And 30 天內未收斂的假說自然衰退

  # ══════════════════════════════════════════════════════════
  # Section 2: 四通道記憶寫入 — 多維記錄互動
  # ══════════════════════════════════════════════════════════

  Scenario: event 通道 — 記錄事實：發生了什麼
    When 使用者傳送一則訊息
    And Brain 產生回覆
    Then event.md 記錄了此次互動
    And 包含 event_type、session_id、timestamp
    And 包含 user_message 摘要和匹配到的技能名稱
    And event 通道只記事實，不記推理

  Scenario: meta-thinking 通道 — 記錄推理過程與決策邏輯
    When Brain 處理一則訊息
    Then meta-thinking.md 記錄了思考過程
    And 包含 DNA27 匹配了哪些技能
    And 包含 reasoning（為什麼這樣回應）
    And 包含 confidence 信心分數
    And 包含迴圈路由決策（fast/exploration/slow）的依據

  Scenario: outcome 通道 — 記錄結果與後果
    When Brain 完成一次回覆
    Then outcome.md 記錄了結果指標
    And 包含 task_id、result、response_length
    And 包含 skills_used 和 token_consumed
    And 包含回覆品質的自我評估分數

  Scenario: user-reaction 通道 — 記錄使用者如何回應
    When 使用者對回覆表達不滿（如「太長了」、「不是我要的」）
    Then user-reaction.md 記錄了使用者的反應
    And 標記 reaction_type 為 negative
    And 記錄反應的具體內容和情緒訊號
    When 使用者表達滿意（如「太棒了！就是這個」）
    Then 標記 reaction_type 為 positive
    And 相關記憶被標記為候選強化項

  # ══════════════════════════════════════════════════════════
  # Section 3: 記憶回憶 — 混合搜尋跨層召回
  # ══════════════════════════════════════════════════════════

  Scenario: 混合搜尋 — Vector 70% + BM25 30% UNION 策略
    Given 記憶庫中有 200 條跨層記憶
    When Brain 需要回憶與「品牌定位」相關的記憶
    Then 啟動混合搜尋引擎
    And 向量語義搜尋佔權重 70%
    And BM25 關鍵字搜尋佔權重 30%
    And 兩種搜尋結果取 UNION（聯集）而非 INTERSECTION（交集）
    And 確保語義相似和關鍵字匹配的結果都不遺漏

  Scenario: 跨層跨通道關聯回憶
    Given 昨天使用者問了關於「品牌定位」的問題
    And Brain 當時匹配了 brand-identity 和 business-12
    When 今天使用者再次提到「品牌」
    Then Brain 從 L2_ep 找到昨天的互動事件
    And 從 meta-thinking 通道找到當時的推理過程
    And 從 outcome 通道找到結果
    And 從 user-reaction 通道找到使用者的反應
    And 同時檢查 L2_sem 是否有相關的蒸餾知識
    And 綜合這些記憶來改進今天的回覆

  Scenario: 按記憶層優先級排序回憶結果
    Given 多層記憶中都有與當前問題相關的內容
    When Brain 執行記憶回憶
    Then L1 防錯基因優先載入（永遠第一）
    And L4 免疫圖書館次之（避免重蹈覆轍）
    And L3 程序技能接著（已驗證的做法）
    And L2_sem 語義記憶再次（蒸餾過的知識）
    And L2_ep 情節記憶最後（原始事件）
    And L5 假說池僅在探索模式下納入

  # ══════════════════════════════════════════════════════════
  # Section 4: 記憶儲存、強化、衰退、壓縮
  # ══════════════════════════════════════════════════════════

  Scenario: 記憶儲存 — 寫入正確的記憶層
    Given Brain 完成了一次互動
    When 記憶系統判斷記憶歸屬
    Then 原始事件寫入 L2_ep
    And 推理過程寫入 meta-thinking 通道
    And 若觸發了防錯規則，候選寫入 L1
    And 若產生了新假說，寫入 L5
    And 寫入同時更新 SQLite 索引和向量嵌入

  Scenario: 記憶強化 — 正面回饋推升記憶層級
    Given 某次互動使用者回覆了「太棒了！就是這個」
    Then 該互動的 user-reaction 記錄為 positive
    And 相關的 meta-thinking 記憶被標記為 reinforced
    And reinforced 記憶的活化溫度提升
    And 下次類似問題時優先參考此記憶
    And 累積足夠正面回饋的記憶候選升級到更高記憶層

  Scenario: 記憶衰退 — 未使用的記憶逐漸弱化
    Given L3 中有一項技能已 60 天未被調用
    When 夜間代謝掃描執行
    Then 該技能被降級回 L2_ep
    And 降級記錄寫入演化日誌
    And L5 假說池中 30 天未收斂的假說自然衰退
    And L2_ep 中 90 天無執行的記憶被降級或歸檔
    But L1 防錯基因永不衰退
    And L4 免疫圖書館極少衰退（僅當領域消失時歸檔）

  Scenario: 記憶壓縮 — 舊情節記憶蒸餾為語義摘要
    Given L2_ep 中有 30 天前的互動記錄
    And 該互動沒有被標記為 reinforced
    When 記憶壓縮流程觸發
    Then 原始情節記憶被壓縮為語義摘要
    And 關鍵模式和因果關係被提取保留
    And 詳細的逐字對話內容被移除
    And 壓縮後的摘要存入 L2_sem
    And 90 天前的摘要進一步濃縮為關鍵標籤

  # ══════════════════════════════════════════════════════════
  # Section 5: 壓縮前記憶沖刷 — 睡前寫日記
  # ══════════════════════════════════════════════════════════

  Scenario: Context Window 接近上限時觸發靜默記憶沖刷
    Given 當前對話的 context window 使用率達到 80%
    When 記憶系統偵測到壓縮即將發生
    Then 自動觸發一輪靜默的記憶沖刷
    And 將 L0 中重要但即將被壓縮的內容寫入持久記憶
    And 沖刷過程對使用者完全不可見（靜默執行）
    And 關鍵的推理脈絡寫入 meta-thinking 通道
    And 未完成的任務狀態寫入 event 通道
    And 使用者的偏好和情緒狀態寫入 user-reaction 通道
    And 像「睡前寫日記」一樣確保重要記憶不丟失

  # ══════════════════════════════════════════════════════════
  # Section 6: 記憶活化溫度 — Hot / Warm / Cool
  # ══════════════════════════════════════════════════════════

  Scenario: Hot 記憶 — 近期高頻存取，快速召回
    Given 某條 L2_sem 記憶在過去 3 天被引用了 5 次
    Then 該記憶的活化溫度為 Hot
    And 在記憶召回時享有最高優先級
    And 幾乎零延遲即可取用
    And 自動出現在相關對話的上下文中

  Scenario: Warm 記憶 — 中等時效，正常召回
    Given 某條記憶在過去 14 天被引用了 2 次
    Then 該記憶的活化溫度為 Warm
    And 在記憶召回時以正常優先級出現
    And 需要語義匹配才會被召回

  Scenario: Cool 記憶 — 久遠低頻，需要顯式搜尋
    Given 某條記憶已 60 天未被引用
    Then 該記憶的活化溫度為 Cool
    And 不會自動出現在召回結果中
    And 只有在使用者或 Brain 顯式搜尋時才會被找到
    And Cool 記憶是衰退的前兆，若持續 Cool 將觸發降級

  # ══════════════════════════════════════════════════════════
  # Section 7: 夜間記憶融合 — 00:00 每日自主代謝
  # ══════════════════════════════════════════════════════════

  Scenario: 夜間融合 — 回顧今日所有對話
    Given 今天有 15 次互動記錄
    And 時間到達 00:00 觸發夜間融合
    When 融合引擎啟動
    Then 回顧今天四通道的所有記憶
    And 跨通道整合（event × meta-thinking × outcome × user-reaction）
    And 識別出今天的關鍵主題和洞見

  Scenario: 夜間融合 — 蒸餾情節記憶為語義記憶
    Given 今天的 L2_ep 中有多筆類似互動
    When 夜間融合執行 L2_ep → L2_sem 蒸餾
    Then 將重複的情節模式抽象為語義知識
    And 例如「使用者在下午精力充沛時更願意做策略討論」
    And 新產出的 L2_sem 記憶初始活化溫度為 Warm

  Scenario: 夜間融合 — 偵測新 L3 技能候選
    Given 某個互動模式在最近 30 天成功 3 次以上
    When 夜間融合執行技能候選偵測
    Then 識別出符合 L3 升級條件的模式
    And 標記為「L3 技能候選」
    And 在下次融合中若再次驗證成功則正式升級

  Scenario: 夜間融合 — 偵測失敗模式寫入 L4 免疫圖書館
    Given 某個互動方式連續 3 次導致使用者負面反應
    When 夜間融合執行失敗模式掃描
    Then 識別出反模式
    And 生成「絕不在 Y 條件下做 X」的免疫規則
    And 寫入 L4 免疫圖書館
    And 後續互動自動攔截該模式

  Scenario: 夜間融合 — 推升成功的 L5 假說
    Given L5 假說池中有一條假說「先共情再分析效果更好」
    And 該假說已連續 2 次採用後結果優於基線
    When 夜間融合執行 L5 評估
    Then 該假說被推升到 L2_sem（蒸餾為語義知識）
    And 若模式可操作且可複用，進一步推升到 L3（程序技能）
    And 推升事件記錄到演化日誌

  Scenario: 夜間融合 — 生成「今日進化報告」
    When 夜間融合完成所有步驟
    Then 生成一份「今日進化報告」
    And 報告包含：
      | 區段                   | 內容                               |
      | 互動統計               | 今日互動次數、使用技能分布              |
      | 記憶層變動             | 新增/升級/降級/壓縮的記憶數量           |
      | 語義蒸餾               | 今日從 L2_ep 蒸餾出的新 L2_sem 數量    |
      | 技能候選               | 新發現的 L3 候選模式                   |
      | 免疫更新               | 新寫入的 L4 反模式                     |
      | 假說動態               | L5 假說的推升/衰退狀態                 |
    And 報告寫入 meta-thinking 通道
    And 更新 ANIMA_MC.memory_summary.last_nightly_fusion

  # ══════════════════════════════════════════════════════════
  # Section 8: 靈魂年輪交互 — 記憶與身份的關聯
  # ══════════════════════════════════════════════════════════

  Scenario: 身份塑造事件同時寫入記憶層和靈魂年輪
    Given 使用者給予了一個深刻改變 MuseClaw 自我認知的回饋
    When 該事件被識別為身份塑造事件
    Then 事件照常寫入 L2_ep 情節記憶
    And 同時作為 append-only 的靈魂年輪事件記錄到 ANIMA_MC
    And 靈魂年輪事件不可修改、不可刪除
    And 靈魂年輪中的事件可反向影響記憶層的優先級排序

  # ══════════════════════════════════════════════════════════
  # Section 9: Knowledge Lattice 整合 — 記憶到結晶
  # ══════════════════════════════════════════════════════════

  Scenario: 經驗證的洞見從記憶層結晶到 Knowledge Lattice
    Given L2_sem 中有一條經多次驗證的語義知識
    And 該知識被確認跨情境有效
    When 知識結晶流程觸發
    Then 該知識被結晶為 Knowledge Lattice 中的 Crystal
    And Crystal 包含 CUID、GEO 四層結構、驗證等級
    And Crystal 初始共振指數根據驗證次數和品質計算
    And Crystal 與其他相關結晶建立 DAG 連結

  Scenario: Crystal 共振指數隨時間衰減
    Given Knowledge Lattice 中有一顆 Crystal 共振指數為 0.85
    And 該 Crystal 已 90 天未被引用或應用
    When 共振指數衰減公式執行
    Then 共振指數按 exp(-0.03 * days) 衰減
    And 共振指數 < 0.2 的結晶被標記為「待審結晶」
    And 使用者可決定歸檔或更新

  Scenario: Crystal 產出 Markdown 版本作為人類可讀格式
    Given 一顆新的 Crystal 被成功入庫
    When Crystal 存儲流程完成
    Then 自動生成 Markdown 格式的結晶文件
    And Markdown 包含摘要、MECE 結構、洞見與侷限
    And Markdown 文件存放在 data/knowledge-lattice/ 目錄下
    And SQLite 索引同步更新以支援快速檢索

  # ══════════════════════════════════════════════════════════
  # Section 10: 檔案式儲存 — Markdown 為源，索引為衍生
  # ══════════════════════════════════════════════════════════

  Scenario: Markdown 文件作為記憶的唯一權威來源
    Given 記憶系統需要儲存一條新記憶
    When 記憶寫入流程執行
    Then 記憶以 Markdown 格式寫入 data/memory/YYYY/MM/DD/channel.md
    And Markdown 文件是唯一的 canonical source（權威來源）
    And 包含完整的 YAML front matter（metadata）
    And 包含人類可讀的記憶內容

  Scenario: SQLite 索引作為 Markdown 的衍生加速層
    Given Markdown 記憶文件已寫入磁碟
    When 索引更新流程觸發
    Then SQLite 索引文件同步更新
    And 索引包含記憶 ID、時間戳、記憶層、活化溫度、標籤
    And 索引支援快速的結構化查詢
    And 若索引損壞，可從 Markdown 文件完整重建
    And Markdown 文件永遠是真相來源，索引只是加速器
