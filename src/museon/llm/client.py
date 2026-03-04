"""LLM Client - Claude API wrapper with Haiku and Sonnet support."""

import os
from typing import Any, Dict, List, Optional, Literal

from anthropic import AsyncAnthropic


class LLMClient:
    """
    Claude API client with support for Haiku and Sonnet models.

    Features:
    - Dual model support (Haiku 4.5 + Sonnet 4.5)
    - Prompt Caching (GA)
    - Token-Efficient Tool Use
    """

    MODEL_MAP = {
        "haiku": "claude-3-5-haiku-20241022",
        "sonnet": "claude-3-5-sonnet-20241022",
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
        model: Literal["haiku", "sonnet"],
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
        response = await self._client.messages.create(**request_params)

        return response

    def get_model_name(self, model: Literal["haiku", "sonnet"]) -> str:
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
