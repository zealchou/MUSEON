"""macOS 權限檢查與請求模組

檢查 Terminal 環境下可偵測的 macOS TCC 權限。
Electron app 的權限（麥克風、相機等）在 Dashboard 中處理。
"""

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List

from .models import StepResult, StepStatus


class PermissionType(Enum):
    """macOS 權限類型"""
    FULL_DISK_ACCESS = "full_disk_access"
    AUTOMATION = "automation"


@dataclass
class PermissionStatus:
    """單一權限的檢查結果"""
    permission: PermissionType
    granted: bool
    message: str
    system_prefs_url: str


class PermissionChecker:
    """macOS 權限檢查器

    在 shell/Python 環境中檢查可偵測的權限。
    """

    SYSTEM_PREFS_URLS = {
        PermissionType.FULL_DISK_ACCESS: (
            "x-apple.systempreferences:"
            "com.apple.preference.security?Privacy_AllFiles"
        ),
        PermissionType.AUTOMATION: (
            "x-apple.systempreferences:"
            "com.apple.preference.security?Privacy_Automation"
        ),
    }

    LABELS = {
        PermissionType.FULL_DISK_ACCESS: "Full Disk Access",
        PermissionType.AUTOMATION: "Automation",
    }

    def check_full_disk_access(self) -> PermissionStatus:
        """檢查 Full Disk Access

        原理：TCC.db 受 FDA 保護，若能讀取代表已授權。
        """
        tcc_path = Path.home() / "Library/Application Support/com.apple.TCC/TCC.db"
        try:
            result = subprocess.run(
                ["ls", str(tcc_path)],
                capture_output=True,
                timeout=5,
            )
            granted = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            granted = False

        return PermissionStatus(
            permission=PermissionType.FULL_DISK_ACCESS,
            granted=granted,
            message="已授權" if granted else "未授權 — 部分檔案存取可能受限",
            system_prefs_url=self.SYSTEM_PREFS_URLS[PermissionType.FULL_DISK_ACCESS],
        )

    def check_automation(self) -> PermissionStatus:
        """檢查 Automation (AppleScript) 權限

        原理：執行 osascript 操控 System Events，
        若回傳 error -1743 代表未授權。
        """
        try:
            result = subprocess.run(
                [
                    "osascript", "-e",
                    'tell application "System Events" to return name of current user',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # error -1743 = errAEEventWouldRequireUserConsent
            if result.returncode != 0 and "1743" in result.stderr:
                granted = False
            else:
                granted = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            granted = False

        return PermissionStatus(
            permission=PermissionType.AUTOMATION,
            granted=granted,
            message="已授權" if granted else "未授權 — AppleScript 操作可能受限",
            system_prefs_url=self.SYSTEM_PREFS_URLS[PermissionType.AUTOMATION],
        )

    def check_all(self) -> List[PermissionStatus]:
        """檢查所有權限"""
        return [
            self.check_full_disk_access(),
            self.check_automation(),
        ]

    def open_system_preferences(self, permission: PermissionType) -> bool:
        """開啟對應的系統設定頁面"""
        url = self.SYSTEM_PREFS_URLS.get(permission)
        if not url:
            return False
        try:
            subprocess.run(["open", url], capture_output=True, timeout=5)
            return True
        except (subprocess.TimeoutExpired, OSError):
            return False
