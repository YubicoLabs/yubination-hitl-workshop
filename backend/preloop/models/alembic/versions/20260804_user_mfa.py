"""Add user.require_mfa_login column for per-user 2FA toggle.

Revision ID: 20260804_user_mfa
Revises: 20260729_rdt_envelope
Create Date: 2026-08-04

Adds a boolean column to the user table to control whether WebAuthn
multi-factor authentication is required at login. Defaults to FALSE
for backward compatibility — existing users can continue using
password-only login until they explicitly enable 2FA in settings.

When TRUE, users must complete WebAuthn ceremony after password
verification. This affects login flow only — approval step-ups
remain mandatory regardless of this setting.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_user_mfa"
down_revision: Union[str, Sequence[str], None] = "adb0618ccd87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column with default FALSE for backward compatibility
    op.add_column(
        "user",
        sa.Column(
            "require_mfa_login",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="When true, user must complete WebAuthn ceremony after password verification",
        ),
    )

    # Create index for query optimization (filtering users by MFA requirement)
    op.create_index(
        "ix_user_require_mfa_login",
        "user",
        ["require_mfa_login"],
    )


def downgrade() -> None:
    # Drop index first, then column
    op.drop_index("ix_user_require_mfa_login", table_name="user")
    op.drop_column("user", "require_mfa_login")
