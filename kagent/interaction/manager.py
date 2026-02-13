from typing import Dict, Any, List, Optional, Callable
import json
import os
from datetime import datetime
from pathlib import Path

from kagent.core.agent import AgentLoop
from kagent.core.context import AgentRuntime, ContextManager
from kagent.core.config import load_config
from kagent.interaction.hook import HookDispatcher


class InteractionManager:
    """
    Interaction Layer that sits between Channels and the Agent.
    Handles multi-session management, history persistence, and hook dispatching.

    Core Principles:
    - AgentRuntime: Pure data (session state) - one per session
    - ContextManager: Operations on runtime - one per AgentLoop
    - InteractionManager: Manages session switching by swapping runtimes
    
    Session Switching:
    - Each session has its own AgentRuntime
    - Switching sessions = swapping the runtime in ContextManager
    - ContextManager itself remains unchanged
    """

    def __init__(
        self,
        agent: AgentLoop,
        sessions_dir: str = "sessions",
        model: str = "gpt-4o",
    ):
        self.agent = agent
        self.model = model
        self.hook_dispatcher = HookDispatcher()
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(exist_ok=True)

        self.current_session_id: Optional[str] = None

        self.session_metadata: Dict[str, Dict[str, Any]] = {}

        self._runtimes: Dict[str, AgentRuntime] = {}

        self._load_all_sessions()

        self._register_hooks()

    def _load_all_sessions(self) -> None:
        """Load all existing session files from sessions directory."""
        if not self.sessions_dir.exists():
            return

        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    session_id = data.get("session_id")
                    if session_id:
                        self.session_metadata[session_id] = {
                            "name": data.get("name", session_id),
                            "created_at": data.get("created_at", ""),
                            "last_active": data.get("last_active", ""),
                        }
            except Exception as e:
                print(f"Warning: Failed to load session file {session_file}: {e}")

        # Find session with latest last_active
        latest_session = max(
            self.session_metadata.items(),
            key=lambda x: x[1].get("last_active", ""),
            default=(None, None),
        )
        session_id, metadata = latest_session
        if not session_id:
            return None

        if self._load_session(session_id):
            self.current_session_id = session_id
            name = metadata.get("name", session_id)
            print(f"Loaded latest session: {name}")
            return session_id
        return None

    def _save_session(self, session_id: str) -> bool:
        """
        Save session to disk.

        Args:
            session_id: Session identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            metadata = self.session_metadata.get(session_id, {})
            
            # Get runtime data from agent's context
            runtime_data = self.agent.context.runtime.to_dict()
            
            session_data = {
                "session_id": session_id,
                "name": metadata.get("name", session_id),
                "created_at": metadata.get("created_at", datetime.now().isoformat()),
                "last_active": datetime.now().isoformat(),
                "runtime": runtime_data,
            }

            session_file = self.sessions_dir / f"{session_id}.json"
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving session {session_id}: {e}")
            return False

    def _load_session(self, session_id: str) -> bool:
        """
        Load session from disk and switch to its runtime.

        Args:
            session_id: Session identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            session_file = self.sessions_dir / f"{session_id}.json"
            if not session_file.exists():
                return False

            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.session_metadata[session_id] = {
                "name": data.get("name", session_id),
                "created_at": data.get("created_at", datetime.now().isoformat()),
                "last_active": data.get("last_active", ""),
            }

            runtime_data = data.get("runtime", {})
            if runtime_data:
                runtime = AgentRuntime.from_dict(runtime_data)
                runtime.session_id = session_id
            else:
                config = load_config()
                runtime = AgentRuntime(
                    session_id=session_id,
                    work_dir=config.work_dir,
                    max_tokens=config.max_tokens,
                    ratio_of_compress=config.ratio_of_compress,
                    keep_last_n_messages=config.keep_last_n_messages,
                )
            
            self._runtimes[session_id] = runtime
            
            self.agent.context.update_runtime(runtime)

            return True
        except Exception as e:
            print(f"Error loading session {session_id}: {e}")
            return False

    def _generate_session_id(self) -> str:
        """Generate a unique session ID based on timestamp."""
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def _resolve_session_name(self, name: str) -> Optional[str]:
        """
        Resolve session name to session ID.

        Args:
            name: Session name or ID

        Returns:
            Session ID if found, None otherwise
        """
        # First check if it's already a session ID
        if name in self.session_metadata:
            return name

        # Search by name
        for session_id, metadata in self.session_metadata.items():
            if metadata.get("name") == name:
                return session_id

        return None

    def _register_hooks(self):
        """Register interaction-level hooks."""
        self.hook_dispatcher.register("/clear", self.hook_clear_session)
        self.hook_dispatcher.register("/compress", self.hook_compress_session)
        self.hook_dispatcher.register("/save", self.hook_save_session)
        self.hook_dispatcher.register("/history", self.hook_show_history)
        self.hook_dispatcher.register("/tools", self.hook_list_tools)

        # New session management hooks
        self.hook_dispatcher.register("/new", self.hook_new_session)
        self.hook_dispatcher.register("/switch", self.hook_switch_session)
        self.hook_dispatcher.register("/list", self.hook_list_sessions)
        self.hook_dispatcher.register("/delete", self.hook_delete_session)
        self.hook_dispatcher.register("/rename", self.hook_rename_session)

    async def handle_request(
        self, 
        text: str, 
        session_id: str,
        on_tool_call: Optional[Callable[[str, Dict[str, Any], Any], None]] = None
    ) -> str:
        """
        The main entry point for any channel.
        Processes the text for a specific session and returns the response.

        Args:
            text: User input text
            session_id: Session identifier
            on_tool_call: Optional callback for tool execution display
        """
        # Set current session if not set
        if self.current_session_id is None:
            self.current_session_id = session_id
            if session_id not in self.session_metadata:
                # Create new session if it doesn't exist
                self.session_metadata[session_id] = {
                    "name": session_id,
                    "created_at": datetime.now().isoformat(),
                    "last_active": "",
                }
                # Initialize runtime for new session
                self.agent.context.runtime.session_id = session_id

        # 1. Dispatch hooks with session context
        hook_result = await self.hook_dispatcher.dispatch(text, hook_context={"session_id": session_id})
        if hook_result is not None:
            return hook_result

        # 2. Process with Agent
        try:
            response = await self.agent.chat(text, on_tool_call=on_tool_call)
            # 3. Auto-save after each message
            self._save_session(self.current_session_id)
            return response
        except Exception as e:
            return f"Agent error: {str(e)}"

    # Hook Handlers

    async def hook_clear_session(self, hook_context: Dict[str, Any]) -> str:
        session_id = hook_context.get("session_id")
        if session_id:
            self.agent.context.clear_history()
            self._save_session(session_id)
            return "Session history cleared."
        return "No active session."

    async def hook_compress_session(self, hook_context: Dict[str, Any]) -> str:
        session_id = hook_context.get("session_id")
        if not session_id:
            return "No active session."

        history = self.agent.context.get_history()
        if not history:
            return "History is empty, nothing to compress."

        result = self.agent.context.compress_context()
        self._save_session(session_id)
        return result

    def hook_save_session(
        self, filename: str = "history.json", hook_context: Optional[Dict[str, Any]] = None
    ) -> str:
        if hook_context is None:
            hook_context = {}
        session_id = hook_context.get("session_id")
        if not session_id:
            return "Error: No session ID provided."

        history = self.agent.context.get_history()
        try:
            dir_path = os.path.dirname(os.path.abspath(filename))
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            return f"History for session {session_id} saved to {filename}."
        except Exception as e:
            return f"Failed to save history: {str(e)}"

    def hook_show_history(self, hook_context: Dict[str, Any]) -> str:
        session_id = hook_context.get("session_id")
        if not session_id:
            return "Error: No session ID provided."

        history = self.agent.context.get_history()
        if not history:
            return "No history in this session."

        summary = [
            f"{m.get('role', 'unknown').upper()}: {m.get('content', '')[:50]}..."
            for m in history
        ]
        return "Recent History:\n" + "\n".join(summary)

    def hook_list_tools(self, hook_context: Optional[Dict[str, Any]] = None) -> str:
        if not self.agent.tool_manager:
            return "No tools available."

        tools = self.agent.tool_manager.list_tools()
        if not tools:
            return "No tools available."

        lines = ["Available Tools:"]
        for tool in tools:
            lines.append(f"\n  • {tool.name}")
            lines.append(f"    {tool.description}")

        return "\n".join(lines)

    def hook_new_session(self, *args, hook_context: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a new session.
        Usage: /new [name]
        If name is not provided, generates one automatically.
        """
        session_id = self._generate_session_id()

        if args:
            base_name = args[0]
            name = self._resolve_duplicate_name(base_name)
        else:
            name = f"session-{session_id}"

        self.session_metadata[session_id] = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "last_active": "",
        }

        if self.current_session_id:
            self._save_session(self.current_session_id)

        config = load_config()
        
        # 继承当前 session 的 skills
        current_skills = self.agent.context.get_loaded_skills()
        
        runtime = AgentRuntime(
            session_id=session_id,
            work_dir=config.work_dir,
            max_tokens=config.max_tokens,
            ratio_of_compress=config.ratio_of_compress,
            keep_last_n_messages=config.keep_last_n_messages,
            loaded_skills=current_skills,  # 继承 skills
        )
        
        self._runtimes[session_id] = runtime
        self.agent.context.update_runtime(runtime)

        self.current_session_id = session_id

        self._save_session(session_id)

        return f"Created new session: {name} (ID: {session_id})"

    def _resolve_duplicate_name(self, base_name: str) -> str:
        """Resolve name conflicts by appending -1, -2, etc."""
        existing_names = {m.get("name") for m in self.session_metadata.values()}

        if base_name not in existing_names:
            return base_name

        # Find next available suffix
        counter = 1
        while f"{base_name}-{counter}" in existing_names:
            counter += 1

        return f"{base_name}-{counter}"

    def hook_switch_session(
        self, *args, hook_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Switch to a different session.
        Usage: /switch <name_or_id>
        """
        if not args:
            return "Usage: /switch <session_name_or_id>"

        target = args[0]
        session_id = self._resolve_session_name(target)

        if not session_id:
            return f"Session '{target}' not found. Use /list to see available sessions."

        if self.current_session_id:
            self._save_session(self.current_session_id)

        if self._load_session(session_id):
            self.current_session_id = session_id
            metadata = self.session_metadata.get(session_id, {})
            return f"Switched to session: {metadata.get('name', session_id)}"
        else:
            return f"Failed to load session: {target}"

    def hook_list_sessions(self, hook_context: Optional[Dict[str, Any]] = None) -> str:
        """
        List all sessions with metadata in Markdown table format.
        Shows: name, message count, creation time, last active time.
        """
        if not self.session_metadata:
            return "No sessions available. Create one with /new [name]"

        lines = ["**Available Sessions:**", ""]
        # Markdown table header
        lines.append("| Name | Messages | Created | Last Active |")
        lines.append("|------|----------|---------|-------------|")

        # Sort sessions by last_active (most recent first)
        sorted_sessions = sorted(
            self.session_metadata.items(),
            key=lambda x: x[1].get("last_active", ""),
            reverse=True,
        )

        for session_id, metadata in sorted_sessions:
            name = metadata.get("name", session_id)
            # Mark current session with asterisk
            if session_id == self.current_session_id:
                name = f"**{name}** *"

            created = metadata.get("created_at", "")[:10]  # Just the date part
            last_active = metadata.get("last_active", "")[:16]  # Date + time

            # Get message count from current context's runtime
            if session_id == self.current_session_id:
                msg_count = len(self.agent.context.get_history())
            else:
                # Load from file to get count
                try:
                    session_file = self.sessions_dir / f"{session_id}.json"
                    if session_file.exists():
                        with open(session_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            runtime_data = data.get("runtime", {})
                            msg_count = len(runtime_data.get("conversation_history", []))
                    else:
                        msg_count = 0
                except:
                    msg_count = 0

            lines.append(f"| {name} | {msg_count} | {created} | {last_active} |")

        lines.append("")
        lines.append("*Current session")

        return "\n".join(lines)

    def hook_delete_session(
        self, *args, hook_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Delete a session.
        Usage: /delete <name_or_id>
        """
        if not args:
            return "Usage: /delete <session_name_or_id>"

        target = args[0]
        session_id = self._resolve_session_name(target)

        if not session_id:
            return f"Session '{target}' not found."

        if session_id == self.current_session_id:
            return "Cannot delete the current active session. Switch to another session first."

        # Delete session file
        try:
            session_file = self.sessions_dir / f"{session_id}.json"
            if session_file.exists():
                session_file.unlink()
        except Exception as e:
            return f"Error deleting session file: {e}"

        # Remove from metadata
        metadata = self.session_metadata.pop(session_id, {})
        name = metadata.get("name", session_id)

        return f"Deleted session: {name}"

    def hook_rename_session(
        self, *args, hook_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Rename the current session.
        Usage: /rename <new_name>
        """
        if not args:
            return "Usage: /rename <new_name>"

        if not self.current_session_id:
            return "No active session to rename."

        new_name = args[0]
        
        # Check for conflicts
        resolved_name = self._resolve_duplicate_name(new_name)
        if resolved_name != new_name:
            return f"Name '{new_name}' already exists. Use '{resolved_name}' instead or choose a different name."

        # Update metadata
        if self.current_session_id in self.session_metadata:
            self.session_metadata[self.current_session_id]["name"] = new_name
            self._save_session(self.current_session_id)
            return f"Renamed session to: {new_name}"

        return "Failed to rename session."
