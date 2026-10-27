"""add_flow_execution_retry_tracking

Revision ID: 9a5b2c3d4e9j
Revises: 9a5b2c3d4e9i
Create Date: 2026-01-27

Adds retry tracking to flow executions:
- retry_of_execution_id: Links to the original execution this is a retry of
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e9j"
down_revision: Union[str, None] = "9a5b2c3d4e9i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retry_of_execution_id column to flow_execution table."""
    # Add retry_of_execution_id with foreign key to flow_execution.id
    op.add_column(
        "flow_execution",
        sa.Column(
            "retry_of_execution_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_flow_execution_retry_of_execution_id",
        "flow_execution",
        "flow_execution",
        ["retry_of_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_flow_execution_retry_of_execution_id"),
        "flow_execution",
        ["retry_of_execution_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove retry_of_execution_id column from flow_execution table."""
    op.drop_index(
        op.f("ix_flow_execution_retry_of_execution_id"),
        table_name="flow_execution",
    )
    op.drop_constraint(
        "fk_flow_execution_retry_of_execution_id",
        "flow_execution",
        type_="foreignkey",
    )
    op.drop_column("flow_execution", "retry_of_execution_id")
