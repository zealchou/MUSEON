#!/bin/bash
# ═══════════════════════════════════════════════════
# MUSEON Gateway 標準啟動腳本 v2.0
#
# 注意：macOS 的 fork() 限制不支援 Gunicorn pre-fork 模式
# （objc_initializeAfterForkError — Objective-C runtime 在 fork 後崩潰）
# 保留 uvicorn 直接啟動，由 launchd 管理進程生命週期。
#
# 由 launchd plist 呼叫，或手動呼叫作為備用啟動腳本。
# ═══════════════════════════════════════════════════

set -e

# ─── 路徑設定 ─────────────────────────────────────
export PATH="/usr/sbin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
MUSEON_HOME="${MUSEON_HOME:-/Users/ZEALCHOU/MUSEON}"
VENV_BIN="$MUSEON_HOME/.runtime/.venv/bin"
PYTHONPATH="${PYTHONPATH:-$MUSEON_HOME/.runtime/src}"
export PYTHONPATH

# ─── 清理 __pycache__（防止舊 bytecode 污染）──────
find "$MUSEON_HOME/.runtime/src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

# ─── 啟動 Gateway（uvicorn 直接模式）────────────
exec "$VENV_BIN/python" -m museon.gateway.server
