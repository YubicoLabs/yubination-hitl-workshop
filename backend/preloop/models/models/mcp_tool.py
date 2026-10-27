"""MCPTool model for storing cached tools from external MCP servers."""

import uuid
from typing import TYPE_CHECKING, Dict, Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .mcp_server import MCPServer


class MCPTool(Base):
    """
    Stores cached tool definitions from external MCP servers.

    When an external MCP server is scanned, its available tools are cached
    in this table. This allows for fast tool listing without repeatedly
    querying the external server.
    """

    __tablename__ = "mcp_tool"

    # Foreign key to MCP server
    mcp_server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_server.id"), nullable=False, index=True
    )

    # Tool definition
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_schema: Mapped[Dict] = mapped_column(JSONB, nullable=False)

    # Discovery tracking
    discovered_at: Mapped[str] = mapped_column(String, nullable=False)

    # Relationships
    mcp_server: Mapped["MCPServer"] = relationship(back_populates="tools")

    def __repr__(self):
        return f"<MCPTool(id={self.id}, name='{self.name}', server_id={self.mcp_server_id})>"
