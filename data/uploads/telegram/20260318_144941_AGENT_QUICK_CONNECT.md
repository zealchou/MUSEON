# MUC Agent 對接文件（Quick Connect）

> **Base URL**：`https://museon.one`
> **API Prefix**：所有 API 都必須帶 `/api/v1/` 前綴
> **最後更新**：2026-03-18

---

## 重要：所有 API 路徑都是 `/api/v1/...`

```
✅ 正確：https://museon.one/api/v1/auth/login
❌ 錯誤：https://museon.one/auth/login          ← 會回 HTML
❌ 錯誤：https://museon.one/api/device/pair      ← 404
❌ 錯誤：https://museon.one/api/devices/pair     ← 404
```

---

## 完整對接流程（3 步）

### Step 1：登入取得 JWT

```
POST https://museon.one/api/v1/auth/login
Content-Type: application/json

Body:
{
  "email": "你的帳號email",
  "password": "你的密碼"
}

Response (201):
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1...",
    "account_id": "498df256-bb63-..."
  },
  "meta": {},
  "error": null
}
```

拿到 `data.access_token`，後續 Step 2 要用。

---

### Step 2：配對設備

```
POST https://museon.one/api/v1/devices/agent/pair
Content-Type: application/json

Body:
{
  "pairCode": "7739eb30c881a19e9052f1aa9f34fe0d",
  "fingerprint": "你的設備指紋hash",
  "agentVersion": "1.0.0",
  "timestamp": "2026-03-18T12:00:00.000Z",
  "nonce": "隨機32字元hex",
  "deviceName": "MyAgent-PC",
  "platform": "windows"
}
```

**欄位說明**：

| 欄位 | 必填 | 說明 |
|------|------|------|
| `pairCode` | 是 | 配對碼（就是那串 `7739eb30...`） |
| `fingerprint` | 是 | 設備硬體指紋的 SHA-256 hash |
| `agentVersion` | 是 | Agent 版本號 |
| `timestamp` | 是 | ISO 8601 UTC，與伺服器時間差 ≤ 5 分鐘 |
| `nonce` | 是 | 隨機字串，每次請求必須不同 |
| `deviceName` | 否 | 設備名稱 |
| `platform` | 否 | 作業系統（windows/macos/linux） |

**成功 Response (201)**：

```json
{
  "data": {
    "deviceId": "28fade11-8d6c-...",
    "deviceToken": "a1b2c3d4e5f6...（64字元hex）",
    "licenseId": "e0a14fc9-9187-..."
  },
  "meta": {},
  "error": null
}
```

**重要**：`deviceToken` 只會在這次回傳，伺服器不存明文。請安全保存。

**失敗 Response**：

| HTTP | error.code | 原因 |
|------|-----------|------|
| 404 | `PAIR_CODE_INVALID` | 配對碼不存在（打錯了） |
| 409 | `PAIR_CODE_USED` | 配對碼已被使用過 |
| 409 | `PAIR_CODE_EXPIRED` | 配對碼已過期（超過 5 分鐘） |
| 409 | `LICENSE_ALREADY_BOUND` | 此 License 已綁定設備 |
| 422 | `VALIDATION_ERROR` | timestamp 超出範圍或欄位格式錯誤 |
| 409 | `NONCE_REPLAY` | nonce 重複使用 |

---

### Step 3：授權輪詢（每 2-3 分鐘）

```
POST https://museon.one/api/v1/agent/entitlement
Content-Type: application/json

Headers:
  Authorization: Bearer <Step 2 拿到的 deviceToken>
  x-device-id: <Step 2 拿到的 deviceId>
  x-timestamp: 2026-03-18T12:05:00.000Z
  x-nonce: 新的隨機hex

Body:
{
  "fingerprint": "跟 Step 2 一樣的指紋",
  "agent_version": "1.0.0"
}
```

**成功 Response (201)**：

```json
{
  "data": {
    "entitlement": {
      "payload": {
        "device_id": "28fade11-...",
        "license_id": "e0a14fc9-...",
        "subscription_status": "ACTIVE",
        "allow_new_jobs": true,
        "grace_until": null
      },
      "key_id": "default",
      "issued_at": "2026-03-18T12:05:00.000Z",
      "expires_at": "2026-03-18T12:10:00.000Z",
      "signature": "Ed25519簽章Base64...",
      "notifications": []
    }
  }
}
```

`allow_new_jobs: true` = 可以接新任務。

---

### 接單前檢查（每次接新任務前）

```
POST https://museon.one/api/v1/agent/check-before-job
Content-Type: application/json

Headers:
  Authorization: Bearer <deviceToken>

Body:
{
  "device_id": "<deviceId>",
  "timestamp": "2026-03-18T12:10:00.000Z",
  "nonce": "新的隨機hex"
}
```

**成功 Response (201)**：

```json
{
  "data": {
    "allow_new_jobs": true,
    "checked_at": "2026-03-18T12:10:00.000Z"
  }
}
```

---

## 回答你的問題

### Q1：實際可用的 API 路由

| 端點 | Method | 用途 |
|------|--------|------|
| `/api/v1/auth/login` | POST | 登入（拿 JWT） |
| `/api/v1/devices/agent/pair` | POST | 配對（拿 Device Token） |
| `/api/v1/agent/entitlement` | POST | 授權輪詢 |
| `/api/v1/agent/check-before-job` | POST | 接單前檢查 |

### Q2：認證方式

- **登入**：email + password → 拿 JWT
- **配對**：不需認證，用 Pair Code 驗證身份
- **輪詢/接單檢查**：Bearer deviceToken（配對時拿到的）

### Q3：那串 `7739eb30c881a19e9052f1aa9f34fe0d` 是什麼

是 **Pair Code（配對碼）**，一次性使用，5 分鐘過期。用在 Step 2 的 `pairCode` 欄位。

---

## 快速驗證（curl）

```bash
# 1. 測試 API 是否通
curl -X POST https://museon.one/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"wrong"}'
# 預期回 401 JSON（不是 HTML）

# 2. 配對
curl -X POST https://museon.one/api/v1/devices/agent/pair \
  -H "Content-Type: application/json" \
  -d '{
    "pairCode": "7739eb30c881a19e9052f1aa9f34fe0d",
    "fingerprint": "test-fingerprint-hash",
    "agentVersion": "1.0.0",
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%S.000Z)'",
    "nonce": "'$(openssl rand -hex 16)'"
  }'
```

---

## 注意事項

1. 配對碼 5 分鐘過期，如果剛才那組已過期，我重新產一組給你
2. `timestamp` 必須是 UTC 時間，跟伺服器差 > 5 分鐘會被拒
3. `nonce` 每次請求必須不同，重複會收到 409
4. 所有 response 都包在 `{ "data": ..., "meta": {}, "error": null }` 裡
