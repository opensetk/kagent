"""
Unified LLM Client for kagent - supports multiple providers.
"""

from typing import Any, Dict, List, Optional, Union

from kagent.llm.base import BaseLLMProvider, LLMResponse
from kagent.llm.openai_provider import OpenAIProvider


class LLMClient:
    """
    Unified LLM Client that supports multiple providers.

    Usage:
        # From preset (recommended)
        client = LLMClient.from_preset("deepseek")
        
        # From environment
        client = LLMClient.from_env("openai", model="gpt-4")

        # Custom provider
        client = LLMClient(provider=MyCustomProvider())
    """

    def __init__(self, provider: BaseLLMProvider):
        """
        Initialize with a provider.

        Args:
            provider: LLM provider instance
        """
        self.provider = provider

    @classmethod
    def from_preset(cls, preset_name: str) -> "LLMClient":
        """
        Create LLMClient from a preset name.
        
        Args:
            preset_name: Preset name (e.g., "deepseek", "gpt4o", "claude-sonnet")
        
        Returns:
            LLMClient instance
        
        Example:
            client = LLMClient.from_preset("deepseek")
        """
        from kagent.llm.preset import PresetManager
        
        manager = PresetManager.load()
        preset = manager.get(preset_name)
        
        if preset is None:
            available = ", ".join(manager.list())
            raise ValueError(f"Unknown preset: '{preset_name}'. Available: {available}")
        
        return cls.from_env(**preset.to_llm_kwargs())

    @classmethod
    def from_env(cls, provider_type: str = "openai", **kwargs) -> "LLMClient":
        """
        Create LLMClient from environment variables.

        Args:
            provider_type: "openai" or "claude"
            **kwargs: Additional arguments passed to provider

        Returns:
            LLMClient instance
        """
        provider_type = provider_type.lower()

        if provider_type == "openai":
            provider = OpenAIProvider(**kwargs)
        elif provider_type in ["claude", "anthropic"]:
            from kagent.llm.claude_provider import ClaudeProvider

            provider = ClaudeProvider(**kwargs)
        else:
            raise ValueError(f"Unknown provider type: {provider_type}")

        return cls(provider)

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """
        Complete a conversation.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tools
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            LLMResponse object
        """
        return await self.provider.complete(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    @property
    def model(self) -> str:
        """Get the model name."""
        return self.provider.model
