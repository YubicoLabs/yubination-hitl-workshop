"""add webauthn credential and challenge session tables

Revision ID: 20260713_webauthn_tables
Revises: 20260409_session_summary
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260713_webauthn_tables"
down_revision: Union[str, None] = "20260409_session_summary"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_webauthn_credential",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False, unique=True),
        sa.Column("public_key_cbor", sa.LargeBinary(), nullable=False),
        sa.Column("aaguid", sa.LargeBinary(16), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_user_webauthn_credential_account_id",
        "user_webauthn_credential",
        ["account_id"],
    )
    op.create_index(
        "ix_user_webauthn_credential_user_id", "user_webauthn_credential", ["user_id"]
    )

    op.create_table(
        "webauthn_challenge_session",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "account_id",
            UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approval_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("approval_request.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fido2_state", sa.LargeBinary(), nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
    )
    op.create_index(
        "ix_webauthn_challenge_session_account_id",
        "webauthn_challenge_session",
        ["account_id"],
    )
    op.create_index(
        "ix_webauthn_challenge_session_approval_request_id",
        "webauthn_challenge_session",
        ["approval_request_id"],
    )


def downgrade() -> None:
    op.drop_table("webauthn_challenge_session")
    op.drop_table("user_webauthn_credential")
