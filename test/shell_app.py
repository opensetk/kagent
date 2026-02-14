"""
Shell App - Interactive shell channel with full InteractionManager integration.

This is the main entry point for running KAgent in interactive shell mode.
It demonstrates the complete integration between:
- ShellChannel: Handles user input/output via terminal
- InteractionManager: Manages multiple sessions and hook commands
- Agent: Processes conversations and tool calls

Usage:
    python test/shell_app.py

Commands:
    /help          - Show available commands
    /new [name]    - Create a new session
    /switch <name> - Switch to another session
    /list          - List all sessions
    /delete <name> - Delete a session
    /rename <o> <n> - Rename a session
    /clear         - Clear current session history
    /compress      - Compress conversation context
    /save          - Save session to disk
    /history       - Show session history
    /tools         - List available tools
    exit, quit     - Exit the shell
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from kagent.core import Agent, AgentRuntime, ContextManager, ToolManager, SkillLibrary
from kagent.core.agent import AgentConfig
from kagent.llm.client import LLMClient
from kagent.interaction.manager import InteractionManager
from kagent.channel.shell import ShellChannel


def create_agent() -> Agent:
    """
    Create and configure the Agent with all necessary components.
    
    Returns:
        Configured Agent instance ready for use
    """
    # Initialize LLM client from environment
    # Supports: openai, claude, etc.
    llm_client = LLMClient.from_env("openai", model="longcat-flash-lite")
    
    # Initialize tool manager with built-in tools
    # Set load_mcp=True if you want to load MCP tools from .agent/mcp.json
    tool_manager = ToolManager(load_builtin=True, load_mcp=False)
    
    # Initialize skill library
    skill_library = SkillLibrary(auto_load=True)
    
    # Initialize context manager for conversation handling
    context_manager = ContextManager(llm_client=llm_client)
    prompt_path = Path("/Volumes/sn580/projects/myagent/workspace/KAGENT.md")
    content = prompt_path.read_text()
    # Configure the agent
    agent_config = AgentConfig().from_markdown(content)
    print(agent_config)
    # Create the agent
    agent = Agent(
        agent_config=agent_config,
        llm_client=llm_client,
        context_manager=context_manager,
        tool_manager=tool_manager,
        skill_library=skill_library,
    )
    
    return agent


async def main():
    """
    Main entry point for the shell application.
    
    Sets up the InteractionManager, creates the ShellChannel,
    and starts the interactive loop.
    """
    print("🚀 Starting KAgent Shell...")
    print()
        
    # Create the agent
    try:
        agent = create_agent()
        print(f"✅ Agent initialized: {agent.config.name}")
    except Exception as e:
        print(f"❌ Failed to initialize agent: {e}")
        sys.exit(1)
    
    # Create the interaction manager
    # Sessions will be saved to .agent/sessions/
    interaction_manager = InteractionManager(sessions_dir=".agent/sessions")
    interaction_manager.set_agent(agent)
    print(f"✅ InteractionManager initialized")
    print(f"   Sessions directory: {interaction_manager.sessions_dir}")
    
    # Load existing sessions
    if interaction_manager.available_sessions:
        print(f"✅ Loaded {len(interaction_manager.available_sessions)} existing session(s)")
        for sid in interaction_manager.available_sessions.keys():
            print(f"   - {sid}")
    else:
        print("📭 No existing sessions found")
    
    print()
    
    # Create and start the shell channel
    shell_channel = ShellChannel(session_id="default")
    
    try:
        # Run the shell with the interaction manager
        await shell_channel.run_with_manager(interaction_manager)
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
        print("👋 Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted by user. Goodbye!")
        sys.exit(0)
