"""Add managed-agent registry and account-scoped runtime session identity.

Revision ID: 20260310_managed_agents
Revises: 20260310_gateway_search_fts
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260310_managed_agents"
down_revision: Union[str, None] = "20260310_gateway_search_fts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_runtime_session_source", "runtime_session", type_="unique")
    op.create_unique_constraint(
        "uq_runtime_session_account_source",
        "runtime_session",
        ["account_id", "session_source_type", "session_source_id"],
    )

    op.create_table(
        "managed_agent",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_source_type", sa.String(length=64), nullable=False),
        sa.Column("session_source_id", sa.String(length=255), nullable=False),
        sa.Column("session_reference", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "enrolled_via",
            sa.String(length=64),
            nullable=False,
            server_default="runtime_session_token",
        ),
        sa.Column(
            "managed_mcp_servers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["runtime_session_id"], ["runtime_session.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "session_source_type",
            "session_source_id",
            name="uq_managed_agent_account_source",
        ),
    )
    op.create_index(
        op.f("ix_managed_agent_account_id"),
        "managed_agent",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_runtime_session_id"),
        "managed_agent",
        ["runtime_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_agent_id"),
        "managed_agent",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_managed_agent_id"), table_name="managed_agent")
    op.drop_index(
        op.f("ix_managed_agent_runtime_session_id"), table_name="managed_agent"
    )
    op.drop_index(op.f("ix_managed_agent_account_id"), table_name="managed_agent")
    op.drop_table("managed_agent")

    op.drop_constraint(
        "uq_runtime_session_account_source", "runtime_session", type_="unique"
    )
    op.create_unique_constraint(
        "uq_runtime_session_source",
        "runtime_session",
        ["session_source_type", "session_source_id"],
    )
