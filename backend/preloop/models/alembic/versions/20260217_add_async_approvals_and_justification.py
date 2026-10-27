"""add_async_approvals_and_justification

Revision ID: 9a5b2c3d4e9q
Revises: 9a5b2c3d4e9p
Create Date: 2026-02-17

Adds:
- approval_event table for detailed workflow event tracking
- async_approval_enabled column to approval_policy
- justification_mode column to tool_configuration
- tool_result column to approval_request (for async mode caching)
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9a5b2c3d4e9q"
down_revision: Union[str, None] = "9a5b2c3d4e9p"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add async approvals and justification features."""

    # Create approval_event table
    op.create_table(
        "approval_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
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
            ["approval_request_id"],
            ["approval_request.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_approval_event_approval_request_id",
        "approval_event",
        ["approval_request_id"],
    )
    op.create_index(
        "ix_approval_event_account_id",
        "approval_event",
        ["account_id"],
    )
    op.create_index(
        "ix_approval_event_event_type",
        "approval_event",
        ["event_type"],
    )
    op.create_index(
        "ix_approval_event_timestamp",
        "approval_event",
        ["timestamp"],
    )

    # Add async_approval_enabled to approval_policy
    op.add_column(
        "approval_policy",
        sa.Column(
            "async_approval_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="When enabled, tool calls return immediately and agents poll for status",
        ),
    )

    # Add justification_mode to tool_configuration
    op.add_column(
        "tool_configuration",
        sa.Column(
            "justification_mode",
            sa.String(20),
            nullable=True,
            comment="Justification parameter mode: null/disabled, optional, or required",
        ),
    )

    # Add tool_result to approval_request (for caching async execution output)
    op.add_column(
        "approval_request",
        sa.Column(
            "tool_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Cached result of tool execution after approval (for async mode)",
        ),
    )


def downgrade() -> None:
    """Remove async approvals and justification features."""
    op.drop_column("approval_request", "tool_result")
    op.drop_column("tool_configuration", "justification_mode")
    op.drop_column("approval_policy", "async_approval_enabled")
    op.drop_index("ix_approval_event_timestamp", "approval_event")
    op.drop_index("ix_approval_event_event_type", "approval_event")
    op.drop_index("ix_approval_event_account_id", "approval_event")
    op.drop_index("ix_approval_event_approval_request_id", "approval_event")
    op.drop_table("approval_event")
