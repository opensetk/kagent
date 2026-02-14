import inspect
from dataclasses import dataclass, field
from typing import Dict, Any, Callable, Optional, Awaitable, List
from enum import Enum

from kagent.core import AgentRuntime


class HookAction(Enum):
    NONE = "none"
    SWITCH_SESSION = "switch_session"
    REFRESH_SESSIONS = "refresh_sessions"


@dataclass
class HookResult:
    message: str
    action: HookAction = HookAction.NONE
    action_data: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    @classmethod
    def ok(cls, message: str) -> "HookResult":
        return cls(message=message)

    @classmethod
    def error(cls, message: str) -> "HookResult":
        return cls(message=message)

    @classmethod
    def switch_session(cls, message: str, session_id: str) -> "HookResult":
        return cls(
            message=message,
            action=HookAction.SWITCH_SESSION,
            action_data={"session_id": session_id}
        )

    @classmethod
    def refresh_sessions(cls, message: str, new_session_id: Optional[str] = None) -> "HookResult":
        return cls(
            message=message,
            action=HookAction.REFRESH_SESSIONS,
            action_data={"new_session_id": new_session_id}
        )


class HookDispatcher:
    """Handles hook commands (e.g. /clear) and dispatches them to appropriate handlers."""

    def __init__(self):
        self.hooks: Dict[str, Callable[..., Any]] = {}

    def register(self, hook_name: str, handler: Callable[..., Any]):
        """Register a hook handler."""
        self.hooks[hook_name.lower()] = handler

    async def dispatch(
        self, text: str, runtime: AgentRuntime
    ) -> Optional[HookResult]:
        """
        Check if text is a hook and dispatch it.
        Returns HookResult if it was a hook, None otherwise.
        """
        text = text.strip()
        if not text.startswith("/"):
            return None

        parts = text.split()
        hook_name = parts[0].lower()
        args = parts[1:]

        if hook_name not in self.hooks:
            supported = ", ".join(self.hooks.keys())
            return HookResult.error(f"Unknown hook: {hook_name}. Supported: {supported}")

        handler = self.hooks[hook_name]

        try:
            if inspect.iscoroutinefunction(handler):
                result = await handler(*args, runtime=runtime)
            else:
                result = handler(*args, runtime=runtime)

            if isinstance(result, HookResult):
                return result
            return HookResult.ok(str(result))
        except Exception as e:
            return HookResult.error(f"Error executing hook {hook_name}: {str(e)}")
