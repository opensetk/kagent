"""
Context module for kagent - manages conversation context and prompt building.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import tiktoken

from kagent.core.skill import Skill, SkillLibrary


@dataclass
class AgentRuntime:
    """
    Runtime context for the agent, including conversation history and token tracking.
    """
    session_id: str = ""
    work_dir: str = ""
    system_prompt: str = "You are a helpful AI assistant with access to tools for file operations."
    loaded_skills: List[Skill] = field(default_factory=list)
    enabled_tools: List[str] = field(default_factory=list)
    enabled_skills: List[str] = field(default_factory=list)
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    max_tokens: int = 200000
    ratio_of_compress: float = 0.8
    keep_last_n_messages: int = 4
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_active: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert AgentRuntime to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "work_dir": self.work_dir,
            "system_prompt": self.system_prompt,
            "loaded_skills": [
                {"name": s.name, "description": s.description, "content": s.content}
                for s in self.loaded_skills
            ],
            "enabled_tools": self.enabled_tools,
            "enabled_skills": self.enabled_skills,
            "conversation_history": self.conversation_history,
            "max_tokens": self.max_tokens,
            "ratio_of_compress": self.ratio_of_compress,
            "keep_last_n_messages": self.keep_last_n_messages,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentRuntime":
        """Create AgentRuntime from dictionary."""
        loaded_skills_data = data.get("loaded_skills", [])
        loaded_skills = [
            Skill(name=s["name"], description=s["description"], content=s["content"])
            for s in loaded_skills_data
        ]
        return cls(
            session_id=data.get("session_id", ""),
            work_dir=data.get("work_dir", ""),
            system_prompt=data.get("system_prompt", ""),
            loaded_skills=loaded_skills,
            enabled_tools=data.get("enabled_tools", []),
            enabled_skills=data.get("enabled_skills", []),
            conversation_history=data.get("conversation_history", []),
            max_tokens=data.get("max_tokens", 8000),
            ratio_of_compress=data.get("ratio_of_compress", 0.8),
            keep_last_n_messages=data.get("keep_last_n_messages", 4),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_active=data.get("last_active", datetime.now().isoformat()),
        )

    def save_to_file(self, sessions_dir: str = ".agent/sessions") -> Path:
        """Save runtime to file."""
        sessions_path = Path(sessions_dir)
        sessions_path.mkdir(parents=True, exist_ok=True)
        file_path = sessions_path / f"{self.session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        return file_path

    @classmethod
    def load_from_file(cls, session_id: str, sessions_dir: str = ".agent/sessions") -> Optional["AgentRuntime"]:
        """Load runtime from file."""
        file_path = Path(sessions_dir) / f"{session_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def update_last_active(self) -> None:
        """Update last active timestamp."""
        self.last_active = datetime.now().isoformat()


class ContextManager:
    """
    Manages conversation context, including message handling, token counting, and compression.
    """

    def __init__(self, llm_client=None, model: str = "gpt-4o"):
        self.llm_client = llm_client
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, runtime: AgentRuntime) -> int:
        """Count total tokens in conversation history."""
        total_tokens = 0
        for message in runtime.conversation_history:
            content = message.get("content", "")
            if content:
                total_tokens += len(self.encoding.encode(content))
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

    def _should_compress(self, runtime: AgentRuntime) -> bool:
        """Check if conversation history should be compressed."""
        threshold = int(runtime.max_tokens * runtime.ratio_of_compress)
        token_count = self._count_tokens(runtime)
        return token_count > threshold

    def _add_message(self, runtime: AgentRuntime, role: str, content: str, **kwargs):
        """Add a message to the conversation history."""
        message = {"role": role, "content": content}
        message.update(kwargs)
        runtime.conversation_history.append(message)

    async def compress_context(self, runtime: AgentRuntime) -> str:
        """Compress conversation history when token limit is exceeded."""
        if not runtime.conversation_history:
            return "History is empty, nothing to compress."

        keep_n = runtime.keep_last_n_messages

        if len(runtime.conversation_history) <= keep_n:
            old_count = len(runtime.conversation_history)
            runtime.conversation_history = []
            return f"Context cleared: {old_count} messages removed (history too short to summarize)"

        messages_to_summarize = runtime.conversation_history[:-keep_n]
        messages_to_keep = runtime.conversation_history[-keep_n:]

        if not self.llm_client:
            runtime.conversation_history = messages_to_keep
            return f"Context compressed: kept last {keep_n} messages only (no LLM client for compression)"

        try:
            summary_input = self._build_summary_input(messages_to_summarize)
            summary_prompt = (
                "Please summarize the following conversation history concisely, "
                "retaining key information and context:\n\n"
                f"{summary_input}"
            )

            messages = [
                {"role": "system", "content": "You are a conversation summarization assistant."},
                {"role": "user", "content": summary_prompt}
            ]
            response = await self.llm_client.complete(messages)
            summary = response.content if hasattr(response, 'content') else str(response)

            compressed_history = []
            if summary:
                compressed_history.append({
                    "role": "assistant",
                    "content": f"[History Summary] {summary}",
                    "is_summary": True,
                })

            if runtime.loaded_skills:
                skill_names = ", ".join([s.name for s in runtime.loaded_skills])
                compressed_history.append({
                    "role": "assistant",
                    "content": f"[Loaded Skills] {skill_names}",
                    "is_metadata": True,
                })

            compressed_history.extend(messages_to_keep)
            runtime.conversation_history = compressed_history

            return (
                f"Context compressed: kept last {keep_n} messages, "
                f"summarized {len(messages_to_summarize)} messages"
            )

        except Exception as e:
            runtime.conversation_history = messages_to_keep
            return f"Context compressed (fallback): kept last {keep_n} messages only (summary failed: {e})"

    def _build_summary_input(self, messages: List[Dict[str, Any]]) -> str:
        """Build input for summary generation from messages."""
        lines = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "tool" or not content:
                continue
            if role == "assistant" and msg.get("tool_calls"):
                lines.append(f"Assistant: {content} [used tools]")
            else:
                lines.append(f"{role.capitalize()}: {content}")
        return "\n".join(lines)

    async def process_a_message(self, runtime: AgentRuntime, role: str, content: str, **kwargs):
        """Process a message: add to history and update last_active."""
        self._add_message(runtime, role, content, **kwargs)
        runtime.update_last_active()
        if self._should_compress(runtime):
            await self.compress_context(runtime)

    def build_messages(self, runtime: AgentRuntime, skill_library: SkillLibrary) -> List[Dict[str, Any]]:
        """Build complete message list including system prompt for API calls."""
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": runtime.system_prompt}
        ]
        messages.extend(runtime.conversation_history)
        return messages
