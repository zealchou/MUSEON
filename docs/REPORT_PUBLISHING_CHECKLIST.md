# 報告發佈檢查清單 v2.0

🎯 **目標**：確保每次發佈報告都能成功上線，連結有效

---

## 快速發佈流程（3 步 5 分鐘）

### Step 1: 複製報告到發佈目錄
```bash
# 確保報告檔案存在
ls -lh docs/reports/your_report.html

# 複製到 gh-pages 分支的發佈位置
cp docs/reports/your_report.html docs/reports/your_report_FINAL.html
```

### Step 2: 上傳到 GitHub Pages

```bash
# 確保工作目錄乾淨（重要！）
git status

# 如果有未提交的變更，先 stash
git stash push -m "temp stash before publishing"

# 切換到 gh-pages 分支
git checkout gh-pages

# 確保 gh-pages 是最新的
git pull origin gh-pages

# 複製報告檔案
mkdir -p reports/
cp ~/MUSEON/docs/reports/your_report.html reports/your_report.html

# 提交
git add reports/your_report.html
git commit -m "docs: 發佈報告 — your_report.html"

# 推送到遠端（需要 GitHub 認證）
git push origin gh-pages

# 切回 main
git checkout main

# 恢復暫存的變更（如果有的話）
git stash pop
```

### Step 3: 驗證連結有效

```bash
# 等待 1-2 分鐘讓 GitHub Pages 部署完成

# 驗證連結有效（應返回 200）
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://zealchou.github.io/MUSEON/reports/your_report.html"

# 瀏覽器手動訪問連結
open "https://zealchou.github.io/MUSEON/reports/your_report.html"
```

---

## 發佈前檢查清單

在執行上述流程前，請完成以下檢查：

### 📋 檔案品質
- [ ] HTML 報告已在本地生成
- [ ] 檔案大小合理（< 5 MB）
- [ ] 瀏覽器本地預覽正常

### 📋 Git 準備
- [ ] 當前在 `main` 分支
- [ ] 執行 `git status` 確認工作目錄狀態
- [ ] 已連接到 GitHub（驗證：`git remote -v` 顯示 github.com）

### 📋 GitHub 認證
- [ ] 已用 `gh auth login` 登入 GitHub
- [ ] 確認認證有效：`gh auth status`

---

## 常見問題排查

### Q1: Git push 時收到 401/403 認證失敗

**症狀**：
```
fatal: Authentication failed for 'https://github.com/...'
```

**解決**：
```bash
# 用 GitHub CLI 重新登入
gh auth login

# 選擇 HTTPS 作為協議
# 選擇 Browser 進行認證
```

### Q2: 無法切換分支，顯示 "local changes would be overwritten"

**症狀**：
```
error: Your local changes to the following files would be overwritten by checkout
```

**解決**：
```bash
# 暫存當前變更
git stash push -m "temp"

# 切換分支
git checkout gh-pages

# 完成發佈後，切回並恢復
git checkout main
git stash pop
```

### Q3: Push 到 gh-pages 後，連結仍然 404

**可能原因**：
- GitHub Pages 尚未部署完成（通常需要 3-10 秒）
- 檔案沒有真的推送到遠端

**解決**：
```bash
# 檢查檔案是否在 gh-pages 上
git checkout gh-pages
ls -la reports/your_report.html

# 檢查推送歷史
git log --oneline -3

# 確認推送成功
git log origin/gh-pages --oneline -3

# 等待 2 分鐘後重新驗證
sleep 120
curl -s -o /dev/null -w "%{http_code}\n" "https://zealchou.github.io/MUSEON/reports/your_report.html"
```

---

## 發佈後檢查清單

### ✅ 連結驗證
- [ ] GitHub Pages 連結返回 HTTP 200
- [ ] 瀏覽器可訪問連結
- [ ] 報告內容正確顯示

### ✅ 對客戶交付
- [ ] 複製了正確的 GitHub Pages URL
- [ ] 在 Telegram/Email 中發送連結
- [ ] 在 GitHub issue 中記錄連結和時間戳

### ✅ 版本記錄
- [ ] 在 `REPORT_HISTORY.md` 中記錄
- [ ] 格式：`| 日期 | 標題 | 連結 | 驗證時間 |`

