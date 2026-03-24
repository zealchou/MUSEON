# Agent 子系統對接指南

> **版本**：v3.0
> **最後更新**：2026-03-24
> **適用對象**：Agent 開發者 / 平台管理員
> **前提文件**：`API_CONTRACT_NOTES.md`、`STATE_RULES.md`、`DECISIONS.md`

---

## 1. 概覽

MUC 平台的 Agent 端需要跟伺服器溝通五件事：

1. **配對**（Pairing）— 首次啟用時，取得 Device Token
2. **授權輪詢**（Entitlement Polling）— 每 2-3 分鐘確認授權狀態
3. **接單前檢查**（Pre-Job Check）— 每次接新任務前再確認一次
4. **點數餘額查詢**（Balance）— 查看目前可用點數（F72）
5. **點數消耗**（Consume）— 執行任務時扣點（F72）

### 1.1 正式環境

| 項目 | 值 |
|---|---|
| Base URL | `https://museon.one` |
| API Prefix | `https://museon.one/api/v1` |

### 1.2 兩種配對方式

| 方式 | 說明 | 適合場景 |
|---|---|---|
| **方式 A：自動配對（推薦）** | Agent 用帳密登入，自動找 License、建碼、配對 | 一般使用、批量部署 |
| **方式 B：手動配對碼** | 使用者在網頁產生 6 碼，手動貼到 Agent | 幫別人的電腦配對 |

---

## 2. Python SDK 快速開始（方式 A）

### 2.1 安裝

```bash
pip install httpx
# 選配（安全儲存）
pip install keyring
```

### 2.2 使用

```python
from muc_agent import MucAgent

agent = MucAgent(base_url="https://museon.one")

# ── 首次配對（只需做一次）──────────────────────
# Agent 會自動：登入 → 找可用 License → 建配對碼 → 配對 → 存 Token
await agent.setup("user@example.com", "password123")
# 帳密用完即丟，不會被保存

# ── 之後每次啟動 ──────────────────────────────
# SDK 自動從本地載入 Device Token，不需要再輸入帳密
agent = MucAgent(base_url="https://museon.one")
print(agent.is_paired)  # True

# ── 授權輪詢（每 2-3 分鐘）─────────────────────
entitlement = await agent.get_entitlement()
payload = entitlement["data"]["entitlement"]["payload"]
print(payload["subscription_status"])  # "ACTIVE"
print(payload["allow_new_jobs"])       # True

# ── 接單前檢查 ────────────────────────────────
allowed = await agent.check_before_job()
if allowed:
    # 接單
    pass

# ── 點數餘額查詢（F72）───────────────────────
balance = await agent.get_balance()
print(balance["availableCredits"])  # 可用點數
print(balance["usedCredits"])       # 已消耗點數

# ── 點數消耗（F72）──────────────────────────
result = await agent.consume_credits(
    amount=10,
    reason="outreach task",
    idempotency_key="job-001-consume-1",  # 可選，防重複扣點
)
print(result["consumedAmount"])   # 本次扣了多少
print(result["balanceAfter"])     # 扣完後餘額
```

### 2.3 自動配對內部流程

```
Agent 啟動
  │
  ├─ 檢查本地是否有 Device Token
  │   ├─ 有 → 直接進入輪詢模式
  │   └─ 沒有 → 進入配對流程 ↓
  │
  ├─ 1. POST /api/v1/auth/login
  │     → 取得 JWT
  │
  ├─ 2. GET /api/v1/licenses/my/details
  │     → 找到 ACTIVE 且未綁定設備的 License
  │
  ├─ 3. POST /api/v1/licenses/:id/pair-code
  │     → 自動建立配對碼
  │
  ├─ 4. POST /api/v1/devices/agent/pair
  │     → 取得 device_id + device_token（僅此一次）
  │
  └─ 5. 存入本地 Keychain，清除帳密
```

### 2.4 安全設計

