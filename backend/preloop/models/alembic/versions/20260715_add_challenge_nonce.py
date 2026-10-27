"""add challenge_nonce to webauthn_challenge_session (ticket 09)

Stores the 32-byte random nonce used to derive
challenge = SHA-256(intent_hash_bytes || nonce), enabling
independent audit verification that the YubiKey signature was
bound to the exact tool call rather than a bare random nonce.

Revision ID: 20260715_add_challenge_nonce
Revises: 20260713_webauthn_tables
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_add_challenge_nonce"
down_revision: Union[str, None] = "20260713_webauthn_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "webauthn_challenge_session",
        sa.Column("challenge_nonce", sa.LargeBinary(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("webauthn_challenge_session", "challenge_nonce")
