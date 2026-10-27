"""Preserve provenance of browser-reported discoverability."""

from alembic import op
import sqlalchemy as sa

revision = "20261001_discovery_source"
down_revision = "20261001_credential_discoverable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_webauthn_credential",
        sa.Column("discoverability_source", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_webauthn_credential", "discoverability_source")
