"""
Interaction layer for kagent.

This module provides the interaction management layer that sits between
channels and the agent core. It handles:
- Multi-session management
- Hook command dispatching
- Session persistence
"""

from kagent.interaction.manager import InteractionManager, ChannelAdapter
from kagent.interaction.hook import HookDispatcher

__all__ = [
    "InteractionManager",
    "ChannelAdapter",
    "HookDispatcher",
]
