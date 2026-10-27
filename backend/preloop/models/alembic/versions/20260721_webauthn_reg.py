"""Add webauthn_registration_session table.

Revision ID: 20260721_webauthn_reg
Revises: 20260720_add_mds_columns
Create Date: 2026-07-21

Replaces the process-local _REG_SESSIONS dict in webauthn_registration.py with
a DB-backed table so that register_begin and register_complete can land on
different Gunicorn workers or container replicas without losing the fido2 state.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260721_webauthn_reg"
down_revision: Union[str, Sequence[str], None] = "20260720_add_mds_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webauthn_registration_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_webauthn_reg_session_expires_at",
        "webauthn_registration_session",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webauthn_reg_session_expires_at")
    op.drop_table("webauthn_registration_session")
