"""Add FIDO MDS snapshot columns to user_webauthn_credential.

Revision ID: 20260720_add_mds_columns
Revises: 20260720_rate_limit_table
Create Date: 2026-07-20

Stores a per-credential snapshot of FIDO MDS metadata captured at registration
time: human-readable authenticator description, key-protection type string, and
icon data URI. Avoids live MDS network calls in the audit UI and receipt endpoint.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_add_mds_columns"
down_revision: Union[str, Sequence[str], None] = "20260720_rate_limit_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_webauthn_credential",
        sa.Column(
            "mds_description",
            sa.Text(),
            nullable=True,
            comment="Authenticator model name from FIDO MDS metadataStatement.description",
        ),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column(
            "mds_key_protection",
            sa.Text(),
            nullable=True,
            comment="Comma-joined keyProtection list from FIDO MDS (e.g. 'hardware,tee')",
        ),
    )
    op.add_column(
        "user_webauthn_credential",
        sa.Column(
            "mds_icon",
            sa.Text(),
            nullable=True,
            comment="Base64 data URI icon from FIDO MDS metadataStatement.icon (may be large)",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_webauthn_credential", "mds_icon")
    op.drop_column("user_webauthn_credential", "mds_key_protection")
    op.drop_column("user_webauthn_credential", "mds_description")
