"""Preloop plugin system.

This package provides the plugin architecture for extending Preloop
with custom evaluators, workflows, and integrations.
"""

from .base import (
    ConditionEvaluatorPlugin,
    Plugin,
    PluginManager,
    PluginMetadata,
    RouterConfig,
    WorkflowOrchestratorPlugin,
    get_plugin_manager,
    reset_plugin_manager,
)

__all__ = [
    "Plugin",
    "PluginMetadata",
    "RouterConfig",
    "ConditionEvaluatorPlugin",
    "WorkflowOrchestratorPlugin",
    "PluginManager",
    "get_plugin_manager",
    "reset_plugin_manager",
]
