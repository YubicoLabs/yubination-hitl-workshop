"""Tool implementations for Preloop."""

from preloop.tools.base import MCPToolContext

__all__ = [
    "MCPToolContext",
]

import importlib

# Discover and register tools
import pkgutil

# Importing the tool modules will register them via the decorator
for _, name, _ in pkgutil.iter_modules(__path__, f"{__name__}."):
    importlib.import_module(name)
