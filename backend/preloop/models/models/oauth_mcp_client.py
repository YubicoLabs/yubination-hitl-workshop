"""OAuth MCP Client model for Dynamic Client Registration (RFC 7591)."""

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base


class OAuthMCPClient(Base):
    """Stores dynamically registered MCP OAuth clients.

    Each MCP client (e.g., Claude Desktop, CLI) registers itself via
    POST /mcp/register and receives a client_id + client_secret.

    Attributes:
        id: UUID primary key (inherited from Base).
        client_id: Unique OAuth client identifier (generated on registration).
        client_secret_hash: SHA-256 hash of the client secret.
        client_secret_expires_at: When the client secret expires (0 = never).
        redirect_uris: JSON array of registered redirect URIs.
        grant_types: JSON array of allowed grant types.
        response_types: JSON array of allowed response types.
        token_endpoint_auth_method: Auth method for the token endpoint.
        client_name: Human-readable client name.
        scope: Space-separated list of allowed scopes.
        client_uri: URL of the client's home page.
        logo_uri: URL of the client's logo.
        contacts: JSON array of contact emails.
        software_id: Unique identifier for the client software.
        software_version: Version of the client software.
        client_id_issued_at: Unix timestamp when client_id was issued.
    """

    __tablename__ = "oauth_mcp_client"

    client_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    client_secret_hash: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    client_secret_expires_at: Mapped[Optional[int]] = mapped_column(
        nullable=True, default=0
    )
    redirect_uris: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    grant_types: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: ["authorization_code", "refresh_token"]
    )
    response_types: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: ["code"]
    )
    token_endpoint_auth_method: Mapped[str] = mapped_column(
        String(50), nullable=False, default="client_secret_post"
    )
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_uri: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    logo_uri: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    contacts: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    software_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    software_version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    client_id_issued_at: Mapped[Optional[int]] = mapped_column(nullable=True)
