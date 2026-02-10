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
        self.channel.set_message_handler(self.manager.handle_request)

    def run(self):
        """Start the application."""
        print(f"🚀 Agent App is starting with channel: {self.channel.__class__.__name__}")
        self.channel.start()
