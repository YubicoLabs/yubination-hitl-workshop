"""Add ARKG columns for previewSign showcase.

Revision ID: 20260717_add_arkg_columns
Revises: 20260715_add_assertion_bytes, 20260715_add_challenge_nonce
Create Date: 2026-07-17

Merges both existing heads and adds:
- user_webauthn_credential: arkg_seed_pub_cbor, arkg_derived_pk, arkg_seed_kh,
                            arkg_derived_kh, arkg_protocol
- approval_request:         arkg_step_up_signature, arkg_step_up_verified
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260717_add_arkg_columns"
down_revision: Union[str, Sequence[str], None] = (
    "20260715_add_assertion_bytes",
    "20260715_add_challenge_nonce",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_webauthn_credential",
        sa.Column("arkg_seed_pub_cbor", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column("arkg_derived_pk", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column("arkg_seed_kh", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column("arkg_derived_kh", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column("arkg_protocol", sa.String(32), nullable=True),
    )

    op.add_column(
        "approval_request",
        sa.Column("arkg_step_up_signature", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "approval_request",
        sa.Column(
            "arkg_step_up_verified",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("approval_request", "arkg_step_up_verified")
    op.drop_column("approval_request", "arkg_step_up_signature")

    op.drop_column("user_webauthn_credential", "arkg_protocol")
    op.drop_column("user_webauthn_credential", "arkg_derived_kh")
    op.drop_column("user_webauthn_credential", "arkg_seed_kh")
    op.drop_column("user_webauthn_credential", "arkg_derived_pk")
    op.drop_column("user_webauthn_credential", "arkg_seed_pub_cbor")
