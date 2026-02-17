"""
Model Preset System for LLM Configuration.

Provides a way to define and load model presets with:
- Preset name
- Model name
- Base URL
- API Key (direct or from env var)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import os
import json


@dataclass
class ModelPreset:
    """
    Model preset configuration.
    
    Attributes:
        name: Preset name (e.g., "deepseek", "gpt4")
        model: Model name (e.g., "deepseek-chat", "gpt-4o")
        base_url: API base URL (optional)
        api_key: API key directly (optional)
        api_key_env: Environment variable name for API key (fallback)
        provider: Provider type ("openai" or "claude")
        extra: Extra provider-specific options
    """
    name: str
    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None
    provider: str = "openai"
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def get_api_key(self) -> Optional[str]:
        """Get API key from direct value or environment variable."""
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.getenv(self.api_key_env)
        return None
    
    def to_llm_kwargs(self) -> Dict[str, Any]:
        """Convert to kwargs for LLMClient.from_env()."""
        kwargs = {
            "model": self.model,
            "provider_type": self.provider,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
        api_key = self.get_api_key()
        if api_key:
            kwargs["api_key"] = api_key
        kwargs.update(self.extra)
        return kwargs


class PresetManager:
    """
    Manages model presets.
    
    Usage:
        # Load from default location
        manager = PresetManager.load()
        
        # Get a preset
        preset = manager.get("deepseek")
        
        # Use with LLMClient
        client = LLMClient.from_preset(preset)
    """
    
    DEFAULT_PRESETS: Dict[str, ModelPreset] = {
        "deepseek": ModelPreset(
            name="deepseek",
            model="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            provider="openai",
        ),
        "deepseek-reasoner": ModelPreset(
            name="deepseek-reasoner",
            model="deepseek-reasoner",
            base_url="https://api.deepseek.com/v1",
            api_key_env="DEEPSEEK_API_KEY",
            provider="openai",
        ),
        "gpt4o": ModelPreset(
            name="gpt4o",
            model="gpt-4o",
            base_url=None,
            api_key_env="OPENAI_API_KEY",
            provider="openai",
        ),
        "gpt4o-mini": ModelPreset(
            name="gpt4o-mini",
            model="gpt-4o-mini",
            base_url=None,
            api_key_env="OPENAI_API_KEY",
            provider="openai",
        ),
        "claude-sonnet": ModelPreset(
            name="claude-sonnet",
            model="claude-sonnet-4-20250514",
            base_url=None,
            api_key_env="ANTHROPIC_API_KEY",
            provider="claude",
        ),
        "claude-haiku": ModelPreset(
            name="claude-haiku",
            model="claude-3-5-haiku-20241022",
            base_url=None,
            api_key_env="ANTHROPIC_API_KEY",
            provider="claude",
        ),
    }
    
    def __init__(self, presets: Optional[Dict[str, ModelPreset]] = None):
        self.presets = presets or dict(self.DEFAULT_PRESETS)
    
    def get(self, name: str) -> Optional[ModelPreset]:
        """Get a preset by name."""
        return self.presets.get(name)
    
    def list(self) -> List[str]:
        """List all preset names."""
        return list(self.presets.keys())
    
    def add(self, preset: ModelPreset) -> None:
        """Add or update a preset."""
        self.presets[preset.name] = preset
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "PresetManager":
        """
        Load presets from config file.
        
        Args:
            config_path: Path to presets config file (JSON)
                        Default: ~/.kagent/presets.json or .agent/presets.json
        
        Returns:
            PresetManager instance
        """
        presets = dict(cls.DEFAULT_PRESETS)
        
        if config_path is None:
            home_config = Path.home() / ".kagent" / ".presets.json"
            local_config = Path(".agent/.presets.json")
            config_path = str(home_config) if home_config.exists() else str(local_config)
        
        path = Path(config_path)
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                for name, preset_data in data.get("presets", {}).items():
                    presets[name] = ModelPreset(
                        name=name,
                        model=preset_data.get("model", ""),
                        base_url=preset_data.get("base_url"),
                        api_key=preset_data.get("api_key"),
                        api_key_env=preset_data.get("api_key_env"),
                        provider=preset_data.get("provider", "openai"),
                        extra=preset_data.get("extra", {}),
                    )
            except Exception as e:
                print(f"Warning: Failed to load presets from {config_path}: {e}")
        
        return cls(presets)
    
    def save(self, config_path: Optional[str] = None) -> None:
        """Save presets to config file."""
        if config_path is None:
            config_path = str(Path.home() / ".kagent" / ".presets.json")
        
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "presets": {
                name: {
                    "model": p.model,
                    "base_url": p.base_url,
                    "api_key": p.api_key,
                    "api_key_env": p.api_key_env,
                    "provider": p.provider,
                    "extra": p.extra,
                }
                for name, p in self.presets.items()
            }
        }
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
