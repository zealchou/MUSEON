# 📢 報告發布系統完整實施指南（v2.0）

> 自動化報告發布流程修復 2026-03-23 事件

## 🚀 快速開始

### 標準命令
\`\`\`bash
bash ~/MUSEON/scripts/publish-report.sh /tmp/my-report.html
\`\`\`

### 預期輸出
\`\`\`
🚀 開始發布報告流程...
✅ 檔案存在
✅ 報告已複製
✅ 已提交並推送
✅ 發布完成！

🔗 外部連結：
https://zealchou.github.io/MUSEON/docs/_reports/my-report.html
\`\`\`

## 📋 四層驗證流程
1. **環境驗證** — 確保克隆目錄有效
2. **複製驗證** — 確保檔案正確轉移
3. **Git 驗證** — 確保版本控制成功
4. **連結驗證** — 確保使用者能訪問（自動重試）

## 🔍 故障排除

| 問題 | 解決方案 |
|------|--------|
| 源檔案不存在 | 檢查：`ls -lh /tmp/my-report.html` |
| Git push 失敗 | 檢查網路 & GitHub credentials |
| 連結 404 | 等待 30 秒後重新訪問 |

## 📚 詳細文檔
- `docs/publish-workflow.md` — 完整工作流
- `docs/publish-quick-guide.md` — 快速參考卡
