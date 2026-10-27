"""Add normalized runtime-session activity records.

Revision ID: 20260310_rt_session_act
Revises: 20260310_managed_agents
Create Date: 2026-03-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260310_rt_session_act"
down_revision: Union[str, None] = "20260310_managed_agents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_session_activity",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flow_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activity_type", sa.String(length=50), nullable=False),
        sa.Column("server_name", sa.String(length=255), nullable=True),
        sa.Column("tool_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_key.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["flow_execution_id"], ["flow_execution.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["runtime_session_id"], ["runtime_session.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_runtime_session_activity_account_id"),
        "runtime_session_activity",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_session_activity_runtime_session_id"),
        "runtime_session_activity",
        ["runtime_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_session_activity_flow_execution_id"),
        "runtime_session_activity",
        ["flow_execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_session_activity_api_key_id"),
        "runtime_session_activity",
        ["api_key_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_session_activity_activity_type"),
        "runtime_session_activity",
        ["activity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_runtime_session_activity_timestamp"),
        "runtime_session_activity",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_runtime_session_activity_timestamp"),
        table_name="runtime_session_activity",
    )
    op.drop_index(
        op.f("ix_runtime_session_activity_activity_type"),
        table_name="runtime_session_activity",
    )
    op.drop_index(
        op.f("ix_runtime_session_activity_api_key_id"),
        table_name="runtime_session_activity",
    )
    op.drop_index(
        op.f("ix_runtime_session_activity_flow_execution_id"),
        table_name="runtime_session_activity",
    )
    op.drop_index(
        op.f("ix_runtime_session_activity_runtime_session_id"),
        table_name="runtime_session_activity",
    )
    op.drop_index(
        op.f("ix_runtime_session_activity_account_id"),
        table_name="runtime_session_activity",
    )
    op.drop_table("runtime_session_activity")
