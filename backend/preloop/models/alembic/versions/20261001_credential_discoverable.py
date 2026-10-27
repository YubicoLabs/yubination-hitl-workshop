"""Record nullable browser-reported credential discoverability."""

from alembic import op
import sqlalchemy as sa

revision = "20261001_credential_discoverable"
down_revision = "20260930_retire_webauthn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_webauthn_credential",
        sa.Column("discoverable", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_webauthn_credential", "discoverable")
