#!/bin/bash
# ═══════════════════════════════════════════════════
# MUSEON 報告發布腳本 v4.0
#
# 策略：用 git worktree 把報告推到 gh-pages 分支
# 不切換 main 分支、不 stash、不碰工作目錄
#
# 用法：
#   bash scripts/publish-report.sh <報告路徑> [目標檔案名]
#
# 範例：
#   bash scripts/publish-report.sh /tmp/my-report.html
#   bash scripts/publish-report.sh /tmp/my-report.html feng_mvp_2026-03-24.html
#
# URL 格式：
#   https://zealchou.github.io/MUSEON/reports/<filename>.html
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
WORKTREE_DIR="/tmp/museon-gh-pages"

# ─── Step 1: 驗證報告檔案 ─────────────────────────
echo "📋 Step 1: 驗證報告檔案..."
if [ ! -f "$SOURCE_FILE" ]; then
    echo "❌ 源檔案不存在：$SOURCE_FILE"
    exit 1
fi
FILE_SIZE=$(du -h "$SOURCE_FILE" | cut -f1)
echo "✅ 檔案存在：$SOURCE_FILE ($FILE_SIZE)"

# ─── Step 2: 準備 gh-pages worktree ─────────────────────────
echo ""
echo "📋 Step 2: 準備 gh-pages worktree..."
cd "$MUSEON_ROOT"

if [ -d "$WORKTREE_DIR" ]; then
    echo "   Worktree 已存在，同步最新..."
    cd "$WORKTREE_DIR"
    git pull origin gh-pages --ff-only 2>/dev/null || true
else
    echo "   建立 worktree..."
    git worktree add "$WORKTREE_DIR" gh-pages 2>/dev/null || {
        # 如果 worktree 記錄殘留，先清理再建立
        git worktree prune
        git worktree add "$WORKTREE_DIR" gh-pages
    }
fi
echo "✅ Worktree 就緒"

# ─── Step 3: 複製報告並提交 ─────────────────────────
echo ""
echo "📋 Step 3: 複製報告到 gh-pages..."
cd "$WORKTREE_DIR"
mkdir -p reports/
cp "$SOURCE_FILE" "reports/$DEST_NAME"
git add "reports/$DEST_NAME"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
git commit -m "report: 發佈 $DEST_NAME（$TIMESTAMP）" 2>/dev/null || {
    echo "⚠️ 檔案無變更，跳過提交"
}
echo "✅ 已提交到 gh-pages"

# ─── Step 4: 推送 ─────────────────────────
echo ""
echo "📋 Step 4: 推送到 GitHub..."
git push origin gh-pages
echo "✅ 已推送"

# ─── Step 5: 同步到 main/docs/reports（備份） ─────────────────────────
echo ""
echo "📋 Step 5: 同步到 main 分支備份..."
cd "$MUSEON_ROOT"
mkdir -p docs/reports/
cp "$SOURCE_FILE" "docs/reports/$DEST_NAME"
git add "docs/reports/$DEST_NAME"
git commit -m "report: 備份 $DEST_NAME 到 docs/reports/" 2>/dev/null || true

# ─── Step 6: 驗證連結（最多重試 4 次，共 2 分鐘） ─────────────────────────
echo ""
EXTERNAL_URL="https://zealchou.github.io/MUSEON/reports/$DEST_NAME"
MAX_RETRIES=4
RETRY_INTERVAL=30
VERIFIED=false

for i in $(seq 1 $MAX_RETRIES); do
    echo "📋 Step 6: 驗證連結（第 ${i}/${MAX_RETRIES} 次，等待 ${RETRY_INTERVAL} 秒）..."
    sleep $RETRY_INTERVAL
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$EXTERNAL_URL")
    if [ "$HTTP_CODE" = "200" ]; then
        VERIFIED=true
        break
    fi
    echo "   HTTP $HTTP_CODE — 尚未就緒"
done

echo ""
echo "════════════════════════════════════════"
if [ "$VERIFIED" = true ]; then
    echo "✅ 發布成功！連結已驗證可訪問"
    echo "🔗 $EXTERNAL_URL"
    echo ""
    echo "VERIFIED_URL=$EXTERNAL_URL"
else
    echo "⚠️ 連結驗證失敗（HTTP $HTTP_CODE）"
    echo "   $EXTERNAL_URL"
    echo "   CDN 快取可能延遲，請 5 分鐘後手動驗證"
    echo ""
    echo "VERIFIED_URL="
    exit 1
fi
echo "════════════════════════════════════════"
