import inspect
from typing import Dict, Any, Callable, Optional, Awaitable


class HookDispatcher:
    """Handles hook commands (e.g. /clear) and dispatches them to appropriate handlers."""

    def __init__(self):
        self.hooks: Dict[str, Callable[..., Any]] = {}

    def register(self, hook_name: str, handler: Callable[..., Any]):
        """Register a hook handler."""
        self.hooks[hook_name.lower()] = handler

    async def dispatch(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Check if text is a hook and dispatch it.
        Returns the result string if it was a hook, None otherwise.
        """
        text = text.strip()
        if not text.startswith("/"):
            return None

        parts = text.split()
        hook_name = parts[0].lower()
        args = parts[1:]

        if hook_name not in self.hooks:
            supported = ", ".join(self.hooks.keys())
            return f"Unknown hook: {hook_name}. Supported: {supported}"

        handler = self.hooks[hook_name]

        try:
            # Prepare arguments based on handler signature
            sig = inspect.signature(handler)
            params = sig.parameters

            kwargs = {}
            if "context" in params:
                kwargs["context"] = context

            # Check if handler accepts *args
            has_var_positional = any(
                p.kind == inspect.Parameter.VAR_POSITIONAL for p in params.values()
            )

            # Handle both sync and async handlers
            if inspect.iscoroutinefunction(handler):
                if has_var_positional:
                    result = await handler(*args, **kwargs)
                elif args and "filename" in params:
                    result = await handler(args[0], **kwargs)
                else:
                    result = await handler(**kwargs)
            else:
                if has_var_positional:
                    result = handler(*args, **kwargs)
                elif args and "filename" in params:
                    result = handler(args[0], **kwargs)
                else:
                    result = handler(**kwargs)

            return str(result)
        except Exception as e:
            return f"Error executing hook {hook_name}: {str(e)}"
