from typing import Dict, Any, List, Optional
import json
import os
import time
from datetime import datetime
from pathlib import Path
from kagent.core.agent import AgentLoop
from kagent.interaction.hook import HookDispatcher


class InteractionManager:
    """
    Interaction Layer that sits between Channels and the Agent.
    Handles multi-session management, history persistence, and hook dispatching.

    Note: Tool management is handled by AgentLoop and core/tool.py.
    This class focuses on session management and interaction hooks.
    """

    def __init__(self, agent: AgentLoop, sessions_dir: str = "sessions"):
        self.agent = agent
        self.hook_dispatcher = HookDispatcher()
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(exist_ok=True)

        # Current active session ID
        self.current_session_id: Optional[str] = None

        # Session metadata storage: {session_id: metadata_dict}
        # metadata includes: name, created_at, last_active
        self.session_metadata: Dict[str, Dict[str, Any]] = {}

        # Load existing sessions from disk
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
            history = []

            # If this is the current session, get history from agent
            if session_id == self.current_session_id:
                history = self.agent.context_manager.get_history()

            session_data = {
                "session_id": session_id,
                "name": metadata.get("name", session_id),
                "created_at": metadata.get("created_at", datetime.now().isoformat()),
                "last_active": datetime.now().isoformat(),
                "messages": history,
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
        Load session from disk into agent context.

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

            # Update metadata
            self.session_metadata[session_id] = {
                "name": data.get("name", session_id),
                "created_at": data.get("created_at", datetime.now().isoformat()),
                "last_active": data.get("last_active", ""),
            }

            # Load messages into agent context
            messages = data.get("messages", [])
            self.agent.context_manager.clear_history()
            for msg in messages:
                self.agent.context_manager.add_message(
                    msg.get("role", "user"),
                    msg.get("content", ""),
                    **{k: v for k, v in msg.items() if k not in ["role", "content"]},
                )

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

    async def handle_request(self, text: str, session_id: str) -> str:
        """
        The main entry point for any channel.
        Processes the text for a specific session and returns the response.
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

        # 1. Dispatch hooks with session context
        context: Dict[str, Any] = {"session_id": session_id}
        hook_result = await self.hook_dispatcher.dispatch(text, context=context)
        if hook_result is not None:
            return hook_result

        # 2. Load session history into agent (already loaded in current session)
        # We don't need to reload as it's already in agent context

        # 3. Process with Agent
        try:
            response = await self.agent.chat(text)
            # 4. Auto-save after each message
            self._save_session(self.current_session_id)
            return response
        except Exception as e:
            return f"Agent error: {str(e)}"

    # Hook Handlers

    async def hook_clear_session(self, context: Dict[str, Any]) -> str:
        session_id = context.get("session_id")
        if session_id:
            self.agent.context_manager.clear_history()
            self._save_session(session_id)
            return "Session history cleared."
        return "No active session."

    async def hook_compress_session(self, context: Dict[str, Any]) -> str:
        session_id = context.get("session_id")
        if not session_id:
            return "No active session."

        history = self.agent.context_manager.get_history()
        if not history:
            return "History is empty, nothing to compress."

        from kagent.llm.client import LLMClient

        result = await self.agent.context_manager.compress_history(LLMClient.from_env())
        # Save compressed history
        self._save_session(session_id)
        return result

    def hook_save_session(
        self, filename: str = "history.json", context: Optional[Dict[str, Any]] = None
    ) -> str:
        if context is None:
            context = {}
        session_id = context.get("session_id")
        if not session_id:
            return "Error: No session ID provided."

        history = self.agent.context_manager.get_history()
        try:
            # Ensure directory exists if filename contains path
            dir_path = os.path.dirname(os.path.abspath(filename))
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            return f"History for session {session_id} saved to {filename}."
        except Exception as e:
            return f"Failed to save history: {str(e)}"

    def hook_show_history(self, context: Dict[str, Any]) -> str:
        session_id = context.get("session_id")
        if not session_id:
            return "Error: No session ID provided."

        history = self.agent.context_manager.get_history()
        if not history:
            return "No history in this session."

        summary = [
            f"{m.get('role', 'unknown').upper()}: {m.get('content', '')[:50]}..."
            for m in history
        ]
        return "Recent History:\n" + "\n".join(summary)

    def hook_list_tools(self, context: Optional[Dict[str, Any]] = None) -> str:
        """List all available tools through the agent's tool manager."""
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

    # New Session Management Hooks

    def hook_new_session(self, *args, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Create a new session.
        Usage: /new [name]
        If name is not provided, generates one automatically.
        """
        # Generate session ID
        session_id = self._generate_session_id()

        # Get session name from args or generate one
        if args:
            base_name = args[0]
            # Check for name conflicts and resolve
            name = self._resolve_duplicate_name(base_name)
        else:
            name = f"session-{session_id}"

        # Create session metadata
        self.session_metadata[session_id] = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "last_active": "",
        }

        # Create empty session file
        self._save_session(session_id)

        # Switch to new session
        self.current_session_id = session_id
        self.agent.context_manager.clear_history()

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
        self, *args, context: Optional[Dict[str, Any]] = None
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

        # Save current session before switching
        if self.current_session_id:
            self._save_session(self.current_session_id)

        # Load new session
        if self._load_session(session_id):
            self.current_session_id = session_id
            metadata = self.session_metadata.get(session_id, {})
            return f"Switched to session: {metadata.get('name', session_id)}"
        else:
            return f"Failed to load session: {target}"

    def hook_list_sessions(self, context: Optional[Dict[str, Any]] = None) -> str:
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

        for session_id, metadata in sorted(
            self.session_metadata.items(),
            key=lambda x: x[1].get("last_active", ""),
            reverse=True,
        ):
            name = metadata.get("name", session_id)
            # Mark current session with bold
            if session_id == self.current_session_id:
                name = f"**{name}** ✓"

            created = metadata.get("created_at", "Unknown")[:16].replace("T", " ")
            last_active = metadata.get("last_active", "Never")
            if last_active:
                last_active = last_active[:16].replace("T", " ")
            else:
                last_active = "Never"

            # Get message count from file
            msg_count = 0
            session_file = self.sessions_dir / f"{session_id}.json"
            if session_file.exists():
                try:
                    with open(session_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        msg_count = len(data.get("messages", []))
                except:
                    pass

            lines.append(f"| {name} | {msg_count} | {created} | {last_active} |")

        lines.append("")
        lines.append("*✓ indicates the current active session*")
        print("\n".join(lines))
        return "\n".join(lines)

    def hook_delete_session(
        self, *args, context: Optional[Dict[str, Any]] = None
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

        # Don't allow deleting current session
        if session_id == self.current_session_id:
            return "Cannot delete the current active session. Switch to another session first."

        # Delete metadata
        metadata = self.session_metadata.pop(session_id, {})
        name = metadata.get("name", session_id)

        # Delete file
        session_file = self.sessions_dir / f"{session_id}.json"
        try:
            if session_file.exists():
                session_file.unlink()
            return f"Deleted session: {name}"
        except Exception as e:
            return f"Error deleting session: {e}"

    def hook_rename_session(
        self, *args, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Rename current or specified session.
        Usage: /rename <new_name> or /rename <session> <new_name>
        """
        if len(args) == 1:
            # Rename current session
            if not self.current_session_id:
                return "No active session to rename."
            session_id = self.current_session_id
            new_name = args[0]
        elif len(args) >= 2:
            # Rename specified session
            target = args[0]
            session_id = self._resolve_session_name(target)
            if not session_id:
                return f"Session '{target}' not found."
            new_name = args[1]
        else:
            return "Usage: /rename <new_name> or /rename <session> <new_name>"

        # Check for conflicts
        old_name = self.session_metadata[session_id].get("name", session_id)
        resolved_name = self._resolve_duplicate_name(new_name)

        # Update metadata
        self.session_metadata[session_id]["name"] = resolved_name

        # Save to disk
        self._save_session(session_id)

        if resolved_name != new_name:
            return f"Renamed '{old_name}' to '{resolved_name}' (name conflict resolved)"
        return f"Renamed '{old_name}' to '{resolved_name}'"
