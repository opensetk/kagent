"""
Agent module for kagent - core conversation loop.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union, Callable, Awaitable

from kagent.core.tool import ToolManager, ToolResult
from kagent.core.context import AgentRuntime, ContextManager
from kagent.core.skill import SkillLibrary, Skill
from kagent.core.events import MessageEvent
from kagent.llm.client import LLMClient


@dataclass
class AgentConfig:
    """
    Configuration for an Agent.
    
    For tools and skills:
    - "all" or ["all"]: Enable all available tools/skills
    - "none" or []: Disable all tools/skills
    - ["tool1", "tool2"]: Enable specific tools/skills
    """
    type: str = "main"
    name: str = ""
    tools: Union[str, List[str]] = field(default_factory=list)
    skills: Union[str, List[str]] = field(default_factory=list)
    description: str = ""
    prompt: str = ""

    def _normalize_tools_skills(self, value: Union[str, List[str]]) -> List[str]:
        """Normalize tools/skills value to a list."""
        if isinstance(value, str):
            value = value.lower().strip()
            print(f"Normalizing value: {value}")
            if value == "all":
                return ["all"]
            elif value == "none" or value == "":
                return []
            else:
                # Comma-separated list
                return [t.strip() for t in value.split(",") if t.strip()]
        elif isinstance(value, list):
            if len(value) == 1 and isinstance(value[0], str):
                first = value[0].lower().strip()
                if first == "all":
                    return ["all"]
                elif first == "none":
                    return []
            return [t.strip() for t in value if t and isinstance(t, str) and t.strip()]
        return []

    def get_tools_list(self) -> List[str]:
        """Get normalized tools list."""
        return self._normalize_tools_skills(self.tools)

    def get_skills_list(self) -> List[str]:
        """Get normalized skills list."""
        return self._normalize_tools_skills(self.skills)

    def is_all_tools(self) -> bool:
        """Check if all tools are enabled."""
        tools = self.get_tools_list()
        return len(tools) == 1 and tools[0] == "all"

    def is_no_tools(self) -> bool:
        """Check if no tools are enabled."""
        return len(self.get_tools_list()) == 0

    def is_all_skills(self) -> bool:
        """Check if all skills are enabled."""
        skills = self.get_skills_list()
        return len(skills) == 1 and skills[0] == "all"

    def is_no_skills(self) -> bool:
        """Check if no skills are enabled."""
        return len(self.get_skills_list()) == 0

    @classmethod
    def from_markdown(cls, content: str) -> "AgentConfig":
        """Parse Markdown file content and return config instance."""
        lines = content.splitlines()
        metadata = {}
        body_lines = []
        in_metadata = False
        for line in lines:
            if line.startswith("---"):
                in_metadata = not in_metadata
                continue
            if in_metadata:
                if ":" in line:
                    key, val = line.split(":", 1)
                    metadata[key.strip()] = val.strip()
            else:
                body_lines.append(line)
        
        # Parse tools - can be "all", "none", or comma-separated list
        tools_raw = metadata.get("tools", "").lower().strip()
        if tools_raw == "all":
            tools = "all"
        elif tools_raw == "none" or tools_raw == "":
            tools = []
        else:
            tools = [t.strip() for t in tools_raw.split(",") if t.strip()]
        
        # Parse skills - can be "all", "none", or comma-separated list
        skills_raw = metadata.get("skills", "").lower().strip()
        if skills_raw == "all":
            skills = "all"
        elif skills_raw == "none" or skills_raw == "":
            skills = []
        else:
            skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
        
        return cls(
            type=metadata.get("type", "main"),
            name=metadata.get("name", ""),
            description=metadata.get("description", ""),
            tools=tools,
            skills=skills,
            prompt="\n".join(body_lines).strip(),
        )


class Agent:
    """Agent - User-facing interface for conversation."""

    def __init__(
        self,
        agent_config: AgentConfig,
        llm_client: LLMClient,
        context_manager: ContextManager,
        tool_manager: ToolManager,
        skill_library: SkillLibrary,
    ):
        self.config = agent_config
        self.max_iterations = 100
        self.llm_client = llm_client
        self.context_manager = context_manager
        self.tool_manager = tool_manager
        self.skill_library = skill_library

    def _get_tool_definitions(self, tool_names: List[str]) -> List[Dict]:
        """
        Return OpenAI format tool definitions for enabled tools.
        
        Args:
            tool_names: List of tool names, or ["all"] for all tools, or [] for no tools
        
        Returns:
            List of tool definitions in OpenAI format
        """
        # Handle "all" - return all available tools
        if len(tool_names) == 1 and tool_names[0] == "all":
            return self.tool_manager.get_all_tools()
        
        # Handle empty list - no tools
        if not tool_names:
            return []
        
        # Handle specific tool list
        tools = []
        for name in tool_names:
            if self.tool_manager.has_tool(name):
                tool = self.tool_manager.get_tool(name)
                if tool:
                    tools.append(tool.to_openai_format())
        return tools

    def _get_skills(self, skill_names: List[str]) -> List[Skill]:
        """
        Return list of enabled skills.
        
        Args:
            skill_names: List of skill names, or ["all"] for all skills, or [] for no skills
        
        Returns:
            List of Skill objects
        """
        # Handle "all" - return all available skills
        if len(skill_names) == 1 and skill_names[0] == "all":
            print(f"Enabling all skills: {self.skill_library.get_all_skills()}")
            return self.skill_library.get_all_skills()
        
        # Handle empty list - no skills
        if not skill_names:
            return []
        
        # Handle specific skill list
        skills = []
        for name in skill_names:
            if self.skill_library.has_skill(name):
                skill = self.skill_library.get_skill(name)
                if skill:
                    skills.append(skill)
        return skills

    def _build_skills_prompt(self, skills: List[Skill]) -> str:
        """Build skills section for system prompt."""
        if not skills:
            return ""
        sections = []
        for skill in skills:
            sections.append(f"<skill name=\"{skill.name}\">\n{skill.content}\n</skill>")
        return "\n\n".join(sections)

    def _build_system_prompt(self) -> str:
        """Build system prompt with skills."""
        skills = self._get_skills(self.config.get_skills_list())
        skills_prompt = self._build_skills_prompt(skills)
        if skills_prompt:
            return f"{self.config.prompt}\n\n{skills_prompt}"
        return self.config.prompt

    def new_session(self, session_id: str) -> AgentRuntime:
        """Create new agent runtime session."""
        system_prompt = self._build_system_prompt()
        runtime = AgentRuntime(
            session_id=session_id,
            system_prompt=system_prompt,
            enabled_tools=self.config.get_tools_list(),
            enabled_skills=self.config.get_skills_list(),
        )
        # Add system message directly without async processing
        runtime.conversation_history.append({
            "role": "system",
            "content": system_prompt,
        })
        return runtime

    async def chat(
        self, 
        runtime: AgentRuntime, 
        user_input: str,
        on_message: Optional[Callable[[MessageEvent], Awaitable[None]]] = None
    ) -> str:
        """
        Process user input and return assistant response.
        
        Args:
            runtime: Agent runtime containing conversation state
            user_input: User's input text
            on_message: Optional async callback for message events
        """
        async def emit(event: MessageEvent):
            if on_message:
                try:
                    import asyncio
                    result = on_message(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    print(f"Error in on_message callback: {e}")
        
        await self.context_manager.process_a_message(runtime, "user", user_input)
        await emit(MessageEvent.user_input(user_input))
        
        tools = self._get_tool_definitions(runtime.enabled_tools)

        assistant_reply = ""
        for _ in range(self.max_iterations):
            messages = runtime.conversation_history
            response = await self.llm_client.complete(messages, tools=tools)

            if not response.tool_calls:
                assistant_reply = response.content or ""
                break

            if response.content:
                await emit(MessageEvent.assistant_thinking(response.content))

            assistant_msg = {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ],
            }
            runtime.conversation_history.append(assistant_msg)

            for tc in response.tool_calls:
                import json
                try:
                    arguments = json.loads(tc.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                await emit(MessageEvent.tool_call(tc.name, arguments, tc.id))

            tool_results = await self.tool_manager.execute_tool_calls(response.tool_calls)
            
            for tr in tool_results:
                await emit(MessageEvent.tool_result(
                    tool_name=tr["name"],
                    result=tr["content"],
                    success=True,
                    tool_call_id=tr["tool_call_id"]
                ))
                await self.context_manager.process_a_message(
                    runtime,
                    role="tool",
                    content=tr["content"],
                    tool_call_id=tr["tool_call_id"],
                    name=tr["name"],
                )
        else:
            assistant_reply = "Too many tool calls, please try again later."

        await self.context_manager.process_a_message(runtime, "assistant", assistant_reply)
        await emit(MessageEvent.assistant_response(assistant_reply))
        return assistant_reply
