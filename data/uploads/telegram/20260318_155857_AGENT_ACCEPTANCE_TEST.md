# MUC Agent 對接驗收測試

> **Server**: `https://museon.one`
> **API Prefix**: `https://museon.one/api/v1`
> **最後更新**: 2026-03-18

---

## 測試帳號

```
Email:    （由平台方提供）
Password: （由平台方提供）
```

## 環境需求

```bash
pip install httpx cryptography
```

## Ed25519 公鑰（驗章用）

```
302a300506032b65700321000359d0a5e67ac2bc1abf965c393c86135794f074c2cb862154d055408b847b85
```

---

## 第一關：API 連通測試

### 1.1 確認 API 有回 JSON（不是 HTML）

```bash
curl -X POST https://museon.one/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"wrong@test.com","password":"wrong"}'
```

**預期**：回 401 + JSON `{"data":null,"meta":{},"error":{"code":"INVALID_CREDENTIALS",...}}`
**失敗**：如果回 HTML，代表路徑錯誤（少了 `/api/v1/`）

### 1.2 登入取得 JWT

```bash
curl -X POST https://museon.one/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"你的email","password":"你的密碼"}'
```

**預期**：回 201

```json
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1...",
    "account_id": "uuid"
  }
}
```

**保存** `access_token`，後續步驟要用。

---

## 第二關：配對流程

### 2.1 查詢可用 License

```bash
curl https://museon.one/api/v1/licenses/my/details \
  -H "Authorization: Bearer {JWT}"
```

**預期**：回 200，至少一筆 `status: "ACTIVE"` 且 `device: null`（未綁定設備）的 License

**保存** License 的 `id`，下一步要用。

### 2.2 建立配對碼

```bash
curl -X POST https://museon.one/api/v1/licenses/{licenseId}/pair-code \
  -H "Authorization: Bearer {JWT}"
```

**預期**：回 201

```json
{
  "data": {
    "code": "72920a906f2e38bed82b24dac39cec49",
    "expiresAt": "2026-03-18T12:05:00.000Z"
  }
}
```

**保存** `code`，5 分鐘內有效。

### 2.3 配對設備

```bash
curl -X POST https://museon.one/api/v1/devices/agent/pair \
  -H "Content-Type: application/json" \
  -d '{
    "pairCode": "{上一步拿到的 code}",
    "fingerprint": "test-device-fingerprint-sha256-hash",
    "agentVersion": "1.0.0",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%S.000Z)'",
    "nonce": "'$(openssl rand -hex 16)'",
    "deviceName": "Test-Agent",
    "platform": "linux"
  }'
```

**預期**：回 201

```json
{
  "data": {
    "deviceId": "uuid",
    "deviceToken": "64字元hex（僅此一次回傳）",
    "licenseId": "uuid"
  }
}
```

**保存** `deviceId` 和 `deviceToken`，後續所有步驟都要用。`deviceToken` 只出現這一次。

### 2.4 重複配對碼測試

用同一組 `pairCode` 再送一次 2.3 的請求。

**預期**：回 409 `PAIR_CODE_USED`

---

## 第三關：授權輪詢（Entitlement）

### 3.1 正常輪詢

```bash
curl -X POST https://museon.one/api/v1/agent/entitlement \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {deviceToken}" \
  -H "x-device-id: {deviceId}" \
  -H "x-timestamp: $(date -u +%Y-%m-%dT%H:%M:%S.000Z)" \
  -H "x-nonce: $(openssl rand -hex 16)" \
  -d '{
    "fingerprint": "test-device-fingerprint-sha256-hash",
    "agent_version": "1.0.0"
  }'
```

**預期**：回 201

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
      "issued_at": "...",
      "expires_at": "...",
      "signature": "Ed25519 Base64 簽章",
      "notifications": [...]
    }
  }
}
```

**檢查點**：
- `subscription_status` = `"ACTIVE"`
- `allow_new_jobs` = `true`
- `signature` 非空

### 3.2 Ed25519 驗章

```python
from cryptography.hazmat.primitives.serialization import load_der_public_key
import base64, json

PUBLIC_KEY_HEX = "302a300506032b65700321000359d0a5e67ac2bc1abf965c393c86135794f074c2cb862154d055408b847b85"

key = load_der_public_key(bytes.fromhex(PUBLIC_KEY_HEX))

# 從 3.1 回應取出
entitlement = response["data"]["entitlement"]
payload = entitlement["payload"]
issued_at = entitlement["issued_at"]
expires_at = entitlement["expires_at"]
signature = base64.b64decode(entitlement["signature"])

# 簽章輸入：JSON.stringify(payload) + "." + issued_at + "." + expires_at
# 注意：JSON 需用緊湊格式（無空格），與 JS JSON.stringify 一致
message = json.dumps(payload, separators=(",", ":")) + "." + issued_at + "." + expires_at

