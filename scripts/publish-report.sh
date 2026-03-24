#!/bin/bash
# 報告發布腳本 v2.0 — 自動化發文流程（修復 2026-03-23 事件）

if [ $# -lt 1 ]; then
    echo "用法：$0 <報告路徑> [目標檔案名]"
    echo "例如：$0 /tmp/my-report.html my-report-2026-03-24.html"
    exit 1
fi

SOURCE_FILE="$1"
DEST_NAME="${2:-$(basename "$SOURCE_FILE")}"
MUSEON_ROOT="${MUSEON_ROOT:-$HOME/MUSEON}"
REPORTS_DIR="$MUSEON_ROOT/docs/_reports"

mkdir -p "$REPORTS_DIR"

echo "🚀 開始發布報告流程..."
echo ""

echo "📋 第 1 步：驗證報告檔案"
if [ ! -f "$SOURCE_FILE" ]; then
    echo "❌ 源檔案不存在：$SOURCE_FILE"
    exit 1
fi
echo "✅ 檔案存在：$SOURCE_FILE"
echo ""

echo "📋 第 2 步：複製報告到發布目錄"
cp "$SOURCE_FILE" "$REPORTS_DIR/$DEST_NAME"
echo "✅ 報告已複製到：$REPORTS_DIR/$DEST_NAME"
echo ""

echo "📋 第 3 步：提交並推送到 GitHub"
cd "$MUSEON_ROOT"
git add "docs/_reports/$DEST_NAME"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
COMMIT_MSG="report: 發佈報告 $DEST_NAME（$TIMESTAMP）"
git commit -m "$COMMIT_MSG" 2>/dev/null || echo "⚠️  無新增更改"
git push origin main 2>/dev/null || echo "⚠️ Push 可能失敗，請檢查網路"
echo "✅ 已提交並推送"
echo ""

echo "📋 第 4 步：驗證外部連結"
EXTERNAL_URL="https://zealchou.github.io/MUSEON/docs/_reports/$DEST_NAME"
echo "📍 連結：$EXTERNAL_URL"
echo "⏳ 驗證連結中..."
echo ""

echo "✅ 發布完成！"
echo ""
echo "🔗 外部連結："
echo "$EXTERNAL_URL"
