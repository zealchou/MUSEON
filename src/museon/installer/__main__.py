"""MUSEON 安裝程式入口點

用法: python -m museon.installer [--non-interactive] [--verbose]
"""

import argparse
import sys
import time
from pathlib import Path

from .models import InstallConfig, StepStatus
from .orchestrator import InstallerOrchestrator
from .ui import InstallerUI


def find_install_dir() -> Path:
    """找到安裝根目錄（使用者看到的頂層目錄）

    優先用環境變數 MUSEON_HOME，否則用 __file__ 反推。
    在正式安裝中，pyproject.toml 位於 .runtime/ 目錄下，
    install_dir = .runtime 的上一層。
    在開發模式中，pyproject.toml 就在專案根目錄。
    """
    import os

    env_home = os.environ.get("MUSEON_HOME")
    if env_home:
        return Path(env_home)

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            # 如果 pyproject.toml 在 .runtime/ 裡，往上一層是 install_dir
            if parent.name == ".runtime":
                return parent.parent
            # 開發模式：pyproject.toml 在專案根目錄
            return parent

    return Path.cwd()


# 每個步驟的 spinner 訊息
STEP_SPINNER_MESSAGES = [
    "檢查系統環境",
    "檢查 macOS 權限",
    "建立 Python 虛擬環境 & 安裝依賴",
    "驗證核心模組",
    "打包 Electron Dashboard（npm install + build）",
    "設定 Gateway 24/7 daemon",
    "設定 API Keys",
    "驗證 Claude Code CLI（MAX 訂閱方案）",
    "安裝 AI 工具（SearXNG / Firecrawl / Whisper / OCR...）",
    "確認 Gateway 啟動狀態",
]


def main():
    parser = argparse.ArgumentParser(
        description="MUSEON 一鍵安裝程式",
    )
    parser.add_argument(
        "--non-interactive", "-n",
        action="store_true",
        help="非互動模式（跳過所有問答）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="顯示詳細資訊",
    )
    args = parser.parse_args()

    # 初始化 UI
    ui = InstallerUI(verbose=args.verbose)
    ui.show_banner()

    # 找到安裝根目錄
    install_dir = find_install_dir()
    ui.info(f"安裝目錄: {install_dir}")

    # 建立安裝設定
    config = InstallConfig(install_dir=install_dir)

    # 建立編排器
    orchestrator = InstallerOrchestrator(
        config=config,
        ui=ui,
        interactive=not args.non_interactive,
    )

    # ─── 執行安裝（每個步驟帶 spinner） ───
    step_names = InstallerUI.STEP_NAMES
    results = []

    for i, step_name_label in enumerate(step_names, 1):
        ui.step_start(i, step_name_label)

        step_method_name = InstallerOrchestrator.STEPS[i - 1]
        step_method = getattr(orchestrator, step_method_name)
        spinner_msg = STEP_SPINNER_MESSAGES[i - 1]

        with ui.spinner(spinner_msg):
            result = step_method()

        results.append(result)
        orchestrator.results = results
        ui.step_done(result)

        if result.is_fatal:
            ui.error("安裝中止 — 請修復上述問題後重試")
            sys.exit(1)

    # ─── 安裝完成後的引導 ───

    # 顯示摘要
    ui.show_summary(orchestrator.generate_summary())

    # Day 0 就緒 + 下一步指引
    readiness = orchestrator.check_day0_readiness()
    ui.show_next_steps(readiness)

    # 自動打開 Dashboard（如果有安裝）
    orchestrator.try_open_dashboard()

    # 告知使用者安裝位置
    has_failures = any(r.is_fatal for r in results)
    if not has_failures:
        print(f"  📂 安裝位置: {install_dir}")
        print(f"     .env      → API 設定")
        print(f"     data/     → 使用者資料")
        print(f"     logs/     → 系統日誌")
        print()

    sys.exit(1 if has_failures else 0)


if __name__ == "__main__":
    main()