| 項目 | 做法 |
|---|---|
| 帳密存放 | **不存**。拿到 Device Token 就清掉 |
| Device Token 存放 | OS Keychain（有 keyring 時）或 `~/.muc/credentials.json` |
| Token 外洩 | 使用者在 museon.one 後台撤銷設備，Token 立即失效 |
| 重新配對 | 呼叫 `await agent.unpair()` 清除本地 Token → 重新 `setup()` |

### 2.5 錯誤處理

```python
from muc_agent import MucAgent, MucAgentError

agent = MucAgent(base_url="https://museon.one")

try:
    await agent.setup("user@example.com", "password123")
except MucAgentError as e:
    if e.code == "LOGIN_FAILED":
        print("帳號或密碼錯誤")
    elif e.code == "NO_AVAILABLE_LICENSE":
        print("沒有可用的 License，請先到 museon.one 購買方案")
    elif e.code == "LICENSE_ALREADY_BOUND":
        print("License 已綁定設備，請先撤銷舊設備")
    else:
        print(f"配對失敗：{e} (code={e.code})")
```

---

## 3. API 端點總覽

| 端點 | Method | 用途 | 認證方式 |
|---|---|---|---|
| `/api/v1/auth/login` | POST | 登入取得 JWT | 無 |
| `/api/v1/licenses/my/details` | GET | 查詢我的 License | Bearer JWT |
| `/api/v1/licenses/:id/pair-code` | POST | 建立配對碼 | Bearer JWT |
| `/api/v1/devices/agent/pair` | POST | 配對取得 Device Token | 無（帶 Pair Code） |
| `/api/v1/agent/entitlement` | POST | 授權輪詢 | Bearer device_token |
| `/api/v1/agent/check-before-job` | POST | 接單前檢查 | Bearer device_token |
| `/api/v1/credits/agent/balance` | GET | 點數餘額查詢（F72） | Bearer device_token |
| `/api/v1/credits/consume` | POST | 點數消耗（F72） | Bearer device_token |

### Login

```
POST /api/v1/auth/login

Body:
  { "email": "user@example.com", "password": "xxx" }

Response:
  { "data": { "access_token": "JWT-xxx", "account_id": "uuid" } }
```

### 查詢 License

```
GET /api/v1/licenses/my/details

Headers:
  Authorization: Bearer <JWT>

Response:
  { "data": [ { "id": "uuid", "status": "ACTIVE", "subscription": {...}, "device": null } ] }
```

### 建立配對碼

```
POST /api/v1/licenses/:licenseId/pair-code

Headers:
  Authorization: Bearer <JWT>

Response:
  { "data": { "code": "72920a906f2e38be...", "expiresAt": "..." } }
```

### Pair（配對）

```
POST /api/v1/devices/agent/pair

Body:
  {
    "pairCode": "<pair_code>",
    "fingerprint": "<device_fingerprint>",
    "agentVersion": "0.1.0",
    "timestamp": "<ISO 8601 UTC>",
    "nonce": "<random hex>",
    "deviceName": "MUC-Agent-MyPC",    // optional
    "platform": "windows"               // optional
  }

Response:
  { "data": { "deviceId": "uuid", "deviceToken": "hex64...", "licenseId": "uuid" } }
```

### Entitlement（授權輪詢）

```
POST /api/v1/agent/entitlement

Headers:
  Authorization: Bearer <device_token>
  x-device-id: <device_id>
  x-timestamp: <ISO 8601 UTC>
  x-nonce: <random hex>

Body:
  { "fingerprint": "<device_fingerprint>", "agent_version": "0.1.0" }

Response:
  {
    "data": {
      "entitlement": {
        "payload": {
          "device_id": "...",
          "license_id": "...",
          "subscription_status": "ACTIVE",
          "allow_new_jobs": true,
          "grace_until": null
        },
        "key_id": "default",
        "issued_at": "...",
        "expires_at": "...",
        "signature": "<Ed25519 Base64>",
        "notifications": [...]
      }
    }
  }
```

