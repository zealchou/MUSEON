"""自解壓安裝包打包器

對應 features/packaging.feature
將 MUSEON 專案打包為單一 .command 自解壓安裝檔
"""

import base64
import logging
import os
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

from .models import StepResult, StepStatus


class InstallerPackager:
    """MUSEON 自解壓 .command 打包器"""

    # 要包含的頂層目錄（遞迴掃描）
    INCLUDE_DIRS = [
        "src",
        "features",
        "data",
    ]

    # 要包含的頂層檔案
    INCLUDE_FILES = [
        "pyproject.toml",
        "Install-MUSEON.command",
        ".env.example",         # API Key 範本（含 PreflightGate 警告說明）
    ]

    # electron/ 下要包含的項目（不含 node_modules/, dist/）
    ELECTRON_INCLUDES = [
        "package.json",
        "package-lock.json",
        "main.js",
        "preload.js",
        ".babelrc",
        "src",      # 整個 src/ 子目錄
        "assets",   # icon.png, tray-icon.png, cis/
        "build",    # icon.icns for macOS app
        "scripts",  # generate-icon.sh (prebuild hook)
    ]

    # 全域排除模式
    EXCLUDE_PATTERNS = {
        ".venv",
        ".git",
        "node_modules",
        "__pycache__",
        "htmlcov",
        ".coverage",
        ".pytest_cache",
        ".DS_Store",
        "_tools",           # 工具本體（whisper.cpp 3GB+）— 由 _step_tools 在線安裝
        ".env",             # 🔒 防止真實 API Key 洩漏（PreflightGate 安全層）
    }

    # 敏感檔案排除（即使在 INCLUDE_DIRS 內也不打包）
    SENSITIVE_FILES = {
        "activity_log.jsonl",   # 可能含 token 討論記錄
        "heartbeat.jsonl",      # 運行時心跳日誌
    }

    # 超過此大小的檔案不打包（安全網：防止意外打包大檔案）
    MAX_FILE_SIZE_MB = 50

    # 使用者資料路徑（更新時保留）
    USER_DATA_PATHS = [".env", "data"]

    def collect_source_files(self, project_dir: Path) -> List[Path]:
        """收集要打包的來源檔案

        Args:
            project_dir: 專案根目錄

        Returns:
            要打包的檔案絕對路徑列表
        """
        files: List[Path] = []

        # 頂層檔案
        for name in self.INCLUDE_FILES:
            path = project_dir / name
            if path.exists() and path.is_file():
                files.append(path)

        # 頂層目錄（遞迴）
        for dir_name in self.INCLUDE_DIRS:
            dir_path = project_dir / dir_name
            if dir_path.exists():
                for f in dir_path.rglob("*"):
                    if f.is_file() and not self._should_exclude(f, project_dir):
                        files.append(f)

        # electron/ 特殊處理
        electron_dir = project_dir / "electron"
        if electron_dir.exists():
            for item_name in self.ELECTRON_INCLUDES:
                item_path = electron_dir / item_name
                if item_path.is_file():
                    files.append(item_path)
                elif item_path.is_dir():
                    for f in item_path.rglob("*"):
                        if f.is_file() and not self._should_exclude(f, project_dir):
                            files.append(f)

        return files

    def create_tarball(self, project_dir: Path, output_path: Path) -> StepResult:
        """建立 tar.gz 壓縮檔

        Args:
            project_dir: 專案根目錄
            output_path: 輸出 tar.gz 路徑
        """
        try:
            files = self.collect_source_files(project_dir)

            output_path.parent.mkdir(parents=True, exist_ok=True)

            with tarfile.open(str(output_path), "w:gz") as tf:
                for f in files:
                    arcname = str(f.relative_to(project_dir))
                    tf.add(str(f), arcname=arcname)

            size_kb = output_path.stat().st_size / 1024
            return StepResult(
                step_name="建立 tar.gz",
                status=StepStatus.SUCCESS,
                message=f"已建立壓縮檔 ({size_kb:.0f} KB, {len(files)} 個檔案)",
                details={"file_count": len(files), "size_kb": round(size_kb)},
            )
        except Exception as e:
            return StepResult(
                step_name="建立 tar.gz",
                status=StepStatus.FAILED,
                message=f"建立壓縮檔失敗: {e}",
            )

    def encode_base64(self, input_path: Path, output_path: Path) -> StepResult:
        """Base64 編碼 tar.gz

        Args:
            input_path: tar.gz 檔案路徑
            output_path: Base64 輸出路徑
        """
        try:
            raw = input_path.read_bytes()
            encoded = base64.b64encode(raw)
            output_path.write_bytes(encoded)

            return StepResult(
                step_name="Base64 編碼",
                status=StepStatus.SUCCESS,
                message=f"已編碼 ({len(encoded) / 1024:.0f} KB)",
            )
        except Exception as e:
            return StepResult(
                step_name="Base64 編碼",
                status=StepStatus.FAILED,
                message=f"Base64 編碼失敗: {e}",
            )

    def generate_header(self) -> str:
        """生成自解壓 shell 標頭

        Returns:
            完整的 bash 標頭字串（以 __PAYLOAD_BELOW__ 結尾）
        """
        return _HEADER_TEMPLATE

    def build(self, project_dir: Path, output_path: Path) -> StepResult:
        """完整打包流程

        collect → tarball → base64 → header → assemble

        Args:
            project_dir: 專案根目錄
            output_path: 輸出 .command 路徑
        """
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)

                # 1. 建立 tar.gz
                tarball = tmp / "payload.tar.gz"
                tar_result = self.create_tarball(project_dir, tarball)
                if tar_result.is_fatal:
                    return tar_result

                # 2. Base64 編碼
                b64_file = tmp / "payload.b64"
                b64_result = self.encode_base64(tarball, b64_file)
                if b64_result.is_fatal:
                    return b64_result

                # 3. 生成標頭
                header = self.generate_header()

                # 4. 計算載荷起始行
                header_lines = header.count("\n") + 1  # 含 __PAYLOAD_BELOW__ 那行
                payload_line = header_lines + 1

                # 替換佔位符
                header = header.replace(
                    "PAYLOAD_LINE=__PAYLOAD_LINE__",
                    f"PAYLOAD_LINE={payload_line}",
                )

                # 5. 組裝
                output_path.parent.mkdir(parents=True, exist_ok=True)
                payload_b64 = b64_file.read_text()

                with open(output_path, "w") as f:
                    f.write(header)
                    f.write("\n")
                    f.write(payload_b64)
                    if not payload_b64.endswith("\n"):
                        f.write("\n")

                # 設定執行權限
                output_path.chmod(
                    output_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                )

                size_kb = output_path.stat().st_size / 1024
                return StepResult(
                    step_name="組裝 .command",
                    status=StepStatus.SUCCESS,
                    message=f"已組裝 {output_path.name} ({size_kb:.0f} KB)",
                    details={
                        "size_kb": round(size_kb),
                        "payload_line": payload_line,
                    },
                )
        except Exception as e:
            return StepResult(
                step_name="組裝 .command",
                status=StepStatus.FAILED,
                message=f"組裝失敗: {e}",
            )

    def extract_payload(self, command_file: Path, extract_dir: Path) -> StepResult:
        """從 .command 檔案提取並解壓載荷

        Args:
            command_file: 自解壓 .command 檔案
            extract_dir: 解壓目標目錄
        """
        try:
            content = command_file.read_text()

            # 找到 __PAYLOAD_BELOW__ 標記
            marker = "__PAYLOAD_BELOW__"
            lines = content.split("\n")
            payload_start = None
            for i, line in enumerate(lines):
                if line.strip() == marker:
                    payload_start = i + 1
                    break

            if payload_start is None:
                return StepResult(
                    step_name="提取載荷",
                    status=StepStatus.FAILED,
                    message="找不到 __PAYLOAD_BELOW__ 標記",
                )

            # 提取 base64 載荷
            payload_lines = lines[payload_start:]
            b64_data = "".join(payload_lines).strip()

            # 解碼
            tar_bytes = base64.b64decode(b64_data)

            # 解壓
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                tmp.write(tar_bytes)
                tmp_path = tmp.name

            try:
                extract_dir.mkdir(parents=True, exist_ok=True)
                with tarfile.open(tmp_path, "r:gz") as tf:
                    import sys
                    if sys.version_info >= (3, 12):
                        tf.extractall(str(extract_dir), filter="data")
                    else:
                        tf.extractall(str(extract_dir))
            finally:
                os.unlink(tmp_path)

            return StepResult(
                step_name="提取載荷",
                status=StepStatus.SUCCESS,
                message=f"已解壓到 {extract_dir}",
            )
        except Exception as e:
            return StepResult(
                step_name="提取載荷",
                status=StepStatus.FAILED,
                message=f"提取載荷失敗: {e}",
            )

    def preserve_user_data(self, install_dir: Path) -> Dict[str, Path]:
        """備份使用者資料到臨時目錄

        Args:
            install_dir: 安裝目錄

        Returns:
            備份映射 {原始相對路徑: 臨時備份路徑}
        """
        backup_dir = Path(tempfile.mkdtemp(prefix="museon-backup-"))
        preserved: Dict[str, Path] = {}

        for rel_path in self.USER_DATA_PATHS:
            source = install_dir / rel_path
            if source.exists():
                dest = backup_dir / rel_path
                if source.is_file():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(source), str(dest))
                elif source.is_dir():
                    shutil.copytree(str(source), str(dest))
                preserved[rel_path] = dest

        preserved["_backup_dir"] = backup_dir
        return preserved

    def restore_user_data(self, install_dir: Path, preserved: Dict[str, Path]) -> None:
        """還原使用者資料

        Args:
            install_dir: 安裝目錄
            preserved: preserve_user_data() 的回傳值
        """
        backup_dir = preserved.get("_backup_dir")

        for rel_path, backup_path in preserved.items():
            if rel_path == "_backup_dir":
                continue

            dest = install_dir / rel_path
            if backup_path.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(backup_path), str(dest))
            elif backup_path.is_dir():
                if dest.exists():
                    shutil.rmtree(str(dest))
                shutil.copytree(str(backup_path), str(dest))

        # 清理臨時目錄
        if backup_dir and backup_dir.exists():
            shutil.rmtree(str(backup_dir))

    def _should_exclude(self, path: Path, project_dir: Path) -> bool:
        """檢查路徑是否應該被排除"""
        rel = path.relative_to(project_dir)
        parts = rel.parts
        for part in parts:
            if part in self.EXCLUDE_PATTERNS:
                return True
        # 敏感檔案排除（檔名匹配）
        if path.name in self.SENSITIVE_FILES:
            return True
        # 安全網：超過 MAX_FILE_SIZE_MB 的檔案不打包
        try:
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > self.MAX_FILE_SIZE_MB:
                return True
        except OSError as e:
            logger.debug("degraded: file stat for %s: %s", path, e)
        return False


