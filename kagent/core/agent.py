"""
Agent module for kagent - core conversation loop.

This module provides the AgentLoop class which manages the conversation flow
between user and LLM, handling tool calls and responses.
"""

from typing import Dict, Any, Optional, Callable, List

from kagent.core.tool import ToolManager
from kagent.core.context import AgentRuntime, ContextManager, Context
from kagent.core.skill import SkillManager, Skill
from kagent.core.config import load_config
from kagent.llm.client import LLMClient


class AgentLoop:
    """
    Agent Loop with tool support.

    This class manages the conversation with LLM and coordinates tool execution
    through the ToolManager. It delegates LLM calls to LLMClient and context
    management to Context.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tool_manager: ToolManager,
        context: Optional[ContextManager] = None,
        skill_manager: Optional[SkillManager] = None,
        max_iterations: int = 100,
    ):
        """
        Initialize AgentLoop.

        Args:
            llm_client: LLM client for API calls
            tool_manager: ToolManager instance for tool execution
            context: Optional Context instance (creates default if not provided)
            skill_manager: Optional SkillManager for loading skills
            max_iterations: Maximum tool call iterations per user message
        """
        self.llm_client = llm_client
        self.tool_manager = tool_manager
        self.max_iterations = max_iterations
        self.skill_manager = skill_manager
        
        # Initialize context
        if context:
            self.context = context
        else:
            # Create default runtime and context
            config = load_config()
            runtime = AgentRuntime(
                max_tokens=config.max_tokens,
                ratio_of_compress=config.ratio_of_compress,
                keep_last_n_messages=config.keep_last_n_messages,
                work_dir=config.work_dir,
            )
            self.context = ContextManager(
                runtime=runtime,
                model=llm_client.model,
                llm_client=llm_client,
                skill_manager=self.skill_manager,
            )
            print(f"[ContextManager] System prompt loaded ({len(runtime.system_prompt)} chars):")
            print("-" * 40)
            print(runtime.system_prompt[:500] + "..." if len(runtime.system_prompt) > 500 else runtime.system_prompt)
            print("-" * 40)
    async def chat(
        self, 
        user_input: str,
        on_tool_call: Optional[Callable[[str, Dict[str, Any], Any], None]] = None
    ) -> str:
        """
        Process a single chat message with tool support.

        Args:
            user_input: User's message
            on_tool_call: Optional callback for tool execution display

        Returns:
            Assistant's response string
        """
        self.context.add_message("user", user_input)

        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1

            # Get messages for API call
            messages = self.context.get_messages()

            # Get available tools
            tools = self.tool_manager.get_openai_tools() if self.tool_manager else None

            # Call LLM
            response = await self.llm_client.complete(messages, tools=tools)

            if not response or not response.content and not response.tool_calls:
                error_msg = "Error: Failed to get response from LLM"
                self.context.add_message("assistant", error_msg)
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
                self.context.add_message(
                    "assistant",
                    response.content or "",
                    tool_calls=tool_calls_data,
                )

                # Execute tools with callback for display
                tool_results = await self.tool_manager.execute_tool_calls(
                    response.tool_calls,
                    on_tool_executed=on_tool_call
                )

                # Add tool results to conversation
                for tool_result in tool_results:
                    self.context.add_message(
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
                self.context.add_message("assistant", response_content)
                return response_content

        # Max iterations reached
        max_iter_msg = "Error: Maximum tool iteration limit reached"
        self.context.add_message("assistant", max_iter_msg)
        return max_iter_msg
