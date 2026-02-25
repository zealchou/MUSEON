#!/bin/bash

#
# MuseClaw .dmg 打包腳本
#
# 用途: 打包 Electron app 為 .dmg 安裝檔
# 使用 electron-builder 與 ad-hoc 簽名
#
# 使用方式:
#   cd museclaw
#   ./scripts/build-dmg.sh
#
# 輸出:
#   electron/dist/MuseClaw-{version}.dmg
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
echo "   MuseClaw .dmg 打包程式"
echo "   Ad-hoc 簽名 (免 Apple Developer)"
echo "================================================"
echo ""

# 檢查是否為 macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    error "此腳本僅支援 macOS"
fi

# 檢查是否在專案根目錄
if [ ! -f "pyproject.toml" ]; then
    error "請在 museclaw 專案根目錄執行此腳本"
fi

# 檢查 electron 目錄
if [ ! -d "electron" ]; then
    error "找不到 electron 目錄"
fi

cd electron

# 檢查 package.json
if [ ! -f "package.json" ]; then
    error "找不到 electron/package.json"
fi

# 檢查 node_modules
if [ ! -d "node_modules" ]; then
    warn "node_modules 不存在,執行 npm install..."
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
DMG_FILE=$(find dist -name "*.dmg" -type f | head -n 1)

if [ -z "$DMG_FILE" ]; then
    error "找不到 .dmg 檔案"
fi

DMG_NAME=$(basename "$DMG_FILE")
DMG_SIZE=$(du -h "$DMG_FILE" | cut -f1)

success "打包完成!"

echo ""
echo "================================================"
echo "   打包完成"
echo ""
echo "   檔案: $DMG_NAME"
echo "   大小: $DMG_SIZE"
echo "   路徑: $DMG_FILE"
echo ""
echo "   此 .dmg 使用 ad-hoc 簽名,"
echo "   安裝時請使用 scripts/install-museclaw.sh"
echo "   或手動移除 quarantine 屬性:"
echo ""
echo "   sudo xattr -r -d com.apple.quarantine /Applications/MuseClaw.app"
echo "================================================"
echo ""

# 回到專案根目錄
cd ..

# 詢問是否測試安裝
echo ""
read -p "是否測試安裝此 .dmg? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    info "掛載 .dmg..."
    open "$DMG_FILE"

    echo ""
    info "請手動拖曳 MuseClaw.app 到 Applications"
    echo ""
    read -p "拖曳完成後按 Enter 繼續..." -r

    # 執行安裝腳本 (移除 quarantine)
    if [ -f "scripts/install-museclaw.sh" ]; then
        info "執行安裝腳本..."
        ./scripts/install-museclaw.sh
    else
        warn "找不到安裝腳本,請手動執行:"
        echo "sudo xattr -r -d com.apple.quarantine /Applications/MuseClaw.app"
    fi
fi

success "完成!"
