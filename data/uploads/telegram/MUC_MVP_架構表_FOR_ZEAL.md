# MUC MVP 架構總覽表

> **專案**：MUC（Museclaw User Control）MVP — Feng 開發
> **狀態**：🚧 Phase 13.5 完成，準備進入 Phase 14
> **版本**：2026-03-23
> **目的**：給老闆的架構一眼表（含進度）

---

## 一、專案定位

| 項目 | 說明 |
|------|------|
| **專案名稱** | **MUC MVP**（Museclaw User Control） |
| **核心目的** | 設備授權 + 訂閱計費 + 安全控管的 SaaS 平台 |
| **第一階段** | 收費閉環 + 設備授權 + 最低防破解基線 |
| **目標用戶** | Museclaw Agent 的設備端（裝在客戶主機上） |
| **商業模式** | 按序號（License）訂閱計費，分訂閱/續約兩類方案 |
| **技術棧** | NestJS + Vue 3 + PostgreSQL + TypeORM |

---

## 二、核心系統七層架構

```
┌─────────────────────────────────────────────┐
│ Layer 1：使用者認證與帳號                     │
│ ├─ Account Registration & Login             │
│ ├─ JWT Token 簽發                           │
│ └─ Role-Based Access Control (RBAC)         │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 2：序號管理（License）                 │
│ ├─ Admin 建立/啟用/停用/作廢序號             │
│ ├─ User 查詢自己的序號清單                  │
│ └─ 序號作為計費與設備綁定的基本單位          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 3：設備配對與令牌                       │
│ ├─ User 產生一次性配對碼（5 分鐘有效）       │
│ ├─ Agent 用配對碼首次綁定                    │
│ ├─ Platform 發行 Device Token                │
│ └─ Token Hash 存儲，明文只回傳一次            │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 4：訂閱管理（Subscription）            │
│ ├─ 三大狀態：ACTIVE / GRACE / SUSPENDED     │
│ ├─ 按日曆月自動轉狀態（Reconciler 5分鐘一次）│
│ ├─ ACTIVE→GRACE→SUSPENDED 逐級降級          │
│ └─ 收款後立即恢復 ACTIVE                    │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 5：付款與計費（Payment）               │
│ ├─ Admin 建立付款單（DRAFT）                │
│ ├─ Admin 確認收款（CONFIRMED）              │
│ ├─ 確認後自動激活 Subscription              │
│ └─ 支援作廢（VOID），但已確認不可逆         │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 6：授權與檢查（Entitlement）          │
│ ├─ Agent 定期輪詢授權狀態（entitlement API）│
│ ├─ Response 用 Ed25519 簽章，有效期 5 分鐘 │
│ ├─ Agent 必須驗章成功才認定有效              │
│ └─ 接新任務前再檢查一次（pre-job check）    │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 7：監控、稽核與告警                     │
│ ├─ Audit Log：所有狀態變更、重要操作記錄    │
│ ├─ Alert：告警事件（WARN/CRITICAL）        │
│ ├─ Notification：Email 發送重要通知          │
│ └─ Admin Dashboard：統計卡片、告警摘要      │
└─────────────────────────────────────────────┘
```

---

## 三、開發進度一覽

| 階段 | 內容 | 狀態 |
|------|------|------|
| **Phase 1** | 專案骨架 + Auth | ✅ 完成 |
| **Phase 2** | License + Pair Code + Subscription | ✅ 完成 |
| **Phase 3** | Payment | ✅ 完成 |
| **Phase 4** | BillingProfile | ✅ 完成 |
| **Phase 5** | Device Pairing | ✅ 完成 |
| **Phase 6** | Audit Log + Alert | ✅ 完成 |
| **Phase 7** | Entitlement + Pre-Job Check | ✅ 完成 |
| **Phase 8** | Notification | ✅ 完成 |
| **Phase 9** | 前台 UI（Admin + Portal） | ✅ 完成 |
| **Phase 10** | 測試 | ✅ 完成 |
| **Phase 11** | Agent SDK + 部署 | ✅ 完成 |
| **Phase 12** | User 自助付款 | ✅ 完成 |
| **Phase 13** | 最小營運範疇 + 全自助訂購 | ✅ 完成 |
| **Phase 13.5** | 付款方式管理 + UI/UX 技術債 | ✅ 完成（2026-03-22） |
| **Phase 14** | **Credit 點數系統** | ⬜ 規劃完成，待開工 |
| **Phase 15** | 自動金流串接 | ⬜ 預留架構 |
| **Phase 16** | 推薦分潤 | ⬜ 待規劃 |
| **Phase 17** | 自動更新發佈平台 | ⬜ 待規劃 |

**進度指標**：✅ 66 項工作完成 / ⬜ 20 項待開工

---

## 四、當前狀態快照（Phase 13.5 完成）

### ✅ 已交付能力

