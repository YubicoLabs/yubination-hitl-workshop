"""Pydantic schemas for MCP tool definitions."""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class MCPToolBase(BaseModel):
    """Base schema for MCP tool definition."""

    name: Optional[str] = Field(None, description="Tool name")
    description: Optional[str] = Field(None, description="Tool description")
    input_schema: Optional[Dict[str, Any]] = Field(
        None, description="JSON schema defining tool input parameters"
    )


class MCPToolCreate(MCPToolBase):
    """Schema for creating an MCP tool."""

    name: str
    input_schema: Dict[str, Any]
    mcp_server_id: str
    discovered_at: str


class MCPToolUpdate(MCPToolBase):
    """Schema for updating an MCP tool."""

    pass


class MCPToolResponse(MCPToolBase):
    """Schema for MCP tool response."""

    id: str
    mcp_server_id: str
    name: str
    input_schema: Dict[str, Any]
    discovered_at: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
