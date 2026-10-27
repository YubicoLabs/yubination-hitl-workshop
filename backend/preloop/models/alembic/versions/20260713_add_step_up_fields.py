"""add step_up fields to approval_request and action_class to approval_workflow

Revision ID: 20260713_add_step_up_fields
Revises: 20260713_webauthn_tables
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260713_add_step_up_fields"
down_revision: Union[str, None] = "20260713_webauthn_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # approval_workflow: add action_class (nullable, zero-downtime)
    op.add_column(
        "approval_workflow",
        sa.Column("action_class", sa.String(50), nullable=True),
    )

    # approval_request: add step-up fields (all have defaults, zero-downtime)
    op.add_column(
        "approval_request",
        sa.Column(
            "step_up_required",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "step_up_verified",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "step_up_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "approval_request",
        sa.Column("step_up_key_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "approval_request",
        sa.Column("step_up_key_id_tail", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "step_up_key_id_tail")
    op.drop_column("approval_request", "step_up_key_name")
    op.drop_column("approval_request", "step_up_verified_at")
    op.drop_column("approval_request", "step_up_verified")
    op.drop_column("approval_request", "step_up_required")
    op.drop_column("approval_workflow", "action_class")
