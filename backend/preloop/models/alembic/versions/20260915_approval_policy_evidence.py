"""Add server-recorded requester and matched-policy context.

Revision ID: 20260915_policy_evidence
Revises: 20260914_restore_login_limit
Create Date: 2026-09-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_policy_evidence"
down_revision: Union[str, Sequence[str], None] = "20260914_restore_login_limit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add nullable context; legacy rows deliberately remain unknown."""
    op.add_column(
        "approval_request",
        sa.Column(
            "server_recorded_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Requester and matched-policy context recorded at approval creation; "
                "not cryptographically bound to intent proofs"
            ),
        ),
    )


def downgrade() -> None:
    """Remove server-recorded context."""
    op.drop_column("approval_request", "server_recorded_context")
