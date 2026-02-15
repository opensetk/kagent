"""
Anthropic Claude LLM Provider implementation.
"""

import os
import json
from typing import Any, Dict, List, Optional

from kagent.llm.base import BaseLLMProvider, LLMResponse, LLMToolCall


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude LLM Provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "claude-3-sonnet-20240229",
    ):
        # Load from environment if not provided
        api_key = (
            api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("LLM_API_KEY") or ""
        )
        base_url = (
            base_url
            or os.getenv("ANTHROPIC_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or ""
        )

        super().__init__(api_key, base_url, model)

        # Try to import anthropic
        try:
            from anthropic import AsyncAnthropic

            self.client = AsyncAnthropic(api_key=self.api_key, base_url=self.base_url)
        except ImportError:
            raise ImportError(
                "Anthropic client not installed. Install with: pip install anthropic"
            )

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> LLMResponse:
        """Complete a conversation with Claude."""
        try:
            # Convert OpenAI format to Claude format
            claude_messages = self.format_messages(messages)

            # Extract system message
            system_message = None
            for msg in claude_messages:
                if msg.get("role") == "system":
                    system_message = msg.get("content")
                    break

            # Filter out system messages from conversation
            conversation = [
                msg for msg in claude_messages if msg.get("role") != "system"
            ]

            # Build request kwargs
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": conversation,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if system_message:
                kwargs["system"] = system_message

            if tools:
                kwargs["tools"] = self.format_tools(tools)

            response = await self.client.messages.create(**kwargs)

            # Extract content and tool calls
            content = None
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content = block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        LLMToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=json.dumps(block.input),
                        )
                    )

            return LLMResponse(
                content=content,
                tool_calls=tool_calls if tool_calls else None,
                raw_response=response,
            )

        except Exception as e:
            print(f"Error calling Claude API: {e}")
            return LLMResponse(content=None)

    def format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert OpenAI format to Claude format."""
        formatted = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                formatted.append({"role": "system", "content": content})
            elif role == "user":
                formatted.append({"role": "user", "content": content})
            elif role == "assistant":
                formatted.append({"role": "assistant", "content": content})
            elif role == "tool":
                # Claude uses tool_result role
                formatted.append(
                    {
                        "role": "user",  # Tool results go as user messages in Claude
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.get("tool_call_id", ""),
                                "content": content,
                            }
                        ],
                    }
                )

        return formatted

    def format_tools(self, tools: List[Dict]) -> List[Dict]:
        """Convert OpenAI tool format to Claude tool format."""
        formatted = []

        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                formatted.append(
                    {
                        "name": func.get("name"),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {}),
                    }
                )

        return formatted
