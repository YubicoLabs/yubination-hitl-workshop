"""Add step_up_credential_id to approval_request.

Revision ID: 20260720_step_up_cred_id
Revises: 20260720_step_up_sign_count
Create Date: 2026-07-20

Stores the full credential_id bytes at step-up time so the receipt endpoint
can do a direct lookup instead of the probabilistic 8-character tail match.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_step_up_cred_id"
down_revision: Union[str, Sequence[str], None] = "20260720_step_up_sign_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approval_request",
        sa.Column(
            "step_up_credential_id",
            sa.LargeBinary(),
            nullable=True,
            comment="Full credential_id bytes of the authenticator used for step-up",
        ),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "step_up_credential_id")
