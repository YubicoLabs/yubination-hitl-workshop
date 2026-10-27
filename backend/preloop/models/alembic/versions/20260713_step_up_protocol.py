"""Add step_up_protocol to approval_workflow.

Revision ID: 20260713_step_up_protocol
Revises: 20260713_add_intent_hash
Create Date: 2026-07-13
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260713_step_up_protocol"
down_revision: Union[str, None] = "20260713_add_intent_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_workflow",
        sa.Column(
            "step_up_protocol",
            sa.String(50),
            nullable=True,
            comment=(
                "Step-up protocol required before approval on this workflow. "
                "NULL means no step-up. "
                "Valid values: webauthn_discoverable, webauthn_sign, piv."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("approval_workflow", "step_up_protocol")
