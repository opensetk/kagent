"""
LLM module for kagent - multi-provider LLM support.
"""

from kagent.llm.base import BaseLLMProvider, LLMResponse, LLMToolCall
from kagent.llm.client import LLMClient
from kagent.llm.openai_provider import OpenAIProvider

try:
    from kagent.llm.claude_provider import ClaudeProvider
except ImportError:
    # Anthropic client not installed
    ClaudeProvider = None  # type: ignore

__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "LLMToolCall",
    "LLMClient",
    "OpenAIProvider",
    "ClaudeProvider",
]
