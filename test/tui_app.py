import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kagent.core.agent import AgentLoop
from kagent.interaction.manager import InteractionManager
from kagent.channel.tui import TUIChannel
from kagent.app.main_app import AgentApp

load_dotenv()


def test_tui_integration():
    """
    Test the multi-layer architecture using the TUIChannel.
    Structure: AgentLoop -> InteractionManager -> TUIChannel -> AgentApp
    """
    print("🛠️  Setting up TUI Test Environment...")

    # 1. Core Layer (Agent)
    from kagent.core.tool import ToolManager
    from kagent.llm.client import LLMClient

    tool_manager = ToolManager()
    llm_client = LLMClient.from_env("openai", model="LongCat-Flash-Lite")
    agent = AgentLoop(llm_client=llm_client, tool_manager=tool_manager)
    agent.set_system_prompt(
        "You are a helpful assistant. Keep your answers very short."
    )

    # 2. Interaction Layer (Manager)
    manager = InteractionManager(agent=agent)

    # 3. Channel Layer (TUI)
    tui_channel = TUIChannel(session_id="tui-test-session")

    # 4. App Layer (Orchestrator)
    app = AgentApp(manager=manager, channel=tui_channel)

    print("\n✅ System ready! Launching TUI...")

    # Start the app
    try:
        app.run()
    except Exception as e:
        print(f"❌ TUI Test failed: {e}")


if __name__ == "__main__":
    test_tui_integration()
