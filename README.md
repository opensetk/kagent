# kAgent

这是一个基于 Python 的多层架构 Agent 系统，支持多渠道（飞书、Shell、TUI）接入、异步处理、Session 管理、Hook 机制以及强大的工具调用系统。

## 🏗️ 项目架构

项目采用分层架构设计，确保每一层职责单一，易于扩展。

```text
kagent/
├── app/             # 应用层：负责协调 Channel 和 InteractionManager
├── channel/         # 通道层：负责具体平台的协议对接（飞书、Shell、TUI）
├── core/            # 核心层：包含 Agent 主循环、工具管理和上下文管理
├── interaction/     # 交互层：处理 Session 历史、Hook 指令和拦截器
├── llm/             # LLM 驱动层：对接不同模型供应商（OpenAI, Claude 等）
└── tools/           # 工具实现层：内置的文件操作、命令执行等工具
```

### 每一层的作用：

1.  **Core Layer (核心层)**:
    -   `AgentLoop`: 核心对话逻辑，支持多轮工具调用（Function Calling）。
    -   `ToolManager`: 统一管理工具的自动发现、注册和执行。
    -   `ContextManager`: 负责管理对话历史和 Token 限制。

2.  **Interaction Layer (交互层)**:
    -   `InteractionManager`: 负责 Session 的持久化保存与加载，确保对话连续性。
    -   `HookDispatcher`: 指令拦截器，处理以 `/` 开头的特殊指令（如 `/clear`, `/session`）。

3.  **Channel Layer (通道层)**:
    -   `LarkChannel`: 飞书机器人对接，支持长连接和 **卡片 JSON 2.0** 格式的 Markdown 回复。
    -   `ShellChannel`: 本地终端交互，用于快速开发调试。
    -   `TUIChannel`: 基于 Textual 的富文本终端界面。

4.  **Tools Implementation (工具层)**:
    -   通过 `@tool` 装饰器自动注册，支持参数类型校验和自动生成 JSON Schema。
    -   内置工具：文件读写 (`read`, `write`)、文件搜索 (`grep`, `glob`)、命令执行 (`bash`) 等。

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install openai httpx python-dotenv lark-oapi textual
```

### 2. 配置环境变量
创建 `.env` 文件（参考 `.env.example`）：
```env
# LLM 配置
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4-turbo

# 飞书配置 (使用 LarkChannel 时需要)
APP_ID=cli_xxx
APP_SECRET=xxx
```

### 3. 运行本地 Shell 测试
```bash
python test/shell_app.py
```

### 4. 运行飞书机器人
```bash
python test/lark_app.py
```

## 🔧 扩展功能

### 自定义工具
只需在 `kagent/tools/` 目录下创建新的 Python 文件并使用 `@tool` 装饰器：

```python
from kagent.core.tool import tool

@tool
async def get_weather(city: str) -> str:
    """获取指定城市的实时天气"""
    return f"{city} 的天气是晴天"
```

### 自定义 Hook
可以在 `InteractionManager` 中注册指令 Hook，拦截特定输入。

## 📄 飞书消息增强
本项目已全面适配飞书 **卡片 JSON 2.0** 结构，支持更美观的 Markdown 渲染。所有 Agent 回复均通过 `interactive` 卡片发送，确保代码块、表格等复杂格式在飞书客户端完美展示。

---
Built with ❤️ by kAgent Team
