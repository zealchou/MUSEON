#!/bin/bash
# ═══════════════════════════════════════════════════
# MUSEON 報告發布腳本 v5.0
#
# 策略：用 git worktree 把報告推到 gh-pages 分支
# 不切換 main 分支、不 stash、不碰工作目錄
#
# 支援格式：.html .pdf .docx .xlsx .pptx（任何檔案皆可）
#
# 用法：
#   bash scripts/publish-report.sh <檔案路徑> [目標檔案名]
#   bash scripts/publish-report.sh file1 file2 file3  # 批次發佈
#
# 範例：
#   bash scripts/publish-report.sh /tmp/report.html
#   bash scripts/publish-report.sh /tmp/report.pdf report_2026-03-24.pdf
#   bash scripts/publish-report.sh /tmp/report.html /tmp/data.xlsx /tmp/slides.pptx
#
# URL 格式：
#   https://zealchou.github.io/MUSEON/reports/<filename>
# ═══════════════════════════════════════════════════

set -e

MUSEON_ROOT="${MUSEON_ROOT:-$HOME/MUSEON}"
WORKTREE_DIR="/tmp/museon-gh-pages"
BASE_URL="https://zealchou.github.io/MUSEON/reports"

# ─── 參數檢查 ─────────────────────────
if [ $# -lt 1 ]; then
    echo "用法：$0 <檔案路徑> [檔案2] [檔案3] ..."
    echo "範例：$0 /tmp/report.pdf"
    echo "      $0 /tmp/report.html /tmp/data.xlsx /tmp/slides.pptx"
    exit 1
fi

# 收集所有檔案
FILES=("$@")
DEST_NAMES=()

# ─── Step 1: 驗證所有檔案 ─────────────────────────
echo "Step 1: 驗證檔案..."
for f in "${FILES[@]}"; do
    if [ ! -f "$f" ]; then
        echo "  ERROR: $f 不存在"
        exit 1
    fi
    SIZE=$(du -h "$f" | cut -f1)
    NAME=$(basename "$f" | tr '_' '-')
    DEST_NAMES+=("$NAME")
    echo "  OK: $NAME ($SIZE)"
done

# ─── Step 2: 準備 gh-pages worktree ─────────────────────────
echo ""
echo "Step 2: 準備 gh-pages worktree..."
cd "$MUSEON_ROOT"

if [ -d "$WORKTREE_DIR" ]; then
    cd "$WORKTREE_DIR"
    git pull origin gh-pages --ff-only 2>/dev/null || true
else
    git worktree add "$WORKTREE_DIR" gh-pages 2>/dev/null || {
        git worktree prune
        git worktree add "$WORKTREE_DIR" gh-pages
    }
fi

# ─── Step 3: 複製所有檔案並提交 ─────────────────────────
echo ""
echo "Step 3: 複製檔案到 gh-pages..."
cd "$WORKTREE_DIR"
mkdir -p reports/

COMMITTED_NAMES=""
for i in "${!FILES[@]}"; do
    cp "${FILES[$i]}" "reports/${DEST_NAMES[$i]}"
    git add "reports/${DEST_NAMES[$i]}"
    COMMITTED_NAMES="$COMMITTED_NAMES ${DEST_NAMES[$i]}"
done

TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
FILE_COUNT=${#FILES[@]}
git commit -m "publish: ${FILE_COUNT} files ($TIMESTAMP) —${COMMITTED_NAMES}" 2>/dev/null || {
    echo "  No changes to commit"
}

# ─── Step 4: 推送 ─────────────────────────
echo ""
echo "Step 4: push to GitHub..."
git push origin gh-pages

# ─── Step 5: 備份到 main ─────────────────────────
echo ""
echo "Step 5: 備份到 main..."
cd "$MUSEON_ROOT"
mkdir -p docs/reports/
for i in "${!FILES[@]}"; do
    cp "${FILES[$i]}" "docs/reports/${DEST_NAMES[$i]}"
    git add "docs/reports/${DEST_NAMES[$i]}"
done
git commit -m "backup: ${FILE_COUNT} files to docs/reports/" 2>/dev/null || true

# ─── Step 6: 驗證連結 ─────────────────────────
echo ""
echo "Step 6: 驗證連結（等 GitHub Pages CDN）..."
MAX_RETRIES=4
RETRY_INTERVAL=30
ALL_VERIFIED=true

# 等第一輪 CDN
sleep $RETRY_INTERVAL

VERIFIED_URLS=""
for name in "${DEST_NAMES[@]}"; do
    URL="$BASE_URL/$name"
    VERIFIED=false
    for attempt in $(seq 1 $MAX_RETRIES); do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
        if [ "$HTTP_CODE" = "200" ]; then
            VERIFIED=true
            break
        fi
        sleep 10
    done
    if [ "$VERIFIED" = true ]; then
        echo "  OK: $URL"
        VERIFIED_URLS="$VERIFIED_URLS$URL\n"
    else
        echo "  PENDING: $URL (HTTP $HTTP_CODE, CDN may be slow)"
        VERIFIED_URLS="$VERIFIED_URLS$URL\n"
        ALL_VERIFIED=false
    fi
done

# ─── 結果 ─────────────────────────
echo ""
echo "════════════════════════════════════════"
if [ "$ALL_VERIFIED" = true ]; then
    echo "ALL ${FILE_COUNT} files published and verified"
else
    echo "${FILE_COUNT} files published (some CDN pending)"
fi
echo ""
for name in "${DEST_NAMES[@]}"; do
    echo "  $BASE_URL/$name"
done
echo ""
echo "VERIFIED_URLS:"
for name in "${DEST_NAMES[@]}"; do
    echo "VERIFIED_URL=$BASE_URL/$name"
done
echo "════════════════════════════════════════"
