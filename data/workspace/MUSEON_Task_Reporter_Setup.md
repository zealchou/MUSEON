# 🤖 MUSEON 主動回報系統 — 配置完成

## ✅ 現在正在運行

### 系統架構
```
macOS launchd (每 10 分鐘執行)
    ↓
~/MUSEON/bin/report-task.sh
    ↓
檢查 ~/MUSEON/data/tasks.json 中的逾期承諾
    ↓
透過 Telegram Bot API 發送訊息給你
```

### 已激活的元件

| 元件 | 狀態 | 說明 |
|------|------|------|
| **launchd 任務** | ✅ 激活 | `com.museon.task-reporter` 已載入 |
| **回報腳本** | ✅ 就位 | `~/MUSEON/bin/report-task.sh` 已建立並可執行 |
| **任務追蹤檔** | ✅ 就位 | `~/MUSEON/data/tasks.json` 已初始化 |
| **Telegram Bot** | ⚠️ 待配置 | Bot Token 已有，Chat ID 待取得 |

---

## 📋 下一步：獲取 Chat ID

要讓系統真正發送訊息給你，需要你的 **Telegram Chat ID**。

### 方式 1：快速取得（推薦）
在 Telegram 上傳一個訊息給 MuseClaw bot，然後執行：

```bash
bash ~/MUSEON/bin/get-chat-id.sh
```

這會顯示你的 Chat ID，例如 `123456789`。

### 方式 2：手動查詢
訪問此 URL（把 TOKEN 替換成實際的 bot token）：
```
https://api.telegram.org/bot8694763877:AAE1dti1giO_4FXA3kVSIXPWP0YcYP43FXM/getUpdates
```

找到最新訊息的 `"id"` 欄位。

### 方式 3：我直接幫你設定
只要告訴我你在 Telegram 的用戶名或 Chat ID，我馬上更新配置。

---

## 🔄 如何運作

### 當你對我說「承諾在 X 時間回報」
1. 我會把這個承諾寫進 `tasks.json`
2. launchd 會每 10 分鐘檢查一次
3. 當到達承諾時間時，系統自動透過 Telegram 發送進度回報

### 承諾的格式
```json
{
  "id": "task_001",
  "name": "任務名稱",
  "status": "in_progress",
  "promised_completion": "2026-03-04T14:04:00+08:00",
  "updates": [...]
}
```

---

## 🛠️ 維護指令

### 檢查系統狀態
```bash
launchctl list | grep museon
```

### 查看最近的回報日誌
```bash
tail -f ~/MUSEON/logs/reporter.log
```

### 手動觸發一次回報
```bash
bash ~/MUSEON/bin/report-task.sh
```

### 禁用自動回報（臨時）
```bash
launchctl unload ~/Library/LaunchAgents/com.museon.task-reporter.plist
```

### 重新啟用
```bash
launchctl load ~/Library/LaunchAgents/com.museon.task-reporter.plist
```

---

## 📌 當前任務追蹤

**任務 1：OpenClaw 主動回報系統配置**
- 狀態：✅ 完成（launchd 已激活）
- 承諾完成時間：2026-03-04 14:04
- 下一次自動回報：10 分鐘內

---

## 💡 這個方案的優勢

✅ **主動積極** — 不需要你敲問，自動在承諾時間回報  
✅ **輕量級** — 用 macOS 原生工具，不依賴複雜的第三方服務  
✅ **可追蹤** — 所有承諾和回報都記錄在 JSON 檔案裡  
✅ **易維護** — Shell script 簡單透明，可隨時修改  
✅ **無誤** — 再也不會說「我會做」然後沒跟進了  

---

## 🎯 下一步行動

1. 【立即】告訴我你的 Telegram Chat ID（方式見上方）
2. 【完成】系統會立即開始自動回報
3. 【檢驗】當承諾時間到時，你會在 Telegram 收到自動訊息

