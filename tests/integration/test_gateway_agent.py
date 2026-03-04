"""Integration tests for Gateway → Adapter → Agent flow."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from museon.agent.loop import AgentLoop
from museon.channels.electron import ElectronAdapter
from museon.channels.telegram import TelegramAdapter
from museon.channels.webhook import WebhookAdapter
from museon.gateway.message import InternalMessage
from museon.gateway.session import SessionManager


class TestGatewayToAgentFlow:
    """Test the full flow: Channel Adapter → Gateway → Agent."""

    @pytest.fixture
    def session_manager(self):
        return SessionManager()

    @pytest.fixture
    def mock_agent_loop(self):
        """Create a mock agent loop for testing."""
        agent = MagicMock(spec=AgentLoop)
        agent.process = AsyncMock(return_value="Agent response")
        return agent

    @pytest.mark.asyncio
    async def test_telegram_to_agent_flow(self, session_manager, mock_agent_loop):
        """Test message flow from Telegram through Gateway to Agent."""
        # Setup Telegram adapter
        telegram_config = {
            "bot_token": "test_token",
            "trusted_user_ids": ["12345"],
        }
        telegram_adapter = TelegramAdapter(telegram_config)

        # Mock incoming Telegram update
        mock_update = MagicMock()
        mock_update.message.from_user.id = 12345
        mock_update.message.text = "Hello MUSEON"
        mock_update.message.date = datetime(2026, 2, 25, 10, 0, 0)
        mock_update.message.chat.id = 12345

        # Step 1: Receive message from Telegram
        telegram_adapter._get_update = lambda: mock_update
        message = await telegram_adapter.receive()

        assert message.source == "telegram"
        assert message.content == "Hello MUSEON"
        assert message.trust_level == "core"

        # Step 2: Session manager acquires lock
        acquired = await session_manager.acquire(message.session_id)
        assert acquired is True

        # Step 3: Agent processes message
        response = await mock_agent_loop.process(message)
        assert response == "Agent response"

        # Step 4: Release session lock
        await session_manager.release(message.session_id)
        assert session_manager.is_processing(message.session_id) is False

        # Step 5: Send response back via Telegram
        response_message = InternalMessage(
            source="telegram",
            session_id=message.session_id,
            user_id=message.user_id,
            content=response,
            timestamp=datetime.now(),
            trust_level="core",
            metadata={"chat_id": 12345},
        )

        telegram_adapter._send_telegram_message = lambda msg: True
        result = await telegram_adapter.send(response_message)
        assert result is True

    @pytest.mark.asyncio
    async def test_webhook_to_agent_flow_with_verification(
        self, session_manager, mock_agent_loop
    ):
        """Test webhook message flow with HMAC verification."""
        # Setup Webhook adapter
        webhook_config = {
            "hmac_secret": "test_secret_123",
            "timestamp_window": 300,
        }
        webhook_adapter = WebhookAdapter(webhook_config)

        # Create valid webhook payload and signature
        import hashlib
        import hmac
        import json

        payload = {
            "user_id": "line_user_123",
            "content": "Product inquiry from LINE",
            "timestamp": int(datetime.now().timestamp()),
            "source_type": "line",
        }
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            "test_secret_123".encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()

        # Step 1: Receive and verify webhook
        webhook_adapter._get_webhook_request = lambda: (payload, signature)
        message = await webhook_adapter.receive()

        assert message.source == "webhook"
        assert message.content == "Product inquiry from LINE"
        assert message.trust_level == "verified"

        # Step 2: Session manager acquires lock
        acquired = await session_manager.acquire(message.session_id)
        assert acquired is True

        # Step 3: Agent processes message
        response = await mock_agent_loop.process(message)
        assert response is not None

        # Step 4: Release session lock
        await session_manager.release(message.session_id)

    @pytest.mark.asyncio
    async def test_electron_to_agent_flow(self, session_manager, mock_agent_loop):
        """Test Electron Dashboard → Gateway → Agent flow."""
        # Setup Electron adapter
        electron_config = {
            "ipc_socket_path": "/tmp/museon_test.sock",
            "owner_user_id": "owner",
        }
        electron_adapter = ElectronAdapter(electron_config)

        # Mock IPC data
        ipc_data = {
            "user_id": "owner",
            "content": "Show me today's token usage",
            "timestamp": datetime.now().isoformat(),
        }

        # Step 1: Receive message from Electron
        electron_adapter._read_from_ipc = lambda: ipc_data
        message = await electron_adapter.receive()

        assert message.source == "electron"
        assert message.content == "Show me today's token usage"
        assert message.trust_level == "core"
        assert message.session_id == "electron_main"

        # Step 2: Session manager acquires lock
        acquired = await session_manager.acquire(message.session_id)
        assert acquired is True

        # Step 3: Agent processes message
        response = await mock_agent_loop.process(message)
        assert response is not None

        # Step 4: Release session lock
        await session_manager.release(message.session_id)

        # Step 5: Send response back via IPC
        response_message = InternalMessage(
            source="electron",
            session_id="electron_main",
            user_id="owner",
            content=response,
            timestamp=datetime.now(),
            trust_level="core",
            metadata={},
        )

        electron_adapter._write_to_ipc = lambda msg: True
        result = await electron_adapter.send(response_message)
        assert result is True

    @pytest.mark.asyncio
    async def test_concurrent_sessions_serial_processing(
        self, session_manager, mock_agent_loop
    ):
        """Test that same session processes serially, different sessions can run concurrently."""
        # Create two messages for same session
        message1 = InternalMessage(
            source="telegram",
            session_id="telegram_12345",
            user_id="12345",
            content="First message",
            timestamp=datetime.now(),
            trust_level="core",
            metadata={},
        )

        message2 = InternalMessage(
            source="telegram",
            session_id="telegram_12345",
            user_id="12345",
            content="Second message",
            timestamp=datetime.now(),
            trust_level="core",
            metadata={},
        )

        # Create message for different session
        message3 = InternalMessage(
            source="electron",
            session_id="electron_main",
            user_id="owner",
            content="Different session",
            timestamp=datetime.now(),
            trust_level="core",
            metadata={},
        )

        # Acquire lock for first message
        acquired1 = await session_manager.acquire(message1.session_id)
        assert acquired1 is True

        # Second message same session should fail to acquire immediately
        acquired2 = await session_manager.acquire(message2.session_id)
        assert acquired2 is False

        # Third message different session should succeed
        acquired3 = await session_manager.acquire(message3.session_id)
        assert acquired3 is True

        # Release locks
        await session_manager.release(message1.session_id)
        await session_manager.release(message3.session_id)

        # Now second message should succeed
        acquired2_retry = await session_manager.acquire(message2.session_id)
        assert acquired2_retry is True

        await session_manager.release(message2.session_id)

    @pytest.mark.asyncio
    async def test_webhook_invalid_signature_blocked(self, session_manager):
        """Test that webhook with invalid signature is rejected before reaching agent."""
        webhook_config = {
            "hmac_secret": "test_secret_123",
            "timestamp_window": 300,
        }
        webhook_adapter = WebhookAdapter(webhook_config)

        # Create payload with INVALID signature
        payload = {
            "user_id": "attacker",
            "content": "Malicious message",
            "timestamp": int(datetime.now().timestamp()),
        }
        invalid_signature = "invalid_signature_here"

        # Webhook adapter should reject before message reaches agent
        webhook_adapter._get_webhook_request = lambda: (payload, invalid_signature)
        with pytest.raises(ValueError, match="Invalid HMAC signature"):
            await webhook_adapter.receive()

    @pytest.mark.asyncio
    async def test_trust_level_propagation(self, mock_agent_loop):
        """Test that trust levels are properly set and propagated."""
        # Test CORE trust level (Telegram trusted user)
        telegram_config = {"bot_token": "test", "trusted_user_ids": ["12345"]}
        telegram_adapter = TelegramAdapter(telegram_config)
        assert telegram_adapter.get_trust_level("12345") == "core"

        # Test EXTERNAL trust level (Telegram untrusted user)
        assert telegram_adapter.get_trust_level("99999") == "external"

        # Test VERIFIED trust level (Webhook with valid HMAC)
        webhook_config = {"hmac_secret": "test"}
        webhook_adapter = WebhookAdapter(webhook_config)
        assert webhook_adapter.get_trust_level("any_user") == "verified"

        # Test CORE trust level (Electron)
        electron_config = {"ipc_socket_path": "/tmp/test.sock"}
        electron_adapter = ElectronAdapter(electron_config)
        assert electron_adapter.get_trust_level("owner") == "core"