| 模組 | 核心功能 | 狀態 |
|------|---------|------|
| **帳號認證** | 註冊、登入、JWT Guard、RBAC | ✅ |
| **序號管理** | Admin 建立/啟用/停用，User 查詢 | ✅ |
| **設備配對** | 配對碼生成、Token 發行、Revoke | ✅ |
| **訂閱狀態機** | ACTIVE→GRACE→SUSPENDED，自動轉換 | ✅ |
| **付款管理** | DRAFT/CONFIRMED/VOID，人工確認 | ✅ |
| **授權檢查** | Ed25519 簽章驗證，5 分鐘有效期 | ✅ |
| **稽核紀錄** | 16 種操作記錄，Append-only | ✅ |
| **告警中心** | 事件偵測、ACK/RESOLVE | ✅ |
| **通知系統** | SendGrid 串接，Email 發送 | ✅ |
| **Admin UI** | 8 張管理頁面 + Dashboard | ✅ |
| **Portal UI** | 用戶自服務頁面 + 帳單查詢 | ✅ |
| **付款方式** | 多種付款方式支援與管理 | ✅ |
| **訂購流程** | 訂閱/續約分流，自助結帳 | ✅ |
| **Order 模型** | 訂單追蹤，完整生命週期 | ✅ |

### ⬜ 待開工（Phase 14+）

| 模組 | 核心功能 | 計畫 |
|------|---------|------|
| **Credit 點數** | 月度配點、超額計費、用量追蹤 | Phase 14 |
| **自動金流** | 串接第三方支付閘道 | Phase 15 |
| **推薦分潤** | 推薦碼、追蹤、獎勵發放 | Phase 16 |
| **自動更新** | 版本檢查、灰度發佈 | Phase 17 |

---

## 五、安全基線清單

| 項目 | 實作 | 狀態 |
|------|------|------|
| 序號不作為直接授權憑證 | 用 Device Token | ✅ |
| 配對碼一次性、短時效 | 5 分鐘內、Hash 存儲 | ✅ |
| Device Token 高熵亂數 | 32 hex (16 bytes) | ✅ |
| Token 綁 device_id + fingerprint | 必填驗證 | ✅ |
| Entitlement 簽章 | Ed25519 簽章 | ✅ |
| Agent 驗章 | 內建公鑰，本地驗章 | ✅ |
| 接新任務前檢查 | pre-job check API | ✅ |
| 離線超過 15 分鐘停止接任務 | Agent SDK 實現 | ✅ |

---

## 六、系統邊界與外部 API

### 設備側 API（Agent 呼叫）
```
POST   /api/device/pair           → 配對 + 取得 Token
GET    /api/device/entitlement    → 查詢授權狀態（驗章）
POST   /api/device/check-before-job → 接新任務前檢查
```

### 管理側 API（Admin 呼叫）
```
License 管理：CRUD、啟用/停用/作廢
Payment 管理：建立草稿、確認、作廢
Subscription 管理：查詢、手動調整
Device 管理：列表、Revoke
Alert 管理：列表、ACK、RESOLVE
```

### 後台排程（無需人工操作）
```
Reconciler (5分鐘)：ACTIVE→GRACE→SUSPENDED 狀態轉換
Notification Worker：Email 發送
```

### 不包含範圍（Phase 1 不做）
- ❌ 自動金流串接（須人工確認收款）
- ❌ 自動退款
- ❌ 推薦/分潤系統
- ❌ 代理商管理
- ❌ 深度反逆向方案

---

## 七、技術棧確認

| 層 | 技術 | 版本 |
|---|------|------|
| **Backend** | NestJS Modular Monolith | v10.3 |
| **Database** | PostgreSQL + TypeORM | - |
| **Auth** | JWT + Passport | - |
| **Frontend** | Vue 3 + Vite + Tailwind | Latest |
| **UI 元件** | shadcn-vue | Latest |
| **Email** | SendGrid | - |
| **Job Queue** | Bull | - |
| **Crypto** | Ed25519（TweetNaCl） | - |

---

## 八、重點決策記錄（OQ — Open Question 解決）

| OQ ID | 問題 | 決策 | 狀態 |
|-------|------|------|------|
| OQ-004 | Payment confirm 是否冪等 | Option B：已 CONFIRMED 則 409 | ✅ |
| OQ-005 | Pair Code TTL | 5 分鐘 | ✅ |
| OQ-006 | Entitlement TTL | 5 分鐘 | ✅ |
| OQ-007 | Alert 分級 | WARN / CRITICAL | ✅ |
| OQ-008 | User 可否自行 revoke | YES | ✅ |
| OQ-010 | Notification 優先級 | SendGrid + Queue | ✅ |

---

## 九、下一步（Phase 14 - Credit 點數系統）

### 預期範疇
- Credit balance 管理（月度配點、超額）
- Credit transaction 紀錄
- 用量統計與超額提醒
- Agent SDK 側的 consume / balance API

### 預期時程
- 規劃完成：✅
- 開發開始：⏳ 待 Feng 安排

---

## 十、為什麼分這些層級？

1. **Layer 1–2（帳號 + 序號）**
   → 基礎身分與資源單位

2. **Layer 3（設備配對）**
   → 物理設備與帳號綁定

3. **Layer 4–5（訂閱 + 付款）**
   → **收費閉環** — 系統能接收 $ 並管理期限

4. **Layer 6（授權檢查）**
   → Agent 決定「要不要給設備用」

5. **Layer 7（稽核 + 告警）**
   → **可控性** — 管理員看得到發生了什麼

**總結**：從身分 → 綁定 → 收費 → 授權 → 監控，是一條完整的「設備管理 SaaS」價值鏈。

---

*文件生成：2026-03-23 by MUSEON*
