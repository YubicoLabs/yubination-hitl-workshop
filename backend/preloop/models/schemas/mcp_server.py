"""Pydantic schemas for MCP server configuration."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class MCPServerBase(BaseModel):
    """Base schema for MCP server configuration."""

    name: Optional[str] = Field(
        None, description="User-defined name for this MCP server"
    )
    url: Optional[str] = Field(None, description="URL of the external MCP server")
    transport: Optional[str] = Field(
        "http-streaming", description="Transport protocol (default: http-streaming)"
    )
    auth_type: Optional[str] = Field(
        "none",
        description="Authentication type: 'none', 'bearer', 'api_key', 'oauth'",
    )
    auth_config: Optional[Dict[str, Any]] = Field(
        None, description="JSON configuration for authentication"
    )
    status: Optional[str] = Field(
        "active", description="Server status: 'active', 'error', 'disabled'"
    )


class MCPServerCreate(MCPServerBase):
    """Schema for creating an MCP server.

    Note: account_id is not included here as it's extracted from
    the authenticated user in the endpoint handler.
    """

    name: str
    url: str


class MCPServerUpdate(MCPServerBase):
    """Schema for updating an MCP server."""

    pass


class MCPServerResponse(MCPServerBase):
    """Schema for MCP server response."""

    id: UUID
    account_id: UUID
    last_scan_at: Optional[str] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("id", "account_id")
    def serialize_uuids(self, value: UUID) -> str:
        """Serialize UUID fields to strings."""
        return str(value)
