"""Add assertion bytes to approval_request for audit re-verification (ticket 12).

Stores the four fields written by step_up_complete so the verify endpoint
can replay the FIDO2 ceremony server-side without the hardware key present.

Revision ID: 20260715_add_assertion_bytes
Revises: 20260713_step_up_protocol
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_add_assertion_bytes"
down_revision: Union[str, None] = "20260713_step_up_protocol"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "approval_request",
        sa.Column("step_up_challenge_nonce", sa.LargeBinary(32), nullable=True),
    )
    op.add_column(
        "approval_request",
        sa.Column("step_up_client_data_json", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "approval_request",
        sa.Column("step_up_authenticator_data", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "approval_request",
        sa.Column("step_up_signature", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "step_up_signature")
    op.drop_column("approval_request", "step_up_authenticator_data")
    op.drop_column("approval_request", "step_up_client_data_json")
    op.drop_column("approval_request", "step_up_challenge_nonce")
