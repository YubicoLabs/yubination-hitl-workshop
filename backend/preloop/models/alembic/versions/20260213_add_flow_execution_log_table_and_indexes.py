"""Add flow_execution_log table and missing composite indexes.

Revision ID: 9a5b2c3d4e9p
Revises: 9a5b2c3d4e9o
Create Date: 2026-02-13

M1: Creates a normalized flow_execution_log table to replace the JSONB
    execution_logs column on flow_execution. Each log entry becomes a row,
    eliminating O(n) write amplification on append.

M2: Adds missing composite indexes on high-volume tables based on
    observed query patterns in CRUD layer.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e9p"
down_revision: Union[str, None] = "9a5b2c3d4e9o"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- M1: Create flow_execution_log table ---
    op.create_table(
        "flow_execution_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "execution_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("flow_execution.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("log_type", sa.String(50), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime, server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_flow_execution_log_execution_id", "flow_execution_log", ["execution_id"]
    )
    op.create_index(
        "ix_flow_execution_log_exec_ts",
        "flow_execution_log",
        ["execution_id", "timestamp"],
    )

    # --- M2: Missing composite indexes on high-volume tables ---

    # flow_execution: queries filter by (flow_id, status) and (status) for active executions
    op.create_index(
        "ix_flow_execution_flow_status",
        "flow_execution",
        ["flow_id", "status"],
    )
    op.create_index(
        "ix_flow_execution_active_status",
        "flow_execution",
        ["status"],
        postgresql_where=sa.text(
            "status IN ('RUNNING','PENDING','INITIALIZING','STARTING')"
        ),
    )

    # event: queries filter by (account_id, event_type) ordered by timestamp
    op.create_index(
        "ix_event_account_type_ts",
        "event",
        ["account_id", "event_type", sa.text("timestamp DESC")],
    )

    # api_usage: queries filter by (user_id) ordered by timestamp
    op.create_index(
        "ix_api_usage_user_ts",
        "api_usage",
        ["user_id", sa.text("timestamp DESC")],
    )

    # audit_log: queries filter by (account_id, action) ordered by timestamp
    op.create_index(
        "ix_audit_log_account_action_ts",
        "audit_log",
        ["account_id", "action", sa.text("timestamp DESC")],
    )


def downgrade() -> None:
    # Drop composite indexes
    op.drop_index("ix_audit_log_account_action_ts", table_name="audit_log")
    op.drop_index("ix_api_usage_user_ts", table_name="api_usage")
    op.drop_index("ix_event_account_type_ts", table_name="event")
    op.drop_index("ix_flow_execution_active_status", table_name="flow_execution")
    op.drop_index("ix_flow_execution_flow_status", table_name="flow_execution")

    # Drop flow_execution_log table
    op.drop_index("ix_flow_execution_log_exec_ts", table_name="flow_execution_log")
    op.drop_index("ix_flow_execution_log_execution_id", table_name="flow_execution_log")
    op.drop_table("flow_execution_log")
