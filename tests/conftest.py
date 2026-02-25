"""Pytest configuration and fixtures for MuseClaw tests."""

import asyncio
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
from unittest.mock import AsyncMock, Mock


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_data_dir(tmp_path: Path) -> Path:
    """Provide a temporary data directory for tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "memory").mkdir(exist_ok=True)
    (data_dir / "vector").mkdir(exist_ok=True)
    return data_dir


@pytest.fixture
def mock_anthropic_client() -> Mock:
    """Mock Anthropic client for testing."""
    client = Mock()
    client.messages = Mock()
    client.messages.create = AsyncMock(
        return_value=Mock(
            content=[Mock(text="Test response", type="text")],
            usage=Mock(input_tokens=100, output_tokens=50),
        )
    )
    return client


@pytest.fixture
def sample_internal_message() -> dict:
    """Sample internal message for testing."""
    return {
        "source": "telegram",
        "session_id": "test_session_123",
        "user_id": "user_456",
        "content": "Hello MuseClaw",
        "timestamp": "2026-02-25T10:00:00Z",
        "trust_level": "verified",
        "metadata": {},
    }


@pytest.fixture
def mock_session_manager() -> Mock:
    """Mock session manager for testing."""
    manager = Mock()
    manager.acquire = AsyncMock()
    manager.release = AsyncMock()
    manager.is_processing = Mock(return_value=False)
    return manager
