#!/bin/bash
# 臨時取得最新訊息的 chat ID（需要你先傳一個訊息給 bot）
TOKEN="8694763877:AAE1dti1giO_4FXA3kVSIXPWP0YcYP43FXM"
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | jq '.result[-1].message.chat.id'
