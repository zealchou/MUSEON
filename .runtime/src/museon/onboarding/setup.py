"""Setup wizard for MUSEON - Platform API and Bot configuration.

Based on plan-v7.md Chapter 3 and Chapter 9:
- Telegram Bot setup (required for v1)
- Instagram API setup (optional)
- LINE Bot setup (v2, optional)
- Google Drive API setup (optional)
- Validates API credentials and connection
"""

from typing import Dict, Any, Optional, List, Tuple
import os
import json
from pathlib import Path
from enum import Enum


class PlatformStatus(Enum):
    """Platform configuration status."""
    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    VERIFIED = "verified"
    ERROR = "error"


class Platform:
    """Represents a platform integration."""

    def __init__(
        self,
        name: str,
        required: bool,
        description: str,
        setup_steps: List[str],
    ):
        self.name = name
        self.required = required
        self.description = description
        self.setup_steps = setup_steps
        self.status = PlatformStatus.NOT_CONFIGURED

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "required": self.required,
            "description": self.description,
            "status": self.status.value,
        }


class SetupWizard:
    """Guides user through MUSEON platform setup.

    Handles:
    - Environment variable validation
    - API credential setup
    - Connection testing
    - Multi-platform configuration
    """

    def __init__(self, config_dir: str = "data"):
        """Initialize setup wizard.

        Args:
            config_dir: Directory for storing configuration
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.config_path = self.config_dir / "platform_config.json"

        self.platforms = {
            "telegram": Platform(
                name="Telegram",
                required=True,
                description="老闆與 MUSEON 的主要對話管道",
                setup_steps=[
                    "前往 https://t.me/BotFather",
                    "發送 /newbot 創建新機器人",
                    "設定機器人名稱和用戶名",
                    "複製 Bot Token",
                    "將 Token 設定到環境變數 TELEGRAM_BOT_TOKEN",
                ],
            ),
            "instagram": Platform(
                name="Instagram",
                required=False,
                description="社群貼文與留言管理",
                setup_steps=[
                    "前往 Meta Developer Console: https://developers.facebook.com/",
                    "建立新應用程式",
                    "啟用 Instagram Graph API",
                    "取得 Access Token",
                    "將 Token 設定到環境變數 INSTAGRAM_ACCESS_TOKEN",
                ],
            ),
            "line": Platform(
                name="LINE",
                required=False,
                description="客戶對接管道 (v2)",
                setup_steps=[
                    "前往 LINE Developers Console: https://developers.line.biz/",
                    "建立新 Provider 和 Channel",
                    "啟用 Messaging API",
                    "取得 Channel Access Token",
                    "將 Token 設定到環境變數 LINE_CHANNEL_ACCESS_TOKEN",
                    "將 Channel Secret 設定到環境變數 LINE_CHANNEL_SECRET",
                ],
            ),
            "google_drive": Platform(
                name="Google Drive",
                required=False,
                description="檔案管理與備份",
                setup_steps=[
                    "前往 Google Cloud Console: https://console.cloud.google.com/",
                    "建立新專案",
                    "啟用 Google Drive API",
                    "建立服務帳號",
                    "下載 JSON 金鑰檔案",
                    "將金鑰檔案路徑設定到環境變數 GOOGLE_DRIVE_CREDENTIALS",
                ],
            ),
        }

        self._load_config()

    def _load_config(self):
        """Load platform configuration from disk."""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                for platform_name, platform_data in config.items():
                    if platform_name in self.platforms:
                        self.platforms[platform_name].status = PlatformStatus(
                            platform_data.get("status", "not_configured")
                        )

    def _save_config(self):
        """Save platform configuration to disk."""
        config = {
            name: platform.to_dict()
            for name, platform in self.platforms.items()
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def check_required_platforms(self) -> Tuple[bool, List[str]]:
        """Check if all required platforms are configured.

        Returns:
            Tuple of (all_required_configured: bool, missing_platforms: list)
        """
        missing = []
        for name, platform in self.platforms.items():
            if platform.required and platform.status == PlatformStatus.NOT_CONFIGURED:
                missing.append(name)

        return len(missing) == 0, missing

    def get_platform_status(self, platform_name: str) -> Optional[PlatformStatus]:
        """Get status of a specific platform.

        Args:
            platform_name: Name of platform (telegram, instagram, etc.)

        Returns:
            Platform status or None if platform not found
        """
        platform = self.platforms.get(platform_name)
        return platform.status if platform else None

    def get_setup_steps(self, platform_name: str) -> List[str]:
        """Get setup steps for a platform.

        Args:
            platform_name: Name of platform

        Returns:
            List of setup steps
        """
        platform = self.platforms.get(platform_name)
        return platform.setup_steps if platform else []

    def verify_telegram_bot(self) -> Tuple[bool, str]:
        """Verify Telegram bot token.

        Returns:
            Tuple of (success: bool, message: str)
        """
        token = os.getenv("TELEGRAM_BOT_TOKEN")

        if not token:
            self.platforms["telegram"].status = PlatformStatus.NOT_CONFIGURED
            self._save_config()
            return False, "TELEGRAM_BOT_TOKEN 環境變數未設定"

        # In production, would test connection to Telegram API
        # For now, just check token format
        if not token.strip():
            self.platforms["telegram"].status = PlatformStatus.ERROR
            self._save_config()
            return False, "TELEGRAM_BOT_TOKEN 不得為空"

        # Simple format check: should be like "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
        if ":" not in token:
            self.platforms["telegram"].status = PlatformStatus.ERROR
            self._save_config()
            return False, "TELEGRAM_BOT_TOKEN 格式錯誤 (應包含 ':' )"

        # Mark as configured (in production, would verify with API)
        self.platforms["telegram"].status = PlatformStatus.CONFIGURED
        self._save_config()

        return True, "Telegram Bot 設定成功"

    def verify_instagram_api(self) -> Tuple[bool, str]:
        """Verify Instagram API credentials.

        Returns:
            Tuple of (success: bool, message: str)
        """
        token = os.getenv("INSTAGRAM_ACCESS_TOKEN")

        if not token:
            self.platforms["instagram"].status = PlatformStatus.NOT_CONFIGURED
            self._save_config()
            return False, "INSTAGRAM_ACCESS_TOKEN 未設定 (選用)"

        # In production, would test connection to Instagram Graph API
        if not token.strip():
            self.platforms["instagram"].status = PlatformStatus.ERROR
            self._save_config()
            return False, "INSTAGRAM_ACCESS_TOKEN 不得為空"

        self.platforms["instagram"].status = PlatformStatus.CONFIGURED
        self._save_config()

        return True, "Instagram API 設定成功"

    def verify_line_bot(self) -> Tuple[bool, str]:
        """Verify LINE bot credentials.

        Returns:
            Tuple of (success: bool, message: str)
        """
        access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        channel_secret = os.getenv("LINE_CHANNEL_SECRET")

        if not access_token or not channel_secret:
            self.platforms["line"].status = PlatformStatus.NOT_CONFIGURED
            self._save_config()
            return False, "LINE credentials 未設定 (v2 功能,選用)"

        # In production, would test connection to LINE API
        if not access_token.strip() or not channel_secret.strip():
            self.platforms["line"].status = PlatformStatus.ERROR
            self._save_config()
            return False, "LINE credentials 不得為空"

        self.platforms["line"].status = PlatformStatus.CONFIGURED
        self._save_config()

        return True, "LINE Bot 設定成功"

    def verify_google_drive(self) -> Tuple[bool, str]:
        """Verify Google Drive API credentials.

        Returns:
            Tuple of (success: bool, message: str)
        """
        credentials_path = os.getenv("GOOGLE_DRIVE_CREDENTIALS")

        if not credentials_path:
            self.platforms["google_drive"].status = PlatformStatus.NOT_CONFIGURED
            self._save_config()
            return False, "GOOGLE_DRIVE_CREDENTIALS 未設定 (選用)"

        # Check if file exists
        if not Path(credentials_path).exists():
            self.platforms["google_drive"].status = PlatformStatus.ERROR
            self._save_config()
            return False, f"憑證檔案不存在: {credentials_path}"

        # In production, would validate JSON and test API connection
        self.platforms["google_drive"].status = PlatformStatus.CONFIGURED
        self._save_config()

        return True, "Google Drive API 設定成功"

    def run_full_check(self) -> Dict[str, Any]:
        """Run complete platform check.

        Returns:
            Dictionary with check results for all platforms
        """
        results = {
            "telegram": self.verify_telegram_bot(),
            "instagram": self.verify_instagram_api(),
            "line": self.verify_line_bot(),
            "google_drive": self.verify_google_drive(),
        }

        all_required_ok, missing = self.check_required_platforms()

        summary = {
            "all_required_ok": all_required_ok,
            "missing_required": missing,
            "results": {
                name: {
                    "success": success,
                    "message": message,
                    "required": self.platforms[name].required,
                }
                for name, (success, message) in results.items()
            },
        }

        return summary

    def generate_setup_guide(self) -> str:
        """Generate complete setup guide for user.

        Returns:
            Formatted setup guide text
        """
        all_ok, missing = self.check_required_platforms()

        if all_ok and all(
            p.status != PlatformStatus.NOT_CONFIGURED
            for p in self.platforms.values()
        ):
            return "所有平台設定完成！"

        guide = "MUSEON 平台設定指南\n\n"

        # Required platforms
        guide += "【必要設定】\n\n"
        for name, platform in self.platforms.items():
            if platform.required:
                status_emoji = self._get_status_emoji(platform.status)
                guide += f"{status_emoji} {platform.name}\n"
                guide += f"  用途: {platform.description}\n"

                if platform.status == PlatformStatus.NOT_CONFIGURED:
                    guide += "  設定步驟:\n"
                    for i, step in enumerate(platform.setup_steps, 1):
                        guide += f"    {i}. {step}\n"
                guide += "\n"

        # Optional platforms
        guide += "【選用功能】\n\n"
        for name, platform in self.platforms.items():
            if not platform.required:
                status_emoji = self._get_status_emoji(platform.status)
                guide += f"{status_emoji} {platform.name}\n"
                guide += f"  用途: {platform.description}\n"

                if platform.status == PlatformStatus.NOT_CONFIGURED:
                    guide += "  設定步驟:\n"
                    for i, step in enumerate(platform.setup_steps, 1):
                        guide += f"    {i}. {step}\n"
                guide += "\n"

        return guide

    def _get_status_emoji(self, status: PlatformStatus) -> str:
        """Get emoji for platform status."""
        emoji_map = {
            PlatformStatus.NOT_CONFIGURED: "⚪",
            PlatformStatus.CONFIGURED: "🟢",
            PlatformStatus.VERIFIED: "✅",
            PlatformStatus.ERROR: "🔴",
        }
        return emoji_map.get(status, "❓")

    def get_platform_summary(self) -> Dict[str, Any]:
        """Get summary of all platform statuses.

        Returns:
            Dictionary with platform statuses
        """
        return {
            name: {
                "required": platform.required,
                "status": platform.status.value,
                "description": platform.description,
            }
            for name, platform in self.platforms.items()
        }
