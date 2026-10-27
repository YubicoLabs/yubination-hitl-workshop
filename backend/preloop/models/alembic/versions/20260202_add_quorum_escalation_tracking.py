"""Add quorum and escalation tracking fields to approval_request.

Revision ID: 9a5b2c3d4e9k
Revises: 9a5b2c3d4e9j
Create Date: 2026-02-02

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9a5b2c3d4e9k"
down_revision: Union[str, None] = "9a5b2c3d4e9j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add responses column for quorum vote tracking
    op.add_column(
        "approval_request",
        sa.Column(
            "responses",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Individual approval/decline responses for quorum tracking",
        ),
    )

    # Add escalation_triggered_at column for escalation tracking
    op.add_column(
        "approval_request",
        sa.Column(
            "escalation_triggered_at",
            sa.DateTime(),
            nullable=True,
            comment="When escalation was triggered (if applicable)",
        ),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "escalation_triggered_at")
    op.drop_column("approval_request", "responses")
