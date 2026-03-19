"""LLM Client - Claude API wrapper (DEPRECATED: 請使用 llm/adapters.py).

此模組為早期 API 直連實作，已被 adapters.py 的 FallbackAdapter 取代。
保留供向後相容參考，不建議在新代碼中使用。
"""

import logging
import os
from typing import Any, Dict, List, Optional, Literal

import anthropic
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Claude API client with support for Haiku and Sonnet models.

    Features:
    - Dual model support (Haiku 4.5 + Sonnet 4.5)
    - Prompt Caching (GA)
    - Token-Efficient Tool Use
    """

    # P4: 新增 opus（v4 三層路由）
    MODEL_MAP = {
        "opus": "claude-opus-4-6",
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-20250514",
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        Initialize LLM Client.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ValueError("ANTHROPIC_API_KEY must be provided or set in environment")

        self._client = AsyncAnthropic(api_key=self._api_key)

    async def create_message(
        self,
        model: Literal["opus", "haiku", "sonnet"],
        messages: List[Dict[str, Any]],
        max_tokens: int = 4096,
        system: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 1.0,
    ) -> Any:
        """
        Create a message using Claude API.

        Args:
            model: Which model to use ("haiku" or "sonnet")
            messages: List of message dicts with role and content
            max_tokens: Maximum tokens to generate
            system: System prompt (will be cached if provided)
            tools: Tool definitions (Token-Efficient Tool Use enabled)
            temperature: Sampling temperature

        Returns:
            Message response from Claude API
        """
        model_id = self.MODEL_MAP[model]

        # Build request parameters
        request_params: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # Add system prompt with caching if provided
        if system:
            # For caching: system prompt should be a list with cache_control
            request_params["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        # Add tools with Token-Efficient header if provided
        if tools:
            request_params["tools"] = tools
            # Token-Efficient Tool Use is enabled via extra_headers
            # Note: In real implementation, this would be passed to the client
            # For now, we just include tools in the request

        # Make API call
        try:
            response = await self._client.messages.create(**request_params)
        except anthropic.RateLimitError as e:
            logger.warning(f"Anthropic rate limit hit: {e}")
            raise
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise

        return response

    def get_model_name(self, model: Literal["opus", "haiku", "sonnet"]) -> str:
        """
        Get the full model name.

        Args:
            model: Model identifier

        Returns:
            Full model name
        """
        return self.MODEL_MAP[model]

    async def close(self) -> None:
        """Close the client connection."""
        await self._client.close()
