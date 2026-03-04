#!/bin/bash
#
# 準備 .runtime-bundle/ 目錄
# 包含 Python 原始碼 + 資料，供 electron-builder extraResources 打包進 DMG
#
# 使用方式:
#   cd museon
#   ./scripts/prepare-runtime-bundle.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUNDLE_DIR="$PROJECT_DIR/.runtime-bundle"

echo ""
echo "  ====================================="
echo "  準備 .runtime-bundle"
echo "  ====================================="
echo ""

# 清理舊的 bundle
if [ -d "$BUNDLE_DIR" ]; then
    echo "  → 清理舊的 .runtime-bundle..."
    rm -rf "$BUNDLE_DIR"
fi

mkdir -p "$BUNDLE_DIR"

# ─── 複製 Python 原始碼 ───
echo "  → 複製 src/..."
rsync -a \
    --exclude='__pycache__' \
    --exclude='.DS_Store' \
    --exclude='*.pyc' \
    "$PROJECT_DIR/src/" "$BUNDLE_DIR/src/"

# ─── 複製 pyproject.toml（pip install -e . 需要）───
echo "  → 複製 pyproject.toml..."
cp "$PROJECT_DIR/pyproject.toml" "$BUNDLE_DIR/pyproject.toml"

# ─── 複製種子資料（data/ 中的 skills、templates 等）───
echo "  → 複製 data/..."
rsync -a \
    --exclude='__pycache__' \
    --exclude='.DS_Store' \
    --exclude='_tools' \
    --exclude='*.db' \
    --exclude='*.log' \
    "$PROJECT_DIR/data/" "$BUNDLE_DIR/data/"

# ─── 複製 features（BDD 安裝流程需要）───
if [ -d "$PROJECT_DIR/features" ]; then
    echo "  → 複製 features/..."
    rsync -a \
        --exclude='__pycache__' \
        --exclude='.DS_Store' \
        "$PROJECT_DIR/features/" "$BUNDLE_DIR/features/"
fi

# ─── 複製 Install-MUSEON.command（如果存在）───
if [ -f "$PROJECT_DIR/Install-MUSEON.command" ]; then
    cp "$PROJECT_DIR/Install-MUSEON.command" "$BUNDLE_DIR/Install-MUSEON.command"
fi

# ─── 計算 bundle 大小 ───
BUNDLE_SIZE=$(du -sh "$BUNDLE_DIR" | cut -f1)
FILE_COUNT=$(find "$BUNDLE_DIR" -type f | wc -l | tr -d ' ')

echo ""
echo "  ====================================="
echo "  .runtime-bundle 準備完成"
echo "  大小: $BUNDLE_SIZE"
echo "  檔案數: $FILE_COUNT"
echo "  路徑: $BUNDLE_DIR"
echo "  ====================================="
echo ""
