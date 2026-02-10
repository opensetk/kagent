"""
Agent module for kagent - core conversation loop.

This module provides the AgentLoop class which manages the conversation flow
between user and LLM, handling tool calls and responses.
"""

from typing import Dict, Any, Optional

from kagent.core.tool import ToolManager
from kagent.core.context import ContextManager
from kagent.llm.client import LLMClient


class AgentLoop:
    """
    Agent Loop with tool support.

    This class manages the conversation with LLM and coordinates tool execution
    through the ToolManager. It delegates LLM calls to LLMClient and context
    management to ContextManager.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_manager: ToolManager,
        context_manager: Optional[ContextManager] = None,
        max_iterations: int = 100,
    ):
        """
        Initialize AgentLoop.

        Args:
            llm_client: LLM client for API calls
            tool_manager: ToolManager instance for tool execution
            context_manager: Optional ContextManager (creates default if not provided)
            max_iterations: Maximum tool call iterations per user message
        """
        self.llm_client = llm_client
        self.tool_manager = tool_manager
        self.context_manager = context_manager or ContextManager(model=llm_client.model)
        self.max_iterations = max_iterations

    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt for the agent"""
        self.context_manager.set_system_prompt(prompt)

    async def chat(self, user_input: str) -> str:
        """
        Process a single chat message with tool support.

        This is the core conversation method that:
        1. Adds user message to context
        2. Calls LLM with available tools
        3. Handles tool calls if present
        4. Returns final assistant response

        Args:
            user_input: User's message

        Returns:
            Assistant's response string
        """
        self.context_manager.add_message("user", user_input)

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # Get messages for API call
            messages = self.context_manager.get_messages()

            # Get available tools
            tools = self.tool_manager.get_openai_tools() if self.tool_manager else None

            # Call LLM
            response = await self.llm_client.complete(messages, tools=tools)

            if not response or not response.content and not response.tool_calls:
                error_msg = "Error: Failed to get response from LLM"
                self.context_manager.add_message("assistant", error_msg)
                return error_msg

            # Check if there are tool calls
            if response.tool_calls:
                # Prepare tool calls data for storage
                tool_calls_data = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ]

                # Add assistant message with tool calls to history
                self.context_manager.add_message(
                    "assistant",
                    response.content or "",
                    tool_calls=tool_calls_data,
                )

                # Execute tools
                tool_results = await self.tool_manager.execute_tool_calls(
                    response.tool_calls
                )

                # Add tool results to conversation
                for tool_result in tool_results:
                    self.context_manager.add_message(
                        tool_result["role"],
                        tool_result["content"],
                        tool_call_id=tool_result.get("tool_call_id"),
                        name=tool_result.get("name"),
                    )

                # Continue loop to let LLM process tool results
                continue
            else:
                # No tool calls, we have a final response
                response_content = response.content or "No response generated"
                self.context_manager.add_message("assistant", response_content)
                return response_content

        # Max iterations reached
        max_iter_msg = "Error: Maximum tool iteration limit reached"
        self.context_manager.add_message("assistant", max_iter_msg)
        return max_iter_msg
