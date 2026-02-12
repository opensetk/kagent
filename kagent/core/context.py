"""
Context module for kagent - manages conversation history and token compression.
"""

from typing import List, Dict, Any, Optional, Callable
import tiktoken

from kagent.core.skill import SkillManager, Skill


class ContextManager:
    """
    Manages conversation history with token tracking and automatic compression.

    This class handles all message storage, token counting using OpenAI's official
    tiktoken library, and triggers compression when token count exceeds threshold.
    """

    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        max_tokens: int = 100000,
        compression_callback: Optional[Callable[[str], None]] = None,
        system_prompt: Optional[str] = None,
        skill_manager: Optional[SkillManager] = None,
    ):
        """
        Initialize ContextManager.

        Args:
            model: OpenAI model name for token encoding
            max_tokens: Maximum token threshold before compression
            compression_callback: Optional callback function when compression is triggered
            system_prompt: Optional custom system prompt (overrides KAGENT.md)
            skill_manager: Optional SkillManager for loading skills into prompt
        """
        self.model = model
        self.max_tokens = max_tokens
        self.compression_callback = compression_callback
        self.conversation_history: List[Dict[str, Any]] = []

        # Load system prompt
        self.base_system_prompt = system_prompt or self._load_system_prompt()
        self.system_prompt = self.base_system_prompt

        # Initialize tokenizer
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            # Fallback to cl100k_base for unknown models
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        # Skill manager for loading skills
        self.skill_manager = skill_manager
        self._loaded_skills: List[Skill] = []

    def _load_system_prompt(self) -> str:
        """
        Load system prompt from KAGENT.md file or use default.

        Returns:
            System prompt string
        """
        import os

        kagent_md_path = "KAGENT.md"
        default_prompt = (
            "You are a helpful AI assistant with access to tools for file operations "
            "and command execution. Use tools when appropriate to help the user."
        )

        if os.path.exists(kagent_md_path):
            try:
                with open(kagent_md_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return content
            except Exception as e:
                print(f"Warning: Failed to read {kagent_md_path}: {e}")

        return default_prompt

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """
        Add a message to the conversation history.

        Args:
            role: Message role (user, assistant, tool, etc.)
            content: Message content
            **kwargs: Additional message fields (tool_calls, tool_call_id, name, etc.)
        """
        message = {"role": role, "content": content}
        message.update(kwargs)
        self.conversation_history.append(message)

        # Check if compression is needed
        if self.should_compress():
            self.compress_context()

    def load_skill(self, skill_name: str) -> bool:
        """
        Load a skill into the system prompt.
        
        Args:
            skill_name: Name of the skill to load
            
        Returns:
            True if skill was loaded successfully
        """
        if not self.skill_manager:
            return False
        
        skill = self.skill_manager.get_skill(skill_name)
        if not skill:
            return False
        
        # Add to loaded skills
        if skill not in self._loaded_skills:
            self._loaded_skills.append(skill)
            self._rebuild_system_prompt()
            return True
        
        return False
    
    def unload_skill(self, skill_name: str) -> bool:
        """
        Unload a skill from the system prompt.
        
        Args:
            skill_name: Name of the skill to unload
            
        Returns:
            True if skill was unloaded
        """
        self._loaded_skills = [s for s in self._loaded_skills if s.name != skill_name]
        self._rebuild_system_prompt()
        return True
    
    def clear_skills(self) -> None:
        """Clear all loaded skills from the system prompt."""
        self._loaded_skills = []
        self._rebuild_system_prompt()
    
    def list_loaded_skills(self) -> List[str]:
        """Get names of currently loaded skills."""
        return [s.name for s in self._loaded_skills]
    
    def _rebuild_system_prompt(self) -> None:
        """Rebuild system prompt with loaded skills."""
        if not self._loaded_skills:
            self.system_prompt = self.base_system_prompt
            return
        
        parts = [self.base_system_prompt, "\n# Loaded Skills\n"]
        
        for skill in self._loaded_skills:
            parts.append(f"\n## {skill.name}\n{skill.content}\n")
        
        self.system_prompt = "\n".join(parts)

    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Get complete message list including system prompt for API calls.

        Returns:
            List of messages ready for OpenAI API
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        messages.extend(self.conversation_history)
        return messages

    def set_system_prompt(self, prompt: str) -> None:
        """Set the system prompt."""
        self.base_system_prompt = prompt
        self._rebuild_system_prompt()

    def clear_history(self, keep_system: bool = True) -> None:
        """
        Clear conversation history.

        Args:
            keep_system: If True, preserves system context
        """
        self.conversation_history = []

    def count_tokens(self) -> int:
        """
        Count total tokens in conversation history using OpenAI's tiktoken.

        Returns:
            Total token count
        """
        total_tokens = 0

        for message in self.conversation_history:
            # Count tokens for each message
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
        return self.count_tokens() > self.max_tokens

    def compress_context(self) -> None:
        """
        Compress conversation history when token limit is exceeded.
        """
        token_count = self.count_tokens()
        self.clear_history()

        message = (
            f"Context compression triggered: cleared {token_count} tokens "
            f"(exceeded {self.max_tokens} threshold)"
        )

        if self.compression_callback:
            self.compression_callback(message)
        else:
            print(f"[ContextManager] {message}")

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get raw conversation history.

        Returns:
            List of conversation messages
        """
        return self.conversation_history.copy()

    def set_max_tokens(self, max_tokens: int) -> None:
        """
        Update the maximum token threshold.

        Args:
            max_tokens: New token threshold
        """
        self.max_tokens = max_tokens

    async def compress_history(self, llm_client) -> str:
        """
        Compress conversation history by summarizing it using LLM.

        Args:
            llm_client: LLM client instance for generating summary

        Returns:
            Status message
        """
        if not self.conversation_history:
            return "History is empty, nothing to compress."

        from kagent.llm.base import LLMResponse

        summary_prompt = "Please summarize the following conversation history concisely:"
        messages = [{"role": "system", "content": summary_prompt}]
        messages.extend(self.conversation_history)

        response: LLMResponse = await llm_client.complete(messages)

        if response.content:
            self.clear_history()
            self.add_message("assistant", f"Previous conversation summary: {response.content}")
            return "History compressed successfully."
        else:
            return "Failed to compress history."
