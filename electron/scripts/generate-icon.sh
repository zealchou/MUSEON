#!/bin/bash
#
# 從源 PNG 自動生成 macOS icon.icns
# 在 npm run build 前自動執行（prebuild hook）
#
# 源頭: assets/cis/museon-app-icon-1024.png
# 輸出: build/icon.icns
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ELECTRON_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SOURCE_PNG="$ELECTRON_DIR/assets/cis/museon-app-icon-1024.png"
OUTPUT_ICNS="$ELECTRON_DIR/build/icon.icns"
ICONSET_DIR="/tmp/museon-icon-$$.iconset"

# 確認源檔案存在
if [ ! -f "$SOURCE_PNG" ]; then
    echo "❌ 找不到源圖示: $SOURCE_PNG"
    exit 1
fi

# 只在 macOS 上生成 .icns（Linux/Windows 跳過）
if [ "$(uname)" != "Darwin" ]; then
    echo "⏭️  非 macOS，跳過 icon.icns 生成"
    exit 0
fi

echo "🎨 生成 MUSEON icon.icns..."

# 建立 iconset 目錄
mkdir -p "$ICONSET_DIR"

# 生成所有必要尺寸
sips -z   16   16 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_16x16.png"      > /dev/null 2>&1
sips -z   32   32 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_16x16@2x.png"   > /dev/null 2>&1
sips -z   32   32 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_32x32.png"      > /dev/null 2>&1
sips -z   64   64 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_32x32@2x.png"   > /dev/null 2>&1
sips -z  128  128 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_128x128.png"    > /dev/null 2>&1
sips -z  256  256 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_128x128@2x.png" > /dev/null 2>&1
sips -z  256  256 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_256x256.png"    > /dev/null 2>&1
sips -z  512  512 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_256x256@2x.png" > /dev/null 2>&1
sips -z  512  512 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_512x512.png"    > /dev/null 2>&1
sips -z 1024 1024 "$SOURCE_PNG" --out "$ICONSET_DIR/icon_512x512@2x.png" > /dev/null 2>&1

# 編譯為 .icns
mkdir -p "$(dirname "$OUTPUT_ICNS")"
iconutil -c icns "$ICONSET_DIR" -o "$OUTPUT_ICNS"

# 清理
rm -rf "$ICONSET_DIR"

echo "✅ icon.icns 已生成: $OUTPUT_ICNS ($(du -h "$OUTPUT_ICNS" | cut -f1))"