### Check-Before-Job（接單前檢查）

```
POST /api/v1/agent/check-before-job

Headers:
  Authorization: Bearer <device_token>

Body:
  {
    "device_id": "<device_id>",
    "timestamp": "<ISO 8601 UTC>",
    "nonce": "<random hex>",
    "job_context": {}    // optional
  }

Response:
  { "data": { "allow_new_jobs": true, "checked_at": "..." } }
```

### Credit Balance（F72）

```
GET /api/v1/credits/agent/balance
Headers:
  Authorization: Bearer <device_token>
  x-device-id: <device_id>

Response 200:
  { "data": { "licenseId": "...", "availableCredits": 280, "usedCredits": 20 } }

Errors:
  401: DEVICE_TOKEN_INVALID / DEVICE_TOKEN_REVOKED
  403: DEVICE_MISMATCH
```

### Credit Consume（F72）

```
POST /api/v1/credits/consume
Headers:
  Authorization: Bearer <device_token>
  x-device-id: <device_id>
Body:
  {
    "amount": 10,
    "reason": "task description",       // optional
    "idempotencyKey": "job-001-run-1"   // optional, auto-generated if omitted
  }

Response 201:
  {
    "data": {
      "licenseId": "...",
      "consumedAmount": 10,
      "balanceBefore": 280,
      "balanceAfter": 270,
      "transactionId": "...",
      "consumedAt": "2026-03-24T12:00:00.000Z"
    }
  }

Errors:
  401: DEVICE_TOKEN_INVALID / DEVICE_TOKEN_REVOKED
  403: DEVICE_MISMATCH
  409: INSUFFICIENT_CREDITS (when OVERAGE_BILLING_ENABLED=false)
  422: VALIDATION_ERROR (amount <= 0)
```

**冪等保護**：同一個 `idempotencyKey` 重送不會重複扣點，會回傳第一次的結果。

---

## 4. 錯誤處理速查表

### 4.1 錯誤碼一覽

| Error Code | HTTP | 原因 | 可重試？ | Agent 該做什麼 |
|---|---|---|---|---|
| `LOGIN_FAILED` | 401 | 帳號或密碼錯誤 | 否 | 提示使用者檢查帳密 |
| `NO_AVAILABLE_LICENSE` | 404 | 沒有可用的 License | 否 | 提示使用者到 museon.one 購買方案 |
| `VALIDATION_ERROR` | 422 | timestamp 超出 ±5 分鐘窗口 | 是（校正後） | 同步時鐘後重試（見 §6） |
| `VALIDATION_ERROR` | 422 | 其他欄位格式錯誤 | 否 | 檢查 `message` 欄位，修正請求 |
| `NONCE_REPLAY` | 409 | 同一個 nonce 10 分鐘內重複使用 | 是（換 nonce） | 產生全新 nonce，立即重送 |
| `TOKEN_INVALID` | 401 | token 不存在或格式錯誤 | 否 | 清除 token，提示重新配對 |
| `TOKEN_REVOKED` | 401 | token 已被撤銷 | 否 | 清除 token，提示重新配對 |
| `DEVICE_MISMATCH` | 403 | device_id 或 fingerprint 不符 | 否 | 停止請求，提示聯繫管理員 |
| `SUBSCRIPTION_SUSPENDED` | 403 | 訂閱已停權（欠費） | 否 | 停止接新任務，顯示「訂閱已暫停」 |
| `PAIR_CODE_INVALID` | 404 | 配對碼不存在 | 否 | 提示重新產生配對碼 |
| `PAIR_CODE_EXPIRED` | 409/422 | 配對碼已過期（TTL = 5 分鐘） | 否 | 提示重新產生配對碼 |
| `PAIR_CODE_USED` | 409 | 配對碼已被使用 | 否 | 提示重新產生配對碼 |
| `PAIR_CODE_ALREADY_ACTIVE` | 409 | 該 License 已有未過期的配對碼 | 否 | SDK 自動跳下一個 License |
| `LICENSE_ALREADY_BOUND` | 409 | 該 License 已有 ACTIVE 設備 | 否 | 提示先撤銷舊設備 |
| `INSUFFICIENT_CREDITS` | 409 | 點數餘額不足（F72） | 否 | 提示使用者充值或等待月配 |
| `CREDIT_CONSUME_NOT_ALLOWED` | 409 | 訂閱已停權，不可扣點（F72） | 否 | 停止任務，顯示「訂閱已暫停」 |

