"""
LLM Provider module for kagent - supports multiple LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMMessage:
    """Unified message format for all LLM providers."""

    def __init__(self, role: str, content: str, **kwargs):
        self.role = role
        self.content = content
        self.metadata = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """Convert to provider-specific format."""
        raise NotImplementedError


class LLMToolCall:
    """Unified tool call format."""

    def __init__(self, id: str, name: str, arguments: str):
        self.id = id
        self.name = name
        self.arguments = arguments


class LLMResponse:
    """Unified LLM response format."""

    def __init__(
        self,
        content: Optional[str] = None,
        tool_calls: Optional[List[LLMToolCall]] = None,
        raw_response: Any = None,
    ):
        self.content = content
        self.tool_calls = tool_calls or []
        self.raw_response = raw_response


class BaseLLMProvider(ABC):
    """Base class for all LLM providers."""

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Complete a conversation with the LLM."""
        pass

    @abstractmethod
    def format_messages(self, messages: List[Dict[str, Any]]) -> Any:
        """Format messages for this specific provider."""
        pass

    @abstractmethod
    def format_tools(self, tools: List[Dict]) -> Any:
        """Format tools for this specific provider."""
        pass
