"""
Configuration module for kagent - manages agent settings and defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class AgentConfig:
    """
    Configuration for the agent.
    
    Loads from environment variables with sensible defaults.
    """
    # Model settings
    model: str = field(default_factory=lambda: os.getenv("KAGENT_MODEL", "gpt-4o"))
    
    # Token management
    max_tokens: int = field(default_factory=lambda: int(os.getenv("KAGENT_MAX_TOKENS", "200000")))
    ratio_of_compress: float = field(default_factory=lambda: float(os.getenv("KAGENT_COMPRESS_RATIO", "0.7")))
    keep_last_n_messages: int = field(default_factory=lambda: int(os.getenv("KAGENT_KEEP_LAST_N", "3")))
    
    # Paths
    work_dir: str = field(default_factory=lambda: os.getenv("KAGENT_WORK_DIR", "./workspace/"))
    skills_dir: str = field(default_factory=lambda: os.getenv("KAGENT_SKILLS_DIR", ".agent/skills"))
    sessions_dir: str = field(default_factory=lambda: os.getenv("KAGENT_SESSIONS_DIR", "sessions"))
    system_prompt_path: str = field(default_factory=lambda: os.getenv("KAGENT_SYSTEM_PROMPT", "./workspace/KAGENT.md"))
    
    # Compression settings
    compression_model: Optional[str] = field(default_factory=lambda: os.getenv("KAGENT_COMPRESSION_MODEL"))
    
    def __post_init__(self):
        """Validate and normalize configuration."""
        # Ensure work_dir is absolute
        self.work_dir = str(Path(self.work_dir).resolve())
        
        # Validate ratio
        if not 0 < self.ratio_of_compress < 1:
            self.ratio_of_compress = 0.7
        
        # Validate keep_last_n_messages
        if self.keep_last_n_messages < 1:
            self.keep_last_n_messages = 3


def load_config() -> AgentConfig:
    """Load configuration from environment variables."""
    return AgentConfig()
