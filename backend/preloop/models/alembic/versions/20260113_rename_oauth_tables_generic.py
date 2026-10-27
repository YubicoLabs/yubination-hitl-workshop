"""rename_oauth_tables_generic

Revision ID: 9a5b2c3d4e7g
Revises: 9a5b2c3d4e6f
Create Date: 2026-01-13

Renames GitHub-specific OAuth tables to generic names for multi-provider support:
- github_app_installation -> oauth_app_installation (with provider column)
- github_oauth_token -> oauth_token (with provider column)
- tracker.github_installation_id -> tracker.oauth_installation_id
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e7g"
down_revision: Union[str, None] = "9a5b2c3d4e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename tables and columns to generic OAuth names."""

    # Rename github_app_installation table to oauth_app_installation
    op.rename_table("github_app_installation", "oauth_app_installation")

    # Add provider column to oauth_app_installation
    op.add_column(
        "oauth_app_installation",
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
            server_default="github",
            comment="OAuth provider: 'github', 'gitlab', etc.",
        ),
    )
    op.create_index(
        op.f("ix_oauth_app_installation_provider"),
        "oauth_app_installation",
        ["provider"],
        unique=False,
    )

    # Rename columns in oauth_app_installation
    op.alter_column(
        "oauth_app_installation",
        "installation_id",
        new_column_name="external_id",
        comment="Provider's installation/application ID",
    )
    op.alter_column(
        "oauth_app_installation",
        "target_login",
        new_column_name="target_name",
        comment="Organization/user/group name or login",
    )
    op.alter_column(
        "oauth_app_installation",
        "repository_selection",
        new_column_name="resource_selection",
        comment="Resource selection mode: 'all', 'selected', etc.",
    )
    op.alter_column(
        "oauth_app_installation",
        "selected_repositories",
        new_column_name="selected_resources",
        comment="List of selected resource IDs if selection='selected'",
    )

    # Add provider_metadata column
    op.add_column(
        "oauth_app_installation",
        sa.Column(
            "provider_metadata",
            sa.JSON(),
            nullable=True,
            comment="Additional provider-specific metadata",
        ),
    )

    # Rename indexes for oauth_app_installation
    op.drop_index(
        "ix_github_app_installation_account_id",
        table_name="oauth_app_installation",
    )
    op.drop_index(
        "ix_github_app_installation_installation_id",
        table_name="oauth_app_installation",
    )
    op.create_index(
        op.f("ix_oauth_app_installation_account_id"),
        "oauth_app_installation",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_app_installation_external_id"),
        "oauth_app_installation",
        ["external_id"],
        unique=False,
    )

    # Rename github_oauth_token table to oauth_token
    op.rename_table("github_oauth_token", "oauth_token")

    # Add provider column to oauth_token
    op.add_column(
        "oauth_token",
        sa.Column(
            "provider",
            sa.String(length=50),
            nullable=False,
            server_default="github",
            comment="OAuth provider: 'github', 'gitlab', etc.",
        ),
    )
    op.create_index(
        op.f("ix_oauth_token_provider"),
        "oauth_token",
        ["provider"],
        unique=False,
    )

    # Rename indexes for oauth_token
    op.drop_index("ix_github_oauth_token_account_id", table_name="oauth_token")
    op.drop_index("ix_github_oauth_token_installation_id", table_name="oauth_token")
    op.drop_index("ix_github_oauth_token_user_id", table_name="oauth_token")
    op.create_index(
        op.f("ix_oauth_token_account_id"),
        "oauth_token",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_token_installation_id"),
        "oauth_token",
        ["installation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_oauth_token_user_id"),
        "oauth_token",
        ["user_id"],
        unique=False,
    )

    # Update foreign key reference in oauth_token
    op.drop_constraint(
        "github_oauth_token_installation_id_fkey",
        "oauth_token",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_oauth_token_installation",
        "oauth_token",
        "oauth_app_installation",
        ["installation_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Rename tracker column
    op.drop_constraint("fk_tracker_github_installation", "tracker", type_="foreignkey")
    op.drop_index("ix_tracker_github_installation_id", table_name="tracker")
    op.alter_column(
        "tracker",
        "github_installation_id",
        new_column_name="oauth_installation_id",
        comment="Reference to OAuth App installation for oauth_app auth type",
    )
    op.create_index(
        op.f("ix_tracker_oauth_installation_id"),
        "tracker",
        ["oauth_installation_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_tracker_oauth_installation",
        "tracker",
        "oauth_app_installation",
        ["oauth_installation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Revert table and column renames."""

    # Revert tracker column
    op.drop_constraint("fk_tracker_oauth_installation", "tracker", type_="foreignkey")
    op.drop_index("ix_tracker_oauth_installation_id", table_name="tracker")
    op.alter_column(
        "tracker",
        "oauth_installation_id",
        new_column_name="github_installation_id",
        comment="Reference to GitHub App installation for github_app auth type",
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
        "oauth_app_installation",
        ["github_installation_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Revert oauth_token to github_oauth_token
    op.drop_constraint("fk_oauth_token_installation", "oauth_token", type_="foreignkey")
    op.drop_index("ix_oauth_token_provider", table_name="oauth_token")
    op.drop_index("ix_oauth_token_account_id", table_name="oauth_token")
    op.drop_index("ix_oauth_token_installation_id", table_name="oauth_token")
    op.drop_index("ix_oauth_token_user_id", table_name="oauth_token")
    op.drop_column("oauth_token", "provider")
    op.create_index(
        op.f("ix_github_oauth_token_account_id"),
        "oauth_token",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_oauth_token_installation_id"),
        "oauth_token",
        ["installation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_oauth_token_user_id"),
        "oauth_token",
        ["user_id"],
        unique=False,
    )
    op.rename_table("oauth_token", "github_oauth_token")
    op.create_foreign_key(
        "github_oauth_token_installation_id_fkey",
        "github_oauth_token",
        "oauth_app_installation",
        ["installation_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Revert oauth_app_installation to github_app_installation
    op.drop_constraint("fk_tracker_github_installation", "tracker", type_="foreignkey")
    op.drop_index(
        "ix_oauth_app_installation_provider", table_name="oauth_app_installation"
    )
    op.drop_index(
        "ix_oauth_app_installation_account_id", table_name="oauth_app_installation"
    )
    op.drop_index(
        "ix_oauth_app_installation_external_id", table_name="oauth_app_installation"
    )
    op.drop_column("oauth_app_installation", "provider")
    op.drop_column("oauth_app_installation", "provider_metadata")
    op.alter_column(
        "oauth_app_installation",
        "external_id",
        new_column_name="installation_id",
        comment="GitHub's installation ID",
    )
    op.alter_column(
        "oauth_app_installation",
        "target_name",
        new_column_name="target_login",
        comment="GitHub organization or user login name",
    )
    op.alter_column(
        "oauth_app_installation",
        "resource_selection",
        new_column_name="repository_selection",
        comment="Repository selection: 'all' or 'selected'",
    )
    op.alter_column(
        "oauth_app_installation",
        "selected_resources",
        new_column_name="selected_repositories",
        comment="List of selected repository IDs if selection='selected'",
    )
    op.create_index(
        op.f("ix_github_app_installation_account_id"),
        "oauth_app_installation",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_github_app_installation_installation_id"),
        "oauth_app_installation",
        ["installation_id"],
        unique=True,
    )
    op.rename_table("oauth_app_installation", "github_app_installation")
    op.create_foreign_key(
        "fk_tracker_github_installation",
        "tracker",
        "github_app_installation",
        ["github_installation_id"],
        ["id"],
        ondelete="SET NULL",
    )
