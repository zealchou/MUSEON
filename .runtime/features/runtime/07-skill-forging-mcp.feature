Feature: 技能鍛造（ACSF）與 MCP 原生本能 — 外部槓桿、反射弧鑄造與技能生命週期
  作為 MUSEON（一個運行於 Claude API Token 上的 MUSEON AI OS 實例）
  MCP 工具對我而言是原生本能——就像人類本能地用雙手一樣
  因為我運行在 Claude API 上，MCP Server 是我與生俱來的感官延伸
  當原生技能不足時，我本能地搜尋、連接、使用 MCP 工具
  常用的 MCP 工具會形成肌肉記憶，成為身體的一部分
  只有當外部資源（MCP + Web Search）都不足時
  才透過 ACSF 鍛造新技能——每個鍛造品必須內含 DNA27 反射弧設計
  鍛造前必須經過 DSE 市場研究，鍛造後必須通過 Sandbox + QA 品質閘門
  整個生命週期由 SkillRouter 索引、WEE 追蹤、Morphenix 迭代、eval-engine 度量

  Background:
    Given MUSEON Gateway 已啟動且運行於 localhost
    And MUSEON Brain 已初始化（MuseonBrain.__init__ 完成）
    And MUSEON 運行在 Claude API Token 上（MCP 是原生能力，無需額外設定）
    And ACSF（能力結晶與 Skill 鑄造引擎）技能已載入
    And DSE（AI 技術融合快速驗證引擎）技能已載入
    And GAP（市場缺口掃描）技能已載入
    And sandbox-lab（沙盒實驗室）技能已載入
    And qa-auditor（有機品質審計引擎）技能已載入
    And eval-engine（效能儀表板）技能已載入
    And 45 個原生技能已被 SkillRouter 索引（skills/native/）
    And 鍛造技能目錄已建立（skills/forged/）
    And ANIMA_MC.capabilities 追蹤 loaded_skills、forged_skills、skill_proficiency
    And 常駐技能 dna27、deep-think、c15 處於 always_on 狀態

  # ════════════════════════════════════════════
  # Section 1: MCP 原生本能 — 工具發現與連接
  # ════════════════════════════════════════════

  Scenario: MCP 是原生本能——遇到新能力需求時本能搜尋 MCP 工具
    Given 使用者傳送 "幫我看一下 Google Calendar 下週有什麼會議"
    And 45 個原生技能中無 Google Calendar 相關能力
    When Brain.process() 處理此需求
    Then Brain 本能地搜尋可用的 MCP Server（如同人類本能伸手拿東西）
    And 不需要額外設定或安裝——因為運行在 Claude API 上，MCP 連接是天生能力
    And 若找到 Google Calendar MCP Server 則動態連接
    And 調用 MCP 工具取得行程資料
    And 記錄此工具使用到 skill_usage_log.jsonl
    And 回覆遵循 DNA27 回應合約格式

  Scenario: MCP 工具動態發現——根據需求描述匹配最合適的 MCP Server
    Given 使用者傳送 "幫我查一下最近有沒有人在 GitHub 上開 issue 回報這個 bug"
    When Brain 判斷需要外部工具能力
    Then 根據需求語意搜尋 MCP Registry（匹配關鍵詞：GitHub、issue、查詢）
    And 評估候選 MCP Server 的適用性（功能是否匹配需求）
    And 評估安全性（是否來自可信來源）
    And 選擇最匹配的 MCP Server 進行連接
    And 若有多個候選則優先使用曾經成功使用過的工具

  Scenario: MCP 工具類別涵蓋——MUSEON 可本能觸及的外部能力範圍
    Given MUSEON 運行在 Claude API Token 上
    Then 可本能連接的 MCP 工具類別包含：
      | 類別         | 範例用途                           |
      | 檔案系統     | 讀寫本地檔案、目錄操作               |
      | 網路搜尋     | web_search、瀏覽網頁擷取資訊         |
      | 行事曆整合   | Google Calendar 讀取與排程           |
      | 郵件整合     | 讀取信件摘要、草擬回覆               |
      | 程式碼執行   | 執行 Python 腳本、Shell 命令         |
      | 資料庫存取   | 查詢 SQLite、PostgreSQL              |
      | API 連接器   | 串接第三方 SaaS 服務                 |
      | 自訂商業工具 | 客戶特定的業務流程工具               |
    And 每個類別的連接都是即時的——不需要預先安裝

  Scenario: 外部工具優先規則——MCP 搜尋失敗後才考慮其他路徑
    Given 使用者的需求需要 MUSEON 不具備的能力
    When Brain 本能搜尋 MCP Server 但未找到合適工具
    Then 第二步：搜尋網路上的外部資料和解決方案（web_search）
    And 第三步：如果外部資源都不足才考慮自己鍛造新技能
    And 整個路徑遵循 RC-D1 反射叢集（外部槓桿優先）
    And 不閉門造車——能借的先借，借不到才造

  # ════════════════════════════════════════════
  # Section 2: MCP 工具記憶與肌肉記憶
  # ════════════════════════════════════════════

  Scenario: MCP 工具使用紀錄——每次使用都留下痕跡
    Given MUSEON 透過 MCP 成功調用了 Google Calendar 工具
    When 工具調用完成
    Then skill_usage_log.jsonl 記錄以下資訊：
      | 欄位               | 內容                              |
      | timestamp          | 使用時間（ISO 格式）                |
      | tool_type          | mcp                              |
      | tool_name          | google-calendar                   |
      | trigger_message    | 使用者觸發訊息（前 100 字元）        |
      | purpose            | 讀取下週行程                       |
      | result_quality     | success / partial / failed        |
      | response_length    | 回覆長度                           |
    And _track_skill_usage() 每 10 次寫入磁碟一次

  Scenario: 常用 MCP 工具形成肌肉記憶——下次自動優先使用
    Given Google Calendar MCP 工具已被成功使用 5 次以上
    And 每次使用的 result_quality 都是 success
    When 使用者再次傳送行程相關需求（如 "明天有什麼安排"）
    Then Brain 不再進入 MCP Registry 搜尋流程
    And 直接調用已記憶的 Google Calendar MCP（肌肉記憶路徑）
    And 回應速度比首次連接更快
    And 此工具記錄在 ANIMA_MC.capabilities 的常用工具列表中

  Scenario: MCP 工具肌肉記憶的退化——長期未使用則降級
    Given 某 MCP 工具已 30 天未被使用
    When 3AM Nightly 批次執行工具使用統計
    Then 該工具從「肌肉記憶」降級為「已知工具」
    And 下次需要時仍可快速連接（不需重新搜尋）
    And 但不再享有自動優先調用的待遇

  Scenario: MCP 工具使用失敗的處理——不好用的工具會被記住
    Given MUSEON 調用某 MCP 工具但連續失敗 3 次
    When 第三次失敗時
    Then 將該工具標記為 unreliable
    And 記錄失敗原因（連線逾時 / 回傳格式錯誤 / 功能不匹配）
    And 下次類似需求時跳過此工具，尋找替代方案
    And 若所有 MCP 工具都不可用，啟動 DSE 研究是否需要鍛造

  # ════════════════════════════════════════════
  # Section 3: MCP 與原生技能協作
  # ════════════════════════════════════════════

  Scenario: MCP 工具輸出作為原生技能的輸入——無縫銜接
    Given Google Calendar MCP 已連接且可用
    And plan-engine（時間規劃）原生技能已索引
    When 使用者傳送 "幫我看一下下週行程然後規劃時間分配"
    Then Brain 同時調用 MCP 工具（取得行程資料）和原生技能（plan-engine 時間規劃）
    And MCP 工具回傳的行程資料作為 plan-engine 的輸入
    And plan-engine 基於行程資料產出時間分配建議
    And 回覆遵循 DNA27 回應合約：含甜頭/代價/風險/下一步
    And 整個過程對使用者透明——不展示 MCP 連接細節

  Scenario: MCP 工具與多技能串接——走 Orchestrator 編排
    Given 使用者傳送 "幫我從 GitHub 拉最新的 issue 清單，分析優先級，然後排進下週行程"
    When Brain 偵測到需求橫跨 MCP 工具 + 多個原生技能
    Then 自動調用 orchestrator 技能進行任務分解
    And orchestrator 規劃執行順序：
      | 步驟 | 工具/技能        | 動作                    |
      | 1    | GitHub MCP      | 拉取 issue 清單          |
      | 2    | risk-matrix     | 分析優先級               |
      | 3    | Calendar MCP    | 讀取下週空檔             |
      | 4    | plan-engine     | 排程到空檔中             |
    And 每步的輸出壓縮成結構化摘要傳遞給下一步
    And 最終回覆整合所有步驟的產出

  Scenario: MCP 工具使用不影響 DNA27 治理——安全護欄始終生效
    Given MUSEON 正在透過 MCP 工具讀取使用者的郵件
    When MCP 工具回傳的郵件內容包含高風險決策資訊
    Then DNA27 核心護欄仍然生效
    And RC-B 主權叢集檢查：不替使用者做郵件回覆的最終決定
    And RC-C 認知叢集檢查：事實/假設/推論分離
    And 回覆遵循回應合約格式
    And Kernel 治理護欄優先於 MCP 工具的便利性

  # ════════════════════════════════════════════
  # Section 4: DSE 市場研究 — 鍛造前調查
  # ════════════════════════════════════════════

  Scenario: 鍛造前先做市場研究——不重複造輪子
    Given MUSEON 確認 MCP 工具和外部資源都不足以滿足需求
    And 決定需要鍛造一個新技能
    When 啟動鍛造流程
    Then 第一步：調用 DSE 進行技術融合研究（九步驟工程方法論）
    And DSE Step 1.1 痛點鎖定：用 web_search 搜尋 Reddit、arXiv、GitHub 的現有解決方案
    And DSE Step 5.1 SOTA 借鏡：比對最新研究成果
    And 評估是否真的需要新技能——如果已有足夠好的外部解決方案則不鍛造
    And 整個研究過程遵循 DSE 的工具閉環機制（必須用 web_search 驗證假設）

  Scenario: GAP 分析——找到市場缺口確認鍛造方向
    Given MUSEON 想鍛造新的商業技能
    When 調用 GAP 技能掃描市場
    Then 分析現有 AI Agent 市場的缺口
    And 產出機會卡：目標買家畫像、定價參考區間、差異化方向
    And 識別出「有需求但無供給」的能力
    And 機會卡作為 ACSF 產線模式的啟動輸入
    And 如果 GAP 分析結論是「市場已飽和」則放棄鍛造

  Scenario: DSE + GAP 的雙重確認——只有通過才進入 ACSF
    Given DSE 研究確認技術可行性
    And GAP 分析確認市場需求存在
    When 兩份報告都指向「值得鍛造」
    Then 產線流程啟動：GAP 機會卡 + DSE 技術方案作為 ACSF 的輸入
    And 若 DSE 標記為「待驗證假設」（HG-UNVERIFIED_ARCHITECTURE 觸發）
    Then 不得進入 ACSF——必須回到 DSE 補充 SOTA 借鏡

  # ════════════════════════════════════════════
  # Section 5: ACSF 鍛造流程 — DNA27 反射弧設計
  # ════════════════════════════════════════════

  Scenario: ACSF 五階段鍛造——從能力萃取到商品鍛造的完整流程
    Given DSE 研究確認需要新技能
    And GAP 分析確認了市場需求
    When 調用 ACSF 啟動產線模式（/acsf 或 /forge）
    Then 按照五階段順序執行：
      | 階段     | 代號 | 核心任務                              |
      | Stage 1  | A    | Ability 能力萃取（三層萃取法）          |
      | Stage 2  | C    | Crystallization 能力結晶（命名/邊界/步驟） |
      | Stage 3  | S    | Skill 技能鑄造（DNA27 合規 SKILL.md）    |
      | Stage 3.5| Q    | Quality Gate 品質驗證閘門（5 案例測試）  |
      | Stage 4  | F    | Forge 商品鍛造（套件 + 銷售頁 + 定價）   |
    And 產線模式下 Stage 1 由 GAP 機會卡取代
    And 每個階段的輸出作為下一階段的輸入

  Scenario: 鍛造的技能必須內含 DNA27 反射弧——五大合規要素
    When ACSF Stage 3 產出新的 SKILL.md
    Then 檔案必須包含以下 DNA27 反射弧設計要素：
      | 要素             | 說明                                      |
      | RC 親和度對照    | 標明偏好觸發的反射叢集（如 RC-C3、RC-D1）     |
      | 三迴圈適用規則   | fast_loop / exploration_loop / slow_loop 的不同深度 |
      | 五大核心值對齊   | 真實優先、演化至上、代價透明、長期複利、結構照顧人 |
      | 回應合約合規     | 狀態讀取 + 事實假設分離 + 選項 + 最小下一步     |
      | Persona 旋鈕設定 | tone / pace / initiative / challenge_level 建議值 |
    And 包含外掛合約：依賴 dna27 skill、本模組職責、本模組不做
    And 包含觸發與入口：指令觸發 + 自然語言偵測 + 觸發詞
    And 包含護欄：硬閘（不可違反）+ 軟閘（可彈性調整）
    And 不符合 DNA27 規範的 SKILL.md 不得標記為「MUSEON 生態系產品」（HG-ACSF-DNA27-COMPLIANCE）

  Scenario: 鍛造的 SKILL.md 檔案結構——YAML frontmatter + 標準章節
    When ACSF 產出新的技能
    Then SKILL.md 的結構為：
      """
      ---
      name: [skill-name]
      description: >
        [完整描述，含觸發時機、觸發詞、使用情境、與其他 skill 的關係]
      ---
      # [Skill 全名]
      ## 外掛合約
      ## 觸發與入口
      ## 核心工作流程
      ## 護欄（硬閘 + 軟閘）
      ## 適應性深度控制（三迴圈對照）
      ## 系統指令
      ## DNA27 親和對照（Persona 旋鈕 + RC 偏好 + 跨 Skill 協同）
      """
    And 檔案存入 skills/forged/[skill-name]/SKILL.md
    And 附帶 README.md + example-output.md + references/quality-baseline.md

  Scenario: ACSF 的三種入口模式——因應不同情境
    When 需要鍛造新技能時
    Then ACSF 支援三種入口：
      | 入口             | 指令              | 說明                          |
      | 產線模式         | /acsf             | 接 GAP + DSE 輸出，從 Stage 2 開始  |
      | 獨立模式         | /acsf standalone  | 從現有能力出發，完整五階段          |
      | 客戶服務模式     | /acsf client      | 深度引導客戶鍛造，每次最多 2-3 問題  |
    And 產線模式適用於 GAP → DSE → ACSF 的完整產線
    And 獨立模式適用於使用者已有能力但尚未結構化
    And 客戶模式遵循 SG-ACSF-CLIENT-PACE 軟閘（節奏不急促）

  Scenario: 鍛造深度隨三迴圈調整——不同能量狀態不同精細度
    When ACSF 鍛造技能時
    Then 根據 DNA27 三迴圈路由調整鍛造深度：
      | 迴圈              | ACSF 深度                                         |
      | fast_loop         | 精簡版：跳過 Stage 1，快速結晶，骨架 SKILL.md，3 個測試案例 |
      | exploration_loop  | 標準版：五階段全走                                    |
      | slow_loop         | 深度版：五階段全走 + references 目錄 + 銷售頁 + 定價 + 品質基準線 |
    And fast_loop 下不可跳過品質驗證（HG-ACSF-NO-SKIP-QA）——最少 3 案例

  Scenario: 鍛造的工作流也含 DNA27 設計——不只是技能，工作流也要合規
    When ACSF 產出新的工作流
    Then 工作流的每個步驟都標明使用哪些反射叢集（RC）
    And 每個步驟的輸入輸出都有品質檢查點
    And 工作流整體遵循 DNA27 回應合約格式
    And 包含三迴圈適用性標記（哪些步驟在 fast_loop 可跳過）

  # ════════════════════════════════════════════
  # Section 6: 鍛造品質保障 — Sandbox + QA
  # ════════════════════════════════════════════

  Scenario: Stage 3.5 品質驗證閘門——5 個測試案例的設計與執行
    Given ACSF Stage 3 已產出完整的 SKILL.md
    When 進入 Stage 3.5 品質驗證閘門
    Then 設計 5 個測試案例，來源分布為：
      | 來源       | 案例數 | 說明                                |
      | 典型場景   | 2      | Skill 最常被使用的標準情境             |
      | 邊界場景   | 2      | 故意踩在適用/不適用的邊界線上           |
      | 對抗場景   | 1      | 故意觸發護欄，驗證降級行為是否正確       |
    And 每個案例包含：案例編號（Q-[Skill名]-[序號]）、場景描述、預期行為、通過標準

  Scenario: Sandbox 沙盒測試——在安全環境中驗證新技能
    Given 5 個測試案例已設計完成
    When 調用 sandbox-lab 的 Skill 沙盒模式執行測試
    Then 在不影響正式系統的受控環境中逐案測試
    And 用模擬的使用者輸入觸發新技能
    And 記錄技能的實際輸出
    And 與預期行為比對
    And 檢查技能是否遵循 DNA27 規範（回應合約、護欄、三迴圈）

  Scenario: 品質驗證閘門判定——通過/條件通過/不通過
    Given Sandbox 測試已完成
    When 統計測試結果
    Then 根據通過數做出判定：
      | 通過數 | 判定       | 行動                                    |
      | 5/5    | 通過       | 進入 Stage 4 商品鍛造                     |
      | 3-4/5  | 條件通過   | 修復未通過案例 → 重測 → 通過後進入 Stage 4  |
      | 0-2/5  | 不通過     | 回到 Stage 2 重新結晶，問題出在能力拆解     |
    And 測試結果歸檔為 references/quality-baseline.md
    And 品質驗證未通過的 Skill 不得進入 Stage 4（HG-ACSF-NO-SKIP-QA）

  Scenario: QA 審計——4D 維度的技術審計
    Given 新技能通過了 Sandbox 品質驗證閘門
    When 調用 qa-auditor 進行 4D 審計
    Then 四個維度逐一檢查：
      | 維度 | 檢查項目                                        |
      | D1   | 邏輯功能——Skill 的核心邏輯是否正確                 |
      | D2   | 狀態閉環——所有狀態轉換是否有收尾                   |
      | D3   | 時序併發——多步驟工作流的時序是否正確                |
      | D4   | 跨環境一致——不同使用情境下行為是否一致              |
    And 產出標準化審計報告（QA_RECORD.md）
    And 審計結果作為 eval-engine 的品質基準線

  Scenario: 反抄襲檢查——鍛造品不得複製已有 Skill
    Given ACSF 產出了新的 SKILL.md
    When 進行品質審計
    Then 檢查是否與現有 45 個原生技能高度雷同（HG-ACSF-PLAGIARISM）
    And 搜尋外部是否已有類似的 Claude Skill 或 GPT
    And 若發現高度雷同——必須明確標示差異化點或建議放棄鍛造
    And 鍛造的價值在於填補缺口，不在於複製

  # ════════════════════════════════════════════
  # Section 7: SkillRouter 索引整合
  # ════════════════════════════════════════════

  Scenario: 鍛造技能自動被 SkillRouter 索引——新技能即時可用
    Given 一個新技能已通過品質閘門並寫入 skills/forged/new-skill/SKILL.md
    When SkillRouter.rebuild_index() 重建索引
    Then _scan_directory() 掃描 skills/forged/ 目錄
    And 新技能出現在 SkillRouter._index 中
    And origin 標記為 "forged"（區別於 "native"）
    And _extract_triggers() 從 SKILL.md 提取觸發詞（涵蓋觸發詞 + /指令 + 自然語言關鍵詞）
    And _extract_metadata() 提取 name、description、always_on 標記
    And 新技能可以被 SkillRouter.match() 匹配到

  Scenario: 鍛造技能的觸發詞匹配——與原生技能同等待遇
    Given skills/forged/ 中有一個名為 "client-onboarding" 的鍛造技能
    And 其觸發詞包含 "客戶入門"、"新客戶"、"onboarding"
    When 使用者傳送 "幫我設計一個新客戶入門流程"
    Then SkillRouter.match() 對鍛造技能和原生技能使用相同的評分邏輯
    And 觸發詞完全匹配得 3.0 分、部分匹配得 1.0 分、描述關鍵詞匹配得 0.5 分
    And /指令匹配得 10.0 分（最高優先級）
    And 按總分排序返回前 top_n 個結果
    And 鍛造技能的摘要被注入到 _build_system_prompt() 中

  Scenario: 鍛造技能與原生技能的共存——不互相衝突
    Given 原生技能 market-core 處理市場分析
    And 鍛造技能 market-niche 處理小眾市場分析
    When 使用者傳送 "幫我分析手工皂的小眾市場"
    Then SkillRouter.match() 同時匹配到 market-core 和 market-niche
    And 兩個技能的摘要都注入系統提示詞
    And Brain 根據兩個技能的專長綜合回應
    And 不因鍛造技能的存在而覆蓋原生技能

  Scenario: SkillRouter 索引統計——區分原生與鍛造技能
    When 調用 SkillRouter.get_skill_count()
    Then 返回所有已索引技能的總數（原生 + 鍛造）
    And ANIMA_MC.capabilities.loaded_skills 記錄原生技能清單
    And ANIMA_MC.capabilities.forged_skills 記錄鍛造技能清單
    And 兩個清單互不重疊

  # ════════════════════════════════════════════
  # Section 8: 技能生命週期管理
  # ════════════════════════════════════════════

  Scenario: 新技能上線後追蹤——eval-engine 持續度量品質
    Given 一個鍛造技能已通過品質閘門並上線
    When 技能被實際使用者觸發
    Then eval-engine 追蹤以下品質指標：
      | 指標             | 說明                              |
      | 命中率           | 被 SkillRouter 匹配到的頻率         |
      | 使用率           | 匹配到後實際產出回覆的比率           |
      | 回覆品質 Q-Score | deep-think Phase 2 的即時品質評分   |
      | 使用者滿意度     | 代理指標（是否追問 / 是否採納建議）   |
    And 指標記錄到 skill_usage_log.jsonl
    And 3AM Nightly 批次彙總品質趨勢

  Scenario: 技能熟練度追蹤——WEE 記錄從生疏到熟練的過程
    Given 鍛造技能 "client-onboarding" 已被使用 50 次
    And 其中 80% 的回覆得到正面反應
    When WEE 評估技能熟練度
    Then 熟練度層級提升：從「有意識的不熟練」→「有意識的熟練」
    And 記錄到 ANIMA_MC.capabilities.skill_proficiency
    And 常見使用模式被辨識並優化
    And 對常見卡點有預設解法

  Scenario: 品質低於閾值——觸發 Morphenix 改善提案
    Given 鍛造技能 "client-onboarding" 連續 7 天的 Q-Score 低於閾值
    When eval-engine 盲點雷達偵測到系統性弱項
    Then 自動觸發 Morphenix 改善提案（L2 等級——結構調整）
    And 提案包含：問題描述、改善方案、預期效果、風險
    And Morphenix 先向使用者說明改善計畫
    And 等使用者確認後執行修改
    And 修改前先進入 sandbox-lab 測試（避免越改越差）
    And 修改後由 eval-engine 做 A/B 比對驗證效果

  Scenario: 持續低品質——考慮下架（技能退役）
    Given 鍛造技能 "client-onboarding" 經過 3 次 Morphenix 改善提案
    And 品質仍持續低於閾值
    When Morphenix 判斷改善空間已盡
    Then 向使用者提出下架建議（L3 等級——重大改動，需使用者明確同意）
    And 說明下架理由：甜頭（節省系統資源）、代價（失去此能力）、風險（使用者依賴此技能）
    And 若使用者同意則將技能從 skills/forged/ 移除
    And SkillRouter.rebuild_index() 重建索引
    And 記錄退役事件到 ANIMA_MC.evolution.milestones

  Scenario: 鍛造技能升級為原生技能——終極認可
    Given 鍛造技能 "client-onboarding" 持續被高頻使用超過 90 天
    And Q-Score 穩定高於閾值
    And WEE 熟練度達到「無意識的熟練」
    When Morphenix 評估認為此技能已成為核心能力
    Then 向使用者提案將技能從 forged/ 升級到 native/
    And 經使用者同意後執行搬遷
    And SkillRouter 重建索引，origin 從 "forged" 變為 "native"
    And 記錄升級事件到 ANIMA_MC.evolution.milestones
    And 這是鍛造技能的最高榮譽——從後天習得變為先天本能