key.verify(signature, message.encode("utf-8"))
# 沒有 exception = 驗證通過
print("簽章驗證通過")
```

**預期**：不拋 exception

### 3.3 Nonce 重複測試

用 3.1 **同一個 nonce** 再送一次。

**預期**：回 409 `NONCE_REPLAY`

### 3.4 Timestamp 過期測試

送一個 10 分鐘前的 timestamp：

```bash
curl -X POST https://museon.one/api/v1/agent/entitlement \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {deviceToken}" \
  -H "x-device-id: {deviceId}" \
  -H "x-timestamp: 2020-01-01T00:00:00.000Z" \
  -H "x-nonce: $(openssl rand -hex 16)" \
  -d '{"fingerprint": "test-device-fingerprint-sha256-hash"}'
```

**預期**：回 422 `VALIDATION_ERROR`

---

## 第四關：接單前檢查（Pre-Job Check）

### 4.1 正常檢查

```bash
curl -X POST https://museon.one/api/v1/agent/check-before-job \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {deviceToken}" \
  -d '{
    "device_id": "{deviceId}",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%S.000Z)'",
    "nonce": "'$(openssl rand -hex 16)'"
  }'
```

**預期**：回 201

```json
{
  "data": {
    "allow_new_jobs": true,
    "checked_at": "..."
  }
}
```

**判定**：`allow_new_jobs: true` = 可以接單

---

## 第五關：錯誤處理

### 5.1 無效 Token

```bash
curl -X POST https://museon.one/api/v1/agent/entitlement \
  -H "Authorization: Bearer invalid_token_here" \
  -H "x-device-id: {deviceId}" \
  -H "x-timestamp: $(date -u +%Y-%m-%dT%H:%M:%S.000Z)" \
  -H "x-nonce: $(openssl rand -hex 16)" \
  -H "Content-Type: application/json" \
  -d '{"fingerprint": "test"}'
```

**預期**：回 401 `TOKEN_INVALID`

### 5.2 錯誤 Fingerprint

```bash
curl -X POST https://museon.one/api/v1/agent/entitlement \
  -H "Authorization: Bearer {deviceToken}" \
  -H "x-device-id: {deviceId}" \
  -H "x-timestamp: $(date -u +%Y-%m-%dT%H:%M:%S.000Z)" \
  -H "x-nonce: $(openssl rand -hex 16)" \
  -H "Content-Type: application/json" \
  -d '{"fingerprint": "wrong-fingerprint-not-matching"}'
```

**預期**：回 403 `DEVICE_MISMATCH`

### 5.3 過期配對碼

等配對碼超過 5 分鐘後再嘗試配對。

**預期**：回 409 或 410 `PAIR_CODE_EXPIRED`

---

## 第六關：SDK 自動配對（使用 muc_agent.py）

### 6.1 首次自動配對

```python
from muc_agent import MucAgent

agent = MucAgent(base_url="https://museon.one")
result = await agent.setup("你的email", "你的密碼")

print(result)
# { "device_id": "uuid", "license_id": "uuid", "message": "Paired successfully" }
```

**預期**：回傳 `device_id` + `license_id`，帳密用完自動清除

### 6.2 重啟後自動載入

```python
agent = MucAgent(base_url="https://museon.one")
print(agent.is_paired)    # True
print(agent.device_id)    # uuid（從本地 keychain 載入）
```

**預期**：不需要重新 setup，自動載入上次的 Token

### 6.3 授權輪詢

```python
ent = await agent.get_entitlement()
payload = ent["data"]["entitlement"]["payload"]
print(payload["subscription_status"])  # "ACTIVE"
print(payload["allow_new_jobs"])       # True
```

**預期**：`ACTIVE` + `True`

### 6.4 接單前檢查

```python
allowed = await agent.check_before_job()
print(allowed)  # True
```

**預期**：`True`

### 6.5 錯誤場景

```python
# 錯誤帳密
try:
    await agent.setup("wrong@test.com", "wrong")
except MucAgentError as e:
    print(e.code)  # "LOGIN_FAILED"

# Token 被撤銷後
# （在 museon.one 後台停用設備後測試）
try:
    await agent.get_entitlement()
except MucAgentError as e:
    print(e.code)  # "TOKEN_REVOKED"
    print(agent.is_paired)  # False（自動清除）
```

---

## 驗收總表

| 關卡 | 測試數 | 全部通過 |
|------|--------|----------|
| 第一關：API 連通 | 2 | |
| 第二關：配對流程 | 4 | |
| 第三關：授權輪詢 | 4 | |
| 第四關：接單前檢查 | 1 | |
| 第五關：錯誤處理 | 3 | |
| 第六關：SDK 自動配對 | 5 | |
| **合計** | **19** | |

全部 19 項通過 = Agent 對接驗收完成。
