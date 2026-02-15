"""
Message events for agent communication.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class MessageType(Enum):
    """Types of messages in the agent conversation."""
    USER_INPUT = "user_input"
    ASSISTANT_THINKING = "assistant_thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ASSISTANT_RESPONSE = "assistant_response"
    ERROR = "error"


@dataclass
class MessageEvent:
    """
    A message event in the agent conversation.
    
    Used to notify channels about various stages of agent processing.
    """
    type: MessageType
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def user_input(cls, content: str) -> "MessageEvent":
        """Create a user input event."""
        return cls(type=MessageType.USER_INPUT, content=content)
    
    @classmethod
    def assistant_thinking(cls, content: str) -> "MessageEvent":
        """Create an assistant thinking event (content before tool calls)."""
        return cls(type=MessageType.ASSISTANT_THINKING, content=content)
    
    @classmethod
    def tool_call(
        cls, 
        tool_name: str, 
        arguments: Dict[str, Any],
        tool_call_id: Optional[str] = None
    ) -> "MessageEvent":
        """Create a tool call event."""
        return cls(
            type=MessageType.TOOL_CALL,
            content=tool_name,
            metadata={
                "arguments": arguments,
                "tool_call_id": tool_call_id,
            }
        )
    
    @classmethod
    def tool_result(
        cls,
        tool_name: str,
        result: Any,
        success: bool = True,
        error: Optional[str] = None,
        tool_call_id: Optional[str] = None
    ) -> "MessageEvent":
        """Create a tool result event."""
        return cls(
            type=MessageType.TOOL_RESULT,
            content=tool_name,
            metadata={
                "result": result,
                "success": success,
                "error": error,
                "tool_call_id": tool_call_id,
            }
        )
    
    @classmethod
    def assistant_response(cls, content: str) -> "MessageEvent":
        """Create an assistant response event (final response)."""
        return cls(type=MessageType.ASSISTANT_RESPONSE, content=content)
    
    @classmethod
    def error(cls, message: str, details: Optional[str] = None) -> "MessageEvent":
        """Create an error event."""
        return cls(
            type=MessageType.ERROR, 
            content=message,
            metadata={"details": details} if details else {}
        )
