import os
import sys
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kagent.core.agent import AgentLoop
from kagent.core.context import AgentRuntime, Context
from kagent.core.skill import SkillManager
from kagent.interaction.manager import InteractionManager
from kagent.channel.shell import ShellChannel
from kagent.app.main_app import AgentApp

load_dotenv()


def test_shell_integration():
    """
    Test the multi-layer architecture using the ShellChannel with tools and skills.
    Structure: AgentLoop (with ToolManager + SkillManager) -> InteractionManager -> ShellChannel -> AgentApp
    """
    print("🛠️  Setting up Shell Test Environment with Tools & Skills...")

    # 1. Create Tool Manager with built-in tools (loaded via @tool decorators)
    from kagent.core.tool import ToolManager
    from kagent.llm.client import LLMClient

    tool_manager = ToolManager()
    print(
        f"✅ Loaded {len(tool_manager.list_tools())} built-in tools via @tool decorator"
    )

    # 2. Core Layer (Agent)
    # Agent receives the tool_manager for executing tools
    llm_client = LLMClient.from_env("openai", model="longcat-flash-lite")
    
    # Create SkillManager to load all skills
    skill_manager = SkillManager()
    print(f"✅ Loaded {len(skill_manager.list_skills())} skills from .agent/skills/")
    
    # Create runtime and context for the agent
    runtime = AgentRuntime()
    context = Context(
        runtime=runtime,
        model=llm_client.model,
        llm_client=llm_client,
        skill_manager=skill_manager,
    )

    
    agent = AgentLoop(
        llm_client=llm_client,
        tool_manager=tool_manager,
        context=context,
        skill_manager=skill_manager,
    )

    # 4. Interaction Layer (Manager)
    # Manages session storage and hooks, delegates tool execution to Agent
    manager = InteractionManager(agent=agent, model=llm_client.model)

    # 5. Channel Layer (Shell)
    shell_channel = ShellChannel(session_id="test-session")

    # 6. App Layer (Orchestrator)
    app = AgentApp(manager=manager, channel=shell_channel)

    print("\n" + "=" * 60)
    print("✅ System ready! You can now chat with the agent.")
    print("=" * 60)
    
    print("\n📋 Session Management:")
    print("   /new [name]       - Create new session")
    print("   /switch <name>    - Switch to session")
    print("   /list             - List all sessions")
    print("   /delete <name>    - Delete session")
    print("   /rename <new>     - Rename current session")
    
    print("\n📋 Other hooks:")
    print("   /history - Show conversation history")
    print("   /clear   - Clear session history")
    print("   /compress - Compress conversation history")
    print("   /save [filename] - Save history to file")
    print("   /tools   - List available tools")
    
    print("\n🎯 Skill Management (via tools):")
    print("   Try asking about PowerPoint, Git, or code review!")
    print("   Or use: list_skills(), view_skill(name), activate_skill(name)")
    
    print("\n🔧 Available tools:")
    for tool in tool_manager.list_tools():
        print(f"   • {tool.name}")
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
