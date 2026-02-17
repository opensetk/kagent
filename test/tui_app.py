"""
TUI App - Terminal User Interface for KAgent.

This application provides a rich terminal interface using Textual.
Features:
- Rich text display with Markdown support
- Message history log
- Real-time interaction with Agent
- Session management via InteractionManager

Usage:
    python test/tui_app.py

Controls:
    - Type your message and press Enter to send
    - Ctrl+C or 'q' to quit
    - Ctrl+L to clear the log

Commands:
    /help          - Show available commands
    /new [name]    - Create a new session
    /switch <name> - Switch to another session
    /list          - List all sessions
    /delete <name> - Delete a session
    /clear         - Clear current session history
    /history       - Show session history
    /tools         - List available tools
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from kagent.core import Agent, ContextManager, ToolManager, SkillLibrary
from kagent.core.agent import AgentConfig
from kagent.llm.client import LLMClient
from kagent.interaction.manager import InteractionManager
from kagent.channel.tui import TUIChannel


def create_agent() -> Agent:
    """
    Create and configure the Agent with all necessary components.
    
    Returns:
        Configured Agent instance ready for use
    """
    # Initialize LLM client from environment
    llm_client = LLMClient.from_preset("modelscope")
    
    # Initialize tool manager with built-in tools
    tool_manager = ToolManager(load_builtin=True, load_mcp=True)
    
    # Initialize skill library (disable auto-load to avoid output pollution in TUI)
    skill_library = SkillLibrary(auto_load=True)
    
    # Initialize context manager for conversation handling
    context_manager = ContextManager(llm_client=llm_client)
    prompt_path = Path("/Volumes/sn580/projects/myagent/workspace/KAGENT.md")
    content = prompt_path.read_text()
    # Configure the agent
    agent_config = AgentConfig().from_markdown(content)
    
    # Create the agent
    agent = Agent(
        agent_config=agent_config,
        llm_client=llm_client,
        context_manager=context_manager,
        tool_manager=tool_manager,
        skill_library=skill_library,
    )
    
    return agent


def main():
    """
    Main entry point for the TUI application.
    """
    print("🚀 Starting KAgent TUI...")
    
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  Warning: No API key found!")
        print("Please set one of the following environment variables:")
        print("  - OPENAI_API_KEY")
        print("  - ANTHROPIC_API_KEY")
        print()
        print("You can create a .env file with your API key.")
        sys.exit(1)
    
    # Create the agent
    try:
        agent = create_agent()
        print(f"✅ Agent initialized: {agent.config.name}")
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Create the interaction manager
    interaction_manager = InteractionManager(sessions_dir=".agent/sessions")
    interaction_manager.set_agent(agent)
    print(f"✅ InteractionManager initialized")
    
    # Load existing sessions
    if interaction_manager.available_sessions:
        print(f"✅ Loaded {len(interaction_manager.available_sessions)} existing session(s)")
    else:
        print("📭 No existing sessions found")
    
    print()
    print("Starting TUI... (Press Ctrl+C or 'q' to quit)")
    print()
    
    # Create and start the TUI channel
    tui_channel = TUIChannel(session_id="tui-default")
    tui_channel.set_message_handler(interaction_manager.handle_request)
    
    try:
        tui_channel.start()
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Save all sessions on exit
        print("\n💾 Saving sessions...")
        for session_id, runtime in interaction_manager.available_sessions.items():
            try:
                runtime.save_to_file(interaction_manager.sessions_dir)
                print(f"   Saved: {session_id}")
            except Exception as e:
                print(f"   Failed to save {session_id}: {e}")


if __name__ == "__main__":
    main()
