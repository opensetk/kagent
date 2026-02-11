import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kagent.core.tool import ToolManager

async def test_mcp_loading():
    print("🚀 Testing MCP Tool Loading...")
    
    # Initialize ToolManager with MCP loading enabled
    # It will automatically try to load from .agent/mcp.json
    manager = ToolManager(load_builtin=False, load_mcp=True)
    
    # Wait a bit for the async background task to complete
    print("Waiting for MCP tools to load...")
    await asyncio.sleep(5)
    
    tools = manager.list_tools()
    print(f"\nTotal tools registered: {len(tools)}")
    
    for t in tools:
        print(f" - [{t.name}]: {t.description[:50]}...")
    
    if len(tools) > 0:
        print("\n✅ MCP tool loading successful!")
    else:
        print("\n❌ No MCP tools loaded. Check if fastmcp is installed and .agent/mcp.json is valid.")

if __name__ == "__main__":
    try:
        asyncio.run(test_mcp_loading())
    except KeyboardInterrupt:
        pass