### 4.2 可重試 vs 不可重試

```
可重試（自動處理）：
  ├─ NONCE_REPLAY    → 換新 nonce，立即重試
  └─ VALIDATION_ERROR（timestamp 相關）→ 校正時鐘後重試

不可重試（需要人介入）：
  ├─ LOGIN_FAILED                    → 檢查帳密
  ├─ NO_AVAILABLE_LICENSE            → 到 museon.one 購買方案
  ├─ TOKEN_INVALID / TOKEN_REVOKED   → 重新配對
  ├─ DEVICE_MISMATCH                 → 聯繫管理員
  ├─ SUBSCRIPTION_SUSPENDED          → 等付款確認
  ├─ PAIR_CODE_EXPIRED / USED        → 重新產生配對碼
  └─ LICENSE_ALREADY_BOUND           → 先撤銷舊設備
```

---

## 5. 手動配對流程（方式 B）

如果不使用 SDK 自動配對，可以手動操作：

```
使用者在網頁端付款成功 → 成功頁自動顯示配對碼（5 分鐘有效）
    或：Portal「我的訂閱」→ 點「產生配對碼」
        │
        ▼
Agent 收到配對碼（使用者手動輸入）
        │
        ▼
Agent 呼叫 POST /api/v1/devices/agent/pair
        │
        ├─ 成功 → 取得 device_token（僅此一次）
        │         → 安全儲存至 OS Keychain
        │
        └─ 失敗 → 見 §4 錯誤處理
```

**重要**：Device Token 只有配對成功時回傳一次明文，伺服器只存 hash。遺失 token 必須重新配對。

---

## 6. 時鐘同步

### 6.1 驗證規則

| 項目 | 值 |
|---|---|
| Timestamp 容許窗口 | ±5 分鐘（300 秒） |
| Nonce 存活期 | 10 分鐘（600 秒） |
| 安全餘量 | 建議時鐘偏差 < 4 分鐘 |

### 6.2 同步方式（擇一）

**方式 A：NTP 校正（推薦）**

Agent 啟動時用 NTP 校正系統時間。

**方式 B：Server Time 補償**

```
offset = Date.parse(response.headers['date']) - Date.now()
timestamp = new Date(Date.now() + offset).toISOString()
```

---

## 7. Nonce 實作規範

```
✅ 每次請求生成全新隨機值
✅ 推薦：secrets.token_hex(16)（Python）或 crypto.randomBytes(16).toString('hex')（Node）
✅ 用完即丟

❌ 用遞增數字
❌ 用時間戳當 nonce
❌ 快取 nonce 做重試
❌ 多個請求共用同一個 nonce
```

---

## 8. 授權輪詢細節

```
Agent 啟動後，每 2-3 分鐘輪詢一次
        │
        ▼
POST /api/v1/agent/entitlement
        │
        ├─ 成功 → 快取 response（用於離線判斷）
        │         → 根據 allow_new_jobs 決定是否接單
        │
        └─ 失敗 → 見 §4 錯誤處理
                   離線 ≤ 15 分鐘：沿用快取
                   離線 > 15 分鐘：停止接新任務
```

### 8.1 Entitlement Response 結構

