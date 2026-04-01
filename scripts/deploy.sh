#!/bin/bash
# ═══════════════════════════════════════════════════
# MUSEON 全自動部署腳本
#
# 用途：每次迭代完成後，一鍵同步 dev → production → DMG
#
# 使用方式：
#   cd museon
#   bash scripts/deploy.sh "變更摘要1" "變更摘要2" ...
#
# 或不帶參數（自動用 git log 取得）：
#   bash scripts/deploy.sh
# ═══════════════════════════════════════════════════

set -e

# ─── 路徑定義 ─────────────────────────
DEV_ROOT="/Users/ZEALCHOU/museon"
PROD_ROOT="/Users/ZEALCHOU/MUSEON"
APP_ASAR="/Applications/MUSEON.app/Contents/Resources/app.asar"
PROD_ASAR="$PROD_ROOT/electron/app.asar"
DMG_DEST="$HOME/Desktop/MUSEON-1.0.0-arm64.dmg"
VERSION_FILE="$PROD_ROOT/update_marker.json"
CHANGELOG_FILE="$PROD_ROOT/CHANGELOG.md"
TG_TOKEN="8570443079:AAG1EbgVr_JoAAnlNoYdt7XGFvfd9j7dyys"
TG_CHAT="6969045906"

# ─── 顏色 ─────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[✅]${NC} $1"; }
warn()    { echo -e "${YELLOW}[⚠️]${NC} $1"; }
fail()    { echo -e "${RED}[❌]${NC} $1"; exit 1; }

echo ""
echo "════════════════════════════════════════"
echo "   MUSEON 全自動部署 🚀"
echo "════════════════════════════════════════"
echo ""

# ─── 版本號自增 ─────────────────────────
if [ -f "$VERSION_FILE" ]; then
    PREV_VER=$(python3 -c "import json; print(json.load(open('$VERSION_FILE'))['version'])" 2>/dev/null || echo "0")
else
    PREV_VER=0
fi
NEW_VER=$((PREV_VER + 1))
BUILD_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
info "版本：v${PREV_VER} → v${NEW_VER}"

