import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kagent.core.agent import AgentLoop
from kagent.interaction.manager import InteractionManager
from kagent.channel.audio import AudioChannel
from kagent.app.main_app import AgentApp

load_dotenv()


def test_audio_integration():
    """
    Test the multi-layer architecture using the AudioChannel.
    Structure: AgentLoop -> InteractionManager -> AudioChannel -> AgentApp
    """
    print("🎙️  Setting up Audio Test Environment...")

    # 1. Core Layer (Agent)
    from kagent.core.tool import ToolManager
    from kagent.llm.client import LLMClient

    tool_manager = ToolManager()
    
    # Use environment variables for LLM configuration
    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    
    llm_client = LLMClient.from_env(provider, model=model)
    agent = AgentLoop(llm_client=llm_client, tool_manager=tool_manager)
    agent.set_system_prompt(
        "You are a helpful AI assistant. Answer concisely and helpfully."
    )

    # 2. Interaction Layer (Manager)
    manager = InteractionManager(agent=agent)

    # 3. Channel Layer (Audio)
    # You can specify input_device_index if needed
    audio_channel = AudioChannel(session_id="audio-test-session")

    # 4. App Layer (Orchestrator)
    app = AgentApp(manager=manager, channel=audio_channel)

    print("\n✅ System ready! Launching Audio Agent...")

    # Start the app
    try:
        app.run()
    except Exception as e:
        print(f"❌ Audio Test failed: {e}")


if __name__ == "__main__":
    test_audio_integration()