```json
{
  "data": {
    "entitlement": {
      "payload": {
        "device_id": "...",
        "license_id": "...",
        "subscription_status": "ACTIVE",
        "allow_new_jobs": true,
        "grace_until": null
      },
      "key_id": "default",
      "issued_at": "2026-03-18T10:00:00.000Z",
      "expires_at": "2026-03-18T10:05:00.000Z",
      "signature": "<Ed25519 Base64>",
      "notifications": [...]
    }
  }
}
```

- `signature`：Ed25519 簽章，Agent 端應以內嵌公鑰驗章
- 簽章輸入格式：`JSON.stringify(payload) + "." + issued_at + "." + expires_at`
- `notifications`：**不在簽章範圍內**，僅供 Agent 參考

### 8.2 Notifications（通知陣列）

| type | level | 觸發條件 | Agent 該做什麼 |
|---|---|---|---|
| `GRACE_WARNING` | warn | 訂閱進入 GRACE 期 | 顯示「訂閱即將到期，請續費」 |
| `EXPIRING_SOON` | warn | ACTIVE 訂閱 ≤ 3 天到期 | 顯示「訂閱將於 N 天後到期」 |
| `AGENT_UPDATE_REQUIRED` | critical | Agent 版本 < 最低要求版本 | **停止接單**，引導使用者更新 |
| `AGENT_UPDATE_AVAILABLE` | info | Agent 版本 < 最新版本 | 顯示提示，不影響功能 |

---

## 9. 接單前檢查

```
Agent 準備接新任務前
        │
        ▼
POST /api/v1/agent/check-before-job
        │
        ├─ allow_new_jobs: true  → 可以接單
        └─ allow_new_jobs: false → 不可接單
```

**重要**：已在執行中的任務不會被強制中止，只有「接新任務」會被擋。

---

## 10. 離線政策

| 離線時間 | 行為 |
|---|---|
| ≤ 15 分鐘 | 沿用最後一次有效的 entitlement 快取，允許接新任務 |
| > 15 分鐘 | 停止接新任務，已在執行的任務不中止 |
| 恢復連線後 | 立即做一次 entitlement 輪詢，成功後恢復正常 |

---

## 11. 安全儲存建議

| 平台 | 建議儲存位置 |
|---|---|
| Windows | Credential Manager（`wincred`） |
| macOS | Keychain |
| Linux | Secret Service API / `libsecret` |

```
❌ 不要存在純文字檔案
❌ 不要存在環境變數
❌ 不要寫進 log
✅ 使用 OS 級別的安全儲存
✅ SDK 預設：有 keyring → OS Keychain，沒有 → ~/.muc/credentials.json
```

---

## 12. 對接 Checklist

### 配對
- [ ] 能正確呼叫 pair API 或使用 SDK `setup()`，取得 device_token
- [ ] device_token 存入 OS Keychain / Credential Manager
- [ ] 配對失敗時顯示正確的錯誤提示
- [ ] 帳密用完即清，不持久化

### 請求安全
- [ ] 每次請求都帶全新的 nonce
- [ ] timestamp 使用 ISO 8601 UTC 格式
- [ ] 時鐘偏差 < 4 分鐘
- [ ] 收到 NONCE_REPLAY 時，換 nonce 重試一次
- [ ] 收到 VALIDATION_ERROR 時，校正時鐘後重試一次

### 授權
- [ ] 啟動後每 2-3 分鐘輪詢 entitlement
- [ ] 請求時帶上 `agent_version`
- [ ] 快取最後一次有效的 entitlement response
- [ ] 離線 > 15 分鐘時停止接新任務
- [ ] 每次接新任務前呼叫 check-before-job
- [ ] `allow_new_jobs: false` 時不接單

### 通知處理
- [ ] 讀取 `notifications` 陣列
- [ ] `AGENT_UPDATE_REQUIRED`（critical）→ 停止接單，引導更新
- [ ] `AGENT_UPDATE_AVAILABLE`（info）→ 顯示提示
- [ ] `GRACE_WARNING` / `EXPIRING_SOON`（warn）→ 顯示警告