# ─── 自解壓標頭模板 ───

_HEADER_TEMPLATE = r"""#!/bin/bash
#
# MUSEON Self-Extracting Installer
# 雙擊此檔案即可在你的 Mac 上安裝 MUSEON
#
# 此檔案包含完整的 MUSEON 原始碼（Base64 編碼）
# 解壓後自動執行 BDD 安裝流程
#

set -e

echo ""
echo "  ╔═══════════════════════════════════════════╗"
echo "  ║  🐾  MUSEON Self-Extracting Installer   ║"
echo "  ╚═══════════════════════════════════════════╝"
echo ""

PAYLOAD_LINE=__PAYLOAD_LINE__
DEFAULT_DIR="$HOME/MUSEON"

# ─── 終端機權限預檢 ───
echo "  🔐 終端機權限預檢"
echo ""

# 偵測終端機類型
detect_terminal() {
    case "${TERM_PROGRAM:-}" in
        Apple_Terminal) echo "終端機 (Terminal)" ;;
        iTerm.app)      echo "iTerm2" ;;
        WarpTerminal)   echo "Warp" ;;
        vscode)         echo "VSCode Terminal" ;;
        *)              echo "終端機" ;;
    esac
}
TERMINAL_NAME=$(detect_terminal)

# 檢查 Full Disk Access
check_full_disk_access() {
    ls "$HOME/Library/Application Support/com.apple.TCC/TCC.db" &>/dev/null 2>&1
}

# 檢查 Automation 權限
check_automation() {
    local result
    result=$(osascript -e 'tell application "System Events" to return name of current user' 2>&1) || true
    if echo "$result" | grep -q "1743"; then
        return 1
    fi
    return 0
}

FDA_OK=false
AUTO_OK=false

if check_full_disk_access; then
    echo "  ✅ Full Disk Access — 已授權"
    FDA_OK=true
else
    echo "  ⚠️  Full Disk Access — 未授權"
    echo ""
    echo "  MUSEON 需要「完整磁碟取用權限」才能存取所有檔案。"
    echo ""
    echo "  正在開啟系統設定..."
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles" 2>/dev/null || true
    sleep 1
    echo ""
    echo "  請在系統設定中："
    echo "    1. 找到「完整磁碟取用權限」(Full Disk Access)"
    echo "    2. 點擊 + 按鈕（可能需要輸入密碼）"
    echo "    3. 加入「$TERMINAL_NAME」"
    echo "    4. 確認已開啟 ✅"
    echo ""
    echo "  ⚠️  授權後需要重新啟動終端機才會生效！"
    echo ""
    read -p "  已完成按 Enter 繼續 / 輸入 skip 跳過: " FDA_CHOICE
    if [ "$FDA_CHOICE" != "skip" ]; then
        if check_full_disk_access; then
            echo "  ✅ Full Disk Access — 已授權"
            FDA_OK=true
        else
            echo "  ⚠️  尚未偵測到權限（可能需要重啟終端機），安裝將繼續"
        fi
    fi
fi

if check_automation; then
    echo "  ✅ Automation — 已授權"
    AUTO_OK=true
else
    echo "  ⚠️  Automation — 未授權"
    echo "  MUSEON 需要 Automation 權限來與其他應用互動。"
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation" 2>/dev/null || true
    echo "  請在系統設定中允許「$TERMINAL_NAME」控制其他應用。"
    read -p "  已完成按 Enter 繼續 / 輸入 skip 跳過: " AUTO_CHOICE
    if [ "$AUTO_CHOICE" != "skip" ]; then
        if check_automation; then
            echo "  ✅ Automation — 已授權"
            AUTO_OK=true
        else
            echo "  ⚠️  尚未偵測到權限，安裝將繼續"
        fi
    fi
fi

echo ""
echo "  權限預檢完成"
echo ""

# ─── [0] 選擇安裝位置 ───
echo "  📁 選擇安裝位置"
echo ""

INSTALL_DIR=""

# 如果環境變數已指定，直接使用
if [ -n "${MUSEON_INSTALL_DIR:-}" ]; then
    INSTALL_DIR="$MUSEON_INSTALL_DIR"
    echo "  使用環境變數指定位置: $INSTALL_DIR"
else
    # 嘗試圖形化對話框（macOS Finder）
    if command -v osascript &>/dev/null; then
        echo "  （正在開啟資料夾選擇視窗...）"
        echo "  （如果沒看到視窗，請按 Enter 用文字輸入）"
        PARENT_DIR=$(osascript -e '
            tell application "Finder" to activate
            try
                POSIX path of (choose folder with prompt "選擇 MUSEON 安裝位置（會在此建立 MUSEON 資料夾）：")
            on error
                ""
            end try
        ' 2>/dev/null) || PARENT_DIR=""

        if [ -n "$PARENT_DIR" ]; then
            BASENAME=$(basename "$PARENT_DIR")
            if [ "$BASENAME" = "MUSEON" ] || [ "$BASENAME" = "museon" ]; then
                INSTALL_DIR="${PARENT_DIR%/}"
            else
                INSTALL_DIR="${PARENT_DIR%/}/MUSEON"
            fi
        fi
    fi

    # 文字回退
    if [ -z "$INSTALL_DIR" ]; then
        echo ""
        read -p "  安裝位置 [$DEFAULT_DIR]: " USER_INPUT
        INSTALL_DIR="${USER_INPUT:-$DEFAULT_DIR}"
    fi
fi

echo ""
echo "  → 將安裝到: $INSTALL_DIR"
echo ""

# ─── 定義路徑 ───
RUNTIME_DIR="$INSTALL_DIR/.runtime"

# ─── [1/5] 準備安裝目錄 ───
echo "  [1/5] 準備安裝目錄..."

# 如果已有安裝，備份使用者資料
BACKUP_DIR=""
if [ -d "$INSTALL_DIR" ]; then
    echo "        偵測到舊版安裝，備份使用者資料..."
    BACKUP_DIR=$(mktemp -d)
    [ -f "$INSTALL_DIR/.env" ] && cp "$INSTALL_DIR/.env" "$BACKUP_DIR/.env"
    [ -d "$INSTALL_DIR/data" ] && cp -R "$INSTALL_DIR/data" "$BACKUP_DIR/data"
    [ -d "$INSTALL_DIR/logs" ] && cp -R "$INSTALL_DIR/logs" "$BACKUP_DIR/logs"
fi

mkdir -p "$INSTALL_DIR" "$RUNTIME_DIR" "$INSTALL_DIR/data" "$INSTALL_DIR/logs"

# ─── [2/5] 解壓 MUSEON ───
echo "  [2/5] 解壓 MUSEON..."
tail -n +"${PAYLOAD_LINE}" "$0" | base64 -D | tar xz -C "$RUNTIME_DIR"

# 複製種子資料到使用者目錄（如果是新安裝且 .runtime/data 存在）
if [ -z "$BACKUP_DIR" ] && [ -d "$RUNTIME_DIR/data" ]; then
    cp -Rn "$RUNTIME_DIR/data/" "$INSTALL_DIR/data/" 2>/dev/null || true
fi

# 還原使用者資料
if [ -n "$BACKUP_DIR" ]; then
    [ -f "$BACKUP_DIR/.env" ] && cp "$BACKUP_DIR/.env" "$INSTALL_DIR/.env"
    [ -d "$BACKUP_DIR/data" ] && cp -R "$BACKUP_DIR/data/" "$INSTALL_DIR/data/"
    [ -d "$BACKUP_DIR/logs" ] && cp -R "$BACKUP_DIR/logs/" "$INSTALL_DIR/logs/"
    rm -rf "$BACKUP_DIR"
    echo "        使用者資料已還原 ✓"
fi

echo "        解壓完成 ✓"

# ─── [3/5] 搜尋 Python >= 3.11 ───
echo "  [3/5] 搜尋 Python >= 3.11..."

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
    echo ""
    echo "  ❌ 找不到 Python >= 3.11"
    echo "  請先安裝: brew install python@3.13"
    echo ""
    read -p "按 Enter 關閉..." -r
    exit 1
}

echo "        找到: $PYTHON_PATH ✓"

# ─── [4/5] 建立 Python 環境 ───
echo "  [4/5] 建立 Python 環境..."

VENV_DIR="$RUNTIME_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

if [ ! -f "$VENV_PYTHON" ]; then
    "$PYTHON_PATH" -m venv "$VENV_DIR"
    echo "        虛擬環境已建立 ✓"
else
    echo "        虛擬環境已存在 ✓"
fi

cd "$RUNTIME_DIR"
if ! "$VENV_PYTHON" -c "import museon.installer" 2>/dev/null; then
    echo "        安裝依賴中（可能需要幾分鐘）..."
    "$VENV_PYTHON" -m pip install -e ".[dev]" --quiet 2>&1 | tail -3
    echo "        依賴安裝完成 ✓"
fi

# ─── [5/5] 啟動 BDD 安裝流程 ───
echo "  [5/5] 啟動 MUSEON 安裝流程..."
echo ""

export MUSEON_HOME="$INSTALL_DIR"
"$VENV_PYTHON" -m museon.installer "$@"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "  🎉 MUSEON 安裝完成！"
    echo ""
    echo "  📂 安裝位置: $INSTALL_DIR"
    echo "     .env      → API 設定"
    echo "     data/     → 使用者資料"
    echo "     logs/     → 系統日誌"
    echo ""
    # 用 Finder 打開安裝目錄讓使用者看到
    open "$INSTALL_DIR" 2>/dev/null || true
else
    echo "  ⚠️  安裝過程中有問題，請查看上方日誌"
fi

echo ""
read -p "按 Enter 關閉..." -r
exit $EXIT_CODE
__PAYLOAD_BELOW__""".lstrip()
