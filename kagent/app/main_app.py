from typing import Dict, Any
from kagent.channel.base import BaseChannel
from kagent.interaction.manager import InteractionManager

class AgentApp:
    """
    Generic application that orchestrates a Channel and the InteractionManager.
    This is the entry point that connects any channel to the agent logic.
    """

    def __init__(self, manager: InteractionManager, channel: BaseChannel):
        self.manager = manager
        self.channel = channel
        
        # Bind the manager's handle_request to the channel's message_handler
        # Pass channel's on_tool_call callback for tool execution display
        self.channel.set_message_handler(self._handle_message)

    async def _handle_message(self, text: str, session_id: str) -> str:
        """
        Handle incoming message from channel.
        Passes channel's on_tool_call callback to enable tool execution display.
        """
        return await self.manager.handle_request(
            text=text, 
            session_id=session_id,
            on_tool_call=self.channel.on_tool_call
        )

    def run(self):
        """Start the application."""
        print(f"🚀 Agent App is starting with channel: {self.channel.__class__.__name__}")
        self.channel.start()
