"""
Skill system for kagent - Prompt templates with metadata.
"""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Skill:
    """A skill is a prompt template with metadata."""

    name: str
    description: str
    content: str


class SkillLibrary:
    """Manages loading of skills from .agent/skills/ directory."""

    SKILL_FILE = "SKILL.md"
    DEFAULT_SKILLS_DIR = ".agent/skills"

    def __init__(self, skills_dir: Optional[str] = None, auto_load: bool = True):
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
        """Get a skill by name."""
        return self._skills.get(name)

    def has_skill(self, name: str) -> bool:
        """Check if a skill with the given name exists."""
        return name in self._skills

    def get_all_skills(self) -> List[Skill]:
        """Get all loaded skills."""
        return list(self._skills.values())

    def _parse_skill_file(self, file_path: Path) -> Optional[Skill]:
        """Parse a SKILL.md file with YAML frontmatter."""
        content = file_path.read_text(encoding="utf-8")

        pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        match = re.match(pattern, content, re.DOTALL)

        if not match:
            name = file_path.parent.name
            return Skill(
                name=name,
                description=f"Skill from {name}",
                content=content.strip(),
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
        )
