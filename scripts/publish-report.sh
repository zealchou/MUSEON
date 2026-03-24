#!/bin/bash
# ═══════════════════════════════════════════════════
# MUSEON 報告發布腳本 v3.0
#
# 唯一正確的發布流程：推送到 main 分支，GitHub Actions 自動部署
# 不切換分支、不 stash、不碰 gh-pages
#
# 用法：
#   bash scripts/publish-report.sh <報告路徑> [目標檔案名]
#
# 範例：
#   bash scripts/publish-report.sh /tmp/my-report.html
#   bash scripts/publish-report.sh /tmp/my-report.html feng_mvp_2026-03-24.html
# ═══════════════════════════════════════════════════

set -e

# ─── 參數檢查 ─────────────────────────
if [ $# -lt 1 ]; then
    echo "用法：$0 <報告路徑> [目標檔案名]"
    echo "範例：$0 /tmp/my-report.html"
    exit 1
fi

SOURCE_FILE="$1"
DEST_NAME="${2:-$(basename "$SOURCE_FILE")}"
MUSEON_ROOT="${MUSEON_ROOT:-$HOME/MUSEON}"
REPORTS_DIR="$MUSEON_ROOT/docs/reports"

# ─── Step 1: 驗證 ─────────────────────────
echo "📋 驗證報告檔案..."
if [ ! -f "$SOURCE_FILE" ]; then
    echo "❌ 源檔案不存在：$SOURCE_FILE"
    exit 1
fi

FILE_SIZE=$(du -h "$SOURCE_FILE" | cut -f1)
echo "✅ 檔案存在：$SOURCE_FILE ($FILE_SIZE)"

# ─── Step 2: 複製到發布目錄 ─────────────────────────
echo ""
echo "📋 複製報告到 docs/reports/..."
mkdir -p "$REPORTS_DIR"
cp "$SOURCE_FILE" "$REPORTS_DIR/$DEST_NAME"
echo "✅ 已複製：$REPORTS_DIR/$DEST_NAME"

# ─── Step 3: 提交到 main ─────────────────────────
echo ""
echo "📋 提交到 main 分支..."
cd "$MUSEON_ROOT"

CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo "❌ 當前不在 main 分支（在 $CURRENT_BRANCH），請先切回 main"
    exit 1
fi

git add "docs/reports/$DEST_NAME"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
git commit -m "report: 發佈 $DEST_NAME（$TIMESTAMP）"
echo "✅ 已提交"

# ─── Step 4: 推送 ─────────────────────────
echo ""
echo "📋 推送到 GitHub..."
git push origin main
echo "✅ 已推送（GitHub Pages 將自動部署）"

# ─── Step 5: 驗證連結 ─────────────────────────
echo ""
echo "📋 等待 GitHub Pages 部署（30 秒）..."
EXTERNAL_URL="https://zealchou.github.io/MUSEON/reports/$DEST_NAME"
sleep 30

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$EXTERNAL_URL")

echo ""
echo "════════════════════════════════════════"
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ 發布成功！"
else
    echo "⏳ HTTP $HTTP_CODE — 可能還在部署中，請 1-2 分鐘後重試"
fi
echo "🔗 連結：$EXTERNAL_URL"
echo "════════════════════════════════════════"
