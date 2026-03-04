#!/bin/bash
#
# MUSEON 一鍵安裝程式 — Portable Bundle v2.2
#
# ✅ 整個 MUSEON/ 資料夾搬到任何位置，雙擊此檔案即可安裝
# ✅ 自動偵測搬家，重建虛擬環境
# ✅ 所有安裝邏輯在 python -m museon.installer（BDD 可測試模組）
#
# 目錄結構：
#   MUSEON/                    ← install_dir（此腳本所在）
#   ├── Install-MUSEON.command ← 你在這裡
#   ├── .env.example           ← API Key 範本
#   ├── data/                  ← 使用者資料
#   ├── logs/                  ← 系統日誌
#   └── .runtime/              ← 程式碼（src/, electron/, pyproject.toml）
#       └── .venv/             ← Python 虛擬環境
#

set -e

# ─── 找到安裝根目錄（此腳本所在位置） ───
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$INSTALL_DIR/.runtime"

echo ""
echo "  🐾 MUSEON Installer Bootstrap v2.2"
echo "  ================================"
echo "  安裝目錄: $INSTALL_DIR"
echo "  程式目錄: $RUNTIME_DIR"
echo ""

# ─── 檢查 .runtime/ 是否存在 ───
if [ ! -d "$RUNTIME_DIR" ] || [ ! -f "$RUNTIME_DIR/pyproject.toml" ]; then
    echo "  ❌ 找不到 .runtime/ 目錄或 pyproject.toml"
    echo "     請確認解壓縮完整。"
    echo ""
    read -p "按 Enter 關閉..." -r
    exit 1
fi

# ─── 自動複製 .env.example → .env（首次安裝） ───
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ -f "$INSTALL_DIR/.env.example" ]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
        echo "  ✓ 已建立 .env（請稍後填入你的 API Key）"
    fi
fi

# ─── 建立 data/ 和 logs/ 目錄 ───
mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs"

# ─── 尋找 Python >= 3.11 ───
find_python() {
    for cmd in python3.13 python3.12 python3.11 python3; do
        local path
        path=$(command -v "$cmd" 2>/dev/null) || continue
        local version
        version=$("$path" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
        local major minor
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 11 ]; then
            echo "$path"
            return 0
        fi
    done
    return 1
}

PYTHON_PATH=$(find_python) || {
    echo "  ❌ 找不到 Python >= 3.11"
    echo "  請先安裝: brew install python@3.13"
    echo ""
    read -p "按 Enter 關閉..." -r
    exit 1
}

echo "  ✓ Python: $PYTHON_PATH"

# ─── 建立/重用虛擬環境（在 .runtime/ 裡，含搬家偵測） ───
VENV_DIR="$RUNTIME_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_MARKER="$VENV_DIR/.museon_home"
NEED_REBUILD=false

if [ -f "$VENV_PYTHON" ]; then
    # 檢查 venv 是否在當前位置建立（搬家偵測）
    if [ -f "$VENV_MARKER" ]; then
        SAVED_HOME=$(cat "$VENV_MARKER")
        if [ "$SAVED_HOME" != "$INSTALL_DIR" ]; then
            echo "  ⚠ 偵測到資料夾已搬家"
            echo "    舊位置: $SAVED_HOME"
            echo "    新位置: $INSTALL_DIR"
            echo "  → 重建虛擬環境..."
            NEED_REBUILD=true
        fi
    else
        # 沒有 marker，用 pyvenv.cfg 的 home 欄位驗證
        if [ -f "$VENV_DIR/pyvenv.cfg" ]; then
            CFG_HOME=$(grep "^home" "$VENV_DIR/pyvenv.cfg" | head -1 | cut -d= -f2 | tr -d ' ')
            if [ -n "$CFG_HOME" ] && [ ! -d "$CFG_HOME" ]; then
                echo "  ⚠ 虛擬環境的 Python 路徑失效，重建中..."
                NEED_REBUILD=true
            fi
        fi
    fi
else
    NEED_REBUILD=true
fi

if [ "$NEED_REBUILD" = true ]; then
    # 清除舊的 venv（如果有的話）
    [ -d "$VENV_DIR" ] && rm -rf "$VENV_DIR"

    echo "  → 建立虛擬環境..."
    "$PYTHON_PATH" -m venv "$VENV_DIR"

    # 寫入位置 marker
    echo "$INSTALL_DIR" > "$VENV_MARKER"
    echo "  ✓ 虛擬環境已建立"
else
    echo "  ✓ 虛擬環境已存在"
fi

# ─── 確保 museon 套件可用（從 .runtime/ 安裝） ───
if ! "$VENV_PYTHON" -c "import museon.installer" 2>/dev/null; then
    echo "  → 安裝 MUSEON 套件..."
    cd "$RUNTIME_DIR"
    "$VENV_PYTHON" -m pip install -e ".[dev]" --quiet
    cd "$INSTALL_DIR"
    echo "  ✓ 套件安裝完成"
fi

# ─── 交給 Python 安裝程式 ───
echo ""
echo "  → 啟動 BDD 安裝流程..."
echo ""

export MUSEON_HOME="$INSTALL_DIR"
"$VENV_PYTHON" -m museon.installer "$@"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "  🎉 安裝完成！"
else
    echo "  ⚠️  安裝過程中有問題，請查看上方日誌"
fi

echo ""
read -p "按 Enter 關閉..." -r
