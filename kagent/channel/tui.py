import asyncio
from typing import Optional, Callable, Awaitable, Any, Dict
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog
from textual.containers import Vertical
from kagent.channel.base import BaseChannel
from kagent.core.events import MessageEvent, MessageType
from kagent.interaction.hook import HookAction


class TUIApp(App):
    """A Textual app for the Agent TUI."""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    #log {
        height: 1fr;
        border: solid $accent;
        background: $surface;
        padding: 1;
    }
    
    Input {
        dock: bottom;
        margin: 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear Log"),
    ]

    def __init__(
        self, 
        message_handler: Optional[Callable[[str, str], Awaitable[Any]]], 
        session_id: str, 
        channel: "TUIChannel",
        interaction_manager=None
    ):
        super().__init__()
        self.message_handler = message_handler
        self.session_id = session_id
        self.channel = channel
        self.interaction_manager = interaction_manager

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="log", highlight=True, markup=True)
        yield Input(placeholder="Type your message here... (Press Enter to send)", id="input")
        yield Footer()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value.strip()
        if not user_text:
            return

        input_widget = self.query_one("#input", Input)
        log_widget = self.query_one("#log", RichLog)

        log_widget.write(f"[bold blue]You:[/bold blue] {user_text}")
        input_widget.value = ""

        if user_text.lower() in ["exit", "quit"]:
            self.exit()
            return

        try:
            log_widget.write("[italic gray]Thinking...[/italic gray]")
            
            if self.interaction_manager:
                result = await self.interaction_manager.handle_request(
                    user_text, 
                    self.session_id,
                    on_message=self.channel.on_message
                )
            elif self.message_handler:
                result = await self.message_handler(user_text, self.session_id)
            else:
                log_widget.write("[bold red]Error:[/bold red] No message handler configured.")
                return
            
            response = str(result)
            log_widget.write(f"[bold green]Agent:[/bold green] {response}")
            self._handle_action(result)
        except Exception as e:
            log_widget.write(f"[bold red]Error:[/bold red] {str(e)}")

    def _handle_action(self, result) -> None:
        """Handle action from HandleResult."""
        action = getattr(result, 'action', None)
        action_data = getattr(result, 'action_data', {})

        if action == HookAction.SWITCH_SESSION:
            new_session_id = action_data.get("session_id")
            if new_session_id:
                self.session_id = new_session_id
                self.channel.session_id = new_session_id
        elif action == HookAction.REFRESH_SESSIONS:
            new_session_id = action_data.get("new_session_id")
            if new_session_id:
                self.session_id = new_session_id
                self.channel.session_id = new_session_id

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()


class TUIChannel(BaseChannel):
    """
    Terminal User Interface (TUI) Channel using Textual.
    Provides a more sophisticated terminal experience than ShellChannel.
    """
    def __init__(self, session_id: str = "tui-user", show_tool_calls: bool = True):
        super().__init__(show_tool_calls=show_tool_calls)
        self.session_id = session_id
        self.app: Optional[TUIApp] = None
        self.interaction_manager = None

    async def _display_tool_call(self, tool_name: str, arguments: Dict[str, Any], tool_call_id: Optional[str] = None) -> None:
        """Display tool call in TUI log."""
        if self.app:
            import json
            log_widget = self.app.query_one("#log", RichLog)
            log_widget.write(f"[bold yellow]🔧 Tool: {tool_name}[/bold yellow]")
            log_widget.write(f"[dim]Arguments: {json.dumps(arguments, ensure_ascii=False)}[/dim]")

    async def _display_tool_result(self, tool_name: str, result: Any, success: bool, error: Optional[str] = None) -> None:
        """Display tool result in TUI log."""
        if self.app:
            log_widget = self.app.query_one("#log", RichLog)
            if success:
                result_str = str(result)
                display = result_str[:200] + "..." if len(result_str) > 200 else result_str
                log_widget.write(f"[dim green]Result: {display}[/dim green]")
            else:
                log_widget.write(f"[dim red]Error: {error}[/dim red]")

    async def _display_response(self, content: str) -> None:
        """Display final response in TUI log."""
        if self.app:
            log_widget = self.app.query_one("#log", RichLog)
            log_widget.write(f"[bold green]Agent:[/bold green] {content}")

    async def send_message(self, target_id: str, content: str, **kwargs):
        if self.app:
            self.app.query_one("#log", RichLog).write(f"[bold green]Agent:[/bold green] {content}")

    def start(self):
        """Start the TUI application."""
        print(f"--- Starting TUI Channel (Session: {self.session_id}) ---")
        self.app = TUIApp(
            self.message_handler, 
            self.session_id, 
            self,
            self.interaction_manager
        )
        self.app.run()
    
    def set_interaction_manager(self, interaction_manager):
        """Set the interaction manager for the TUI channel."""
        self.interaction_manager = interaction_manager

if __name__ == "__main__":
    async def mock_handler(text, sid):
        await asyncio.sleep(0.5)
        return f"TUI Echo: {text}"

    channel = TUIChannel()
    channel.set_message_handler(mock_handler)
    channel.start()
