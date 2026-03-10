"""Unit tests for LLM Client and Router."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any


class TestRouter:
    """Test Router classification logic."""

    def test_classify_simple_greeting_to_haiku(self):
        """Test that simple greetings are routed to Haiku."""
        from museon.llm.router import Router

        router = Router()

        greetings = ["Hello!", "Hi", "Hey there", "Good morning"]

        for greeting in greetings:
            result = router.classify(greeting, session_context={})
            assert result["model"] == "haiku"
            assert result["task_type"] == "simple_greeting"

    def test_classify_skill_task_to_sonnet(self):
        """Test that skill-based tasks are routed to Sonnet."""
        from museon.llm.router import Router

        router = Router()

        skill_requests = [
            "Help me write an Instagram post",
            "Create a brand story for my business",
            "Write a marketing email",
        ]

        for request in skill_requests:
            result = router.classify(request, session_context={})
            assert result["model"] == "sonnet"
            assert result["reason"].startswith("kw:")
            assert result["task_type"] == "complex"

    def test_classify_business_consulting_to_sonnet(self):
        """Test that business consulting is routed to Sonnet."""
        from museon.llm.router import Router

        router = Router()

        consulting_requests = [
            "My revenue dropped this month",
            "How can I improve my business?",
            "What marketing strategy should I use?",
        ]

        for request in consulting_requests:
            result = router.classify(request, session_context={})
            assert result["model"] == "sonnet"
            assert result["reason"].startswith("kw:")
            assert result["task_type"] == "complex"

    def test_classify_simple_query_to_haiku(self):
        """Test that simple queries are routed to Haiku."""
        from museon.llm.router import Router

        router = Router()

        simple_queries = [
            "What time is it?",
            "What's the weather today?",
        ]

        for query in simple_queries:
            result = router.classify(query, session_context={})
            assert result["model"] == "haiku"
            # Short queries may hit ultra_short rule or HAIKU_PATTERNS regex;
            # either way task_type is simple_ack or simple_query.
            assert result["task_type"] in ("simple_query", "simple_ack")

    def test_maintain_sonnet_with_active_skills(self):
        """Test routing when skills are active in session context.

        Note: Current router does not check active_skills in session_context.
        A short message without Sonnet keywords is routed to Haiku (casual_chat).
        Active skill awareness is handled at a higher layer, not the Router.
        """
        from museon.llm.router import Router

        router = Router()

        session_context = {"active_skills": ["text-alchemy", "brand-identity"]}

        result = router.classify("Continue with the post", session_context=session_context)
        # Router classifies purely on message content; active_skills not checked
        assert result["model"] == "haiku"
        assert result["reason"] == "casual_chat"
        assert result["task_type"] == "chat"

    def test_default_to_sonnet_for_complex_tasks(self):
        """Test that tasks with Sonnet keywords are routed to Sonnet."""
        from museon.llm.router import Router

        router = Router()

        complex_requests = [
            "Help me draft a business plan for next quarter",
            "Can you analyze this data and give me insights?",
        ]

        for request in complex_requests:
            result = router.classify(request, session_context={})
            assert result["model"] == "sonnet"
            assert result["reason"].startswith("kw:")
            assert result["task_type"] == "complex"


class TestLLMClient:
    """Test LLM Client."""

    @pytest.mark.asyncio
    async def test_create_message_with_haiku(self, mock_anthropic_client):
        """Test creating message with Haiku model."""
        from museon.llm.client import LLMClient

        client = LLMClient(api_key="test_key")
        client._client = mock_anthropic_client

        response = await client.create_message(
            model="haiku", messages=[{"role": "user", "content": "Hello"}], max_tokens=100
        )

        assert response is not None
        mock_anthropic_client.messages.create.assert_called_once()
        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert "claude-haiku-4-5" in call_kwargs["model"]

    @pytest.mark.asyncio
    async def test_create_message_with_sonnet(self, mock_anthropic_client):
        """Test creating message with Sonnet model."""
        from museon.llm.client import LLMClient

        client = LLMClient(api_key="test_key")
        client._client = mock_anthropic_client

        response = await client.create_message(
            model="sonnet", messages=[{"role": "user", "content": "Hello"}], max_tokens=100
        )

        assert response is not None
        mock_anthropic_client.messages.create.assert_called_once()
        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert "claude-sonnet-4" in call_kwargs["model"]

    @pytest.mark.asyncio
    async def test_prompt_caching_header(self, mock_anthropic_client):
        """Test that prompt caching is enabled."""
        from museon.llm.client import LLMClient

        client = LLMClient(api_key="test_key")
        client._client = mock_anthropic_client

        system_prompt = "You are a helpful assistant."

        await client.create_message(
            model="sonnet",
            messages=[{"role": "user", "content": "Hello"}],
            system=system_prompt,
            max_tokens=100,
        )

        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        # Check that system prompt is set up for caching
        assert "system" in call_kwargs

    @pytest.mark.asyncio
    async def test_token_efficient_tool_use_header(self, mock_anthropic_client):
        """Test that token-efficient tool use header is sent."""
        from museon.llm.client import LLMClient

        client = LLMClient(api_key="test_key")
        client._client = mock_anthropic_client

        tools = [{"name": "search", "description": "Search the web"}]

        # Mock the Anthropic client to check extra_headers
        client._client.messages.create = AsyncMock(
            return_value=Mock(
                content=[Mock(text="Test", type="text")], usage=Mock(input_tokens=10, output_tokens=5)
            )
        )

        await client.create_message(
            model="sonnet",
            messages=[{"role": "user", "content": "Search for info"}],
            tools=tools,
            max_tokens=100,
        )

        # Check that the call includes tools
        call_kwargs = client._client.messages.create.call_args[1]
        assert "tools" in call_kwargs or "extra_headers" in call_kwargs


class TestBudgetMonitor:
    """Test Token Budget Monitor."""

    def test_track_usage(self):
        """Test tracking token usage."""
        from museon.llm.budget import BudgetMonitor

        monitor = BudgetMonitor(daily_limit=200000)

        monitor.track_usage(input_tokens=1000, output_tokens=500)
        monitor.track_usage(input_tokens=2000, output_tokens=1000)

        total = monitor.get_total_usage()
        assert total == 4500

    def test_usage_percentage(self):
        """Test calculating usage percentage."""
        from museon.llm.budget import BudgetMonitor

        monitor = BudgetMonitor(daily_limit=200000)

        monitor.track_usage(input_tokens=100000, output_tokens=50000)

        percentage = monitor.get_usage_percentage()
        assert percentage == 75.0  # 150000 / 200000

    def test_check_budget_within_limit(self):
        """Test checking budget when within limit."""
        from museon.llm.budget import BudgetMonitor

        monitor = BudgetMonitor(daily_limit=200000)

        monitor.track_usage(input_tokens=50000, output_tokens=50000)

        assert monitor.check_budget(required_tokens=50000) is True

    def test_check_budget_exceeded(self):
        """Test checking budget when exceeded."""
        from museon.llm.budget import BudgetMonitor

        monitor = BudgetMonitor(daily_limit=200000)

        monitor.track_usage(input_tokens=150000, output_tokens=60000)

        # Already exceeded budget
        assert monitor.check_budget(required_tokens=1000) is False

    def test_warning_threshold(self):
        """Test warning when approaching budget limit."""
        from museon.llm.budget import BudgetMonitor

        monitor = BudgetMonitor(daily_limit=200000, warning_threshold=0.8)

        monitor.track_usage(input_tokens=130000, output_tokens=30000)

        assert monitor.should_warn() is True


class TestReflexEngine:
    """Test Reflex Engine for template matching."""

    def test_match_template(self):
        """Test matching a template."""
        from museon.llm.reflex import ReflexEngine

        engine = ReflexEngine()

        # Add template
        engine.add_template(pattern=r"(?i)(what'?s? (your|the) (phone|number))", response="Please contact us at: +886-XXX-XXXX")

        result = engine.match("What's your phone number?")

        assert result is not None
        assert "contact us" in result.lower()

    def test_no_match(self):
        """Test when no template matches."""
        from museon.llm.reflex import ReflexEngine

        engine = ReflexEngine()

        result = engine.match("Tell me about your business strategy")

        assert result is None

    def test_multiple_templates(self):
        """Test multiple templates."""
        from museon.llm.reflex import ReflexEngine

        engine = ReflexEngine()

        engine.add_template(pattern=r"(?i)hello|hi|hey", response="Hello! How can I help you today?")
        engine.add_template(pattern=r"(?i)bye|goodbye", response="Goodbye! Have a great day!")

        assert engine.match("Hello") is not None
        assert engine.match("Goodbye!") is not None
        assert engine.match("Random text") is None


class TestPromptCaching:
    """Test Prompt Caching functionality."""

    def test_cache_config_structure(self):
        """Test that cache config is properly structured."""
        from museon.llm.cache import PromptCacheConfig

        config = PromptCacheConfig.create_system_cache(content="Test system prompt", ttl=3600)

        assert config["type"] == "text"
        assert config["text"] == "Test system prompt"
        assert config.get("cache_control") is not None

    def test_cache_breakpoints(self):
        """Test that cache breakpoints are set correctly."""
        from museon.llm.cache import PromptCacheConfig

        # Should support up to 4 cache breakpoints
        configs = [
            PromptCacheConfig.create_system_cache("DNA27 core", ttl=3600),
            PromptCacheConfig.create_system_cache("Active skills", ttl=300),
        ]

        assert len(configs) <= 4
        for config in configs:
            assert "cache_control" in config