---

## 成功案例

### ✅ 完整流程示例

```bash
# 1️⃣ 準備階段
cd /Users/ZEALCHOU/MUSEON
git status  # 確認在 main 分支

# 2️⃣ 暫存當前變更（如果有的話）
git stash push -m "temp_before_publish_$(date +%s)"

# 3️⃣ 切換到 gh-pages
git checkout gh-pages
git pull origin gh-pages

# 4️⃣ 複製報告
mkdir -p reports/
cp ../feng_muc_mvp_2026-03-24.html reports/feng_muc_mvp_2026-03-24.html

# 5️⃣ 提交
git add reports/feng_muc_mvp_2026-03-24.html
git commit -m "docs: 發佈 Feng 客戶 MUC MVP 進度報告（2026-03-24）"

# 6️⃣ 推送
git push origin gh-pages

# 7️⃣ 返回 main
git checkout main
git stash pop

# 8️⃣ 驗證連結（等待 2 秒）
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://zealchou.github.io/MUSEON/reports/feng_muc_mvp_2026-03-24.html"
# 輸出應為：200

# 9️⃣ 瀏覽器驗證
open "https://zealchou.github.io/MUSEON/reports/feng_muc_mvp_2026-03-24.html"

# 🔟 分享給客戶
# 複製連結：https://zealchou.github.io/MUSEON/reports/feng_muc_mvp_2026-03-24.html
# 發送給 Feng
```

---

## 便捷腳本

將以下內容保存為 `bin/publish_report.sh`：

```bash
#!/bin/bash
set -e

REPORT_FILE="${1:?報告檔案路徑}"
REPORT_NAME="${2:?報告名稱}"

if [ ! -f "$REPORT_FILE" ]; then
  echo "❌ 檔案不存在：$REPORT_FILE"
  exit 1
fi

echo "🔄 準備發佈報告..."

# 暫存
STASH_ID="publish_$(date +%s)"
git stash push -m "$STASH_ID"

# 切換到 gh-pages
git checkout gh-pages
git pull origin gh-pages

# 複製
mkdir -p reports/
BASENAME=$(basename "$REPORT_FILE")
cp "$REPORT_FILE" "reports/$BASENAME"

# 提交
git add "reports/$BASENAME"
git commit -m "docs: 發佈 $REPORT_NAME"

# 推送
git push origin gh-pages

# 返回
git checkout main
git stash pop

# 驗證
sleep 2
REMOTE_PATH="https://zealchou.github.io/MUSEON/reports/$BASENAME"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$REMOTE_PATH")

echo ""
echo "════════════════════════════════════════"
if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ 發佈成功！"
  echo "🔗 連結：$REMOTE_PATH"
else
  echo "⚠️ 連結驗證失敗（HTTP $HTTP_CODE）"
  echo "   可能還在部署中，請稍候 1-2 分鐘後重試"
  echo "🔗 連結：$REMOTE_PATH"
fi
echo "════════════════════════════════════════"
```

使用方式：
```bash
chmod +x bin/publish_report.sh
./bin/publish_report.sh docs/reports/my_report.html "我的報告"
```

---

## 備忘錄

### GitHub Pages URL 格式
```
https://zealchou.github.io/MUSEON/reports/FILENAME.html
```

### Git 常用命令速查
```bash
git status                 # 查看當前狀態
git checkout main         # 切換到 main
git checkout gh-pages     # 切換到 gh-pages
git pull origin main      # 拉取最新代碼
git push origin gh-pages  # 推送到遠端
git stash                 # 暫存變更
git stash pop             # 恢復暫存
```

### 認證排查
```bash
gh auth status            # 檢查登入狀態
gh auth login             # 重新登入
git credential reject     # 清除 credential cache（若需要）
```

---

## 最後檢查

發佈前，完成這份最終檢查清單：

- [ ] 我已讀過這個文件
- [ ] 我知道 3 個發佈步驟
- [ ] 我知道如何驗證連結有效
- [ ] 我知道遇到問題時的排查方法
- [ ] 我已準備好發佈第一份報告

現在可以開始發佈了！祝你成功！ 🚀
