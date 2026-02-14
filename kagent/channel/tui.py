import asyncio
from typing import Optional, Callable, Awaitable, Any
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog
from textual.containers import Vertical
from kagent.channel.base import BaseChannel
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

    def __init__(self, message_handler: Optional[Callable[[str, str], Awaitable[Any]]], session_id: str, channel: "TUIChannel"):
        super().__init__()
        self.message_handler = message_handler
        self.session_id = session_id
        self.channel = channel

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

        if self.message_handler:
            try:
                log_widget.write("[italic gray]Thinking...[/italic gray]")
                
                result = await self.message_handler(user_text, self.session_id)
                response = str(result)
                
                log_widget.write(f"[bold green]Agent:[/bold green] {response}")
                
                self._handle_action(result)
            except Exception as e:
                log_widget.write(f"[bold red]Error:[/bold red] {str(e)}")
        else:
            log_widget.write("[bold red]Error:[/bold red] No message handler configured.")

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
    def __init__(self, session_id: str = "tui-user"):
        super().__init__()
        self.session_id = session_id
        self.app: Optional[TUIApp] = None

    async def send_message(self, target_id: str, content: str, **kwargs):
        """
        This is primarily handled by the TUIApp internally, 
        but we implement it to satisfy BaseChannel.
        """
        if self.app:
            self.app.query_one("#log", RichLog).write(f"[bold green]Agent:[/bold green] {content}")

    def start(self):
        """Start the TUI application."""
        print(f"--- Starting TUI Channel (Session: {self.session_id}) ---")
        self.app = TUIApp(self.message_handler, self.session_id, self)
        self.app.run()

if __name__ == "__main__":
    # Example usage for quick testing
    async def mock_handler(text, sid):
        await asyncio.sleep(0.5) # Simulate thinking
        return f"TUI Echo: {text}"

    channel = TUIChannel()
    channel.set_message_handler(mock_handler)
    channel.start()
