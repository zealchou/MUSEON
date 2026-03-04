#!/bin/bash
#
# MUSEON 自解壓安裝包打包腳本
#
# 用途: 將專案打包為單一 .command 自解壓安裝檔
# 使用方式:
#   cd museon
#   ./scripts/build-installer.sh
#
# 輸出:
#   dist/Install-MUSEON.command
#

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "  ====================================="
echo "  MUSEON 自解壓安裝包打包程式"
echo "  ====================================="
echo ""

cd "$PROJECT_DIR"

# 檢查 venv
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "  ❌ 找不到 .venv，請先執行: pip install -e '.[dev]'"
    exit 1
fi

# 建立輸出目錄
mkdir -p dist

# 執行打包
echo "  → 開始打包..."
echo ""

"$VENV_PYTHON" -c "
from pathlib import Path
from museon.installer.packager import InstallerPackager

packager = InstallerPackager()
result = packager.build(
    project_dir=Path('$PROJECT_DIR'),
    output_path=Path('$PROJECT_DIR/dist/Install-MUSEON.command'),
)

print(f'  狀態: {result.status.value}')
print(f'  訊息: {result.message}')
if result.details:
    for k, v in result.details.items():
        print(f'  {k}: {v}')
"

# 報告結果
if [ -f "dist/Install-MUSEON.command" ]; then
    SIZE=$(du -h "dist/Install-MUSEON.command" | cut -f1)
    echo ""
    echo "  ====================================="
    echo "  ✅ 打包完成！"
    echo ""
    echo "  輸出: dist/Install-MUSEON.command"
    echo "  大小: $SIZE"
    echo "  ====================================="
    echo ""

    # ═══════════════════════════════════════
    # 安裝後自動驗證（防止反覆出包）
    # ═══════════════════════════════════════
    echo "  → 執行打包後自動驗證..."
    echo ""
    VERIFY_PASS=true

    # V1: main.js getProjectRoot() 必須支援生產佈局
    if grep -q "\.runtime.*pyproject\.toml" "$PROJECT_DIR/electron/main.js"; then
        echo "  ✅ V1: getProjectRoot() 支援 .runtime/pyproject.toml"
    else
        echo "  ❌ V1: getProjectRoot() 不支援 .runtime 佈局 — 會導致生產版 .env 被忽略！"
        VERIFY_PASS=false
    fi

    # V2: preload.js 有完整的 API bridge
    PRELOAD="$PROJECT_DIR/electron/preload.js"
    MISSING_API=""
    for api in getAutoLaunch setAutoLaunch getGatewayInfo getTelegramStatus getBudgetStats setBudgetLimit getAgentState getGuardianStatus runGuardianCheck getToolsList getToolsStatus toggleTool installTool installToolsBatch getInstallProgress getVectorStatus vectorSearch getSandboxStatus; do
        if ! grep -q "$api" "$PRELOAD" 2>/dev/null; then
            MISSING_API="$MISSING_API $api"
        fi
    done
    if [ -z "$MISSING_API" ]; then
        echo "  ✅ V2: preload.js API 完整"
    else
        echo "  ❌ V2: preload.js 缺少 API:$MISSING_API"
        VERIFY_PASS=false
    fi

    # V3: app.js toggle 綁定了狀態和事件
    if grep -q "autoLaunchEnabled" "$PROJECT_DIR/electron/src/app.js" && \
       grep -q "setAutoLaunch" "$PROJECT_DIR/electron/src/app.js"; then
        echo "  ✅ V3: 開機自動啟動 toggle 已綁定狀態/事件"
    else
        echo "  ❌ V3: 開機自動啟動 toggle 未綁定狀態或事件！"
        VERIFY_PASS=false
    fi

    # V4: findPython 有 fastapi 驗證（防 zombie venv）
    if grep -q "import fastapi" "$PROJECT_DIR/electron/main.js"; then
        echo "  ✅ V4: findPython() 有 fastapi 驗證"
    else
        echo "  ❌ V4: findPython() 無 fastapi 驗證 — 可能用到 zombie venv！"
        VERIFY_PASS=false
    fi

    # V5: UI 無殘留英文（關鍵字檢查）
    for eng_word in "'Loading...'" "'Gateway'" "'Uptime'" "'Port'" "'ON'" "'OFF'"; do
        if grep -q "$eng_word" "$PROJECT_DIR/electron/src/app.js" 2>/dev/null; then
            echo "  ⚠️  V5: app.js 仍有英文 $eng_word"
            VERIFY_PASS=false
        fi
    done
    if $VERIFY_PASS; then
        echo "  ✅ V5: UI 中文化完整"
    fi

    # V7: orchestrator 有 _step_tools（工具安裝步驟）
    if grep -q "_step_tools" "$PROJECT_DIR/src/museon/installer/orchestrator.py"; then
        echo "  ✅ V7: 安裝器包含工具安裝步驟"
    else
        echo "  ❌ V7: 安裝器缺少 _step_tools — 工具不會被自動安裝！"
        VERIFY_PASS=false
    fi

    # V10: 安裝檔大小不超過 200MB（防止意外打包大型模型/工具）
    SIZE_KB=$(du -k "dist/Install-MUSEON.command" | cut -f1)
    SIZE_MB=$((SIZE_KB / 1024))
    if [ "$SIZE_MB" -gt 200 ]; then
        echo "  ❌ V10: 安裝檔 ${SIZE_MB}MB 過大（上限 200MB）— 可能打包了工具模型！"
        VERIFY_PASS=false
    else
        echo "  ✅ V10: 安裝檔大小合理（${SIZE_MB}MB）"
    fi

    # V8: Firecrawl image 已更新（mendableai → firecrawl org）
    REGISTRY_PY="$PROJECT_DIR/src/museon/tools/tool_registry.py"
    if grep -q "ghcr.io/mendableai" "$REGISTRY_PY" 2>/dev/null; then
        echo "  ❌ V8: tool_registry.py 仍使用已廢棄的 ghcr.io/mendableai — Firecrawl 會安裝失敗！"
        VERIFY_PASS=false
    else
        echo "  ✅ V8: Firecrawl image 使用正確 org (firecrawl)"
    fi

    # V9: tool_registry 健康檢查有 HTTPError 處理
    if grep -q "HTTPError" "$REGISTRY_PY" 2>/dev/null; then
        echo "  ✅ V9: 健康檢查有 HTTPError 處理（4xx 容錯）"
    else
        echo "  ❌ V9: 健康檢查缺少 HTTPError 處理 — POST-only 端點會誤判為不健康！"
        VERIFY_PASS=false
    fi

    # V6: 正式版同步驗證 + 自動同步
    # 偵測已安裝的正式版，自動同步最新程式碼
    PROD_RUNTIME="$HOME/MUSEON 正式版/MUSEON/.runtime"
    if [ -d "$PROD_RUNTIME/src" ]; then
        echo ""
        echo "  → 偵測到正式版安裝，執行自動同步..."

        # 同步 Python 原始碼
        rsync -a --delete \
            --exclude='__pycache__' --exclude='.DS_Store' \
            "$PROJECT_DIR/src/" "$PROD_RUNTIME/src/" 2>/dev/null

        # 同步 Electron 原始碼（不覆蓋 node_modules）
        for ef in main.js preload.js .babelrc; do
            cp "$PROJECT_DIR/electron/$ef" "$PROD_RUNTIME/electron/$ef" 2>/dev/null
        done
        rsync -a --delete \
            --exclude='node_modules' --exclude='.DS_Store' \
            "$PROJECT_DIR/electron/src/" "$PROD_RUNTIME/electron/src/" 2>/dev/null

        # 同步 skills
        if [ -d "$PROJECT_DIR/data/skills" ]; then
            rsync -a --delete \
                --exclude='__pycache__' --exclude='.DS_Store' \
                "$PROJECT_DIR/data/skills/" "$PROD_RUNTIME/data/skills/" 2>/dev/null
        fi

        # 驗證同步結果
        V6_OK=true
        # 抽樣比對：server.py 的 md5
        DEV_HASH=$(md5 -q "$PROJECT_DIR/src/museon/gateway/server.py" 2>/dev/null)
        PROD_HASH=$(md5 -q "$PROD_RUNTIME/src/museon/gateway/server.py" 2>/dev/null)
        if [ "$DEV_HASH" = "$PROD_HASH" ] && [ -n "$DEV_HASH" ]; then
            echo "  ✅ V6: 正式版已同步最新程式碼 (server.py ✓)"
        else
            echo "  ❌ V6: 正式版同步失敗 — server.py hash 不符！"
            echo "       DEV:  $DEV_HASH"
            echo "       PROD: $PROD_HASH"
            V6_OK=false
            VERIFY_PASS=false
        fi

        # 抽樣比對：brain.py
        DEV_HASH2=$(md5 -q "$PROJECT_DIR/src/museon/agent/brain.py" 2>/dev/null)
        PROD_HASH2=$(md5 -q "$PROD_RUNTIME/src/museon/agent/brain.py" 2>/dev/null)
        if [ "$DEV_HASH2" = "$PROD_HASH2" ] && [ -n "$DEV_HASH2" ]; then
            echo "  ✅ V6: brain.py 同步確認 ✓"
        else
            echo "  ❌ V6: brain.py 同步失敗！"
            V6_OK=false
            VERIFY_PASS=false
        fi

        # 抽樣比對：app.js
        DEV_HASH3=$(md5 -q "$PROJECT_DIR/electron/src/app.js" 2>/dev/null)
        PROD_HASH3=$(md5 -q "$PROD_RUNTIME/electron/src/app.js" 2>/dev/null)
        if [ "$DEV_HASH3" = "$PROD_HASH3" ] && [ -n "$DEV_HASH3" ]; then
            echo "  ✅ V6: app.js 同步確認 ✓"
        else
            echo "  ❌ V6: app.js 同步失敗！"
            V6_OK=false
            VERIFY_PASS=false
        fi
        # V6b: 重建 Electron app 並更新 /Applications/MUSEON.app
        if [ "$V6_OK" = true ] && [ -f "$PROD_RUNTIME/electron/package.json" ]; then
            echo ""
            echo "  → 重建 Electron app（確保 app.asar 包含最新程式碼）..."
            ELECTRON_DIR="$PROD_RUNTIME/electron"
            if command -v npm &>/dev/null && (cd "$ELECTRON_DIR" && npm run build 2>/dev/null); then
                NEW_APP="$ELECTRON_DIR/dist/mac-arm64/MUSEON.app"
                if [ -d "$NEW_APP" ]; then
                    if [ -d /Applications/MUSEON.app ]; then
                        mv /Applications/MUSEON.app /tmp/MUSEON-prev-$$.app 2>/dev/null
                    fi
                    cp -R "$NEW_APP" /Applications/MUSEON.app 2>/dev/null
                    # 驗證 asar hash
                    BUILD_ASAR_HASH=$(md5 -q "$NEW_APP/Contents/Resources/app.asar" 2>/dev/null)
                    INSTALLED_ASAR_HASH=$(md5 -q /Applications/MUSEON.app/Contents/Resources/app.asar 2>/dev/null)
                    if [ "$BUILD_ASAR_HASH" = "$INSTALLED_ASAR_HASH" ] && [ -n "$BUILD_ASAR_HASH" ]; then
                        echo "  ✅ V6b: MUSEON.app 已重建並安裝（asar hash 驗證通過）"
                    else
                        echo "  ⚠️  V6b: MUSEON.app 安裝但 hash 不符，請手動檢查"
                        VERIFY_PASS=false
                    fi
                else
                    echo "  ⚠️  V6b: Electron 打包完成但找不到 .app 輸出"
                fi
            else
                echo "  ⚠️  V6b: npm 不可用或 Electron 打包失敗，跳過 MUSEON.app 更新"
            fi
        fi
    else
        echo ""
        echo "  ℹ️  V6: 未偵測到正式版安裝（跳過同步）"
    fi

    echo ""
    if $VERIFY_PASS; then
        echo "  ✅ 所有驗證通過"
    else
        echo "  ⚠️  部分驗證未通過 — 請修復後再發布"
    fi

    echo ""
    echo "  使用方式:"
    echo "  1. 將此檔案傳給客戶"
    echo "  2. 客戶雙擊即可自動安裝"
    echo "  ====================================="
    echo ""
else
    echo ""
    echo "  ❌ 打包失敗"
    exit 1
fi
