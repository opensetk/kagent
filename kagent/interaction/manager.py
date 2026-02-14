from typing import Dict, Any, List, Optional, Callable
import json
import os
from datetime import datetime
from pathlib import Path
import asyncio
from dataclasses import dataclass, field

from kagent.core import Agent, AgentRuntime, ContextManager
from kagent.interaction.hook import HookDispatcher, HookResult, HookAction


@dataclass
class HandleResult:
    message: str
    action: HookAction = HookAction.NONE
    action_data: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    @classmethod
    def from_hook_result(cls, hook_result: HookResult) -> "HandleResult":
        return cls(
            message=hook_result.message,
            action=hook_result.action,
            action_data=hook_result.action_data,
        )

    @classmethod
    def response(cls, message: str) -> "HandleResult":
        return cls(message=message)


class InteractionManager:
    """
    Interaction Layer that sits between Channels and the Agent.
    Handles multi-session management, history persistence, and hook dispatching.

    Core Principles:
    - AgentRuntime: Pure data (session state) - one per session
    - ContextManager: Operations on runtime - shared by all sessions
    - InteractionManager: Manages sessions but does not track "current" session
    - Each request explicitly provides the session_id and runtime
    """

    def __init__(self, sessions_dir: str = ".agent/sessions"):
        self.sessions_dir = sessions_dir
        self.available_sessions: Dict[str, AgentRuntime] = {}
        self.agent: Optional[Agent] = None
        self._load_all_sessions()
        self.hook_dispatcher = HookDispatcher()
        self._register_hooks()

    def _load_all_sessions(self):
        """Load all available sessions from disk."""
        sessions_path = Path(self.sessions_dir)
        if not sessions_path.exists():
            sessions_path.mkdir(parents=True, exist_ok=True)
            return

        for session_file in sessions_path.glob("*.json"):
            session_id = session_file.stem
            try:
                runtime = AgentRuntime.load_from_file(session_id, self.sessions_dir)
                if runtime:
                    self.available_sessions[session_id] = runtime
            except Exception as e:
                print(f"Failed to load session {session_id}: {e}")

    def _register_hooks(self):
        """Register interaction-level hooks."""
        self.hook_dispatcher.register("/clear", self.hook_clear_session)
        self.hook_dispatcher.register("/compress", self.hook_compress_session)
        self.hook_dispatcher.register("/save", self.hook_save_session)
        self.hook_dispatcher.register("/history", self.hook_show_history)
        self.hook_dispatcher.register("/tools", self.hook_list_tools)
        self.hook_dispatcher.register("/new", self.hook_new_session)
        self.hook_dispatcher.register("/switch", self.hook_switch_session)
        self.hook_dispatcher.register("/list", self.hook_list_sessions)
        self.hook_dispatcher.register("/delete", self.hook_delete_session)
        self.hook_dispatcher.register("/rename", self.hook_rename_session)
        self.hook_dispatcher.register("/help", self.hook_help)

    def set_agent(self, agent: Agent):
        """Set the agent instance."""
        self.agent = agent

    async def handle_request(
        self,
        text: str,
        session_id: str,
    ) -> HandleResult:
        """
        The main entry point for any channel.
        Processes the text for a specific session and returns the response.
        """
        if self.agent is None:
            return HandleResult.response("Error: Agent not set. Please call set_agent() first.")

        runtime = self._get_or_create_runtime(session_id)

        hook_result = await self.hook_dispatcher.dispatch(text, runtime)
        if hook_result is not None:
            self._save_runtime(runtime)
            return HandleResult.from_hook_result(hook_result)

        try:
            response = await self.agent.chat(
                runtime=runtime,
                user_input=text,
            )
            self._save_runtime(runtime)
            return HandleResult.response(response)
        except Exception as e:
            return HandleResult.response(f"Agent error: {str(e)}")

    def _get_or_create_runtime(self, session_id: str) -> AgentRuntime:
        """Get existing runtime or create new one for the session."""
        if session_id in self.available_sessions:
            return self.available_sessions[session_id]

        # Create new session
        runtime = self.agent.new_session(session_id)
        self.available_sessions[session_id] = runtime
        return runtime

    def _save_runtime(self, runtime: AgentRuntime):
        """Save runtime to file."""
        try:
            runtime.save_to_file(self.sessions_dir)
        except Exception as e:
            print(f"Failed to save session {runtime.session_id}: {e}")

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # ==================== Hook Handlers ====================

    async def hook_new_session(self, *args, **kwargs) -> HookResult:
        """Create a new session."""
        runtime = kwargs.get("runtime")
        session_name = args[0] if args else None

        if session_name:
            session_id = session_name
        else:
            session_id = self._generate_session_id()

        if session_id in self.available_sessions:
            return HookResult.error(f"❌ Session '{session_id}' already exists.")

        if runtime:
            self._save_runtime(runtime)

        new_runtime = self.agent.new_session(session_id)
        self.available_sessions[session_id] = new_runtime
        self._save_runtime(new_runtime)

        return HookResult.switch_session(
            f"✅ New session created: {session_id}",
            session_id
        )

    async def hook_switch_session(self, *args, **kwargs) -> HookResult:
        """Switch to an existing session."""
        runtime = kwargs.get("runtime")

        if not args:
            return HookResult.error("Usage: /switch <session_id>")

        session_id = args[0]

        if session_id not in self.available_sessions:
            available = ", ".join(self.available_sessions.keys())
            return HookResult.error(f"❌ Session '{session_id}' not found. Available: {available}")

        if runtime:
            self._save_runtime(runtime)

        return HookResult.switch_session(
            f"✅ Switched to session: {session_id}",
            session_id
        )

    async def hook_list_sessions(self, *args, **kwargs) -> HookResult:
        """List all sessions."""
        if not self.available_sessions:
            return HookResult.ok("No sessions available. Use /new to create one.")

        lines = ["📋 Available Sessions:"]
        for idx, (sid, rt) in enumerate(self.available_sessions.items(), 1):
            created = rt.created_at[:19] if rt.created_at else "Unknown"
            lines.append(f"  {idx}. {sid} (created: {created})")

        return HookResult.ok("\n".join(lines))

    async def hook_delete_session(self, *args, **kwargs) -> HookResult:
        """Delete a session."""
        runtime = kwargs.get("runtime")
        current_session_id = runtime.session_id if runtime else None

        if not args:
            return HookResult.error("Usage: /delete <session_id>")

        session_id = args[0]

        if session_id not in self.available_sessions:
            return HookResult.error(f"❌ Session '{session_id}' not found.")

        del self.available_sessions[session_id]

        session_file = Path(self.sessions_dir) / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()

        if session_id == current_session_id:
            remaining = list(self.available_sessions.keys())
            new_session = remaining[0] if remaining else None
            return HookResult.refresh_sessions(
                f"✅ Session '{session_id}' deleted. Current session was deleted.",
                new_session_id=new_session
            )

        return HookResult.ok(f"✅ Session '{session_id}' deleted.")

    async def hook_rename_session(self, *args, **kwargs) -> HookResult:
        """Rename a session."""
        runtime = kwargs.get("runtime")
        current_session_id = runtime.session_id if runtime else None

        if len(args) < 2:
            return HookResult.error("Usage: /rename <old_name> <new_name>")

        old_name, new_name = args[0], args[1]

        if old_name not in self.available_sessions:
            return HookResult.error(f"❌ Session '{old_name}' not found.")

        if new_name in self.available_sessions:
            return HookResult.error(f"❌ Session '{new_name}' already exists.")

        rt = self.available_sessions[old_name]
        rt.session_id = new_name

        del self.available_sessions[old_name]
        self.available_sessions[new_name] = rt

        old_file = Path(self.sessions_dir) / f"{old_name}.json"
        if old_file.exists():
            old_file.unlink()
        self._save_runtime(rt)

        if old_name == current_session_id:
            return HookResult.switch_session(
                f"✅ Session renamed: {old_name} -> {new_name}",
                new_name
            )

        return HookResult.ok(f"✅ Session renamed: {old_name} -> {new_name}")

    async def hook_clear_session(self, *args, **kwargs) -> HookResult:
        """Clear current session history."""
        runtime = kwargs.get("runtime")
        if not runtime:
            return HookResult.error("❌ No active session.")

        runtime.conversation_history.clear()
        return HookResult.ok("✅ Session history cleared.")

    async def hook_compress_session(self, *args, **kwargs) -> HookResult:
        """Compress current session context."""
        runtime = kwargs.get("runtime")
        if not runtime:
            return HookResult.error("❌ No active session.")

        if self.agent and self.agent.context_manager:
            result = await self.agent.context_manager.compress_context(runtime)
            return HookResult.ok(f"✅ {result}")
        return HookResult.error("❌ Context manager not available.")

    async def hook_save_session(self, *args, **kwargs) -> HookResult:
        """Save current session to disk."""
        runtime = kwargs.get("runtime")
        if not runtime:
            return HookResult.error("❌ No active session.")

        try:
            file_path = runtime.save_to_file(self.sessions_dir)
            return HookResult.ok(f"✅ Session saved to: {file_path}")
        except Exception as e:
            return HookResult.error(f"❌ Failed to save session: {e}")

    async def hook_show_history(self, *args, **kwargs) -> HookResult:
        """Show current session history."""
        runtime = kwargs.get("runtime")
        if not runtime:
            return HookResult.error("❌ No active session.")

        if not runtime.conversation_history:
            return HookResult.ok("📭 No messages in history.")

        lines = [f"📜 Session History ({len(runtime.conversation_history)} messages):"]
        for idx, msg in enumerate(runtime.conversation_history, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if len(content) > 100:
                content = content[:100] + "..."
            lines.append(f"  {idx}. [{role}] {content}")

        return HookResult.ok("\n".join(lines))

    async def hook_list_tools(self, *args, **kwargs) -> HookResult:
        """List enabled tools for the current runtime."""
        runtime = kwargs.get("runtime")
        if not runtime:
            return HookResult.error("❌ No active session.")

        if not self.agent or not self.agent.tool_manager:
            return HookResult.error("❌ Tool manager not available.")

        enabled_tools = runtime.enabled_tools

        if not enabled_tools:
            tools = self.agent.tool_manager.get_all_tools()
            lines = [f"🔧 All Available Tools ({len(tools)}) - none specifically enabled:"]
            for tool in tools:
                name = tool.get("function", {}).get("name", "unknown")
                desc = tool.get("function", {}).get("description", "No description")
                lines.append(f"  • {name}: {desc}")
            return HookResult.ok("\n".join(lines))

        lines = [f"🔧 Enabled Tools ({len(enabled_tools)}) for session '{runtime.session_id}':"]
        for tool_name in enabled_tools:
            tool = self.agent.tool_manager.get_tool(tool_name)
            if tool:
                desc = tool.description if hasattr(tool, 'description') else "No description"
                lines.append(f"  ✅ {tool_name}: {desc}")
            else:
                lines.append(f"  ⚠️  {tool_name}: Tool not found")

        return HookResult.ok("\n".join(lines))

    async def hook_help(self, *args, **kwargs) -> HookResult:
        """Show help information."""
        help_text = """
🤖 Available Commands:

Session Management:
  /new [name]        - Create a new session
  /switch <name>     - Switch to another session
  /list              - List all sessions
  /delete <name>     - Delete a session
  /rename <old> <new> - Rename a session

Session Operations:
  /clear             - Clear current session history
  /compress          - Compress conversation context
  /save              - Save session to disk
  /history           - Show session history

Tools & Info:
  /tools             - List available tools
  /help              - Show this help message

Other:
  exit, quit         - Exit the shell
        """
        return HookResult.ok(help_text)


class ChannelAdapter:
    """
    Adapter to connect any Channel with the InteractionManager.
    Provides a unified interface for channel-to-manager communication.
    """

    def __init__(self, manager: InteractionManager):
        self.manager = manager

    async def handle_message(self, text: str, session_id: str) -> HandleResult:
        """
        Handle incoming message from any channel.
        This is the unified entry point for all channels.
        """
        return await self.manager.handle_request(text, session_id)
