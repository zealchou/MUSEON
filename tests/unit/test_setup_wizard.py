"""Dashboard 開機精靈 — Setup Wizard 測試

對應 features/setup_wizard.feature
5 個 Section、17 個 Scenario → 17 個 test methods
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from museon.gateway.setup_handlers import SetupManager
from museon.installer.models import StepStatus


# ═══════════════════════════════════════
# Section 1：首次啟動偵測
# ═══════════════════════════════════════


class TestFirstRunDetection:
    """首次啟動偵測"""

    def test_no_env_file_is_first_run(self, tmp_path):
        """Scenario: .env 不存在 → 應顯示精靈"""
        env_file = tmp_path / ".env"
        manager = SetupManager()
        assert manager.is_first_run(env_file) is True

    def test_env_missing_required_key_is_first_run(self, tmp_path):
        """Scenario: .env 缺少必要 key → 應顯示精靈"""
        env_file = tmp_path / ".env"
        env_file.write_text("# empty template\n")
        manager = SetupManager()
        assert manager.is_first_run(env_file) is True

    def test_env_with_all_keys_and_marker_not_first_run(self, tmp_path):
        """Scenario: .env 已有所有必要 key + 標記 → 跳過精靈"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ANTHROPIC_API_KEY=sk-ant-api03-test\n"
            "TELEGRAM_BOT_TOKEN=123456:ABCdef\n"
            "MUSEON_SETUP_DONE=1\n"
        )
        manager = SetupManager()
        assert manager.is_first_run(env_file) is False

    def test_env_with_keys_but_no_marker_is_first_run(self, tmp_path):
        """有 key 但沒有 MUSEON_SETUP_DONE 標記 → 仍需設定"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "ANTHROPIC_API_KEY=sk-ant-api03-test\n"
            "TELEGRAM_BOT_TOKEN=123456:ABCdef\n"
        )
        manager = SetupManager()
        assert manager.is_first_run(env_file) is True


# ═══════════════════════════════════════
# Section 2：API Key 儲存
# ═══════════════════════════════════════


class TestApiKeySave:
    """API Key 儲存"""

    def test_save_anthropic_key(self, tmp_path):
        """Scenario: 儲存 Anthropic API Key"""
        env_file = tmp_path / ".env"
        env_file.write_text("# MUSEON\n")

        manager = SetupManager()
        result = manager.save_api_key(env_file, "ANTHROPIC_API_KEY", "sk-ant-api03-test123")

        assert result.status == StepStatus.SUCCESS
        content = env_file.read_text()
        assert "ANTHROPIC_API_KEY=sk-ant-api03-test123" in content

    def test_save_telegram_token(self, tmp_path):
        """Scenario: 儲存 Telegram Bot Token"""
        env_file = tmp_path / ".env"
        env_file.write_text("# MUSEON\n")

        manager = SetupManager()
        result = manager.save_api_key(env_file, "TELEGRAM_BOT_TOKEN", "123456:ABCdefGHIjklMNO")

        content = env_file.read_text()
        assert "TELEGRAM_BOT_TOKEN=123456:ABCdefGHIjklMNO" in content

    def test_update_existing_key_no_duplicate(self, tmp_path):
        """Scenario: 更新已存在的 key — 覆蓋而非重複"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=old_value\n")

        manager = SetupManager()
        manager.save_api_key(env_file, "ANTHROPIC_API_KEY", "new_value")

        content = env_file.read_text()
        assert content.count("ANTHROPIC_API_KEY") == 1
        assert "ANTHROPIC_API_KEY=new_value" in content
        assert "old_value" not in content


# ═══════════════════════════════════════
# Section 3：API Key 格式驗證
# ═══════════════════════════════════════


class TestApiKeyValidation:
    """API Key 格式驗證"""

    def test_valid_anthropic_key(self):
        """Scenario: Anthropic key 格式正確"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("sk-ant-api03-validkey123")
        assert valid is True

    def test_invalid_anthropic_key(self):
        """Scenario: Anthropic key 格式錯誤"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("invalid-key")
        assert valid is False
        assert "格式" in msg or "sk-ant" in msg

    def test_valid_telegram_token(self):
        """Scenario: Telegram token 格式正確"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
        assert valid is True

    def test_invalid_telegram_token(self):
        """Scenario: Telegram token 格式錯誤"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("not-a-valid-token")
        assert valid is False

    def test_empty_anthropic_key_rejected(self):
        """Scenario: 空值拒絕"""
        manager = SetupManager()
        valid, msg = manager.validate_anthropic_key("")
        assert valid is False
        assert "空" in msg or "empty" in msg.lower() or "不得" in msg

    def test_empty_telegram_token_rejected(self):
        """Scenario: Telegram 空值拒絕"""
        manager = SetupManager()
        valid, msg = manager.validate_telegram_token("")
        assert valid is False


# ═══════════════════════════════════════
# Section 4：連線測試
# ═══════════════════════════════════════


class TestConnectionTest:
    """連線測試"""

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_anthropic_connection_success(self, mock_urlopen):
        """Scenario: Anthropic API 連線成功"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"data": [{"id": "claude-3"}]}).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        manager = SetupManager()
        success, msg = manager.test_anthropic_connection("sk-ant-api03-valid")
        assert success is True

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_telegram_connection_success(self, mock_urlopen):
        """Scenario: Telegram Bot 連線成功"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "ok": True,
            "result": {"username": "test_bot", "first_name": "Test Bot"}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        manager = SetupManager()
        success, msg = manager.test_telegram_connection("123456:ABCdef")
        assert success is True
        assert "test_bot" in msg or "Test Bot" in msg

    @patch("museon.gateway.setup_handlers.urllib.request.urlopen")
    def test_connection_timeout_handled(self, mock_urlopen):
        """Scenario: 連線超時處理"""
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("timeout")

        manager = SetupManager()
        success, msg = manager.test_anthropic_connection("sk-ant-api03-valid")
        assert success is False
        assert "超時" in msg or "timeout" in msg.lower() or "失敗" in msg


# ═══════════════════════════════════════
# Section 5：設定狀態管理
# ═══════════════════════════════════════


class TestSetupStatusManagement:
    """設定狀態管理"""

    def test_get_status_partial(self, tmp_path):
        """Scenario: 取得設定狀態 — 部分完成"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-api03-test\n")

        manager = SetupManager()
        status = manager.get_setup_status(env_file)

        assert status["ANTHROPIC_API_KEY"]["configured"] is True
        assert status["TELEGRAM_BOT_TOKEN"]["configured"] is False

    def test_mark_setup_complete(self, tmp_path):
        """Scenario: 標記設定完成"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=test\n")

        manager = SetupManager()
        manager.mark_setup_complete(env_file)

        content = env_file.read_text()
        assert "MUSEON_SETUP_DONE=1" in content

    def test_get_status_masks_values(self, tmp_path):
        """設定狀態回傳時應遮罩敏感值"""
        env_file = tmp_path / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-api03-verylongsecretkey\n")

        manager = SetupManager()
        status = manager.get_setup_status(env_file)

        # 應該有 masked_value 且不包含完整 key
        masked = status["ANTHROPIC_API_KEY"]["masked_value"]
        assert "verylongsecretkey" not in masked
        assert "sk-ant" in masked or "***" in masked
