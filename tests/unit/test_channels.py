"""Unit tests for Channel Adapters."""

import asyncio
import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from museclaw.channels.base import ChannelAdapter, TrustLevel
from museclaw.channels.electron import ElectronAdapter
from museclaw.channels.telegram import TelegramAdapter
from museclaw.channels.webhook import WebhookAdapter
from museclaw.gateway.message import InternalMessage


class TestChannelAdapter:
    """Test the base ChannelAdapter ABC."""

    def test_cannot_instantiate_abstract_class(self):
        """ChannelAdapter is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            ChannelAdapter()


class TestTelegramAdapter:
    """Test TelegramAdapter."""

    @pytest.fixture
    def telegram_config(self):
        return {
            "bot_token": "test_token_123",
            "trusted_user_ids": ["12345", "67890"],
        }

    @pytest.fixture
    def telegram_adapter(self, telegram_config):
        return TelegramAdapter(telegram_config)

    def test_initialization(self, telegram_adapter):
        """Test adapter initializes correctly."""
        assert telegram_adapter.bot_token == "test_token_123"
        assert telegram_adapter.trusted_user_ids == ["12345", "67890"]

    @pytest.mark.asyncio
    async def test_receive_message_from_trusted_user(self, telegram_adapter):
        """Test receiving message from trusted user."""
        mock_update = MagicMock()
        mock_update.message.from_user.id = 12345
        mock_update.message.text = "Hello MuseClaw"
        mock_update.message.date = datetime(2026, 2, 25, 10, 0, 0)
        mock_update.message.chat.id = 12345

        # Set mock method directly on instance
        telegram_adapter._get_update = lambda: mock_update
        message = await telegram_adapter.receive()

        assert message.source == "telegram"
        assert message.user_id == "12345"
        assert message.content == "Hello MuseClaw"
        assert message.trust_level == "core"
        assert message.session_id.startswith("telegram_")

    @pytest.mark.asyncio
    async def test_receive_message_from_untrusted_user(self, telegram_adapter):
        """Test receiving message from untrusted user."""
        mock_update = MagicMock()
        mock_update.message.from_user.id = 99999
        mock_update.message.text = "Spam message"
        mock_update.message.date = datetime(2026, 2, 25, 10, 0, 0)
        mock_update.message.chat.id = 99999

        telegram_adapter._get_update = lambda: mock_update
        message = await telegram_adapter.receive()

        assert message.trust_level == "external"

    @pytest.mark.asyncio
    async def test_send_message(self, telegram_adapter):
        """Test sending message."""
        message = InternalMessage(
            source="telegram",
            session_id="telegram_12345",
            user_id="12345",
            content="Response from MuseClaw",
            timestamp=datetime.now(),
            trust_level="core",
            metadata={"chat_id": 12345},
        )

        telegram_adapter._send_telegram_message = lambda msg: True
        result = await telegram_adapter.send(message)

        assert result is True

    def test_get_trust_level_trusted(self, telegram_adapter):
        """Test trust level for trusted user."""
        trust_level = telegram_adapter.get_trust_level("12345")
        assert trust_level == TrustLevel.CORE

    def test_get_trust_level_untrusted(self, telegram_adapter):
        """Test trust level for untrusted user."""
        trust_level = telegram_adapter.get_trust_level("99999")
        assert trust_level == TrustLevel.EXTERNAL


class TestWebhookAdapter:
    """Test WebhookAdapter."""

    @pytest.fixture
    def webhook_config(self):
        return {
            "hmac_secret": "test_secret_key_123",
            "timestamp_window": 300,  # 5 minutes
        }

    @pytest.fixture
    def webhook_adapter(self, webhook_config):
        return WebhookAdapter(webhook_config)

    def test_initialization(self, webhook_adapter):
        """Test adapter initializes correctly."""
        assert webhook_adapter.hmac_secret == "test_secret_key_123"
        assert webhook_adapter.timestamp_window == 300

    def test_verify_hmac_valid(self, webhook_adapter):
        """Test HMAC verification with valid signature."""
        payload = {"user_id": "user123", "content": "Test message"}
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        signature = hmac.new(
            "test_secret_key_123".encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        assert webhook_adapter.verify_hmac(payload, signature) is True

    def test_verify_hmac_invalid(self, webhook_adapter):
        """Test HMAC verification with invalid signature."""
        payload = {"user_id": "user123", "content": "Test message"}
        invalid_signature = "invalid_signature_123"

        assert webhook_adapter.verify_hmac(payload, invalid_signature) is False

    def test_verify_timestamp_valid(self, webhook_adapter):
        """Test timestamp verification within window."""
        current_timestamp = int(datetime.now().timestamp())
        assert webhook_adapter.verify_timestamp(current_timestamp) is True

    def test_verify_timestamp_expired(self, webhook_adapter):
        """Test timestamp verification outside window."""
        old_timestamp = int(datetime.now().timestamp()) - 400  # 6+ minutes ago
        assert webhook_adapter.verify_timestamp(old_timestamp) is False

    @pytest.mark.asyncio
    async def test_receive_message_valid(self, webhook_adapter):
        """Test receiving webhook message with valid signature."""
        payload = {
            "user_id": "user123",
            "content": "Webhook test message",
            "timestamp": int(datetime.now().timestamp()),
        }
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            "test_secret_key_123".encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        webhook_adapter._get_webhook_request = lambda: (payload, signature)
        message = await webhook_adapter.receive()

        assert message.source == "webhook"
        assert message.user_id == "user123"
        assert message.content == "Webhook test message"
        assert message.trust_level == "verified"

    @pytest.mark.asyncio
    async def test_receive_message_invalid_hmac(self, webhook_adapter):
        """Test receiving webhook message with invalid signature."""
        payload = {
            "user_id": "user123",
            "content": "Malicious message",
            "timestamp": int(datetime.now().timestamp()),
        }
        invalid_signature = "invalid_signature"

        webhook_adapter._get_webhook_request = lambda: (payload, invalid_signature)
        with pytest.raises(ValueError, match="Invalid HMAC signature"):
            await webhook_adapter.receive()

    @pytest.mark.asyncio
    async def test_receive_message_expired_timestamp(self, webhook_adapter):
        """Test receiving webhook message with expired timestamp."""
        old_timestamp = int(datetime.now().timestamp()) - 400
        payload = {
            "user_id": "user123",
            "content": "Old message",
            "timestamp": old_timestamp,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            "test_secret_key_123".encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

        webhook_adapter._get_webhook_request = lambda: (payload, signature)
        with pytest.raises(ValueError, match="Timestamp outside valid window"):
            await webhook_adapter.receive()

    @pytest.mark.asyncio
    async def test_send_not_implemented(self, webhook_adapter):
        """Test that webhook send is not implemented."""
        message = InternalMessage(
            source="webhook",
            session_id="webhook_123",
            user_id="user123",
            content="Test",
            timestamp=datetime.now(),
            trust_level="verified",
            metadata={},
        )

        result = await webhook_adapter.send(message)
        assert result is False


class TestElectronAdapter:
    """Test ElectronAdapter."""

    @pytest.fixture
    def electron_config(self):
        return {
            "ipc_socket_path": "/tmp/museclaw.sock",
            "owner_user_id": "owner123",
        }

    @pytest.fixture
    def electron_adapter(self, electron_config):
        return ElectronAdapter(electron_config)

    def test_initialization(self, electron_adapter):
        """Test adapter initializes correctly."""
        assert electron_adapter.ipc_socket_path == "/tmp/museclaw.sock"
        assert electron_adapter.owner_user_id == "owner123"

    @pytest.mark.asyncio
    async def test_receive_message(self, electron_adapter):
        """Test receiving message via IPC."""
        ipc_data = {
            "user_id": "owner123",
            "content": "Show me today's token usage",
            "timestamp": datetime.now().isoformat(),
        }

        electron_adapter._read_from_ipc = lambda: ipc_data
        message = await electron_adapter.receive()

        assert message.source == "electron"
        assert message.user_id == "owner123"
        assert message.content == "Show me today's token usage"
        assert message.trust_level == "core"
        assert message.session_id == "electron_main"

    @pytest.mark.asyncio
    async def test_send_message(self, electron_adapter):
        """Test sending message via IPC."""
        message = InternalMessage(
            source="electron",
            session_id="electron_main",
            user_id="owner123",
            content="Today's usage: 150K tokens",
            timestamp=datetime.now(),
            trust_level="core",
            metadata={},
        )

        electron_adapter._write_to_ipc = lambda msg: True
        result = await electron_adapter.send(message)

        assert result is True

    def test_get_trust_level(self, electron_adapter):
        """Test trust level is always CORE for Electron."""
        trust_level = electron_adapter.get_trust_level("owner123")
        assert trust_level == TrustLevel.CORE
