"""Add start_time index to flow_execution for ORDER BY performance.

Revision ID: 9a5b2c3d4e9l
Revises: 9a5b2c3d4e9k
Create Date: 2026-02-02

Adds index on start_time column which is used for ORDER BY in common queries.
This significantly improves performance of the /api/v1/flows/executions endpoint.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e9l"
down_revision: Union[str, None] = "9a5b2c3d4e9k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add index on start_time for ORDER BY performance."""
    # Index on start_time (used for ORDER BY start_time DESC)
    op.create_index(
        "ix_flow_execution_start_time",
        "flow_execution",
        ["start_time"],
        unique=False,
    )


def downgrade() -> None:
    """Remove start_time index."""
    op.drop_index(
        "ix_flow_execution_start_time",
        table_name="flow_execution",
    )
