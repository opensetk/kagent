# Tool Call Display in Channels

This document describes how tool execution is displayed across different channels in kAgent.

## Overview

By default, kAgent displays tool execution details (tool name, arguments, and results) to provide transparency about what the agent is doing. However, different channels may have different display requirements.

## Channel Behavior

| Channel | Displays Tool Calls | Implementation |
|---------|-------------------|----------------|
| `ShellChannel` | ✅ Yes | Inherits from `BaseChannel`, prints to console |
| `TUIChannel` | ✅ Yes | Inherits from `BaseChannel`, prints to console |
| `LarkChannel` | ❌ No | Override with `pass` (silent) |
| `BaseChannel` | ✅ Yes | Default implementation prints to console |

## How It Works

### 1. BaseChannel (Default Behavior)

```python
class BaseChannel(ABC):
    def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
        """Default: Print tool execution to console"""
        print(f"\n[Tool: {tool_name}]")
        print(f"Arguments: {json.dumps(arguments, ensure_ascii=False)}")
        if result.success:
            print(f"Result: {result.result}")
        else:
            print(f"Error: {result.error}")
```

### 2. LarkChannel (Silent)

```python
class LarkChannel(BaseChannel):
    def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
        """Override: Do nothing for Lark channel"""
        pass  # Lark channel doesn't display tool calls
```

### 3. Data Flow

```
User Input
    ↓
Channel.message_handler
    ↓
InteractionManager.handle_request(on_tool_call=channel.on_tool_call)
    ↓
AgentLoop.chat(on_tool_call=on_tool_call)
    ↓
ToolManager.execute_tool_calls(on_tool_executed=on_tool_call)
    ↓
[Tool: xxx]  ← Displayed in console (except LarkChannel)
```

## Customizing Tool Display

### For New Channels

When creating a new channel, you can customize tool display behavior:

```python
class MyCustomChannel(BaseChannel):
    def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
        """Custom tool call display"""
        # Option 1: Inherit default behavior (prints to console)
        super().on_tool_call(tool_name, arguments, result)
        
        # Option 2: Custom display
        print(f"🔧 Executing {tool_name}...")
        
        # Option 3: Silent (like LarkChannel)
        pass
```

### Accessing Tool Result Details

The `result` parameter is a `ToolResult` object:

```python
def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
    if isinstance(result, ToolResult):
        print(f"Tool: {result.tool_name}")
        print(f"Success: {result.success}")
        print(f"Result: {result.result}")
        print(f"Error: {result.error}")
```

## Example Output

### ShellChannel

```
[You]: List files in current directory

[Tool: bash]
Arguments: {"command": "ls -la"}
Result: total 32
drwxr-xr-x  6 user staff  192 Jan 10 10:00 .
drwxr-xr-x  3 user staff   96 Jan 10 09:00 ..
-rw-r--r--  1 user staff  123 Jan 10 10:00 file.txt

[Agent]: I found 1 file: file.txt
```

### LarkChannel

LarkChannel silently executes tools without console output. Users only see the final response in Lark.

## Disabling Tool Display for a Channel

To suppress tool call display for any channel, override `on_tool_call` with `pass`:

```python
class SilentChannel(BaseChannel):
    def on_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Any) -> None:
        pass  # Silent execution
```
