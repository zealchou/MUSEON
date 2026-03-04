#!/bin/bash

# MUSEON Task Reporter - 每 10 分鐘檢查是否有承諾需要回報

TELEGRAM_BOT_TOKEN="8570443079:AAG1EbgVr_JoAAnlNo_Ydt7XGFvfd9j7dyys"
TELEGRAM_CHAT_ID="6969045906"  # 需要替換成實際的 chat ID
TASK_FILE="$HOME/MUSEON/data/tasks.json"

# 檢查任務文件是否存在
if [ ! -f "$TASK_FILE" ]; then
    echo "[$(date)] Task file not found: $TASK_FILE" >> "$HOME/MUSEON/logs/reporter.log"
    exit 0
fi

# 查找所有逾期未回報的任務
OVERDUE_TASKS=$(jq '.tasks[] | select(.status=="in_progress" and (.promised_completion < now | strftime("%Y-%m-%dT%H:%M:%S+08:00")))' "$TASK_FILE" 2>/dev/null)

if [ -n "$OVERDUE_TASKS" ]; then
    MESSAGE="⏰ 進度回報：有逾期承諾需要更新
$OVERDUE_TASKS"
    
    # 透過 Telegram Bot API 發送訊息
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" \
        -d "text=${MESSAGE}" \
        >> "$HOME/MUSEON/logs/reporter.log" 2>&1
    
    echo "[$(date)] Sent report for overdue tasks" >> "$HOME/MUSEON/logs/reporter.log"
fi
