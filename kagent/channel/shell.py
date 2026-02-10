import asyncio
import sys
from typing import Dict, Any, Optional
from kagent.channel.base import BaseChannel


class ShellChannel(BaseChannel):
    """
    Interactive Shell Channel for local testing.
    Allows talking to the agent via terminal input/output.
    """

    def __init__(self, session_id: str = "local-user", agent=None):
        super().__init__()
        self.session_id = session_id
        self.is_running = False
        self.agent = agent

    async def send_message(self, target_id: str, content: str, **kwargs):
        """Print the agent's response to the console."""
        print(f"\n[Agent]: {content}")

    async def _loop(self):
        """Main interactive loop."""
        print(f"--- Shell Channel Started (Session: {self.session_id}) ---")
        print("Type 'exit' or 'quit' to stop.")

        while self.is_running:
            try:
                # Use run_in_executor to avoid blocking the event loop with input()
                loop = asyncio.get_event_loop()
                user_input = await loop.run_in_executor(
                    None, lambda: input("\n[You]: ")
                )

                if user_input.lower() in ["exit", "quit"]:
                    self.is_running = False
                    print("Exiting shell channel...")
                    break

                if not user_input.strip():
                    continue

                if self.message_handler:
                    # Process via InteractionManager
                    response = await self.message_handler(user_input, self.session_id)
                    await self.send_message(self.session_id, response)
                else:
                    print("Error: No message handler configured.")

            except EOFError:
                break
            except Exception as e:
                print(f"Error in shell loop: {e}")

    def start(self):
        """Start the interactive loop."""
        self.is_running = True
        try:
            asyncio.run(self._loop())
        except KeyboardInterrupt:
            print("\nShell channel stopped by user.")

    async def run_with_agent(self, agent) -> None:
        """
        Run interactive mode directly with an AgentLoop instance.

        This is a convenience method for running the agent in interactive mode
        without using the InteractionManager layer.

        Args:
            agent: AgentLoop instance to interact with
        """
        self.agent = agent
        self.is_running = True

        print("--- Agent Shell ---")
        print("Type 'quit', 'exit', or 'q' to stop.")
        print()

        # Clear history for new conversation
        agent.context_manager.clear_history()

        while self.is_running:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("\nYou: ").strip()
                )

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("👋 Goodbye!")
                    self.is_running = False
                    break

                if not user_input:
                    continue

                response = await agent.chat(user_input)
                await self.send_message(self.session_id, response)

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                self.is_running = False
                break
            except Exception as e:
                print(f"Error: {e}")


if __name__ == "__main__":
    # Example usage with AgentLoop
    import os
    from kagent.core.agent import AgentLoop
    from kagent.core.tool import ToolManager
    from kagent.llm.client import LLMClient

    async def main():
        # Create components
        llm_client = LLMClient.from_env("openai")
        tool_manager = ToolManager()
        agent = AgentLoop(llm_client, tool_manager)
        agent.set_system_prompt(
            "You are a helpful AI assistant with access to tools for file operations "
            "and command execution. Use tools when appropriate to help the user."
        )

        # Run interactive mode
        channel = ShellChannel()
        await channel.run_with_agent(agent)

    asyncio.run(main())
