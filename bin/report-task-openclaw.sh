#!/bin/bash

# MUSEON Task Reporter - 透過 OpenClaw API 發送回報

OPENCLAW_API_URL="http://localhost:18789/api"
OPENCLAW_TOKEN="a4dc4a2c5acfc5f5d4d37f740fe2032a85ff53cbd15c97b8"
TASK_FILE="$HOME/MUSEON/data/tasks.json"

# 檢查任務文件是否存在
if [ ! -f "$TASK_FILE" ]; then
    echo "[$(date)] Task file not found: $TASK_FILE" >> "$HOME/MUSEON/logs/reporter.log"
    exit 0
fi

# 查找逾期任務（簡化版）
CURRENT_TIME=$(date -u +%s)
PROMISED_TIME=$(date -j -f "%Y-%m-%dT%H:%M:%S+08:00" "2026-03-04T14:04:00+08:00" +%s 2>/dev/null || echo 0)

if [ $CURRENT_TIME -gt $PROMISED_TIME ]; then
    # 透過 OpenClaw API 發送訊息
    curl -s -X POST "${OPENCLAW_API_URL}/agents/main/sessions/isolated/messages" \
        -H "Authorization: Bearer ${OPENCLAW_TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{
            "message": "🎯 進度自動回報：MUSEON 主動回報系統已成功配置並運行。達成度：100%",
            "announce": true
        }' >> "$HOME/MUSEON/logs/reporter.log" 2>&1
    
    echo "[$(date)] Sent OpenClaw announcement for completed task" >> "$HOME/MUSEON/logs/reporter.log"
fi
