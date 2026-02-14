"""
Lark App - Feishu/Lark Bot for KAgent.

This application runs a Feishu/Lark bot that integrates with KAgent.
It uses WebSocket long connection to receive messages and respond.

Usage:
    python test/lark_app.py

Environment Variables Required:
    APP_ID       - Feishu/Lark App ID
    APP_SECRET   - Feishu/Lark App Secret
    OPENAI_API_KEY or ANTHROPIC_API_KEY - LLM API key

Optional:
    OPENAI_BASE_URL - Custom OpenAI API base URL
    OPENAI_MODEL    - Model name (default: longcat-flash-lite)

Features:
- Multi-session support (each chat/group is a separate session)
- Interactive commands (/help, /list, /new, /switch, etc.)
- Rich message cards with Markdown support
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
from kagent.channel.lark import LarkChannel


def create_agent() -> Agent:
    """
    Create and configure the Agent with all necessary components.
    
    Returns:
        Configured Agent instance ready for use
    """
    # Initialize LLM client from environment
    llm_client = LLMClient.from_env("openai", model="longcat-flash-lite")
    
    # Initialize tool manager with built-in tools
    tool_manager = ToolManager(load_builtin=True, load_mcp=False)
    
    # Initialize skill library (disable auto-load to avoid output pollution)
    skill_library = SkillLibrary(auto_load=False)
    
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
    Main entry point for the Lark bot application.
    """
    print("🚀 Starting KAgent Lark Bot...")
    print()
    
    # Check for required environment variables
    required_vars = ["APP_ID", "APP_SECRET"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print()
        print("Please set the following in your .env file:")
        print("  APP_ID=your_feishu_app_id")
        print("  APP_SECRET=your_feishu_app_secret")
        print()
        print("You can get these from Feishu/Lark Open Platform:")
        print("  https://open.feishu.cn/app/")
        sys.exit(1)
    
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  Warning: No LLM API key found!")
        print("Please set one of the following environment variables:")
        print("  - OPENAI_API_KEY")
        print("  - ANTHROPIC_API_KEY")
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
    
    # Create and start the Lark channel
    try:
        lark_channel = LarkChannel(
            app_id=os.getenv("APP_ID"),
            app_secret=os.getenv("APP_SECRET"),
        )
        lark_channel.set_message_handler(interaction_manager.handle_request)
        print("✅ LarkChannel initialized")
        print()
        print("🤖 Bot is running! Send a message to the bot in Feishu/Lark.")
        print("   Press Ctrl+C to stop.")
        print()
        
        # Start the bot (this blocks)
        lark_channel.start()
        
    except KeyboardInterrupt:
        print("\n\n👋 Stopping bot...")
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
    main()
