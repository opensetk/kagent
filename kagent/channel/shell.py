import asyncio
import sys
from typing import Dict, Any, Optional, Callable, Awaitable
from kagent.channel.base import BaseChannel
from kagent.interaction.hook import HookAction


class ShellChannel(BaseChannel):
    """
    Interactive Shell Channel for local testing.
    Allows talking to the agent via terminal input/output.
    Integrates with InteractionManager for session management.
    """

    def __init__(
        self, 
        session_id: str = "local-shell", 
        interaction_manager=None,
        show_tool_calls: bool = True
    ):
        super().__init__(show_tool_calls=show_tool_calls)
        self.session_id = session_id
        self.is_running = False
        self.interaction_manager = interaction_manager
        self._message_handler: Optional[Callable[[str, str], Awaitable[Any]]] = None

    def set_message_handler(self, handler: Callable[[str, str], Awaitable[str]]):
        """
        Set the handler that will process incoming messages.
        The handler should accept (text, session_id) and return a response string.
        """
        self._message_handler = handler
        super().set_message_handler(handler)

    async def send_message(self, target_id: str, content: str, **kwargs):
        """Print the agent's response to the console."""
        print(f"\n🤖 Agent: {content}")

    def _print_welcome(self):
        """Print welcome message."""
        print("=" * 50)
        print("🤖 KAgent Shell")
        print("=" * 50)
        print(f"Session: {self.session_id}")
        print()
        print("Commands:")
        print("  /help    - Show available commands")
        print("  /new     - Create a new session")
        print("  /list    - List all sessions")
        print("  /switch  - Switch to another session")
        print("  exit     - Exit the shell")
        print()
        print("Type your message and press Enter to chat.")
        print("=" * 50)

    async def _loop(self):
        """Main interactive loop."""
        self._print_welcome()

        while self.is_running:
            try:
                loop = asyncio.get_event_loop()
                user_input = await loop.run_in_executor(
                    None, lambda: input(f"\n[{self.session_id}] You: ")
                )

                user_input = user_input.strip()
                
                if not user_input:
                    continue

                if user_input.lower() in ["exit", "quit", "q"]:
                    self.is_running = False
                    print("\n👋 Goodbye!")
                    break

                if self.interaction_manager:
                    result = await self.interaction_manager.handle_request(
                        user_input, 
                        self.session_id,
                        on_message=self.on_message
                    )
                    await self.send_message(self.session_id, str(result))
                    self._handle_action(result)
                elif self._message_handler:
                    result = await self._message_handler(user_input, self.session_id)
                    await self.send_message(self.session_id, str(result))
                    self._handle_action(result)
                else:
                    print("❌ Error: No message handler configured.")

            except EOFError:
                print("\n👋 Goodbye!")
                break
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error in shell loop: {e}")

    def _handle_action(self, result) -> None:
        """Handle action from HandleResult."""
        action = getattr(result, 'action', None)
        action_data = getattr(result, 'action_data', {})

        if action == HookAction.SWITCH_SESSION:
            new_session_id = action_data.get("session_id")
            if new_session_id:
                self.session_id = new_session_id
        elif action == HookAction.REFRESH_SESSIONS:
            new_session_id = action_data.get("new_session_id")
            if new_session_id:
                self.session_id = new_session_id
            elif not self.interaction_manager.available_sessions:
                print("⚠️  No sessions available. Use /new to create one.")

    def start(self):
        """Start the interactive loop."""
        self.is_running = True
        try:
            asyncio.run(self._loop())
        except KeyboardInterrupt:
            print("\n👋 Shell channel stopped by user.")

    async def start_async(self):
        """Start the interactive loop (async version)."""
        self.is_running = True
        await self._loop()

    async def run_with_manager(self, interaction_manager) -> None:
        """
        Run interactive mode with an InteractionManager.
        
        This is the recommended way to use ShellChannel with full
        session management capabilities.
        
        Args:
            interaction_manager: InteractionManager instance
        """
        self.interaction_manager = interaction_manager
        
        if self.session_id not in interaction_manager.available_sessions:
            result = await interaction_manager.handle_request(
                f"/new {self.session_id}", 
                self.session_id,
                on_message=self.on_message
            )
            self._handle_action(result)
        
        self.is_running = True
        await self._loop()
