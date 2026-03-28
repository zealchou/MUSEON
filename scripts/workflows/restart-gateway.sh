#!/bin/bash
# ═══════════════════════════════════════════════════
# MUSEON Gateway 安全重啟腳本 v2.1（uvicorn + launchd 版）
#
# 核心改動（vs v1.0）：
#   - 移除 kickstart -k（不強殺 launchd 控制的進程）
#   - 改用 launchctl kickstart（不加 -k，讓 launchd 優雅處理）
#   - 驗證改查 /health/live（純 liveness，不等 brain 深度檢查）
#   - 等待時間延長至 60 秒（uvicorn + Brain 初始化需要時間）
#
# 用法：
#   bash scripts/workflows/restart-gateway.sh
# ═══════════════════════════════════════════════════

set -e

export PATH="/usr/sbin:$PATH"

GATEWAY_URL="http://127.0.0.1:8765"
DAEMON_LABEL="com.museon.gateway"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "═══════════════════════════════════════"
echo "  MUSEON Gateway 安全重啟 v2.1"
echo "═══════════════════════════════════════"
echo ""

# ─── Step 1: 檢查 busy session ─────────────────────────
echo "📋 Step 1: 檢查進行中的 session..."
BUSY=$(curl -s --connect-timeout 5 --max-time 10 "$GATEWAY_URL/api/sessions" 2>/dev/null | python3 -c "
import sys, json
try:
    sessions = json.load(sys.stdin).get('sessions', [])
    busy = [s['id'] for s in sessions if s.get('processing')]
    if busy:
        print(' '.join(busy))
except:
    pass
" 2>/dev/null)

if [ -n "$BUSY" ]; then
    echo "⚠️  有進行中的 session: $BUSY"
    echo "   等待 30 秒讓它完成..."
    sleep 30
fi
echo "✅ session 檢查完成"

# ─── Step 1.5: 同步 src/ → .runtime/src/ ─────────────────
echo ""
echo "📋 Step 1.5: 同步 src/ → .runtime/src/..."
if [ -d "$PROJECT_DIR/.runtime/src" ]; then
    find "$PROJECT_DIR/src" "$PROJECT_DIR/.runtime/src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find "$PROJECT_DIR/src" "$PROJECT_DIR/.runtime/src" -name "*.pyc" -delete 2>/dev/null || true
    rsync -a --delete \
        --exclude='__pycache__' --exclude='.DS_Store' \
        "$PROJECT_DIR/src/" "$PROJECT_DIR/.runtime/src/"
    echo "✅ .runtime 同步完成"
else
    echo "⚠️  .runtime/src 不存在，跳過同步"
fi

# ─── Step 2: 透過 launchctl 重啟 ─────────────────
echo ""
echo "📋 Step 2: 重啟 Gateway（透過 launchd）..."

# 不加 -k 旗標：讓 launchd 自然停止後重啟，不強殺
# launchctl kickstart 如果 service 已在運行，需要先 stop
launchctl stop "gui/$(id -u)/$DAEMON_LABEL" 2>/dev/null || true
sleep 3
launchctl kickstart "gui/$(id -u)/$DAEMON_LABEL" 2>/dev/null || \
    echo "   (kickstart 失敗，launchd 的 KeepAlive 會自動重啟)"
echo "✅ 重啟指令已發送"

# ─── Step 3: 等待 /health/live 回應 ──────────────────
echo ""
echo "📋 Step 3: 等待 Gateway liveness（最多 60 秒）..."
MAX_WAIT=60
ALIVE=false
for i in $(seq 1 $MAX_WAIT); do
    sleep 1
    STATUS=$(curl -s --connect-timeout 3 --max-time 5 "$GATEWAY_URL/health/live" 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))" 2>/dev/null || echo "unreachable")
    if [ "$STATUS" = "ok" ]; then
        ALIVE=true
        break
    fi
    printf "   %d/%d (%s)...\r" "$i" "$MAX_WAIT" "$STATUS"
done

echo ""
echo ""
echo "═══════════════════════════════════════"
if [ "$ALIVE" = true ]; then
    echo "✅ Gateway 重啟成功！（${i}s）"
    echo "   /health/live: ok"
else
    echo "⚠️  Gateway liveness 未通過（${MAX_WAIT}s timeout）"
    echo "   請手動檢查：curl $GATEWAY_URL/health/live"
    echo "   日誌：tail -f $PROJECT_DIR/logs/gateway.err"
    exit 1
fi
echo "═══════════════════════════════════════"