### 錯誤處理
- [ ] LOGIN_FAILED → 提示帳密錯誤
- [ ] NO_AVAILABLE_LICENSE → 提示購買方案
- [ ] TOKEN_INVALID / TOKEN_REVOKED → 清除 token，重新配對
- [ ] DEVICE_MISMATCH → 停止請求，提示聯繫管理員
- [ ] SUBSCRIPTION_SUSPENDED → 停止接新任務

### 點數（F72）
- [ ] 能呼叫 `get_balance()` 取得可用點數
- [ ] 能呼叫 `consume_credits()` 扣點
- [ ] 帶 idempotencyKey 防重複扣點
- [ ] INSUFFICIENT_CREDITS 時不接新任務
- [ ] TOKEN_INVALID / TOKEN_REVOKED 時清除本地配對

---

## 13. Admin 手動建帳對接（平台管理員）

> 適用場景：幫客戶手動建帳、測試環境、或使用者無法自助訂購時。

### 第 1 步：登入 Admin 後台

1. 開啟 `https://museon.one/admin/login`
2. 用管理員帳號登入

### 第 2 步：建帳號（如果對方還沒註冊）

1. 左側選單 **「帳號管理」**（`/admin/accounts`）
2. 點 **「建立帳號」**
3. 填入 Email、密碼、姓名，角色選 **USER**

### 第 3 步：建序號 + 啟用

1. 左側選單 **「序號管理」**（`/admin/licenses`）
2. **「建立序號」** → 選擇帳號
3. 建立後點 **「啟用」**

### 第 4 步：建付款 + 確認收款

1. 左側選單 **「收款管理」**（`/admin/payments`）
2. **「建立收款」** → 選序號、金額依方案定價
3. 點 **「確認收款」** → 訂閱自動變 ACTIVE

### 第 5 步：給 Agent 開發者

把帳號密碼給 Agent 開發者，讓 SDK 自動配對：
```
Email：user@example.com
Password：xxx
Server：https://museon.one
```

---

## 14. 常見問題

| 問題 | 原因 | 解法 |
|------|------|------|
| `LOGIN_FAILED` | 帳密錯誤 | 確認 email 和密碼 |
| `NO_AVAILABLE_LICENSE` | 沒有可用的 License | 到 museon.one 購買方案 |
| 配對碼無效 | 超過 5 分鐘過期 | 重新產生一組 |
| `LICENSE_ALREADY_BOUND` | 序號已有配對設備 | 到 Portal 停用舊設備 |
| `SUBSCRIPTION_SUSPENDED` | 訂閱停權 | 到 Portal 付款或請 Admin 確認收款 |
| `TOKEN_REVOKED` | 設備被撤銷 | 重新走配對流程 |
| `DEVICE_MISMATCH` | 換了機器 | 重新配對 |
| `INSUFFICIENT_CREDITS` | 點數不足 | 等月配或請 Admin 補點 |

### 重新配對

```python
await agent.unpair()                          # 清除本地 Token
await agent.setup("user@example.com", "xxx")  # 重新配對
```

---

## 附錄

### A. SDK 檔案

| 檔案 | 位置 | 說明 |
|---|---|---|
| `muc_agent.py` | `agent-sdk/muc_agent.py` | Python SDK 主模組 |
| `test_integration.py` | `agent-sdk/test_integration.py` | HTTP 整合測試（41 場景，含 F72 Credit） |
| `requirements.txt` | `agent-sdk/requirements.txt` | Python 依賴 |

### B. 相關文件

| 文件 | 說明 |
|---|---|
| `API_CONTRACT_NOTES.md` | 完整 API 契約 |
| `STATE_RULES.md` | 狀態機規則 |
| `DECISIONS.md` | 已拍板的架構決策 |
