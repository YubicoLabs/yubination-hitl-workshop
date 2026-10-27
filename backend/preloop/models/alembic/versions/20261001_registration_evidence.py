"""Retain accepted registration protocol evidence with its credential."""

from alembic import op
import sqlalchemy as sa

revision = "20261001_registration_evidence"
down_revision = "20261001_discovery_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_webauthn_credential",
        sa.Column("registration_evidence", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_webauthn_credential", "registration_evidence")
