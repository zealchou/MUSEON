# Agent 對接操作手冊

> **適用對象**：平台管理員 / Agent 開發者
> **最後更新**：2026-03-18
> **前提**：使用者已自助完成註冊 + 訂購（或由 Admin 手動建立）

---

## 流程總覽

```
方式 A（全自助，推薦）：
  使用者自己搞定 → Agent 輸入帳密 → 自動配對

方式 B（Admin 協助）：
  Admin 幫忙建帳號/序號 → 產生配對碼 → 給 Agent 開發者
```

---

## 方式 A：全自助流程（推薦）

### 使用者自己做（網頁端）

1. 開啟 `https://museon.one/portal/register` 註冊帳號
2. 登入後到 `https://museon.one/pricing` 選方案
3. 確認付款 → 訂閱自動生效

### Agent 端做（程式碼）

```python
from muc_agent import MucAgent

agent = MucAgent(base_url="https://museon.one")
await agent.setup("user@example.com", "password123")
# 完成。之後 Agent 自動維持授權。
```

SDK 會自動完成：登入 → 找 License → 建配對碼 → 配對 → 存 Token → 清除帳密。

**使用者不需要手動複製任何碼。**

---

## 方式 B：Admin 手動協助

> 適用場景：幫客戶手動建帳、測試環境、或使用者無法自助訂購時。

### 第 1 步：登入 Admin 後台

1. 開啟 `https://museon.one/admin/login`
2. 用管理員帳號登入

### 第 2 步：建帳號（如果對方還沒註冊）

1. 左側選單 **「帳號管理」**（`/admin/accounts`）
2. 點 **「建立帳號」**
3. 填入 Email、密碼、姓名，角色選 **USER**
4. 記下帳號 ID

### 第 3 步：建序號 + 啟用

1. 左側選單 **「序號管理」**（`/admin/licenses`）
2. **「建立序號」** → 選擇帳號、填序號（如 `AGENT-DEV-001`）
3. 建立後點 **「啟用」**（INACTIVE → ACTIVE）

### 第 4 步：建付款 + 確認收款

1. 左側選單 **「收款管理」**（`/admin/payments`）
2. **「建立收款」** → 選序號、金額 990、幣別 TWD
3. 建立後點 **「確認收款」** → 訂閱自動變 ACTIVE

### 第 5 步：給 Agent 開發者配對資訊

**選項 1：給帳密（推薦）**

把帳號密碼給 Agent 開發者，讓 SDK 自動配對：

```
Email：user@example.com
Password：xxx
Server：https://museon.one
```

Agent 端執行：
```python
agent = MucAgent(base_url="https://museon.one")
await agent.setup("user@example.com", "xxx")
```

**選項 2：給配對碼**

1. 用對方帳號登入 Portal（`/portal/login`）
2. 「我的訂閱」→ 點 **「產生配對碼」**
3. 把 6 碼給 Agent 開發者（5 分鐘有效）

Agent 端手動呼叫 pair API：
```
POST https://museon.one/api/v1/devices/agent/pair
Body: { "pairCode": "xxx", "fingerprint": "...", ... }
```

---

## 驗證對接是否成功

### 在 Agent 端確認

```python
agent = MucAgent(base_url="https://museon.one")
print(f"已配對: {agent.is_paired}")           # True
print(f"Device ID: {agent.device_id}")        # uuid
print(f"License ID: {agent.license_id}")      # uuid

ent = await agent.get_entitlement()
payload = ent["data"]["entitlement"]["payload"]
print(f"訂閱狀態: {payload['subscription_status']}")  # ACTIVE
print(f"可接單: {payload['allow_new_jobs']}")          # True

allowed = await agent.check_before_job()
print(f"接單前檢查: {allowed}")               # True
```

### 在 Admin 後台確認

1. **「設備管理」** → 可以看到新配對的設備（狀態 ACTIVE）
2. **「稽核日誌」** → 可以看到 `DEVICE_PAIRED` 事件

---

## 常見問題

| 問題 | 原因 | 解法 |
|------|------|------|
| `LOGIN_FAILED` | 帳密錯誤 | 確認 email 和密碼 |
| `NO_AVAILABLE_LICENSE` | 沒有可用的 License | 到 museon.one 購買方案 |
| 配對碼無效 | 超過 5 分鐘過期 | 重新產生一組 |
| 配對碼已使用 | 同一組碼只能用一次 | 重新產生一組 |
| `LICENSE_ALREADY_BOUND` | 序號已有配對設備 | 到 Portal「我的設備」停用舊設備 |
| `SUBSCRIPTION_SUSPENDED` | 訂閱停權（沒付款） | 到 Portal 付款或請 Admin 確認收款 |
| `TOKEN_REVOKED` | 設備被撤銷 | 重新走配對流程 |
| `DEVICE_MISMATCH` | 指紋跟配對時不一樣 | 確認沒有換機器，或重新配對 |

---

## 如果需要重新配對

**用 SDK：**
```python
await agent.unpair()                          # 清除本地 Token
await agent.setup("user@example.com", "xxx")  # 重新配對
```

**手動操作：**
1. Portal → 「我的設備」→ 點舊設備的 **「停用」**
2. 「我的訂閱」→ 重新產生 Pair Code
3. 把新的 Pair Code 給 Agent 開發者

---

## 相關文件

| 文件 | 說明 |
|------|------|
| `AGENT_INTEGRATION_GUIDE.md` | 完整技術對接指南（API 格式、錯誤處理、安全規範） |
| `agent-sdk/muc_agent.py` | Python SDK 原始碼 |
| `agent-sdk/test_integration.py` | 整合測試（33 場景） |
