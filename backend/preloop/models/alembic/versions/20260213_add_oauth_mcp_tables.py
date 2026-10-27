"""add_oauth_mcp_tables

Revision ID: 9a5b2c3d4e9o
Revises: 9a5b2c3d4e9m
Create Date: 2026-02-13

Adds tables for MCP OAuth 2.1 Authorization Server:
- oauth_mcp_client: Dynamically registered OAuth clients (RFC 7591)
- oauth_mcp_authorization_code: Authorization codes (short-lived)
- oauth_mcp_access_token: Issued access tokens (hashed)
- oauth_mcp_refresh_token: Issued refresh tokens (hashed)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e9o"
down_revision: Union[str, None] = "9a5b2c3d4e9m"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create OAuth MCP tables."""

    # oauth_mcp_client — Dynamic Client Registration
    op.create_table(
        "oauth_mcp_client",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("client_secret_hash", sa.String(255), nullable=True),
        sa.Column(
            "client_secret_expires_at", sa.Integer(), nullable=True, server_default="0"
        ),
        sa.Column(
            "redirect_uris", postgresql.JSON(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "grant_types",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default='["authorization_code", "refresh_token"]',
        ),
        sa.Column(
            "response_types",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default='["code"]',
        ),
        sa.Column(
            "token_endpoint_auth_method",
            sa.String(50),
            nullable=False,
            server_default="client_secret_post",
        ),
        sa.Column("client_name", sa.String(255), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("client_uri", sa.String(2048), nullable=True),
        sa.Column("logo_uri", sa.String(2048), nullable=True),
        sa.Column("contacts", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("software_id", sa.String(255), nullable=True),
        sa.Column("software_version", sa.String(255), nullable=True),
        sa.Column("client_id_issued_at", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oauth_mcp_client_id", "oauth_mcp_client", ["id"], unique=False)
    op.create_index(
        "ix_oauth_mcp_client_client_id", "oauth_mcp_client", ["client_id"], unique=True
    )

    # oauth_mcp_authorization_code
    op.create_table(
        "oauth_mcp_authorization_code",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("redirect_uri", sa.String(2048), nullable=False),
        sa.Column(
            "redirect_uri_provided_explicitly",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("code_challenge", sa.String(255), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("resource", sa.String(2048), nullable=True),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oauth_mcp_auth_code_id",
        "oauth_mcp_authorization_code",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_oauth_mcp_auth_code_hash",
        "oauth_mcp_authorization_code",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_mcp_auth_code_client_id",
        "oauth_mcp_authorization_code",
        ["client_id"],
        unique=False,
    )

    # oauth_mcp_access_token
    op.create_table(
        "oauth_mcp_access_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("resource", sa.String(2048), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oauth_mcp_access_token_id", "oauth_mcp_access_token", ["id"], unique=False
    )
    op.create_index(
        "ix_oauth_mcp_access_token_hash",
        "oauth_mcp_access_token",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_mcp_access_token_client_id",
        "oauth_mcp_access_token",
        ["client_id"],
        unique=False,
    )

    # oauth_mcp_refresh_token
    op.create_table(
        "oauth_mcp_refresh_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("expires_at", sa.Integer(), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oauth_mcp_refresh_token_id", "oauth_mcp_refresh_token", ["id"], unique=False
    )
    op.create_index(
        "ix_oauth_mcp_refresh_token_hash",
        "oauth_mcp_refresh_token",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_oauth_mcp_refresh_token_client_id",
        "oauth_mcp_refresh_token",
        ["client_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop OAuth MCP tables."""

    # Drop refresh token table
    op.drop_index(
        "ix_oauth_mcp_refresh_token_client_id", table_name="oauth_mcp_refresh_token"
    )
    op.drop_index(
        "ix_oauth_mcp_refresh_token_hash", table_name="oauth_mcp_refresh_token"
    )
    op.drop_index("ix_oauth_mcp_refresh_token_id", table_name="oauth_mcp_refresh_token")
    op.drop_table("oauth_mcp_refresh_token")

    # Drop access token table
    op.drop_index(
        "ix_oauth_mcp_access_token_client_id", table_name="oauth_mcp_access_token"
    )
    op.drop_index("ix_oauth_mcp_access_token_hash", table_name="oauth_mcp_access_token")
    op.drop_index("ix_oauth_mcp_access_token_id", table_name="oauth_mcp_access_token")
    op.drop_table("oauth_mcp_access_token")

    # Drop authorization code table
    op.drop_index(
        "ix_oauth_mcp_auth_code_client_id", table_name="oauth_mcp_authorization_code"
    )
    op.drop_index(
        "ix_oauth_mcp_auth_code_hash", table_name="oauth_mcp_authorization_code"
    )
    op.drop_index(
        "ix_oauth_mcp_auth_code_id", table_name="oauth_mcp_authorization_code"
    )
    op.drop_table("oauth_mcp_authorization_code")

    # Drop client table
    op.drop_index("ix_oauth_mcp_client_client_id", table_name="oauth_mcp_client")
    op.drop_index("ix_oauth_mcp_client_id", table_name="oauth_mcp_client")
    op.drop_table("oauth_mcp_client")
