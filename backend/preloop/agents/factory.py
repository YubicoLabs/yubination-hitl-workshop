"""Factory for creating agent executors."""

import logging
from typing import Any, Dict

from .base import AgentExecutor
from .openhands import OpenHandsAgent
from .aider import AiderAgent
from .codex import CodexAgent
from .gemini import GeminiAgent
from .opencode import OpenCodeAgent

logger = logging.getLogger(__name__)


def create_agent_executor(agent_type: str, config: Dict[str, Any]) -> AgentExecutor:
    """
    Create an agent executor based on agent type.

    Args:
        agent_type: Type of agent (e.g., 'openhands', 'aider', 'codex', 'gemini')
        config: Agent-specific configuration

    Returns:
        AgentExecutor instance for the specified agent type

    Raises:
        ValueError: If agent_type is not supported
    """
    agent_type_lower = agent_type.lower()

    if agent_type_lower == "openhands":
        return OpenHandsAgent(config)
    elif agent_type_lower == "aider":
        return AiderAgent(config)
    elif agent_type_lower == "codex":
        return CodexAgent(config)
    elif agent_type_lower == "gemini":
        return GeminiAgent(config)
    elif agent_type_lower == "opencode":
        return OpenCodeAgent(config)
    else:
        raise ValueError(
            f"Unsupported agent type: {agent_type}. "
            f"Supported types: codex, gemini, opencode, aider, openhands"
        )
