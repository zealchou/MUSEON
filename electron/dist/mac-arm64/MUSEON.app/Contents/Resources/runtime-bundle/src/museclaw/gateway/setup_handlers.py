"""Dashboard 開機精靈 — 後端設定管理

對應 features/setup_wizard.feature
管理 API Key 的儲存、格式驗證、連線測試、首次啟動偵測
"""

import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Tuple

from museclaw.installer.api_keys import ApiKeyConfigurator
from museclaw.installer.models import StepResult, StepStatus


class SetupManager:
    """Dashboard 開機精靈的後端設定管理

    所有操作直接讀寫 .env 檔案，不依賴 Gateway 運行。
    這確保首次安裝時（Gateway 尚未啟動）精靈仍可運作。
    """

    # 必要的 API Key 清單
    REQUIRED_KEYS = ["ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN"]

    # 設定完成標記
    SETUP_DONE_KEY = "MUSECLAW_SETUP_DONE"

    def __init__(self):
        self._api_key_config = ApiKeyConfigurator()

    # ─── Section 1：首次啟動偵測 ───

    def is_first_run(self, env_file: Path) -> bool:
        """檢查是否為首次啟動（需要設定精靈）

        條件：.env 不存在 OR 缺少必要 key OR 沒有完成標記

        Args:
            env_file: .env 檔案路徑

        Returns:
            True = 需要顯示精靈
        """
        if not env_file.exists():
            return True

        # 檢查完成標記
        if not self._api_key_config.has_key(env_file, self.SETUP_DONE_KEY):
            return True

        return False

    # ─── Section 2：API Key 儲存 ───

    def save_api_key(self, env_file: Path, key_name: str, key_value: str) -> StepResult:
        """儲存 API Key 到 .env 檔案

        委託 ApiKeyConfigurator 處理，確保更新而非重複。

        Args:
            env_file: .env 檔案路徑
            key_name: key 名稱 (e.g. "ANTHROPIC_API_KEY")
            key_value: key 值

        Returns:
            StepResult
        """
        # 確保 .env 存在
        if not env_file.exists():
            self._api_key_config.create_env_file(env_file)

        return self._api_key_config.write_key(env_file, key_name, key_value)

    # ─── Section 3：API Key 格式驗證 ───

    def validate_anthropic_key(self, key: str) -> Tuple[bool, str]:
        """驗證 Anthropic API Key 格式

        合法格式：sk-ant-... 開頭

        Args:
            key: API Key 字串

        Returns:
            (valid, message)
        """
        if not key or not key.strip():
            return False, "API Key 不得為空"

        key = key.strip()

        # Anthropic key 格式：sk-ant-api03-... 或 sk-ant-...
        if not key.startswith("sk-ant-"):
            return False, "格式錯誤：Anthropic API Key 應以 sk-ant- 開頭"

        if len(key) < 20:
            return False, "格式錯誤：API Key 太短"

        return True, "格式正確"

    def validate_telegram_token(self, token: str) -> Tuple[bool, str]:
        """驗證 Telegram Bot Token 格式

        合法格式：數字:英數混合（例如 123456789:ABCdefGHI...）

        Args:
            token: Bot Token 字串

        Returns:
            (valid, message)
        """
        if not token or not token.strip():
            return False, "Bot Token 不得為空"

        token = token.strip()

        # Telegram Bot Token 格式：{bot_id}:{auth_token}
        pattern = r"^\d+:[A-Za-z0-9_-]+$"
        if not re.match(pattern, token):
            return False, "格式錯誤：Telegram Bot Token 應為「數字:英數」格式"

        if ":" not in token:
            return False, "格式錯誤：Token 應包含 ':' 分隔符"

        return True, "格式正確"

    # ─── Section 4：連線測試 ───

    def test_anthropic_connection(self, key: str) -> Tuple[bool, str]:
        """測試 Anthropic API 連線

        使用 GET /v1/models 驗證 key 是否有效。

        Args:
            key: Anthropic API Key

        Returns:
            (success, message)
        """
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return True, "Anthropic API 連線成功"
                return False, f"Anthropic API 回應異常: HTTP {response.status}"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "API Key 無效（驗證失敗）"
            return False, f"Anthropic API 錯誤: HTTP {e.code}"
        except urllib.error.URLError as e:
            return False, f"連線失敗: {e.reason}"
        except Exception as e:
            return False, f"連線失敗: {e}"

    def test_telegram_connection(self, token: str) -> Tuple[bool, str]:
        """測試 Telegram Bot 連線

        使用 getMe API 驗證 token 是否有效。

        Args:
            token: Telegram Bot Token

        Returns:
            (success, message) — 成功時包含 Bot 名稱
        """
        try:
            url = f"https://api.telegram.org/bot{token}/getMe"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                if data.get("ok"):
                    bot_info = data.get("result", {})
                    bot_name = bot_info.get("first_name", "Unknown")
                    bot_username = bot_info.get("username", "")
                    display = f"@{bot_username}" if bot_username else bot_name
                    return True, f"Telegram Bot 連線成功 ({display})"
                return False, "Telegram API 回應異常"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Bot Token 無效（驗證失敗）"
            return False, f"Telegram API 錯誤: HTTP {e.code}"
        except urllib.error.URLError as e:
            return False, f"連線失敗: {e.reason}"
        except Exception as e:
            return False, f"連線失敗: {e}"

    # ─── Section 5：設定狀態管理 ───

    def get_setup_status(self, env_file: Path) -> Dict[str, dict]:
        """取得所有 API Key 的設定狀態

        Args:
            env_file: .env 檔案路徑

        Returns:
            dict: {
                "ANTHROPIC_API_KEY": {"configured": True, "masked_value": "sk-ant-...***"},
                "TELEGRAM_BOT_TOKEN": {"configured": False, "masked_value": ""},
            }
        """
        status = {}

        for key_name in self.REQUIRED_KEYS:
            configured = self._api_key_config.has_key(env_file, key_name)
            masked_value = ""

            if configured:
                raw_value = self._read_key_value(env_file, key_name)
                masked_value = self._mask_value(raw_value)

            status[key_name] = {
                "configured": configured,
                "masked_value": masked_value,
            }

        return status

    def mark_setup_complete(self, env_file: Path) -> None:
        """標記設定完成

        寫入 MUSECLAW_SETUP_DONE=1 到 .env

        Args:
            env_file: .env 檔案路徑
        """
        self._api_key_config.write_key(env_file, self.SETUP_DONE_KEY, "1")

    # ─── 內部輔助 ───

    def _read_key_value(self, env_file: Path, key_name: str) -> str:
        """從 .env 讀取指定 key 的值"""
        if not env_file.exists():
            return ""

        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith(f"{key_name}="):
                return stripped[len(f"{key_name}="):]

        return ""

    def _mask_value(self, value: str) -> str:
        """遮罩敏感值

        保留前 8 字元，其餘用 *** 取代
        """
        if not value:
            return ""
        if len(value) <= 8:
            return value[:3] + "***"
        return value[:8] + "***"
