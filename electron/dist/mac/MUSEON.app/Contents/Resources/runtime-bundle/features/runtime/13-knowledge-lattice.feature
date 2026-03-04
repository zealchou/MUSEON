Feature: Knowledge-Lattice — 知識晶格結晶化引擎、Crystal Protocol 與再結晶系統
  作為 MuseClaw 的結構化知識累積系統
  我將對話中驗證過的洞見、失敗教訓、成功模式
  萃取為可索引、可連結、可演化的知識結晶（Crystal）
  形成跨對話持續成長的智慧資產網路
  融合 Crystal Protocol（四類結晶 × GEO 四層 × 再結晶演算法）
  與 Crystal Chain Protocol（CUID × DAG × 共振指數）
  核心命題：知識量本身無用，知識的結構、連結、可用性才是關鍵

  Background:
    Given MuseClaw Brain 已初始化
    And Knowledge-Lattice 模組已載入
    And 結晶存儲路徑為 data/knowledge/crystals/
    And 結晶索引路徑為 data/knowledge/index.json
    And DNA27 六層記憶系統可用
    And deep-think Phase 2 審計可用（結晶品質閘）
    And 結晶 DAG（有向無環圖）已初始化

  # ════════════════════════════════════════════
  # Section 1: 四種結晶類型 — Crystal Protocol
  # ════════════════════════════════════════════

  Scenario: Insight 型結晶 — 已驗證的原理或因果關係
    Given 使用者和 MuseClaw 經過深入分析確認了一個原理
    When 結晶化流程被觸發
    And 結晶類型被判定為 Insight
    Then 結晶包含：
    And crystal.type = "Insight"
    And crystal.verification.level = "proven" 或 "tested"
    And Insight 代表最高層級的知識——已經跨情境驗證
    And Insight 型結晶為永久性（除非被新證據推翻）

  Scenario: Pattern 型結晶 — 反覆出現的成功/失敗模式
    Given 同一個因果模式在 3 次以上的觀察中反覆出現
    When 結晶化流程被觸發
    And 結晶類型被判定為 Pattern
    Then crystal.type = "Pattern"
    And crystal.verification.level = "observed"
    And Pattern 是半永久的——隨環境變化可能衰退
    And Pattern 可升級為 Insight（跨情境驗證後）

  Scenario: Lesson 型結晶 — 從錯誤中提取的預防知識
    Given MuseClaw 在一次服務中犯了錯誤
    And 根因分析已完成
    When 結晶化流程被觸發
    And 結晶類型被判定為 Lesson
    Then crystal.type = "Lesson"
    And crystal.verification.level = "observed"
    And Lesson 是演化型的——可升級為 Insight
    And Lesson 與 Soul Ring 的 failure_lesson 互相參照
    And Lesson 是免疫系統的養分

  Scenario: Hypothesis 型結晶 — 尚未驗證的候選知識
    Given MuseClaw 觀察到一個初步現象但證據不足
    When 結晶化流程被觸發
    And 結晶類型被判定為 Hypothesis
    Then crystal.type = "Hypothesis"
    And crystal.verification.level = "hypothetical"
    And Hypothesis 有 30 天的驗證窗口
    And 30 天內未被驗證則自動標記為待清理
    And Hypothesis 成功應用 3 次以上 → 建議升級為 Pattern

  # ════════════════════════════════════════════
  # Section 2: GEO 四層結構 — 每顆結晶的內容格式
  # ════════════════════════════════════════════

  Scenario: G1 摘要說明 — 一句話核心知識
    When 一顆結晶的 G1 層被撰寫
    Then G1 必須是一句話的核心摘要
    And 通過「五歲小孩也能懂」測試（詞彙複雜度 < 小四程度）
    And 通過「電梯測試」（30 秒內可向非專業人士解釋）
    And G1 是結晶的門面——快速理解的入口

  Scenario: G2 MECE 結構 — 互斥完備的拆解
    When 一顆結晶的 G2 層被撰寫
    Then G2 包含 2~5 個面向的 MECE 拆解
    And 各面向之間互不重疊（Mutually Exclusive）
    And 合在一起完整涵蓋（Completely Exhaustive）
    And 冗餘率必須 < 10%（系統自動檢查）
    And 若冗餘率 > 10% 則提示使用者合併

  Scenario: G3 問題背後的問題 — Root Inquiry
    When 一顆結晶的 G3 層被撰寫
    Then G3 至少追問一層「為什麼」
    And 表面問題是什麼？更深層的系統性失衡是什麼？
    And G3 防止結晶停留在症狀層面
    And 鼓勵找到真正的原因而非表面的解法

  Scenario: G4 洞見與反思 — 行動原則與限制條件
    When 一顆結晶的 G4 層被撰寫
    Then G4 包含可行動的原則（Actionable）
    And G4 包含限制條件（何時這個結論會失效？）
    And G4 是結晶最珍貴的部分——知道邊界的知識才是真知識

  # ════════════════════════════════════════════
  # Section 3: 結晶化五步驟流程
  # ════════════════════════════════════════════

  Scenario: Step 1 — 原始捕獲
    When 結晶化流程啟動
    Then 系統記錄觸發情境：對話摘要、原始陳述、相關技能
    And 判定結晶類型（Insight / Pattern / Lesson / Hypothesis）
    And 生成初始結構框架

  Scenario: Step 2 — 結構精煉（GEO 打磨）
    Given Step 1 完成原始捕獲
    When 進入結構精煉
    Then 逐層填寫 G1~G4
    And G1: 一句話摘要 → 電梯測試
    And G2: MECE 拆解 → 冗餘率檢查（< 10%）
    And G3: Root Inquiry → 至少一層「為什麼」
    And G4: 洞見 + 限制 → 識別失效條件

  Scenario: Step 3 — 連結發現
    Given Step 2 完成結構精煉
    When 系統掃描現有結晶網路
    Then 自動識別語義相關的結晶
    And 為每個關聯設定關係類型：
      | 關係類型    | 說明                          |
      | cite        | 引用（A 基於 B 的結論）       |
      | fork        | 分支（A 是 B 的特化版本）     |
      | merge       | 合併候選（A 和 B 高度重疊）   |
      | contradict  | 矛盾（A 和 B 結論相反）       |
    And 若偵測到矛盾 → 兩顆結晶都標記為 "pending recrystallization"

  Scenario: Step 4 — 品質閘檢查（四道 Gate）
    Given Step 3 完成連結發現
    When 結晶進入品質閘檢查
    Then 四道 Gate 依序驗證：
      | Gate | 名稱     | 檢查內容                                     |
      | G0   | 合法性   | 無偏見、無傷害、無智財侵權                   |
      | G1   | 完整性   | G1~G4 四層全部填寫                           |
      | G2   | 結構性   | MECE 冗餘率 < 10%                            |
      | G3   | 驗證性   | 驗證等級已標明（hypothetical~proven）         |
    And 所有 Gate 通過 → 進入 Step 5
    And 未通過的 Gate → 標記問題，提示使用者修復

  Scenario: Step 5 — 註冊入庫
    Given Step 4 所有 Gate 通過
    When 結晶被註冊入庫
    Then 生成 CUID（格式：KL-{type}-{seq}，如 KL-Insight-0042）
    And 計算初始共振指數（Resonance Index）
    And 寫入結晶存儲（data/knowledge/crystals/{cuid}.json）
    And 更新結晶 DAG（有向無環圖）
    And 更新索引（data/knowledge/index.json）
    And 通知使用者結晶化成功

  # ════════════════════════════════════════════
  # Section 4: CUID 與 Crystal Chain — 身份與連結
  # ════════════════════════════════════════════

  Scenario: CUID 唯一識別碼格式
    When 一顆結晶被註冊
    Then CUID 格式為 KL-{Type}-{四位序號}
    And 例如：KL-Insight-0042、KL-Lesson-0017
    And CUID 一旦分配不可變更
    And CUID 是結晶在 DAG 中的唯一節點 ID

  Scenario: Crystal DAG — 知識的有向無環圖
    Given 結晶 A 引用了結晶 B 和 C
    When 連結關係被建立
    Then DAG 中新增邊：A → B（cite）, A → C（cite）
    And DAG 不允許環路（結晶不能循環引用自己）
    And DAG 用於快速追蹤知識的繼承和衍生關係
    And 從任一結晶出發，可在 2 hop 內找到所有相關結晶

  Scenario: 共振指數計算（Resonance Index）
    Given 一顆結晶被創建後在多次對話中被引用
    When 系統計算共振指數
    Then RI = Σ [ 0.3×Freq + 0.4×Depth + 0.3×Quality ] × Decay(Δt)
    And Freq = 使用頻率（0~1 正規化）
    And Depth = 應用深度（理論 0.2 / 設計 0.4 / 部署 0.6 / 產出 0.8 / 影響 1.0）
    And Quality = 結果品質（0~1）
    And Decay = exp(-0.03 × 天數)（90 天半衰期）
    And 解讀：RI > 0.7 核心知識 / 0.2~0.7 活躍知識 / < 0.2 候選知識

  # ════════════════════════════════════════════
  # Section 5: 語義召回 — 知識檢索
  # ════════════════════════════════════════════

  Scenario: /recall 語義搜尋
    When 使用者執行 /recall "系統創業方法論"
    Then 系統對所有結晶執行語義相似度搜尋
    And 返回 Top 5 結果，按共振指數排序
    And 每條結果顯示：CUID、G1 摘要、類型、RI、驗證等級
    And 高 RI 結晶標記為 [verified: tested/proven]
    And 低 RI 結晶標記為 [verified: hypothetical]

  Scenario: 自動結晶召回 — 使用者引用過往結論
    Given 使用者在對話中提到一個之前的結論
    When Brain.process() 偵測到引用
    Then 自動檢索相關結晶
    And 若找到匹配 → 顯示結晶摘要供使用者確認
    And 若結晶與當前陳述矛盾 → 標記矛盾供使用者注意
    And 自動召回增強知識的一致性

  Scenario: 對話中主動推送相關結晶
    Given 使用者遇到一個之前處理過的類似問題
    When Brain.process() 偵測到問題模式相似
    Then 系統主動推送：「這與結晶 KL-Pattern-0023 相關：[G1 摘要]」
    And 推送不強制——使用者可以忽略
    And 推送頻率限制：每次對話最多 2 次主動推送

  # ════════════════════════════════════════════
  # Section 6: 再結晶引擎 — 知識的演化
  # ════════════════════════════════════════════

  Scenario: 冗餘偵測 — 語義重疊超過 70%
    Given 結晶 A 和結晶 B 的語義重疊超過 70%
    When 再結晶引擎掃描偵測到冗餘
    Then 系統提議合併（不自動合併）
    And 顯示兩顆結晶的差異點
    And 使用者決定是否合併
    And 合併後：新結晶生成，舊結晶標記為 "merged"

  Scenario: 矛盾偵測 — 相反的結論
    Given 結晶 A 說「X 有效」，結晶 B 說「X 無效」
    When 矛盾被偵測到
    Then 兩顆結晶都標記為 status="disputed"
    And 不強制消除矛盾——保留兩方觀點
    And 引導使用者探索矛盾的原因（情境不同？時間不同？）
    And 矛盾本身可能是新洞見的來源

  Scenario: 過期偵測 — 90 天未使用且 RI 極低
    Given 結晶 X 已 90 天未被引用
    And 結晶 X 的 RI 已降至 0.08（< 0.1 閾值）
    When 再結晶引擎執行過期掃描
    Then 系統提議歸檔結晶 X
    And 使用者可以選擇：歸檔（移至 archive/）/ 更新 / 保留
    And 歸檔不是刪除——歸檔的結晶仍可搜尋

  Scenario: 升級候選 — Hypothesis 成功 3 次以上
    Given Hypothesis 型結晶 H 在 3 次不同場合被成功應用
    When 再結晶引擎偵測到升級信號
    Then 系統建議將 H 從 Hypothesis 升級為 Pattern
    And 升級需要使用者確認
    And 升級後 verification.level 從 "hypothetical" 變為 "observed"
    And 結晶的 CUID 保持不變（只是 type 和 verification 改變）

  Scenario: 降級候選 — Insight 被反證
    Given Insight 型結晶 I 被 2 條以上反證挑戰
    When 再結晶引擎偵測到降級信號
    Then 系統建議將 I 從 Insight 降級為 Hypothesis
    And 降級需要使用者確認
    And 不盲目維護舊結論——實事求是

  Scenario: 碎片整合 — 同領域 5+ 小結晶
    Given 某領域有 5 個以上小型結晶
    When 再結晶引擎偵測到碎片化
    Then 系統建議整合為一顆綜合性結晶
    And 整合保留所有原始結晶的 CUID 作為 parent_links
    And 整合降低認知負擔，提升知識的可用性

  # ════════════════════════════════════════════
  # Section 7: 知識圖譜與健康度 — Atlas
  # ════════════════════════════════════════════

  Scenario: /atlas 知識圖譜視覺化
    When 使用者執行 /atlas
    Then 系統顯示知識圖譜概覽：
    And 節點 = 結晶（大小 ∝ RI）
    And 邊 = 關聯（顏色區分 cite/fork/merge/contradict）
    And 熱區 = 結晶密集的領域
    And 盲區 = 結晶稀少的領域
    And 圖譜以文字描述呈現（ASCII 或結構化文字）

  Scenario: /lattice health 知識健康度儀表板
    When 使用者執行 /lattice health
    Then 系統顯示：
    And 結晶總數及類型分布（Insight / Pattern / Lesson / Hypothesis）
    And 平均共振指數
    And 活躍結晶率（近 90 天被引用的結晶佔比）
    And 孤立結晶（零連結）列表
    And 領域覆蓋度分布
    And 盲點警告（某領域 ≤ 2 顆結晶 → ⚠️）

  Scenario: /lattice audit 盲點掃描
    When 使用者執行 /lattice audit
    Then 系統掃描所有領域的知識覆蓋
    And 識別結晶數 ≤ 2 的領域為盲點
    And 識別 Hypothesis 佔比 > 50% 的領域為「知識不穩定」區
    And 識別 30 天無新結晶的領域為「停滯」區
    And 盲點報告可驅動下一步的研究方向

  # ════════════════════════════════════════════
  # Section 8: 與 DNA27 六層記憶的整合
  # ════════════════════════════════════════════

  Scenario: 記憶層到結晶的升級路徑
    Given DNA27 六層記憶系統持續運行
    When 記憶中的內容達到結晶門檻
    Then 升級路徑為：
      | 記憶層    | 結晶類型     | 條件                               |
      | L0 工作   | → Hypothesis | 對話中識別到候選洞見               |
      | L1 免疫   | → Lesson     | 錯誤事件經過根因分析               |
      | L2 事件   | → Pattern    | 同類事件累積 3+ 次                 |
      | L3 技能   | → Insight    | 穩定 + 可遷移的行為模式            |
      | L5 假說   | → Hypothesis | 成功率 50%+ 的策略                 |
    And 記憶層提供素材，結晶提供結構化和持久化

  Scenario: 結晶反哺記憶系統
    Given 一顆 Pattern 結晶的 RI 持續上升
    When RI > 0.7 且跨 3 個以上場景成功應用
    Then 該 Pattern 被標記為「值得沉入 L3 技能層記憶」
    And 結晶不只是從記憶中提取——也能反哺記憶
    And 形成記憶 ↔ 結晶的雙向循環

  # ════════════════════════════════════════════
  # Section 9: 背景運行與心跳整合
  # ════════════════════════════════════════════

  Scenario: 對話結束後自動掃描結晶候選
    When 一次對話結束
    Then Knowledge-Lattice 靜默掃描對話內容
    And 識別潛在的結晶候選（不干擾使用者）
    And 候選被暫存到 data/knowledge/candidates.json
    And 下次對話時提示使用者是否要結晶化

  Scenario: 每 20 顆新結晶觸發輕量再結晶掃描
    Given 自上次再結晶以來已新增 20 顆結晶
    When 第 20 顆結晶被註冊
    Then 系統自動觸發輕量再結晶掃描
    And 掃描冗餘、矛盾、升級候選
    And 結果以建議列表呈現（不自動執行）

  Scenario: Nightly Job 結晶健康同步
    When Nightly Job 00:00 執行
    Then 結晶健康數據同步到 Morphenix 的 Skill 健康儀表板
    And 計算當日新增結晶數
    And 更新所有結晶的共振指數（衰減計算）
    And 標記過期候選
    And 更新 Intuition Engine 的 L2 啟發式庫

  # ════════════════════════════════════════════
  # Section 10: 安全護欄與品質保障
  # ════════════════════════════════════════════

  Scenario: 假設/證據/限制三元組 — 每顆結晶必備
    When 一顆結晶被創建
    Then 必須包含：
    And crystal.assumptions — 此結晶的基本假設
    And crystal.evidence_base — 支持結論的具體證據
    And crystal.limitations — 此結論失效的條件
    And 三元組缺一不可——沒有限制條件的知識是危險的

  Scenario: 驗證等級透明 — 不允許冒充
    When 結晶的 verification.level 被設定
    Then Hypothesis 不能偽裝成 Insight
    And verification.level 的升級必須有明確證據
    And 使用者在召回時可以看到每顆結晶的驗證等級
    And 低驗證等級的結晶標記為「僅供參考」

  Scenario: 矛盾保留不消除
    Given 兩顆結晶存在矛盾
    When 矛盾被偵測
    Then 系統保留兩顆結晶（不強制選邊站）
    And 兩顆都標記為 "disputed"
    And 引導探索而非強制解決
    And 矛盾是思考的起點，不是需要消滅的問題

  Scenario: 隱私保護 — 結晶不含個人具體事件
    When 結晶化流程提取知識
    Then 只結晶抽象化的原理和模式
    And 不結晶具體的個人資訊或私密事件
    And 例如結晶「決策信心與資訊完整度正相關」
    And 而非結晶「Zeal 在 2 月 26 日因為 X 而猶豫」

  Scenario: 有害知識過濾 — 與 DNA27 Kernel 對齊
    When 一顆結晶被提交品質閘
    Then G0 合法性檢查包含：
    And 不結晶可能造成傷害的知識
    And 不結晶帶有偏見的結論
    And 不結晶侵犯他人智財的內容
    And 結晶必須與 DNA27 Kernel 五大不可覆寫值一致
