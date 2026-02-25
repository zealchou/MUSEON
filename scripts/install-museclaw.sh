#!/bin/bash

#
# MuseClaw 安裝腳本
#
# 用途: 在客戶的 Mac 上安裝 MuseClaw.app
# 功能:
# 1. 複製 .app 到 /Applications
# 2. 移除 quarantine 屬性 (允許執行 ad-hoc 簽名的應用)
# 3. 驗證安裝
# 4. 啟動應用
#
# 使用方式:
#   ./install-museclaw.sh [path/to/MuseClaw.app]
#
# 如果不提供路徑,會假設 .app 在當前目錄
#

set -e  # 遇到錯誤立即停止

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 輸出函數
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

# Banner
echo ""
echo "================================================"
echo "   MuseClaw 安裝程式"
echo "   Ad-hoc 簽名 + 免簽名安裝"
echo "================================================"
echo ""

# 檢查是否為 macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    error "此腳本僅支援 macOS"
fi

# 檢查是否有 sudo 權限
if ! sudo -v; then
    error "需要管理員權限才能安裝到 /Applications"
fi

# 取得 .app 路徑
if [ -z "$1" ]; then
    # 在當前目錄尋找 MuseClaw.app
    if [ -d "MuseClaw.app" ]; then
        APP_PATH="$(pwd)/MuseClaw.app"
    elif [ -d "electron/dist/mac/MuseClaw.app" ]; then
        APP_PATH="$(pwd)/electron/dist/mac/MuseClaw.app"
    elif [ -d "electron/dist/mac-arm64/MuseClaw.app" ]; then
        APP_PATH="$(pwd)/electron/dist/mac-arm64/MuseClaw.app"
    else
        error "找不到 MuseClaw.app。請提供路徑作為參數。"
    fi
else
    APP_PATH="$1"
fi

# 驗證 .app 存在
if [ ! -d "$APP_PATH" ]; then
    error "找不到應用程式: $APP_PATH"
fi

info "找到應用程式: $APP_PATH"

# 目標路徑
TARGET_PATH="/Applications/MuseClaw.app"

# 如果已經安裝,詢問是否覆蓋
if [ -d "$TARGET_PATH" ]; then
    warn "MuseClaw 已安裝在 /Applications"
    read -p "是否覆蓋現有版本? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "取消安裝"
        exit 0
    fi
    info "移除舊版本..."
    sudo rm -rf "$TARGET_PATH"
fi

# 複製到 /Applications
info "複製 MuseClaw.app 到 /Applications..."
sudo cp -R "$APP_PATH" "$TARGET_PATH"

if [ ! -d "$TARGET_PATH" ]; then
    error "複製失敗"
fi

success "複製完成"

# 移除 quarantine 屬性
info "移除 quarantine 屬性 (允許執行 ad-hoc 簽名的應用)..."
sudo xattr -r -d com.apple.quarantine "$TARGET_PATH" 2>/dev/null || true

success "Quarantine 屬性已移除"

# 設定正確的權限
info "設定權限..."
sudo chmod -R 755 "$TARGET_PATH"
sudo chown -R $(whoami):staff "$TARGET_PATH"

success "權限設定完成"

# 驗證安裝
info "驗證安裝..."

# 檢查 .app 結構
if [ ! -f "$TARGET_PATH/Contents/MacOS/MuseClaw" ] && \
   [ ! -f "$TARGET_PATH/Contents/MacOS/MuseClaw Dashboard" ]; then
    error "應用程式結構異常"
fi

# 檢查簽名狀態 (ad-hoc 簽名會顯示 adhoc)
SIGN_STATUS=$(codesign -dv "$TARGET_PATH" 2>&1 || echo "unsigned")
info "簽名狀態: $SIGN_STATUS"

success "安裝驗證成功"

# 詢問是否立即啟動
echo ""
read -p "是否立即啟動 MuseClaw? (Y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    info "啟動 MuseClaw..."
    open "$TARGET_PATH"
    success "MuseClaw 已啟動"
fi

echo ""
echo "================================================"
echo "   MuseClaw 安裝完成！"
echo ""
echo "   應用位置: /Applications/MuseClaw.app"
echo ""
echo "   首次啟動時,macOS 可能會顯示安全警告。"
echo "   請前往:"
echo "   系統偏好設定 > 隱私權與安全性"
echo "   點擊「強制打開」即可。"
echo ""
echo "   這是因為我們使用 ad-hoc 簽名,"
echo "   不需要 Apple Developer 帳號。"
echo "================================================"
echo ""
