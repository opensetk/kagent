import os
import sys
from dotenv import load_dotenv

# 将项目根目录添加到 python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kagent.core.agent import AgentLoop
from kagent.core.skill import SkillManager
from kagent.interaction.manager import InteractionManager
from kagent.channel.lark import LarkChannel
from kagent.app.main_app import AgentApp

load_dotenv()


def main():
    print("🚀 Initializing Multi-layer Agent System...")

    # 1. 核心执行层 (Agent)
    from kagent.core.tool import ToolManager
    from kagent.llm.client import LLMClient

    tool_manager = ToolManager()
    skill_manager = SkillManager()
    
    llm_client = LLMClient.from_env("openai", model="LongCat-Flash-Lite")
    agent = AgentLoop(llm_client=llm_client, tool_manager=tool_manager, skill_manager=skill_manager)    

    # 2. 交互管理层 (Interaction Manager - 处理 Session, 历史, 指令)
    # 初始化时自动加载最新 session
    manager = InteractionManager(agent=agent)

    # 3. 通道层 (Channel - 负责具体的平台对接)
    try:
        lark_channel = LarkChannel()

        # 4. 应用层 (App - 协调 Manager 和 Channel)
        app = AgentApp(manager=manager, channel=lark_channel)

        # 启动服务
        app.run()

    except Exception as e:
        print(f"❌ Failed to start application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
