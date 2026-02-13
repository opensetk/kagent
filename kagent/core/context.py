"""
Context module for kagent - manages conversation context and prompt building.

This module provides:
- AgentRuntime: Pure data class for agent state
- Context: Functional class for context management (prompt building, message handling, compression)
"""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path
import tiktoken

from kagent.core.config import AgentConfig
from kagent.core.skill import Skill


@dataclass
class AgentRuntime:
    """
    Runtime context for the agent, including conversation history and token tracking.
    
    This is a pure data class that stores the state of an agent session.
    All functional operations are handled by the Context class.
    """
    session_id: str = ""
    work_dir: str = ""
    token_count: int = 0
    max_tokens: int = 200000
    ratio_of_compress: float = 0.7
    keep_last_n_messages: int = 3
    system_prompt: str = "You are a helpful AI assistant with access to tools for file operations."
    loaded_skills: List[Skill] = field(default_factory=list)
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize runtime to dictionary (for persistence)."""
        return {
            "session_id": self.session_id,
            "work_dir": self.work_dir,
            "token_count": self.token_count,
            "max_tokens": self.max_tokens,
            "ratio_of_compress": self.ratio_of_compress,
            "keep_last_n_messages": self.keep_last_n_messages,
            "system_prompt": self.system_prompt,
            "loaded_skills": [
                {"name": s.name, "description": s.description, "path": str(s.path) if s.path else ""}
                for s in self.loaded_skills
            ],
            "conversation_history": self.conversation_history,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentRuntime":
        """Deserialize runtime from dictionary."""
        runtime = cls(
            session_id=data.get("session_id", ""),
            work_dir=data.get("work_dir", ""),
            token_count=data.get("token_count", 0),
            max_tokens=data.get("max_tokens", 200000),
            ratio_of_compress=data.get("ratio_of_compress", 0.7),
            keep_last_n_messages=data.get("keep_last_n_messages", 3),
            system_prompt=data.get("system_prompt", ""),
            conversation_history=data.get("conversation_history", []),
        )
        # Reconstruct skills from metadata (content will be loaded on demand)
        skills_data = data.get("loaded_skills", [])
        runtime.loaded_skills = [
            Skill(
                name=s.get("name", ""),
                description=s.get("description", ""),
                content="",  # Content loaded when needed
                path=Path(s.get("path", "")) if s.get("path") else None,
            )
            for s in skills_data
        ]
        return runtime


class ContextManager:
    """
    Manages conversation context with token tracking and automatic compression.
    
    This class handles:
    - System prompt building (from KAGENT.md + skill descriptions)
    - Message storage and retrieval
    - Token counting using tiktoken
    - Context compression when token limit is exceeded
    
    The Context operates on an AgentRuntime instance but does not own it,
    allowing the runtime state to be managed externally (e.g., by SessionManager).
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        model: str = "gpt-4o",
        compression_callback: Optional[Callable[[str], None]] = None,
        llm_client=None,
        skill_manager=None,
    ):
        """
        Initialize Context.

        Args:
            runtime: AgentRuntime instance to operate on
            model: Model name for token encoding
            compression_callback: Optional callback when compression is triggered
            llm_client: LLM client for compression (optional, can be set later)
            skill_manager: SkillManager instance for available skills
        """
        self.runtime = runtime
        self.model = model
        self.compression_callback = compression_callback
        self.llm_client = llm_client
        self.skill_manager = skill_manager
        
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        self._base_system_prompt = self._load_system_prompt()
        
        self._rebuild_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load system prompt from KAGENT.md file or use default."""
        default_prompt = (
            "你是xiaok，一个智能助手，你可以使用各项能力协助我完成不同任务。"
        )
        
        prompt_path = getattr(self.runtime, 'system_prompt_path', 'KAGENT.md')
        if not prompt_path:
            prompt_path = 'KAGENT.md'
        
        path = Path(prompt_path)
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except Exception as e:
                print(f"Warning: Failed to read {prompt_path}: {e}")
        
        return default_prompt

    def _build_skills_xml(self) -> str:
        """Build XML representation of all available skills."""
        all_skills = []
        loaded_skill_names = {s.name for s in self.runtime.loaded_skills}
        
        # 如果有 skill_manager，获取所有可用的 skills
        if self.skill_manager:
            all_skills = self.skill_manager.list_skills()
        
        if not all_skills and not self.runtime.loaded_skills:
            return ""
        
        lines = ["\n<skills>"]
        
        # 显示已加载的 skills
        for skill in self.runtime.loaded_skills:
            lines.append("  <skill state=\"loaded\">")
            lines.append(f"    <name>{skill.name}</name>")
            lines.append(f"    <description>{skill.description}</description>")
            if skill.path:
                lines.append(f"    <path>{skill.path}</path>")
            lines.append("  </skill>")
        
        # 显示未加载的 skills
        for skill in all_skills:
            if skill.name not in loaded_skill_names:
                lines.append("  <skill state=\"available\">")
                lines.append(f"    <name>{skill.name}</name>")
                lines.append(f"    <description>{skill.description}</description>")
                if skill.path:
                    lines.append(f"    <path>{skill.path}</path>")
                lines.append("  </skill>")
        
        lines.append("</skills>")
        lines.append("\n注意：如需使用skill，请使用read工具读取skill文件。")
        return "\n".join(lines)

    def _rebuild_system_prompt(self) -> None:
        """Rebuild system prompt with base content and skill descriptions."""
        parts = [self._base_system_prompt]
        
        # Add working directory info
        work_dir = getattr(self.runtime, 'work_dir', None)
        if work_dir:
            parts.append(f"\n工作目录: {work_dir}")
        
        # Add skills in XML format
        skills_xml = self._build_skills_xml()
        if skills_xml:
            parts.append(skills_xml)
        
        self.runtime.system_prompt = "\n".join(parts)

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """
        Add a message to the conversation history.
        
        Automatically triggers compression if token limit is exceeded.
        
        Args:
            role: Message role (user, assistant, tool, etc.)
            content: Message content
            **kwargs: Additional message fields (tool_calls, tool_call_id, name, etc.)
        """
        message = {"role": role, "content": content}
        message.update(kwargs)
        self.runtime.conversation_history.append(message)
        
        # Update token count
        self.runtime.token_count = self.count_tokens()
        
        # Check if compression is needed
        if self.should_compress():
            self.compress_context()

    def add_messages(self, messages: List[Dict[str, Any]]) -> None:
        """Add multiple messages at once."""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            extra = {k: v for k, v in msg.items() if k not in ["role", "content"]}
            self.add_message(role, content, **extra)

    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Get complete message list including system prompt for API calls.
        
        Returns:
            List of messages ready for LLM API
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.runtime.system_prompt}
        ]
        messages.extend(self.runtime.conversation_history)
        return messages

    def get_history(self) -> List[Dict[str, Any]]:
        """Get raw conversation history (without system prompt)."""
        return self.runtime.conversation_history.copy()

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.runtime.conversation_history = []
        self.runtime.token_count = 0

    def count_tokens(self) -> int:
        """
        Count total tokens in conversation history.
        
        Returns:
            Total token count
        """
        total_tokens = 0
        
        for message in self.runtime.conversation_history:
            content = message.get("content", "")
            if content:
                total_tokens += len(self.encoding.encode(content))
            
            # Count tokens for tool_calls if present
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                for tool_call in tool_calls:
                    function = tool_call.get("function", {})
                    name = function.get("name", "")
                    arguments = function.get("arguments", "")
                    if name:
                        total_tokens += len(self.encoding.encode(name))
                    if arguments:
                        total_tokens += len(self.encoding.encode(arguments))
        
        return total_tokens

    def should_compress(self) -> bool:
        """
        Check if conversation history should be compressed.
        
        Returns:
            True if token count exceeds threshold
        """
        threshold = int(self.runtime.max_tokens * self.runtime.ratio_of_compress)
        return self.runtime.token_count > threshold

    def compress_context(self) -> str:
        """
        Compress conversation history when token limit is exceeded.
        
        This method:
        1. Keeps the last keep_last_n_messages messages
        2. Summarizes older messages using LLM (without tool call details)
        3. Replaces old history with summary + metadata
        
        Returns:
            Status message about compression
        """
        if not self.runtime.conversation_history:
            return "History is empty, nothing to compress."
        
        if not self.llm_client:
            # Fallback: just clear history if no LLM client
            old_count = len(self.runtime.conversation_history)
            self.clear_history()
            msg = f"Context cleared: {old_count} messages removed (no LLM client for compression)"
            if self.compression_callback:
                self.compression_callback(msg)
            return msg
        
        keep_n = self.runtime.keep_last_n_messages
        
        # If history is shorter than keep_n, just clear it
        if len(self.runtime.conversation_history) <= keep_n:
            old_tokens = self.runtime.token_count
            self.clear_history()
            msg = f"Context cleared: {old_tokens} tokens removed (history too short to summarize)"
            if self.compression_callback:
                self.compression_callback(msg)
            return msg
        
        # Split history: older messages to summarize, recent to keep
        messages_to_summarize = self.runtime.conversation_history[:-keep_n]
        messages_to_keep = self.runtime.conversation_history[-keep_n:]
        
        # Build summary prompt
        summary_input = self._build_summary_input(messages_to_summarize)
        
        try:
            import asyncio
            
            # Generate summary
            summary_prompt = (
                "请对以下对话历史进行简洁的摘要，保留关键信息和上下文：\n\n"
                f"{summary_input}"
            )
            
            # Run async summary generation
            if asyncio.iscoroutinefunction(self.llm_client.complete):
                # If we're in async context, run it
                try:
                    loop = asyncio.get_running_loop()
                    # We're already in an event loop, need to handle carefully
                    # For now, just clear without summary
                    raise RuntimeError("Cannot compress in async context without proper handling")
                except RuntimeError:
                    # No running loop, can use run
                    response = asyncio.run(self.llm_client.complete(
                        [{"role": "system", "content": "你是一个对话摘要助手。"},
                         {"role": "user", "content": summary_prompt}]
                    ))
            else:
                response = self.llm_client.complete(
                    [{"role": "system", "content": "你是一个对话摘要助手。"},
                     {"role": "user", "content": summary_prompt}]
                )
            
            summary = response.content if hasattr(response, 'content') else str(response)
            
            # Build compressed context
            compressed_history = []
            
            # Add summary as a system/context message
            if summary:
                compressed_history.append({
                    "role": "assistant",
                    "content": f"[历史对话摘要] {summary}",
                    "is_summary": True,
                })
            
            # Add metadata about loaded skills
            if self.runtime.loaded_skills:
                skill_names = ", ".join([s.name for s in self.runtime.loaded_skills])
                compressed_history.append({
                    "role": "assistant", 
                    "content": f"[已加载技能] {skill_names}",
                    "is_metadata": True,
                })
            
            # Add kept messages
            compressed_history.extend(messages_to_keep)
            
            # Update history
            old_token_count = self.runtime.token_count
            self.runtime.conversation_history = compressed_history
            self.runtime.token_count = self.count_tokens()
            
            msg = (
                f"Context compressed: {old_token_count} -> {self.runtime.token_count} tokens "
                f"(kept last {keep_n} messages, summarized {len(messages_to_summarize)} messages)"
            )
            
        except Exception as e:
            # Fallback: keep recent messages only
            self.runtime.conversation_history = messages_to_keep
            self.runtime.token_count = self.count_tokens()
            msg = f"Context compressed (fallback): kept last {keep_n} messages only (summary failed: {e})"
        
        if self.compression_callback:
            self.compression_callback(msg)
        
        return msg

    def _build_summary_input(self, messages: List[Dict[str, Any]]) -> str:
        """
        Build input for summary generation from messages.
        
        Excludes tool call details, focuses on user questions and assistant responses.
        """
        lines = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Skip tool messages and messages without content
            if role == "tool" or not content:
                continue
            
            # For assistant messages with tool calls, just note that tools were used
            if role == "assistant" and msg.get("tool_calls"):
                lines.append(f"Assistant: {content} [使用了工具]")
            else:
                lines.append(f"{role.capitalize()}: {content}")
        
        return "\n".join(lines)

    def load_skill(self, skill: Skill) -> bool:
        """
        Load a skill into the context.
        
        Args:
            skill: Skill instance to load
            
        Returns:
            True if skill was loaded successfully
        """
        # Check if already loaded
        for s in self.runtime.loaded_skills:
            if s.name == skill.name:
                return False
        
        self.runtime.loaded_skills.append(skill)
        self._rebuild_system_prompt()
        return True

    def unload_skill(self, skill_name: str) -> bool:
        """
        Unload a skill from the context.
        
        Args:
            skill_name: Name of the skill to unload
            
        Returns:
            True if skill was unloaded
        """
        original_count = len(self.runtime.loaded_skills)
        self.runtime.loaded_skills = [
            s for s in self.runtime.loaded_skills if s.name != skill_name
        ]
        
        if len(self.runtime.loaded_skills) < original_count:
            self._rebuild_system_prompt()
            return True
        return False

    def clear_skills(self) -> None:
        """Clear all loaded skills."""
        self.runtime.loaded_skills = []
        self._rebuild_system_prompt()

    def list_loaded_skills(self) -> List[str]:
        """Get names of currently loaded skills."""
        return [s.name for s in self.runtime.loaded_skills]

    def get_loaded_skills(self) -> List[Skill]:
        """Get list of loaded skill instances."""
        return self.runtime.loaded_skills.copy()

    def set_base_system_prompt(self, prompt: str) -> None:
        """Set the base system prompt (without skills)."""
        self._base_system_prompt = prompt
        self._rebuild_system_prompt()

    def update_runtime(self, runtime: AgentRuntime) -> None:
        """Update the runtime instance this context operates on."""
        print(f"[ContextManager] Switching to session: {runtime.session_id}")
        self.runtime = runtime
        self._rebuild_system_prompt()
        print(f"[ContextManager] System prompt loaded ({len(runtime.system_prompt)} chars):")
        print("-" * 40)
        print(runtime.system_prompt[:500] + "..." if len(runtime.system_prompt) > 500 else runtime.system_prompt)
        print("-" * 40)


Context = ContextManager
