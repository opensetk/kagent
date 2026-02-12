from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable, Optional, Dict


class BaseChannel(ABC):
    """
    Abstract Base Class for all communication channels (Lark, Slack, etc.)
    """

    def __init__(self):
        self.message_handler: Optional[Callable[[str, str], Awaitable[str]]] = None

    def set_message_handler(self, handler: Callable[[str, str], Awaitable[str]]):
        """
        Set the handler that will process incoming messages.
        The handler should accept (text, session_id) and return a response string.
        """
        self.message_handler = handler

    def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
        """
        Callback called when a tool is executed.
        Override this method in subclasses to display tool execution.
        Base implementation prints to console.
        
        Args:
            tool_name: Name of the tool that was executed
            arguments: Arguments passed to the tool
            result: ToolResult object containing success status and result/error
        """
        import json
        from kagent.core.tool import ToolResult
        
        print(f"\n[Tool: {tool_name}]")
        print(f"Arguments: {json.dumps(arguments, ensure_ascii=False)}")
        
        if isinstance(result, ToolResult):
            if result.success:
                result_str = str(result.result)
                display = result_str[:200] + "..." if len(result_str) > 200 else result_str
                print(f"Result: {display}")
            else:
                print(f"Error: {result.error}")
        else:
            print(f"Result: {result}")

    @abstractmethod
    async def send_message(self, target_id: str, content: str, **kwargs) -> Any:
        """Send a message to a specific target (user or group)."""
        pass

    @abstractmethod
    def start(self):
        """Start the channel client (e.g., connect to WebSocket)."""
        pass
