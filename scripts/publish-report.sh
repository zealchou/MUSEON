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
RAW_BASE_URL="https://raw.githubusercontent.com/zealchou/MUSEON/gh-pages/reports"

# ─── Trap 清理（worktree 殘留防護） ─────────────────────────
_cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ] && [ -d "$WORKTREE_DIR" ]; then
        echo ""
        echo "  [trap] 腳本中途失敗，清理 worktree..."
        cd "$MUSEON_ROOT" 2>/dev/null || true
        git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || true
        git worktree prune 2>/dev/null || true
    fi
}
trap _cleanup EXIT

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
FIRST_WAIT=45   # CDN 通常需要 30-60 秒，第一輪等 45 秒
RETRY_INTERVAL=10
ALL_CDN_VERIFIED=true

# 等第一輪 CDN
echo "  等待 ${FIRST_WAIT}s 讓 CDN 同步..."
sleep $FIRST_WAIT

CACHE_BUST=$(date +%s)

for name in "${DEST_NAMES[@]}"; do
    URL="$BASE_URL/$name"
    RAW_URL="$RAW_BASE_URL/$name"

    # ── Phase A: 先驗 raw.githubusercontent.com（不經 CDN）──
    RAW_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$RAW_URL")

    if [ "$RAW_CODE" != "200" ]; then
        # raw 也不是 200 → 檔案本身可能還沒到 gh-pages
        echo "  FAILED: $name (raw=$RAW_CODE，gh-pages 分支可能尚未同步)"
        echo "FAILED_URL=$URL"
        ALL_CDN_VERIFIED=false
        continue
    fi

    # ── Phase B: raw 200，再驗 CDN（附 cache-bust 參數）──
    CDN_VERIFIED=false
    HTTP_CODE="000"
    for attempt in $(seq 1 $MAX_RETRIES); do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${URL}?v=${CACHE_BUST}")
        if [ "$HTTP_CODE" = "200" ]; then
            CDN_VERIFIED=true
            break
        fi
        sleep $RETRY_INTERVAL
    done

    if [ "$CDN_VERIFIED" = true ]; then
        echo "  OK: $URL"
        echo "VERIFIED_URL=$URL"
    else
        # 檔案確實在 gh-pages，只是 CDN 還沒同步
        echo "  VERIFIED (CDN syncing): $URL (raw=200, cdn=$HTTP_CODE, may take 1-2 min)"
        echo "VERIFIED_URL=$URL  # CDN syncing, may take 1-2 min"
        ALL_CDN_VERIFIED=false
    fi
done

# ─── 結果 ─────────────────────────
echo ""
echo "════════════════════════════════════════"
if [ "$ALL_CDN_VERIFIED" = true ]; then
    echo "ALL ${FILE_COUNT} files published and CDN verified"
else
    echo "${FILE_COUNT} files published (CDN may still be syncing)"
fi
echo ""
for name in "${DEST_NAMES[@]}"; do
    echo "  $BASE_URL/$name"
done
echo "════════════════════════════════════════"