# ─── 變更摘要 ─────────────────────────
CHANGES=()
if [ $# -gt 0 ]; then
    for arg in "$@"; do
        CHANGES+=("$arg")
    done
else
    CHANGES+=("一般迭代更新")
fi
info "變更：${CHANGES[*]}"

# ════════════════════════════════════════
# Step 1: 同步 Python 後端
# ════════════════════════════════════════
info "Step 1/7: 同步 Python 後端..."

# Agent 模組
rsync -a --delete "$DEV_ROOT/src/museon/agent/" "$PROD_ROOT/src/museon/agent/"
# Nightly 模組
rsync -a --delete "$DEV_ROOT/src/museon/nightly/" "$PROD_ROOT/src/museon/nightly/"
# Gateway 模組
rsync -a --delete "$DEV_ROOT/src/museon/gateway/" "$PROD_ROOT/src/museon/gateway/"

# 驗證 import
cd "$PROD_ROOT"
PYTHONPATH="./src:$PYTHONPATH" python3 -c "
from museon.agent.brain import MuseonBrain
from museon.agent.kernel_guard import KernelGuard
from museon.agent.drift_detector import DriftDetector
from museon.agent.golden_test import GoldenTestSuite
from museon.agent.anima_exporter import AnimaExporter
print('Python imports OK')
" || fail "Python import 驗證失敗"
cd "$DEV_ROOT"

success "Python 後端同步完成"

# ════════════════════════════════════════
# Step 2: 重建 ASAR
# ════════════════════════════════════════
info "Step 2/7: 重建 ASAR..."

ASAR_WORK="/tmp/museon_asar_build"
rm -rf "$ASAR_WORK"
mkdir -p "$ASAR_WORK"

# 解壓現有 ASAR（保留 node_modules 等）
npx @electron/asar extract "$APP_ASAR" "$ASAR_WORK/extracted" 2>/dev/null

# 用 dev 最新檔案覆蓋
cp "$DEV_ROOT/electron/src/app.js"       "$ASAR_WORK/extracted/src/app.js"
cp "$DEV_ROOT/electron/src/styles.css"   "$ASAR_WORK/extracted/src/styles.css"
cp "$DEV_ROOT/electron/src/index.html"   "$ASAR_WORK/extracted/src/index.html"
cp "$DEV_ROOT/electron/src/topology.js"  "$ASAR_WORK/extracted/src/topology.js"
cp "$DEV_ROOT/electron/main.js"          "$ASAR_WORK/extracted/main.js"
cp "$DEV_ROOT/electron/preload.js"       "$ASAR_WORK/extracted/preload.js"

# 重新打包
npx @electron/asar pack "$ASAR_WORK/extracted" "$ASAR_WORK/app.asar" 2>/dev/null
ASAR_SHA=$(shasum -a 256 "$ASAR_WORK/app.asar" | cut -c1-16)

success "ASAR 重建完成 (SHA: $ASAR_SHA)"

# ════════════════════════════════════════
# Step 3: 部署 ASAR
# ════════════════════════════════════════
info "Step 3/7: 部署 ASAR..."

cp "$ASAR_WORK/app.asar" "$APP_ASAR"
cp "$ASAR_WORK/app.asar" "$PROD_ASAR"

# 驗證 SHA256 一致
SHA_APP=$(shasum -a 256 "$APP_ASAR" | cut -c1-16)
SHA_PROD=$(shasum -a 256 "$PROD_ASAR" | cut -c1-16)

if [ "$SHA_APP" != "$SHA_PROD" ]; then
    fail "ASAR SHA256 不一致：$SHA_APP vs $SHA_PROD"
fi

success "ASAR 部署完成 (SHA: $SHA_APP)"

# ════════════════════════════════════════
# Step 4: 寫入版本標記
# ════════════════════════════════════════
info "Step 4/7: 寫入版本標記..."

# JSON 格式的 changes 陣列
CHANGES_JSON="["
for i in "${!CHANGES[@]}"; do
    if [ $i -gt 0 ]; then CHANGES_JSON+=","; fi
    CHANGES_JSON+="\"${CHANGES[$i]}\""
done
CHANGES_JSON+="]"

cat > "$VERSION_FILE" << EOF
{
  "version": $NEW_VER,
  "build_at": "$BUILD_AT",
  "changes": $CHANGES_JSON,
  "asar_sha256": "$ASAR_SHA"
}
EOF

# 更新 CHANGELOG.md
if [ ! -f "$CHANGELOG_FILE" ]; then
    echo "# MUSEON 版本變更紀錄" > "$CHANGELOG_FILE"
    echo "" >> "$CHANGELOG_FILE"
fi

# 在檔案第三行後插入新版本紀錄
CHANGELOG_ENTRY="## v${NEW_VER} — $(date '+%Y-%m-%d %H:%M')\n"
for c in "${CHANGES[@]}"; do
    CHANGELOG_ENTRY+="- ${c}\n"
done
CHANGELOG_ENTRY+="\n"

# 使用 python 在正確位置插入
python3 -c "
import sys
lines = open('$CHANGELOG_FILE', 'r').readlines()
header = lines[:2] if len(lines) >= 2 else lines
rest = lines[2:] if len(lines) >= 2 else []
entry = '''$CHANGELOG_ENTRY'''
with open('$CHANGELOG_FILE', 'w') as f:
    f.writelines(header)
    f.write(entry)
    f.writelines(rest)
"

success "版本標記 v${NEW_VER} 寫入完成"

# ════════════════════════════════════════
# Step 5: 重建 DMG
# ════════════════════════════════════════
info "Step 5/7: 重建 DMG..."

cd "$DEV_ROOT/electron"
export CSC_IDENTITY_AUTO_DISCOVERY=false
export ELECTRON_BUILDER_SIGN=false

npm run build 2>&1 | tail -5

DMG_FILE=$(find dist -name "*.dmg" -type f 2>/dev/null | head -n 1)

if [ -z "$DMG_FILE" ]; then
    warn "DMG 打包失敗，跳過 DMG 更新（ASAR 已更新）"
else
    cp "$DMG_FILE" "$DMG_DEST"
    DMG_SIZE=$(du -h "$DMG_DEST" | cut -f1)
    success "DMG 重建完成 ($DMG_SIZE)"
fi

cd "$DEV_ROOT"

# ════════════════════════════════════════
# Step 6: 驗證
# ════════════════════════════════════════
info "Step 6/7: 驗證..."

# 驗證 ASAR 一致性
FINAL_SHA=$(shasum -a 256 "$APP_ASAR" | cut -c1-16)
info "ASAR SHA256: $FINAL_SHA"

# 驗證版本標記
VER_CHECK=$(python3 -c "import json; d=json.load(open('$VERSION_FILE')); print(f'v{d[\"version\"]} @ {d[\"build_at\"]}')")
info "版本標記: $VER_CHECK"

success "驗證通過"

# ════════════════════════════════════════
# Step 7: 通知
# ════════════════════════════════════════
info "Step 7/7: 發送通知..."

# 3 beeps
osascript -e 'beep 3' 2>/dev/null || true

# Telegram
CHANGES_TEXT=""
for c in "${CHANGES[@]}"; do
    CHANGES_TEXT+="• ${c}\n"
done

curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d "{
    \"chat_id\": \"${TG_CHAT}\",
    \"text\": \"🚀 MUSEON v${NEW_VER} 部署完成\n\n📋 變更：\n${CHANGES_TEXT}\n📦 ASAR: ${FINAL_SHA}\n⏰ ${BUILD_AT}\n\n💡 Dashboard 會顯示更新通知\"
  }" > /dev/null 2>&1

success "通知已發送"

echo ""
echo "════════════════════════════════════════"
echo "   ✅ MUSEON v${NEW_VER} 部署完成！"
echo ""
echo "   ASAR SHA: $FINAL_SHA"
echo "   版本標記: $VER_CHECK"
[ -n "$DMG_FILE" ] && echo "   DMG: $DMG_DEST ($DMG_SIZE)"
echo "════════════════════════════════════════"
echo ""

# 清理
rm -rf "$ASAR_WORK"
