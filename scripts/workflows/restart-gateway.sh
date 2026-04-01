#!/bin/bash
# ═══════════════════════════════════════════════════
# MUSEON Gateway 安全重啟腳本 v3.0（supervisord 版）
#
# 核心改動（vs v2.1）：
#   - 改用 supervisorctl restart（取代 launchctl stop/kickstart）
#   - supervisord 確保序列化重啟，消除雙實例衝突
#   - 等待時間維持 60 秒，驗證改查 /health/live
#
# 用法：
#   bash scripts/workflows/restart-gateway.sh
# ═══════════════════════════════════════════════════

set -e

export PATH="/usr/sbin:$PATH"

GATEWAY_URL="http://127.0.0.1:8765"
SUPERVISORCTL="/Users/ZEALCHOU/Library/Python/3.9/bin/supervisorctl"
SUPERVISOR_CONF="/Users/ZEALCHOU/MUSEON/data/_system/supervisord.conf"
PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "═══════════════════════════════════════"
echo "  MUSEON Gateway 安全重啟 v3.0"
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

# ─── Step 1.5: 清理 __pycache__ ─────────────────
echo ""
echo "📋 Step 1.5: 清理 src/ __pycache__..."
find "$PROJECT_DIR/src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$PROJECT_DIR/src" -name "*.pyc" -delete 2>/dev/null || true
echo "✅ __pycache__ 清理完成"

# ─── Step 2: 透過 supervisorctl 重啟 ─────────────────
echo ""
echo "📋 Step 2: 重啟 Gateway（透過 supervisord）..."

"$SUPERVISORCTL" -c "$SUPERVISOR_CONF" restart museon-gateway 2>/dev/null || \
    echo "   (restart 失敗，嘗試 start...)" && \
    "$SUPERVISORCTL" -c "$SUPERVISOR_CONF" start museon-gateway 2>/dev/null || \
    echo "   ⚠️  supervisorctl 指令失敗，請確認 supervisord 正在運行"
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
    echo "   supervisord 狀態：$SUPERVISORCTL -c $SUPERVISOR_CONF status"
    echo "   日誌：tail -f $PROJECT_DIR/logs/gateway.err"
    exit 1
fi
echo "═══════════════════════════════════════"
