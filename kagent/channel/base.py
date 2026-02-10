from abc import ABC, abstractmethod
from typing import Any, Callable, Awaitable, Optional


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

    @abstractmethod
    async def send_message(self, target_id: str, content: str, **kwargs) -> Any:
        """Send a message to a specific target (user or group)."""
        pass

    @abstractmethod
    def start(self):
        """Start the channel client (e.g., connect to WebSocket)."""
        pass
