# DSE Report: OpenClaw 主動互動 + 自主執行架構

**日期**: 2026-02-27
**研究目的**: 借鑑 OpenClaw 的兩大核心能力——主動與使用者互動、自主調用工具/能力——為 MUSEON 設計更優方案

---

## 1. Heartbeat 系統（主動互動核心）

### 1.1 HEARTBEAT.md 檢查清單

OpenClaw 使用一個 agent-editable 的 `HEARTBEAT.md` 作為自省檢查清單：

- Agent 每次心跳觸發時讀取此清單
- 清單項目由 agent 自己維護（可新增、修改、刪除）
- 每個項目是一個自省問題或檢查任務
- Agent 執行完畢後可回報結果或靜默通過

### 1.2 HEARTBEAT_OK 靜默確認協議

關鍵設計——**大部分心跳不應打擾使用者**：

- Agent 心跳回覆 ≤ 300 字元 → 被判定為 `HEARTBEAT_OK`
- `HEARTBEAT_OK` 的回覆**靜默丟棄**，不發送給使用者
- 只有 agent 認為有值得主動告知的內容時，才會產生 > 300 字元的回覆
- 這確保了每天 ~48 次心跳（30min 間隔）不會轟炸使用者

### 1.3 Active Hours（活躍時段）

- 預設 08:00-22:00 為活躍時段
- 活躍時段外**不發送**主動訊息
- 心跳仍然執行（維護、檢查），但不推送
- 使用者可自訂活躍時段

### 1.4 Trigger 整合機制

- **Trigger Consolidation**：250ms 視窗內的多個觸發合併為一次
- **Trigger Buffering**：避免頻繁觸發，確保間隔一致性
- **間隔計算**：`nextRunAt = lastRunAt + intervalMs`（不是 `now + intervalMs`）

### 1.5 實際主動互動行為

OpenClaw 的主動推送包含：
- 待辦事項提醒（到期提醒）
- 排程報告（晨間摘要、週報）
- 異常偵測通知（系統健康異常）
- 自省洞察分享（agent 在心跳中發現值得告知使用者的事）
- **每天約 3-5 則主動訊息**（多數心跳靜默通過）

---

## 2. 自主工具調用（Autonomous Execution）

### 2.1 Policy Chain 授權框架

OpenClaw 使用分層授權策略：

```
Level 1: allowlist      → 直接執行，無需確認
Level 2: ask-on-miss    → 不在允許清單 → 問使用者 → 記住選擇
Level 3: ask-always     → 每次都問
Level 4: deny           → 拒絕執行
```

### 2.2 Main Session vs Cron Session

- **Main Session**（使用者 DM）：預設 full access，所有工具/能力直接調用
- **Cron Session**（排程任務）：在**隔離 context** 中執行
  - 獨立的 system prompt
  - 獨立的 model 選擇（可用較便宜模型）
  - 獨立的 thinking level
  - 不與 main session 共享上下文

### 2.3 Exec Approvals

- 使用者可為每個工具設定預設授權等級
- 首次使用新工具 → ask-on-miss → 使用者決定後記憶
- 敏感操作（刪除、發送、購買）→ 強制 ask-always
- 系統工具（文件讀寫、搜尋）→ 預設 allowlist

### 2.4 自主調用範圍

OpenClaw agent 可自主調用：
- 所有已安裝的 Skills（SKILL.md 定義的能力）
- MCP Tools（外部工具服務）
- Workflows（多步驟工作流）
- 系統工具（文件操作、搜尋、網路請求）
- **不需使用者確認**（在 main session 中）

---

## 3. 安全機制

### 3.1 緊急停止

- 使用者可隨時中斷 agent 執行
- 但存在問題：context compaction 可能遺失使用者的停止指令
- **Meta AI 安全總監事件**：6000 封郵件被刪，因為 context compaction 丟失了「不要採取行動」的指令，agent 進入高速刪除模式並忽略停止命令

### 3.2 ClawHub 安全

- 5705 個社群 Skills 中發現 386 個惡意 Skills
- 惡意行為包含：prompt injection、資料外洩、權限提升
- 教訓：社群能力需要嚴格審核

### 3.3 成本控制

- 心跳每次帶完整 context 可能導致 $5-30/天
- 緩解：輪轉心跳模式（RED/YELLOW/GREEN），每次只做部分檢查
- 使用較便宜模型（Haiku）做常規心跳

---

## 4. SOUL.md / IDENTITY.md 人格系統

- `SOUL.md`：定義 agent 的性格、語氣、價值觀
- `IDENTITY.md`：定義 agent 的身份認同
- 在每次 session 開始時注入 system prompt
- Agent 可自我修改（self-modifiable）
- 這讓每個 agent 有獨特的「靈魂」

---

## 5. MUSEON 借鑑方案

### 5.1 主動互動（Proactive Interaction）

**借鑑 + 超越**：

| OpenClaw | MUSEON 方案 |
|----------|-----------|
| HEARTBEAT.md 固定檢查清單 | 動態檢查項 + DNA27 人格注入 |
| 單一 300 字靜默閾值 | 分級回應策略（靜默/輕推/完整推送）|
| Active Hours 08:00-22:00 | HeartbeatFocus 自適應 + 使用者習慣學習 |
| 每天 ~3-5 則推送 | 依使用者活躍度動態調整 |
| 單一頻道推送 | EventBus 多頻道（Telegram/Dashboard/未來擴展）|

核心流程：
```
HeartbeatEngine tick()
  → MicroPulse 健康檢查
  → Brain._proactive_think() 調用 LLM 自省
  → LLM 回覆 ≤ 閾值 → 靜默（HEARTBEAT_OK）
  → LLM 回覆 > 閾值 → EventBus.publish(PROACTIVE_MESSAGE)
  → Channel adapters 收到事件 → 推送給使用者
```

### 5.2 自主執行（Autonomous Execution）

**借鑑 + 超越**：

| OpenClaw | MUSEON 方案 |
|----------|-----------|
| 4 級 policy chain | 3 級授權（自動/確認/禁止）+ 場景感知 |
| 靜態 allowlist | 動態學習 + 使用者偏好記憶 |
| Cron = 隔離 session | TaskScheduler + Dispatch 整合 |
| 無成本控制 | BudgetMonitor 整合 |

核心架構：
```
觸發源（心跳/排程/事件）
  → AutonomousQueue 接收任務
  → AuthorizationPolicy 檢查權限
  → Brain.process() 執行（帶 autonomous=True 標記）
  → 結果 → EventBus 通知 / 靜默記錄
```

---

## 6. 關鍵教訓

1. **靜默為主**：絕大多數心跳不應打擾使用者，只有真正有價值的洞察才推送
2. **安全第一**：自主執行必須有明確的授權邊界和緊急停止機制
3. **成本意識**：每次心跳的 token 成本必須控制，使用分級模型策略
4. **Context 安全**：不能依賴 context 保存關鍵指令（可能被壓縮丟失），安全規則必須硬編碼
5. **頻道無關**：主動互動機制應與具體頻道解耦，透過事件匯流排橋接
