"""Add durable managed-agent credentials and enrollment state.

Revision ID: 20260311_managed_agent_identity
Revises: 20260311_agent_lifecycle
Create Date: 2026-03-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260311_managed_agent_identity"
down_revision: Union[str, None] = "20260311_agent_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "managed_agent_credential",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("managed_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("credential_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("key_prefix", sa.String(length=16), nullable=True),
        sa.Column("last_issued_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["managed_agent_id"], ["managed_agent.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_key.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "managed_agent_id",
            "name",
            name="uq_managed_agent_credential_name",
        ),
        sa.UniqueConstraint("api_key_id", name="uq_managed_agent_credential_api_key"),
    )
    op.create_index(
        op.f("ix_managed_agent_credential_account_id"),
        "managed_agent_credential",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_credential_managed_agent_id"),
        "managed_agent_credential",
        ["managed_agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_credential_api_key_id"),
        "managed_agent_credential",
        ["api_key_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_credential_created_by_user_id"),
        "managed_agent_credential",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_credential_id"),
        "managed_agent_credential",
        ["id"],
        unique=False,
    )

    op.create_table(
        "managed_agent_enrollment",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("managed_agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("enrollment_type", sa.String(length=64), nullable=False),
        sa.Column("adapter_key", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("target_config_path", sa.String(length=512), nullable=True),
        sa.Column(
            "discovered_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "managed_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "backup_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "validation_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "restore_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_applied_at", sa.DateTime(), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(), nullable=True),
        sa.Column("last_restored_at", sa.DateTime(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["managed_agent_id"], ["managed_agent.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_managed_agent_enrollment_account_id"),
        "managed_agent_enrollment",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_enrollment_managed_agent_id"),
        "managed_agent_enrollment",
        ["managed_agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_enrollment_created_by_user_id"),
        "managed_agent_enrollment",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_enrollment_id"),
        "managed_agent_enrollment",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_managed_agent_enrollment_id"), table_name="managed_agent_enrollment"
    )
    op.drop_index(
        op.f("ix_managed_agent_enrollment_created_by_user_id"),
        table_name="managed_agent_enrollment",
    )
    op.drop_index(
        op.f("ix_managed_agent_enrollment_managed_agent_id"),
        table_name="managed_agent_enrollment",
    )
    op.drop_index(
        op.f("ix_managed_agent_enrollment_account_id"),
        table_name="managed_agent_enrollment",
    )
    op.drop_table("managed_agent_enrollment")

    op.drop_index(
        op.f("ix_managed_agent_credential_id"), table_name="managed_agent_credential"
    )
    op.drop_index(
        op.f("ix_managed_agent_credential_created_by_user_id"),
        table_name="managed_agent_credential",
    )
    op.drop_index(
        op.f("ix_managed_agent_credential_api_key_id"),
        table_name="managed_agent_credential",
    )
    op.drop_index(
        op.f("ix_managed_agent_credential_managed_agent_id"),
        table_name="managed_agent_credential",
    )
    op.drop_index(
        op.f("ix_managed_agent_credential_account_id"),
        table_name="managed_agent_credential",
    )
    op.drop_table("managed_agent_credential")
