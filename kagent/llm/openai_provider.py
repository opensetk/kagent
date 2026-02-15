"""
OpenAI LLM Provider implementation.
"""

import os
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageToolCall

from kagent.llm.base import BaseLLMProvider, LLMResponse, LLMToolCall


class OpenAIProvider(BaseLLMProvider):
    """OpenAI LLM Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
    ):
        # Load from environment if not provided
        api_key = (
            api_key or os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or ""
        )
        base_url = (
            base_url or os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or ""
        )

        super().__init__(api_key, base_url, model)

        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Complete a conversation with OpenAI."""
        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = await self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            # Extract tool calls
            tool_calls = None
            if message.tool_calls:
                tool_calls = [
                    LLMToolCall(
                        id=tc.id, name=tc.function.name, arguments=tc.function.arguments
                    )
                    for tc in message.tool_calls
                ]

            return LLMResponse(
                content=message.content, tool_calls=tool_calls, raw_response=response
            )

        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return LLMResponse(content=None)

    def format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """OpenAI uses native message format."""
        return messages

    def format_tools(self, tools: List[Dict]) -> List[Dict]:
        """OpenAI uses native tool format."""
        return tools
