"""
Skill system for kagent - Prompt templates with metadata.

Skills are stored in .agent/skills/<skill-name>/SKILL.md with YAML frontmatter.
They provide specialized capabilities when loaded into the system prompt.

Example SKILL.md:
    ---
    name: ppt-expert
    description: Expert at creating presentations
    tags: [office, ppt]
    ---
    
    # PowerPoint Expert
    
    You are an expert at creating professional presentations...
"""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Skill:
    """A skill is a prompt template with metadata."""
    
    name: str
    description: str
    content: str
    path: Optional[Path] = None


class SkillManager:
    """
    Manages loading of skills from .agent/skills/ directory.
    """
    
    SKILL_FILE = "SKILL.md"
    DEFAULT_SKILLS_DIR = ".agent/skills"
    
    def __init__(self, skills_dir: Optional[str] = None, auto_load: bool = True):
        """
        Initialize SkillManager.
        
        Args:
            skills_dir: Directory containing skill folders
            auto_load: Whether to load skills on init
        """
        self.skills_dir = Path(skills_dir or self.DEFAULT_SKILLS_DIR)
        self._skills: Dict[str, Skill] = {}
        
        if auto_load:
            self.load_all()
    
    def load_all(self) -> List[Skill]:
        """Load all skills from the skills directory."""
        loaded = []
        
        if not self.skills_dir.exists():
            return loaded
        
        for skill_file in self.skills_dir.rglob(self.SKILL_FILE):
            try:
                skill = self._parse_skill_file(skill_file)
                if skill:
                    self._skills[skill.name] = skill
                    loaded.append(skill)
            except Exception as e:
                print(f"Warning: Failed to load skill from {skill_file}: {e}")
        
        return loaded
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """
        Get a skill by name.
        
        Args:
            name: Name of the skill
            
        Returns:
            Skill instance if found, None otherwise
        """
        return self._skills.get(name)
    
    def list_skills(self) -> List[Skill]:
        """List all loaded skills."""
        return list(self._skills.values())
    
    def list_skill_names(self) -> List[str]:
        """List names of all loaded skills."""
        return list(self._skills.keys())
    
    def _parse_skill_file(self, file_path: Path) -> Optional[Skill]:
        """Parse a SKILL.md file with YAML frontmatter."""
        content = file_path.read_text(encoding="utf-8")
        
        # Parse YAML frontmatter
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)
        
        if not match:
            # No frontmatter, use filename
            name = file_path.parent.name
            return Skill(
                name=name,
                description=f"Skill from {name}",
                content=content.strip(),
                path=file_path.parent,
            )
        
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
            markdown_content = match.group(2).strip()
        except Exception as e:
            print(f"Warning: Failed to parse {file_path}: {e}")
            return None
        
        name = frontmatter.get("name", file_path.parent.name)
        
        return Skill(
            name=name,
            description=frontmatter.get("description", "No description"),
            content=markdown_content,
            path=file_path.parent,
        )
