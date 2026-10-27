"""Add WebAuthn login sessions, rate-limit table, and credential BE/BS/UV columns.

Revision ID: 20260723_add_webauthn_login
Revises: 20260721_webauthn_reg
Create Date: 2026-07-23

Adds three things needed for WebAuthn-backed passwordless login and 2FA:
1. webauthn_login_session  — ephemeral session for the login ceremony
2. webauthn_login_rate_limit — DB-backed fixed-window IP/user rate limiter
3. backup_eligible / backup_state / uv_initialized on user_webauthn_credential
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260723_add_webauthn_login"
down_revision: Union[str, Sequence[str], None] = "20260721_webauthn_reg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. webauthn_login_session
    op.create_table(
        "webauthn_login_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column(
            "account_id", postgresql.UUID(as_uuid=True), nullable=True, index=True
        ),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="passwordless"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        "ix_webauthn_login_session_expires_at",
        "webauthn_login_session",
        ["expires_at"],
    )

    # 2. webauthn_login_rate_limit
    op.create_table(
        "webauthn_login_rate_limit",
        sa.Column("namespace", sa.String(8), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("namespace", "key_hash"),
    )

    # 3. Backup eligibility / state flags on user_webauthn_credential
    op.add_column(
        "user_webauthn_credential",
        sa.Column("backup_eligible", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column("backup_state", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column("uv_initialized", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_webauthn_credential", "uv_initialized")
    op.drop_column("user_webauthn_credential", "backup_state")
    op.drop_column("user_webauthn_credential", "backup_eligible")
    op.drop_index("ix_webauthn_login_session_expires_at")
    op.drop_table("webauthn_login_session")
    op.drop_table("webauthn_login_rate_limit")
