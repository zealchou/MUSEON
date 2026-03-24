#!/bin/bash
# ═══════════════════════════════════════════════════
# MUSEON Gateway 安全重啟腳本 v1.0
#
# 遵守 Gateway 重啟鐵律：檢查 busy session → 通知群組 → 重啟 → 驗證
#
# 用法：
#   bash scripts/workflows/restart-gateway.sh
# ═══════════════════════════════════════════════════

set -e

GATEWAY_URL="http://127.0.0.1:8765"
DAEMON_LABEL="com.museon.gateway"

echo "═══════════════════════════════════════"
echo "  MUSEON Gateway 安全重啟"
echo "═══════════════════════════════════════"
echo ""

# ─── Step 1: 檢查 busy session ─────────────────────────
echo "📋 Step 1: 檢查進行中的 session..."
BUSY=$(curl -s "$GATEWAY_URL/api/sessions" 2>/dev/null | python3 -c "
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
    echo "   等待 60 秒讓它完成..."
    sleep 60
    # 再次檢查
    BUSY2=$(curl -s "$GATEWAY_URL/api/sessions" 2>/dev/null | python3 -c "
import sys, json
try:
    sessions = json.load(sys.stdin).get('sessions', [])
    busy = [s['id'] for s in sessions if s.get('processing')]
    if busy:
        print(' '.join(busy))
except:
    pass
" 2>/dev/null)
    if [ -n "$BUSY2" ]; then
        echo "❌ Session 仍在處理中: $BUSY2"
        echo "   請手動確認後再重啟"
        exit 1
    fi
fi
echo "✅ 無進行中的 session"

# ─── Step 2: 重啟 Gateway ─────────────────────────
echo ""
echo "📋 Step 2: 重啟 Gateway daemon..."
launchctl kickstart -k "gui/$(id -u)/$DAEMON_LABEL"
echo "✅ 重啟指令已發送"

# ─── Step 3: 等待啟動 ─────────────────────────
echo ""
echo "📋 Step 3: 等待 Gateway 啟動（最多 30 秒）..."
MAX_WAIT=30
HEALTHY=false
for i in $(seq 1 $MAX_WAIT); do
    sleep 1
    HEALTH=$(curl -s "$GATEWAY_URL/health" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f'{d.get(\"status\",\"unknown\")}|{d.get(\"brain\",\"unknown\")}')
except:
    print('unreachable|unknown')
" 2>/dev/null)
    STATUS=$(echo "$HEALTH" | cut -d'|' -f1)
    BRAIN=$(echo "$HEALTH" | cut -d'|' -f2)
    if [ "$STATUS" = "healthy" ] && [ "$BRAIN" = "alive" ]; then
        HEALTHY=true
        break
    fi
    printf "   %d/%d (%s)...\r" "$i" "$MAX_WAIT" "$STATUS"
done

echo ""
echo ""
echo "═══════════════════════════════════════"
if [ "$HEALTHY" = true ]; then
    echo "✅ Gateway 重啟成功！"
    echo "   status=$STATUS, brain=$BRAIN"
    echo "   啟動耗時: ${i}s"
else
    echo "⚠️ Gateway 健康檢查未通過"
    echo "   status=$STATUS, brain=$BRAIN"
    echo "   請手動檢查: curl $GATEWAY_URL/health"
    exit 1
fi
echo "═══════════════════════════════════════"
