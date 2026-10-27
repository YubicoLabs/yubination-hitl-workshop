"""add_github_app_oauth_tables

Revision ID: 9a5b2c3d4e6f
Revises: 8f4a1b2c3d5e
Create Date: 2026-01-13

Adds tables for GitHub App OAuth integration:
- github_app_installation: Stores GitHub App installations per account
- github_oauth_token: Stores encrypted OAuth tokens for user authentication
- Adds auth_type and github_installation_id columns to tracker table
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e6f"
down_revision: Union[str, None] = "8f4a1b2c3d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create GitHub App OAuth tables and update tracker table."""

    # Create github_app_installation table
    op.create_table(
        "github_app_installation",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "installation_id",
            sa.BigInteger(),
            nullable=False,
            comment="GitHub's installation ID",
        ),
        sa.Column(
            "target_type",
            sa.String(length=50),
            nullable=False,
            comment="Type of target: 'Organization' or 'User'",
        ),
        sa.Column(
            "target_id",
            sa.BigInteger(),
            nullable=False,
            comment="GitHub organization or user ID",
        ),
        sa.Column(
            "target_login",
            sa.String(length=255),
            nullable=False,
            comment="GitHub organization or user login name",
        ),
        sa.Column(
            "permissions",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="Permissions granted to this installation",
        ),
        sa.Column(
            "repository_selection",
            sa.String(length=50),
            nullable=True,
            comment="Repository selection: 'all' or 'selected'",
        ),
        sa.Column(
            "selected_repositories",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            comment="List of selected repository IDs if selection='selected'",
        ),
        sa.Column(
            "suspended_at",
            sa.DateTime(),
            nullable=True,
            comment="Timestamp when installation was suspended, if any",
        ),
        sa.Column(
            "suspended_by",
            sa.String(length=255),
            nullable=True,
            comment="GitHub username who suspended the installation",
        ),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("installation_id"),
    )
    op.create_index(
        op.f("ix_github_app_installation_account_id"),
        "github_app_installation",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_installation_installation_id"),
        "github_app_installation",
        ["installation_id"],
        unique=True,
    )

    # Create github_oauth_token table
    op.create_table(
        "github_oauth_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "access_token_encrypted",
            sa.Text(),
            nullable=False,
            comment="Encrypted access token",
        ),
        sa.Column(
            "refresh_token_encrypted",
            sa.Text(),
            nullable=True,
            comment="Encrypted refresh token",
        ),
        sa.Column(
            "token_type",
            sa.String(length=50),
            nullable=False,
            server_default="bearer",
            comment="Token type (usually 'bearer')",
        ),
        sa.Column(
            "scope",
            sa.Text(),
            nullable=True,
            comment="OAuth scopes granted to this token",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=True,
            comment="When the access token expires",
        ),
        sa.Column(
            "refresh_token_expires_at",
            sa.DateTime(),
            nullable=True,
            comment="When the refresh token expires",
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"],
            ["github_app_installation.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_github_oauth_token_account_id"),
        "github_oauth_token",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_oauth_token_installation_id"),
        "github_oauth_token",
        ["installation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_oauth_token_user_id"),
        "github_oauth_token",
        ["user_id"],
        unique=False,
    )

    # Add columns to tracker table
    op.add_column(
        "tracker",
        sa.Column(
            "auth_type",
            sa.String(length=50),
            nullable=False,
            server_default="api_token",
            comment="Authentication type: 'api_token' or 'github_app'",
        ),
    )
    op.add_column(
        "tracker",
        sa.Column(
            "github_installation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Reference to GitHub App installation for github_app auth type",
        ),
    )
    op.create_index(
        op.f("ix_tracker_github_installation_id"),
        "tracker",
        ["github_installation_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_tracker_github_installation",
        "tracker",
        "github_app_installation",
        ["github_installation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Drop GitHub App OAuth tables and revert tracker table changes."""

    # Remove foreign key and columns from tracker table
    op.drop_constraint("fk_tracker_github_installation", "tracker", type_="foreignkey")
    op.drop_index(op.f("ix_tracker_github_installation_id"), table_name="tracker")
    op.drop_column("tracker", "github_installation_id")
    op.drop_column("tracker", "auth_type")

    # Drop github_oauth_token table
    op.drop_index(
        op.f("ix_github_oauth_token_user_id"), table_name="github_oauth_token"
    )
    op.drop_index(
        op.f("ix_github_oauth_token_installation_id"), table_name="github_oauth_token"
    )
    op.drop_index(
        op.f("ix_github_oauth_token_account_id"), table_name="github_oauth_token"
    )
    op.drop_table("github_oauth_token")

    # Drop github_app_installation table
    op.drop_index(
        op.f("ix_github_app_installation_installation_id"),
        table_name="github_app_installation",
    )
    op.drop_index(
        op.f("ix_github_app_installation_account_id"),
        table_name="github_app_installation",
    )
    op.drop_table("github_app_installation")
