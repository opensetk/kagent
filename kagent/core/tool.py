"""
Tool system for kagent with decorator-based registration.
"""

import json
import asyncio
import inspect
import traceback
import importlib
import pkgutil
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Dict, Any, List, Callable, Awaitable, Optional, Union


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    error: Optional[str] = None

    def to_display_string(self) -> str:
        """Format the tool result for display."""
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
    parameters: Dict[str, Any]
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


class MCPToolAdapter:
    """Adapter to bridge MCP (Model Context Protocol) tools into kagent."""

    def __init__(self, mcp_url: str):
        self.mcp_url = mcp_url

    async def get_mcp_tools(self) -> List["Tool"]:
        """Fetch tools from MCP server and wrap them as kagent Tools."""
        try:
            from fastmcp import Client
        except ImportError:
            print("Warning: fastmcp not installed. MCP tools will not be available.")
            return []

        try:
            async with Client(self.mcp_url) as client:
                mcp_tools = await client.list_tools()
                kagent_tools = []
                for tool in mcp_tools:
                    handler = self._make_handler(tool.name)
                    kagent_tool = Tool(
                        name=tool.name,
                        description=tool.description or "",
                        parameters=tool.inputSchema or {"type": "object", "properties": {}},
                        handler=handler,
                    )
                    kagent_tools.append(kagent_tool)
                return kagent_tools
        except Exception as e:
            print(f"Error fetching MCP tools from {self.mcp_url}: {e}")
            return []

    def _make_handler(self, tool_name: str):
        """Create a handler closure for an MCP tool."""
        async def handler(**arguments):
            return await self.call_mcp_tool(tool_name, arguments)
        return handler

    async def call_mcp_tool(self, tool_name: str, arguments: dict):
        """Call an MCP tool and return the result."""
        from fastmcp import Client
        try:
            async with Client(self.mcp_url) as client:
                result = await client.call_tool(tool_name, arguments)
                if hasattr(result, "data"):
                    return result.data
                if hasattr(result, "content") and len(result.content) > 0:
                    return result.content[0].text
                return str(result)
        except Exception as e:
            raise Exception(f"Failed to call MCP tool '{tool_name}': {e}")


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

    origin = getattr(py_type, "__origin__", None)
    if origin is Union:
        args = getattr(py_type, "__args__", ())
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            return _python_type_to_json_schema(non_none_types[0])
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
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            continue

        if param.annotation != inspect.Parameter.empty:
            schema = _python_type_to_json_schema(param.annotation)
        else:
            schema = {"type": "string"}

        if name in param_descriptions:
            schema["description"] = param_descriptions[name]

        properties[name] = schema

        if param.default == inspect.Parameter.empty:
            required.append(name)

    return {"type": "object", "properties": properties, "required": required}


_tool_registry: List[Tool] = []


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    param_descriptions: Optional[Dict[str, str]] = None,
):
    """Decorator to register a function as a tool."""

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").strip()
        parameters = _build_schema_from_signature(func, param_descriptions)

        tool_obj = Tool(
            name=tool_name, description=tool_desc, parameters=parameters, handler=func
        )
        _tool_registry.append(tool_obj)

        func._tool = tool_obj

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        wrapper._tool = tool_obj
        return wrapper

    return decorator


def get_registered_tools() -> List[Tool]:
    """Get all tools registered via decorator."""
    return _tool_registry.copy()


class ToolManager:
    """Central manager for all tools."""

    def __init__(self, load_builtin: bool = True, load_mcp: bool = True):
        self._tools: Dict[str, Tool] = {}
        self._load_mcp = load_mcp
        self._mcp_loaded = False

        if load_builtin:
            self.load_builtin_tools()
        if load_mcp:
            self._start_mcp_load()

    def _start_mcp_load(self) -> None:
        """Start loading MCP tools if event loop is running."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.load_mcp_tools())
        except RuntimeError:
            pass

    async def load_mcp_tools(self) -> None:
        """Load MCP tools from .agent/mcp.json."""
        if self._mcp_loaded:
            return

        mcp_config_path = Path(".agent/mcp.json")
        if not mcp_config_path.exists():
            return

        try:
            with open(mcp_config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            mcp_servers = config.get("mcpServers", {}) if isinstance(config, dict) else {}

            if not mcp_servers and isinstance(config, list):
                for entry in config:
                    mcp_servers.update(entry.get("mcpServers", {}))

            for server_name, server_config in mcp_servers.items():
                url = server_config.get("url")
                if url:
                    print(f"Loading MCP tools from {server_name} ({url})...")
                    adapter = MCPToolAdapter(url)
                    mcp_tools = await adapter.get_mcp_tools()
                    for t in mcp_tools:
                        self.register(t)
                    if mcp_tools:
                        print(f"Loaded {len(mcp_tools)} tools from MCP server: {server_name}")

            self._mcp_loaded = True
        except Exception as e:
            print(f"Error loading MCP config: {e}")

    def load_builtin_tools(self) -> None:
        """Automatically discover and load all tools in the kagent.tools package."""
        import kagent.tools as tools_package

        for _, module_name, _ in pkgutil.iter_modules(
            tools_package.__path__, tools_package.__name__ + "."
        ):
            try:
                module = importlib.import_module(module_name)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    tool_obj = getattr(attr, "_tool", None)
                    if tool_obj and isinstance(tool_obj, Tool):
                        self.register(tool_obj)
            except Exception as e:
                print(f"Error loading tool module {module_name}: {e}")

        for tool_obj in get_registered_tools():
            self.register(tool_obj)

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name.lower()] = tool

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name.lower())

    def has_tool(self, name: str) -> bool:
        """Check if a tool with the given name exists."""
        return name.lower() in self._tools

    def get_all_tools(self) -> List[Dict[str, Any]]:
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
                error=f"Tool '{tool_name}' not found",
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

    async def execute_tool_calls(self, tool_calls: List[Any]) -> List[Dict[str, Any]]:
        """
        Execute tool calls from LLM responses.

        Returns:
            List of tool result messages ready for conversation history
        """
        tool_messages = []

        for tool_call in tool_calls:
            if hasattr(tool_call, "function"):
                tool_name = tool_call.function.name
                tool_id = tool_call.id
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
            else:
                tool_name = tool_call.name
                tool_id = tool_call.id
                try:
                    arguments = json.loads(tool_call.arguments)
                except json.JSONDecodeError:
                    arguments = {}

            result: ToolResult = await self.execute(tool_name, arguments)

            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result.to_display_string(),
                }
            )

        return tool_messages
