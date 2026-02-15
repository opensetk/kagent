from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable, Optional, Dict
from kagent.core.events import MessageEvent, MessageType


class BaseChannel(ABC):
    """
    Abstract Base Class for all communication channels (Lark, Slack, etc.)
    """

    def __init__(self, show_tool_calls: bool = True):
        self.message_handler: Optional[Callable[[str, str], Awaitable[Any]]] = None
        self.show_tool_calls = show_tool_calls

    def set_message_handler(self, handler: Callable[[str, str], Awaitable[Any]]):
        """
        Set the handler that will process incoming messages.
        The handler should accept (text, session_id) and return a response.
        """
        self.message_handler = handler

    async def on_message(self, event: MessageEvent) -> None:
        """
        Handle message events from the agent.
        This is the unified callback for all message types.
        
        Args:
            event: MessageEvent containing type, content, and metadata
        """
        if event.type == MessageType.USER_INPUT:
            await self._display_user_input(event.content)
        elif event.type == MessageType.ASSISTANT_THINKING:
            await self._display_thinking(event.content)
        elif event.type == MessageType.TOOL_CALL:
            if self.show_tool_calls:
                await self._display_tool_call(
                    event.content,
                    event.metadata.get("arguments", {}),
                    event.metadata.get("tool_call_id")
                )
        elif event.type == MessageType.TOOL_RESULT:
            if self.show_tool_calls:
                await self._display_tool_result(
                    event.content,
                    event.metadata.get("result"),
                    event.metadata.get("success", True),
                    event.metadata.get("error")
                )
        elif event.type == MessageType.ASSISTANT_RESPONSE:
            await self._display_response(event.content)
        elif event.type == MessageType.ERROR:
            await self._display_error(event.content, event.metadata.get("details"))

    async def _display_user_input(self, content: str) -> None:
        """Display user input. Override in subclasses for custom formatting."""
        pass

    async def _display_thinking(self, content: str) -> None:
        """Display assistant thinking content. Override in subclasses."""
        pass

    async def _display_tool_call(self, tool_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None) -> None:
        """Display tool call. Base implementation prints to console."""
        import json
        print(f"\n[Tool: {tool_name}]")
        print(f"Arguments: {json.dumps(arguments, ensure_ascii=False)}")

    async def _display_tool_result(self, tool_name: str, result: Any, success: bool, error: Optional[str] = None) -> None:
        """Display tool result. Base implementation prints to console."""
        if success:
            result_str = str(result)
            display = result_str[:200] + "..." if len(result_str) > 200 else result_str
            print(f"Result: {display}")
        else:
            print(f"Error: {error}")

    async def _display_response(self, content: str) -> None:
        """Display final assistant response. Override in subclasses."""
        pass

    async def _display_error(self, message: str, details: Optional[str] = None) -> None:
        """Display error message."""
        print(f"❌ Error: {message}")
        if details:
            print(f"Details: {details}")

    @abstractmethod
    async def send_message(self, target_id: str, content: str, **kwargs) -> Any:
        """Send a message to a specific target (user or group)."""
        pass

    @abstractmethod
    def start(self):
        """Start the channel client (e.g., connect to WebSocket)."""
        pass
