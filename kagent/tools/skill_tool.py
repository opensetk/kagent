"""
Skill loading tools for kagent.

Skills are prompt templates with metadata (description, triggers, tags).
They are loaded into the system prompt when needed - either auto-detected
based on user input or manually activated.
"""

from typing import Optional
from kagent.core.tool import tool


@tool()
async def list_skills() -> str:
    """
    List all available skills that can be loaded.
    
    Skills are located in .agent/skills/<skill-name>/SKILL.md
    Each skill provides specialized capabilities when activated.
    """
    from kagent.core.skill import SkillManager
    
    manager = SkillManager(auto_load=True)
    skills = manager.list_skills()
    
    if not skills:
        return "No skills found. Create skills in .agent/skills/<name>/SKILL.md"
    
    lines = [f"Available skills ({len(skills)}):\n"]
    
    for skill in skills:
        lines.append(f"• {skill.name}")
        lines.append(f"  {skill.description}")
        if skill.tags:
            lines.append(f"  Tags: {', '.join(skill.tags)}")
        lines.append("")
    
    lines.append("Use 'use_skill' to activate a skill for this session.")
    return "\n".join(lines)


@tool(
    param_descriptions={
        "name": "Name of the skill to activate (e.g., 'ppt-expert')",
    }
)
async def use_skill(name: str) -> str:
    """
    Load and activate a skill for the current session.
    
    The skill's instructions will be added to the system prompt immediately,
    giving the agent specialized capabilities for this conversation.
    
    Example:
        use_skill(name="ppt-expert")  # For presentation creation help
        use_skill(name="code-reviewer")  # For code review assistance
    """
    from kagent.core.skill import SkillManager
    
    manager = SkillManager(auto_load=True)
    skill = manager.get_skill(name)
    
    if not skill:
        available = ", ".join(s.name for s in manager.list_skills())
        return f"Skill '{name}' not found.\n\nAvailable: {available or 'None'}"
    
    # Activate the skill
    if manager.activate_skill(name):
        # Update the context manager's active skills if available
        # This is handled through the skill manager's state
        return f"✅ Loaded skill: {skill.name}\n\n{skill.description}"
    
    return f"⚠️ Skill '{name}' is already active."
