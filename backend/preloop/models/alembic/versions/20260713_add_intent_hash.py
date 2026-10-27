"""Add intent_hash_hex to approval_request.

Revision ID: 20260713_add_intent_hash
Revises: 20260713_add_step_up_fields
Create Date: 2026-07-13
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260713_add_intent_hash"
down_revision: Union[str, None] = "20260713_add_step_up_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_request",
        sa.Column(
            "intent_hash_hex",
            sa.String(64),
            nullable=True,
            comment=(
                "SHA-256 hex digest of the RFC 8785 JCS-canonicalized intent envelope "
                "(account_id, approval_request_id, tool_name, tool_args, requested_at). "
                "Null for requests created before this migration."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "intent_hash_hex")
