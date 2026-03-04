#!/bin/bash

#
# MUSEON .dmg 打包腳本（自帶 Python Runtime）
#
# 用途: 打包 Electron app + Python 原始碼 為 .dmg 安裝檔
# 客戶安裝後首次啟動會自動部署 Python 環境
#
# 使用方式:
#   cd museon
#   ./scripts/build-dmg.sh
#
# 輸出:
#   electron/dist/MUSEON-{version}-{arch}.dmg
#

set -e

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

echo ""
echo "================================================"
echo "   MUSEON .dmg 打包程式（自帶 Python Runtime）"
echo "   Ad-hoc 簽名 (免 Apple Developer)"
echo "================================================"
echo ""

# 檢查是否為 macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    error "此腳本僅支援 macOS"
fi

# 檢查是否在專案根目錄
if [ ! -f "pyproject.toml" ]; then
    error "請在 museon 專案根目錄執行此腳本"
fi

# 檢查 electron 目錄
if [ ! -d "electron" ]; then
    error "找不到 electron 目錄"
fi

# ─── Step 1: 準備 .runtime-bundle（Python 原始碼）───
info "Step 1: 準備 Python runtime bundle..."
if [ -f "scripts/prepare-runtime-bundle.sh" ]; then
    bash scripts/prepare-runtime-bundle.sh
else
    error "找不到 scripts/prepare-runtime-bundle.sh"
fi

# 驗證 bundle 存在
if [ ! -f ".runtime-bundle/pyproject.toml" ]; then
    error ".runtime-bundle 準備失敗（找不到 pyproject.toml）"
fi

BUNDLE_SIZE=$(du -sh .runtime-bundle | cut -f1)
info "runtime-bundle 大小: $BUNDLE_SIZE"

# ─── Step 2: 打包 Electron DMG ───
info "Step 2: 打包 Electron DMG..."

cd electron

# 檢查 package.json
if [ ! -f "package.json" ]; then
    error "找不到 electron/package.json"
fi

# 檢查 node_modules
if [ ! -d "node_modules" ]; then
    warn "node_modules 不存在，執行 npm install..."
    npm install
fi

# 清理舊的 dist
if [ -d "dist" ]; then
    info "清理舊的 dist 目錄..."
    rm -rf dist
fi

# 設定環境變數 (關閉公證)
export CSC_IDENTITY_AUTO_DISCOVERY=false
export ELECTRON_BUILDER_SIGN=false

info "開始打包 (使用 ad-hoc 簽名)..."

# 執行 electron-builder
npm run build

# 檢查輸出
if [ ! -d "dist" ]; then
    error "打包失敗: dist 目錄不存在"
fi

# 尋找 .dmg 檔案
DMG_FILES=$(find dist -name "*.dmg" -type f)

if [ -z "$DMG_FILES" ]; then
    error "找不到 .dmg 檔案"
fi

cd ..

# ─── Step 3: 驗證 DMG 內容 ───
info "Step 3: 驗證 DMG 包含 runtime..."

# 找到一個 DMG 進行驗證
FIRST_DMG=$(echo "$DMG_FILES" | head -n 1)
FIRST_DMG="electron/$FIRST_DMG"

# 掛載 DMG 靜默驗證
MOUNT_POINT=$(hdiutil attach "$FIRST_DMG" -nobrowse -readonly -mountpoint /tmp/museon-verify-$$ 2>/dev/null | tail -1 | awk '{print $NF}')

if [ -n "$MOUNT_POINT" ]; then
    APP_PATH="$MOUNT_POINT/MUSEON.app"
    RUNTIME_IN_DMG="$APP_PATH/Contents/Resources/runtime-bundle"

    if [ -d "$RUNTIME_IN_DMG" ] && [ -f "$RUNTIME_IN_DMG/pyproject.toml" ]; then
        RUNTIME_SIZE=$(du -sh "$RUNTIME_IN_DMG" | cut -f1)
        SRC_FILES=$(find "$RUNTIME_IN_DMG/src" -name "*.py" 2>/dev/null | wc -l | tr -d ' ')
        success "DMG 內含 runtime-bundle ($RUNTIME_SIZE, $SRC_FILES 個 .py 檔案)"
    else
        warn "DMG 內未找到 runtime-bundle！客戶安裝後需要另外部署 Python 環境"
    fi

    hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || true
else
    warn "無法掛載 DMG 進行驗證（非致命）"
fi

# ─── 結果報告 ───
echo ""
echo "================================================"
echo "   打包完成（自帶 Python Runtime）"
echo ""

for DMG_FILE in $DMG_FILES; do
    DMG_FILE="electron/$DMG_FILE"
    DMG_NAME=$(basename "$DMG_FILE")
    DMG_SIZE=$(du -h "$DMG_FILE" | cut -f1)
    echo "   檔案: $DMG_NAME"
    echo "   大小: $DMG_SIZE"
    echo "   路徑: $DMG_FILE"
    echo ""
done

echo "   客戶使用方式："
echo "   1. 打開 .dmg，拖曳 MUSEON.app 到 Applications"
echo "   2. 首次啟動會自動部署 Python 環境"
echo "   3. 需要系統已安裝 Python >= 3.11"
echo "      (brew install python@3.13)"
echo ""
echo "   移除 quarantine："
echo "   sudo xattr -r -d com.apple.quarantine /Applications/MUSEON.app"
echo "================================================"
echo ""

# 清理 .runtime-bundle
info "清理 .runtime-bundle..."
rm -rf .runtime-bundle

success "完成!"
