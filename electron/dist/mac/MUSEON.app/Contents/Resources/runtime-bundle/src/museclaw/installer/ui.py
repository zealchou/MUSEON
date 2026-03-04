"""安裝程式互動介面

提供彩色終端輸出、旋轉動畫、進度條、互動問答
與安裝邏輯分離，方便測試
"""

import sys
import threading
import time
from contextlib import contextmanager
from typing import Optional

from .models import StepResult, StepStatus


# ANSI 顏色碼
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    MAGENTA = "\033[0;35m"
    CYAN = "\033[0;36m"
    BOLD = "\033[1m"
    NC = "\033[0m"  # No Color
    DIM = "\033[2m"


class InstallerUI:
    """安裝程式的終端介面"""

    BANNER = f"""\
{Colors.CYAN}
  ╔═══════════════════════════════════════════════╗
  ║                                               ║
  ║   🐾  MuseClaw 一鍵安裝程式  🐾              ║
  ║                                               ║
  ║   BDD-Driven Installer v2.1                   ║
  ║   讓台灣中小企業擁有 24/7 AI 助手             ║
  ║                                               ║
  ╚═══════════════════════════════════════════════╝
{Colors.NC}"""

    STATUS_ICONS = {
        StepStatus.SUCCESS: f"{Colors.GREEN}✅{Colors.NC}",
        StepStatus.WARNING: f"{Colors.YELLOW}⚠️{Colors.NC}",
        StepStatus.SKIPPED: f"{Colors.BLUE}⏭️{Colors.NC}",
        StepStatus.FAILED: f"{Colors.RED}❌{Colors.NC}",
        StepStatus.PENDING: "⏳",
    }

    STEP_NAMES = [
        "環境檢查",
        "Python 環境建置",
        "核心模組驗證",
        "Electron Dashboard",
        "Gateway Daemon",
        "API Key 設定",
        "工具安裝",
        "啟動確認",
    ]

    # 每個步驟的預估時間（秒），用來給使用者心理預期
    STEP_ESTIMATES = {
        "環境檢查": "幾秒",
        "Python 環境建置": "1~3 分鐘",
        "核心模組驗證": "幾秒",
        "Electron Dashboard": "3~10 分鐘",
        "Gateway Daemon": "幾秒",
        "API Key 設定": "幾秒",
        "工具安裝": "3~10 分鐘",
        "啟動確認": "幾秒",
    }

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.current_step = 0
        self.total_steps = len(self.STEP_NAMES)
        self._spinner_stop = threading.Event()
        self._spinner_thread: Optional[threading.Thread] = None
        self._spinner_message = ""

    def show_banner(self):
        """顯示歡迎橫幅"""
        print(self.BANNER)

    def step_start(self, step_num: int, step_name: str):
        """顯示步驟開始"""
        self.current_step = step_num
        progress = f"[{step_num}/{self.total_steps}]"
        estimate = self.STEP_ESTIMATES.get(step_name, "")
        est_str = f" {Colors.DIM}(預計 {estimate}){Colors.NC}" if estimate else ""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{progress}{Colors.NC} {step_name}{est_str}", flush=True)

    def step_done(self, result: StepResult):
        """顯示步驟結果"""
        icon = self.STATUS_ICONS.get(result.status, "?")
        print(f"  {icon} {result.message}")

        if self.verbose and result.details:
            for key, value in result.details.items():
                print(f"     {Colors.CYAN}{key}{Colors.NC}: {value}")

    @contextmanager
    def spinner(self, message: str = "處理中"):
        """旋轉動畫 context manager

        用法:
            with ui.spinner("安裝依賴中"):
                do_long_task()
        """
        self._spinner_message = message
        self._spinner_stop.clear()
        self._spinner_thread = threading.Thread(
            target=self._spin, daemon=True
        )
        self._spinner_thread.start()
        try:
            yield
        finally:
            self._spinner_stop.set()
            self._spinner_thread.join(timeout=2)
            # 清除 spinner 行
            sys.stdout.write(f"\r  {'':40}\r")
            sys.stdout.flush()

    def _spin(self):
        """背景旋轉動畫"""
        idx = 0
        start = time.time()
        while not self._spinner_stop.is_set():
            elapsed = int(time.time() - start)
            mins, secs = divmod(elapsed, 60)
            time_str = f"{mins}:{secs:02d}" if mins else f"{secs}s"
            frame = self.SPINNER_FRAMES[idx % len(self.SPINNER_FRAMES)]
            msg = f"  {Colors.CYAN}{frame}{Colors.NC} {self._spinner_message}... {Colors.DIM}({time_str}){Colors.NC}"
            sys.stdout.write(f"\r{msg:60}")
            sys.stdout.flush()
            idx += 1
            self._spinner_stop.wait(0.1)

    def substep(self, message: str):
        """顯示子步驟（在 spinner 之間的靜態訊息）"""
        print(f"  {Colors.DIM}→{Colors.NC} {message}", flush=True)

    def info(self, message: str):
        """資訊訊息"""
        print(f"  {Colors.BLUE}ℹ{Colors.NC}  {message}")

    def warn(self, message: str):
        """警告訊息"""
        print(f"  {Colors.YELLOW}⚠{Colors.NC}  {message}")

    def error(self, message: str):
        """錯誤訊息"""
        print(f"  {Colors.RED}✗{Colors.NC}  {message}")

    def success(self, message: str):
        """成功訊息"""
        print(f"  {Colors.GREEN}✓{Colors.NC}  {message}")

    def ask_yes_no(self, question: str, default: bool = True) -> bool:
        """互動問答 — 是/否"""
        hint = "[Y/n]" if default else "[y/N]"
        try:
            answer = input(f"  {Colors.MAGENTA}?{Colors.NC}  {question} {hint} ").strip().lower()
            if not answer:
                return default
            return answer in ("y", "yes", "是")
        except (EOFError, KeyboardInterrupt):
            print()
            return default

    def ask_input(self, prompt: str, required: bool = False) -> Optional[str]:
        """互動問答 — 自由輸入"""
        try:
            while True:
                value = input(f"  {Colors.MAGENTA}>{Colors.NC}  {prompt}: ").strip()
                if value or not required:
                    return value if value else None
                print(f"  {Colors.YELLOW}  此欄位為必填{Colors.NC}")
        except (EOFError, KeyboardInterrupt):
            print()
            return None

    def show_summary(self, summary: str):
        """顯示安裝結果摘要"""
        print(f"\n{Colors.BOLD}{summary}{Colors.NC}")

    def show_next_steps(self, message: str):
        """顯示下一步指引"""
        print(f"\n{Colors.CYAN}{'─' * 50}{Colors.NC}")
        print(message)
        print(f"{Colors.CYAN}{'─' * 50}{Colors.NC}\n")
