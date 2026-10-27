"""Add step_up_sign_count to approval_request.

Revision ID: 20260720_step_up_sign_count
Revises: 20260720_arkg_step_up_derived_pk
Create Date: 2026-07-20

Stores the authenticator sign count observed at step-up time for inclusion
in the ConsumptionReceipt. CISOs use the sign counter to detect potential
credential cloning: an unexpected counter regression is a FIDO2 security alert.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_step_up_sign_count"
down_revision: Union[str, Sequence[str], None] = "20260720_arkg_step_up_derived_pk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approval_request",
        sa.Column(
            "step_up_sign_count",
            sa.Integer(),
            nullable=True,
            comment=(
                "Authenticator sign counter at the time of step-up; "
                "stored for clone-detection in the audit receipt"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "step_up_sign_count")
