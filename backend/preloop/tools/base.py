"""Base classes for MCP tools in Preloop."""

from typing import Any, Dict, Set, TypeVar

from pydantic import BaseModel, Field


# Stub implementation for removed MCP dependencies
class Context:
    """Stub implementation of MCP Context."""

    def __init__(self, *args, **kwargs):
        pass


class EmbeddedResource:
    """Stub implementation of MCP EmbeddedResource."""

    def __init__(self, *args, **kwargs):
        pass


class ImageContent:
    """Stub implementation of MCP ImageContent."""

    def __init__(self, *args, **kwargs):
        pass


class TextContent:
    """Stub implementation of MCP TextContent."""

    def __init__(self, *args, **kwargs):
        pass


# Redefine types for back-compatibility during migration
MCPToolContext = Context

# TypeVar for tool implementations
T = TypeVar("T", bound="BaseModel")


class MCPToolMetadata(BaseModel):
    """Metadata about an MCP tool (for backward compatibility)."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    required_parameters: Set[str] = Field(
        default_factory=set, description="Required parameters for the tool"
    )
    optional_parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Optional parameters with default values"
    )


class ToolResult(BaseModel):
    """Base class for tool results."""

    pass
