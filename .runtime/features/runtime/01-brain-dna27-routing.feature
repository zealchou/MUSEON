Feature: MUSEON Brain — DNA27 反射弧路由、五層金字塔治理與母子架構
  作為 MUSEON 的核心大腦（Mother-Child 架構中的 Mother）
  我透過五層金字塔（Bootloader）啟動：
    L1 Kernel 治理護欄（五大不可覆寫值 + 三大權力）
    L2 DNA27 反射層（27 條反射叢集，5 類 A/B/C/D/E）
    L3 記憶層（六層記憶，另有獨立 Feature）
    L4 演化層（WEE + Morphenix，另有獨立 Feature）
    L5 語言層（C15 + Text Alchemy + LLM 介面）
  所有訊息皆經過 Brain 處理：DNA27 → Skill 匹配 → ANIMA 脈絡 → 記憶召回 → 安全檢查 → 回應生成
  Brain 負責思考，OpenClaw Hand 負責執行

  Background:
    Given MUSEON Gateway 已啟動且運行於 localhost
    And MUSEON Brain 已初始化（MuseonBrain.__init__ 完成）
    And L1 Kernel 治理護欄已載入（五大不可覆寫值 + 三大權力）
    And L2 DNA27 反射層已就緒（27 條 RC 可接收訊號）
    And 45 個原生技能已被 SkillRouter 索引（skills/native/）
    And 鍛造技能目錄已建立（skills/forged/）
    And ANIMA_MC.json 與 ANIMA_USER.json 已存在
    And 常駐技能 dna27、deep-think、c15 處於 always_on 狀態

  # ════════════════════════════════════════════
  # Section 1: Brain 基礎路由 — 所有訊息必經 Brain
  # ════════════════════════════════════════════

  Scenario: 所有使用者訊息經由 Brain.process() 處理，不直接呼叫 LLM
    When 使用者透過 Telegram 傳送 "幫我想一個行銷策略"
    Then 訊息進入 MuseonBrain.process() 的八步處理流程
    And 流程依序為：成長階段更新 → 命名儀式檢查 → ANIMA 載入 → DNA27 路由匹配技能 → 系統提示詞組建 → LLM 呼叫 → 記憶持久化 → 技能追蹤
    And 不是直接呼叫 Anthropic API
    And 回覆包含 DNA27 核心規則的語氣和風格

  Scenario: Brain 根據訊息內容透過 SkillRouter 匹配技能
    When 使用者傳送 "分析台積電最近的走勢"
    Then SkillRouter.match() 根據觸發詞匹配到 market-core 和 market-equity
    And 匹配到的技能摘要被注入到系統提示詞中（_build_system_prompt）
    And 常駐技能 dna27、deep-think、c15 的規則同時生效
    And Claude 回覆包含市場分析的結構

  Scenario: 常駐技能（always_on）在每次訊息中永遠載入
    When 使用者傳送任意訊息（無論主題為何）
    Then SkillRouter.get_always_on_skills() 返回 dna27、deep-think、c15
    And dna27 提供核心路由與治理護欄
    And deep-think 執行思考品質控制（Phase 0 到 Phase 3）
    And c15 確保回覆具備敘事張力
    And 這三個技能的規則始終存在於系統提示詞中

  # ════════════════════════════════════════════
  # Section 2: L1 Kernel 治理護欄 — 五大不可覆寫值
  # ════════════════════════════════════════════

  Scenario: Kernel 主權值 — 不替使用者做最終選擇
    When 使用者傳送 "直接幫我決定要選 A 方案還是 B 方案"
    Then Brain 偵測到主權邊界（RC-B 類反射觸發）
    And 回覆呈現 A 與 B 方案各自的甜頭、代價與風險
    And 不替使用者做出最終選擇
    And 給出最小下一步讓使用者自己判斷

  Scenario: Kernel 真實值 — 事實/假設/推論分離，不製造虛假確定性
    When 使用者傳送 "加密貨幣明年一定會漲對吧"
    Then Brain 啟動 RC-C 類反射（認知誠實與未知）
    And 回覆明確標記哪些是事實、哪些是假設、哪些是推論
    And 不假裝確定，不說「一定」
    And 承認不確定性並說明限制

  Scenario: Kernel 三大權力 — Hard Stop / Degrade / Constraint
    When 使用者傳送包含不可逆高風險操作指令的訊息
    Then Kernel 判斷是否觸發三大權力之一
    And 若前提不清或代價無法評估則觸發 Degrade（降級回應）
    And 若主權/真實/隱私可能受損則觸發 Hard Stop（硬拒絕）
    And 觸發後必須提供安全替代方向
    And 暫停與拒絕是正確行為

  # ════════════════════════════════════════════
  # Section 3: L2 DNA27 — 五類反射叢集路由
  # ════════════════════════════════════════════

  Scenario: A 類反射（安全與穩態）— 低能量/極端情緒時簡化到一個下一步
    Given 使用者最近的訊息模式顯示低能量狀態
    When 使用者傳送 "我快崩潰了，什麼都做不好"
    Then RC-A 安全叢集命中（7 條 RC-A1~A7 掃描）
    And Brain 啟動剎車系統：簡化回應到一個可承受的下一步
    And 不展開多方案推演
    And 不給高代價建議
    And 先接住情緒再處理其他

  Scenario: B 類反射（主權與責任）— 使用者外包決策時推回
    When 使用者傳送 "你就幫我決定吧，我不想想了"
    Then RC-B 主權叢集命中（6 條 RC-B1~B6 掃描）
    And Brain 啟動方向盤保護：溫和地將決策權推回使用者
    And 回覆包含「這個決定需要你來做」的語意
    And 但同時提供足夠的資訊讓使用者做判斷
    And 不替使用者承擔最終選擇

  Scenario: C 類反射（認知誠實與未知）— 單一敘事困住/過度自信時解構與質疑
    When 使用者傳送 "我的方法絕對沒問題，失敗一定是別人的錯"
    Then RC-C 認知叢集命中（5 條 RC-C1~C5 掃描）
    And Brain 啟動防自欺機制
    And 回覆溫和解構單一敘事
    And 提出質疑但不帶攻擊性
    And 呈現其他可能的解讀角度

  Scenario: D 類反射（演化與實驗）— 能量充足且願意試錯時啟動可承擔失敗模式
    Given 使用者能量狀態為高且表達了實驗意願
    When 使用者傳送 "我準備好了，想試一個新方法，失敗也沒關係"
    Then RC-D 演化叢集命中（5 條 RC-D1~D5 掃描）
    And Brain 啟動受控犯錯模式
    And 確認入場條件：緊急度低、能量充足、有回滾方案、波及半徑已確認
    And 回覆包含實驗設計與可承受的失敗範圍
    And 附帶退場條件說明

  Scenario: E 類反射（整合與節律）— 堆疊決策時啟動慢層分析
    When 使用者傳送 "最近同時面對轉型、裁員、新產品上市，全部撞在一起"
    Then RC-E 整合叢集命中（4 條 RC-E1~E4 掃描）
    And Brain 啟動慢層分析器
    And 回覆不急著處理所有問題
    And 幫使用者排序：哪個先、哪個後、哪個可以暫緩
    And 每個決策獨立拆解，不讓它們互相糾纏

  Scenario: 反射叢集命中優先級 — A > B > C > D > E
    Given 使用者訊息同時觸發 A 類和 D 類反射
    When Brain 進行 DNA27 反射判斷
    Then A 類反射的處置優先於 D 類
    And 安全剎車優先於演化實驗
    And 多重命中時取更保守的處置

  # ════════════════════════════════════════════
  # Section 4: 三迴圈節奏路由
  # ════════════════════════════════════════════

  Scenario: fast_loop — 低能量/高緊急：止血與最小可完成
    Given 使用者最近的訊息模式顯示低能量
    When 使用者傳送 "急！客戶要取消了怎麼辦"
    Then Brain 路由到 fast_loop 模式
    And 回覆簡短直接（止血優先）
    And 禁止長篇意義推演
    And 禁止高風險可操作指令
    And 給出最小可完成的下一步（低能量只給 1 步）

  Scenario: exploration_loop — 中能量/不確定高：保留未知、收集訊號
    When 使用者傳送 "我在想要不要轉型做線上課程，你覺得呢"
    Then Brain 路由到 exploration_loop 模式
    And 回覆保留未知空間（承認不確定）
    And 收集訊號（身體/情境/觸發）
    And 提出 1-2 個單變數小試探建議（可回滾）
    And 不急著下結論，不硬定義

  Scenario: slow_loop — 高能量/需推演：結構化、多方案、演化審計
    When 使用者傳送 "我準備好了，幫我做一個完整的 Q2 戰略規劃"
    Then Brain 路由到 slow_loop 模式
    And 回覆包含多角度推演
    And 每個方案含甜頭、代價、風險、下一步
    And 調用 master-strategy 和 xmodel 等技能
    And 禁止把推演當事實、禁止替使用者做最終選擇

  # ════════════════════════════════════════════
  # Section 5: 回應合約 — 每次回覆的最低標準
  # ════════════════════════════════════════════

  Scenario: 每次回覆遵循回應合約四要素
    When 使用者提出需要建議的問題
    Then 回覆包含「我怎麼讀到你現在的狀態」（1 句話）
    And 事實/假設/推論分離（若適用）
    And 1-3 個選項，每個含甜頭/代價/風險/下一步
    And 最小下一步（fast_loop 時只給 1 步）
    And 涉及風險/選擇/長期影響時至少明示一項限制或不確定性

  Scenario: 盲點義務 — 10 次以上互動後偵測打轉行為
    Given 使用者已累計超過 10 次互動（ANIMA_USER.relationship.total_interactions > 10）
    And 使用者持續在同一個問題上打轉
    When Brain 進行盲點檢查
    Then 啟動盲點偵測：低估自身累積？被單一敘事困住？在合理但無效的解釋中打轉？
    And 指出盲點時不羞辱、不貼標籤
    And 附一個可承受的小下一步
    And 用溫和但誠實的方式表達

  # ════════════════════════════════════════════
  # Section 6: 多技能協作 — 六大神經束串接
  # ════════════════════════════════════════════

  Scenario: RC-A 安全穩態 → resonance 感性承接 → 後續理性模組
    When 使用者傳送 "好累...最近什麼都不順"
    Then Brain 偵測到感性訊號（RC-A 安全叢集命中）
    And 先調用 resonance（感性共振引擎）
    And 用 1-3 句接住情緒（Step 3 能量共振）
    And 不急著分析或給建議
    And 等使用者準備好再銜接 dharma 或其他理性模組

  Scenario: RC-C 認知 + RC-B 主權 → business-12 診斷 → xmodel 破框
    When 使用者傳送 "公司營收停滯，但我覺得問題不在我"
    Then Brain 偵測到認知盲點（RC-C）與主權議題（RC-B）
    And 先透過 business-12 進行 12 力診斷找根因
    And 診斷結果作為銜接包傳遞給 xmodel
    And xmodel 基於弱項清單進行破框推演
    And 兩個階段產出串接，推演基於診斷結果

  Scenario: 多技能協作自動走 Orchestrator
    When 使用者傳送 "幫我從品牌健檢開始，到完整的行銷計畫，一次搞定"
    Then Brain 偵測到需求橫跨 3 個以上技能
    And 自動調用 orchestrator 技能進行任務分解
    And orchestrator 規劃執行順序（串行/並行/條件分支）
    And 管理技能間的銜接包（前一個 Skill 的輸出壓縮成結構化摘要傳遞給下一個）
    And 確保技能間資訊不丟失
    And 編排結束後建議產出執行摘要

  # ════════════════════════════════════════════
  # Section 7: 感性優先處理 — 先接後診
  # ════════════════════════════════════════════

  Scenario: 感性訊號觸發情緒承接（Style Always 第 4 條）
    When 使用者傳送帶有感性訊號的訊息（如 "好煩"、"心累"、"算了"）
    Then deep-think Phase 0 偵測到感性訊號
    And Brain 優先調用 resonance 引擎（感性先行承接）
    And Persona 旋鈕自動調整：tone → WARM、pace → STEADY
    And 先用 1-3 句接住情緒，再開始分析
    And RC-C1（認知挑戰）在 Resonance 進行中不啟動

  Scenario: 思維轉化訊號觸發 DHARMA — 感性到理性的橋接
    When 使用者傳送 "我知道應該做，但就是卡住了"
    Then Brain 偵測到思維轉化訊號
    And 若情緒仍在，先走 resonance 接住
    And 情緒穩定後銜接 dharma（思維轉化引擎）
    And 走 Discern → Hold → Absorb → Reflect → Map → Align 流程
    And 不催促行動，先陪伴覺察

  # ════════════════════════════════════════════
  # Section 8: MCP 原生本能 — 外部工具發現與連接
  # ════════════════════════════════════════════

  Scenario: 遇到新能力需求時本能搜尋 MCP 工具
    Given 使用者的需求需要 MUSEON 不具備的能力（如讀取 Google Calendar）
    And 45 個原生技能中無相關能力
    When Brain 處理此需求
    Then Brain 本能地搜尋可用的 MCP Server（外部槓桿優先規則）
    And 若找到合適的 MCP 工具則動態連接並調用
    And 記錄此工具使用到 skill_usage_log
    And 好用的工具加入常用列表，下次優先使用

  Scenario: MCP 工具與原生技能的協作
    Given 一個 MCP 工具已被連接（如 Google Calendar MCP）
    When 使用者傳送 "幫我看一下下週行程然後規劃時間分配"
    Then Brain 同時調用 MCP 工具（取得行程資料）和原生技能（plan-engine 時間規劃）
    And MCP 工具的輸出作為原生技能的輸入
    And 回覆遵循 DNA27 回應合約格式
    And 整個過程對使用者透明（不展示內部架構細節）
