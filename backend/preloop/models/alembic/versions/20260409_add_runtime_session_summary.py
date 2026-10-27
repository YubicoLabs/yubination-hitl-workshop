"""add runtime session summary

Revision ID: 20260409_session_summary
Revises: 20260408_price_override_terms
Create Date: 2026-04-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260409_session_summary"
down_revision: Union[str, None] = "20260408_price_override_terms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Store optional model-generated session summaries."""
    op.add_column(
        "runtime_session",
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "runtime_session",
        sa.Column("summary_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove optional model-generated session summaries."""
    op.drop_column("runtime_session", "summary_updated_at")
    op.drop_column("runtime_session", "summary")
