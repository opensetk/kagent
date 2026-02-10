import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kagent.core.agent import AgentLoop
from kagent.interaction.manager import InteractionManager
from kagent.channel.shell import ShellChannel
from kagent.app.main_app import AgentApp

load_dotenv()


def test_shell_integration():
    """
    Test the multi-layer architecture using the ShellChannel with tools.
    Structure: AgentLoop (with ToolManager) -> InteractionManager -> ShellChannel -> AgentApp
    """
    print("🛠️  Setting up Shell Test Environment with Tools...")

    # 1. Create Tool Manager with built-in tools (loaded via @tool decorators)
    from kagent.core.tool import ToolManager
    from kagent.llm.client import LLMClient

    tool_manager = ToolManager()
    print(
        f"✅ Loaded {len(tool_manager.list_tools())} built-in tools via @tool decorator"
    )

    # 2. Core Layer (Agent)
    # Agent receives the tool_manager and can use tools via OpenAI function calling
    llm_client = LLMClient.from_env("openai", model="LongCat-Flash-Lite")
    agent = AgentLoop(llm_client=llm_client, tool_manager=tool_manager)
    agent.set_system_prompt(
        "You are a helpful AI assistant with access to tools for file operations "
        "and command execution. Use tools when appropriate to help the user. "
        "Always show the tool name, arguments, and results to the user."
    )

    # 3. Interaction Layer (Manager)
    # Manages session storage and hooks, delegates tool execution to Agent
    manager = InteractionManager(agent=agent)

    # 4. Channel Layer (Shell)
    shell_channel = ShellChannel(session_id="test-session")

    # 5. App Layer (Orchestrator)
    app = AgentApp(manager=manager, channel=shell_channel)

    print("\n✅ System ready! You can now chat with the agent.")
    print("\n📋 Session Management:")
    print("   /new [name]       - Create new session")
    print("   /change <name/id> - Switch to session")
    print("   /list             - List all sessions")
    print("   /delete <name/id> - Delete session")
    print("   /rename <new>     - Rename current session")
    print("\n📋 Other hooks:")
    print("   /history - Show conversation history")
    print("   /clear   - Clear session history")
    print("   /compress - Compress conversation history")
    print("   /save [filename] - Save history to file")
    print("   /tools   - List available tools")
    print("\n🔧 Available tools:")
    for tool in tool_manager.list_tools():
        print(f"   • {tool.name}: {tool.description}")
    print()

    # Start the app (this will enter an interactive loop)
    try:
        app.run()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_shell_integration()
