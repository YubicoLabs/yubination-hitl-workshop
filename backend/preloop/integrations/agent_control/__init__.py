"""Preloop agent-control integration kit for external runtimes."""

from preloop.integrations.agent_control.adapters import (
    HermesAgentControlAdapter,
    HookedAgentControlAdapter,
    OpenClawAgentControlAdapter,
    create_hermes_agent_control_client,
    create_openclaw_agent_control_client,
    load_agent_control_config,
    load_hermes_control_config,
    load_openclaw_control_config,
)
from preloop.integrations.agent_control.core import (
    AgentControlCapabilities,
    AgentControlClient,
    AgentControlConfig,
    AgentControlResult,
    AgentControlRuntimeHooks,
    OperatorCommand,
    dispatch_operator_command,
)

__all__ = [
    "AgentControlCapabilities",
    "AgentControlClient",
    "AgentControlConfig",
    "AgentControlResult",
    "AgentControlRuntimeHooks",
    "HermesAgentControlAdapter",
    "HookedAgentControlAdapter",
    "OpenClawAgentControlAdapter",
    "create_hermes_agent_control_client",
    "create_openclaw_agent_control_client",
    "OperatorCommand",
    "dispatch_operator_command",
    "load_agent_control_config",
    "load_hermes_control_config",
    "load_openclaw_control_config",
]
