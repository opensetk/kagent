"""
Tool system for kagent with decorator-based registration.

Usage:
    from kagent.core.tool import tool, ToolManager

    @tool(description="Optional custom description")
    async def my_tool(param: str, optional: int = 0) -> str:
        '''Tool description here'''
        return f"Result: {param}"
"""

import json
import os
import sys
import asyncio
import inspect
import traceback
import importlib
import pkgutil
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Dict, Any, List, Callable, Awaitable, Optional, Union, TypeVar


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    error: Optional[str] = None

    def to_display_string(self) -> str:
        """Format the tool result for display to the user."""
        lines = [
            f"[Tool: {self.tool_name}]",
            f"Arguments: {json.dumps(self.arguments, ensure_ascii=False, indent=2)}",
        ]
        if self.success:
            result_str = str(self.result) if self.result is not None else "(empty)"
            lines.append(f"Result:\n{result_str}")
        else:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)


@dataclass
class Tool:
    """Definition of a tool that can be called by the agent."""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    handler: Callable[..., Awaitable[Any]]

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _python_type_to_json_schema(py_type: type) -> Dict[str, Any]:
    """Convert Python type to JSON Schema type."""
    type_map = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        list: {"type": "array"},
        dict: {"type": "object"},
    }

    # Handle Optional types
    origin = getattr(py_type, "__origin__", None)
    if origin is Union:
        args = getattr(py_type, "__args__", ())
        # Filter out NoneType
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            return _python_type_to_json_schema(non_none_types[0])
        # Multiple types - use anyOf
        return {"anyOf": [_python_type_to_json_schema(t) for t in non_none_types]}

    return type_map.get(py_type, {"type": "string"})


def _build_schema_from_signature(
    func: Callable, param_descriptions: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Build JSON Schema from function signature."""
    sig = inspect.signature(func)
    properties = {}
    required = []
    param_descriptions = param_descriptions or {}

    for name, param in sig.parameters.items():
        # Skip **kwargs
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            continue

        # Get type annotation
        if param.annotation != inspect.Parameter.empty:
            schema = _python_type_to_json_schema(param.annotation)
        else:
            schema = {"type": "string"}

        # Add description
        if name in param_descriptions:
            schema["description"] = param_descriptions[name]

        properties[name] = schema

        # Check if required
        if param.default == inspect.Parameter.empty:
            required.append(name)

    return {"type": "object", "properties": properties, "required": required}


# Global registry for decorated tools
_tool_registry: List[Tool] = []


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    param_descriptions: Optional[Dict[str, str]] = None,
):
    """
    Decorator to register a function as a tool.

    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to function docstring)
        param_descriptions: Descriptions for parameters {param_name: description}

    Example:
        @tool(param_descriptions={"path": "File path to read"})
        async def read_file(path: str, limit: int = 100) -> str:
            '''Read file contents'''
            return open(path).read()[:limit]
    """

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip()

        # Build schema from signature
        parameters = _build_schema_from_signature(func, param_descriptions)

        # Create tool
        tool_obj = Tool(
            name=tool_name, description=tool_desc, parameters=parameters, handler=func
        )

        # Register globally
        _tool_registry.append(tool_obj)

        # Mark function as a tool
        func._tool = tool_obj

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        wrapper._tool = tool_obj
        return wrapper

    return decorator


def clear_tool_registry():
    """Clear the global tool registry."""
    global _tool_registry
    _tool_registry = []


def get_registered_tools() -> List[Tool]:
    """Get all tools registered via decorator."""
    return _tool_registry.copy()


class ToolManager:
    """
    Central manager for all tools.

    Responsibilities:
    - Manage tool registration and execution
    - Provide tools in OpenAI function calling format
    """

    def __init__(self, load_builtin: bool = True):
        """
        Initialize ToolManager.

        Args:
            load_builtin: Whether to automatically load built-in tools from kagent.tools
        """
        self._tools: Dict[str, Tool] = {}
        if load_builtin:
            self.load_builtin_tools()

    def load_builtin_tools(self) -> None:
        """
        Automatically discover and load all tools in the kagent.tools package.
        """
        import kagent.tools as tools_package

        # Discover and import all modules in kagent.tools
        for _, module_name, _ in pkgutil.iter_modules(
            tools_package.__path__, tools_package.__name__ + "."
        ):
            try:
                module = importlib.import_module(module_name)
                # After importing (or getting from cache), scan module for tools
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    tool_obj = getattr(attr, "_tool", None)
                    if tool_obj and isinstance(tool_obj, Tool):
                        self.register(tool_obj)
            except Exception as e:
                print(f"Error loading tool module {module_name}: {e}")

        # Also register any tools that might have been registered globally via other means
        for tool_obj in get_registered_tools():
            self.register(tool_obj)

    def add_tools(self, tool_funcs: List[Callable]) -> None:
        """
        Add extra tools from a list of decorated functions.

        Args:
            tool_funcs: List of functions decorated with @tool
        """
        for func in tool_funcs:
            # Check if it's a decorated function (has _tool attribute)
            tool_obj = getattr(func, "_tool", None)
            if tool_obj and isinstance(tool_obj, Tool):
                self.register(tool_obj)
            else:
                # If it's not decorated, we could potentially try to decorate it on the fly
                # but based on requirements, we expect decorated tools.
                print(f"Warning: Function {func.__name__} is not a decorated tool.")

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name.lower()] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        name = name.lower()
        if name in self._tools:
            del self._tools[name]

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name.lower())

    def list_tools(self) -> List[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Get all tools in OpenAI function calling format."""
        return [tool.to_openai_format() for tool in self._tools.values()]

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute a tool with given arguments."""
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=f"Tool '{tool_name}' not found. Available: {', '.join(self._tools.keys())}",
            )

        try:
            result = await tool.handler(**arguments)
            return ToolResult(
                success=True, tool_name=tool_name, arguments=arguments, result=result
            )
        except Exception as e:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                arguments=arguments,
                result=None,
                error=f"{str(e)}\n{traceback.format_exc()}",
            )

    async def execute_multiple(self, calls: List[Dict[str, Any]]) -> List[ToolResult]:
        """Execute multiple tool calls concurrently."""
        tasks = [self.execute(call["tool_name"], call["arguments"]) for call in calls]
        return await asyncio.gather(*tasks)

    async def execute_tool_calls(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """
        Execute tool calls from LLM responses and return formatted messages.

        Args:
            tool_calls: List of tool call objects (OpenAI or LLMToolCall format)

        Returns:
            List of tool result messages ready for conversation history
        """
        tool_messages = []

        for tool_call in tool_calls:
            # Extract tool call info (handles both OpenAI and unified format)
            if hasattr(tool_call, "function"):
                # OpenAI format
                tool_name = tool_call.function.name
                tool_id = tool_call.id
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
            else:
                # Unified format (from LLMToolCall)
                tool_name = tool_call.name
                tool_id = tool_call.id
                try:
                    arguments = json.loads(tool_call.arguments)
                except json.JSONDecodeError:
                    arguments = {}

            # Execute the tool
            result: ToolResult = await self.execute(tool_name, arguments)

            # Print tool execution for user visibility
            print(f"\n[Tool: {tool_name}]")
            print(f"Arguments: {json.dumps(arguments, ensure_ascii=False)}")
            if result.success:
                result_str = str(result.result)
                display = (
                    result_str[:200] + "..." if len(result_str) > 200 else result_str
                )
                print(f"Result: {display}")
            else:
                print(f"Error: {result.error}")

            # Create tool result message
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result.to_display_string(),
                }
            )

        return tool_messages
