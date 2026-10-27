"""Add managed-agent lifecycle and ownership fields.

Revision ID: 20260311_agent_lifecycle
Revises: 20260310_rt_session_act
Create Date: 2026-03-11
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260311_agent_lifecycle"
down_revision: Union[str, None] = "20260310_rt_session_act"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "managed_agent",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "managed_agent",
        sa.Column(
            "lifecycle_state",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
    )
    op.add_column(
        "managed_agent",
        sa.Column("lifecycle_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "managed_agent",
        sa.Column("lifecycle_updated_at", sa.DateTime(), nullable=True),
    )
    op.execute(
        """
        UPDATE managed_agent
        SET lifecycle_updated_at = COALESCE(last_seen_at, created_at, now())
        """
    )
    op.alter_column("managed_agent", "lifecycle_updated_at", nullable=False)
    op.create_foreign_key(
        "fk_managed_agent_owner_user_id_user",
        "managed_agent",
        "user",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_managed_agent_owner_user_id"),
        "managed_agent",
        ["owner_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_managed_agent_owner_user_id"), table_name="managed_agent")
    op.drop_constraint(
        "fk_managed_agent_owner_user_id_user",
        "managed_agent",
        type_="foreignkey",
    )
    op.drop_column("managed_agent", "lifecycle_updated_at")
    op.drop_column("managed_agent", "lifecycle_reason")
    op.drop_column("managed_agent", "lifecycle_state")
    op.drop_column("managed_agent", "owner_user_id")
