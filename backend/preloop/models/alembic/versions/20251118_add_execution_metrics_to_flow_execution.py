"""add_execution_metrics_to_flow_execution

Revision ID: 58e4ca3de37b
Revises: a7421af76e5f
Create Date: 2025-11-18 15:16:41.942033

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "58e4ca3de37b"
down_revision: Union[str, None] = "a7421af76e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add execution metrics columns to flow_execution table."""
    # Add tool_calls_count column
    op.add_column(
        "flow_execution",
        sa.Column("tool_calls_count", sa.Integer(), nullable=True, server_default="0"),
    )

    # Add total_tokens column
    op.add_column(
        "flow_execution",
        sa.Column("total_tokens", sa.Integer(), nullable=True, server_default="0"),
    )

    # Add estimated_cost column
    op.add_column(
        "flow_execution",
        sa.Column(
            "estimated_cost",
            sa.Numeric(precision=10, scale=4),
            nullable=True,
            server_default="0.0",
        ),
    )


def downgrade() -> None:
    """Remove execution metrics columns from flow_execution table."""
    op.drop_column("flow_execution", "estimated_cost")
    op.drop_column("flow_execution", "total_tokens")
    op.drop_column("flow_execution", "tool_calls_count")
